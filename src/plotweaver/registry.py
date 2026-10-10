"""Model registry, shared download folder, and SHA-256 checks.

Default entries are Apache-2.0. A licence outside Apache-2.0 / MIT is refused
unless the caller passes allow_other_license.
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

import httpx

from plotweaver.atomic import read_json, write_json
from plotweaver.errors import PlotweaverError
from plotweaver.paths import models_dir

APPROVED_LICENSES = {"apache-2.0", "mit"}


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


def load_registry(path: Path) -> list[RegistryEntry]:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("model") or []
    if not isinstance(rows, list):
        raise PlotweaverError(f"{path} has no [[model]] entries")
    entries: list[RegistryEntry] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        entries.append(
            RegistryEntry(
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
            )
        )
    return entries


def licence_allowed(entry: RegistryEntry, *, allow_other: bool = False) -> bool:
    if entry.license.lower() in APPROVED_LICENSES:
        return True
    return allow_other


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
    """Reference-count this app in the shared models folder (.users.json)."""
    store.mkdir(parents=True, exist_ok=True)
    path = store / ".users.json"
    data: dict[str, object] = {}
    if path.is_file():
        loaded = read_json(path)
        if isinstance(loaded, dict):
            data = loaded
    data[user] = True
    write_json(path, data)


def download_model(
    entry: RegistryEntry, store: Path | None = None, *, allow_other: bool = False
) -> Path:
    if not licence_allowed(entry, allow_other=allow_other):
        raise PlotweaverError(
            f"{entry.id} is licensed {entry.license!r}. "
            "Plotweaver downloads Apache-2.0 and MIT weights unless you pass "
            "--allow-other-license."
        )
    folder = store or models_dir()
    folder.mkdir(parents=True, exist_ok=True)
    claim_user(folder)
    target = folder / entry.filename
    if target.is_file():
        verify_file(target, size=entry.size, sha256=entry.sha256)
        return target
    url = f"https://huggingface.co/{entry.repo}/resolve/main/{entry.filename}?download=true"
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
        "license": entry.license,
        "source": url,
        "sha256": entry.sha256,
        "size": entry.size,
        "role": entry.role,
        "notes": entry.notes,
    }
    write_json(folder / f"{entry.id}.manifest.json", manifest)
    return target
