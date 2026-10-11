"""Bundled UI fonts draw Latin and Cyrillic instead of empty boxes."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QImage, QPainter, QRawFont
from PySide6.QtWidgets import QApplication

from plotweaver.ui.fonts import font_families, register_ui_fonts, ui_font


def _indexes(family: str, text: str) -> list[int]:
    font = QFont(family)
    font.setPointSize(24)
    return list(QRawFont.fromFont(font).glyphIndexesForString(text))


def test_latin_and_cyrillic_glyphs_are_not_blank() -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    register_ui_fonts()
    latin = _indexes("Inter", "Plotweaver")
    assert latin
    assert all(index != 0 for index in latin)
    cyrillic = _indexes("Noto Sans", "Привет")
    assert cyrillic
    assert all(index != 0 for index in cyrillic)
    image = QImage(480, 96, QImage.Format.Format_ARGB32)
    background = QColor("#1a1a1a")
    image.fill(background)
    painter = QPainter(image)
    painter.setFont(ui_font(28))
    painter.setPen(QColor("#ffffff"))
    painter.drawText(8, 58, "Plotweaver Привет")
    painter.end()
    painted = background.rgba()
    different = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixel(x, y) != painted
    )
    assert different > 20
    assert font_families() == ("Inter", "Noto Sans", "Segoe UI")
    del app
