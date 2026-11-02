from dataclasses import dataclass

from cross_correlation import standard_cross_correlation, windowed_cross_correlation
from dfa import dfa
from signal_processing import preprocess_dyad


@dataclass(frozen=True)
class AnalysisConfig:
    """Every setting that affects analysis results, so that the GUI, batch and random pairs can't differ."""
    signal_type: str            # 'event-based' or 'fixed-rate'
    windowed: bool
    standardised: bool
    window_size: int
    step_size: int
    max_lag: int
    absolute: bool
    average_windows: bool
    use_lag_filter: bool
    lag_filter_min: int
    lag_filter_max: int
    max_lag_sxc: int
    absolute_sxc: bool

    @classmethod
    def from_params(cls, params):
        return cls(
            signal_type='event-based' if params['checkbox_eb'] else 'fixed-rate',
            windowed=params['checkbox_windowed_xcorr'],
            standardised=params['standardised_signals'],
            window_size=params['window_size'],
            step_size=params['step_size'],
            max_lag=params['max_lag'],
            absolute=params['checkbox_absolute_corr'],
            average_windows=params['checkbox_average_windows'],
            use_lag_filter=params['use_lag_filter'],
            lag_filter_min=params['lag_filter_min'],
            lag_filter_max=params['lag_filter_max'],
            max_lag_sxc=params['max_lag_sxc'],
            absolute_sxc=params['checkbox_absolute_corr_sxc'],
        )

    @property
    def windowed_settings(self):
        """The settings behind windowed results."""
        return (
            self.standardised, self.window_size, self.step_size, self.max_lag, self.absolute,
            self.average_windows, self.use_lag_filter, self.lag_filter_min, self.lag_filter_max,
        )

    @property
    def standard_settings(self):
        """The settings behind standard results."""
        return self.standardised, self.max_lag_sxc, self.absolute_sxc


def preprocess_signals(raw_signal_a, raw_signal_b, config):
    """Returns (signal_a, signal_b, signal_a_std, signal_b_std)."""
    return preprocess_dyad(raw_signal_a, raw_signal_b, signal_type=config.signal_type)


def correlate_signals(signals, config):
    """
    Runs the correlation type chosen in the config on the result of preprocess_signals.
    Returns the result of windowed_cross_correlation or standard_cross_correlation.
    """
    signal_a, signal_b, signal_a_std, signal_b_std = signals
    x = signal_a_std if config.standardised else signal_a
    y = signal_b_std if config.standardised else signal_b

    if config.windowed:
        return windowed_cross_correlation(
            x, y,
            window_size=config.window_size,
            step_size=config.step_size,
            max_lag=config.max_lag,
            absolute=config.absolute,
            average_windows=config.average_windows,
            use_lag_filter=config.use_lag_filter,
            lag_filter_min=config.lag_filter_min,
            lag_filter_max=config.lag_filter_max,
        )
    return standard_cross_correlation(x, y, max_lag=config.max_lag_sxc, absolute=config.absolute_sxc)


def standard_dfa_alpha(sxcorr):
    """DFA scaling exponent of a standard cross-correlation, or None for short lag ranges."""
    try:
        A, _ = dfa(sxcorr['corr'], order=1)
    except ValueError:
        return None
    return A[0]


def analyze_dyad(raw_signal_a, raw_signal_b, config):
    """Returns the preprocessed signals and their correlation result. Doesn't read or write anything else."""
    signals = preprocess_signals(raw_signal_a, raw_signal_b, config)
    return signals, correlate_signals(signals, config)
