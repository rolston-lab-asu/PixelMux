"""
About dialog: app identity, credits, acknowledgements, and license.
Opened from the header's About action (Home screen only).
"""
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from core.app_info import (
    ACKNOWLEDGEMENTS, APP_NAME, APP_NAME_UPPER, APP_VERSION, AUTHOR,
    COPYRIGHT_YEAR, GITHUB_LABEL, GITHUB_URL, LICENSE_NAME,
)
from core.paths import get_project_root

ICON_SIZE = 46
ICON_RADIUS = 9


def _icon_path():
    return os.path.join(get_project_root(), ".app_internal", "assets", "icons", "app_icon.png")


def _rounded_icon(size, radius):
    """Center-crops the app icon to a square and clips it to rounded
    corners, so the About dialog gets the same mark as the taskbar icon."""
    src = QPixmap(_icon_path())
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


class AboutDialog(QDialog):
    def __init__(self, parent, colors):
        super().__init__(parent)
        self.setObjectName("AboutDialog")
        self.setWindowTitle(f"About {APP_NAME}")
        self.setFixedWidth(460)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 22, 26, 20)
        outer.setSpacing(0)

        outer.addLayout(self._build_identity_row())

        tagline = QLabel(
            "A characterization suite for photovoltaic devices, built around "
            "perovskite thin-film cells on multi-pixel substrates."
        )
        tagline.setObjectName("DimLabel")
        tagline.setWordWrap(True)
        tagline.setStyleSheet("font-weight: 500; margin-top: 14px;")
        outer.addWidget(tagline)

        outer.addWidget(self._divider())
        outer.addWidget(self._section_label("CREDITS"))
        outer.addLayout(self._info_row("Created by", AUTHOR))
        outer.addLayout(self._info_row("Source", GITHUB_LABEL))

        outer.addWidget(self._divider())
        outer.addWidget(self._section_label("ACKNOWLEDGEMENTS"))
        for name in ACKNOWLEDGEMENTS:
            outer.addWidget(self._ack_row(name))

        outer.addWidget(self._divider())
        outer.addWidget(self._section_label("LICENSE"))
        outer.addLayout(self._license_row())

        outer.addLayout(self._build_footer_row())

        copyright_lbl = QLabel(
            f"\u00a9 {COPYRIGHT_YEAR} {APP_NAME}. Released for internal / research use."
        )
        copyright_lbl.setObjectName("FieldLabel")
        copyright_lbl.setAlignment(Qt.AlignHCenter)
        copyright_lbl.setStyleSheet("margin-top: 14px;")
        outer.addWidget(copyright_lbl)

        self.setStyleSheet(self._local_qss(colors))

    # --- Row builders ---

    def _build_identity_row(self):
        row = QHBoxLayout()
        row.setSpacing(14)

        icon_lbl = QLabel()
        icon_lbl.setObjectName("AboutIcon")
        icon_lbl.setFixedSize(ICON_SIZE, ICON_SIZE)
        icon_lbl.setPixmap(_rounded_icon(ICON_SIZE, ICON_RADIUS))
        row.addWidget(icon_lbl, 0, Qt.AlignTop)

        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        name_lbl = QLabel(APP_NAME_UPPER)
        name_lbl.setObjectName("PanelTitleLarge")
        name_col.addWidget(name_lbl)
        version_lbl = QLabel(APP_VERSION)
        version_lbl.setObjectName("FieldLabel")
        name_col.addWidget(version_lbl)
        row.addLayout(name_col)
        row.addStretch(1)
        return row

    def _info_row(self, role_text, value_text):
        row = QHBoxLayout()
        role = QLabel(role_text)
        role.setObjectName("DimLabel")
        role.setStyleSheet("font-weight: 500;")
        value = QLabel(value_text)
        value.setObjectName("MainLabel")
        row.addWidget(role)
        row.addStretch(1)
        row.addWidget(value)
        return row

    def _ack_row(self, name):
        card = QFrame()
        card.setObjectName("AckRow")
        card.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(1)

        name_lbl = QLabel(name)
        name_lbl.setObjectName("AckName")
        name_lbl.setMinimumWidth(140)
        layout.addWidget(name_lbl)
        return card

    def _license_row(self):
        row = QHBoxLayout()
        role = QLabel(f"{APP_NAME} is released under the")
        role.setObjectName("DimLabel")
        role.setStyleSheet("font-weight: 500;")
        role.setWordWrap(True)
        chip = QLabel(LICENSE_NAME)
        chip.setObjectName("LicenseChip")
        row.addWidget(role, 1)
        row.addWidget(chip, 0, Qt.AlignVCenter)
        return row

    def _build_footer_row(self):
        row = QHBoxLayout()
        row.setSpacing(10)
        row.setContentsMargins(0, 20, 0, 0)

        gh_btn = QPushButton("View on GitHub")
        gh_btn.setObjectName("GithubButton")
        gh_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        row.addWidget(gh_btn, 1)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("PrimaryButton")
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn, 0)
        return row

    def _section_label(self, text):
        lbl = QLabel(text.upper())
        lbl.setObjectName("AccentLabel")
        lbl.setStyleSheet("font-size: 9pt; margin-bottom: 10px;")
        return lbl

    def _divider(self):
        line = QFrame()
        line.setObjectName("Divider")
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("margin: 18px 0;")
        return line

    def _local_qss(self, c):
        return f"""
        QDialog#AboutDialog {{
            background-color: {c['bg_panel']};
        }}
        QLabel#AboutIcon {{
            border: 1px solid {c['border']};
            border-radius: {ICON_RADIUS}px;
        }}
        QFrame#AckRow {{
            background-color: {c['card_bg']};
            border: 1px solid {c['border']};
            border-radius: 7px;
        }}
        QLabel#AckName {{
            color: {c['text_main']};
            font-weight: 600;
            font-size: 12px;
        }}
        QLabel#LicenseChip {{
            font-size: 9pt;
            font-weight: 800;
            letter-spacing: 0.5px;
            color: {c['text_dim']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            padding: 3px 7px;
        }}
        QPushButton#GithubButton {{
            background-color: {c['bg_input']};
            border: 1px solid {c['border']};
        }}
        QPushButton#GithubButton:hover {{
            background-color: {c['row_hover']};
            border-color: {c['text_dim']};
        }}
        """
