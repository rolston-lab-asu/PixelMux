"""Background thread that runs one DIT voltage-step transient per selected pixel."""
import time

from PySide6.QtCore import QThread, Signal

from core.dit_math import calculate_dit_metrics
from core.pv_math import check_fault

# OPEN floor for DIT's 100 nA sense range.
DIT_OPEN_THRESHOLD_A = 5e-10
from instruments.keithley2460 import (
    keithley_output_safe,
    keithley_dit_voltage_step,
)
from core.instrument_manager import make_safe
from instruments.numato_relay import (
    RELAY_SETTLE_S,
    numato_relay_token,
    numato_command,
    all_pixels_disconnect,
    connect_pixel,
)


class DITWorker(QThread):
    log = Signal(str)
    pixel_started = Signal(str)
    pixel_result = Signal(dict)
    pixel_faulted = Signal(str, float, str, int)
    finished_sweep = Signal(bool, bool)
    progress_update = Signal(int, str)

    def __init__(self, keithley, relay, selected_pixels, dit_params, parent=None):
        super().__init__(parent)
        self.keithley = keithley
        self.relay = relay
        self.selected_pixels = selected_pixels
        self.params = dit_params
        self._abort = False

    def request_abort(self):
        self._abort = True

    def _total_sequence_count(self):
        reps = int(self.params["repetitions"])
        has_recovery = self.params["recovery_s"] > 0
        return reps * 3 + max(0, reps - 1) * (1 if has_recovery else 0)

    def run(self):
        p = self.params
        measurement_error = False
        total_pixels = len(self.selected_pixels)
        total_sequences = max(1, self._total_sequence_count())

        try:
            for pixel_idx, (pixel, ch, area) in enumerate(self.selected_pixels):
                if self._abort:
                    break

                use_relay = ch is not None
                self.pixel_started.emit(pixel)

                keithley_output_safe(self.keithley)

                if use_relay:
                    relay_token = numato_relay_token(ch)
                    self.log.emit(f"DIT pixel {pixel} on relay channel {ch} ({relay_token})")
                    all_pixels_disconnect(self.relay)
                    time.sleep(RELAY_SETTLE_S)
                    connect_pixel(self.relay, ch)
                    time.sleep(RELAY_SETTLE_S)
                else:
                    self.log.emit(f"DIT {pixel} direct-connected pixel; relay board bypassed")

                sequences_done = [0]

                def on_chunk_progress(_t, _v, _i, pixel=pixel, pixel_idx=pixel_idx):
                    sequences_done[0] += 1
                    percent = int(min(sequences_done[0] / total_sequences, 1.0) * 100)
                    self.progress_update.emit(
                        percent,
                        f"Pixel {pixel} ({pixel_idx + 1}/{total_pixels}) - transient {sequences_done[0]}/{total_sequences}"
                    )

                try:
                    t, v, i = keithley_dit_voltage_step(
                        self.keithley,
                        v1_v=p["v1"], v2_v=p["v2"],
                        hold_v1_s=p["hold1_s"], hold_v2_s=p["hold2_s"],
                        trigger_delay_ms=p["trigger_delay_ms"],
                        integration_time_ms=p["integration_ms"],
                        current_limit_a=p["current_limit_a"],
                        sense_range=p["sense_range"],
                        delay_fudge_ms=p["fudge_ms"],
                        max_points_per_chunk=p["chunk_points"],
                        four_wire=p["four_wire"],
                        autozero=p["autozero"],
                        repetitions=p["repetitions"],
                        recovery_s=p["recovery_s"],
                        progress=on_chunk_progress,
                        should_stop=lambda: self._abort,
                    )
                finally:
                    keithley_output_safe(self.keithley)
                    if use_relay:
                        numato_command(self.relay, f"relay off {numato_relay_token(ch)}")
                        time.sleep(RELAY_SETTLE_S)

                if self._abort:
                    break

                fault = check_fault(
                    i, compliance_a=p["current_limit_a"], open_threshold_a=DIT_OPEN_THRESHOLD_A,
                )
                if fault:
                    self.pixel_faulted.emit(pixel, area, fault, 1)
                    self.log.emit(f"Pixel {pixel} flagged as {fault}")
                    continue

                metrics = calculate_dit_metrics(t, v, i)

                record = {
                    "pixel": pixel,
                    "channel": ch,
                    "loop": 1,
                    "area_cm2": area,
                    "v1_v": p["v1"],
                    "v2_v": p["v2"],
                    "time_s": t.tolist(),
                    "voltage_v": v.tolist(),
                    "current_a": i.tolist(),
                    **metrics,
                }
                self.pixel_result.emit(record)
                charge = metrics.get("extracted_charge_c")
                peak = metrics.get("peak_abs_current_a")
                if charge is not None and peak is not None:
                    self.log.emit(f"DIT {pixel}: charge={charge:.4g} C, peak |I|={peak:.4g} A")
                else:
                    self.log.emit(f"DIT {pixel}: trace too short to extract metrics")

        except Exception as e:
            measurement_error = True
            self.log.emit(f"ERROR: DIT stopped: {e}")
        finally:
            make_safe(self.keithley, self.relay, self.log.emit)
            self.finished_sweep.emit(self._abort, measurement_error)
