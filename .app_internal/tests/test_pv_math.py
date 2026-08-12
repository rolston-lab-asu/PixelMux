"""
Tests for core/pv_math.py.

Pure math, no hardware/Qt involved. Run from .app_internal:

    pytest tests/test_pv_math.py -v

Two checks here:
  1. Exact hand-derived cases for the zero-crossing interpolation and the
     fault/validation guards (deterministic, no tolerance needed).
  2. A synthetic single-diode JV curve (built with single_diode_model_current
     using known Iph/I0/n/Rs/Rsh) fed back through extract_parameters and
     diode_fit_resistances, checked against the known ground-truth values.
     This pins down the current numeric behavior so future changes to the
     interpolation/fit logic show up as a failing test here.
"""
import numpy as np
import pytest

from core.pv_math import (
    _interp_zero_crossing,
    check_fault,
    derivative_resistances,
    diode_fit_resistances,
    extract_parameters,
    full_iv_report,
    single_diode_model_current,
)


# --- _interp_zero_crossing -------------------------------------------------

def test_interp_zero_crossing_exact_hit():
    assert _interp_zero_crossing([0, 1, 2], [0.0, 1, 2]) == 0.0


def test_interp_zero_crossing_linear_interpolation():
    # y goes -2, -1, 1, 2 -> crosses zero 1/2 way between x=1 (y=-1) and x=2 (y=1)
    result = _interp_zero_crossing([0, 1, 2, 3], [-2, -1, 1, 2])
    assert result == pytest.approx(1.5)


def test_interp_zero_crossing_no_sign_change():
    assert np.isnan(_interp_zero_crossing([0, 1, 2], [1, 2, 3]))


def test_interp_zero_crossing_insufficient_points():
    assert np.isnan(_interp_zero_crossing([0], [0]))
    assert np.isnan(_interp_zero_crossing([], []))


def test_interp_zero_crossing_ignores_non_finite():
    result = _interp_zero_crossing([0, 1, 2, 3], [-2, np.nan, 1, 2])
    # with the nan point dropped: x=[0,2,3], y=[-2,1,2] -> crossing between x=0(-2), x=2(1)
    assert result == pytest.approx(4 / 3)


# --- check_fault -------------------------------------------------------

def test_check_fault_short():
    assert check_fault(np.array([0.1, 0.96, 0.2])) == "SHORT"


def test_check_fault_open():
    assert check_fault(np.array([1e-8, -1e-9, 0.0])) == "OPEN"


def test_check_fault_normal():
    assert check_fault(np.array([0.01, 0.05, -0.02])) is None


def test_check_fault_boundaries_are_exclusive():
    # exactly at the thresholds should NOT trip (code uses strict > / <)
    assert check_fault(np.array([0.95])) is None
    assert check_fault(np.array([1e-6])) is None


# --- check_fault: compliance-relative SHORT detection --------------------
# A shorted pixel rails AT whatever compliance is configured, not at some
# fixed absolute current. Compliance is user-settable (0.001-1000 mA,
# default 105 mA), so a fixed 0.95 A threshold never fires in practice.

def test_check_fault_detects_short_at_default_compliance():
    default_compliance = 0.105  # KEITHLEY_DEFAULT_COMPLIANCE_A
    railed = np.full(20, default_compliance)
    assert check_fault(railed, compliance_a=default_compliance) == "SHORT"


def test_check_fault_detects_short_at_low_compliance():
    compliance = 0.010  # 10 mA
    railed = np.full(20, compliance)
    assert check_fault(railed, compliance_a=compliance) == "SHORT"


def test_check_fault_normal_cell_not_flagged_short_near_compliance():
    # A healthy cell drawing well under compliance must not trip SHORT.
    compliance = 0.105
    healthy = np.linspace(0.0, 0.0012, 20)  # ~1.2 mA, typical small pixel
    assert check_fault(healthy, compliance_a=compliance) is None


def test_check_fault_short_scales_with_configured_compliance():
    # The same 105 mA reading is a short at 105 mA compliance, but is
    # perfectly normal headroom at 1000 mA compliance.
    reading = np.full(20, 0.105)
    assert check_fault(reading, compliance_a=0.105) == "SHORT"
    assert check_fault(reading, compliance_a=1.0) is None


# --- check_fault: swept measurements must not mistake forward injection
# past Voc for a short. A JV sweep routinely runs to 1.3 V on a ~0.6 V Voc
# cell, where a HEALTHY diode rails at compliance. Only railing at zero
# bias means the pixel is actually shorted.

def _healthy_sweep():
    """V from +1.3 down to -0.2; rails at compliance in deep forward bias,
    delivers a normal ~1.2 mA photocurrent at and below 0 V."""
    V = np.linspace(1.3, -0.2, 15)
    I = np.where(V > 0.9, -0.105, np.where(V > 0.6, -0.03, 0.0012))
    return V, I


def test_check_fault_healthy_sweep_railing_past_voc_is_not_short():
    V, I = _healthy_sweep()
    assert check_fault(I, compliance_a=0.105, V=V) is None


def test_check_fault_sweep_railed_at_zero_bias_is_short():
    V = np.linspace(1.3, -0.2, 15)
    I = np.full_like(V, -0.105)  # railed everywhere, including 0 V
    assert check_fault(I, compliance_a=0.105, V=V) == "SHORT"


def test_check_fault_fixed_bias_hold_uses_all_samples_railed():
    # No V supplied (SPO/DIT sit at one operating point): every sample
    # railed is a short, but a single transient spike is not.
    assert check_fault(np.full(20, 0.105), compliance_a=0.105) == "SHORT"
    spiky = np.full(20, 0.001)
    spiky[7] = 0.105
    assert check_fault(spiky, compliance_a=0.105) is None


# --- check_fault: open_threshold_a override (DIT's sub-uA sense ranges) --

def test_check_fault_default_open_threshold_flags_sub_microamp_reading():
    assert check_fault(np.full(10, 5e-7)) == "OPEN"  # 0.5 uA, default 1 uA floor


def test_check_fault_lower_open_threshold_accepts_same_reading():
    # A real DIT transient decaying into the 100 nA sense range: 0.5 uA is
    # normal signal there, not noise -- must not be flagged with a lower
    # threshold appropriate to that range.
    assert check_fault(np.full(10, 5e-7), open_threshold_a=5e-10) is None


def test_check_fault_lower_open_threshold_still_flags_true_noise_floor():
    assert check_fault(np.full(10, 1e-11), open_threshold_a=5e-10) == "OPEN"


# --- extract_parameters: input validation -------------------------------

def test_extract_parameters_rejects_zero_area():
    with pytest.raises(ValueError):
        extract_parameters([0, 1], [0, 1], area_cm2=0)


def test_extract_parameters_rejects_negative_pin():
    with pytest.raises(ValueError):
        extract_parameters([0, 1], [0, 1], area_cm2=0.1, pin_mw_cm2=-5)


# --- extract_parameters / diode_fit_resistances against a known curve ---

# A synthetic curve generated from the model itself, so the true Iph/I0/n/Rs/Rsh
# are known exactly and can be checked against what the pure-math functions recover.
_VT = 0.02585
_TRUE_PARAMS = dict(Iph=0.030, I0=1e-10, n=1.4, Rs=2.0, Rsh=5000.0)
_AREA_CM2 = 0.108  # default 12-pixel area


def _synthetic_curve(n_points=300):
    V = np.linspace(-0.05, 0.75, n_points)  # wide enough to bracket Voc (~0.706V)
    I = single_diode_model_current(list(_TRUE_PARAMS.values()), V, _VT)
    return V, I


def test_extract_parameters_recovers_voc_and_jsc():
    V, I = _synthetic_curve()
    result = extract_parameters(V, I, _AREA_CM2)

    # Reference Isc/Voc solved directly from the same model, independent of
    # extract_parameters' interpolation logic.
    I_at_zero = single_diode_model_current(list(_TRUE_PARAMS.values()), np.array([0.0]), _VT)[0]
    jsc_ref = abs(I_at_zero / _AREA_CM2 * 1000)

    assert result["Voc"] == pytest.approx(0.70623, abs=1e-3)
    assert result["Jsc"] == pytest.approx(jsc_ref, rel=1e-3)
    assert 0.0 < result["FF"] < 1.0
    assert result["Pmax"] > 0.0
    # PCE == Pmax numerically when pin_mw_cm2 defaults to 100
    assert result["PCE"] == pytest.approx(result["Pmax"])


def test_diode_fit_resistances_recovers_true_rs_rsh():
    V, I = _synthetic_curve()
    Rs_fit, Rsh_fit = diode_fit_resistances(V, I)

    assert Rs_fit == pytest.approx(_TRUE_PARAMS["Rs"], rel=1e-2)
    assert Rsh_fit == pytest.approx(_TRUE_PARAMS["Rsh"], rel=1e-2)


def test_diode_fit_resistances_insufficient_points():
    V, I = _synthetic_curve(n_points=9)  # fewer than the 10-point minimum
    Rs_fit, Rsh_fit = diode_fit_resistances(V, I)
    assert np.isnan(Rs_fit)
    assert np.isnan(Rsh_fit)


# --- derivative_resistances: sanity, not ground truth ------------
# The docstring calls this a noisier local-slope approximation, so it's
# checked for physically-sane behavior rather than an exact regression value.

def test_derivative_resistances_insufficient_points():
    Rs, Rsh = derivative_resistances([0, 1, 2, 3, 4], [0, 1, 2, 3, 4])
    assert np.isnan(Rs)
    assert np.isnan(Rsh)


def test_derivative_resistances_sane_on_synthetic_curve():
    V, I = _synthetic_curve()
    Rs, Rsh = derivative_resistances(V, I)

    assert np.isfinite(Rs) and Rs > 0
    assert np.isfinite(Rsh) and Rsh > 0
    # Shunt resistance should be orders of magnitude larger than series
    # resistance for a healthy cell -- true here by construction (2 vs 5000).
    assert Rsh > Rs


# --- full_iv_report: wiring / fit_resistances flag ----------------------

def test_full_iv_report_skips_diode_fit_when_disabled():
    V, I = _synthetic_curve()
    result = full_iv_report(V, I, _AREA_CM2, fit_resistances=False)

    assert np.isnan(result["Rs_diode_eq"])
    assert np.isnan(result["Rsh_diode_eq"])
    # derivative estimate always runs regardless of the flag
    assert np.isfinite(result["Rs_derivative"])
    assert np.isfinite(result["Rsh_derivative"])


def test_full_iv_report_includes_diode_fit_when_enabled():
    V, I = _synthetic_curve()
    result = full_iv_report(V, I, _AREA_CM2, fit_resistances=True)

    assert result["Rs_diode_eq"] == pytest.approx(_TRUE_PARAMS["Rs"], rel=1e-2)
    assert result["Rsh_diode_eq"] == pytest.approx(_TRUE_PARAMS["Rsh"], rel=1e-2)
