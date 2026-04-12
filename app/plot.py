import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.colors as mcolors
import numpy as np

# Custom diverging colormap
_cmap_wxc = mcolors.LinearSegmentedColormap.from_list(
    'wxc_diverging',
    [
        (0.0, "#ffc6e6"),  
        (0.5, '#000000'),  
        (1.0, "#cdff9b"),  
    ]
)

SCALING_PARAMS = {
    'FIGSIZE': (5, 4),
    'DPI': 100,
}

def plot_init(is_retina):
    # rcParams — font/line sizes depend on display type, not on window size
    if is_retina:
        plt.rcParams.update({
            'font.size': 6,
            'axes.titlesize': 4,
            'axes.labelsize': 4,
            'xtick.labelsize': 4,
            'ytick.labelsize': 4,
            'lines.linewidth': 1,
        })
    else:
        plt.rcParams.update({
            'font.size': 12,
            'axes.titlesize': 8,
            'axes.labelsize': 8,
            'xtick.labelsize': 8,
            'ytick.labelsize': 8,
            'lines.linewidth': 2,
        })
    # Default figsize — the canvas resize handler will set the real size at draw time
    fig = plt.figure(figsize=SCALING_PARAMS['FIGSIZE'], dpi=SCALING_PARAMS['DPI'])
    return fig

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
    fig = plt.figure(figsize=SCALING_PARAMS['FIGSIZE'], dpi=SCALING_PARAMS['DPI'], layout='constrained')
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
    ax1.set_title('Peak (positive) correlation per window')
    ax1.grid()
    num_bins_r_max = min(len(r_max_values)//3, 40)
    ax1_hist = fig.add_subplot(ax1_gs_inner[1])
    ax1_hist.hist(r_max_values, bins=num_bins_r_max, orientation='vertical', color='black', alpha=1)
    ax1_hist.set_xlim(-1, 1)

    # Plot corresponding lags over time
    ax2_gs_inner = gridspec.GridSpecFromSubplotSpec(1, 2, subplot_spec=gs[2], width_ratios=[6, 1], wspace=.1)
    ax2 = fig.add_subplot(ax2_gs_inner[0])
    ax2.plot(window_start_indices, tau_max_values, marker='o', markersize=.8, color='black', label='Lag of peak')
    ax2.set_ylabel('tau_max')
    ax2.set_title('Lag of peak (positive) correlation per window')
    ax2.grid()
    num_bins_tau_max = min(len(tau_max_values)//4, max_lag)
    ax2_hist = fig.add_subplot(ax2_gs_inner[1])
    ax2_hist.hist(tau_max_values, bins=num_bins_tau_max, orientation='vertical', color='black', alpha=1)
    ax2_hist.set_xlim(-max_lag, max_lag)

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
    fig = plt.figure(figsize=SCALING_PARAMS['FIGSIZE'], dpi=SCALING_PARAMS['DPI'], layout='constrained')
    gs = gridspec.GridSpec(3, 1, height_ratios=[3, 1, 1], figure=fig)

    # Plot cross-correlation
    ax2 = fig.add_subplot(gs[0])
    ax2.plot(lags, corr, marker='o', markersize=1.5, color='black')
    ax2.set_xlabel('Lag')
    ax2.set_ylabel('Cross-correlation')
    ax2.set_title('Standard Cross-correlation')
    ax2.grid()

    # Plot input signal a over time
    ax1 = fig.add_subplot(gs[1])
    ax1.plot(signal_a, label='Signal a', color='blue')
    ax1.set_xlabel('Index')
    ax1.set_ylabel('Signal a')
    ax1.grid()

    # Plot input signal b over time
    ax1 = fig.add_subplot(gs[2])
    ax1.plot(signal_b, label='Signal b', color='purple')
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
    fig = plt.figure(figsize=SCALING_PARAMS['FIGSIZE'], dpi=SCALING_PARAMS['DPI'], layout='constrained')
    gs = gridspec.GridSpec(2, 1, figure=fig)
    
    # Plot signal_a
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(signal_a, color='blue')
    ax1.set_title(plot_titles['a'])
    ax1.set_xlabel('Index')
    ax1.set_ylabel('Value')
    ax1.grid()
    
    # Plot signal_b
    ax2 = fig.add_subplot(gs[1])
    ax2.plot(signal_b, color='purple')
    ax2.set_title(plot_titles['b'])
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
    #plt.close(fig)