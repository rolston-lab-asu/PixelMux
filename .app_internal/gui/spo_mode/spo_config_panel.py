"""
SPO "CONFIG" tab: hold-parameter form on the left, substrate diagram +
dataset card on the right.
"""
from atom.api import Atom, Bool, Event, List, Typed
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel,
    QCheckBox, QPushButton, QLineEdit, QLayout, QStyle,
)

from instruments.keithley2460 import KEITHLEY_DEFAULT_COMPLIANCE_A
from gui.custom_widgets import PlainIntField, PlainDoubleField
from gui.common_panels.substrate_panel import SubstratePanel
from gui.effects import make_panel_shadow, update_shadow_color


class SPOConfigPanel(Atom):
    __slots__ = ('__weakref__',)

    is_dark_mode = Bool(False)

    run_requested = Event()
    layout_changed = Event()
    browse_requested = Event()
    name_changed = Event()
    autosave_table_toggled = Event()
    autosave_curves_toggled = Event()

    _widget = Typed(QWidget)

    # Hold-parameter inputs
    _hold_v = Typed(PlainDoubleField)
    _duration = Typed(PlainDoubleField)
    _interval = Typed(PlainDoubleField)
    _loops = Typed(PlainIntField)
    _compliance_ma = Typed(PlainDoubleField)
    _start_btn = Typed(QPushButton)

    _top_layout = Typed(QHBoxLayout)
    _sweep_panel = Typed(QFrame)
    _shadow_widgets = List()

    _substrate = Typed(SubstratePanel)

    # Dataset card: Name field, browse icon button, auto-save toggle + path preview
    _name_field = Typed(QLineEdit)
    _autosave_table_checkbox = Typed(QCheckBox)
    _autosave_curves_checkbox = Typed(QCheckBox)
    _path_preview = Typed(QLabel)

    def get_widget(self):
        return self._widget

    def create_widget(self, parent):
        container = QWidget(parent)

        self._top_layout = layout = QHBoxLayout(container)
        layout.setSpacing(15)
        layout.setSizeConstraint(QLayout.SetNoConstraint)
        self._sweep_panel = self._build_sweep_panel()
        layout.addWidget(self._sweep_panel, 1)
        layout.addWidget(self._build_pixel_panel(), 2)

        self._widget = container
        return container

    # --- Hold-parameter panel ---

    def _build_sweep_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(0)

        title_lbl = QLabel("SPO PARAMETERS")
        title_lbl.setObjectName("PanelTitle")
        title_lbl.setStyleSheet("padding-bottom: 8px;")
        layout.addWidget(title_lbl)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        self._hold_v = PlainDoubleField()
        self._hold_v.setRange(-5, 5)
        self._hold_v.setDecimals(2)
        self._hold_v.setValue(0.80)

        self._duration = PlainDoubleField()
        self._duration.setRange(1, 36000)
        self._duration.setDecimals(0)
        self._duration.setValue(120)

        self._interval = PlainDoubleField()
        self._interval.setRange(0.1, 3600)
        self._interval.setDecimals(1)
        self._interval.setValue(1.0)

        self._loops = PlainIntField()
        self._loops.setRange(1, 20)
        self._loops.setValue(1)

        self._compliance_ma = PlainDoubleField()
        self._compliance_ma.setRange(0.001, 1000)
        self._compliance_ma.setDecimals(0)
        self._compliance_ma.setValue(KEITHLEY_DEFAULT_COMPLIANCE_A * 1000)

        def make_row(label_text, widget):
            row = QFrame()
            row.setObjectName("FormRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 8, 0, 8)

            lbl = QLabel(label_text)
            lbl.setObjectName("DimLabel")

            widget.setFixedWidth(140)

            row_layout.addWidget(lbl)
            row_layout.addStretch(1)
            row_layout.addWidget(widget)
            return row

        layout.addWidget(make_row("Hold V (V)", self._hold_v))
        layout.addWidget(make_row("Duration (s)", self._duration))
        layout.addWidget(make_row("Interval (s)", self._interval))
        layout.addWidget(make_row("Loops", self._loops))
        layout.addWidget(make_row("Compliance (mA)", self._compliance_ma))

        layout.addStretch(1)

        self._start_btn = QPushButton("INITIALIZE SPO HOLD")
        self._start_btn.setObjectName("PrimaryButton")
        self._start_btn.setMinimumHeight(44)
        self._start_btn.clicked.connect(self._on_run_clicked)
        layout.addWidget(self._start_btn)

        self._add_shadow(panel)
        return panel

    def _on_run_clicked(self):
        self.run_requested = True

    # --- Substrate diagram (shared widget) ---

    def _build_pixel_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self._substrate = SubstratePanel(is_dark_mode=self.is_dark_mode)
        self._substrate.observe("layout_changed", self._on_substrate_layout_changed)
        layout.addWidget(self._substrate.create_widget(panel))
        layout.addStretch(1)

        layout.addWidget(self._build_dataset_card())

        self._add_shadow(panel)
        return panel

    def _on_substrate_layout_changed(self, change):
        self.layout_changed = True

    # --- Dataset card ---

    def _build_dataset_card(self):
        card = QFrame()
        card.setObjectName("DatasetCard")
        card.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        name_row = QHBoxLayout()
        name_row.setSpacing(10)
        name_lbl = QLabel("Name:")
        name_lbl.setObjectName("DimLabel")
        name_lbl.setFixedWidth(45)
        name_row.addWidget(name_lbl)

        self._name_field = QLineEdit("Sample_A")
        self._name_field.textChanged.connect(self._on_name_changed)
        name_row.addWidget(self._name_field, 1)

        browse_btn = QPushButton()
        browse_btn.setIcon(browse_btn.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        browse_btn.setFixedSize(34, 34)
        browse_btn.clicked.connect(self._on_browse_clicked)
        name_row.addWidget(browse_btn)
        layout.addLayout(name_row)

        self._autosave_table_checkbox = QCheckBox("Autosave results table")
        self._autosave_table_checkbox.setChecked(True)
        self._autosave_table_checkbox.toggled.connect(self._on_autosave_table_toggled)
        layout.addWidget(self._autosave_table_checkbox)

        self._autosave_curves_checkbox = QCheckBox("Autosave individual time-series data points")
        self._autosave_curves_checkbox.setChecked(True)
        self._autosave_curves_checkbox.toggled.connect(self._on_autosave_curves_toggled)
        layout.addWidget(self._autosave_curves_checkbox)

        self._path_preview = QLabel("")
        self._path_preview.setObjectName("PathPreview")
        self._path_preview.setAttribute(Qt.WA_StyledBackground, True)
        self._path_preview.setWordWrap(True)
        layout.addWidget(self._path_preview)

        return card

    def _on_name_changed(self, text):
        self.name_changed = True

    def _on_browse_clicked(self):
        self.browse_requested = True

    def _on_autosave_table_toggled(self, checked):
        self.autosave_table_toggled = True

    def _on_autosave_curves_toggled(self, checked):
        self.autosave_curves_toggled = True

    def _add_shadow(self, widget):
        effect = make_panel_shadow(widget, self.is_dark_mode)
        self._shadow_widgets = self._shadow_widgets + [effect]

    # --- Public API for the controller ---

    def refresh_layout(self, available_width=None):
        widget = self.get_widget()
        if widget is not None:
            widget.updateGeometry()

    def validate(self):
        if not self._substrate.has_active_pixel():
            return "ERROR: Please select at least one pixel."
        return None

    def get_spo_params(self):
        return {
            "hold_v": self._hold_v.value(),
            "duration_s": self._duration.value(),
            "interval_s": self._interval.value(),
            "compliance_a": self._compliance_ma.value() / 1000,
            "loops": self._loops.value(),
        }

    def get_selected_pixels(self):
        return self._substrate.get_selected_pixels()

    def set_running(self, running):
        self._start_btn.setEnabled(not running)
        self._name_field.setEnabled(not running)
        self._autosave_table_checkbox.setEnabled(not running)
        self._autosave_curves_checkbox.setEnabled(not running)

    def set_start_button_alert(self, alert):
        self._start_btn.setProperty("alert", "true" if alert else "false")
        self._repolish(self._start_btn)

    def flash_alert(self):
        """Brief red blink on the run button -- used when the user tries
        to start a run that will immediately fail (e.g. instruments not
        connected), rather than a persistent color change."""
        self.set_start_button_alert(True)
        QTimer.singleShot(180, lambda: self.set_start_button_alert(False))
        QTimer.singleShot(360, lambda: self.set_start_button_alert(True))
        QTimer.singleShot(540, lambda: self.set_start_button_alert(False))

    def apply_theme(self, colors, is_dark_mode):
        self.is_dark_mode = is_dark_mode
        for effect in self._shadow_widgets:
            update_shadow_color(effect, is_dark_mode)
        self._substrate.apply_theme(colors, is_dark_mode)

    def sample_name(self):
        return self._name_field.text().strip()

    def autosave_table_enabled(self):
        return self._autosave_table_checkbox.isChecked()

    def autosave_curves_enabled(self):
        return self._autosave_curves_checkbox.isChecked()

    def set_path_preview(self, text, is_warning):
        self._path_preview.setText(text)
        self._path_preview.setProperty("state", "warning" if is_warning else "")
        self._repolish(self._path_preview)

    @staticmethod
    def _repolish(widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)
