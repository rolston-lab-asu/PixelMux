"""Small Qt and pyqtgraph widget overrides."""
from PySide6.QtCore import Qt, QRectF, QSize, Signal
from PySide6.QtGui import QTextDocument, QFont, QFontMetrics, QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QSpinBox, QDoubleSpinBox, QComboBox, QFrame, QHeaderView, QStyle, QStyleOptionHeader,
    QTabBar, QTabWidget, QAbstractSpinBox, QLineEdit, QHBoxLayout, QPushButton, QButtonGroup,
)
import pyqtgraph as pg


class ClickableFrame(QFrame):
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class NoWheelSpinBox(QSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def wheelEvent(self, event):
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def wheelEvent(self, event):
        event.ignore()


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


class _PlainNumberField(QLineEdit):
    valueChanged = Signal(float)
    _decimals = 0
    _is_int = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._minimum = 0.0
        self._maximum = 100.0
        self._value = 0.0
        self._validator = QDoubleValidator(self)
        self.setValidator(self._validator)
        self.textEdited.connect(self._on_text_edited)
        self.editingFinished.connect(self._on_editing_finished)
        self.setValue(0)

    def setRange(self, minimum, maximum):
        self._minimum = minimum
        self._maximum = maximum
        self._validator.setRange(minimum, maximum, self._decimals)

    def setDecimals(self, n):
        self._decimals = n
        self._validator.setDecimals(n)

    def value(self):
        return int(self._value) if self._is_int else self._value

    def setValue(self, value):
        value = max(self._minimum, min(self._maximum, value))
        changed = value != self._value
        self._value = value
        self.setText(self._format(value))
        if changed:
            self.valueChanged.emit(self.value())

    def _format(self, value):
        if self._is_int or self._decimals == 0:
            return str(int(round(value)))
        return f"{value:.{self._decimals}f}"

    def _on_text_edited(self, text):
        try:
            parsed = float(text)
        except ValueError:
            return
        clamped = max(self._minimum, min(self._maximum, parsed))
        self._value = clamped
        self.valueChanged.emit(self.value())

    def _on_editing_finished(self):
        self.setValue(self._value)


class PlainIntField(_PlainNumberField):
    _is_int = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._validator = QIntValidator(self)
        self.setValidator(self._validator)

    def setRange(self, minimum, maximum):
        self._minimum = minimum
        self._maximum = maximum
        self._validator.setRange(int(minimum), int(maximum))


class PlainDoubleField(_PlainNumberField):
    pass


def build_segmented_toggle(labels, colors, accent, checked_index=0):
    pill = QFrame()
    pill.setObjectName("TogglePill")
    pill_layout = QHBoxLayout(pill)
    pill_layout.setContentsMargins(2, 2, 2, 2)
    pill_layout.setSpacing(0)

    bold_font = QFont()
    bold_font.setBold(True)
    metrics = QFontMetrics(bold_font)
    widest_text = max(labels, key=lambda s: metrics.horizontalAdvance(s))
    seg_width = metrics.horizontalAdvance(widest_text) + 28

    buttons = []
    for label in labels:
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setFixedSize(seg_width, 26)
        btn.setObjectName("ToggleOption")
        btn.setFont(bold_font)
        pill_layout.addWidget(btn)
        buttons.append(btn)
    buttons[checked_index].setChecked(True)

    group = QButtonGroup(pill)
    group.setExclusive(True)
    for btn in buttons:
        group.addButton(btn)

    restyle_segmented_toggle(pill, colors, accent)
    return pill, buttons, group


def restyle_segmented_toggle(pill, colors, accent):
    text_on_accent = colors.get("success_text_on", colors["accent_text_on"])
    pill.setStyleSheet(f"""
        QFrame#TogglePill {{
            background-color: {colors['bg_input']};
            border: 1px solid {colors['border']};
            border-radius: 14px;
        }}
        QPushButton#ToggleOption {{
            padding: 0px;
            border: none;
            border-radius: 12px;
            background-color: transparent;
            color: {colors['text_dim']};
            font-weight: 600;
        }}
        QPushButton#ToggleOption:checked {{
            background-color: {accent};
            color: {text_on_accent};
        }}
    """)


class NoWheelViewBox(pg.ViewBox):
    def __init__(self, range_callback=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.range_callback = range_callback

    def wheelEvent(self, event, axis=None):
        event.ignore()

    def mouseClickEvent(self, event):
        if event.button() == Qt.RightButton and self.range_callback:
            event.accept()
            self.range_callback()
            return
        super().mouseClickEvent(event)


class RichTextHeaderView(QHeaderView):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setDefaultAlignment(Qt.AlignCenter)
        self._text_color = "#000000"

    def set_text_color(self, hex_color):
        self._text_color = hex_color
        self.viewport().update()

    def paintSection(self, painter, rect, logical_index):
        painter.save()

        opt = self._style_option(logical_index, rect)
        opt.text = ""
        self.style().drawControl(QStyle.CE_Header, opt, painter, self)

        text = self.model().headerData(logical_index, self.orientation(), Qt.DisplayRole)
        if text:
            doc = QTextDocument()
            doc.setDefaultFont(self.font())
            doc.setHtml(
                f'<div align="center" style="color:{self._text_color}; font-weight:bold;">{text}</div>'
            )
            doc.setTextWidth(rect.width())

            doc_height = doc.size().height()
            y_offset = max(0, (rect.height() - doc_height) / 2)

            painter.translate(rect.left(), rect.top() + y_offset)
            doc.drawContents(painter, QRectF(0, 0, rect.width(), rect.height()))

        painter.restore()

    def _style_option(self, logical_index, rect):
        opt = QStyleOptionHeader()
        self.initStyleOption(opt)
        opt.rect = rect
        opt.section = logical_index
        return opt

    def sectionSizeHint(self, logical_index):
        size = super().sectionSizeHint(logical_index)
        return QSize(size.width(), max(size.height(), 34))

    def sectionSizeFromContents(self, logical_index):
        text = self.model().headerData(logical_index, self.orientation(), Qt.DisplayRole) if self.model() else None
        if not text:
            return super().sectionSizeFromContents(logical_index)

        doc = QTextDocument()
        doc.setDefaultFont(self.font())
        doc.setHtml(f'<div style="font-weight:bold; white-space:nowrap;">{text}</div>')
        doc.setTextWidth(-1)

        width = int(doc.idealWidth()) + 24
        height = max(int(doc.size().height()) + 14, 34)
        return QSize(width, height)


class SafeTabBar(QTabBar):
    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)

        bold_font = QFont(self.font())
        bold_font.setBold(True)
        text_width = QFontMetrics(bold_font).horizontalAdvance(self.tabText(index))

        needed_width = text_width + 64
        needed_height = max(size.height(), 46)
        return QSize(max(size.width(), needed_width), needed_height)


class SizeAwareTabWidget(QTabWidget):
    def sizeHint(self):
        tab_bar_hint = self.tabBar().sizeHint()
        current = self.currentWidget()
        page_hint = current.sizeHint() if current is not None else super().sizeHint()

        frame = 2 * self.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        width = max(page_hint.width(), tab_bar_hint.width()) + frame
        height = page_hint.height() + tab_bar_hint.height() + frame
        return QSize(width, height)

    def minimumSizeHint(self):
        tab_bar_hint = self.tabBar().sizeHint()
        current = self.currentWidget()
        page_hint = current.minimumSizeHint() if current is not None else super().minimumSizeHint()

        frame = 2 * self.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        width = max(page_hint.width(), tab_bar_hint.width()) + frame
        height = page_hint.height() + tab_bar_hint.height() + frame
        return QSize(width, height)
