"""
Pure display-formatting helpers with no Qt/widget dependency, 
shared by any results-table panel.
"""
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
    """Auto-scaled SI-prefix formatter, e.g. 0.0000000012 + 'C' -> '1.200 nC'."""
    if value is None or not np.isfinite(value):
        return "--"
    if value == 0:
        return f"0 {unit}"

    abs_val = abs(value)
    for factor, prefix in _SI_PREFIXES:
        if abs_val >= factor:
            return f"{value / factor:.{decimals}f} {prefix}{unit}"

    factor, prefix = _SI_PREFIXES[-1]  # smaller than 1f -- report in femto
    return f"{value / factor:.{decimals}f} {prefix}{unit}"


def format_resistance(value):
    """
    SI-style formatter for resistances.
    Converts raw ohms into readable k and M suffixes.
    """
    if value is None or not np.isfinite(value):
        return "--"

    abs_val = abs(value)

    # Millions (Mega-ohms)
    if abs_val >= 1_000_000:
        return f"{value / 1_000_000:.2f} M"

    # Thousands (Kilo-ohms)
    elif abs_val >= 1_000:
        # For large Rsh (over 10k), 1 decimal: [e.g. 133.2 k]
        # For small Rs errors (under 10k), 2 decimal: [e.g. 3.29 k]
        if abs_val >= 10_000:
            return f"{value / 1_000:.1f} k"
        return f"{value / 1_000:.2f} k"

    # Standard Ohms
    elif abs_val >= 1:
        return f"{value:.2f}"

    # Sub-ohm values
    else:
        return f"{value:.3f}"
