"""Checkout root, the shared suite folder, and the suite settings file.

Suite home, the shared directory, and the model directory come from
voxprint-common. ``PLOTWEAVER_MODELS`` still overrides the model directory.
A file already stored under ``<shared>/models`` by an older Plotweaver
install is reused when its size and SHA-256 match.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from voxprint_common.paths import home, state_dir
from voxprint_common.paths import models_dir as suite_models_dir
from voxprint_common.paths import shared_dir as suite_shared_dir


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
    """Suite home. ``VOXPRINT_HOME`` replaces the platform default."""
    return home()


def shared_dir() -> Path:
    """Versioned suite folder: ``runtime/``, ``models/``, and ``tools/``."""
    return suite_shared_dir()


def shared_runtime_dir() -> Path:
    """Shared interpreters and llama.cpp trees."""
    return shared_dir() / "runtime"


def shared_tools_dir() -> Path:
    """Shared helper binaries. Empty until an app puts a tool here."""
    return shared_dir() / "tools"


def models_dir() -> Path:
    """Suite model folder from voxprint-common. ``PLOTWEAVER_MODELS`` wins when set."""
    override = os.environ.get("PLOTWEAVER_MODELS")
    if override:
        return Path(override)
    return suite_models_dir()


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
    return state_dir()


def gguf_dir() -> Path:
    """GGUF folder, ``<models>/llm``, using the suite model root.

    A matching file under the older ``<shared>/models/llm`` path is reused.
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


def splash_art() -> Path:
    """Approved splash image. The packaged file wins, then ``assets/splash.jpg``."""
    packaged = Path(__file__).resolve().parent / "data" / "splash.jpg"
    if packaged.is_file():
        return packaged
    return repo_root() / "assets" / "splash.jpg"
