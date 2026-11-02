import numpy as np

# Below this, DFA has too few distinct window sizes for a usable estimate. With 200 values, alpha of
# white noise (true value 0.5) is between 0.33 and 0.71 in 90% of cases.
MIN_DFA_VALUES = 200

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
        If the data length is less than MIN_DFA_VALUES.
    ValueError
        If the data length is too short for the specified polynomial order.
    
    """
    N = len(data)
    
    if N < MIN_DFA_VALUES:
        raise ValueError(f"DFA needs at least {MIN_DFA_VALUES} values (got {N}).")

    max_window = int(0.1 * N)  # Max window size is 10% of data length
    if max_window < order + 1:
        raise ValueError(f"Data length ({N}) is too short for polynomial order {order}.")
    
    # rounding can give the same size several times, which would count double in the fit
    window_sizes = np.unique(np.logspace(np.log10(10), np.log10(max_window), num=10).astype(int))
    
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

    data = np.asarray(data, dtype=float)
    window_sizes = _make_window_sizes(data, order)
    if np.isnan(data).any():
        raise ValueError("DFA can't use a series with missing values, such as flat windows.")
    if np.ptp(data) == 0:
        raise ValueError("DFA can't use a series with the same value throughout.")
    return _detrended_fluctuation_analysis(data, window_sizes, order)

def dfa_wxcorr_window_averages(wxcorr_data, order=1):
    """
    Performs DFA on the correlation averaged across lags, over time.
    Args:
        wxcorr_data (list of dict): Result of windowed_cross_correlation, from windows that don't overlap.
        order (int, optional): The order of the polynomial for detrending in DFA. Default is 1 (linear detrending).
    Returns:
        float: The scaling exponent alpha.
    """
    A, _ = dfa([np.mean(window['correlations']) for window in wxcorr_data], order)
    return A[0]

def dfa_wxcorr(wxcorr_data, min_lag, order=1):
    """
    Performs DFA on the correlation at each lag, over time.
    Args:
        wxcorr_data (list of dict): Result of windowed_cross_correlation, from windows that don't overlap.
        min_lag (int): The lag of the first correlation value in each window.
        order (int, optional): The order of the polynomial for detrending in DFA. Default is 1 (linear detrending).
    Returns:
        list of dict: A list where each element is a dictionary with keys:
            - 'lag': The lag value.
            - 'A': ndarray [alpha, intercept] where `alpha` is the scaling exponent for this lag.
            - 'F': ndarray of Fluctuation function values for each window in `window_sizes` for this lag.
    """
    correlations_per_lag = np.array([window['correlations'] for window in wxcorr_data]).T

    dfa_per_lag = []
    for lag_index, correlations in enumerate(correlations_per_lag):
        A, F = dfa(correlations, order)
        dfa_per_lag.append({'lag': min_lag + lag_index, 'A': A, 'F': F})

    return dfa_per_lag
