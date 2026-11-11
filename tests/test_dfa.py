"""
DFA results must be right for signals with a known answer, and must be refused when they couldn't be trusted.
"""
import numpy as np
import openpyxl
import pytest

import analysis
import corr_plot
import export
import state
from analysis import AnalysisConfig, format_dfa, signal_dfa, windowed_dfa
from cross_correlation import windowed_cross_correlation
from dfa import MIN_DFA_VALUES, dfa, dfa_wxcorr, dfa_wxcorr_window_averages


def _config(**overrides):
    return AnalysisConfig(**{**dict(
        signal_type='event-based', windowed=True, standardised=False, window_size=150, step_size=150, max_lag=30,
        absolute=False, average_windows=False, use_lag_filter=False, lag_filter_min=-30, lag_filter_max=30,
        max_lag_sxc=150, absolute_sxc=False,
    ), **overrides})


def _signal(kind, n, seed=0):
    rng = np.random.default_rng(seed)
    white = rng.normal(size=n)
    if kind == "white":
        return white
    if kind == "brown":
        return np.cumsum(white)
    frequencies = np.fft.rfftfreq(n)
    frequencies[0] = frequencies[1]
    return np.fft.irfft(np.fft.rfft(white) / np.sqrt(frequencies), n)


@pytest.mark.parametrize("kind, expected", [("white", 0.5), ("pink", 1.0), ("brown", 1.5)])
def test_known_signals_give_their_known_alpha(kind, expected):
    alphas = [dfa(_signal(kind, 2000, seed))[0][0] for seed in range(20)]
    assert np.median(alphas) == pytest.approx(expected, abs=0.05)


def test_scale_of_the_signal_does_not_change_alpha():
    signal = _signal("pink", 500)
    assert dfa(800 + 50 * signal)[0][0] == pytest.approx(dfa(signal)[0][0])


@pytest.mark.parametrize("length", [0, 50, 100, 150, MIN_DFA_VALUES - 1])
def test_series_that_are_too_short_are_refused(length):
    with pytest.raises(ValueError, match="at least 200 values"):
        dfa(np.arange(length, dtype=float) ** 2 + 1)


def test_shortest_allowed_series_has_distinct_window_sizes():
    _, F = dfa(_signal("white", MIN_DFA_VALUES))
    assert len(F) >= 8 and len(np.unique(F)) == len(F)


def test_missing_values_are_refused():
    signal = _signal("white", 500)
    signal[10] = np.nan
    with pytest.raises(ValueError, match="missing values"):
        dfa(signal)


def test_constant_series_is_refused():
    with pytest.raises(ValueError, match="same value"):
        dfa(np.full(500, 0.1))


def _ibi(kind="white", n=600, seed=0):
    signal = _signal(kind, n, seed)
    return list(800 + 60 * (signal - signal.mean()) / signal.std())


def test_event_based_uses_the_intervals_without_first_and_last_value():
    ibi_a, ibi_b = _ibi(seed=0), _ibi(seed=1)
    result = signal_dfa([5000, *ibi_a, 3], [1, *ibi_b, 99999], _config())
    assert result['alpha_a'] == pytest.approx(dfa(ibi_a)[0][0])
    assert result['alpha_b'] == pytest.approx(dfa(ibi_b)[0][0])
    assert result['note'] is None


def test_resampling_does_not_inflate_white_noise():
    alphas = [signal_dfa([500, *_ibi(seed=s), 300], [500, *_ibi(seed=s), 300], _config())['alpha_a'] for s in range(20)]
    assert np.median(alphas) == pytest.approx(0.5, abs=0.06)


def test_fixed_rate_uses_every_sample():
    signal = _ibi(seed=2)
    result = signal_dfa(signal, signal, _config(signal_type='fixed-rate'))
    assert result['alpha_a'] == pytest.approx(dfa(signal)[0][0])


@pytest.mark.parametrize("short_person", ["a", "b"])
def test_short_recording_gives_a_reason_not_a_number(short_person):
    short, long = [500, *_ibi(n=100), 300], [500, *_ibi(), 300]
    a, b = (short, long) if short_person == "a" else (long, short)
    result = signal_dfa(a, b, _config())
    assert result['alpha_' + short_person] is None
    assert "at least 200 values" in result['note']


def _windows(n_windows, window=30, step=30, max_lag=5, seed=0, **kwargs):
    length = window + step * (n_windows - 1)
    rng = np.random.default_rng(seed)
    return windowed_cross_correlation(rng.normal(size=length), rng.normal(size=length), window, step, max_lag, **kwargs)


def _windowed_config(window=30, step=30, max_lag=5, **overrides):
    return _config(window_size=window, step_size=step, max_lag=max_lag, **overrides)


@pytest.mark.parametrize("step", [1, 15, 29])
def test_overlapping_windows_are_refused(step):
    result = windowed_dfa(_windows(300, step=step), _windowed_config(step=step))
    assert result['alpha_window_averages'] is None and result['alpha_per_lag'] is None
    assert "don't overlap" in result['note']


@pytest.mark.parametrize("step", [30, 45])
def test_windows_without_overlap_give_results_per_lag(step):
    windows = _windows(300, step=step)
    result = windowed_dfa(windows, _windowed_config(step=step))
    assert result['note'] is None
    assert result['alpha_window_averages'] == pytest.approx(dfa_wxcorr_window_averages(windows))
    assert [row['lag'] for row in result['alpha_per_lag']] == list(range(-5, 6))


def test_unrelated_signals_show_no_structure_over_time():
    alphas = [windowed_dfa(_windows(400, seed=s), _windowed_config())['alpha_window_averages'] for s in range(15)]
    assert np.median(alphas) == pytest.approx(0.5, abs=0.08)


def test_lag_filter_keeps_the_real_lags():
    kwargs = dict(use_lag_filter=True, lag_filter_min=-2, lag_filter_max=4)
    windows = _windows(300, **kwargs)
    result = windowed_dfa(windows, _windowed_config(**kwargs))
    assert [row['lag'] for row in result['alpha_per_lag']] == list(range(-2, 5))
    correlations_at_lag_4 = [window['correlations'][6] for window in windows]
    assert result['alpha_per_lag'][-1]['alpha'] == pytest.approx(dfa(correlations_at_lag_4)[0][0])


def test_too_few_windows_give_a_reason():
    result = windowed_dfa(_windows(100), _windowed_config())
    assert result['alpha_window_averages'] is None and "at least 200 values" in result['note']


def test_flat_windows_give_a_reason_not_nan():
    rng = np.random.default_rng(0)
    x, y = rng.normal(size=9000), rng.normal(size=9000)
    x[:60] = 1.0
    result = windowed_dfa(windowed_cross_correlation(x, y, 30, 30, 5), _windowed_config())
    assert result['alpha_window_averages'] is None and "flat windows" in result['note']


def test_averaged_windows_have_no_per_lag_result():
    windows = _windows(300, average_windows=True)
    result = windowed_dfa(windows, _windowed_config(average_windows=True))
    assert result['alpha_window_averages'] is not None and result['alpha_per_lag'] is None


SIGNALS = {'alpha_a': 1.0349, 'alpha_b': 0.98, 'note': None}


def test_text_shows_both_people_and_time():
    windows = {'alpha_window_averages': 0.512, 'alpha_per_lag': [], 'note': None}
    assert format_dfa(SIGNALS, windows) == "DFA α per person: A 1.03, B 0.98\nDFA α over time: 0.51"


def test_text_gives_the_reason_when_not_available():
    windows = {'alpha_window_averages': None, 'alpha_per_lag': None, 'note': "Reason."}
    text = format_dfa({'alpha_a': None, 'alpha_b': 1.0, 'note': "Too short."}, windows)
    assert text == "DFA per person: not available. Too short.\nDFA over time: not available. Reason."


def test_text_without_data_and_in_standard_mode():
    assert format_dfa(None, None) == "DFA: no data"
    assert format_dfa(SIGNALS, None) == "DFA α per person: A 1.03, B 0.98"


@pytest.mark.parametrize("windowed, expected_second_line", [(True, "No valid results yet."), (False, None)])
def test_window_text_follows_the_correlation_type(fake_state, monkeypatch, windowed, expected_second_line):
    fake_state.val_checkbox_windowed_xcorr.set(windowed)
    fake_state.val_CORRELATION_SETTINGS_VALID.set(True)
    monkeypatch.setitem(state.dat_correlation_data, "dfa_signals", SIGNALS)
    monkeypatch.setitem(state.dat_correlation_data, "dfa_windows", None)
    corr_plot.update_dfa_text()
    text = fake_state.val_dfa_text.get()
    assert ("over time" in text) == windowed
    if expected_second_line:
        assert expected_second_line in text


def _sheet(path):
    return list(openpyxl.load_workbook(path).worksheets[0].iter_rows(values_only=True))


def _wx_params(**overrides):
    window = {
        'start_idx': 0, 'center_idx': 75, 'correlations': [0.5, -0.25, 0.125], 'r_max': 0.5, 'tau_max': -1,
        'avg_z_transformed_corr': 0.25, 'var_z_transformed_corr': 0.75,
    }
    return {
        'selected_dyad_dir': 'dyad', 'input_file_a': 'a.xlsx', 'input_file_b': 'b.xlsx', 'checkbox_fr': False,
        'is_standardised': False, 'window_size': 150, 'max_lag': 1, 'step_size': 75, 'checkbox_absolute_corr': False,
        'checkbox_average_windows': False, 'checkbox_lag_filter': False, 'lag_filter_min': -1, 'lag_filter_max': 1,
        'signal_a': [1.5], 'signal_a_std': [], 'signal_b': [3.5], 'signal_b_std': [], 'wxcorr': [window], **overrides,
    }


def test_export_adds_dfa_after_the_existing_metadata_and_fills_the_existing_columns(tmp_path):
    export.export_wxcorr_data(str(tmp_path / "f.xlsx"), _wx_params(
        dfa_signals=SIGNALS,
        dfa_windows={'alpha_window_averages': 0.5, 'note': None, 'alpha_per_lag': [{'lag': -1, 'alpha': 0.6}, {'lag': 0, 'alpha': 0.7}]},
    ))
    rows = _sheet(tmp_path / "f.xlsx")
    metadata = [(row[0], row[1]) for row in rows if row[0]]
    assert metadata[13][0] == 'Lag filter maximum'
    assert metadata[14:18] == [
        ('DFA alpha, signal A', 1.0349), ('DFA alpha, signal B', 0.98),
        ('DFA alpha, over time (average across lags)', 0.5), ('DFA note', '-'),
    ]
    header = rows[0]
    assert [rows[1][header.index('dfa_lags')], rows[2][header.index('dfa_lags')]] == [-1, 0]
    assert [rows[1][header.index('dfa_alpha')], rows[2][header.index('dfa_alpha')]] == [0.6, 0.7]


def test_export_shows_why_dfa_is_missing(tmp_path):
    export.export_wxcorr_data(str(tmp_path / "f.xlsx"), _wx_params(
        dfa_signals={'alpha_a': None, 'alpha_b': None, 'note': "Too short."},
        dfa_windows={'alpha_window_averages': None, 'alpha_per_lag': None, 'note': "Overlap."},
    ))
    rows = _sheet(tmp_path / "f.xlsx")
    metadata = {row[0]: row[1] for row in rows if row[0]}
    assert metadata['DFA alpha, signal A'] == '-'
    assert metadata['DFA note'] == "Too short. Overlap."
    assert rows[1][rows[0].index('dfa_alpha')] == '-'


def test_standard_export_keeps_the_old_row_empty_and_adds_the_new_ones(tmp_path):
    export.export_sxcorr_data(str(tmp_path / "f.xlsx"), {
        'selected_dyad_dir': 'dyad', 'input_file_a': 'a.xlsx', 'input_file_b': 'b.xlsx', 'checkbox_fr': False,
        'is_standardised': False, 'max_lag': 1, 'checkbox_absolute_corr': False, 'signal_a': [1.5], 'signal_b': [3.5],
        'signal_a_std': [], 'signal_b_std': [], 'sxcorr': {'lags': [0], 'corr': [0.5]}, 'dfa_signals': SIGNALS,
    })
    metadata = [(row[0], row[1]) for row in _sheet(tmp_path / "f.xlsx") if row[0]]
    assert metadata[8] == ('Alpha (DFA scaling exponent)', '-')
    assert metadata[9:12] == [('DFA alpha, signal A', 1.0349), ('DFA alpha, signal B', 0.98), ('DFA note', '-')]
