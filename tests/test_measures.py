"""
The number each dyad contributes to a surrogate test. Checked against values computed independently of the
correlation code, for example Pearson r with numpy.
"""
import numpy as np
import pytest

import surrogates
from analysis import AnalysisConfig, correlate_signals
from cross_correlation import standard_cross_correlation, windowed_cross_correlation
from helpers import batch_params, write_dyad
from measures import MEAN_ABS_R_MAX, MEAN_R, MEASURES, R_AT_LAG_0, dyad_measure, measure_problem

WINDOW, STEP, MAX_LAG = 100, 50, 10


def _config(**overrides):
    settings = dict(
        signal_type='fixed-rate', windowed=True, standardised=False, window_size=WINDOW, step_size=STEP,
        max_lag=MAX_LAG, absolute=False, average_windows=False, use_lag_filter=False,
        lag_filter_min=-MAX_LAG, lag_filter_max=MAX_LAG, max_lag_sxc=MAX_LAG, absolute_sxc=False,
    )
    settings.update(overrides)
    return AnalysisConfig(**settings)


@pytest.fixture
def signals():
    rng = np.random.default_rng(1)
    x = np.convolve(rng.normal(size=600), np.ones(5) / 5, mode="same")
    y = 0.6 * np.roll(x, 3) + 0.4 * rng.normal(size=600)
    return x, y


def _correlate(signals, config):
    x, y = signals
    return correlate_signals((x, y, x, y), config)


def _window(correlations, r_max):
    return {'correlations': correlations, 'r_max': r_max}


# ---------------------------------------------------------------------------
# VALUES
# ---------------------------------------------------------------------------

def test_mean_r_is_the_mean_over_windows_and_lags():
    windows = [_window([0.1, 0.5, -0.3], 0.5), _window([0.2, 0.2, 0.8], 0.8)]
    assert dyad_measure(windows, _config(max_lag=1), MEAN_R) == pytest.approx(1.5 / 6)


def test_mean_abs_r_max_ignores_the_sign_of_each_peak():
    windows = [_window([0.1, -0.8, 0.3], -0.8), _window([0.4, 0.2, 0.1], 0.4)]
    assert dyad_measure(windows, _config(max_lag=1), MEAN_ABS_R_MAX) == pytest.approx(0.6)


def test_r_at_lag_0_is_the_pearson_r_of_each_window(signals):
    x, y = signals
    config = _config()
    windows = _correlate(signals, config)
    starts = range(0, len(x) - WINDOW + 1, STEP)
    pearson = [np.corrcoef(x[s:s + WINDOW], y[s:s + WINDOW])[0, 1] for s in starts]
    assert dyad_measure(windows, config, R_AT_LAG_0) == pytest.approx(np.mean(pearson))


@pytest.mark.parametrize("low, high", [(-2, 3), (0, 5), (-6, 0)])
def test_r_at_lag_0_is_found_within_a_lag_filter(signals, low, high):
    unfiltered = dyad_measure(_correlate(signals, _config()), _config(), R_AT_LAG_0)
    config = _config(use_lag_filter=True, lag_filter_min=low, lag_filter_max=high)
    assert dyad_measure(_correlate(signals, config), config, R_AT_LAG_0) == pytest.approx(unfiltered)


def test_mean_abs_r_max_is_at_least_mean_abs_r_at_lag_0(signals):
    config = _config()
    windows = _correlate(signals, config)
    lag_0 = np.mean([abs(w['correlations'][MAX_LAG]) for w in windows])
    assert dyad_measure(windows, config, MEAN_ABS_R_MAX) >= lag_0


def test_standard_correlation_measures(signals):
    x, y = signals
    config = _config(windowed=False)
    result = standard_cross_correlation(x, y, MAX_LAG)
    assert dyad_measure(result, config, R_AT_LAG_0) == pytest.approx(np.corrcoef(x, y)[0, 1])
    assert dyad_measure(result, config, MEAN_ABS_R_MAX) == pytest.approx(np.max(np.abs(result['corr'])))
    assert dyad_measure(result, config, MEAN_R) == pytest.approx(np.mean(result['corr']))


def test_flat_windows_are_left_out(signals):
    x, y = signals
    x = x.copy()
    x[:WINDOW] = 0.1
    config = _config()
    windows = windowed_cross_correlation(x, y, WINDOW, STEP, MAX_LAG)
    valid = [w for w in windows if not np.isnan(w['r_max'])]
    assert 0 < len(valid) < len(windows)
    for measure in MEASURES:
        assert dyad_measure(windows, config, measure) == pytest.approx(dyad_measure(valid, config, measure))


def test_only_flat_windows_give_nan(signals, recwarn):
    _, y = signals
    config = _config()
    windows = windowed_cross_correlation(np.full_like(y, 0.1), y, WINDOW, STEP, MAX_LAG)
    for measure in MEASURES:
        assert np.isnan(dyad_measure(windows, config, measure))
    assert not recwarn.list


# ---------------------------------------------------------------------------
# SETTINGS THAT RULE A MEASURE OUT
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("measure, config, expected", [
    (MEAN_R, _config(average_windows=True), None),
    (MEAN_ABS_R_MAX, _config(average_windows=True), "average windows"),
    (R_AT_LAG_0, _config(average_windows=True), "average windows"),
    (R_AT_LAG_0, _config(use_lag_filter=True, lag_filter_min=1, lag_filter_max=5), "leaves out lag 0"),
    (R_AT_LAG_0, _config(use_lag_filter=True, lag_filter_min=-5, lag_filter_max=-1), "leaves out lag 0"),
    (R_AT_LAG_0, _config(use_lag_filter=True, lag_filter_min=0, lag_filter_max=5), None),
    (R_AT_LAG_0, _config(windowed=False, average_windows=True), None),
    (MEAN_ABS_R_MAX, _config(), None),
    ("median r", _config(), "unknown measure"),
])
def test_measure_problem(measure, config, expected):
    problem = measure_problem(measure, config)
    if expected is None:
        assert problem is None
    else:
        assert expected in problem


def test_measure_refuses_settings_it_cant_use(signals):
    config = _config(average_windows=True)
    with pytest.raises(ValueError, match="average windows"):
        dyad_measure(_correlate(signals, config), config, R_AT_LAG_0)


# ---------------------------------------------------------------------------
# IN THE RANDOM PAIR ANALYSIS
# ---------------------------------------------------------------------------

@pytest.fixture
def dyads(tmp_path):
    for index in range(3):
        write_dyad(tmp_path / "in" / f"dyad{index}", seed=index)
    return tmp_path / "in"


def test_random_pair_analysis_compares_the_chosen_measure(dyads):
    params = batch_params(dyads, dyads)
    mean_r = surrogates.welch_random_pair_test(params, str(dyads), 4, seed=2)
    r_max = surrogates.welch_random_pair_test(params, str(dyads), 4, seed=2, measure=MEAN_ABS_R_MAX)
    for mean_r_values, r_max_values in ((mean_r.null_values, r_max.null_values), (mean_r.real_values, r_max.real_values)):
        assert len(mean_r_values) == len(r_max_values)
        assert all(r > abs(m) for m, r in zip(mean_r_values, r_max_values))


def test_random_pair_analysis_refuses_a_measure_before_analysing(dyads, monkeypatch):
    monkeypatch.setattr(surrogates, "_analysed_pair", lambda *a, **k: pytest.fail("analysed a pair"))
    params = batch_params(dyads, dyads, checkbox_average_windows=True)
    with pytest.raises(ValueError, match="Can't compare r at lag 0"):
        surrogates.welch_random_pair_test(params, str(dyads), 4, measure=R_AT_LAG_0)
