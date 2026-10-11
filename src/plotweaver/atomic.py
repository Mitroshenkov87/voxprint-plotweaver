"""Atomic JSON and text writes so a crash never leaves a half file.

The publish and the lock are voxprint-common. ``read_json`` stays here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from voxprint_common.atomic import (
    LockTimeout,
    exclusive_lock,
    replace,
    write_bytes,
    write_json,
    write_text,
)

__all__ = [
    "LockTimeout",
    "exclusive_lock",
    "read_json",
    "replace",
    "write_bytes",
    "write_json",
    "write_text",
]


def read_json(path: Path) -> Any:
    """Read a JSON file written by write_json."""
    return json.loads(path.read_text(encoding="utf-8"))
