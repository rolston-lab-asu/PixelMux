"""Background thread that runs JV sweeps across the selected pixels and loops."""
import time

import numpy as np
from PySide6.QtCore import QThread, Signal

from core.pv_math import full_iv_report, check_fault
from instruments.keithley2460 import (
    init_keithley,
    keithley_output_safe,
    keithley_output_enable,
    keithley_read_current,
    keithley_source_voltage,
)
from core.instrument_manager import make_safe
from instruments.numato_relay import (
    RELAY_SETTLE_S,
    numato_relay_token,
    numato_command,
    all_pixels_disconnect,
    connect_pixel,
)


class MeasurementWorker(QThread):
    log = Signal(str)
    pixel_started = Signal(str)
    pixel_result = Signal(dict)
    pixel_faulted = Signal(str, float, str, int)
    finished_sweep = Signal(bool, bool)
    progress_update = Signal(int, str)

    def __init__(self, keithley, relay, selected_pixels, sweep_params, parent=None):
        super().__init__(parent)
        self.keithley = keithley
        self.relay = relay
        self.selected_pixels = selected_pixels
        self.params = sweep_params
        self._abort = False

    def request_abort(self):
        self._abort = True

    def _log_current_outliers(self, pixel, V, I, area):
        if len(I) < 5:
            return
        J = np.abs((I / area) * 1000)
        finite = np.isfinite(J)
        if not np.any(finite):
            return
        median = np.nanmedian(J[finite])
        peak_idx = int(np.nanargmax(J))
        peak = J[peak_idx]
        if median > 0 and peak > max(5 * median, 50):
            self.log.emit(
                f"WARNING: {pixel} current-density spike at {V[peak_idx]:.3f} V: "
                f"{peak:.2f} mA/cm\u00b2 vs median {median:.2f} mA/cm\u00b2"
            )

    def run(self):
        p = self.params
        measurement_error = False

        try:
            init_keithley(self.keithley, compliance_a=p["compliance_a"], logger=self.log.emit)
            self.log.emit(f"Keithley current compliance set to {p['compliance_a']:.6f} A")

            for loop_idx in range(p["loops"]):
                if self._abort:
                    break
                self.log.emit(f"Starting loop {loop_idx + 1} of {p['loops']}")

                for pixel, ch, area in self.selected_pixels:
                    if self._abort:
                        break

                    use_relay = ch is not None

                    self.pixel_started.emit(pixel)


                    keithley_output_safe(self.keithley)

                    if use_relay:
                        relay_token = numato_relay_token(ch)
                        self.log.emit(f"Measuring pixel {pixel} on relay channel {ch} ({relay_token})")
                        all_pixels_disconnect(self.relay)
                        time.sleep(RELAY_SETTLE_S)
                        connect_pixel(self.relay, ch)
                        time.sleep(RELAY_SETTLE_S)
                    else:
                        self.log.emit(f"Measuring {pixel} direct-connected pixel; relay board bypassed")

                    keithley_output_enable(self.keithley, logger=self.log.emit)

                    sweep_start, sweep_end = (p["v1"], p["v0"]) if p["reverse"] else (p["v0"], p["v1"])
                    V = np.linspace(sweep_start, sweep_end, p["points"])
                    V_keithley = []
                    I = []
                    self.log.emit(
                        f"Sweep {pixel} device voltage: {sweep_start:.3f} V -> {sweep_end:.3f} V "
                        f"({p['points']} points, {'reverse' if p['reverse'] else 'forward'})"
                    )

                    total_points_in_pixel = len(V)
                    for point_idx, v in enumerate(V):
                        if self._abort:
                            break

                        percent = int(((point_idx + 1) / total_points_in_pixel) * 100)
                        self.progress_update.emit(
                            percent, 
                            f"Pixel {pixel} - Point {point_idx + 1}/{total_points_in_pixel} - Loop {loop_idx + 1}/{p['loops']}"
                        )

                        current, raw, keithley_v = keithley_read_current(
                            self.keithley, v, p["point_delay_s"]
                        )
                        V_keithley.append(keithley_v)


                        if point_idx == 0:
                            self.log.emit(f"First raw Keithley current response for {pixel}: {raw}")
                        if point_idx in {0, len(V) // 2, len(V) - 1}:
                            try:
                                source_check = keithley_source_voltage(self.keithley)
                                self.log.emit(
                                    f"{pixel} source check point {point_idx + 1}: "
                                    f"device {v:.4f} V, Keithley command {keithley_v:.4f} V, "
                                    f"Keithley setpoint {source_check:.4f} V"
                                )
                            except Exception as e:
                                self.log.emit(f"WARNING: could not query Keithley source voltage: {e}")
                        I.append(current)


                    keithley_output_safe(self.keithley)
                    if use_relay:
                        numato_command(self.relay, f"relay off {numato_relay_token(ch)}")
                        time.sleep(RELAY_SETTLE_S)

                    if self._abort:
                        break

                    I = np.asarray(I, dtype=float)
                    V_keithley = np.asarray(V_keithley, dtype=float)
                    self._log_current_outliers(pixel, V, I, area)


                    fault = check_fault(I, compliance_a=p["compliance_a"], V=V)
                    if fault:
                        self.pixel_faulted.emit(pixel, area, fault, loop_idx + 1)
                        self.log.emit(f"Pixel {pixel} flagged as {fault}")
                        continue

                    metrics = full_iv_report(V, I, area, p["pin"])
                    J = (I / area) * 1000

                    record = {
                        "pixel": pixel,
                        "channel": ch,
                        "loop": loop_idx + 1,
                        "area_cm2": area,
                        "pin_mw_cm2": p["pin"],
                        "voltage_v": V.tolist(),
                        "keithley_voltage_v": V_keithley.tolist(),
                        "current_a": I.tolist(),
                        "current_density_ma_cm2": J.tolist(),
                        **metrics,
                    }
                    self.pixel_result.emit(record)
                    self.log.emit(
                        f"Pixel {pixel}: Voc={metrics['Voc']:.3f} V, "
                        f"Jsc={metrics['Jsc']:.3f} mA/cm\u00b2, "
                        f"PCE={metrics['PCE']:.2f}%"
                    )

        except Exception as e:
            measurement_error = True
            self.log.emit(f"ERROR: measurement stopped: {e}")
        finally:
            make_safe(self.keithley, self.relay, self.log.emit)
            self.finished_sweep.emit(self._abort, measurement_error)
