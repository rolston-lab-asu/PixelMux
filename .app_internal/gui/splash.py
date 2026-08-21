"""
Startup splash screen.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QSplashScreen

from core.app_info import APP_NAME_UPPER, APP_VERSION
from gui.icon_utils import rounded_icon
from gui.style import THEME_COLORS

_COLORS = THEME_COLORS[False]  # light mode
_WIDTH, _HEIGHT = 460, 260

_ICON_SIZE = 72
_BAR_WIDTH = 220
_BAR_HEIGHT = 4


def _splash_font(point_size, bold=False):
    """Segoe UI on Windows, with the platform's own UI font as the fallback
    elsewhere."""
    font = QFont()
    font.setFamilies(["Segoe UI", "Inter", "Helvetica Neue", "Arial"])
    font.setStyleHint(QFont.SansSerif)
    font.setPointSize(point_size)
    font.setBold(bold)
    return font


def _render(message, percent):
    """Draws the full splash frame."""
    pix = QPixmap(_WIDTH, _HEIGHT)
    pix.fill(QColor(_COLORS["bg_panel"]))  # white

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    # Accent top bar
    painter.setBrush(QColor(_COLORS["accent"]))
    painter.setPen(Qt.NoPen)
    painter.drawRect(0, 0, _WIDTH, 6)

    # Icon mark, centered
    icon = rounded_icon(_ICON_SIZE, _ICON_SIZE // 5)
    icon_x = (_WIDTH - _ICON_SIZE) // 2
    icon_y = 42
    painter.drawPixmap(icon_x, icon_y, icon)

    # Wordmark
    painter.setFont(_splash_font(17, bold=True))
    painter.setPen(QColor(_COLORS["text_main"]))
    wordmark_y = icon_y + _ICON_SIZE + 16
    painter.drawText(
        0, wordmark_y, _WIDTH, 30, Qt.AlignHCenter | Qt.AlignTop, APP_NAME_UPPER
    )

    # Progress bar: track
    bar_x = (_WIDTH - _BAR_WIDTH) // 2
    bar_y = wordmark_y + 44
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(_COLORS["border"]))
    painter.drawRoundedRect(bar_x, bar_y, _BAR_WIDTH, _BAR_HEIGHT, 2, 2)

    clamped = max(0, min(percent, 100))
    fill_w = max(_BAR_HEIGHT, int(_BAR_WIDTH * clamped / 100))
    painter.setBrush(QColor(_COLORS["accent"]))
    painter.drawRoundedRect(bar_x, bar_y, fill_w, _BAR_HEIGHT, 2, 2)

    # Status message for the current stage
    painter.setFont(_splash_font(9))
    painter.setPen(QColor(_COLORS["text_dim"]))
    painter.drawText(
        0, bar_y + 14, _WIDTH, 20, Qt.AlignHCenter | Qt.AlignTop, message
    )

    # Version stamp
    painter.setFont(_splash_font(7))
    painter.setPen(QColor(_COLORS["text_dim"]))
    painter.drawText(
        0, _HEIGHT - 22, _WIDTH - 14, 16, Qt.AlignRight | Qt.AlignVCenter, APP_VERSION
    )

    painter.end()
    return pix


def build_splash(app):
    """Builds the splash with an empty bar."""
    pix = _render("", 0)
    splash = QSplashScreen(pix, Qt.WindowStaysOnTopHint)
    splash.setWindowFlag(Qt.FramelessWindowHint)
    return splash


def splash_progress(splash, message, percent):
    """Advances the splash to a new loading stage."""
    splash.setPixmap(_render(message, percent))
