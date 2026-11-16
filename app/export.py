import os

import numpy as np

import xlsx
from analysis import AnalysisConfig, dfa_category
from measures import MEAN_ABS_R, MEAN_ABS_R_MAX, MEAN_R, R_AT_LAG_0, dyad_measure, measure_problem
from plot import plot_surrogate_result, plot_windowed_cross_correlation, save_figure_to_png
from signal_processing import EVENT_BASED_SAMPLING_RATE_HZ
from stationarity import ALPHA as KPSS_ALPHA, stationary_share
from surrogates import BLOCKS, REPAIRED, SIGNIFICANCE_LEVEL, WELCH, result_summary

# ---------------------------------------------------------------------------
# CORRELATION RESULTS
# Each file is a set of tables, one per sheet, so that programs can read any of them in one call:
#   metadata       name, value and note of each setting and single result
#   windows        one row per window (windowed)
#   correlations   windows × lags (windowed), or one row per lag (standard)
#   signals        the signals as they were correlated
#   dfa_per_lag    DFA alpha of the correlations over time at each lag (windowed, empty when not available)
# A cell holds a number, TRUE/FALSE or text. A missing value is an empty cell, and its note says why.
# ---------------------------------------------------------------------------

WINDOWED_ANALYSIS = "windowed cross-correlation"
STANDARD_ANALYSIS = "standard cross-correlation"
GROUP_AVERAGE_ANALYSIS = "windowed cross-correlation, group average"


def _metadata_sheet(rows):
    """rows are (name, value) or (name, value, note)."""
    return {'title': 'metadata', 'columns': ['name', 'value', 'note'],
            'rows': [[*row, None] if len(row) == 2 else list(row) for row in rows]}


def _base_name(path):
    return os.path.basename(path) if path else None


def _input_rows(params):
    return [
        ('dyad_folder', _base_name(params.get('selected_dyad_dir'))),
        ('file_a', _base_name(params.get('input_file_a'))),
        ('file_b', _base_name(params.get('input_file_b'))),
        ('sheet', params.get('selected_sheet') or None),
        ('column', params.get('selected_column') or None),
    ]


def _signal_rows(config, sampling_rate):
    """The data type and its sampling rate. sampling_rate is the fixed rate the app knows, 0 if it doesn't."""
    if config.signal_type == 'event-based':
        rate = (EVENT_BASED_SAMPLING_RATE_HZ, "intervals resampled to this rate")
    elif sampling_rate:
        rate = (sampling_rate, "from the sampling rate field of the Input Data tab")
    else:
        rate = (None, "not known: enter it on the Input Data tab to have it here")
    return [
        ('data_type', config.signal_type),
        ('sampling_rate_hz', *rate),
        ('standardised', config.standardised, "z-scored before correlating"),
    ]


def _windowed_settings_rows(config):
    if config.use_lag_filter:
        low, high = sorted((config.lag_filter_min, config.lag_filter_max))
        lag_filter = [('lag_filter_min_samples', low), ('lag_filter_max_samples', high)]
    else:
        lag_filter = [('lag_filter_min_samples', None, "lag filter not used"),
                      ('lag_filter_max_samples', None, "lag filter not used")]
    return [
        ('window_size_samples', config.window_size),
        ('step_size_samples', config.step_size),
        ('max_lag_samples', config.max_lag),
        ('absolute_correlations', config.absolute),
        ('average_windows', config.average_windows, "correlations averaged over the lags of each window"),
        ('lag_filter', config.use_lag_filter),
        *lag_filter,
    ]


def _min_lag(config):
    return min(config.lag_filter_min, config.lag_filter_max) if config.use_lag_filter else -config.max_lag


def _alpha_row(name, alpha, reason):
    return (name, alpha, dfa_category(alpha)) if alpha is not None else (name, None, reason or "no data")


def _dfa_rows(dfa_signals, dfa_windows=None):
    dfa_signals = dfa_signals or {}
    rows = [
        _alpha_row('dfa_alpha_a', dfa_signals.get('alpha_a'), dfa_signals.get('note')),
        _alpha_row('dfa_alpha_b', dfa_signals.get('alpha_b'), dfa_signals.get('note')),
    ]
    if dfa_windows is not None:
        rows.append(_alpha_row('dfa_alpha_correlations_over_time', dfa_windows.get('alpha_window_averages'),
                               dfa_windows.get('note')))
    return rows


def _kpss_window_rows(stationarity):
    rows = []
    for person in ('a', 'b'):
        stationary, tested = stationary_share(stationarity[f'p_{person}']) if stationarity else (0, 0)
        if tested:
            rows.append((f'kpss_stationary_share_{person}', stationary / tested,
                         f"{stationary} of {tested} windows with KPSS p >= {KPSS_ALPHA}"))
        else:
            rows.append((f'kpss_stationary_share_{person}', None, "no window could be tested"))
    return rows


def _kpss_signal_rows(stationarity):
    rows = []
    for person in ('a', 'b'):
        p = stationarity[f'p_{person}'] if stationarity else None
        if p is None or np.isnan(p):
            rows.append((f'kpss_p_{person}', None, "flat signal, can't be tested" if stationarity else "no data"))
        else:
            rows.append((f'kpss_p_{person}', p, f"KPSS of the whole signal; p < {KPSS_ALPHA}: not stationary. "
                                                "Read from a table: 0.01 means 0.01 or less, 0.1 means 0.1 or more."))
    return rows


def _windows_sheet(wxcorr, stationarity=None):
    columns = ['window', 'start_index', 'center_index', 'r_max', 'tau_max', 'avg_z_transformed_corr',
               'var_z_transformed_corr']
    rows = [[number, w['start_idx'], w['center_idx'], w['r_max'], w['tau_max'], w['avg_z_transformed_corr'],
             w['var_z_transformed_corr']] for number, w in enumerate(wxcorr, start=1)]
    if stationarity is not None:
        columns += ['kpss_p_a', 'kpss_p_b']
        for row, p_a, p_b in zip(rows, stationarity['p_a'], stationarity['p_b']):
            row += [p_a, p_b]
    return {'title': 'windows', 'columns': columns, 'rows': rows}


def _correlations_sheet(wxcorr, min_lag):
    """One row per window, labelled with its start index, and one column per lag, labelled in samples."""
    return xlsx.matrix_table({
        'title': 'correlations',
        'corner': 'window start index / lag',
        'row_labels': [window['start_idx'] for window in wxcorr],
        'column_labels': list(range(min_lag, min_lag + len(wxcorr[0]['correlations']))) if wxcorr else [],
        'rows': [window['correlations'] for window in wxcorr],
    })


def _signals_sheet(params, config):
    signal_a = params['signal_a_std'] if config.standardised else params['signal_a']
    signal_b = params['signal_b_std'] if config.standardised else params['signal_b']
    return {'title': 'signals', 'columns': ['sample', 'signal_a', 'signal_b'],
            'rows': [[sample, a, b] for sample, (a, b) in enumerate(zip(signal_a, signal_b))]}


def _dfa_per_lag_sheet(dfa_windows):
    per_lag = (dfa_windows or {}).get('alpha_per_lag') or []
    return {'title': 'dfa_per_lag', 'columns': ['lag', 'alpha'], 'rows': [[d['lag'], d['alpha']] for d in per_lag]}


def export_wxcorr_data(file_path, params):
    """
    Writes the windowed correlation of one dyad. params has 'config' (analysis.AnalysisConfig), the signals,
    'wxcorr', the file names, and optionally 'sampling_rate', 'selected_sheet', 'selected_column', 'dfa_signals',
    'dfa_windows' and 'stationarity' (stationarity.signal_stationarity).
    """
    config = params['config']
    wxcorr = params['wxcorr']
    metadata = _metadata_sheet([
        ('analysis', WINDOWED_ANALYSIS),
        *_input_rows(params),
        *_signal_rows(config, params.get('sampling_rate')),
        *_windowed_settings_rows(config),
        ('windows', len(wxcorr)),
        *_dfa_rows(params.get('dfa_signals'), params.get('dfa_windows') or {}),
        *_kpss_window_rows(params.get('stationarity')),
    ])
    stationarity = params.get('stationarity') or {'p_a': [None] * len(wxcorr), 'p_b': [None] * len(wxcorr)}
    xlsx.write_tables(file_path, [
        metadata,
        _windows_sheet(wxcorr, stationarity),
        _correlations_sheet(wxcorr, _min_lag(config)),
        _signals_sheet(params, config),
        _dfa_per_lag_sheet(params.get('dfa_windows')),
    ])


def export_avg_wxcorr_data(file_path, avg_wxcorr, n_dyads, params, window_counts=None):
    """
    Writes a group average (from average_wxcorr_matrices). params are the analysis parameters, as for
    AnalysisConfig.from_params. window_counts are the numbers of windows of the averaged dyads.
    """
    config = AnalysisConfig.from_params(params)
    counts = [('windows_per_dyad_min', min(window_counts)), ('windows_per_dyad_max', max(window_counts))] \
        if window_counts else [('windows_per_dyad_min', None, "not known"), ('windows_per_dyad_max', None, "not known")]
    metadata = _metadata_sheet([
        ('analysis', GROUP_AVERAGE_ANALYSIS),
        ('dyads_averaged', n_dyads),
        *_signal_rows(config, params.get('sampling_rate')),
        *_windowed_settings_rows(config),
        ('windows_averaged', len(avg_wxcorr), "windows are averaged by position, up to the number of windows of "
                                              "the shortest dyad; later windows of longer dyads are left out"),
        *counts,
    ])
    xlsx.write_tables(file_path, [
        metadata,
        _windows_sheet(avg_wxcorr),
        _correlations_sheet(avg_wxcorr, _min_lag(config)),
    ])


def export_sxcorr_data(file_path, params):
    """Writes the standard correlation of one dyad. params as for export_wxcorr_data, with 'sxcorr'."""
    config = params['config']
    metadata = _metadata_sheet([
        ('analysis', STANDARD_ANALYSIS),
        *_input_rows(params),
        *_signal_rows(config, params.get('sampling_rate')),
        ('max_lag_samples', config.max_lag_sxc),
        ('absolute_correlations', config.absolute_sxc),
        *_dfa_rows(params.get('dfa_signals')),
        *_kpss_signal_rows(params.get('stationarity')),
    ])
    correlations = {'title': 'correlations', 'columns': ['lag', 'correlation'],
                    'rows': [[lag, r] for lag, r in zip(params['sxcorr']['lags'], params['sxcorr']['corr'])]}
    xlsx.write_tables(file_path, [metadata, correlations, _signals_sheet(params, config)])


# ---------------------------------------------------------------------------
# BATCH SUMMARY: one row per dyad, so that dyads can be compared without opening each file
# ---------------------------------------------------------------------------

SUMMARY_MEASURES = {MEAN_R: 'mean_r', MEAN_ABS_R: 'mean_abs_r', MEAN_ABS_R_MAX: 'mean_abs_r_max', R_AT_LAG_0: 'r_at_lag_0'}

SUMMARY_DESCRIPTIONS = {
    'dyad': "the dyad folder",
    'status': "ok, or failed: then the note says why, and the values are empty",
    'note': "why the dyad failed, or what to know about how it was processed",
    'file_a': "the recording used as person A", 'file_b': "the recording used as person B",
    'windows': "number of windows",
    'r_max': "the correlation of largest size, with its sign", 'tau_max': "its lag in samples; > 0: A leads B",
    'mean_r': "mean of all correlations, over windows and lags",
    'mean_abs_r': "mean of all correlations without their sign",
    'mean_abs_r_max': "mean over windows of the strongest correlation at any lag, without its sign",
    'r_at_lag_0': "mean over windows of the correlation without delay",
    'dfa_alpha_a': "DFA alpha of A's input signal", 'dfa_alpha_b': "DFA alpha of B's input signal",
    'dfa_alpha_correlations_over_time': "DFA alpha of the windowed correlations over time",
    'kpss_stationary_share_a': f"share of A's windows with KPSS p >= {KPSS_ALPHA}",
    'kpss_stationary_share_b': f"share of B's windows with KPSS p >= {KPSS_ALPHA}",
    'kpss_p_a': "KPSS p of A's whole signal", 'kpss_p_b': "KPSS p of B's whole signal",
}


def summary_columns(config):
    """The columns of the summary's dyads sheet."""
    first = ['dyad', 'status', 'note', 'file_a', 'file_b']
    if config.windowed:
        return first + ['windows', *SUMMARY_MEASURES.values(), 'dfa_alpha_a', 'dfa_alpha_b',
                        'dfa_alpha_correlations_over_time', 'kpss_stationary_share_a', 'kpss_stationary_share_b']
    return first + ['r_max', 'tau_max', 'mean_r', 'mean_abs_r', 'r_at_lag_0', 'dfa_alpha_a', 'dfa_alpha_b',
                    'kpss_p_a', 'kpss_p_b']


def summary_values(corr_data, config, dfa_signals, dfa_windows, stationarity):
    """The summary values of one dyad, from the results its file is written from."""
    dfa_signals = dfa_signals or {}
    values = {'dfa_alpha_a': dfa_signals.get('alpha_a'), 'dfa_alpha_b': dfa_signals.get('alpha_b')}
    columns = summary_columns(config)
    for measure, column in SUMMARY_MEASURES.items():
        if column in columns and measure_problem(measure, config) is None:
            values[column] = dyad_measure(corr_data, config, measure)
    if config.windowed:
        values['windows'] = len(corr_data)
        values['dfa_alpha_correlations_over_time'] = (dfa_windows or {}).get('alpha_window_averages')
        for person in ('a', 'b'):
            stationary, tested = stationary_share(stationarity[f'p_{person}']) if stationarity else (0, 0)
            values[f'kpss_stationary_share_{person}'] = stationary / tested if tested else None
    else:
        correlations = np.asarray(corr_data['corr'], dtype=float)
        if not np.all(np.isnan(correlations)):
            peak = int(np.nanargmax(np.abs(correlations)))
            values['r_max'], values['tau_max'] = correlations[peak], int(corr_data['lags'][peak])
        for person in ('a', 'b'):
            values[f'kpss_p_{person}'] = stationarity[f'p_{person}'] if stationarity else None
    return values


def export_batch_summary(file_path, rows, params):
    """
    Writes the batch summary: 'dyads' with one row per dyad folder (dicts with the keys of summary_columns, missing
    ones empty), 'metadata' with the settings, and 'columns' with what each column means.
    """
    config = AnalysisConfig.from_params(params)
    columns = summary_columns(config)
    descriptions = []
    for column in columns:
        description = SUMMARY_DESCRIPTIONS[column]
        measure = next((m for m, name in SUMMARY_MEASURES.items() if name == column), None)
        problem = measure_problem(measure, config) if measure else None
        descriptions.append([column, f"{description}. Empty: {problem}." if problem else description])
    settings = _windowed_settings_rows(config) if config.windowed else [
        ('max_lag_samples', config.max_lag_sxc), ('absolute_correlations', config.absolute_sxc)]
    failed = sum(row.get('status') == 'failed' for row in rows)
    metadata = _metadata_sheet([
        ('analysis', WINDOWED_ANALYSIS if config.windowed else STANDARD_ANALYSIS),
        ('input_folder', params.get('batch_input_folder') or None),
        ('sheet', params.get('selected_sheet') or None),
        ('column', params.get('selected_column_a') or None),
        *_signal_rows(config, params.get('sampling_rate')),
        *settings,
        ('dyads', len(rows)),
        ('dyads_ok', len(rows) - failed),
        ('dyads_failed', failed),
    ])
    xlsx.write_tables(file_path, [
        {'title': 'dyads', 'columns': columns, 'rows': [[row.get(column) for column in columns] for row in rows]},
        metadata,
        {'title': 'columns', 'columns': ['column', 'description'], 'rows': descriptions},
    ])


# ---------------------------------------------------------------------------
# SURROGATE TESTS
# Tables as for correlation results:
#   metadata           result, settings and counts
#   surrogate_sets     the value of each surrogate set (shuffled blocks, re-paired people)
#   dyads              each real dyad's value; for shuffled blocks also its own test
#   shuffled_versions  the value of every shuffled version of each dyad (shuffled blocks)
#   random_pairs       each random pair and its value (re-paired people, Welch)
#   files_left_out     recordings that couldn't be in a random pair, and why (re-paired people, Welch)
#   skipped            dyads or pairs without a value, and why
# ---------------------------------------------------------------------------

# Excel keeps 15 significant digits, so larger counts are rounded
LARGEST_EXACT_COUNT = 10 ** 15


def left_out_names(left_out_files, input_dir):
    """Each recording left out of random pairs as 'folder/file (reason)'."""
    return [f"{os.path.relpath(path, input_dir)} ({reason})" for path, reason in left_out_files or []]


def _count_cell(value):
    """A count as a number Excel can store: rounded when it's too large to keep exactly, None beyond floats."""
    if value is None or value < LARGEST_EXACT_COUNT:
        return value
    try:
        return float(value)
    except OverflowError:
        return None


def _count_row(name, value):
    if value is None:
        return (name, None, "not known")
    cell = _count_cell(value)
    if cell is None:
        return (name, None, "more than 10^308")
    return (name, cell, "rounded: Excel keeps 15 digits") if value >= LARGEST_EXACT_COUNT else (name, cell)


def _settings_rows(params):
    config = AnalysisConfig.from_params(params)
    settings = _windowed_settings_rows(config) if config.windowed else [
        ('max_lag_samples', config.max_lag_sxc), ('absolute_correlations', config.absolute_sxc)]
    return [
        ('correlation', WINDOWED_ANALYSIS if config.windowed else STANDARD_ANALYSIS),
        *_signal_rows(config, params.get('sampling_rate')),
        *settings,
    ]


def _surrogate_metadata(params, input_dir, result):
    null_values = np.asarray(result.null_values, dtype=float)
    welch = result.method == WELCH
    rows = [
        ('analysis', "surrogate test"),
        ('method', result.method),
        ('measure', result.measure),
        ('sides', result.side),
        *([('t_statistic', result.t_statistic)] if welch else []),
        ('p_value', result.p_value),
        ('summary', result_summary(result)),
        ('real_mean', result.real_value, "mean of the real dyads' values"),
    ]
    if welch:
        rows.append(('random_pair_mean', float(np.nanmean(null_values)) if len(null_values) else None,
                     "mean of the random pairs' values"))
    else:
        rows += [('surrogate_mean', float(np.nanmean(null_values)), "mean of the surrogate sets' values"),
                 ('surrogate_sd', float(np.nanstd(null_values)), "their standard deviation")]
    rows += [
        ('input_folder', input_dir),
        ('sheet', params.get('selected_sheet') or None),
        ('column', params.get('selected_column_a') or None),
        *_settings_rows(params),
        ('seed', result.seed),
    ]
    if welch:
        rows.append(('random_pairs_requested', result.n_surrogates))
    else:
        rows += [('surrogate_sets', result.n_surrogates), _count_row('different_sets_possible', result.n_sets_possible)]
    rows += [
        ('real_dyads_used', len(result.real_values)),
        ('skipped', len(result.failures), "dyads or pairs without a value, see sheet 'skipped'"),
    ]
    if result.method in (REPAIRED, WELCH):
        rows += [
            ('random_pairs_possible', result.n_pairs_possible, "pairs of people from different dyads"),
            ('random_pairs_used', result.n_pairs_used,
             "pairs drawn more than once count again" if welch else "each possible pair, once"),
            ('files_left_out', len(result.left_out_files or []), "see sheet 'files_left_out'"),
        ]
    if result.method == BLOCKS:
        rows += [
            ('block_length_samples', result.block_length),
            ('dyads_significant', sum(p < SIGNIFICANCE_LEVEL for p in result.dyad_p_values),
             f"dyads with their own p < {SIGNIFICANCE_LEVEL}, not corrected for testing many dyads"),
        ]
    return _metadata_sheet(rows)


def _dyads_table(result):
    columns = ['dyad', 'value']
    rows = [[name, value] for name, value in zip(result.dyad_names, result.real_values)]
    if result.method == BLOCKS:
        columns += ['p_value', 'shuffled_percentile_2_5', 'shuffled_median', 'shuffled_percentile_97_5',
                    'block_orders_possible']
        for row, null_values, p_value, orders in zip(rows, result.dyad_null_values, result.dyad_p_values,
                                                     result.dyad_orders_possible):
            row += [p_value, *np.nanpercentile(np.asarray(null_values, dtype=float), [2.5, 50, 97.5]),
                    _count_cell(orders)]
    return {'title': 'dyads', 'columns': columns, 'rows': rows}


def _surrogate_sets_table(result):
    return {'title': 'surrogate_sets', 'columns': ['set', 'value'],
            'rows': [[number, value] for number, value in enumerate(result.null_values, start=1)]}


def _shuffled_versions_table(result):
    """The measure of every shuffled version, one column per dyad, so that the test can be checked or redone."""
    versions = np.array(result.dyad_null_values, dtype=float).T
    return {'title': 'shuffled_versions', 'columns': ['version', *result.dyad_names],
            'rows': [[number, *values] for number, values in enumerate(versions, start=1)]}


def _random_pairs_table(result, input_dir):
    pairs = zip(result.pair_files or [], result.pair_values or [])
    return {'title': 'random_pairs', 'columns': ['pair', 'file_a', 'file_b', 'value'],
            'rows': [[number, os.path.relpath(file_a, input_dir), os.path.relpath(file_b, input_dir), value]
                     for number, ((file_a, file_b), value) in enumerate(pairs, start=1)]}


def _files_left_out_table(result, input_dir):
    return {'title': 'files_left_out', 'columns': ['file', 'reason'],
            'rows': [[os.path.relpath(path, input_dir), reason] for path, reason in result.left_out_files or []]}


def _skipped_table(result):
    return {'title': 'skipped', 'columns': ['dyad_or_pair', 'reason'], 'rows': [list(f) for f in result.failures]}


def _figure(result):
    """The result figure, taller when there are many dyads, so that each keeps a readable row."""
    fig = plot_surrogate_result(result)
    if result.method == BLOCKS:
        width, height = fig.get_size_inches()
        fig.set_size_inches(width, max(height, 3 + 0.2 * len(result.dyad_names)))
    return fig


def export_surrogate_figure(file_path, result):
    """Saves the figure of a surrogates.SurrogateResult as a PNG, as the Surrogates tab shows it."""
    save_figure_to_png(_figure(result), file_path)


def _export_welch_group_averages(file_path, params, result):
    """Welch, as in earlier versions: the group averages of the real dyads and the random pairs, next to the file."""
    base = os.path.splitext(file_path)[0]
    for name, average, n_averaged, window_counts in (
        ("real_pairs", result.avg_wxcorr_real, len(result.real_values), result.window_counts_real),
        ("random_pairs", result.avg_wxcorr_surrogates, result.n_pairs_used, result.window_counts_surrogates),
    ):
        if not average:
            continue
        export_avg_wxcorr_data(f"{base}_avg_{name}.xlsx", average, n_averaged, params, window_counts)
        fig = plot_windowed_cross_correlation(
            wxc_data=average, signal_a=[], signal_b=[], window_size=params['window_size'], max_lag=params['max_lag'],
            step_size=params['step_size'], show_sigmoid_correlations=params.get('sigmoid_correlations', False),
            use_lag_filter=params['use_lag_filter'], lag_filter_min=params['lag_filter_min'],
            lag_filter_max=params['lag_filter_max'],
        )
        save_figure_to_png(fig, f"{base}_avg_{name}.png")


def export_surrogate_result(file_path, params, input_dir, result):
    """
    Writes a surrogates.SurrogateResult to file_path, as the tables listed above. For Welch with windowed
    correlation, the group averages of the real dyads and the random pairs are written next to it.
    """
    sheets = [_surrogate_metadata(params, input_dir, result)]
    if result.method != WELCH:
        sheets.append(_surrogate_sets_table(result))
    sheets.append(_dyads_table(result))
    if result.method == BLOCKS:
        sheets.append(_shuffled_versions_table(result))
    else:
        sheets += [_random_pairs_table(result, input_dir), _files_left_out_table(result, input_dir)]
    sheets.append(_skipped_table(result))
    xlsx.write_tables(file_path, sheets)
    if result.method == WELCH and params['checkbox_windowed_xcorr']:
        _export_welch_group_averages(file_path, params, result)
