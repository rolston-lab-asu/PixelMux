"""Tests for SPOWorker's fixed-voltage and MPP-tracking holds against the mock Keithley."""
import numpy as np
import pytest

from controllers.spo_worker import SPOWorker
from core.pv_math import full_iv_report
from instruments.keithley2460 import keithley_read_current
from instruments.mock_keithley import MockKeithley

AREA_CM2 = 0.0396


def _ground_truth(seed=42):
    k = MockKeithley(seed=seed)
    k.write("*RST")
    k.write(":SOUR:VOLT:ILIM 0.105")
    k.write(":OUTPut:STATe ON")
    V = np.linspace(-0.05, 0.75, 200)
    I = np.array([keithley_read_current(k, v, 0.0)[0] for v in V])
    return full_iv_report(V, I, area_cm2=AREA_CM2, pin_mw_cm2=100, fit_resistances=False)


def _run_worker(keithley, params):
    records = []
    faults = []
    worker = SPOWorker(keithley, None, [("A1", None, AREA_CM2)], params)
    worker.pixel_result.connect(lambda r: records.append(r))
    worker.pixel_faulted.connect(lambda *a: faults.append(a))
    worker.run()
    return records, faults


def test_fixed_hold_reports_positive_power_at_vmpp():
    truth = _ground_truth()
    k = MockKeithley(seed=42)
    records, faults = _run_worker(k, {
        "hold_v": truth["Vmpp"], "duration_s": 3, "interval_s": 0.5,
        "compliance_a": 0.105, "loops": 1, "mppt_enabled": False,
    })
    assert not faults
    r = records[-1]
    assert r["final_power_density_mw_cm2"] > 0
    assert abs(r["final_power_density_mw_cm2"] - truth["Pmax"]) < 0.5
    assert abs(r["final_voltage_v"] - truth["Vmpp"]) < 1e-6
    assert r["mppt_enabled"] is False


def test_fixed_hold_off_peak_gives_less_power_than_at_vmpp():
    truth = _ground_truth()
    k = MockKeithley(seed=42)
    records, faults = _run_worker(k, {
        "hold_v": 0.20, "duration_s": 3, "interval_s": 0.5,
        "compliance_a": 0.105, "loops": 1, "mppt_enabled": False,
    })
    assert not faults
    r = records[-1]
    assert r["final_power_density_mw_cm2"] < truth["Pmax"] * 0.85


def test_mppt_converges_to_vmpp_starting_below():
    truth = _ground_truth()
    k = MockKeithley(seed=42)
    records, faults = _run_worker(k, {
        "hold_v": 0.20, "duration_s": 8, "interval_s": 0.05,
        "compliance_a": 0.105, "loops": 1, "mppt_enabled": True,
        "start_v": 0.20, "step_v": 0.02, "min_step_v": 0.001,
        "step_decay": 0.5, "settle_s": 0.1, "v_min": 0.0, "v_max": 1.5,
    })
    assert not faults
    r = records[-1]
    assert r["final_power_density_mw_cm2"] > 0
    assert abs(r["final_voltage_v"] - truth["Vmpp"]) < 0.03
    assert r["mppt_enabled"] is True


def test_mppt_converges_to_vmpp_starting_above():
    truth = _ground_truth(seed=43)
    k = MockKeithley(seed=43)
    records, faults = _run_worker(k, {
        "hold_v": 0.65, "duration_s": 8, "interval_s": 0.05,
        "compliance_a": 0.105, "loops": 1, "mppt_enabled": True,
        "start_v": 0.65, "step_v": 0.02, "min_step_v": 0.001,
        "step_decay": 0.5, "settle_s": 0.1, "v_min": 0.0, "v_max": 1.5,
    })
    assert not faults
    r = records[-1]
    assert abs(r["final_voltage_v"] - truth["Vmpp"]) < 0.03


def test_mppt_respects_voltage_ceiling_clamp():
    k = MockKeithley(seed=42)
    records, faults = _run_worker(k, {
        "hold_v": 0.40, "duration_s": 2, "interval_s": 0.05,
        "compliance_a": 0.105, "loops": 1, "mppt_enabled": True,
        "start_v": 0.40, "step_v": 0.5, "min_step_v": 0.001,
        "step_decay": 0.5, "settle_s": 0.5, "v_min": 0.0, "v_max": 0.6,
    })
    assert not faults
    r = records[-1]
    assert max(r["voltage_v"]) <= 0.6 + 1e-9
    assert min(r["voltage_v"]) >= 0.0 - 1e-9


def test_record_schema_matches_between_modes():
    k1 = MockKeithley(seed=42)
    records_fixed, _ = _run_worker(k1, {
        "hold_v": 0.4, "duration_s": 1, "interval_s": 0.2,
        "compliance_a": 0.105, "loops": 1, "mppt_enabled": False,
    })
    k2 = MockKeithley(seed=42)
    records_mppt, _ = _run_worker(k2, {
        "hold_v": 0.4, "duration_s": 1, "interval_s": 0.2,
        "compliance_a": 0.105, "loops": 1, "mppt_enabled": True,
        "start_v": 0.4, "step_v": 0.01, "min_step_v": 0.001,
        "step_decay": 0.5, "settle_s": 0.2, "v_min": 0.0, "v_max": 1.5,
    })
    assert set(records_fixed[-1].keys()) == set(records_mppt[-1].keys())


def test_missing_mppt_enabled_key_defaults_to_fixed_hold():
    k = MockKeithley(seed=42)
    records, faults = _run_worker(k, {
        "hold_v": 0.4, "duration_s": 1, "interval_s": 0.2,
        "compliance_a": 0.105, "loops": 1,
    })
    assert not faults
    assert records[-1]["mppt_enabled"] is False


def test_stabilized_pce_matches_jv_pce_at_vmpp():
    truth = _ground_truth()
    k = MockKeithley(seed=42)
    records, _ = _run_worker(k, {
        "hold_v": truth["Vmpp"], "duration_s": 2, "interval_s": 0.5,
        "compliance_a": 0.105, "loops": 1, "mppt_enabled": False,
        "pin": 100,
    })
    r = records[-1]
    assert r["pin_mw_cm2"] == 100
    assert abs(r["final_pce_percent"] - truth["PCE"]) < 0.5


def test_stabilized_pce_scales_with_irradiance():
    k = MockKeithley(seed=42)
    records, _ = _run_worker(k, {
        "hold_v": 0.45, "duration_s": 1, "interval_s": 0.5,
        "compliance_a": 0.105, "loops": 1, "mppt_enabled": False,
        "pin": 50,
    })
    r = records[-1]
    assert r["final_pce_percent"] == pytest.approx(
        (r["final_power_density_mw_cm2"] / 50) * 100
    )


def test_pin_defaults_to_one_sun_when_absent():
    k = MockKeithley(seed=42)
    records, _ = _run_worker(k, {
        "hold_v": 0.45, "duration_s": 1, "interval_s": 0.5,
        "compliance_a": 0.105, "loops": 1, "mppt_enabled": False,
    })
    assert records[-1]["pin_mw_cm2"] == 100


def test_shorted_pixel_is_flagged_at_configured_compliance():
    compliance = 0.105
    k = MockKeithley(iph=10.0, seed=1)
    records, faults = _run_worker(k, {
        "hold_v": 0.4, "duration_s": 1, "interval_s": 0.25,
        "compliance_a": compliance, "loops": 1, "mppt_enabled": False,
    })
    assert not records
    assert faults and faults[0][2] == "SHORT"
