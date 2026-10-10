"""Model registry, shared GGUF folder, and SHA-256 checks.

Weights live in `<models>/llm` (the suite folder Audiobook Builder uses).
Every entry records a confirmed base licence. Apache-2.0 and MIT are accepted.
An empty licence is refused, including with --allow-other-license, because an
untagged tune has nothing to record. Heretic is not a registry entry.
"""

from __future__ import annotations

import hashlib
import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

import httpx

from plotweaver.atomic import write_json
from plotweaver.errors import PlotweaverError
from plotweaver.paths import gguf_dir

APPROVED_LICENSES = {"apache-2.0", "mit"}
OPTIONAL_VRAM_GB = 20.0


@dataclass(frozen=True)
class RegistryEntry:
    id: str
    role: str
    repo: str
    filename: str
    sha256: str
    size: int
    license: str
    min_vram_gb: float
    context: int
    moe: bool
    notes: str
    revision: str = ""
    base_repo: str = ""
    base_revision: str = ""
    base_license: str = ""
    card: str = ""
    default: bool = False
    enabled: bool = True


def load_registry(path: Path) -> list[RegistryEntry]:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("model") or []
    if not isinstance(rows, list):
        raise PlotweaverError(f"{path} has no [[model]] entries")
    entries: list[RegistryEntry] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        entry = RegistryEntry(
            id=str(row["id"]),
            role=str(row.get("role") or "main"),
            repo=str(row["repo"]),
            filename=str(row["filename"]),
            sha256=str(row["sha256"]).lower(),
            size=int(row["size"]),
            license=str(row.get("license") or ""),
            min_vram_gb=float(row.get("min_vram_gb") or 0),
            context=int(row.get("context") or 8192),
            moe=bool(row.get("moe")),
            notes=str(row.get("notes") or ""),
            revision=str(row.get("revision") or ""),
            base_repo=str(row.get("base_repo") or ""),
            base_revision=str(row.get("base_revision") or ""),
            base_license=str(row.get("base_license") or ""),
            card=str(row.get("card") or ""),
            default=bool(row.get("default")),
            enabled=bool(row.get("enabled", True)),
        )
        if entry.enabled and (
            not entry.revision
            or not entry.sha256
            or entry.size <= 0
            or not entry.base_repo
            or not entry.base_license
        ):
            raise PlotweaverError(
                f"{entry.id} needs revision, sha256, size, base_repo, and base_license. "
                "Untagged tunes are not downloaded."
            )
        entries.append(entry)
    return entries


def licence_allowed(entry: RegistryEntry, *, allow_other: bool = False) -> bool:
    return _licence_ok(entry.license, allow_other=allow_other) and _licence_ok(
        entry.base_license, allow_other=allow_other
    )


def _licence_ok(value: str, *, allow_other: bool) -> bool:
    text = value.strip().lower()
    if not text:
        return False
    if text in APPROVED_LICENSES:
        return True
    return allow_other


def canonical_licence(value: str) -> str:
    text = value.strip().lower()
    if text == "apache-2.0":
        return "Apache-2.0"
    if text == "mit":
        return "MIT"
    return value.strip()


def verify_file(path: Path, *, size: int, sha256: str) -> None:
    actual = path.stat().st_size
    if actual != size:
        raise PlotweaverError(f"{path.name} is {actual} bytes, expected {size}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    found = digest.hexdigest()
    if found != sha256.lower():
        raise PlotweaverError(f"{path.name} SHA-256 {found} does not match {sha256}")


def claim_user(store: Path, user: str = "plotweaver") -> None:
    """Add this app to `<models>/.users.json` without dropping other suite apps.

    The file is the same one Audiobook Builder and Movie Dubber share. A key that
    is already true is left byte-for-byte alone.
    """
    store.mkdir(parents=True, exist_ok=True)
    path = store / ".users.json"
    data: dict[str, bool] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8-sig"))
        except UnicodeError, json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            data = {str(key): bool(value) for key, value in loaded.items()}
    if data.get(user) is True:
        return
    data[user] = True
    payload = json.dumps(data, indent=1, sort_keys=True)
    tmp = path.with_name(f".users.json.{os.urandom(4).hex()}.tmp")
    tmp.write_text(payload, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def is_optional_download(entry: RegistryEntry) -> bool:
    """Models that need 20 GB of VRAM are optional downloads."""
    return entry.min_vram_gb >= OPTIONAL_VRAM_GB


def allows_optional_download(*, total_vram_gb: float | None, preference: bool | None) -> bool:
    """A saved Settings choice wins. Otherwise a 20 GB GPU opts in."""
    if preference is not None:
        return preference
    return total_vram_gb is not None and total_vram_gb >= OPTIONAL_VRAM_GB


def download_decision(
    entry: RegistryEntry,
    *,
    free_gb: float,
    total_vram_gb: float | None,
    optional_preference: bool | None,
) -> str | None:
    """Return a skip reason, or None when the file should be downloaded."""
    if not entry.enabled:
        return "disabled until the file is published with a revision and SHA-256"
    if is_optional_download(entry) and not allows_optional_download(
        total_vram_gb=total_vram_gb, preference=optional_preference
    ):
        return f"optional (needs {OPTIONAL_VRAM_GB:.0f} GB of VRAM)"
    if entry.min_vram_gb > free_gb + 0.5:
        return f"needs {entry.min_vram_gb} GB, {free_gb:.1f} GB free"
    return None


def download_model(
    entry: RegistryEntry, store: Path | None = None, *, allow_other: bool = False
) -> Path:
    if not entry.enabled:
        raise PlotweaverError(
            f"{entry.id} is disabled until Voxprint Model Forge publishes it "
            "with a revision and SHA-256. Plotweaver does not abliterate or quantize."
        )
    if not licence_allowed(entry, allow_other=allow_other):
        raise PlotweaverError(
            f"{entry.id} is licensed {entry.license!r} "
            f"(base {entry.base_license!r}). "
            "Plotweaver downloads Apache-2.0 and MIT weights with a confirmed "
            "base licence unless you pass --allow-other-license. "
            "An empty licence is refused."
        )
    folder = store or gguf_dir()
    folder.mkdir(parents=True, exist_ok=True)
    claim_user(folder.parent)
    target = folder / entry.filename
    url = (
        f"https://huggingface.co/{entry.repo}/resolve/{entry.revision}/"
        f"{entry.filename}?download=true"
    )
    if not target.is_file():
        partial = target.with_suffix(target.suffix + ".partial")
        headers = {"User-Agent": "plotweaver"}
        with httpx.stream(
            "GET",
            url,
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(3600.0, connect=30.0),
        ) as response:
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_bytes(1024 * 1024):
                    handle.write(chunk)
        partial.replace(target)
    verify_file(target, size=entry.size, sha256=entry.sha256)
    manifest = {
        "id": entry.id,
        "repo": entry.repo,
        "revision": entry.revision,
        "files": [{"path": entry.filename, "sha256": entry.sha256, "size": entry.size}],
        "license": canonical_licence(entry.license),
        "base_repo": entry.base_repo,
        "base_revision": entry.base_revision,
        "base_license": canonical_licence(entry.base_license),
        "role": entry.role,
        "card": entry.card,
        "default": entry.default,
        "notes": entry.notes,
    }
    write_json(folder / f"{entry.id}.manifest.json", manifest)
    return target
