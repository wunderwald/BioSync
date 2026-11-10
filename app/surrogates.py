"""
Surrogate tests: do real dyads have a higher (or different) measure than surrogates, in which coupling can't exist?
Each surrogate set is built like the real group and gives one group mean. The p-value is the share of surrogate
group means that reach the real group mean.

Re-paired people: each surrogate set has as many pairs as there are real dyads, made of people from different
dyads. It asks whether the real dyads are more coupled than strangers recorded in the same setting.
"""
import math
import os
import random
from dataclasses import dataclass

import numpy as np

import utils
import xlsx
from analysis import AnalysisConfig, analyze_dyad
from batch_processing import _eligible_random_pairs, _no_progress
from measures import MEAN_ABS_R_MAX, dyad_measure, measure_problem

REPAIRED = 're-paired people'

GREATER = 'one-sided (real higher)'
TWO_SIDED = 'two-sided'


@dataclass
class SurrogateResult:
    method: str
    measure: str
    side: str                   # GREATER or TWO_SIDED
    seed: int
    dyad_names: list            # the real dyads that gave a value
    real_values: list           # the measure of each of those dyads
    real_value: float           # their mean, which is tested
    null_values: np.ndarray     # the mean of each surrogate set
    p_value: float
    n_surrogates: int
    n_pairs_possible: int       # pairs of people from different dyads
    n_pairs_used: int           # of those, the pairs that gave a value
    n_sets_possible: int        # different surrogate sets, which limits how small p can usefully be
    failures: list              # (name, reason) for each dyad or pair without a value


def comparison_side(measure, config):
    """
    Real coupling can only make |r_max| and absolute correlations higher. A signed correlation can also be
    negative, for example when one person calms down as the other gets stressed, so it is tested both ways.
    """
    absolute = config.absolute if config.windowed else config.absolute_sxc
    return GREATER if measure == MEAN_ABS_R_MAX or absolute else TWO_SIDED


def surrogate_p_value(real_value, null_values, side):
    """
    The share of surrogate values at least as extreme as the real value, counting the real value as one of them,
    so that p is never 0: with 1000 surrogates, the smallest p is 1/1001.
    """
    null_values = np.asarray(null_values, dtype=float)
    n = len(null_values)
    p_greater = (1 + np.count_nonzero(null_values >= real_value)) / (n + 1)
    if side == GREATER:
        return float(p_greater)
    p_less = (1 + np.count_nonzero(null_values <= real_value)) / (n + 1)
    return float(min(1.0, 2 * min(p_greater, p_less)))


def repaired_null_distribution(pair_values, n_per_set, n_surrogates, rng):
    """The mean of each of n_surrogates sets of n_per_set different pairs, drawn with rng (a random.Random)."""
    if not 1 <= n_per_set <= len(pair_values):
        raise ValueError(f"a surrogate set needs {n_per_set} different pairs, and there are {len(pair_values)}")
    values = np.asarray(pair_values, dtype=float)
    indices = range(len(values))
    return np.array([values[rng.sample(indices, n_per_set)].mean() for _ in range(n_surrogates)])


class _Recordings:
    """Reads each recording once, however many pairs it is part of."""
    def __init__(self, params):
        self.sheet = params['selected_sheet']
        self.has_headers = params['has_headers']
        self.signals = {}

    def signal(self, file_path, column):
        key = (file_path, column)
        if key not in self.signals:
            try:
                self.signals[key] = self._read(file_path, column)
            except Exception as e:
                self.signals[key] = e
        if isinstance(self.signals[key], Exception):
            raise self.signals[key]
        return self.signals[key]

    def _read(self, file_path, column):
        workbook = xlsx.read_xlsx(file_path)
        name = os.path.basename(file_path)
        if self.sheet not in workbook:
            raise ValueError(f"{name} has no sheet '{self.sheet}'")
        columns = xlsx.get_columns(workbook, self.sheet, headers=self.has_headers)
        if column not in columns:
            raise ValueError(f"{name} has no column '{column}'")
        return columns[column]


def _real_dyads(input_dir, dyad_folders):
    """(folder name, file path A, file path B) of each folder with at least two recordings."""
    dyads = []
    for dyad_folder in dyad_folders:
        dyad_path = os.path.join(input_dir, dyad_folder)
        file_names = utils.list_dyad_files(dyad_path)
        if len(file_names) >= 2:
            file_a, file_b, _ = xlsx.choose_dyad_files(dyad_path, file_names)
            dyads.append((dyad_folder, os.path.join(dyad_path, file_a), os.path.join(dyad_path, file_b)))
    return dyads


def _pair_value(recordings, file_path_a, file_path_b, params, config, measure):
    raw_signal_a = recordings.signal(file_path_a, params['selected_column_a'])
    raw_signal_b = recordings.signal(file_path_b, params['selected_column_b'])
    _signals, corr_data = analyze_dyad(raw_signal_a, raw_signal_b, config)
    value = dyad_measure(corr_data, config, measure)
    if np.isnan(value):
        raise ValueError("no correlation, because a signal doesn't change in any window")
    return value


def repaired_pair_test(params, input_dir, n_surrogates=1000, progress=_no_progress, seed=None,
                       measure=MEAN_ABS_R_MAX):
    """
    Compares the real dyads in input_dir with surrogate sets of re-paired people. Every possible pair of people
    from different dyads is analysed once, with person A and B in an order the seed decides. The same seed and
    files give the same result.
    Args:
        params (dict): The settings, see batch_processing.batch_process.
        input_dir (str): A folder with one folder per dyad.
        n_surrogates (int): The number of surrogate sets.
        progress (function): Called with (done, total, text) before each dyad or pair.
        seed (int): Seeds the order of A and B and the surrogate sets.
        measure (str): One of measures.MEASURES.
    Returns:
        SurrogateResult
    Raises:
        ValueError: if the measure doesn't fit the settings, or there are too few dyads or pairs.
    """
    config = AnalysisConfig.from_params(params)
    problem = measure_problem(measure, config)
    if problem:
        raise ValueError(f"Can't compare {measure}: {problem}.")
    if n_surrogates < 1:
        raise ValueError("At least one surrogate set is needed.")

    dyad_folders = sorted(f for f in os.listdir(input_dir) if os.path.isdir(os.path.join(input_dir, f)))
    real_dyads = _real_dyads(input_dir, dyad_folders)
    eligible_pairs = _eligible_random_pairs(input_dir, dyad_folders)
    if not eligible_pairs:
        raise ValueError("No random pairs are possible: all recordings are the same person or share a dyad folder.")

    rng = random.Random(seed)
    ordered_pairs = [tuple(rng.sample(pair, 2)) for pair in eligible_pairs]
    recordings = _Recordings(params)
    failures = []
    total_steps = len(real_dyads) + len(ordered_pairs) + 1

    dyad_names, real_values = [], []
    for index, (name, file_path_a, file_path_b) in enumerate(real_dyads):
        progress(index, total_steps, name)
        try:
            real_values.append(_pair_value(recordings, file_path_a, file_path_b, params, config, measure))
            dyad_names.append(name)
        except Exception as e:
            failures.append((name, str(e)))

    pair_values = []
    for index, (file_path_a, file_path_b) in enumerate(ordered_pairs):
        progress(len(real_dyads) + index, total_steps, "Random pairs")
        try:
            pair_values.append(_pair_value(recordings, file_path_a, file_path_b, params, config, measure))
        except Exception as e:
            failures.append((f"random pair {os.path.basename(file_path_a)}, {os.path.basename(file_path_b)}", str(e)))

    if not real_values:
        raise ValueError("No real dyad could be analysed.")
    if len(pair_values) < len(real_values):
        raise ValueError(
            f"A surrogate set needs {len(real_values)} different random pairs, as many as there are real dyads, "
            f"and only {len(pair_values)} could be analysed."
        )

    progress(total_steps - 1, total_steps, "Surrogate sets")
    null_values = repaired_null_distribution(pair_values, len(real_values), n_surrogates, rng)
    real_value = float(np.mean(real_values))
    side = comparison_side(measure, config)
    return SurrogateResult(
        method=REPAIRED,
        measure=measure,
        side=side,
        seed=seed,
        dyad_names=dyad_names,
        real_values=real_values,
        real_value=real_value,
        null_values=null_values,
        p_value=surrogate_p_value(real_value, null_values, side),
        n_surrogates=n_surrogates,
        n_pairs_possible=len(eligible_pairs),
        n_pairs_used=len(pair_values),
        n_sets_possible=math.comb(len(pair_values), len(real_values)),
        failures=failures,
    )
