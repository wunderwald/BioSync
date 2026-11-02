import customtkinter as tk
from analysis import AnalysisConfig
from plot import plot_init

# ----------------------
# DEFAULTS / INIT VALUES
# ----------------------

INIT_WINDOW_SIZE = 150   # 150 := 30s for 5hz signals
INIT_MAX_LAG     = 30    # 30 := 6s
INIT_STEP_SIZE   = 75    # 75 := 15s
INIT_MAX_LAG_SXC = 150

# ---------------------
# SCREEN METRICS
# (populated by init_state before any tk.Vars are used)
# ---------------------
screen_dpi    = None
screen_width  = None
screen_height = None
RETINA        = None

# ---------------------
# GLOBAL STATE & EVENTS
# ---------------------

# input validation trackers
val_CORRELATION_SETTINGS_VALID     = None
val_CORRELATION_SETTINGS_VALID_SXC = None
val_WINDOW_SIZE_VALID              = None
val_STEP_SIZE_VALID                = None
val_MAX_LAG_VALID                  = None
val_MAX_LAG_VALID_SXC              = None
val_INPUT_DATA_VALID               = None
val_LAG_FILTER_VALID               = None

# GUI state
val_CURRENT_TAB  = None
val_UPDATE_COUNT = None

# app state variables
val_checkbox_absolute_corr           = None
val_checkbox_absolute_corr_sxc       = None
val_checkbox_eb                      = None
val_checkbox_fr                      = None
val_checkbox_windowed_xcorr          = None
val_window_size_input                = None
val_step_size_input                  = None
val_max_lag_input                    = None
val_max_lag_input_sxc                = None
val_window_size                      = None
val_step_size                        = None
val_max_lag                          = None
val_max_lag_sxc                      = None
val_checkbox_lag_filter              = None
val_lag_filter_min                   = None
val_lag_filter_max                   = None
val_lag_filter_min_input             = None
val_lag_filter_max_input             = None
val_checkbox_average_windows         = None
val_checkbox_show_sigmoid_correlations = None
val_checkbox_standardise             = None
val_selected_dyad_dir                = None
val_selected_file_a                  = None
val_selected_file_b                  = None
val_data_length                      = None
val_selected_sheet                   = None
val_selected_column                  = None
val_checkbox_data_has_headers        = None
val_batch_input_folder               = None
val_batch_output_folder              = None
val_batch_processing_is_ready        = None
val_rp_n_input                       = None
val_rp_n                             = None
val_random_pair_input_folder         = None
val_random_pair_output_file          = None
val_random_pair_is_ready             = None
val_job_running                      = None
val_job_progress                     = None
val_job_progress_text                = None

# data containers
dat_plot_data         = {}
dat_workbook_data     = {}
dat_physiological_data = {}
dat_correlation_data  = {}


# whether the update requested last should wait for typing to pause
update_is_debounced = False


def PARAMS_CHANGED(debounce=False):
    global update_is_debounced
    update_is_debounced = debounce
    val_UPDATE_COUNT.set(val_UPDATE_COUNT.get() + 1)


def analysis_config():
    """The current settings for the analysis."""
    return AnalysisConfig(
        signal_type='event-based' if val_checkbox_eb.get() else 'fixed-rate',
        windowed=val_checkbox_windowed_xcorr.get(),
        standardised=val_checkbox_standardise.get(),
        window_size=val_window_size.get(),
        step_size=val_step_size.get(),
        max_lag=val_max_lag.get(),
        absolute=val_checkbox_absolute_corr.get(),
        average_windows=val_checkbox_average_windows.get(),
        use_lag_filter=val_checkbox_lag_filter.get(),
        lag_filter_min=val_lag_filter_min.get(),
        lag_filter_max=val_lag_filter_max.get(),
        max_lag_sxc=val_max_lag_sxc.get(),
        absolute_sxc=val_checkbox_absolute_corr_sxc.get(),
    )


def init_state(dpi, sw, sh, retina):
    """
    Must be called once after tk.CTk() is created but before any widgets are built.
    Initialises all module-level tk.Vars and data containers.
    """
    global screen_dpi, screen_width, screen_height, RETINA
    global val_CORRELATION_SETTINGS_VALID, val_CORRELATION_SETTINGS_VALID_SXC
    global val_WINDOW_SIZE_VALID, val_STEP_SIZE_VALID, val_MAX_LAG_VALID
    global val_MAX_LAG_VALID_SXC, val_INPUT_DATA_VALID, val_LAG_FILTER_VALID
    global val_CURRENT_TAB, val_UPDATE_COUNT
    global val_checkbox_absolute_corr, val_checkbox_absolute_corr_sxc
    global val_checkbox_eb, val_checkbox_fr, val_checkbox_windowed_xcorr
    global val_window_size_input, val_step_size_input, val_max_lag_input, val_max_lag_input_sxc
    global val_window_size, val_step_size, val_max_lag, val_max_lag_sxc
    global val_checkbox_lag_filter, val_lag_filter_min, val_lag_filter_max
    global val_lag_filter_min_input, val_lag_filter_max_input
    global val_checkbox_average_windows, val_checkbox_show_sigmoid_correlations
    global val_checkbox_standardise, val_selected_dyad_dir
    global val_selected_file_a, val_selected_file_b, val_data_length
    global val_selected_sheet, val_selected_column
    global val_checkbox_data_has_headers, val_batch_input_folder, val_batch_output_folder
    global val_batch_processing_is_ready, val_rp_n_input, val_rp_n
    global val_random_pair_input_folder, val_random_pair_output_file, val_random_pair_is_ready
    global val_job_running, val_job_progress, val_job_progress_text
    global dat_plot_data, dat_workbook_data, dat_physiological_data, dat_correlation_data

    screen_dpi    = dpi
    screen_width  = sw
    screen_height = sh
    RETINA        = retina

    # validation trackers
    val_CORRELATION_SETTINGS_VALID     = tk.BooleanVar(value=True)
    val_CORRELATION_SETTINGS_VALID_SXC = tk.BooleanVar(value=True)
    val_WINDOW_SIZE_VALID              = tk.BooleanVar(value=True)
    val_STEP_SIZE_VALID                = tk.BooleanVar(value=True)
    val_MAX_LAG_VALID                  = tk.BooleanVar(value=True)
    val_MAX_LAG_VALID_SXC              = tk.BooleanVar(value=True)
    val_INPUT_DATA_VALID               = tk.BooleanVar(value=False)
    val_LAG_FILTER_VALID               = tk.BooleanVar(value=True)

    # GUI state
    val_CURRENT_TAB  = tk.StringVar(value="Input Data")
    val_UPDATE_COUNT = tk.IntVar(value=0)

    # app state variables
    val_checkbox_absolute_corr             = tk.BooleanVar(value=False)
    val_checkbox_absolute_corr_sxc         = tk.BooleanVar(value=False)
    val_checkbox_eb                        = tk.BooleanVar(value=True)
    val_checkbox_fr                        = tk.BooleanVar(value=False)
    val_checkbox_windowed_xcorr            = tk.BooleanVar(value=True)
    val_window_size_input                  = tk.StringVar(value=INIT_WINDOW_SIZE)
    val_step_size_input                    = tk.StringVar(value=INIT_STEP_SIZE)
    val_max_lag_input                      = tk.StringVar(value=INIT_MAX_LAG)
    val_max_lag_input_sxc                  = tk.StringVar(value=INIT_MAX_LAG_SXC)
    val_window_size                        = tk.IntVar(value=INIT_WINDOW_SIZE)
    val_step_size                          = tk.IntVar(value=INIT_STEP_SIZE)
    val_max_lag                            = tk.IntVar(value=INIT_MAX_LAG)
    val_max_lag_sxc                        = tk.IntVar(value=INIT_MAX_LAG_SXC)
    val_checkbox_lag_filter                = tk.BooleanVar(value=False)
    val_lag_filter_min                     = tk.IntVar(value=-INIT_MAX_LAG)
    val_lag_filter_max                     = tk.IntVar(value=INIT_MAX_LAG)
    val_lag_filter_min_input               = tk.StringVar(value=str(-INIT_MAX_LAG))
    val_lag_filter_max_input               = tk.StringVar(value=str(INIT_MAX_LAG))
    val_checkbox_average_windows           = tk.BooleanVar(value=False)
    val_checkbox_show_sigmoid_correlations = tk.BooleanVar(value=False)
    val_checkbox_standardise               = tk.BooleanVar(value=False)
    val_selected_dyad_dir                  = tk.StringVar(value='')
    val_selected_file_a                    = tk.StringVar(value='')
    val_selected_file_b                    = tk.StringVar(value='')
    val_data_length                        = tk.IntVar(value=0)
    val_selected_sheet                     = tk.StringVar(value='- None -')
    val_selected_column                    = tk.StringVar(value='- None -')
    val_checkbox_data_has_headers          = tk.BooleanVar(value=True)
    val_batch_input_folder                 = tk.StringVar(value='')
    val_batch_output_folder                = tk.StringVar(value='')
    val_batch_processing_is_ready         = tk.BooleanVar(value=False)
    val_rp_n_input                         = tk.StringVar(value="100")
    val_rp_n                               = tk.IntVar(value=100)
    val_random_pair_input_folder           = tk.StringVar(value='')
    val_random_pair_output_file            = tk.StringVar(value='')
    val_random_pair_is_ready               = tk.BooleanVar(value=False)
    val_job_running                        = tk.BooleanVar(value=False)
    val_job_progress                       = tk.DoubleVar(value=0)
    val_job_progress_text                  = tk.StringVar(value='')

    # data containers
    dat_plot_data['fig'] = plot_init(is_retina=retina)

    dat_workbook_data.update({
        'workbook_a': None,
        'workbook_b': None,
        'sheet_names': [],
        'columns_a': {},
        'columns_b': {},
        'column_names': [],
        'has_headers': True
    })

    dat_physiological_data.update({
        'signal_a': [],
        'signal_b': [],
        'signal_a_std': [],
        'signal_b_std': [],
        'raw_signal_a': [],
        'raw_signal_b': []
    })

    dat_correlation_data.update({
        'wxcorr': [],
        'sxcorr': [],
        'dfa_alpha_sxcorr': None,
        'dfa_alpha_per_lag_wxcorr': None,
        'dfa_alpha_window_averages_wxcorr': None,
    })
