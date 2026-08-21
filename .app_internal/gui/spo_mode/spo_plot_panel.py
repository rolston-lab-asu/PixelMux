"""
SPO "SWEEP" tab: the live Power-vs-Time (or Voltage-vs-Time) plot plus a
live-metrics HUD sitting beside it.
"""
from atom.api import Atom, Bool, Callable, Dict, Event, List, Str, Typed
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton

from gui.plot_manager import PlotManager
from gui.custom_widgets import build_segmented_toggle, restyle_segmented_toggle
from gui.effects import make_panel_shadow, update_shadow_color
from gui.style import get_theme_colors, get_mode_accent

_POWER_Y_AXIS = ("Power Density", "mW/cm\u00b2", (0, 25))
_VOLTAGE_Y_AXIS = ("Voltage", "V", (0, 1.5))


class SPOPlotPanel(Atom):
    __slots__ = ('__weakref__',)

    is_dark_mode = Bool(False)

    abort_requested = Event()
    export_png_requested = Event()

    _widget = Typed(QWidget)
    plot_manager = Typed(PlotManager)
    _hud_active_pixel = Typed(QLabel)
    _hud_final_power = Typed(QLabel)
    _hud_mean_power = Typed(QLabel)
    _hud_abort = Typed(QPushButton)
    _shadow_widgets = List()
    _log = Callable(lambda message: None)

    # View toggle: which series the plot currently shows.
    _view_mode = Str("power")  # "power" or "voltage"
    _view_power_btn = Typed(QPushButton)
    _view_voltage_btn = Typed(QPushButton)
    _view_toggle_group = Typed(object)
    _view_toggle_pill = Typed(QFrame)

    # Cached per-curve data so toggling redraws instantly without re-running
    # the hold: {(channel, loop_number): {"t":[...], "v":[...], "p":[...]}}
    _series_cache = Dict()
    # {(channel, loop_number): PlotDataItem} -- updated in place via setData()
    # on toggle, rather than clearing/re-adding (which would also disturb
    # the pixel/loop legend).
    _curve_items = Dict()

    def get_widget(self):
        return self._widget

    def create_widget(self, parent):
        container = QWidget(parent)
        layout = QHBoxLayout(container)
        layout.setSpacing(15)
        layout.addWidget(self._build_plot_panel(), 3)
        layout.addWidget(self._build_live_hud(), 1)
        self._widget = container
        return container

    def _build_plot_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        y_label, y_units, y_range = _POWER_Y_AXIS
        self.plot_manager = PlotManager(
            range_dialog_callback=lambda: self.plot_manager.open_range_dialog(
                self.get_widget(), self._log
            ),
            x_label="Time", x_units="s",
            y_label=y_label, y_units=y_units,
            default_x_range=(0, 120), default_y_range=y_range,
        )
        layout.addWidget(self.plot_manager.widget, 1)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(8)

        reset_view_btn = QPushButton("Reset View")
        reset_view_btn.clicked.connect(self.plot_manager.apply_default_range)
        tools_row.addWidget(reset_view_btn)

        set_range_btn = QPushButton("Set Range...")
        set_range_btn.clicked.connect(
            lambda: self.plot_manager.open_range_dialog(self.get_widget(), self._log)
        )
        tools_row.addWidget(set_range_btn)

        export_png_btn = QPushButton("Export PNG")
        export_png_btn.clicked.connect(self._on_export_png_clicked)
        tools_row.addWidget(export_png_btn)

        tools_row.addStretch(1)
        layout.addLayout(tools_row)

        colors = get_theme_colors(self.is_dark_mode)
        plot = self.plot_manager.widget
        plot.setBackground(colors["bg_panel"])
        plot.getAxis("bottom").setPen(pg.mkPen(colors["border"]))
        plot.getAxis("left").setPen(pg.mkPen(colors["border"]))
        plot.getAxis("bottom").setTextPen(pg.mkPen(colors["text_dim"]))
        plot.getAxis("left").setTextPen(pg.mkPen(colors["text_dim"]))

        self._add_shadow(panel)
        return panel

    def _build_live_hud(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self._hud_active_pixel = QLabel("Latest Pixel: --")
        self._hud_active_pixel.setObjectName("HudActivePixel")
        layout.addWidget(self._hud_active_pixel)

        layout.addWidget(self._build_view_toggle_row())

        divider2 = QFrame()
        divider2.setObjectName("Divider")
        divider2.setFrameShape(QFrame.HLine)
        layout.addWidget(divider2)

        def make_metric(label_html):
            card = QFrame()
            card.setObjectName("MetricCard")
            card.setAttribute(Qt.WA_StyledBackground, True)
            card.setMinimumHeight(108)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 14, 16, 14)
            card_layout.setSpacing(6)
            card_layout.setAlignment(Qt.AlignHCenter)

            lbl_title = QLabel(label_html)
            lbl_title.setObjectName("MetricLabel")
            lbl_title.setAlignment(Qt.AlignHCenter)

            lbl_val = QLabel("--")
            lbl_val.setObjectName("MetricValue")
            lbl_val.setAlignment(Qt.AlignHCenter)

            card_layout.addWidget(lbl_title)
            card_layout.addWidget(lbl_val)
            layout.addWidget(card)
            return lbl_val

        self._hud_final_power = make_metric("FINAL POWER (mW/cm\u00b2)")
        self._hud_mean_power = make_metric("MEAN POWER (mW/cm\u00b2)")

        layout.addStretch()

        self._hud_abort = QPushButton("ABORT HOLD")
        self._hud_abort.setObjectName("DangerButton")
        self._hud_abort.setMinimumHeight(42)
        self._hud_abort.clicked.connect(self._on_abort_clicked)
        self._hud_abort.setEnabled(False)
        layout.addWidget(self._hud_abort)

        self._add_shadow(panel)
        return panel

    def _build_view_toggle_row(self):
        row = QFrame()
        row.setObjectName("FormRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 4, 0, 4)

        lbl = QLabel("View")
        lbl.setObjectName("DimLabel")
        row_layout.addWidget(lbl)
        row_layout.addStretch(1)

        colors = get_theme_colors(self.is_dark_mode)
        accent = get_mode_accent(colors, "spo")
        checked_index = 0 if self._view_mode == "power" else 1
        pill, (self._view_power_btn, self._view_voltage_btn), self._view_toggle_group = (
            build_segmented_toggle(["P(t)", "V(t)"], colors, accent, checked_index=checked_index)
        )
        self._view_toggle_group.buttonClicked.connect(self._on_view_toggled)
        self._view_toggle_pill = pill

        row_layout.addWidget(pill)
        return row

    def _on_view_toggled(self, _button):
        mode = "power" if self._view_power_btn.isChecked() else "voltage"
        self.set_view_mode(mode)

    def _add_shadow(self, widget):
        effect = make_panel_shadow(widget, self.is_dark_mode)
        self._shadow_widgets = self._shadow_widgets + [effect]

    def _on_abort_clicked(self):
        self.abort_requested = True

    def _on_export_png_clicked(self):
        self.export_png_requested = True

    # --- Public API for the controller ---

    def set_logger(self, log_fn):
        self._log = log_fn

    def reset_for_new_run(self):
        self.plot_manager.clear_curves()
        self.plot_manager.clear_legends()
        y_label, y_units, y_range = _POWER_Y_AXIS if self._view_mode == "power" else _VOLTAGE_Y_AXIS
        self.plot_manager.set_y_axis(y_label, y_units, y_range)
        self._hud_active_pixel.setText("Latest Pixel: --")
        for lbl in (self._hud_final_power, self._hud_mean_power):
            lbl.setText("--")
        self._series_cache = {}
        self._curve_items = {}

    def prepare_legends(self, selected_pixels, loop_count):
        self.plot_manager.reset_legends(selected_pixels, loop_count)

    def plot_curve(self, t, voltage, power_density, channel, loop_number):
        """Caches both series for this (channel, loop) and plots whichever
        one is currently selected by the P(t)/V(t) toggle."""
        key = (channel, loop_number)
        self._series_cache = {**self._series_cache, key: {
            "t": list(t), "v": list(voltage), "p": list(power_density),
        }}
        y = power_density if self._view_mode == "power" else voltage
        item = self.plot_manager.plot_curve(t, y, channel, loop_number)
        self._curve_items = {**self._curve_items, key: item}

    def set_view_mode(self, mode):
        """Switches the plotted series (power density vs. voltage) for every
        curve already drawn this run, in place."""
        if mode not in ("power", "voltage"):
            return
        self._view_mode = mode

        y_label, y_units, y_range = _POWER_Y_AXIS if mode == "power" else _VOLTAGE_Y_AXIS
        self.plot_manager.set_y_axis(y_label, y_units, y_range)

        for key, item in self._curve_items.items():
            series = self._series_cache.get(key)
            if series is None:
                continue
            y = series["p"] if mode == "power" else series["v"]
            item.setData(series["t"], y)

    def set_active_pixel(self, pixel):
        self._hud_active_pixel.setText(f"Latest Pixel: {pixel}")

    def set_hud_metrics(self, final_power_text, mean_power_text):
        self._hud_final_power.setText(final_power_text)
        self._hud_mean_power.setText(mean_power_text)

    def set_running(self, running):
        self._hud_abort.setEnabled(running)

    def apply_theme(self, colors, is_dark_mode):
        self.is_dark_mode = is_dark_mode
        for effect in self._shadow_widgets:
            update_shadow_color(effect, is_dark_mode)
        plot = self.plot_manager.widget
        plot.setBackground(colors["bg_panel"])
        plot.getAxis("bottom").setPen(pg.mkPen(colors["border"]))
        plot.getAxis("left").setPen(pg.mkPen(colors["border"]))
        plot.getAxis("bottom").setTextPen(pg.mkPen(colors["text_dim"]))
        plot.getAxis("left").setTextPen(pg.mkPen(colors["text_dim"]))
        accent = get_mode_accent(colors, "spo")
        restyle_segmented_toggle(self._view_toggle_pill, colors, accent)
