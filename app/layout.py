import tkinter
import customtkinter as tk

import state
import callbacks as cb


def build_layout(app, validate_numeric_input):
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
    group_params_tabview = tk.CTkTabview(app)
    group_params_tabview.pack(side='right', anchor='n', padx=(5, 20), pady=10)

    group_plot = tkinter.Frame(app)
    group_plot.pack(side='left', fill='both', expand=True, padx=(20, 5), pady=10)

    # -------------------
    # GUI PARAMETER GROUP
    # -------------------

    tab_input_data   = group_params_tabview.add("Input Data")
    tab_correlation  = group_params_tabview.add("Correlation")
    tab_export_batch = group_params_tabview.add("Export & Batch")
    group_params_tabview.configure(command=cb.on_tab_change)

    # ---------------------------
    # TAB: INPUT DATA & PREPROCESS
    # ---------------------------

    subgroup_input_data = tk.CTkFrame(tab_input_data)
    subgroup_input_data.grid(row=0, column=0, sticky='ew', columnspan=2, padx=0, pady=0)

    label_input_data = tk.CTkLabel(subgroup_input_data, text="Input Data", font=("Arial", 20, "bold"))
    label_input_data.grid(row=0, column=0, columnspan=2, pady=20, padx=10, sticky='w')

    button_file_picker = tk.CTkButton(subgroup_input_data, text="Choose Dyad Folder", command=cb.open_dir_picker)
    button_file_picker.grid(row=1, column=0, sticky="w", padx=10, pady=5)

    label_dir_picker = tk.CTkLabel(subgroup_input_data, text="No folder selected.", font=("Arial", 14, "bold"))
    label_dir_picker.grid(row=2, column=0, sticky="w", padx=10, pady=5)

    label_select_sheet = tk.CTkLabel(subgroup_input_data, text="Select Sheet", font=("Arial", 14, "bold"))
    label_select_sheet.grid(row=3, column=0, sticky="w", padx=10, pady=5)

    dropdown_select_sheet = tk.CTkComboBox(
        subgroup_input_data, values=['- None -'],
        command=cb.on_dropdown_select_sheet_change,
        variable=state.val_selected_sheet
    )
    dropdown_select_sheet.grid(row=4, column=0, sticky="w", padx=10, pady=5)

    checkbox_data_has_headers = tk.CTkCheckBox(
        subgroup_input_data, text='columns have headers',
        variable=state.val_checkbox_data_has_headers
    )
    checkbox_data_has_headers.grid(row=5, column=0, sticky="w", padx=10, pady=5)

    label_select_column_a = tk.CTkLabel(subgroup_input_data, text="Select Column A", font=("Arial", 14, "bold"))
    label_select_column_a.grid(row=6, column=0, sticky="w", padx=10, pady=5)

    dropdown_select_column_a = tk.CTkComboBox(
        subgroup_input_data, values=['- None -'],
        command=cb.on_dropdown_select_column_a_change,
        variable=state.val_selected_column_a
    )
    dropdown_select_column_a.grid(row=7, column=0, sticky="w", padx=10, pady=5)

    label_select_column_b = tk.CTkLabel(subgroup_input_data, text="Select Column B", font=("Arial", 14, "bold"))
    label_select_column_b.grid(row=8, column=0, sticky="w", padx=10, pady=5)

    dropdown_select_column_b = tk.CTkComboBox(
        subgroup_input_data, values=['- None -'],
        command=cb.on_dropdown_select_column_b_change,
        variable=state.val_selected_column_b
    )
    dropdown_select_column_b.grid(row=9, column=0, sticky="w", padx=10, pady=5)

    error_label_input_data = tk.CTkLabel(subgroup_input_data, text='Data is invalid.', text_color='red')
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

    checkbox_standardise = tk.CTkCheckBox(
        subgroup_data_type, text='standardise',
        variable=state.val_checkbox_standardise, command=cb.on_standardise_change
    )
    checkbox_standardise.grid(row=8, column=0, sticky="w", padx=10, pady=5)

    label_standardise = tk.CTkLabel(subgroup_data_type, text="Scales to zero mean, unit variance.")
    label_standardise.grid(row=9, column=0, columnspan=2, sticky="w", padx=10, pady=5)

    # ---------------------------
    # TAB: CORRELATION & VISUALISATION
    # ---------------------------

    subgroup_corr_settings = tk.CTkFrame(tab_correlation)
    subgroup_corr_settings.grid(row=0, column=0, sticky='ew', columnspan=2, padx=0, pady=0)

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
    subgroup_windowed_xcorr_parameters.grid(row=2, sticky='ew', column=0, columnspan=2, padx=0, pady=0)

    label_wxp = tk.CTkLabel(
        subgroup_windowed_xcorr_parameters, text='Windowed cross-correlation parameters (# samples)'
    )
    label_wxp.grid(row=0, column=0, columnspan=2, padx=10, pady=5, sticky='w')

    label_window_size = tk.CTkLabel(subgroup_windowed_xcorr_parameters, text='Window Size')
    label_window_size.grid(row=1, column=0, sticky="w", padx=10, pady=5)

    entry_window_size = tk.CTkEntry(
        subgroup_windowed_xcorr_parameters,
        validate="key", validatecommand=(validate_numeric_input, "%P"),
        textvariable=state.val_window_size_input, border_color='#777777'
    )
    entry_window_size.grid(row=1, column=1, sticky="w", padx=10, pady=5)

    error_label_window_size = tk.CTkLabel(
        subgroup_windowed_xcorr_parameters,
        text='Window Size must be in range [1, data_length]', text_color='red'
    )
    # initially hidden

    label_max_lag = tk.CTkLabel(subgroup_windowed_xcorr_parameters, text='Max Lag')
    label_max_lag.grid(row=3, column=0, sticky="w", padx=10, pady=5)

    entry_max_lag = tk.CTkEntry(
        subgroup_windowed_xcorr_parameters,
        validate="key", validatecommand=(validate_numeric_input, "%P"),
        textvariable=state.val_max_lag_input, border_color='#777777'
    )
    entry_max_lag.grid(row=3, column=1, sticky="w", padx=10, pady=5)

    error_label_max_lag = tk.CTkLabel(
        subgroup_windowed_xcorr_parameters,
        text='Max Lag must be in range [1, window_size//2]', text_color='red'
    )
    # initially hidden

    label_step_size = tk.CTkLabel(subgroup_windowed_xcorr_parameters, text='Step Size')
    label_step_size.grid(row=5, column=0, sticky="w", padx=10, pady=5)

    entry_step_size = tk.CTkEntry(
        subgroup_windowed_xcorr_parameters,
        validate="key", validatecommand=(validate_numeric_input, "%P"),
        textvariable=state.val_step_size_input, border_color='#777777'
    )
    entry_step_size.grid(row=5, column=1, sticky="w", padx=10, pady=5)

    error_label_step_size = tk.CTkLabel(
        subgroup_windowed_xcorr_parameters,
        text='Step Size must be in range [1, window_size]', text_color='red'
    )
    # initially hidden

    checkbox_lag_filter = tk.CTkCheckBox(
        subgroup_windowed_xcorr_parameters, text='Filter Range of Lags',
        variable=state.val_checkbox_lag_filter
    )
    checkbox_lag_filter.grid(row=9, column=0, sticky="w", padx=10, pady=5)

    entry_lag_filter_min = tk.CTkEntry(
        subgroup_windowed_xcorr_parameters,
        validate="key", validatecommand=(validate_numeric_input, "%P"),
        textvariable=state.val_lag_filter_min_input, border_color='#777777'
    )
    entry_lag_filter_max = tk.CTkEntry(
        subgroup_windowed_xcorr_parameters,
        validate="key", validatecommand=(validate_numeric_input, "%P"),
        textvariable=state.val_lag_filter_max_input, border_color='#777777'
    )
    error_label_lag_filter = tk.CTkLabel(
        subgroup_windowed_xcorr_parameters, text='', text_color='red'
    )
    # initially hidden

    checkbox_absolute_corr = tk.CTkCheckBox(
        subgroup_windowed_xcorr_parameters, text='Absolute Correlation Values',
        variable=state.val_checkbox_absolute_corr, command=cb.on_absolute_corr_change
    )
    checkbox_absolute_corr.grid(row=15, column=0, sticky="w", padx=10, pady=5)

    checkbox_average_windows = tk.CTkCheckBox(
        subgroup_windowed_xcorr_parameters, text='Average Values in Windows',
        variable=state.val_checkbox_average_windows, command=cb.on_average_windows_change
    )
    checkbox_average_windows.grid(row=16, column=0, sticky="w", padx=10, pady=5)

    # Standard xcorr parameters subgroup (initially hidden)
    subgroup_standard_xcorr_parameters = tk.CTkFrame(subgroup_corr_settings)

    label_sxp = tk.CTkLabel(
        subgroup_standard_xcorr_parameters, text='Standard cross-correlation parameters'
    )
    label_sxp.grid(row=0, column=0, sticky='ew', columnspan=2, padx=10, pady=5)

    label_max_lag_sxc = tk.CTkLabel(subgroup_standard_xcorr_parameters, text='Max Lag')
    label_max_lag_sxc.grid(row=1, column=0, sticky="w", padx=10, pady=5)

    entry_max_lag_sxc = tk.CTkEntry(
        subgroup_standard_xcorr_parameters,
        validate="key", validatecommand=(validate_numeric_input, "%P"),
        textvariable=state.val_max_lag_input_sxc, border_color='#777777'
    )
    entry_max_lag_sxc.grid(row=1, column=1, sticky="w", padx=10, pady=5)

    error_label_max_lag_sxc = tk.CTkLabel(
        subgroup_standard_xcorr_parameters,
        text='Max Lag must be in range [0, data_length - 1]', text_color='red'
    )
    # initially hidden

    checkbox_absolute_corr_sxc = tk.CTkCheckBox(
        subgroup_standard_xcorr_parameters, text='Absolute Correlation Values',
        variable=state.val_checkbox_absolute_corr_sxc, command=cb.on_absolute_corr_change_sxc
    )
    checkbox_absolute_corr_sxc.grid(row=3, column=0, sticky="w", padx=10, pady=5)

    # ---------------------------
    # TAB: CORRELATION — Visualisation subgroup
    # ---------------------------

    subgroup_visualisation = tk.CTkFrame(tab_correlation)
    subgroup_visualisation.grid(row=1, column=0, sticky='ew', columnspan=2, padx=0, pady=0)

    label_visualisation = tk.CTkLabel(subgroup_visualisation, text="Visualisation", font=("Arial", 20, "bold"))
    label_visualisation.grid(row=0, column=0, columnspan=2, pady=20, padx=10, sticky='w')

    checkbox_show_sigmoid_correlations = tk.CTkCheckBox(
        subgroup_visualisation, text='Sigmoid-Scaled Correlation Values',
        variable=state.val_checkbox_show_sigmoid_correlations,
        command=cb.on_show_sigmoid_correlations_change
    )
    checkbox_show_sigmoid_correlations.grid(row=1, column=0, sticky="w", padx=10, pady=5)

    label_sigmoid_info = tk.CTkLabel(
        subgroup_visualisation,
        text="Applies sigmoid scaling to displayed values only."
    )
    label_sigmoid_info.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=5)

    subgroup_lag_hint = tk.CTkFrame(tab_correlation)
    subgroup_lag_hint.grid(row=2, column=0, sticky='ew', columnspan=2, padx=0, pady=0)

    label_lag_hint = tk.CTkLabel(
        subgroup_lag_hint,
        text="How to read tau_max:\n  τ > 0  →  A leads B\n  τ = 0  →  simultaneous\n  τ < 0  →  B leads A",
        justify='left',
        font=("Arial", 12),
    )
    label_lag_hint.grid(row=0, column=0, sticky="w", padx=10, pady=12)

    subgroup_lag_info = tk.CTkFrame(tab_correlation)
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

    button_export_data = tk.CTkButton(subsubgroup_export_buttons, text='Export XLSX', command=cb.export_data)
    button_export_data.grid(row=1, column=0, padx=10, pady=10)

    button_export_plot = tk.CTkButton(subsubgroup_export_buttons, text='Export Plots', command=cb.export_plot)
    button_export_plot.grid(row=1, column=1, padx=10, pady=10)

    # Batch processing subgroup
    subgroup_batch = tk.CTkFrame(tab_export_batch)
    subgroup_batch.grid(row=1, column=0, sticky='ew', columnspan=2, padx=0, pady=0)

    label_batch = tk.CTkLabel(subgroup_batch, text="Batch Processing", font=("Arial", 20, "bold"))
    label_batch.grid(row=0, column=0, sticky='w', padx=10, columnspan=2, pady=10)

    info_batch = tk.CTkLabel(subgroup_batch, text="Applies the same settings to multiple dyads.")
    info_batch.grid(row=1, column=0, padx=10, sticky='w', columnspan=2)

    button_batch_input_folder = tk.CTkButton(
        subgroup_batch, text='Select input folder', command=cb.open_batch_input_folder
    )
    button_batch_input_folder.grid(row=2, column=0, padx=10, pady=10, sticky='w')

    label_batch_input_folder = tk.CTkLabel(subgroup_batch, text="No folder selected.")
    label_batch_input_folder.grid(row=2, column=1, padx=10, sticky='w')

    label_batch_input_num_subdirs = tk.CTkLabel(subgroup_batch, text="No folder selected.")
    # initially hidden

    button_output_dir_picker = tk.CTkButton(
        subgroup_batch, text='Select output folder', command=cb.open_batch_output_dir_picker
    )
    button_output_dir_picker.grid(row=3, column=0, padx=10, pady=10, sticky='w')

    label_output_dir = tk.CTkLabel(subgroup_batch, text="No folder selected.")
    label_output_dir.grid(row=3, column=1, padx=10, sticky='w')

    button_batch = tk.CTkButton(
        subgroup_batch, text='Run batch process',
        command=cb.handle_run_batch_button, state="disabled"
    )
    button_batch.grid(row=8, column=0, padx=10, pady=10, sticky='w')

    # Random pair analysis subgroup
    subgroup_random_pair = tk.CTkFrame(tab_export_batch)
    subgroup_random_pair.grid(row=2, column=0, sticky='ew', columnspan=2, padx=0, pady=0)

    label_random_pair = tk.CTkLabel(subgroup_random_pair, text="Random Pair Analysis", font=("Arial", 20, "bold"))
    label_random_pair.grid(row=0, column=0, sticky='w', padx=10, columnspan=2, pady=10)

    button_random_pair_input_folder = tk.CTkButton(
        subgroup_random_pair, text='Select input folder',
        command=cb.open_random_pair_input_dir_picker
    )
    button_random_pair_input_folder.grid(row=2, column=0, padx=10, pady=10, sticky='w')

    label_random_pair_input_folder = tk.CTkLabel(subgroup_random_pair, text="No folder selected.")
    label_random_pair_input_folder.grid(row=2, column=1, padx=10, sticky='w')

    button_random_pair_output_file = tk.CTkButton(
        subgroup_random_pair, text='Select output file',
        command=cb.open_random_pair_output_file_picker
    )
    button_random_pair_output_file.grid(row=3, column=0, padx=10, pady=10, sticky='w')

    label_random_pair_output_file = tk.CTkLabel(subgroup_random_pair, text="No file selected.")
    label_random_pair_output_file.grid(row=3, column=1, padx=10, sticky='w')

    label_rp_n = tk.CTkLabel(subgroup_random_pair, text="N")
    label_rp_n.grid(row=4, column=0, sticky="w", padx=10, pady=5)

    entry_rp_n = tk.CTkEntry(
        subgroup_random_pair,
        validate="key", validatecommand=(validate_numeric_input, "%P"),
        textvariable=state.val_rp_n_input, border_color='#777777'
    )
    entry_rp_n.grid(row=4, column=1, sticky="w", padx=10, pady=5)

    button_random_pair = tk.CTkButton(
        subgroup_random_pair, text='Run rp analysis',
        command=cb.handle_run_random_pair_button, state="disabled"
    )
    button_random_pair.grid(row=8, column=0, padx=10, pady=10, sticky='w')

    # -----------------------------------------------------------------
    # Inject widget references that callbacks need for dropdown updates
    # -----------------------------------------------------------------
    cb.register_dropdowns(dropdown_select_sheet, dropdown_select_column_a, dropdown_select_column_b)
    cb.register_tabview(group_params_tabview)

    # -----------------------------------------------------------------
    # Return all widgets needed by app_gui_updates and app_corr_plot
    # -----------------------------------------------------------------
    return {
        'group_plot':                          group_plot,
        'label_dir_picker':                    label_dir_picker,
        'label_select_column_a':               label_select_column_a,
        'label_select_column_b':               label_select_column_b,
        'error_label_input_data':              error_label_input_data,
        'entry_window_size':                   entry_window_size,
        'error_label_window_size':             error_label_window_size,
        'entry_max_lag':                       entry_max_lag,
        'error_label_max_lag':                 error_label_max_lag,
        'entry_step_size':                     entry_step_size,
        'error_label_step_size':               error_label_step_size,
        'entry_lag_filter_min':                entry_lag_filter_min,
        'entry_lag_filter_max':                entry_lag_filter_max,
        'error_label_lag_filter':              error_label_lag_filter,
        'entry_max_lag_sxc':                   entry_max_lag_sxc,
        'error_label_max_lag_sxc':             error_label_max_lag_sxc,
        'button_export_data':                  button_export_data,
        'button_export_plot':                  button_export_plot,
        'subgroup_windowed_xcorr_parameters':  subgroup_windowed_xcorr_parameters,
        'subgroup_standard_xcorr_parameters':  subgroup_standard_xcorr_parameters,
        'subgroup_lag_hint':                   subgroup_lag_hint,
        'subgroup_lag_info':                   subgroup_lag_info,
        'subgroup_visualisation':              subgroup_visualisation,
        'label_batch_input_folder':            label_batch_input_folder,
        'label_output_dir':                    label_output_dir,
        'label_batch_input_num_subdirs':       label_batch_input_num_subdirs,
        'button_batch':                        button_batch,
        'label_random_pair_input_folder':      label_random_pair_input_folder,
        'label_random_pair_output_file':       label_random_pair_output_file,
        'button_random_pair':                  button_random_pair,
    }
