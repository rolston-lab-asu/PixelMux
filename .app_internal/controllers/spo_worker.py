"""
Background SPO worker (QThread): holds each selected pixel at a fixed
voltage and samples current at a fixed interval for a fixed duration,
computing power density over time.
"""
import time

import numpy as np
from PySide6.QtCore import QThread, Signal

from core.pv_math import check_fault
from instruments.keithley2460 import (
    init_keithley,
    keithley_output_safe,
    keithley_output_enable,
    keithley_read_current,
)
from instruments.numato_relay import (
    RELAY_SETTLE_S,
    numato_relay_token,
    numato_command,
    all_pixels_disconnect,
    connect_pixel,
)


class SPOWorker(QThread):
    """Runs one full SPO run (all loops x all selected pixels) off the GUI thread."""

    log = Signal(str)
    pixel_started = Signal(str)
    pixel_result = Signal(dict)                     # successful pixel/loop -> full record
    pixel_faulted = Signal(str, float, str, int)    # pixel, area, fault, loop_number
    finished_sweep = Signal(bool, bool)             # (aborted, had_error)
    progress_update = Signal(int, str)              # (percent_0_to_100, text)

    def __init__(self, keithley, relay, selected_pixels, spo_params, parent=None):
        super().__init__(parent)
        self.keithley = keithley
        self.relay = relay
        self.selected_pixels = selected_pixels  # list of (pixel_label, channel, area_cm2)
        # spo_params keys: hold_v, duration_s, interval_s, compliance_a, loops
        self.params = spo_params
        self._abort = False

    def request_abort(self):
        self._abort = True

    def run(self):
        p = self.params
        measurement_error = False

        try:
            init_keithley(self.keithley, compliance_a=p["compliance_a"], logger=self.log.emit)
            self.log.emit(f"Keithley current compliance set to {p['compliance_a']:.6f} A")

            for loop_idx in range(p["loops"]):
                if self._abort:
                    break
                self.log.emit(f"Starting SPO loop {loop_idx + 1} of {p['loops']}")

                for pixel, ch, area in self.selected_pixels:
                    if self._abort:
                        break

                    use_relay = ch is not None
                    self.pixel_started.emit(pixel)
      
                    keithley_output_safe(self.keithley)

                    if use_relay:
                        relay_token = numato_relay_token(ch)
                        self.log.emit(f"SPO pixel {pixel} on relay channel {ch} ({relay_token})")
                        all_pixels_disconnect(self.relay)
                        time.sleep(RELAY_SETTLE_S)
                        connect_pixel(self.relay, ch)
                        time.sleep(RELAY_SETTLE_S)
                    else:
                        self.log.emit(f"SPO {pixel} direct-connected pixel; relay board bypassed")

                    keithley_output_enable(self.keithley, logger=self.log.emit)

                    # --- CONSTANT-VOLTAGE HOLD LOOP ---
                    start_time = time.monotonic()
                    times = []
                    currents = []
                    voltages = []
                    while not self._abort:
                        elapsed = time.monotonic() - start_time
                        if elapsed > p["duration_s"] and times:
                            break

                        current, _raw, keithley_v = keithley_read_current(self.keithley, p["hold_v"], 0.0)
                        times.append(elapsed)
                        currents.append(current)
                        voltages.append(keithley_v)

                        percent = int(min(elapsed / p["duration_s"], 1.0) * 100)
                        self.progress_update.emit(
                            percent,
                            f"Pixel {pixel} - {elapsed:.1f}s/{p['duration_s']:.0f}s - Loop {loop_idx + 1}/{p['loops']}"
                        )

                        remaining = p["interval_s"] - (time.monotonic() - start_time - elapsed)
                        if remaining > 0:
                            time.sleep(remaining)

                    # --- POST-HOLD SAFE STATE ---
                    keithley_output_safe(self.keithley)
                    if use_relay:
                        numato_command(self.relay, f"relay off {numato_relay_token(ch)}")
                        time.sleep(RELAY_SETTLE_S)

                    if self._abort:
                        break

                    t = np.asarray(times, dtype=float)
                    i = np.asarray(currents, dtype=float)
                    v_keithley = np.asarray(voltages, dtype=float)

                    fault = check_fault(i)
                    if fault:
                        self.pixel_faulted.emit(pixel, area, fault, loop_idx + 1)
                        self.log.emit(f"Pixel {pixel} flagged as {fault}")
                        continue

                    j_pv = (-i / area) * 1000.0
                    p_density = p["hold_v"] * j_pv
                    final_power = float(p_density[-1]) if len(p_density) else float("nan")
                    mean_power = float(np.nanmean(p_density)) if len(p_density) else float("nan")

                    record = {
                        "pixel": pixel,
                        "channel": ch,
                        "loop": loop_idx + 1,
                        "area_cm2": area,
                        "hold_voltage_v": p["hold_v"],
                        "time_s": t.tolist(),
                        "keithley_voltage_v": v_keithley.tolist(),
                        "current_a": i.tolist(),
                        "power_density_mw_cm2": p_density.tolist(),
                        "final_power_density_mw_cm2": final_power,
                        "mean_power_density_mw_cm2": mean_power,
                    }
                    self.pixel_result.emit(record)
                    self.log.emit(
                        f"SPO {pixel}: final={final_power:.3f} mW/cm\u00b2, mean={mean_power:.3f} mW/cm\u00b2"
                    )

        except Exception as e:
            measurement_error = True
            self.log.emit(f"ERROR: SPO stopped: {e}")
        finally:
            try:
                keithley_output_safe(self.keithley)
                if self.relay is not None:
                    all_pixels_disconnect(self.relay)
            except Exception:
                pass
            self.finished_sweep.emit(self._abort, measurement_error)
