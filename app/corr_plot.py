import os
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from plot import plot_init, plot_message, update_sxcorr_plots, update_wxcorr_plots, update_preproc_plots
from analysis import correlate_signals, format_dfa, windowed_dfa

import state

canvas = None

UPDATE_DEBOUNCE_MS = 250
NO_WINDOWED_DFA = {'alpha_window_averages': None, 'alpha_per_lag': None, 'note': 'No valid results yet.'}

_pending_update = None    # id of the scheduled UPDATE, if any
_computed_wx_settings = None    # the settings behind the current wxcorr results
_computed_sx_settings = None    # the settings behind the current sxcorr results


def setup(group_plot):
    """Creates and packs the matplotlib canvas inside group_plot."""
    global canvas
    canvas = FigureCanvasTkAgg(state.dat_plot_data["fig"], master=group_plot)
    widget = canvas.get_tk_widget()
    widget.pack(fill='both', expand=True)


def fit_canvas_to_container():
    """
    Sizes the figure to the canvas and does the first draw.
    Safe to call multiple times — only resizes/draws when canvas has real dimensions.
    Called once pre-show (may be 1x1 on external displays) and once post-show.
    """
    widget = canvas.get_tk_widget()
    w, h = widget.winfo_width(), widget.winfo_height()
    if w > 1 and h > 1:
        _apply_figure_size(canvas.figure, w, h)
        canvas.draw()


def _apply_figure_size(fig, w, h):
    fig.set_size_inches(w / fig.get_dpi(), h / fig.get_dpi())


# ---------------------------------------------------------------------------
# CORRELATION DATA COMPUTATION
# ---------------------------------------------------------------------------

def _signals():
    d = state.dat_physiological_data
    return d["signal_a"], d["signal_b"], d["signal_a_std"], d["signal_b_std"]


def _update_wxcorr_data():
    global _computed_wx_settings
    if not state.val_INPUT_DATA_VALID.get() or not state.val_CORRELATION_SETTINGS_VALID.get():
        return

    # new data clears the results, so only the settings can make non-empty results out of date
    config = state.analysis_config()
    if state.dat_correlation_data['wxcorr'] and config.windowed_settings == _computed_wx_settings:
        return

    state.dat_correlation_data['wxcorr'] = correlate_signals(_signals(), config)
    _computed_wx_settings = config.windowed_settings

    state.dat_correlation_data['dfa_windows'] = windowed_dfa(state.dat_correlation_data['wxcorr'], config)


def _update_sxcorr_data():
    global _computed_sx_settings
    if not state.val_INPUT_DATA_VALID.get() or not state.val_CORRELATION_SETTINGS_VALID_SXC.get():
        return

    config = state.analysis_config()
    if state.dat_correlation_data['sxcorr'] and config.standard_settings == _computed_sx_settings:
        return

    state.dat_correlation_data['sxcorr'] = correlate_signals(_signals(), config)
    _computed_sx_settings = config.standard_settings


def update_corr():
    if state.val_checkbox_windowed_xcorr.get():
        _update_wxcorr_data()
    else:
        _update_sxcorr_data()


# ---------------------------------------------------------------------------
# PLOT UPDATE
# ---------------------------------------------------------------------------

def update_plot(*args):
    current_tab = state.val_CURRENT_TAB.get()

    if current_tab == "Input Data":
        _update_preprocess_plot()
    elif state.val_checkbox_windowed_xcorr.get():
        _update_wxcorr_plot()
    else:
        _update_sxcorr_plot()


def _no_results_message(settings_valid):
    """Why there is no result to plot, or None if there is one."""
    if not state.val_INPUT_DATA_VALID.get():
        return "No results: " + (state.val_input_error.get() or "no data loaded.")
    if not settings_valid:
        return "No results: check the correlation settings."
    return None


def _update_preprocess_plot():
    if not state.val_INPUT_DATA_VALID.get():
        reason = state.val_input_error.get()
        state.dat_plot_data["fig"] = plot_message(reason) if reason else plot_init(is_retina=state.RETINA)
        return

    use_std  = state.val_checkbox_standardise.get()
    signal_a = state.dat_physiological_data["signal_a_std" if use_std else "signal_a"]
    signal_b = state.dat_physiological_data["signal_b_std" if use_std else "signal_b"]

    state.dat_plot_data["fig"] = update_preproc_plots({
        'signal_a':      signal_a,
        'signal_b':      signal_b,
        'dyad_folder':   os.path.basename(state.val_selected_dyad_dir.get()),
        'selected_sheet': state.val_selected_sheet.get(),
        'filename_a':    os.path.basename(state.val_selected_file_a.get()),
        'filename_b':    os.path.basename(state.val_selected_file_b.get()),
        'column_a':      state.val_selected_column.get(),
        'column_b':      state.val_selected_column.get(),
        'is_resampled':  state.val_checkbox_eb.get(),
    })


def _update_wxcorr_plot():
    message = _no_results_message(state.val_CORRELATION_SETTINGS_VALID.get())
    if message or not state.dat_correlation_data['wxcorr']:
        state.dat_plot_data["fig"] = plot_message(message or "No results.")
        return

    use_std  = state.val_checkbox_standardise.get()
    signal_a = state.dat_physiological_data["signal_a_std" if use_std else "signal_a"]
    signal_b = state.dat_physiological_data["signal_b_std" if use_std else "signal_b"]

    state.dat_plot_data["fig"] = update_wxcorr_plots({
        'signal_a':               signal_a,
        'signal_b':               signal_b,
        'window_size':            state.val_window_size.get(),
        'step_size':              state.val_step_size.get(),
        'max_lag':                state.val_max_lag.get(),
        'use_lag_filter':         state.val_checkbox_lag_filter.get(),
        'lag_filter_min':         state.val_lag_filter_min.get(),
        'lag_filter_max':         state.val_lag_filter_max.get(),
        'windowed_xcorr_data':    state.dat_correlation_data["wxcorr"],
        'show_sigmoid_correlations': state.val_checkbox_show_sigmoid_correlations.get(),
    })


def _update_sxcorr_plot():
    message = _no_results_message(state.val_CORRELATION_SETTINGS_VALID_SXC.get())
    if message or not state.dat_correlation_data['sxcorr']:
        state.dat_plot_data["fig"] = plot_message(message or "No results.")
        return

    use_std  = state.val_checkbox_standardise.get()
    signal_a = state.dat_physiological_data["signal_a_std" if use_std else "signal_a"]
    signal_b = state.dat_physiological_data["signal_b_std" if use_std else "signal_b"]

    state.dat_plot_data["fig"] = update_sxcorr_plots({
        'signal_a':   signal_a,
        'signal_b':   signal_b,
        'xcorr_data': state.dat_correlation_data['sxcorr'],
    })


# ---------------------------------------------------------------------------
# CANVAS UPDATE
# ---------------------------------------------------------------------------

def update_canvas():
    if not state.dat_plot_data["fig"]:
        return
    widget = canvas.get_tk_widget()
    w, h = widget.winfo_width(), widget.winfo_height()
    if w <= 1 or h <= 1:
        return  # not yet laid out; fit_canvas_to_container() handles the first draw
    canvas.figure = state.dat_plot_data["fig"]
    _apply_figure_size(canvas.figure, w, h)
    canvas.draw()


# ---------------------------------------------------------------------------
# MAIN UPDATE LOOP
# Scheduled whenever val_UPDATE_COUNT changes, so that repeated changes run it once.
# ---------------------------------------------------------------------------

def update_dfa_text():
    windowed = state.val_checkbox_windowed_xcorr.get()
    dfa_windows = state.dat_correlation_data.get('dfa_windows') or NO_WINDOWED_DFA
    if not state.val_CORRELATION_SETTINGS_VALID.get():
        dfa_windows = {**NO_WINDOWED_DFA, 'note': 'Check the correlation settings.'}
    state.val_dfa_text.set(format_dfa(state.dat_correlation_data.get('dfa_signals'), dfa_windows if windowed else None))


def UPDATE(*args):
    global _pending_update
    _pending_update = None
    update_corr()
    update_dfa_text()
    update_plot()
    update_canvas()


def schedule_update(*args):
    global _pending_update
    widget = canvas.get_tk_widget()
    if _pending_update is not None:
        widget.after_cancel(_pending_update)
    delay_ms = UPDATE_DEBOUNCE_MS if state.update_is_debounced else 0
    _pending_update = widget.after(delay_ms, UPDATE)


def flush_update():
    """Runs a scheduled update now, for anything that is about to read the results."""
    if _pending_update is not None:
        canvas.get_tk_widget().after_cancel(_pending_update)
        UPDATE()
