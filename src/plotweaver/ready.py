"""One readiness gate for the window.

The main window opens only when :func:`voxprint_common.mdl.ready` is true.
Otherwise the window shows a short notice and Manage models.

``voxprint_common.mdl.ensure_ready(app, progress_cb)`` was checked against the
0.2.1 wheel before this shim was written. ``progress_cb`` is
``(fraction, message)``, and the call enqueues a download. That is not the
gate: a missing set stays closed until Manage models, or the installer, has
run ``voxprint-mdl download``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from voxprint_common.mdl import ready as mdl_ready
from voxprint_common.mdl.status import StatusError


@dataclass(frozen=True)
class Ready:
    """MDL reports ready. The main window may open."""


@dataclass(frozen=True)
class Failed:
    """Models are not ready. ``message`` is one plain sentence."""

    message: str


def ensure_ready(progress_cb: Callable[[str], None]) -> Ready | Failed:
    """Return ready only when the MDL status file says so.

    ``progress_cb`` receives one plain sentence. This function does not
    download and does not draw a window.
    """
    progress_cb("Checking models.")
    try:
        if mdl_ready():
            return Ready()
    except StatusError as exc:
        return Failed(str(exc))
    return Failed("models not ready")
