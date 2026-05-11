import os
from tkinter import filedialog

import xlsx
import utils
from signal_processing import preprocess_dyad
from batch_processing import batch_process, random_pair_analysis
from export import export_sxcorr_data, export_wxcorr_data, export_random_pair_data
from plot import plot_init

import state
import validation

# ---------------------------------------------------------------------------
# LATE-REGISTERED WIDGET REFERENCES
# (populated by app_layout.build_layout after widgets are created)
# ---------------------------------------------------------------------------
_dropdowns = {}   # keys: 'sheet', 'col_a', 'col_b'
_tabview   = {}   # key: 'tabview'


def register_dropdowns(sheet_dd, col_a_dd, col_b_dd):
    _dropdowns['sheet'] = sheet_dd
    _dropdowns['col_a'] = col_a_dd
    _dropdowns['col_b'] = col_b_dd


def register_tabview(tabview):
    _tabview['tabview'] = tabview


# ---------------------------------------------------------------------------
# GUI STATE CALLBACKS
# ---------------------------------------------------------------------------

def on_tab_change():
    selected_tab = _tabview['tabview'].get()
    state.val_CURRENT_TAB.set(selected_tab)
    state.PARAMS_CHANGED()


# ---------------------------------------------------------------------------
# ENTRY CALLBACKS — windowed xcorr
# ---------------------------------------------------------------------------

def on_window_size_input_change(name, index, mode):
    new_str_val = state.val_window_size_input.get()
    state.val_window_size.set(0 if new_str_val == '' else int(new_str_val))
    validation.check_wx_correlation_settings()


def on_step_size_input_change(name, index, mode):
    new_str_val = state.val_step_size_input.get()
    state.val_step_size.set(0 if new_str_val == '' else int(new_str_val))
    validation.check_wx_correlation_settings()


def on_max_lag_input_change(name, index, mode):
    new_str_val = state.val_max_lag_input.get()
    state.val_max_lag.set(0 if new_str_val == '' else int(new_str_val))
    validation.check_wx_correlation_settings()


# ENTRY CALLBACKS — standard xcorr

def on_max_lag_input_change_sxc(name, index, mode):
    new_str_val = state.val_max_lag_input_sxc.get()
    state.val_max_lag_sxc.set(0 if new_str_val == '' else int(new_str_val))
    validation.check_sx_correlation_settings()


# ENTRY CALLBACKS — lag filter

def on_min_lag_input_change(name, index, mode):
    new_str_val = state.val_lag_filter_min_input.get()
    if new_str_val == '' or new_str_val == '-':
        state.val_lag_filter_min.set(0)
        state.val_lag_filter_min_input.set(0)
    else:
        state.val_lag_filter_min.set(int(new_str_val))
    validation.check_wx_correlation_settings()


def on_max_lag_filter_input_change(name, index, mode):
    new_str_val = state.val_lag_filter_max_input.get()
    if new_str_val == '':
        state.val_lag_filter_max.set(0)
        state.val_lag_filter_max_input.set(0)
    else:
        state.val_lag_filter_max.set(int(new_str_val))
    validation.check_wx_correlation_settings()


def on_max_lag_change_update_filter(*args):
    new_max_lag = state.val_max_lag.get()
    state.val_lag_filter_min.set(-new_max_lag)
    state.val_lag_filter_max.set(new_max_lag)
    state.val_lag_filter_min_input.set(str(-new_max_lag))
    state.val_lag_filter_max_input.set(str(new_max_lag))
    validation.check_wx_correlation_settings()


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


# ---------------------------------------------------------------------------
# DROPDOWN CALLBACKS
# ---------------------------------------------------------------------------

def on_dropdown_select_sheet_change(value):
    update_column_names()
    preprocess_data()
    clear_correlation_data()
    state.PARAMS_CHANGED()


def on_dropdown_select_column_a_change(value):
    preprocess_data()
    clear_correlation_data()
    state.PARAMS_CHANGED()


def on_dropdown_select_column_b_change(value):
    preprocess_data()
    clear_correlation_data()
    state.PARAMS_CHANGED()


def on_change_data_has_headers(*args):
    state.dat_workbook_data["has_headers"] = state.val_checkbox_data_has_headers.get()
    update_column_names()
    preprocess_data()
    clear_correlation_data()
    state.PARAMS_CHANGED()


# ---------------------------------------------------------------------------
# DROPDOWN UPDATE UTILITY
# ---------------------------------------------------------------------------

def update_dropdown_options(dropdown, dropdown_state_var, new_options):
    dropdown.configure(values=new_options)
    dropdown_state_var.set(new_options[0])


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
    state.val_batch_input_folder.trace_add('write', _batch_processing_is_ready)
    state.val_batch_output_folder.trace_add('write', _batch_processing_is_ready)

    # random pair ready state
    state.val_INPUT_DATA_VALID.trace_add('write', _random_pair_is_ready)
    state.val_CORRELATION_SETTINGS_VALID.trace_add('write', _random_pair_is_ready)
    state.val_CORRELATION_SETTINGS_VALID_SXC.trace_add('write', _random_pair_is_ready)
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
    if not wb_a or not wb_b:
        return
    names_a = xlsx.get_sheet_names(wb_a)
    names_b = xlsx.get_sheet_names(wb_b)
    state.dat_workbook_data["sheet_names"] = list(set(names_a) & set(names_b))
    update_dropdown_options(
        _dropdowns['sheet'],
        state.val_selected_sheet,
        state.dat_workbook_data["sheet_names"]
    )


def update_column_names():
    if not state.val_selected_sheet.get() or state.val_selected_sheet.get() == '- None -':
        return
    wb_a    = state.dat_workbook_data["workbook_a"]
    wb_b    = state.dat_workbook_data["workbook_b"]
    sheet   = state.val_selected_sheet.get()
    headers = state.dat_workbook_data["has_headers"]

    state.dat_workbook_data["column_names_a"] = list(xlsx.get_columns(wb_a, sheet, headers=headers).keys())
    state.dat_workbook_data["column_names_b"] = list(xlsx.get_columns(wb_b, sheet, headers=headers).keys())

    update_dropdown_options(_dropdowns['col_a'], state.val_selected_column_a, state.dat_workbook_data["column_names_a"])
    update_dropdown_options(_dropdowns['col_b'], state.val_selected_column_b, state.dat_workbook_data["column_names_b"])

    state.dat_workbook_data["selected_column_a"] = state.dat_workbook_data["column_names_a"][0]
    state.dat_workbook_data["selected_column_b"] = state.dat_workbook_data["column_names_b"][0]

    state.dat_workbook_data["columns_a"] = xlsx.get_columns(wb_a, sheet, headers=headers)
    state.dat_workbook_data["columns_b"] = xlsx.get_columns(wb_b, sheet, headers=headers)


# ---------------------------------------------------------------------------
# DATA PRE-PROCESSING
# ---------------------------------------------------------------------------

def preprocess_data():
    d = state.dat_physiological_data

    if not state.val_selected_sheet.get() or state.val_selected_sheet.get() == '- None -':
        state.val_INPUT_DATA_VALID.set(False)
        return
    if not state.val_selected_column_a.get() or state.val_selected_column_a.get() == '- None -':
        state.val_INPUT_DATA_VALID.set(False)
        return
    if not state.val_selected_column_b.get() or state.val_selected_column_b.get() == '- None -':
        state.val_INPUT_DATA_VALID.set(False)
        return

    d["raw_signal_a"] = state.dat_workbook_data["columns_a"][state.val_selected_column_a.get()]
    d["raw_signal_b"] = state.dat_workbook_data["columns_b"][state.val_selected_column_b.get()]

    if not (utils.is_numeric_array(d["raw_signal_a"]) and utils.is_numeric_array(d["raw_signal_b"])):
        state.val_INPUT_DATA_VALID.set(False)
        return

    try:
        signal_a, signal_b, signal_a_std, signal_b_std = preprocess_dyad(
            d["raw_signal_a"],
            d["raw_signal_b"],
            signal_type='event-based' if state.val_checkbox_eb.get() else 'fixed-rate'
        )
        d["signal_a"]     = signal_a
        d["signal_b"]     = signal_b
        d["signal_a_std"] = signal_a_std
        d["signal_b_std"] = signal_b_std
        state.val_data_length.set(len(signal_a))
        state.val_INPUT_DATA_VALID.set(True)

    except Exception as e:
        print(f"Data is invalid [{e}]")
        d["signal_a"]     = []
        d["signal_b"]     = []
        d["signal_a_std"] = []
        d["signal_b_std"] = []
        d["raw_signal_a"] = []
        d["raw_signal_b"] = []
        state.dat_plot_data['fig'] = plot_init(
            dpi=state.screen_dpi,
            screen_width=state.screen_width,
            screen_height=state.screen_height,
            is_retina=state.RETINA
        )
        state.val_INPUT_DATA_VALID.set(False)


def clear_correlation_data():
    state.dat_correlation_data["wxcorr"] = []
    state.dat_correlation_data["sxcorr"] = []


# ---------------------------------------------------------------------------
# MAIN DATA LOADING ROUTINE
# ---------------------------------------------------------------------------

def load_xlsx_data():
    read_xlsx_files()
    update_sheet_names()
    update_column_names()
    preprocess_data()
    clear_correlation_data()


# ---------------------------------------------------------------------------
# FILE PICKERS
# ---------------------------------------------------------------------------

def open_dir_picker():
    dir_path = filedialog.askdirectory(title="Select a directory")
    if not dir_path:
        return
    state.val_selected_dyad_dir.set(dir_path)
    xlsx_files = [f for f in os.listdir(dir_path) if f.endswith('.xlsx')]
    if len(xlsx_files) < 2:
        return
    state.val_selected_file_a.set(os.path.join(dir_path, xlsx_files[0]))
    state.val_selected_file_b.set(os.path.join(dir_path, xlsx_files[1]))
    load_xlsx_data()
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
        'checkbox_EDA':                   state.val_checkbox_fr.get(),
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
        'dfa_alpha_window_averages_wxcorr': state.dat_correlation_data['dfa_alpha_window_averages_wxcorr'],
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
        'dfa_alpha':              state.dat_correlation_data['dfa_alpha_sxcorr'],
    }
    export_sxcorr_data(file_path, params)


def export_data():
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
    if state.val_checkbox_windowed_xcorr.get():
        _export_wxcorr_data(file_path)
    else:
        _export_sxcorr_data(file_path)


def export_plot():
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
# BATCH PROCESSING
# ---------------------------------------------------------------------------

def _batch_processing_is_ready(*args):
    data_is_valid = (
        state.val_INPUT_DATA_VALID.get() and
        state.val_CORRELATION_SETTINGS_VALID.get() and
        state.val_CORRELATION_SETTINGS_VALID_SXC.get()
    )
    io_is_ready = (
        state.val_batch_input_folder.get() != '' and
        state.val_batch_output_folder.get() != ''
    )
    state.val_batch_processing_is_ready.set(data_is_valid and io_is_ready)


def run_batch_process():
    params = {
        'batch_input_folder':         state.val_batch_input_folder.get(),
        'output_dir':                 state.val_batch_output_folder.get(),
        'selected_sheet':             state.val_selected_sheet.get(),
        'workbook_data':              state.dat_workbook_data,
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
    batch_process(params)


def handle_run_batch_button():
    state.val_batch_processing_is_ready.set(False)
    run_batch_process()
    state.val_batch_processing_is_ready.set(True)


# ---------------------------------------------------------------------------
# RANDOM PAIR ANALYSIS
# ---------------------------------------------------------------------------

def _random_pair_is_ready(*args):
    data_is_valid = (
        state.val_INPUT_DATA_VALID.get() and
        state.val_CORRELATION_SETTINGS_VALID.get() and
        state.val_CORRELATION_SETTINGS_VALID_SXC.get()
    )
    io_is_ready = (
        state.val_random_pair_input_folder.get() != '' and
        state.val_random_pair_output_file.get() != ''
    )
    state.val_random_pair_is_ready.set(data_is_valid and io_is_ready)


def run_random_pair():
    params = {
        'batch_input_folder':         state.val_batch_input_folder.get(),
        'output_dir':                 state.val_batch_output_folder.get(),
        'selected_sheet':             state.val_selected_sheet.get(),
        'workbook_data':              state.dat_workbook_data,
        'checkbox_windowed_xcorr':    state.val_checkbox_windowed_xcorr.get(),
        'window_size':                state.val_window_size.get(),
        'step_size':                  state.val_step_size.get(),
        'max_lag':                    state.val_max_lag.get(),
        'max_lag_sxc':                state.val_max_lag_sxc.get(),
        'checkbox_absolute_corr':     state.val_checkbox_absolute_corr.get(),
        'sigmoid_correlations':       state.val_checkbox_show_sigmoid_correlations.get(),
        'checkbox_absolute_corr_sxc': state.val_checkbox_absolute_corr_sxc.get(),
        'checkbox_average_windows':   state.val_checkbox_average_windows.get(),
        'checkbox_eb':                state.val_checkbox_eb.get(),
        'checkbox_fr':                state.val_checkbox_fr.get(),
        'standardised_signals':       state.val_checkbox_standardise.get(),
        'use_lag_filter':             state.val_checkbox_lag_filter.get(),
        'lag_filter_min':             state.val_lag_filter_min.get(),
        'lag_filter_max':             state.val_lag_filter_max.get(),
    }
    t_stat, p_value, avg_corr_rp, avg_corr_real, avg_wxcorr_real, avg_wxcorr_rp = random_pair_analysis(
        params=params,
        random_pair_count=state.val_rp_n.get(),
        input_dir=state.val_random_pair_input_folder.get(),
    )
    export_random_pair_data(
        file_path=state.val_random_pair_output_file.get(),
        params=params,
        input_dir=state.val_random_pair_input_folder.get(),
        t_stat=t_stat,
        p_value=p_value,
        avg_corr_rp=avg_corr_rp,
        avg_corr_real=avg_corr_real,
        avg_wxcorr_real=avg_wxcorr_real,
        avg_wxcorr_rp=avg_wxcorr_rp,
    )


def handle_run_random_pair_button():
    state.val_random_pair_is_ready.set(False)
    run_random_pair()
    state.val_random_pair_is_ready.set(True)
