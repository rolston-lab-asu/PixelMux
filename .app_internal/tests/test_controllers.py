"""
Characterization tests for the three measurement controllers.

These pin the SHARED behavior (lifecycle, results-table management, path
preview, export naming) that BaseMeasurementController factors out, plus
the per-mode strings that must stay mode-specific.
"""
from unittest.mock import Mock

import pytest

from controllers.jv_controller import JVController
from controllers.spo_controller import SPOController
from controllers.dit_controller import DITController
from controllers.measurement_mode import MeasurementMode
from core.sweep_state import SweepState


def _make(cls, **panel_overrides):
    config_panel = Mock()
    config_panel.autosave_table_enabled.return_value = False
    config_panel.autosave_curves_enabled.return_value = False
    config_panel.get_selected_pixels.return_value = []
    config_panel.sample_name.return_value = "sample"
    for k, v in panel_overrides.items():
        getattr(config_panel, k).return_value = v

    exporter = Mock()
    exporter.output_dir = "/tmp/out"

    controller = cls(
        instrument_manager=Mock(),
        exporter=exporter,
        config_panel=config_panel,
        plot_panel=Mock(),
        results_panel=Mock(),
        log_fn=Mock(),
        get_sample_name=Mock(return_value="sample"),
        tabs=Mock(),
        sweep_tab_index=1,
        parent_widget=Mock(),
    )
    return controller


ALL = [JVController, SPOController, DITController]


@pytest.mark.parametrize("cls", ALL)
def test_satisfies_measurement_mode_protocol(cls):
    assert isinstance(_make(cls), MeasurementMode)


@pytest.mark.parametrize("cls", ALL)
def test_state_is_sweep_state(cls):
    assert isinstance(_make(cls).state.__class__(), SweepState)


@pytest.mark.parametrize("cls", ALL)
def test_set_output_dir_writes_to_exporter(cls):
    c = _make(cls)
    c.set_output_dir("/tmp/some/output")
    assert c.exporter.output_dir == "/tmp/some/output"


@pytest.mark.parametrize("cls", ALL)
def test_export_disabled_at_startup(cls):
    c = _make(cls)
    c.results_panel.set_export_enabled.assert_called_with(False)


@pytest.mark.parametrize("cls", ALL)
def test_validate_fails_without_keithley(cls):
    c = _make(cls)
    c.inst.keithley = None
    assert c.validate() is False
    c.config_panel.flash_alert.assert_called()


@pytest.mark.parametrize("cls", ALL)
def test_validate_fails_when_config_panel_reports_error(cls):
    c = _make(cls)
    c.config_panel.validate.return_value = "ERROR: bad config"
    assert c.validate() is False


@pytest.mark.parametrize("cls", ALL)
def test_validate_passes_when_everything_ok(cls):
    c = _make(cls)
    c.config_panel.validate.return_value = None
    c.config_panel.get_selected_pixels.return_value = [("A", 0, 0.04)]
    assert c.validate() is True


@pytest.mark.parametrize("cls", ALL)
def test_clear_results_table_resets_state(cls):
    c = _make(cls)
    c.results = [{"a": 1}]
    c.state.results = [{"a": 1}]
    c.state.faults = [{"f": 1}]
    c.clear_results_table()
    assert c.results == []
    assert list(c.state.results) == []
    assert list(c.state.faults) == []
    c.results_panel.clear.assert_called_once()


@pytest.mark.parametrize("cls", ALL)
def test_delete_selected_rows_removes_matching_results(cls):
    c = _make(cls)
    keep, drop = {"pixel": "A"}, {"pixel": "B"}
    c.results = [keep, drop]
    c.state.results = [keep, drop]
    c.results_panel.get_selected_row_tokens.return_value = [id(drop)]

    c.delete_selected_rows()

    assert c.results == [keep]
    c.results_panel.remove_rows_by_tokens.assert_called_once()


@pytest.mark.parametrize("cls", ALL)
def test_delete_selected_rows_noop_without_selection(cls):
    c = _make(cls)
    c.results = [{"pixel": "A"}]
    c.results_panel.get_selected_row_tokens.return_value = []
    c.delete_selected_rows()
    assert len(c.results) == 1
    c.results_panel.remove_rows_by_tokens.assert_not_called()


@pytest.mark.parametrize("cls", ALL)
def test_pixel_faulted_records_fault_and_adds_row(cls):
    c = _make(cls)
    c._on_pixel_faulted("A", 0.04, "SHORT", 1)
    assert len(c.state.faults) == 1
    assert c.state.faults[0]["fault"] == "SHORT"
    c.results_panel.add_result_row.assert_called_once()


@pytest.mark.parametrize("cls", ALL)
def test_progress_update_writes_to_state(cls):
    c = _make(cls)
    c._on_progress_update(42, "halfway")
    assert c.state.progress_percent == 42
    assert c.state.progress_text == "halfway"


@pytest.mark.parametrize("cls", ALL)
def test_pixel_started_sets_active_pixel(cls):
    c = _make(cls)
    c._on_pixel_started("C")
    assert c.state.active_pixel == "C"


@pytest.mark.parametrize("cls", ALL)
def test_set_running_propagates_to_panels(cls):
    c = _make(cls)
    c._set_running(True)
    assert c.state.running is True
    c.config_panel.set_running.assert_called_with(True)
    c.plot_panel.set_running.assert_called_with(True)


@pytest.mark.parametrize("cls", ALL)
def test_abort_requests_abort_on_running_worker(cls):
    c = _make(cls)
    worker = Mock()
    worker.isRunning.return_value = True
    c.worker = worker
    c.abort_measurement()
    worker.request_abort.assert_called_once()


@pytest.mark.parametrize("cls", ALL)
def test_abort_is_noop_without_worker(cls):
    c = _make(cls)
    c.worker = None
    c.abort_measurement()  # must not raise


@pytest.mark.parametrize("cls", ALL)
def test_sweep_finished_updates_state_and_reenables_config(cls):
    c = _make(cls)
    c._on_sweep_finished(aborted=False, had_error=False)
    assert c.state.finish_count == 1
    assert c.state.active_pixel == "--"
    assert c.state.running is False


@pytest.mark.parametrize("cls", ALL)
def test_run_measurement_blocked_when_other_mode_running(cls):
    config_panel = Mock()
    config_panel.autosave_table_enabled.return_value = False
    config_panel.autosave_curves_enabled.return_value = False
    config_panel.get_selected_pixels.return_value = [("A", 0, 0.04)]
    config_panel.sample_name.return_value = "s"
    config_panel.validate.return_value = None

    c = cls(
        instrument_manager=Mock(), exporter=Mock(), config_panel=config_panel,
        plot_panel=Mock(), results_panel=Mock(), log_fn=Mock(),
        get_sample_name=Mock(return_value="s"), tabs=Mock(), sweep_tab_index=1,
        parent_widget=Mock(), is_other_mode_running=lambda: True,
    )
    c.run_measurement()
    assert c.worker is None  # never constructed


@pytest.mark.parametrize("cls", ALL)
def test_path_preview_warns_when_autosave_fully_disabled(cls):
    c = _make(cls)
    c._update_path_preview()
    args, kwargs = c.config_panel.set_path_preview.call_args
    assert kwargs.get("is_warning") is True
    assert "Auto-save disabled" in args[0]


@pytest.mark.parametrize("cls", ALL)
def test_save_results_warns_when_nothing_to_save(cls):
    c = _make(cls)
    c.results = []
    c.save_results(auto=False)
    c.log.assert_any_call("WARNING: No results to save")


@pytest.mark.parametrize("cls", ALL)
def test_export_csv_warns_when_no_rows(cls):
    c = _make(cls)
    c.results_panel.has_rows.return_value = False
    c.export_results_csv()
    c.log.assert_any_call("WARNING: No results to export")


# --- Per-mode strings that must NOT be collapsed by the refactor --------

@pytest.mark.parametrize("cls,expected", [
    (JVController, "Sweep complete"),
    (SPOController, "SPO complete"),
    (DITController, "DIT complete"),
])
def test_each_mode_keeps_its_own_completion_message(cls, expected):
    c = _make(cls)
    c._on_sweep_finished(aborted=False, had_error=False)
    c.log.assert_any_call(expected)


@pytest.mark.parametrize("cls,expected", [
    (JVController, "Sweep aborted"),
    (SPOController, "SPO aborted"),
    (DITController, "DIT aborted"),
])
def test_each_mode_keeps_its_own_abort_message(cls, expected):
    c = _make(cls)
    c._on_sweep_finished(aborted=True, had_error=False)
    c.log.assert_any_call(expected)


@pytest.mark.parametrize("cls,method", [
    (JVController, "manifest_path"),
    (SPOController, "manifest_path_spo"),
    (DITController, "manifest_path_dit"),
])
def test_each_mode_uses_its_own_manifest(cls, method):
    """Auto-save summary must point at that mode's own session_summary CSV."""
    c = _make(cls, autosave_table_enabled=True, autosave_curves_enabled=True)
    c.results = [{"pixel": "A"}]
    c._on_sweep_finished(aborted=False, had_error=False)
    assert getattr(c.exporter, method).called
