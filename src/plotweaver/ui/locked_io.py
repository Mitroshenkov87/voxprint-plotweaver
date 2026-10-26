"""Atomic, locked writes for the shared book settings and the history strip.

The shell's in-memory state is the source of the document. This module
replaces the library's plain ``write_text`` with the suite lock and an
atomic replace, so a reader sees the previous file or the finished file.
"""

from __future__ import annotations

import json

from voxprint_common.atomic import exclusive_lock, write_text
from voxprint_common.ui.presets import SettingState
from voxprint_common.ui.simple_image import SimpleImageLayout

_HISTORY_LIMIT = 50
_INSTALLED = False


def install_locked_writes() -> None:
    """Install the locked writers once. Later calls do nothing."""
    global _INSTALLED
    if _INSTALLED:
        return
    SettingState._write = _write_state  # type: ignore[method-assign]
    SimpleImageLayout._write_history = _write_history  # type: ignore[method-assign]
    _INSTALLED = True


def _write_state(self: SettingState) -> None:
    if self._state_dir is None or not self._loaded:
        return
    self._state_dir.mkdir(parents=True, exist_ok=True)
    payload = {"schema": 1, **self.snapshot()}
    path = self._state_dir / self._state_name
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    with exclusive_lock(path.with_name(f"{path.name}.lock")):
        write_text(path, text)


def _write_history(self: SimpleImageLayout) -> None:
    if self._state_dir is None:
        return
    self._state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": 1,
        "items": [
            {
                "id": item.item_id,
                "prompt": item.prompt,
                "presets": [list(pair) for pair in item.presets],
                "seed": item.seed,
            }
            for item in self.history[:_HISTORY_LIMIT]
        ],
    }
    path = self._state_dir / self._history_name
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    with exclusive_lock(path.with_name(f"{path.name}.lock")):
        write_text(path, text)
