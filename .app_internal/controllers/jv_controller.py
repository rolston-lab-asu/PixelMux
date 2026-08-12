"""
One full JV sweep. Everything shared lives in BaseMeasurementController; 
this file holds only what's JV-specific.
"""
import numpy as np

from controllers.base_measurement_controller import BaseMeasurementController
from controllers.jv_worker import MeasurementWorker
from gui.formatting import format_metric

_METRIC_KEYS = (
    "Voc", "Jsc", "Vmpp", "Jmpp", "Pmax", "FF", "PCE",
    "Rs_diode_eq", "Rsh_diode_eq", "Rs_derivative", "Rsh_derivative",
)


class JVController(BaseMeasurementController):

    EXPORT_SUFFIX = ""  # JV owns the exporter's unsuffixed methods
    RUN_NOUN = "Sweep"
    ALREADY_RUNNING_MSG = "ERROR: a sweep is already running"
    CURVE_NOUN_PLURAL = "curves"
    COMPLETION_NOUN = "sweep"
    PNG_FILENAME_PART = "ivcurve"
    PNG_DIALOG_TITLE = "Export IV Curve Image"
    CSV_FILENAME_PART = "results"

    def _get_params(self):
        return self.config_panel.get_sweep_params()

    def _make_worker(self, selected, params):
        return MeasurementWorker(self.inst.keithley, self.inst.relay, selected, params)

    def _on_pixel_result(self, record):
        self.results.append(record)
        self.state.results.append(record)
        V = np.asarray(record["voltage_v"], dtype=float)
        J = np.asarray(record["current_density_ma_cm2"], dtype=float)
        self.plot_panel.plot_curve(V, J, record["channel"], record["loop"])

        metrics = {k: record[k] for k in _METRIC_KEYS}
        self.results_panel.add_result_row(
            record["pixel"], record["area_cm2"], metrics, "OK", record["loop"],
            row_token=id(record),
        )

        self.plot_panel.set_active_pixel(record["pixel"])
        self.plot_panel.set_hud_metrics(
            format_metric(metrics["Voc"], 3),
            format_metric(metrics["Jsc"], 2),
            format_metric(metrics["PCE"], 2),
            format_metric(metrics["FF"], 2),
        )
        self._autosave_pixel(record)

    def _add_fault_row(self, fault_entry):
        self.results_panel.add_result_row(
            fault_entry["pixel"], fault_entry["area"], None, fault_entry["fault"],
            fault_entry["loop"], row_token=id(fault_entry),
        )

    def _write_all_results(self, auto):
        # JV has its own batch writer on the exporter.
        self.exporter.save_results(self.results, auto=auto)
