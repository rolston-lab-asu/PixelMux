"""
DIT "RESULTS" tab: the extracted-charge/peak-current table and its
Export .TXT / Export .CSV buttons.
"""
from atom.api import Atom, Bool, Event, List, Typed
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QMessageBox,
)

from gui.custom_widgets import RichTextHeaderView
from gui.formatting import format_si
from gui.effects import make_panel_shadow, update_shadow_color
from gui.style import get_theme_colors

_HEADERS = [
    "Pixel", "Area", "V1 (V)", "V2 (V)", "Extracted Charge", "Peak |I|", "Status",
]


class DITResultsPanel(Atom):
    __slots__ = ('__weakref__',)

    is_dark_mode = Bool(False)

    export_txt_requested = Event()
    export_csv_requested = Event()
    delete_selected_requested = Event()
    clear_table_requested = Event()

    _widget = Typed(QWidget)
    _table = Typed(QTableWidget)
    _export_txt_btn = Typed(QPushButton)
    _export_csv_btn = Typed(QPushButton)
    _delete_selected_btn = Typed(QPushButton)
    _clear_table_btn = Typed(QPushButton)
    _shadow = Typed(object)
    _role_colored_items = List()  # [(QTableWidgetItem, role), ...] for theme refresh

    def get_widget(self):
        return self._widget

    def create_widget(self, parent):
        container = QWidget(parent)
        layout = QVBoxLayout(container)
        layout.addWidget(self._build_results_panel())
        self._widget = container
        return container

    def _build_results_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        title_lbl = QLabel("DARK INJECTION TRANSIENTS")
        title_lbl.setObjectName("PanelTitle")
        header_row.addWidget(title_lbl)
        header_row.addStretch(1)

        self._delete_selected_btn = QPushButton("Delete Selected")
        self._delete_selected_btn.clicked.connect(self._on_delete_selected_clicked)
        self._delete_selected_btn.setEnabled(False)
        header_row.addWidget(self._delete_selected_btn)

        self._clear_table_btn = QPushButton("Clear Table")
        self._clear_table_btn.clicked.connect(self._on_clear_table_clicked)
        header_row.addWidget(self._clear_table_btn)

        export_lbl = QLabel("MANUAL EXPORT:")
        export_lbl.setObjectName("DimLabel")
        header_row.addWidget(export_lbl)

        self._export_txt_btn = QPushButton("Export .TXT")
        self._export_txt_btn.clicked.connect(self._on_export_txt_clicked)
        self._export_txt_btn.setEnabled(False)
        header_row.addWidget(self._export_txt_btn)

        self._export_csv_btn = QPushButton("Export .CSV")
        self._export_csv_btn.clicked.connect(self._on_export_csv_clicked)
        self._export_csv_btn.setEnabled(False)
        header_row.addWidget(self._export_csv_btn)

        layout.addLayout(header_row)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        table_wrap = QFrame()
        table_wrap.setObjectName("TableWrap")
        table_wrap.setAttribute(Qt.WA_StyledBackground, True)
        table_wrap_layout = QVBoxLayout(table_wrap)
        table_wrap_layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget()
        self._table.setObjectName("ResultsTable")
        self._table.setFrameShape(QFrame.NoFrame)
        self._table.setColumnCount(len(_HEADERS))

        header = RichTextHeaderView(Qt.Horizontal, self._table)
        self._table.setHorizontalHeader(header)
        header.set_text_color(get_theme_colors(self.is_dark_mode)["accent"])

        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)

        self._table.setSelectionMode(QAbstractItemView.MultiSelection)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(24)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.setMinimumHeight(260)
        table_wrap_layout.addWidget(self._table)

        layout.addWidget(table_wrap)

        self._shadow = make_panel_shadow(panel, self.is_dark_mode)
        return panel

    def _on_export_txt_clicked(self):
        self.export_txt_requested = True

    def _on_export_csv_clicked(self):
        self.export_csv_requested = True

    def _on_selection_changed(self):
        self._delete_selected_btn.setEnabled(bool(self._table.selectedIndexes()))

    def _on_delete_selected_clicked(self):
        self.delete_selected_requested = True

    def _on_clear_table_clicked(self):
        row_count = self._table.rowCount()
        if row_count == 0:
            return
        reply = QMessageBox.question(
            self._table,
            "Clear Table",
            f"Clear all {row_count} row(s) from the results table?\n"
            "This can't be undone (already-autosaved files on disk are not affected).",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.clear_table_requested = True

    # --- Public API for the controller ---

    def clear(self):
        self._table.setRowCount(0)
        self._role_colored_items = []
        self._delete_selected_btn.setEnabled(False)

    def get_selected_row_tokens(self):
        rows = sorted({index.row() for index in self._table.selectedIndexes()})
        tokens = []
        for r in rows:
            item = self._table.item(r, 0)
            if item is not None:
                tokens.append(item.data(Qt.UserRole))
        return tokens

    def remove_rows_by_tokens(self, tokens):
        token_set = set(tokens)
        for r in range(self._table.rowCount() - 1, -1, -1):
            item = self._table.item(r, 0)
            if item is not None and item.data(Qt.UserRole) in token_set:
                self._table.removeRow(r)
        self._delete_selected_btn.setEnabled(False)

    def add_result_row(self, pixel, area, v1, v2, charge, peak_current, status, row_token=None):
        r = self._table.rowCount()
        self._table.insertRow(r)

        values = [pixel, f"{area:.4f}"]

        if v1 is not None:
            values.extend([f"{v1:.3f}", f"{v2:.3f}"])
        else:
            values.extend(["--", "--"])

        if charge is not None:
            values.extend([format_si(charge, "C"), format_si(peak_current, "A")])
        else:
            values.extend(["--", "--"])

        values.append(status)

        role_colored = list(self._role_colored_items)
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)

            if col == 0:
                item.setData(Qt.UserRole, row_token)

            if col > 0:
                item.setTextAlignment(Qt.AlignCenter)

            if col == self._table.columnCount() - 1:
                # Status column: green for OK, red for any fault string
                self._apply_role_color(item, "success" if value == "OK" else "error", role_colored)
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            self._table.setItem(r, col, item)
        self._role_colored_items = role_colored

    def _apply_role_color(self, item, role, role_colored):
        item.setForeground(QBrush(QColor(get_theme_colors(self.is_dark_mode)[role])))
        role_colored.append((item, role))

    def get_export_data(self):
        headers = []
        for col in range(self._table.columnCount()):
            header_item = self._table.horizontalHeaderItem(col)
            raw = header_item.text() if header_item else ""
            headers.append(raw)

        rows = []
        for r in range(self._table.rowCount()):
            rows.append([
                self._table.item(r, c).text() if self._table.item(r, c) else ""
                for c in range(self._table.columnCount())
            ])
        return headers, rows

    def has_rows(self):
        return self._table.rowCount() > 0

    def set_export_enabled(self, enabled):
        self._export_txt_btn.setEnabled(enabled)
        self._export_csv_btn.setEnabled(enabled)

    def apply_theme(self, colors, is_dark_mode):
        self.is_dark_mode = is_dark_mode
        update_shadow_color(self._shadow, is_dark_mode)

        for item, role in self._role_colored_items:
            item.setForeground(QBrush(QColor(colors[role])))

        header = self._table.horizontalHeader()
        if isinstance(header, RichTextHeaderView):
            header.set_text_color(colors["accent"])
