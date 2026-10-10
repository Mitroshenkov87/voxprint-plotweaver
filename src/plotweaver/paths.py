"""Checkout root, shared model folder, and the suite settings file."""

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
    is found the same way: its virtual environment lives in that directory.
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


def models_dir() -> Path:
    """Shared suite model folder. Override with PLOTWEAVER_MODELS."""
    override = os.environ.get("PLOTWEAVER_MODELS")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / "Voxprint" / "models"
    return Path.home() / ".local" / "share" / "voxprint" / "models"


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
    """Shared suite GGUF folder, `<models>/llm`.

    Audiobook Builder stores Gemma 4 12B at this path, so one download serves both apps.
    """
    return models_dir() / "llm"


def llama_runtime_dir() -> Path:
    """Unpacked llama.cpp b11476 tree, `<models>/llm/llama.cpp-b11476`.

    The same directory Audiobook Builder uses for its Vulkan `llama-server`.
    """
    override = os.environ.get("PLOTWEAVER_LLAMA_DIR")
    if override:
        return Path(override)
    return gguf_dir() / "llama.cpp-b11476"
