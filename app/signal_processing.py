import numpy as np
from scipy.interpolate import CubicSpline
from scipy.stats import zscore

def _remove_invalid_IBI(ibi_ms):
    return [sample for sample in ibi_ms if sample >= 100 and sample < 1000]

def _remove_invalid_EDA(eda):
    print("!! EDA filter not implemented yet.") # TODO: Implement EDA filter
    return [sample for sample in eda if sample >= 0]

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

def resample_ibi(ibi_ms, t_offset_ms=0, target_sampling_rate_hz=5, scale_output=False, t_start_ms=None, t_end_ms=None):
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
    scale_output : bool, optional
        If True, scales the output IBI to maintain the same total sum as the original IBI. Default is False.
    t_start_ms, t_end_ms : float, optional
        Time span of the output grid, including the offset. Default is from the first to the last beat.
    Returns:
    --------
    ibi_ms_interpl_out : numpy.ndarray
        The resampled IBI values.
    """
    # convert ibi to time series (t, ibi), with offset on the time axis
    t_ms_ts = _beat_times_ms(ibi_ms, t_offset_ms)
    ibi_ms_ts = np.array(ibi_ms)

    # Create a cubic spline interpolation
    cs = CubicSpline(t_ms_ts, ibi_ms_ts)

    # Generate time grid for interpolation
    sampling_interval_ms = 1000/target_sampling_rate_hz
    t_start_ms = min(t_ms_ts) if t_start_ms is None else t_start_ms
    t_end_ms = max(t_ms_ts) if t_end_ms is None else t_end_ms
    t_ms_interpl = np.arange(t_start_ms, t_end_ms, sampling_interval_ms)

    # Get sample values at new grid
    ibi_ms_interpl = cs(t_ms_interpl)

    # optionally scale interpolated ibi
    sum_ibi_original = sum(ibi_ms)
    sum_ibi_interpl = sum(ibi_ms_interpl)
    scl = sum_ibi_original / sum_ibi_interpl
    ibi_ms_interpl_out = ibi_ms_interpl * (scl if scale_output else 1)

    return ibi_ms_interpl_out



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
        remove_invalid_samples (bool, optional): If True, invalid samples will be removed from the signals. Defaults to False.
    Returns:
        tuple: A tuple containing the preprocessed signal_a and signal_b.
    Raises:
        Exception: If the signal_type is not 'event-based' or 'fixed-rate'.
    """
    if signal_type not in ['event-based', 'fixed-rate']:
        raise Exception("Invalid signal type. Must be 'event-based' or 'fixed-rate'.")

    # optionally remove invalid values
    if remove_invalid_samples:
        signal_a = _remove_invalid_IBI(signal_a) if signal_type == 'event-based' else _remove_invalid_EDA(signal_a)
        signal_b = _remove_invalid_IBI(signal_b) if signal_type == 'event-based' else _remove_invalid_EDA(signal_b)

    # resample IBI (exclude first and last sample, shift by first sample)
    if signal_type == 'event-based':
        t_offset_ms_a = signal_a[0]
        t_offset_ms_b = signal_b[0]
        ibi_a = signal_a[1:-1]
        ibi_b = signal_b[1:-1]
        beats_a = _beat_times_ms(ibi_a, t_offset_ms_a)
        beats_b = _beat_times_ms(ibi_b, t_offset_ms_b)
        t_start_ms = max(beats_a[0], beats_b[0])
        t_end_ms = min(beats_a[-1], beats_b[-1])
        if t_end_ms <= t_start_ms:
            raise ValueError("The two recordings do not overlap in time.")
        signal_a = resample_ibi(ibi_a, t_offset_ms=t_offset_ms_a, target_sampling_rate_hz=5, t_start_ms=t_start_ms, t_end_ms=t_end_ms)
        signal_b = resample_ibi(ibi_b, t_offset_ms=t_offset_ms_b, target_sampling_rate_hz=5, t_start_ms=t_start_ms, t_end_ms=t_end_ms)

    # fix lengths
    min_length = min(len(signal_a), len(signal_b))
    signal_a = signal_a[:min_length]
    signal_b = signal_b[:min_length]

    # apply z-score standardisation
    signal_a_z_scored = standardize(signal_a)
    signal_b_z_scored = standardize(signal_b)

    return signal_a, signal_b, signal_a_z_scored, signal_b_z_scored 