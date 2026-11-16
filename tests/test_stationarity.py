"""
KPSS test of level stationarity, per window and for the whole signal: the same values as statsmodels, windows cut
as the correlation cuts them, and what the Correlation tab and the exports say.
"""
import numpy as np
import pytest

import batch_processing
import callbacks
import corr_plot
import export
import state
from analysis import AnalysisConfig
from cross_correlation import windowed_cross_correlation
from helpers import EXPORT_WINDOW, batch_params, export_params, read_column, read_metadata, read_notes, write_dyad
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

def test_windowed_export_has_shares_and_the_p_of_each_window(tmp_path):
    path = tmp_path / "f.xlsx"
    windows = [dict(EXPORT_WINDOW, start_idx=start) for start in (0, 75, 150, 225)]
    export.export_wxcorr_data(str(path), export_params(
        wxcorr=windows, stationarity={'windowed': True, 'p_a': [0.1, 0.01, 0.06, np.nan], 'p_b': [0.01, 0.01, 0.01, 0.01]},
    ))
    metadata, notes = read_metadata(path), read_notes(path)
    assert metadata['kpss_stationary_share_a'] == pytest.approx(2 / 3)
    assert notes['kpss_stationary_share_a'] == "2 of 3 windows with KPSS p >= 0.05"
    assert metadata['kpss_stationary_share_b'] == 0
    assert read_column(path, "windows", "kpss_p_a") == [0.1, 0.01, 0.06, None]     # a flat window is empty


def test_standard_export_has_the_p_of_each_whole_signal(tmp_path):
    path = tmp_path / "f.xlsx"
    export.export_sxcorr_data(str(path), export_params(
        windowed=False, stationarity={'windowed': False, 'p_a': 0.0712, 'p_b': np.nan}))
    metadata, notes = read_metadata(path), read_notes(path)
    assert (metadata['kpss_p_a'], metadata['kpss_p_b']) == (0.0712, None)
    assert notes['kpss_p_b'] == "flat signal, can't be tested"
    assert notes['kpss_p_a'].startswith("KPSS of the whole signal; p < 0.05: not stationary.")


@pytest.mark.parametrize("windowed, name", [(True, 'kpss_stationary_share_a'), (False, 'kpss_p_a')])
def test_export_without_a_result_has_empty_cells_and_says_why(tmp_path, windowed, name):
    path = tmp_path / "f.xlsx"
    (export.export_wxcorr_data if windowed else export.export_sxcorr_data)(str(path), export_params(windowed=windowed))
    assert read_metadata(path)[name] is None and read_notes(path)[name]


@pytest.mark.parametrize("windowed, name, key", [
    (True, "BioSync_wcc_dyad0.xlsx", 'kpss_stationary_share_a'),
    (False, "BioSync_scc_dyad0.xlsx", 'kpss_p_a'),
])
def test_batch_files_have_the_rows(tmp_path, windowed, name, key):
    input_dir, output_dir = tmp_path / "in", tmp_path / "out"
    output_dir.mkdir()
    write_dyad(input_dir / "dyad0", seed=0)
    summary = batch_processing.batch_process(batch_params(input_dir, output_dir, checkbox_windowed_xcorr=windowed))
    assert summary['failed'] == []
    assert 0 <= read_metadata(output_dir / name)[key] <= 1
