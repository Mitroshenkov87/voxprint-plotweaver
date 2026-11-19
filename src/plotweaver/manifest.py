"""Shared suite manifest, schema 1, via voxprint-common.

The file is ``shared/manifest.json``. Top-level keys are ``schema`` and
``components``. An older Plotweaver file (``version`` plus ``resources`` plus
``apps``) is migrated on first read. Other apps' refs are kept. Unknown keys
are kept. A file is removed only after :func:`remove_ref` reports that this
app was the last ref. ``models/``, ``runtime/``, ``voices/``, ``cache/``, and
the suite home are never one component and are never deleted.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from voxprint_common.atomic import exclusive_lock, write_json
from voxprint_common.hashing import sha256_bytes, sha256_file
from voxprint_common.runtime_manifest import ManifestError as CommonManifestError
from voxprint_common.runtime_manifest import (
    _refuse_protected,
    add_ref,
    load,
    lock_path,
    remove_ref,
)

from plotweaver.errors import PlotweaverError
from plotweaver.paths import legacy_models_dir, models_dir, shared_dir, voxprint_home
from plotweaver.textio import read_text

MANIFEST_NAME = "manifest.json"
APP_ID = "plotweaver"
_SHA = re.compile(r"^[a-f0-9]{64}$")
_ROOT_NAMES = frozenset({"models", "runtime", "voices", "cache"})


class ManifestError(PlotweaverError):
    """The shared manifest could not be read or updated."""


@dataclass(frozen=True)
class Resource:
    """One shared file set, as Plotweaver's repair and uninstall still see it."""

    kind: str
    path: str
    nbytes: int
    files: dict[str, str]
    apps: tuple[str, ...]
    source: str = ""

    @property
    def refcount(self) -> int:
        """How many apps still use this resource."""
        return len(self.apps)


def manifest_path(shared: Path) -> Path:
    """``manifest.json`` inside the shared directory."""
    return shared / MANIFEST_NAME


def file_sha256(path: Path) -> str:
    """SHA-256 of one file, lowercase hex."""
    return sha256_file(path)


def load_manifest(shared: Path) -> dict[str, Resource]:
    """Resources in the manifest. A missing file is an empty map.

    A pre-schema-1 file is rewritten in place. Refs that belong to other apps
    stay on the component.
    """
    path = manifest_path(shared)
    if not path.is_file():
        return {}
    try:
        document = load(path)
    except CommonManifestError as exc:
        raise ManifestError(str(exc)) from exc
    resources: dict[str, Resource] = {}
    for key, component in document.components.items():
        files = component.extra.get("files")
        mapped = (
            {str(name): str(digest) for name, digest in files.items()}
            if isinstance(files, dict)
            else {}
        )
        raw_bytes = component.extra.get("bytes", component.extra.get("nbytes", 0))
        try:
            nbytes = int(raw_bytes) if isinstance(raw_bytes, int | float | str) else 0
        except ValueError:
            nbytes = 0
        source = component.extra.get("source", "")
        resources[str(key)] = Resource(
            kind=component.kind,
            path=component.path or ".",
            nbytes=nbytes,
            files=mapped,
            apps=tuple(component.refs),
            source=source if isinstance(source, str) else "",
        )
    return resources


def refuse_shared_delete(path: Path) -> None:
    """Raise when ``path`` is a shared root or an ancestor of one.

    Plotweaver's own list runs first. voxprint-common's guard then refuses a
    path ours missed. A file inside a root is still allowed.
    """
    target = path.resolve()
    for root in _shared_delete_roots():
        if target == root or target in root.parents:
            raise ManifestError(
                f"refusing to delete {path}: it is a shared root or an ancestor of one"
            )
    try:
        _refuse_protected(target, str(path))
    except CommonManifestError as exc:
        raise ManifestError(str(exc)) from exc


def register_resource(
    shared: Path,
    resource_id: str,
    *,
    kind: str,
    path: str,
    nbytes: int,
    files: dict[str, str],
    app: str = APP_ID,
    source: str = "",
    model_roots: tuple[Path, ...] = (),
) -> None:
    """Record one component and add ``app`` to its refs."""
    _refuse_component_path(shared, path)
    target = manifest_path(shared)
    digest = _digest(files)
    version = "1"
    if target.is_file():
        try:
            current = load(target).components.get(resource_id)
        except CommonManifestError as exc:
            raise ManifestError(str(exc)) from exc
        if current is not None and current.sha256 == digest:
            version = current.version or "1"
    try:
        add_ref(
            resource_id,
            app,
            kind=kind,
            version=version,
            path=path,
            sha256=digest,
            manifest=target,
            model_roots=model_roots,
        )
    except CommonManifestError as exc:
        raise ManifestError(str(exc)) from exc
    _remember(target, resource_id, files, nbytes, source)


def unregister_app(shared: Path, app: str = APP_ID) -> list[str]:
    """Drop ``app``. Delete a file only when ``remove_ref`` drops the component."""
    target = manifest_path(shared)
    if not target.is_file():
        return []
    stored = load_manifest(shared)
    removed: list[str] = []
    for key, resource in stored.items():
        if app not in resource.apps:
            continue
        try:
            gone = remove_ref(key, app, manifest=target)
        except CommonManifestError as exc:
            raise ManifestError(str(exc)) from exc
        if not gone:
            continue
        _delete_files(shared, resource)
        removed.append(key)
    return removed


def broken_files(shared: Path, resource: Resource) -> list[str]:
    """File names whose bytes are missing or do not match the recorded hash."""
    base = _resource_dir(shared, resource)
    broken: list[str] = []
    for name, digest in resource.files.items():
        path = base / name
        if not path.is_file():
            broken.append(name)
            continue
        try:
            found = file_sha256(path)
        except OSError:
            broken.append(name)
            continue
        if found != digest.lower():
            broken.append(name)
    return broken


def _digest(files: dict[str, str]) -> str:
    if len(files) == 1:
        only = str(next(iter(files.values()))).strip().lower()
        if _SHA.fullmatch(only):
            return only
    return sha256_bytes(json.dumps(files, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def _remember(
    path: Path,
    resource_id: str,
    files: dict[str, str],
    nbytes: int,
    source: str,
) -> None:
    with exclusive_lock(lock_path(path)):
        payload = json.loads(read_text(path))
        components = payload.get("components")
        if not isinstance(components, dict) or resource_id not in components:
            raise ManifestError(f"{resource_id} was not recorded")
        row = components[resource_id]
        if not isinstance(row, dict):
            raise ManifestError(f"{resource_id} is not an object")
        row["files"] = dict(files)
        row["bytes"] = nbytes
        if source:
            row["source"] = source
        write_json(path, payload)


def _resource_dir(shared: Path, resource: Resource) -> Path:
    raw = Path(resource.path)
    if raw.is_absolute():
        base = raw
    else:
        base = (shared / resource.path).resolve()
        root = shared.resolve()
        if base != root and root not in base.parents:
            raise ManifestError("a resource path must stay inside the shared folder")
    if raw.name in resource.files:
        return base.parent
    return base


def _inside(target: Path, root: Path) -> bool:
    return target == root or root in target.parents


def _shared_delete_roots() -> tuple[Path, ...]:
    home = voxprint_home().resolve()
    shared = shared_dir().resolve()
    found = [home, shared, models_dir().resolve(), legacy_models_dir().resolve()]
    for base in (home, shared):
        for name in _ROOT_NAMES:
            found.append(base / name)
    unique: list[Path] = []
    seen: set[str] = set()
    for item in found:
        key = os.path.normcase(str(item))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return tuple(unique)


def _refuse_component_path(shared: Path, path: str) -> None:
    text = path.strip().replace("\\", "/")
    if not text or text in {".", "./"}:
        raise ManifestError("a shared root cannot be one component")
    raw = Path(text)
    parts = raw.parts
    if parts and parts[0].casefold() in _ROOT_NAMES and len(parts) == 1:
        raise ManifestError("a shared root cannot be one component")
    target = raw if raw.is_absolute() else shared / raw
    refuse_shared_delete(target)


def _delete_files(shared: Path, resource: Resource) -> None:
    base = _resource_dir(shared, resource)
    refuse_shared_delete(base)
    root = shared.resolve()
    # ``base`` is not an allowed root. A manifest path outside the shared
    # folder and the models folder must not become a delete root.
    allowed = (root, models_dir().resolve())
    for name in resource.files:
        target = (base / name).resolve()
        refuse_shared_delete(target)
        if not any(_inside(target, folder) for folder in allowed):
            continue
        if target.is_dir():
            raise ManifestError("refusing to delete a directory in the shared tree")
        if target.is_file():
            target.unlink()
