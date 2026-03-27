import os
import utils
import state
import validation

# ---------------------------------------------------------------------------
# LATE-REGISTERED WIDGET REFERENCES
# (populated by app.py via register_widgets after build_layout returns)
# ---------------------------------------------------------------------------
_w = {}


def register_widgets(widget_dict):
    _w.update(widget_dict)


# ---------------------------------------------------------------------------
# TRACE SETUP
# All reactive bindings between state vars and widget appearance live here.
# Call setup_traces() once, after register_widgets().
# ---------------------------------------------------------------------------

def setup_traces():
    state.val_selected_dyad_dir.trace_add('write', update_dir_picker_label)
    state.val_selected_file_a.trace_add('write', update_dir_picker_label)
    state.val_selected_file_b.trace_add('write', update_dir_picker_label)

    state.val_selected_file_a.trace_add('write', update_select_column_a_label)
    state.val_selected_file_b.trace_add('write', update_select_column_b_label)

    state.val_selected_sheet.trace_add('write', update_input_data_validation_error)
    state.val_INPUT_DATA_VALID.trace_add('write', update_input_data_validation_error)

    state.val_WINDOW_SIZE_VALID.trace_add('write', update_window_size_entry_on_validation)
    state.val_MAX_LAG_VALID.trace_add('write', update_max_lag_entry_on_validation)
    state.val_STEP_SIZE_VALID.trace_add('write', update_step_size_entry_on_validation)

    state.val_checkbox_lag_filter.trace_add('write', update_lag_filter_visibility)
    state.val_LAG_FILTER_VALID.trace_add('write', update_lag_filter_entries_on_validation)

    state.val_MAX_LAG_VALID_SXC.trace_add('write', update_max_lag_entry_on_validation_sxc)

    state.val_CORRELATION_SETTINGS_VALID.trace_add('write', update_active_state_export_button)

    state.val_checkbox_windowed_xcorr.trace_add('write', update_xcorr_parameter_groups)

    state.val_batch_input_folder.trace_add(
        'write',
        lambda *a: _w['label_batch_input_folder'].configure(
            text=f"Selected: {os.path.basename(state.val_batch_input_folder.get())}"
        )
    )
    state.val_batch_output_folder.trace_add(
        'write',
        lambda *a: _w['label_output_dir'].configure(
            text=f"Selected: {os.path.basename(state.val_batch_output_folder.get())}"
        )
    )
    state.val_batch_input_folder.trace_add('write', update_batch_input_num_subdirs)

    state.val_batch_processing_is_ready.trace_add('write', update_active_state_run_batch_button)

    state.val_random_pair_input_folder.trace_add(
        'write',
        lambda *a: _w['label_random_pair_input_folder'].configure(
            text=(
                f"Selected: {os.path.basename(state.val_random_pair_input_folder.get())}"
                if state.val_random_pair_input_folder.get()
                else "No folder selected."
            )
        )
    )
    state.val_random_pair_output_file.trace_add(
        'write',
        lambda *a: _w['label_random_pair_output_file'].configure(
            text=(
                f"Selected: {os.path.basename(state.val_random_pair_output_file.get())}"
                if state.val_random_pair_output_file.get()
                else "No file selected."
            )
        )
    )
    state.val_random_pair_is_ready.trace_add('write', update_active_state_random_pair_button)


# ---------------------------------------------------------------------------
# UPDATE FUNCTIONS — input data section
# ---------------------------------------------------------------------------

def update_dir_picker_label(*args):
    dir_path = state.val_selected_dyad_dir.get()
    _w['label_dir_picker'].configure(
        text='No folder selected.' if dir_path == '' else f"Selected: {os.path.basename(dir_path)}"
    )


def update_select_column_a_label(*args):
    file_a = state.val_selected_file_a.get()
    _w['label_select_column_a'].configure(
        text="Select Column" if not file_a else f"Select Column for {os.path.basename(file_a)}"
    )


def update_select_column_b_label(*args):
    file_b = state.val_selected_file_b.get()
    _w['label_select_column_b'].configure(
        text="Select Column" if not file_b else f"Select Column for {os.path.basename(file_b)}"
    )


def update_input_data_validation_error(*args):
    input_data_is_valid = (
        state.val_selected_sheet.get() == '- None -' or
        state.val_INPUT_DATA_VALID.get()
    )
    if input_data_is_valid:
        _w['error_label_input_data'].grid_forget()
    else:
        _w['error_label_input_data'].grid(row=10, column=0, columnspan=2, sticky="w", padx=10, pady=0)


# ---------------------------------------------------------------------------
# UPDATE FUNCTIONS — windowed xcorr entry validation
# ---------------------------------------------------------------------------

def update_window_size_entry_on_validation(*args):
    if state.val_WINDOW_SIZE_VALID.get():
        _w['entry_window_size'].configure(border_color='#777777')
        _w['error_label_window_size'].grid_forget()
    else:
        _w['entry_window_size'].configure(border_color='red')
        _w['error_label_window_size'].grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=0)


def update_max_lag_entry_on_validation(*args):
    if state.val_MAX_LAG_VALID.get():
        _w['entry_max_lag'].configure(border_color='#777777')
        _w['error_label_max_lag'].grid_forget()
    else:
        _w['entry_max_lag'].configure(border_color='red')
        _w['error_label_max_lag'].grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=0)


def update_step_size_entry_on_validation(*args):
    if state.val_STEP_SIZE_VALID.get():
        _w['entry_step_size'].configure(border_color='#777777')
        _w['error_label_step_size'].grid_forget()
    else:
        _w['entry_step_size'].configure(border_color='red')
        _w['error_label_step_size'].grid(row=6, column=0, columnspan=2, sticky="w", padx=10, pady=0)


def update_lag_filter_visibility(*args):
    if state.val_checkbox_lag_filter.get():
        _w['entry_lag_filter_min'].grid(row=10, column=0, sticky="w", padx=10, pady=5)
        _w['entry_lag_filter_max'].grid(row=10, column=1, sticky="w", padx=10, pady=5)
    else:
        _w['entry_lag_filter_min'].grid_forget()
        _w['entry_lag_filter_max'].grid_forget()
        _w['error_label_lag_filter'].grid_forget()


def update_lag_filter_entries_on_validation(*args):
    if state.val_LAG_FILTER_VALID.get():
        _w['entry_lag_filter_min'].configure(border_color='#777777')
        _w['entry_lag_filter_max'].configure(border_color='#777777')
        _w['error_label_lag_filter'].grid_forget()
        return
    _w['entry_lag_filter_min'].configure(border_color='#777777')
    _w['entry_lag_filter_max'].configure(border_color='#777777')
    lf_sorted   = validation.check_lag_filter_sorted()
    lf_in_range = validation.check_lag_filter_in_range()
    if not lf_sorted or not lf_in_range:
        msg = (
            f"Filter limits must be "
            f"{'sorted' if not lf_sorted else ''}"
            f"{' and ' if not lf_sorted and not lf_in_range else ''}"
            f"{'in [-max_lag, max_lag]' if not lf_in_range else ''}"
        )
        _w['error_label_lag_filter'].configure(text=msg, text_color='red')
        _w['error_label_lag_filter'].grid(row=11, column=0, sticky="w", padx=10, pady=5)


# ---------------------------------------------------------------------------
# UPDATE FUNCTIONS — standard xcorr entry validation
# ---------------------------------------------------------------------------

def update_max_lag_entry_on_validation_sxc(*args):
    if state.val_MAX_LAG_VALID_SXC.get():
        _w['entry_max_lag_sxc'].configure(border_color='#777777')
        _w['error_label_max_lag_sxc'].grid_forget()
    else:
        _w['entry_max_lag_sxc'].configure(border_color='red')
        _w['error_label_max_lag_sxc'].grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=0)


# ---------------------------------------------------------------------------
# UPDATE FUNCTIONS — export & batch
# ---------------------------------------------------------------------------

def update_active_state_export_button(*args):
    state_str = "normal" if state.val_CORRELATION_SETTINGS_VALID.get() else "disabled"
    _w['button_export_data'].configure(state=state_str)
    _w['button_export_plot'].configure(state=state_str)


def update_xcorr_parameter_groups(*args):
    if state.val_checkbox_windowed_xcorr.get():
        _w['subgroup_windowed_xcorr_parameters'].grid(
            row=2, column=0, sticky='ew', columnspan=2, padx=0, pady=0
        )
        _w['subgroup_standard_xcorr_parameters'].grid_forget()
        _w['subgroup_lag_hint'].grid(row=2, column=0, sticky='ew', columnspan=2, padx=0, pady=0)
        _w['subgroup_lag_info'].grid_forget()
        _w['subgroup_visualisation'].grid(row=1, column=0, sticky='ew', columnspan=2, padx=0, pady=0)
    else:
        _w['subgroup_windowed_xcorr_parameters'].grid_forget()
        _w['subgroup_standard_xcorr_parameters'].grid(
            row=2, column=0, sticky='ew', columnspan=2, padx=0, pady=0
        )
        _w['subgroup_lag_hint'].grid_forget()
        _w['subgroup_lag_info'].grid(row=2, column=0, sticky='ew', columnspan=2, padx=0, pady=0)
        _w['subgroup_visualisation'].grid_forget()


def update_batch_input_num_subdirs(*args):
    input_folder = state.val_batch_input_folder.get()
    if input_folder:
        _w['label_batch_input_num_subdirs'].configure(
            text=f"{utils.count_subdirectories(input_folder)} sub-folders / dyads"
        )
        _w['label_batch_input_num_subdirs'].grid(row=4, column=0, padx=10, sticky='w')
    else:
        _w['label_batch_input_num_subdirs'].grid_forget()


def update_active_state_run_batch_button(*args):
    _w['button_batch'].configure(
        state="normal" if state.val_batch_processing_is_ready.get() else "disabled"
    )


def update_active_state_random_pair_button(*args):
    _w['button_random_pair'].configure(
        state="normal" if state.val_random_pair_is_ready.get() else "disabled"
    )
