"""Saved suite choices. The optional-model switch lives in Settings."""

from __future__ import annotations

import json
from pathlib import Path

from plotweaver.atomic import read_json, write_json
from plotweaver.errors import PlotweaverError
from plotweaver.paths import suite_state_dir

_KEY = "uncensored_models"
_TIER_KEY = "model_tier_override"
_TIER_VALUES = {"auto", "16gb", "24gb"}


def _path() -> Path:
    return suite_state_dir() / "settings.json"


def _load() -> dict[str, object]:
    path = _path()
    if not path.is_file():
        return {}
    try:
        loaded = read_json(path)
    except OSError, UnicodeError, json.JSONDecodeError:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def uncensored_models_preference() -> bool:
    """Abliterated downloads stay off until Settings saves an explicit yes."""
    return bool(_load().get(_KEY))


def save_uncensored_models(enabled: bool) -> None:
    """Save whether Settings should download abliterated models."""
    data = _load()
    data[_KEY] = enabled
    write_json(_path(), data)


def model_tier_override() -> str:
    """Advanced Settings choice: auto, 16gb, or 24gb. Missing values mean auto."""
    value = _load().get(_TIER_KEY)
    if isinstance(value, str) and value in _TIER_VALUES:
        return value
    return "auto"


def save_model_tier_override(value: str) -> None:
    """Save the advanced VRAM tier choice: auto, 16gb, or 24gb."""
    if value not in _TIER_VALUES:
        raise PlotweaverError(f"VRAM tier override must be one of {sorted(_TIER_VALUES)}")
    data = _load()
    data[_TIER_KEY] = value
    write_json(_path(), data)
