"""
Existing pipelines read results as text, so the vectorised computation must match the original
window-by-window one exactly, not just approximately.
"""
import numpy as np
import pytest

import cross_correlation
from cross_correlation import FISHER_Z_MAX_R, fisher_z, scale_sigmoid, windowed_cross_correlation


def _reference(x, y, window_size, step_size, max_lag, use_lag_filter=False, lag_filter_min=None, lag_filter_max=None,
               absolute=False, average_windows=False):
    """The original implementation, one window and one lag at a time."""
    x, y = np.asarray(x), np.asarray(y)
    results = []
    _min_lag, _max_lag = -max_lag, max_lag
    if use_lag_filter and not (lag_filter_min is None or lag_filter_max is None):
        _min_lag, _max_lag = min(lag_filter_min, lag_filter_max), max(lag_filter_min, lag_filter_max)
    lag_range = range(_min_lag, _max_lag + 1)
    for start in range(0, len(x) - window_size + 1, step_size):
        x_window, y_window = x[start:start + window_size], y[start:start + window_size]
        if np.ptp(x_window) == 0 or np.ptp(y_window) == 0:
            results.append(cross_correlation._flat_window_result(start, window_size, len(lag_range)))
            continue
        x_window = (x_window - np.mean(x_window)) / np.std(x_window)
        y_window = (y_window - np.mean(y_window)) / np.std(y_window)
        correlations = []
        for lag in lag_range:
            if lag < 0:
                corr = np.mean(x_window[-lag:] * y_window[:lag])
            elif lag > 0:
                corr = np.mean(x_window[:-lag] * y_window[lag:])
            else:
                corr = np.mean(x_window * y_window)
            correlations.append(np.abs(corr) if absolute else corr)
        correlations_sigmoid = scale_sigmoid(np.array(correlations))
        correlations_z = fisher_z(correlations)
        avg_z, var_z = np.mean(correlations_z), np.var(correlations_z)
        if average_windows:
            avg = np.mean(np.array(correlations))
            correlations = [avg for _ in correlations]
            avg_sigmoid = np.mean(np.array(correlations_sigmoid))
            correlations_sigmoid = [avg_sigmoid for _ in correlations_sigmoid]
        idx = np.argmax(np.abs(correlations))
        idx_sigmoid = np.argmax(np.abs(correlations_sigmoid))
        results.append({
            'start_idx': start, 'center_idx': start + window_size // 2,
            'correlations': correlations, 'r_max': correlations[idx],
            'tau_max': idx + _min_lag if not average_windows else 0,
            'correlations_sigmoid': correlations_sigmoid, 'r_max_sigmoid': correlations_sigmoid[idx_sigmoid],
            'tau_max_sigmoid': idx_sigmoid + _min_lag if not average_windows else 0,
            'avg_z_transformed_corr': avg_z, 'var_z_transformed_corr': var_z,
        })
    return results


@pytest.fixture
def signals():
    rng = np.random.default_rng(0)
    x = 800 + 50 * np.convolve(rng.normal(size=2200), np.ones(9) / 3, mode="same")
    y = 800 + 50 * np.convolve(rng.normal(size=2200), np.ones(9) / 3, mode="same")
    return x, 0.5 * np.roll(x, 3) + 0.5 * y


def _assert_identical(windows, reference):
    assert len(windows) == len(reference)
    for window, expected in zip(windows, reference):
        assert window.keys() == expected.keys()
        for key in window:
            # text must match too, which is what ends up in the first sheet of an export
            assert np.array_equal(window[key], expected[key], equal_nan=True), key
            assert str(np.asarray(window[key]).tolist()) == str(np.asarray(expected[key]).tolist()), key
            assert type(window[key]) is type(expected[key]) or key in ("start_idx", "center_idx", "tau_max", "tau_max_sigmoid"), key
            assert str(window[key]) == str(expected[key]) or key.startswith("correlations"), key


SETTINGS = [
    (150, 75, 30, {}),
    (150, 75, 30, {"absolute": True}),
    (150, 75, 30, {"average_windows": True}),
    (150, 75, 30, {"use_lag_filter": True, "lag_filter_min": -5, "lag_filter_max": 10}),
    (150, 75, 30, {"use_lag_filter": True, "lag_filter_min": 10, "lag_filter_max": 30}),
    (150, 75, 30, {"use_lag_filter": True, "lag_filter_min": -30, "lag_filter_max": -10}),
    (100, 1, 10, {}),
    (151, 37, 75, {}),
    (2200, 1, 5, {}),
    (10, 3, 1, {}),
]


@pytest.mark.parametrize("window_size, step_size, max_lag, kwargs", SETTINGS)
def test_results_match_the_original_exactly(signals, window_size, step_size, max_lag, kwargs):
    x, y = signals
    _assert_identical(
        windowed_cross_correlation(x, y, window_size, step_size, max_lag, **kwargs),
        _reference(x, y, window_size, step_size, max_lag, **kwargs),
    )


@pytest.mark.parametrize("kwargs", [{}, {"absolute": True}, {"average_windows": True}])
def test_flat_windows_match_the_original_exactly(signals, kwargs):
    x, y = signals
    x = x.copy()
    x[:200] = 0.1
    y = y.copy()
    y[1000:1300] = 800.0
    windows = windowed_cross_correlation(x, y, 150, 75, 30, **kwargs)
    assert np.isnan(windows[0]['r_max'])
    assert not np.isnan(windows[5]['r_max'])
    _assert_identical(windows, _reference(x, y, 150, 75, 30, **kwargs))


def test_all_flat_windows(signals):
    windows = windowed_cross_correlation(np.full(500, 0.1), signals[1][:500], 150, 75, 30)
    assert len(windows) == 5 and all(np.isnan(window['r_max']) for window in windows)


@pytest.mark.parametrize("batch_size", [1, 2, 7, 28, 29])
def test_batching_does_not_change_results(signals, monkeypatch, batch_size):
    x, y = signals
    expected = _reference(x, y, 150, 75, 30)
    assert len(expected) == 28
    monkeypatch.setattr(cross_correlation, "WINDOWS_PER_BATCH", batch_size)
    _assert_identical(windowed_cross_correlation(x, y, 150, 75, 30), expected)


def test_more_windows_than_one_batch(signals):
    x, y = signals
    windows = windowed_cross_correlation(x, y, 100, 1, 5)
    assert len(windows) > cross_correlation.WINDOWS_PER_BATCH
    _assert_identical(windows, _reference(x, y, 100, 1, 5))


def test_data_shorter_than_a_window_has_no_windows():
    assert windowed_cross_correlation(np.arange(50.0), np.arange(50.0), 150, 75, 30) == []


def test_lists_are_accepted(signals):
    x, y = signals
    _assert_identical(windowed_cross_correlation(list(x), list(y), 150, 75, 30), _reference(x, y, 150, 75, 30))


def test_extreme_correlation_is_clipped_as_before(signals):
    x = signals[0]
    windows = windowed_cross_correlation(x, x, 150, 75, 30)
    assert windows[0]['correlations'][30] == pytest.approx(1)
    assert windows[0]['avg_z_transformed_corr'] == pytest.approx(np.mean(np.arctanh(np.clip(windows[0]['correlations'], -FISHER_Z_MAX_R, FISHER_Z_MAX_R))))
