"""Shared Qt visual helpers such as panel shadows."""
from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QAbstractAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsOpacityEffect


def set_glow(widget, color_hex, enabled, blur_radius=10):
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsDropShadowEffect):
        effect = QGraphicsDropShadowEffect(widget)
        effect.setXOffset(0)
        effect.setYOffset(0)
        widget.setGraphicsEffect(effect)
    effect.setEnabled(enabled)
    if enabled:
        effect.setBlurRadius(blur_radius)
        effect.setColor(QColor(color_hex))


def make_panel_shadow(widget, is_dark_mode=False):
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(20)
    effect.setXOffset(0)
    effect.setYOffset(4)
    effect.setColor(QColor(0, 0, 0, 90 if is_dark_mode else 25))
    widget.setGraphicsEffect(effect)
    return effect


def update_shadow_color(effect, is_dark_mode):
    if effect is not None:
        effect.setColor(QColor(0, 0, 0, 90 if is_dark_mode else 25))


def refresh_led_glow(led, colors):
    state = led.property("status")
    glow_color = {"ok": colors["success"], "bad": colors["error"]}.get(state)

    if glow_color:
        effect = led.graphicsEffect()
        if not isinstance(effect, QGraphicsDropShadowEffect):
            effect = QGraphicsDropShadowEffect(led)
            effect.setBlurRadius(14)
            effect.setXOffset(0)
            effect.setYOffset(0)
            led.setGraphicsEffect(effect)
        effect.setColor(QColor(glow_color))
    else:
        led.setGraphicsEffect(None)


def set_status_led(led, label, state):
    led.setProperty("status", state)
    label.setProperty("status", state)

    led.style().unpolish(led)
    led.style().polish(led)
    label.style().unpolish(label)
    label.style().polish(label)


def animate_tab_switch(tabs, index, anim_owner):
    widget = tabs.widget(index)
    if widget is None:
        return None

    if widget.graphicsEffect() is not None:
        return None

    opacity_effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(opacity_effect)

    fade = QPropertyAnimation(opacity_effect, b"opacity", anim_owner)
    fade.setDuration(250)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.setEasingCurve(QEasingCurve.OutCubic)
    fade.finished.connect(lambda: widget.setGraphicsEffect(None))
    fade.start(QAbstractAnimation.DeleteWhenStopped)
    return fade
