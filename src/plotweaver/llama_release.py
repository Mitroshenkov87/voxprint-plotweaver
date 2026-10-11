"""Pinned llama.cpp b11476 Vulkan and CUDA builds.

The binaries are not vendored in git. The Vulkan archive matches Audiobook
Builder (URL, size, SHA-256). The CUDA archive is the b11476 build from the
same GitHub release, pinned by the published SHA-256. The suite copy lives
under ``<shared>/runtime``. Tests cover the pins. They never start the process.
"""

from __future__ import annotations

import os
import sys
import tarfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from plotweaver.errors import PlotweaverError
from plotweaver.fetch import stream_download
from plotweaver.hardware import driver_allows_cuda
from plotweaver.paths import llama_cuda_dir, llama_runtime_dir, repo_root
from plotweaver.registry import verify_file
from plotweaver.textio import read_text

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

# SHA-256 values are the digests GitHub published on the b11476 release.
CUDA_MARKER = f"{LLAMA_BUILD}-cuda"
CUDA_ASSETS: dict[str, LlamaAsset] = {
    "linux": LlamaAsset(
        name=f"llama-{LLAMA_BUILD}-bin-ubuntu-cuda-12.8-x64.tar.gz",
        size=171_688_764,
        sha256="1a854ea10d271145a731f1f7e91119d85c3a93ea4a4015b1d4375860465d1379",
    ),
    "windows": LlamaAsset(
        name=f"llama-{LLAMA_BUILD}-bin-win-cuda-12.4-x64.zip",
        size=264_521_953,
        sha256="b30289b92274bb7e89200832f4bcfd9e731b716a4056d00b61440f623d4cc8e8",
    ),
}


def pinned_asset(system: str) -> LlamaAsset | None:
    """The Vulkan x64 archive for Windows or Linux, or None on any other OS."""
    if system == "windows":
        return SERVER_ASSETS["windows"]
    if system == "linux":
        return SERVER_ASSETS["linux"]
    return None


def pinned_cuda_asset(system: str) -> LlamaAsset | None:
    """The CUDA x64 archive for Windows or Linux, or None on any other OS."""
    if system == "windows":
        return CUDA_ASSETS["windows"]
    if system == "linux":
        return CUDA_ASSETS["linux"]
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


def ensure_pinned_runtime(
    folder: Path,
    asset: LlamaAsset,
    marker: str,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> Path:
    """Download and unpack one pinned llama.cpp archive when the folder is not ready."""
    ready = _ready_marked(folder, marker)
    if ready is not None:
        return ready
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / asset.name
    _fetch_verified(
        _RELEASE_BASE + asset.name,
        archive,
        size=asset.size,
        sha256=asset.sha256,
        on_progress=on_progress,
        label=asset.name,
    )
    extract_archive(archive, folder)
    archive.unlink(missing_ok=True)
    (folder / ".complete").write_text(marker, encoding="utf-8")
    binary = find_server(folder)
    if binary is None:
        raise PlotweaverError("The llama.cpp archive did not contain llama-server.")
    binary.chmod(binary.stat().st_mode | 0o755)
    return binary


def _ensure_in(folder: Path) -> Path:
    system = "windows" if sys.platform == "win32" else "linux"
    asset = pinned_asset(system)
    if asset is None:
        raise PlotweaverError("llama.cpp b11476 is published for Windows and Linux x64.")
    return ensure_pinned_runtime(folder, asset, LLAMA_BUILD)


def ensure_llama_server(dest: Path | None = None) -> Path:
    """Return b11476 ``llama-server``.

    ``PLOTWEAVER_LLAMA_SERVER`` wins. An explicit ``dest`` is the Vulkan tree.
    Otherwise a ready CUDA build is used when the driver is new enough, then
    the shared Vulkan tree, then the copy shipped next to the app.
    """
    override = os_environ_server()
    if override is not None:
        return override
    if dest is not None:
        return _ensure_in(dest)
    if driver_allows_cuda():
        cuda = _ready_marked(llama_cuda_dir(), CUDA_MARKER)
        if cuda is not None:
            return cuda
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
    return _ready_marked(folder, LLAMA_BUILD)


def _ready_marked(folder: Path, marker_text: str) -> Path | None:
    marker = folder / ".complete"
    if not marker.is_file():
        return None
    try:
        tag = read_text(marker).strip()
    except OSError:
        return None
    if tag != marker_text:
        return None
    return find_server(folder)


def _fetch_verified(
    url: str,
    dest: Path,
    *,
    size: int,
    sha256: str,
    on_progress: Callable[[str], None] | None = None,
    label: str = "llama.cpp",
) -> None:
    if dest.is_file():
        try:
            verify_file(dest, size=size, sha256=sha256)
            return
        except PlotweaverError:
            dest.unlink()
    stream_download(
        url,
        dest,
        total=size,
        on_progress=on_progress,
        label=label,
        sha256=sha256,
    )
    verify_file(dest, size=size, sha256=sha256)
