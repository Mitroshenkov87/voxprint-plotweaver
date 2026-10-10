"""Palette contrast, catalogues, and the offscreen window self-test."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QApplication

from plotweaver.appinfo import version_label
from plotweaver.settings import model_tier_override, uncensored_models_preference
from plotweaver.ui.i18n import STRINGS
from plotweaver.ui.icons import ICON_NAMES, suite_icon
from plotweaver.ui.splash import Splash
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


def test_settings_hides_abliterated_downloads_below_20gb(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PLOTWEAVER_STATE", str(tmp_path))
    monkeypatch.setenv("PLOTWEAVER_FAKE_GPU", "NVIDIA GeForce RTX 4060 Ti,8.9,16384,14000")
    app = QApplication.instance() or QApplication([])
    window = MainWindow(mock=True)
    window.show()
    window._open_settings()
    assert window.stack.currentIndex() == 4
    assert window.uncensored_models.isEnabled() is False
    assert "published" in window.settings_note.text()
    window.uncensored_models.setChecked(True)
    window._save_settings()
    assert uncensored_models_preference() is False
    model = window.vram_tier.model()
    assert isinstance(model, QStandardItemModel)
    item = model.item(2)
    assert item is not None
    assert item.isEnabled() is False
    assert "16" in window.vram_note.text()
    window.vram_tier.setCurrentIndex(1)
    window._save_settings()
    assert model_tier_override() == "16gb"
    window.vram_tier.setCurrentIndex(2)
    window._save_settings()
    assert model_tier_override() == "auto"
    del app


def test_settings_offers_abliterated_downloads_at_20gb(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PLOTWEAVER_STATE", str(tmp_path))
    monkeypatch.setenv("PLOTWEAVER_FAKE_GPU", "NVIDIA GeForce RTX 4090,8.9,24576,20000")
    app = QApplication.instance() or QApplication([])
    window = MainWindow(mock=True)
    window.show()
    window._open_settings()
    assert window.uncensored_models.isEnabled() is True
    assert window.download_uncensored.isEnabled() is False
    window.uncensored_models.setChecked(True)
    assert window.download_uncensored.isEnabled() is True
    window._save_settings()
    assert uncensored_models_preference() is True
    model = window.vram_tier.model()
    assert isinstance(model, QStandardItemModel)
    item = model.item(2)
    assert item is not None
    assert item.isEnabled() is True
    assert "24" in window.vram_note.text()
    window.vram_tier.setCurrentIndex(2)
    window._save_settings()
    assert model_tier_override() == "24gb"
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
    assert window.about_text() == version_label()
    del app


def test_suite_icons_and_splash() -> None:
    app = QApplication.instance() or QApplication([])
    folder = Path(__file__).parents[1] / "src" / "plotweaver" / "ui" / "icons"
    blob = "\n".join((folder / f"{name}.svg").read_text(encoding="utf-8") for name in ICON_NAMES)
    assert "currentColor" in blob
    assert "floppy" not in blob.casefold()
    icon = suite_icon("save", "#f2f2f5")
    assert not icon.isNull()
    splash = Splash()
    splash.show()
    assert splash.version_text == version_label()
    window = MainWindow(mock=True)
    window.show()
    assert window.about_text() == '0.2.0 RC · build dev "Sefer"'
    save = next(
        button
        for button in window.findChildren(type(window.download_uncensored))
        if button.text() == "Save"
    )
    assert not save.icon().isNull()
    assert not window.download_uncensored.icon().isNull()
    splash.close()
    del app
