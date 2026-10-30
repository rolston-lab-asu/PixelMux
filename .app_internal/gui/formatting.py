"""Number formatting helpers for the results tables."""
import numpy as np


def format_metric(value, decimals):
    if value is None or not np.isfinite(value):
        return "--"
    return f"{value:.{decimals}f}"


_SI_PREFIXES = [
    (1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""),
    (1e-3, "m"), (1e-6, "\u00b5"), (1e-9, "n"), (1e-12, "p"), (1e-15, "f"),
]


def format_si(value, unit, decimals=3):
    if value is None or not np.isfinite(value):
        return "--"
    if value == 0:
        return f"0 {unit}"

    abs_val = abs(value)
    for factor, prefix in _SI_PREFIXES:
        if abs_val >= factor:
            return f"{value / factor:.{decimals}f} {prefix}{unit}"

    factor, prefix = _SI_PREFIXES[-1]
    return f"{value / factor:.{decimals}f} {prefix}{unit}"


def format_resistance(value):
    if value is None or not np.isfinite(value):
        return "--"

    abs_val = abs(value)

    if abs_val >= 1_000_000:
        return f"{value / 1_000_000:.2f} M"

    elif abs_val >= 1_000:
        if abs_val >= 10_000:
            return f"{value / 1_000:.1f} k"
        return f"{value / 1_000:.2f} k"

    elif abs_val >= 1:
        return f"{value:.2f}"

    else:
        return f"{value:.3f}"
