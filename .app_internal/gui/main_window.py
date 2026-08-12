"""
Builds the header, the mode tabs, the log panel, and the footer progress strip. then hands them off to the
controllers to process respective button presses.
"""
import os

import pyqtgraph as pg
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget

from core.instrument_manager import InstrumentManager
from core.exporter import ResultsExporter
from core.paths import get_data_dir

from controllers.main_controller import MainController
from controllers.jv_controller import JVController
from controllers.spo_controller import SPOController
from controllers.dit_controller import DITController

from gui.style import get_theme, get_theme_colors

from gui.common_panels.header_panel import HeaderPanel
from gui.common_panels.home_panel import HomePanel

from gui.jv_mode.jv_main_view import JVMainView, SWEEP_TAB_INDEX as JV_SWEEP_TAB_INDEX
from gui.spo_mode.spo_main_view import SPOMainView, SWEEP_TAB_INDEX as SPO_SWEEP_TAB_INDEX
from gui.dit_mode.dit_main_view import DITMainView, SWEEP_TAB_INDEX as DIT_SWEEP_TAB_INDEX

HOME_PAGE_INDEX = 0


class MainWindow(QWidget):
    def __init__(self, mock=False):
        super().__init__()

        self.is_dark_mode = False
        self._shadow_widgets = []
        self._theme_aware_panels = []  # anything with an apply_theme(colors, is_dark_mode) method
        self._active_mode_count = 0  # how many modes (JV/SPO/DIT) currently have a sweep running
        self.mock = mock

        self.setWindowTitle("Multiplex Solar Simulator")
        self.resize(1440, 900)
        self.setMinimumSize(680, 560)
        self.setObjectName("Root")

        self.output_dir = get_data_dir()
        self.instrument_manager = InstrumentManager(mock=mock)

        self.apply_style()
        self._build_ui()
        self._wire_controllers()

    def apply_style(self):
        self.setFont(QFont("Segoe UI", 10))
        self.setStyleSheet(get_theme(self.is_dark_mode))

    # --- Layout assembly ---

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(14, 14, 14, 14)
        main.setSpacing(10)

        self.header_panel = HeaderPanel(is_dark_mode=self.is_dark_mode)
        self._register_theme_aware(self.header_panel)
        self.header_panel.observe("theme_toggled", self._on_theme_toggled)
        self.header_panel.observe("home_clicked", self._on_home_clicked)
        main.addWidget(self.header_panel.create_widget(self))

        self.stack = QStackedWidget()
        main.addWidget(self.stack, 1)

        self.home_panel = HomePanel(is_dark_mode=self.is_dark_mode)
        self._register_theme_aware(self.home_panel)
        self.home_panel.observe("module_selected", self._on_module_selected)
        self.stack.addWidget(self.home_panel.create_widget(self.stack))  # HOME_PAGE_INDEX

        self._mode_pages = {}  # module_id -> stack index, for _on_module_selected

        self.jv_view = JVMainView(is_dark_mode=self.is_dark_mode, output_dir=self.output_dir)
        self._register_theme_aware(self.jv_view)
        self._mode_pages["jv"] = self.stack.addWidget(self.jv_view.create_widget(self.stack))

        self.spo_view = SPOMainView(is_dark_mode=self.is_dark_mode, output_dir=self.output_dir)
        self._register_theme_aware(self.spo_view)
        self._mode_pages["spo"] = self.stack.addWidget(self.spo_view.create_widget(self.stack))

        self.dit_view = DITMainView(is_dark_mode=self.is_dark_mode, output_dir=self.output_dir)
        self._register_theme_aware(self.dit_view)
        self._mode_pages["dit"] = self.stack.addWidget(self.dit_view.create_widget(self.stack))

        self.stack.setCurrentIndex(HOME_PAGE_INDEX)

    def _register_theme_aware(self, panel):
        self._theme_aware_panels.append(panel)

    # --- Controller wiring ---

    def _wire_controllers(self):
        self.exporter = ResultsExporter(self.output_dir, "Sample", self.jv_view.log_panel.log_message)

        self.main_controller = MainController(
            instrument_manager=self.instrument_manager,
            header_panel=self.header_panel,
            log_panel=self.jv_view.log_panel,
            get_colors=lambda: get_theme_colors(self.is_dark_mode),
            parent_widget=self,
        )
        self.main_controller.register_log_panel(self.spo_view.log_panel)
        self.main_controller.register_log_panel(self.dit_view.log_panel)

        self.jv_controller = JVController(
            instrument_manager=self.instrument_manager,
            exporter=self.exporter,
            config_panel=self.jv_view.config_panel,
            plot_panel=self.jv_view.plot_panel,
            results_panel=self.jv_view.results_panel,
            log_fn=self.jv_view.log_panel.log_message,
            get_sample_name=self.jv_view.config_panel.sample_name,
            tabs=self.jv_view.tabs,
            sweep_tab_index=JV_SWEEP_TAB_INDEX,
            parent_widget=self,
            is_other_mode_running=self.is_any_mode_running,
        )
        self.main_controller.register_mode_controller(self.jv_controller)
        self._wire_mode_state(self.jv_view, self.jv_controller)

        # Browse is on the dataset card.
        self.jv_view.config_panel.observe(
            "browse_requested", lambda change: self.main_controller.choose_output_dir()
        )

        self.spo_controller = SPOController(
            instrument_manager=self.instrument_manager,
            exporter=self.exporter,
            config_panel=self.spo_view.config_panel,
            plot_panel=self.spo_view.plot_panel,
            results_panel=self.spo_view.results_panel,
            log_fn=self.spo_view.log_panel.log_message,
            get_sample_name=self.spo_view.config_panel.sample_name,
            tabs=self.spo_view.tabs,
            sweep_tab_index=SPO_SWEEP_TAB_INDEX,
            parent_widget=self,
            is_other_mode_running=self.is_any_mode_running,
        )
        self.main_controller.register_mode_controller(self.spo_controller)
        self._wire_mode_state(self.spo_view, self.spo_controller)

        self.spo_view.config_panel.observe(
            "browse_requested", lambda change: self.main_controller.choose_output_dir()
        )

        self.dit_controller = DITController(
            instrument_manager=self.instrument_manager,
            exporter=self.exporter,
            config_panel=self.dit_view.config_panel,
            plot_panel=self.dit_view.plot_panel,
            results_panel=self.dit_view.results_panel,
            log_fn=self.dit_view.log_panel.log_message,
            get_sample_name=self.dit_view.config_panel.sample_name,
            tabs=self.dit_view.tabs,
            sweep_tab_index=DIT_SWEEP_TAB_INDEX,
            parent_widget=self,
            is_other_mode_running=self.is_any_mode_running,
        )
        self.main_controller.register_mode_controller(self.dit_controller)
        self._wire_mode_state(self.dit_view, self.dit_controller)

        self.dit_view.config_panel.observe(
            "browse_requested", lambda change: self.main_controller.choose_output_dir()
        )

    def _wire_mode_state(self, view, controller):
        """Cross-panel running state (start/abort/connect/browse all need
        to agree on whether a hold/sweep is in flight) -- bound to this
        specific mode's own view/controller pair, so JV and SPO (&
        future modes) each drive only their own footer/HUD."""
        controller.state.observe(
            "running", lambda change, v=view: self._on_running_changed(change, v)
        )
        controller.state.observe(
            "progress_percent", lambda change, v=view, c=controller: self._on_progress_update(v, c)
        )
        controller.state.observe(
            "progress_text", lambda change, v=view, c=controller: self._on_progress_update(v, c)
        )

    # --- Cross-cutting state broadcasts ---

    def _on_running_changed(self, change, view):
        running = change["value"]
        self._active_mode_count = max(0, self._active_mode_count + (1 if running else -1))
        any_running = self._active_mode_count > 0
        self.header_panel.set_running(any_running)
        view.set_running(running)

    def is_any_mode_running(self):
        """Shared hardware guard: JV/SPO/DIT all drive the same physical
        Keithley/relay through InstrumentManager, so only one mode may run
        a measurement at a time."""
        return self._active_mode_count > 0

    def _on_progress_update(self, view, controller):
        view.set_progress(controller.state.progress_percent, controller.state.progress_text)

    def _on_theme_toggled(self, change):
        self.toggle_theme()

    def _on_module_selected(self, change):
        page_index = self._mode_pages.get(change["value"])
        if page_index is None:
            return
        self.stack.setCurrentIndex(page_index)
        self.header_panel.set_workspace_mode(True)

    def _on_home_clicked(self, change):
        if self.is_any_mode_running():
            self.header_panel.flash_home_alert()
            return
        self.stack.setCurrentIndex(HOME_PAGE_INDEX)
        self.header_panel.set_workspace_mode(False)

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_style()

        colors = get_theme_colors(self.is_dark_mode)
        for panel in self._theme_aware_panels:
            panel.apply_theme(colors, self.is_dark_mode)
