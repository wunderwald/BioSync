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
    assert max(bar.get_width() for bar in tau_bars) == pytest.approx(1)
    assert sorted(bar.get_x() + 0.5 for bar in tau_bars) == sorted(set(tau_values))     # each lag has its own bar
