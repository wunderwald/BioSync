"""
Batch processing and random pair analysis, using small synthetic dyads where each column has a known relationship:
    'Coupled' columns of a dyad are near-identical (r near 1 at lag 0).
    'Independent' columns of a dyad are unrelated.
"""
import os
import subprocess
import time
import sys

import matplotlib.pyplot as plt
import numpy as np
import openpyxl
import pytest
from openpyxl import Workbook

import batch_processing
import callbacks
import export
import utils

N_BEATS = 1000
SHEET = "Sheet"


def _ibi(rng):
    noise = np.convolve(rng.normal(size=N_BEATS), np.ones(4) / 2, mode="same")
    return 800 + 50 * noise


def _write_person(path, columns):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET
    sheet.append(list(columns))
    for row in zip(*columns.values()):
        sheet.append([float(value) for value in row])
    workbook.save(path)


def _write_dyad(folder, seed=0, file_names=("P1.xlsx", "P2.xlsx")):
    os.makedirs(folder)
    rng = np.random.default_rng(seed)
    coupled = _ibi(rng)
    for file_name in file_names:
        _write_person(
            os.path.join(folder, file_name),
            {"Coupled": coupled + rng.normal(0, 5, N_BEATS), "Independent": _ibi(rng)},
        )


def _params(input_dir, output_dir, column="Coupled", **overrides):
    params = {
        'batch_input_folder': str(input_dir),
        'output_dir': str(output_dir),
        'selected_sheet': SHEET,
        'has_headers': True,
        'selected_column_a': column,
        'selected_column_b': column,
        'checkbox_windowed_xcorr': True,
        'window_size': 150,
        'step_size': 75,
        'max_lag': 30,
        'max_lag_sxc': 150,
        'standardised_signals': False,
        'checkbox_absolute_corr': False,
        'checkbox_absolute_corr_sxc': False,
        'checkbox_average_windows': False,
        'sigmoid_correlations': False,
        'checkbox_eb': True,
        'checkbox_fr': False,
        'use_lag_filter': False,
        'lag_filter_min': -30,
        'lag_filter_max': 30,
    }
    params.update(overrides)
    return params


def _read_export(path):
    """Returns (metadata, columns) of an exported file."""
    sheet = openpyxl.load_workbook(path).active
    metadata = {row[0].value: row[1].value for row in sheet.iter_rows(max_col=2) if row[0].value}
    columns = {}
    for column in sheet.iter_cols(min_col=4):
        columns[column[0].value] = [cell.value for cell in column[1:] if cell.value is not None]
    return metadata, columns


@pytest.fixture
def batch_dirs(tmp_path):
    input_dir, output_dir = tmp_path / "in", tmp_path / "out"
    output_dir.mkdir()
    for seed in range(2):
        _write_dyad(input_dir / f"dyad{seed}", seed=seed)
    return input_dir, output_dir


# ---------------------------------------------------------------------------
# COLUMN SELECTION
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("column, is_coupled", [("Coupled", True), ("Independent", False)])
def test_selected_column_is_the_one_analysed(batch_dirs, column, is_coupled):
    input_dir, output_dir = batch_dirs
    result = batch_processing._process_dyad(
        input_dir / "dyad0" / "P1.xlsx", input_dir / "dyad0" / "P2.xlsx",
        None, _params(input_dir, output_dir, column=column), export=False,
    )
    assert (np.median([w['r_max'] for w in result]) > 0.9) == is_coupled


def test_params_use_the_columns_selected_in_the_dropdowns(fake_state):
    fake_state.val_selected_column_a.set("Column from dropdown A")
    fake_state.val_selected_column_b.set("Column from dropdown B")
    params = callbacks._analysis_params()
    assert params['selected_column_a'] == "Column from dropdown A"
    assert params['selected_column_b'] == "Column from dropdown B"


# ---------------------------------------------------------------------------
# LAG FILTER
# ---------------------------------------------------------------------------

def test_lag_filter_limits_the_lags_of_each_dyad(batch_dirs):
    input_dir, output_dir = batch_dirs
    params = _params(input_dir, output_dir, use_lag_filter=True, lag_filter_min=10, lag_filter_max=30)
    result = batch_processing._process_dyad(
        input_dir / "dyad0" / "P1.xlsx", input_dir / "dyad0" / "P2.xlsx", None, params, export=False,
    )
    assert all(len(w['correlations']) == 21 for w in result)
    assert all(10 <= w['tau_max'] <= 30 for w in result)


def test_grand_average_tau_stays_inside_the_lag_filter(batch_dirs):
    input_dir, output_dir = batch_dirs
    params = _params(input_dir, output_dir, use_lag_filter=True, lag_filter_min=10, lag_filter_max=30)
    batch_processing.batch_process(params)
    _, columns = _read_export(output_dir / "grand_avg_wxcorr.xlsx")
    taus = [int(tau) for tau in columns['lag of peak correlation (tau_max)']]
    assert taus and all(10 <= tau <= 30 for tau in taus)


def test_grand_average_without_filter_keeps_all_lags(batch_dirs):
    input_dir, output_dir = batch_dirs
    batch_processing.batch_process(_params(input_dir, output_dir))
    _, columns = _read_export(output_dir / "grand_avg_wxcorr.xlsx")
    assert len(columns['w_0_correlations']) == 61
    # The beat noise of each person adds up to about one sample of timing drift over the recording.
    assert all(abs(int(tau)) <= 2 for tau in columns['lag of peak correlation (tau_max)'])


def test_random_pairs_apply_the_lag_filter(batch_dirs):
    input_dir, output_dir = batch_dirs
    params = _params(input_dir, output_dir, use_lag_filter=True, lag_filter_min=10, lag_filter_max=30)
    result = batch_processing.random_pair_analysis(params, str(input_dir), random_pair_count=4)
    avg_wxcorr_real, avg_wxcorr_rp = result[4], result[5]
    for averaged in (avg_wxcorr_real, avg_wxcorr_rp):
        assert all(len(w['correlations']) == 21 for w in averaged)


# ---------------------------------------------------------------------------
# FILE SELECTION
# ---------------------------------------------------------------------------

def test_dyad_files_are_sorted_whatever_the_listing_order(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "listdir", lambda _: ["b.xlsx", "A.xlsx", "c.xlsx"])
    assert utils.list_dyad_files(tmp_path) == ["A.xlsx", "b.xlsx", "c.xlsx"]


def test_dyad_files_ignore_lock_hidden_and_other_files(tmp_path):
    for name in ("~$P1.xlsx", "._P1.xlsx", ".DS_Store", "notes.txt", "P1.xlsx", "P2.xlsx"):
        (tmp_path / name).touch()
    assert utils.list_dyad_files(tmp_path) == ["P1.xlsx", "P2.xlsx"]


def test_extra_file_is_reported_and_first_two_are_used(tmp_path):
    input_dir, output_dir = tmp_path / "in", tmp_path / "out"
    output_dir.mkdir()
    _write_dyad(input_dir / "dyad0", file_names=("P1.xlsx", "P2.xlsx", "P3.xlsx"))
    summary = batch_processing.batch_process(_params(input_dir, output_dir))
    assert summary['processed'] == ["dyad0"]
    assert "P1.xlsx and P2.xlsx" in summary['warnings'][0]
    metadata, _ = _read_export(output_dir / "wx_dyad0_wxcorr.xlsx")
    assert (metadata['Input file A'], metadata['Input file B']) == ("P1.xlsx", "P2.xlsx")


# ---------------------------------------------------------------------------
# STANDARD XCORR AND METADATA
# ---------------------------------------------------------------------------

def test_standard_xcorr_with_short_lag_range_is_exported_without_dfa(batch_dirs):
    input_dir, output_dir = batch_dirs
    params = _params(input_dir, output_dir, checkbox_windowed_xcorr=False, max_lag_sxc=40)
    summary = batch_processing.batch_process(params)
    assert summary['failed'] == []
    metadata, _ = _read_export(output_dir / "dyad0_sxcorr.xlsx")
    assert metadata['Alpha (DFA scaling exponent)'] == '-'


def test_random_pair_metadata_reports_standard_xcorr_settings(tmp_path):
    path = tmp_path / "random_pairs.xlsx"
    params = _params("", "", checkbox_windowed_xcorr=False, max_lag=30, max_lag_sxc=150,
                     checkbox_absolute_corr=False, checkbox_absolute_corr_sxc=True)
    export.export_random_pair_data(str(path), params, "input", 0.1, 0.5, [0.1], [0.2])
    metadata, _ = _read_export(path)
    assert metadata['Max lag'] == 150
    assert metadata['Absolute correlation values'] == 'True'


# ---------------------------------------------------------------------------
# FIGURES AND FAILURE REPORTING
# ---------------------------------------------------------------------------

def test_batch_leaves_no_open_figures(batch_dirs):
    input_dir, output_dir = batch_dirs
    plt.close('all')
    batch_processing.batch_process(_params(input_dir, output_dir))
    assert plt.get_fignums() == []
    assert (output_dir / "wx_dyad0_wxcorr.png").exists()
    assert (output_dir / "grand_avg_wxcorr.png").exists()


def test_app_modules_do_not_load_pyplot():
    # With pyplot on the macOS backend, closing a figure segfaults the Tk event loop.
    # The tests run on Agg and can't see that crash, so guard against pyplot itself.
    code = (
        "import sys, plot, export, batch_processing, callbacks, corr_plot, state; "
        "sys.exit('matplotlib.pyplot' in sys.modules)"
    )
    env = {**os.environ, "PYTHONPATH": os.path.dirname(callbacks.__file__)}
    assert subprocess.run([sys.executable, "-c", code], env=env).returncode == 0


def test_summary_reports_failed_and_incomplete_dyads(batch_dirs):
    input_dir, output_dir = batch_dirs
    (input_dir / "one_file").mkdir()
    (input_dir / "one_file" / "P1.xlsx").touch()
    wrong_columns = input_dir / "wrong_columns"
    wrong_columns.mkdir()
    for name in ("P1.xlsx", "P2.xlsx"):
        _write_person(wrong_columns / name, {"Other": [800.0, 810.0]})

    summary = batch_processing.batch_process(_params(input_dir, output_dir))

    assert summary['processed'] == ["dyad0", "dyad1"]
    failed = dict(summary['failed'])
    assert set(failed) == {"one_file", "wrong_columns"}
    assert "found 1" in failed["one_file"]
    assert "Processed 2 dyads, skipped 2." in callbacks._format_batch_summary(summary)


class ImmediateTimer:
    """Stands in for Tk's timer: runs the scheduled polls in the test."""
    def __init__(self):
        self.pending = []

    def after(self, delay_ms, callback, *args):
        self.pending.append((callback, args))

    def run_until_idle(self, timeout_s=10):
        deadline = time.monotonic() + timeout_s
        while self.pending:
            assert time.monotonic() < deadline, "job didn't finish"
            pending, self.pending = self.pending, []
            for callback, args in pending:
                callback(*args)
            time.sleep(0.001)


@pytest.mark.parametrize("handler, runner, ready_var, input_var, output_var", [
    (callbacks.handle_run_batch_button, "run_batch_process", "val_batch_processing_is_ready",
     "val_batch_input_folder", "val_batch_output_folder"),
    (callbacks.handle_run_random_pair_button, "run_random_pair", "val_random_pair_is_ready",
     "val_random_pair_input_folder", "val_random_pair_output_file"),
])
def test_button_is_enabled_again_and_error_shown_after_a_crash(
    fake_state, monkeypatch, handler, runner, ready_var, input_var, output_var
):
    for name in ("val_INPUT_DATA_VALID", "val_CORRELATION_SETTINGS_VALID", "val_CORRELATION_SETTINGS_VALID_SXC"):
        getattr(fake_state, name).set(True)
    getattr(fake_state, input_var).set("in")
    getattr(fake_state, output_var).set("out")

    def crash(*args):
        raise RuntimeError("disk full")
    monkeypatch.setattr(callbacks, runner, crash)
    errors = []
    monkeypatch.setattr(callbacks.messagebox, "showerror", lambda title, message: errors.append(message))
    tabview = ImmediateTimer()
    monkeypatch.setitem(callbacks._tabview, "tabview", tabview)

    handler()
    tabview.run_until_idle()

    assert errors == ["disk full"]
    assert getattr(fake_state, ready_var).get() is True
