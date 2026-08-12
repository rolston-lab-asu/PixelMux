"""
Tests for SPOConfigPanel. Covers get_spo_params()'s two shapes (tracking off/on),
including the Settle Time field added alongside Step/Min Step/V Ceiling,
plus the toggle's visibility wiring and validation.
"""
import pytest

from gui.spo_mode.spo_config_panel import SPOConfigPanel


@pytest.fixture
def panel(qapp):
    from PySide6.QtWidgets import QWidget
    p = SPOConfigPanel()
    host = QWidget()
    p.create_widget(host)
    host.resize(host.sizeHint())
    host.show()
    qapp.processEvents()
    # yield (not return): keeps `host` alive in this frame
    yield p


# --- get_spo_params(): tracking OFF -------------------------------------

def test_params_off_has_no_mppt_keys(panel):
    params = panel.get_spo_params()
    assert params["mppt_enabled"] is False
    for key in ("start_v", "step_v", "min_step_v", "step_decay", "settle_s", "v_min", "v_max"):
        assert key not in params


def test_params_off_base_keys_and_defaults(panel):
    params = panel.get_spo_params()
    assert params["hold_v"] == pytest.approx(0.80)
    assert params["duration_s"] == pytest.approx(120)
    assert params["interval_s"] == pytest.approx(1.0)
    assert params["pin"] == pytest.approx(100.0)
    assert params["compliance_a"] == pytest.approx(0.105)
    assert params["loops"] == 1


# --- get_spo_params(): tracking ON ---------------------------------------

def test_params_on_includes_settle_s_default(panel, qapp):
    panel._mppt_on_btn.click()
    qapp.processEvents()
    params = panel.get_spo_params()
    assert params["mppt_enabled"] is True
    assert params["settle_s"] == pytest.approx(2.0)  # default shown in the UI


def test_params_on_settle_s_reflects_user_edit(panel, qapp):
    panel._mppt_on_btn.click()
    panel._settle_s.setValue(0.35)
    qapp.processEvents()
    assert panel.get_spo_params()["settle_s"] == pytest.approx(0.35)


def test_params_on_start_v_mirrors_hold_v_field(panel, qapp):
    panel._hold_v.setValue(0.42)
    panel._mppt_on_btn.click()
    qapp.processEvents()
    params = panel.get_spo_params()
    assert params["start_v"] == pytest.approx(0.42)


def test_params_on_step_and_ceiling_unit_conversion(panel, qapp):
    panel._mppt_on_btn.click()
    panel._step_mv.setValue(25.0)
    panel._min_step_mv.setValue(2.5)
    panel._v_ceiling.setValue(0.9)
    qapp.processEvents()
    params = panel.get_spo_params()
    assert params["step_v"] == pytest.approx(0.025)
    assert params["min_step_v"] == pytest.approx(0.0025)
    assert params["v_max"] == pytest.approx(0.9)
    assert params["v_min"] == pytest.approx(0.0)


# --- Toggle visibility wiring --------------------------------------------

def test_toggle_off_by_default(panel):
    assert panel.mppt_enabled() is False
    assert panel._hold_v_label.text() == "Hold V (V)"


def test_toggle_on_shows_advanced_rows_and_relabels(panel, qapp):
    panel._mppt_on_btn.click()
    qapp.processEvents()
    assert panel.mppt_enabled() is True
    assert panel._hold_v_label.text() == "Start V (V)"
    for row in (panel._step_row, panel._min_step_row, panel._ceiling_row, panel._settle_row):
        assert row.isVisible()
    assert panel._mppt_hint.isVisible()


def test_toggle_off_again_hides_advanced_rows(panel, qapp):
    panel._mppt_on_btn.click()
    qapp.processEvents()
    panel._mppt_off_btn.click()
    qapp.processEvents()
    assert panel.mppt_enabled() is False
    assert panel._hold_v_label.text() == "Hold V (V)"
    for row in (panel._step_row, panel._min_step_row, panel._ceiling_row, panel._settle_row):
        assert not row.isVisible()


# --- Validation ------------------------------------------------------------

def test_validate_rejects_start_v_above_ceiling(panel, qapp):
    panel._mppt_on_btn.click()
    panel._hold_v.setValue(2.0)
    panel._v_ceiling.setValue(1.0)
    qapp.processEvents()
    err = panel.validate()
    assert err is not None
    assert "V Ceiling" in err


def test_validate_passes_start_v_at_or_below_ceiling(panel, qapp):
    panel._mppt_on_btn.click()
    panel._hold_v.setValue(0.5)
    panel._v_ceiling.setValue(1.5)
    qapp.processEvents()
    # (no pixel selected in this fixture, so validate() still fails, but not
    # on the ceiling check -- confirm that specific error is absent)
    err = panel.validate()
    assert err is None or "V Ceiling" not in err


def test_validate_ceiling_check_not_applied_when_tracking_off(panel, qapp):
    panel._hold_v.setValue(4.0)
    panel._v_ceiling.setValue(1.0)  # would fail the check if tracking were on
    qapp.processEvents()
    err = panel.validate()
    assert err is None or "V Ceiling" not in err


# --- set_running() disables the new field too -----------------------------

def test_set_running_disables_settle_field(panel, qapp):
    panel._mppt_on_btn.click()
    qapp.processEvents()
    panel.set_running(True)
    assert panel._settle_s.isEnabled() is False
    panel.set_running(False)
    assert panel._settle_s.isEnabled() is True
