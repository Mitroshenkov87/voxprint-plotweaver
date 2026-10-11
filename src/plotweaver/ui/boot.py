"""Open the window only after required files are ready.

A splash is shown first. Provisioning, the GPU probe, and hash checks run on
a worker. The main window is constructed when that worker reports ready.
``PLOTWEAVER_STARTUP_PROBE=1`` prints the seconds to the first window and to
the main window, then exits. Heavy modules stay out of this import.
"""

from __future__ import annotations

import os
import tempfile
import time

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog
from voxprint_common.ui.splash import Splash

from plotweaver.buildstamp import suite_build_info
from plotweaver.paths import splash_art
from plotweaver.ready import Failed, Ready
from plotweaver.startup_mark import STARTED
from plotweaver.ui.fonts import register_ui_fonts, ui_font
from plotweaver.ui.i18n import tr
from plotweaver.ui.theme import SPLASH


class _ProvisionThread(QThread):
    """Run :func:`plotweaver.ready.ensure_ready` off the UI thread."""

    progressed = Signal(str)
    finished_with = Signal(object)

    def run(self) -> None:
        # Suite repair imports llama and the registry. Keep that off this module's import.
        from plotweaver.ready import ensure_ready

        self.finished_with.emit(ensure_ready(self.progressed.emit))


class _Boot(QObject):
    """Hold the splash, the progress dialog, and the worker."""

    def __init__(self, app: QApplication, *, mock: bool, selftest: bool, started: float) -> None:
        super().__init__()
        self.app = app
        self.mock = mock
        self.selftest = selftest
        self.started = started
        self.code = 0
        self.enter_loop = True
        self.splash = Splash(splash_art(), SPLASH, suite_build_info())
        self._note_first_window()
        self.dialog = QProgressDialog(tr("repair_checking"), "", 0, 0)
        self.dialog.setCancelButton(None)
        self.dialog.setWindowTitle(tr("app"))
        self.dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.dialog.setMinimumDuration(0)
        self.dialog.setMinimumWidth(520)
        self.worker: _ProvisionThread | None = None

    def start(self) -> None:
        """Show progress, or the main window immediately for a mock launch."""
        if self.mock:
            self.dialog.close()
            self._open_main()
            return
        self.dialog.show()
        self.dialog.raise_()
        self.app.processEvents()
        self.worker = _ProvisionThread()
        self.worker.progressed.connect(self._on_progress)
        self.worker.finished_with.connect(self._finished)
        self.worker.start()

    def _on_progress(self, text: str) -> None:
        self.splash.set_stage(text)
        self.dialog.setLabelText(text)

    def _finished(self, outcome: object) -> None:
        self.dialog.close()
        if isinstance(outcome, Failed):
            self._not_ready(outcome.message)
            return
        if isinstance(outcome, Ready):
            self._open_main()
            return
        raise RuntimeError("provisioning returned an unknown result")

    def _not_ready(self, message: str) -> None:
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("manage_models"))
        box.setText(message or tr("models_not_ready"))
        manage = box.addButton(tr("manage_models"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is manage:
            # mdl_ui builds the progress dialog. Keep it off the splash import.
            from plotweaver.mdl_ui import manage_models
            from plotweaver.ready import ensure_ready

            manage_models()
            again = ensure_ready(self._on_progress)
            if isinstance(again, Ready):
                self._open_main()
                return
        self.code = 1
        self.splash.finish()
        self.app.quit()

    def _open_main(self) -> None:
        from PySide6.QtCore import QTimer

        # The window imports the book pipeline. The splash is already visible.
        from plotweaver.ui.window import MainWindow

        window = MainWindow(mock=self.mock or self.selftest)
        window.show()
        self.app.processEvents()
        self._note_main_window()
        if os.environ.get("PLOTWEAVER_STARTUP_PROBE") == "1" or self.selftest:
            self.enter_loop = False
            self.splash.finish()
            if self.selftest:
                window.run_selftest()
            self.app.quit()
            return

        def _retire() -> None:
            self.splash.finish()

        QTimer.singleShot(0, _retire)

    def _note_first_window(self) -> None:
        if os.environ.get("PLOTWEAVER_STARTUP_PROBE") != "1":
            return
        elapsed = time.perf_counter() - self.started
        print(f"first_window {elapsed:.3f}", flush=True)

    def _note_main_window(self) -> None:
        if os.environ.get("PLOTWEAVER_STARTUP_PROBE") != "1":
            return
        elapsed = time.perf_counter() - self.started
        print(f"main_window {elapsed:.3f}", flush=True)


def run_gui(*, mock: bool, selftest: bool) -> int:
    """Show a splash, provision on a worker, then open the main window."""
    if selftest:
        os.environ["PLOTWEAVER_UI_PROJECT"] = tempfile.mkdtemp(prefix="plotweaver-selftest-")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    current = QApplication.instance()
    app = current if isinstance(current, QApplication) else QApplication([])
    register_ui_fonts()
    app.setFont(ui_font(10))
    boot = _Boot(app, mock=mock, selftest=selftest, started=STARTED)
    boot.start()
    if boot.enter_loop:
        app.exec()
    return boot.code
