"""
One full SPO hold. Everything shared lives in BaseMeasurementController; this
file holds only what's SPO-specific.
"""
import numpy as np

from controllers.base_measurement_controller import BaseMeasurementController
from controllers.spo_worker import SPOWorker
from gui.formatting import format_metric


class SPOController(BaseMeasurementController):

    EXPORT_SUFFIX = "_spo"
    RUN_NOUN = "SPO"
    ALREADY_RUNNING_MSG = "ERROR: an SPO hold is already running"
    CURVE_NOUN_PLURAL = "curves"
    COMPLETION_NOUN = "hold"
    PNG_FILENAME_PART = "spo"
    PNG_DIALOG_TITLE = "Export SPO Curve Image"
    CSV_FILENAME_PART = "spo_results"

    def _get_params(self):
        return self.config_panel.get_spo_params()

    def _make_worker(self, selected, params):
        return SPOWorker(self.inst.keithley, self.inst.relay, selected, params)

    def _on_pixel_result(self, record):
        self.results.append(record)
        self.state.results.append(record)
        t = np.asarray(record["time_s"], dtype=float)
        voltage = np.asarray(record.get("voltage_v", []), dtype=float)
        power_density = np.asarray(record["power_density_mw_cm2"], dtype=float)
        self.plot_panel.plot_curve(t, voltage, power_density, record["channel"], record["loop"])

        final_power = record["final_power_density_mw_cm2"]
        mean_power = record["mean_power_density_mw_cm2"]
        self.results_panel.add_result_row(
            record["pixel"], record["area_cm2"], final_power, mean_power, "OK", record["loop"],
            row_token=id(record), final_v=record.get("final_voltage_v"),
            final_pce=record.get("final_pce_percent"),
        )

        self.plot_panel.set_active_pixel(record["pixel"])
        self.plot_panel.set_hud_metrics(
            format_metric(final_power, 3),
            format_metric(mean_power, 3),
        )
        self._autosave_pixel(record)

    def _add_fault_row(self, fault_entry):
        self.results_panel.add_result_row(
            fault_entry["pixel"], fault_entry["area"], None, None, fault_entry["fault"],
            fault_entry["loop"], row_token=id(fault_entry),
        )
