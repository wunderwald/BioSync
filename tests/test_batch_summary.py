"""
The batch summary: one row per dyad folder, with the values of each dyad's own file, failed dyads with their
reason, and a sheet that says what each column means.
"""
import numpy as np
import pytest

import batch_processing
import callbacks
from helpers import batch_params, read_column, read_metadata, read_table, write_dyad, write_person
from measures import MEAN_ABS_R, MEAN_ABS_R_MAX, MEAN_R, R_AT_LAG_0

WINDOWED_SUMMARY, STANDARD_SUMMARY = "BioSync_wcc_summary.xlsx", "BioSync_scc_summary.xlsx"


@pytest.fixture
def dirs(tmp_path):
    input_dir, output_dir = tmp_path / "in", tmp_path / "out"
    output_dir.mkdir()
    for index in range(2):
        write_dyad(input_dir / f"dyad{index}", seed=index)
    return input_dir, output_dir


def _rows(path):
    """{dyad: {column: value}} of the dyads sheet."""
    columns, rows = read_table(path, "dyads")
    return {row[0]: dict(zip(columns, row)) for row in rows}


def test_windowed_summary_has_a_row_per_dyad_with_the_values_of_its_file(dirs):
    input_dir, output_dir = dirs
    summary = batch_processing.batch_process(batch_params(input_dir, output_dir))
    assert summary['summary_file'] == WINDOWED_SUMMARY
    rows = _rows(output_dir / WINDOWED_SUMMARY)
    assert list(rows) == ["dyad0", "dyad1"]
    for dyad, row in rows.items():
        dyad_file = output_dir / f"BioSync_wcc_{dyad}.xlsx"
        metadata = read_metadata(dyad_file)
        assert (row['status'], row['note'], row['file_a'], row['file_b']) == ("ok", None, "P1.xlsx", "P2.xlsx")
        for column in ('windows', 'dfa_alpha_a', 'dfa_alpha_b', 'dfa_alpha_correlations_over_time',
                       'kpss_stationary_share_a', 'kpss_stationary_share_b'):
            assert row[column] == metadata[column], column
        correlations = np.array([r[1:] for r in read_table(dyad_file, "correlations")[1]], dtype=float)
        lag_0 = read_table(dyad_file, "correlations")[0].index(0)
        assert row['mean_r'] == pytest.approx(np.mean(correlations))
        assert row['mean_abs_r'] == pytest.approx(np.mean(np.abs(correlations)))
        assert row['mean_abs_r_max'] == pytest.approx(np.mean(np.abs(read_column(dyad_file, "windows", "r_max"))))
        assert row['r_at_lag_0'] == pytest.approx(np.mean(correlations[:, lag_0 - 1]))


def test_summary_values_are_those_the_surrogate_tests_compare(dirs):
    import surrogates
    input_dir, output_dir = dirs
    params = batch_params(input_dir, output_dir)
    batch_processing.batch_process(params)
    rows = _rows(output_dir / WINDOWED_SUMMARY)
    for measure, column in ((MEAN_R, 'mean_r'), (MEAN_ABS_R, 'mean_abs_r'), (MEAN_ABS_R_MAX, 'mean_abs_r_max'),
                            (R_AT_LAG_0, 'r_at_lag_0')):
        result = surrogates.surrogate_analysis(surrogates.BLOCKS, params, str(input_dir), 5, 1, measure,
                                               block_length=300)
        assert result.real_values == pytest.approx([rows[dyad][column] for dyad in result.dyad_names]), column


def test_standard_summary_has_the_peak_and_its_lag(dirs):
    input_dir, output_dir = dirs
    batch_processing.batch_process(batch_params(input_dir, output_dir, checkbox_windowed_xcorr=False, max_lag_sxc=40))
    rows = _rows(output_dir / STANDARD_SUMMARY)
    assert read_table(output_dir / STANDARD_SUMMARY, "dyads")[0] == [
        'dyad', 'status', 'note', 'file_a', 'file_b', 'r_max', 'tau_max', 'mean_r', 'mean_abs_r', 'r_at_lag_0',
        'dfa_alpha_a', 'dfa_alpha_b', 'kpss_p_a', 'kpss_p_b']
    for dyad, row in rows.items():
        lags, correlations = zip(*read_table(output_dir / f"BioSync_scc_{dyad}.xlsx", "correlations")[1])
        peak = int(np.argmax(np.abs(correlations)))
        assert (row['r_max'], row['tau_max']) == (pytest.approx(correlations[peak]), lags[peak])
        assert row['r_at_lag_0'] == pytest.approx(correlations[lags.index(0)])
        assert row['kpss_p_a'] == read_metadata(output_dir / f"BioSync_scc_{dyad}.xlsx")['kpss_p_a']


def test_failed_dyads_have_a_row_with_the_reason_and_notes_say_what_to_know(dirs):
    input_dir, output_dir = dirs
    for folder in ("one_file", "wrong_columns"):
        (input_dir / folder).mkdir()
    write_person(input_dir / "one_file" / "P1.xlsx", {"Coupled": [800.0] * 50})
    for name in ("P1.xlsx", "P2.xlsx"):
        write_person(input_dir / "wrong_columns" / name, {"Other": [800.0, 810.0]})
    write_dyad(input_dir / "three_files", file_names=("P1.xlsx", "P2.xlsx", "P3.xlsx"))
    batch_processing.batch_process(batch_params(input_dir, output_dir))
    rows = _rows(output_dir / WINDOWED_SUMMARY)
    assert list(rows) == ["dyad0", "dyad1", "one_file", "three_files", "wrong_columns"]
    assert (rows["one_file"]['status'], rows["one_file"]['note']) == ("failed", "needs 2 xlsx files, found 1")
    assert rows["one_file"]['file_a'] is None and rows["one_file"]['mean_r'] is None
    assert rows["wrong_columns"]['status'] == "failed" and rows["wrong_columns"]['mean_r'] is None
    assert rows["three_files"]['status'] == "ok"
    assert rows["three_files"]['note'] == "found 3 xlsx files, used P1.xlsx and P2.xlsx"
    metadata = read_metadata(output_dir / WINDOWED_SUMMARY)
    assert (metadata['dyads'], metadata['dyads_ok'], metadata['dyads_failed']) == (5, 3, 2)


def test_measures_the_settings_rule_out_are_empty_and_the_columns_sheet_says_why(dirs):
    input_dir, output_dir = dirs
    batch_processing.batch_process(batch_params(input_dir, output_dir, checkbox_average_windows=True))
    rows = _rows(output_dir / WINDOWED_SUMMARY)
    assert all(row['mean_r'] is not None and row['mean_abs_r_max'] is None and row['r_at_lag_0'] is None
               for row in rows.values())
    descriptions = dict(read_table(output_dir / WINDOWED_SUMMARY, "columns")[1])
    assert descriptions['mean_abs_r_max'].endswith("Empty: it needs a correlation for each lag, and 'average windows' is on.")
    assert "Empty" not in descriptions['mean_r']


def test_metadata_has_the_settings_of_the_run(dirs):
    input_dir, output_dir = dirs
    batch_processing.batch_process(batch_params(input_dir, output_dir, window_size=200, step_size=100))
    metadata = read_metadata(output_dir / WINDOWED_SUMMARY)
    assert (metadata['analysis'], metadata['input_folder']) == ("windowed cross-correlation", str(input_dir))
    assert (metadata['window_size_samples'], metadata['step_size_samples'], metadata['standardised']) == (200, 100, False)
    described = [column for column, _ in read_table(output_dir / WINDOWED_SUMMARY, "columns")[1]]
    assert described == read_table(output_dir / WINDOWED_SUMMARY, "dyads")[0]     # every column, in order


def test_a_dyad_named_like_a_group_file_is_warned_about(dirs):
    input_dir, output_dir = dirs
    write_dyad(input_dir / "summary", seed=3)
    summary = batch_processing.batch_process(batch_params(input_dir, output_dir))
    assert any(warning.startswith("summary: its result files have the name of a file for the whole group")
               for warning in summary['warnings'])
    assert "rename the folder" in _rows(output_dir / WINDOWED_SUMMARY)["summary"]['note']


def test_no_dyad_folders_no_summary(tmp_path):
    (tmp_path / "in").mkdir()
    (tmp_path / "out").mkdir()
    summary = batch_processing.batch_process(batch_params(tmp_path / "in", tmp_path / "out"))
    assert 'summary_file' not in summary and list((tmp_path / "out").iterdir()) == []


def test_summary_counts_as_a_result_of_an_earlier_run(dirs):
    input_dir, output_dir = dirs
    batch_processing.batch_process(batch_params(input_dir, output_dir))
    assert WINDOWED_SUMMARY in batch_processing.find_result_files(str(output_dir))


def test_finished_message_names_the_summary():
    text = callbacks._format_batch_summary(
        {'processed': ["d"], 'failed': [], 'warnings': [], 'summary_file': WINDOWED_SUMMARY})
    assert text.splitlines()[:2] == ["Processed 1 dyads, skipped 0.", f"All dyads, one row each: {WINDOWED_SUMMARY}"]


def test_standard_peak_is_the_largest_size_with_its_sign():
    from export import summary_values
    from helpers import export_params
    config = export_params(windowed=False)['config']
    values = summary_values({'lags': [-1, 0, 1], 'corr': [0.2, -0.6, 0.5]}, config, None, None, None)
    assert (values['r_max'], values['tau_max']) == (-0.6, 0)
    assert values['kpss_p_a'] is None and values['dfa_alpha_a'] is None
