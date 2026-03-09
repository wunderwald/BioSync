import numpy as np

def _detrended_fluctuation_analysis(data, window_sizes, order=1):
    """
    Perform Detrended Fluctuation Analysis (DFA) on a time series to estimate 
    long-range correlations through the scaling exponent α.

    Parameters:
    -----------
    data : array_like
        1D time series data (e.g., physiological signals, financial data, etc.).
        Must contain at least `max(window_sizes)` samples.
    window_sizes : array_like
        Window sizes (in samples) at which to compute fluctuations. 
        Must satisfy:
        1. All elements > `order + 1` (e.g., for `order=1`, min window ≥ 4).
        2. Recommended: Logarithmically spaced (e.g., `np.logspace(np.log10(10), np.log10(100), 10).astype(int)`).
        3. Max window ≤ 10% of signal length (e.g., 1000-point signal → max window ≤ 100).
    order : int, optional (default=1)
        Order of the polynomial used for detrending:
        - 1: Linear detrending (standard for most applications).
        - 2: Quadratic detrending (use if strong curvature is present).
        - 0: No detrending (not recommended for DFA).

    Returns:
    --------
    A : ndarray
        [alpha, intercept] where `alpha` is the scaling exponent.
    F : ndarray
        Fluctuation function values for each window in `window_sizes`.
    """

    # --- Input validation ---
    data = np.asarray(data)
    if data.ndim > 1:
        if data.shape[0] == 1:
            data = data.T
        else:
            raise ValueError("Data must be 1D. Use data.ravel() if needed.")
    data = data.squeeze()
    if data.ndim != 1:
        raise ValueError("Data must be a 1D time series.")

    window_sizes = np.asarray(window_sizes, dtype=int)
    if window_sizes.ndim != 1:
        raise ValueError("window_sizes must be a 1D array of window sizes.")

    if len(data) < max(window_sizes):
        raise ValueError(f"Signal length ({len(data)}) < max window size ({max(window_sizes)}).")

    if order < 0:
        raise ValueError("Order must be ≥ 0 (0: no detrending, 1: linear, etc.).")

    if min(window_sizes) <= order + 1:
        raise ValueError(
            f"All window sizes must be > order + 1 ({order + 1}). "
            f"Found min(window_sizes) = {min(window_sizes)}."
        )

    # --- DFA [based on DFA_fun.m by Alon] ---
    n_window_sizes = len(window_sizes)
    F = np.zeros(n_window_sizes)
    N = len(data)

    for h in range(n_window_sizes):
        w = window_sizes[h]
        n = int(np.floor(N / w))
        Nfloor = n * w
        D = data[:Nfloor]
        
        # Integrated series
        y = np.cumsum(D - np.mean(D))
        
        # Prepare segments
        bin_edges = np.arange(0, Nfloor, w)
        vec = np.arange(1, w + 1)
        
        # Calculate local trends and detrend
        y_hat = np.zeros_like(y)
        for j in range(n):
            segment = y[bin_edges[j]:bin_edges[j]+w]
            coeff = np.polyfit(vec, segment, order)
            y_hat[bin_edges[j]:bin_edges[j]+w] = np.polyval(coeff, vec)
        
        # Calculate fluctuation for this window size
        F[h] = np.sqrt(np.mean((y - y_hat) ** 2))
    
    # Calculate scaling coefficient
    A = np.polyfit(np.log(window_sizes), np.log(F), 1)
    
    return A, F

def _make_window_sizes(data, order=1):
    """
    Automatically determine appropriate window sizes for DFA based on the data length.

    Parameters:
    -----------
    data : array_like
        1D time series data (e.g., physiological signals, financial data, etc.).
    order : int, optional (default=1)
        Order of the polynomial used for detrending.

    Returns:
    --------
    window_sizes : ndarray
        Recommended window sizes for DFA that are logarithmically spaced between min and max size. 
    
    Raises
    ------
    ValueError
        If the data length is less than 100 samples.
    ValueError
        If the data length is too short for the specified polynomial order.
    
    """
    N = len(data)
    
    if N < 100:
        raise ValueError(f"Data length must be at least 100 samples for reliable DFA (got {N}).")

    max_window = int(0.1 * N)  # Max window size is 10% of data length
    if max_window < order + 1:
        raise ValueError(f"Data length ({N}) is too short for polynomial order {order}.")
    
    window_sizes = np.logspace(np.log10(10), np.log10(max_window), num=10).astype(int)
    
    return window_sizes

def dfa(data, order=1):
    """
    Performs Detrended Fluctuation Analysis (DFA) on the input data. Automatically determines appropriate window sizes based on the data length.
    See detailed documentation (about order, window_sizes...) in `_detrended_fluctuation_analysis` and `_make_window_sizes`.
    
    Parameters:
    -----------
    data : array_like
        1D time series data (e.g., physiological signals, financial data, etc.).
    order : int, optional (default=1)
        Order of the polynomial used for detrending.

    Returns:
    --------
    A : ndarray
        [alpha, intercept] where `alpha` is the scaling exponent:
        - α ≈ 0.5: White noise (uncorrelated).
        - α ≈ 1: Pink noise (1/f dynamics).
        - α ≈ 1.5: Non-stationary or strongly trending data.
    F : ndarray
        Fluctuation function values for each window in `window_sizes`.    
    """

    window_sizes = _make_window_sizes(data, order)
    return _detrended_fluctuation_analysis(data, window_sizes, order)

def dfa_wxcorr_window_averages(wxcorr_data, max_lag, order=1):
    if not wxcorr_data:
        return np.array([-1]), np.array([-1])
    
    # calculate correlation averages per window
    per_window_averages = []
    for window in wxcorr_data:
        avg_corr = np.mean(window['correlations'])
        per_window_averages.append(avg_corr)

    A, F = dfa(per_window_averages,  order)

    return A[0]

def dfa_wxcorr(wxcorr_data, max_lag, order=1):
    """
    Performs Detrended Fluctuation Analysis (DFA) on cross-correlation data for each lag.
    Args:
        wxcorr_data (list of dict): List of dictionaries, each representing a window of cross-correlation data.
            Each dictionary should have the keys:
                - 'lags': list or array of lag values.
                - 'correlations': list or array of correlation values corresponding to each lag.
        max_lag (int): The maximum lag value of wxcorr windows (lags in windows go from -max_lag to +max_lag).
        order (int, optional): The order of the polynomial for detrending in DFA. Default is 1 (linear detrending).
    Returns:
        list of dict: A list where each element is a dictionary with keys:
            - 'lag': The lag value.
            - 'A': ndarray [alpha, intercept] where `alpha` is the scaling exponent for this lag.
            - 'F': ndarray of Fluctuation function values for each window in `window_sizes` for this lag.
        If `wxcorr_data` is empty or None, returns (np.array([-1]), np.array([-1])).
    """
    
    if not wxcorr_data:
        return []

    # extract horizontal lines of wxcorr plot (lists of correlation values per in-window lag)
    lags = range(-max_lag, max_lag + 1)
    correlations_per_lag = {lag: [] for lag in lags}
    for window in wxcorr_data:
        for i, correlation in enumerate(window['correlations']):
            correlations_per_lag[i-max_lag].append(correlation)
    
    # for each correlation line, perform DFA
    dfa_per_lag = []
    for lag, correlations in correlations_per_lag.items():
        A, F = dfa(correlations, order)
        dfa_per_lag.append({'lag': lag, 'A': A, 'F': F})

    return dfa_per_lag