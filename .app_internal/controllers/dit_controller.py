"""
One full DIT (Dark Injection Transient) run. Everything shared lives in
BaseMeasurementController; this file holds only what's DIT-specific.
"""
import numpy as np

from controllers.base_measurement_controller import BaseMeasurementController
from controllers.dit_worker import DITWorker
from gui.formatting import format_si


class DITController(BaseMeasurementController):

    EXPORT_SUFFIX = "_dit"
    RUN_NOUN = "DIT"
    ALREADY_RUNNING_MSG = "ERROR: a DIT transient is already running"
    CURVE_NOUN_PLURAL = "traces"
    COMPLETION_NOUN = "run"
    PNG_FILENAME_PART = "dit"
    PNG_DIALOG_TITLE = "Export DIT Transient Image"
    CSV_FILENAME_PART = "dit_results"
    # Repetitions live inside a single trace, so there is no outer loop.
    AUTOSAVE_LOG_SHOWS_LOOP = False

    def _get_params(self):
        return self.config_panel.get_dit_params()

    def _make_worker(self, selected, params):
        return DITWorker(self.inst.keithley, self.inst.relay, selected, params)

    def _loop_count(self, params):
        return 1  # DIT has no outer loop concept

    def _prepare_run(self, selected, params):
        self.plot_panel.set_log_y(self.config_panel.log_plot_enabled())

    def _on_pixel_result(self, record):
        self.results.append(record)
        self.state.results.append(record)

        t = np.asarray(record["time_s"], dtype=float)
        current = np.asarray(record["current_a"], dtype=float)
        y = np.abs(current) if self.config_panel.log_plot_enabled() else current
        self.plot_panel.plot_curve(t, y, record["channel"], record["loop"])

        charge = record.get("extracted_charge_c")
        peak_current = record.get("peak_abs_current_a")
        status = "OK" if charge is not None else "NO TRANSITION"
        self.results_panel.add_result_row(
            record["pixel"], record["area_cm2"], record["v1_v"], record["v2_v"],
            charge, peak_current, status, row_token=id(record),
        )

        self.plot_panel.set_active_pixel(record["pixel"])
        self.plot_panel.set_hud_metrics(
            format_si(charge, "C"),
            format_si(peak_current, "A"),
        )
        self._autosave_pixel(record)

    def _add_fault_row(self, fault_entry):
        self.results_panel.add_result_row(
            fault_entry["pixel"], fault_entry["area"], None, None, None, None,
            fault_entry["fault"], row_token=id(fault_entry),
        )
