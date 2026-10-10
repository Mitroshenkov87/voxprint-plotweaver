"""Suite save-icon family. Strokes stay currentColor in the files and take a palette tint here."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICON_NAMES = ("save", "save-as", "save-copy", "export", "download")
_DIR = Path(__file__).resolve().parent / "icons"


def suite_icon(name: str, color: str, *, size: int = 22) -> QIcon:
    """Rasterize one suite icon at `size` CSS pixels, tinted with an opaque hex colour."""
    if name not in ICON_NAMES:
        raise KeyError(name)
    path = _DIR / f"{name}.svg"
    svg = path.read_text(encoding="utf-8").replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    if not renderer.isValid():
        raise RuntimeError(f"could not render {path.name}")
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
