"""
Home screen: a grid of workflow-module cards.

Plain Atom panel + imperative PySide6 layout, matching the other
common_panels (HeaderPanel, LogPanel).
"""
import functools

from atom.api import Atom, Bool, Event, Typed
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QGraphicsOpacityEffect

from gui.custom_widgets import ClickableFrame

_CARDS = [
    dict(id="jv", category="jv", tag="CHARACTERIZATION", title="JV Sweep Profile",
         desc="Standard voltage sweeps mapping short-circuit current, Voc, and dynamic PCE parameters.",
         enabled=True),
    dict(id="spo", category="spo", tag="STABILITY", title="Stabilized Power Output",
         desc="Active holding sweeps mapping power output characteristics over extended intervals.",
         enabled=True),
    dict(id="dit", category="dit", tag="KINETICS", title="Dark Injection Transient",
         desc="High-speed pulsed decay sequences for transient SCLC charge mapping analysis.",
         enabled=True),
    dict(id="cv", category="cv", tag="ELECTROCHEMISTRY", title="Cyclic Voltammetry",
         desc="Triangular potential waveform sweeps mapping redox behavior and electrochemical kinetics (Module currently disabled or not installed).",
         enabled=False),
]
_CARDS_PER_ROW = 3


class HomePanel(Atom):
    __slots__ = ('__weakref__',)

    is_dark_mode = Bool(False)

    module_selected = Event()  # fires the card's id (str), e.g. "jv"

    _widget = Typed(QWidget)

    def get_widget(self):
        return self._widget

    def create_widget(self, parent):
        container = QWidget(parent)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(14)

        title_lbl = QLabel("SELECT WORKFLOW MODULE")
        title_lbl.setObjectName("PanelTitleLarge")
        layout.addWidget(title_lbl)

        grid = QGridLayout()
        grid.setSpacing(16)
        for i, spec in enumerate(_CARDS):
            grid.addWidget(self._build_card(spec), i // _CARDS_PER_ROW, i % _CARDS_PER_ROW)
        layout.addLayout(grid)
        layout.addStretch(1)

        self._widget = container
        return container

    def _build_card(self, spec):
        card = ClickableFrame()
        card.setObjectName("HomeCard")
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setProperty("category", spec["category"])
        card.setProperty("state", "enabled" if spec["enabled"] else "disabled")
        card.setCursor(Qt.PointingHandCursor if spec["enabled"] else Qt.ForbiddenCursor)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(6)

        tag_lbl = QLabel(spec["tag"])
        tag_lbl.setObjectName("CardTag")
        tag_lbl.setProperty("category", spec["category"])
        card_layout.addWidget(tag_lbl)

        title_lbl = QLabel(spec["title"])
        title_lbl.setObjectName("CardTitle")
        card_layout.addWidget(title_lbl)

        desc_lbl = QLabel(spec["desc"])
        desc_lbl.setObjectName("CardDesc")
        desc_lbl.setWordWrap(True)
        card_layout.addWidget(desc_lbl)

        if spec["enabled"]:
            card.clicked.connect(functools.partial(self._on_card_clicked, spec["id"]))
        else:
            effect = QGraphicsOpacityEffect(card)
            effect.setOpacity(0.6)
            card.setGraphicsEffect(effect)

        return card

    def _on_card_clicked(self, module_id):
        self.module_selected = module_id

    def apply_theme(self, colors, is_dark_mode):
        self.is_dark_mode = is_dark_mode
