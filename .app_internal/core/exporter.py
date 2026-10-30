"""Output paths, run IDs, and TXT/CSV writers for measurement results."""
import csv
import os
import re
import time

import numpy as np

RAW_CURVES_SUBDIR = "raw_curves"
MANIFEST_FILENAME = "session_summary.csv"
MANIFEST_FILENAME_SPO = "session_summary_spo.csv"

DEFAULT_SAMPLE_NAME = "solar_iv_data"

_MANIFEST_HEADER = [
    "run_id", "timestamp", "sample_name", "loop", "pixel", "area_cm2",
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
        self._run_id_folder = None
        self._last_run_id = 0

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


    def raw_curves_dir(self, create=True):
        path = os.path.abspath(os.path.join(self.output_dir, RAW_CURVES_SUBDIR))
        if create:
            os.makedirs(path, exist_ok=True)
        return path

    def manifest_path(self):
        return os.path.abspath(os.path.join(self.output_dir, MANIFEST_FILENAME))


    def _sync_run_ids(self):
        folder = os.path.abspath(self.output_dir)
        if folder == self._run_id_folder:
            return
        ids = [0]
        curves = self.raw_curves_dir(create=False)
        if os.path.isdir(curves):
            for name in os.listdir(curves):
                match = re.search(r"_(\d+)_pixel_", name)
                if match:
                    ids.append(int(match.group(1)))
        if os.path.exists(self.manifest_path()):
            with open(self.manifest_path(), newline="") as f:
                ids += [int(row["run_id"]) for row in csv.DictReader(f) if (row.get("run_id") or "").isdigit()]
        self._run_id_folder = folder
        self._last_run_id = max(ids)

    def peek_run_id(self):
        self._sync_run_ids()
        return self._last_run_id + 1

    def next_run_id(self):
        self._sync_run_ids()
        self._last_run_id += 1
        return self._last_run_id

    def _unique_raw_curve_filename(self, pixel, loop, probe_disk=True, suffix="JV", run_id=None):
        basename = self._basename()
        if run_id is not None:
            basename = f"{basename}_{int(run_id):03d}"
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

    def preview_txt_path(self, pixel, loop=1, suffix="JV", run_id=None):
        filename = self._unique_raw_curve_filename(pixel, loop, probe_disk=True, suffix=suffix, run_id=run_id)
        return os.path.join(self.raw_curves_dir(create=False), filename)

    def save_curve_now(self, record):
        filename = self._unique_raw_curve_filename(record["pixel"], record["loop"], run_id=record.get("run_id"))
        curve_path = os.path.join(self.raw_curves_dir(), filename)

        V = np.asarray(record["voltage_v"], dtype=float)
        J = np.asarray(record["current_density_ma_cm2"], dtype=float)
        with open(curve_path, "w") as f:
            f.write("# voltage_v\tcurrent_density_mA_cm2\n")
            for voltage, current_density in zip(V, J):
                f.write(f"{voltage:.8g}\t{current_density:.8g}\n")

        return curve_path, filename

    def save_table_row_now(self, record, curve_filename=None):
        manifest_path = self.manifest_path()
        write_header = not os.path.exists(manifest_path)
        if not write_header:
            _add_run_id_column(manifest_path)
        with open(manifest_path, "a", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(_MANIFEST_HEADER)
            writer.writerow([
                record.get("run_id", ""),
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


    def manifest_path_spo(self):
        return os.path.abspath(os.path.join(self.output_dir, MANIFEST_FILENAME_SPO))

    def preview_txt_path_spo(self, pixel, loop=1):
        return self.preview_txt_path(pixel, loop, suffix="SPO")

    def save_curve_now_spo(self, record):
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


    def manifest_path_dit(self):
        return os.path.abspath(os.path.join(self.output_dir, MANIFEST_FILENAME_DIT))

    def preview_txt_path_dit(self, pixel, loop=1):
        return self.preview_txt_path(pixel, loop, suffix="DIT")

    def save_curve_now_dit(self, record):
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


    def build_txt_path(self, row):
        filename = self._unique_raw_curve_filename(row["pixel"], row.get("loop", 1), run_id=row.get("run_id"))
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
                "# run_id\tloop\tpixel\tarea_cm2\tVoc_V\tJsc_mA_cm2\tFF\t"
                "PCE_percent\tVmpp_V\tJmp_mA_cm2\tPmax_mW_cm2\t"
                "Rs_diode_eq_ohm\tRsh_diode_eq_ohm\tRs_derivative_ohm\tRsh_derivative_ohm\t"
                "status\n"
            )
            for row in rows:
                f.write(
                    f"{row.get('run_id', '')}\t"
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


def _add_run_id_column(path):
    with open(path, newline="") as f:
        if f.readline().startswith("run_id,"):
            return
        f.seek(0)
        rows = list(csv.reader(f))
    if not rows:
        return
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["run_id"] + rows[0])
        writer.writerows([""] + row for row in rows[1:])
    os.replace(tmp, path)
