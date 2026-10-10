"""New book, progress, and result. The pipeline runs on the UI thread in the self-test
and on a worker thread for a normal click, so the window can repaint.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from plotweaver.domain import BookMode, BookRequest, Language, ModelTier
from plotweaver.errors import PlotweaverError
from plotweaver.hardware import require_supported_gpu
from plotweaver.llama_release import ensure_llama_server
from plotweaver.llama_server import LlamaServer
from plotweaver.llm import LLMBackend, MockBackend
from plotweaver.runner import RunResult, run_book
from plotweaver.sound import add_sound
from plotweaver.store import Project
from plotweaver.ui.i18n import tr
from plotweaver.ui.theme import build_style, enable_acrylic
from plotweaver.update_check import check_for_update

HOME, FORM, PROGRESS, RESULT = 0, 1, 2, 3


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
        return MockBackend()
    require_supported_gpu()
    return LlamaServer(ensure_llama_server())


class MainWindow(QMainWindow):
    def __init__(self, mock: bool = False) -> None:
        super().__init__()
        self.mock_default = mock
        self.setWindowTitle(tr("app"))
        self.resize(960, 680)
        self._clicks: list[float] = []
        self._egg_shown = False
        self._thread: _RunThread | None = None
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
        outer.addWidget(card)
        self._egg = QLabel("")
        self._egg.setObjectName("muted")
        outer.addWidget(self._egg)
        return page

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
        self.synopsis.setMinimumHeight(160)
        self.tier = QComboBox()
        self.tier.addItem(tr("tier_standard"), ModelTier.STANDARD.value)
        self.tier.addItem(tr("tier_least_censored"), ModelTier.LEAST_CENSORED.value)
        self.mode = QComboBox()
        for mode in (BookMode.AUTOPILOT, BookMode.COPILOT, BookMode.MANUAL):
            self.mode.addItem(mode.value, mode.value)
        self.words = QSpinBox()
        self.words.setRange(500, 200_000)
        self.words.setValue(80_000)
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
        form.addRow(tr("tier"), self.tier)
        form.addRow(tr("mode"), self.mode)
        form.addRow(tr("words"), self.words)
        form.addRow(tr("chapters"), self.chapters)
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
        return page

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
        open_button = QPushButton(tr("result"))
        open_button.setObjectName("primary")
        open_button.clicked.connect(self._open_export)
        self.sound_button = QPushButton(tr("sound_markup"))
        self.sound_button.clicked.connect(self._add_sound)
        layout.addWidget(self.result_label)
        layout.addWidget(open_button)
        layout.addWidget(self.sound_button)
        outer.addWidget(card)
        return page

    def _open_export(self) -> None:
        if self._project is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._project.export_dir)))

    def request_from_form(self) -> BookRequest:
        chapters = self.chapters.value()
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
            title=self.title.text().strip() or "Untitled",
            author=self.author.text().strip(),
            language=Language(str(self.language.currentData())),
            synopsis=self.synopsis.toPlainText().strip(),
            target_words=self.words.value(),
            chapter_count=None if chapters == 0 else chapters,
            dark_themes=self.dark.isChecked(),
            tier=ModelTier(str(self.tier.currentData())),
            mode=BookMode(str(self.mode.currentData())),
            reference_paths=list(self._refs),
            export_formats=formats,
            sound_markup=self.sound_markup.isChecked(),
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
        self.words.setValue(800)
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
