"""Every plotweaver command, opened from the shell.

The book form is the ``run`` command. This dialog is the rest: doctor,
export, the Mars scenario, the bake-off, Voxprint Book checks, the model
registry, sound markup, brief draft, provision, the installer, and release.
Each flag from the command line has a control here. Dry run is on until the
user turns it off.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from plotweaver.errors import PlotweaverError
from plotweaver.ui.i18n import tr


def run_captured(func: object, args: object) -> str:
    """Run a command function and return everything it printed.

    Args:
        func: A ``plotweaver.cli`` command. It returns an exit code.
        args: The namespace that command expects.
    """
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = 1
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = int(func(args))  # type: ignore[operator]
    except PlotweaverError as exc:
        stderr.write(str(exc))
        code = 1
    except Exception as exc:  # noqa: BLE001 - the dialog shows the message
        stderr.write(str(exc))
        code = 1
    text = f"{stdout.getvalue()}{stderr.getvalue()}".strip()
    return f"{text}\nexit {code}".strip()


class ToolsDialog(QDialog):
    """One wizard for the commands that are not the book form."""

    def __init__(self, parent: QWidget | None = None, *, mock: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("tools"))
        self.resize(760, 640)
        self._mock = mock
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.tool = QComboBox()
        self._ids = (
            "version",
            "doctor",
            "export",
            "scenario-mars",
            "bakeoff",
            "vxbook",
            "models",
            "sound",
            "brief",
            "provision",
            "mdl-progress",
            "release-shared",
            "selftest",
        )
        labels = (
            tr("version_tool"),
            tr("gpu_check"),
            tr("export_tool"),
            tr("mars"),
            tr("bakeoff_tool"),
            tr("validate_book"),
            tr("list_models"),
            tr("sound_tool"),
            tr("brief_help"),
            tr("provision_tool"),
            tr("mdl_progress_tool"),
            tr("release_tool"),
            tr("suite_selftest"),
        )
        for tool_id, label in zip(self._ids, labels, strict=True):
            self.tool.addItem(label, tool_id)
        self.tool.currentIndexChanged.connect(lambda _index: self._apply_tool())
        form.addRow(tr("tools"), self.tool)
        self.project = QLineEdit("out/ui-book")
        self.export_dir = QLineEdit()
        self.file = QLineEdit()
        self.output = QLineEdit()
        self.idea = QLineEdit()
        self.author = QLineEdit()
        self.results = QLineEdit("out/bakeoff")
        self.registry = QLineEdit()
        self.main_gguf = QLineEdit()
        self.least_gguf = QLineEdit()
        self.main_model = QLineEdit()
        self.least_model = QLineEdit()
        self.language = QComboBox()
        self.language.addItem("Russian", "ru")
        self.language.addItem("English", "en")
        self.limit = QSpinBox()
        self.limit.setRange(0, 1000)
        self.dry_run = QCheckBox(tr("dry_run"))
        self.dry_run.setChecked(True)
        self.json_report = QCheckBox(tr("json_report"))
        self.yes = QCheckBox(tr("skip_approval"))
        self.sound = QCheckBox(tr("sound_markup"))
        self.mirror = QCheckBox(tr("mirror_sound"))
        self.fb2 = QCheckBox(tr("export_fb2"))
        self.docx = QCheckBox(tr("export_docx"))
        self.markdown = QCheckBox(tr("export_markdown"))
        self.marks = QCheckBox(tr("export_marks"))
        self.allow_license = QCheckBox(tr("allow_license"))
        self.quiet = QCheckBox(tr("quiet_install"))
        self.installer = QCheckBox(tr("installer_ok"))
        rows: tuple[tuple[str, QWidget], ...] = (
            (tr("choose_project"), self._browse_row(self.project, directory=True)),
            (tr("choose_export"), self._browse_row(self.export_dir, directory=True)),
            (tr("validate_book"), self._browse_row(self.file, directory=False)),
            (tr("sound_tool"), self._browse_row(self.output, directory=False)),
            (tr("brief_notes"), self.idea),
            (tr("author"), self.author),
            (tr("language"), self.language),
            (tr("results_folder"), self._browse_row(self.results, directory=True)),
            (tr("registry_file"), self._browse_row(self.registry, directory=False)),
            (tr("main_gguf"), self._browse_row(self.main_gguf, directory=False)),
            (tr("least_gguf"), self._browse_row(self.least_gguf, directory=False)),
            (tr("main_model"), self.main_model),
            (tr("least_model"), self.least_model),
            (tr("bakeoff_limit"), self.limit),
            ("", self.dry_run),
            ("", self.json_report),
            ("", self.yes),
            ("", self.sound),
            ("", self.mirror),
            ("", self.fb2),
            ("", self.docx),
            ("", self.markdown),
            ("", self.marks),
            ("", self.allow_license),
            ("", self.quiet),
            ("", self.installer),
        )
        for label, widget in rows:
            form.addRow(label, widget)
        root.addLayout(form)
        self.output_view = QPlainTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.setObjectName("toolOutput")
        root.addWidget(self.output_view, 1)
        buttons = QDialogButtonBox()
        run = buttons.addButton(tr("run_tool"), QDialogButtonBox.ButtonRole.AcceptRole)
        if isinstance(run, QPushButton):
            run.clicked.connect(self._run)
        close = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        if isinstance(close, QPushButton):
            close.clicked.connect(self.reject)
        root.addWidget(buttons)
        self._apply_tool()

    def _browse_row(self, edit: QLineEdit, *, directory: bool) -> QWidget:
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

    def _apply_tool(self) -> None:
        tool_id = str(self.tool.currentData() or "")
        heavy = tool_id in {"scenario-mars", "bakeoff", "export", "sound", "provision"}
        self.dry_run.setEnabled(
            tool_id not in {"version", "provision", "mdl-progress", "release-shared"}
        )
        if heavy:
            self.dry_run.setChecked(True)

    def _run(self) -> None:
        from plotweaver import cli

        tool_id = str(self.tool.currentData() or "")
        if tool_id == "release-shared" and not self._confirm(tr("confirm_release")):
            return
        if tool_id == "provision" and not self._confirm(tr("confirm_provision")):
            return
        if tool_id == "selftest":
            self.output_view.setPlainText(
                run_captured(cli._selftest_command, self.json_report.isChecked())
            )
            return
        args = self._namespace()
        command = {
            "version": cli._version,
            "doctor": cli._doctor,
            "export": cli._export,
            "scenario-mars": cli._scenario_mars,
            "bakeoff": cli._bakeoff,
            "vxbook": cli._vxbook_validate,
            "models": cli._models_list,
            "sound": cli._sound_add,
            "brief": cli._brief_draft,
            "provision": cli._provision,
            "mdl-progress": cli._mdl_progress,
            "release-shared": cli._release,
        }.get(tool_id)
        if command is None:
            return
        self.output_view.setPlainText(run_captured(command, args))

    def _confirm(self, text: str) -> bool:
        answer = QMessageBox.question(self, tr("tools"), text)
        return answer == QMessageBox.StandardButton.Yes

    def _namespace(self) -> object:
        file_text = self.file.text().strip()
        registry = self.registry.text().strip()
        export_text = self.export_dir.text().strip()
        return _Args(
            project=Path(self.project.text().strip() or "out/ui-book"),
            export_dir=Path(export_text) if export_text else None,
            file=Path(file_text or "."),
            src=Path(file_text or "."),
            output=Path(self.output.text().strip() or "out/book.sound.vxbook"),
            idea=self.idea.text(),
            author=self.author.text(),
            language=str(self.language.currentData() or "ru"),
            results=Path(self.results.text().strip() or "out/bakeoff"),
            registry=Path(registry) if registry else None,
            main_gguf=self.main_gguf.text().strip(),
            least_censored_gguf=self.least_gguf.text().strip(),
            main_model_id=self.main_model.text().strip(),
            least_censored_model_id=self.least_model.text().strip(),
            mock=self._mock,
            dry_run=self.dry_run.isChecked(),
            json=self.json_report.isChecked(),
            yes=self.yes.isChecked(),
            sound=self.sound.isChecked(),
            mirror=self.mirror.isChecked(),
            fb2=self.fb2.isChecked(),
            docx=self.docx.isChecked(),
            markdown=self.markdown.isChecked(),
            speaker_marks=self.marks.isChecked(),
            allow_other_license=self.allow_license.isChecked(),
            quiet=self.quiet.isChecked(),
            installer=self.installer.isChecked(),
            limit=self.limit.value(),
            command=str(self.tool.currentData() or ""),
        )


class _Args:
    """The attribute set the command functions read. One object covers every flag."""

    def __init__(self, **values: object) -> None:
        self.__dict__.update(values)
