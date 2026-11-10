import math
import os
import queue
import random
import threading
from tkinter import filedialog, messagebox

import xlsx
import utils
from analysis import AnalysisConfig, preprocess_signals, signal_dfa
from signal_processing import detect_sampling_rate, guess_is_event_based
from batch_processing import batch_process, find_result_files, remove_result_files
from export import (
    export_surrogate_figure, export_surrogate_result, export_sxcorr_data, export_wxcorr_data, left_out_names,
)
from surrogates import (
    BLOCKS, DEFAULT_SURROGATES, MIN_BLOCKS, MIN_WELCH_GROUP, REPAIRED, WELCH, SurrogateChoice, choice_problem,
    few_sets_warning, folder_overview, plan_summary, result_summary, surrogate_analysis,
)

import corr_plot
import state
import validation

# ---------------------------------------------------------------------------
# LATE-REGISTERED WIDGET REFERENCES
# (populated by app_layout.build_layout after widgets are created)
# ---------------------------------------------------------------------------
PREVIEW_TAB = "Input Data"
SURROGATES_TAB = "Surrogates"
TABS_WITH_OWN_PLOT = (PREVIEW_TAB, SURROGATES_TAB)   # the other tabs show the correlation of the loaded dyad

_dropdowns = {}   # keys: 'sheet', 'column'
_tabview   = {}   # key: 'tabview'


def register_dropdowns(sheet_dd, column_dd):
    _dropdowns['sheet'] = sheet_dd
    _dropdowns['column'] = column_dd


def register_tabview(tabview):
    _tabview['tabview'] = tabview


# ---------------------------------------------------------------------------
# GUI STATE CALLBACKS
# ---------------------------------------------------------------------------

def on_tab_change():
    previous_tab = state.val_CURRENT_TAB.get()
    selected_tab = _tabview['tabview'].get()
    state.val_CURRENT_TAB.set(selected_tab)
    if previous_tab not in TABS_WITH_OWN_PLOT and selected_tab not in TABS_WITH_OWN_PLOT:
        return
    _tabview['tabview'].update_idletasks()  # show the new tab before the slower plot update
    state.PARAMS_CHANGED()


# ---------------------------------------------------------------------------
# ENTRY CALLBACKS — windowed xcorr
# ---------------------------------------------------------------------------

def on_window_size_input_change(name, index, mode):
    new_str_val = state.val_window_size_input.get()
    state.val_window_size.set(0 if new_str_val == '' else int(new_str_val))
    validation.check_wx_correlation_settings()
    state.PARAMS_CHANGED(debounce=True)


def on_step_size_input_change(name, index, mode):
    new_str_val = state.val_step_size_input.get()
    state.val_step_size.set(0 if new_str_val == '' else int(new_str_val))
    validation.check_wx_correlation_settings()
    state.PARAMS_CHANGED(debounce=True)


def on_max_lag_input_change(name, index, mode):
    new_str_val = state.val_max_lag_input.get()
    state.val_max_lag.set(0 if new_str_val == '' else int(new_str_val))
    validation.check_wx_correlation_settings()
    state.PARAMS_CHANGED(debounce=True)


# ENTRY CALLBACKS — standard xcorr

def on_max_lag_input_change_sxc(name, index, mode):
    new_str_val = state.val_max_lag_input_sxc.get()
    state.val_max_lag_sxc.set(0 if new_str_val == '' else int(new_str_val))
    validation.check_sx_correlation_settings()
    state.PARAMS_CHANGED(debounce=True)


# ENTRY CALLBACKS — lag filter

# The filter the user typed, or None to use the full range. It is kept while the max lag changes, so that
# typing a max lag doesn't lose it: typing 40 passes 4, which would otherwise narrow the filter for good.
_wanted_lag_filter = None
_setting_lag_filter = False     # True while the app writes the filter fields itself


def on_min_lag_input_change(name, index, mode):
    new_str_val = state.val_lag_filter_min_input.get()
    if new_str_val not in ('', '-'):
        state.val_lag_filter_min.set(int(new_str_val))
    _remember_lag_filter()
    validation.check_wx_correlation_settings()
    state.PARAMS_CHANGED(debounce=True)


def on_max_lag_filter_input_change(name, index, mode):
    new_str_val = state.val_lag_filter_max_input.get()
    if new_str_val not in ('', '-'):
        state.val_lag_filter_max.set(int(new_str_val))
    _remember_lag_filter()
    validation.check_wx_correlation_settings()
    state.PARAMS_CHANGED(debounce=True)


def _remember_lag_filter():
    global _wanted_lag_filter
    if not _setting_lag_filter:
        _wanted_lag_filter = (state.val_lag_filter_min.get(), state.val_lag_filter_max.get())


def lag_filter_for_max_lag(wanted, max_lag):
    """
    The wanted filter, narrowed to what the max lag allows. Falls back to the full range when nothing of the
    wanted filter is left, or when no filter was typed yet.
    """
    if wanted is None:
        return -max_lag, max_lag
    low = min(max(wanted[0], -max_lag), max_lag)
    high = min(max(wanted[1], -max_lag), max_lag)
    if high <= low:
        return -max_lag, max_lag
    return low, high


def on_max_lag_change_update_filter(*args):
    global _setting_lag_filter
    low, high = lag_filter_for_max_lag(_wanted_lag_filter, state.val_max_lag.get())
    _setting_lag_filter = True
    try:
        state.val_lag_filter_min.set(low)
        state.val_lag_filter_max.set(high)
        if state.val_lag_filter_min_input.get() != str(low):
            state.val_lag_filter_min_input.set(str(low))
        if state.val_lag_filter_max_input.get() != str(high):
            state.val_lag_filter_max_input.set(str(high))
    finally:
        _setting_lag_filter = False
    validation.check_wx_correlation_settings()
    state.PARAMS_CHANGED(debounce=True)


# ---------------------------------------------------------------------------
# CHECKBOX CALLBACKS
# ---------------------------------------------------------------------------

def on_absolute_corr_change():
    state.PARAMS_CHANGED()


def on_absolute_corr_change_sxc():
    state.PARAMS_CHANGED()


def on_is_eb_change():
    state.val_checkbox_fr.set(not state.val_checkbox_eb.get())
    preprocess_data()
    clear_correlation_data()
    state.PARAMS_CHANGED()


def on_is_fr_change():
    state.val_checkbox_eb.set(not state.val_checkbox_fr.get())
    preprocess_data()
    clear_correlation_data()
    state.PARAMS_CHANGED()


def on_standardise_change():
    clear_correlation_data()
    state.PARAMS_CHANGED()


def on_show_sigmoid_correlations_change():
    state.PARAMS_CHANGED()


def on_windowed_xcorr_change():
    state.PARAMS_CHANGED()


def on_average_windows_change():
    state.PARAMS_CHANGED()


def on_lag_filter_checkbox_change():
    validation.check_wx_correlation_settings()
    state.PARAMS_CHANGED()


# ---------------------------------------------------------------------------
# DROPDOWN CALLBACKS
# ---------------------------------------------------------------------------

def on_dropdown_select_sheet_change(value):
    update_column_names()
    guess_signal_type()
    preprocess_data()
    clear_correlation_data()
    state.PARAMS_CHANGED()


def on_dropdown_select_column_change(value):
    guess_signal_type()
    preprocess_data()
    clear_correlation_data()
    state.PARAMS_CHANGED()


def on_change_data_has_headers(*args):
    state.dat_workbook_data["has_headers"] = state.val_checkbox_data_has_headers.get()
    update_column_names()
    guess_signal_type()
    preprocess_data()
    clear_correlation_data()
    state.PARAMS_CHANGED()


# ---------------------------------------------------------------------------
# DROPDOWN UPDATE UTILITY
# ---------------------------------------------------------------------------

def update_dropdown_options(dropdown, dropdown_state_var, new_options):
    dropdown.configure(values=new_options)
    dropdown_state_var.set(new_options[0] if new_options else '- None -')


# ---------------------------------------------------------------------------
# SURROGATE SETTINGS
# ---------------------------------------------------------------------------

def on_rp_n_input_change(name, index, mode):
    new_str_val = state.val_rp_n_input.get()
    if new_str_val == '':
        state.val_rp_n.set(0)
    else:
        new_val = int(new_str_val)
        if new_val < 0:
            new_val = 0
        state.val_rp_n.set(new_val)


# ---------------------------------------------------------------------------
# SAMPLING RATE OF FIXED-RATE DATA
# Only shown in seconds when it is known: from a time column next to the data, or entered by hand.
# ---------------------------------------------------------------------------

_rate_detection = {'data': None, 'found': None, 'files_disagree': False, 'filled': None}


def _format_rate(rate):
    return f"{rate:g}"


def detect_sampling_rate_of_loaded_data(column):
    """
    Looks for a time column next to the data in both files. A found rate fills the field, once for each data, so
    that a rate entered by hand stays until other data is loaded. Without a time column, a rate entered by hand
    stays, and one that came from the previous data's time column is cleared.
    """
    data = (state.val_selected_file_a.get(), state.val_selected_file_b.get(), state.val_selected_sheet.get(),
            column, state.val_checkbox_data_has_headers.get())
    if data == _rate_detection['data']:
        return
    found_a = detect_sampling_rate(state.dat_workbook_data["columns_a"], column)
    found_b = detect_sampling_rate(state.dat_workbook_data["columns_b"], column)
    files_disagree = bool(found_a and found_b and found_a[0] != found_b[0])
    found = None if files_disagree else (found_a or found_b)
    previously_filled = _rate_detection['filled']
    _rate_detection.update(data=data, found=found, files_disagree=files_disagree, filled=None)
    if found:
        _rate_detection['filled'] = _format_rate(found[0])
        state.val_sampling_rate_input.set(_rate_detection['filled'])
    elif previously_filled is not None and state.val_sampling_rate_input.get() == previously_filled:
        state.val_sampling_rate_input.set('')
    update_sampling_rate_note()


def on_sampling_rate_input_change(name, index, mode):
    state.val_sampling_rate.set(validation.parse_decimal(state.val_sampling_rate_input.get()))
    update_sampling_rate_note()


def update_sampling_rate_note(*args):
    rate = state.val_sampling_rate.get()
    found = _rate_detection['found']
    if found and rate == found[0]:
        note = f"From column '{found[1]}'."
    elif rate:
        note = "Entered by hand." + (f" Column '{found[1]}' says {_format_rate(found[0])} Hz." if found else "")
    elif _rate_detection['files_disagree']:
        note = "The time columns of the two files give different rates. Enter the rate to see times in seconds."
    else:
        note = "No time column found next to the data. Optional: enter the rate to see times in seconds."
    state.val_sampling_rate_note.set(note)


# The block length follows the window size until it is set to something else
_block_length = {'follows_window': True}


def on_block_length_input_change(name, index, mode):
    new_str_val = state.val_block_length_input.get()
    state.val_block_length.set(0 if new_str_val == '' else int(new_str_val))
    _block_length['follows_window'] = state.val_block_length.get() == state.val_window_size.get()


def on_window_size_change_update_block_length(*args):
    if _block_length['follows_window']:
        state.val_block_length_input.set(str(state.val_window_size.get()))


def surrogate_choice():
    """The test the Surrogates tab is set to. Welch's t-test is an option of re-paired people."""
    method = state.val_surrogate_method.get()
    if method == REPAIRED and state.val_surrogate_test.get() == WELCH:
        method = WELCH
    return SurrogateChoice(
        method=method,
        measure=state.val_surrogate_measure.get(),
        n_surrogates=state.val_rp_n.get(),
        block_length=state.val_block_length.get() if method == BLOCKS else None,
    )


_surrogates = {'method': None, 'folder': {}}


def on_surrogate_method_change(*args):
    """Welch's t-test and the surrogate distribution have different usual numbers, which follow the test."""
    method = surrogate_choice().method
    previous = _surrogates['method']
    if previous and previous != method and state.val_rp_n.get() == DEFAULT_SURROGATES[previous]:
        state.val_rp_n_input.set(str(DEFAULT_SURROGATES[method]))
    _surrogates['method'] = method
    update_surrogate_plan()


def on_surrogate_folder_change(*args):
    folder = state.val_random_pair_input_folder.get()
    try:
        _surrogates['folder'] = folder_overview(folder) if folder else {}
    except OSError:
        _surrogates['folder'] = {}
    update_surrogate_plan()


def _surrogate_warning(choice):
    """What will limit the result, judged before the run from the folder and the loaded dyad."""
    folder = _surrogates['folder']
    if choice.method in (REPAIRED, WELCH) and folder:
        if folder['n_dyads'] == 0:
            return "The selected folder has no dyad folders with two recordings."
        if choice.method == REPAIRED:
            return few_sets_warning(folder['n_sets'], choice.n_surrogates, about=True)
    if choice.method == BLOCKS and choice.block_length and state.val_INPUT_DATA_VALID.get():
        n_blocks = state.val_data_length.get() // choice.block_length
        if n_blocks < MIN_BLOCKS:
            return (
                f"The dyad loaded in Input Data fits only {n_blocks} blocks of {choice.block_length} samples, and "
                f"at least {MIN_BLOCKS} are needed. Dyads as long as it would be skipped."
            )
        if math.factorial(n_blocks) - 1 < choice.n_surrogates:
            return (
                f"The dyad loaded in Input Data has {n_blocks} blocks, which allow {math.factorial(n_blocks) - 1} "
                f"different orders, fewer than the {choice.n_surrogates} drawn. Its own p can't usefully go below "
                f"about 1/{math.factorial(n_blocks) - 1}."
            )
    return None


def update_surrogate_plan(*args):
    choice = surrogate_choice()
    config = state.analysis_config()
    problem = choice_problem(choice, config)
    state.val_surrogate_problem.set(problem or '')
    n_dyads = _surrogates['folder'].get('n_dyads')
    state.val_surrogate_plan.set('' if problem else plan_summary(choice, config, n_dyads))
    state.val_surrogate_warning.set('' if problem else (_surrogate_warning(choice) or ''))
    _surrogates_are_ready()
    _update_surrogate_staleness()


# settings that don't change a surrogate result
SETTINGS_NOT_IN_A_RESULT = ('batch_input_folder', 'output_dir', 'sigmoid_correlations')


def surrogate_settings(params, choice, input_dir):
    """Everything a surrogate result depends on, so that a change since the run can be noticed."""
    kept = tuple(sorted((key, value) for key, value in params.items() if key not in SETTINGS_NOT_IN_A_RESULT))
    return kept, choice, input_dir


def _update_surrogate_staleness():
    run = state.dat_surrogate_run
    if run['result'] is None:
        return
    stale = run['settings'] != surrogate_settings(_analysis_params(), surrogate_choice(),
                                                  state.val_random_pair_input_folder.get())
    if stale != run['stale']:
        run['stale'] = stale
        _update_surrogate_result_text()
        if state.val_CURRENT_TAB.get() == SURROGATES_TAB:
            state.PARAMS_CHANGED()


def _update_surrogate_result_text():
    """Says which result the export button writes."""
    run = state.dat_surrogate_run
    if run['result'] is None:
        state.val_surrogate_result_text.set('')
        return
    text = f"Last run: {os.path.basename(run['folder'])}, seed {run['result'].seed}."
    if run['stale']:
        text += " The settings have changed since. The export has the settings of that run."
    state.val_surrogate_result_text.set(text)


# ---------------------------------------------------------------------------
# TRACE REGISTRATIONS
# (called by app.py via setup_input_traces / setup_batch_traces)
# ---------------------------------------------------------------------------

def setup_traces():
    state.val_window_size_input.trace_add("write", on_window_size_input_change)
    state.val_step_size_input.trace_add("write", on_step_size_input_change)
    state.val_max_lag_input.trace_add("write", on_max_lag_input_change)
    state.val_max_lag_input_sxc.trace_add("write", on_max_lag_input_change_sxc)
    state.val_lag_filter_min_input.trace_add("write", on_min_lag_input_change)
    state.val_lag_filter_max_input.trace_add("write", on_max_lag_filter_input_change)
    state.val_max_lag.trace_add('write', on_max_lag_change_update_filter)
    state.val_checkbox_data_has_headers.trace_add('write', on_change_data_has_headers)
    state.val_rp_n_input.trace_add("write", on_rp_n_input_change)
    state.val_block_length_input.trace_add("write", on_block_length_input_change)
    state.val_sampling_rate_input.trace_add("write", on_sampling_rate_input_change)
    update_sampling_rate_note()
    state.val_window_size.trace_add("write", on_window_size_change_update_block_length)

    # batch ready state
    state.val_INPUT_DATA_VALID.trace_add('write', _batch_processing_is_ready)
    state.val_CORRELATION_SETTINGS_VALID.trace_add('write', _batch_processing_is_ready)
    state.val_CORRELATION_SETTINGS_VALID_SXC.trace_add('write', _batch_processing_is_ready)
    state.val_checkbox_windowed_xcorr.trace_add('write', _batch_processing_is_ready)
    state.val_batch_input_folder.trace_add('write', _batch_processing_is_ready)
    state.val_batch_output_folder.trace_add('write', _batch_processing_is_ready)

    # surrogate analysis: what it will do, and whether it can run
    state.val_surrogate_method.trace_add('write', on_surrogate_method_change)
    state.val_surrogate_test.trace_add('write', on_surrogate_method_change)
    state.val_random_pair_input_folder.trace_add('write', on_surrogate_folder_change)
    for var in (
        state.val_surrogate_measure, state.val_rp_n, state.val_block_length, state.val_data_length,
        state.val_INPUT_DATA_VALID, state.val_CORRELATION_SETTINGS_VALID, state.val_CORRELATION_SETTINGS_VALID_SXC,
        state.val_checkbox_windowed_xcorr, state.val_checkbox_average_windows, state.val_checkbox_lag_filter,
        state.val_lag_filter_min, state.val_lag_filter_max, state.val_max_lag, state.val_checkbox_absolute_corr,
        state.val_checkbox_absolute_corr_sxc,
        # these only matter for whether the shown result is out of date
        state.val_window_size, state.val_step_size, state.val_max_lag_sxc, state.val_checkbox_standardise,
        state.val_selected_sheet, state.val_selected_column, state.val_checkbox_data_has_headers,
        state.val_checkbox_eb, state.val_checkbox_fr,
    ):
        var.trace_add('write', update_surrogate_plan)
    _surrogates['method'] = surrogate_choice().method
    update_surrogate_plan()


# ---------------------------------------------------------------------------
# XLSX DATA HANDLING
# ---------------------------------------------------------------------------

def read_xlsx_files():
    state.dat_workbook_data["workbook_a"] = xlsx.read_xlsx(state.val_selected_file_a.get())
    state.dat_workbook_data["workbook_b"] = xlsx.read_xlsx(state.val_selected_file_b.get())


def update_sheet_names():
    wb_a = state.dat_workbook_data["workbook_a"]
    wb_b = state.dat_workbook_data["workbook_b"]
    state.dat_workbook_data["sheet_names"] = []
    if wb_a and wb_b:
        names_b = xlsx.get_sheet_names(wb_b)
        state.dat_workbook_data["sheet_names"] = [name for name in xlsx.get_sheet_names(wb_a) if name in names_b]
    update_dropdown_options(
        _dropdowns['sheet'],
        state.val_selected_sheet,
        state.dat_workbook_data["sheet_names"]
    )


def update_column_names():
    state.dat_workbook_data["column_names"] = []
    if state.val_selected_sheet.get() and state.val_selected_sheet.get() != '- None -':
        wb_a    = state.dat_workbook_data["workbook_a"]
        wb_b    = state.dat_workbook_data["workbook_b"]
        sheet   = state.val_selected_sheet.get()
        headers = state.dat_workbook_data["has_headers"]

        state.dat_workbook_data["columns_a"] = xlsx.get_columns(wb_a, sheet, headers=headers)
        state.dat_workbook_data["columns_b"] = xlsx.get_columns(wb_b, sheet, headers=headers)

        # person A and B are analysed in the same column, so it has to exist in both files
        state.dat_workbook_data["column_names"] = [
            name for name in state.dat_workbook_data["columns_a"] if name in state.dat_workbook_data["columns_b"]
        ]

    update_dropdown_options(_dropdowns['column'], state.val_selected_column, state.dat_workbook_data["column_names"])


# ---------------------------------------------------------------------------
# DATA PRE-PROCESSING
# ---------------------------------------------------------------------------

def set_invalid_data(reason):
    """
    Clears the signals and all results computed from them, so that nothing out of date can be shown or exported.
    reason says why the data can't be used, and is shown under the dropdowns. It is empty when nothing is loaded.
    """
    d = state.dat_physiological_data
    for key in ("signal_a", "signal_b", "signal_a_std", "signal_b_std", "raw_signal_a", "raw_signal_b"):
        d[key] = []
    state.dat_correlation_data['dfa_signals'] = None
    clear_correlation_data()
    state.val_input_error.set(reason)
    state.val_INPUT_DATA_VALID.set(False)


def preprocess_data():
    d = state.dat_physiological_data
    files_loaded = bool(state.dat_workbook_data.get("workbook_a") and state.dat_workbook_data.get("workbook_b"))
    sheet = state.val_selected_sheet.get()
    column = state.val_selected_column.get()

    if not sheet or sheet == '- None -':
        set_invalid_data("The two files have no sheet with the same name." if files_loaded else "")
        return
    if not column or column == '- None -':
        set_invalid_data(f"The two files have no column with the same name in sheet '{sheet}'.")
        return

    raw_signal_a = state.dat_workbook_data["columns_a"][column]
    raw_signal_b = state.dat_workbook_data["columns_b"][column]
    detect_sampling_rate_of_loaded_data(column)
    if not (utils.is_numeric_array(raw_signal_a) and utils.is_numeric_array(raw_signal_b)):
        set_invalid_data(f"Column '{column}' contains values that aren't numbers, or empty cells.")
        return

    try:
        signal_a, signal_b, signal_a_std, signal_b_std = preprocess_signals(
            raw_signal_a, raw_signal_b, state.analysis_config()
        )
    except Exception as e:
        set_invalid_data(str(e))
        return

    d["raw_signal_a"] = raw_signal_a
    d["raw_signal_b"] = raw_signal_b
    d["signal_a"]     = signal_a
    d["signal_b"]     = signal_b
    d["signal_a_std"] = signal_a_std
    d["signal_b_std"] = signal_b_std
    state.dat_correlation_data['dfa_signals'] = signal_dfa(raw_signal_a, raw_signal_b, state.analysis_config())
    state.val_data_length.set(len(signal_a))
    state.val_input_error.set("")
    state.val_INPUT_DATA_VALID.set(True)
    validation.check_all_settings()


def clear_correlation_data():
    state.dat_correlation_data["wxcorr"] = []
    state.dat_correlation_data["sxcorr"] = []
    state.dat_correlation_data["dfa_windows"] = None


# ---------------------------------------------------------------------------
# MAIN DATA LOADING ROUTINE
# ---------------------------------------------------------------------------

def load_xlsx_data():
    read_xlsx_files()
    show_loaded_workbooks()


def show_loaded_workbooks():
    """Fills the dropdowns and signals from the workbooks in state.dat_workbook_data."""
    update_sheet_names()
    update_column_names()
    guess_signal_type()
    preprocess_data()
    clear_correlation_data()


def guess_signal_type():
    """
    Sets event-based or fixed-rate from the values of the selected column, when new data is chosen.
    Ticking a data type by hand still works, until the data changes again.
    """
    column = state.val_selected_column.get()
    raw_a = state.dat_workbook_data["columns_a"].get(column)
    raw_b = state.dat_workbook_data["columns_b"].get(column)
    if not (utils.is_numeric_array(raw_a) and utils.is_numeric_array(raw_b)):
        return
    is_event_based = bool(guess_is_event_based(raw_a, raw_b))
    state.val_checkbox_eb.set(is_event_based)
    state.val_checkbox_fr.set(not is_event_based)


# ---------------------------------------------------------------------------
# FILE PICKERS
# ---------------------------------------------------------------------------

def open_dir_picker():
    """Loads a dyad folder. If it can't be used, the data loaded before stays, together with its folder name."""
    dir_path = filedialog.askdirectory(title="Select a directory")
    if not dir_path:
        return
    xlsx_files = utils.list_dyad_files(dir_path)
    if len(xlsx_files) < 2:
        messagebox.showwarning(
            "Not a dyad folder",
            f"Found {len(xlsx_files)} xlsx file{'' if len(xlsx_files) == 1 else 's'} in {os.path.basename(dir_path)}. "
            "A dyad folder needs two."
        )
        return
    file_a, file_b, sheets_match = xlsx.choose_dyad_files(dir_path, xlsx_files)
    workbooks = {"workbook_a": None, "workbook_b": None}
    read_error = None
    for key, file_name in (("workbook_a", file_a), ("workbook_b", file_b)):
        try:
            workbooks[key] = xlsx.read_xlsx(os.path.join(dir_path, file_name))
        except Exception as e:
            read_error = f"{file_name} can't be read as an xlsx file ({e})."
            break
    if len(xlsx_files) > 2:
        reason = "the first two with the same sheets" if sheets_match else "the first two, because no two have the same sheets"
        messagebox.showwarning(
            "More than two files",
            f"Found {len(xlsx_files)} xlsx files, using {file_a} and {file_b} ({reason})."
        )
    state.val_selected_dyad_dir.set(dir_path)
    state.val_selected_file_a.set(os.path.join(dir_path, file_a))
    state.val_selected_file_b.set(os.path.join(dir_path, file_b))
    state.dat_workbook_data.update(workbooks)
    show_loaded_workbooks()
    if read_error:
        set_invalid_data(read_error)
    state.PARAMS_CHANGED()


def open_batch_output_dir_picker():
    dir_path = filedialog.askdirectory(title="Select Output Directory")
    if not dir_path:
        return
    state.val_batch_output_folder.set(dir_path)


def open_batch_input_folder():
    dir_path = filedialog.askdirectory(title="Select Batch Input Folder")
    if not dir_path:
        return
    state.val_batch_input_folder.set(dir_path)


def open_random_pair_input_dir_picker():
    dir_path = filedialog.askdirectory(title="Select Input Folder")
    if not dir_path:
        return
    state.val_random_pair_input_folder.set(dir_path)


# ---------------------------------------------------------------------------
# EXPORT HANDLERS
# ---------------------------------------------------------------------------

def _export_wxcorr_data(file_path):
    params = {
        'selected_dyad_dir':              state.val_selected_dyad_dir.get(),
        'input_file_a':                   state.val_selected_file_a.get(),
        'input_file_b':                   state.val_selected_file_b.get(),
        'window_size':                    state.val_window_size.get(),
        'max_lag':                        state.val_max_lag.get(),
        'step_size':                      state.val_step_size.get(),
        'checkbox_lag_filter':            state.val_checkbox_lag_filter.get(),
        'lag_filter_min':                 state.val_lag_filter_min.get(),
        'lag_filter_max':                 state.val_lag_filter_max.get(),
        'checkbox_absolute_corr':         state.val_checkbox_absolute_corr.get(),
        'checkbox_average_windows':       state.val_checkbox_average_windows.get(),
        'checkbox_eb':                    state.val_checkbox_eb.get(),
        'checkbox_fr':                    state.val_checkbox_fr.get(),
        'signal_a':                       state.dat_physiological_data["signal_a"],
        'signal_b':                       state.dat_physiological_data["signal_b"],
        'signal_a_std':                   state.dat_physiological_data["signal_a_std"],
        'signal_b_std':                   state.dat_physiological_data["signal_b_std"],
        'is_standardised':                state.val_checkbox_standardise.get(),
        'wxcorr':                         state.dat_correlation_data["wxcorr"],
        'dfa_signals':                    state.dat_correlation_data['dfa_signals'],
        'dfa_windows':                    state.dat_correlation_data['dfa_windows'],
    }
    export_wxcorr_data(file_path, params)


def _export_sxcorr_data(file_path):
    params = {
        'selected_dyad_dir':      state.val_selected_dyad_dir.get(),
        'input_file_a':           state.val_selected_file_a.get(),
        'input_file_b':           state.val_selected_file_b.get(),
        'checkbox_fr':            state.val_checkbox_fr.get(),
        'checkbox_eb':            state.val_checkbox_eb.get(),
        'max_lag':                state.val_max_lag_sxc.get(),
        'checkbox_absolute_corr': state.val_checkbox_absolute_corr_sxc.get(),
        'signal_a':               state.dat_physiological_data["signal_a"],
        'signal_b':               state.dat_physiological_data["signal_b"],
        'signal_a_std':           state.dat_physiological_data["signal_a_std"],
        'signal_b_std':           state.dat_physiological_data["signal_b_std"],
        'is_standardised':        state.val_checkbox_standardise.get(),
        'sxcorr':                 state.dat_correlation_data["sxcorr"],
        'dfa_signals':            state.dat_correlation_data['dfa_signals'],
    }
    export_sxcorr_data(file_path, params)


def _export_file_name(kind):
    """The suggested name for an export: biosync_<wxc|xc>_<data|plot>, followed by the dyad folder if there is one."""
    correlation_type = "wxc" if state.val_checkbox_windowed_xcorr.get() else "xc"
    selected_dir = state.val_selected_dyad_dir.get()
    name = f"biosync_{correlation_type}_{kind}"
    return f"{name}_{os.path.basename(selected_dir)}" if selected_dir else name


def _while_exporting(kind, write):
    """
    Runs write on the main thread, which freezes the window for a few seconds with many windows.
    Shows that the window is busy first, because it can't redraw until write is done.
    """
    state.val_exporting.set(kind)
    _tabview['tabview'].update_idletasks()
    try:
        write()
    finally:
        state.val_exporting.set('')


def export_data():
    corr_plot.flush_update()  # results must match settings typed just before clicking
    filename_init  = _export_file_name("data")
    file_path = filedialog.asksaveasfilename(
        title="Save As",
        defaultextension=".xlsx",
        initialfile=filename_init,
        filetypes=(("XLSX files", "*.xlsx"),)
    )
    if not file_path:
        return
    write = _export_wxcorr_data if state.val_checkbox_windowed_xcorr.get() else _export_sxcorr_data
    try:
        _while_exporting("data", lambda: write(file_path))
    except Exception as e:
        messagebox.showerror("Export failed", str(e))


def export_plot():
    corr_plot.flush_update()
    fig = state.dat_plot_data["fig"]
    if not fig:
        return
    filename_init = _export_file_name("plot")
    file_path = filedialog.asksaveasfilename(
        title="Save As",
        defaultextension=".png",
        initialfile=filename_init,
        filetypes=(("PNG files", "*.png"),)
    )
    if not file_path:
        return
    try:
        _while_exporting("plot", lambda: fig.savefig(file_path, dpi=300, format='png'))
    except Exception as e:
        messagebox.showerror("Export failed", str(e))


# ---------------------------------------------------------------------------
# BACKGROUND JOBS
# Tk only works on the main thread, so a job gets everything it needs up front
# and reports through a queue, which the main thread reads.
# ---------------------------------------------------------------------------

JOB_POLL_MS = 100

_job_cancel_event = threading.Event()


class JobCancelled(Exception):
    pass


def _format_progress(done, total, text):
    return f"{text} ({done + 1} of {total})" if done < total else text


def _start_job(title, work, on_success):
    """
    Runs work(progress) on another thread, so that the window stays responsive.
    work must not use state or any widget. on_success(result) runs on the main thread.
    A job stops when it next reports progress after cancel_job, so the dyad it is working on gets finished.
    """
    messages = queue.Queue()
    _job_cancel_event.clear()

    def progress(done, total, text):
        if _job_cancel_event.is_set():
            raise JobCancelled
        messages.put(('progress', done, total, text))

    def run():
        try:
            result = work(progress)
        except JobCancelled:
            messages.put(('cancelled',))
        except Exception as e:
            messages.put(('error', e))
        else:
            messages.put(('done', result))

    state.val_job_cancel_requested.set(False)
    state.val_job_progress.set(0)
    state.val_job_progress_text.set(title)
    state.val_job_running.set(True)
    _batch_processing_is_ready()
    _surrogates_are_ready()
    threading.Thread(target=run, daemon=True).start()
    _tabview['tabview'].after(JOB_POLL_MS, _poll_job, messages, title, on_success)


def _poll_job(messages, title, on_success):
    while True:
        try:
            message = messages.get_nowait()
        except queue.Empty:
            _tabview['tabview'].after(JOB_POLL_MS, _poll_job, messages, title, on_success)
            return
        if message[0] == 'progress':
            _, done, total, text = message
            state.val_job_progress.set(done / total if total else 0)
            if not _job_cancel_event.is_set():
                state.val_job_progress_text.set(_format_progress(done, total, text))
            continue
        state.val_job_running.set(False)
        _batch_processing_is_ready()
        _surrogates_are_ready()
        if message[0] == 'error':
            messagebox.showerror(f"{title} failed", str(message[1]))
        elif message[0] == 'cancelled':
            messagebox.showinfo(f"{title} cancelled", "Stopped early. Files that were already written are kept.")
        else:
            on_success(message[1])
        return


def cancel_job():
    _job_cancel_event.set()
    state.val_job_cancel_requested.set(True)
    state.val_job_progress_text.set("Cancelling after the current step...")


def confirm_close():
    """Closing the window ends a running job, which leaves its output files incomplete."""
    return not state.val_job_running.get() or messagebox.askokcancel(
        "Still running", "A batch or random pair analysis is still running. Close and stop it?"
    )


# ---------------------------------------------------------------------------
# BATCH PROCESSING
# ---------------------------------------------------------------------------

MAX_LISTED_FAILURES = 10


def _analysis_params():
    """Collects the current settings for batch processing and random pair analysis."""
    return {
        'batch_input_folder':         state.val_batch_input_folder.get(),
        'output_dir':                 state.val_batch_output_folder.get(),
        'selected_sheet':             state.val_selected_sheet.get(),
        'has_headers':                state.val_checkbox_data_has_headers.get(),
        'selected_column_a':          state.val_selected_column.get(),
        'selected_column_b':          state.val_selected_column.get(),
        'checkbox_windowed_xcorr':    state.val_checkbox_windowed_xcorr.get(),
        'window_size':                state.val_window_size.get(),
        'step_size':                  state.val_step_size.get(),
        'max_lag':                    state.val_max_lag.get(),
        'max_lag_sxc':                state.val_max_lag_sxc.get(),
        'standardised_signals':       state.val_checkbox_standardise.get(),
        'checkbox_absolute_corr':     state.val_checkbox_absolute_corr.get(),
        'checkbox_absolute_corr_sxc': state.val_checkbox_absolute_corr_sxc.get(),
        'checkbox_average_windows':   state.val_checkbox_average_windows.get(),
        'sigmoid_correlations':       state.val_checkbox_show_sigmoid_correlations.get(),
        'checkbox_eb':                state.val_checkbox_eb.get(),
        'checkbox_fr':                state.val_checkbox_fr.get(),
        'use_lag_filter':             state.val_checkbox_lag_filter.get(),
        'lag_filter_min':             state.val_lag_filter_min.get(),
        'lag_filter_max':             state.val_lag_filter_max.get(),
    }


def _format_failures(failures):
    lines = [f"{name}: {error}" for name, error in failures[:MAX_LISTED_FAILURES]]
    if len(failures) > MAX_LISTED_FAILURES:
        lines.append(f"... and {len(failures) - MAX_LISTED_FAILURES} more")
    return lines


def _format_batch_summary(summary):
    lines = [f"Processed {len(summary['processed'])} dyads, skipped {len(summary['failed'])}."]
    if summary['failed']:
        lines += ["", "Skipped:"] + _format_failures(summary['failed'])
    if summary['warnings']:
        lines += ["", "Warnings:"] + summary['warnings']
    return "\n".join(lines)


def _batch_processing_is_ready(*args):
    data_is_valid = (
        state.val_INPUT_DATA_VALID.get() and validation.check_active_settings_valid() and
        not state.val_job_running.get()
    )
    io_is_ready = (
        state.val_batch_input_folder.get() != '' and
        state.val_batch_output_folder.get() != ''
    )
    state.val_batch_processing_is_ready.set(data_is_valid and io_is_ready)


def run_batch_process(params, progress):
    return batch_process(params, progress=progress)


def _replace_earlier_results(output_dir):
    """
    Asks before a run whether to delete the results of an earlier run in the output folder, which would otherwise
    stay next to the new ones. Returns False if the run shouldn't start.
    """
    earlier = find_result_files(output_dir)
    if not earlier:
        return True
    if not messagebox.askyesno(
        "Earlier results in the output folder",
        f"{os.path.basename(output_dir)} contains {len(earlier)} files from an earlier run. "
        "Delete them and start? Other files in the folder stay.",
    ):
        return False
    try:
        remove_result_files(output_dir, earlier)
    except OSError as e:
        messagebox.showerror("Can't delete earlier results", str(e))
        return False
    return True


def handle_run_batch_button():
    params = _analysis_params()
    if not _replace_earlier_results(params['output_dir']):
        return
    _start_job(
        "Batch processing",
        lambda progress: run_batch_process(params, progress),
        lambda summary: messagebox.showinfo("Batch processing finished", _format_batch_summary(summary)),
    )


# ---------------------------------------------------------------------------
# SURROGATE ANALYSIS
# ---------------------------------------------------------------------------

MAX_RANDOM_SEED = 2**32


def _surrogates_are_ready(*args):
    data_is_valid = (
        state.val_INPUT_DATA_VALID.get() and validation.check_active_settings_valid() and
        not state.val_job_running.get()
    )
    folder_is_chosen = state.val_random_pair_input_folder.get() != ''
    state.val_random_pair_is_ready.set(bool(data_is_valid and folder_is_chosen and not state.val_surrogate_problem.get()))


def run_surrogate_analysis(params, choice, input_dir, seed, progress):
    """Runs the test. Exporting is a separate step, so that a result can be looked at first."""
    result = surrogate_analysis(
        choice.method, params, input_dir, choice.n_surrogates, seed, choice.measure,
        block_length=choice.block_length, progress=progress,
    )
    return {
        'result': result,
        'method': result.method,
        'failures': result.failures,
        'p_value': result.p_value,
        'random_pairs_requested': choice.n_surrogates,
        'random_pairs_used': result.n_pairs_used,
        'real_dyads_used': len(result.real_values),
        'left_out_files': left_out_names(result.left_out_files, input_dir),
    }


def _random_pair_problems(summary):
    """Reasons not to trust the result of Welch's t-test, as sentences. Empty if there are none."""
    problems = []
    if summary['random_pairs_used'] < MIN_WELCH_GROUP or summary['real_dyads_used'] < MIN_WELCH_GROUP:
        problems.append(
            f"The t-test needs at least {MIN_WELCH_GROUP} random pairs and {MIN_WELCH_GROUP} real dyads, "
            f"and got {summary['random_pairs_used']} and {summary['real_dyads_used']}."
        )
    elif summary['p_value'] != summary['p_value']:   # NaN
        problems.append("The t-test gave no p-value, for example because all values were the same.")
    skipped = summary['random_pairs_requested'] - summary['random_pairs_used']
    if skipped:
        problems.append(f"{skipped} of {summary['random_pairs_requested']} random pairs were skipped, so the result rests on fewer.")
    return problems


def _surrogate_problems(summary):
    """Reasons not to trust the result, as sentences. Empty if there are none."""
    if summary.get('method', WELCH) == WELCH:
        return _random_pair_problems(summary)
    result = summary['result']
    problems = []
    if result.method == REPAIRED:
        warning = few_sets_warning(result.n_sets_possible, result.n_surrogates)
        if warning:
            problems.append(warning)
    if result.method == BLOCKS:
        few_orders = [orders for orders in result.dyad_orders_possible if orders < result.n_surrogates]
        if few_orders:
            problems.append(
                f"{len(few_orders)} of {len(result.dyad_names)} dyads allow fewer different block orders than the "
                f"{result.n_surrogates} drawn, so their own p can't usefully go below about 1/{min(few_orders)}."
            )
    return problems


def _show_surrogate_summary(summary):
    failures = summary['failures']
    problems = _surrogate_problems(summary)
    lines = [result_summary(summary['result'])] if 'result' in summary else []
    lines.append(f"Finished, {len(failures)} pairs or dyads skipped.")
    if problems:
        lines += [""] + problems
    if summary.get('left_out_files'):
        lines += ["", "Not used for random pairs:"] + summary['left_out_files'][:MAX_LISTED_FAILURES]
    if failures:
        lines += ["", "Skipped:"] + _format_failures(failures)
    if problems:
        messagebox.showwarning("Surrogate analysis finished with problems", "\n".join(lines))
    else:
        messagebox.showinfo("Surrogate analysis finished", "\n".join(lines))


def handle_run_surrogate_button():
    params = _analysis_params()
    choice = surrogate_choice()
    problem = choice_problem(choice, AnalysisConfig.from_params(params))
    if problem:
        messagebox.showwarning("Can't run the surrogate analysis", problem)
        return
    input_dir = state.val_random_pair_input_folder.get()
    seed_input = state.val_rp_seed_input.get()
    seed = int(seed_input) if seed_input else random.randrange(MAX_RANDOM_SEED)
    settings = surrogate_settings(params, choice, input_dir)
    _start_job(
        "Surrogate analysis",
        lambda progress: run_surrogate_analysis(params, choice, input_dir, seed, progress),
        lambda summary: _surrogate_run_finished(summary, settings, params, input_dir),
    )


def _surrogate_run_finished(summary, settings, params, input_dir):
    """Keeps the result for the Surrogates tab's plot and export, shows it there, and says what was found."""
    state.dat_surrogate_run.update(result=summary['result'], settings=settings, params=params, folder=input_dir,
                                   stale=False)
    _update_surrogate_result_text()
    _update_surrogate_staleness()       # settings changed during the run make it out of date at once
    if state.val_CURRENT_TAB.get() == SURROGATES_TAB:
        state.PARAMS_CHANGED()
    _show_surrogate_summary(summary)


def _export_surrogates(kind, extension, file_type, write):
    """Asks where to save the last result and writes it there with write(file_path, run)."""
    run = state.dat_surrogate_run
    if run['result'] is None:
        return
    file_path = filedialog.asksaveasfilename(
        title="Save As",
        defaultextension=extension,
        initialfile=f"biosync_surrogates_{os.path.basename(run['folder'])}",
        filetypes=((f"{file_type} files", f"*{extension}"),)
    )
    if not file_path:
        return
    try:
        _while_exporting(kind, lambda: write(file_path, run))
    except Exception as e:
        messagebox.showerror("Export failed", str(e))


def export_surrogate_data():
    """Writes the last result as xlsx, with the settings it was run with."""
    _export_surrogates("surrogate data", ".xlsx", "XLSX",
                       lambda path, run: export_surrogate_result(path, run['params'], run['folder'], run['result']))


def export_surrogate_plot():
    """Saves the figure of the last result as PNG."""
    _export_surrogates("surrogate plot", ".png", "PNG", lambda path, run: export_surrogate_figure(path, run['result']))
