"""JV metric extraction, Rs/Rsh estimates, and fault detection."""
import numpy as np
from scipy.optimize import least_squares


def _interp_zero_crossing(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x = x[valid]
    y = y[valid]

    if len(x) < 2:
        return np.nan

    exact = np.where(np.isclose(y, 0.0, atol=1e-15))[0]
    if exact.size:
        return float(x[exact[0]])

    sign_changes = np.where(np.diff(np.signbit(y)))[0]
    if sign_changes.size == 0:
        return np.nan

    idx = sign_changes[0]
    x0, x1 = x[idx], x[idx + 1]
    y0, y1 = y[idx], y[idx + 1]
    if np.isclose(y1, y0):
        return float((x0 + x1) / 2)
    return float(x0 + (0 - y0) * (x1 - x0) / (y1 - y0))


def derivative_resistances(V, I):
    V = np.asarray(V, dtype=float)
    I = np.asarray(I, dtype=float)

    finite = np.isfinite(V) & np.isfinite(I)
    V = V[finite]
    I = I[finite]

    if len(V) < 6:
        return np.nan, np.nan

    order = np.argsort(V)
    V = V[order]
    I = I[order]

    try:
        # Rs from the slope at Voc is an upper bound.
        voc_idx = np.argmin(np.abs(I))
        rs_lo = max(0, voc_idx - 3)
        rs_hi = min(len(V), voc_idx + 4)
        V_rs = V[rs_lo:rs_hi]
        I_rs = I[rs_lo:rs_hi]

        if len(V_rs) >= 3:
            p = np.polyfit(I_rs, V_rs, 1)
            Rs = abs(p[0])
        else:
            Rs = np.nan
    except Exception:
        Rs = np.nan

    try:
        mask = np.abs(V) <= 0.05
        V_rsh = V[mask]
        I_rsh = I[mask]

        if len(V_rsh) >= 3:
            p = np.polyfit(I_rsh, V_rsh, 1)
            Rsh = abs(p[0])
        else:
            Rsh = np.nan
    except Exception:
        Rsh = np.nan

    return Rs, Rsh


def single_diode_model_current(params, V, vt):
    """Solves the single-diode equation for current (I) at each voltage (V).

    Parameters
    ----------
    params : tuple or list of float
        A 5-element sequence containing:
        - `Iph` (float): Photocurrent (A).
        - `I0` (float): Diode saturation current (A).
        - `n` (float): Diode ideality factor (dimensionless).
        - `Rs` (float): Series resistance (Ohms).
        - `Rsh` (float): Shunt resistance (Ohms).
    V : array_like
        Voltages at which to evaluate the current (V).
    vt : float
        Thermal voltage (kT/q) in V (~0.02585 V at room temperature).

    Returns
    -------
    ndarray
        Calculated diode current (A) for each voltage point in `V`.
    """
    Iph, I0, n, Rs, Rsh = params

    I = np.full_like(V, Iph, dtype=float)

    for _ in range(60):
        exp_term = np.exp(np.clip((V + I * Rs) / (n * vt), -100, 100))

        f = (
            Iph
            - I0 * (exp_term - 1)
            - (V + I * Rs) / Rsh
            - I
        )

        df = (
            -I0 * exp_term * (Rs / (n * vt))
            - Rs / Rsh
            - 1
        )

        step = f / df
        I -= step

        if np.max(np.abs(step)) < 1e-12:
            break

    return I


def diode_fit_resistances(V, I):
    V = np.asarray(V, dtype=float)
    I = np.asarray(I, dtype=float)

    finite = np.isfinite(V) & np.isfinite(I)
    V = V[finite]
    I = I[finite]

    if len(V) < 10:
        return np.nan, np.nan

    vt = 0.02585

    # Fit I0 and Rsh in log10.
    def unpack(x):
        Iph, log_I0, n, Rs, log_Rsh = x
        return [Iph, 10 ** log_I0, n, Rs, 10 ** log_Rsh]

    x0 = [
        max(np.max(I), 1e-9),
        -10.0,
        1.5,
        20,
        5.0,
    ]
    lower = [0, -15, 1.0, 0, 1]
    upper = [1, -3, 4.0, 1e4, 9]

    f_scale = max(0.01 * np.max(np.abs(I)), 1e-12)

    def residuals(params_x):
        try:
            modeled = single_diode_model_current(unpack(params_x), V, vt)
            return modeled - I
        except Exception:
            return np.ones_like(I) * 1e6

    try:
        result = least_squares(
            residuals,
            x0,
            bounds=(lower, upper),
            loss="soft_l1",
            f_scale=f_scale,
            max_nfev=2000,
            x_scale="jac",
        )

        Iph, I0, n, Rs, Rsh = unpack(result.x)

        if Rsh > 1e8:
            Rsh = 1e8

        return float(Rs), float(Rsh)
    except Exception:
        return np.nan, np.nan


def extract_parameters(V, I, area_cm2, pin_mw_cm2=100):
    """Extracts J-V characteristics from raw solar cell sweep data.

    Parameters
    ----------
    V : array_like
        Measured voltage points (V).
    I : array_like
        Measured current points (A).
    area_cm2 : float
        Active solar cell pixel area in cm^2.
    pin_mw_cm2 : float, optional
        Incident light power density in mW/cm^2. Defaults to 100.

    Returns
    -------
    dict
        A dictionary containing the extracted performance metrics:
        - "Voc" (float): Open-circuit voltage (V).
        - "Jsc" (float): Short-circuit current density (mA/cm^2).
        - "Vmpp" (float): Voltage at the maximum power point (V).
        - "Jmpp" (float): Current density at the maximum power point (mA/cm^2).
        - "Pmax" (float): Maximum electrical power density (mW/cm^2).
        - "FF" (float): Fill factor (dimensionless, 0 to 1).
        - "PCE" (float): Power conversion efficiency (%).
    """
    V = np.asarray(V, dtype=float)
    I = np.asarray(I, dtype=float)

    if area_cm2 <= 0:
        raise ValueError("Pixel area must be greater than zero.")
    if pin_mw_cm2 <= 0:
        raise ValueError("Incident power must be greater than zero.")

    J = (I / area_cm2) * 1000

    order_v = np.argsort(V)
    V_sorted = V[order_v]
    J_sorted = J[order_v]
    I_sorted = I[order_v]

    Voc = _interp_zero_crossing(V_sorted, I_sorted)
    Jsc_raw = _interp_zero_crossing(J_sorted, V_sorted)
    Jsc = abs(Jsc_raw) if np.isfinite(Jsc_raw) else np.nan

    measured_power = V * J
    if np.isfinite(Jsc_raw) and not np.isclose(Jsc_raw, 0.0):
        current_polarity = np.sign(Jsc_raw)
    else:
        current_polarity = -1 if abs(np.nanmin(measured_power)) > abs(np.nanmax(measured_power)) else 1
    power_density = current_polarity * measured_power

    finite = np.isfinite(V) & np.isfinite(power_density)
    if np.isfinite(Voc):
        lo, hi = sorted((0.0, Voc))
        operating_region = finite & (V >= lo) & (V <= hi)
    else:
        operating_region = finite
    positive_region = operating_region & (power_density >= 0)
    candidates = np.where(positive_region)[0]
    if candidates.size == 0:
        candidates = np.where(finite)[0]
    if candidates.size == 0:
        raise ValueError("No finite IV data available for metric extraction.")

    mpp_idx = int(candidates[np.nanargmax(power_density[candidates])])
    Pmax = max(float(power_density[mpp_idx]), 0.0)
    Vmpp = float(V[mpp_idx])
    Jmpp = abs(float(J[mpp_idx]))

    denom = abs(Voc * Jsc) if np.isfinite(Voc) and np.isfinite(Jsc) else np.nan
    FF = Pmax / denom if denom and np.isfinite(denom) else np.nan
    PCE = (Pmax / pin_mw_cm2) * 100

    return {
        "Voc": float(Voc),
        "Jsc": float(Jsc),
        "Vmpp": Vmpp,
        "Jmpp": Jmpp,
        "Pmax": Pmax,
        "FF": float(FF),
        "PCE": float(PCE),
    }


SHORT_COMPLIANCE_FRACTION = 0.95
LEGACY_SHORT_THRESHOLD_A = 0.95
OPEN_THRESHOLD_A = 1e-6
# Judge SHORT only within this window of 0 V.
SHORT_CIRCUIT_WINDOW_V = 0.05


def check_fault(I, compliance_a=None, V=None, open_threshold_a=OPEN_THRESHOLD_A):
    I = np.asarray(I, dtype=float)
    peak = np.max(np.abs(I))

    if compliance_a and compliance_a > 0:
        rail = SHORT_COMPLIANCE_FRACTION * compliance_a
        if V is not None:
            V = np.asarray(V, dtype=float)
            near_zero_bias = np.abs(V) <= SHORT_CIRCUIT_WINDOW_V
            if np.any(near_zero_bias):
                if np.all(np.abs(I[near_zero_bias]) >= rail):
                    return "SHORT"
            elif np.all(np.abs(I) >= rail):
                return "SHORT"
        elif np.all(np.abs(I) >= rail):
            return "SHORT"
    elif peak > LEGACY_SHORT_THRESHOLD_A:
        return "SHORT"

    if peak < open_threshold_a:
        return "OPEN"
    return None


def full_iv_report(V, I, area_cm2, pin_mw_cm2=100, fit_resistances=True):
    """Extracts standard JV parameters and calculates series/shunt resistances.

    Parameters
    ----------
    V : array_like
        Measured voltage points (V).
    I : array_like
        Measured current points (A).
    area_cm2 : float
        Active solar cell pixel area in cm^2.
    pin_mw_cm2 : float, optional
        Incident light power density in mW/cm^2. Defaults to 100.
    fit_resistances : bool, optional
        Run the single-diode least-squares fit for Rs/Rsh. Defaults to True.

    Returns
    -------
    dict
        The `extract_parameters` metrics plus:
        - "Rs_derivative": Series resistance from local Voc slope (Ohms).
        - "Rsh_derivative": Shunt resistance from local zero-bias slope (Ohms).
        - "Rs_diode_eq": Series resistance from the diode-model fit (Ohms or NaN).
        - "Rsh_diode_eq": Shunt resistance from the diode-model fit (Ohms or NaN).
    """
    metrics = extract_parameters(V, I, area_cm2, pin_mw_cm2)

    Rs_derivative, Rsh_derivative = derivative_resistances(V, I)
    metrics["Rs_derivative"] = float(Rs_derivative)
    metrics["Rsh_derivative"] = float(Rsh_derivative)

    if fit_resistances:
        Rs_diode_eq, Rsh_diode_eq = diode_fit_resistances(V, I)
    else:
        Rs_diode_eq, Rsh_diode_eq = np.nan, np.nan
    metrics["Rs_diode_eq"] = float(Rs_diode_eq)
    metrics["Rsh_diode_eq"] = float(Rsh_diode_eq)

    return metrics
