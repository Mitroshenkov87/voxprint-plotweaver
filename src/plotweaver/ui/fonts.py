"""Bundled UI fonts. A clean Windows Server has no face Qt can draw with.

Inter covers the Latin UI. Noto Sans covers Cyrillic. Segoe UI is the
system fallback when it is installed.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

_registered = False
_FAMILIES = ("Inter", "Noto Sans", "Segoe UI")


def register_ui_fonts() -> None:
    """Register the bundled faces with Qt. Safe to call more than once."""
    global _registered
    if _registered:
        return
    folder = Path(__file__).resolve().parent / "fonts"
    for path in sorted(folder.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(path))
    _registered = True


def ui_font(point_size: float) -> QFont:
    """Application font: Inter, then Noto Sans, then Segoe UI."""
    font = QFont()
    font.setFamilies(list(_FAMILIES))
    font.setPointSizeF(point_size)
    return font


def font_families() -> tuple[str, ...]:
    """Family order used for the UI and the glyph check."""
    return _FAMILIES
