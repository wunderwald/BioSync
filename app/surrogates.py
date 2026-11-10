"""
Surrogate tests: do real dyads have a higher (or different) measure than surrogates, in which coupling can't exist?
Each surrogate set is built like the real group and gives one group mean. The p-value is the share of surrogate
group means that reach the real group mean.

Re-paired people: each surrogate set has as many pairs as there are real dyads, made of people from different
dyads. It asks whether the real dyads are more coupled than strangers recorded in the same setting.

Shuffled blocks: partner B's signal is cut into blocks, which are put in a random order. It keeps each signal's
short-term course and breaks the timing between the partners. It asks whether a dyad's coupling depends on the
moment-to-moment timing, and gives a p-value for each dyad as well as for the group.

Random pairs with Welch's t-test: the test of earlier versions, kept so that their results can be repeated. It
compares the values of random pairs with those of the real dyads, as if every random pair were independent.

surrogate_analysis runs any of them.
"""
import hashlib
import itertools
import math
import os
import random
from dataclasses import dataclass

import numpy as np
from scipy.stats import ttest_ind

import utils
import xlsx
from analysis import AnalysisConfig, analyze_dyad, correlate_signals
from cross_correlation import average_wxcorr_matrices
from measures import MEAN_ABS_R_MAX, MEAN_R, dyad_measure, measure_problem

REPAIRED = 're-paired people'
BLOCKS = 'shuffled blocks'
WELCH = "random pairs, Welch's t-test"
METHODS = (REPAIRED, BLOCKS, WELCH)

# fewer blocks have too few orders for a dyad to be significant: 4 blocks have 24, so p can't go below about 0.04
MIN_BLOCKS = 5

GREATER = 'one-sided (real higher)'
TWO_SIDED = 'two-sided'

SIGNIFICANCE_LEVEL = 0.05


@dataclass
class SurrogateResult:
    method: str
    measure: str
    side: str                   # GREATER or TWO_SIDED
    seed: int
    dyad_names: list            # the real dyads that gave a value
    real_values: list           # the measure of each of those dyads
    real_value: float           # their mean, which is tested
    null_values: np.ndarray     # the mean of each surrogate set. For Welch: the value of each random pair
    p_value: float
    n_surrogates: int
    n_sets_possible: int        # different surrogate sets, which limits how small p can usefully be (None for Welch)
    failures: list              # (name, reason) for each dyad or pair without a value
    # re-paired people and Welch
    n_pairs_possible: int = None        # pairs of people from different dyads
    n_pairs_used: int = None            # of those, the pairs that gave a value. For Welch, repeats count again.
    left_out_files: list = None         # (file path, reason) of recordings that can't be in a random pair
    # shuffled blocks, with one entry per dyad in dyad_names
    block_length: int = None
    dyad_null_values: list = None       # the measure of each of the dyad's surrogates
    dyad_p_values: list = None
    dyad_orders_possible: list = None   # different block orders, which limits how small the dyad's p can be
    # Welch
    t_statistic: float = None
    avg_wxcorr_real: list = None        # group-average windowed results, None for standard correlation
    avg_wxcorr_surrogates: list = None
    window_counts_real: list = None     # windows of each real dyad and random pair (empty for standard correlation)
    window_counts_surrogates: list = None


def _no_progress(done, total, text):
    pass


def _file_hash(file_path):
    with open(file_path, 'rb') as file:
        return hashlib.sha256(file.read()).hexdigest()


def _files_without_sheet(input_dir, dyad_folders, sheet):
    """(file path, reason) of each recording that doesn't have the sheet, such as a result file in a dyad folder."""
    left_out = []
    for dyad_folder in dyad_folders:
        dyad_path = os.path.join(input_dir, dyad_folder)
        for file_name in utils.list_dyad_files(dyad_path):
            file_path = os.path.join(dyad_path, file_name)
            sheet_names = xlsx.read_sheet_names(file_path)
            if sheet_names is None:
                left_out.append((file_path, "can't be read"))
            elif sheet not in sheet_names:
                left_out.append((file_path, f"no sheet '{sheet}'"))
    return left_out


def _eligible_random_pairs(input_dir, dyad_folders, excluded=()):
    """
    Lists the pairs of recordings that can be used as random pairs. Recordings are told apart by their content,
    because preprocessing/group_to_dyads.py copies a person's file to many folders. This leaves out self-pairs,
    and real pairs, which are any two recordings that share a dyad folder.
    Args:
        input_dir (str): Path to the input directory containing dyad folders with Excel files.
        dyad_folders (list): Names of the dyad folders, in a fixed order.
        excluded (collection): File paths to leave out, see _files_without_sheet.
    Returns:
        list: (file_path_a, file_path_b) pairs, in a fixed order.
    """
    path_of_recording = {}
    real_pairs = set()
    for dyad_folder in dyad_folders:
        dyad_path = os.path.join(input_dir, dyad_folder)
        recordings = set()
        for file_name in utils.list_dyad_files(dyad_path):
            file_path = os.path.join(dyad_path, file_name)
            if file_path in excluded:
                continue
            recording = _file_hash(file_path)
            path_of_recording.setdefault(recording, file_path)
            recordings.add(recording)
        real_pairs.update(frozenset(pair) for pair in itertools.combinations(recordings, 2))
    return [
        (path_of_recording[recording_a], path_of_recording[recording_b])
        for recording_a, recording_b in itertools.combinations(path_of_recording, 2)
        if frozenset((recording_a, recording_b)) not in real_pairs
    ]


def _random_pair_candidates(input_dir, dyad_folders, params):
    """The eligible pairs and the left-out files. Raises ValueError if no pair is possible."""
    left_out = _files_without_sheet(input_dir, dyad_folders, params['selected_sheet'])
    eligible_pairs = _eligible_random_pairs(input_dir, dyad_folders, {path for path, _ in left_out})
    if not eligible_pairs:
        reason = "all recordings are the same person or share a dyad folder"
        if left_out:
            reason += f", or are left out because they don't have the sheet '{params['selected_sheet']}'"
        raise ValueError(f"No random pairs are possible: {reason}.")
    return eligible_pairs, left_out


def _draw_random_pairs(eligible_pairs, n_random_pairs, rng):
    """Random pairs with replacement, with a random person A and B, as in earlier versions."""
    return [rng.sample(rng.choice(eligible_pairs), 2) for _ in range(n_random_pairs)]


def format_p(p_value):
    if p_value != p_value:      # NaN
        return "p = -"
    return "p < 0.001" if p_value < 0.001 else f"p = {p_value:.3f}"


def result_summary(result):
    """One sentence that says what was tested and the result, for the export and the app."""
    n = len(result.real_values)
    if result.method == REPAIRED:
        compared = f"{result.n_surrogates} sets of {n} re-paired people"
    elif result.method == BLOCKS:
        compared = f"{result.n_surrogates} shuffled versions of each dyad, in blocks of {result.block_length} samples"
    else:
        compared = f"{result.n_surrogates} random pairs with Welch's t-test"
    sentence = f"{result.measure} of {n} real dyads compared with {compared} ({result.side}): "
    if result.method == WELCH:
        t_text = "t = -" if result.t_statistic != result.t_statistic else f"t = {result.t_statistic:.2f}"
        return sentence + f"{t_text}, {format_p(result.p_value)}."
    sentence += f"{format_p(result.p_value)}"
    if result.method == BLOCKS:
        n_significant = sum(p < SIGNIFICANCE_LEVEL for p in result.dyad_p_values)
        sentence += f" for the group, and {n_significant} of {n} dyads with p < {SIGNIFICANCE_LEVEL} on their own"
    return sentence + "."


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


def _measure_of(corr_data, config, measure):
    value = dyad_measure(corr_data, config, measure)
    if np.isnan(value):
        raise ValueError("no correlation, because a signal doesn't change in any window")
    return value


def _analysed_pair(recordings, file_path_a, file_path_b, params, config):
    raw_signal_a = recordings.signal(file_path_a, params['selected_column_a'])
    raw_signal_b = recordings.signal(file_path_b, params['selected_column_b'])
    return analyze_dyad(raw_signal_a, raw_signal_b, config)


def _pair_value(recordings, file_path_a, file_path_b, params, config, measure):
    _signals, corr_data = _analysed_pair(recordings, file_path_a, file_path_b, params, config)
    return _measure_of(corr_data, config, measure)


def _check_measure(measure, config):
    problem = measure_problem(measure, config)
    if problem:
        raise ValueError(f"Can't compare {measure}: {problem}.")


def _dyad_folders(input_dir):
    return sorted(f for f in os.listdir(input_dir) if os.path.isdir(os.path.join(input_dir, f)))


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
    _check_measure(measure, config)
    if n_surrogates < 1:
        raise ValueError("At least one surrogate set is needed.")

    dyad_folders = _dyad_folders(input_dir)
    real_dyads = _real_dyads(input_dir, dyad_folders)
    eligible_pairs, left_out = _random_pair_candidates(input_dir, dyad_folders, params)

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
        left_out_files=left_out,
    )


def shuffle_blocks(signal, block_length, order):
    """
    The signal with its whole blocks of block_length samples in the given order. Samples after the last whole
    block stay at the end.
    """
    signal = np.asarray(signal)
    n_whole = len(order) * block_length
    blocks = signal[:n_whole].reshape(len(order), block_length)
    return np.concatenate([blocks[list(order)].ravel(), signal[n_whole:]])


def _shuffled_order(n_blocks, rng):
    """A random order of the blocks, other than the original one, so that every surrogate is shuffled."""
    if n_blocks < 2:
        raise ValueError(f"{n_blocks} blocks can't be shuffled")
    original = list(range(n_blocks))
    while True:
        order = rng.sample(original, n_blocks)
        if order != original:
            return order


def _block_count_problem(n_samples, block_length):
    n_blocks = n_samples // block_length
    if n_blocks < MIN_BLOCKS:
        return (
            f"{n_samples} samples fit only {n_blocks} blocks of {block_length}, "
            f"and at least {MIN_BLOCKS} are needed"
        )
    return None


def _block_surrogate_values(signals, config, measure, block_length, n_surrogates, rng):
    """The measure of n_surrogates versions of the dyad, with B's blocks shuffled. B's z-scores keep their order."""
    signal_a, signal_b, signal_a_std, signal_b_std = signals
    n_blocks = len(signal_b) // block_length
    values = np.empty(n_surrogates)
    for index in range(n_surrogates):
        order = _shuffled_order(n_blocks, rng)
        shuffled = (
            signal_a, shuffle_blocks(signal_b, block_length, order),
            signal_a_std, shuffle_blocks(signal_b_std, block_length, order),
        )
        values[index] = dyad_measure(correlate_signals(shuffled, config), config, measure)
    return values


def block_shuffle_test(params, input_dir, block_length, n_surrogates=1000, progress=_no_progress, seed=None,
                       measure=MEAN_ABS_R_MAX):
    """
    Compares each real dyad in input_dir with versions of it in which B's blocks are shuffled, and the group mean
    with surrogate sets that take one shuffled version of each dyad. The same seed and files give the same result.
    Args:
        params (dict): The settings, see batch_processing.batch_process.
        input_dir (str): A folder with one folder per dyad.
        block_length (int): Samples per block, after preprocessing (for event-based data at 5 Hz).
        n_surrogates (int): The number of shuffled versions of each dyad, which is also the number of sets.
        progress (function): Called with (done, total, text) before each dyad.
        seed (int): Seeds the block orders.
        measure (str): One of measures.MEASURES.
    Returns:
        SurrogateResult
    Raises:
        ValueError: if the measure doesn't fit the settings, or no dyad could be analysed.
    """
    config = AnalysisConfig.from_params(params)
    _check_measure(measure, config)
    if n_surrogates < 1:
        raise ValueError("At least one surrogate is needed.")
    if block_length < 1:
        raise ValueError("A block needs at least one sample.")

    real_dyads = _real_dyads(input_dir, _dyad_folders(input_dir))
    rng = random.Random(seed)
    recordings = _Recordings(params)
    failures = []
    dyad_names, real_values, dyad_null_values, dyad_orders_possible = [], [], [], []
    for index, (name, file_path_a, file_path_b) in enumerate(real_dyads):
        progress(index, len(real_dyads) + 1, name)
        try:
            signals, corr_data = _analysed_pair(recordings, file_path_a, file_path_b, params, config)
            problem = _block_count_problem(len(signals[1]), block_length)
            if problem:
                raise ValueError(problem)
            value = _measure_of(corr_data, config, measure)
            null_values = _block_surrogate_values(signals, config, measure, block_length, n_surrogates, rng)
        except Exception as e:
            failures.append((name, str(e)))
            continue
        dyad_names.append(name)
        real_values.append(value)
        dyad_null_values.append(null_values)
        dyad_orders_possible.append(math.factorial(len(signals[1]) // block_length) - 1)

    if not real_values:
        raise ValueError("No real dyad could be analysed.")

    progress(len(real_dyads), len(real_dyads) + 1, "Surrogate sets")
    side = comparison_side(measure, config)
    # set i takes each dyad's surrogate i. The orders were drawn independently, so the sets are random combinations.
    # A shuffled version whose windows are all flat has no value, and is left out of its set.
    null_values = np.nanmean(np.array(dyad_null_values), axis=0)
    real_value = float(np.mean(real_values))
    return SurrogateResult(
        method=BLOCKS,
        measure=measure,
        side=side,
        seed=seed,
        dyad_names=dyad_names,
        real_values=real_values,
        real_value=real_value,
        null_values=null_values,
        p_value=surrogate_p_value(real_value, null_values, side),
        n_surrogates=n_surrogates,
        n_sets_possible=math.prod(dyad_orders_possible),
        failures=failures,
        block_length=block_length,
        dyad_null_values=dyad_null_values,
        dyad_p_values=[
            surrogate_p_value(value, dyad_null[~np.isnan(dyad_null)], side)
            for value, dyad_null in zip(real_values, dyad_null_values)
        ],
        dyad_orders_possible=dyad_orders_possible,
    )


def _random_pair_name(file_path_a, file_path_b):
    return f"random pair {os.path.basename(file_path_a)}, {os.path.basename(file_path_b)}"


def _group_average(all_wxcorr, params):
    if not all_wxcorr:
        return None
    min_lag = (
        min(params['lag_filter_min'], params['lag_filter_max']) if params['use_lag_filter'] else -params['max_lag']
    )
    return average_wxcorr_matrices(all_wxcorr, min_lag, params['checkbox_average_windows'])


def welch_random_pair_test(params, input_dir, n_random_pairs=100, progress=_no_progress, seed=None, measure=MEAN_R):
    """
    The test of earlier versions: Welch's t-test between the values of random pairs and those of the real dyads.
    Random pairs are drawn with replacement, with a random person A and B, exactly as before, so that a seed
    repeats an earlier result. A pair that is drawn again is analysed only once.
    Args:
        params (dict): The settings, see batch_processing.batch_process.
        input_dir (str): A folder with one folder per dyad.
        n_random_pairs (int): The number of random pairs to draw.
        progress (function): Called with (done, total, text) before each pair or dyad.
        seed (int): Seeds the random pairs.
        measure (str): One of measures.MEASURES. Earlier versions compared mean r.
    Returns:
        SurrogateResult, with the value of each random pair as null_values
    """
    config = AnalysisConfig.from_params(params)
    _check_measure(measure, config)

    dyad_folders = _dyad_folders(input_dir)
    eligible_pairs, left_out = _random_pair_candidates(input_dir, dyad_folders, params)
    rng = random.Random(seed)
    random_pairs = _draw_random_pairs(eligible_pairs, n_random_pairs, rng)
    real_dyads = _real_dyads(input_dir, dyad_folders)

    recordings = _Recordings(params)
    analysed = {}
    failures = []
    total_steps = len(random_pairs) + len(real_dyads)

    def analyse(name, file_path_a, file_path_b, values, all_wxcorr):
        """Adds the pair's value, or its failure. Its windowed result counts for the group average either way."""
        key = (file_path_a, file_path_b)
        if key not in analysed:
            try:
                analysed[key] = _analysed_pair(recordings, file_path_a, file_path_b, params, config)[1]
            except Exception as e:
                analysed[key] = e
        try:
            if isinstance(analysed[key], Exception):
                raise analysed[key]
            if config.windowed:
                all_wxcorr.append(analysed[key])
            values.append(_measure_of(analysed[key], config, measure))
            return True
        except Exception as e:
            failures.append((name, str(e)))
            return False

    pair_values, wxcorr_surrogates = [], []
    for index, (file_path_a, file_path_b) in enumerate(random_pairs):
        progress(index, total_steps, "Random pairs")
        analyse(_random_pair_name(file_path_a, file_path_b), file_path_a, file_path_b, pair_values, wxcorr_surrogates)

    dyad_names, real_values, wxcorr_real = [], [], []
    for index, (name, file_path_a, file_path_b) in enumerate(real_dyads):
        progress(len(random_pairs) + index, total_steps, name)
        if analyse(name, file_path_a, file_path_b, real_values, wxcorr_real):
            dyad_names.append(name)

    t_statistic, p_value = ttest_ind(pair_values, real_values, equal_var=False)
    return SurrogateResult(
        method=WELCH,
        measure=measure,
        side=TWO_SIDED,
        seed=seed,
        dyad_names=dyad_names,
        real_values=real_values,
        real_value=float(np.mean(real_values)) if real_values else np.nan,
        null_values=np.array(pair_values),
        p_value=float(p_value),
        n_surrogates=n_random_pairs,
        n_sets_possible=None,
        failures=failures,
        n_pairs_possible=len(eligible_pairs),
        n_pairs_used=len(pair_values),
        left_out_files=left_out,
        t_statistic=float(t_statistic),
        avg_wxcorr_real=_group_average(wxcorr_real, params) if config.windowed else None,
        avg_wxcorr_surrogates=_group_average(wxcorr_surrogates, params) if config.windowed else None,
        window_counts_real=[len(wxcorr) for wxcorr in wxcorr_real],
        window_counts_surrogates=[len(wxcorr) for wxcorr in wxcorr_surrogates],
    )


def surrogate_analysis(method, params, input_dir, n_surrogates, seed, measure, block_length=None,
                       progress=_no_progress):
    """
    Runs one of METHODS on the dyads in input_dir. n_surrogates is the number of surrogate sets, of shuffled
    versions of each dyad, or of random pairs for Welch. block_length is only for shuffled blocks.
    Returns a SurrogateResult.
    """
    if method == REPAIRED:
        return repaired_pair_test(params, input_dir, n_surrogates, progress, seed, measure)
    if method == BLOCKS:
        if block_length is None:
            raise ValueError("Shuffled blocks need a block length.")
        return block_shuffle_test(params, input_dir, block_length, n_surrogates, progress, seed, measure)
    if method == WELCH:
        return welch_random_pair_test(params, input_dir, n_surrogates, progress, seed, measure)
    raise ValueError(f"Unknown method '{method}'.")


# ---------------------------------------------------------------------------
# PLANNING A TEST IN THE APP
# ---------------------------------------------------------------------------

SURROGATE_DISTRIBUTION = 'surrogate distribution'   # the test of re-paired people and shuffled blocks
DEFAULT_SURROGATES = {REPAIRED: 1000, BLOCKS: 1000, WELCH: 100}
MIN_WELCH_GROUP = 2         # the t-test needs at least two values per group


@dataclass(frozen=True)
class SurrogateChoice:
    """What the app's Surrogates tab asks for, so that a job gets it in one piece."""
    method: str
    measure: str
    n_surrogates: int
    block_length: int = None


def choice_problem(choice, config):
    """Why the test can't run with these settings, or None. The same rules as the analysis, checked up front."""
    problem = measure_problem(choice.measure, config)
    if problem:
        return f"Can't compare {choice.measure}: {problem}."
    if choice.method == WELCH and choice.n_surrogates < MIN_WELCH_GROUP:
        return f"The t-test needs at least {MIN_WELCH_GROUP} random pairs."
    if choice.n_surrogates < 1:
        return "At least one surrogate is needed."
    if choice.method == BLOCKS and not choice.block_length:
        return "Enter a block length."
    return None


def smallest_p(n_surrogates, side):
    """The smallest p-value n surrogates can give."""
    p = 1 / (n_surrogates + 1)
    return p if side == GREATER else min(1.0, 2 * p)


def plan_summary(choice, config, n_dyads=None):
    """One sentence on what will be tested, shown before the run. n_dyads is the number in the chosen folder."""
    side = TWO_SIDED if choice.method == WELCH else comparison_side(choice.measure, config)
    if choice.method == REPAIRED:
        compared = f"{choice.n_surrogates} sets of re-paired people"
    elif choice.method == BLOCKS:
        compared = f"{choice.n_surrogates} shuffled versions of each dyad, in blocks of {choice.block_length} samples"
    else:
        compared = f"{choice.n_surrogates} random pairs with Welch's t-test"
    dyads = "the real dyads" if n_dyads is None else f"the {n_dyads} real dyad{'' if n_dyads == 1 else 's'}"
    sentence = f"Compares {choice.measure} of {dyads} with {compared}, {side}."
    if choice.method != WELCH:
        sentence += f" The smallest possible p is {smallest_p(choice.n_surrogates, side):.3g}."
    return sentence


def folder_overview(input_dir):
    """
    The dyads in a folder, and about how many random pairs they allow, from the file names alone, so that it is
    quick enough for the app. The analysis tells copies of a recording apart by content and can find fewer pairs.
    """
    dyad_files = [len(utils.list_dyad_files(os.path.join(input_dir, folder))) for folder in _dyad_folders(input_dir)]
    dyad_files = [n for n in dyad_files if n]
    n_recordings = sum(dyad_files)
    n_pairs = math.comb(n_recordings, 2) - sum(math.comb(n, 2) for n in dyad_files)
    n_dyads = sum(n >= 2 for n in dyad_files)
    return {'n_dyads': n_dyads, 'n_pairs': n_pairs,
            'n_sets': math.comb(n_pairs, n_dyads) if n_pairs >= n_dyads else 0}


def few_sets_warning(n_sets_possible, n_surrogates, about=False):
    """A warning when fewer different surrogate sets exist than are drawn, or None."""
    if n_sets_possible is None or n_sets_possible >= n_surrogates:
        return None
    return (
        f"Only {'about ' if about else ''}{n_sets_possible} different sets of re-paired people are possible, fewer "
        f"than the {n_surrogates} drawn, so sets repeat and p can't usefully go below about 1/{n_sets_possible}."
    )
