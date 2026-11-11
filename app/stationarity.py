"""
KPSS test of level stationarity (Kwiatkowski, Phillips, Schmidt & Shin, 1992): its null hypothesis is that a signal
varies around a constant mean, so a small p says it doesn't. Computed as statsmodels' kpss(x, regression='c',
nlags='auto') does, so that results can be compared: the number of lags of the long-run variance is chosen from
the data (Hobijn, Franses & Ooms, 1998), and p is read from the table of critical values, so it lies between 0.01
and 0.10.

Not rejecting stationarity is weak evidence that a signal is stationary, especially in short windows.
"""
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

# critical values of the level-stationarity statistic, and their p (Kwiatkowski et al., 1992, table 1)
CRITICAL_VALUES = (0.347, 0.463, 0.574, 0.739)
P_VALUES = (0.10, 0.05, 0.025, 0.01)
SMALLEST_P, LARGEST_P = min(P_VALUES), max(P_VALUES)
ALPHA = 0.05


def _lagged_products(residuals, lag):
    """The sum of residual[t] * residual[t + lag] of each row."""
    n = residuals.shape[1]
    return np.einsum('ij,ij->i', residuals[:, lag:], residuals[:, :n - lag])


def _automatic_lags(residuals):
    """The number of lags of each row's long-run variance (Hobijn et al., 1998), as statsmodels chooses it."""
    n = residuals.shape[1]
    s0 = np.sum(residuals ** 2, axis=1) / n
    s1 = np.zeros(len(residuals))
    for lag in range(1, int(n ** (2 / 9)) + 1):
        products = _lagged_products(residuals, lag) / (n / 2)
        s0 += products
        s1 += lag * products
    gamma = 1.1447 * np.cbrt((s1 / s0) ** 2)
    return np.minimum(np.floor(gamma * np.cbrt(n)).astype(int), n - 1)


def kpss_p_values(segments):
    """
    The KPSS p of each row of a 2-d array. NaN for rows that are flat or contain NaN, which have no variance.
    """
    segments = np.atleast_2d(np.asarray(segments, dtype=float))
    p_values = np.full(len(segments), np.nan)
    testable = ~np.isnan(segments).any(axis=1) & (np.ptp(segments, axis=1) > 0) if segments.shape[1] > 1 else \
        np.zeros(len(segments), dtype=bool)
    if not testable.any():
        return p_values

    residuals = segments[testable] - segments[testable].mean(axis=1, keepdims=True)
    n = residuals.shape[1]
    lags = _automatic_lags(residuals)
    long_run_variance = np.sum(residuals ** 2, axis=1)
    for lag in range(1, lags.max() + 1):
        weight = np.where(lag <= lags, 1 - lag / (lags + 1), 0)     # Bartlett kernel
        long_run_variance += 2 * weight * _lagged_products(residuals, lag)
    long_run_variance /= n
    statistic = np.sum(np.cumsum(residuals, axis=1) ** 2, axis=1) / n ** 2 / long_run_variance
    p_values[testable] = np.interp(statistic, CRITICAL_VALUES, P_VALUES)
    return p_values


def window_p_values(signal, window_size, step_size):
    """The KPSS p of each window, cut as windowed_cross_correlation cuts them."""
    signal = np.asarray(signal, dtype=float)
    if window_size > len(signal):
        return np.array([])
    return kpss_p_values(sliding_window_view(signal, window_size)[::step_size])


def signal_stationarity(signals, config):
    """
    KPSS of each person's signal, as it is correlated: the windows of windowed cross-correlation, or the whole
    signal of standard cross-correlation. Standardising doesn't change the test. Returns a dict with
    'windowed' and 'p_a', 'p_b': arrays of one p per window, or a single p each.
    """
    signal_a, signal_b = signals[0], signals[1]
    if config.windowed:
        return {'windowed': True,
                'p_a': window_p_values(signal_a, config.window_size, config.step_size),
                'p_b': window_p_values(signal_b, config.window_size, config.step_size)}
    return {'windowed': False, 'p_a': float(kpss_p_values(signal_a)[0]), 'p_b': float(kpss_p_values(signal_b)[0])}


def stationary_share(p_values):
    """(windows without evidence against stationarity, windows tested): p >= ALPHA, leaving out untestable ones."""
    p_values = np.asarray(p_values, dtype=float)
    tested = p_values[~np.isnan(p_values)]
    return int(np.sum(tested >= ALPHA)), len(tested)


def format_kpss_p(p):
    if np.isnan(p):
        return "not testable (flat)"
    if p <= SMALLEST_P:
        return f"p ≤ {SMALLEST_P:.2f}"
    if p >= LARGEST_P:
        return f"p ≥ {LARGEST_P:.2f}"
    return f"p = {p:.3f}"


def format_stationarity(stationarity):
    """The KPSS results as text for the window."""
    if stationarity is None:
        return "KPSS: no data"
    if not stationarity['windowed']:
        return (f"KPSS of the whole signal: A {format_kpss_p(stationarity['p_a'])}, "
                f"B {format_kpss_p(stationarity['p_b'])} (p < {ALPHA}: not stationary)")
    parts = []
    for person in ('a', 'b'):
        stationary, tested = stationary_share(stationarity[f'p_{person}'])
        share = f" ({100 * stationary / tested:.0f}%)" if tested else ""
        parts.append(f"{person.upper()} {stationary} of {tested}{share}")
    return f"KPSS, stationary windows (p ≥ {ALPHA}): " + ", ".join(parts)
