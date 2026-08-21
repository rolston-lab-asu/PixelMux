"""
About dialog: app identity, credits, acknowledgements, and license.
Opened from the header's About action (Home screen only).

Two-column layout: a sidebar carries the identity mark (icon, version,
repository link) while the main pane carries the descriptive content
(title, tagline, credits, license, close).
"""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from core.app_info import (
    ACKNOWLEDGEMENTS, APP_NAME, APP_VERSION, AUTHOR, AUTHOR_INSTITUTION,
    COPYRIGHT_YEAR, GITHUB_URL, LICENSE_NAME,
)
from gui.icon_utils import rounded_icon

SIDEBAR_WIDTH = 150
ICON_SIZE = 64
ICON_RADIUS = 14


class AboutDialog(QDialog):
    def __init__(self, parent, colors):
        super().__init__(parent)
        self.setObjectName("AboutDialog")
        self.setWindowTitle(f"About {APP_NAME}")
        self.setFixedWidth(560)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_sidebar())
        outer.addWidget(self._build_main_pane(), 1)

        self.setStyleSheet(self._local_qss(colors))

        # Fix both dimensions so the dialog can't be dragged/resized —
        # width is set above; height is derived from the populated layout.
        self.adjustSize()
        self.setFixedHeight(self.sizeHint().height())

    # --- Column builders ---

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("AboutSidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 22, 16, 20)
        layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setObjectName("AboutIcon")
        icon_lbl.setFixedSize(ICON_SIZE, ICON_SIZE)
        icon_lbl.setPixmap(rounded_icon(ICON_SIZE, ICON_RADIUS))
        layout.addWidget(icon_lbl, 0, Qt.AlignHCenter)

        version_lbl = QLabel(APP_VERSION)
        version_lbl.setObjectName("VersionPill")
        version_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_lbl, 0, Qt.AlignHCenter)

        layout.addStretch(1)

        repo_btn = QPushButton("Repository")
        repo_btn.setObjectName("GithubButton")
        repo_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        layout.addWidget(repo_btn)

        return sidebar

    def _build_main_pane(self):
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(0)

        name_lbl = QLabel(APP_NAME)
        name_lbl.setObjectName("AboutTitleName")
        layout.addWidget(name_lbl)

        tagline = QLabel(
            "A characterization suite for photovoltaic devices, built around "
            "perovskite thin-film cells on multi-pixel substrates."
        )
        tagline.setObjectName("DimLabel")
        tagline.setWordWrap(True)
        tagline.setStyleSheet("font-weight: 500; margin-top: 4px;")
        layout.addWidget(tagline)

        layout.addSpacing(14)
        layout.addWidget(self._divider())
        layout.addSpacing(14)

        layout.addLayout(self._build_meta_grid())
        layout.addLayout(self._build_footer_row())

        return pane

    # --- Row builders ---

    def _build_meta_grid(self):
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(12)
        grid.setColumnMinimumWidth(0, 84)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self._caption_label("CREATED BY"), 0, 0, Qt.AlignTop)
        grid.addLayout(self._value_with_suffix(AUTHOR, AUTHOR_INSTITUTION), 0, 1)

        grid.addWidget(self._caption_label("THANKS TO"), 1, 0, Qt.AlignTop)
        grid.addLayout(self._value_with_suffix(", ".join(ACKNOWLEDGEMENTS), None), 1, 1)

        grid.addWidget(self._caption_label("LICENSE"), 2, 0, Qt.AlignVCenter)
        chip = QLabel(LICENSE_NAME)
        chip.setObjectName("LicenseChip")
        grid.addWidget(chip, 2, 1, Qt.AlignLeft | Qt.AlignVCenter)

        return grid

    def _caption_label(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("FieldLabel")
        lbl.setStyleSheet("letter-spacing: 0.4px;")
        return lbl

    def _value_with_suffix(self, value_text, suffix_text):
        row = QHBoxLayout()
        row.setSpacing(4)
        value = QLabel(value_text)
        value.setObjectName("MainLabel")
        row.addWidget(value)
        if suffix_text:
            suffix = QLabel(f"({suffix_text})")
            suffix.setObjectName("DimLabel")
            suffix.setStyleSheet("font-weight: 400; font-size: 9pt;")
            row.addWidget(suffix)
        row.addStretch(1)
        return row

    def _build_footer_row(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 22, 0, 0)
        row.setSpacing(10)

        copyright_lbl = QLabel(
            f"\u00a9 {COPYRIGHT_YEAR} {APP_NAME} \u00b7 Research use"
        )
        copyright_lbl.setObjectName("FieldLabel")
        row.addWidget(copyright_lbl)
        row.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("PrimaryButton")
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        return row

    def _divider(self):
        line = QFrame()
        line.setObjectName("Divider")
        line.setFrameShape(QFrame.HLine)
        return line

    def _local_qss(self, c):
        return f"""
        QDialog#AboutDialog {{
            background-color: {c['bg_panel']};
        }}
        QFrame#AboutSidebar {{
            background-color: {c['card_bg']};
            border-right: 1px solid {c['border']};
        }}
        QLabel#AboutIcon {{
            border: 1px solid {c['border']};
            border-radius: {ICON_RADIUS}px;
        }}
        QLabel#VersionPill {{
            color: {c['accent']};
            background-color: {c['accent_glow']};
            font-weight: 700;
            font-size: 8pt;
            padding: 3px 9px;
            border-radius: 6px;
        }}
        QLabel#AboutTitleName {{
            color: {c['text_main']};
            font-weight: 700;
            font-size: 13pt;
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
