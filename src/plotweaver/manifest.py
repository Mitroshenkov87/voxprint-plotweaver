"""Shared suite manifest, schema 1, via voxprint-common.

The file is ``shared/manifest.json``. Top-level keys are ``schema`` and
``components``. An older Plotweaver file (``version`` plus ``resources`` plus
``apps``) is migrated on first read. Other apps' refs are kept. Unknown keys
are kept. This module still deletes the bytes when the last ref leaves,
which the shared library does not do.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from voxprint_common.atomic import exclusive_lock, write_json
from voxprint_common.hashing import sha256_bytes, sha256_file
from voxprint_common.runtime_manifest import (
    ManifestError as CommonManifestError,
)
from voxprint_common.runtime_manifest import (
    add_ref,
    load,
    lock_path,
    remove_ref,
)

from plotweaver.errors import PlotweaverError

MANIFEST_NAME = "manifest.json"
APP_ID = "plotweaver"
_SHA = re.compile(r"^[a-f0-9]{64}$")


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
) -> None:
    """Record one component and add ``app`` to its refs."""
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
        )
    except CommonManifestError as exc:
        raise ManifestError(str(exc)) from exc
    _remember(target, resource_id, files, nbytes, source)


def unregister_app(shared: Path, app: str = APP_ID) -> list[str]:
    """Drop ``app``. Delete a component's files only when its refs become empty."""
    target = manifest_path(shared)
    if not target.is_file():
        return []
    stored = load_manifest(shared)
    removed: list[str] = []
    for key, resource in stored.items():
        if app not in resource.apps:
            continue
        if resource.refcount == 1:
            _delete_files(shared, resource)
            removed.append(key)
        try:
            remove_ref(key, app, manifest=target)
        except CommonManifestError as exc:
            raise ManifestError(str(exc)) from exc
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
        payload = json.loads(path.read_text(encoding="utf-8"))
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
    base = (shared / resource.path).resolve()
    root = shared.resolve()
    if base != root and root not in base.parents:
        raise ManifestError("a resource path must stay inside the shared folder")
    return base


def _delete_files(shared: Path, resource: Resource) -> None:
    base = _resource_dir(shared, resource)
    root = shared.resolve()
    if resource.kind == "runtime" and base != root and root in base.parents and base.is_dir():
        shutil.rmtree(base)
        return
    for name in resource.files:
        target = (base / name).resolve()
        if target != root and root not in target.parents:
            continue
        if target.is_file():
            target.unlink()
