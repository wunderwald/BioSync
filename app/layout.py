import tkinter
import customtkinter as tk

import state
import validation
import callbacks as cb
from measures import MEASURES
from surrogates import BLOCKS, REPAIRED, SURROGATE_DISTRIBUTION, WELCH


DROPDOWN_WIDTH = 240
TAB_WIDTH = 410
SCROLLBAR_SPACE = 20    # room for a tab's scrollbar, which appears when its settings don't fit the window
TABVIEW_WIDTH = 422 + SCROLLBAR_SPACE
PATH_LABEL_WRAP = 220  # long folder names wrap instead of running out of the fixed-size tabview
PARAMETER_ENTRY_WIDTH = 80
PARAMETER_SECONDS_WIDTH = 60  # room for values like -19.8 s, so that the panel keeps its width

# what the Surrogates tab shows for each choice
SURROGATE_METHOD_LABELS = {"Shuffled blocks": BLOCKS, "Re-paired people": REPAIRED}
SURROGATE_TEST_LABELS = {"Surrogate distribution": SURROGATE_DISTRIBUTION, "Welch's t-test": WELCH}


def _button_opening_a_dialog(parent, command, **options):
    """
    A button that runs its command when the mouse button is released, not when it is pressed. CTkButton runs
    commands on press, and a dialog opened then makes Tk miss the release: it keeps sending every later click
    to the button, which reopens the dialog until the window is focused again. Releasing outside the button
    cancels the click, as with any button.
    """
    button = tk.CTkButton(parent, **options)

    def released(event):
        x = event.widget.winfo_rootx() + event.x - button.winfo_rootx()
        y = event.widget.winfo_rooty() + event.y - button.winfo_rooty()
        if button.cget("state") != "disabled" and 0 <= x < button.winfo_width() and 0 <= y < button.winfo_height():
            button.after_idle(command)

    button.bind("<ButtonRelease-1>", released)
    return button


def needs_scrollbar(content_height, visible_height):
    return content_height > visible_height


def _scrollable(tab):
    """
    Returns a frame inside the tab that scrolls when its content doesn't fit, for example on a 1280x800 screen.
    The window can't be resized, so without it the lower settings and the Cancel button would be out of reach.
    The scrollbar is only shown when it is needed.
    """
    content = tk.CTkScrollableFrame(tab, fg_color='transparent', width=TAB_WIDTH, corner_radius=0)
    content.pack(fill='both', expand=True)

    def show_scrollbar_if_needed(event=None):
        if needs_scrollbar(content.winfo_reqheight(), content._parent_canvas.winfo_height()):
            content._scrollbar.grid()
        else:
            content._scrollbar.grid_remove()

    content.bind('<Configure>', show_scrollbar_if_needed, add='+')
    content._parent_canvas.bind('<Configure>', show_scrollbar_if_needed, add='+')
    return content


def _parameter_row(parent, row, name, variable, validator):
    """
    Adds '<name> <entry> samples <value in seconds>' to a row of a grid.
    Returns the widgets, and the seconds label is filled in by gui_updates.
    """
    label = tk.CTkLabel(parent, text=name)
    label.grid(row=row, column=0, sticky="w", padx=10, pady=5)

    entry = tk.CTkEntry(
        parent, width=PARAMETER_ENTRY_WIDTH,
        validate="key", validatecommand=(validator, "%P"),
        textvariable=variable, border_color='#777777'
    )
    entry.grid(row=row, column=1, sticky="w", padx=(0, 5), pady=5)

    label_samples = tk.CTkLabel(parent, text="samples")
    label_samples.grid(row=row, column=2, sticky="w", padx=(0, 10), pady=5)

    label_seconds = tk.CTkLabel(parent, text="", width=PARAMETER_SECONDS_WIDTH, anchor="w")
    label_seconds.grid(row=row, column=3, sticky="w", padx=(0, 10), pady=5)

    return label, entry, label_samples, label_seconds


def _job_progress_panel(parent):
    """The progress and Cancel button of a running batch or surrogate analysis, below the content of a tab."""
    frame = tk.CTkFrame(parent)
    label = tk.CTkLabel(frame, textvariable=state.val_job_progress_text)
    label.grid(row=0, column=0, padx=10, pady=5, sticky='w')
    progress_bar = tk.CTkProgressBar(frame)
    progress_bar.grid(row=1, column=0, padx=10, pady=5, sticky='w')
    button_cancel = tk.CTkButton(frame, text='Cancel', command=cb.cancel_job)
    button_cancel.grid(row=2, column=0, padx=10, pady=5, sticky='w')
    return {'frame': frame, 'progress_bar': progress_bar, 'button_cancel': button_cancel}


def _section(parent, row):
    """An outlined container for one section of a tab, with space around it, so that sections stand apart."""
    frame = tk.CTkFrame(parent, border_width=1, corner_radius=8)
    frame.grid(row=row, column=0, sticky='ew', columnspan=2, padx=4, pady=(4, 8))
    frame.grid_columnconfigure(0, weight=1)
    return frame


def _heading(parent, row, text):
    label = tk.CTkLabel(parent, text=text, font=("Arial", 14, "bold"))
    label.grid(row=row, column=0, columnspan=4, sticky='w', padx=10, pady=(12, 2))
    return label


def _explanation(parent, row):
    label = tk.CTkLabel(parent, text="", wraplength=TAB_WIDTH - 30, justify='left', font=("Arial", 12))
    label.grid(row=row, column=0, columnspan=4, sticky='w', padx=10, pady=(2, 4))
    return label


def _build_surrogates_tab(tab, validate_numeric_input):
    """
    The Surrogates tab reads from top to bottom like the method: the dyads, what they are compared with, the
    measure, how many surrogates, then a sentence on what will be tested, and the run.
    """
    group = tk.CTkFrame(tab)
    group.grid(row=0, column=0, sticky='ew', columnspan=2, padx=0, pady=0)

    title = tk.CTkLabel(group, text="Surrogate Analysis", font=("Arial", 20, "bold"))
    title.grid(row=0, column=0, columnspan=4, sticky='w', padx=10, pady=(10, 0))
    intro = tk.CTkLabel(
        group, wraplength=TAB_WIDTH - 30, justify='left', font=("Arial", 12),
        text="Compares the real dyads with surrogates, in which coupling can't exist. "
             "Uses the settings of the Input Data and Correlation tabs.",
    )
    intro.grid(row=1, column=0, columnspan=4, sticky='w', padx=10, pady=(0, 4))

    _heading(group, 2, "Real dyads")
    button_input_folder = _button_opening_a_dialog(group, cb.open_random_pair_input_dir_picker, text='Select input folder')
    button_input_folder.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky='w')
    label_input_folder = tk.CTkLabel(group, text="No folder selected.", wraplength=PATH_LABEL_WRAP, justify='left')
    label_input_folder.grid(row=3, column=2, columnspan=2, padx=10, sticky='w')

    _heading(group, 4, "Compare with")
    method_labels = {method: label for label, method in SURROGATE_METHOD_LABELS.items()}
    segmented_method = tk.CTkSegmentedButton(
        group, values=list(SURROGATE_METHOD_LABELS),
        command=lambda label: state.val_surrogate_method.set(SURROGATE_METHOD_LABELS[label]),
    )
    segmented_method.set(method_labels[state.val_surrogate_method.get()])
    segmented_method.grid(row=5, column=0, columnspan=4, sticky='w', padx=10, pady=5)
    label_method_explanation = _explanation(group, 6)

    # only for re-paired people: the test of earlier versions
    frame_test = tk.CTkFrame(group, fg_color='transparent')
    frame_test.grid(row=7, column=0, columnspan=4, sticky='w', padx=0, pady=0)
    tk.CTkLabel(frame_test, text="Test").grid(row=0, column=0, sticky='w', padx=10, pady=5)
    test_labels = {test: label for label, test in SURROGATE_TEST_LABELS.items()}
    dropdown_test = tk.CTkOptionMenu(
        frame_test, values=list(SURROGATE_TEST_LABELS), width=DROPDOWN_WIDTH, dynamic_resizing=False,
        command=lambda label: state.val_surrogate_test.set(SURROGATE_TEST_LABELS[label]),
    )
    dropdown_test.set(test_labels[state.val_surrogate_test.get()])
    dropdown_test.grid(row=0, column=1, sticky='w', padx=(0, 10), pady=5)

    # only for shuffled blocks
    frame_block_length = tk.CTkFrame(group, fg_color='transparent')
    frame_block_length.grid(row=8, column=0, columnspan=4, sticky='w', padx=0, pady=0)
    _, entry_block_length, _, label_block_length_seconds = _parameter_row(
        frame_block_length, 0, 'Block length', state.val_block_length_input, validate_numeric_input
    )

    _heading(group, 9, "Measure")
    segmented_measure = tk.CTkSegmentedButton(group, values=list(MEASURES), variable=state.val_surrogate_measure)
    segmented_measure.grid(row=10, column=0, columnspan=4, sticky='w', padx=10, pady=5)
    label_measure_explanation = _explanation(group, 11)

    _heading(group, 12, "Repeats")
    label_n = tk.CTkLabel(group, text="Surrogates")
    label_n.grid(row=13, column=0, sticky="w", padx=10, pady=5)
    entry_n = tk.CTkEntry(
        group, width=PARAMETER_ENTRY_WIDTH, validate="key", validatecommand=(validate_numeric_input, "%P"),
        textvariable=state.val_rp_n_input, border_color='#777777',
    )
    entry_n.grid(row=13, column=1, sticky="w", padx=(0, 5), pady=5)
    tk.CTkLabel(group, text="Seed (optional)").grid(row=14, column=0, sticky="w", padx=10, pady=5)
    entry_seed = tk.CTkEntry(
        group, width=PARAMETER_ENTRY_WIDTH, validate="key", validatecommand=(validate_numeric_input, "%P"),
        textvariable=state.val_rp_seed_input, border_color='#777777',
    )
    entry_seed.grid(row=14, column=1, sticky="w", padx=(0, 5), pady=5)
    seed_info = _explanation(group, 15)
    seed_info.configure(text="Left empty, a new seed is used. Every export records its seed, so a run can be repeated.")

    # what will be tested, and what stops or limits it
    frame_plan = tk.CTkFrame(group)
    frame_plan.grid(row=16, column=0, columnspan=4, sticky='ew', padx=10, pady=(10, 5))
    label_plan = tk.CTkLabel(frame_plan, textvariable=state.val_surrogate_plan, wraplength=TAB_WIDTH - 50, justify='left')
    label_plan.grid(row=0, column=0, sticky='w', padx=10, pady=5)
    label_problem = tk.CTkLabel(frame_plan, textvariable=state.val_surrogate_problem, text_color='red',
                                wraplength=TAB_WIDTH - 50, justify='left')
    label_warning = tk.CTkLabel(frame_plan, textvariable=state.val_surrogate_warning, text_color='#c27c0e',
                                wraplength=TAB_WIDTH - 50, justify='left')
    # problem and warning are shown when they have text

    button_run = _button_opening_a_dialog(group, cb.handle_run_surrogate_button, text='Run surrogate analysis',
                                          state="disabled")
    button_run.grid(row=17, column=0, columnspan=2, padx=10, pady=10, sticky='w')

    # below the progress of a run (row 10 of the tab, see gui_updates.JOB_PROGRESS_ROW)
    group_export = tk.CTkFrame(tab)
    group_export.grid(row=11, column=0, sticky='ew', columnspan=2, padx=0, pady=(10, 0))
    label_export = tk.CTkLabel(group_export, text="Export", font=("Arial", 20, "bold"))
    label_export.grid(row=0, column=0, sticky='w', padx=10, pady=(10, 0))
    label_result = tk.CTkLabel(group_export, text="", wraplength=TAB_WIDTH - 30, justify='left', font=("Arial", 12))
    label_result.grid(row=1, column=0, sticky='w', padx=10, pady=(0, 4))
    frame_export_buttons = tk.CTkFrame(group_export, fg_color='transparent')
    frame_export_buttons.grid(row=2, column=0, sticky='w', padx=0, pady=0)
    button_export_data = _button_opening_a_dialog(frame_export_buttons, cb.export_surrogate_data, text='Export XLSX',
                                                  state="disabled")
    button_export_data.grid(row=0, column=0, padx=10, pady=10, sticky='w')
    button_export_plot = _button_opening_a_dialog(frame_export_buttons, cb.export_surrogate_plot, text='Export PNG',
                                                  state="disabled")
    button_export_plot.grid(row=0, column=1, padx=10, pady=10, sticky='w')

    return {
        'label_random_pair_input_folder':    label_input_folder,
        'label_surrogate_result':            label_result,
        'button_export_surrogate_data':      button_export_data,
        'button_export_surrogate_plot':      button_export_plot,
        'button_random_pair':                button_run,
        'segmented_surrogate_method':        segmented_method,
        'label_surrogate_method_explanation': label_method_explanation,
        'frame_surrogate_test':              frame_test,
        'dropdown_surrogate_test':           dropdown_test,
        'frame_block_length':                frame_block_length,
        'entry_block_length':                entry_block_length,
        'label_block_length_seconds':        label_block_length_seconds,
        'segmented_surrogate_measure':       segmented_measure,
        'label_measure_explanation':         label_measure_explanation,
        'label_surrogate_n':                 label_n,
        'entry_surrogate_n':                 entry_n,
        'label_surrogate_problem':           label_problem,
        'label_surrogate_warning':           label_warning,
        'job_progress':                      _job_progress_panel(tab),
    }


def build_layout(app, validate_numeric_input, validate_signed_numeric_input):
    """
    Creates all widgets and grid/packs them into the app window.
    Returns a dict of widget references needed by app_gui_updates.py and app_corr_plot.py.
    Must be called after app_state.init_state() and app_callbacks.setup_traces().
    """

    # ---------------
    # MAIN APP LAYOUT
    # ---------------
    # Both top-level widgets pack directly into app (CTk root handles its own background).
    # No intermediate container — any wrapper frame inherits system colors and shows
    # as black on macOS dark-mode systems regardless of CTk appearance mode.
    #
    # Pack order matters: tabview must be packed side='right' FIRST so it claims its
    # strip before group_plot fills all remaining space.
    # The tabview keeps a fixed size, also while a tab change removes its content for a moment.
    # A size change would resize the plot next to it, and every plot resize is a slow redraw.
    group_params_tabview = tk.CTkTabview(app, width=TABVIEW_WIDTH)
    group_params_tabview.grid_propagate(False)
    group_params_tabview.pack(side='right', fill='y', padx=(5, 20), pady=10)

    group_plot = tkinter.Frame(app)
    group_plot.pack(side='left', fill='both', expand=True, padx=(20, 5), pady=10)

    # -------------------
    # GUI PARAMETER GROUP
    # -------------------

    tab_input_data   = _scrollable(group_params_tabview.add("Input Data"))
    tab_correlation  = _scrollable(group_params_tabview.add("Correlation"))
    tab_export_batch = _scrollable(group_params_tabview.add("Export & Batch"))
    tab_surrogates   = _scrollable(group_params_tabview.add("Surrogates"))
    group_params_tabview.configure(command=cb.on_tab_change)
    for tab in (tab_input_data, tab_correlation, tab_export_batch, tab_surrogates):
        tab.grid_columnconfigure(0, minsize=TAB_WIDTH)

    # ---------------------------
    # TAB: INPUT DATA & PREPROCESS
    # ---------------------------

    subgroup_input_data = tk.CTkFrame(tab_input_data)
    subgroup_input_data.grid(row=0, column=0, sticky='ew', columnspan=2, padx=0, pady=0)

    label_input_data = tk.CTkLabel(subgroup_input_data, text="Input Data", font=("Arial", 20, "bold"))
    label_input_data.grid(row=0, column=0, columnspan=2, pady=20, padx=10, sticky='w')

    button_file_picker = _button_opening_a_dialog(subgroup_input_data, cb.open_dir_picker, text="Choose Dyad Folder")
    button_file_picker.grid(row=1, column=0, sticky="w", padx=10, pady=5)

    label_dir_picker = tk.CTkLabel(subgroup_input_data, text="No folder selected.", font=("Arial", 14, "bold"), wraplength=TAB_WIDTH - 20)
    label_dir_picker.grid(row=2, column=0, sticky="w", padx=10, pady=5)

    label_select_sheet = tk.CTkLabel(subgroup_input_data, text="Select Sheet", font=("Arial", 14, "bold"))
    label_select_sheet.grid(row=3, column=0, sticky="w", padx=10, pady=5)

    dropdown_select_sheet = tk.CTkOptionMenu(
        subgroup_input_data, values=['- None -'],
        command=cb.on_dropdown_select_sheet_change,
        variable=state.val_selected_sheet, width=DROPDOWN_WIDTH, dynamic_resizing=False
    )
    dropdown_select_sheet.grid(row=4, column=0, sticky="w", padx=10, pady=5)

    label_select_column = tk.CTkLabel(subgroup_input_data, text="Select Column", font=("Arial", 14, "bold"))
    label_select_column.grid(row=6, column=0, sticky="w", padx=10, pady=5)

    dropdown_select_column = tk.CTkOptionMenu(
        subgroup_input_data, values=['- None -'],
        command=cb.on_dropdown_select_column_change,
        variable=state.val_selected_column, width=DROPDOWN_WIDTH, dynamic_resizing=False
    )
    dropdown_select_column.grid(row=7, column=0, sticky="w", padx=10, pady=5)

    checkbox_data_has_headers = tk.CTkCheckBox(
        subgroup_input_data, text='columns have headers',
        variable=state.val_checkbox_data_has_headers
    )
    checkbox_data_has_headers.grid(row=8, column=0, sticky="w", padx=10, pady=5)

    error_label_input_data = tk.CTkLabel(
        subgroup_input_data, text='Data is invalid.', text_color='red', justify='left', wraplength=TAB_WIDTH - 20
    )
    # initially hidden — shown reactively via gui_updates

    # Pre-process subgroup
    subgroup_data_type = tk.CTkFrame(tab_input_data)
    subgroup_data_type.grid(row=1, column=0, sticky='ew', columnspan=2, padx=0, pady=0)

    label_data_type = tk.CTkLabel(subgroup_data_type, text="Pre-Process", font=("Arial", 20, "bold"))
    label_data_type.grid(row=0, column=0, columnspan=2, pady=20, padx=10, sticky='w')

    checkbox_is_eb_data = tk.CTkCheckBox(
        subgroup_data_type, text='event-based',
        variable=state.val_checkbox_eb, command=cb.on_is_eb_change
    )
    checkbox_is_eb_data.grid(row=4, column=0, sticky="w", padx=10, pady=5)

    checkbox_is_fr_data = tk.CTkCheckBox(
        subgroup_data_type, text='fixed-rate',
        variable=state.val_checkbox_fr, command=cb.on_is_fr_change
    )
    checkbox_is_fr_data.grid(row=4, column=1, sticky="w", padx=10, pady=5)

    label_select_data_type = tk.CTkLabel(
        subgroup_data_type, text="Event-based data will be resampled to 5hz."
    )
    label_select_data_type.grid(row=5, column=0, columnspan=2, sticky="w", padx=10, pady=5)
    # shown instead for fixed-rate data
    frame_sampling_rate = tk.CTkFrame(subgroup_data_type, fg_color='transparent')
    frame_sampling_rate.grid(row=6, column=0, columnspan=2, sticky="w", padx=0, pady=0)
    tk.CTkLabel(frame_sampling_rate, text="Sampling rate").grid(row=0, column=0, sticky="w", padx=10, pady=5)
    entry_sampling_rate = tk.CTkEntry(
        frame_sampling_rate, width=PARAMETER_ENTRY_WIDTH,
        validate="key", validatecommand=(app.register(validation.is_decimal_input), "%P"),
        textvariable=state.val_sampling_rate_input, border_color='#777777',
    )
    entry_sampling_rate.grid(row=0, column=1, sticky="w", padx=(0, 5), pady=5)
    tk.CTkLabel(frame_sampling_rate, text="Hz").grid(row=0, column=2, sticky="w", padx=(0, 10), pady=5)
    label_sampling_rate_note = tk.CTkLabel(
        frame_sampling_rate, textvariable=state.val_sampling_rate_note, wraplength=TAB_WIDTH - 30, justify='left',
        font=("Arial", 12),
    )
    label_sampling_rate_note.grid(row=1, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 5))

    checkbox_standardise = tk.CTkCheckBox(
        subgroup_data_type, text='standardise',
        variable=state.val_checkbox_standardise, command=cb.on_standardise_change
    )
    checkbox_standardise.grid(row=8, column=0, sticky="w", padx=10, pady=5)

    label_standardise = tk.CTkLabel(subgroup_data_type, text="Scales to zero mean, unit variance. Correlations don't change.")
    label_standardise.grid(row=9, column=0, columnspan=2, sticky="w", padx=10, pady=5)

    # ---------------------------
    # TAB: CORRELATION
    # ---------------------------

    subgroup_corr_settings = _section(tab_correlation, 0)

    label_corr_settings = tk.CTkLabel(
        subgroup_corr_settings, text="Correlation Settings", font=("Arial", 20, "bold")
    )
    label_corr_settings.grid(row=0, column=0, columnspan=2, pady=20, padx=10, sticky='w')

    checkbox_windowed_xcorr = tk.CTkCheckBox(
        subgroup_corr_settings, text='Windowed cross-correlation',
        variable=state.val_checkbox_windowed_xcorr, command=cb.on_windowed_xcorr_change
    )
    checkbox_windowed_xcorr.grid(row=1, column=0, sticky="w", padx=10, pady=5)

    # Windowed xcorr parameters subgroup
    subgroup_windowed_xcorr_parameters = tk.CTkFrame(subgroup_corr_settings)
    subgroup_windowed_xcorr_parameters.grid(row=2, sticky='ew', column=0, columnspan=2, padx=8, pady=(0, 8))

    label_wxp = tk.CTkLabel(
        subgroup_windowed_xcorr_parameters, text='Windowed cross-correlation parameters'
    )
    label_wxp.grid(row=0, column=0, columnspan=4, padx=10, pady=5, sticky='w')

    _, entry_window_size, _, label_window_size_seconds = _parameter_row(
        subgroup_windowed_xcorr_parameters, 1, 'Window Size', state.val_window_size_input, validate_numeric_input
    )

    error_label_window_size = tk.CTkLabel(
        subgroup_windowed_xcorr_parameters,
        text='Window Size must be in range [1, data_length]', text_color='red'
    )
    # initially hidden

    _, entry_max_lag, _, label_max_lag_seconds = _parameter_row(
        subgroup_windowed_xcorr_parameters, 3, 'Max Lag', state.val_max_lag_input, validate_numeric_input
    )

    error_label_max_lag = tk.CTkLabel(
        subgroup_windowed_xcorr_parameters,
        text='Max Lag must be in range [1, window_size//2]', text_color='red'
    )
    # initially hidden

    _, entry_step_size, _, label_step_size_seconds = _parameter_row(
        subgroup_windowed_xcorr_parameters, 5, 'Step Size', state.val_step_size_input, validate_numeric_input
    )

    error_label_step_size = tk.CTkLabel(
        subgroup_windowed_xcorr_parameters,
        text='Step Size must be in range [1, window_size]', text_color='red'
    )
    # initially hidden

    checkbox_lag_filter = tk.CTkCheckBox(
        subgroup_windowed_xcorr_parameters, text='Filter Range of Lags',
        variable=state.val_checkbox_lag_filter, command=cb.on_lag_filter_checkbox_change
    )
    checkbox_lag_filter.grid(row=9, column=0, columnspan=4, sticky="w", padx=10, pady=5)

    # shown when the filter is used, see gui_updates.update_lag_filter_visibility
    lag_filter_row_min = _parameter_row(
        subgroup_windowed_xcorr_parameters, 10, 'Minimum', state.val_lag_filter_min_input, validate_signed_numeric_input
    )
    lag_filter_row_max = _parameter_row(
        subgroup_windowed_xcorr_parameters, 11, 'Maximum', state.val_lag_filter_max_input, validate_signed_numeric_input
    )
    for widget in (*lag_filter_row_min, *lag_filter_row_max):
        widget.grid_remove()

    error_label_lag_filter = tk.CTkLabel(
        subgroup_windowed_xcorr_parameters, text='', text_color='red'
    )
    # initially hidden

    checkbox_absolute_corr = tk.CTkCheckBox(
        subgroup_windowed_xcorr_parameters, text='Absolute Correlation Values',
        variable=state.val_checkbox_absolute_corr, command=cb.on_absolute_corr_change
    )
    checkbox_absolute_corr.grid(row=15, column=0, columnspan=4, sticky="w", padx=10, pady=5)

    checkbox_average_windows = tk.CTkCheckBox(
        subgroup_windowed_xcorr_parameters, text='Average Values in Windows',
        variable=state.val_checkbox_average_windows, command=cb.on_average_windows_change
    )
    checkbox_average_windows.grid(row=16, column=0, columnspan=4, sticky="w", padx=10, pady=5)

    # Standard xcorr parameters subgroup (initially hidden)
    subgroup_standard_xcorr_parameters = tk.CTkFrame(subgroup_corr_settings)

    label_sxp = tk.CTkLabel(
        subgroup_standard_xcorr_parameters, text='Standard cross-correlation parameters'
    )
    label_sxp.grid(row=0, column=0, sticky='w', columnspan=4, padx=10, pady=5)

    _, entry_max_lag_sxc, _, label_max_lag_sxc_seconds = _parameter_row(
        subgroup_standard_xcorr_parameters, 1, 'Max Lag', state.val_max_lag_input_sxc, validate_numeric_input
    )

    error_label_max_lag_sxc = tk.CTkLabel(
        subgroup_standard_xcorr_parameters,
        text='Max Lag must be in range [0, data_length - 1]', text_color='red'
    )
    # initially hidden

    checkbox_absolute_corr_sxc = tk.CTkCheckBox(
        subgroup_standard_xcorr_parameters, text='Absolute Correlation Values',
        variable=state.val_checkbox_absolute_corr_sxc, command=cb.on_absolute_corr_change_sxc
    )
    checkbox_absolute_corr_sxc.grid(row=3, column=0, columnspan=4, sticky="w", padx=10, pady=5)

    # ---------------------------
    # TAB: CORRELATION — Signal properties, then how to read the lag
    # ---------------------------

    # Sigmoid scaling is hidden for now: its checkbox is built but never placed, so the plot shows raw values.
    # The option still works everywhere else; placing subgroup_sigmoid with .grid() brings it back.
    subgroup_sigmoid = tk.CTkFrame(tab_correlation)
    checkbox_show_sigmoid_correlations = tk.CTkCheckBox(
        subgroup_sigmoid, text='Sigmoid-Scaled Correlation Values',
        variable=state.val_checkbox_show_sigmoid_correlations,
        command=cb.on_show_sigmoid_correlations_change
    )
    checkbox_show_sigmoid_correlations.grid(row=0, column=0, sticky="w", padx=10, pady=5)
    label_sigmoid_info = tk.CTkLabel(subgroup_sigmoid, text="Applies sigmoid scaling to displayed values only.")
    label_sigmoid_info.grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=5)

    subgroup_signal_properties = _section(tab_correlation, 1)

    label_signal_properties = tk.CTkLabel(
        subgroup_signal_properties, text="Signal Properties", font=("Arial", 20, "bold")
    )
    label_signal_properties.grid(row=0, column=0, columnspan=2, pady=(20, 0), padx=10, sticky='w')

    _heading(subgroup_signal_properties, 1, "Stationarity")
    label_stationarity = tk.CTkLabel(
        subgroup_signal_properties, textvariable=state.val_stationarity_text, justify='left',
        wraplength=TAB_WIDTH - 40
    )
    label_stationarity.grid(row=2, column=0, sticky="w", padx=10, pady=(0, 4))

    _heading(subgroup_signal_properties, 3, "Persistence")

    label_dfa = tk.CTkLabel(
        subgroup_signal_properties, textvariable=state.val_dfa_text, justify='left', wraplength=TAB_WIDTH - 40
    )
    label_dfa.grid(row=4, column=0, sticky="w", padx=10, pady=(0, 14))

    # below the signal properties: how to read tau_max (windowed) or the lag (standard), one at a time, see gui_updates
    subgroup_hints = _section(tab_correlation, 2)

    subgroup_lag_hint = tk.CTkFrame(subgroup_hints, fg_color='transparent')
    subgroup_lag_hint.grid(row=0, column=0, sticky='ew', padx=2, pady=2)

    label_lag_hint = tk.CTkLabel(
        subgroup_lag_hint,
        text="How to read tau_max:\n  τ > 0  →  A leads B\n  τ = 0  →  simultaneous\n  τ < 0  →  B leads A",
        justify='left',
        font=("Arial", 12),
    )
    label_lag_hint.grid(row=0, column=0, sticky="w", padx=10, pady=12)

    subgroup_lag_info = tk.CTkFrame(subgroup_hints, fg_color='transparent')
    # initially hidden — shown when standard xcorr is selected

    label_lag_info = tk.CTkLabel(
        subgroup_lag_info,
        text="How to read lag:\n  lag > 0  →  A leads B\n  lag = 0  →  simultaneous\n  lag < 0  →  B leads A",
        justify='left',
        font=("Arial", 12),
    )
    label_lag_info.grid(row=0, column=0, sticky="w", padx=10, pady=12)

    # ---------------------------
    # TAB: EXPORT & BATCH
    # ---------------------------

    # Export subgroup
    subgroup_export = tk.CTkFrame(tab_export_batch)
    subgroup_export.grid(row=0, column=0, sticky='ew', columnspan=2, padx=0, pady=0)

    label_export = tk.CTkLabel(subgroup_export, text="Export", font=("Arial", 20, "bold"))
    label_export.grid(row=0, column=0, sticky='w', padx=10, columnspan=2, pady=10)

    subsubgroup_export_buttons = tk.CTkFrame(subgroup_export)
    subsubgroup_export_buttons.grid(row=1, column=0, columnspan=2, padx=0, pady=0)

    button_export_data = _button_opening_a_dialog(subsubgroup_export_buttons, cb.export_data, text='Export XLSX')
    button_export_data.grid(row=1, column=0, padx=10, pady=10)

    button_export_plot = _button_opening_a_dialog(subsubgroup_export_buttons, cb.export_plot, text='Export Plots')
    button_export_plot.grid(row=1, column=1, padx=10, pady=10)

    # Batch processing subgroup
    subgroup_batch = tk.CTkFrame(tab_export_batch)
    subgroup_batch.grid(row=1, column=0, sticky='ew', columnspan=2, padx=0, pady=0)

    label_batch = tk.CTkLabel(subgroup_batch, text="Batch Processing", font=("Arial", 20, "bold"))
    label_batch.grid(row=0, column=0, sticky='w', padx=10, columnspan=2, pady=10)

    info_batch = tk.CTkLabel(subgroup_batch, text="Applies the same settings to multiple dyads.")
    info_batch.grid(row=1, column=0, padx=10, sticky='w', columnspan=2)

    button_batch_input_folder = _button_opening_a_dialog(
        subgroup_batch, cb.open_batch_input_folder, text='Select input folder'
    )
    button_batch_input_folder.grid(row=2, column=0, padx=10, pady=10, sticky='w')

    label_batch_input_folder = tk.CTkLabel(subgroup_batch, text="No folder selected.", wraplength=PATH_LABEL_WRAP)
    label_batch_input_folder.grid(row=2, column=1, padx=10, sticky='w')

    label_batch_input_num_subdirs = tk.CTkLabel(subgroup_batch, text="No folder selected.")
    # initially hidden

    button_output_dir_picker = _button_opening_a_dialog(
        subgroup_batch, cb.open_batch_output_dir_picker, text='Select output folder'
    )
    button_output_dir_picker.grid(row=3, column=0, padx=10, pady=10, sticky='w')

    label_output_dir = tk.CTkLabel(subgroup_batch, text="No folder selected.", wraplength=PATH_LABEL_WRAP)
    label_output_dir.grid(row=3, column=1, padx=10, sticky='w')

    button_batch = _button_opening_a_dialog(
        subgroup_batch, cb.handle_run_batch_button, text='Run batch process', state="disabled"
    )
    button_batch.grid(row=8, column=0, padx=10, pady=10, sticky='w')

    # Progress of a running batch (initially hidden)
    job_progress_batch = _job_progress_panel(tab_export_batch)

    surrogate_widgets = _build_surrogates_tab(tab_surrogates, validate_numeric_input)

    # -----------------------------------------------------------------
    # Inject widget references that callbacks need for dropdown updates
    # -----------------------------------------------------------------
    cb.register_dropdowns(dropdown_select_sheet, dropdown_select_column)
    cb.register_tabview(group_params_tabview)

    # -----------------------------------------------------------------
    # Return all widgets needed by app_gui_updates and app_corr_plot
    # -----------------------------------------------------------------
    return {
        'group_plot':                          group_plot,
        'label_dir_picker':                    label_dir_picker,
        'error_label_input_data':              error_label_input_data,
        'dropdown_select_sheet':               dropdown_select_sheet,
        'dropdown_select_column':              dropdown_select_column,
        'label_window_size_seconds':           label_window_size_seconds,
        'label_step_size_seconds':             label_step_size_seconds,
        'label_max_lag_seconds':               label_max_lag_seconds,
        'label_max_lag_sxc_seconds':           label_max_lag_sxc_seconds,
        'label_lag_filter_min_seconds':        lag_filter_row_min[3],
        'label_lag_filter_max_seconds':        lag_filter_row_max[3],
        'lag_filter_rows':                     (*lag_filter_row_min, *lag_filter_row_max),
        'entry_window_size':                   entry_window_size,
        'error_label_window_size':             error_label_window_size,
        'entry_max_lag':                       entry_max_lag,
        'error_label_max_lag':                 error_label_max_lag,
        'entry_step_size':                     entry_step_size,
        'error_label_step_size':               error_label_step_size,
        'entry_lag_filter_min':                lag_filter_row_min[1],
        'entry_lag_filter_max':                lag_filter_row_max[1],
        'error_label_lag_filter':              error_label_lag_filter,
        'entry_max_lag_sxc':                   entry_max_lag_sxc,
        'error_label_max_lag_sxc':             error_label_max_lag_sxc,
        'button_export_data':                  button_export_data,
        'button_export_plot':                  button_export_plot,
        'subgroup_windowed_xcorr_parameters':  subgroup_windowed_xcorr_parameters,
        'subgroup_standard_xcorr_parameters':  subgroup_standard_xcorr_parameters,
        'subgroup_lag_hint':                   subgroup_lag_hint,
        'subgroup_lag_info':                   subgroup_lag_info,
        'subgroup_signal_properties':          subgroup_signal_properties,
        'label_dfa':                           label_dfa,
        'label_stationarity':                  label_stationarity,
        'subgroup_sigmoid':                    subgroup_sigmoid,
        'label_batch_input_folder':            label_batch_input_folder,
        'label_output_dir':                    label_output_dir,
        'label_batch_input_num_subdirs':       label_batch_input_num_subdirs,
        'button_batch':                        button_batch,
        'label_select_data_type':              label_select_data_type,
        'frame_sampling_rate':                 frame_sampling_rate,
        'job_progress_panels':                 [job_progress_batch, surrogate_widgets.pop('job_progress')],
        **surrogate_widgets,
    }
