"""One provisioning entry for the window.

The GUI calls :func:`ensure_ready` and nothing else in this module. When
``voxprint-mdl`` arrives in voxprint-common, replace the body of
:func:`ensure_ready`. The window stays the same.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from plotweaver.errors import PlotweaverError


@dataclass(frozen=True)
class Ready:
    """Required files are present. The main window may open."""


@dataclass(frozen=True)
class Failed:
    """Provisioning stopped. ``message`` is one plain sentence."""

    message: str


def ensure_ready(progress_cb: Callable[[str], None]) -> Ready | Failed:
    """Install or repair required files and report each step.

    ``progress_cb`` receives plain sentences, including the model name, size,
    speed, and remaining time while a download is moving. The call does not
    draw a window.
    """
    # The window calls this function only. The suite import stays inside it so a
    # later voxprint-mdl body can replace the call without loading suite at import.
    from plotweaver.suite import repair_shared

    try:
        repair_shared(progress_cb)
    except PlotweaverError as exc:
        return Failed(str(exc))
    except OSError as exc:
        return Failed(str(exc))
    return Ready()
