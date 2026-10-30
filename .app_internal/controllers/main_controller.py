"""Connects the instruments and applies the chosen output folder to every mode."""
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QFileDialog


class MainController(QObject):
    def __init__(self, instrument_manager, header_panel, log_panel, get_colors, parent_widget, parent=None):
        super().__init__(parent)
        self.inst = instrument_manager
        self.header = header_panel
        self.log_panel = log_panel
        self.log_panels = [log_panel]
        self.get_colors = get_colors
        self.parent_widget = parent_widget

        self.output_dir = log_panel.output_dir
        self._mode_controllers = []

        self.header.observe("connect_clicked", self._on_connect_clicked)

    def register_mode_controller(self, controller):
        self._mode_controllers.append(controller)

    def register_log_panel(self, log_panel):
        self.log_panels.append(log_panel)

    def _log_all(self, message):
        for panel in self.log_panels:
            panel.log_message(message)

    def _on_connect_clicked(self, change):
        self.connect_instruments()

    def connect_instruments(self):
        self._log_all("Connecting instruments...")
        keithley_ok, relay_ok = self.inst.connect_all(self._log_all)
        self.header.set_connection_status(keithley_ok, relay_ok, self.get_colors())

    def choose_output_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self.parent_widget,
            "Choose TXT Save Folder",
            self.output_dir,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if directory:
            self.output_dir = directory
            for panel in self.log_panels:
                panel.set_output_dir(directory)
            for controller in self._mode_controllers:
                controller.set_output_dir(directory)
            self._log_all(f"TXT save folder set to {directory}")
