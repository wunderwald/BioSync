import os
import utils
import state
import validation
from measures import MEAN_ABS_R_MAX, MEAN_R, R_AT_LAG_0
from signal_processing import EVENT_BASED_SAMPLING_RATE_HZ
from surrogates import BLOCKS, REPAIRED, WELCH

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
        state.val_lag_filter_min, state.val_lag_filter_max, state.val_checkbox_eb, state.val_block_length,
        state.val_sampling_rate,
    ):
        var.trace_add('write', update_parameter_labels)
    update_parameter_labels()

    state.val_checkbox_eb.trace_add('write', update_sampling_rate_visibility)
    update_sampling_rate_visibility()

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

    state.val_surrogate_method.trace_add('write', update_surrogate_method_widgets)
    state.val_surrogate_test.trace_add('write', update_surrogate_method_widgets)
    update_surrogate_method_widgets()
    state.val_surrogate_measure.trace_add('write', update_measure_explanation)
    update_measure_explanation()
    state.val_surrogate_problem.trace_add('write', update_surrogate_messages)
    state.val_surrogate_warning.trace_add('write', update_surrogate_messages)
    update_surrogate_messages()

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


def _sampling_rate():
    """Hz, or 0 if unknown: event-based data is resampled at a fixed rate, fixed-rate data has the rate entered."""
    if state.val_checkbox_eb.get():
        return EVENT_BASED_SAMPLING_RATE_HZ
    return state.val_sampling_rate.get() or 0


def _seconds_text(samples):
    """A parameter in seconds, or nothing when the sampling rate is unknown."""
    rate = _sampling_rate()
    if not rate:
        return ''
    seconds = samples / rate
    return f"{seconds:.0f} s" if abs(seconds) >= 100 else f"{seconds:.3g} s"


def update_sampling_rate_visibility(*args):
    """Event-based data has a fixed resampling rate. Fixed-rate data shows the field for its rate instead."""
    if state.val_checkbox_eb.get():
        _w['label_select_data_type'].grid()
        _w['frame_sampling_rate'].grid_remove()
    else:
        _w['label_select_data_type'].grid_remove()
        _w['frame_sampling_rate'].grid()


def update_parameter_labels(*args):
    for label, var in (
        ('label_window_size_seconds', state.val_window_size),
        ('label_step_size_seconds', state.val_step_size),
        ('label_max_lag_seconds', state.val_max_lag),
        ('label_max_lag_sxc_seconds', state.val_max_lag_sxc),
        ('label_lag_filter_min_seconds', state.val_lag_filter_min),
        ('label_lag_filter_max_seconds', state.val_lag_filter_max),
        ('label_block_length_seconds', state.val_block_length),
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


JOB_PROGRESS_ROW = 10      # below the content of every tab with a job


def update_job_progress_visibility(*args):
    """Every tab that can start a job shows its progress, so that it is visible wherever it was started."""
    for panel in _w['job_progress_panels']:
        if state.val_job_running.get():
            panel['frame'].grid(row=JOB_PROGRESS_ROW, column=0, sticky='ew', columnspan=2, padx=0, pady=0)
        else:
            panel['frame'].grid_forget()


def update_active_state_cancel_button(*args):
    for panel in _w['job_progress_panels']:
        panel['button_cancel'].configure(state="disabled" if state.val_job_cancel_requested.get() else "normal")


def update_job_progress_bar(*args):
    for panel in _w['job_progress_panels']:
        panel['progress_bar'].set(state.val_job_progress.get())


def update_active_state_random_pair_button(*args):
    _w['button_random_pair'].configure(
        state="normal" if state.val_random_pair_is_ready.get() else "disabled"
    )


# ---------------------------------------------------------------------------
# UPDATE FUNCTIONS — surrogates
# ---------------------------------------------------------------------------

METHOD_EXPLANATIONS = {
    REPAIRED: "Pairs each person with people from other dyads. Asks whether the real dyads are more coupled "
              "than strangers recorded in the same setting.",
    BLOCKS: "Cuts partner B's signal into blocks and puts them in a random order. Asks whether a dyad's "
            "coupling depends on the timing between the partners, and also gives a p-value for each dyad.",
    WELCH: "The test of earlier versions, to repeat their results. It counts every random pair as independent, "
           "which they aren't, as the same people appear again and again, so its p isn't exact.",
}
MEASURE_EXPLANATIONS = {
    MEAN_R: "The average correlation over all windows and lags.",
    MEAN_ABS_R_MAX: "The strongest correlation at any lag, without its sign, averaged over the windows.",
    R_AT_LAG_0: "The correlation without delay, averaged over the windows.",
}


def _effective_method():
    method = state.val_surrogate_method.get()
    return WELCH if method == REPAIRED and state.val_surrogate_test.get() == WELCH else method


def update_surrogate_method_widgets(*args):
    method = _effective_method()
    _w['label_surrogate_method_explanation'].configure(text=METHOD_EXPLANATIONS.get(method, ''))
    if state.val_surrogate_method.get() == REPAIRED:
        _w['frame_surrogate_test'].grid()
    else:
        _w['frame_surrogate_test'].grid_remove()
    if method == BLOCKS:
        _w['frame_block_length'].grid()
    else:
        _w['frame_block_length'].grid_remove()
    _w['label_surrogate_n'].configure(text="Random pairs" if method == WELCH else "Surrogates")


def update_measure_explanation(*args):
    _w['label_measure_explanation'].configure(text=MEASURE_EXPLANATIONS.get(state.val_surrogate_measure.get(), ''))


def update_surrogate_messages(*args):
    for key, var, row in (
        ('label_surrogate_problem', state.val_surrogate_problem, 1),
        ('label_surrogate_warning', state.val_surrogate_warning, 2),
    ):
        if var.get():
            _w[key].grid(row=row, column=0, sticky='w', padx=10, pady=(0, 5))
        else:
            _w[key].grid_forget()
    _w['entry_block_length'].configure(
        border_color='red' if 'block length' in state.val_surrogate_problem.get() else '#777777'
    )
