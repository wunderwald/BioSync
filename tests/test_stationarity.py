"""
KPSS test of level stationarity, per window and for the whole signal: the same values as statsmodels, windows cut
as the correlation cuts them, and what the Correlation tab and the exports say.
"""
import numpy as np
import openpyxl
import pytest

import batch_processing
import callbacks
import corr_plot
import export
import state
from analysis import AnalysisConfig
from cross_correlation import windowed_cross_correlation
from helpers import batch_params, write_dyad
from stationarity import (
    ALPHA, LARGEST_P, SMALLEST_P, format_stationarity, kpss_p_values, signal_stationarity, stationary_share,
    window_p_values,
)


def _config(**overrides):
    settings = dict(
        signal_type='fixed-rate', windowed=True, standardised=False, window_size=100, step_size=50, max_lag=10,
        absolute=False, average_windows=False, use_lag_filter=False, lag_filter_min=-10, lag_filter_max=10,
        max_lag_sxc=10, absolute_sxc=False,
    )
    settings.update(overrides)
    return AnalysisConfig(**settings)


def _drifting(seed, n=120):
    rng = np.random.default_rng(seed)
    return np.cumsum(rng.normal(size=n)) * 0.15 + rng.normal(size=n)


# ---------------------------------------------------------------------------
# THE TEST
# ---------------------------------------------------------------------------

# statsmodels.tsa.stattools.kpss(x, regression='c', nlags='auto')[1], computed with statsmodels 0.14
@pytest.mark.parametrize("seed, expected", [
    (2, 0.08798059014842911), (6, 0.019063343941034896), (8, 0.07221147353145829), (9, 0.06429030572450525),
])
def test_p_is_the_one_of_statsmodels(seed, expected):
    assert kpss_p_values(_drifting(seed))[0] == pytest.approx(expected, abs=1e-12)


def test_white_noise_of_statsmodels():
    # a chance rejection, as 5% of stationary signals have one
    assert kpss_p_values(np.random.default_rng(1).normal(size=500))[0] == pytest.approx(0.02397320613756211, abs=1e-12)


def test_p_is_read_from_a_table_so_it_stops_at_its_ends():
    walk = np.cumsum(np.random.default_rng(2).normal(size=500))
    assert kpss_p_values(walk)[0] == SMALLEST_P
    assert kpss_p_values(np.tile([1.0, -1.0], 100))[0] == LARGEST_P


def test_scale_and_offset_dont_change_p():
    x = _drifting(6)
    assert kpss_p_values(3 * x + 7)[0] == pytest.approx(kpss_p_values(x)[0])


@pytest.mark.parametrize("segment", [np.full(50, 2.0), np.r_[np.ones(49), np.nan], np.ones(1)])
def test_flat_or_incomplete_segments_cant_be_tested(segment):
    assert np.isnan(kpss_p_values(segment)[0])


def test_rows_are_tested_on_their_own():
    rows = np.array([_drifting(seed) for seed in (2, 6, 8)] + [np.full(120, 1.0)])
    expected = [kpss_p_values(row)[0] for row in rows[:3]]
    assert np.allclose(kpss_p_values(rows)[:3], expected) and np.isnan(kpss_p_values(rows)[3])


def test_drift_is_found_and_noise_mostly_passes():
    rng = np.random.default_rng(0)
    noise = kpss_p_values(rng.normal(size=(200, 150)))
    walks = kpss_p_values(np.cumsum(rng.normal(size=(200, 150)), axis=1))
    assert np.mean(noise < ALPHA) < 0.1
    assert np.mean(walks < ALPHA) > 0.6


# ---------------------------------------------------------------------------
# WINDOWS AND SIGNALS
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("window, step", [(100, 50), (100, 100), (37, 11), (500, 1)])
def test_windows_are_those_of_the_correlation(window, step):
    x = np.cumsum(np.random.default_rng(3).normal(size=1000))
    p_values = window_p_values(x, window, step)
    correlated = windowed_cross_correlation(x, x[::-1].copy(), window, step, max_lag=5)
    assert len(p_values) == len(correlated)
    for p, result in zip(p_values, correlated):
        start = result['start_idx']
        assert p == pytest.approx(kpss_p_values(x[start:start + window])[0])


def test_window_longer_than_the_signal_gives_no_windows():
    assert len(window_p_values(np.arange(10.0), 20, 5)) == 0


def test_windowed_and_standard_correlation_test_what_they_correlate():
    a, b = _drifting(2, 400), _drifting(6, 400)
    signals = (a, b, (a - a.mean()) / a.std(), (b - b.mean()) / b.std())
    windowed = signal_stationarity(signals, _config())
    assert windowed['windowed'] and np.allclose(windowed['p_b'], window_p_values(b, 100, 50))
    standard = signal_stationarity(signals, _config(windowed=False, standardised=True))
    assert standard == {'windowed': False, 'p_a': kpss_p_values(a)[0], 'p_b': kpss_p_values(b)[0]}


def test_share_counts_windows_at_or_above_alpha_and_leaves_out_flat_ones():
    assert stationary_share([0.01, 0.05, 0.1, np.nan, 0.049]) == (2, 4)
    assert stationary_share([]) == (0, 0)


# ---------------------------------------------------------------------------
# TEXT
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stationarity, text", [
    (None, "KPSS: no data"),
    ({'windowed': True, 'p_a': [0.1, 0.01, 0.06, 0.1], 'p_b': [0.01, 0.01, np.nan, 0.1]},
     "KPSS, stationary windows (p ≥ 0.05): A 3 of 4 (75%), B 1 of 3 (33%)"),
    ({'windowed': True, 'p_a': [], 'p_b': []}, "KPSS, stationary windows (p ≥ 0.05): A 0 of 0, B 0 of 0"),
    ({'windowed': False, 'p_a': 0.01, 'p_b': 0.0712},
     "KPSS of the whole signal: A p ≤ 0.01, B p = 0.071 (p < 0.05: not stationary)"),
    ({'windowed': False, 'p_a': 0.1, 'p_b': np.nan},
     "KPSS of the whole signal: A p ≥ 0.10, B not testable (flat) (p < 0.05: not stationary)"),
])
def test_text(stationarity, text):
    assert format_stationarity(stationarity) == text


@pytest.fixture
def results(fake_state, monkeypatch):
    windowed = {'windowed': True, 'p_a': [0.1, 0.01], 'p_b': [0.1, 0.1]}
    whole = {'windowed': False, 'p_a': 0.01, 'p_b': 0.1}
    monkeypatch.setitem(state.dat_correlation_data, "stationarity_windows", windowed)
    monkeypatch.setitem(state.dat_correlation_data, "stationarity_signal", whole)
    fake_state.val_INPUT_DATA_VALID.set(True)
    fake_state.val_CORRELATION_SETTINGS_VALID.set(True)
    fake_state.val_CORRELATION_SETTINGS_VALID_SXC.set(True)
    return fake_state


@pytest.mark.parametrize("windowed, start", [(True, "KPSS, stationary windows"), (False, "KPSS of the whole signal")])
def test_tab_shows_the_result_of_the_chosen_correlation(results, windowed, start):
    results.val_checkbox_windowed_xcorr.set(windowed)
    corr_plot.update_stationarity_text()
    assert results.val_stationarity_text.get().startswith(start)


@pytest.mark.parametrize("windowed, setting", [(True, "val_CORRELATION_SETTINGS_VALID"),
                                               (False, "val_CORRELATION_SETTINGS_VALID_SXC")])
def test_tab_says_when_the_settings_dont_allow_a_result(results, windowed, setting):
    results.val_checkbox_windowed_xcorr.set(windowed)
    getattr(results, setting).set(False)
    corr_plot.update_stationarity_text()
    assert results.val_stationarity_text.get() == "KPSS: check the correlation settings."


def test_new_data_clears_the_results(results):
    callbacks.clear_correlation_data()
    assert state.dat_correlation_data["stationarity_windows"] is None
    assert state.dat_correlation_data["stationarity_signal"] is None


# ---------------------------------------------------------------------------
# EXPORT
# ---------------------------------------------------------------------------

def _metadata(path):
    return [(row[0], row[1]) for row in openpyxl.load_workbook(path).worksheets[0].iter_rows(max_col=2, values_only=True)
            if row[0]]


def test_windowed_export_adds_shares_after_the_dfa_rows(tmp_path):
    window = {'start_idx': 0, 'center_idx': 50, 'correlations': [0.5, 0.1, 0.2], 'r_max': 0.5, 'tau_max': -1,
              'avg_z_transformed_corr': 0.25, 'var_z_transformed_corr': 0.75}
    export.export_wxcorr_data(str(tmp_path / "f.xlsx"), {
        'selected_dyad_dir': 'dyad', 'input_file_a': 'a.xlsx', 'input_file_b': 'b.xlsx', 'checkbox_fr': False,
        'is_standardised': False, 'window_size': 100, 'max_lag': 1, 'step_size': 50, 'checkbox_absolute_corr': False,
        'checkbox_average_windows': False, 'checkbox_lag_filter': False, 'lag_filter_min': -1, 'lag_filter_max': 1,
        'signal_a': [1.5], 'signal_a_std': [], 'signal_b': [3.5], 'signal_b_std': [], 'wxcorr': [window],
        'stationarity': {'windowed': True, 'p_a': [0.1, 0.01, 0.06, np.nan], 'p_b': [0.01, 0.01, 0.01, 0.01]},
    })
    metadata = _metadata(tmp_path / "f.xlsx")
    assert metadata[17][0] == 'DFA note'
    assert metadata[18:] == [
        ('KPSS share of stationary windows, signal A', pytest.approx(2 / 3)),
        ('KPSS share of stationary windows, signal B', 0),
        ('KPSS note', "Windows with KPSS p >= 0.05, in which level stationarity isn't rejected: A 2 of 3, B 0 of 4. "
                      "Flat windows can't be tested."),
    ]


def test_standard_export_adds_p_after_the_dfa_rows(tmp_path):
    export.export_sxcorr_data(str(tmp_path / "f.xlsx"), {
        'selected_dyad_dir': 'dyad', 'input_file_a': 'a.xlsx', 'input_file_b': 'b.xlsx', 'checkbox_fr': False,
        'is_standardised': False, 'max_lag': 1, 'checkbox_absolute_corr': False, 'signal_a': [1.5], 'signal_b': [3.5],
        'signal_a_std': [], 'signal_b_std': [], 'sxcorr': {'lags': [0], 'corr': [0.5]},
        'stationarity': {'windowed': False, 'p_a': 0.0712, 'p_b': np.nan},
    })
    metadata = _metadata(tmp_path / "f.xlsx")
    assert metadata[11][0] == 'DFA note'
    assert metadata[12:14] == [('KPSS p, signal A', 0.0712), ('KPSS p, signal B', '-')]
    assert metadata[14][0] == 'KPSS note'


def test_export_without_a_result_has_dashes(tmp_path):
    rows = dict(export._stationarity_metadata(None, windowed=True))
    assert rows['KPSS share of stationary windows, signal A'] == '-'


@pytest.mark.parametrize("windowed, name, key", [
    (True, "wx_dyad0_wxcorr.xlsx", 'KPSS share of stationary windows, signal A'),
    (False, "dyad0_sxcorr.xlsx", 'KPSS p, signal A'),
])
def test_batch_files_have_the_rows(tmp_path, windowed, name, key):
    input_dir, output_dir = tmp_path / "in", tmp_path / "out"
    output_dir.mkdir()
    write_dyad(input_dir / "dyad0", seed=0)
    summary = batch_processing.batch_process(batch_params(input_dir, output_dir, checkbox_windowed_xcorr=windowed))
    assert summary['failed'] == []
    metadata = dict(_metadata(output_dir / name))
    assert 0 <= metadata[key] <= 1
