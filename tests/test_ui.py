"""Palette contrast, catalogues, and the offscreen window self-test."""

from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QWidget,
)
from voxprint_common.ui.safety import reject_reserved_key
from voxprint_common.ui.splash import HEIGHT, WIDTH, layout

from plotweaver.appinfo import version_label
from plotweaver.domain import BookRequest, Language
from plotweaver.length import STRUCTURAL_MAX_PAGES, plan_shape
from plotweaver.paths import splash_art
from plotweaver.settings import model_tier_override, uncensored_models_preference
from plotweaver.ui.gate import FictionGate
from plotweaver.ui.i18n import STRINGS, tr
from plotweaver.ui.icons import ICON_NAMES, suite_icon
from plotweaver.ui.presets import (
    GENRES,
    LONG_BOOK_NOTE_PAGES,
    READING_WORDS_PER_MINUTE,
    TONES,
    match_plain,
    plain_for_book,
    preset_path,
    reading_estimate,
    resolved_model_id,
)
from plotweaver.ui.shell_shots import sample_synopsis
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
from plotweaver.ui.tools import ToolsDialog
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
    window.brief_form.notes.setPlainText("The seal fails.\nThe crew stays.")
    window._draft_brief()
    assert window.title.text()
    assert window.synopsis.toPlainText()
    limited = window.findChild(QPushButton, "chip-pov-limited")
    past = window.findChild(QPushButton, "chip-tense-past")
    first = window.findChild(QPushButton, "chip-pov-first")
    more = window.findChild(QPushButton, "moreSettings")
    assert limited is not None and limited.isVisible()
    assert more is not None
    more.click()
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
    image = icon.pixmap(22, 22).toImage()
    left = sum(
        1
        for y in range(image.height())
        for x in range(image.width() // 2)
        if image.pixelColor(x, y).alpha() > 20
    )
    assert left > 20
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
    assert all(box.text() != tr("mock") for box in window.findChildren(QCheckBox))
    dialog = ToolsDialog(window, mock=True)
    assert dialog._mock is True
    assert all(box.text() != tr("mock") for box in dialog.findChildren(QCheckBox))
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
    assert window.book.get("book.pages") == 250
    estimate = window.findChild(QLabel, "lengthEstimate")
    assert estimate is not None and "62 500" in estimate.text()
    app.processEvents()
    scroll = window.findChild(QScrollArea, "presetScroll")
    readers = window.findChild(QPushButton, "chip-readers-adults")
    assert scroll is not None and readers is not None
    readers_bottom = readers.mapTo(scroll.viewport(), readers.rect().bottomLeft()).y()
    assert 0 <= readers_bottom <= scroll.viewport().height()
    big = window.findChild(QPushButton, "chip-length-big")
    note = window.findChild(QLabel, "lengthLongNote")
    hint = window.brief_form.chapter_hint
    assert big is not None and big.isEnabled()
    assert note is not None and note.isVisible() is False
    assert "20" in hint.text() and "3" in hint.text()
    window.book.set_value("book.pages", 200)
    window.shell.refresh()
    chip = window.findChild(QPushButton, "chip-length-novel")
    custom = window.findChild(QPushButton, "chip-length-custom")
    reset = window.findChild(QPushButton, "reset-length")
    spin = window.findChild(QSpinBox, "customPages")
    assert chip is not None and "changes" not in chip.text()
    assert custom is not None and custom.isVisible()
    assert reset is not None and reset.isVisible()
    assert spin is not None and spin.maximum() == STRUCTURAL_MAX_PAGES
    assert spin.value() == 200
    assert estimate is not None and "50 000" in estimate.text()
    assert note.isVisible() is False
    pages = window.book.get("book.pages")
    window._expert.toggle()
    app.processEvents()
    assert window.findChild(QSpinBox, "book.pages") is None
    shown = window.findChild(QLabel, "expertPages")
    assert shown is not None and shown.text() == "200"
    assert window.book.get("book.pages") == pages
    spin.setValue(180)
    app.processEvents()
    assert shown.text() == "180"
    assert window.book.get("book.pages") == 180
    window._expert.toggle()
    assert window.book.get("book.pages") == 180
    reset.click()
    assert window.book.get("book.pages") == 250
    assert spin.value() == 250
    spin.setValue(80)
    novella = window.findChild(QPushButton, "chip-length-novella")
    assert novella is not None and novella.isChecked()
    assert custom.isVisible() is False
    window.book.set_value("book.words_per_page", 200)
    window.shell.refresh()
    assert "16 000" in estimate.text()
    window.book.choose("length", "big")
    window.shell.refresh()
    assert window.book.get("book.pages") == 550
    assert big.isChecked()
    assert note.isVisible() is False
    spin.setValue(600)
    assert note.isVisible() is False
    spin.setValue(601)
    assert note.isVisible()
    del app


def test_genre_tone_and_more_settings(tmp_path: Path) -> None:
    os.environ["PLOTWEAVER_UI_PROJECT"] = str(tmp_path / "ui")
    app = QApplication.instance() or QApplication([])
    window = MainWindow(mock=True)
    window.resize(1200, 900)
    window.show()
    app.processEvents()
    document = json.loads(preset_path().read_text(encoding="utf-8"))
    ids = [group["id"] for group in document["groups"]]
    assert ids[:7] == ["genre", "tone", "length", "pov", "readers", "ending", "language"]
    assert ids[7:] == [
        "tense",
        "stops",
        "themes",
        "save-fb2",
        "save-docx",
        "save-markdown",
        "save-marks",
        "sound",
    ]
    drama = window.findChild(QPushButton, "chip-genre-drama")
    other = window.findChild(QPushButton, "chip-genre-custom")
    serious = window.findChild(QPushButton, "chip-tone-serious")
    assert drama is not None and drama.isChecked()
    assert other is not None and other.isVisible() and other.text() == "Other"
    assert other.isChecked() is False
    assert serious is not None and serious.isChecked()
    assert window.brief_form.genre.text() == "Drama"
    assert window.brief_form.tone.text() == "Serious"
    assert window._current_brief().genre == "драма"
    assert window._current_brief().tone == "серьёзный"
    window.brief_form.genre.setText("coastal gothic")
    app.processEvents()
    assert window.book.get("book.genre") == "coastal gothic"
    assert other.isChecked()
    assert drama.isChecked() is False
    other.click()
    app.processEvents()
    assert window.book.get("book.genre") == ""
    window.book.choose("tone", "comic")
    window.shell.refresh()
    app.processEvents()
    assert window.brief_form.tone.text() == "With humour"
    assert window._current_brief().tone == "с юмором"
    window.book.choose("language", "en")
    window.shell.refresh()
    app.processEvents()
    assert window._current_brief().tone == "with humour"
    more = window.findChild(QPushButton, "moreSettings")
    body = window.findChild(QWidget, "moreSettingsBody")
    tense = window.findChild(QPushButton, "chip-tense-past")
    scroll = window.findChild(QScrollArea, "presetScroll")
    assert more is not None and more.text().endswith("More settings")
    assert body is not None and body.isVisible() is False
    assert tense is not None and tense.isVisible() is False
    assert scroll is not None and scroll.verticalScrollBar().maximum() == 0
    tops: list[int] = []
    for row_id in ("genre", "tone", "length", "pov", "readers", "ending", "language"):
        label = window.findChild(QLabel, f"preset-{row_id}")
        assert label is not None and label.isVisible()
        point = label.mapTo(scroll.viewport(), label.rect().bottomLeft())
        assert 0 <= point.y() <= scroll.viewport().height()
        tops.append(point.y())
    assert tops == sorted(tops)
    more.click()
    app.processEvents()
    assert body.isVisible()
    assert tense.isVisible()
    assert match_plain("Драма", GENRES) == "drama"
    assert match_plain("Mit Humor", TONES) == "comic"
    assert plain_for_book("fantasy", "en", GENRES) == "fantasy"
    del app


def test_expert_panel_shows_full_values_without_overlap(tmp_path: Path) -> None:
    os.environ["PLOTWEAVER_UI_PROJECT"] = str(tmp_path / "ui")
    previous_lang = os.environ.get("PLOTWEAVER_LANG")
    os.environ["PLOTWEAVER_LANG"] = "ru"
    app = QApplication.instance() or QApplication([])
    window = MainWindow(mock=True)
    window.resize(1200, 900)
    window.show()
    app.processEvents()
    assert _surface_problems(window) == []
    assert _chips_share_a_line(window, "preset-genre", "chip-genre-thriller")
    long_id = "t-lite-it-2.1-abliterated-iq4-xs"
    full_id = resolved_model_id(vram="auto", tier="standard", detected="16gb")
    assert full_id == "t-lite-it-2.1-q4"
    window._open_settings()
    window._expert.toggle()
    window._expert.toggle()
    shown = window.findChild(QPlainTextEdit, "book.model")
    assert shown is not None and shown.toPlainText() == full_id
    window.book.set_value("book.model", long_id)
    window.shell.refresh()
    app.processEvents()
    app.processEvents()
    panel = window.shell._expert_panel
    scroll = window.findChild(QScrollArea, "expertScroll")
    assert isinstance(panel, QWidget) and panel.isVisible()
    assert scroll is not None
    assert panel.height() >= int(window.height() * 0.7)
    body = scroll.widget()
    assert body is not None
    assert body.width() <= scroll.viewport().width() + 1
    models = body.findChildren(QPlainTextEdit, "book.model")
    assert len(models) == 1
    model = models[0]
    assert model.toPlainText() == long_id
    assert model.horizontalScrollBar().maximum() == 0
    needed = model.fontMetrics().boundingRect(
        0,
        0,
        model.viewport().width(),
        1000,
        int(Qt.TextFlag.TextWordWrap),
        long_id,
    )
    assert model.viewport().height() >= needed.height()
    title = body.findChild(QLabel, "expertTitle")
    assert title is not None and title.text()
    title_rect = _content_rect(title, body)
    model_rect = _content_rect(model, body)
    assert not title_rect.intersects(model_rect)
    assert title_rect.bottom() <= model_rect.top()
    groups = [label for label in body.findChildren(QLabel) if label.objectName() == "settingGroup"]
    # voxprint-common 0.2.5 hides the group heading when Expert has a single group.
    assert all(label.text() for label in groups)
    for label in groups:
        label.ensurePolished()
        assert label.font().pixelSize() >= 14, label.text()
    problems = _expert_layout_problems(body)
    assert problems == []
    assert _surface_problems(window) == []
    scroll_rows = window.findChild(QScrollArea, "presetScroll")
    assert scroll_rows is not None
    assert scroll_rows.horizontalScrollBar().maximum() == 0
    for name in ("chip-genre-thriller", "chip-length-big", "chip-ending-tragic"):
        chip = window.findChild(QPushButton, name)
        assert chip is not None and chip.isVisible()
        origin = chip.mapTo(scroll_rows.viewport(), QPoint(0, 0))
        assert origin.x() >= 0
        assert origin.x() + chip.width() <= scroll_rows.viewport().width() + 1
    hint = window.findChild(QLabel, "bookTextHint")
    assert hint is not None and hint.isVisible()
    assert hint.text() == "Здесь появится текст книги"
    assert all(version_label() not in label.text() for label in window.findChildren(QLabel))
    assert sample_synopsis("ru") == "Ночной паром сел на мель. Смотритель остаётся."
    assert sample_synopsis("en") == "A night ferry sticks. The keeper stays."
    if previous_lang is None:
        os.environ.pop("PLOTWEAVER_LANG", None)
    else:
        os.environ["PLOTWEAVER_LANG"] = previous_lang
    del app


def _content_rect(widget: QWidget, ancestor: QWidget) -> QRect:
    return QRect(widget.mapTo(ancestor, QPoint(0, 0)), widget.size())


def _chips_share_a_line(window: QWidget, label_name: str, chip_name: str) -> bool:
    """Return whether a chip still sits on its label's line."""
    label = window.findChild(QLabel, label_name)
    chip = window.findChild(QPushButton, chip_name)
    if label is None or chip is None:
        return False
    label_y = label.mapTo(window, QPoint(0, 0)).y()
    chip_y = chip.mapTo(window, QPoint(0, 0)).y()
    return abs(label_y - chip_y) < 20


def _render_window(window: QWidget) -> QImage:
    image = QImage(window.size(), QImage.Format.Format_ARGB32)
    image.fill(0xFF17171C)
    painter = QPainter(image)
    window.render(painter, QPoint())
    painter.end()
    return image


def _uniform_light(image: QImage, x: int, y: int, size: int = 8) -> bool:
    """Return whether an ``size`` square is a near-white background."""
    if x < 0 or y < 0 or x + size > image.width() or y + size > image.height():
        return False
    light = 0
    for yy in range(y, y + size):
        for xx in range(x, x + size):
            color = image.pixelColor(xx, yy)
            if color.red() >= 0xE0 and color.green() >= 0xE0 and color.blue() >= 0xE0:
                light += 1
    return light >= size * size * 9 // 10


def _label_contrast(image: QImage, label: QLabel, window: QWidget) -> float | None:
    """Return the contrast of a label's text against the colour behind it."""
    if not label.isVisible() or not label.text().strip():
        return None
    if label.width() < 4 or label.height() < 4:
        return None
    origin = label.mapTo(window, QPoint(0, 0))
    if not window.rect().contains(origin + QPoint(1, 1)):
        return None
    parent: QWidget | None = label.parentWidget()
    while parent is not None and parent is not window:
        if isinstance(parent, QScrollArea):
            point = label.mapTo(parent.viewport(), QPoint(1, 1))
            if not parent.viewport().rect().contains(point):
                return None
        parent = parent.parentWidget()
    rect = QRect(origin, label.size()).intersected(image.rect())
    if rect.width() < 4 or rect.height() < 4:
        return None
    samples: list[QColor] = []
    step_x = max(1, rect.width() // 12)
    step_y = max(1, rect.height() // 6)
    for y in range(rect.top(), rect.bottom() + 1, step_y):
        for x in range(rect.left(), rect.right() + 1, step_x):
            samples.append(image.pixelColor(x, y))
    buckets: dict[tuple[int, int, int], list[QColor]] = {}
    for color in samples:
        key = (color.red() // 16, color.green() // 16, color.blue() // 16)
        buckets.setdefault(key, []).append(color)
    background = max(buckets.values(), key=len)[0]
    foreground = label.palette().color(label.foregroundRole())
    painted = contrast_ratio(foreground.name(), background.name())
    # A short label is mostly background, so the sampled pixels can miss the
    # glyphs. The palette colour is the stylesheet text. A light glyph on a
    # light card still fails both checks.
    lightest = max(samples, key=lambda color: color.red() + color.green() + color.blue())
    return max(painted, contrast_ratio(lightest.name(), background.name()))


def _surface_problems(window: QWidget) -> list[str]:
    """Return light backgrounds and labels below a 4.5:1 contrast ratio."""
    image = _render_window(window)
    problems: list[str] = []
    for scroll in window.findChildren(QScrollArea):
        if not scroll.isVisible():
            continue
        viewport = scroll.viewport()
        origin = viewport.mapTo(window, QPoint(0, 0))
        probes = (
            (2, 2),
            (max(2, viewport.width() // 2), 2),
            (2, max(2, viewport.height() // 2)),
        )
        for dx, dy in probes:
            if _uniform_light(image, origin.x() + dx, origin.y() + dy):
                problems.append(f"light background {scroll.objectName() or 'scroll'}")
                break
    for edit in window.findChildren(QPlainTextEdit):
        if not edit.isVisible():
            continue
        viewport = edit.viewport()
        origin = viewport.mapTo(window, QPoint(0, 0))
        if _uniform_light(image, origin.x() + 2, origin.y() + 2):
            problems.append(f"light text {edit.objectName() or 'text'}")
    for label in window.findChildren(QLabel):
        ratio = _label_contrast(image, label, window)
        if ratio is not None and ratio < 4.5:
            problems.append(f"contrast {ratio:.2f} {label.objectName() or label.text()}")
    return problems


def _expert_layout_problems(body: QWidget) -> list[str]:
    """Return overlap and clipping failures for the open Expert panel."""
    problems: list[str] = []
    widgets = [
        widget
        for widget in body.findChildren(QWidget)
        if widget.isVisible() and widget.width() > 2 and widget.height() > 2
    ]
    for index, left in enumerate(widgets):
        left_rect = _content_rect(left, body)
        for right in widgets[index + 1 :]:
            if left.isAncestorOf(right) or right.isAncestorOf(left):
                continue
            inter = left_rect.intersected(_content_rect(right, body))
            if inter.width() > 4 and inter.height() > 4:
                problems.append(
                    f"overlap {left.objectName() or left.metaObject().className()}"
                    f" and {right.objectName() or right.metaObject().className()}"
                )
    for label in body.findChildren(QLabel):
        if not label.isVisible() or not label.text().strip():
            continue
        if label.wordWrap():
            needed = label.heightForWidth(max(1, label.width()))
            if label.height() + 2 < needed:
                problems.append(f"clipped label {label.text()}")
            continue
        if label.fontMetrics().horizontalAdvance(label.text()) > label.width() + 1:
            problems.append(f"clipped label {label.text()}")
    for box in body.findChildren(QCheckBox):
        if not box.isVisible() or not box.text().strip():
            continue
        needed = box.fontMetrics().horizontalAdvance(box.text()) + 28
        if needed > box.width() + 1:
            problems.append(f"clipped check {box.text()}")
    for combo in body.findChildren(QComboBox):
        if not combo.isVisible():
            continue
        fitted = combo.property("fittedText")
        if isinstance(fitted, str) and fitted != combo.currentText():
            problems.append(f"clipped combo {combo.objectName()}: {fitted}")
    return problems


def test_save_menu_and_the_audiobook_action(tmp_path: Path) -> None:
    os.environ["PLOTWEAVER_UI_PROJECT"] = str(tmp_path / "ui")
    previous_lang = os.environ.get("PLOTWEAVER_LANG")
    os.environ["PLOTWEAVER_LANG"] = "en"
    app = QApplication.instance() or QApplication([])
    window = MainWindow(mock=True)
    window.show()
    app.processEvents()
    save = window.shell._save
    assert isinstance(save, QPushButton)
    more = window.findChild(QPushButton, "saveMore")
    assert more is not None and more.text() == "▾"
    bar = save.parentWidget()
    assert bar is not None
    assert all(
        button.text() not in {"Save as", "Save a copy"} for button in bar.findChildren(QPushButton)
    )
    texts = [action.text() for action in window._save_menu.actions()]
    assert texts == ["Save as", "Save a copy"]
    window._save_as()
    window._save_copy()
    assert window.sound_button.text() == "Prepare for audiobook"
    assert tr("sound_markup") == "Prepare for audiobook"
    assert STRINGS["de"]["sound_markup"] == "Für Hörbuch vorbereiten"
    assert STRINGS["ru"]["book_placeholder"] == "Здесь появится текст книги"
    assert STRINGS["de"]["book_placeholder"] == "Hier erscheint der Text des Buches"
    hint = window.findChild(QLabel, "bookTextHint")
    assert hint is not None and hint.text() == "The book text will appear here"
    if previous_lang is None:
        os.environ.pop("PLOTWEAVER_LANG", None)
    else:
        os.environ["PLOTWEAVER_LANG"] = previous_lang
    del app


def test_page_presets_and_the_chapter_cap() -> None:
    assert READING_WORDS_PER_MINUTE == 250
    assert reading_estimate(250, 250) == (250, 62_500, 250)
    assert reading_estimate(25, 250) == (25, 6_250, 25)
    document = json.loads(preset_path().read_text(encoding="utf-8"))
    length = next(group for group in document["groups"] if group["id"] == "length")
    assert length["default"] == "novel"
    values = {option["id"]: option["values"] for option in length["options"]}
    assert values == {
        "story": {"book.pages": 25},
        "novella": {"book.pages": 80},
        "novel": {"book.pages": 250},
        "big": {"book.pages": 550},
    }
    assert STRUCTURAL_MAX_PAGES == 2000
    assert LONG_BOOK_NOTE_PAGES == 600
    story = BookRequest(title="T", language=Language.EN, synopsis="s", target_words=25 * 250)
    novel = BookRequest(title="T", language=Language.EN, synopsis="s", target_words=250 * 250)
    big = BookRequest(title="T", language=Language.EN, synopsis="s", target_words=550 * 250)
    huge = BookRequest(title="T", language=Language.EN, synopsis="s", target_words=2000 * 250)
    assert story.shape() == plan_shape(25 * 250, "en", None, 2)
    assert novel.shape() == plan_shape(250 * 250, "en", None, 2)
    assert big.shape() == plan_shape(550 * 250, "en", None, 2)
    assert huge.shape() == plan_shape(2000 * 250, "en", None, 2)
    assert novel.shape()[0] == 20
    assert big.shape() == (43, 3, 1065)
    assert huge.shape()[0] == 156


def test_feature_map_keeps_commands_and_flags_the_mock_control() -> None:
    root = Path(__file__).parents[1]
    text = (root / "docs" / "ui" / "FEATURE-MAP.md").read_text(encoding="utf-8")
    phrase = "removed from GUI, approved by Aleksandr 2026-10-17 12:39 MSK; CLI --mock stays"
    assert phrase in text
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
