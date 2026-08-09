"""
Top header bar: brand title, Keithley/Relay status LEDs, connect button,
and the theme toggle.

Plain Atom object + imperative PySide6 layout, not Enaml given uncomptability.
Instead, simply focus on atom stuff.

Qt-facing signals (connect_clicked/theme_toggled) are plain Atom Events;
controllers use `.observe(...)`.
"""
from atom.api import Atom, Bool, Event, Typed
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

from gui.effects import refresh_led_glow, set_status_led


class HeaderPanel(Atom):
    __slots__ = ('__weakref__',)

    is_dark_mode = Bool(False)
    _in_workspace = Bool(False)

    connect_clicked = Event()
    theme_toggled = Event()
    home_clicked = Event()

    _widget = Typed(QWidget)
    _brand_title = Typed(QLabel)
    _keithley_led = Typed(QLabel)
    _keithley_lbl = Typed(QLabel)
    _relay_led = Typed(QLabel)
    _relay_lbl = Typed(QLabel)
    _connect_btn = Typed(QPushButton)
    _theme_btn = Typed(QPushButton)

    def get_widget(self):
        return self._widget

    def create_widget(self, parent):
        container = QWidget(parent)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(10)

        self._brand_title = QLabel("MULTIPLEX SIM")
        self._brand_title.setObjectName("BrandTitle")
        layout.addWidget(self._brand_title, 0, Qt.AlignVCenter)

        self._keithley_led = QLabel("")
        self._keithley_led.setObjectName("StatusLED")
        self._keithley_led.setAttribute(Qt.WA_StyledBackground, True)
        layout.addWidget(self._keithley_led, 0, Qt.AlignVCenter)

        self._keithley_lbl = QLabel("KEITHLEY\n2460")
        self._keithley_lbl.setObjectName("StatusLabel")
        layout.addWidget(self._keithley_lbl, 0, Qt.AlignVCenter)

        self._relay_led = QLabel("")
        self._relay_led.setObjectName("StatusLED")
        self._relay_led.setAttribute(Qt.WA_StyledBackground, True)
        layout.addWidget(self._relay_led, 0, Qt.AlignVCenter)

        self._relay_lbl = QLabel("RELAY\nMATRIX")
        self._relay_lbl.setObjectName("StatusLabel")
        layout.addWidget(self._relay_lbl, 0, Qt.AlignVCenter)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._on_connect_clicked)
        layout.addWidget(self._connect_btn, 0, Qt.AlignVCenter)

        layout.addStretch(1)

        self._theme_btn = QPushButton()
        self._theme_btn.setObjectName("ThemeButton")
        self._theme_btn.clicked.connect(self._on_action_btn_clicked)
        layout.addWidget(self._theme_btn, 0, Qt.AlignVCenter)
        self._refresh_action_btn()

        set_status_led(self._keithley_led, self._keithley_lbl, "idle")
        set_status_led(self._relay_led, self._relay_lbl, "idle")

        self._widget = container
        return container

    def _on_connect_clicked(self):
        self.connect_clicked = True

    def _on_action_btn_clicked(self):
        # One button, two identities: home glyph + `home_clicked` while a
        # workspace is open, theme glyph + `theme_toggled` on the Home screen.
        if self._in_workspace:
            self.home_clicked = True
        else:
            self.theme_toggled = True

    def _refresh_action_btn(self):
        if self._in_workspace:
            self._theme_btn.setText("\U0001F3E0")  # house
        else:
            self._theme_btn.setText("\u2600\ufe0f" if self.is_dark_mode else "\U0001F319")

    @staticmethod
    def _repolish(widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    # --- Public API (unchanged names/signatures from the old QFrame/enaml versions) ---

    def set_workspace_mode(self, in_workspace):
        """Switches the action button between theme-toggle (Home) and
        back-to-home (Workspace) identities."""
        self._in_workspace = in_workspace
        self._refresh_action_btn()

    def set_connection_status(self, keithley_ok, relay_ok, colors):
        set_status_led(self._keithley_led, self._keithley_lbl, "ok" if keithley_ok else "bad")
        set_status_led(self._relay_led, self._relay_lbl, "ok" if relay_ok else "bad")
        refresh_led_glow(self._keithley_led, colors)
        refresh_led_glow(self._relay_led, colors)
        self._connect_btn.setText("Reconnect")

    def set_running(self, running):
        self._connect_btn.setEnabled(not running)

    def flash_home_alert(self):
        """Brief red blink on the home/theme button -- used when the user
        tries to leave a mode while it has an active sweep running."""
        self._set_flashing(True)
        QTimer.singleShot(180, lambda: self._set_flashing(False))
        QTimer.singleShot(360, lambda: self._set_flashing(True))
        QTimer.singleShot(540, lambda: self._set_flashing(False))

    def _set_flashing(self, on):
        self._theme_btn.setProperty("flashing", "true" if on else "false")
        self._repolish(self._theme_btn)

    def apply_theme(self, colors, is_dark_mode):
        self.is_dark_mode = is_dark_mode
        self._refresh_action_btn()
        refresh_led_glow(self._keithley_led, colors)
        refresh_led_glow(self._relay_led, colors)
