"""Palette contrast, catalogues, and the offscreen window self-test."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import QApplication

from plotweaver.settings import optional_models_preference
from plotweaver.ui.i18n import STRINGS
from plotweaver.ui.theme import (
    ACCENT_STRONG,
    CARD_PLAIN,
    MENU_SELECTION,
    PRIMARY,
    ROOT_PLAIN,
    TEXT,
    TEXT_FAINT,
    TEXT_MUTED,
    TEXT_ON_PRIMARY,
    WHITE,
    contrast_ratio,
)
from plotweaver.ui.window import MainWindow


def test_text_contrast_on_solid_colours() -> None:
    pairs = (
        (TEXT, ROOT_PLAIN),
        (TEXT, CARD_PLAIN),
        (TEXT_MUTED, CARD_PLAIN),
        (TEXT_FAINT, CARD_PLAIN),
        (TEXT_ON_PRIMARY, PRIMARY),
        (WHITE, MENU_SELECTION),
        (WHITE, ACCENT_STRONG),
    )
    for foreground, background in pairs:
        assert contrast_ratio(foreground, background) >= 4.5


def test_catalogues_share_keys() -> None:
    english = set(STRINGS["en"])
    assert set(STRINGS["ru"]) == english
    assert set(STRINGS["de"]) == english


def test_settings_page_saves_optional_models(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PLOTWEAVER_STATE", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    window = MainWindow(mock=True)
    window.show()
    window._open_settings()
    assert window.stack.currentIndex() == 4
    window.optional_models.setChecked(True)
    window._save_settings()
    assert optional_models_preference() is True
    assert window.settings_status.text()
    del app


def test_window_selftest(tmp_path: Path) -> None:
    os.environ["PLOTWEAVER_UI_PROJECT"] = str(tmp_path / "ui")
    app = QApplication.instance() or QApplication([])
    window = MainWindow(mock=True)
    window.show()
    window.run_selftest()
    assert "book.vxbook" in window.result_label.text()
    assert window._project is not None
    export = window._project.export_dir
    assert (export / "book.epub").is_file()
    assert (export / "book.fb2").is_file()
    assert (export / "book.vxbook").is_file()
    assert (export / "book.sound.vxbook").is_file()
    assert not (export / "audiobook" / "speaker-marks.txt").is_file()
    assert not (export / "book.docx").is_file()
    del app
