"""
Handles building output paths and writing per-pixel TXT files and the
summary results table. Pure I/O.

Auto-save uses a different on-disk layout than the manual batch export

  Project_Folder/                  <- exporter.output_dir
  |-- session_summary.csv          <- one persistent file
  |-- raw_curves/                  <- raw_curves_dir(): one .txt per pixel
      |-- SampleA_pixel_A_loop_1_JV.txt
      |-- SampleA_pixel_A_loop_1_JV_(001).txt   <- safe-overwrite suffix.
"""
import csv
import os
import time

import numpy as np

RAW_CURVES_SUBDIR = "raw_curves"
MANIFEST_FILENAME = "session_summary.csv"
MANIFEST_FILENAME_SPO = "session_summary_spo.csv"

# Single source of truth for the "no name given" fallback.
DEFAULT_SAMPLE_NAME = "solar_iv_data"

_MANIFEST_HEADER = [
    "timestamp", "sample_name", "loop", "pixel", "area_cm2",
    "Voc_V", "Jsc_mA_cm2", "FF", "PCE_percent", "Vmpp_V", "Jmp_mA_cm2", "Pmax_mW_cm2",
    "Rs_diode_eq_ohm", "Rsh_diode_eq_ohm", "Rs_derivative_ohm", "Rsh_derivative_ohm",
    "raw_curve_file",
]

_MANIFEST_HEADER_SPO = [
    "timestamp", "sample_name", "loop", "pixel", "area_cm2", "mppt_enabled",
    "hold_voltage_v", "final_voltage_v", "duration_s", "pin_mw_cm2",
    "final_power_mW_cm2", "mean_power_mW_cm2", "final_pce_percent",
    "mean_pce_percent", "raw_curve_file",
]

MANIFEST_FILENAME_DIT = "session_summary_dit.csv"

_MANIFEST_HEADER_DIT = [
    "timestamp", "sample_name", "pixel", "area_cm2",
    "v1_v", "v2_v", "extracted_charge_C", "peak_abs_current_A", "baseline_current_A",
    "raw_curve_file",
]


class ResultsExporter:
    def __init__(self, output_dir, sample_name="Sample", logger=None):
        self.output_dir = output_dir
        self.sample_name = sample_name
        self.logger = logger or (lambda msg: None)

    @staticmethod
    def safe_filename_part(text):
        allowed = []
        for ch in text:
            if ch.isalnum() or ch in ("-", "_"):
                allowed.append(ch)
            elif ch in (" ", ".", "/"):
                allowed.append("_")
        return "".join(allowed).strip("_") or DEFAULT_SAMPLE_NAME

    def _basename(self):
        basename = os.path.basename((self.sample_name or "").strip() or DEFAULT_SAMPLE_NAME)
        root, ext = os.path.splitext(basename)
        if ext:
            basename = root
        return self.safe_filename_part(basename)

    # --- Auto-save ---

    def raw_curves_dir(self, create=True):
        path = os.path.abspath(os.path.join(self.output_dir, RAW_CURVES_SUBDIR))
        if create:
            os.makedirs(path, exist_ok=True)
        return path

    def manifest_path(self):
        return os.path.abspath(os.path.join(self.output_dir, MANIFEST_FILENAME))

    def _unique_raw_curve_filename(self, pixel, loop, probe_disk=True, suffix="JV"):
        """Overwrite naming: {name}_pixel_{p}_loop_{n}_{suffix}.txt, and if
        that exact name already exists in raw_curves/, append _(001), _(002), ... 
        until a free name """
        basename = self._basename()
        pixel_part = self.safe_filename_part(str(pixel))
        stem = f"{basename}_pixel_{pixel_part}_loop_{int(loop)}_{suffix}"

        if not probe_disk:
            return f"{stem}.txt"

        folder = self.raw_curves_dir(create=False)
        candidate = f"{stem}.txt"
        if not os.path.exists(os.path.join(folder, candidate)):
            return candidate
        n = 1
        while True:
            candidate = f"{stem}_({n:03d}).txt"
            if not os.path.exists(os.path.join(folder, candidate)):
                return candidate
            n += 1

    def preview_txt_path(self, pixel, loop=1, suffix="JV"):
        """Generates the same filename as save_pixel_now but w/o writing to disk."""
        filename = self._unique_raw_curve_filename(pixel, loop, probe_disk=True, suffix=suffix)
        return os.path.join(self.raw_curves_dir(create=False), filename)

    def save_curve_now(self, record):
        """Saves a single completed pixel immediately: writes the raw curve 
        to raw_curves/ and appends a row to session_summary.csv (creating 
        it if needed). 

        Saving incrementally prevents data loss if the system crashes mid-sweep.
        """
        filename = self._unique_raw_curve_filename(record["pixel"], record["loop"])
        curve_path = os.path.join(self.raw_curves_dir(), filename)

        V = np.asarray(record["voltage_v"], dtype=float)
        J = np.asarray(record["current_density_ma_cm2"], dtype=float)
        with open(curve_path, "w") as f:
            f.write("# voltage_v\tcurrent_density_mA_cm2\n")
            for voltage, current_density in zip(V, J):
                f.write(f"{voltage:.8g}\t{current_density:.8g}\n")

        return curve_path, filename

    def save_table_row_now(self, record, curve_filename=None):
        """Incremental auto-save of ONE just-completed pixel's row into the
        persistent session_summary.csv.
        """
        manifest_path = self.manifest_path()
        write_header = not os.path.exists(manifest_path)
        with open(manifest_path, "a", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(_MANIFEST_HEADER)
            writer.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                self.sample_name,
                int(record["loop"]),
                record["pixel"],
                f"{record['area_cm2']:.8g}",
                f"{record['Voc']:.8g}",
                f"{record['Jsc']:.8g}",
                f"{record['FF']:.8g}",
                f"{record['PCE']:.8g}",
                f"{record['Vmpp']:.8g}",
                f"{record['Jmpp']:.8g}",
                f"{record['Pmax']:.8g}",
                f"{record.get('Rs_diode_eq', float('nan')):.8g}",
                f"{record.get('Rsh_diode_eq', float('nan')):.8g}",
                f"{record.get('Rs_derivative', float('nan')):.8g}",
                f"{record.get('Rsh_derivative', float('nan')):.8g}",
                curve_filename or "",
            ])

    # --- SPO auto-save: same layout/conventions as JV above, own manifest
    # file and "_SPO" filename suffix. ---

    def manifest_path_spo(self):
        return os.path.abspath(os.path.join(self.output_dir, MANIFEST_FILENAME_SPO))

    def preview_txt_path_spo(self, pixel, loop=1):
        return self.preview_txt_path(pixel, loop, suffix="SPO")

    def save_curve_now_spo(self, record):
        """SPO counterpart of save_curve_now(): writes time_s/voltage_v/
        power_density."""
        filename = self._unique_raw_curve_filename(record["pixel"], record["loop"], suffix="SPO")
        curve_path = os.path.join(self.raw_curves_dir(), filename)

        t = np.asarray(record["time_s"], dtype=float)
        v = np.asarray(record.get("voltage_v", []), dtype=float)
        p = np.asarray(record["power_density_mw_cm2"], dtype=float)
        with open(curve_path, "w") as f:
            f.write("# time_s\tvoltage_v\tpower_density_mW_cm2\n")
            for idx, (time_s, power_density) in enumerate(zip(t, p)):
                voltage_v = v[idx] if idx < len(v) else float("nan")
                f.write(f"{time_s:.8g}\t{voltage_v:.8g}\t{power_density:.8g}\n")

        return curve_path, filename

    def save_table_row_now_spo(self, record, curve_filename=None):
        """SPO counterpart of save_table_row_now(): appends to its own
        session_summary_spo.csv."""
        manifest_path = self.manifest_path_spo()
        write_header = not os.path.exists(manifest_path)
        with open(manifest_path, "a", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(_MANIFEST_HEADER_SPO)
            writer.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                self.sample_name,
                int(record["loop"]),
                record["pixel"],
                f"{record['area_cm2']:.8g}",
                "1" if record.get("mppt_enabled") else "0",
                f"{record['hold_voltage_v']:.8g}",
                f"{record.get('final_voltage_v', record['hold_voltage_v']):.8g}",
                f"{record['time_s'][-1] if record['time_s'] else float('nan'):.8g}",
                f"{record.get('pin_mw_cm2', 100):.8g}",
                f"{record['final_power_density_mw_cm2']:.8g}",
                f"{record['mean_power_density_mw_cm2']:.8g}",
                f"{record.get('final_pce_percent', float('nan')):.8g}",
                f"{record.get('mean_pce_percent', float('nan')):.8g}",
                curve_filename or "",
            ])

    # --- DIT auto-save: same layout/conventions
    # manifest file and "_DIT" filename suffix. ---

    def manifest_path_dit(self):
        return os.path.abspath(os.path.join(self.output_dir, MANIFEST_FILENAME_DIT))

    def preview_txt_path_dit(self, pixel, loop=1):
        return self.preview_txt_path(pixel, loop, suffix="DIT")

    def save_curve_now_dit(self, record):
        """DIT counterpart of save_curve_now(): writes time_s/voltage_v/current_a."""
        filename = self._unique_raw_curve_filename(record["pixel"], record["loop"], suffix="DIT")
        curve_path = os.path.join(self.raw_curves_dir(), filename)

        t = np.asarray(record["time_s"], dtype=float)
        v = np.asarray(record["voltage_v"], dtype=float)
        i = np.asarray(record["current_a"], dtype=float)
        with open(curve_path, "w") as f:
            f.write("# time_s\tvoltage_v\tcurrent_a\n")
            for time_s, voltage, current in zip(t, v, i):
                f.write(f"{time_s:.8g}\t{voltage:.8g}\t{current:.8g}\n")

        return curve_path, filename

    def save_table_row_now_dit(self, record, curve_filename=None):
        """DIT counterpart of save_table_row_now(): appends to its own
        session_summary_dit.csv."""
        manifest_path = self.manifest_path_dit()
        write_header = not os.path.exists(manifest_path)
        with open(manifest_path, "a", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(_MANIFEST_HEADER_DIT)
            writer.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                self.sample_name,
                record["pixel"],
                f"{record['area_cm2']:.8g}",
                f"{record['v1_v']:.8g}",
                f"{record['v2_v']:.8g}",
                f"{record.get('extracted_charge_c', float('nan')):.8g}",
                f"{record.get('peak_abs_current_a', float('nan')):.8g}",
                f"{record.get('baseline_current_a', float('nan')):.8g}",
                curve_filename or "",
            ])

    # --- Manual batch export (Export .TXT / Export .CSV buttons) ---

    def build_txt_path(self, row):
        """Curve file path for manual Export .TXT."""
        filename = self._unique_raw_curve_filename(row["pixel"], row.get("loop", 1))
        return os.path.join(self.raw_curves_dir(), filename)

    def build_results_table_path(self, timestamp):
        basename = self._basename()
        filename = f"{basename}_results_{timestamp}.txt"
        return os.path.join(os.path.abspath(self.output_dir), filename)

    def save_results_table(self, results, timestamp):
        path = self.build_results_table_path(timestamp)
        rows = sorted(
            results,
            key=lambda row: (int(row.get("loop", 1)), int(row.get("channel") or 0)),
        )

        with open(path, "w") as f:
            f.write(
                "# loop\tpixel\tarea_cm2\tVoc_V\tJsc_mA_cm2\tFF\t"
                "PCE_percent\tVmpp_V\tJmp_mA_cm2\tPmax_mW_cm2\t"
                "Rs_diode_eq_ohm\tRsh_diode_eq_ohm\tRs_derivative_ohm\tRsh_derivative_ohm\t"
                "status\n"
            )
            for row in rows:
                f.write(
                    f"{int(row.get('loop', 1))}\t"
                    f"{row['pixel']}\t"
                    f"{row['area_cm2']:.8g}\t"
                    f"{row['Voc']:.8g}\t"
                    f"{row['Jsc']:.8g}\t"
                    f"{row['FF']:.8g}\t"
                    f"{row['PCE']:.8g}\t"
                    f"{row['Vmpp']:.8g}\t"
                    f"{row['Jmpp']:.8g}\t"
                    f"{row['Pmax']:.8g}\t"
                    f"{row.get('Rs_diode_eq', float('nan')):.8g}\t"
                    f"{row.get('Rsh_diode_eq', float('nan')):.8g}\t"
                    f"{row.get('Rs_derivative', float('nan')):.8g}\t"
                    f"{row.get('Rsh_derivative', float('nan')):.8g}\t"
                    "OK\n"
                )
        return path

    def save_results(self, results, auto=False):
        if not results:
            self.logger("WARNING: No results to save")
            return

        saved_paths = []

        try:
            for row in results:
                path = self.build_txt_path(row)
                V = np.asarray(row["voltage_v"], dtype=float)
                I = np.asarray(row["current_a"], dtype=float)
                J = (I / row["area_cm2"]) * 1000

                with open(path, "w") as f:
                    f.write("# voltage_v\tcurrent_density_mA_cm2\n")
                    for voltage, current_density in zip(V, J):
                        f.write(f"{voltage:.8g}\t{current_density:.8g}\n")
                saved_paths.append(path)

            timestamp = time.strftime("%H%M%S")
            table_path = self.save_results_table(results, timestamp)

            mode = "Auto-saved" if auto else "Saved"
            self.logger(
                f"{mode} {len(saved_paths)} JV text file(s) to "
                f"{self.raw_curves_dir(create=False)} and 1 results table "
                f"file to {table_path}"
            )
        except Exception as e:
            self.logger(f"ERROR: could not save TXT files: {e}")
