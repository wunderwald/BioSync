"""
Known-lag recovery: the cross-correlation must find the lag and direction that were put into the data.
Convention under test: lag > 0 means A leads B.

Ground truth for the simulated dyads comes from simulated_data/simulated_data.ipynb:
coupling follows a Hanning envelope over the middle 2/3 of the recording, peaking at the centre.
    ex1_drifting_coupling: lag 0
    ex2_leader_follower:   A leads B by 4 s (20 samples at 5 Hz)
    ex3_no_coupling:       independent signals
"""
import numpy as np
import pytest

from cross_correlation import standard_cross_correlation, windowed_cross_correlation

# 60 s windows, as in the notebook's rolling correlation preview
WINDOW_SIZE = 300
STEP_SIZE = 75
MAX_LAG = 30


def _peak_lag(sxcorr):
    return sxcorr["lags"][np.argmax(np.abs(sxcorr["corr"]))]


def _wxcorr(signal_a, signal_b):
    return windowed_cross_correlation(signal_a, signal_b, WINDOW_SIZE, STEP_SIZE, MAX_LAG)


def _central_windows(wxcorr):
    """The middle third of windows, where the simulated coupling is strongest."""
    n = len(wxcorr)
    return wxcorr[n // 3 : 2 * n // 3]


def _median_tau(windows):
    return np.median([w["tau_max"] for w in windows])


def _median_abs_r(windows):
    return np.median([abs(w["r_max"]) for w in windows])


@pytest.fixture
def smooth_noise():
    return np.convolve(np.random.default_rng(0).normal(size=3000), np.ones(9) / 9, mode="same")


# ---------------------------------------------------------------------------
# EXACT SHIFTS
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lag", [1, 7, 20])
def test_standard_xcorr_finds_exact_lag_and_direction(smooth_noise, lag):
    a_leads, b_follows = smooth_noise[lag:], smooth_noise[:-lag]
    assert _peak_lag(standard_cross_correlation(a_leads, b_follows, max_lag=30)) == lag
    assert _peak_lag(standard_cross_correlation(b_follows, a_leads, max_lag=30)) == -lag


@pytest.mark.parametrize("lag", [1, 7, 20])
def test_windowed_xcorr_finds_exact_lag_and_direction(smooth_noise, lag):
    a_leads, b_follows = smooth_noise[lag:], smooth_noise[:-lag]
    assert {w["tau_max"] for w in windowed_cross_correlation(a_leads, b_follows, 150, 75, 30)} == {lag}
    assert {w["tau_max"] for w in windowed_cross_correlation(b_follows, a_leads, 150, 75, 30)} == {-lag}


def test_identical_signals_correlate_perfectly_at_lag_zero(smooth_noise):
    for window in windowed_cross_correlation(smooth_noise, smooth_noise, 150, 75, 30):
        assert window["tau_max"] == 0
        assert window["r_max"] == pytest.approx(1)


# ---------------------------------------------------------------------------
# SIMULATED DYADS, FROM FILE THROUGH PREPROCESSING
# ---------------------------------------------------------------------------

def test_drifting_coupling_is_found_at_lag_zero(load_simulated_dyad):
    central = _central_windows(_wxcorr(*load_simulated_dyad("ex1_drifting_coupling")))
    assert _median_tau(central) == pytest.approx(0, abs=1)
    assert _median_abs_r(central) > 0.6


def test_leader_is_found_at_the_simulated_lag(load_simulated_dyad):
    central = _central_windows(_wxcorr(*load_simulated_dyad("ex2_leader_follower")))
    assert _median_tau(central) == pytest.approx(20, abs=1)
    assert _median_abs_r(central) > 0.6


def test_swapping_people_flips_the_leader(load_simulated_dyad):
    signal_a, signal_b = load_simulated_dyad("ex2_leader_follower")
    central = _central_windows(_wxcorr(signal_b, signal_a))
    assert _median_tau(central) == pytest.approx(-20, abs=1)


def test_no_coupling_stays_below_coupled_dyads(load_simulated_dyad):
    # |r_max| is not near 0 even without coupling, so compare against a coupled dyad.
    uncoupled = _central_windows(_wxcorr(*load_simulated_dyad("ex3_no_coupling")))
    coupled = _central_windows(_wxcorr(*load_simulated_dyad("ex2_leader_follower")))
    assert _median_abs_r(uncoupled) < 0.5
    assert _median_abs_r(uncoupled) < _median_abs_r(coupled) - 0.2
