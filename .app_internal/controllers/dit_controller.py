"""
DIT pass: validates inputs, starts/stops the DITWorker, routes
its signals into the plot/results panels, and handles the DIT-specific
exports (per-pixel TXT, results table, PNG, CSV).
"""
import os
import time

import numpy as np
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QFileDialog

from controllers.dit_worker import DITWorker
from core.sweep_state import SweepState
from core.exporter import DEFAULT_SAMPLE_NAME
from gui.formatting import format_si


class DITController(QObject):

    def __init__(
        self,
        instrument_manager,
        exporter,
        config_panel,
        plot_panel,
        results_panel,
        log_fn,
        get_sample_name,
        tabs,
        sweep_tab_index,
        parent_widget,
        parent=None,
        is_other_mode_running=None,
    ):
        super().__init__(parent)
        self.inst = instrument_manager
        self.exporter = exporter
        self.config_panel = config_panel
        self.plot_panel = plot_panel
        self.results_panel = results_panel
        self.log = log_fn
        self.get_sample_name = get_sample_name
        self.tabs = tabs
        self.sweep_tab_index = sweep_tab_index
        self.parent_widget = parent_widget
        self._is_other_mode_running = is_other_mode_running

        self.results = []
        self.worker = None
        self.state = SweepState()

        self.plot_panel.set_logger(self.log)
        self.config_panel.observe("run_requested", lambda change: self.run_measurement())
        self.plot_panel.observe("abort_requested", lambda change: self.abort_measurement())
        self.plot_panel.observe("export_png_requested", lambda change: self.export_plot_png())
        self.results_panel.observe("export_txt_requested", lambda change: self.save_results(auto=False))
        self.results_panel.observe("export_csv_requested", lambda change: self.export_results_csv())
        self.results_panel.observe("delete_selected_requested", lambda change: self.delete_selected_rows())
        self.results_panel.observe("clear_table_requested", lambda change: self.clear_results_table())

        self.config_panel.observe("name_changed", self._update_path_preview)
        self.config_panel.observe("autosave_table_toggled", self._update_path_preview)
        self.config_panel.observe("autosave_curves_toggled", self._update_path_preview)
        self.config_panel.observe("layout_changed", self._update_path_preview)

        self.results_panel.set_export_enabled(False)
        self._update_path_preview()

    # --- Transient lifecycle ---

    def validate(self):
        if not self.inst.keithley:
            self.config_panel.flash_alert()
            self.log("ERROR: instruments are not connected")
            return False

        selected = self.config_panel.get_selected_pixels()
        needs_relay = any(channel is not None for _pixel, channel, _area in selected)
        if needs_relay and not self.inst.relay:
            self.config_panel.flash_alert()
            self.log("ERROR: instruments are not connected")
            return False

        err = self.config_panel.validate()
        if err:
            self.log(err)
            return False
        return True

    def run_measurement(self):
        if not self.validate():
            self.tabs.setCurrentIndex(0)
            return

        if self._is_other_mode_running is not None and self._is_other_mode_running():
            self.log("ERROR: another mode is currently running a measurement -- wait for it to finish")
            return

        if self.worker is not None and self.worker.isRunning():
            self.log("ERROR: a DIT transient is already running")
            return

        selected = self.config_panel.get_selected_pixels()
        if not selected:
            self.log("ERROR: select at least one pixel")
            return

        self.plot_panel.reset_for_new_run()
        self.plot_panel.set_log_y(self.config_panel.log_plot_enabled())

        dit_params = self.config_panel.get_dit_params()
        self.plot_panel.prepare_legends(selected, 1)
        self._set_running(True)

        # Pass the active hardware connections to the background thread.
        self.worker = DITWorker(self.inst.keithley, self.inst.relay, selected, dit_params)
        self.worker.log.connect(self._on_log)
        self.worker.pixel_started.connect(self._on_pixel_started)
        self.worker.pixel_result.connect(self._on_pixel_result)
        self.worker.pixel_faulted.connect(self._on_pixel_faulted)
        self.worker.finished_sweep.connect(self._on_sweep_finished)
        self.worker.progress_update.connect(self._on_progress_update)
        self.tabs.setCurrentIndex(self.sweep_tab_index)
        self.worker.start()

    def abort_measurement(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_abort()
            self.log("Abort requested")

    def _set_running(self, running):
        self.state.running = running
        self.config_panel.set_running(running)
        self.plot_panel.set_running(running)

    # --- Worker signal slots ---

    def _on_log(self, message):
        self.state.log_lines.append(message)
        self.log(message)

    def _on_pixel_started(self, pixel):
        self.state.active_pixel = pixel
        self._update_path_preview()

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

        # Incremental auto-save & write THIS pixel's result immediately.
        saved_curve = False
        saved_table = False
        curve_filename = None

        if self.config_panel.autosave_curves_enabled():
            self.exporter.sample_name = self.get_sample_name() or DEFAULT_SAMPLE_NAME
            try:
                _curve_path, curve_filename = self.exporter.save_curve_now_dit(record)
                saved_curve = True
            except Exception as e:
                self.log(f"ERROR: could not auto-save curve for pixel {record['pixel']}: {e}")

        if self.config_panel.autosave_table_enabled():
            self.exporter.sample_name = self.get_sample_name() or DEFAULT_SAMPLE_NAME
            try:
                self.exporter.save_table_row_now_dit(record, curve_filename)
                saved_table = True
            except Exception as e:
                self.log(f"ERROR: could not auto-save table row for pixel {record['pixel']}: {e}")

        if saved_curve and saved_table:
            self.log(f"OK: Auto-saved pixel {record['pixel']}")
        elif saved_curve:
            self.log(f"OK: Auto-saved curve for pixel {record['pixel']}")
        elif saved_table:
            self.log(f"OK: Auto-saved table row for pixel {record['pixel']}")

        self._update_path_preview()

    def _on_pixel_faulted(self, pixel, area, fault, loop_number):
        fault_entry = {"pixel": pixel, "area": area, "fault": fault, "loop": loop_number}
        self.state.faults.append(fault_entry)
        self.results_panel.add_result_row(
            pixel, area, None, None, None, None, fault, row_token=id(fault_entry),
        )

    def _on_sweep_finished(self, aborted, had_error):
        self.state.finished_aborted = aborted
        self.state.finished_had_error = had_error
        self.state.finish_count += 1
        self.state.active_pixel = "--"

        self._set_running(False)

        if aborted:
            self.log("DIT aborted")
        elif had_error:
            self.log("DIT ended with an error")
        else:
            self.log("DIT complete")

        if self.results:
            table_on = self.config_panel.autosave_table_enabled()
            curves_on = self.config_panel.autosave_curves_enabled()
            if table_on and curves_on:
                self.log(
                    f"Auto-save complete: {len(self.results)} pixel result(s) "
                    f"written to {self.exporter.manifest_path_dit()}"
                )
            elif curves_on:
                self.log(
                    f"Auto-save complete: {len(self.results)} curve file(s) "
                    f"written to {self.exporter.raw_curves_dir(create=False)} "
                    f"(table not auto-saved)"
                )
            elif table_on:
                self.log(
                    f"Auto-save complete: {len(self.results)} row(s) written "
                    f"to {self.exporter.manifest_path_dit()} (curves not auto-saved)"
                )
            else:
                self.log("Results kept in memory -- export from the Results tab when ready")

        self.results_panel.set_export_enabled(bool(self.results))
        self._update_path_preview()

    def _on_progress_update(self, percent, text):
        self.state.progress_percent = percent
        self.state.progress_text = text

    # --- Results table management (row delete / full clear) ---

    def delete_selected_rows(self):
        tokens = self.results_panel.get_selected_row_tokens()
        if not tokens:
            return
        token_set = set(tokens)

        kept_results = [r for r in self.results if id(r) not in token_set]
        removed = len(self.results) - len(kept_results)
        self.results = kept_results
        self.state.results = list(self.results)

        kept_faults = [f for f in self.state.faults if id(f) not in token_set]
        removed += len(self.state.faults) - len(kept_faults)
        self.state.faults = kept_faults

        self.results_panel.remove_rows_by_tokens(tokens)
        self.results_panel.set_export_enabled(bool(self.results))
        self.log(f"Removed {removed} row(s) from the results table")

    def clear_results_table(self):
        self.results = []
        self.state.results = []
        self.state.faults = []
        self.results_panel.clear()
        self.results_panel.set_export_enabled(False)
        self.log("Results table cleared")

    # --- Output directory / exports ---

    def set_output_dir(self, path):
        self.exporter.output_dir = path
        self._update_path_preview()

    def _update_path_preview(self, change=None):
        panel = self.config_panel
        table_on = panel.autosave_table_enabled()
        curves_on = panel.autosave_curves_enabled()

        if not table_on and not curves_on:
            panel.set_path_preview(
                "\u26A0\uFE0F Auto-save disabled. Use the \"Results\" tab to "
                "manually export raw traces (.txt) and results table (.csv) "
                "once the run completes.",
                is_warning=True,
            )
            return

        active = self.state.active_pixel
        pixel = active if active and active != "--" else None
        if pixel is None:
            selected = panel.get_selected_pixels()
            pixel = selected[0][0] if selected else None

        if pixel is None:
            panel.set_path_preview("Select at least one pixel to preview the save path.", is_warning=False)
            return

        self.exporter.sample_name = panel.sample_name() or DEFAULT_SAMPLE_NAME

        if table_on and curves_on:
            path = self.exporter.preview_txt_path_dit(pixel)
            panel.set_path_preview(f"Auto-saving to: {path}", is_warning=False)
        elif curves_on:
            path = self.exporter.preview_txt_path_dit(pixel)
            panel.set_path_preview(
                f"Auto-saving curve to: {path} (table not auto-saved)", is_warning=False,
            )
        else:
            path = self.exporter.manifest_path_dit()
            panel.set_path_preview(
                f"Auto-saving table row to: {path} (curves not auto-saved)", is_warning=False,
            )

    def save_results(self, auto=False):
        if not self.results:
            if not auto:
                self.log("WARNING: No results to save")
            return

        self.exporter.sample_name = self.get_sample_name() or DEFAULT_SAMPLE_NAME

        if not auto:
            chosen_dir = QFileDialog.getExistingDirectory(
                self.parent_widget, "Choose Folder to Save TXT Results", self.exporter.output_dir,
                QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
            )
            if not chosen_dir:
                return  # user cancelled
            self.exporter.output_dir = chosen_dir

        try:
            for record in self.results:
                self.exporter.save_curve_now_dit(record)
            self.log(f"Saved {len(self.results)} DIT text file(s) to {self.exporter.raw_curves_dir(create=False)}")
        except Exception as e:
            self.log(f"ERROR: could not save TXT files: {e}")

    def export_plot_png(self):
        try:
            import pyqtgraph.exporters

            self.exporter.sample_name = self.get_sample_name() or DEFAULT_SAMPLE_NAME
            folder = os.path.abspath(self.exporter.output_dir)
            timestamp = time.strftime("%H%M%S")
            basename = self.exporter._basename()
            suggested_path = os.path.join(folder, f"{basename}_dit_{timestamp}.png")

            path, _ = QFileDialog.getSaveFileName(
                self.parent_widget, "Export DIT Transient Image", suggested_path, "PNG Image (*.png)"
            )
            if not path:
                return  # user cancelled

            image_exporter = pyqtgraph.exporters.ImageExporter(self.plot_panel.plot_manager.plot.getPlotItem())
            image_exporter.parameters()["width"] = 1600
            image_exporter.export(path)
            self.log(f"OK: Exported plot image to {path}")
        except Exception as e:
            self.log(f"ERROR: could not export plot image: {e}")

    def export_results_csv(self):
        if not self.results_panel.has_rows():
            self.log("WARNING: No results to export")
            return

        try:
            import csv

            self.exporter.sample_name = self.get_sample_name() or DEFAULT_SAMPLE_NAME
            folder = os.path.abspath(self.exporter.output_dir)
            timestamp = time.strftime("%H%M%S")
            basename = self.exporter._basename()
            suggested_path = os.path.join(folder, f"{basename}_dit_results_{timestamp}.csv")

            path, _ = QFileDialog.getSaveFileName(
                self.parent_widget, "Export Results CSV", suggested_path, "CSV File (*.csv)"
            )
            if not path:
                return  # user cancelled

            headers, rows = self.results_panel.get_export_data()
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for row in rows:
                    writer.writerow(row)
            self.log(f"OK: Exported {len(rows)} row(s) to {path}")
        except Exception as e:
            self.log(f"ERROR: could not export CSV: {e}")
