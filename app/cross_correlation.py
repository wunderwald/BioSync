import warnings

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

# r=±1 has an infinite Fisher z, so correlations are limited to this magnitude first (z of about ±3.8)
FISHER_Z_MAX_R = 0.999

# windows computed at once, which limits memory use for small step sizes
WINDOWS_PER_BATCH = 1024

def fisher_z(correlations):
    '''
    Fisher z-transforms correlation values. Values at or beyond ±FISHER_Z_MAX_R are clipped to it, because they
    are the strongest correlations and must stay the largest z-values. NaN stays NaN.
    '''
    clipped = np.clip(np.asarray(correlations, dtype=float), -FISHER_Z_MAX_R, FISHER_Z_MAX_R)
    return np.arctanh(clipped)


def _flat_window_result(start, window_size, n_lags):
    '''
    A window where a signal doesn't change has no correlation at any lag. Every value is NaN, so that it can't be
    mistaken for a measured result and is left out of averages.
    '''
    return {
        'start_idx': start,
        'center_idx': start + window_size // 2,
        'correlations': [np.nan] * n_lags,
        'r_max': np.nan,
        'tau_max': np.nan,
        'correlations_sigmoid': [np.nan] * n_lags,
        'r_max_sigmoid': np.nan,
        'tau_max_sigmoid': np.nan,
        'avg_z_transformed_corr': np.nan,
        'var_z_transformed_corr': np.nan,
    }


def scale_sigmoid(x: np.array):
    '''
    Scales values a numpy array using a modified sigmoid function. The sigmoid itsself is scaled so that it returns values
    in range [-1, 1] for inputs in range [-1, 1]. It basically gives more range to values closer to zero and less range to
    values closer to -1 or 1. In the correlation heatmap, sigmoid scaling increases contrast.
    '''
    return 2 * (1 / (1 + np.exp(-4*x))) - 1


def windowed_cross_correlation(x, y, window_size, step_size, max_lag, use_lag_filter=False, lag_filter_min=None, lag_filter_max=None, absolute=False, average_windows=False):
    """
    Compute windowed cross-correlation between two time series.

    Lag convention:
        Rxy(lag) = mean( x_window[t] * y_window[t + lag] )
        - lag > 0: x leads y (x's pattern occurs lag steps before y's)
        - lag = 0: simultaneous correlation (Pearson r)
        - lag < 0: y leads x (y's pattern occurs |lag| steps before x's)
        tau_max follows the same convention: positive means x led y in that window.

    Parameters:
        x (np.ndarray): First time series.
        y (np.ndarray): Second time series.
        window_size (int): Number of data points in each window.
        step_size (int): Step size for the sliding window.
        max_lag (int): Maximum lag to compute cross-correlation.
        absolute (bool): Calculate abs of correlation values.
        average_windows (bool): Average correlation values across lags within each window
            (result is stored for every lag position for shape consistency).
        use_lag_filter (bool): Apply lag filter to limit lag range.
        lag_filter_min (int): Minimum lag for filter (inclusive).
        lag_filter_max (int): Maximum lag for filter (inclusive).

    Returns:
        results (list of dict): A list containing the results for each window.
            Each result is a dictionary with keys:
                - 'start_idx': Start index of the window in the time series.
                - 'center_idx': Index of window center in time series (allows aligning correlation result with input time series).
                - 'r_max': Peak cross-correlation value in the window (largest magnitude, signed).
                - 'tau_max': Lag at which the peak correlation occurs (see lag convention above).
                - 'correlations': Array of cross-correlation values for all lags.
                - 'correlations_sigmoid': Array of sigmoid-scaled cross-correlation values for all lags.
                - 'avg_z_transformed_corr': mean of Fisher z-transformed per-lag correlations (computed before any window averaging)
                - 'var_z_transformed_corr': variance of Fisher z-transformed per-lag correlations (computed before any window averaging)
    """
    n = len(x)
    results = []

    # Ensure inputs are numpy arrays
    x = np.asarray(x)
    y = np.asarray(y)

    # set lag range: filtered or unfiltered
    _min_lag = -max_lag
    _max_lag = max_lag
    lag_range = range(_min_lag, _max_lag + 1)
    if use_lag_filter and not (lag_filter_min is None or lag_filter_max is None):
        _min_lag = min(lag_filter_min, lag_filter_max)
        _max_lag = max(lag_filter_min, lag_filter_max)
        lag_range = range(_min_lag, _max_lag + 1)

    # loop over batches of windows
    all_starts = range(0, n - window_size + 1, step_size)
    for batch_begin in range(0, len(all_starts), WINDOWS_PER_BATCH):
        starts = np.array(all_starts[batch_begin:batch_begin + WINDOWS_PER_BATCH])

        # Extract the windowed segments, one window per row
        x_windows = sliding_window_view(x, window_size)[starts]
        y_windows = sliding_window_view(y, window_size)[starts]

        is_flat = (np.ptp(x_windows, axis=1) == 0) | (np.ptp(y_windows, axis=1) == 0)
        windows = _correlate_windows(x_windows[~is_flat], y_windows[~is_flat], lag_range, absolute, average_windows)

        next_valid_window = iter(windows)
        for start, flat in zip(starts, is_flat):
            if flat:
                results.append(_flat_window_result(int(start), window_size, len(lag_range)))
            else:
                results.append(_window_result(int(start), window_size, _min_lag, average_windows, next(next_valid_window)))

    return results


def _correlate_windows(x_windows, y_windows, lag_range, absolute, average_windows):
    """Computes the values for several windows at once, with one row per window. Yields one tuple per window."""
    # Normalize the segments (zero mean, unit variance)
    x_windows = (x_windows - np.mean(x_windows, axis=1, keepdims=True)) / np.std(x_windows, axis=1, keepdims=True)
    y_windows = (y_windows - np.mean(y_windows, axis=1, keepdims=True)) / np.std(y_windows, axis=1, keepdims=True)

    # Compute cross-correlation for every lag
    # Convention: Rxy(lag) = mean(x[t] * y[t+lag]), so lag > 0 means x leads y.
    correlations = np.empty((len(x_windows), len(lag_range)))
    for lag_index, lag in enumerate(lag_range):
        if lag < 0:
            correlations[:, lag_index] = np.mean(x_windows[:, -lag:] * y_windows[:, :lag], axis=1)
        elif lag > 0:
            correlations[:, lag_index] = np.mean(x_windows[:, :-lag] * y_windows[:, lag:], axis=1)
        else:
            correlations[:, lag_index] = np.mean(x_windows * y_windows, axis=1)
    if absolute:
        correlations = np.abs(correlations)

    # apply sigmoid scaling to correlation values
    correlations_sigmoid = scale_sigmoid(correlations)

    # Fisher z-transform per-lag correlations
    correlations_z_transformed = fisher_z(correlations)
    avg_z_transformed_corr = np.mean(correlations_z_transformed, axis=1)
    var_z_transformed_corr = np.var(correlations_z_transformed, axis=1)

    # optionally average correlation values across lags within the window
    if average_windows:
        correlations = np.repeat(np.mean(correlations, axis=1, keepdims=True), len(lag_range), axis=1)
        correlations_sigmoid = np.repeat(np.mean(correlations_sigmoid, axis=1, keepdims=True), len(lag_range), axis=1)

    return zip(correlations, correlations_sigmoid, avg_z_transformed_corr, var_z_transformed_corr)


def _window_result(start, window_size, min_lag, average_windows, values):
    correlations, correlations_sigmoid, avg_z_transformed_corr, var_z_transformed_corr = values

    # Find the peak correlation (largest magnitude, signed) and its corresponding lag
    _abs_idx = np.argmax(np.abs(correlations))
    r_max = correlations[_abs_idx]
    tau_max = _abs_idx + min_lag if not average_windows else 0
    _abs_idx_sigmoid = np.argmax(np.abs(correlations_sigmoid))
    r_max_sigmoid = correlations_sigmoid[_abs_idx_sigmoid]
    tau_max_sigmoid = _abs_idx_sigmoid + min_lag if not average_windows else 0

    return {
        'start_idx': start,
        'center_idx': start + window_size // 2,
        'correlations': list(correlations),
        'r_max': r_max,
        'tau_max': tau_max,
        'correlations_sigmoid': correlations_sigmoid if not average_windows else list(correlations_sigmoid),
        'r_max_sigmoid': r_max_sigmoid,
        'tau_max_sigmoid': tau_max_sigmoid,
        'avg_z_transformed_corr': avg_z_transformed_corr,
        'var_z_transformed_corr': var_z_transformed_corr
    }

def mean_ignoring_flat_windows(values, axis=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # all flat gives NaN, which is the right result
        return np.nanmean(values, axis=axis)


def _peak_of_average(avg_corr, min_lag):
    if np.all(np.isnan(avg_corr)):
        return np.nan, np.nan
    abs_idx = int(np.nanargmax(np.abs(avg_corr)))
    return float(avg_corr[abs_idx]), int(abs_idx + min_lag)


def average_wxcorr_matrices(list_of_wxcorr, min_lag):
    """
    Average multiple wxcorr result lists element-wise, truncating to the shortest.

    min_lag must be supplied by the caller:
      - no lag filter: -max_lag
      - lag filter active: min(lag_filter_min, lag_filter_max)
    Never infer min_lag from array length — asymmetric filters break that assumption.
    A dyad's flat window is left out of the average for that window.

    Returns a list of window dicts with the same keys as windowed_cross_correlation output,
    directly passable to plot_windowed_cross_correlation.
    """
    if not list_of_wxcorr:
        return []

    n_windows = min(len(w) for w in list_of_wxcorr)

    avg = []
    for i in range(n_windows):
        all_corrs         = np.array([d[i]['correlations']         for d in list_of_wxcorr])
        all_corrs_sigmoid = np.array([d[i]['correlations_sigmoid'] for d in list_of_wxcorr])

        avg_corr         = mean_ignoring_flat_windows(all_corrs, axis=0)
        avg_corr_sigmoid = mean_ignoring_flat_windows(all_corrs_sigmoid, axis=0)

        r_max, tau_max                 = _peak_of_average(avg_corr, min_lag)
        r_max_sigmoid, tau_max_sigmoid = _peak_of_average(avg_corr_sigmoid, min_lag)

        avg.append({
            'start_idx':             list_of_wxcorr[0][i]['start_idx'],
            'center_idx':            list_of_wxcorr[0][i]['center_idx'],
            'correlations':          avg_corr.tolist(),
            'correlations_sigmoid':  avg_corr_sigmoid.tolist(),
            'r_max':                 r_max,
            'tau_max':               tau_max,
            'r_max_sigmoid':         r_max_sigmoid,
            'tau_max_sigmoid':       tau_max_sigmoid,
            'avg_z_transformed_corr': float(mean_ignoring_flat_windows([d[i]['avg_z_transformed_corr'] for d in list_of_wxcorr])),
            'var_z_transformed_corr': float(mean_ignoring_flat_windows([d[i]['var_z_transformed_corr'] for d in list_of_wxcorr])),
        })

    return avg


def standard_cross_correlation(x, y, max_lag, absolute=False):
    """
    Compute standard (1D) cross-correlation between two time series.

    Lag convention:
        Rxy(lag) = mean( x[t] * y[t + lag] )
        - lag > 0: x leads y (x's pattern occurs lag steps before y's)
        - lag = 0: simultaneous correlation (Pearson r)
        - lag < 0: y leads x (y's pattern occurs |lag| steps before x's)

    Parameters:
        x (np.ndarray): First time series.
        y (np.ndarray): Second time series.
        max_lag (int): Maximum lag to compute cross-correlation.
        absolute (bool): Calculate abs of correlation values.

    Returns:
        dict: A dictionary containing:
            - 'corr' (np.ndarray): Array of cross-correlation values for all lags.
            - 'lags' (np.ndarray): Array of lag values.
    """
    n = len(x)

    # Ensure inputs are numpy arrays
    x = np.asarray(x)
    y = np.asarray(y)

    # Normalize the series (zero mean, unit variance)
    x = (x - np.mean(x)) / np.std(x)
    y = (y - np.mean(y)) / np.std(y)

    # Compute cross-correlation for lags in the range [-max_lag, max_lag]
    # Convention: Rxy(lag) = mean(x[t] * y[t+lag]), so lag > 0 means x leads y.
    correlations = []
    lags = []
    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            corr = np.mean(x[-lag:] * y[:lag])
        elif lag > 0:
            corr = np.mean(x[:-lag] * y[lag:])
        else:
            corr = np.mean(x * y)
        if absolute:
            corr = np.abs(corr)
        correlations.append(corr)
        lags.append(lag)

    return {
        'corr': np.array(correlations),
        'lags': np.array(lags)
    }
