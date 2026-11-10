"""
A small version of surrogate_simulation.py: on simulated groups of dyads, the surrogate tests must rarely find
coupling that isn't there, must find strong coupling, and must differ as expected on a time course that everyone
in a session shares. The limits leave room for chance in few groups; the full run gives the exact rates.
"""
import pytest

import surrogate_simulation as sim
from measures import MEAN_ABS_R_MAX, MEAN_R, MEASURES, R_AT_LAG_0
from surrogates import BLOCKS, REPAIRED, WELCH

N_DYADS = 8
N_SURROGATES = 99
SEED = 3

NO_COUPLING, STRONG_COUPLING, SHARED_EVENTS = sim.SCENARIOS[0], sim.SCENARIOS[3], sim.SCENARIOS[4]


@pytest.fixture(scope="module")
def no_coupling():
    return sim.significant_shares(NO_COUPLING, 40, N_DYADS, N_SURROGATES, seed=SEED)


@pytest.mark.parametrize("method", [REPAIRED, BLOCKS, WELCH])
@pytest.mark.parametrize("measure", MEASURES)
def test_few_false_positives_without_coupling(no_coupling, method, measure):
    # 5% expected; up to 6 of 40 groups is still chance
    assert no_coupling[(method, measure)] <= 0.15


def test_strong_coupling_is_found_by_every_method():
    shares = sim.significant_shares(STRONG_COUPLING, 12, N_DYADS, N_SURROGATES, seed=SEED)
    assert min(shares.values()) >= 0.9


def test_a_shared_time_course_is_coupling_for_shuffled_blocks_but_not_for_re_paired_people():
    shares = sim.significant_shares(SHARED_EVENTS, 12, N_DYADS, N_SURROGATES, seed=SEED)
    for measure in (MEAN_R, R_AT_LAG_0):
        assert shares[(BLOCKS, measure)] >= 0.8
    for measure in (MEAN_R, MEAN_ABS_R_MAX, R_AT_LAG_0):
        assert shares[(REPAIRED, measure)] <= 0.3


def test_simulated_coupling_is_where_it_should_be():
    """B follows A by COUPLING_LAG samples, with about the chosen correlation."""
    import numpy as np
    rng = np.random.default_rng(0)
    (a, b), = sim.simulate_group(sim.Scenario("coupling", coupling=0.5), 1, rng)
    lags = range(-8, 9)
    correlations = [np.corrcoef(a[8:-8], np.roll(b, -lag)[8:-8])[0, 1] for lag in lags]
    assert list(lags)[int(np.argmax(correlations))] == sim.COUPLING_LAG
    assert max(correlations) == pytest.approx(0.5, abs=0.15)
