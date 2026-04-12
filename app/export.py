import os
import xlsx

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
    for window_index, window in enumerate(params['wxcorr']):
        vectors[f"w_{window_index}_correlations"] = window['correlations']
        vectors[f"w_{window_index}_meta"] = [ f"start_idx={window['start_idx']}", f"center_idx={window['center_idx']}", f"r_max={window['r_max']}", f"tau_max={window['tau_max']}" ]
    # DFA per lag
    if params.get('dfa_alpha_per_lag_wxcorr') is not None:
        vectors['dfa_lags'] = [d['lag'] for d in params['dfa_alpha_per_lag_wxcorr']]
        vectors['dfa_alpha'] = [d['alpha'] for d in params['dfa_alpha_per_lag_wxcorr']]
    else:
        vectors['dfa_lags'] = ['-']
        vectors['dfa_alpha'] = ['-']

    xlsx.write_xlsx(vectors=vectors, single_values=metadata, output_path=file_path)

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
        'Alpha (DFA scaling exponent)': params['dfa_alpha'] if params['dfa_alpha'] is not None else '-'
    }
    vectors = {
        'signal_a': params['signal_a_std'] if params['is_standardised'] else params['signal_a'],
        'signal_b': params['signal_b_std'] if params['is_standardised'] else params['signal_b'],
        'lag': params['sxcorr']['lags'],
        'correlation': params['sxcorr']['corr'],
    }
    xlsx.write_xlsx(vectors=vectors, single_values=metadata, output_path=file_path)

def export_random_pair_data(file_path, params, input_dir, t_stat, p_value, avg_corr_rp, avg_corr_real):
    # collect metadata
    is_windowed_xcorr = params['checkbox_windowed_xcorr']
    metadata = {
        'xcorr type': "windowed cross-correlation",
        'Data type': 'fixed-rate' if params['checkbox_fr'] else 'event-based (resampled to 5hz)', 
        'Window size': params['window_size'],
        'Max lag': params['max_lag'],
        'Step size': params['step_size'],
        'Absolute correlation values': params['checkbox_absolute_corr'],
        'Standardised (z-score)': params['standardised_signals'],
        'Lag filter used': params['use_lag_filter'],
        'Lag filter minimum': params['lag_filter_min'] if params['use_lag_filter'] else '-',
        'Lag filter maximum': params['lag_filter_max'] if params['use_lag_filter'] else '-',
    } if is_windowed_xcorr else {
        'xcorr type': "(standard) cross-correlation",
        'Data type': 'fixed-rate' if params['checkbox_fr'] else 'event-based (resampled to 5hz)', 
        'Standardised (z-score)': params['standardised_signals'],
        'Max lag': params['max_lag'],
        'Absolute correlation values': params['checkbox_absolute_corr'],
    }
    metadata['Input dyad directory'] = f"{input_dir}"

    # collect single-value data
    single_values = {
        't-statistic': t_stat,
        'p-value': p_value,
        **metadata
    }

    # collect vector data
    vectors = {
        'random pair correlation': avg_corr_rp,
        'real pair correlation': avg_corr_real,
    }

    # write to xlsx
    xlsx.write_xlsx(vectors=vectors, single_values=single_values, output_path=file_path, sheet_title="Random Pair Analysis")