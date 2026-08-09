"""
DIT "CONFIG" tab: voltage-step + acquisition parameter form on the left,
substrate diagram + dataset card on the right. 

Split into a "Voltage Step" group and an "Acquisition" group.
"""
from atom.api import Atom, Bool, Event, List, Typed
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QFrame, QGridLayout, QHBoxLayout, QVBoxLayout, QLabel,
    QCheckBox, QPushButton, QLineEdit, QLayout, QStyle,
)

from instruments.keithley2460 import KEITHLEY_DEFAULT_COMPLIANCE_A
from gui.custom_widgets import NoWheelComboBox, PlainIntField, PlainDoubleField
from gui.common_panels.substrate_panel import SubstratePanel
from gui.effects import make_panel_shadow, update_shadow_color

_SENSE_RANGES = ["AUTO", "1e-3", "100e-6", "10e-6", "1e-6", "100e-9"]


class DITConfigPanel(Atom):
    __slots__ = ('__weakref__',)

    is_dark_mode = Bool(False)

    run_requested = Event()
    layout_changed = Event()
    browse_requested = Event()
    name_changed = Event()
    autosave_table_toggled = Event()
    autosave_curves_toggled = Event()

    _widget = Typed(QWidget)

    # Voltage-step inputs
    _v1 = Typed(PlainDoubleField)
    _v2 = Typed(PlainDoubleField)
    _hold1 = Typed(PlainDoubleField)
    _hold2 = Typed(PlainDoubleField)
    _repetitions = Typed(PlainIntField)
    _recovery = Typed(PlainDoubleField)

    # Acquisition inputs
    _trigger_delay = Typed(PlainDoubleField)
    _integration = Typed(PlainDoubleField)
    _current_limit_ma = Typed(PlainDoubleField)
    _sense_range = Typed(NoWheelComboBox)
    _fudge = Typed(PlainDoubleField)
    _chunk_points = Typed(PlainIntField)
    _four_wire = Typed(QCheckBox)
    _autozero = Typed(QCheckBox)
    _log_plot = Typed(QCheckBox)

    _start_btn = Typed(QPushButton)
    _top_layout = Typed(QHBoxLayout)
    _sweep_panel = Typed(QFrame)
    _shadow_widgets = List()

    _substrate = Typed(SubstratePanel)

    # Dataset card
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

    # --- Voltage-step / acquisition panel ---

    def _build_sweep_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(0)

        title_lbl = QLabel("DIT PARAMETERS")
        title_lbl.setObjectName("PanelTitle")
        title_lbl.setStyleSheet("padding-bottom: 8px;")
        layout.addWidget(title_lbl)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        def make_group_title(text):
            lbl = QLabel(text)
            lbl.setObjectName("AccentLabel")
            lbl.setStyleSheet("padding-top: 12px; padding-bottom: 4px;")
            return lbl

        def make_field(label_text, widget):
            """Label-above-field block, for a 2-per-row grid -- far more
            vertically compact than one full-width row per field."""
            block = QWidget()
            block.setObjectName("FieldBlock")
            block_layout = QVBoxLayout(block)
            block_layout.setContentsMargins(0, 0, 0, 0)
            block_layout.setSpacing(3)
            lbl = QLabel(label_text)
            lbl.setObjectName("FieldLabel")
            block_layout.addWidget(lbl)
            block_layout.addWidget(widget)
            return block

        def make_grid():
            grid = QGridLayout()
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(10)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            return grid

        # --- Voltage step group ---
        self._v1 = PlainDoubleField()
        self._v1.setRange(-5, 5)
        self._v1.setDecimals(3)
        self._v1.setValue(0.0)

        self._v2 = PlainDoubleField()
        self._v2.setRange(-5, 5)
        self._v2.setDecimals(3)
        self._v2.setValue(0.8)

        self._hold1 = PlainDoubleField()
        self._hold1.setRange(0.001, 3600)
        self._hold1.setDecimals(3)
        self._hold1.setValue(0.05)

        self._hold2 = PlainDoubleField()
        self._hold2.setRange(0.001, 3600)
        self._hold2.setDecimals(3)
        self._hold2.setValue(0.05)

        self._repetitions = PlainIntField()
        self._repetitions.setRange(1, 100)
        self._repetitions.setValue(1)

        self._recovery = PlainDoubleField()
        self._recovery.setRange(0, 3600)
        self._recovery.setDecimals(2)
        self._recovery.setValue(1.0)

        layout.addWidget(make_group_title("VOLTAGE STEP"))
        voltage_grid = make_grid()
        voltage_grid.addWidget(make_field("V1 (V)", self._v1), 0, 0)
        voltage_grid.addWidget(make_field("V2 (V)", self._v2), 0, 1)
        voltage_grid.addWidget(make_field("Hold V1 (s)", self._hold1), 1, 0)
        voltage_grid.addWidget(make_field("Hold V2 (s)", self._hold2), 1, 1)
        voltage_grid.addWidget(make_field("Repetitions", self._repetitions), 2, 0)
        voltage_grid.addWidget(make_field("Recovery (s)", self._recovery), 2, 1)
        layout.addLayout(voltage_grid)

        # --- Acquisition group ---
        self._trigger_delay = PlainDoubleField()
        self._trigger_delay.setRange(0, 10000)
        self._trigger_delay.setDecimals(3)
        self._trigger_delay.setValue(1.0)

        self._integration = PlainDoubleField()
        self._integration.setRange(0.01, 10000)
        self._integration.setDecimals(3)
        self._integration.setValue(1.0)

        self._current_limit_ma = PlainDoubleField()
        self._current_limit_ma.setRange(0.001, 1000)
        self._current_limit_ma.setDecimals(0)
        self._current_limit_ma.setValue(KEITHLEY_DEFAULT_COMPLIANCE_A * 1000)

        self._sense_range = NoWheelComboBox()
        self._sense_range.addItems(_SENSE_RANGES)

        self._fudge = PlainDoubleField()
        self._fudge.setRange(0, 1000)
        self._fudge.setDecimals(3)
        self._fudge.setValue(0.01)

        self._chunk_points = PlainIntField()
        self._chunk_points.setRange(10, 5000)
        self._chunk_points.setValue(500)

        layout.addWidget(make_group_title("ACQUISITION"))
        acq_grid = make_grid()
        acq_grid.addWidget(make_field("Trigger Delay (ms)", self._trigger_delay), 0, 0)
        acq_grid.addWidget(make_field("Integration (ms)", self._integration), 0, 1)
        acq_grid.addWidget(make_field("Current Limit (mA)", self._current_limit_ma), 1, 0)
        acq_grid.addWidget(make_field("Sense Range", self._sense_range), 1, 1)
        acq_grid.addWidget(make_field("Delay Fudge (ms)", self._fudge), 2, 0)
        acq_grid.addWidget(make_field("Max Points/Chunk", self._chunk_points), 2, 1)
        layout.addLayout(acq_grid)

        self._four_wire = QCheckBox("4-wire (Kelvin) sensing")
        self._four_wire.setChecked(True)

        self._autozero = QCheckBox("Autozero")
        self._autozero.setChecked(False)

        self._log_plot = QCheckBox("Log-scale |I| plot")
        self._log_plot.setChecked(False)

        checkbox_grid = make_grid()
        checkbox_grid.setVerticalSpacing(8)
        checkbox_grid.addWidget(self._four_wire, 0, 0)
        checkbox_grid.addWidget(self._autozero, 0, 1)
        checkbox_grid.addWidget(self._log_plot, 1, 0)
        layout.addSpacing(12)
        layout.addLayout(checkbox_grid)

        layout.addStretch(1)

        self._start_btn = QPushButton("INITIALIZE DIT TRANSIENT")
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

        self._autosave_curves_checkbox = QCheckBox("Autosave individual transient traces")
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

    def validate(self):
        if self._v1.value() == self._v2.value():
            return "ERROR: V1 and V2 cannot be the same."
        if not self._substrate.has_active_pixel():
            return "ERROR: Please select at least one pixel."
        return None

    def get_dit_params(self):
        return {
            "v1": self._v1.value(),
            "v2": self._v2.value(),
            "hold1_s": self._hold1.value(),
            "hold2_s": self._hold2.value(),
            "trigger_delay_ms": self._trigger_delay.value(),
            "integration_ms": self._integration.value(),
            "current_limit_a": self._current_limit_ma.value() / 1000,
            "sense_range": self._sense_range.currentText(),
            "fudge_ms": self._fudge.value(),
            "chunk_points": self._chunk_points.value(),
            "four_wire": self._four_wire.isChecked(),
            "autozero": self._autozero.isChecked(),
            "repetitions": self._repetitions.value(),
            "recovery_s": self._recovery.value(),
        }

    def log_plot_enabled(self):
        return self._log_plot.isChecked()

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
