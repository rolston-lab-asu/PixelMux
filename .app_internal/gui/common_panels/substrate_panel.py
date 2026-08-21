"""
Substrate diagram + pixel-selection widget: the interactive glass-slide
pad/trace diagram, its mode selector (6/12/Custom), and the properties
inspector bar (global default area, or a selected pin's own area override).
"""
import functools

from atom.api import Atom, Bool, Event, Typed, Value
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QCheckBox, QPushButton,
)

from core.pixel_map import PIXEL_TO_RELAY_CHANNEL, active_pixel_labels, default_pixel_area, pixel_uses_relay
from gui.custom_widgets import NoWheelComboBox, PlainDoubleField
from gui.effects import set_glow
from gui.style import get_theme_colors

_GLASS_W, _GLASS_H = 110, 190
_TRACE_W, _TRACE_H = 35, 2
_PAD_W, _PAD_H = 10, 6


class SubstratePanel(Atom):
    __slots__ = ('__weakref__',)

    is_dark_mode = Bool(False)

    layout_changed = Event()

    _widget = Typed(QWidget)

    _pixel_mode = Typed(NoWheelComboBox)
    _left_pads_layout = Typed(QVBoxLayout)
    _right_pads_layout = Typed(QVBoxLayout)
    _glass_slide_widget = Typed(QFrame)
    _pad_buttons = Value()        # {pin: QPushButton}
    _trace_widgets = Value()      # {pin: QFrame}
    _pixel_pad_widgets = Value()  # {pin: QFrame}

    _pin_active = Value()      # {pin: bool}
    _pin_areas = Value()       # {pin: float}
    _pin_overrides = Value()   # {pin: bool}
    _default_area = Value(0.0396)
    _selected_pin = Value(None)

    # Properties inspector bar
    _inspector_title_lbl = Typed(QLabel)
    _inspector_action_layout = Typed(QHBoxLayout)
    _inspector_main_layout = Typed(QHBoxLayout)

    def get_widget(self):
        return self._widget

    def create_widget(self, parent):
        self._pad_buttons = {}
        self._trace_widgets = {}
        self._pixel_pad_widgets = {}
        self._pin_active = {}
        self._pin_areas = {}
        self._pin_overrides = {}

        container = QWidget(parent)
        container.setObjectName("SubstrateRoot")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        title_lbl = QLabel("SUBSTRATE")
        title_lbl.setObjectName("PanelTitle")
        header_row.addWidget(title_lbl, 1)

        self._pixel_mode = NoWheelComboBox()
        self._pixel_mode.setMinimumWidth(110)
        self._pixel_mode.addItems(["6 Pixels", "12 Pixels", "Custom"])
        self._pixel_mode.currentIndexChanged.connect(self._on_mode_changed)
        header_row.addWidget(self._pixel_mode)
        layout.addLayout(header_row)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        hybrid_container = QVBoxLayout()
        hybrid_container.setSpacing(15)
        hybrid_container.setAlignment(Qt.AlignHCenter)

        glass_row = QHBoxLayout()
        glass_row.setSpacing(10)
        glass_row.setAlignment(Qt.AlignHCenter)

        self._left_pads_layout = QVBoxLayout()
        self._left_pads_layout.setSpacing(6)
        left_wrap = QWidget()
        left_wrap.setObjectName("PadColumn")
        left_wrap.setAttribute(Qt.WA_StyledBackground, True)
        left_wrap.setLayout(self._left_pads_layout)
        glass_row.addWidget(left_wrap)

        self._glass_slide_widget = QFrame()
        self._glass_slide_widget.setObjectName("GlassSlide")
        self._glass_slide_widget.setAttribute(Qt.WA_StyledBackground, True)
        self._glass_slide_widget.setFixedSize(_GLASS_W, _GLASS_H)
        glass_row.addWidget(self._glass_slide_widget)

        self._right_pads_layout = QVBoxLayout()
        self._right_pads_layout.setSpacing(6)
        right_wrap = QWidget()
        right_wrap.setObjectName("PadColumn")
        right_wrap.setAttribute(Qt.WA_StyledBackground, True)
        right_wrap.setLayout(self._right_pads_layout)
        glass_row.addWidget(right_wrap)

        hybrid_container.addLayout(glass_row)
        hybrid_container.addWidget(self._build_inspector_bar())
        layout.addLayout(hybrid_container)

        self._render_layout()

        self._widget = container
        return container

    def _build_inspector_bar(self):
        bar = QFrame()
        bar.setObjectName("InspectorBar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        outer = QVBoxLayout(bar)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(6)

        top_row = QHBoxLayout()
        self._inspector_title_lbl = QLabel("GLOBAL BATCH DEFAULT")
        self._inspector_title_lbl.setObjectName("InspectorTitle")
        top_row.addWidget(self._inspector_title_lbl)
        top_row.addStretch(1)
        self._inspector_action_layout = QHBoxLayout()
        top_row.addLayout(self._inspector_action_layout)
        outer.addLayout(top_row)

        self._inspector_main_layout = QHBoxLayout()
        outer.addLayout(self._inspector_main_layout)

        return bar

    def _on_mode_changed(self):
        self._selected_pin = None
        self._render_layout()

    def _current_pin_lists(self):
        """Returns (left_pins, right_pins) for the current mode. Custom
        mode is a single directly-wired pixel (no relay) -- shown as one
        pad in the left column, right column empty."""
        mode = self._pixel_mode.currentText()
        labels = active_pixel_labels(mode)
        if mode == "Custom":
            return labels, []
        return labels[0::2], labels[1::2]

    def _render_layout(self):
        """Rebuilds pad buttons + glass-slide trace/marker widgets from
        scratch for the current mode. Mirrors the mockup's renderLayout()."""
        self._clear_layout(self._left_pads_layout)
        self._clear_layout(self._right_pads_layout)
        for child in list(self._glass_slide_widget.children()):
            if isinstance(child, QWidget):
                child.deleteLater()

        left_pins, right_pins = self._current_pin_lists()
        self._default_area = default_pixel_area(self._pixel_mode.currentText())

        # Mode switch resets every visible pin to a fresh state at the new
        # mode's real default area.
        for pin in left_pins + right_pins:
            self._pin_active[pin] = True
            self._pin_areas[pin] = self._default_area
            self._pin_overrides[pin] = False

        self._pad_buttons = {}
        self._trace_widgets = {}
        self._pixel_pad_widgets = {}

        for pin in left_pins:
            self._left_pads_layout.addWidget(self._create_pad_btn(pin))
        for pin in right_pins:
            self._right_pads_layout.addWidget(self._create_pad_btn(pin))

        for i, pin in enumerate(left_pins):
            self._add_visual_elements(pin, i, len(left_pins), is_left=True)
        for i, pin in enumerate(right_pins):
            self._add_visual_elements(pin, i, len(right_pins), is_left=False)

        self._update_inspector()
        self.layout_changed = True

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _create_pad_btn(self, pin):
        btn = QPushButton(pin)
        btn.setObjectName("PadBtn")
        btn.setFixedSize(38, 24)
        btn.setProperty("state", "active" if self._pin_active.get(pin) else "inactive")
        self._repolish(btn)
        btn.clicked.connect(functools.partial(self._select_pin, pin))
        self._pad_buttons[pin] = btn
        return btn

    def _add_visual_elements(self, pin, index, total, is_left):
        step = _GLASS_H / (total + 1)
        top_y = int((index + 1) * step)
        is_active = self._pin_active.get(pin)
        accent = get_theme_colors(self.is_dark_mode)["accent"]

        trace = QFrame(self._glass_slide_widget)
        trace.setObjectName("Trace")
        trace.setProperty("state", "active" if is_active else "inactive")
        trace.setGeometry(0 if is_left else _GLASS_W - _TRACE_W, top_y, _TRACE_W, _TRACE_H)
        self._repolish(trace)
        set_glow(trace, accent, is_active, blur_radius=6)
        trace.show()
        self._trace_widgets[pin] = trace

        pad = QFrame(self._glass_slide_widget)
        pad.setObjectName("PixelPad")
        pad.setProperty("state", "active" if is_active else "inactive")
        pad.setGeometry(
            _TRACE_W if is_left else _GLASS_W - _TRACE_W - _PAD_W,
            top_y - _PAD_H // 2, _PAD_W, _PAD_H,
        )
        self._repolish(pad)
        set_glow(pad, accent, is_active, blur_radius=8)
        pad.show()
        self._pixel_pad_widgets[pin] = pad

    def _select_pin(self, pin):
        if self._selected_pin == pin:
            return
        self._selected_pin = pin
        for p, btn in self._pad_buttons.items():
            btn.setProperty("state", "selected" if p == pin else ("active" if self._pin_active.get(p) else "inactive"))
            self._repolish(btn)
        self._update_inspector()
        self.layout_changed = True

    def _deselect_pin(self):
        self._selected_pin = None
        for p, btn in self._pad_buttons.items():
            btn.setProperty("state", "active" if self._pin_active.get(p) else "inactive")
            self._repolish(btn)
        self._update_inspector()
        self.layout_changed = True

    @staticmethod
    def _repolish(widget):
        # setProperty() alone doesn't retroactively re-resolve an
        # attribute-selector QSS rule for an already-polished widget.
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _update_inspector(self):
        self._clear_layout(self._inspector_action_layout)
        self._clear_layout(self._inspector_main_layout)

        if self._selected_pin is None:
            self._inspector_title_lbl.setText("GLOBAL BATCH DEFAULT")

            hint = QLabel("Click a pin above to inspect.")
            hint.setObjectName("DimLabel")
            hint.setStyleSheet("font-size: 7.5pt;")
            self._inspector_action_layout.addWidget(hint)

            lbl = QLabel("Batch Area:")
            lbl.setObjectName("DimLabel")
            self._inspector_main_layout.addWidget(lbl)
            self._inspector_main_layout.addStretch(1)

            area_input = PlainDoubleField()
            area_input.setRange(0.0001, 100)
            area_input.setDecimals(4)
            area_input.setValue(self._default_area)
            area_input.setFixedWidth(90)
            area_input.valueChanged.connect(self._on_area_input_changed)
            self._inspector_main_layout.addWidget(area_input)

            unit_lbl = QLabel("cm\u00b2")
            unit_lbl.setObjectName("DimLabel")
            self._inspector_main_layout.addWidget(unit_lbl)
        else:
            pin = self._selected_pin
            self._inspector_title_lbl.setText(f"PIN {pin} PROPERTIES")

            close_btn = QPushButton("\u2715")
            close_btn.setObjectName("CloseInspectorBtn")
            close_btn.setToolTip("Return to global settings")
            close_btn.clicked.connect(self._deselect_pin)
            self._inspector_action_layout.addWidget(close_btn)

            active_check = QCheckBox("Active")
            active_check.setChecked(bool(self._pin_active.get(pin)))
            active_check.toggled.connect(functools.partial(self._toggle_pin_active, pin))
            self._inspector_main_layout.addWidget(active_check)
            self._inspector_main_layout.addStretch(1)

            override_check = QCheckBox("Override")
            override_check.setChecked(bool(self._pin_overrides.get(pin)))
            override_check.toggled.connect(functools.partial(self._toggle_override, pin))
            self._inspector_main_layout.addWidget(override_check)

            is_override = bool(self._pin_overrides.get(pin))
            area_input = PlainDoubleField()
            area_input.setRange(0.0001, 100)
            area_input.setDecimals(4)
            area_input.setValue(self._pin_areas.get(pin, self._default_area) if is_override else self._default_area)
            area_input.setEnabled(is_override)
            area_input.setFixedWidth(90)
            area_input.valueChanged.connect(self._on_area_input_changed)
            self._inspector_main_layout.addWidget(area_input)

            unit_lbl = QLabel("cm\u00b2")
            unit_lbl.setObjectName("DimLabel")
            self._inspector_main_layout.addWidget(unit_lbl)

    def _toggle_pin_active(self, pin, checked):
        self._pin_active[pin] = checked

        btn = self._pad_buttons.get(pin)
        if btn is not None:
            btn.setProperty("state", "selected" if self._selected_pin == pin else ("active" if checked else "inactive"))
            self._repolish(btn)

        for widgets in (self._trace_widgets, self._pixel_pad_widgets):
            w = widgets.get(pin)
            if w is not None:
                w.setProperty("state", "active" if checked else "inactive")
                self._repolish(w)
                accent = get_theme_colors(self.is_dark_mode)["accent"]
                set_glow(w, accent, checked, blur_radius=6 if widgets is self._trace_widgets else 8)

        self.layout_changed = True

    def _toggle_override(self, pin, checked):
        self._pin_overrides[pin] = checked
        if not checked:
            self._pin_areas[pin] = self._default_area
        self._update_inspector()
        self.layout_changed = True

    def _on_area_input_changed(self, value):
        if self._selected_pin is None:
            self._default_area = value
            for pin, overridden in self._pin_overrides.items():
                if not overridden:
                    self._pin_areas[pin] = value
        else:
            if self._pin_overrides.get(self._selected_pin):
                self._pin_areas[self._selected_pin] = value
        self.layout_changed = True

    # --- Public API for a mode's config panel ---

    def has_active_pixel(self):
        return any(self._pin_active.values())

    def get_selected_pixels(self):
        use_relay = pixel_uses_relay(self._pixel_mode.currentText())
        ordered_pins = active_pixel_labels(self._pixel_mode.currentText())
        selected = []
        for pin in ordered_pins:
            if self._pin_active.get(pin):
                channel = PIXEL_TO_RELAY_CHANNEL[pin] if use_relay else None
                selected.append((pin, channel, self._pin_areas.get(pin, self._default_area)))
        return selected

    def apply_theme(self, colors, is_dark_mode):
        self.is_dark_mode = is_dark_mode
        # Static QSS (style.py)| theme change is handled by the global
        # stylesheet cascade, yet explict repolish per defense.
        for widgets in (self._pad_buttons, self._trace_widgets, self._pixel_pad_widgets):
            for w in widgets.values():
                self._repolish(w)
        accent = colors["accent"]
        for pin, trace in self._trace_widgets.items():
            set_glow(trace, accent, bool(self._pin_active.get(pin)), blur_radius=6)
        for pin, pad in self._pixel_pad_widgets.items():
            set_glow(pad, accent, bool(self._pin_active.get(pin)), blur_radius=8)
