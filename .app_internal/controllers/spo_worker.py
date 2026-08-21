"""
Background SPO worker (QThread): holds each selected pixel at a fixed
voltage (or actively tracks its maximum power point via perturb-and-
observe) and samples current at a fixed interval for a fixed duration,
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
        # spo_params keys: hold_v, duration_s, interval_s, compliance_a, loops,
        # mppt_enabled, and (when mppt_enabled) start_v, step_v, min_step_v,
        # step_decay, settle_s, v_min, v_max -- see SPOConfigPanel.get_spo_params().
        self.params = spo_params
        self._abort = False

    def request_abort(self):
        self._abort = True

    # --- Hold-loop strategies ---

    def _run_fixed_hold(self, pixel, loop_idx, p):
        """Sit at a single fixed voltage for the whole
        duration and just sample current at each interval."""
        start_time = time.monotonic()
        times, currents, device_v, raw_keithley_v = [], [], [], []

        while not self._abort:
            elapsed = time.monotonic() - start_time
            if elapsed > p["duration_s"] and times:
                break

            current, _raw, keithley_v = keithley_read_current(self.keithley, p["hold_v"], 0.0)
            times.append(elapsed)
            currents.append(current)
            device_v.append(p["hold_v"])
            raw_keithley_v.append(keithley_v)

            percent = int(min(elapsed / p["duration_s"], 1.0) * 100)
            self.progress_update.emit(
                percent,
                f"Pixel {pixel} - {elapsed:.1f}s/{p['duration_s']:.0f}s - Loop {loop_idx + 1}/{p['loops']}"
            )

            remaining = p["interval_s"] - (time.monotonic() - start_time - elapsed)
            if remaining > 0:
                time.sleep(remaining)

        return times, currents, device_v, raw_keithley_v

    def _run_mppt_hold(self, pixel, loop_idx, p):
        """Adaptive-step perturb-and-observe (P&O) MPP tracking hold.

        Samples current every `interval_s`, but only *evaluates* and
        *steps* the bias every `settle_samples` samples.

        On each evaluation:
          - if power increased since the last evaluation, keep stepping in
            the same direction at the same step size (found a good direction).
          - if power decreased, reverse direction and shrink the step size by
            `step_decay`, floored at `min_step_v` so it never fully stalls.
        Voltage is clamped to [v_min, v_max] the whole time so a
        pixel can't get walked toward compliance indefinitely.
        """
        start_time = time.monotonic()
        times, currents, device_v, raw_keithley_v = [], [], [], []

        target_v = p["start_v"]
        step = p["step_v"]
        min_step = p["min_step_v"]
        step_decay = p.get("step_decay", 0.5)
        v_min, v_max = p["v_min"], p["v_max"]

        # Settle window: wait this many *samples* after each perturbation
        # before trusting the power reading for the next P&O decision.
        settle_s = p.get("settle_s", 2 * p["interval_s"])
        settle_samples = max(1, round(settle_s / p["interval_s"]))

        prev_power = None
        samples_since_step = 0
        area = p.get("_area_cm2")

        while not self._abort:
            elapsed = time.monotonic() - start_time
            if elapsed > p["duration_s"] and times:
                break

            applied_v = max(v_min, min(v_max, target_v))
            current, _raw, keithley_v = keithley_read_current(self.keithley, applied_v, 0.0)
            times.append(elapsed)
            currents.append(current)
            device_v.append(applied_v)
            raw_keithley_v.append(keithley_v)

            percent = int(min(elapsed / p["duration_s"], 1.0) * 100)
            self.progress_update.emit(
                percent,
                f"Pixel {pixel} - {elapsed:.1f}s/{p['duration_s']:.0f}s - "
                f"Loop {loop_idx + 1}/{p['loops']} - tracking {applied_v:.3f} V"
            )

            samples_since_step += 1
            if samples_since_step >= settle_samples:
                samples_since_step = 0
                # Power from the *device* voltage actually applied, not the
                # raw (sign-flipped) Keithley source register
                power_now = applied_v * (current / area) * 1000.0 if area else applied_v * current

                if prev_power is not None:
                    if power_now < prev_power:
                        # Power got worse: reverse direction and shrink the step.
                        step = -np.sign(step) * max(abs(step) * step_decay, min_step)
                    # else: power improved or held -- keep stepping the same way.

                prev_power = power_now
                target_v = applied_v + step

            remaining = p["interval_s"] - (time.monotonic() - start_time - elapsed)
            if remaining > 0:
                time.sleep(remaining)

        return times, currents, device_v, raw_keithley_v

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

                    # --- VOLTAGE HOLD LOOP (fixed-V, or adaptive-step P&O
                    # MPP tracking when p["mppt_enabled"] is True) ---
                    mppt_enabled = p.get("mppt_enabled", False)
                    if mppt_enabled:
                        p_run = dict(p, _area_cm2=area)
                        times, currents, device_v, raw_keithley_v = self._run_mppt_hold(pixel, loop_idx, p_run)
                    else:
                        times, currents, device_v, raw_keithley_v = self._run_fixed_hold(pixel, loop_idx, p)

                    # --- POST-HOLD SAFE STATE ---
                    keithley_output_safe(self.keithley)
                    if use_relay:
                        numato_command(self.relay, f"relay off {numato_relay_token(ch)}")
                        time.sleep(RELAY_SETTLE_S)

                    if self._abort:
                        break

                    t = np.asarray(times, dtype=float)
                    i = np.asarray(currents, dtype=float)
                    v_device = np.asarray(device_v, dtype=float)
                    v_keithley_raw = np.asarray(raw_keithley_v, dtype=float)

                    fault = check_fault(i, compliance_a=p["compliance_a"])
                    if fault:
                        self.pixel_faulted.emit(pixel, area, fault, loop_idx + 1)
                        self.log.emit(f"Pixel {pixel} flagged as {fault}")
                        continue

                    j_pv = (i / area) * 1000.0
                    p_density = v_device * j_pv
                    final_power = float(p_density[-1]) if len(p_density) else float("nan")
                    mean_power = float(np.nanmean(p_density)) if len(p_density) else float("nan")
                    final_voltage = float(v_device[-1]) if len(v_device) else float("nan")

                    # Stabilized efficiency: the number most SPO runs are
                    # quoted by. Mirrors pv_math.extract_parameters'
                    pin = p.get("pin", 100) or 100
                    final_pce = (final_power / pin) * 100
                    mean_pce = (mean_power / pin) * 100

                    record = {
                        "pixel": pixel,
                        "channel": ch,
                        "loop": loop_idx + 1,
                        "area_cm2": area,
                        "pin_mw_cm2": pin,
                        "mppt_enabled": mppt_enabled,
                        "hold_voltage_v": p["hold_v"],
                        "final_voltage_v": final_voltage,
                        "time_s": t.tolist(),
                        "voltage_v": v_device.tolist(),
                        "keithley_voltage_v": v_keithley_raw.tolist(),
                        "current_a": i.tolist(),
                        "power_density_mw_cm2": p_density.tolist(),
                        "final_power_density_mw_cm2": final_power,
                        "mean_power_density_mw_cm2": mean_power,
                        "final_pce_percent": final_pce,
                        "mean_pce_percent": mean_pce,
                    }
                    self.pixel_result.emit(record)
                    if mppt_enabled:
                        self.log.emit(
                            f"SPO {pixel}: tracked V settled at {final_voltage:.3f} V, "
                            f"final={final_power:.3f} mW/cm\u00b2, mean={mean_power:.3f} mW/cm\u00b2"
                        )
                    else:
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
