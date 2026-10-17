"""Offscreen 1200 by 900 grabs of the book shell.

These are the pictures Aleksandr reviews before a merge. They are not a
substitute for the VM shots, which keep their own file names.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication
from voxprint_common.i18n import set_language
from voxprint_common.ui.simple_image import Phase

from plotweaver.ui.fonts import register_ui_fonts, ui_font
from plotweaver.ui.i18n import tr
from plotweaver.ui.window import MainWindow

_WIDTH = 1200
_HEIGHT = 900


def save_shell_shots(folder: Path) -> list[Path]:
    """Write the simple, expert, changed, progress, and approval grabs.

    Args:
        folder: Destination directory. It is created when missing.
    """
    folder.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("PLOTWEAVER_NO_UPDATE_CHECK", "1")
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    register_ui_fonts()
    app.setFont(ui_font(10))
    shots = [
        _grab("en", expert=False, name="en-simple.png", folder=folder),
        _grab("ru", expert=False, name="ru-simple.png", folder=folder),
        _grab("en", expert=True, name="en-expert.png", folder=folder),
        _grab("ru", expert=True, name="ru-expert.png", folder=folder),
        _grab("en", expert=False, name="en-modified.png", folder=folder, modified=True),
        _progress(folder / "en-progress.png"),
        _approve(folder / "en-approve.png"),
    ]
    return shots


def _grab(
    language: str,
    *,
    expert: bool,
    name: str,
    folder: Path,
    modified: bool = False,
) -> Path:
    os.environ["PLOTWEAVER_LANG"] = language
    set_language(language)
    window = MainWindow(mock=True)
    window.resize(_WIDTH, _HEIGHT)
    window.show()
    window.title.setText("The lock")
    window.author.setText("Ilya")
    window.synopsis.setPlainText("A night ferry sticks. The keeper stays.")
    window.shell.set_prompt_text(window.synopsis.toPlainText())
    if modified:
        window.book.set_value("book.pages", 200)
    if expert:
        window._open_settings()
    window.shell.refresh()
    _pump()
    return _save(window, folder / name)


def _progress(path: Path) -> Path:
    os.environ["PLOTWEAVER_LANG"] = "en"
    set_language("en")
    window = MainWindow(mock=True)
    window.resize(_WIDTH, _HEIGHT)
    window.show()
    window.synopsis.setPlainText("A night ferry sticks. The keeper stays.")
    window.shell.set_prompt_text(window.synopsis.toPlainText())
    window.book.generate()
    window.book.progress(1, 1, tr("progress"))
    window.log.setPlainText("story bible\noutline")
    window.shell.refresh()
    _pump()
    return _save(window, path)


def _approve(path: Path) -> Path:
    os.environ["PLOTWEAVER_LANG"] = "en"
    set_language("en")
    os.environ["PLOTWEAVER_UI_PROJECT"] = str(Path(tempfile.mkdtemp()) / "approve-project")
    window = MainWindow(mock=True)
    window.resize(_WIDTH, _HEIGHT)
    window.show()
    window.title.setText("Approval")
    window.synopsis.setPlainText("A short ferry story for the approval grab.")
    window.book.set_value("book.pages", 4)
    window.book.set_value("book.words_per_page", 200)
    window.book.set_value("book.chapters", 1)
    window.skip_approval.setChecked(False)
    window.dry_run.setChecked(False)
    window.start(synchronous=True)
    if window.book.phase is not Phase.BUSY or not window.approve.isVisible():
        raise RuntimeError("approval grab did not reach a gate")
    _pump()
    return _save(window, path)


def _pump() -> None:
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


def _save(window: MainWindow, path: Path) -> Path:
    window.resize(_WIDTH, _HEIGHT)
    window.show()
    _pump()
    image = QImage(window.size(), QImage.Format.Format_ARGB32)
    image.fill(0xFF1A1A1A)
    painter = QPainter(image)
    window.render(painter, QPoint())
    painter.end()
    if image.width() != _WIDTH or image.height() != _HEIGHT:
        raise RuntimeError(f"{path.name} is {image.width()}x{image.height()}")
    if not image.save(str(path), "PNG"):  # type: ignore[call-overload]
        raise RuntimeError(f"could not save {path}")
    return path
