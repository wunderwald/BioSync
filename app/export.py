import os

import numpy as np

import xlsx
from analysis import AnalysisConfig, dfa_category
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
# SURROGATE TESTS AND RANDOM PAIRS
# ---------------------------------------------------------------------------

def _correlation_settings(params):
    """The rows that describe the correlation settings, in the order of earlier random pair exports."""
    data_type = 'fixed-rate' if params['checkbox_fr'] else 'event-based (resampled to 5hz)'
    if params['checkbox_windowed_xcorr']:
        return {
            'xcorr type': "windowed cross-correlation",
            'Data type': data_type,
            'Window size': params['window_size'],
            'Max lag': params['max_lag'],
            'Step size': params['step_size'],
            'Absolute correlation values': params['checkbox_absolute_corr'],
            'Standardised (z-score)': params['standardised_signals'],
            'Lag filter used': params['use_lag_filter'],
            'Lag filter minimum': params['lag_filter_min'] if params['use_lag_filter'] else '-',
            'Lag filter maximum': params['lag_filter_max'] if params['use_lag_filter'] else '-',
        }
    return {
        'xcorr type': "(standard) cross-correlation",
        'Data type': data_type,
        'Standardised (z-score)': params['standardised_signals'],
        'Max lag': params['max_lag_sxc'],
        'Absolute correlation values': params['checkbox_absolute_corr_sxc'],
    }


def export_random_pair_data(file_path, params, input_dir, t_stat, p_value, avg_corr_rp, avg_corr_real,
                            avg_wxcorr_real=None, avg_wxcorr_rp=None, seed='-', n_eligible_pairs='-',
                            n_random_pairs_requested='-', window_counts_real=None, window_counts_rp=None,
                            left_out_files=None, extra_rows=None, extra_sheets=()):
    """
    The export of earlier versions. Pipelines read its first sheet, so its rows and columns stay as they are:
    extra_rows go after them, and extra_sheets after the first sheet.
    """
    # collect metadata
    is_windowed_xcorr = params['checkbox_windowed_xcorr']
    metadata = _correlation_settings(params)
    metadata['Input dyad directory'] = f"{input_dir}"

    # collect single-value data
    single_values = {
        't-statistic': t_stat,
        'p-value': p_value,
        **metadata,
        'Random seed': seed,
        'Different random pairs possible': n_eligible_pairs,
        'Random pairs requested': n_random_pairs_requested,
        'Random pairs used': len(avg_corr_rp),
        'Real dyads used': len(avg_corr_real),
        'Files not used for random pairs': "; ".join(left_out_files) if left_out_files else '-',
        **(extra_rows or {}),
    }

    # collect vector data
    vectors = {
        'random pair correlation': avg_corr_rp,
        'real pair correlation': avg_corr_real,
    }

    # write main stats xlsx
    xlsx.write_xlsx(vectors=vectors, single_values=single_values, output_path=file_path, sheet_title="Random Pair Analysis",
                    extra_sheets=extra_sheets)

    # export group-average heatmaps when wxcorr was used
    if is_windowed_xcorr and avg_wxcorr_real is not None and avg_wxcorr_rp is not None:
        base = os.path.splitext(file_path)[0]

        if avg_wxcorr_real:
            export_avg_wxcorr_data(f"{base}_avg_real_pairs.xlsx", avg_wxcorr_real, len(avg_corr_real), params, window_counts_real)
            fig_real = plot_windowed_cross_correlation(
                wxc_data=avg_wxcorr_real,
                signal_a=[], signal_b=[],
                window_size=params['window_size'],
                max_lag=params['max_lag'],
                step_size=params['step_size'],
                show_sigmoid_correlations=params.get('sigmoid_correlations', False),
                use_lag_filter=params['use_lag_filter'],
                lag_filter_min=params['lag_filter_min'],
                lag_filter_max=params['lag_filter_max'],
            )
            save_figure_to_png(fig_real, f"{base}_avg_real_pairs.png")

        if avg_wxcorr_rp:
            export_avg_wxcorr_data(f"{base}_avg_random_pairs.xlsx", avg_wxcorr_rp, len(avg_corr_rp), params, window_counts_rp)
            fig_rp = plot_windowed_cross_correlation(
                wxc_data=avg_wxcorr_rp,
                signal_a=[], signal_b=[],
                window_size=params['window_size'],
                max_lag=params['max_lag'],
                step_size=params['step_size'],
                show_sigmoid_correlations=params.get('sigmoid_correlations', False),
                use_lag_filter=params['use_lag_filter'],
                lag_filter_min=params['lag_filter_min'],
                lag_filter_max=params['lag_filter_max'],
            )
            save_figure_to_png(fig_rp, f"{base}_avg_random_pairs.png")


# ---------------------------------------------------------------------------
# SURROGATE TESTS
# ---------------------------------------------------------------------------

# Excel stores numbers as floating point, so counts beyond this are written as text
LARGEST_EXACT_COUNT = 10 ** 15


def left_out_names(left_out_files, input_dir):
    """Each recording left out of random pairs as 'folder/file (reason)'."""
    return [f"{os.path.relpath(path, input_dir)} ({reason})" for path, reason in left_out_files or []]


def _count(value):
    if value is None:
        return '-'
    return value if value < LARGEST_EXACT_COUNT else f"more than 10^{len(str(LARGEST_EXACT_COUNT)) - 1}"


def _result_rows(result):
    """Rows that every surrogate export has: for Welch at the end, for the others at the start."""
    return {
        'Method': result.method,
        'Measure': result.measure,
        'Sides': result.side,
        'Summary': result_summary(result),
    }


def _dyad_sheet(result):
    columns = ['value']
    rows = [[value] for value in result.real_values]
    if result.method == BLOCKS:
        columns += ['p-value', 'shuffled 2.5%', 'shuffled median', 'shuffled 97.5%', 'block orders possible']
        for row, null_values, p_value, orders in zip(rows, result.dyad_null_values, result.dyad_p_values,
                                                     result.dyad_orders_possible):
            null_values = np.asarray(null_values, dtype=float)
            row += [p_value, *np.nanpercentile(null_values, [2.5, 50, 97.5]), _count(orders)]
    return {'title': 'dyads', 'corner': 'dyad', 'row_labels': result.dyad_names, 'column_labels': columns,
            'rows': rows}


def _shuffled_versions_sheet(result):
    """The measure of every shuffled version, one column per dyad, so that the test can be checked or redone."""
    return {
        'title': 'shuffled versions', 'corner': 'version', 'row_labels': range(1, result.n_surrogates + 1),
        'column_labels': result.dyad_names, 'rows': np.array(result.dyad_null_values, dtype=float).T,
    }


def _skipped_sheet(result):
    return {'title': 'skipped', 'corner': 'dyad or pair', 'row_labels': [name for name, _ in result.failures],
            'column_labels': ['reason'], 'rows': [[reason] for _, reason in result.failures]}


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


def export_surrogate_result(file_path, params, input_dir, result):
    """
    Writes a surrogates.SurrogateResult to file_path as xlsx. Welch keeps the file of earlier versions, with the
    new rows at the end of its first sheet.
    """
    left_out = left_out_names(result.left_out_files, input_dir)
    sheets = [_dyad_sheet(result)]
    if result.method == BLOCKS:
        sheets.append(_shuffled_versions_sheet(result))
    if result.failures:
        sheets.append(_skipped_sheet(result))

    if result.method == WELCH:
        export_random_pair_data(
            file_path=file_path,
            params=params,
            input_dir=input_dir,
            t_stat=result.t_statistic,
            p_value=result.p_value,
            avg_corr_rp=list(result.null_values),
            avg_corr_real=result.real_values,
            avg_wxcorr_real=result.avg_wxcorr_real,
            avg_wxcorr_rp=result.avg_wxcorr_surrogates,
            seed=result.seed,
            n_eligible_pairs=result.n_pairs_possible,
            n_random_pairs_requested=result.n_surrogates,
            window_counts_real=result.window_counts_real,
            window_counts_rp=result.window_counts_surrogates,
            left_out_files=left_out,
            extra_rows=_result_rows(result),
            extra_sheets=sheets,
        )
    else:
        null_values = np.asarray(result.null_values, dtype=float)
        single_values = {
            'p-value': result.p_value,
            **_result_rows(result),
            'Real group mean': result.real_value,
            'Surrogate mean': float(np.nanmean(null_values)),
            'Surrogate SD': float(np.nanstd(null_values)),
            **_correlation_settings(params),
            'Input dyad directory': f"{input_dir}",
            'Random seed': result.seed,
            'Surrogate sets': result.n_surrogates,
            'Different surrogate sets possible': _count(result.n_sets_possible),
            'Real dyads used': len(result.real_values),
            'Dyads or pairs skipped': len(result.failures),
        }
        if result.method == REPAIRED:
            single_values.update({
                'Different random pairs possible': result.n_pairs_possible,
                'Random pairs used': result.n_pairs_used,
                'Files not used for random pairs': "; ".join(left_out) if left_out else '-',
            })
        if result.method == BLOCKS:
            single_values.update({
                'Block length (samples)': result.block_length,
                f'Dyads with p < {SIGNIFICANCE_LEVEL}': sum(p < SIGNIFICANCE_LEVEL for p in result.dyad_p_values),
            })
        vectors = {'surrogate set mean': null_values, 'real dyad value': result.real_values}
        xlsx.write_xlsx(vectors=vectors, single_values=single_values, output_path=file_path,
                        sheet_title="Surrogate Analysis", extra_sheets=sheets)
