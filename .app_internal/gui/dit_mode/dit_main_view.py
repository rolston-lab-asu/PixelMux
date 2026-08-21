"""
DIT mode container: builds the CONFIG/SWEEP/RESULTS/LOGS tab strip and the
transient-progress footer, and owns the 4 DIT panels + tabs as attributes
so MainWindow (and DITController) can wire into them w/o knowing how
the DIT workspace is assembled internally.
"""
from atom.api import Atom, Bool, List, Str, Typed, Value
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QProgressBar, QScrollArea

from gui.custom_widgets import SafeTabBar, SizeAwareTabWidget
from gui.effects import make_panel_shadow, update_shadow_color, animate_tab_switch
from gui.common_panels.log_panel import LogPanel
from gui.dit_mode.dit_config_panel import DITConfigPanel
from gui.dit_mode.dit_plot_panel import DITPlotPanel
from gui.dit_mode.dit_results_panel import DITResultsPanel
from gui.style import get_mode_accent

CONFIG_TAB_INDEX = 0
SWEEP_TAB_INDEX = 1
RESULTS_TAB_INDEX = 2
LOGS_TAB_INDEX = 3


class DITMainView(Atom):
    __slots__ = ('__weakref__',)

    is_dark_mode = Bool(False)
    output_dir = Str()

    theme_aware_panels = List()  # populated during create_widget()

    _widget = Typed(QWidget)
    tabs = Typed(SizeAwareTabWidget)
    scroll = Typed(QScrollArea)
    footer = Typed(QFrame)
    progress_bar = Typed(QProgressBar)
    progress_pct = Typed(QLabel)
    progress_txt = Typed(QLabel)
    _footer_shadow = Value()
    _footer_title_lbl = Typed(QLabel)

    config_panel = Typed(DITConfigPanel)
    plot_panel = Typed(DITPlotPanel)
    results_panel = Typed(DITResultsPanel)
    log_panel = Typed(LogPanel)

    def get_widget(self):
        return self._widget

    def create_widget(self, parent):
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.tabs = SizeAwareTabWidget()
        self.tabs.setObjectName("DITTabs")
        self.tabs.setTabBar(SafeTabBar(self.tabs))
        self.tabs.tabBar().setElideMode(Qt.ElideNone)
        self.tabs.tabBar().setExpanding(False)

        self.scroll = scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.tabs)
        layout.addWidget(scroll, 1)

        # TAB 1: CONFIG
        self.config_panel = DITConfigPanel(is_dark_mode=self.is_dark_mode)
        self.theme_aware_panels.append(self.config_panel)
        self.tabs.addTab(self.config_panel.create_widget(self.tabs), "1. CONFIG")
        self.config_panel.observe("layout_changed", self._on_config_layout_changed)

        # TAB 2: SWEEP
        self.plot_panel = DITPlotPanel(is_dark_mode=self.is_dark_mode)
        self.theme_aware_panels.append(self.plot_panel)
        self.tabs.addTab(self.plot_panel.create_widget(self.tabs), "2. SWEEP")

        # TAB 3: RESULTS
        self.results_panel = DITResultsPanel(is_dark_mode=self.is_dark_mode)
        self.theme_aware_panels.append(self.results_panel)
        self.tabs.addTab(self.results_panel.create_widget(self.tabs), "3. RESULTS")

        # TAB 4: LOGS
        self.log_panel = LogPanel(output_dir=self.output_dir, is_dark_mode=self.is_dark_mode)
        self.theme_aware_panels.append(self.log_panel)
        self.tabs.addTab(self.log_panel.create_widget(self.tabs), "4. LOGS")

        self.tabs.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self._build_footer())

        self._widget = page
        return page

    def _build_footer(self):
        self.footer = QFrame()
        self.footer.setObjectName("FooterStrip")
        self.footer.setAttribute(Qt.WA_StyledBackground, True)
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(16, 12, 16, 12)

        lbl_title = QLabel("DIT PROGRESS:")
        lbl_title.setObjectName("AccentLabel")
        footer_layout.addWidget(lbl_title)
        self._footer_title_lbl = lbl_title

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        footer_layout.addWidget(self.progress_bar, 1)

        self.progress_pct = QLabel("0%")
        self.progress_pct.setObjectName("MainLabel")
        footer_layout.addWidget(self.progress_pct)

        divider = QFrame()
        divider.setObjectName("VDivider")
        divider.setFrameShape(QFrame.VLine)
        footer_layout.addWidget(divider)

        self.progress_txt = QLabel("Ready")
        self.progress_txt.setObjectName("DimLabel")
        footer_layout.addWidget(self.progress_txt)

        self.footer.setVisible(False)
        self._footer_shadow = make_panel_shadow(self.footer, self.is_dark_mode)
        return self.footer

    def _on_tab_changed(self, index):
        animate_tab_switch(self.tabs, index, anim_owner=self._widget)
        self.tabs.updateGeometry()

    def _on_config_layout_changed(self, change):
        self.config_panel.get_widget().updateGeometry()
        self.tabs.updateGeometry()
        self.scroll.updateGeometry()

    # --- Public API (used by MainWindow, which owns cross-mode state) ---

    def set_running(self, running):
        self.footer.setVisible(running)
        if running:
            self.progress_bar.setValue(0)
            self.progress_pct.setText("0%")
            self.progress_txt.setText("Initializing hardware...")

    def set_progress(self, percent, text):
        self.progress_bar.setValue(percent)
        self.progress_pct.setText(f"{percent}%")
        self.progress_txt.setText(text)

    def apply_theme(self, colors, is_dark_mode):
        self.is_dark_mode = is_dark_mode

        tab_bar = self.tabs.tabBar()
        tab_bar.style().unpolish(tab_bar)
        tab_bar.style().polish(tab_bar)
        tab_bar.updateGeometry()

        update_shadow_color(self._footer_shadow, is_dark_mode)
        self._footer_title_lbl.setStyleSheet(f"color: {get_mode_accent(colors, 'dit')};")

        for panel in self.theme_aware_panels:
            panel.apply_theme(colors, is_dark_mode)
