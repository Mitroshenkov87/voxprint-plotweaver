"""Checkout root, shared model folder, and the suite settings file."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def repo_root() -> Path:
    """Directory that contains pyproject.toml and the bake-off data.

    Walks up from this file so an editable install and a plain checkout both work.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "bakeoff").is_dir():
            return candidate
    raise FileNotFoundError("Plotweaver repo root was not found (pyproject.toml + bakeoff/)")


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
