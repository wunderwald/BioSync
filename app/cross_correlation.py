import numpy as np

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

    # loop over windows
    for start in range(0, n - window_size + 1, step_size):
        # Extract the windowed segments
        x_window = x[start:start + window_size]
        y_window = y[start:start + window_size]

        # Normalize the segments (zero mean, unit variance)
        x_window = (x_window - np.mean(x_window)) / np.std(x_window)
        y_window = (y_window - np.mean(y_window)) / np.std(y_window)

        # Compute cross-correlation for lags in the range [-max_lag, max_lag]
        # Convention: Rxy(lag) = mean(x[t] * y[t+lag]), so lag > 0 means x leads y.
        correlations = []
        for lag in lag_range:
            if lag < 0:
                corr = np.mean(x_window[-lag:] * y_window[:lag])
            elif lag > 0:
                corr = np.mean(x_window[:-lag] * y_window[lag:])
            else:
                corr = np.mean(x_window * y_window)
            if absolute:
                corr = np.abs(corr)
            correlations.append(corr)

        # apply sigmoid scaling to correlation values
        correlations_sigmoid = scale_sigmoid(np.array(correlations))

        # Fisher z-transform per-lag correlations
        # Suppress the expected RuntimeWarning for r=±1 (arctanh(±1)=±inf); those
        # entries are zeroed out immediately below.
        with np.errstate(invalid='ignore', divide='ignore'):
            # correlations_z_transformed = np.arctanh(np.array(correlations))
            correlations_z_transformed = np.array([ .5 * np.log((1 + r) / (1 - r)) for r in correlations ])
        correlations_z_transformed[np.isinf(correlations_z_transformed)] = 0
        correlations_z_transformed[np.isnan(correlations_z_transformed)] = 0
        avg_z_transformed_corr = np.mean(correlations_z_transformed)
        var_z_transformed_corr = np.var(correlations_z_transformed)

        # optionally average correlation values across lags within the window
        if average_windows:
            avg = np.mean(np.array(correlations))
            correlations = [avg for _ in correlations]
            avg_sigmoid = np.mean(np.array(correlations_sigmoid))
            correlations_sigmoid = [avg_sigmoid for _ in correlations_sigmoid]

        # Find the peak correlation (largest magnitude, signed) and its corresponding lag
        _abs_idx = np.argmax(np.abs(correlations))
        r_max = correlations[_abs_idx]
        tau_max = _abs_idx + _min_lag if not average_windows else 0
        _abs_idx_sigmoid = np.argmax(np.abs(correlations_sigmoid))
        r_max_sigmoid = correlations_sigmoid[_abs_idx_sigmoid]
        tau_max_sigmoid = _abs_idx_sigmoid + _min_lag if not average_windows else 0

        result = {
            'start_idx': start,
            'center_idx': start + window_size // 2,
            'correlations': correlations,
            'r_max': r_max,
            'tau_max': tau_max,
            'correlations_sigmoid': correlations_sigmoid,
            'r_max_sigmoid': r_max_sigmoid,
            'tau_max_sigmoid': tau_max_sigmoid,
            'avg_z_transformed_corr': avg_z_transformed_corr,
            'var_z_transformed_corr': var_z_transformed_corr
        }

        # Append the result to the list
        results.append(result)

    return results

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
