"""
Keithley 2460 SourceMeter driver: VISA discovery, SCPI setup, output
control, and point-by-point sweep reads.
"""
import time

import numpy as np
import pyvisa

KEITHLEY_SAFE_VOLTAGE = 0.0
KEITHLEY_DEFAULT_COMPLIANCE_A = 0.105
KEITHLEY_OUTPUT_SETTLE_S = 0.15

# Wiring convention:
#   relay NO bus -> Keithley Force HI -> selected individual n-side pixel
#   shared p-side electrode -> Keithley Force LO
# GUI voltage is device voltage V(p-side shared electrode) - V(n-side pixel).
# Keithley source voltage is V(HI) - V(LO), so it is the negative of device voltage.
KEITHLEY_VOLTAGE_FROM_DEVICE_VOLTAGE = -1.0


def find_keithley(resource_name=None, logger=None):
    """
    Locates the Keithley 2460.
    """
    backend_note = "NI-VISA"
    try:
        # 1. Try to use the standard NI-VISA backend (the 800MB driver)
        rm = pyvisa.ResourceManager()
    except Exception:
        # 2. Fallback: Use the 'pyvisa-py' backend
        backend_note = "pyvisa-py (self-contained)"
        try:
            import libusb_package
            rm = pyvisa.ResourceManager('@py')
        except Exception:
            raise RuntimeError(
                "No VISA driver found. Please run install.bat to set up "
                "local drivers or install NI-VISA."
            )

    if logger:
        logger(f"VISA backend: {backend_note}")

    # If the user provided a specific ID (like 'USB0::0x05E6::...'), use it directly
    if resource_name:
        return rm.open_resource(resource_name)

    # 3. Discovery Loop: USB instruments only.
    for r in rm.list_resources('USB?*::INSTR'):
        try:
            inst = rm.open_resource(r)
            inst.timeout = 2000 # 2-second limit
            
            idn = inst.query("*IDN?").upper()
            
            # Look for Keithley and the specific model number 2460
            if "KEITHLEY" in idn and "2460" in idn:
                return inst
            
            inst.close() # Close connection if it's not the right device
        except Exception:
            continue
            
    raise RuntimeError("Keithley 2460 not found. Check USB connection and power.")


def keithley_system_error(k):
    try:
        return k.query(":SYST:ERR?").strip()
    except Exception as e:
        return f"Could not query Keithley error queue: {e}"


def keithley_log_errors(k, logger=None, context="Keithley"):
    errors = []
    for _ in range(8):
        err = keithley_system_error(k)
        errors.append(err)
        if err.startswith("0") or "No error" in err:
            break
    if logger:
        for err in errors:
            logger(f"{context} error queue: {err}")
    return errors


def keithley_write_checked(k, command, logger=None):
    k.write(command)
    err = keithley_system_error(k)
    if logger and not (err.startswith("0") or "No error" in err):
        logger(f"Keithley rejected command {command!r}: {err}")
    return err


def keithley_output_state(k):
    response = k.query(":OUTPut:STATe?").strip()
    return response.startswith("1") or response.upper().startswith("ON")


def keithley_set_output(k, enabled, logger=None):
    state = "ON" if enabled else "OFF"
    keithley_write_checked(k, f":OUTPut:STATe {state}", logger=logger)
    time.sleep(KEITHLEY_OUTPUT_SETTLE_S)

    try:
        actual_state = keithley_output_state(k)
        if logger:
            logger(f"Keithley output {'ON' if actual_state else 'OFF'} after command {state}")
        if enabled and not actual_state:
            raise RuntimeError("Keithley did not report output ON after :OUTPut:STATe ON.")
    except Exception as e:
        if logger:
            logger(f"WARNING: could not verify Keithley output state: {e}")
        if enabled:
            raise


def init_keithley(k, compliance_a=KEITHLEY_DEFAULT_COMPLIANCE_A, logger=None):
    compliance_a = max(float(compliance_a), 1e-9)
    k.write("*RST")
    time.sleep(0.2)
    k.write("*CLS")

    commands = [
        ":SENS:FUNC \"CURR\"",
        ":SENS:CURR:RANG:AUTO ON",
        ":SOUR:FUNC VOLT",
        f":SOUR:VOLT {KEITHLEY_SAFE_VOLTAGE}",
        f":SOUR:VOLT:ILIM {compliance_a}",
        ":OUTPut:STATe OFF",
    ]
    for command in commands:
        keithley_write_checked(k, command, logger=logger)

    keithley_log_errors(k, logger=logger, context="Keithley setup")


def keithley_output_safe(k):
    k.write(f":SOUR:VOLT {KEITHLEY_SAFE_VOLTAGE}")
    time.sleep(KEITHLEY_OUTPUT_SETTLE_S)
    keithley_set_output(k, False)


def keithley_output_enable(k, logger=None):
    keithley_set_output(k, True, logger=logger)


def parse_keithley_current(raw):
    # For the 2460, when SENS:FUNC is CURR, READ? returns the active
    # measurement reading first. Additional fields, if present, are metadata.
    for part in raw.split(","):
        try:
            return float(part.strip())
        except ValueError:
            continue
    raise RuntimeError(f"Could not parse Keithley reading: {raw}")


def keithley_source_voltage(k):
    return float(k.query(":SOUR:VOLT?").strip().split(",")[0])


def keithley_voltage_for_device_voltage(device_voltage):
    return KEITHLEY_VOLTAGE_FROM_DEVICE_VOLTAGE * device_voltage


def keithley_read_current(k, device_voltage, point_delay_s):
    keithley_voltage = keithley_voltage_for_device_voltage(device_voltage)
    k.write(f":SOUR:VOLT {keithley_voltage}")
    time.sleep(point_delay_s)
    k.write(":READ?")
    raw = k.read().strip()
    return parse_keithley_current(raw), raw, keithley_voltage


# --- DIT (Dark Injection Transient): fast timed-current trace-buffer sweeps ---

def keithley_configure_timed_current(
    k,
    integration_time_ms,
    sense_range="AUTO",
    four_wire=True,
    autozero=False,
    terminals="FRONT",
    line_frequency_hz=60.0,
):
    nplc = min(10.0, max(0.01, float(integration_time_ms) * float(line_frequency_hz) / 1000.0))
    k.write(f"ROUT:TERM {terminals}")
    k.write("SENS:FUNC 'CURR'")
    k.write(f"SENS:CURR:NPLC {nplc:.6g}")
    k.write(f"SYST:AZER {'ON' if autozero else 'OFF'}")
    if str(sense_range).upper() == "AUTO":
        k.write("SENS:CURR:RANG:AUTO ON")
    else:
        k.write("SENS:CURR:RANG:AUTO OFF")
        k.write(f"SENS:CURR:RANG {sense_range}")
    k.write(f"SENS:CURR:RSEN {'ON' if four_wire else 'OFF'}")
    k.write("SOUR:FUNC VOLT")
    k.write("SOUR:VOLT:READ:BACK ON")
    k.write("OUTP:VOLT:SMOD HIMP")


def _chunk_sequences(values, max_points_per_chunk):
    if max_points_per_chunk <= 0:
        raise ValueError("Chunk size must be greater than 0.")
    values = np.asarray(values, dtype=float)
    return [values[i:i + max_points_per_chunk] for i in range(0, values.size, max_points_per_chunk)]


def keithley_run_voltage_program(k, device_voltages, source_delay_s, max_points_per_chunk=500, progress=None):
    chunks = _chunk_sequences(device_voltages, int(max_points_per_chunk))
    time_fragments = []
    voltage_fragments = []
    current_fragments = []
    cursor = 0.0
    buffer_name = '"defbuffer1"'

    for chunk in chunks:
        points = int(chunk.size)
        source_chunk = keithley_voltage_for_device_voltage(chunk)
        k.write(f"TRAC:CLE {buffer_name}")
        k.write(
            f"SOUR:SWE:VOLT:LIN {source_chunk[0]:.9g},{source_chunk[-1]:.9g},"
            f"{points},{source_delay_s:.9g}"
        )
        k.write("INIT")
        k.write("*WAI")
        raw = k.query_ascii_values(
            f"TRAC:DATA? 1,{points},{buffer_name},REL,SOUR,READ,STAT,SOURSTAT"
        )

        values = np.asarray(raw, dtype=float)
        if values.size == points * 5:
            trace = values.reshape(-1, 5)
            measured_t = trace[:, 0]
            measured_t = measured_t - measured_t[0] + cursor
            measured_v = keithley_voltage_for_device_voltage(trace[:, 1])
            current_a = trace[:, 2]
            cursor = float(measured_t[-1] + max(source_delay_s, 1e-6))
        elif values.size == points * 2:
            trace = values.reshape(-1, 2)
            measured_v = keithley_voltage_for_device_voltage(trace[:, 0])
            current_a = trace[:, 1]
            measured_t = cursor + np.arange(points, dtype=float) * max(source_delay_s, 1e-6)
            cursor = float(measured_t[-1] + max(source_delay_s, 1e-6))
        else:
            raise RuntimeError(f"Expected {points} trace points; instrument returned {values.size} values.")

        time_fragments.append(measured_t)
        voltage_fragments.append(measured_v)
        current_fragments.append(current_a)
        if progress is not None:
            progress(measured_t.copy(), measured_v.copy(), current_a.copy())

    if not time_fragments:
        return np.array([]), np.array([]), np.array([])
    return np.concatenate(time_fragments), np.concatenate(voltage_fragments), np.concatenate(current_fragments)


def keithley_dit_voltage_step(
    k,
    v1_v,
    v2_v,
    hold_v1_s,
    hold_v2_s,
    trigger_delay_ms,
    integration_time_ms,
    current_limit_a,
    sense_range="AUTO",
    delay_fudge_ms=0.01,
    max_points_per_chunk=500,
    four_wire=True,
    autozero=False,
    repetitions=1,
    recovery_s=1.0,
    progress=None,
):
    if current_limit_a <= 0:
        raise ValueError("DIT current limit must be greater than 0 A.")
    sample_interval_s = max(1e-6, (trigger_delay_ms + integration_time_ms + delay_fudge_ms) / 1000.0)
    n1 = max(1, int(round(hold_v1_s / sample_interval_s)))
    n2 = max(1, int(round(hold_v2_s / sample_interval_s)))
    recovery_points = max(1, int(round(recovery_s / sample_interval_s)))

    sequences = []
    for repeat in range(int(repetitions)):
        sequences.extend(
            [
                np.full(n1, float(v1_v), dtype=float),
                np.array([float(v1_v), float(v2_v)], dtype=float),
                np.full(n2, float(v2_v), dtype=float),
            ]
        )
        if repeat < int(repetitions) - 1 and recovery_s > 0:
            sequences.append(np.full(recovery_points, float(v1_v), dtype=float))

    try:
        k.write("*RST")
        k.write("*CLS")
        keithley_configure_timed_current(
            k,
            integration_time_ms=integration_time_ms,
            sense_range=sense_range,
            four_wire=four_wire,
            autozero=autozero,
        )
        k.write(f"SOUR:VOLT:RANG {max(abs(v1_v), abs(v2_v), 0.2):.9g}")
        k.write(f"SOUR:VOLT:ILIM {current_limit_a:.9g}")
        k.write(f":SOUR:VOLT:LEV {keithley_voltage_for_device_voltage(v1_v):.9g}")
        keithley_output_enable(k)

        all_t = []
        all_v = []
        all_i = []
        cursor = 0.0
        source_delay_s = max(0.0, (trigger_delay_ms + delay_fudge_ms) / 1000.0)
        for sequence in sequences:
            t, v, i = keithley_run_voltage_program(
                k,
                sequence,
                source_delay_s,
                max_points_per_chunk=max_points_per_chunk,
                progress=progress,
            )
            all_t.append(t + cursor)
            all_v.append(v)
            all_i.append(i)
            cursor = float(all_t[-1][-1] + max(sample_interval_s, 1e-6))

        return np.concatenate(all_t), np.concatenate(all_v), np.concatenate(all_i)
    finally:
        keithley_output_safe(k)
