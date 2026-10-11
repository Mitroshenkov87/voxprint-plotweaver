"""New book, progress, and result. The pipeline runs on the UI thread in the self-test
and on a worker thread for a normal click, so the window can repaint.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import assert_never

from PySide6.QtCore import QSize, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QStandardItemModel
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
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from plotweaver.appinfo import version_label
from plotweaver.brief import (
    BookBrief,
    BriefError,
    chat_prompt,
    parse_brief,
    writing_guide_path,
)
from plotweaver.domain import BookMode, BookRequest, Language, ModelTier
from plotweaver.errors import PlotweaverError
from plotweaver.hardware import query_gpu, require_supported_gpu
from plotweaver.install import ensure_uncensored_models, prepare_real_models
from plotweaver.llama_release import ensure_llama_server
from plotweaver.llama_server import LlamaServer
from plotweaver.llm import LLMBackend
from plotweaver.optional_mock import mock_backend
from plotweaver.registry import (
    TierName,
    detected_tier,
    resolve_tier,
    tier_option_enabled,
    uncensored_offer_allowed,
)
from plotweaver.runner import RunResult, draft_book_brief, run_book
from plotweaver.settings import (
    model_tier_override,
    save_model_tier_override,
    save_uncensored_models,
    uncensored_models_preference,
)
from plotweaver.sound import add_sound
from plotweaver.store import Project
from plotweaver.ui.brief_form import BriefForm
from plotweaver.ui.i18n import tr
from plotweaver.ui.icons import suite_icon
from plotweaver.ui.theme import TEXT, TEXT_ON_PRIMARY, build_style, enable_acrylic
from plotweaver.update_check import check_for_update

HOME, FORM, PROGRESS, RESULT, SETTINGS = 0, 1, 2, 3, 4


class _DownloadThread(QThread):
    progressed = Signal(str)
    finished_ok = Signal(int)
    failed = Signal(str)

    def __init__(self, total_vram_gb: float, free_gb: float) -> None:
        super().__init__()
        self.total_vram_gb = total_vram_gb
        self.free_gb = free_gb

    def run(self) -> None:
        try:
            count = ensure_uncensored_models(
                total_vram_gb=self.total_vram_gb,
                free_gb=self.free_gb,
                on_progress=self.progressed.emit,
            )
        except Exception as exc:  # noqa: BLE001 - show the message, keep the window
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(count)


class _RunThread(QThread):
    progressed = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, project: Project, request_mock: bool, yes: bool, approve: bool) -> None:
        super().__init__()
        self.project = project
        self.request_mock = request_mock
        self.yes = yes
        self.approve = approve

    def run(self) -> None:
        try:
            if not self.request_mock:
                request = self.project.request()
                prepare_real_models(request, on_progress=self.progressed.emit)
                self.project.save_request(request)
            backend = _backend(self.request_mock)
            result = run_book(
                self.project,
                backend,
                yes=self.yes,
                approve=self.approve,
                on_progress=self.progressed.emit,
                export_to=self.project.root / "export",
            )
        except Exception as exc:  # noqa: BLE001 - show the message, keep the window
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(result)


def _backend(mock: bool) -> LLMBackend:
    if mock:
        return mock_backend()
    require_supported_gpu()
    return LlamaServer(ensure_llama_server())


class MainWindow(QMainWindow):
    """The desktop window: new book, progress, and result."""

    def __init__(self, mock: bool = False) -> None:
        super().__init__()
        self.mock_default = mock
        self.setWindowTitle(tr("app"))
        self.resize(960, 680)
        self._clicks: list[float] = []
        self._egg_shown = False
        self._thread: _RunThread | None = None
        self._download: _DownloadThread | None = None
        self._project: Project | None = None
        self._refs: list[str] = []
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.stack.addWidget(self._home())
        self.stack.addWidget(self._form())
        self.stack.addWidget(self._progress())
        self.stack.addWidget(self._result())
        self.stack.addWidget(self._settings())
        help_menu = self.menuBar().addMenu(tr("help"))
        help_menu.addAction(tr("help_brief")).triggered.connect(self._show_guide)
        self.setStyleSheet(build_style(glass=False))

    def showEvent(self, event: object) -> None:
        super().showEvent(event)  # type: ignore[arg-type]
        if enable_acrylic(int(self.winId())):
            self.setStyleSheet(build_style(glass=True))

    def _card(self) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        return frame, layout

    def _home(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        card, layout = self._card()
        title = QLabel(tr("app"))
        title.setObjectName("title")
        title.mousePressEvent = self._logo_click  # type: ignore[method-assign]
        layout.addWidget(title)
        version = QLabel(version_label())
        version.setObjectName("faint")
        layout.addWidget(version)
        muted = QLabel(tr("subtitle"))
        muted.setObjectName("muted")
        layout.addWidget(muted)
        note = QLabel(tr("gpu_note"))
        note.setObjectName("faint")
        note.setWordWrap(True)
        newer = check_for_update()
        if newer:
            note.setText(f"{tr('gpu_note')}\n{newer}")
        layout.addWidget(note)
        button = QPushButton(tr("new"))
        button.setObjectName("primary")
        button.clicked.connect(lambda: self.stack.setCurrentIndex(FORM))
        layout.addWidget(button)
        settings = QPushButton(tr("settings"))
        settings.clicked.connect(self._open_settings)
        layout.addWidget(settings)
        about = QPushButton(tr("about"))
        about.clicked.connect(self._show_about)
        layout.addWidget(about)
        outer.addWidget(card)
        self._egg = QLabel("")
        self._egg.setObjectName("muted")
        outer.addWidget(self._egg)
        return page

    def about_text(self) -> str:
        return version_label()

    def _show_about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(tr("about"))
        box.setText(tr("app"))
        box.setInformativeText(self.about_text())
        box.exec()

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

    def _form(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        card, layout = self._card()
        form = QFormLayout()
        self.title = QLineEdit()
        self.author = QLineEdit()
        self.language = QComboBox()
        self.language.addItem("Russian", Language.RU.value)
        self.language.addItem("English", Language.EN.value)
        self.synopsis = QPlainTextEdit()
        self.synopsis.setMinimumHeight(100)
        self.brief_form = BriefForm(page)
        self.tier = QComboBox()
        self.tier.addItem(tr("tier_standard"), ModelTier.STANDARD.value)
        self.tier.addItem(tr("tier_least_censored"), ModelTier.LEAST_CENSORED.value)
        self.mode = QComboBox()
        for mode in (BookMode.AUTOPILOT, BookMode.COPILOT, BookMode.MANUAL):
            self.mode.addItem(mode.value, mode.value)
        self.chapters = QSpinBox()
        self.chapters.setRange(0, 40)
        self.chapters.setValue(0)
        self.export_epub = QCheckBox(tr("export_epub"))
        self.export_epub.setChecked(True)
        self.export_epub.setEnabled(False)
        self.export_fb2 = QCheckBox(tr("export_fb2"))
        self.export_docx = QCheckBox(tr("export_docx"))
        self.export_md = QCheckBox(tr("export_markdown"))
        self.export_marks = QCheckBox(tr("export_marks"))
        self.sound_markup = QCheckBox(tr("sound_markup"))
        formats = QHBoxLayout()
        formats.addWidget(self.export_epub)
        formats.addWidget(self.export_fb2)
        formats.addWidget(self.export_docx)
        formats.addWidget(self.export_md)
        formats.addWidget(self.export_marks)
        self.dark = QCheckBox(tr("dark"))
        self.mock = QCheckBox(tr("mock"))
        self.mock.setChecked(self.mock_default)
        self.confirm = QCheckBox("Stop for bible and outline approval")
        refs = QHBoxLayout()
        self.ref_label = QLabel("—")
        self.ref_label.setObjectName("muted")
        add = QPushButton(tr("add_ref"))
        add.clicked.connect(self._add_ref)
        refs.addWidget(self.ref_label)
        refs.addWidget(add)
        form.addRow(tr("title"), self.title)
        form.addRow(tr("author"), self.author)
        form.addRow(tr("language"), self.language)
        form.addRow(tr("synopsis"), self.synopsis)
        self.brief_form.populate(form)
        self.brief_form.bind(self.title, self.language, self.synopsis, self.dark, self.chapters)
        self.brief_form.help_button.clicked.connect(self._draft_brief)
        self.brief_form.copy_button.clicked.connect(self._copy_prompt)
        self.brief_form.paste_button.clicked.connect(self._paste_brief)
        form.addRow(tr("chapters"), self.chapters)
        form.addRow(tr("tier"), self.tier)
        form.addRow(tr("mode"), self.mode)
        form.addRow(tr("formats"), formats)
        form.addRow("", self.sound_markup)
        form.addRow("", self.dark)
        form.addRow("", self.mock)
        form.addRow("", self.confirm)
        form.addRow(tr("references"), refs)
        layout.addLayout(form)
        start = QPushButton(tr("start"))
        start.setObjectName("primary")
        start.clicked.connect(lambda: self.start(synchronous=False))
        layout.addWidget(start)
        outer.addWidget(card)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        return scroll

    def _settings(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        card, layout = self._card()
        title = QLabel(tr("settings"))
        title.setObjectName("title")
        layout.addWidget(title)
        self.vram_note = QLabel(tr("settings_vram_note").format(detected="—", chosen="—"))
        self.vram_note.setObjectName("muted")
        self.vram_note.setWordWrap(True)
        layout.addWidget(self.vram_note)
        self.vram_tier = QComboBox()
        self.vram_tier.addItem(tr("settings_vram_auto"), "auto")
        self.vram_tier.addItem(tr("settings_vram_16"), "16gb")
        self.vram_tier.addItem(tr("settings_vram_24"), "24gb")
        layout.addWidget(self.vram_tier)
        self.settings_note = QLabel(tr("settings_uncensored_note"))
        self.settings_note.setObjectName("muted")
        self.settings_note.setWordWrap(True)
        layout.addWidget(self.settings_note)
        self.uncensored_models = QCheckBox(tr("settings_uncensored"))
        self.uncensored_models.toggled.connect(self._uncensored_toggled)
        layout.addWidget(self.uncensored_models)
        self.settings_status = QLabel("")
        self.settings_status.setObjectName("faint")
        self.settings_status.setWordWrap(True)
        layout.addWidget(self.settings_status)
        save = self._icon_button(tr("settings_save"), "save", primary=True)
        save.clicked.connect(self._save_settings)
        layout.addWidget(save)
        self.download_uncensored = self._icon_button(tr("settings_download"), "download")
        self.download_uncensored.clicked.connect(self._download_uncensored)
        layout.addWidget(self.download_uncensored)
        back = QPushButton(tr("back"))
        back.clicked.connect(lambda: self.stack.setCurrentIndex(HOME))
        layout.addWidget(back)
        outer.addWidget(card)
        return page

    def _gpu_total(self) -> float | None:
        gpu = query_gpu()
        if gpu is None:
            return None
        return gpu.total_gb

    def _gpu_free(self) -> float | None:
        gpu = query_gpu()
        if gpu is None:
            return None
        return gpu.free_gb

    def _tier_label(self, tier: TierName) -> str:
        match tier:
            case "16gb":
                return tr("settings_vram_16")
            case "24gb":
                return tr("settings_vram_24")
            case _ as unreachable:
                assert_never(unreachable)

    def _can_use_24(self) -> bool:
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
        total = self._gpu_total()
        free = self._gpu_free()
        can_24 = self._can_use_24()
        self._set_tier_item_enabled(2, can_24)
        saved = model_tier_override()
        if saved == "24gb" and not can_24:
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

    def _selected_override(self) -> str:
        value = self.vram_tier.currentData()
        if value == "auto":
            return "auto"
        if value == "16gb":
            return "16gb"
        if value == "24gb":
            return "24gb"
        return "auto"

    def _open_settings(self) -> None:
        self._refresh_vram_tier()
        allowed = uncensored_offer_allowed(self._gpu_total(), self._gpu_free())
        self.uncensored_models.setEnabled(allowed)
        self.uncensored_models.setChecked(uncensored_models_preference() if allowed else False)
        self.download_uncensored.setEnabled(allowed and self.uncensored_models.isChecked())
        self.settings_note.setText(
            tr("settings_uncensored_note") if allowed else tr("settings_uncensored_blocked")
        )
        self.settings_status.setText("")
        self.stack.setCurrentIndex(SETTINGS)

    def _uncensored_toggled(self, checked: bool) -> None:
        allowed = uncensored_offer_allowed(self._gpu_total(), self._gpu_free())
        self.download_uncensored.setEnabled(allowed and checked)

    def _save_settings(self) -> None:
        choice = self._selected_override()
        if choice == "24gb" and not self._can_use_24():
            choice = "auto"
        save_model_tier_override(choice)
        self._refresh_vram_tier()
        allowed = uncensored_offer_allowed(self._gpu_total(), self._gpu_free())
        enabled = bool(self.uncensored_models.isChecked()) and allowed
        save_uncensored_models(enabled)
        if not allowed:
            self.uncensored_models.setChecked(False)
            self.settings_status.setText(tr("settings_uncensored_blocked"))
            return
        self.settings_status.setText(tr("settings_saved"))

    def _download_uncensored(self) -> None:
        total = self._gpu_total()
        if not uncensored_offer_allowed(total, self._gpu_free()):
            self.settings_status.setText(tr("settings_uncensored_blocked"))
            return
        save_uncensored_models(True)
        self.settings_status.setText(tr("settings_downloading"))
        self.download_uncensored.setEnabled(False)
        assert total is not None
        free = self._gpu_free()
        self._download = _DownloadThread(total, total if free is None else free)
        self._download.progressed.connect(self.settings_status.setText)
        self._download.finished_ok.connect(self._download_done)
        self._download.failed.connect(self._download_failed)
        self._download.start()

    def _download_done(self, count: int) -> None:
        self.settings_status.setText(f"{tr('settings_saved')} {count}")
        self.download_uncensored.setEnabled(True)

    def _download_failed(self, message: str) -> None:
        self.settings_status.setText(message)
        self.download_uncensored.setEnabled(
            uncensored_offer_allowed(self._gpu_total(), self._gpu_free())
        )

    def _add_ref(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self, tr("add_ref"), "", "Books (*.txt *.md *.docx *.epub)"
        )
        if path:
            self._refs.append(path)
            self.ref_label.setText(str(len(self._refs)))

    def _progress(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        card, layout = self._card()
        self.progress_label = QLabel(tr("progress"))
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.approve = QPushButton(tr("approve"))
        self.approve.setObjectName("primary")
        self.approve.setVisible(False)
        self.approve.clicked.connect(lambda: self.start(synchronous=False, approve=True))
        layout.addWidget(self.progress_label)
        layout.addWidget(self.bar)
        layout.addWidget(self.log)
        layout.addWidget(self.approve)
        outer.addWidget(card)
        return page

    def _result(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        card, layout = self._card()
        self.result_label = QLabel(tr("done"))
        self.result_label.setWordWrap(True)
        open_button = self._icon_button(tr("result"), "export", primary=True)
        open_button.clicked.connect(self._open_export)
        save_as = self._icon_button(tr("save_as"), "save-as")
        save_as.clicked.connect(self._save_as)
        save_copy = self._icon_button(tr("save_copy"), "save-copy")
        save_copy.clicked.connect(self._save_copy)
        self.sound_button = QPushButton(tr("sound_markup"))
        self.sound_button.clicked.connect(self._add_sound)
        layout.addWidget(self.result_label)
        layout.addWidget(open_button)
        layout.addWidget(save_as)
        layout.addWidget(save_copy)
        layout.addWidget(self.sound_button)
        outer.addWidget(card)
        return page

    def _icon_button(self, text: str, icon: str, *, primary: bool = False) -> QPushButton:
        button = QPushButton(text)
        color = TEXT_ON_PRIMARY if primary else TEXT
        button.setIcon(suite_icon(icon, color))
        button.setIconSize(QSize(22, 22))
        if primary:
            button.setObjectName("primary")
        return button

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
        dest = Path(folder) / self._project.root.name
        self._copy_project(dest)

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
        self.result_label.setText(f"{tr('done')}\n{target}")

    def _draft_brief(self) -> None:
        notes = self.brief_form.notes.toPlainText().strip()
        if not notes:
            QMessageBox.warning(self, tr("app"), tr("brief_need_notes"))
            return
        language = str(self.language.currentData() or "en")
        try:
            brief = draft_book_brief(notes, language, _backend(self.mock.isChecked()))
        except PlotweaverError as exc:
            QMessageBox.warning(self, tr("app"), str(exc))
            return
        self._apply_loaded_brief(brief)

    def _apply_loaded_brief(self, brief: BookBrief) -> None:
        self.brief_form._loading = True
        self.title.setText(brief.title)
        index = self.language.findData(brief.language)
        if index >= 0:
            self.language.setCurrentIndex(index)
        self.synopsis.setPlainText(brief.synopsis)
        self.dark.setChecked(brief.dark_themes)
        self.chapters.setValue(brief.chapter_count or 0)
        self.brief_form._loading = False
        self.brief_form.apply(brief)

    def _copy_prompt(self) -> None:
        language = str(self.language.currentData() or "en")
        QApplication.clipboard().setText(chat_prompt(language))
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

    def _show_guide(self) -> None:
        path = writing_guide_path()
        text = path.read_text(encoding="utf-8") if path.is_file() else tr("help_brief")
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

    def request_from_form(self) -> BookRequest:
        brief = self.brief_form.read_lenient()
        formats = ["epub"]
        if self.export_fb2.isChecked():
            formats.append("fb2")
        if self.export_docx.isChecked():
            formats.append("docx")
        if self.export_md.isChecked():
            formats.append("markdown")
        if self.export_marks.isChecked():
            formats.append("speaker-marks")
        return BookRequest(
            title=brief.title or "Untitled",
            author=self.author.text().strip(),
            language=Language(brief.language),
            synopsis=brief.synopsis,
            genre=brief.genre,
            target_words=brief.target_words,
            chapter_count=brief.chapter_count,
            scenes_per_chapter=brief.derived_scenes(),
            pov=brief.pov,
            tense=brief.tense,
            dark_themes=brief.dark_themes,
            tier=ModelTier(str(self.tier.currentData())),
            mode=BookMode(str(self.mode.currentData())),
            reference_paths=list(self._refs),
            export_formats=formats,
            sound_markup=self.sound_markup.isChecked(),
            brief=brief.to_dict(),
            prompt_override=self.brief_form.override_text(),
        )

    def start(self, *, synchronous: bool, approve: bool = False) -> None:
        request = self.request_from_form()
        if not request.synopsis:
            QMessageBox.warning(self, tr("app"), tr("synopsis"))
            return
        root = (
            Path(os.environ.get("PLOTWEAVER_UI_PROJECT", ""))
            if os.environ.get("PLOTWEAVER_UI_PROJECT")
            else None
        )
        if self._project is None:
            folder = root or Path.cwd() / "out" / "ui-book"
            self._project = Project.open_or_create(folder, request)
        self._project.save_request(request)
        self.stack.setCurrentIndex(PROGRESS)
        self.approve.setVisible(False)
        mock = self.mock.isChecked()
        yes = not self.confirm.isChecked()
        if synchronous:
            self._run_sync(mock, yes, approve)
            return
        self._thread = _RunThread(self._project, mock, yes, approve)
        self._thread.progressed.connect(self._on_progress)
        self._thread.finished_ok.connect(self._on_done)
        self._thread.failed.connect(self._on_fail)
        self._thread.start()

    def _run_sync(self, mock: bool, yes: bool, approve: bool) -> None:
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
                export_to=self._project.export_dir,
            )
        except PlotweaverError as exc:
            self._on_fail(str(exc))
            return
        self._on_done(result)

    def _on_progress(self, message: str) -> None:
        self.log.appendPlainText(message)

    def _on_done(self, result: object) -> None:
        if not isinstance(result, RunResult):
            return
        if result.status == "waiting":
            self.progress_label.setText(f"{tr('waiting')}: {result.gate}")
            self.bar.setRange(0, 1)
            self.approve.setVisible(True)
            return
        marks = ""
        if result.export_dir is not None:
            path = result.export_dir / "book.vxbook"
            marks = str(path)
        self.result_label.setText(f"{tr('done')}\n{marks}")
        self.stack.setCurrentIndex(RESULT)

    def _add_sound(self) -> None:
        if self._project is None:
            return
        source = self._project.export_dir / "book.vxbook"
        dest = self._project.export_dir / "book.sound.vxbook"
        try:
            add_sound(source, dest, _backend(self.mock.isChecked()))
        except PlotweaverError as exc:
            QMessageBox.warning(self, tr("app"), str(exc))
            return
        self.result_label.setText(f"{tr('done')}\n{source}\n{dest}")

    def _on_fail(self, message: str) -> None:
        self.progress_label.setText(message)
        self.bar.setRange(0, 1)

    def run_selftest(self) -> None:
        """Fill the form and write a one-chapter book with the mock backend."""
        self.stack.setCurrentIndex(FORM)
        self.title.setText("Self-test")
        self.author.setText("Илья Воронов")
        self.export_fb2.setChecked(True)
        self.language.setCurrentIndex(0)
        self.synopsis.setPlainText(
            "Короткий синопсис для проверки окна. Ещё одна фраза про корабль и пыль."
        )
        self.brief_form.pages.setValue(4)
        self.brief_form.words_per_page.setValue(200)
        self.chapters.setValue(1)
        self.dark.setChecked(False)
        self.mock.setChecked(True)
        self.confirm.setChecked(False)
        self.start(synchronous=True)
        if self.stack.currentIndex() != RESULT:
            raise RuntimeError("self-test did not reach the result screen")
        if "book.vxbook" not in self.result_label.text():
            raise RuntimeError("self-test result has no book.vxbook path")
        self.sound_button.click()
        if self._project is None or not (self._project.export_dir / "book.sound.vxbook").is_file():
            raise RuntimeError("self-test did not write book.sound.vxbook")


def _brief_error_text(exc: BriefError) -> str:
    return "\n".join(tr(f"brief_err_{item.code}").format(field=item.field) for item in exc.errors)
