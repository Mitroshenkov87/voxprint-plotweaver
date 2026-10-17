"""Palette contrast, catalogues, and the offscreen window self-test."""

from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton
from voxprint_common.ui.safety import reject_reserved_key
from voxprint_common.ui.splash import HEIGHT, WIDTH, layout

from plotweaver.appinfo import version_label
from plotweaver.paths import splash_art
from plotweaver.settings import model_tier_override, uncensored_models_preference
from plotweaver.ui.gate import FictionGate
from plotweaver.ui.i18n import STRINGS
from plotweaver.ui.icons import ICON_NAMES, suite_icon
from plotweaver.ui.presets import preset_path
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
from plotweaver.ui.vm_shots import save_vm_shots
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


def test_settings_offers_abliterated_downloads_on_16gb(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PLOTWEAVER_STATE", str(tmp_path))
    monkeypatch.setenv("PLOTWEAVER_FAKE_GPU", "NVIDIA GeForce RTX 4060 Ti,8.9,16384,14000")
    app = QApplication.instance() or QApplication([])
    window = MainWindow(mock=True)
    window.show()
    window._open_settings()
    assert window.shell._expert_panel.isVisible() is True
    assert window.uncensored_models.isEnabled() is True
    window.uncensored_models.setChecked(True)
    window._save_settings()
    assert uncensored_models_preference() is True
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


def test_settings_hides_abliterated_downloads_when_nothing_fits(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("PLOTWEAVER_STATE", str(tmp_path))
    monkeypatch.setenv("PLOTWEAVER_FAKE_GPU", "NVIDIA GeForce RTX 4060,8.9,6144,1024")
    app = QApplication.instance() or QApplication([])
    window = MainWindow(mock=True)
    window.show()
    window._open_settings()
    assert window.uncensored_models.isEnabled() is False
    assert "published" in window.settings_note.text()
    window.uncensored_models.setChecked(True)
    window._save_settings()
    assert uncensored_models_preference() is False
    del app


def test_settings_offers_abliterated_downloads_on_24gb(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PLOTWEAVER_STATE", str(tmp_path))
    monkeypatch.setenv("PLOTWEAVER_FAKE_GPU", "NVIDIA GeForce RTX 4090,8.9,24576,20000")
    app = QApplication.instance() or QApplication([])
    window = MainWindow(mock=True)
    window.show()
    window._open_settings()
    assert window.uncensored_models.isEnabled() is True
    assert window.manage_models.isEnabled() is True
    window.uncensored_models.setChecked(True)
    assert window.manage_models.isEnabled() is True
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


def test_brief_form_marks_guesses_and_shows_pov(tmp_path: Path) -> None:
    os.environ["PLOTWEAVER_UI_PROJECT"] = str(tmp_path / "ui")
    app = QApplication.instance() or QApplication([])
    window = MainWindow(mock=True)
    window.show()
    window.mock.setChecked(True)
    window.brief_form.notes.setPlainText("The seal fails.\nThe crew stays.")
    window._draft_brief()
    assert window.title.text()
    assert window.synopsis.toPlainText()
    limited = window.findChild(QPushButton, "chip-pov-limited")
    past = window.findChild(QPushButton, "chip-tense-past")
    first = window.findChild(QPushButton, "chip-pov-first")
    assert limited is not None and limited.isVisible()
    assert past is not None and past.isVisible()
    assert first is not None
    assert window.brief_form._marks["pov"].isVisible()
    assert window.brief_form._marks["tense"].isVisible()
    first.click()
    assert window.brief_form._marks["pov"].isVisible() is False
    window.brief_form.preview_toggle.setChecked(True)
    assert "BOOK BRIEF" in window.brief_form.preview.toPlainText()
    window.brief_form.preview.setPlainText("Use the edited preview.")
    request = window.request_from_form()
    assert request.prompt_override == "Use the edited preview."
    assert request.brief is not None
    menu = window.menuBar().actions()[0].menu()
    assert menu is not None
    assert menu.actions()[0].text() == "How to write a brief"
    del app


def test_vm_shots(tmp_path: Path) -> None:
    paths = save_vm_shots(tmp_path / "shots")
    assert [path.name for path in paths] == [
        "brief-form.png",
        "progress.png",
        "result.png",
        "settings-tier.png",
    ]
    for path in paths:
        assert path.is_file()
        assert path.stat().st_size > 1000


def test_suite_icons_and_splash() -> None:
    app = QApplication.instance() or QApplication([])
    folder = Path(__file__).parents[1] / "src" / "plotweaver" / "ui" / "icons"
    blob = "\n".join((folder / f"{name}.svg").read_text(encoding="utf-8") for name in ICON_NAMES)
    assert "currentColor" in blob
    assert "floppy" not in blob.casefold()
    icon = suite_icon("save", "#f2f2f5")
    assert not icon.isNull()
    boxes = layout()
    assert boxes.width == WIDTH == 960
    assert boxes.height == HEIGHT == 540
    assert splash_art().is_file()
    window = MainWindow(mock=True)
    window.show()
    assert window.about_text() == '0.2.0 RC · build dev "Erev"'
    save = next(
        button
        for button in window.findChildren(type(window.manage_models))
        if button.text() == "Save"
    )
    assert not save.icon().isNull()
    assert not window.manage_models.icon().isNull()
    assert window.mock.text()
    assert window.findChild(QCheckBox, "mock") is window.mock
    del app


def test_shell_catalogs_share_keys() -> None:
    folder = Path(__file__).parents[1] / "src" / "plotweaver" / "ui" / "locales"
    catalogs = {
        name: set(json.loads((folder / f"{name}.json").read_text(encoding="utf-8")))
        for name in ("en", "ru", "de")
    }
    assert catalogs["ru"] == catalogs["en"]
    assert catalogs["de"] == catalogs["en"]


def test_readers_choice_is_not_a_filter(tmp_path: Path) -> None:
    os.environ["PLOTWEAVER_UI_PROJECT"] = str(tmp_path / "ui")
    app = QApplication.instance() or QApplication([])
    window = MainWindow(mock=True)
    window.show()
    window.book.choose("readers", "children")
    assert window.book.get("book.readers") == "child"
    gate = FictionGate()
    assert gate.review_prompt("a child walks home") is None
    assert gate.review_result("a child walks home", "book-1") is None
    state = window.book.state
    assert state is not None
    snapshot = state.snapshot()
    values = snapshot["values"]
    assert isinstance(values, dict)
    for key in values:
        reject_reserved_key(str(key))
    document = json.loads(preset_path().read_text(encoding="utf-8"))
    blob = json.dumps(document)
    assert "minor" not in blob.casefold()
    assert "guard" not in blob.casefold()
    del app


def test_expert_toggle_keeps_pages(tmp_path: Path) -> None:
    os.environ["PLOTWEAVER_UI_PROJECT"] = str(tmp_path / "ui")
    app = QApplication.instance() or QApplication([])
    window = MainWindow(mock=True)
    window.show()
    window.book.set_value("book.pages", 321)
    window.shell.refresh()
    chip = window.findChild(QPushButton, "chip-length-novel")
    reset = window.findChild(QPushButton, "reset-length")
    assert chip is not None and "changes" in chip.text()
    assert reset is not None and reset.isVisible()
    pages = window.book.get("book.pages")
    window._expert.toggle()
    assert window.book.get("book.pages") == pages
    window._expert.toggle()
    assert window.book.get("book.pages") == pages
    reset.click()
    assert window.book.get("book.pages") == 320
    del app


def test_feature_map_keeps_commands_and_flags_the_mock_control() -> None:
    root = Path(__file__).parents[1]
    text = (root / "docs" / "ui" / "FEATURE-MAP.md").read_text(encoding="utf-8")
    assert "proposed removal, needs Aleksandr OK" in text
    for command in (
        "version",
        "doctor",
        "run",
        "export",
        "scenario-mars",
        "bakeoff",
        "gui",
        "vxbook",
        "models",
        "sound",
        "brief",
        "provision",
        "mdl-progress",
        "release-shared",
        "--selftest",
        "--dry-run",
        "--json",
        "--mock",
    ):
        assert command in text
    del root
