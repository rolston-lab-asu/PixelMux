"""
Shared helper for rendering the app's icon mark.
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap

from core.paths import get_project_root


def icon_path():
    return os.path.join(get_project_root(), ".app_internal", "assets", "icons", "app_icon.png")


def rounded_icon(size, radius):
    """Center-crops the app icon to a square and clips it to rounded
    corners."""
    src = QPixmap(icon_path())
    if src.isNull():
        return src
    src = src.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x, y = (src.width() - size) // 2, (src.height() - size) // 2
    src = src.copy(x, y, size, size)

    rounded = QPixmap(size, size)
    rounded.fill(Qt.transparent)
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, src)
    painter.end()
    return rounded
