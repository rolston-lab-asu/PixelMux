"""
Substrate/relay-channel topology: which pixel labels exist per mode, their
default areas, and which relay channel each one maps to.

Shared by every measurement mode's worker and by
gui/common_panels/substrate_panel.py.
"""

PIXEL_LABELS = [chr(ord("A") + i) for i in range(12)]
PIXEL_TO_RELAY_CHANNEL = {label: i for i, label in enumerate(PIXEL_LABELS)}

DEFAULT_AREA_6_PIXEL_CM2 = 0.0396
DEFAULT_AREA_12_PIXEL_CM2 = 0.108
DEFAULT_CUSTOM_AREA_CM2 = 0.0396

# "Custom" is a single, directly-wired pixel (no relay board)
CUSTOM_PIXEL_MODE = "Custom"
CUSTOM_PIXEL_LABEL = "A"


def active_pixel_labels(pixel_mode_text):
    if pixel_mode_text == CUSTOM_PIXEL_MODE:
        return [CUSTOM_PIXEL_LABEL]
    count = 6 if pixel_mode_text.startswith("6") else 12
    return PIXEL_LABELS[:count]


def default_pixel_area(pixel_mode_text):
    if pixel_mode_text == CUSTOM_PIXEL_MODE:
        return DEFAULT_CUSTOM_AREA_CM2
    if pixel_mode_text.startswith("6"):
        return DEFAULT_AREA_6_PIXEL_CM2
    return DEFAULT_AREA_12_PIXEL_CM2


def pixel_uses_relay(pixel_mode_text):
    """Custom mode is wired straight to the Keithley, bypassing the relay
    board entirely"""
    return pixel_mode_text != CUSTOM_PIXEL_MODE
