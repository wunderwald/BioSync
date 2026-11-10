import os

import numpy as np

import xlsx
from plot import plot_surrogate_result, plot_windowed_cross_correlation, save_figure_to_png
from surrogates import BLOCKS, REPAIRED, SIGNIFICANCE_LEVEL, WELCH, result_summary

FIRST_VECTOR_COLUMN = 4  # see xlsx.write_xlsx

def _value_or_dash(value):
    return '-' if value is None else value

def _dfa_metadata(dfa_signals, dfa_windows=None):
    """Rows for the end of the metadata, so that the rows before them keep their place."""
    dfa_signals = dfa_signals or {}
    metadata = {
        'DFA alpha, signal A': _value_or_dash(dfa_signals.get('alpha_a')),
        'DFA alpha, signal B': _value_or_dash(dfa_signals.get('alpha_b')),
    }
    notes = [dfa_signals.get('note')]
    if dfa_windows is not None:
        metadata['DFA alpha, over time (average across lags)'] = _value_or_dash(dfa_windows.get('alpha_window_averages'))
        notes.append(dfa_windows.get('note'))
    metadata['DFA note'] = ' '.join(note for note in notes if note) or '-'
    return metadata

def _correlation_matrix(wxcorr, min_lag):
    """Real numbers with one row per window and one column per lag, labelled with the lag in samples."""
    return {
        'title': 'correlations',
        'corner': 'window start index / lag',
        'row_labels': [window['start_idx'] for window in wxcorr],
        'column_labels': list(range(min_lag, min_lag + len(wxcorr[0]['correlations']))) if wxcorr else [],
        'rows': [window['correlations'] for window in wxcorr],
    }

def _add_per_window_columns(vectors, metadata, wxcorr, n_columns_after=0):
    """
    Adds two columns per window to the first sheet. With too many windows for Excel they are left out,
    and only the correlation matrix sheet has them.
    """
    if FIRST_VECTOR_COLUMN + len(vectors) + 2 * len(wxcorr) + n_columns_after - 1 > xlsx.MAX_COLUMNS:
        metadata['Per-window columns'] = "left out: too many windows for one sheet, see sheet 'correlations'"
        return
    for window_index, window in enumerate(wxcorr):
        vectors[f"w_{window_index}_correlations"] = window['correlations']
        vectors[f"w_{window_index}_meta"] = [
            f"start_idx={window['start_idx']}",
            f"center_idx={window['center_idx']}",
            f"r_max={window['r_max']}",
            f"tau_max={window['tau_max']}",
        ]

def export_wxcorr_data(file_path, params):
    metadata = {
        'xcorr type': "windowed cross-correlation",
        'Input dyad directory': f"{os.path.basename(params['selected_dyad_dir'])}",
        'Input file A': f"{os.path.basename(params['input_file_a'])}",
        'Input file B': f"{os.path.basename(params['input_file_b'])}",
        'Data type': 'fixed-rate' if params['checkbox_fr'] else 'event-based (resampled to 5hz)',
        'Standardised (z-score)': params['is_standardised'],
        'Window size': params['window_size'],
        'Max lag': params['max_lag'],
        'Step size': params['step_size'],
        'Absolute correlation values': params['checkbox_absolute_corr'],
        'Per-window averages': params['checkbox_average_windows'],
        'Lag filter used': params['checkbox_lag_filter'],
        'Lag filter minimum': params['lag_filter_min'] if params['checkbox_lag_filter'] else '-',
        'Lag filter maximum': params['lag_filter_max'] if params['checkbox_lag_filter'] else '-',
    }
    vectors = {
        'signal_a': params['signal_a_std'] if params['is_standardised'] else params['signal_a'],
        'signal_b': params['signal_b_std'] if params['is_standardised'] else params['signal_b'],
        'window start index': [o['start_idx'] for o in params['wxcorr']],
        'peak correlation (r_max)': [o['r_max'] for o in params['wxcorr']],
        'lag of peak correlation (tau_max)': [o['tau_max'] for o in params['wxcorr']],
    }
    vectors['avg_z_transformed_corr'] = [o['avg_z_transformed_corr'] for o in params['wxcorr']]
    vectors['var_z_transformed_corr'] = [o['var_z_transformed_corr'] for o in params['wxcorr']]
    _add_per_window_columns(vectors, metadata, params['wxcorr'], n_columns_after=2)
    # DFA per lag
    dfa_windows = params.get('dfa_windows') or {}
    if dfa_windows.get('alpha_per_lag') is not None:
        vectors['dfa_lags'] = [d['lag'] for d in dfa_windows['alpha_per_lag']]
        vectors['dfa_alpha'] = [d['alpha'] for d in dfa_windows['alpha_per_lag']]
    else:
        vectors['dfa_lags'] = ['-']
        vectors['dfa_alpha'] = ['-']

    metadata.update(_dfa_metadata(params.get('dfa_signals'), dfa_windows))
    min_lag = (
        min(params['lag_filter_min'], params['lag_filter_max'])
        if params['checkbox_lag_filter'] else -params['max_lag']
    )
    xlsx.write_xlsx(vectors=vectors, single_values=metadata, output_path=file_path,
                    matrix=_correlation_matrix(params['wxcorr'], min_lag))

def _window_count_metadata(n_windows_averaged, window_counts):
    """Rows for the end of the metadata that say how much of each dyad the average covers."""
    if not window_counts:
        return {}
    return {
        'Windows averaged': n_windows_averaged,
        'Windows per dyad': f"{min(window_counts)} to {max(window_counts)}",
        'Window note': (
            "Windows are averaged by position, up to the number of windows of the shortest dyad. "
            "Later windows of longer dyads are not part of the average."
        ),
    }

def export_avg_wxcorr_data(file_path, avg_wxcorr, n_dyads, params, window_counts=None):
    """
    Export an averaged wxcorr result (from average_wxcorr_matrices) to XLSX.
    window_counts are the numbers of windows of the averaged dyads, which the export reports.
    """
    metadata = {
        'xcorr type':                   'windowed cross-correlation (group average)',
        'Number of dyads averaged':     n_dyads,
        'Data type':                    'fixed-rate' if params.get('checkbox_fr') else 'event-based (resampled to 5hz)',
        'Standardised (z-score)':       params.get('standardised_signals', params.get('is_standardised', '-')),
        'Window size':                  params.get('window_size', '-'),
        'Max lag':                      params.get('max_lag', '-'),
        'Step size':                    params.get('step_size', '-'),
        'Absolute correlation values':  params.get('checkbox_absolute_corr', '-'),
        'Per-window averages':          params.get('checkbox_average_windows', '-'),
        'Lag filter used':              params.get('use_lag_filter', params.get('checkbox_lag_filter', '-')),
        'Lag filter minimum':           params.get('lag_filter_min', '-'),
        'Lag filter maximum':           params.get('lag_filter_max', '-'),
    }
    vectors = {
        'window start index':               [o['start_idx']               for o in avg_wxcorr],
        'peak correlation (r_max)':         [o['r_max']                   for o in avg_wxcorr],
        'lag of peak correlation (tau_max)':[o['tau_max']                 for o in avg_wxcorr],
        'avg_z_transformed_corr':           [o['avg_z_transformed_corr']  for o in avg_wxcorr],
        'var_z_transformed_corr':           [o['var_z_transformed_corr']  for o in avg_wxcorr],
    }
    _add_per_window_columns(vectors, metadata, avg_wxcorr)
    metadata.update(_window_count_metadata(len(avg_wxcorr), window_counts))
    min_lag = (
        min(params['lag_filter_min'], params['lag_filter_max'])
        if params.get('use_lag_filter') else -params['max_lag']
    )
    xlsx.write_xlsx(vectors=vectors, single_values=metadata, output_path=file_path, sheet_title="Grand Avg WXCorr",
                    matrix=_correlation_matrix(avg_wxcorr, min_lag))


def export_sxcorr_data(file_path, params):
    metadata = {
        'xcorr type': "(standard) cross-correlation",
        'Input dyad directory': f"{os.path.basename(params['selected_dyad_dir'])}",
        'Input file A': f"{os.path.basename(params['input_file_a'])}",
        'Input file B': f"{os.path.basename(params['input_file_b'])}",
        'Data type': 'fixed-rate' if params['checkbox_fr'] else 'event-based (resampled to 5hz)', 
        'Standardised (z-score)': params['is_standardised'],
        'Max lag': params['max_lag'],
        'Absolute correlation values': params['checkbox_absolute_corr'],
        'Alpha (DFA scaling exponent)': '-',  # kept for existing pipelines: DFA across lags measures nothing useful
        **_dfa_metadata(params.get('dfa_signals')),
    }
    vectors = {
        'signal_a': params['signal_a_std'] if params['is_standardised'] else params['signal_a'],
        'signal_b': params['signal_b_std'] if params['is_standardised'] else params['signal_b'],
        'lag': params['sxcorr']['lags'],
        'correlation': params['sxcorr']['corr'],
    }
    xlsx.write_xlsx(vectors=vectors, single_values=metadata, output_path=file_path)

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


def export_surrogate_result(file_path, params, input_dir, result):
    """
    Writes a surrogates.SurrogateResult to file_path, and its figure next to it as a PNG with the same name.
    Welch keeps the file of earlier versions, with the new rows at the end of its first sheet. The figure is made
    first, so that a failure leaves no files.
    """
    fig = _figure(result)
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
    save_figure_to_png(fig, f"{os.path.splitext(file_path)[0]}.png")
