"""Manage models: the MDL window, or a dialog that only draws MDL events.

``voxprint-mdl --gui --app plotweaver`` opens the localized window. This dialog
runs only when that command fails, and it only paints JSON events.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence

from PySide6.QtCore import QEventLoop, QObject, QThread, Signal
from PySide6.QtWidgets import QApplication, QProgressDialog, QWidget

from plotweaver.mdl_progress import download_command, manage_command, run_download, run_mdl
from plotweaver.ui.i18n import tr


class _DownloadThread(QThread):
    """Read MDL JSON events off the UI thread."""

    progressed = Signal(object)
    finished_code = Signal(int)

    def __init__(self, command: Sequence[str]) -> None:
        super().__init__()
        self.command = list(command)
        self.process: list[subprocess.Popen[str]] = []

    def run(self) -> None:
        code = run_download(self.command, on_event=self.progressed.emit, process=self.process)
        self.finished_code.emit(code)

    def stop(self) -> None:
        """Kill the MDL process. The dialog does not download on its own."""
        for proc in self.process:
            proc.kill()


def manage_models(parent: QWidget | None = None, models: Sequence[str] = ()) -> int:
    """Open ``voxprint-mdl --gui --app plotweaver``. Fall back if that fails."""
    code = run_mdl(manage_command())
    if code in (0, 3):
        return code
    return show_progress_dialog(parent, models)


def show_progress_dialog(parent: QWidget | None = None, models: Sequence[str] = ()) -> int:
    """Show MDL progress. The dialog does not download anything itself."""
    current = QApplication.instance()
    if not isinstance(current, QApplication):
        QApplication([])
    dialog = QProgressDialog(tr("models_not_ready"), tr("back"), 0, 1000, parent)
    dialog.setWindowTitle(tr("manage_models"))
    dialog.setMinimumWidth(520)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    dialog.setValue(0)
    holder = _Holder(download_command(models), dialog)
    loop = QEventLoop(dialog)
    dialog.canceled.connect(holder.cancel)
    holder.worker.finished_code.connect(loop.quit)
    dialog.show()
    holder.start()
    loop.exec()
    dialog.close()
    return holder.code


class _Holder(QObject):
    """Keep the worker and the latest MDL fraction."""

    def __init__(self, command: list[str], dialog: QProgressDialog) -> None:
        super().__init__(dialog)
        self.code = 1
        self.dialog = dialog
        self.worker = _DownloadThread(command)
        self.worker.progressed.connect(self._on_event)
        self.worker.finished_code.connect(self._on_code)

    def start(self) -> None:
        """Start the MDL process."""
        self.worker.start()

    def cancel(self) -> None:
        """Stop the MDL process when the dialog is cancelled."""
        self.code = 3
        self.worker.stop()

    def _on_code(self, code: int) -> None:
        if self.code != 3:
            self.code = code

    def _on_event(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        message = payload.get("message")
        if isinstance(message, str) and message:
            self.dialog.setLabelText(message)
        fraction = payload.get("fraction")
        if isinstance(fraction, int | float):
            self.dialog.setValue(max(0, min(1000, int(float(fraction) * 1000))))
