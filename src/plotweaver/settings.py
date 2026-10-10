"""Saved suite choices. The optional-model switch lives in Settings."""

from __future__ import annotations

import json
from pathlib import Path

from plotweaver.atomic import read_json, write_json
from plotweaver.paths import suite_state_dir

_KEY = "uncensored_models"


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
    data = _load()
    data[_KEY] = enabled
    write_json(_path(), data)
