"""
Settings validity depends on the loaded data, and on what is currently typed into the lag filter fields.
"""
import numpy as np
import pytest

import callbacks
import plot
import state
import validation
from cross_correlation import windowed_cross_correlation


@pytest.fixture
def settings(fake_state):
    fake_state.val_checkbox_windowed_xcorr.set(True)
    fake_state.val_checkbox_lag_filter.set(False)
    fake_state.val_data_length.set(1000)
    fake_state.val_window_size.set(150)
    fake_state.val_step_size.set(75)
    fake_state.val_max_lag.set(30)
    fake_state.val_max_lag_sxc.set(150)
    fake_state.val_lag_filter_min.set(-30)
    fake_state.val_lag_filter_max.set(30)
    fake_state.val_lag_filter_min_input.set("-30")
    fake_state.val_lag_filter_max_input.set("30")
    fake_state.val_UPDATE_COUNT.set(0)
    return fake_state


@pytest.fixture
def loaded_columns(settings, monkeypatch):
    """A selected dyad with two long enough columns, ready for preprocess_data."""
    ibi = list(800 + 50 * np.random.default_rng(0).normal(size=400))
    settings.val_selected_sheet.set("IBI Series")
    settings.val_selected_column.set("IBI_ms")
    settings.val_checkbox_eb.set(True)
    monkeypatch.setitem(state.dat_workbook_data, "columns_a", {"IBI_ms": [500, *ibi, 300]})
    monkeypatch.setitem(state.dat_workbook_data, "columns_b", {"IBI_ms": [500, *ibi, 300]})
    for key in ("raw_signal_a", "raw_signal_b", "signal_a", "signal_b", "signal_a_std", "signal_b_std"):
        monkeypatch.setitem(state.dat_physiological_data, key, [])
    monkeypatch.setitem(state.dat_plot_data, "fig", None)
    return settings


@pytest.mark.parametrize("text, expected", [
    ("", True), ("0", True), ("30", True),
    ("-", False), ("-30", False), ("3.5", False), ("a", False),
])
def test_numeric_input(text, expected):
    assert validation.is_numeric_input(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("", True), ("-", True), ("-3", True), ("-30", True), ("30", True),
    ("--3", False), ("3-", False), ("-3.5", False), ("a", False),
])
def test_signed_numeric_input(text, expected):
    assert validation.is_signed_numeric_input(text) == expected


def test_window_size_typed_before_loading_becomes_valid_after_loading(loaded_columns):
    loaded_columns.val_data_length.set(0)
    validation.check_wx_correlation_settings()
    assert not loaded_columns.val_CORRELATION_SETTINGS_VALID.get()

    callbacks.preprocess_data()

    assert loaded_columns.val_CORRELATION_SETTINGS_VALID.get()


def test_window_size_longer_than_loaded_data_becomes_invalid(loaded_columns):
    loaded_columns.val_window_size.set(100000)
    validation.check_wx_correlation_settings()

    callbacks.preprocess_data()

    assert not loaded_columns.val_WINDOW_SIZE_VALID.get()
    assert not loaded_columns.val_CORRELATION_SETTINGS_VALID.get()


def test_standard_max_lag_is_checked_against_loaded_data(loaded_columns):
    loaded_columns.val_max_lag_sxc.set(100000)
    callbacks.preprocess_data()
    assert not loaded_columns.val_CORRELATION_SETTINGS_VALID_SXC.get()


def test_validation_does_not_trigger_a_recompute(settings):
    validation.check_all_settings()
    assert settings.val_UPDATE_COUNT.get() == 0


def test_data_that_fails_preprocessing_is_marked_invalid(loaded_columns, monkeypatch):
    state.dat_workbook_data["columns_a"]["IBI_ms"] = [0, 800, 800, 300]
    state.dat_workbook_data["columns_b"]["IBI_ms"] = [100000, 800, 800, 300]
    monkeypatch.setattr(state, "RETINA", False)
    loaded_columns.val_INPUT_DATA_VALID.set(True)

    callbacks.preprocess_data()

    assert not loaded_columns.val_INPUT_DATA_VALID.get()
    assert state.dat_physiological_data["signal_a"] == []
    assert "do not overlap" in loaded_columns.val_input_error.get()


def test_lag_filter_checkbox_recomputes(settings):
    settings.val_checkbox_lag_filter.set(True)
    callbacks.on_lag_filter_checkbox_change()
    assert settings.val_UPDATE_COUNT.get() == 1


def test_unticking_lag_filter_clears_its_error(settings):
    settings.val_checkbox_lag_filter.set(True)
    settings.val_lag_filter_min_input.set("")
    validation.check_wx_correlation_settings()
    assert not settings.val_LAG_FILTER_VALID.get()

    settings.val_checkbox_lag_filter.set(False)
    validation.check_wx_correlation_settings()

    assert settings.val_LAG_FILTER_VALID.get()
    assert settings.val_CORRELATION_SETTINGS_VALID.get()


@pytest.mark.parametrize("handler, field, value", [
    (callbacks.on_min_lag_input_change, "val_lag_filter_min", -30),
    (callbacks.on_max_lag_filter_input_change, "val_lag_filter_max", 30),
])
@pytest.mark.parametrize("typed", ["", "-"])
def test_editing_a_lag_filter_field_leaves_it_alone(settings, handler, field, value, typed):
    settings.val_checkbox_lag_filter.set(True)
    input_var = getattr(settings, f"{field}_input")
    input_var.set(typed)

    handler(None, None, None)

    assert input_var.get() == typed                     # not overwritten with 0 while typing
    assert getattr(settings, field).get() == value
    assert not settings.val_CORRELATION_SETTINGS_VALID.get()


def test_typing_a_negative_lag_filter_limit(settings):
    settings.val_checkbox_lag_filter.set(True)
    for typed in ("-", "-1", "-12"):
        settings.val_lag_filter_min_input.set(typed)
        callbacks.on_min_lag_input_change(None, None, None)
    assert settings.val_lag_filter_min.get() == -12
    assert settings.val_CORRELATION_SETTINGS_VALID.get()


def test_negative_max_lag_filter_limit_is_accepted(settings):
    settings.val_checkbox_lag_filter.set(True)
    settings.val_lag_filter_max_input.set("-5")
    callbacks.on_max_lag_filter_input_change(None, None, None)
    assert settings.val_lag_filter_max.get() == -5
    assert settings.val_CORRELATION_SETTINGS_VALID.get()


@pytest.mark.parametrize("windowed, wx_valid, sx_valid, expected", [
    (True, True, False, True),
    (True, False, True, False),
    (False, False, True, True),
    (False, True, False, False),
])
def test_batch_and_random_pairs_only_need_the_active_settings(settings, windowed, wx_valid, sx_valid, expected):
    settings.val_checkbox_windowed_xcorr.set(windowed)
    settings.val_INPUT_DATA_VALID.set(True)
    settings.val_CORRELATION_SETTINGS_VALID.set(wx_valid)
    settings.val_CORRELATION_SETTINGS_VALID_SXC.set(sx_valid)
    settings.val_batch_input_folder.set("in")
    settings.val_batch_output_folder.set("out")
    settings.val_random_pair_input_folder.set("in")
    settings.val_random_pair_output_file.set("out.xlsx")

    callbacks._batch_processing_is_ready()
    callbacks._random_pair_is_ready()

    assert settings.val_batch_processing_is_ready.get() == expected
    assert settings.val_random_pair_is_ready.get() == expected


@pytest.mark.parametrize("n_windows", [1, 2, 3, 4, 8])
def test_plot_handles_few_windows(n_windows):
    signal = np.convolve(np.random.default_rng(0).normal(size=1000), np.ones(9) / 9, mode="same")
    length = 150 + 75 * (n_windows - 1)
    windows = windowed_cross_correlation(signal[:length], np.roll(signal, 3)[:length], 150, 75, 30)
    assert len(windows) == n_windows
    plot.plot_windowed_cross_correlation(windows, 150, 30, 75, signal, signal)
