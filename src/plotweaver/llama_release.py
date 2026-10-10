"""Pinned llama.cpp b11476 Vulkan build, shared with Audiobook Builder.

The binary is not vendored in git. The full installer unpacks the same archive
Audiobook Builder pins (URL, size, SHA-256) under ``runtime/llama.cpp-b11476``.
A checkout without that tree downloads it into ``<models>/llm/llama.cpp-b11476``.
Tests cover the pin and the bundled-tree lookup. They never start the process.
"""

from __future__ import annotations

import os
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from plotweaver.errors import PlotweaverError
from plotweaver.paths import llama_runtime_dir, repo_root
from plotweaver.registry import verify_file

LLAMA_BUILD = "b11476"
_RELEASE_BASE = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}/"


@dataclass(frozen=True)
class LlamaAsset:
    name: str
    size: int
    sha256: str


# Same names, sizes, and SHA-256 as Audiobook Builder infra/llm_tool.py (b11476 Vulkan).
SERVER_ASSETS: dict[str, LlamaAsset] = {
    "linux": LlamaAsset(
        name=f"llama-{LLAMA_BUILD}-bin-ubuntu-vulkan-x64.tar.gz",
        size=31_684_207,
        sha256="5bb4306d7917f33e81efda02e6f791ae6a82e86bee121227a3ab2b4e8e40427f",
    ),
    "windows": LlamaAsset(
        name=f"llama-{LLAMA_BUILD}-bin-win-vulkan-x64.zip",
        size=33_380_424,
        sha256="5c71e7b749697da4a8d46e9ee55486845cbba27c9dfbecb4007f31ba6610d523",
    ),
}


def pinned_asset(system: str) -> LlamaAsset | None:
    """The Vulkan x64 archive for Windows or Linux, or None on any other OS."""
    if system == "windows":
        return SERVER_ASSETS["windows"]
    if system == "linux":
        return SERVER_ASSETS["linux"]
    return None


def _safe_members(archive: tarfile.TarFile, dest: Path) -> list[tarfile.TarInfo]:
    root = dest.resolve()
    kept: list[tarfile.TarInfo] = []
    for member in archive.getmembers():
        target = (root / member.name).resolve()
        if root not in target.parents and target != root:
            raise PlotweaverError(f"unsafe path in llama.cpp archive: {member.name}")
        kept.append(member)
    return kept


def extract_archive(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            infos = bundle.infolist()
            root = dest.resolve()
            for info in infos:
                target = (root / info.filename).resolve()
                if root not in target.parents and target != root:
                    raise PlotweaverError(f"unsafe path in llama.cpp archive: {info.filename}")
            for info in infos:
                bundle.extract(info, dest)
        return
    with tarfile.open(archive) as bundle:
        bundle.extractall(dest, members=_safe_members(bundle, dest), filter="data")


def find_server(dest: Path) -> Path | None:
    names = ("llama-server", "llama-server.exe")
    for name in names:
        matches = list(dest.rglob(name))
        if matches:
            return matches[0]
    return None


def bundled_runtime_dir(root: Path) -> Path:
    """llama.cpp tree shipped beside the app, ``<root>/runtime/llama.cpp-b11476``."""
    return root / "runtime" / f"llama.cpp-{LLAMA_BUILD}"


def _bundled_dir() -> Path | None:
    try:
        root = repo_root()
    except FileNotFoundError:
        return None
    return bundled_runtime_dir(root)


def _ensure_in(folder: Path) -> Path:
    ready = _ready_server(folder)
    if ready is not None:
        return ready
    system = "windows" if sys.platform == "win32" else "linux"
    asset = pinned_asset(system)
    if asset is None:
        raise PlotweaverError(
            "llama.cpp b11476 Vulkan build is published for Windows and Linux x64"
        )
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / asset.name
    _fetch_verified(
        _RELEASE_BASE + asset.name,
        archive,
        size=asset.size,
        sha256=asset.sha256,
    )
    extract_archive(archive, folder)
    archive.unlink(missing_ok=True)
    (folder / ".complete").write_text(LLAMA_BUILD, encoding="utf-8")
    binary = find_server(folder)
    if binary is None:
        raise PlotweaverError("llama.cpp archive did not contain llama-server")
    binary.chmod(binary.stat().st_mode | 0o755)
    return binary


def ensure_llama_server(dest: Path | None = None) -> Path:
    """Return b11476 ``llama-server``.

    ``PLOTWEAVER_LLAMA_SERVER`` wins. An explicit ``dest`` is filled in place.
    Otherwise an already unpacked shared copy is used, then the copy shipped
    next to the app, and only then a download into the shared models folder.
    """
    override = os_environ_server()
    if override is not None:
        return override
    if dest is not None:
        return _ensure_in(dest)
    ready = _ready_server(llama_runtime_dir())
    if ready is not None:
        return ready
    bundled = _bundled_dir()
    if bundled is not None:
        found = _ready_server(bundled)
        if found is not None:
            return found
    return _ensure_in(llama_runtime_dir())


def os_environ_server() -> Path | None:
    raw = os.environ.get("PLOTWEAVER_LLAMA_SERVER")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_file():
        raise PlotweaverError(f"PLOTWEAVER_LLAMA_SERVER is not a file: {path}")
    return path


def _ready_server(folder: Path) -> Path | None:
    marker = folder / ".complete"
    if not marker.is_file():
        return None
    try:
        tag = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if tag != LLAMA_BUILD:
        return None
    return find_server(folder)


def _fetch_verified(url: str, dest: Path, *, size: int, sha256: str) -> None:
    if dest.is_file():
        try:
            verify_file(dest, size=size, sha256=sha256)
            return
        except PlotweaverError:
            dest.unlink()
    _download(url, dest)
    verify_file(dest, size=size, sha256=sha256)


def _download(url: str, dest: Path) -> None:
    partial = dest.with_suffix(dest.suffix + ".partial")
    with httpx.stream(
        "GET", url, follow_redirects=True, timeout=httpx.Timeout(600.0, connect=30.0)
    ) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)
    partial.replace(dest)
