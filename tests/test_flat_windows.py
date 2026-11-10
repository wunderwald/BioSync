"""
A window where a signal doesn't change has no correlation. It must be recognisable as invalid, and must not
affect any other result.
"""
import io

import numpy as np
import pytest

import surrogates
import plot
from analysis import AnalysisConfig
from cross_correlation import average_wxcorr_matrices, windowed_cross_correlation
from measures import MEAN_R
from signal_processing import preprocess_dyad

WINDOW, STEP, MAX_LAG = 150, 75, 30
VALUE_KEYS = ('r_max', 'tau_max', 'r_max_sigmoid', 'tau_max_sigmoid', 'avg_z_transformed_corr', 'var_z_transformed_corr')


@pytest.fixture
def signal():
    return np.convolve(np.random.default_rng(0).normal(size=1000), np.ones(9) / 9, mode="same")


def _wxcorr(x, y, **kwargs):
    return windowed_cross_correlation(x, y, WINDOW, STEP, MAX_LAG, **kwargs)


def _with_flat_start(signal):
    flat = signal.copy()
    flat[:WINDOW] = 0.1     # the standard deviation of this isn't exactly 0 in floating point
    return flat


def _assert_flat(window, n_lags=2 * MAX_LAG + 1):
    assert np.isnan(window['correlations']).all() and len(window['correlations']) == n_lags
    assert np.isnan(window['correlations_sigmoid']).all() and len(window['correlations_sigmoid']) == n_lags
    assert all(np.isnan(window[key]) for key in VALUE_KEYS)


@pytest.mark.parametrize("flat_signal", ["a", "b"])
@pytest.mark.parametrize("kwargs", [{}, {"absolute": True}, {"average_windows": True}])
def test_flat_window_is_nan_and_others_are_unchanged(signal, flat_signal, kwargs):
    flat = _with_flat_start(signal)
    other = np.roll(signal, 3)
    x, y = (flat, other) if flat_signal == "a" else (other, flat)

    windows = _wxcorr(x, y, **kwargs)

    _assert_flat(windows[0])
    assert windows[0]['start_idx'] == 0 and windows[0]['center_idx'] == WINDOW // 2
    assert not np.isnan(windows[3]['r_max'])
    assert windows[5]['r_max'] == _wxcorr(signal if flat_signal == "a" else other,
                                          other if flat_signal == "a" else signal, **kwargs)[5]['r_max']


def test_flat_window_has_the_filtered_number_of_lags(signal):
    windows = _wxcorr(_with_flat_start(signal), signal, use_lag_filter=True, lag_filter_min=-5, lag_filter_max=10)
    _assert_flat(windows[0], n_lags=16)
    assert len(windows[5]['correlations']) == 16


def test_group_average_leaves_out_a_flat_window(signal):
    other = np.roll(signal, 3)
    intact, with_flat = _wxcorr(signal, other), _wxcorr(_with_flat_start(signal), other)

    average = average_wxcorr_matrices([intact, with_flat], -MAX_LAG)

    assert average[0]['correlations'] == pytest.approx(list(intact[0]['correlations']))
    assert average[0]['r_max'] == pytest.approx(intact[0]['r_max'])
    assert average[0]['tau_max'] == intact[0]['tau_max']
    assert average[0]['avg_z_transformed_corr'] == pytest.approx(intact[0]['avg_z_transformed_corr'])


def test_group_average_peak_is_the_largest_magnitude(signal):
    windows = _wxcorr(signal, -signal)
    average = average_wxcorr_matrices([windows, windows], -MAX_LAG)
    assert average[0]['r_max'] == pytest.approx(-1)
    assert average[0]['tau_max'] == 0


def test_group_average_of_only_flat_windows_is_nan(signal, recwarn):
    with_flat = _wxcorr(_with_flat_start(signal), signal)
    average = average_wxcorr_matrices([with_flat, with_flat], -MAX_LAG)
    _assert_flat(average[0])
    assert not recwarn.list


def test_pair_with_only_flat_windows_has_no_value(signal, recwarn):
    config = AnalysisConfig(
        signal_type='fixed-rate', windowed=True, standardised=False, window_size=WINDOW, step_size=STEP,
        max_lag=MAX_LAG, absolute=False, average_windows=False, use_lag_filter=False, lag_filter_min=-MAX_LAG,
        lag_filter_max=MAX_LAG, max_lag_sxc=1, absolute_sxc=False,
    )
    assert surrogates._measure_of(_wxcorr(_with_flat_start(signal), signal), config, MEAN_R) == pytest.approx(
        np.nanmean([w['correlations'] for w in _wxcorr(_with_flat_start(signal), signal)])
    )
    with pytest.raises(ValueError, match="doesn't change in any window"):
        surrogates._measure_of(_wxcorr(np.full_like(signal, 0.1), signal), config, MEAN_R)
    assert not recwarn.list


@pytest.mark.parametrize("flat_windows", ["some", "all"])
def test_plot_handles_flat_windows(signal, flat_windows):
    x = np.full_like(signal, 0.1) if flat_windows == "all" else _with_flat_start(signal)
    windows = _wxcorr(x, signal)
    assert np.isnan(windows[0]['r_max'])
    plot.plot_windowed_cross_correlation(windows, WINDOW, MAX_LAG, STEP, x, signal).savefig(io.BytesIO())


@pytest.mark.parametrize("signal_type, constant", [("fixed-rate", [5.0] * 300), ("event-based", [500] + [800] * 300 + [300])])
@pytest.mark.parametrize("flat_person", [0, 1])
def test_signal_with_the_same_value_throughout_is_rejected(signal_type, constant, flat_person):
    varied = list(800 + 50 * np.random.default_rng(0).normal(size=len(constant)))
    pair = [varied, varied]
    pair[flat_person] = constant
    with pytest.raises(ValueError, match="same value throughout"):
        preprocess_dyad(pair[0], pair[1], signal_type=signal_type)


def test_group_average_of_averaged_windows_has_no_lag(signal):
    windows = [_wxcorr(signal, np.roll(signal, shift), average_windows=True) for shift in (2, 5)]
    assert {window['tau_max'] for dyad in windows for window in dyad} == {0}
    average = average_wxcorr_matrices(windows, -MAX_LAG, average_windows=True)
    assert {window['tau_max'] for window in average} == {0}
    assert {window['tau_max_sigmoid'] for window in average} == {0}
    assert average[0]['r_max'] == pytest.approx(np.mean([dyad[0]['correlations'][0] for dyad in windows]))


def test_group_average_without_averaged_windows_keeps_its_lags(signal):
    windows = [_wxcorr(signal, np.roll(signal, 3)) for _ in range(2)]
    average = average_wxcorr_matrices(windows, -MAX_LAG)
    assert [window['tau_max'] for window in average] == [window['tau_max'] for window in windows[0]]
