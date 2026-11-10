"""
The surrogate test with shuffled blocks: the shuffling itself, each dyad's own test, and the group test.
"""
import math
import os
import random

import numpy as np
import pytest
from scipy.stats import zscore

import surrogates
import xlsx
from helpers import N_BEATS, batch_params, ibi, write_dyad, write_person
from measures import MEAN_ABS_R_MAX, MEAN_R, R_AT_LAG_0
from surrogates import BLOCKS, GREATER, MIN_BLOCKS, TWO_SIDED, block_shuffle_test, shuffle_blocks

N_DYADS = 4
N_SURROGATES = 200
BLOCK_LENGTH = 150


# ---------------------------------------------------------------------------
# SHUFFLING
# ---------------------------------------------------------------------------

def test_whole_blocks_move_and_leftover_samples_stay_at_the_end():
    signal = np.arange(14)
    shuffled = shuffle_blocks(signal, 3, [2, 0, 3, 1])
    assert shuffled.tolist() == [6, 7, 8, 0, 1, 2, 9, 10, 11, 3, 4, 5, 12, 13]


def test_original_order_gives_the_original_signal():
    signal = np.random.default_rng(0).normal(size=23)
    assert np.array_equal(shuffle_blocks(signal, 4, range(5)), signal)


def test_shuffled_order_is_never_the_original():
    rng = random.Random(0)
    assert all(surrogates._shuffled_order(2, rng) == [1, 0] for _ in range(50))
    orders = {tuple(surrogates._shuffled_order(MIN_BLOCKS, rng)) for _ in range(3000)}
    assert tuple(range(MIN_BLOCKS)) not in orders
    assert len(orders) == math.factorial(MIN_BLOCKS) - 1


@pytest.mark.parametrize("n_blocks", [0, 1])
def test_fewer_than_two_blocks_cant_be_shuffled(n_blocks):
    with pytest.raises(ValueError, match="can't be shuffled"):
        surrogates._shuffled_order(n_blocks, random.Random(0))


@pytest.mark.parametrize("n_samples, problem", [
    (MIN_BLOCKS * 10, None),
    (MIN_BLOCKS * 10 + 9, None),
    (MIN_BLOCKS * 10 - 1, f"fit only {MIN_BLOCKS - 1} blocks of 10, and at least {MIN_BLOCKS} are needed"),
])
def test_block_count(n_samples, problem):
    result = surrogates._block_count_problem(n_samples, 10)
    assert result == problem if problem is None else problem in result


# ---------------------------------------------------------------------------
# FOLDERS OF DYADS
# ---------------------------------------------------------------------------

@pytest.fixture
def dyads(tmp_path):
    for index in range(N_DYADS):
        write_dyad(tmp_path / "in" / f"dyad{index}", seed=index)
    return tmp_path / "in"


def _run(dyads, column="Coupled", seed=1, block_length=BLOCK_LENGTH, **kwargs):
    kwargs.setdefault("n_surrogates", N_SURROGATES)
    params = batch_params(dyads, dyads, column=column, **kwargs.pop("params", {}))
    return block_shuffle_test(params, str(dyads), block_length, seed=seed, **kwargs)


def test_coupled_dyads_beat_their_shuffled_versions(dyads):
    result = _run(dyads)
    assert result.method == BLOCKS
    assert result.measure == MEAN_ABS_R_MAX
    assert result.side == GREATER
    assert result.block_length == BLOCK_LENGTH
    assert result.dyad_names == [f"dyad{index}" for index in range(N_DYADS)]
    assert result.dyad_p_values == pytest.approx([1 / (N_SURROGATES + 1)] * N_DYADS)
    assert result.p_value == pytest.approx(1 / (N_SURROGATES + 1))
    assert len(result.null_values) == N_SURROGATES
    assert [len(values) for values in result.dyad_null_values] == [N_SURROGATES] * N_DYADS
    assert result.real_value == pytest.approx(np.mean(result.real_values))
    assert result.failures == []
    assert result.n_pairs_possible is None


def test_group_set_is_the_mean_of_one_surrogate_of_each_dyad(dyads):
    result = _run(dyads)
    assert result.null_values == pytest.approx(np.mean(result.dyad_null_values, axis=0))


def test_uncoupled_dyads_are_within_their_shuffled_versions(dyads):
    result = _run(dyads, column="Independent")
    assert result.p_value > 0.05
    assert max(result.dyad_p_values) > 0.05


def test_signed_measure_is_tested_both_ways(dyads):
    result = _run(dyads, measure=MEAN_R)
    assert result.side == TWO_SIDED
    assert result.p_value == pytest.approx(2 / (N_SURROGATES + 1))


def test_orders_possible_are_counted_per_dyad(dyads, monkeypatch):
    lengths = []
    original = surrogates._analysed_pair

    def recording(*args):
        signals, corr_data = original(*args)
        lengths.append(len(signals[1]))
        return signals, corr_data

    monkeypatch.setattr(surrogates, "_analysed_pair", recording)
    result = _run(dyads)
    assert result.dyad_orders_possible == [math.factorial(n // BLOCK_LENGTH) - 1 for n in lengths]
    assert result.n_sets_possible == math.prod(result.dyad_orders_possible)


@pytest.fixture
def correlated(monkeypatch):
    """Records the signals of every correlation of a shuffled version."""
    calls = []
    original = surrogates.correlate_signals

    def recording(signals, config):
        calls.append(signals)
        return original(signals, config)

    monkeypatch.setattr(surrogates, "correlate_signals", recording)
    return calls


@pytest.mark.parametrize("standardised", [False, True])
def test_original_order_reproduces_the_real_value(dyads, monkeypatch, standardised):
    monkeypatch.setattr(surrogates, "_shuffled_order", lambda n_blocks, rng: list(range(n_blocks)))
    result = _run(dyads, n_surrogates=3, params={'standardised_signals': standardised})
    for value, null_values in zip(result.real_values, result.dyad_null_values):
        assert null_values == pytest.approx([value] * 3)


def test_only_b_is_shuffled_and_its_z_scores_move_with_it(dyads, correlated):
    _run(dyads, n_surrogates=5)
    first_a = correlated[0][0]
    for signal_a, signal_b, signal_a_std, signal_b_std in correlated[:5]:
        assert np.array_equal(signal_a, first_a)
        assert np.allclose(zscore(signal_b), signal_b_std)
    assert not np.array_equal(correlated[0][1], correlated[1][1])


def test_same_seed_repeats_the_result_and_another_seed_does_not(dyads):
    first, second, other = _run(dyads, seed=5), _run(dyads, seed=5), _run(dyads, seed=6)
    assert np.array_equal(first.null_values, second.null_values)
    assert first.dyad_p_values == second.dyad_p_values
    assert first.seed == 5
    assert not np.array_equal(first.null_values, other.null_values)


def test_a_dyad_with_too_few_blocks_is_named_and_left_out(dyads):
    folder = dyads / "dyad_short"
    os.makedirs(folder)
    rng = np.random.default_rng(9)
    short = ibi(rng)[:N_BEATS // 4]
    for file_name in ("P1.xlsx", "P2.xlsx"):
        write_person(folder / file_name, {"Coupled": short + rng.normal(0, 5, len(short))})
    result = _run(dyads, block_length=600)
    assert result.dyad_names == [f"dyad{index}" for index in range(N_DYADS)]
    assert [name for name, _ in result.failures] == ["dyad_short"]
    assert f"at least {MIN_BLOCKS} are needed" in result.failures[0][1]


def test_a_dyad_without_the_column_is_named_and_left_out(dyads):
    folder = dyads / "dyad1"
    os.remove(folder / "P2.xlsx")
    write_person(folder / "P2.xlsx", {"Other": np.ones(N_BEATS)})
    result = _run(dyads)
    assert result.dyad_names == ["dyad0", "dyad2", "dyad3"]
    assert result.failures == [("dyad1", "P2.xlsx has no column 'Coupled'")]


def test_no_dyad_with_enough_blocks(dyads):
    with pytest.raises(ValueError, match="No real dyad could be analysed"):
        _run(dyads, block_length=10 ** 6)


@pytest.mark.parametrize("block_length", [0, -3])
def test_a_block_needs_samples(dyads, block_length):
    with pytest.raises(ValueError, match="at least one sample"):
        _run(dyads, block_length=block_length)


def test_a_measure_the_settings_rule_out_is_refused_before_reading(dyads, monkeypatch):
    monkeypatch.setattr(xlsx, "read_xlsx", lambda path: pytest.fail("read a file"))
    with pytest.raises(ValueError, match="Can't compare r at lag 0"):
        _run(dyads, measure=R_AT_LAG_0, params={'checkbox_average_windows': True})


class Cancelled(Exception):
    pass


def test_cancelling_stops_the_test_instead_of_counting_as_a_failure(dyads):
    def progress(done, total, text):
        if done == 2:
            raise Cancelled

    with pytest.raises(Cancelled):
        _run(dyads, progress=progress)
