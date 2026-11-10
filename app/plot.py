import matplotlib
from matplotlib.figure import Figure
import matplotlib.gridspec as gridspec
import matplotlib.colors as mcolors
import numpy as np

# Custom diverging colormap
_cmap_wxc = mcolors.LinearSegmentedColormap.from_list(
    'wxc_diverging',
    [
        (0.0, "#000000"),  
        (0.5, '#ffffff'),  
        (1.0, "#cc00bb"),  
    ]
)

R_MAX_BIN_WIDTH = 0.1    # 20 bins from -1 to 1
TAU_MAX_BINS = 20        # about this many, each a whole number of lags wide

SCALING_PARAMS = {
    'FIGSIZE': (10, 8),
    'DPI': 100,
}

# Figures are created without pyplot: it keeps every figure open until closed, and on the macOS
# backend closing one crashes the Tk event loop.
def plot_init(is_retina):
    # rcParams — font/line sizes depend on display type, not on window size
    if is_retina:
        matplotlib.rcParams.update({
            'font.size': 12,
            'axes.titlesize': 12,
            'axes.labelsize': 11,
            'xtick.labelsize': 10,
            'ytick.labelsize': 10,
            'lines.linewidth': 1,
        })
    else:
        matplotlib.rcParams.update({
            'font.size': 16,
            'axes.titlesize': 16,
            'axes.labelsize': 15,
            'xtick.labelsize': 14,
            'ytick.labelsize': 14,
            'lines.linewidth': 2,
        })
    # Default figsize — the canvas resize handler will set the real size at draw time
    fig = Figure(figsize=SCALING_PARAMS['FIGSIZE'], dpi=SCALING_PARAMS['DPI'])
    return fig

def _without_flat_windows(values):
    values = np.asarray(values, dtype=float)
    return values[~np.isnan(values)]

def plot_message(text):
    """An empty figure with a message, shown instead of a plot that would be out of date."""
    fig = Figure(figsize=SCALING_PARAMS['FIGSIZE'], dpi=SCALING_PARAMS['DPI'])
    fig.text(0.5, 0.5, text, ha='center', va='center', wrap=True, color='#777777')
    return fig

def _hist_bins(values, low, high, width, centred=False):
    """
    Bin edges of a fixed width from low to high, widened to include every value. With a fixed width, a few
    windows with the same value give one narrow bar instead of one bar across the whole axis, and values that
    differ only by rounding can't make bins narrower than numbers can be.
    centred puts the bins' middles on multiples of the width, so that a bin of lags is centred on 0.
    """
    if len(values):
        low, high = min(low, float(np.min(values))), max(high, float(np.max(values)))
    if centred:
        return np.arange((np.floor(low / width + 0.5) - 0.5) * width, high + width, width)
    return np.arange(np.floor(low / width) * width, high + width, width)


def _count_ticks(ax, counts):
    """A histogram counts windows, so its axis only marks 0 and the count of the tallest bar."""
    highest = int(max(counts, default=0))
    ax.set_yticks([0, highest] if highest else [0])
    ax.set_ylim(0, max(highest, 1) * 1.05)


def _lag_bin_width(min_lag, max_lag):
    """An odd number of lags per bin, so that each bin is centred on a lag, giving about TAU_MAX_BINS bins."""
    width = max(1, round((max_lag - min_lag + 1) / TAU_MAX_BINS))
    return width if width % 2 else width + 1

def plot_windowed_cross_correlation(wxc_data, window_size, max_lag, step_size, signal_a, signal_b, show_sigmoid_correlations=False, use_lag_filter=False, lag_filter_min=None, lag_filter_max=None):
    """
    Create and return a figure plotting the wxc_data of the windowed cross-correlation.

    Args:
        wxc_data (list of dict): Output from `windowed_cross_correlation`.
        max_lag (int): Maximum lag used in the computation.
        step_size (int): Step size for the sliding window.
        signal_a (array-like): First input signal.
        signal_b (array-like): Second input signal.
        show_sigmoid_correlations (bool): Show sigmoid scaled correlation values.
    Returns:
        matplotlib.figure.Figure: The figure containing the plots.
    """
    # Extract values for plotting
    window_start_indices = [res['start_idx'] for res in wxc_data]
    r_max_values = [res['r_max_sigmoid' if show_sigmoid_correlations else 'r_max'] for res in wxc_data]
    tau_max_values = [res['tau_max_sigmoid' if show_sigmoid_correlations else 'tau_max'] for res in wxc_data]
    correlation_values = [res['correlations_sigmoid' if show_sigmoid_correlations else 'correlations'] for res in wxc_data]

    # Initialize plot layout
    fig = Figure(figsize=SCALING_PARAMS['FIGSIZE'], dpi=SCALING_PARAMS['DPI'], layout='constrained')
    gs = gridspec.GridSpec(3, 1, height_ratios=[3, 1, 1], figure=fig)

    # get lag range (filtered or unfiltered) for y-axis
    _min_lag = -max_lag
    _max_lag = max_lag
    if use_lag_filter and not (lag_filter_min is None or lag_filter_max is None):
        _min_lag = min(lag_filter_min, lag_filter_max)
        _max_lag = max(lag_filter_min, lag_filter_max)

    # Create a heatmap of correlations
    ax0 = fig.add_subplot(gs[0])
    heatmap_data = np.array(correlation_values)
    im = ax0.imshow(
        heatmap_data.T,
        aspect='auto',
        cmap=_cmap_wxc,
        extent=[0, len(wxc_data) * step_size, _min_lag, _max_lag],
        origin='lower',
        vmin=-1,
        vmax=1
    )
    fig.colorbar(im, ax=ax0, label='Correlation')
    ax0.axhline(y=0, color='white', linestyle='dotted', linewidth=0.5)
    ax0.set_xlabel('Window Start Index')
    ax0.set_ylabel('Lag')
    ax0.set_title(f"Correlation Heatmap{' (sigmoid-scaled)' if show_sigmoid_correlations else ''}")
    
    # Plot peak correlation values over time and as histogram
    ax1_gs_inner = gridspec.GridSpecFromSubplotSpec(1, 2, subplot_spec=gs[1], width_ratios=[6, 1], wspace=.1)
    ax1 = fig.add_subplot(ax1_gs_inner[0])
    ax1.plot(window_start_indices, r_max_values, marker='o', markersize=.8, color='black', label='peak correlation')
    ax1.set_ylabel('r_max')
    ax1.set_title('Peak correlation per window')
    ax1.grid()
    r_max_hist_values = _without_flat_windows(r_max_values)
    ax1_hist = fig.add_subplot(ax1_gs_inner[1])
    counts, _, _ = ax1_hist.hist(r_max_hist_values, bins=_hist_bins(r_max_hist_values, -1, 1, R_MAX_BIN_WIDTH), orientation='vertical', color='black', alpha=1)
    ax1_hist.set_xlim(-1, 1)
    _count_ticks(ax1_hist, counts)

    # Plot corresponding lags over time
    ax2_gs_inner = gridspec.GridSpecFromSubplotSpec(1, 2, subplot_spec=gs[2], width_ratios=[6, 1], wspace=.1)
    ax2 = fig.add_subplot(ax2_gs_inner[0])
    ax2.plot(window_start_indices, tau_max_values, marker='o', markersize=.8, color='black', label='Lag of peak')
    ax2.set_ylabel('tau_max')
    ax2.set_title('Lag of peak correlation per window')
    ax2.grid()
    tau_max_hist_values = _without_flat_windows(tau_max_values)
    ax2_hist = fig.add_subplot(ax2_gs_inner[1])
    counts, _, _ = ax2_hist.hist(tau_max_hist_values, bins=_hist_bins(tau_max_hist_values, _min_lag, _max_lag, _lag_bin_width(_min_lag, _max_lag), centred=True), orientation='vertical', color='black', alpha=1)
    ax2_hist.set_xlim(-max_lag, max_lag)
    _count_ticks(ax2_hist, counts)

    # Return the figure
    return fig

def plot_standard_cross_correlation(sxc_data, signal_a, signal_b):
    """
    Create and return a figure plotting the standard cross-correlation between two signals.

    Args:
        sxc_data (dict): Dictionary containing 'corr' (correlation values) and 'lags' arrays.
        signal_a (array-like): First input signal.
        signal_b (array-like): Second input signal.

    Returns:
        matplotlib.figure.Figure: The figure containing the plot.
    """
    corr = sxc_data['corr']
    lags = sxc_data['lags']

    # Initialize plot layout
    fig = Figure(figsize=SCALING_PARAMS['FIGSIZE'], dpi=SCALING_PARAMS['DPI'], layout='constrained')
    gs = gridspec.GridSpec(3, 1, height_ratios=[3, 1, 1], figure=fig)

    # Plot cross-correlation
    ax2 = fig.add_subplot(gs[0])
    ax2.plot(lags, corr, marker='o', markersize=.5, color='#333333')
    ax2.set_xlabel('Lag')
    ax2.set_ylabel('Cross-correlation')
    ax2.set_title('Standard Cross-correlation')
    ax2.grid()

    # Plot input signal a over time
    ax1 = fig.add_subplot(gs[1])
    ax1.plot(signal_a, label='Signal a', color='#333333')
    ax1.set_xlabel('Index')
    ax1.set_ylabel('Signal a')
    ax1.grid()

    # Plot input signal b over time
    ax1 = fig.add_subplot(gs[2])
    ax1.plot(signal_b, label='Signal b', color='#333333')
    ax1.set_xlabel('Index')
    ax1.set_ylabel('Signal b')
    ax1.grid()

    # Return figure object
    return fig

def make_plot_titles_preproc(dyad_folder, selected_sheet, filename_a, filename_b, column_a, column_b, is_resampled):
    """
    Generate plot titles for preprocessed signal visualization.

    Args:
        dyad_folder (str): Name of the dyad folder.
        selected_sheet (str): Name of the selected sheet in the Excel files.
        filename_a (str): Filename of the first Excel file.
        filename_b (str): Filename of the second Excel file.
        column_a (str): Column name for the first signal.
        column_b (str): Column name for the second signal.
        is_resampled (bool): Whether the signals have been resampled to 5Hz.

    Returns:
        dict: Dictionary with keys 'a' and 'b' containing formatted title strings for each signal.
    """
    title_a = f"Data in column '{column_a}' of sheet '{selected_sheet}' of '{filename_a}' [in folder '{dyad_folder}']{' - resampled to 5hz' if is_resampled else ''}"
    title_b = f"Data in column '{column_b}' of sheet '{selected_sheet}' of '{filename_b}' [in folder '{dyad_folder}']{' - resampled to 5hz' if is_resampled else ''}"
    return {'a': title_a, 'b': title_b}

def plot_preprocessed_signals(signal_a, signal_b, plot_titles):
    """
    Plot two preprocessed signals on separate subplots.
    Args: 
        signal_a (array-like): First signal to plot.
        signal_a (array-like): Second signal to plot.
        plot_titles (dict): Dictionary containing plot titles with keys 'a' and 'b'.
    Returns:
        matplotlib.figure.Figure: The figure containing the plot.
    """
    # Initialize plot layout
    fig = Figure(figsize=SCALING_PARAMS['FIGSIZE'], dpi=SCALING_PARAMS['DPI'], layout='constrained')
    gs = gridspec.GridSpec(2, 1, figure=fig)
    
    # Plot signal_a
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(signal_a, color='#333333')
    ax1.set_title(plot_titles['a'], wrap=True)
    ax1.set_xlabel('Index')
    ax1.set_ylabel('Value')
    ax1.grid()
    
    # Plot signal_b
    ax2 = fig.add_subplot(gs[1])
    ax2.plot(signal_b, color='#333333')
    ax2.set_title(plot_titles['b'], wrap=True)
    ax2.set_xlabel('Index')
    ax2.set_ylabel('Value')
    ax2.grid()
    
    return fig

# update windowed xcorr plots
def update_wxcorr_plots(params):
    """
    Updates the windowed cross-correlation plots based on the provided parameters.
    Args:
        params (dict): A dictionary containing the following keys:
            - "signal_a" (array-like): The first signal data.
            - "signal_b" (array-like): The second signal data.
            - "window_size" (int): The size of the window for cross-correlation.
            - "step_size" (int): The step size for moving the window.
            - "max_lag" (int): The maximum lag to consider in the cross-correlation.
            - "windowed_xcorr_data" (array-like): The precomputed windowed cross-correlation data.
            - "use_lag_filter" (bool): Apply lag filter to limit lag range.
            - "lag_filter_min" (int): Minimum lag for filter (inclusive).
            - "lag_filter_max" (int): Maximum lag for filter (inclusive).
            - "show_sigmoid_correlations" (bool): Visualise sigmoid scaled correlation values.
    Returns:
        matplotlib.figure.Figure: The figure object containing the updated plot.
    """
    signal_a = params["signal_a"]
    signal_b = params["signal_b"]
    window_size = params['window_size']
    step_size = params['step_size']
    max_lag = params['max_lag']
    windowed_xcorr_data = params['windowed_xcorr_data']
    use_lag_filter = params['use_lag_filter']
    lag_filter_min = params['lag_filter_min']
    lag_filter_max = params['lag_filter_max']
    show_sigmoid_correlations = params['show_sigmoid_correlations']
    
    # create and store plot figure
    fig = plot_windowed_cross_correlation(windowed_xcorr_data, window_size, max_lag, step_size, signal_a, signal_b, show_sigmoid_correlations=show_sigmoid_correlations, use_lag_filter=use_lag_filter, lag_filter_min=lag_filter_min, lag_filter_max=lag_filter_max)
    return fig

# update standard xcorr plots
def update_sxcorr_plots(params):
    """
    Updates the standard cross-correlation plots based on the provided parameters.
    Args:
        params (dict): A dictionary containing the following keys:
            - "signal_a" (array-like): The first signal data.
            - "signal_b" (array-like): The second signal data.
            - "xcorr_data" (array-like): The cross-correlation data.
    Returns:
        matplotlib.figure.Figure: The figure object containing the updated cross-correlation plot.
    """

    # read data from data containers and state variables
    signal_a = params["signal_a"]
    signal_b = params["signal_b"]
    xcorr_data = params["xcorr_data"]

    # create and store plot figure
    fig = plot_standard_cross_correlation(xcorr_data, signal_a, signal_b)
    return fig

# update preprocessing preview plots
def update_preproc_plots(params):
    """
    Updates the preprocessing preview plots based on the provided parameters.
    Args:
        params (dict): A dictionary containing the following keys:
            - "signal_a" (array-like): The first signal data.
            - "signal_b" (array-like): The second signal data.
            - "dyad_folder" (str): Path to the dyad folder.
            - "selected_sheet" (str): Name of selected sheet.
            - "filename_a" (str): Filename associated with signal_a.
            - "filename_b" (str): Filename associated with signal_b.
            - "column_a" (str): Column name for signal_a.
            - "column_b" (str): Column name for signal_b.
            - "is_resampled" (bool): Flag indicating whether signals have been resampled (to 5hz).
    Returns:
        matplotlib.figure.Figure: The figure object containing the updated plot.
    """
    signal_a = params["signal_a"]
    signal_b = params["signal_b"]
    plot_titles = make_plot_titles_preproc(params["dyad_folder"], params["selected_sheet"], params["filename_a"], params["filename_b"], params["column_a"], params["column_b"], params["is_resampled"])
    fig = plot_preprocessed_signals(signal_a, signal_b, plot_titles)
    return fig

def save_figure_to_png(fig, filepath):
    """
    Save a matplotlib figure to a PNG file.

    Args:
        fig (matplotlib.figure.Figure): The figure object to save.
        filepath (str): The full path where the PNG file should be saved.
    """
    fig.savefig(filepath, dpi=300, bbox_inches='tight')

# ---------------------------------------------------------------------------
# SURROGATE TESTS
# ---------------------------------------------------------------------------

REAL_COLOR = '#cc00bb'          # the positive pole of the heatmap, the app's accent
SURROGATE_COLOR = '#b4b4b4'
SURROGATE_DARK_COLOR = '#555555'
SIGNIFICANCE_LEVEL = 0.05
SURROGATE_HISTOGRAM_BINS = 30
MANY_DYADS = 20                 # from here on, dyad names get smaller text
MAX_DYAD_LABELS = 40            # beyond this, only every n-th dyad is named
DYAD_PANEL_POINTS = 450         # about the height of the dyad panel, which sets how thick each dyad's marks can be


def format_p(p_value):
    if p_value != p_value:      # NaN
        return "p = -"
    return "p < 0.001" if p_value < 0.001 else f"p = {p_value:.3f}"


def _method_title(result):
    # imported here: surrogates imports the analysis modules, which plotting doesn't need otherwise
    from surrogates import BLOCKS, REPAIRED
    if result.method == REPAIRED:
        return f"Real dyads vs. {result.n_surrogates} sets of re-paired people"
    if result.method == BLOCKS:
        return f"Real dyads vs. {result.n_surrogates} sets of shuffled versions (blocks of {result.block_length} samples)"
    return f"Real dyads vs. {result.n_surrogates} random pairs, Welch's t-test"


def _with_margin(low, high):
    margin = (high - low) * 0.05 or 0.01
    return low - margin, high + margin


def _draw_surrogate_sets(ax, result):
    """Histogram of the surrogate group means, with the real group mean as a line."""
    null_values = _without_flat_windows(result.null_values)
    counts, _, _ = ax.hist(null_values, bins=SURROGATE_HISTOGRAM_BINS, color=SURROGATE_COLOR, edgecolor='white',
                           linewidth=1)
    ax.axvline(result.real_value, color=REAL_COLOR, linewidth=2.5)
    ax.set_xlim(*_with_margin(min(null_values.min(), result.real_value), max(null_values.max(), result.real_value)))
    ax.set_ylim(0, counts.max() * 1.18)     # room for the label of the real value above the bars
    ax.text(result.real_value, 0.97, f" real {result.real_value:.3f} ", transform=ax.get_xaxis_transform(),
            color=REAL_COLOR, va='top', ha='left' if result.real_value <= np.median(null_values) else 'right')
    ax.set_xlabel(f"{result.measure}, mean over dyads")
    ax.set_ylabel('surrogate sets')
    ax.set_title(f"{_method_title(result)}\n{result.measure}: {format_p(result.p_value)}, {result.side}")


def _draw_welch_groups(ax, result):
    """Every random pair and real dyad as a dot, in two rows, with each row's mean."""
    jitter = np.random.default_rng(0)       # fixed, so that a figure of the same result looks the same
    rows = [
        ('random pairs', _without_flat_windows(result.null_values), SURROGATE_DARK_COLOR),
        ('real dyads', np.asarray(result.real_values, dtype=float), REAL_COLOR),
    ]
    for row, (label, values, color) in enumerate(rows):
        ax.scatter(values, row + jitter.uniform(-0.15, 0.15, len(values)), s=36, color=color, alpha=0.6,
                   edgecolors='white', linewidths=0.8, label=f"{label} (n = {len(values)})")
        if len(values):
            ax.plot([values.mean()] * 2, [row - 0.3, row + 0.3], color=color, linewidth=2.5)
    ax.set_yticks([0, 1], [label for label, _, _ in rows])
    ax.set_ylim(-0.6, 1.6)
    ax.set_xlabel(result.measure)
    t_text = "t = -" if result.t_statistic != result.t_statistic else f"t = {result.t_statistic:.2f}"
    ax.set_title(f"{_method_title(result)}\n{result.measure}: {t_text}, {format_p(result.p_value)}, {result.side}")
    ax.grid(axis='x', color='#e6e6e6')
    ax.set_axisbelow(True)


def _draw_dyad_tests(ax, result):
    """One row per dyad: the middle 95% of its shuffled versions, and its real value, filled if p < 0.05."""
    n = len(result.dyad_names)
    rows = np.arange(n)[::-1]       # the first dyad at the top
    row_points = DYAD_PANEL_POINTS / n
    bar_width = float(np.clip(row_points * 0.45, 1.5, 6))
    marker_size = float(np.clip(row_points * 0.6, 3, 8))
    for row, value, null_values, p_value in zip(rows, result.real_values, result.dyad_null_values, result.dyad_p_values):
        null_values = _without_flat_windows(null_values)
        low, high = np.percentile(null_values, [2.5, 97.5])
        ax.plot([low, high], [row, row], color=SURROGATE_COLOR, linewidth=bar_width, solid_capstyle='round')
        ax.plot([np.median(null_values)] * 2, [row - 0.3, row + 0.3], color=SURROGATE_DARK_COLOR, linewidth=1)
        significant = p_value < SIGNIFICANCE_LEVEL
        ax.plot(value, row, 'o', markersize=marker_size, color=REAL_COLOR,
                markerfacecolor=REAL_COLOR if significant else 'white', markeredgewidth=min(1.8, marker_size / 4))

    # dyad names on the left, p-values on the right. Many dyads get smaller text, and beyond MAX_DYAD_LABELS only
    # every n-th is named, so that the labels never overlap.
    every = -(-n // MAX_DYAD_LABELS)
    labelled = list(range(0, n, every))
    text = {'fontsize': 'x-small' if n >= MANY_DYADS else 'medium'}
    ax.set_ylim(-0.7, n - 0.3)
    ax.set_yticks(rows[labelled], [result.dyad_names[i] for i in labelled], **text)
    p_axis = ax.twinx()
    p_axis.set_ylim(ax.get_ylim())
    p_axis.set_yticks(rows[labelled], [format_p(result.dyad_p_values[i]) for i in labelled], **text)
    for label, i in zip(p_axis.get_yticklabels(), labelled):
        label.set_color('black' if result.dyad_p_values[i] < SIGNIFICANCE_LEVEL else SURROGATE_DARK_COLOR)
    p_axis.tick_params(length=0)

    ax.set_xlabel(result.measure)
    n_significant = sum(p < SIGNIFICANCE_LEVEL for p in result.dyad_p_values)
    ax.set_title(
        f"Each dyad vs. its own shuffled versions: {n_significant} of {n} with p < {SIGNIFICANCE_LEVEL}\n"
        f"grey: middle 95% of shuffled versions, | their median, ● real p < {SIGNIFICANCE_LEVEL}, ○ real p ≥ {SIGNIFICANCE_LEVEL}",
        fontsize='medium',
    )
    ax.grid(axis='x', color='#e6e6e6')
    ax.set_axisbelow(True)


def plot_surrogate_result(result):
    """
    The figure of a surrogates.SurrogateResult: the group test, and for shuffled blocks also each dyad's test.
    Welch compares single random pairs with the real dyads, so it shows both groups' values instead.
    """
    from surrogates import BLOCKS, WELCH
    fig = Figure(figsize=SCALING_PARAMS['FIGSIZE'], dpi=SCALING_PARAMS['DPI'], layout='constrained')
    if result.method == WELCH:
        _draw_welch_groups(fig.add_subplot(), result)
    elif result.method == BLOCKS:
        gs = gridspec.GridSpec(2, 1, height_ratios=[1, 2 if len(result.dyad_names) < MANY_DYADS else 3], figure=fig)
        _draw_surrogate_sets(fig.add_subplot(gs[0]), result)
        _draw_dyad_tests(fig.add_subplot(gs[1]), result)
    else:
        _draw_surrogate_sets(fig.add_subplot(), result)
    return fig
