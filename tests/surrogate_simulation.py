"""
Checks the surrogate tests on simulated groups of dyads whose coupling is known: how often each method and measure
finds p < 0.05 without coupling (should be about 5% or less), with coupling of several strengths, and with a time
course that everyone in a session shares but no coupling between partners: responses to the same task events at
the same moments, or a steady decline such as habituation.

It uses the functions the analysis uses (preprocessing, correlation, measures, block shuffling, surrogate sets and
p-values), with simulated signals in memory instead of xlsx files, which the other tests cover.

Run from the repository root, for the numbers in TODO.md (takes several minutes):
    app/.venv/bin/python tests/surrogate_simulation.py --groups 200
test_surrogate_simulation.py runs a small version.
"""
import argparse
import os
import random
import sys
import time
from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter
from scipy.stats import ttest_ind

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app'))

from analysis import AnalysisConfig, correlate_signals, preprocess_signals     # noqa: E402
from measures import MEASURES, dyad_measure                                     # noqa: E402
from surrogates import (                                                        # noqa: E402
    BLOCKS, REPAIRED, WELCH, _shuffled_order, comparison_side, repaired_null_distribution,
    shuffle_blocks, surrogate_p_value,
)

ALPHA = 0.05

# EDA-like fixed-rate data: 10 minutes at 2 Hz, 30 s windows, 15 s steps, lags up to 5 s, 30 s blocks
N_SAMPLES = 1200
CONFIG = AnalysisConfig(
    signal_type='fixed-rate', windowed=True, standardised=False, window_size=60, step_size=30, max_lag=10,
    absolute=False, average_windows=False, use_lag_filter=False, lag_filter_min=-10, lag_filter_max=10,
    max_lag_sxc=10, absolute_sxc=False,
)
BLOCK_LENGTH = 60
SMOOTHNESS = 0.95       # how much each sample keeps of the previous one: slow, like skin conductance
COUPLING_LAG = 4        # B follows A by 2 s


EVENT_SPACING = (40, 120)      # samples between the task events of a session: 20 to 60 s
EVENT_TIME_CONSTANT = 6         # samples: a response peaks after 3 s and fades over about 15 s


@dataclass(frozen=True)
class Scenario:
    name: str
    coupling: float = 0.0       # share of B's signal that is A's, a moment later
    events: float = 0.0         # size of everyone's response to the same task events, relative to their own signal
    decline: float = 0.0        # how far everyone's level sinks per window, relative to their own signal


SCENARIOS = (
    Scenario("no coupling"),
    Scenario("coupling 0.2", coupling=0.2),
    Scenario("coupling 0.35", coupling=0.35),
    Scenario("coupling 0.5", coupling=0.5),
    Scenario("shared task events, no coupling", events=1.5),
    Scenario("shared steady decline, no coupling", decline=1.5),
)


def _person(rng, n=N_SAMPLES + COUPLING_LAG):
    signal = lfilter([1], [1, -SMOOTHNESS], rng.normal(size=n))
    return signal / signal.std()


def _shared_course(scenario, rng):
    """What every person of a session has in common: responses to the same events, and a steady decline."""
    events = np.zeros(N_SAMPLES)
    position = rng.integers(*EVENT_SPACING)
    while position < N_SAMPLES:
        events[position] = 1
        position += rng.integers(*EVENT_SPACING)
    t = np.arange(10 * EVENT_TIME_CONSTANT)
    response = (t / EVENT_TIME_CONSTANT) * np.exp(1 - t / EVENT_TIME_CONSTANT)     # peaks at 1
    decline = -np.arange(N_SAMPLES) / CONFIG.window_size
    return scenario.events * np.convolve(events, response)[:N_SAMPLES] + scenario.decline * decline


def simulate_group(scenario, n_dyads, rng):
    """(signal A, signal B) of each dyad of one session."""
    shared = _shared_course(scenario, rng)
    dyads = []
    for _ in range(n_dyads):
        a, b = _person(rng), _person(rng)
        b = scenario.coupling * np.roll(a, COUPLING_LAG) + np.sqrt(1 - scenario.coupling ** 2) * b
        a, b = a[COUPLING_LAG:], b[COUPLING_LAG:]
        dyads.append(tuple(signal + rng.uniform(0.5, 1.5) * shared for signal in (a, b)))
    return dyads


def _measures(signals):
    corr_data = correlate_signals(signals, CONFIG)
    return {measure: dyad_measure(corr_data, CONFIG, measure) for measure in MEASURES}


def _pair_measures(raw_a, raw_b):
    return _measures(preprocess_signals(raw_a, raw_b, CONFIG))


def run_group(dyads, n_surrogates, n_welch_pairs, seed):
    """p of each method and measure for one group: {(method, measure): p}."""
    rng = random.Random(seed)
    p_values = {}

    # real dyads
    real = [_pair_measures(a, b) for a, b in dyads]

    # re-paired people and Welch: every pair of people from different dyads, in a random order of A and B
    people = [signal for dyad in dyads for signal in dyad]
    pairs = [(i, j) for i in range(len(people)) for j in range(i + 1, len(people)) if i // 2 != j // 2]
    pair_values = [_pair_measures(*(people[k] for k in rng.sample(pair, 2))) for pair in pairs]
    for measure in MEASURES:
        real_values = [values[measure] for values in real]
        values = [values[measure] for values in pair_values]
        side = comparison_side(measure, CONFIG)
        null = repaired_null_distribution(values, len(dyads), n_surrogates, rng)
        p_values[(REPAIRED, measure)] = surrogate_p_value(np.mean(real_values), null, side)
        drawn = [values[rng.randrange(len(values))] for _ in range(n_welch_pairs)]
        p_values[(WELCH, measure)] = float(ttest_ind(drawn, real_values, equal_var=False)[1])

    # shuffled blocks of B
    null_by_measure = {measure: [] for measure in MEASURES}
    for a, b in dyads:
        signals = preprocess_signals(a, b, CONFIG)
        n_blocks = len(signals[1]) // BLOCK_LENGTH
        shuffled = []
        for _ in range(n_surrogates):
            order = _shuffled_order(n_blocks, rng)
            shuffled.append(_measures((signals[0], shuffle_blocks(signals[1], BLOCK_LENGTH, order),
                                       signals[2], shuffle_blocks(signals[3], BLOCK_LENGTH, order))))
        for measure in MEASURES:
            null_by_measure[measure].append([values[measure] for values in shuffled])
    for measure in MEASURES:
        side = comparison_side(measure, CONFIG)
        real_value = np.mean([values[measure] for values in real])
        p_values[(BLOCKS, measure)] = surrogate_p_value(real_value, np.mean(null_by_measure[measure], axis=0), side)
    return p_values


def significant_shares(scenario, n_groups, n_dyads, n_surrogates, n_welch_pairs=100, seed=0, progress=None):
    """The share of groups with p < ALPHA, for each (method, measure)."""
    rng = np.random.default_rng(seed)
    counts = {}
    for group in range(n_groups):
        if progress:
            progress(group)
        p_values = run_group(simulate_group(scenario, n_dyads, rng), n_surrogates, n_welch_pairs, seed * 10007 + group)
        for key, p in p_values.items():
            counts[key] = counts.get(key, 0) + (p < ALPHA)
    return {key: count / n_groups for key, count in counts.items()}


def _table(results, n_groups):
    columns = [(REPAIRED, measure) for measure in MEASURES] + [(BLOCKS, measure) for measure in MEASURES] + [
        (WELCH, MEASURES[0])]
    header = "| Scenario | " + " | ".join(f"{method}, {measure}" for method, measure in columns) + " |"
    lines = [header, "|" + "---|" * (len(columns) + 1)]
    for name, shares in results.items():
        lines.append(f"| {name} | " + " | ".join(f"{100 * shares[key]:.0f}%" for key in columns) + " |")
    lines.append(f"\nShare of {n_groups} simulated groups with p < {ALPHA}.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--groups", type=int, default=200)
    parser.add_argument("--dyads", type=int, default=15)
    parser.add_argument("--surrogates", type=int, default=200)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    results = {}
    start = time.time()
    for scenario in SCENARIOS:
        def progress(group, name=scenario.name):
            if group % 20 == 0:
                print(f"{name}: group {group} of {args.groups}, {time.time() - start:.0f} s", file=sys.stderr, flush=True)
        results[scenario.name] = significant_shares(
            scenario, args.groups, args.dyads, args.surrogates, seed=args.seed, progress=progress)
    print(f"{args.dyads} dyads per group, {args.surrogates} surrogates, seed {args.seed}, "
          f"{N_SAMPLES} samples at 2 Hz, windows of {CONFIG.window_size}, blocks of {BLOCK_LENGTH}.\n")
    print(_table(results, args.groups))


if __name__ == "__main__":
    main()
