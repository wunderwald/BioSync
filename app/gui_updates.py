import os
import utils
import state
import validation
from signal_processing import EVENT_BASED_SAMPLING_RATE_HZ

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

    state.val_input_error.trace_add('write', update_input_data_validation_error)

    state.val_WINDOW_SIZE_VALID.trace_add('write', update_window_size_entry_on_validation)
    state.val_MAX_LAG_VALID.trace_add('write', update_max_lag_entry_on_validation)
    state.val_STEP_SIZE_VALID.trace_add('write', update_step_size_entry_on_validation)

    state.val_checkbox_lag_filter.trace_add('write', update_lag_filter_visibility)

    for var in (
        state.val_window_size, state.val_step_size, state.val_max_lag, state.val_max_lag_sxc,
        state.val_lag_filter_min, state.val_lag_filter_max, state.val_checkbox_eb,
    ):
        var.trace_add('write', update_parameter_labels)
    update_parameter_labels()

    state.val_LAG_FILTER_VALID.trace_add('write', update_lag_filter_entries_on_validation)

    state.val_MAX_LAG_VALID_SXC.trace_add('write', update_max_lag_entry_on_validation_sxc)

    state.val_INPUT_DATA_VALID.trace_add('write', update_active_state_export_button)
    state.val_CORRELATION_SETTINGS_VALID.trace_add('write', update_active_state_export_button)
    state.val_CORRELATION_SETTINGS_VALID_SXC.trace_add('write', update_active_state_export_button)
    state.val_checkbox_windowed_xcorr.trace_add('write', update_active_state_export_button)
    state.val_exporting.trace_add('write', update_export_busy)
    update_active_state_export_button()

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

    state.val_job_running.trace_add('write', update_job_progress_visibility)
    state.val_job_progress.trace_add('write', update_job_progress_bar)
    state.val_job_cancel_requested.trace_add('write', update_active_state_cancel_button)


# ---------------------------------------------------------------------------
# UPDATE FUNCTIONS — input data section
# ---------------------------------------------------------------------------

def update_dir_picker_label(*args):
    dir_path = state.val_selected_dyad_dir.get()
    _w['label_dir_picker'].configure(
        text='No folder selected.' if dir_path == '' else f"Selected: {os.path.basename(dir_path)}"
    )


INVALID_DROPDOWN_COLORS = {'fg_color': '#b03a2e', 'button_color': '#922b21', 'button_hover_color': '#7b241c'}
_normal_dropdown_colors = {}


def _set_dropdowns_invalid(invalid):
    for key in ('dropdown_select_sheet', 'dropdown_select_column'):
        dropdown = _w[key]
        if key not in _normal_dropdown_colors:
            _normal_dropdown_colors[key] = {name: dropdown.cget(name) for name in INVALID_DROPDOWN_COLORS}
        dropdown.configure(**(INVALID_DROPDOWN_COLORS if invalid else _normal_dropdown_colors[key]))


def update_input_data_validation_error(*args):
    reason = state.val_input_error.get()
    _set_dropdowns_invalid(bool(reason))
    if reason:
        _w['error_label_input_data'].configure(text=f"Data is invalid: {reason}")
        _w['error_label_input_data'].grid(row=10, column=0, columnspan=2, sticky="w", padx=10, pady=0)
    else:
        _w['error_label_input_data'].grid_forget()


# ---------------------------------------------------------------------------
# UPDATE FUNCTIONS — windowed xcorr entry validation
# ---------------------------------------------------------------------------

def update_window_size_entry_on_validation(*args):
    if state.val_WINDOW_SIZE_VALID.get():
        _w['entry_window_size'].configure(border_color='#777777')
        _w['error_label_window_size'].grid_forget()
    else:
        _w['entry_window_size'].configure(border_color='red')
        _w['error_label_window_size'].grid(row=2, column=0, columnspan=4, sticky="w", padx=10, pady=0)


def update_max_lag_entry_on_validation(*args):
    if state.val_MAX_LAG_VALID.get():
        _w['entry_max_lag'].configure(border_color='#777777')
        _w['error_label_max_lag'].grid_forget()
    else:
        _w['entry_max_lag'].configure(border_color='red')
        _w['error_label_max_lag'].grid(row=4, column=0, columnspan=4, sticky="w", padx=10, pady=0)


def update_step_size_entry_on_validation(*args):
    if state.val_STEP_SIZE_VALID.get():
        _w['entry_step_size'].configure(border_color='#777777')
        _w['error_label_step_size'].grid_forget()
    else:
        _w['entry_step_size'].configure(border_color='red')
        _w['error_label_step_size'].grid(row=6, column=0, columnspan=4, sticky="w", padx=10, pady=0)


def _seconds_text(samples):
    """Fixed-rate data can have any sampling rate, so only event-based data can be shown in seconds."""
    if not state.val_checkbox_eb.get():
        return ''
    return f"{samples / EVENT_BASED_SAMPLING_RATE_HZ:g} s"


def update_parameter_labels(*args):
    for label, var in (
        ('label_window_size_seconds', state.val_window_size),
        ('label_step_size_seconds', state.val_step_size),
        ('label_max_lag_seconds', state.val_max_lag),
        ('label_max_lag_sxc_seconds', state.val_max_lag_sxc),
        ('label_lag_filter_min_seconds', state.val_lag_filter_min),
        ('label_lag_filter_max_seconds', state.val_lag_filter_max),
    ):
        _w[label].configure(text=_seconds_text(var.get()))


def update_lag_filter_visibility(*args):
    for widget in _w['lag_filter_rows']:
        if state.val_checkbox_lag_filter.get():
            widget.grid()
        else:
            widget.grid_remove()
    if not state.val_checkbox_lag_filter.get():
        _w['error_label_lag_filter'].grid_forget()


def update_lag_filter_entries_on_validation(*args):
    if state.val_LAG_FILTER_VALID.get():
        _w['entry_lag_filter_min'].configure(border_color='#777777')
        _w['entry_lag_filter_max'].configure(border_color='#777777')
        _w['error_label_lag_filter'].grid_forget()
        return
    _w['entry_lag_filter_min'].configure(border_color='red')
    _w['entry_lag_filter_max'].configure(border_color='red')
    if not validation.check_lag_filter_exists():
        msg = "Enter both filter limits"
    else:
        lf_sorted   = validation.check_lag_filter_sorted()
        lf_in_range = validation.check_lag_filter_in_range()
        msg = (
            f"Filter limits must be "
            f"{'sorted' if not lf_sorted else ''}"
            f"{' and ' if not lf_sorted and not lf_in_range else ''}"
            f"{'in [-max_lag, max_lag]' if not lf_in_range else ''}"
        )
    _w['error_label_lag_filter'].configure(text=msg, text_color='red')
    _w['error_label_lag_filter'].grid(row=12, column=0, columnspan=4, sticky="w", padx=10, pady=5)


# ---------------------------------------------------------------------------
# UPDATE FUNCTIONS — standard xcorr entry validation
# ---------------------------------------------------------------------------

def update_max_lag_entry_on_validation_sxc(*args):
    if state.val_MAX_LAG_VALID_SXC.get():
        _w['entry_max_lag_sxc'].configure(border_color='#777777')
        _w['error_label_max_lag_sxc'].grid_forget()
    else:
        _w['entry_max_lag_sxc'].configure(border_color='red')
        _w['error_label_max_lag_sxc'].grid(row=2, column=0, columnspan=4, sticky="w", padx=10, pady=0)


# ---------------------------------------------------------------------------
# UPDATE FUNCTIONS — export & batch
# ---------------------------------------------------------------------------

def update_active_state_export_button(*args):
    state_str = "normal" if validation.check_export_ready() else "disabled"
    _w['button_export_data'].configure(state=state_str)
    _w['button_export_plot'].configure(state=state_str)


_EXPORT_BUTTONS = {'data': 'button_export_data', 'plot': 'button_export_plot'}
_export_button_texts = {}


def update_export_busy(*args):
    """While an export runs, the window shows a busy cursor, and the clicked button says so."""
    kind = state.val_exporting.get()
    for button_kind, key in _EXPORT_BUTTONS.items():
        button = _w[key]
        _export_button_texts.setdefault(key, button.cget('text'))
        button.configure(text="Exporting..." if button_kind == kind else _export_button_texts[key])
    _w['button_export_data'].winfo_toplevel().configure(cursor="watch" if kind else "")
    if kind:
        for key in _EXPORT_BUTTONS.values():
            _w[key].configure(state="disabled")
    else:
        update_active_state_export_button()


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


def update_job_progress_visibility(*args):
    if state.val_job_running.get():
        _w['subgroup_job_progress'].grid(row=3, column=0, sticky='ew', columnspan=2, padx=0, pady=0)
    else:
        _w['subgroup_job_progress'].grid_forget()


def update_active_state_cancel_button(*args):
    _w['button_cancel_job'].configure(state="disabled" if state.val_job_cancel_requested.get() else "normal")


def update_job_progress_bar(*args):
    _w['progress_bar_job'].set(state.val_job_progress.get())


def update_active_state_random_pair_button(*args):
    _w['button_random_pair'].configure(
        state="normal" if state.val_random_pair_is_ready.get() else "disabled"
    )
