"""
Startup splash screen.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QSplashScreen

from core.app_info import APP_NAME_UPPER, APP_TAGLINE
from gui.style import THEME_COLORS

_COLORS = THEME_COLORS[True]  # dark mode
_WIDTH, _HEIGHT = 460, 260


def _splash_font(point_size, bold=False):
    """Segoe UI on Windows, with the platform's own UI font as the fallback
    elsewhere."""
    font = QFont()
    font.setFamilies(["Segoe UI", "Inter", "Helvetica Neue", "Arial"])
    font.setStyleHint(QFont.SansSerif)
    font.setPointSize(point_size)
    font.setBold(bold)
    return font


def build_splash(app):
    pix = QPixmap(_WIDTH, _HEIGHT)
    pix.fill(QColor(_COLORS["bg_base"]))

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    # Accent bar
    painter.setBrush(QColor(_COLORS["accent"]))
    painter.setPen(Qt.NoPen)
    painter.drawRect(0, 0, _WIDTH, 6)

    # Title
    painter.setFont(_splash_font(18, bold=True))
    painter.setPen(QColor(_COLORS["text_main"]))
    painter.drawText(pix.rect().adjusted(0, 40, 0, 0), Qt.AlignHCenter | Qt.AlignTop, APP_NAME_UPPER)

    painter.setFont(_splash_font(10))
    painter.setPen(QColor(_COLORS["text_dim"]))
    painter.drawText(
        pix.rect().adjusted(0, 78, 0, 0),
        Qt.AlignHCenter | Qt.AlignTop,
        APP_TAGLINE,
    )
    painter.end()

    splash = QSplashScreen(pix, Qt.WindowStaysOnTopHint)
    splash.setWindowFlag(Qt.FramelessWindowHint)
    return splash


def splash_message(splash, text):
    splash.showMessage(text, Qt.AlignHCenter | Qt.AlignBottom, QColor(_COLORS["accent"]))
