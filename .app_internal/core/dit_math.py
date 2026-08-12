"""
DIT (Dark Injection Transient) metrics extraction: finds the voltage-step
transition, subtracts a final-tail baseline current, and integrates the
transient to get the extracted charge.
"""
import numpy as np


def calculate_dit_metrics(time_s, voltage_v, current_a):
    t = np.asarray(time_s, dtype=float)
    v = np.asarray(voltage_v, dtype=float)
    i = np.asarray(current_a, dtype=float)
    if len(t) < 2:
        return {
            "transition_index": None,
            "baseline_current_a": None,
            "peak_abs_current_a": None,
            "peak_time_s": None,
            "extracted_charge_c": None,
        }

    changes = np.flatnonzero(np.abs(np.diff(v)) > max(1e-9, np.ptp(v) * 1e-6))
    transition = int(changes[0] + 1) if changes.size else 0
    tail = i[max(transition, int(len(i) * 0.9)):]
    baseline = float(np.median(tail)) if tail.size else float(i[-1])
    extraction_i = i[transition:] - baseline
    extraction_t = t[transition:]
    peak_relative_index = int(np.argmax(np.abs(extraction_i)))
    peak_index = transition + peak_relative_index
    peak_time = float(t[peak_index] - t[transition])
    if hasattr(np, "trapezoid"):
        charge = float(np.trapezoid(extraction_i, extraction_t)) if len(extraction_t) >= 2 else 0.0
    else:
        charge = float(np.trapz(extraction_i, extraction_t)) if len(extraction_t) >= 2 else 0.0
    return {
        "transition_index": transition,
        "transition_time_s": float(t[transition]),
        "baseline_current_a": baseline,
        "peak_abs_current_a": float(np.max(np.abs(extraction_i))),
        "peak_time_s": peak_time,
        "peak_index": peak_index,
        "extracted_charge_c": charge,
        "extracted_charge_abs_c": abs(charge),
        "analysis_note": "Signed trapezoidal integral after median final-tail baseline subtraction.",
    }
