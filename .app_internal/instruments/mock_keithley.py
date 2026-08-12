"""
Mock Keithley 2460
"""
import random

import numpy as np

from core.pv_math import single_diode_model_current

_VT = 0.02585  # thermal voltage at room temperature, matches pv_math.py's own default


class MockKeithley:
    def __init__(self, iph=0.0012, i0=1e-10, n=1.4, rs=2.0, rsh=5000.0, noise_a=1e-6, seed=None):
        self.timeout = 2000
        self._source_voltage = 0.0
        self._output_on = False
        self._compliance_a = 0.105
        self._iph, self._i0, self._n, self._rs, self._rsh = iph, i0, n, rs, rsh
        self._noise_a = noise_a
        self._rng = random.Random(seed)
        
        # DIT trace-buffer state (TRAC:CLE / SOUR:SWE:VOLT:LIN / INIT / TRAC:DATA?)
        self._pending_sweep = None
        self._last_trace_values = []

    def write(self, command):
        command = command.strip()
        if command == "*RST":
            self._source_voltage = 0.0
            self._output_on = False
            self._pending_sweep = None
            self._last_trace_values = []
            return
        if command == "*CLS":
            return

        # SCPI's leading colon is optional (":SOUR:VOLT" == "SOUR:VOLT"); the
        # DIT driver (keithley2460.py) writes some commands w/o it, so
        # normalize before matching the branches below.
        if not command.startswith(":"):
            command = ":" + command

        if command.startswith(":TRAC:CLE"):
            self._pending_sweep = None
        elif command.startswith(":SOUR:SWE:VOLT:LIN"):
            self._pending_sweep = self._parse_sweep_program(command)
        elif command == ":INIT":
            self._run_pending_sweep()
        elif command.startswith(":SOUR:VOLT:RANG"):
            pass  # range hint only, mock doesn't need a real range
        elif command.startswith(":SOUR:VOLT:ILIM"):
            try:
                self._compliance_a = float(command.split()[-1])
            except ValueError:
                pass
        elif command.startswith(":SOUR:VOLT"):
            try:
                self._source_voltage = float(command.split()[-1])
            except ValueError:
                pass
        elif command.startswith(":OUTPut:STATe"):
            self._output_on = command.strip().upper().endswith("ON")
        # :SENS:FUNC, :SENS:CURR:RANG:AUTO, :SENS:CURR:NPLC, :SYST:AZER,
        # :SENS:CURR:RSEN, :ROUT:TERM, :OUTP:VOLT:SMOD, :SOUR:VOLT:READ:BACK
        # -- accepted, no state to track for a mock.

    def query(self, command):
        command = command.strip()
        if command == "*IDN?":
            return "KEITHLEY INSTRUMENTS,MODEL 2460,MOCK,1.0.0"
        if command == ":SYST:ERR?":
            return '0,"No error"'
        if command == ":OUTPut:STATe?":
            return "1" if self._output_on else "0"
        if command.startswith(":SOUR:VOLT?"):
            return f"{self._source_voltage:.6f}"
        if command == ":READ?":
            return self._format_current(self._simulate_current())
        return "0"

    def query_ascii_values(self, command):
        """DIT-only: pyvisa parses a comma-separated ASCII reply into a list
        of floats for TRAC:DATA?; the mock just returns the trace it
        computed for the most recent INIT directly."""
        command = command.strip()
        if command.startswith("TRAC:DATA?"):
            return list(self._last_trace_values)
        return []

    def read(self):
        return self._format_current(self._simulate_current())

    def close(self):
        pass

    def _simulate_current(self, device_voltage=None):
        if not self._output_on:
            return 0.0
        # Keithley source voltage is the negative of device voltage
        if device_voltage is None:
            device_voltage = -self._source_voltage
        current = single_diode_model_current(
            [self._iph, self._i0, self._n, self._rs, self._rsh], [device_voltage], _VT,
        )[0]
        current += self._rng.uniform(-1, 1) * self._noise_a
        limit = self._compliance_a
        return max(-limit, min(limit, current))

    @staticmethod
    def _parse_sweep_program(command):
        # ":SOUR:SWE:VOLT:LIN start,stop,points,delay"
        payload = command.split(None, 1)[1] if " " in command else ""
        start, stop, points, delay = payload.split(",")
        return float(start), float(stop), int(float(points)), float(delay)

    def _run_pending_sweep(self):
        if self._pending_sweep is None:
            self._last_trace_values = []
            return

        start, stop, points, delay = self._pending_sweep
        source_v = np.linspace(start, stop, points) if points > 1 else np.array([start], dtype=float)

        if not self._output_on:
            current = np.zeros(points)
        else:
            device_v = -source_v  # mirrors _simulate_current's own sign convention
            current = single_diode_model_current(
                [self._iph, self._i0, self._n, self._rs, self._rsh], device_v, _VT,
            )
            current = current + self._rng.uniform(-1, 1) * self._noise_a
            current = np.clip(current, -self._compliance_a, self._compliance_a)

        flat = []
        for idx in range(points):
            rel_time = idx * max(delay, 1e-6)  # matches source_delay_s spacing on real hardware
            flat.extend([rel_time, float(source_v[idx]), float(current[idx]), 0.0, 0.0])
        self._last_trace_values = flat
        self._source_voltage = float(source_v[-1])

    @staticmethod
    def _format_current(value):
        return f"{value:.9e}"
