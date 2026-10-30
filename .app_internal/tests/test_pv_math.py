"""Tests for core/pv_math.py."""
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


def test_interp_zero_crossing_exact_hit():
    assert _interp_zero_crossing([0, 1, 2], [0.0, 1, 2]) == 0.0


def test_interp_zero_crossing_linear_interpolation():
    result = _interp_zero_crossing([0, 1, 2, 3], [-2, -1, 1, 2])
    assert result == pytest.approx(1.5)


def test_interp_zero_crossing_no_sign_change():
    assert np.isnan(_interp_zero_crossing([0, 1, 2], [1, 2, 3]))


def test_interp_zero_crossing_insufficient_points():
    assert np.isnan(_interp_zero_crossing([0], [0]))
    assert np.isnan(_interp_zero_crossing([], []))


def test_interp_zero_crossing_ignores_non_finite():
    result = _interp_zero_crossing([0, 1, 2, 3], [-2, np.nan, 1, 2])
    assert result == pytest.approx(4 / 3)


def test_check_fault_short():
    assert check_fault(np.array([0.1, 0.96, 0.2])) == "SHORT"


def test_check_fault_open():
    assert check_fault(np.array([1e-8, -1e-9, 0.0])) == "OPEN"


def test_check_fault_normal():
    assert check_fault(np.array([0.01, 0.05, -0.02])) is None


def test_check_fault_boundaries_are_exclusive():
    assert check_fault(np.array([0.95])) is None
    assert check_fault(np.array([1e-6])) is None


def test_check_fault_detects_short_at_default_compliance():
    default_compliance = 0.105
    railed = np.full(20, default_compliance)
    assert check_fault(railed, compliance_a=default_compliance) == "SHORT"


def test_check_fault_detects_short_at_low_compliance():
    compliance = 0.010
    railed = np.full(20, compliance)
    assert check_fault(railed, compliance_a=compliance) == "SHORT"


def test_check_fault_normal_cell_not_flagged_short_near_compliance():
    compliance = 0.105
    healthy = np.linspace(0.0, 0.0012, 20)
    assert check_fault(healthy, compliance_a=compliance) is None


def test_check_fault_short_scales_with_configured_compliance():
    reading = np.full(20, 0.105)
    assert check_fault(reading, compliance_a=0.105) == "SHORT"
    assert check_fault(reading, compliance_a=1.0) is None


def _healthy_sweep():
    V = np.linspace(1.3, -0.2, 15)
    I = np.where(V > 0.9, -0.105, np.where(V > 0.6, -0.03, 0.0012))
    return V, I


def test_check_fault_healthy_sweep_railing_past_voc_is_not_short():
    V, I = _healthy_sweep()
    assert check_fault(I, compliance_a=0.105, V=V) is None


def test_check_fault_sweep_railed_at_zero_bias_is_short():
    V = np.linspace(1.3, -0.2, 15)
    I = np.full_like(V, -0.105)
    assert check_fault(I, compliance_a=0.105, V=V) == "SHORT"


def test_check_fault_fixed_bias_hold_uses_all_samples_railed():
    assert check_fault(np.full(20, 0.105), compliance_a=0.105) == "SHORT"
    spiky = np.full(20, 0.001)
    spiky[7] = 0.105
    assert check_fault(spiky, compliance_a=0.105) is None


def test_check_fault_default_open_threshold_flags_sub_microamp_reading():
    assert check_fault(np.full(10, 5e-7)) == "OPEN"


def test_check_fault_lower_open_threshold_accepts_same_reading():
    assert check_fault(np.full(10, 5e-7), open_threshold_a=5e-10) is None


def test_check_fault_lower_open_threshold_still_flags_true_noise_floor():
    assert check_fault(np.full(10, 1e-11), open_threshold_a=5e-10) == "OPEN"


def test_extract_parameters_rejects_zero_area():
    with pytest.raises(ValueError):
        extract_parameters([0, 1], [0, 1], area_cm2=0)


def test_extract_parameters_rejects_negative_pin():
    with pytest.raises(ValueError):
        extract_parameters([0, 1], [0, 1], area_cm2=0.1, pin_mw_cm2=-5)


_VT = 0.02585
_TRUE_PARAMS = dict(Iph=0.030, I0=1e-10, n=1.4, Rs=2.0, Rsh=5000.0)
_AREA_CM2 = 0.108


def _synthetic_curve(n_points=300):
    V = np.linspace(-0.05, 0.75, n_points)
    I = single_diode_model_current(list(_TRUE_PARAMS.values()), V, _VT)
    return V, I


def test_extract_parameters_recovers_voc_and_jsc():
    V, I = _synthetic_curve()
    result = extract_parameters(V, I, _AREA_CM2)

    I_at_zero = single_diode_model_current(list(_TRUE_PARAMS.values()), np.array([0.0]), _VT)[0]
    jsc_ref = abs(I_at_zero / _AREA_CM2 * 1000)

    assert result["Voc"] == pytest.approx(0.70623, abs=1e-3)
    assert result["Jsc"] == pytest.approx(jsc_ref, rel=1e-3)
    assert 0.0 < result["FF"] < 1.0
    assert result["Pmax"] > 0.0
    assert result["PCE"] == pytest.approx(result["Pmax"])


def test_diode_fit_resistances_recovers_true_rs_rsh():
    V, I = _synthetic_curve()
    Rs_fit, Rsh_fit = diode_fit_resistances(V, I)

    assert Rs_fit == pytest.approx(_TRUE_PARAMS["Rs"], rel=1e-2)
    assert Rsh_fit == pytest.approx(_TRUE_PARAMS["Rsh"], rel=1e-2)


def test_diode_fit_resistances_insufficient_points():
    V, I = _synthetic_curve(n_points=9)
    Rs_fit, Rsh_fit = diode_fit_resistances(V, I)
    assert np.isnan(Rs_fit)
    assert np.isnan(Rsh_fit)


def test_derivative_resistances_insufficient_points():
    Rs, Rsh = derivative_resistances([0, 1, 2, 3, 4], [0, 1, 2, 3, 4])
    assert np.isnan(Rs)
    assert np.isnan(Rsh)


def test_derivative_resistances_sane_on_synthetic_curve():
    V, I = _synthetic_curve()
    Rs, Rsh = derivative_resistances(V, I)

    assert np.isfinite(Rs) and Rs > 0
    assert np.isfinite(Rsh) and Rsh > 0
    assert Rsh > Rs


def test_full_iv_report_skips_diode_fit_when_disabled():
    V, I = _synthetic_curve()
    result = full_iv_report(V, I, _AREA_CM2, fit_resistances=False)

    assert np.isnan(result["Rs_diode_eq"])
    assert np.isnan(result["Rsh_diode_eq"])
    assert np.isfinite(result["Rs_derivative"])
    assert np.isfinite(result["Rsh_derivative"])


def test_full_iv_report_includes_diode_fit_when_enabled():
    V, I = _synthetic_curve()
    result = full_iv_report(V, I, _AREA_CM2, fit_resistances=True)

    assert result["Rs_diode_eq"] == pytest.approx(_TRUE_PARAMS["Rs"], rel=1e-2)
    assert result["Rsh_diode_eq"] == pytest.approx(_TRUE_PARAMS["Rsh"], rel=1e-2)
