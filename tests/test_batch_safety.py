"""
Batch checks every dyad against the settings, never mixes its results with an earlier run's, and doesn't
read its own output as a dyad. The data type is guessed when new data is chosen.
"""
import itertools
import os

import numpy as np
import openpyxl
import pytest

import analysis
import batch_processing
import callbacks
import state
import validation
from signal_processing import guess_is_event_based
from test_batch import ImmediateTimer, _params, _write_dyad, _write_person


# ---------------------------------------------------------------------------
# THE SAME RULES AS THE APP
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("window, step, max_lag, use_filter, low, high, length", list(itertools.product(
    (0, 1, 50, 150, 400), (0, 1, 75, 150, 151), (0, 1, 25, 75, 76), (False, True), (-30, -5, 10), (-10, 5, 30), (300,),
)))
def test_batch_uses_the_rules_of_the_windowed_settings_fields(fake_state, window, step, max_lag, use_filter, low, high, length):
    for name, value in {
        "val_data_length": length, "val_window_size": window, "val_step_size": step, "val_max_lag": max_lag,
        "val_checkbox_lag_filter": use_filter, "val_lag_filter_min": low, "val_lag_filter_max": high,
        "val_lag_filter_min_input": str(low), "val_lag_filter_max_input": str(high),
    }.items():
        getattr(fake_state, name).set(value)
    app_says_valid = validation.check_wx_correlation_settings()
    config = analysis.AnalysisConfig(
        signal_type='event-based', windowed=True, standardised=False, window_size=window, step_size=step,
        max_lag=max_lag, absolute=False, average_windows=False, use_lag_filter=use_filter, lag_filter_min=low,
        lag_filter_max=high, max_lag_sxc=10, absolute_sxc=False,
    )
    assert (analysis.settings_problem(config, length) is None) == app_says_valid


@pytest.mark.parametrize("max_lag, length", [(0, 10), (9, 10), (10, 10), (11, 10), (-1, 10)])
def test_batch_uses_the_rules_of_the_standard_settings_field(fake_state, max_lag, length):
    fake_state.val_data_length.set(length)
    fake_state.val_max_lag_sxc.set(max_lag)
    config = analysis.AnalysisConfig(
        signal_type='event-based', windowed=False, standardised=False, window_size=1, step_size=1, max_lag=1,
        absolute=False, average_windows=False, use_lag_filter=False, lag_filter_min=0, lag_filter_max=0,
        max_lag_sxc=max_lag, absolute_sxc=False,
    )
    assert (analysis.settings_problem(config, length) is None) == validation.check_sx_correlation_settings()


# ---------------------------------------------------------------------------
# DYADS THAT DON'T FIT THE SETTINGS
# ---------------------------------------------------------------------------

def _write_short_dyad(folder, n_beats=20):
    os.makedirs(folder)
    ibi = 800 + 20 * np.sin(np.arange(n_beats))
    for person, noise in (("P1", 0), ("P2", 3)):
        _write_person(os.path.join(folder, f"{person}.xlsx"), {"Coupled": ibi + noise * np.cos(np.arange(n_beats))})


@pytest.mark.parametrize("windowed", [True, False])
def test_short_dyad_is_skipped_with_the_reason_and_leaves_no_files(tmp_path, windowed):
    _write_dyad(tmp_path / "in" / "long", seed=0)
    _write_short_dyad(tmp_path / "in" / "short")
    (tmp_path / "out").mkdir()
    summary = batch_processing.batch_process(_params(tmp_path / "in", tmp_path / "out", checkbox_windowed_xcorr=windowed))
    assert summary['processed'] == ["long"]
    (name, reason), = summary['failed']
    assert name == "short" and "Doesn't fit the settings" in reason and "samples" in reason
    assert not [f for f in os.listdir(tmp_path / "out") if "short" in f]


def test_random_pairs_skip_pairs_that_dont_fit(tmp_path):
    for index in range(2):
        _write_dyad(tmp_path / "in" / f"long{index}", seed=index)
    _write_short_dyad(tmp_path / "in" / "short")
    result = batch_processing.random_pair_analysis(_params(tmp_path / "in", tmp_path), str(tmp_path / "in"), random_pair_count=30, seed=1)
    failures = result[6]
    assert failures and all("Doesn't fit the settings" in reason for _, reason in failures)
    assert len(result[3]) == 2      # the two long real dyads


def test_failure_while_plotting_leaves_no_files(tmp_path, monkeypatch):
    _write_dyad(tmp_path / "in" / "dyad0", seed=0)
    (tmp_path / "out").mkdir()

    def broken_plot(*args, **kwargs):
        raise RuntimeError("plot failed")

    monkeypatch.setattr(batch_processing, "plot_windowed_cross_correlation", broken_plot)
    summary = batch_processing.batch_process(_params(tmp_path / "in", tmp_path / "out"))
    assert summary['failed'] == [("dyad0", "plot failed")]
    assert os.listdir(tmp_path / "out") == []


# ---------------------------------------------------------------------------
# OUTPUT FOLDER INSIDE THE INPUT FOLDER
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("same_column", [True, False])
def test_output_folder_inside_the_input_is_never_a_dyad(tmp_path, same_column):
    for index in range(2):
        _write_dyad(tmp_path / "study" / f"d{index}", seed=index)
    results = tmp_path / "study" / "results"
    results.mkdir()
    if same_column:     # result files that happen to have the selected column
        for name in ("a.xlsx", "b.xlsx"):
            _write_person(results / name, {"Coupled": 800 + np.arange(1000) % 7})
    for _ in range(2):
        summary = batch_processing.batch_process(_params(tmp_path / "study", results))
        assert summary['processed'] == ["d0", "d1"] and summary['failed'] == []
        assert "results: skipped, because it is the output folder" in summary['warnings']


def test_output_folder_reached_through_another_path_is_recognised(tmp_path):
    _write_dyad(tmp_path / "study" / "d0", seed=0)
    (tmp_path / "study" / "results").mkdir()
    os.symlink(tmp_path / "study" / "results", tmp_path / "link")
    summary = batch_processing.batch_process(_params(tmp_path / "study", tmp_path / "link"))
    assert summary['processed'] == ["d0"]


# ---------------------------------------------------------------------------
# RESULTS OF AN EARLIER RUN
# ---------------------------------------------------------------------------

RESULTS = ["wx_d0_wxcorr.xlsx", "wx_d0_wxcorr.png", "d0_sxcorr.xlsx", "d0_sxcorr.png", "grand_avg_wxcorr.xlsx", "grand_avg_wxcorr.png"]
OTHER = ["notes.xlsx", "wx_d0_wxcorr.xlsx.bak", "my_wxcorr.xlsx", "grand_avg_wxcorr_old.xlsx", "summary.png"]


def test_only_files_a_batch_writes_count_as_earlier_results(tmp_path):
    for name in RESULTS + OTHER:
        (tmp_path / name).write_text("x")
    (tmp_path / "wx_folder_wxcorr.xlsx").mkdir()
    assert batch_processing.find_result_files(str(tmp_path)) == sorted(RESULTS)


def test_missing_output_folder_has_no_earlier_results(tmp_path):
    assert batch_processing.find_result_files(str(tmp_path / "missing")) == []
    assert batch_processing.find_result_files("") == []


@pytest.fixture
def app(fake_state, tmp_path, monkeypatch):
    _write_dyad(tmp_path / "in" / "d0", seed=0)
    (tmp_path / "out").mkdir()
    for name in ("val_INPUT_DATA_VALID", "val_CORRELATION_SETTINGS_VALID", "val_CORRELATION_SETTINGS_VALID_SXC"):
        getattr(fake_state, name).set(True)
    fake_state.val_job_running.set(False)
    fake_state.val_job_progress.set(0)
    fake_state.timer = ImmediateTimer()
    monkeypatch.setitem(callbacks._tabview, "tabview", fake_state.timer)
    monkeypatch.setattr(callbacks, "_analysis_params", lambda: _params(tmp_path / "in", tmp_path / "out"))
    fake_state.asked = []
    fake_state.answer = True
    monkeypatch.setattr(callbacks.messagebox, "askyesno", lambda title, text: fake_state.asked.append(text) or fake_state.answer)
    monkeypatch.setattr(callbacks.messagebox, "showinfo", lambda title, text: None)
    fake_state.out = tmp_path / "out"
    return fake_state


def _put_earlier_results(folder):
    for name in RESULTS + OTHER:
        (folder / name).write_text("earlier run")


def test_empty_output_folder_starts_without_asking(app):
    callbacks.handle_run_batch_button()
    app.timer.run_until_idle(60)
    assert app.asked == []
    assert (app.out / "wx_d0_wxcorr.xlsx").exists()


def test_earlier_results_are_deleted_when_confirmed(app):
    _put_earlier_results(app.out)
    callbacks.handle_run_batch_button()
    app.timer.run_until_idle(60)
    assert "6 files from an earlier run" in app.asked[0]
    assert not (app.out / "d0_sxcorr.xlsx").exists()
    assert (app.out / "wx_d0_wxcorr.xlsx").read_bytes() != b"earlier run"     # written by this run
    assert all((app.out / name).read_text() == "earlier run" for name in OTHER)


def test_declining_keeps_everything_and_doesnt_run(app):
    _put_earlier_results(app.out)
    app.answer = False
    callbacks.handle_run_batch_button()
    assert app.val_job_running.get() is False
    assert all((app.out / name).read_text() == "earlier run" for name in RESULTS + OTHER)


def test_failed_delete_doesnt_run(app, monkeypatch):
    _put_earlier_results(app.out)
    errors = []
    monkeypatch.setattr(callbacks.messagebox, "showerror", lambda title, text: errors.append(title))

    def locked(output_dir, names):
        raise PermissionError("file is open in Excel")

    monkeypatch.setattr(callbacks, "remove_result_files", locked)
    callbacks.handle_run_batch_button()
    assert errors == ["Can't delete earlier results"]
    assert app.val_job_running.get() is False


# ---------------------------------------------------------------------------
# GUESSING THE DATA TYPE
# ---------------------------------------------------------------------------

RNG = np.random.default_rng(0)


def _with_ends(values):
    return [500, *values, 300]


@pytest.mark.parametrize("values, event_based", [
    (800 + 50 * RNG.normal(size=500), True),                       # IBI in ms
    (400 + 20 * RNG.normal(size=500), True),                       # fast heart rate
    (1500 + 50 * RNG.normal(size=500), True),                      # slow heart rate
    (0.8 + 0.05 * RNG.normal(size=500), True),                     # IBI in seconds: unclear, so the default
    (3000 + 100 * RNG.normal(size=500), True),                     # long but possible: unclear, so the default
    (5 + 3 * np.abs(RNG.normal(size=3000)), False),                # EDA in microsiemens
    (33 + 0.1 * RNG.normal(size=3000), False),                     # skin temperature
    (RNG.normal(size=3000), False),                                # a signal with negative values
    (30000 + 100 * RNG.normal(size=3000), False),                  # raw device counts
])
def test_guess(values, event_based):
    assert guess_is_event_based(_with_ends(values), _with_ends(values)) == event_based


def test_first_and_last_value_are_not_used_for_the_guess():
    ibi = list(800 + 50 * RNG.normal(size=500))
    assert guess_is_event_based([-5, *ibi, 0], [99999, *ibi, -1]) is True


def test_one_person_with_negative_values_makes_it_fixed_rate():
    assert guess_is_event_based(_with_ends(800 + 50 * RNG.normal(size=500)), _with_ends(RNG.normal(size=500))) is False


def test_empty_signal_stays_event_based():
    assert guess_is_event_based([500, 300], [500, 300]) is True


@pytest.fixture
def loaded(fake_state, monkeypatch):
    columns = {"IBI": _with_ends(list(800 + 50 * RNG.normal(size=400))), "EDA": list(5 + np.abs(RNG.normal(size=3000))), "Text": ["a"] * 10}
    monkeypatch.setitem(state.dat_workbook_data, "columns_a", columns)
    monkeypatch.setitem(state.dat_workbook_data, "columns_b", columns)
    fake_state.val_checkbox_eb.set(True)
    fake_state.val_checkbox_fr.set(False)
    return fake_state


@pytest.mark.parametrize("column, event_based", [("EDA", False), ("IBI", True)])
def test_choosing_a_column_sets_the_data_type(loaded, column, event_based):
    loaded.val_checkbox_eb.set(not event_based)
    loaded.val_checkbox_fr.set(event_based)
    loaded.val_selected_column.set(column)
    callbacks.guess_signal_type()
    assert loaded.val_checkbox_eb.get() is event_based and loaded.val_checkbox_fr.get() is (not event_based)


def test_non_numeric_column_leaves_the_data_type(loaded):
    loaded.val_checkbox_eb.set(False)
    loaded.val_checkbox_fr.set(True)
    loaded.val_selected_column.set("Text")
    callbacks.guess_signal_type()
    assert loaded.val_checkbox_fr.get() is True


@pytest.mark.parametrize("handler", [
    lambda: callbacks.on_dropdown_select_column_change("EDA"),
    lambda: callbacks.on_dropdown_select_sheet_change("S"),
    lambda: callbacks.on_change_data_has_headers(),
    lambda: callbacks.show_loaded_workbooks(),
])
def test_new_data_is_guessed(loaded, monkeypatch, handler):
    for name in ("update_sheet_names", "update_column_names", "preprocess_data", "clear_correlation_data"):
        monkeypatch.setattr(callbacks, name, lambda: None)
    monkeypatch.setattr(callbacks.state, "PARAMS_CHANGED", lambda: None)
    loaded.val_selected_column.set("EDA")
    loaded.val_checkbox_data_has_headers.set(True)
    handler()
    assert loaded.val_checkbox_fr.get() is True


@pytest.mark.parametrize("handler, ticked", [(callbacks.on_is_eb_change, "val_checkbox_eb"), (callbacks.on_is_fr_change, "val_checkbox_fr")])
def test_ticking_a_data_type_by_hand_is_not_overruled(loaded, monkeypatch, handler, ticked):
    monkeypatch.setattr(callbacks, "preprocess_data", lambda: None)
    monkeypatch.setattr(callbacks, "clear_correlation_data", lambda: None)
    monkeypatch.setattr(callbacks.state, "PARAMS_CHANGED", lambda: None)
    loaded.val_selected_column.set("EDA" if ticked == "val_checkbox_eb" else "IBI")
    getattr(loaded, ticked).set(True)
    handler()
    assert getattr(loaded, ticked).get() is True
