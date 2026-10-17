"""The book window on the shared text shell.

The idea box, the Write button, the preset chips, and the document view come
from ``surface_for("plotweaver")``. Plotweaver supplies the book presets, the
brief fields, and the same pipeline as ``plotweaver run``. Heavy imports stay
inside the methods that run a book, so constructing the window does not load
the llama client.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPalette, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from voxprint_common.i18n import add_catalogs, set_language
from voxprint_common.i18n import tr as shell_tr
from voxprint_common.paths import state_dir
from voxprint_common.ui.expert import ExpertMode
from voxprint_common.ui.settings import Settings
from voxprint_common.ui.simple_image import Phase, SimpleLayout, SimpleWidget
from voxprint_common.ui.theme import build_shell_style
from voxprint_common.ui.variants import AppSurface, state_names, surface_for

from plotweaver.appinfo import version_label
from plotweaver.atomic import exclusive_lock, write_text
from plotweaver.brief import BookBrief, BriefError, chat_prompt, compile_brief, parse_brief
from plotweaver.domain import BookMode, BookRequest, Language, ModelTier
from plotweaver.errors import PlotweaverError
from plotweaver.length import SAFETY_CHAPTER_CEILING, STRUCTURAL_MAX_PAGES
from plotweaver.llm import LLMBackend
from plotweaver.settings import (
    model_tier_override,
    save_model_tier_override,
    save_uncensored_models,
    uncensored_models_preference,
)
from plotweaver.store import Project
from plotweaver.textio import read_text
from plotweaver.ui.brief_form import BriefForm
from plotweaver.ui.fonts import register_ui_fonts, ui_font
from plotweaver.ui.gate import FictionGate
from plotweaver.ui.i18n import tr, ui_language
from plotweaver.ui.icons import suite_icon
from plotweaver.ui.locked_io import install_locked_writes
from plotweaver.ui.presets import (
    GENRES,
    LONG_BOOK_NOTE_PAGES,
    MAX_SCENES_PER_CHAPTER,
    TONES,
    PlainChoice,
    book_presets,
    book_settings,
    grouped_number,
    match_plain,
    plain_for_book,
    reading_estimate,
    resolved_model_id,
)
from plotweaver.ui.theme import (
    CARD_PLAIN,
    CONTROL_BG,
    TEXT,
    TEXT_ON_PRIMARY,
    enable_acrylic,
    scrollbar_style,
)
from plotweaver.ui.tools import ToolsDialog, run_captured

_LOCALES = Path(__file__).resolve().parent / "locales"
_POV = {
    "third-person limited": "limited",
    "first person": "first",
    "third-person omniscient": "omniscient",
}
_TENSE = {"past": "past", "present": "present"}
_READERS = {"adult": "adults", "teen": "teenagers", "child": "children"}
_ENDING = ("closed", "open", "bittersweet", "twist", "tragic")
_GUESSES = {
    "language": "language",
    "genre": "genre",
    "tone": "tone",
    "pov": "pov",
    "tense": "tense",
    "readers": "audience",
    "ending": "ending_type",
    "themes": "dark_themes",
    "length": "pages",
}
_MORE_ROWS = (
    "tense",
    "stops",
    "themes",
    "save-fb2",
    "save-docx",
    "save-markdown",
    "save-marks",
    "sound",
)


class _RunThread(QThread):
    """One book run off the UI thread."""

    progressed = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        project: Project,
        request_mock: bool,
        yes: bool,
        approve: bool,
        export_to: Path | None,
    ) -> None:
        super().__init__()
        self.project = project
        self.request_mock = request_mock
        self.yes = yes
        self.approve = approve
        self.export_to = export_to

    def run(self) -> None:
        """Run the pipeline and emit the result or the error text."""
        from plotweaver.install import prepare_real_models
        from plotweaver.runner import run_book

        try:
            if not self.request_mock:
                request = self.project.request()
                prepare_real_models(request, on_progress=self.progressed.emit)
                self.project.save_request(request)
            result = run_book(
                self.project,
                _backend(self.request_mock),
                yes=self.yes,
                approve=self.approve,
                on_progress=self.progressed.emit,
                export_to=self.export_to or self.project.export_dir,
            )
        except Exception as exc:  # noqa: BLE001 - show the message, keep the window
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(result)


def _zero_stretches(layout: QVBoxLayout) -> None:
    for index in range(layout.count()):
        layout.setStretch(index, 0)


def _paint_dark(widget: QWidget, colour: str) -> None:
    """Fill a widget from the suite palette.

    A stylesheet background does not paint a scroll viewport. Qt fills that
    viewport from QPalette.Base, which is light on this platform, and the
    shell's light text then disappears. The same paint is what
    ``voxprint_common.ui.simple_image._darken`` does for the history strip
    and the expert scroll only.
    """
    color = QColor(colour)
    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.Window, color)
    palette.setColor(QPalette.ColorRole.Base, color)
    widget.setPalette(palette)
    widget.setAutoFillBackground(True)


def _paint_scroll(scroll: QScrollArea, colour: str) -> None:
    _paint_dark(scroll, colour)
    _paint_dark(scroll.viewport(), colour)
    inner = scroll.widget()
    if isinstance(inner, QWidget):
        _paint_dark(inner, colour)


def _row_index(layout: QVBoxLayout, row_id: str) -> int:
    """Return the preset row whose label is ``preset-{row_id}``."""
    name = f"preset-{row_id}"
    for index in range(layout.count()):
        item = layout.itemAt(index)
        row = None if item is None else item.layout()
        if row is None:
            continue
        for child_index in range(row.count()):
            child = row.itemAt(child_index)
            widget = None if child is None else child.widget()
            if isinstance(widget, QLabel) and widget.objectName() == name:
                return index
    return -1


def _length_row_index(layout: QVBoxLayout) -> int:
    """Return the preset row that holds the length chips."""
    found = _row_index(layout, "length")
    return 1 if found < 0 else found


def _backend(mock: bool) -> LLMBackend:
    from plotweaver.hardware import require_supported_gpu
    from plotweaver.llama_release import ensure_llama_server
    from plotweaver.llama_server import LlamaServer
    from plotweaver.optional_mock import mock_backend

    if mock:
        return mock_backend()
    require_supported_gpu()
    return LlamaServer(ensure_llama_server())


class BookScreen(SimpleWidget):
    """The shared simple screen, with the book form living on the empty page."""

    def __init__(
        self,
        layout: SimpleLayout,
        settings: Settings,
        *,
        on_generate: Callable[[], None] | None = None,
        on_command: Callable[[str], None] | None = None,
        on_chip: Callable[[str], None] | None = None,
        on_length: Callable[[], None] | None = None,
        compiled: Callable[[], str] | None = None,
        surface: AppSurface | None = None,
    ) -> None:
        self._on_chip = on_chip
        self._on_length = on_length
        self._compiled = compiled
        self._after_paint: Callable[[], None] | None = None
        self._live = False
        self.export_text = ""
        super().__init__(
            layout,
            settings,
            on_generate=on_generate,
            on_command=on_command,
            surface=surface,
        )
        self._fit_shell()
        self._live = True

    def refresh(self, *, prompt: bool = False) -> None:
        """Paint the shell, then the book status row and the compiled brief."""
        super().refresh(prompt=prompt)
        if self._live:
            self._paint_book()

    def _choose(self, row_id: str, value: str) -> None:
        super()._choose(row_id, value)
        if self._on_chip is not None:
            self._on_chip(row_id)
        self._notify_length()

    def _reset_group(self, row_id: str) -> None:
        super()._reset_group(row_id)
        self._notify_length()

    def _on_expert_edit(self, setting_id: str, value: object) -> None:
        super()._on_expert_edit(setting_id, value)
        if setting_id in {"book.pages", "book.words_per_page"}:
            self._notify_length()

    def _notify_length(self) -> None:
        if self._on_length is not None:
            self._on_length()

    def _fit_shell(self) -> None:
        prompt = self._prompt
        if isinstance(prompt, QPlainTextEdit):
            prompt.setFixedHeight(96)
        button = self._generate_button
        if isinstance(button, QPushButton):
            button.setMinimumHeight(96)
            if button.minimumWidth() < 168:
                button.setMinimumWidth(168)
        cancel = QPushButton(shell_tr("simple.cancel"))
        cancel.setObjectName("statusCancel")
        cancel.clicked.connect(self._cancel)
        self._status_cancel = cancel
        row = self._status_row.layout()
        if row is not None:
            row.addWidget(cancel)
        cancel.hide()

    def _paint_book(self) -> None:
        busy = self._layout.phase is Phase.BUSY
        self._status_cancel.setVisible(busy)
        if busy:
            self._status_row.show()
        elif self._layout.eta_seconds is None:
            self._status_row.hide()
        self._show_compiled()
        document = self._document
        if (
            self._layout.phase is Phase.READY
            and self.export_text
            and isinstance(document, QPlainTextEdit)
        ):
            document.setPlainText(self.export_text)
        if self._after_paint is not None:
            self._after_paint()

    def _show_compiled(self) -> None:
        if self._compiled is None or not self._expert_panel.isVisible():
            return
        state = self._layout.state
        if state is None or not state.has("book.prompt") or state.get("book.prompt") != "":
            return
        edit = self.root.findChild(QPlainTextEdit, "book.prompt")
        if edit is None:
            return
        edit.blockSignals(True)
        edit.setPlainText(self._compiled())
        edit.blockSignals(False)


class MainWindow(QMainWindow):
    """Write a book from the shell. Simple mode is the default."""

    def __init__(self, mock: bool = False) -> None:
        super().__init__()
        register_ui_fonts()
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setFont(ui_font(10))
        install_locked_writes()
        set_language(ui_language())
        add_catalogs(_LOCALES)
        self._use_mock = mock
        self._clicks: list[float] = []
        self._egg_shown = False
        self._thread: _RunThread | None = None
        self._project: Project | None = None
        self._refs: list[str] = []
        self._waiting = False
        self._auto_model = ""
        self._seq = 0
        surface = surface_for("plotweaver")
        self._setting_specs = book_settings()
        presets = book_presets(self._setting_specs)
        self._state_dir = state_dir() / surface.app_id
        settings_name, history_name = state_names(surface)
        fresh = not (self._state_dir / settings_name).is_file()
        self.book = SimpleLayout(
            presets=presets,
            settings=self._setting_specs,
            state_dir=self._state_dir,
            gate=FictionGate(),
            state_name=settings_name,
            history_name=history_name,
        )
        if fresh:
            saved_tier = model_tier_override()
            if saved_tier != "auto":
                self.book.set_value("book.vram", saved_tier)
            if uncensored_models_preference():
                self.book.set_value("book.abliterated", True)
        self._expert = ExpertMode()
        self.shell = BookScreen(
            self.book,
            self._setting_specs,
            on_generate=lambda: self.start(synchronous=False),
            on_command=self._on_command,
            on_chip=self._on_chip,
            on_length=self._sync_length,
            compiled=self._compiled_prompt,
            surface=surface,
        )
        self.shell._after_paint = self._sync_model
        self._expert.subscribe(self._on_expert_flag)
        self.shell.root.setObjectName("shell")
        self.setObjectName("shell")
        self.setCentralWidget(self.shell.root)
        self.setWindowTitle(shell_tr("splash.app.plotweaver"))
        self.resize(1200, 900)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(build_shell_style(False) + scrollbar_style())
        self._build_form()
        self._contain_presets()
        self._build_expert_extras()
        self._build_result_actions()
        self._build_menus()
        self._restore_geometry()
        self.shell.set_expert(self._expert.enabled())
        if self._expert.enabled():
            self._tune_expert()
        self.shell.refresh()
        QTimer.singleShot(0, self._check_update)

    def showEvent(self, event: object) -> None:
        """Turn on Acrylic when Windows can blur this window."""
        super().showEvent(event)  # type: ignore[arg-type]
        self._fit_preset_height()
        if enable_acrylic(int(self.winId())):
            self.setStyleSheet(build_shell_style(True) + scrollbar_style())

    def resizeEvent(self, event: object) -> None:
        """Keep the preset list from swallowing the book form."""
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._fit_preset_height()

    def closeEvent(self, event: object) -> None:
        """Remember where the window sat."""
        self._save_geometry()
        super().closeEvent(event)  # type: ignore[arg-type]

    def about_text(self) -> str:
        """Return the version line shown in About."""
        return version_label()

    def request_from_form(self) -> BookRequest:
        """Read the brief, the chips, and the expert paths into one request."""
        brief = self._current_brief()
        formats = ["epub"]
        if self._flag("book.export.fb2"):
            formats.append("fb2")
        if self._flag("book.export.docx"):
            formats.append("docx")
        if self._flag("book.export.markdown"):
            formats.append("markdown")
        if self._flag("book.export.marks"):
            formats.append("speaker-marks")
        override = self._text("book.prompt").strip() or self.brief_form.override_text()
        target = brief.target_words
        if self.target_words.value() > 0:
            target = self.target_words.value()
        request = BookRequest(
            title=brief.title or "Untitled",
            author=self.author.text().strip(),
            language=_language(brief.language),
            synopsis=brief.synopsis,
            genre=brief.genre,
            target_words=target,
            chapter_count=brief.chapter_count,
            scenes_per_chapter=brief.derived_scenes(),
            pov=brief.pov,
            tense=brief.tense,
            dark_themes=brief.dark_themes,
            tier=_tier(self._text("book.tier")),
            mode=_mode(self._text("book.mode")),
            reference_paths=list(self._refs),
            export_formats=formats,
            sound_markup=self._flag("book.sound"),
            brief=brief.to_dict(),
            prompt_override=override,
        )
        self._apply_paths(request)
        return request

    def start(self, *, synchronous: bool, approve: bool = False) -> None:
        """Start or resume the book. A dry run only prints the plan."""
        synopsis = self.synopsis.toPlainText().strip()
        if not synopsis and not approve:
            QMessageBox.warning(self, tr("app"), tr("synopsis"))
            return
        self.shell.set_prompt_text(self.synopsis.toPlainText())
        if self.dry_run.isChecked() and not approve:
            if self.book.phase is Phase.BUSY:
                self.book.cancel()
                self.shell.refresh()
            self._show_plan()
            return
        if self.book.phase is not Phase.BUSY:
            if not self.book.generate():
                return
            self.shell.refresh()
        request = self.request_from_form()
        folder = self._project_path()
        if self._project is None:
            self._project = Project.open_or_create(folder, request)
        self._project.save_request(request)
        export_to = self._export_path()
        self.approve.setVisible(False)
        self._waiting = False
        mock = self._use_mock
        yes = self.skip_approval.isChecked()
        if synchronous:
            self._run_sync(mock, yes, approve, export_to)
            return
        if self._thread is not None and self._thread.isRunning():
            return
        self._thread = _RunThread(self._project, mock, yes, approve, export_to)
        self._thread.progressed.connect(self._on_progress)
        self._thread.finished_ok.connect(self._on_done)
        self._thread.failed.connect(self._on_fail)
        self._thread.start()

    def run_selftest(self) -> None:
        """Fill the form and write a one-chapter book with the mock backend."""
        self.title.setText("Self-test")
        self.author.setText("Илья Воронов")
        self.book.choose("save-fb2", "on")
        self.language.setCurrentIndex(0)
        self.synopsis.setPlainText(
            "Короткий синопсис для проверки окна. Ещё одна фраза про корабль и пыль."
        )
        self.book.set_value("book.pages", 4)
        self.book.set_value("book.words_per_page", 200)
        self.book.set_value("book.chapters", 1)
        self.book.set_value("book.dark", False)
        previous_mock = self._use_mock
        self._use_mock = True
        self.skip_approval.setChecked(False)
        self.dry_run.setChecked(False)
        self.shell.refresh()
        try:
            self.start(synchronous=True)
            guard = 0
            while self._waiting and guard < 8:
                guard += 1
                self.start(synchronous=True, approve=True)
            if self.book.phase is not Phase.READY:
                raise RuntimeError("self-test did not reach the result")
            if "book.vxbook" not in self.result_label.text():
                raise RuntimeError("self-test result has no book.vxbook path")
            self.sound_button.click()
        finally:
            self._use_mock = previous_mock
        if self._project is None or not (self._project.export_dir / "book.sound.vxbook").is_file():
            raise RuntimeError("self-test did not write book.sound.vxbook")

    def _build_form(self) -> None:
        empty = self.shell._stack.widget(0)
        hint = empty.findChild(QLabel, "emptyHint")
        if hint is not None:
            hint.hide()
        host = QWidget()
        form = QFormLayout(host)
        self._title_label = QLabel(shell_tr("splash.app.plotweaver"))
        self._title_label.setObjectName("titlebar")
        self._title_label.mousePressEvent = self._logo_click  # type: ignore[method-assign]
        form.addRow(self._title_label)
        version = QLabel(version_label())
        version.setObjectName("faint")
        form.addRow(version)
        subtitle = QLabel(tr("subtitle"))
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        form.addRow(subtitle)
        gpu = QLabel(tr("gpu_note"))
        gpu.setObjectName("faint")
        gpu.setWordWrap(True)
        form.addRow(gpu)
        self.update_note = QLabel("")
        self.update_note.setWordWrap(True)
        form.addRow(self.update_note)
        self._egg = QLabel("")
        self._egg.setObjectName("muted")
        form.addRow(self._egg)
        self.title = QLineEdit()
        self.author = QLineEdit()
        self.language = QComboBox()
        self.language.setObjectName("language")
        self.language.addItem("Russian", Language.RU.value)
        self.language.addItem("English", Language.EN.value)
        self.language.currentIndexChanged.connect(lambda _index: self._language_changed())
        prompt = self.shell._prompt
        self.synopsis: QPlainTextEdit = (
            prompt if isinstance(prompt, QPlainTextEdit) else QPlainTextEdit()
        )
        self.brief_form = BriefForm(host)
        self.dark = QCheckBox(tr("dark"))
        self.dark.hide()
        self.chapters = QSpinBox()
        self.chapters.setRange(0, SAFETY_CHAPTER_CEILING)
        self.chapters.hide()
        self.brief_form.bind(self.title, self.language, self.synopsis, self.dark, self.chapters)
        self.brief_form.genre.textChanged.connect(
            lambda text: self._on_plain_typed("book.genre", GENRES, text)
        )
        self.brief_form.tone.textChanged.connect(
            lambda text: self._on_plain_typed("book.tone", TONES, text)
        )
        form.addRow(tr("title"), self.title)
        form.addRow(tr("author"), self.author)
        form.addRow(tr("language"), self.language)
        form.addRow(tr("brief_notes"), self.brief_form.notes)
        buttons = QHBoxLayout()
        buttons.addWidget(self.brief_form.help_button)
        buttons.addWidget(self.brief_form.copy_button)
        buttons.addWidget(self.brief_form.paste_button)
        form.addRow("", buttons)
        self.brief_form.help_button.clicked.connect(self._draft_brief)
        self.brief_form.copy_button.clicked.connect(self._copy_prompt)
        self.brief_form.paste_button.clicked.connect(self._paste_brief)
        files = QHBoxLayout()
        open_synopsis = QPushButton(tr("open_synopsis"))
        open_synopsis.clicked.connect(self._open_synopsis)
        open_brief = QPushButton(tr("open_brief"))
        open_brief.clicked.connect(self._open_brief)
        files.addWidget(open_synopsis)
        files.addWidget(open_brief)
        form.addRow("", files)
        form.addRow(tr("target_words"), self.brief_form.target_label)
        form.addRow("", self.brief_form.chapter_hint)
        form.addRow(tr("genre"), self._mark("genre", self.brief_form.genre))
        form.addRow(tr("subgenre"), self._mark("subgenre", self.brief_form.subgenre))
        form.addRow(tr("tone"), self._mark("tone", self.brief_form.tone))
        form.addRow(tr("pov"), self._mark("pov", self.brief_form.pov, hide=True))
        form.addRow(tr("tense"), self._mark("tense", self.brief_form.tense, hide=True))
        form.addRow(tr("audience"), self._mark("audience", self.brief_form.audience, hide=True))
        form.addRow(tr("setting"), self._mark("setting", self.brief_form.setting))
        people = QVBoxLayout()
        people.addWidget(self.brief_form.characters)
        people.addWidget(self.brief_form.add_character)
        form.addRow(tr("characters"), self._mark("characters", people))
        form.addRow(tr("plot_points"), self._mark("plot_points", self.brief_form.plot_points))
        form.addRow(tr("ending"), self._mark("ending_type", self.brief_form.ending, hide=True))
        form.addRow(
            tr("style_references"),
            self._mark("style_references", self.brief_form.style_references),
        )
        form.addRow("", self.brief_form.preview_toggle)
        form.addRow("", self.brief_form.preview)
        epub = QLabel(tr("epub_always"))
        epub.setObjectName("muted")
        form.addRow(tr("formats"), epub)
        self.ref_label = QLabel("—")
        self.ref_label.setObjectName("muted")
        add = QPushButton(tr("add_ref"))
        add.clicked.connect(self._add_ref)
        refs = QHBoxLayout()
        refs.addWidget(self.ref_label, 1)
        refs.addWidget(add)
        form.addRow(tr("references"), refs)
        self.plan_label = QLabel("")
        self.plan_label.setWordWrap(True)
        self.plan_label.setObjectName("plan")
        form.addRow(self.plan_label)
        scroll = QScrollArea()
        scroll.setObjectName("briefScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(host)
        layout = empty.layout()
        if isinstance(layout, QVBoxLayout):
            _zero_stretches(layout)
            layout.addWidget(scroll, 1)
        _paint_scroll(scroll, CARD_PLAIN)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setObjectName("progressLog")
        self.approve = QPushButton(tr("approve"))
        self.approve.setObjectName("approve")
        self.approve.setVisible(False)
        self.approve.clicked.connect(lambda: self.start(synchronous=False, approve=True))
        busy = self.shell._stack.widget(1)
        busy_layout = busy.layout()
        if isinstance(busy_layout, QVBoxLayout):
            _zero_stretches(busy_layout)
            busy_layout.insertWidget(1, self.log, 1)
            busy_layout.insertWidget(2, self.approve)
        _paint_dark(self.log.viewport(), CONTROL_BG)
        document = self.shell._document
        if isinstance(document, QPlainTextEdit):
            _paint_dark(document.viewport(), CONTROL_BG)
        self.progress_label = self.shell._progress_text
        if not isinstance(self.progress_label, QLabel):
            self.progress_label = QLabel(tr("progress"))
        self.result_label = QLabel(tr("done"))
        self.result_label.setWordWrap(True)
        self.result_label.setObjectName("resultLabel")
        ready = self.shell._stack.widget(2)
        ready_layout = ready.layout()
        if ready_layout is not None:
            ready_layout.insertWidget(0, self.result_label)

    def _mark(self, key: str, widget: QWidget | QVBoxLayout, *, hide: bool = False) -> QWidget:
        host = self.brief_form._marked(key, widget)
        if hide and isinstance(widget, QWidget):
            widget.hide()
        return host

    def _build_expert_extras(self) -> None:
        extras = QWidget()
        extras.setObjectName("expertExtras")
        form = QFormLayout(extras)
        self.skip_approval = QCheckBox(tr("skip_approval"))
        self.skip_approval.setObjectName("skipApproval")
        self.dry_run = QCheckBox(tr("dry_run"))
        self.dry_run.setObjectName("dryRun")
        self.json_report = QCheckBox(tr("json_report"))
        self.json_report.setObjectName("jsonReport")
        self.target_words = QSpinBox()
        self.target_words.setRange(0, 500_000)
        self.target_words.setObjectName("targetWords")
        self.main_gguf = QLineEdit()
        self.least_gguf = QLineEdit()
        self.main_model = QLineEdit()
        self.least_model = QLineEdit()
        self.project_path = QLineEdit()
        self.project_path.setPlaceholderText(tr("choose_project"))
        self.export_path_edit = QLineEdit()
        self.export_path_edit.setPlaceholderText(tr("choose_export"))
        form.addRow("", self.skip_approval)
        form.addRow("", self.dry_run)
        form.addRow("", self.json_report)
        form.addRow(tr("target_words_override"), self.target_words)
        form.addRow(tr("main_gguf"), self.main_gguf)
        form.addRow(tr("least_gguf"), self.least_gguf)
        form.addRow(tr("main_model"), self.main_model)
        form.addRow(tr("least_model"), self.least_model)
        form.addRow(tr("choose_project"), self._path_row(self.project_path, directory=True))
        form.addRow(tr("choose_export"), self._path_row(self.export_path_edit, directory=True))
        self.vram_note = QLabel("")
        self.vram_note.setObjectName("vramNote")
        self.vram_note.setWordWrap(True)
        self.settings_note = QLabel("")
        self.settings_note.setObjectName("settingsNote")
        self.settings_note.setWordWrap(True)
        self.settings_status = QLabel("")
        self.settings_status.setObjectName("settingsStatus")
        self.settings_status.setWordWrap(True)
        form.addRow(self.vram_note)
        form.addRow(self.settings_note)
        form.addRow(self.settings_status)
        save = self._icon_button(tr("settings_save"), "save", primary=True)
        save.clicked.connect(self._save_settings)
        form.addRow(save)
        self.manage_models = self._icon_button(tr("manage_models"), "download")
        self.manage_models.clicked.connect(self._manage_models)
        form.addRow(self.manage_models)
        self.vram_tier = QComboBox()
        self.uncensored_models = QCheckBox(extras)
        self.uncensored_models.hide()
        self._mount_expert_extras(extras)

    def _contain_presets(self) -> None:
        host = self.shell._preset_host
        if not isinstance(host, QWidget):
            return
        parent = host.parentWidget()
        layout = None if parent is None else parent.layout()
        if not isinstance(layout, QVBoxLayout):
            return
        index = layout.indexOf(host)
        if index < 0:
            return
        scroll = QScrollArea()
        scroll.setObjectName("presetScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(host)
        layout.insertWidget(index, scroll)
        self._preset_scroll = scroll
        self._build_length_row()
        self._build_more()
        _paint_scroll(scroll, CARD_PLAIN)
        self._fit_preset_height()

    def _build_length_row(self) -> None:
        """Put the free page count and the reading estimate under the length chips."""
        host = self.shell._preset_host
        layout = None if not isinstance(host, QWidget) else host.layout()
        if not isinstance(layout, QVBoxLayout):
            return
        block = QWidget()
        block.setObjectName("lengthExtras")
        column = QVBoxLayout(block)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(8)
        caption = QLabel(shell_tr("book.length.custom_pages"))
        caption.setObjectName("customPagesLabel")
        caption.setProperty("presetLabel", True)
        caption.setMinimumWidth(108)
        self._custom_pages = QSpinBox()
        self._custom_pages.setObjectName("customPages")
        self._custom_pages.setRange(1, STRUCTURAL_MAX_PAGES)
        self._custom_pages.setValue(max(1, self._integer("book.pages") or 250))
        self._custom_pages.valueChanged.connect(self._on_custom_pages)
        row.addWidget(caption)
        row.addWidget(self._custom_pages)
        row.addStretch(1)
        column.addLayout(row)
        note = QLabel(shell_tr("book.length.long_note"))
        note.setObjectName("lengthLongNote")
        note.setProperty("presetLabel", True)
        note.setWordWrap(True)
        note.hide()
        self._length_note = note
        column.addWidget(note)
        estimate = QLabel("")
        estimate.setObjectName("lengthEstimate")
        estimate.setProperty("presetLabel", True)
        estimate.setWordWrap(True)
        self._length_estimate = estimate
        column.addWidget(estimate)
        layout.insertWidget(_length_row_index(layout) + 1, block)
        self._sync_length()

    def _build_more(self) -> None:
        """Park the less common chips under a More settings expander."""
        host = self.shell._preset_host
        layout = None if not isinstance(host, QWidget) else host.layout()
        if not isinstance(layout, QVBoxLayout):
            return
        body = QWidget()
        body.setObjectName("moreSettingsBody")
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 4, 0, 0)
        column.setSpacing(8)
        for row_id in _MORE_ROWS:
            index = _row_index(layout, row_id)
            if index < 0:
                continue
            item = layout.takeAt(index)
            row = None if item is None else item.layout()
            if isinstance(row, QHBoxLayout):
                column.addLayout(row)
        header = QPushButton("▸  " + shell_tr("book.more"))
        header.setObjectName("moreSettings")
        header.setFlat(True)
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.setStyleSheet(
            "QPushButton#moreSettings {"
            f" text-align: left; padding: 6px 2px; background: transparent;"
            f" border: none; color: {TEXT}; font-weight: 600;"
            "}"
        )
        header.clicked.connect(self._toggle_more)
        self._more_header = header
        self._more_body = body
        body.hide()
        wrap = QWidget()
        wrap.setObjectName("moreSettingsWrap")
        wrap_layout = QVBoxLayout(wrap)
        wrap_layout.setContentsMargins(0, 4, 0, 0)
        wrap_layout.setSpacing(4)
        wrap_layout.addWidget(header)
        wrap_layout.addWidget(body)
        layout.addWidget(wrap)
        self._wire_other("genre", "book.genre")
        self._wire_other("tone", "book.tone")
        self._sync_plain()

    def _toggle_more(self) -> None:
        body = getattr(self, "_more_body", None)
        header = getattr(self, "_more_header", None)
        if not isinstance(body, QWidget) or not isinstance(header, QPushButton):
            return
        open_more = not body.isVisible()
        body.setVisible(open_more)
        mark = "▾  " if open_more else "▸  "
        header.setText(mark + shell_tr("book.more"))
        self._fit_preset_height()

    def _wire_other(self, row_id: str, key: str) -> None:
        button = self.shell.root.findChild(QPushButton, f"chip-{row_id}-custom")
        if button is None:
            return
        button.clicked.connect(lambda _checked=False, setting=key: self._choose_other(setting))

    def _choose_other(self, key: str) -> None:
        if self._text(key) != "":
            self.book.set_value(key, "")
        self.shell.refresh()

    def _on_plain_typed(self, key: str, choices: tuple[PlainChoice, ...], text: str) -> None:
        if self.brief_form._loading:
            return
        stored = match_plain(text, choices)
        if stored == self._text(key):
            return
        self.book.set_value(key, stored)
        self.shell.refresh()

    def _sync_plain(self) -> None:
        """Keep Genre and Tone chips, including Other, on the brief fields."""
        self._show_other("genre", "book.genre", GENRES, self.brief_form.genre)
        self._show_other("tone", "book.tone", TONES, self.brief_form.tone)
        self._fit_preset_height()

    def _show_other(
        self,
        row_id: str,
        key: str,
        choices: tuple[PlainChoice, ...],
        edit: QLineEdit,
    ) -> None:
        button = self.shell.root.findChild(QPushButton, f"chip-{row_id}-custom")
        value = self._text(key)
        known = any(choice.option_id == value for choice in choices)
        if button is not None:
            button.setText(shell_tr("book.other"))
            button.ensurePolished()
            advance = button.fontMetrics().horizontalAdvance(button.text())
            button.setMinimumWidth(advance + 36)
            button.setVisible(True)
            button.setChecked(not known)
        if edit.hasFocus():
            return
        shown = value
        for choice in choices:
            if choice.option_id == value:
                shown = shell_tr(choice.label_key)
                break
        if edit.text() != shown:
            edit.blockSignals(True)
            edit.setText(shown)
            edit.blockSignals(False)

    def _on_custom_pages(self, value: int) -> None:
        if self._integer("book.pages") == value:
            return
        self.book.set_value("book.pages", value)
        self.shell.refresh()

    def _sync_length(self) -> None:
        """Copy pages and words per page onto the free field and the estimate."""
        pages = max(1, self._integer("book.pages") or 250)
        words_per_page = max(1, self._integer("book.words_per_page") or 250)
        spin = getattr(self, "_custom_pages", None)
        if isinstance(spin, QSpinBox) and spin.value() != pages:
            spin.blockSignals(True)
            spin.setValue(pages)
            spin.blockSignals(False)
        label = getattr(self, "_length_estimate", None)
        if isinstance(label, QLabel):
            shown, words, minutes = reading_estimate(pages, words_per_page)
            if minutes >= 60:
                time = shell_tr("book.length.hours", count=max(1, round(minutes / 60)))
            else:
                time = shell_tr("book.length.minutes", count=minutes)
            label.setText(
                shell_tr(
                    "book.length.estimate",
                    pages=grouped_number(shown),
                    words=grouped_number(words),
                    time=time,
                )
            )
        note = getattr(self, "_length_note", None)
        if isinstance(note, QLabel):
            note.setVisible(pages > LONG_BOOK_NOTE_PAGES)
        if hasattr(self, "brief_form"):
            self._sync_hidden()
            self._refresh_target()
        self._fit_preset_height()

    def _fit_preset_height(self) -> None:
        scroll = getattr(self, "_preset_scroll", None)
        if not isinstance(scroll, QScrollArea):
            return
        host = scroll.widget()
        rows = None if host is None else host.layout()
        if not isinstance(rows, QVBoxLayout):
            return
        rows.activate()
        # The seven main rows stay fully visible. More settings can grow the
        # list, and the document view gives up space before a vertical scroll.
        top = scroll.mapTo(self, scroll.rect().topLeft()).y()
        room = max(180, self.height() - top - 120)
        bottoms: list[int] = []
        for index in range(rows.count()):
            item = rows.itemAt(index)
            if item is None:
                continue
            bottom = item.geometry().y() + item.geometry().height()
            if bottom > 0:
                bottoms.append(bottom)
        content = max(bottoms) if bottoms else min(360, room)
        if content <= room:
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            height = content
        else:
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            height = room
        bar = scroll.horizontalScrollBar()
        if bar.isVisible():
            height += bar.height()
        if scroll.maximumHeight() == height and scroll.minimumHeight() == height:
            return
        scroll.setMinimumHeight(height)
        scroll.setMaximumHeight(height)

    def _mount_expert_extras(self, extras: QWidget) -> None:
        scroll = self.shell.root.findChild(QScrollArea, "expertScroll")
        inner = None if scroll is None else scroll.takeWidget()
        if scroll is None or inner is None:
            self.shell._panel_layout.insertWidget(0, extras)
            return
        wrapper = QWidget()
        wrapper.setObjectName("expertBody")
        column = QVBoxLayout(wrapper)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        column.addWidget(inner)
        column.addWidget(extras)
        scroll.setWidget(wrapper)

    def _path_row(self, edit: QLineEdit, *, directory: bool) -> QWidget:
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(edit, 1)
        button = QPushButton("…")
        button.clicked.connect(lambda: self._browse(edit, directory=directory))
        row.addWidget(button)
        return host

    def _browse(self, edit: QLineEdit, *, directory: bool) -> None:
        if directory:
            path = QFileDialog.getExistingDirectory(self, tr("choose_project"))
        else:
            path, _selected = QFileDialog.getOpenFileName(self, tr("add_ref"))
        if path:
            edit.setText(path)

    def _build_result_actions(self) -> None:
        save = self.shell._save
        if isinstance(save, QPushButton):
            save.setIcon(suite_icon("save", TEXT))
            save.setIconSize(QSize(22, 22))
        bar = save.parentWidget() if isinstance(save, QPushButton) else None
        layout = None if bar is None else bar.layout()
        self._save_as_button = self._icon_button(tr("save_as"), "save-as")
        self._save_as_button.clicked.connect(self._save_as)
        self._save_copy_button = self._icon_button(tr("save_copy"), "save-copy")
        self._save_copy_button.clicked.connect(self._save_copy)
        self.sound_button = QPushButton(tr("sound_markup"))
        self.sound_button.setObjectName("soundMarkup")
        self.sound_button.clicked.connect(self._add_sound)
        if layout is not None:
            layout.addWidget(self._save_as_button)
            layout.addWidget(self._save_copy_button)
            layout.addWidget(self.sound_button)

    def _build_menus(self) -> None:
        help_menu = self.menuBar().addMenu(tr("help"))
        help_menu.addAction(tr("help_brief")).triggered.connect(self._show_guide)
        tools = self.menuBar().addMenu(tr("tools"))
        tools.addAction(tr("new")).triggered.connect(self._new_book)
        tools.addAction(tr("tools")).triggered.connect(self._show_tools)
        tools.addAction(tr("window_selftest")).triggered.connect(self.run_selftest)
        tools.addAction(tr("suite_selftest")).triggered.connect(self._suite_selftest)
        tools.addAction(tr("back")).triggered.connect(lambda: self._expert.set_enabled(False))
        menu = self.shell._overflow.menu()
        if menu is None:
            return
        menu.addAction(tr("about"), self._show_about)
        menu.addAction(tr("help_brief"), self._show_guide)
        menu.addAction(tr("new"), self._new_book)
        menu.addAction(tr("tools"), self._show_tools)
        menu.addAction(tr("window_selftest"), self.run_selftest)
        menu.addAction(tr("suite_selftest"), self._suite_selftest)

    def _icon_button(self, text: str, icon: str, *, primary: bool = False) -> QPushButton:
        button = QPushButton(text)
        color = TEXT_ON_PRIMARY if primary else TEXT
        button.setIcon(suite_icon(icon, color))
        button.setIconSize(QSize(22, 22))
        if primary:
            button.setObjectName("primary")
        return button

    def _on_expert_flag(self, enabled: bool) -> None:
        self.shell.set_expert(enabled)
        if enabled:
            self._tune_expert()

    def _on_command(self, command: str) -> None:
        if command == "view.toggle_expert_mode":
            self._expert.toggle()
            return
        if command == "models.manage":
            self._manage_models()
            return
        if command == "file.open_folder":
            self._open_export()
            return
        if command == "view.settings":
            self._open_settings()
            return

    def _on_chip(self, row_id: str) -> None:
        if self.brief_form._loading:
            return
        guess = _GUESSES.get(row_id)
        if guess is not None:
            self.brief_form._clear_guess(guess)
        self._sync_hidden()
        self._refresh_target()

    def _open_settings(self) -> None:
        """Show Expert mode and the VRAM controls."""
        if self._expert.enabled():
            self.shell.set_expert(True)
            self._tune_expert()
            return
        self._expert.set_enabled(True)

    def _tune_expert(self) -> None:
        from plotweaver.registry import uncensored_offer_allowed

        vram = self.shell.root.findChild(QComboBox, "book.vram")
        box = self.shell.root.findChild(QCheckBox, "book.abliterated")
        if isinstance(vram, QComboBox):
            self.vram_tier = vram
        if isinstance(box, QCheckBox):
            self.uncensored_models = box
        self._refresh_vram_tier()
        allowed = uncensored_offer_allowed(self._gpu_total(), self._gpu_free())
        self.uncensored_models.setEnabled(allowed)
        self.uncensored_models.setChecked(uncensored_models_preference() if allowed else False)
        self.manage_models.setEnabled(True)
        self.settings_note.setText(
            tr("settings_uncensored_note") if allowed else tr("settings_uncensored_blocked")
        )
        self.settings_status.setText("")
        self._bind_uncensored()

    def _bind_uncensored(self) -> None:
        box = self.uncensored_models
        if box.receivers("toggled(bool)") > 0:
            box.toggled.disconnect(self._uncensored_toggled)
        box.toggled.connect(self._uncensored_toggled)

    def _uncensored_toggled(self, _checked: bool) -> None:
        self.manage_models.setEnabled(True)

    def _save_settings(self) -> None:
        """Store the VRAM tier and the abliterated-download choice."""
        from plotweaver.registry import uncensored_offer_allowed

        choice = self._selected_override()
        if choice == "24gb" and not self._can_use_24():
            choice = "auto"
        save_model_tier_override(choice)
        if self.book.state is not None and self.book.state.has("book.vram"):
            self.book.set_value("book.vram", choice)
        self._refresh_vram_tier()
        allowed = uncensored_offer_allowed(self._gpu_total(), self._gpu_free())
        enabled = bool(self.uncensored_models.isChecked()) and allowed
        save_uncensored_models(enabled)
        if self.book.state is not None and self.book.state.has("book.abliterated"):
            self.book.set_value("book.abliterated", enabled)
        if not allowed:
            self.uncensored_models.setChecked(False)
            self.settings_status.setText(tr("settings_uncensored_blocked"))
            return
        self.settings_status.setText(tr("settings_saved"))

    def _gpu_total(self) -> float | None:
        from plotweaver.hardware import query_gpu

        gpu = query_gpu()
        if gpu is None:
            return None
        return gpu.total_gb

    def _gpu_free(self) -> float | None:
        from plotweaver.hardware import query_gpu

        gpu = query_gpu()
        if gpu is None:
            return None
        return gpu.free_gb

    def _can_use_24(self) -> bool:
        from plotweaver.registry import tier_option_enabled

        total = self._gpu_total()
        free = self._gpu_free()
        if total is None or free is None:
            return False
        return tier_option_enabled("24gb", total_gb=total, free_gb=free)

    def _set_tier_item_enabled(self, index: int, enabled: bool) -> None:
        model = self.vram_tier.model()
        if not isinstance(model, QStandardItemModel):
            return
        item = model.item(index)
        if item is not None:
            item.setEnabled(enabled)

    def _refresh_vram_tier(self) -> None:
        from plotweaver.registry import detected_tier, resolve_tier

        if not isinstance(self.vram_tier, QComboBox) or self.vram_tier.count() < 3:
            return
        total = self._gpu_total()
        free = self._gpu_free()
        self._set_tier_item_enabled(2, self._can_use_24())
        saved = model_tier_override()
        if saved == "24gb" and not self._can_use_24():
            saved = "auto"
        match saved:
            case "auto":
                index = 0
            case "16gb":
                index = 1
            case "24gb":
                index = 2
            case _:
                index = 0
        self.vram_tier.setCurrentIndex(index)
        if total is None or free is None:
            self.vram_note.setText(tr("settings_vram_blocked"))
            return
        chosen = resolve_tier(total, saved)
        self.vram_note.setText(
            tr("settings_vram_note").format(
                detected=self._tier_label(detected_tier(total)),
                chosen=self._tier_label(chosen),
            )
        )

    def _tier_label(self, tier: str) -> str:
        if tier == "16gb":
            return tr("settings_vram_16")
        if tier == "24gb":
            return tr("settings_vram_24")
        return tier

    def _selected_override(self) -> str:
        value = self.vram_tier.currentData()
        if value in {"auto", "16gb", "24gb"}:
            return str(value)
        return "auto"

    def _sync_model(self) -> None:
        self._sync_length()
        if hasattr(self, "brief_form"):
            self._sync_plain()
        if self.book.state is None or not self.book.state.has("book.model"):
            return
        from plotweaver.registry import detected_tier

        total = self._gpu_total()
        detected = detected_tier(total) if total is not None else "16gb"
        model_id = resolved_model_id(
            vram=self._text("book.vram") or "auto",
            tier=self._text("book.tier") or "standard",
            detected=detected,
        )
        current = self._text("book.model")
        if current and current != self._auto_model:
            return
        if model_id and current != model_id:
            self.book.set_value("book.model", model_id)
            edit = self.shell.root.findChild(QPlainTextEdit, "book.model")
            if edit is not None:
                edit.blockSignals(True)
                edit.setPlainText(model_id)
                edit.blockSignals(False)
        self._auto_model = model_id

    def _compiled_prompt(self) -> str:
        try:
            return compile_brief(self._current_brief())
        except PlotweaverError:
            return ""

    def _current_brief(self) -> BookBrief:
        form = self.brief_form
        pages = max(1, self._integer("book.pages") or 250)
        words = max(1, self._integer("book.words_per_page") or 250)
        chapters = self._integer("book.chapters")
        scenes = self._integer("book.scenes") or 2
        return BookBrief(
            title=self.title.text().strip(),
            language=self._text("book.language") or "ru",
            pages=pages,
            words_per_page=words,
            genre=plain_for_book(
                self._text("book.genre"), self._text("book.language") or "ru", GENRES
            ),
            subgenre=form.subgenre.text().strip(),
            tone=plain_for_book(
                self._text("book.tone"), self._text("book.language") or "ru", TONES
            ),
            pov=self._text("book.pov") or "third-person limited",
            tense=self._text("book.tense") or "past",
            audience=self._text("book.readers") or "adult",
            setting=form.setting.text().strip(),
            characters=form._people(),
            plot_points=form._lines(form.plot_points),
            ending_type=self._text("book.ending") or "closed",
            style_references=form._lines(form.style_references),
            dark_themes=self._flag("book.dark"),
            synopsis=self.synopsis.toPlainText().strip(),
            guessed=list(form._guessed),
            chapter_count=None if chapters == 0 else chapters,
            scenes_per_chapter=scenes,
        )

    def _text(self, key: str) -> str:
        if self.book.state is None or not self.book.state.has(key):
            return ""
        value = self.book.get(key)
        return value if isinstance(value, str) else ""

    def _integer(self, key: str) -> int:
        if self.book.state is None or not self.book.state.has(key):
            return 0
        value = self.book.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            return 0
        return value

    def _flag(self, key: str) -> bool:
        if self.book.state is None or not self.book.state.has(key):
            return False
        return self.book.get(key) is True

    def _language_changed(self) -> None:
        if self.brief_form._loading:
            return
        value = str(self.language.currentData() or "ru")
        if self._text("book.language") != value:
            self.book.choose("language", value)
            self.shell.refresh()
        self.brief_form._clear_guess("language")

    def _sync_hidden(self) -> None:
        form = self.brief_form
        form._loading = True
        _set_combo(form.pov, self._text("book.pov"))
        _set_combo(form.tense, self._text("book.tense"))
        _set_combo(form.audience, self._text("book.readers"))
        _set_combo(form.ending, self._text("book.ending"))
        index = self.language.findData(self._text("book.language"))
        if index >= 0 and index != self.language.currentIndex():
            self.language.blockSignals(True)
            self.language.setCurrentIndex(index)
            self.language.blockSignals(False)
        self.dark.setChecked(self._flag("book.dark"))
        self.chapters.setValue(self._integer("book.chapters"))
        form.pages.setValue(max(1, self._integer("book.pages") or 250))
        form.words_per_page.setValue(max(100, self._integer("book.words_per_page") or 250))
        form.scenes.setValue(max(1, self._integer("book.scenes") or 2))
        form._loading = False
        form._refresh_numbers()

    def _refresh_target(self) -> None:
        pages = max(0, self._integer("book.pages"))
        words = max(0, self._integer("book.words_per_page"))
        self.brief_form.target_label.setText(str(pages * words))

    def _project_path(self) -> Path:
        text = self.project_path.text().strip()
        if text:
            return Path(text)
        env = os.environ.get("PLOTWEAVER_UI_PROJECT", "")
        if env:
            return Path(env)
        return Path.cwd() / "out" / "ui-book"

    def _export_path(self) -> Path | None:
        text = self.export_path_edit.text().strip()
        if not text:
            return None
        return Path(text)

    def _apply_paths(self, request: BookRequest) -> None:
        main = self.main_gguf.text().strip()
        least = self.least_gguf.text().strip()
        main_id = self.main_model.text().strip()
        least_id = self.least_model.text().strip()
        if main:
            request.main_gguf = main
            request.main_model_id = main_id or Path(main).stem
        elif main_id:
            request.main_model_id = main_id
        if least:
            request.least_censored_gguf = least
            request.least_censored_model_id = least_id or Path(least).stem
        elif least_id:
            request.least_censored_model_id = least_id

    def _show_plan(self) -> None:
        from plotweaver.cli import _run

        folder = self._project_path()
        folder.mkdir(parents=True, exist_ok=True)
        synopsis = folder / "synopsis.txt"
        synopsis.write_text(self.synopsis.toPlainText(), encoding="utf-8")
        args = _Plan(
            project=folder,
            synopsis=synopsis,
            brief=None,
            title=self.title.text().strip() or "Untitled",
            language=self._text("book.language") or "ru",
            genre=plain_for_book(
                self._text("book.genre"),
                self._text("book.language") or "ru",
                GENRES,
            ),
            target_words=self.target_words.value() or self._current_brief().target_words,
            chapters=self._integer("book.chapters"),
            scenes_per_chapter=max(1, self._integer("book.scenes") or 2),
            dark_themes=self._flag("book.dark"),
            tier=self._text("book.tier") or ModelTier.STANDARD.value,
            mode=self._text("book.mode") or BookMode.AUTOPILOT.value,
            reference=list(self._refs),
            mock=self._use_mock,
            yes=self.skip_approval.isChecked(),
            approve=False,
            export_dir=self._export_path(),
            main_gguf=self.main_gguf.text().strip(),
            least_censored_gguf=self.least_gguf.text().strip(),
            main_model_id=self.main_model.text().strip(),
            least_censored_model_id=self.least_model.text().strip(),
            author=self.author.text().strip(),
            fb2=self._flag("book.export.fb2"),
            docx=self._flag("book.export.docx"),
            markdown=self._flag("book.export.markdown"),
            speaker_marks=self._flag("book.export.marks"),
            sound=self._flag("book.sound"),
            json=self.json_report.isChecked(),
            dry_run=True,
        )
        text = run_captured(_run, args)
        self.plan_label.setText(text)
        self.log.setPlainText(text)
        self.shell.set_note(tr("dry_run"))

    def _run_sync(self, mock: bool, yes: bool, approve: bool, export_to: Path | None) -> None:
        from plotweaver.install import prepare_real_models
        from plotweaver.runner import run_book

        assert self._project is not None
        try:
            if not mock:
                request = self._project.request()
                prepare_real_models(request, on_progress=self._on_progress)
                self._project.save_request(request)
            result = run_book(
                self._project,
                _backend(mock),
                yes=yes,
                approve=approve,
                on_progress=self._on_progress,
                export_to=export_to or self._project.export_dir,
            )
        except PlotweaverError as exc:
            self._on_fail(str(exc))
            return
        self._on_done(result)

    def _on_progress(self, message: str) -> None:
        self.log.appendPlainText(message)
        if self.book.phase is Phase.BUSY and message.strip():
            self.book.progress(1, 1, message.strip().splitlines()[-1][:180])
            self.shell.refresh()

    def _on_done(self, result: object) -> None:
        from plotweaver.runner import RunResult

        if not isinstance(result, RunResult) or self.book.phase is not Phase.BUSY:
            return
        if result.status == "waiting":
            self._waiting = True
            label = f"{tr('waiting')}: {result.gate}"
            self.progress_label.setText(label)
            self.approve.setVisible(True)
            self.book.progress(1, 1, label)
            self.shell.refresh()
            return
        self._waiting = False
        self.approve.setVisible(False)
        lines = [tr("done")]
        if result.export_dir is not None:
            lines.append(str(result.export_dir / "book.vxbook"))
            lines.extend(
                str(path) for path in sorted(result.export_dir.rglob("*")) if path.is_file()
            )
        text = "\n".join(lines)
        if self.json_report.isChecked():
            text = json.dumps(
                {
                    "status": result.status,
                    "gate": result.gate,
                    "export_dir": None if result.export_dir is None else str(result.export_dir),
                },
                ensure_ascii=False,
                indent=2,
            )
        self.result_label.setText(text)
        self.shell.export_text = text
        self._seq += 1
        self.book.finish(f"book-{self._seq}")
        self.shell.refresh()

    def _on_fail(self, message: str) -> None:
        self._waiting = False
        self.approve.setVisible(False)
        self.progress_label.setText(message)
        if message.strip():
            self.book.block(message.strip())
            self.shell.refresh()

    def _add_sound(self) -> None:
        from plotweaver.sound import add_sound

        if self._project is None:
            return
        source = self._project.export_dir / "book.vxbook"
        dest = self._project.export_dir / "book.sound.vxbook"
        try:
            add_sound(source, dest, _backend(self._use_mock))
        except PlotweaverError as exc:
            QMessageBox.warning(self, tr("app"), str(exc))
            return
        text = f"{tr('done')}\n{source}\n{dest}"
        self.result_label.setText(text)
        self.shell.export_text = text
        document = self.shell._document
        if isinstance(document, QPlainTextEdit):
            document.setPlainText(text)

    def _draft_brief(self) -> None:
        from plotweaver.runner import draft_book_brief

        notes = self.brief_form.notes.toPlainText().strip()
        if not notes:
            QMessageBox.warning(self, tr("app"), tr("brief_need_notes"))
            return
        language = self._text("book.language") or str(self.language.currentData() or "en")
        try:
            brief = draft_book_brief(notes, language, _backend(self._use_mock))
        except PlotweaverError as exc:
            QMessageBox.warning(self, tr("app"), str(exc))
            return
        self._apply_loaded_brief(brief)

    def _apply_loaded_brief(self, brief: BookBrief) -> None:
        form = self.brief_form
        form._loading = True
        self.title.setText(brief.title)
        index = self.language.findData(brief.language)
        if index >= 0:
            self.language.setCurrentIndex(index)
        self.synopsis.setPlainText(brief.synopsis)
        self.shell.set_prompt_text(brief.synopsis)
        self.dark.setChecked(brief.dark_themes)
        self.chapters.setValue(brief.chapter_count or 0)
        self._push_brief(brief)
        form._loading = False
        form.apply(brief)
        self._refresh_target()
        self.shell.refresh()

    def _push_brief(self, brief: BookBrief) -> None:
        self._choose_known("language", brief.language)
        pov = _POV.get(brief.pov)
        if pov is not None:
            self._choose_known("pov", pov)
        tense = _TENSE.get(brief.tense)
        if tense is not None:
            self._choose_known("tense", tense)
        readers = _READERS.get(brief.audience)
        if readers is not None:
            self._choose_known("readers", readers)
        if brief.ending_type in _ENDING:
            self._choose_known("ending", brief.ending_type)
        self._choose_known("themes", "on" if brief.dark_themes else "off")
        self.book.set_value("book.genre", match_plain(brief.genre, GENRES))
        self.book.set_value("book.tone", match_plain(brief.tone, TONES))
        self.book.set_value("book.pages", min(STRUCTURAL_MAX_PAGES, max(1, brief.pages)))
        self.book.set_value("book.words_per_page", brief.words_per_page)
        self.book.set_value(
            "book.scenes",
            min(MAX_SCENES_PER_CHAPTER, max(1, brief.derived_scenes())),
        )
        self.book.set_value(
            "book.chapters",
            min(SAFETY_CHAPTER_CEILING, max(0, brief.chapter_count or 0)),
        )

    def _choose_known(self, row_id: str, option_id: str) -> None:
        try:
            self.book.choose(row_id, option_id)
        except ValueError:
            return

    def _copy_prompt(self) -> None:
        language = self._text("book.language") or "en"
        clipboard = QApplication.clipboard()
        clipboard.setText(chat_prompt(language))
        QMessageBox.information(self, tr("app"), tr("brief_copied"))

    def _paste_brief(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("brief_paste"))
        dialog.resize(720, 480)
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit()
        editor.setPlaceholderText(tr("brief_paste"))
        layout.addWidget(editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            brief = parse_brief(editor.toPlainText())
        except BriefError as exc:
            QMessageBox.warning(self, tr("app"), _brief_error_text(exc))
            return
        self._apply_loaded_brief(brief)

    def _open_synopsis(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self, tr("open_synopsis"), "", "Text (*.txt *.md)"
        )
        if not path:
            return
        self.synopsis.setPlainText(read_text(Path(path)))
        self.shell.set_prompt_text(self.synopsis.toPlainText())

    def _open_brief(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self, tr("open_brief"), "", "Brief (*.json *.md *.txt)"
        )
        if not path:
            return
        try:
            brief = parse_brief(read_text(Path(path)))
        except BriefError as exc:
            QMessageBox.warning(self, tr("app"), _brief_error_text(exc))
            return
        self._apply_loaded_brief(brief)

    def _show_guide(self) -> None:
        from plotweaver.brief import writing_guide_path

        path = writing_guide_path()
        text = read_text(path) if path.is_file() else tr("help_brief")
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("help_brief"))
        dialog.resize(720, 560)
        layout = QVBoxLayout(dialog)
        view = QPlainTextEdit(text)
        view.setReadOnly(True)
        layout.addWidget(view)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _show_about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(tr("about"))
        box.setText(tr("app"))
        box.setInformativeText(f"{self.about_text()}\n{tr('subtitle')}\n{tr('gpu_note')}")
        box.exec()

    def _show_tools(self) -> None:
        dialog = ToolsDialog(self, mock=self._use_mock)
        dialog.project.setText(str(self._project_path()))
        export_to = self._export_path()
        if export_to is not None:
            dialog.export_dir.setText(str(export_to))
        dialog.author.setText(self.author.text())
        dialog.main_gguf.setText(self.main_gguf.text())
        dialog.least_gguf.setText(self.least_gguf.text())
        dialog.main_model.setText(self.main_model.text())
        dialog.least_model.setText(self.least_model.text())
        dialog.exec()

    def _suite_selftest(self) -> None:
        from plotweaver.cli import _selftest_command

        self.plan_label.setText(run_captured(_selftest_command, self.json_report.isChecked()))

    def _new_book(self) -> None:
        self._project = None
        self._waiting = False
        self.title.clear()
        self.author.clear()
        self.synopsis.clear()
        self.shell.set_prompt_text("")
        self._refs.clear()
        self.ref_label.setText("—")
        self.book.phase = Phase.EMPTY
        self.book.selected = None
        self.shell.refresh()

    def _logo_click(self, event: object) -> None:
        del event
        if self._egg_shown:
            return
        now = time.monotonic()
        self._clicks = [stamp for stamp in self._clicks if now - stamp < 2.0]
        self._clicks.append(now)
        if len(self._clicks) >= 6:
            self._egg_shown = True
            self._egg.setText(tr("egg"))

    def _check_update(self) -> None:
        if os.environ.get("PLOTWEAVER_NO_UPDATE_CHECK") == "1":
            return
        from plotweaver.update_check import check_for_update

        newer = check_for_update()
        if newer:
            self.update_note.setText(f"{tr('gpu_note')}\n{newer}")

    def _add_ref(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self, tr("add_ref"), "", "Books (*.txt *.md *.docx *.epub)"
        )
        if path:
            self._refs.append(path)
            self.ref_label.setText(str(len(self._refs)))

    def _open_export(self) -> None:
        if self._project is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._project.export_dir)))

    def _save_as(self) -> None:
        if self._project is None:
            return
        folder = QFileDialog.getExistingDirectory(self, tr("save_as"))
        if not folder:
            return
        self._copy_project(Path(folder) / self._project.root.name)

    def _save_copy(self) -> None:
        if self._project is None:
            return
        src = self._project.root
        dest = src.with_name(f"{src.name}-copy")
        index = 2
        while dest.exists():
            dest = src.with_name(f"{src.name}-copy-{index}")
            index += 1
        self._copy_project(dest)

    def _copy_project(self, dest: Path) -> None:
        if self._project is None:
            return
        src = self._project.root.resolve()
        target = dest.resolve()
        if target == src or src in target.parents:
            QMessageBox.warning(self, tr("app"), tr("save_as"))
            return
        if target.exists():
            QMessageBox.warning(self, tr("app"), str(target))
            return
        shutil.copytree(src, target)
        text = f"{tr('done')}\n{target}"
        self.result_label.setText(text)
        self.shell.export_text = text

    def _manage_models(self) -> None:
        from plotweaver.mdl_ui import manage_models

        manage_models(self)

    def _restore_geometry(self) -> None:
        path = self._state_dir / "geometry.json"
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return
        width = data.get("width")
        height = data.get("height")
        if isinstance(width, int) and isinstance(height, int):
            self.resize(max(960, width), max(640, height))
        if data.get("maximized") is True:
            self.showMaximized()

    def _save_geometry(self) -> None:
        payload = {
            "x": self.x(),
            "y": self.y(),
            "width": self.width(),
            "height": self.height(),
            "maximized": self.isMaximized(),
            "fullscreen": self.isFullScreen(),
        }
        path = self._state_dir / "geometry.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, indent=2) + "\n"
        with exclusive_lock(path.with_name(f"{path.name}.lock")):
            write_text(path, text)


class _Plan:
    """Attribute bag for ``plotweaver.cli._run`` in dry-run mode."""

    def __init__(self, **values: object) -> None:
        self.__dict__.update(values)


def _language(value: str) -> Language:
    match value:
        case Language.RU:
            return Language.RU
        case Language.EN:
            return Language.EN
        case _:
            raise PlotweaverError("language must be en or ru")


def _mode(value: str) -> BookMode:
    match value:
        case BookMode.AUTOPILOT:
            return BookMode.AUTOPILOT
        case BookMode.COPILOT:
            return BookMode.COPILOT
        case BookMode.MANUAL:
            return BookMode.MANUAL
        case _:
            raise PlotweaverError("mode must be autopilot, copilot, or manual")


def _tier(value: str) -> ModelTier:
    match value:
        case ModelTier.STANDARD:
            return ModelTier.STANDARD
        case ModelTier.LEAST_CENSORED:
            return ModelTier.LEAST_CENSORED
        case _:
            return ModelTier.STANDARD


def _set_combo(box: QComboBox, value: str) -> None:
    index = box.findData(value)
    if index < 0:
        index = box.findText(value)
    if index >= 0:
        box.setCurrentIndex(index)


def _brief_error_text(exc: BriefError) -> str:
    return "\n".join(tr(f"brief_err_{item.code}").format(field=item.field) for item in exc.errors)
