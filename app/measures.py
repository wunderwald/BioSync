"""
One number per dyad, computed from its correlation result. Surrogate tests compare real dyads with surrogates
on one of these.
"""
import numpy as np

from cross_correlation import mean_ignoring_flat_windows

MEAN_R = 'mean r'
MEAN_ABS_R_MAX = 'mean |r_max|'
R_AT_LAG_0 = 'r at lag 0'
MEASURES = (MEAN_R, MEAN_ABS_R_MAX, R_AT_LAG_0)


def _windowed_lag_range(config):
    """The lowest and highest lag of windowed results, as windowed_cross_correlation computes them."""
    if config.use_lag_filter:
        return min(config.lag_filter_min, config.lag_filter_max), max(config.lag_filter_min, config.lag_filter_max)
    return -config.max_lag, config.max_lag


def measure_problem(measure, config):
    """Why the measure can't be computed with these settings, or None."""
    if measure not in MEASURES:
        return f"unknown measure '{measure}'"
    if not config.windowed or measure == MEAN_R:
        return None
    if config.average_windows:
        return f"{measure} needs a correlation for each lag, and 'average windows' is on"
    if measure == R_AT_LAG_0:
        low, high = _windowed_lag_range(config)
        if not low <= 0 <= high:
            return "the lag filter leaves out lag 0"
    return None


def dyad_measure(corr_data, config, measure):
    """
    The measure of one dyad: the result of windowed_cross_correlation or standard_cross_correlation, whichever the
    config chose. Flat windows are left out. NaN if every window is flat.
        mean r:       the mean of every correlation, over all windows and lags
        mean |r_max|: the mean over windows of the strongest correlation at any lag, without its sign
        r at lag 0:   the mean over windows of the correlation without delay
    Raises ValueError if measure_problem names a problem.
    """
    problem = measure_problem(measure, config)
    if problem:
        raise ValueError(problem)

    if config.windowed:
        correlations = np.array([window['correlations'] for window in corr_data], dtype=float)
        if measure == MEAN_R:
            return float(mean_ignoring_flat_windows(correlations))
        if measure == MEAN_ABS_R_MAX:
            return float(mean_ignoring_flat_windows(np.abs([window['r_max'] for window in corr_data])))
        low, _high = _windowed_lag_range(config)
        return float(mean_ignoring_flat_windows(correlations[:, -low]))

    correlations = np.asarray(corr_data['corr'], dtype=float)
    if measure == MEAN_R:
        return float(mean_ignoring_flat_windows(correlations))
    if measure == MEAN_ABS_R_MAX:
        return float(np.max(np.abs(correlations))) if not np.all(np.isnan(correlations)) else np.nan
    return float(correlations[list(corr_data['lags']).index(0)])
