"""Plain byte and time labels. This module does not download."""

from __future__ import annotations

from plotweaver.ui.i18n import tr

_MIB = 1024 * 1024
_GIB = 1024 * 1024 * 1024


def format_size(nbytes: int) -> str:
    """Render a byte count as GB or MB."""
    if nbytes >= _GIB:
        return f"{nbytes / _GIB:.1f} GB"
    if nbytes >= _MIB:
        return f"{nbytes / _MIB:.0f} MB"
    return f"{nbytes} B"


def format_eta(seconds: float) -> str:
    """Render a remaining time as minutes or seconds."""
    if seconds >= 90:
        return tr("eta_min").format(count=max(1, round(seconds / 60)))
    return tr("eta_sec").format(count=max(1, round(seconds)))


def estimate_minutes(nbytes: int) -> int:
    """Rough minutes at 20 MB/s, at least one."""
    seconds = nbytes / (20 * _MIB)
    return max(1, round(seconds / 60))
