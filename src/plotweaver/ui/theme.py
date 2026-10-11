"""Suite palette from voxprint-common, plus Plotweaver's splash violet.

The splash bar is not a theme token. ``SPLASH`` is the identity colour passed
to the shared splash. Acrylic on Windows stays in this module.
"""

from __future__ import annotations

import ctypes
import sys

from voxprint_common.ui.theme import (
    ACCENT,
    ACCENT_HOVER,
    ACCENT_SOFT,
    ACCENT_STRONG,
    AMBER,
    CARD_GLASS,
    CARD_PLAIN,
    CONTROL_BG,
    CONTROL_BORDER,
    CONTROL_HOVER,
    GREEN,
    MENU_BG,
    MENU_SELECTION,
    NOTE_BG,
    NOTE_BORDER,
    PRIMARY,
    PRIMARY_BORDER,
    PRIMARY_DISABLED_BG,
    PRIMARY_DISABLED_TEXT,
    PRIMARY_HOVER,
    RED,
    ROOT_GLASS,
    ROOT_PLAIN,
    TEXT,
    TEXT_DISABLED,
    TEXT_FAINT,
    TEXT_MUTED,
    TEXT_ON_ACCENT,
    TEXT_ON_PRIMARY,
    contrast_ratio,
)
from voxprint_common.ui.theme import build_style as suite_style

# Plotweaver's own splash colour. The shared palette does not name one for this app.
SPLASH = "#8b7cff"
WHITE = "#ffffff"

__all__ = [
    "ACCENT",
    "ACCENT_HOVER",
    "ACCENT_SOFT",
    "ACCENT_STRONG",
    "AMBER",
    "CARD_GLASS",
    "CARD_PLAIN",
    "CONTROL_BG",
    "CONTROL_BORDER",
    "CONTROL_HOVER",
    "GREEN",
    "MENU_BG",
    "MENU_SELECTION",
    "NOTE_BG",
    "NOTE_BORDER",
    "PRIMARY",
    "PRIMARY_BORDER",
    "PRIMARY_DISABLED_BG",
    "PRIMARY_DISABLED_TEXT",
    "PRIMARY_HOVER",
    "RED",
    "ROOT_GLASS",
    "ROOT_PLAIN",
    "SPLASH",
    "TEXT",
    "TEXT_DISABLED",
    "TEXT_FAINT",
    "TEXT_MUTED",
    "TEXT_ON_ACCENT",
    "TEXT_ON_PRIMARY",
    "WHITE",
    "build_style",
    "contrast_ratio",
    "enable_acrylic",
]


def build_style(*, glass: bool) -> str:
    """Suite stylesheet, plus the menu bar and tool buttons this window uses."""
    root = ROOT_GLASS if glass else ROOT_PLAIN
    extra = f"""
    QMainWindow {{ background: {root}; color: {TEXT}; }}
    QMenuBar {{ background: {root}; color: {TEXT}; }}
    QMenuBar::item:selected {{ background: {MENU_SELECTION}; }}
    QToolButton {{
        background: transparent;
        color: {TEXT};
        border: none;
        padding: 4px;
    }}
    """
    return suite_style(glass) + extra


def enable_acrylic(hwnd: int) -> bool:
    """Windows 11 Acrylic. Returns False on every other platform."""
    if sys.platform != "win32" or hwnd == 0:
        return False
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return False
    try:
        dwmapi = windll.dwmapi
    except AttributeError:
        return False
    backdrop = ctypes.c_int(3)  # DWMSBT_TRANSIENTWINDOW, acrylic
    result = dwmapi.DwmSetWindowAttribute(
        ctypes.c_void_p(hwnd),
        ctypes.c_uint(38),
        ctypes.byref(backdrop),
        ctypes.sizeof(backdrop),
    )
    return int(result) == 0
