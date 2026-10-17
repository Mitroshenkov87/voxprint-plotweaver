"""Offscreen renders of the four screens the VM test records."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication
from voxprint_common.ui.simple_image import Phase

from plotweaver.hardware import query_gpu
from plotweaver.ui.fonts import register_ui_fonts, ui_font
from plotweaver.ui.window import MainWindow

_FAKE_4090 = "NVIDIA GeForce RTX 4090,8.9,24576,22000"
_EXPORT_NAMES = ("book.epub", "book.fb2", "book.vxbook", "book.sound.vxbook")


def save_vm_shots(folder: Path, *, export_dir: Path | None = None) -> list[Path]:
    """Write brief, progress, result, and Settings screenshots into folder."""
    folder.mkdir(parents=True, exist_ok=True)
    previous_gpu = os.environ.get("PLOTWEAVER_FAKE_GPU")
    previous_project = os.environ.get("PLOTWEAVER_UI_PROJECT")
    forced_gpu = False
    if query_gpu() is None:
        os.environ["PLOTWEAVER_FAKE_GPU"] = _FAKE_4090
        forced_gpu = True
    os.environ["PLOTWEAVER_UI_PROJECT"] = str(folder / "shot-project")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            app = QApplication([])
        register_ui_fonts()
        app.setFont(ui_font(10))
        window = MainWindow(mock=True)
        window.resize(900, 1500)
        window.show()
        app.processEvents()
        brief = _shot_brief(window, folder / "brief-form.png")
        progress = _shot_progress(window, folder / "progress.png")
        settings = _shot_settings(window, folder / "settings-tier.png")
        result = _shot_result(window, folder / "result.png", export_dir)
        return [brief, progress, result, settings]
    finally:
        if forced_gpu:
            if previous_gpu is None:
                os.environ.pop("PLOTWEAVER_FAKE_GPU", None)
            else:
                os.environ["PLOTWEAVER_FAKE_GPU"] = previous_gpu
        if previous_project is None:
            os.environ.pop("PLOTWEAVER_UI_PROJECT", None)
        else:
            os.environ["PLOTWEAVER_UI_PROJECT"] = previous_project


def _shot_brief(window: MainWindow, path: Path) -> Path:
    window.mock.setChecked(True)
    english = window.language.findData("en")
    if english >= 0:
        window.language.setCurrentIndex(english)
    window.brief_form.notes.setPlainText(
        "A night ferry sticks in a lock. The keeper stays. One passenger stays."
    )
    window._draft_brief()
    if not window.title.text().strip():
        raise RuntimeError("Help me write the brief did not fill the form")
    return _save(window, path)


def _shot_progress(window: MainWindow, path: Path) -> Path:
    window.synopsis.setPlainText("A night ferry sticks in a lock.")
    window.shell.set_prompt_text(window.synopsis.toPlainText())
    if window.book.phase is not Phase.BUSY:
        window.book.generate()
    window.book.progress(1, 1, "Writing")
    window.log.setPlainText(
        "\n".join(
            [
                "story bible",
                "outline",
                "beats ch-01",
                "draft sc-01",
                "load qwen3.6-27b-abliterated-q3-k-m",
                "fill sc-01",
            ]
        )
    )
    window.shell.refresh()
    return _save(window, path)


def _shot_settings(window: MainWindow, path: Path) -> Path:
    window._open_settings()
    note = window.vram_note.text()
    if "16" not in note and "24" not in note:
        raise RuntimeError(f"Settings tier panel has no tier: {note}")
    return _save(window, path)


def _shot_result(window: MainWindow, path: Path, export_dir: Path | None) -> Path:
    if export_dir is None:
        window.run_selftest()
        if "book.vxbook" not in window.result_label.text():
            raise RuntimeError("result screen has no book.vxbook path")
        return _save(window, path)
    lines = [str(export_dir / name) for name in _EXPORT_NAMES]
    text = "Done\n" + "\n".join(lines)
    window.result_label.setText(text)
    window.shell.export_text = text
    if window.book.phase is not Phase.BUSY:
        window.synopsis.setPlainText("A finished book.")
        window.shell.set_prompt_text(window.synopsis.toPlainText())
        window.book.generate()
    window.book.finish("vm-shot-result")
    window.shell.refresh()
    return _save(window, path)


def save_main_window(path: Path) -> Path:
    """Grab the real main window at 1920x1080. An offscreen platform is refused."""
    if os.environ.get("QT_QPA_PLATFORM", "").strip().lower() == "offscreen":
        raise RuntimeError("main-window.png needs a real window")
    path.parent.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    register_ui_fonts()
    app.setFont(ui_font(10))
    window = MainWindow(mock=True)
    window.resize(1920, 1080)
    window.show()
    app.processEvents()
    screen = window.screen()
    if screen is None:
        raise RuntimeError("main-window.png needs a real window")
    pixmap = screen.grabWindow(int(window.winId()))
    if pixmap.width() < 1900 or pixmap.height() < 1000:
        raise RuntimeError(f"main window is {pixmap.width()}x{pixmap.height()}")
    if not pixmap.save(str(path), "PNG"):
        raise RuntimeError(f"could not save {path}")
    return path


def _save(window: MainWindow, path: Path) -> Path:
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("Qt application is missing")
    window.resize(900, 1500)
    window.show()
    app.processEvents()
    image = QImage(window.size(), QImage.Format.Format_ARGB32)
    image.fill(0xFF1A1A1A)
    painter = QPainter(image)
    window.render(painter, QPoint())
    painter.end()
    if image.width() < 800 or image.height() < 600:
        raise RuntimeError(f"screenshot is too small: {path.name}")
    # This PySide build accepts a str format. The stub types that argument as bytes.
    if not image.save(str(path), "PNG"):  # type: ignore[call-overload]
        raise RuntimeError(f"could not save {path}")
    return path
