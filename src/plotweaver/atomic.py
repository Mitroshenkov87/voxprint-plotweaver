"""Atomic JSON and text writes so a crash never leaves a half file."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def write_text(path: Path, text: str) -> None:
    """Replace a text file by writing a temporary file and renaming it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def write_json(path: Path, payload: Any) -> None:
    """Write a JSON file the same way as write_text."""
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path) -> Any:
    """Read a JSON file written by write_json."""
    return json.loads(path.read_text(encoding="utf-8"))
