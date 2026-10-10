"""Suite blue + yellow palette. Acrylic on Windows, plain dark everywhere else.

Tokens match suite/design/PALETTE.md. Text sits on solid cards so contrast does not
depend on the blurred desktop. The splash accent is Plotweaver's own violet.
"""

from __future__ import annotations

import ctypes
import sys

PRIMARY = "#f5d76e"
PRIMARY_HOVER = "#f9e291"
PRIMARY_BORDER = "#fbe8a6"
TEXT_ON_PRIMARY = "#1c1604"
PRIMARY_DISABLED_BG = "#36321f"
PRIMARY_DISABLED_TEXT = "#b9b08a"
MENU_BG = "#1c2535"
MENU_SELECTION = "#2f4c78"
ACCENT = "#60a5fa"
ACCENT_HOVER = "#7db9ff"
ACCENT_SOFT = "#93c5fd"
ACCENT_STRONG = "#2563eb"
TEXT_ON_ACCENT = "#0b1220"
TEXT = "#f2f2f5"
TEXT_MUTED = "#c4c4d0"
TEXT_FAINT = "#a8a8b8"
TEXT_DISABLED = "#8e8e9e"
ROOT_PLAIN = "#17171c"
ROOT_GLASS = "rgba(16,16,22,222)"
CARD_PLAIN = "#202029"
CARD_GLASS = "rgba(34,34,44,238)"
CONTROL_BG = "#2c2c38"
CONTROL_HOVER = "#383846"
CONTROL_BORDER = "#4b4b5c"
AMBER = "#fcd34d"
NOTE_BG = "#2a2418"
NOTE_BORDER = "#6b5720"
GREEN = "#86efac"
RED = "#fca5a5"
SPLASH = "#8b7cff"
WHITE = "#ffffff"


def _channel(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.removeprefix("#")
    red = int(value[0:2], 16) / 255
    green = int(value[2:4], 16) / 255
    blue = int(value[4:6], 16) / 255
    return red, green, blue


def _linearize(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return float(((channel + 0.055) / 1.055) ** 2.4)


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG relative contrast. Both colours are opaque hex."""

    def luminance(hex_color: str) -> float:
        red, green, blue = (_linearize(channel) for channel in _channel(hex_color))
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    lighter = max(luminance(foreground), luminance(background))
    darker = min(luminance(foreground), luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def build_style(*, glass: bool) -> str:
    root = ROOT_GLASS if glass else ROOT_PLAIN
    card = CARD_GLASS if glass else CARD_PLAIN
    return f"""
    QMainWindow, QWidget#root {{
        background: {root};
        color: {TEXT};
        font-size: 14px;
    }}
    QLabel {{ color: {TEXT}; background: transparent; }}
    QLabel#muted {{ color: {TEXT_MUTED}; }}
    QLabel#faint {{ color: {TEXT_FAINT}; }}
    QFrame#card {{
        background: {card};
        border: 1px solid {CONTROL_BORDER};
        border-radius: 12px;
    }}
    QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {{
        background: {CONTROL_BG};
        color: {TEXT};
        border: 1px solid {CONTROL_BORDER};
        border-radius: 8px;
        padding: 6px;
        selection-background-color: {ACCENT_STRONG};
        selection-color: {WHITE};
    }}
    QComboBox QAbstractItemView {{
        background: {MENU_BG};
        color: {TEXT};
        selection-background-color: {MENU_SELECTION};
        selection-color: {WHITE};
    }}
    QPushButton {{
        background: {CONTROL_BG};
        color: {TEXT};
        border: 1px solid {CONTROL_BORDER};
        border-radius: 8px;
        padding: 8px 14px;
    }}
    QPushButton:hover {{ background: {CONTROL_HOVER}; }}
    QPushButton#primary {{
        background: {PRIMARY};
        color: {TEXT_ON_PRIMARY};
        border: 1px solid {PRIMARY_BORDER};
        font-weight: 600;
    }}
    QPushButton#primary:hover {{ background: {PRIMARY_HOVER}; }}
    QPushButton#primary:disabled {{
        background: {PRIMARY_DISABLED_BG};
        color: {PRIMARY_DISABLED_TEXT};
    }}
    QCheckBox {{ color: {TEXT}; spacing: 8px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border: 1px solid {ACCENT};
        background: {CONTROL_BG};
        border-radius: 3px;
    }}
    QCheckBox::indicator:checked {{ background: {ACCENT}; }}
    QProgressBar {{
        background: {CONTROL_BG};
        border: 1px solid {CONTROL_BORDER};
        border-radius: 6px;
        color: {TEXT};
        text-align: center;
    }}
    QProgressBar::chunk {{ background: {ACCENT_STRONG}; border-radius: 6px; }}
    """


def enable_acrylic(hwnd: int) -> bool:
    """Windows 11 Acrylic. Returns False on every other platform."""
    if sys.platform != "win32" or hwnd == 0:
        return False
    try:
        dwmapi = ctypes.windll.dwmapi
    except AttributeError:
        return False
    backdrop = ctypes.c_int(3)  # DWMSBT_TRANSIENTWINDOW, acrylic
    # DWMWA_SYSTEMBACKDROP_TYPE = 38
    result = dwmapi.DwmSetWindowAttribute(
        ctypes.c_void_p(hwnd),
        ctypes.c_uint(38),
        ctypes.byref(backdrop),
        ctypes.sizeof(backdrop),
    )
    return int(result) == 0
