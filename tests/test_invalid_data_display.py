"""
When data can't be used, the window must say why, and must not show or keep anything computed from older data.
"""
import numpy as np
import pytest

import callbacks
import corr_plot
import gui_updates
import state
from helpers import FakeWidget


@pytest.fixture
def data(fake_state, monkeypatch):
    """A loaded dyad with an IBI, a text and a too-short column, with results from an earlier load."""
    ibi = [500, *(800 + 50 * np.random.default_rng(0).normal(size=400)), 300]
    columns = {"IBI": ibi, "Text": ["a"] * 10, "Gap": [800, None, 800], "Short": [0, 800, 800, 300]}
    columns_b = {**columns, "Short": [100000, 800, 800, 300]}
    monkeypatch.setitem(state.dat_workbook_data, "workbook_a", {"S": []})
    monkeypatch.setitem(state.dat_workbook_data, "workbook_b", {"S": []})
    monkeypatch.setitem(state.dat_workbook_data, "columns_a", columns)
    monkeypatch.setitem(state.dat_workbook_data, "columns_b", columns_b)
    for key in ("raw_signal_a", "raw_signal_b", "signal_a", "signal_b", "signal_a_std", "signal_b_std"):
        monkeypatch.setitem(state.dat_physiological_data, key, [1.0, 2.0])
    for key, value in (("wxcorr", [{}]), ("sxcorr", {"corr": []}), ("dfa_signals", {"alpha_a": 1}), ("dfa_windows", {"x": 1})):
        monkeypatch.setitem(state.dat_correlation_data, key, value)
    monkeypatch.setattr(callbacks.validation, "check_all_settings", lambda: None)
    fake_state.val_selected_sheet.set("S")
    fake_state.val_checkbox_eb.set(True)
    fake_state.val_INPUT_DATA_VALID.set(True)
    fake_state.val_input_error.set("")
    return fake_state


def _assert_cleared():
    assert all(state.dat_physiological_data[key] == [] for key in ("signal_a", "signal_b", "raw_signal_a"))
    assert state.dat_correlation_data["wxcorr"] == [] and state.dat_correlation_data["sxcorr"] == []
    assert state.dat_correlation_data["dfa_signals"] is None and state.dat_correlation_data["dfa_windows"] is None


@pytest.mark.parametrize("sheet, column, reason", [
    ("S", "Text", "contains values that aren't numbers"),
    ("S", "Gap", "contains values that aren't numbers, or empty cells"),
    ("S", "Short", "do not overlap"),
    ("S", "- None -", "no column with the same name in sheet 'S'"),
    ("- None -", "IBI", "no sheet with the same name"),
])
def test_invalid_data_is_cleared_and_says_why(data, sheet, column, reason):
    data.val_selected_sheet.set(sheet)
    data.val_selected_column.set(column)
    callbacks.preprocess_data()
    assert data.val_INPUT_DATA_VALID.get() is False
    assert reason in data.val_input_error.get()
    _assert_cleared()


def test_nothing_loaded_has_no_reason(data, monkeypatch):
    monkeypatch.setitem(state.dat_workbook_data, "workbook_a", None)
    data.val_selected_sheet.set("- None -")
    callbacks.preprocess_data()
    assert data.val_input_error.get() == ""
    _assert_cleared()


def test_valid_data_clears_the_reason(data):
    data.val_input_error.set("old reason")
    data.val_selected_column.set("IBI")
    callbacks.preprocess_data()
    assert data.val_INPUT_DATA_VALID.get() is True and data.val_input_error.get() == ""
    assert len(state.dat_physiological_data["signal_a"]) > 100


NORMAL_COLORS = {'fg_color': 'grey', 'button_color': 'darkgrey', 'button_hover_color': 'black'}


def _colors(widget):
    return {name: widget.cget(name) for name in NORMAL_COLORS}


@pytest.fixture
def widgets(fake_state, monkeypatch):
    widgets = {
        'dropdown_select_sheet': FakeWidget(**NORMAL_COLORS), 'dropdown_select_column': FakeWidget(**NORMAL_COLORS),
        'error_label_input_data': FakeWidget(),
    }
    monkeypatch.setattr(gui_updates, "_w", widgets)
    monkeypatch.setattr(gui_updates, "_normal_dropdown_colors", {})
    return widgets


def test_reason_turns_the_dropdowns_red_and_shows_it(fake_state, widgets):
    fake_state.val_input_error.set("Column 'Text' contains values that aren't numbers.")
    gui_updates.update_input_data_validation_error()
    assert _colors(widgets['dropdown_select_sheet']) == gui_updates.INVALID_DROPDOWN_COLORS
    assert _colors(widgets['dropdown_select_column']) == gui_updates.INVALID_DROPDOWN_COLORS
    assert widgets['error_label_input_data'].visible
    assert widgets['error_label_input_data'].text == "Data is invalid: Column 'Text' contains values that aren't numbers."


def test_valid_data_restores_the_normal_colors(fake_state, widgets):
    fake_state.val_input_error.set("reason")
    gui_updates.update_input_data_validation_error()
    fake_state.val_input_error.set("")
    gui_updates.update_input_data_validation_error()
    assert _colors(widgets['dropdown_select_column']) == NORMAL_COLORS
    assert not widgets['error_label_input_data'].visible


def _figure_text(fig):
    return " ".join(text.get_text() for text in fig.texts)


@pytest.fixture
def plotting(fake_state, monkeypatch):
    monkeypatch.setitem(state.dat_plot_data, "fig", "old figure")
    monkeypatch.setattr(state, "RETINA", True)
    fake_state.val_CORRELATION_SETTINGS_VALID.set(True)
    fake_state.val_CORRELATION_SETTINGS_VALID_SXC.set(True)
    monkeypatch.setitem(state.dat_correlation_data, "wxcorr", [])
    monkeypatch.setitem(state.dat_correlation_data, "sxcorr", [])
    return fake_state


@pytest.mark.parametrize("windowed", [True, False])
def test_invalid_data_replaces_the_correlation_plot_with_the_reason(plotting, windowed):
    plotting.val_CURRENT_TAB.set("Correlation")
    plotting.val_checkbox_windowed_xcorr.set(windowed)
    plotting.val_INPUT_DATA_VALID.set(False)
    plotting.val_input_error.set("The two recordings do not overlap in time.")
    corr_plot.update_plot()
    assert _figure_text(state.dat_plot_data["fig"]) == "No results: The two recordings do not overlap in time."


@pytest.mark.parametrize("windowed, var", [(True, "val_CORRELATION_SETTINGS_VALID"), (False, "val_CORRELATION_SETTINGS_VALID_SXC")])
def test_invalid_settings_replace_the_plot_instead_of_keeping_another(plotting, windowed, var):
    plotting.val_CURRENT_TAB.set("Correlation")
    plotting.val_checkbox_windowed_xcorr.set(windowed)
    plotting.val_INPUT_DATA_VALID.set(True)
    getattr(plotting, var).set(False)
    corr_plot.update_plot()
    assert "check the correlation settings" in _figure_text(state.dat_plot_data["fig"])


def test_invalid_data_shows_its_reason_on_the_input_tab(plotting):
    plotting.val_CURRENT_TAB.set("Input Data")
    plotting.val_INPUT_DATA_VALID.set(False)
    plotting.val_input_error.set("Column 'Text' contains values that aren't numbers.")
    corr_plot.update_plot()
    assert _figure_text(state.dat_plot_data["fig"]) == "Column 'Text' contains values that aren't numbers."


def test_nothing_loaded_shows_an_empty_input_plot(plotting):
    plotting.val_CURRENT_TAB.set("Input Data")
    plotting.val_INPUT_DATA_VALID.set(False)
    plotting.val_input_error.set("")
    corr_plot.update_plot()
    assert _figure_text(state.dat_plot_data["fig"]) == ""


def test_dfa_text_doesnt_show_results_for_invalid_settings(plotting, monkeypatch):
    plotting.val_checkbox_windowed_xcorr.set(True)
    plotting.val_CORRELATION_SETTINGS_VALID.set(False)
    monkeypatch.setitem(state.dat_correlation_data, "dfa_signals", {'alpha_a': 1.0, 'alpha_b': 1.0, 'note': None})
    monkeypatch.setitem(state.dat_correlation_data, "dfa_windows", {'alpha_window_averages': 0.7, 'alpha_per_lag': [], 'note': None})
    corr_plot.update_dfa_text()
    assert "0.70" not in plotting.val_dfa_text.get()
    assert "Check the correlation settings." in plotting.val_dfa_text.get()


@pytest.mark.parametrize("r_max, tau_max", [(0.5, 3), (1.0000000000000002, 0), (-1.2, -30)])
def test_plot_handles_windows_with_almost_equal_values(r_max, tau_max):
    import io
    import plot
    windows = [
        {'start_idx': index * 75, 'center_idx': index * 75 + 75, 'correlations': [r_max + index * 1e-17] * 61,
         'correlations_sigmoid': [0.1] * 61, 'r_max': r_max + index * 1e-17, 'tau_max': tau_max,
         'r_max_sigmoid': 0.1, 'tau_max_sigmoid': tau_max}
        for index in range(30)
    ]
    plot.plot_windowed_cross_correlation(windows, 150, 30, 75, [0.0] * 2400, [0.0] * 2400).savefig(io.BytesIO())


def _histogram_bars(fig):
    """The bars of the r_max and tau_max histograms: the axes with bars and no lines."""
    import matplotlib.patches as mpatches
    bars = [[p for p in ax.patches if isinstance(p, mpatches.Rectangle) and p.get_height() > 0] for ax in fig.axes]
    return [axis_bars for ax, axis_bars in zip(fig.axes, bars) if axis_bars and not ax.lines]


@pytest.mark.parametrize("tau_values", [[0] * 7, [3] * 7, [-30, 30] * 4])
def test_histograms_have_narrow_bars_however_few_values_differ(tau_values):
    import plot
    windows = [
        {'start_idx': index * 75, 'center_idx': index * 75 + 75, 'correlations': [0.97] * 61, 'correlations_sigmoid': [0.9] * 61,
         'r_max': 0.95 + index * 0.005, 'tau_max': tau, 'r_max_sigmoid': 0.9, 'tau_max_sigmoid': tau}
        for index, tau in enumerate(tau_values)
    ]
    fig = plot.plot_windowed_cross_correlation(windows, 150, 30, 75, [0.0] * 800, [0.0] * 800)
    r_max_bars, tau_bars = _histogram_bars(fig)
    assert max(bar.get_width() for bar in r_max_bars) == pytest.approx(plot.R_MAX_BIN_WIDTH)
    assert max(bar.get_width() for bar in tau_bars) == pytest.approx(3)       # lags -30 to 30 in bins of 3
    centres = {round(bar.get_x() + bar.get_width() / 2) for bar in tau_bars}
    assert centres == {3 * round(tau / 3) for tau in tau_values}             # bins are centred on lags, 0 included


@pytest.mark.parametrize("min_lag, max_lag, width", [(-30, 30, 3), (-5, 10, 1), (-100, 100, 11), (0, 40, 3)])
def test_lag_bins_are_an_odd_number_of_lags_wide(min_lag, max_lag, width):
    import plot
    assert plot._lag_bin_width(min_lag, max_lag) == width
    edges = plot._hist_bins([], min_lag, max_lag, width, centred=True)
    assert edges[0] <= min_lag and edges[-1] >= max_lag     # every lag in the range has a bin
    assert np.allclose(np.diff(edges), width)
    if min_lag <= 0 <= max_lag:
        assert any(np.isclose(edges, -width / 2))          # a bin from -width/2 to width/2, centred on 0


def test_histograms_count_every_window_also_beyond_the_axis_range():
    import plot
    values = [(-1.2, -30), (1.0000000000000002, 0), (0.5, 3), (1.05, 2)]     # r beyond 1 can come from the estimator
    windows = [
        {'start_idx': index * 75, 'center_idx': index * 75 + 75, 'correlations': [r] * 61, 'correlations_sigmoid': [0.1] * 61,
         'r_max': r, 'tau_max': tau, 'r_max_sigmoid': 0.1, 'tau_max_sigmoid': tau}
        for index, (r, tau) in enumerate(values)
    ]
    fig = plot.plot_windowed_cross_correlation(windows, 150, 30, 75, [0.0] * 600, [0.0] * 600)
    for bars in _histogram_bars(fig):
        assert sum(bar.get_height() for bar in bars) == len(values)


@pytest.mark.parametrize("n_windows", [1, 7, 28])
def test_histogram_axes_mark_zero_and_the_tallest_bar(n_windows):
    import plot
    windows = [
        {'start_idx': index * 75, 'center_idx': index * 75 + 75, 'correlations': [0.5] * 61, 'correlations_sigmoid': [0.4] * 61,
         'r_max': 0.95, 'tau_max': 0, 'r_max_sigmoid': 0.4, 'tau_max_sigmoid': 0}
        for index in range(n_windows)
    ]
    fig = plot.plot_windowed_cross_correlation(windows, 150, 30, 75, [0.0] * 600, [0.0] * 600)
    for bars in _histogram_bars(fig):
        ax = bars[0].axes
        assert list(ax.get_yticks()) == [0, n_windows]
        assert ax.get_ylim()[1] >= n_windows


def test_histogram_axes_of_flat_windows_only_mark_zero():
    import plot
    windows = [
        {'start_idx': 0, 'center_idx': 75, 'correlations': [float('nan')] * 61, 'correlations_sigmoid': [float('nan')] * 61,
         'r_max': float('nan'), 'tau_max': float('nan'), 'r_max_sigmoid': float('nan'), 'tau_max_sigmoid': float('nan')}
    ]
    fig = plot.plot_windowed_cross_correlation(windows, 150, 30, 75, [0.0] * 600, [0.0] * 600)
    histogram_axes = [ax for ax in fig.axes if not ax.lines and not ax.images and ax.get_label() != '<colorbar>']
    assert histogram_axes and all(list(ax.get_yticks()) == [0] for ax in histogram_axes)
