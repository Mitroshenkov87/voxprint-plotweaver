"""Checkout root, the shared suite folder, and the suite settings file."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _marked_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "bakeoff").is_dir():
            return candidate
    return None


def repo_root() -> Path:
    """Directory that contains pyproject.toml and the bake-off data.

    An editable checkout is found by walking up from this file. A full installer
    is found the same way: its bundled interpreter lives in that directory.
    ``PLOTWEAVER_ROOT`` overrides both.
    """
    override = os.environ.get("PLOTWEAVER_ROOT")
    if override:
        return Path(override)
    found = _marked_root(Path(__file__).resolve())
    if found is None:
        found = _marked_root(Path(sys.executable).resolve())
    if found is None:
        raise FileNotFoundError("Plotweaver install root was not found (pyproject.toml + bakeoff/)")
    return found


def voxprint_home() -> Path:
    """Suite home. ``VOXPRINT_HOME`` replaces the platform default.

    Windows uses ``%LOCALAPPDATA%\\Voxprint``. Linux uses
    ``$XDG_DATA_HOME/voxprint`` when that variable is set, otherwise
    ``~/.local/share/voxprint``.
    """
    override = os.environ.get("VOXPRINT_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / "Voxprint"
    data = os.environ.get("XDG_DATA_HOME")
    base = Path(data) if data else Path.home() / ".local" / "share"
    return base / "voxprint"


def shared_dir() -> Path:
    """Versioned suite folder: ``runtime/``, ``models/``, and ``tools/``."""
    return voxprint_home() / "shared"


def shared_runtime_dir() -> Path:
    """Shared interpreters and llama.cpp trees."""
    return shared_dir() / "runtime"


def shared_tools_dir() -> Path:
    """Shared helper binaries. Empty until an app puts a tool here."""
    return shared_dir() / "tools"


def models_dir() -> Path:
    """Shared suite model folder, ``<shared>/models``. Override with PLOTWEAVER_MODELS."""
    override = os.environ.get("PLOTWEAVER_MODELS")
    if override:
        return Path(override)
    return shared_dir() / "models"


def legacy_models_dir() -> Path:
    """Previous suite model folder, ``<home>/models``.

    Audiobook Builder and Movie Dubber still read ``.users.json`` and GGUF
    files here. Plotweaver reuses a matching file and does not delete it.
    """
    return voxprint_home() / "models"


def suite_state_dir() -> Path:
    """Suite settings folder. Override with PLOTWEAVER_STATE."""
    override = os.environ.get("PLOTWEAVER_STATE")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / "Voxprint" / "state"
    return Path.home() / ".local" / "share" / "voxprint" / "state"


def gguf_dir() -> Path:
    """Shared GGUF folder, ``<shared>/models/llm``.

    A file already stored by Audiobook Builder under the older ``<home>/models/llm``
    path is reused when its size and SHA-256 match.
    """
    return models_dir() / "llm"


def llama_runtime_dir() -> Path:
    """Unpacked llama.cpp b11476 Vulkan tree, ``<shared>/runtime/llama.cpp-b11476``."""
    override = os.environ.get("PLOTWEAVER_LLAMA_DIR")
    if override:
        return Path(override)
    return shared_runtime_dir() / "llama.cpp-b11476"


def llama_cuda_dir() -> Path:
    """Unpacked llama.cpp b11476 CUDA tree, ``<shared>/runtime/llama.cpp-b11476-cuda``."""
    override = os.environ.get("PLOTWEAVER_LLAMA_CUDA_DIR")
    if override:
        return Path(override)
    return shared_runtime_dir() / "llama.cpp-b11476-cuda"
