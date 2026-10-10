"""Pick a llama.cpp CUDA build from the GitHub release asset list.

The network download lives in the bake-off script path. Tests cover only the picker.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import httpx

from plotweaver.errors import PlotweaverError
from plotweaver.paths import llama_runtime_dir

GITHUB_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=20"


def select_asset(names: list[str], *, system: str, cuda_major: int) -> str | None:
    """Return the llama-server archive name for this OS and CUDA major version."""
    if system == "windows":
        needle = "win-cuda-13" if cuda_major >= 13 else "win-cuda-12"
        suffix = ".zip"
    else:
        needle = "ubuntu-cuda-13" if cuda_major >= 13 else "ubuntu-cuda-12"
        suffix = ".tar.gz"
    matches = [
        name
        for name in names
        if name.startswith("llama-")
        and "cudart" not in name
        and needle in name
        and name.endswith(suffix)
    ]
    if not matches:
        return None
    return sorted(matches)[-1]


def cudart_companion(asset: str, names: list[str]) -> str | None:
    """The matching CUDA runtime archive, when the release ships one."""
    tag = "cuda-13" if "cuda-13" in asset else "cuda-12"
    system = "win" if "win-" in asset else "ubuntu"
    for name in names:
        if name.startswith("cudart-") and tag in name and system in name:
            return name
    return None


def cuda_major_from_smi(text: str) -> int:
    for line in text.splitlines():
        if "CUDA Version" not in line:
            continue
        tail = line.split("CUDA Version", 1)[1]
        digits = ""
        for char in tail:
            if char.isdigit():
                digits += char
            elif digits:
                break
        if digits:
            return int(digits)
    return 12


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


def ensure_llama_server(dest: Path | None = None) -> Path:
    """Download the newest tagged CUDA build if the binary is not already there."""
    override = os_environ_server()
    if override is not None:
        return override
    folder = dest or llama_runtime_dir()
    existing = find_server(folder)
    if existing is not None:
        return existing
    folder.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "plotweaver", "Accept": "application/vnd.github+json"}
    try:
        listing = httpx.get(GITHUB_API, headers=headers, timeout=60.0)
        listing.raise_for_status()
        releases = listing.json()
    except httpx.HTTPError as exc:
        raise PlotweaverError(f"could not list llama.cpp releases: {exc}") from exc
    if not isinstance(releases, list):
        raise PlotweaverError("llama.cpp release list was not a JSON list")
    system = "windows" if sys.platform == "win32" else "linux"
    cuda_major = _local_cuda_major()
    for release in releases:
        if not isinstance(release, dict):
            continue
        assets = release.get("assets")
        if not isinstance(assets, list):
            continue
        names = [str(item.get("name")) for item in assets if isinstance(item, dict)]
        chosen = select_asset(names, system=system, cuda_major=cuda_major)
        if chosen is None:
            continue
        urls = {
            str(item.get("name")): str(item.get("browser_download_url"))
            for item in assets
            if isinstance(item, dict)
        }
        _download(urls[chosen], folder / chosen)
        extract_archive(folder / chosen, folder)
        companion = cudart_companion(chosen, names)
        if companion and companion in urls:
            _download(urls[companion], folder / companion)
            extract_archive(folder / companion, folder)
        binary = find_server(folder)
        if binary is None:
            raise PlotweaverError("llama.cpp archive did not contain llama-server")
        binary.chmod(binary.stat().st_mode | 0o755)
        return binary
    raise PlotweaverError("no Ubuntu/Windows CUDA llama-server asset in recent llama.cpp releases")


def os_environ_server() -> Path | None:
    raw = os.environ.get("PLOTWEAVER_LLAMA_SERVER")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_file():
        raise PlotweaverError(f"PLOTWEAVER_LLAMA_SERVER is not a file: {path}")
    return path


def _local_cuda_major() -> int:
    try:
        proc = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except OSError:
        return 12
    return cuda_major_from_smi(proc.stdout or "")


def _download(url: str, dest: Path) -> None:
    if dest.is_file() and dest.stat().st_size > 0:
        return
    partial = dest.with_suffix(dest.suffix + ".partial")
    with httpx.stream(
        "GET", url, follow_redirects=True, timeout=httpx.Timeout(600.0, connect=30.0)
    ) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)
    partial.replace(dest)
