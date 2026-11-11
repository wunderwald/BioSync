"""
The surrogate test with re-paired people: its p-value, its surrogate sets, and the analysis of a folder of dyads.
"""
import math
import os
import random

import numpy as np
import pytest

import surrogates
import xlsx
from analysis import AnalysisConfig
from helpers import N_BEATS, batch_params, write_dyad, write_person
from measures import MEAN_ABS_R, MEAN_ABS_R_MAX, MEAN_R, R_AT_LAG_0
from surrogates import (
    GREATER, REPAIRED, TWO_SIDED, comparison_side, repaired_null_distribution, repaired_pair_test,
    surrogate_p_value,
)

N_DYADS = 4
N_PAIRS = math.comb(2 * N_DYADS, 2) - N_DYADS
N_SURROGATES = 200


# ---------------------------------------------------------------------------
# P-VALUE AND SIDES
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("real, null, side, expected", [
    (0.5, [0.1, 0.2, 0.6], GREATER, 2 / 4),
    (0.7, [0.1, 0.2, 0.6], GREATER, 1 / 4),       # never 0
    (0.6, [0.1, 0.2, 0.6], GREATER, 2 / 4),       # a tie counts as reaching the real value
    (0.0, [0.1, 0.2, 0.3], GREATER, 4 / 4),
    (0.0, [0.1, 0.2, 0.3], TWO_SIDED, 2 * 1 / 4),
    (0.4, [0.1, 0.2, 0.3], TWO_SIDED, 2 * 1 / 4),
    (0.2, [0.1, 0.2, 0.3], TWO_SIDED, 1.0),       # capped at 1
])
def test_p_value(real, null, side, expected):
    assert surrogate_p_value(real, null, side) == pytest.approx(expected)


def _config(**overrides):
    settings = dict(
        signal_type='event-based', windowed=True, standardised=False, window_size=150, step_size=75, max_lag=30,
        absolute=False, average_windows=False, use_lag_filter=False, lag_filter_min=-30, lag_filter_max=30,
        max_lag_sxc=30, absolute_sxc=False,
    )
    settings.update(overrides)
    return AnalysisConfig(**settings)


@pytest.mark.parametrize("measure, config, side", [
    (MEAN_ABS_R_MAX, _config(), GREATER),
    (MEAN_ABS_R, _config(), GREATER),
    (MEAN_ABS_R, _config(windowed=False), GREATER),
    (MEAN_R, _config(), TWO_SIDED),
    (R_AT_LAG_0, _config(), TWO_SIDED),
    (MEAN_R, _config(absolute=True), GREATER),
    (R_AT_LAG_0, _config(windowed=False, absolute_sxc=True), GREATER),
    (MEAN_R, _config(absolute_sxc=True), TWO_SIDED),           # the standard setting doesn't apply to windowed
    (MEAN_R, _config(windowed=False, absolute=True), TWO_SIDED),
])
def test_comparison_side(measure, config, side):
    assert comparison_side(measure, config) == side


def test_each_surrogate_set_has_different_pairs():
    pair_values = [2.0 ** i for i in range(10)]     # the sum of a set shows which values it has
    means = repaired_null_distribution(pair_values, 4, 300, random.Random(0))
    assert len(means) == 300
    for mean in means:
        assert bin(round(mean * 4)).count("1") == 4


def test_surrogate_sets_need_enough_pairs():
    with pytest.raises(ValueError, match="needs 4 different pairs"):
        repaired_null_distribution([0.1, 0.2, 0.3], 4, 10, random.Random(0))


# ---------------------------------------------------------------------------
# FOLDERS OF DYADS
# ---------------------------------------------------------------------------

@pytest.fixture
def dyads(tmp_path):
    for index in range(N_DYADS):
        write_dyad(tmp_path / "in" / f"dyad{index}", seed=index)
    return tmp_path / "in"


def _run(dyads, column="Coupled", seed=1, **kwargs):
    kwargs.setdefault("n_surrogates", N_SURROGATES)
    params = batch_params(dyads, dyads, column=column, **kwargs.pop("params", {}))
    return repaired_pair_test(params, str(dyads), seed=seed, **kwargs)


def test_coupled_dyads_beat_every_surrogate_set(dyads):
    result = _run(dyads)
    assert result.method == REPAIRED
    assert result.measure == MEAN_ABS_R_MAX
    assert result.side == GREATER
    assert result.dyad_names == [f"dyad{index}" for index in range(N_DYADS)]
    assert result.real_value == pytest.approx(np.mean(result.real_values))
    assert result.real_value > result.null_values.max()
    assert result.p_value == pytest.approx(1 / (N_SURROGATES + 1))
    assert len(result.null_values) == N_SURROGATES
    assert result.n_pairs_possible == result.n_pairs_used == N_PAIRS
    assert result.n_sets_possible == math.comb(N_PAIRS, N_DYADS)
    assert result.failures == []


def test_uncoupled_dyads_are_within_the_surrogates(dyads):
    result = _run(dyads, column="Independent")
    assert result.null_values.min() < result.real_value < result.null_values.max()
    assert result.p_value > 0.05


def test_signed_measure_is_tested_both_ways(dyads):
    result = _run(dyads, measure=MEAN_R)
    assert result.side == TWO_SIDED
    assert result.p_value == pytest.approx(2 / (N_SURROGATES + 1))


def test_same_seed_repeats_the_result_and_another_seed_does_not(dyads):
    first, second, other = _run(dyads, seed=5), _run(dyads, seed=5), _run(dyads, seed=6)
    assert np.array_equal(first.null_values, second.null_values)
    assert first.p_value == second.p_value
    assert first.seed == 5
    assert not np.array_equal(first.null_values, other.null_values)


def test_each_recording_is_read_once(dyads, monkeypatch):
    read = []
    original = xlsx.read_xlsx
    monkeypatch.setattr(xlsx, "read_xlsx", lambda path: read.append(path) or original(path))
    _run(dyads)
    assert len(read) == len(set(read)) == 2 * N_DYADS


def test_each_pair_is_analysed_once_in_either_order(dyads, monkeypatch):
    analysed = []
    original = surrogates.analyze_dyad

    def recording_analyze(raw_signal_a, raw_signal_b, config):
        analysed.append((raw_signal_a[0], raw_signal_b[0]))   # first values tell the people apart
        return original(raw_signal_a, raw_signal_b, config)

    monkeypatch.setattr(surrogates, "analyze_dyad", recording_analyze)
    _run(dyads)
    random_pairs = analysed[N_DYADS:]
    assert len(analysed) == N_DYADS + N_PAIRS
    assert len({frozenset(pair) for pair in random_pairs}) == N_PAIRS
    people_in_file_order = [person for real_dyad in analysed[:N_DYADS] for person in real_dyad]
    a_before_b = [people_in_file_order.index(a) < people_in_file_order.index(b) for a, b in random_pairs]
    assert any(a_before_b) and not all(a_before_b)


def test_a_dyad_without_the_column_is_named_and_left_out(dyads):
    folder = dyads / "dyad1"
    os.remove(folder / "P2.xlsx")
    write_person(folder / "P2.xlsx", {"Other": np.ones(N_BEATS)})
    result = _run(dyads)
    assert result.dyad_names == ["dyad0", "dyad2", "dyad3"]
    assert ("dyad1", "P2.xlsx has no column 'Coupled'") in result.failures
    failed_pairs = [name for name, _ in result.failures if name.startswith("random pair")]
    assert len(failed_pairs) == 2 * (N_DYADS - 1)     # that person with everyone from other dyads
    assert result.n_pairs_used == N_PAIRS - len(failed_pairs)
    assert result.p_value == pytest.approx(1 / (N_SURROGATES + 1))


def test_too_few_pairs_for_a_surrogate_set(dyads, monkeypatch):
    original = surrogates._eligible_random_pairs
    monkeypatch.setattr(surrogates, "_eligible_random_pairs", lambda *args: original(*args)[:N_DYADS - 1])
    with pytest.raises(ValueError, match=f"needs {N_DYADS} different random pairs.*only {N_DYADS - 1}"):
        _run(dyads)


def test_a_measure_the_settings_rule_out_is_refused_before_reading(dyads, monkeypatch):
    monkeypatch.setattr(xlsx, "read_xlsx", lambda path: pytest.fail("read a file"))
    with pytest.raises(ValueError, match="Can't compare r at lag 0"):
        _run(dyads, measure=R_AT_LAG_0, params={'checkbox_average_windows': True})


class Cancelled(Exception):
    pass


@pytest.mark.parametrize("cancel_at", [1, N_DYADS + 2], ids=["real dyads", "random pairs"])
def test_cancelling_stops_the_test_instead_of_counting_as_a_failure(dyads, cancel_at):
    def progress(done, total, text):
        if done == cancel_at:
            raise Cancelled

    with pytest.raises(Cancelled):
        _run(dyads, progress=progress)
