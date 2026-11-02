from dataclasses import dataclass

from cross_correlation import standard_cross_correlation, windowed_cross_correlation
from dfa import dfa, dfa_wxcorr, dfa_wxcorr_window_averages
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


def signal_dfa(raw_signal_a, raw_signal_b, config):
    """
    DFA of each person's signal. Returns a dict with 'alpha_a', 'alpha_b' (None if not possible) and 'note'.
    Event-based signals use the original intervals: resampling smooths short scales, which raises alpha
    (white noise 0.49 to 0.63 at 5 Hz). Their first and last values are not intervals, see preprocess_dyad.
    """
    def alpha(raw_signal):
        series = raw_signal[1:-1] if config.signal_type == 'event-based' else raw_signal
        try:
            return dfa(series, order=1)[0][0], None
        except ValueError as e:
            return None, str(e)

    alpha_a, note_a = alpha(raw_signal_a)
    alpha_b, note_b = alpha(raw_signal_b)
    return {'alpha_a': alpha_a, 'alpha_b': alpha_b, 'note': note_a or note_b}


def windowed_dfa(wxcorr, config):
    """
    DFA of the windowed correlation over time. Returns a dict with 'alpha_window_averages',
    'alpha_per_lag' (a list of {'lag', 'alpha'}), which are None if not possible, and 'note'.
    Overlapping windows share data, which raises alpha even for unrelated signals (0.49 without overlap,
    1.35 at 97% overlap), so results are only given for windows that don't overlap.
    """
    result = {'alpha_window_averages': None, 'alpha_per_lag': None, 'note': None}
    if config.step_size < config.window_size:
        result['note'] = "DFA over time needs windows that don't overlap (step size of at least the window size)."
        return result

    min_lag = min(config.lag_filter_min, config.lag_filter_max) if config.use_lag_filter else -config.max_lag
    try:
        result['alpha_window_averages'] = dfa_wxcorr_window_averages(wxcorr, order=1)
        if not config.average_windows:     # all lags have the same values then
            result['alpha_per_lag'] = [
                {'lag': o['lag'], 'alpha': o['A'][0]} for o in dfa_wxcorr(wxcorr, min_lag, order=1)
            ]
    except ValueError as e:
        result['note'] = str(e)
    return result


def format_dfa(dfa_signals, dfa_windows):
    """The DFA results as text for the window. dfa_windows is None for standard cross-correlation."""
    if dfa_signals is None:
        return "DFA: no data"
    if dfa_signals['alpha_a'] is None or dfa_signals['alpha_b'] is None:
        lines = [f"DFA per person: not available. {dfa_signals['note']}"]
    else:
        lines = [f"DFA α per person: A {dfa_signals['alpha_a']:.2f}, B {dfa_signals['alpha_b']:.2f}"]
    if dfa_windows is not None:
        if dfa_windows['alpha_window_averages'] is None:
            lines.append(f"DFA over time: not available. {dfa_windows['note']}")
        else:
            lines.append(f"DFA α over time: {dfa_windows['alpha_window_averages']:.2f}")
    return "\n".join(lines)


def analyze_dyad(raw_signal_a, raw_signal_b, config):
    """Returns the preprocessed signals and their correlation result. Doesn't read or write anything else."""
    signals = preprocess_signals(raw_signal_a, raw_signal_b, config)
    return signals, correlate_signals(signals, config)
