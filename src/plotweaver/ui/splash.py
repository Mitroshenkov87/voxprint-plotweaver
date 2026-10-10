"""Startup splash. The version line is the same string as plotweaver --version."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from plotweaver.appinfo import version_label
from plotweaver.ui.i18n import tr
from plotweaver.ui.theme import ROOT_PLAIN, SPLASH, TEXT, TEXT_MUTED


class Splash(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("splash")
        self.version_text = version_label()
        self.setStyleSheet(
            f"QWidget#splash {{ background: {ROOT_PLAIN}; }}QLabel {{ background: transparent; }}"
        )
        self.resize(440, 200)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        title = QLabel(tr("app"))
        title.setStyleSheet(f"color: {SPLASH}; font-size: 22px; font-weight: 600;")
        layout.addWidget(title)
        version = QLabel(self.version_text)
        version.setObjectName("splash-version")
        version.setStyleSheet(f"color: {TEXT}; font-size: 15px;")
        version.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(version)
        note = QLabel(tr("subtitle"))
        note.setStyleSheet(f"color: {TEXT_MUTED};")
        note.setWordWrap(True)
        layout.addWidget(note)
