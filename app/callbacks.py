import os
import queue
import random
import threading
from tkinter import filedialog, messagebox

import xlsx
import utils
from analysis import preprocess_signals, signal_dfa
from signal_processing import guess_is_event_based
from batch_processing import batch_process, find_result_files, random_pair_analysis, remove_result_files
from export import export_sxcorr_data, export_wxcorr_data, export_random_pair_data

import corr_plot
import state
import validation

# ---------------------------------------------------------------------------
# LATE-REGISTERED WIDGET REFERENCES
# (populated by app_layout.build_layout after widgets are created)
# ---------------------------------------------------------------------------
PREVIEW_TAB = "Input Data"

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
    # only the Input Data tab has its own plot, the others share one
    if PREVIEW_TAB not in (previous_tab, selected_tab):
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

def on_min_lag_input_change(name, index, mode):
    new_str_val = state.val_lag_filter_min_input.get()
    if new_str_val not in ('', '-'):
        state.val_lag_filter_min.set(int(new_str_val))
    validation.check_wx_correlation_settings()
    state.PARAMS_CHANGED(debounce=True)


def on_max_lag_filter_input_change(name, index, mode):
    new_str_val = state.val_lag_filter_max_input.get()
    if new_str_val not in ('', '-'):
        state.val_lag_filter_max.set(int(new_str_val))
    validation.check_wx_correlation_settings()
    state.PARAMS_CHANGED(debounce=True)


def on_max_lag_change_update_filter(*args):
    new_max_lag = state.val_max_lag.get()
    state.val_lag_filter_min.set(-new_max_lag)
    state.val_lag_filter_max.set(new_max_lag)
    state.val_lag_filter_min_input.set(str(-new_max_lag))
    state.val_lag_filter_max_input.set(str(new_max_lag))
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
# RANDOM PAIR N INPUT
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

    # batch ready state
    state.val_INPUT_DATA_VALID.trace_add('write', _batch_processing_is_ready)
    state.val_CORRELATION_SETTINGS_VALID.trace_add('write', _batch_processing_is_ready)
    state.val_CORRELATION_SETTINGS_VALID_SXC.trace_add('write', _batch_processing_is_ready)
    state.val_checkbox_windowed_xcorr.trace_add('write', _batch_processing_is_ready)
    state.val_batch_input_folder.trace_add('write', _batch_processing_is_ready)
    state.val_batch_output_folder.trace_add('write', _batch_processing_is_ready)

    # random pair ready state
    state.val_INPUT_DATA_VALID.trace_add('write', _random_pair_is_ready)
    state.val_CORRELATION_SETTINGS_VALID.trace_add('write', _random_pair_is_ready)
    state.val_CORRELATION_SETTINGS_VALID_SXC.trace_add('write', _random_pair_is_ready)
    state.val_checkbox_windowed_xcorr.trace_add('write', _random_pair_is_ready)
    state.val_random_pair_input_folder.trace_add('write', _random_pair_is_ready)
    state.val_random_pair_output_file.trace_add('write', _random_pair_is_ready)


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
    is_event_based = guess_is_event_based(raw_a, raw_b)
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


def open_random_pair_output_file_picker():
    file_path = filedialog.asksaveasfilename(
        title="Save As",
        defaultextension=".xlsx",
        filetypes=(("XLSX files", "*.xlsx"),)
    )
    if not file_path:
        return
    state.val_random_pair_output_file.set(file_path)


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


def export_data():
    corr_plot.flush_update()  # results must match settings typed just before clicking
    selected_dir   = state.val_selected_dyad_dir.get()
    filename_init  = f"wx_data_{os.path.basename(selected_dir)}" if selected_dir else "wx_data"
    file_path = filedialog.asksaveasfilename(
        title="Save As",
        defaultextension=".xlsx",
        initialfile=filename_init,
        filetypes=(("XLSX files", "*.xlsx"),)
    )
    if not file_path:
        return
    try:
        if state.val_checkbox_windowed_xcorr.get():
            _export_wxcorr_data(file_path)
        else:
            _export_sxcorr_data(file_path)
    except Exception as e:
        messagebox.showerror("Export failed", str(e))


def export_plot():
    corr_plot.flush_update()
    fig = state.dat_plot_data["fig"]
    if not fig:
        return
    selected_dir  = state.val_selected_dyad_dir.get()
    filename_init = f"wx_plot_{os.path.basename(selected_dir)}" if selected_dir else "wx_plot"
    file_path = filedialog.asksaveasfilename(
        title="Save As",
        defaultextension=".png",
        initialfile=filename_init,
        filetypes=(("PNG files", "*.png"),)
    )
    if not file_path:
        return
    fig.savefig(file_path, dpi=300, format='png')


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
    _random_pair_is_ready()
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
        _random_pair_is_ready()
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
# RANDOM PAIR ANALYSIS
# ---------------------------------------------------------------------------

MAX_RANDOM_SEED = 2**32


def _random_pair_is_ready(*args):
    data_is_valid = (
        state.val_INPUT_DATA_VALID.get() and validation.check_active_settings_valid() and
        not state.val_job_running.get()
    )
    io_is_ready = (
        state.val_random_pair_input_folder.get() != '' and
        state.val_random_pair_output_file.get() != ''
    )
    state.val_random_pair_is_ready.set(data_is_valid and io_is_ready)


def run_random_pair(params, random_pair_count, input_dir, output_file, seed, progress):
    (t_stat, p_value, avg_corr_rp, avg_corr_real, avg_wxcorr_real, avg_wxcorr_rp, failures, n_eligible_pairs,
     window_counts_real, window_counts_rp) = random_pair_analysis(
        params=params,
        random_pair_count=random_pair_count,
        input_dir=input_dir,
        progress=progress,
        seed=seed,
    )
    progress(1, 1, "Writing results")
    export_random_pair_data(
        file_path=output_file,
        params=params,
        input_dir=input_dir,
        t_stat=t_stat,
        p_value=p_value,
        avg_corr_rp=avg_corr_rp,
        avg_corr_real=avg_corr_real,
        avg_wxcorr_real=avg_wxcorr_real,
        avg_wxcorr_rp=avg_wxcorr_rp,
        seed=seed,
        n_eligible_pairs=n_eligible_pairs,
        n_random_pairs_requested=random_pair_count,
        window_counts_real=window_counts_real,
        window_counts_rp=window_counts_rp,
    )
    return {
        'failures': failures,
        'p_value': p_value,
        'random_pairs_requested': random_pair_count,
        'random_pairs_used': len(avg_corr_rp),
        'real_dyads_used': len(avg_corr_real),
    }


MIN_GROUP_SIZE = 2  # the t-test needs at least two values per group


def _random_pair_problems(summary):
    """Reasons not to trust the result, as sentences. Empty if there are none."""
    problems = []
    if summary['random_pairs_used'] < MIN_GROUP_SIZE or summary['real_dyads_used'] < MIN_GROUP_SIZE:
        problems.append(
            f"The t-test needs at least {MIN_GROUP_SIZE} random pairs and {MIN_GROUP_SIZE} real dyads, "
            f"and got {summary['random_pairs_used']} and {summary['real_dyads_used']}."
        )
    elif summary['p_value'] != summary['p_value']:   # NaN
        problems.append("The t-test gave no p-value, for example because all values were the same.")
    skipped = summary['random_pairs_requested'] - summary['random_pairs_used']
    if skipped:
        problems.append(f"{skipped} of {summary['random_pairs_requested']} random pairs were skipped, so the result rests on fewer.")
    return problems


def _show_random_pair_summary(summary):
    failures = summary['failures']
    problems = _random_pair_problems(summary)
    lines = [f"Finished, {len(failures)} pairs or dyads skipped."]
    if problems:
        lines += [""] + problems
    if failures:
        lines += ["", "Skipped:"] + _format_failures(failures)
    if problems:
        messagebox.showwarning("Random pair analysis finished with problems", "\n".join(lines))
    else:
        messagebox.showinfo("Random pair analysis finished", "\n".join(lines))


def handle_run_random_pair_button():
    params = _analysis_params()
    random_pair_count = state.val_rp_n.get()
    if random_pair_count < MIN_GROUP_SIZE:
        messagebox.showwarning("Too few random pairs", f"N must be at least {MIN_GROUP_SIZE} for the t-test.")
        return
    input_dir = state.val_random_pair_input_folder.get()
    output_file = state.val_random_pair_output_file.get()
    seed_input = state.val_rp_seed_input.get()
    seed = int(seed_input) if seed_input else random.randrange(MAX_RANDOM_SEED)
    _start_job(
        "Random pair analysis",
        lambda progress: run_random_pair(params, random_pair_count, input_dir, output_file, seed, progress),
        _show_random_pair_summary,
    )
