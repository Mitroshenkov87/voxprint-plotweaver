"""Locate the Audiobook Builder command-line program.

The suite component id is one assignment. Audiobook Builder has not published
it yet, so the lookup falls through to the suite install paths, then PATH,
then the older ``Voxprint`` directory.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from voxprint_common.runtime_manifest import load

# Set this to the voxprint-common manifest component id when ABB publishes it.
ABB_COMPONENT_ID = ""

_WIN_DEFAULT = Path(r"C:\Program Files\VOXPrint AI Suite\Audiobook Builder") / (
    "voxprint-audiobook-cli.exe"
)
_LINUX_DEFAULT = Path("/opt/voxprint-ai-suite/audiobook-builder/voxprint-audiobook-cli")
_WIN_LEGACY = Path(r"C:\Program Files\Voxprint\voxprint-cli.exe")
_PATH_NAMES = ("voxprint-audiobook-cli", "voxprint-audiobook-cli.exe")
_CLI_NAMES = ("voxprint-audiobook-cli", "voxprint-audiobook-cli.exe")


def find_audiobook_cli() -> Path | None:
    """Return the Audiobook Builder CLI, or None when it is not installed.

    Windows path checks are case-insensitive. A registry hit wins, then the
    suite defaults, then ``voxprint-audiobook-cli`` on PATH, then the legacy
    ``voxprint-cli.exe``.
    """
    found = _from_registry(ABB_COMPONENT_ID)
    if found is not None:
        return found
    for candidate in (_WIN_DEFAULT, _LINUX_DEFAULT):
        match = _existing(candidate)
        if match is not None:
            return match
    on_path = _on_path()
    if on_path is not None:
        return on_path
    return _existing(_WIN_LEGACY)


def _from_registry(component_id: str) -> Path | None:
    """Read one component path. An empty id skips the manifest."""
    if not component_id:
        return None
    try:
        manifest = load()
    except OSError, ValueError:
        return None
    component = manifest.components.get(component_id)
    if component is None:
        return None
    raw = Path(component.path)
    if raw.is_file():
        return raw
    if raw.is_dir():
        return _named_child(raw)
    return _existing(raw)


def _on_path() -> Path | None:
    for name in _PATH_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def _existing(path: Path) -> Path | None:
    if path.is_file():
        return path
    if os.name != "nt":
        return None
    return _case_insensitive(path)


def _named_child(folder: Path) -> Path | None:
    for name in _CLI_NAMES:
        candidate = _existing(folder / name)
        if candidate is not None:
            return candidate
    if os.name != "nt" or not folder.is_dir():
        return None
    try:
        children = list(folder.iterdir())
    except OSError:
        return None
    wanted = {name.lower() for name in _CLI_NAMES}
    for child in children:
        if child.name.lower() in wanted and child.is_file():
            return child
    return None


def _case_insensitive(path: Path) -> Path | None:
    """Walk ``path`` from its drive root, matching each part without case."""
    anchor = path.anchor
    if not anchor:
        return None
    current = Path(anchor)
    for part in path.parts[1:]:
        if not current.is_dir():
            return None
        match: Path | None = None
        try:
            for child in current.iterdir():
                if child.name.lower() == part.lower():
                    match = child
                    break
        except OSError:
            return None
        if match is None:
            return None
        current = match
    if current.is_file():
        return current
    return None
