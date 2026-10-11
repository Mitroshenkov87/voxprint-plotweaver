"""One readiness gate for the window.

The main window opens only when :func:`voxprint_common.mdl.ready` is true for
``plotweaver``. In voxprint-common 0.2.4 that call checks each required file's
presence and size. It does not trust the status file and it does not download.
Otherwise the window shows a short notice and Manage models.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from voxprint_common.mdl import ready as mdl_ready
from voxprint_common.mdl.catalog import CatalogError
from voxprint_common.mdl.status import StatusError


@dataclass(frozen=True)
class Ready:
    """MDL reports ready. The main window may open."""


@dataclass(frozen=True)
class Failed:
    """Models are not ready. ``message`` is one plain sentence."""

    message: str


def ensure_ready(progress_cb: Callable[[str], None]) -> Ready | Failed:
    """Return ready only when 0.2.4 ``ready('plotweaver')`` is true.

    ``progress_cb`` receives one plain sentence. This function does not
    download and does not draw a window.
    """
    progress_cb("Checking models.")
    try:
        if mdl_ready("plotweaver"):
            return Ready()
    except (StatusError, CatalogError) as exc:
        return Failed(str(exc))
    return Failed("models not ready")
