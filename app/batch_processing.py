import hashlib
import itertools
import os
import re
import xlsx
import utils
from analysis import AnalysisConfig, analyze_dyad, signal_dfa, windowed_dfa
from export import export_sxcorr_data, export_wxcorr_data, export_avg_wxcorr_data
from cross_correlation import average_wxcorr_matrices, mean_ignoring_flat_windows
import random
import numpy as np
from datetime import datetime
from scipy.stats import ttest_ind
from plot import plot_windowed_cross_correlation, plot_standard_cross_correlation, save_figure_to_png

def _process_dyad(file_path_a, file_path_b, output_dir, params, export=True, dyad_dir=''):
    """
    Processes dyadic data from Excel files, performs cross-correlation analysis, and optionally exports the results.
    Args:
        file_path_a (str): Path to the first Excel file.
        file_path_b (str): Path to the second Excel file.
        output_dir (str): Directory where the output files will be saved.
        params (dict): Dictionary of parameters for processing and analysis.
            - 'selected_sheet' (str): Name of the sheet to be selected from the Excel files.
            - 'has_headers' (bool): Indicates if the workbook has headers.
            - 'selected_column_a' (str): Name of the column to be selected from the first Excel file.
            - 'selected_column_b' (str): Name of the column to be selected from the second Excel file.
            - 'checkbox_eb' (bool): Indicates if the signal type is event-based (not fixed rate).
            - 'checkbox_windowed_xcorr' (bool): Indicates if windowed cross-correlation should be performed.
            - 'window_size' (int): Size of the window for windowed cross-correlation.
            - 'step_size' (int): Step size for windowed cross-correlation.
            - 'max_lag' (int): Maximum lag for windowed cross-correlation.
            - 'checkbox_absolute_corr' (bool): Indicates if absolute values should be used for correlation.
            - 'checkbox_average_windows' (bool): Indicates if windows should be averaged.
            - 'max_lag_sxc' (int): Maximum lag for standard cross-correlation.
            - 'checkbox_absolute_corr_sxc' (bool): Indicates if absolute values should be used for standard cross-correlation.
            - 'checkbox_fr' (bool): Indicates if the signal type is fixed-rate.
        export (bool, optional): If True, the results will be exported to an Excel file. Defaults to True.
    Returns:
        dict: Correlation data resulting from the analysis.
    Raises:
        Exception: If an error occurs during processing, it will be printed.
    """
    
    # read data to workbooks
    wb_a = xlsx.read_xlsx(file_path_a)
    wb_b = xlsx.read_xlsx(file_path_b)

    try:
        # create columns object from selected sheet
        columns_a = xlsx.get_columns(wb_a, params['selected_sheet'], headers=params['has_headers'])
        columns_b = xlsx.get_columns(wb_b, params['selected_sheet'], headers=params['has_headers'])

        # get raw data
        raw_signal_a = columns_a[params['selected_column_a']]
        raw_signal_b = columns_b[params['selected_column_b']]

        # process data
        config = AnalysisConfig.from_params(params)
        signals, corr_data = analyze_dyad(raw_signal_a, raw_signal_b, config)
        _signal_a, _signal_b, _signal_a_z_scored, _signal_b_z_scored = signals

        # select signals based on standardisation flag
        use_standardised_data = config.standardised
        signal_a = _signal_a_z_scored if use_standardised_data else _signal_a
        signal_b = _signal_b_z_scored if use_standardised_data else _signal_b

        # make and export correlation data
        if params['checkbox_windowed_xcorr']:
            # WXCorr
            # export
            export_params = {
                'selected_dyad_dir': dyad_dir,
                'input_file_a': file_path_a,
                'input_file_b': file_path_b,
                'checkbox_fr': params['checkbox_fr'],
                'window_size': params['window_size'],
                'max_lag': params['max_lag'],
                'step_size': params['step_size'],
                'checkbox_absolute_corr': params['checkbox_absolute_corr'],
                'checkbox_average_windows': params['checkbox_average_windows'],
                'checkbox_eb': params['checkbox_eb'],
                'signal_a': _signal_a,
                'signal_b': _signal_b,
                'signal_a_std': _signal_a_z_scored,
                'signal_b_std': _signal_b_z_scored,
                'wxcorr': corr_data,
                'checkbox_lag_filter': params['use_lag_filter'],
                'lag_filter_min': params['lag_filter_min'],
                'lag_filter_max': params['lag_filter_max'],
                'is_standardised': use_standardised_data,
                'dfa_signals': signal_dfa(raw_signal_a, raw_signal_b, config) if export else None,
                'dfa_windows': windowed_dfa(corr_data, config) if export else None,
            }
            
            # export data and plot, making the plot first so that a failure leaves no files
            if export:
                fig = plot_windowed_cross_correlation(
                    wxc_data=corr_data, signal_a=signal_a, signal_b=signal_b,
                    show_sigmoid_correlations=params['sigmoid_correlations'],
                    use_lag_filter=params['use_lag_filter'], lag_filter_min=params['lag_filter_min'], lag_filter_max=params['lag_filter_max'],
                    window_size=params['window_size'], max_lag=params['max_lag'], step_size=params['step_size']
                )
                output_file_name = f"wx_{os.path.basename(dyad_dir) if dyad_dir else datetime.now().strftime('%Y%m%d%H%M%S')}_wxcorr.xlsx"
                output_file_path = os.path.join(output_dir, output_file_name)
                export_wxcorr_data(output_file_path, export_params)

                plot_file_name = f"wx_{os.path.basename(dyad_dir) if dyad_dir else datetime.now().strftime('%Y%m%d%H%M%S')}_wxcorr.png"
                plot_file_path = os.path.join(output_dir, plot_file_name)
                save_figure_to_png(fig=fig, filepath=plot_file_path)

            # return correlation data    
            return corr_data
        
        else:
            # Standard XCorr
            # export
            export_params = {
                'selected_dyad_dir': dyad_dir,
                'input_file_a': file_path_a,
                'input_file_b': file_path_b,
                'checkbox_fr': params['checkbox_fr'],
                'max_lag': params['max_lag_sxc'],
                'checkbox_absolute_corr': params['checkbox_absolute_corr_sxc'],
                'checkbox_eb': params['checkbox_eb'],
                'signal_a': _signal_a,
                'signal_b': _signal_b,
                'signal_a_std': _signal_a_z_scored,
                'signal_b_std': _signal_b_z_scored,
                'sxcorr': corr_data,
                'is_standardised': use_standardised_data,
                'dfa_signals': signal_dfa(raw_signal_a, raw_signal_b, config) if export else None,
            }
            
            # export data and plot, making the plot first so that a failure leaves no files
            if export:
                fig = plot_standard_cross_correlation(sxc_data=corr_data, signal_a=signal_a, signal_b=signal_b)
                output_file_name = f"{os.path.basename(dyad_dir) if dyad_dir else datetime.now().strftime('%Y%m%d%H%M%S')}_sxcorr.xlsx"
                output_file_path = os.path.join(output_dir, output_file_name)
                export_sxcorr_data(output_file_path, export_params)

                plot_file_name = f"{os.path.basename(dyad_dir) if dyad_dir else datetime.now().strftime('%Y%m%d%H%M%S')}_sxcorr.png"
                plot_file_path = os.path.join(output_dir, plot_file_name)
                save_figure_to_png(fig=fig, filepath=plot_file_path)

            return corr_data
    except Exception as e:
        print(f"! {os.path.basename(file_path_a)}, {os.path.basename(file_path_b)}: {e}")
        raise(e)

def _no_progress(done, total, text):
    pass

def _average_correlations(all_correlations):
    """One average per pair. A pair with only flat windows has no correlation to contribute."""
    averages = [mean_ignoring_flat_windows(c) for c in all_correlations]
    return [average for average in averages if not np.isnan(average)]

def _file_hash(file_path):
    with open(file_path, 'rb') as file:
        return hashlib.sha256(file.read()).hexdigest()

def _eligible_random_pairs(input_dir, dyad_folders):
    """
    Lists the pairs of recordings that can be used as random pairs. Recordings are told apart by their content,
    because preprocessing/group_to_dyads.py copies a person's file to many folders. This leaves out self-pairs,
    and real pairs, which are any two recordings that share a dyad folder.
    Args:
        input_dir (str): Path to the input directory containing dyad folders with Excel files.
        dyad_folders (list): Names of the dyad folders, in a fixed order.
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
            recording = _file_hash(file_path)
            path_of_recording.setdefault(recording, file_path)
            recordings.add(recording)
        real_pairs.update(frozenset(pair) for pair in itertools.combinations(recordings, 2))
    return [
        (path_of_recording[recording_a], path_of_recording[recording_b])
        for recording_a, recording_b in itertools.combinations(path_of_recording, 2)
        if frozenset((recording_a, recording_b)) not in real_pairs
    ]

def random_pair_analysis(params, input_dir, random_pair_count=100, progress=_no_progress, seed=None):
    """
    Perform analysis on random pairs and real dyad correlations.
    Args:
        params (dict): A dictionary of parameters, see batch_process function for details.
        input_dir (str): Path to the input directory containing dyad folders with Excel files.
        random_pair_count (int, optional): Number of random pairs to generate. Defaults to 100.
        progress (function, optional): Called with (done, total, text) before each pair or dyad.
        seed (int, optional): The same seed and files give the same random pairs.
    Returns:
        tuple: A tuple containing:
            - t_stat (float): The t-statistic from Welch's t-test.
            - p_value (float): The p-value from Welch's t-test.
            - average_correlations_rp (list): List of average correlations for random pairs.
            - average_correlations_real (list): List of average correlations for real dyads.
            - avg_wxcorr_real (list): Group-average wxcorr of real dyads (None for standard xcorr).
            - avg_wxcorr_rp (list): Group-average wxcorr of random pairs (None for standard xcorr).
            - failures (list): (name, error message) for each pair or dyad that could not be processed.
            - n_eligible_pairs (int): Number of different pairs the random pairs were drawn from.
            - window_counts_real (list): Number of windows of each real dyad (empty for standard xcorr).
            - window_counts_rp (list): Number of windows of each random pair (empty for standard xcorr).
    """

    # get input data
    dyad_folders = sorted(f for f in os.listdir(input_dir) if os.path.isdir(os.path.join(input_dir, f)))
    eligible_pairs = _eligible_random_pairs(input_dir, dyad_folders)
    if not eligible_pairs:
        raise ValueError("No random pairs are possible: all recordings are the same person or share a dyad folder.")
    # make random_pair_count random pairs of xlsx files, with a random person A and B
    rng = random.Random(seed)
    random_pairs = [rng.sample(rng.choice(eligible_pairs), 2) for _ in range(random_pair_count)]

    # read correlation type
    is_windowed_corr = params['checkbox_windowed_xcorr']

    # process random pairs
    failures = []
    all_correlations_rp = []
    all_wxcorr_rp = []
    total_steps = len(random_pairs) + len(dyad_folders)
    for pair_index, pair in enumerate(random_pairs):
        progress(pair_index, total_steps, "Random pairs")
        file_path_a, file_path_b = pair
        try:
            corr_data = _process_dyad(file_path_a, file_path_b, None, params, export=False)
        except Exception as e:
            print(f"! Skipping random pair: {e}")
            failures.append((f"random pair {os.path.basename(file_path_a)}, {os.path.basename(file_path_b)}", str(e)))
            continue
        if not corr_data:
            continue
        if is_windowed_corr:
            all_correlations_rp.append([val for d in corr_data for val in d['correlations']])
            all_wxcorr_rp.append(corr_data)
        else:
            all_correlations_rp.append(corr_data['corr'])

    # calculate averages of all correlations
    average_correlations_rp = _average_correlations(all_correlations_rp)

    # process all real dyads
    all_correlations_real = []
    all_wxcorr_real = []
    for dyad_index, dyad_folder in enumerate(dyad_folders):
        progress(len(random_pairs) + dyad_index, total_steps, dyad_folder)
        dyad_path = os.path.join(input_dir, dyad_folder)
        xlsx_files = utils.list_dyad_files(dyad_path)
        if len(xlsx_files) >= 2:
            file_a, file_b, _ = xlsx.choose_dyad_files(dyad_path, xlsx_files)
            file_path_a = os.path.join(dyad_path, file_a)
            file_path_b = os.path.join(dyad_path, file_b)
            try:
                corr_data = _process_dyad(
                    file_path_a=file_path_a,
                    file_path_b=file_path_b,
                    output_dir=None,
                    params=params,
                    export=False
                )
            except Exception as e:
                print(f"! Skipping {dyad_folder}: {e}")
                failures.append((dyad_folder, str(e)))
                continue
            if not corr_data:
                continue
            if is_windowed_corr:
                all_correlations_real.append([val for d in corr_data for val in d['correlations']])
                all_wxcorr_real.append(corr_data)
            else:
                all_correlations_real.append(corr_data['corr'])

    # calculate averages of all real dyad correlations
    average_correlations_real = _average_correlations(all_correlations_real)

    # run Welch's t-test
    t_stat, p_value = ttest_ind(average_correlations_rp, average_correlations_real, equal_var=False)

    # compute group-average correlation matrices for wxcorr
    avg_wxcorr_real = None
    avg_wxcorr_rp   = None
    if is_windowed_corr:
        min_lag = (
            min(params['lag_filter_min'], params['lag_filter_max'])
            if params['use_lag_filter'] else -params['max_lag']
        )
        if all_wxcorr_real:
            avg_wxcorr_real = average_wxcorr_matrices(all_wxcorr_real, min_lag, params['checkbox_average_windows'])
        if all_wxcorr_rp:
            avg_wxcorr_rp = average_wxcorr_matrices(all_wxcorr_rp, min_lag, params['checkbox_average_windows'])

    return (
        t_stat, p_value, average_correlations_rp, average_correlations_real, avg_wxcorr_real, avg_wxcorr_rp, failures,
        len(eligible_pairs), [len(wxcorr) for wxcorr in all_wxcorr_real], [len(wxcorr) for wxcorr in all_wxcorr_rp],
    )


def _same_folder(path_a, path_b):
    """True for two paths to one folder, also through links, and on Windows in another case."""
    return os.path.normcase(os.path.realpath(path_a)) == os.path.normcase(os.path.realpath(path_b))

# ---------------------------------------------------------------------------
# RESULTS OF EARLIER RUNS
# ---------------------------------------------------------------------------

RESULT_FILE_PATTERNS = (
    re.compile(r"^wx_.+_wxcorr\.(xlsx|png)$"),
    re.compile(r"^.+_sxcorr\.(xlsx|png)$"),
    re.compile(r"^grand_avg_wxcorr\.(xlsx|png)$"),
)

def find_result_files(output_dir):
    """The files in output_dir that a batch run writes. Anything else is left out, so it is never deleted."""
    if not output_dir or not os.path.isdir(output_dir):
        return []
    return sorted(
        f for f in os.listdir(output_dir)
        if os.path.isfile(os.path.join(output_dir, f)) and any(p.match(f) for p in RESULT_FILE_PATTERNS)
    )

def remove_result_files(output_dir, file_names):
    for file_name in file_names:
        os.remove(os.path.join(output_dir, file_name))

def batch_process(params, progress=_no_progress):
    """
    Processes a batch of dyad data files, performs cross-correlation analysis, and exports the results.
    Args:
        params (dict): A dictionary containing the following keys:
            - batch_input_folder (str): Path to the directory containing dyad folders.
            - output_dir (str): Path to the directory where output files will be saved.
            - selected_sheet (str): Name of the sheet to be processed in the Excel files.
            - has_headers (bool): Indicates if the Excel sheets have headers.
            - selected_column_a (str): Column name for the first signal.
            - selected_column_b (str): Column name for the second signal.
            - checkbox_eb (bool): If True, process data as 'eb_MS', otherwise as 'fr'.
            - checkbox_windowed_xcorr (bool): If True, perform windowed cross-correlation, otherwise standard cross-correlation.
            - window_size (int): Size of the window for windowed cross-correlation.
            - step_size (int): Step size for windowed cross-correlation.
            - max_lag (int): Maximum lag for windowed cross-correlation.
            - standardised_signals (bool): Use standardised (z-scored) input signals.
            - checkbox_absolute_corr (bool): If True, use absolute values for windowed cross-correlation.
            - checkbox_average_windows (bool): If True, average the windows for windowed cross-correlation.
            - sigmoid_correlations (bool): If True, export sigmoid-scaled correlation values.
            - max_lag_sxc (int): Maximum lag for standard cross-correlation.
            - checkbox_absolute_corr_sxc (bool): If True, use absolute values for standard cross-correlation.
            - checkbox_fr (bool): If True, indicates that fr data is being processed.
            - use_lag_filter (bool): Apply lag filter to limit lag range (wxcorr only).
            - lag_filter_min (int): Minimum lag for filter (inclusive) (wxcorr only).
            - lag_filter_max (int): Maximum lag for filter (inclusive) (wxcorr only).
        progress (function, optional): Called with (done, total, text) before each step.
    Returns:
        dict: A summary of the run:
            - processed (list): Names of the dyad folders that were processed.
            - failed (list): (folder name, error message) for each dyad folder that was skipped.
            - warnings (list): Messages about dyad folders that were processed with a caveat.
    """
    summary = {'processed': [], 'failed': [], 'warnings': []}

    # get directory in which dyad directories are stored
    batch_input_folder = params['batch_input_folder']
    if not batch_input_folder: return summary

    # get output directory
    output_dir = params['output_dir']
    if not output_dir: return summary

    # process dyads in folder, except the output folder: after a run it holds result files that would look like a dyad
    dyad_folders = sorted(f for f in os.listdir(batch_input_folder) if os.path.isdir(os.path.join(batch_input_folder, f)))
    output_folder = next((f for f in dyad_folders if _same_folder(os.path.join(batch_input_folder, f), output_dir)), None)
    if output_folder:
        dyad_folders.remove(output_folder)
        summary['warnings'].append(f"{output_folder}: skipped, because it is the output folder")
    all_wxcorr_results = []
    for dyad_index, dyad_folder in enumerate(dyad_folders):
        progress(dyad_index, len(dyad_folders), dyad_folder)
        dyad_path = os.path.join(batch_input_folder, dyad_folder)
        xlsx_files = utils.list_dyad_files(dyad_path)
        if len(xlsx_files) < 2:
            summary['failed'].append((dyad_folder, f"needs 2 xlsx files, found {len(xlsx_files)}"))
            continue
        file_a, file_b, sheets_match = xlsx.choose_dyad_files(dyad_path, xlsx_files)
        if len(xlsx_files) > 2:
            caveat = "" if sheets_match else ", because no two have the same sheets"
            summary['warnings'].append(f"{dyad_folder}: found {len(xlsx_files)} xlsx files, used {file_a} and {file_b}{caveat}")
        file_path_a = os.path.join(dyad_path, file_a)
        file_path_b = os.path.join(dyad_path, file_b)
        try:
            corr_data = _process_dyad(file_path_a, file_path_b, output_dir, params, dyad_dir=dyad_path, export=True)
            if params['checkbox_windowed_xcorr'] and corr_data:
                all_wxcorr_results.append(corr_data)
            summary['processed'].append(dyad_folder)
        except Exception as e:
            print(f"! Skipping {dyad_folder}: {e}")
            summary['failed'].append((dyad_folder, str(e)))

    # export group-average heatmap after all dyads are processed
    if params['checkbox_windowed_xcorr'] and all_wxcorr_results:
        progress(len(dyad_folders), len(dyad_folders), "Group average")
        min_lag = (
            min(params['lag_filter_min'], params['lag_filter_max'])
            if params['use_lag_filter'] else -params['max_lag']
        )
        avg_wxcorr = average_wxcorr_matrices(all_wxcorr_results, min_lag, params['checkbox_average_windows'])
        if avg_wxcorr:
            export_avg_wxcorr_data(
                os.path.join(output_dir, 'grand_avg_wxcorr.xlsx'),
                avg_wxcorr, len(all_wxcorr_results), params,
                window_counts=[len(wxcorr) for wxcorr in all_wxcorr_results],
            )
            fig = plot_windowed_cross_correlation(
                wxc_data=avg_wxcorr,
                signal_a=[], signal_b=[],
                window_size=params['window_size'],
                max_lag=params['max_lag'],
                step_size=params['step_size'],
                show_sigmoid_correlations=params['sigmoid_correlations'],
                use_lag_filter=params['use_lag_filter'],
                lag_filter_min=params['lag_filter_min'],
                lag_filter_max=params['lag_filter_max'],
            )
            save_figure_to_png(fig=fig, filepath=os.path.join(output_dir, 'grand_avg_wxcorr.png'))

    return summary