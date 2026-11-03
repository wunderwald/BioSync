import numpy as np
from scipy.interpolate import CubicSpline
from scipy.stats import zscore

# event-based signals are resampled to this rate
EVENT_BASED_SAMPLING_RATE_HZ = 5

def _replace_invalid_EDA(eda):
    '''
    Interpolates across negative samples, the only values that count as invalid for now.
    Deleting them would shift all later samples in time.
    '''
    eda = np.array(eda, dtype=float)
    valid = eda >= 0
    if not valid.any():
        raise ValueError("The signal has no valid samples.")
    indices = np.arange(len(eda))
    return np.interp(indices, indices[valid], eda[valid])

# Heartbeat intervals in ms: 2000 ms is 30 bpm, 250 ms is 240 bpm
TYPICAL_IBI_MS = (250, 2000)

def guess_is_event_based(signal_a, signal_b):
    """
    Guesses whether two signals are heartbeat intervals in ms (event-based) rather than samples (fixed-rate).
    Only values that clearly can't be intervals in ms count as fixed-rate, such as EDA in microsiemens.
    Everything else stays event-based, the default. Returns a plain bool, which Tk variables require.
    """
    values = np.concatenate([np.asarray(signal_a[1:-1], dtype=float), np.asarray(signal_b[1:-1], dtype=float)])
    if len(values) == 0:
        return True
    if bool((values < 0).any()):
        return False
    median = float(np.median(values))
    clearly_not_ms = median < TYPICAL_IBI_MS[0] / 2 or median > TYPICAL_IBI_MS[1] * 5
    return not clearly_not_ms

def standardize(signal):
    '''
    Apply z-score standardisation to signal: zero mean, unit variance.
    (z-scoring != z-transform)
    '''
    return zscore(signal)

def _beat_times_ms(ibi_ms, t_offset_ms=0):
    '''
    Time of the beat that starts each interval, relative to the start of the recording.
    '''
    return np.cumsum(np.insert(ibi_ms, 0, 0)[:-1]) + t_offset_ms

def _ibi_time_series(ibi_ms, t_offset_ms=0, remove_invalid_samples=False):
    '''
    Beat times and interval values. Beat times are computed before invalid intervals are removed, because the
    time an invalid interval took still passed: removing it must not move the beats after it.
    '''
    t_ms_ts = _beat_times_ms(ibi_ms, t_offset_ms)
    ibi_ms_ts = np.array(ibi_ms)
    if remove_invalid_samples:
        valid = (ibi_ms_ts >= 100) & (ibi_ms_ts < 1000)
        if valid.sum() < 2:
            raise ValueError("The signal has fewer than two valid intervals.")
        t_ms_ts, ibi_ms_ts = t_ms_ts[valid], ibi_ms_ts[valid]
    return t_ms_ts, ibi_ms_ts

def resample_ibi(ibi_ms, t_offset_ms=0, target_sampling_rate_hz=5, t_start_ms=None, t_end_ms=None, remove_invalid_samples=False):
    """
    Resample inter-beat intervals (IBI) to a target sampling rate using cubic spline interpolation.
    Parameters:
    -----------
    ibi_ms : list or array-like
        List or array of inter-beat intervals in milliseconds.
    t_offset_ms : int, optional
        The time offset in milliseconds. Default is 0.
    target_sampling_rate_hz : int, optional
        The target sampling rate in Hertz (Hz). Default is 5 Hz.
    t_start_ms, t_end_ms : float, optional
        Time span of the output grid, including the offset. Default is from the first to the last beat.
    remove_invalid_samples : bool, optional
        If True, intervals outside 100-1000 ms are left out of the interpolation. Default is False.
    Returns:
    --------
    ibi_ms_interpl : numpy.ndarray
        The resampled IBI values.
    """
    # convert ibi to time series (t, ibi), with offset on the time axis
    t_ms_ts, ibi_ms_ts = _ibi_time_series(ibi_ms, t_offset_ms, remove_invalid_samples)

    # Create a cubic spline interpolation
    cs = CubicSpline(t_ms_ts, ibi_ms_ts)

    # Generate time grid for interpolation
    sampling_interval_ms = 1000/target_sampling_rate_hz
    t_start_ms = min(t_ms_ts) if t_start_ms is None else t_start_ms
    t_end_ms = max(t_ms_ts) if t_end_ms is None else t_end_ms
    t_ms_interpl = np.arange(t_start_ms, t_end_ms, sampling_interval_ms)

    # Get sample values at new grid
    ibi_ms_interpl = cs(t_ms_interpl)

    return ibi_ms_interpl



def preprocess_dyad(signal_a, signal_b, signal_type, remove_invalid_samples=False):
    """
    Preprocesses two signals (dyad) by filtering invalid values, resampling, and aligning their lengths.
    Event-based signals have the form [t_offset, ibi_1, ..., ibi_n, rest], where t_offset is the time from the
    start of the recording to the first beat and rest is the time from the last beat to the end. Both people are
    assumed to start recording at the same moment, and are resampled onto one time grid over the span they share.
    Parameters:
        signal_a (list or array-like): The first signal to preprocess.
        signal_b (list or array-like): The second signal to preprocess.
        signal_type (str): The type of the signals, must be either 'event-based' or 'fixed-rate'.
        remove_invalid_samples (bool, optional): If True, invalid samples are bridged by interpolation, keeping later samples at their original time. Defaults to False.
    Returns:
        tuple: A tuple containing the preprocessed signal_a and signal_b.
    Raises:
        Exception: If the signal_type is not 'event-based' or 'fixed-rate'.
    """
    if signal_type not in ['event-based', 'fixed-rate']:
        raise Exception("Invalid signal type. Must be 'event-based' or 'fixed-rate'.")

    # optionally replace invalid values (event-based signals handle this during resampling)
    if remove_invalid_samples and signal_type == 'fixed-rate':
        signal_a = _replace_invalid_EDA(signal_a)
        signal_b = _replace_invalid_EDA(signal_b)

    # resample IBI (exclude first and last sample, shift by first sample)
    if signal_type == 'event-based':
        t_offset_ms_a = signal_a[0]
        t_offset_ms_b = signal_b[0]
        ibi_a = signal_a[1:-1]
        ibi_b = signal_b[1:-1]
        beats_a, _ = _ibi_time_series(ibi_a, t_offset_ms_a, remove_invalid_samples)
        beats_b, _ = _ibi_time_series(ibi_b, t_offset_ms_b, remove_invalid_samples)
        t_start_ms = max(beats_a[0], beats_b[0])
        t_end_ms = min(beats_a[-1], beats_b[-1])
        if t_end_ms <= t_start_ms:
            raise ValueError("The two recordings do not overlap in time.")
        signal_a = resample_ibi(ibi_a, t_offset_ms=t_offset_ms_a, target_sampling_rate_hz=EVENT_BASED_SAMPLING_RATE_HZ, t_start_ms=t_start_ms, t_end_ms=t_end_ms, remove_invalid_samples=remove_invalid_samples)
        signal_b = resample_ibi(ibi_b, t_offset_ms=t_offset_ms_b, target_sampling_rate_hz=EVENT_BASED_SAMPLING_RATE_HZ, t_start_ms=t_start_ms, t_end_ms=t_end_ms, remove_invalid_samples=remove_invalid_samples)

    # fix lengths
    min_length = min(len(signal_a), len(signal_b))
    signal_a = signal_a[:min_length]
    signal_b = signal_b[:min_length]

    # a signal that never changes has no correlation with anything
    if np.ptp(signal_a) == 0 or np.ptp(signal_b) == 0:
        raise ValueError("A signal has the same value throughout.")

    # apply z-score standardisation
    signal_a_z_scored = standardize(signal_a)
    signal_b_z_scored = standardize(signal_b)

    return signal_a, signal_b, signal_a_z_scored, signal_b_z_scored 