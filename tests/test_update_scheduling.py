"""
Typing must not recompute on every keystroke, and changes that only affect the display must not recompute at all.
"""
import numpy as np
import pytest

import analysis
import callbacks
import corr_plot
import state


class FakeWidget:
    """Stands in for Tk's timer: callbacks only run when the test says the time has passed."""
    def __init__(self):
        self.timers = {}
        self.next_id = 0

    def after(self, delay_ms, callback):
        self.next_id += 1
        self.timers[self.next_id] = (delay_ms, callback)
        return self.next_id

    def after_cancel(self, timer_id):
        del self.timers[timer_id]

    def run_timers(self):
        timers, self.timers = self.timers, {}
        for _, callback in timers.values():
            callback()


class FakeCanvas:
    def __init__(self):
        self.widget = FakeWidget()

    def get_tk_widget(self):
        return self.widget


@pytest.fixture
def app_state(fake_state, monkeypatch):
    """A loaded dyad with valid settings, counting how often each computation and redraw runs."""
    signal = np.convolve(np.random.default_rng(0).normal(size=600), np.ones(9) / 9, mode="same")
    for name, value in {
        "val_INPUT_DATA_VALID": True, "val_CORRELATION_SETTINGS_VALID": True,
        "val_CORRELATION_SETTINGS_VALID_SXC": True, "val_checkbox_windowed_xcorr": True,
        "val_checkbox_standardise": False, "val_checkbox_absolute_corr": False,
        "val_checkbox_absolute_corr_sxc": False, "val_checkbox_average_windows": False,
        "val_checkbox_lag_filter": False, "val_window_size": 150, "val_step_size": 75, "val_max_lag": 30,
        "val_max_lag_sxc": 30, "val_lag_filter_min": -30, "val_lag_filter_max": 30, "val_UPDATE_COUNT": 0,
        "val_data_length": 600,
    }.items():
        getattr(fake_state, name).set(value)
    for key in ("signal_a", "signal_b", "signal_a_std", "signal_b_std"):
        monkeypatch.setitem(state.dat_physiological_data, key, signal)
    monkeypatch.setitem(state.dat_correlation_data, "wxcorr", [])
    monkeypatch.setitem(state.dat_correlation_data, "sxcorr", [])

    fake_state.counts = {"wx": 0, "sx": 0, "plot": 0}
    real_wx, real_sx = analysis.windowed_cross_correlation, analysis.standard_cross_correlation

    def counted(key, function):
        def wrapper(*args, **kwargs):
            fake_state.counts[key] += 1
            return function(*args, **kwargs)
        return wrapper

    def count_plot():
        fake_state.counts["plot"] += 1

    monkeypatch.setattr(analysis, "windowed_cross_correlation", counted("wx", real_wx))
    monkeypatch.setattr(analysis, "standard_cross_correlation", counted("sx", real_sx))
    monkeypatch.setattr(corr_plot, "update_plot", count_plot)
    monkeypatch.setattr(corr_plot, "update_canvas", lambda: None)
    monkeypatch.setattr(corr_plot, "canvas", FakeCanvas())
    monkeypatch.setattr(corr_plot, "_pending_update", None)
    monkeypatch.setattr(corr_plot, "_computed_wx_settings", None)
    monkeypatch.setattr(corr_plot, "_computed_sx_settings", None)
    monkeypatch.setattr(state, "update_is_debounced", False)
    fake_state.val_UPDATE_COUNT.set = _triggering_schedule(fake_state.val_UPDATE_COUNT)
    return fake_state


def _triggering_schedule(var):
    def set_and_schedule(value):
        var.value = value
        corr_plot.schedule_update()
    return set_and_schedule


def _timers():
    return corr_plot.canvas.widget.timers


def _settle(app_state):
    """Lets the first computation finish and resets the counters."""
    corr_plot.UPDATE()
    app_state.counts.update(wx=0, sx=0, plot=0)


def test_repeated_changes_run_one_update(app_state):
    for _ in range(5):
        state.PARAMS_CHANGED()
    assert len(_timers()) == 1
    corr_plot.canvas.widget.run_timers()
    assert app_state.counts["plot"] == 1


def test_typing_waits_for_a_pause_and_other_changes_do_not(app_state):
    state.PARAMS_CHANGED(debounce=True)
    assert [delay for delay, _ in _timers().values()] == [corr_plot.UPDATE_DEBOUNCE_MS]
    state.PARAMS_CHANGED()
    assert [delay for delay, _ in _timers().values()] == [0]


@pytest.mark.parametrize("handler, input_var, value", [
    (callbacks.on_window_size_input_change, "val_window_size_input", "160"),
    (callbacks.on_step_size_input_change, "val_step_size_input", "60"),
    (callbacks.on_max_lag_input_change, "val_max_lag_input", "20"),
    (callbacks.on_max_lag_input_change_sxc, "val_max_lag_input_sxc", "20"),
    (callbacks.on_min_lag_input_change, "val_lag_filter_min_input", "-5"),
    (callbacks.on_max_lag_filter_input_change, "val_lag_filter_max_input", "5"),
])
def test_typing_in_any_field_is_debounced(app_state, handler, input_var, value):
    app_state.val_lag_filter_min_input.set("-30")
    app_state.val_lag_filter_max_input.set("30")
    getattr(app_state, input_var).set(value)
    handler(None, None, None)
    assert [delay for delay, _ in _timers().values()] == [corr_plot.UPDATE_DEBOUNCE_MS]


@pytest.mark.parametrize("change", [
    lambda s: s.val_CURRENT_TAB.set("Correlation"),
    lambda s: s.val_checkbox_show_sigmoid_correlations.set(True),
])
def test_display_changes_redraw_without_recomputing(app_state, change):
    _settle(app_state)
    change(app_state)
    corr_plot.UPDATE()
    assert app_state.counts == {"wx": 0, "sx": 0, "plot": 1}


@pytest.mark.parametrize("var, value", [
    ("val_window_size", 160), ("val_step_size", 60), ("val_max_lag", 20),
    ("val_checkbox_absolute_corr", True), ("val_checkbox_average_windows", True),
    ("val_checkbox_lag_filter", True), ("val_lag_filter_min", -5), ("val_lag_filter_max", 5),
    ("val_checkbox_standardise", True),
])
def test_every_windowed_setting_recomputes(app_state, var, value):
    _settle(app_state)
    getattr(app_state, var).set(value)
    corr_plot.UPDATE()
    assert app_state.counts["wx"] == 1


@pytest.mark.parametrize("var, value", [
    ("val_max_lag_sxc", 20), ("val_checkbox_absolute_corr_sxc", True), ("val_checkbox_standardise", True),
])
def test_every_standard_setting_recomputes(app_state, var, value):
    app_state.val_checkbox_windowed_xcorr.set(False)
    _settle(app_state)
    getattr(app_state, var).set(value)
    corr_plot.UPDATE()
    assert app_state.counts["sx"] == 1


@pytest.mark.parametrize("windowed", [True, False])
def test_new_data_recomputes_with_unchanged_settings(app_state, windowed):
    app_state.val_checkbox_windowed_xcorr.set(windowed)
    _settle(app_state)
    callbacks.clear_correlation_data()
    corr_plot.UPDATE()
    assert app_state.counts["wx" if windowed else "sx"] == 1


def test_switching_correlation_type_keeps_both_results(app_state):
    _settle(app_state)
    app_state.val_checkbox_windowed_xcorr.set(False)
    corr_plot.UPDATE()
    app_state.val_checkbox_windowed_xcorr.set(True)
    corr_plot.UPDATE()
    assert app_state.counts["wx"] == 0
    assert app_state.counts["sx"] == 1


def test_invalid_settings_do_not_compute_or_count_as_computed(app_state):
    _settle(app_state)
    app_state.val_window_size.set(160)
    app_state.val_CORRELATION_SETTINGS_VALID.set(False)
    corr_plot.UPDATE()
    assert app_state.counts["wx"] == 0
    app_state.val_CORRELATION_SETTINGS_VALID.set(True)
    corr_plot.UPDATE()
    assert app_state.counts["wx"] == 1


def test_failed_computation_is_retried(app_state, monkeypatch):
    _settle(app_state)
    app_state.val_window_size.set(160)

    def fail(*args, **kwargs):
        raise RuntimeError

    working = analysis.windowed_cross_correlation
    monkeypatch.setattr(analysis, "windowed_cross_correlation", fail)
    with pytest.raises(RuntimeError):
        corr_plot.UPDATE()
    monkeypatch.setattr(analysis, "windowed_cross_correlation", working)
    corr_plot.UPDATE()

    assert app_state.counts["wx"] == 1


def test_flush_runs_a_pending_update_now_and_only_once(app_state):
    _settle(app_state)
    app_state.val_window_size.set(160)
    state.PARAMS_CHANGED(debounce=True)

    corr_plot.flush_update()

    assert app_state.counts["wx"] == 1
    assert _timers() == {}
    assert state.dat_correlation_data["wxcorr"][0]["center_idx"] == 80
    corr_plot.flush_update()
    assert app_state.counts["plot"] == 1


@pytest.mark.parametrize("export", [callbacks.export_data, callbacks.export_plot])
def test_export_writes_results_for_settings_typed_just_before(app_state, monkeypatch, export):
    _settle(app_state)
    app_state.val_window_size.set(160)
    state.PARAMS_CHANGED(debounce=True)
    seen = []
    monkeypatch.setattr(
        callbacks.filedialog, "asksaveasfilename",
        lambda **kwargs: seen.append(app_state.counts["wx"]) or "",
    )
    app_state.val_selected_dyad_dir.set("")
    monkeypatch.setitem(state.dat_plot_data, "fig", object())

    export()

    assert seen == [1]
