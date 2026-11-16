"""
The export of a surrogate test: its tables (metadata, surrogate sets, dyads, shuffled versions, random pairs,
files left out, skipped), Welch's group averages, and the figure, which is saved on its own.
"""
import os

import numpy as np
import openpyxl
import pytest

import export
import surrogates
from helpers import N_BEATS, batch_params, read_column, read_metadata, read_notes, read_table, write_dyad, write_person
from measures import MEAN_ABS_R_MAX, MEAN_R
from surrogates import BLOCKS, REPAIRED, WELCH, surrogate_analysis

N_SURROGATES = 50
BLOCK_LENGTH = 300


@pytest.fixture
def dyads(tmp_path):
    for index in range(3):
        write_dyad(tmp_path / "in" / f"dyad{index}", seed=index)
    return tmp_path / "in"


def _export(dyads, tmp_path, method, measure=MEAN_ABS_R_MAX, **params):
    params = batch_params(dyads, dyads, **params)
    result = surrogate_analysis(method, params, str(dyads), N_SURROGATES, 4, measure, block_length=BLOCK_LENGTH)
    path = tmp_path / "result.xlsx"
    export.export_surrogate_result(str(path), params, str(dyads), result)
    return result, path


# ---------------------------------------------------------------------------
# METADATA
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method, sheets", [
    (BLOCKS, ["metadata", "surrogate_sets", "dyads", "shuffled_versions", "skipped"]),
    (REPAIRED, ["metadata", "surrogate_sets", "dyads", "random_pairs", "files_left_out", "skipped"]),
    (WELCH, ["metadata", "dyads", "random_pairs", "files_left_out", "skipped"]),
])
def test_every_method_writes_its_tables_even_when_empty(dyads, tmp_path, method, sheets):
    _, path = _export(dyads, tmp_path, method, measure=MEAN_R)
    assert openpyxl.load_workbook(path).sheetnames == sheets
    assert read_table(path, "skipped") == (['dyad_or_pair', 'reason'], [])


@pytest.mark.parametrize("method", [REPAIRED, BLOCKS])
def test_metadata_has_the_result_and_how_it_was_made(dyads, tmp_path, method):
    result, path = _export(dyads, tmp_path, method)
    metadata = read_metadata(path)
    assert metadata['analysis'] == "surrogate test"
    assert (metadata['method'], metadata['measure'], metadata['sides']) == (method, MEAN_ABS_R_MAX, surrogates.GREATER)
    assert metadata['p_value'] == pytest.approx(result.p_value)
    assert metadata['summary'] == surrogates.result_summary(result)
    assert metadata['real_mean'] == pytest.approx(result.real_value)
    assert metadata['surrogate_mean'] == pytest.approx(np.mean(result.null_values))
    assert (metadata['seed'], metadata['surrogate_sets'], metadata['real_dyads_used'], metadata['skipped']) == (
        4, N_SURROGATES, 3, 0)
    assert (metadata['window_size_samples'], metadata['max_lag_samples']) == (150, 30)
    assert (metadata['correlation'], metadata['standardised']) == ("windowed cross-correlation", False)
    assert metadata['input_folder'] == str(dyads)
    assert (metadata['sheet'], metadata['column']) == ("Sheet", "Coupled")
    assert read_column(path, "surrogate_sets", "value") == pytest.approx(list(result.null_values))
    assert 't_statistic' not in metadata


def test_repaired_rows(dyads, tmp_path):
    result, path = _export(dyads, tmp_path, REPAIRED)
    metadata = read_metadata(path)
    assert metadata['random_pairs_possible'] == metadata['random_pairs_used'] == 12
    assert metadata['different_sets_possible'] == result.n_sets_possible == 220
    assert metadata['files_left_out'] == 0
    assert 'block_length_samples' not in metadata


def test_blocks_rows(dyads, tmp_path):
    result, path = _export(dyads, tmp_path, BLOCKS)
    metadata, notes = read_metadata(path), read_notes(path)
    assert metadata['block_length_samples'] == BLOCK_LENGTH
    assert metadata['dyads_significant'] == sum(p < 0.05 for p in result.dyad_p_values)
    assert "not corrected" in notes['dyads_significant']
    assert metadata['different_sets_possible'] == pytest.approx(float(result.n_sets_possible))
    assert notes['different_sets_possible'] == "rounded: Excel keeps 15 digits"
    assert 'random_pairs_used' not in metadata


@pytest.mark.parametrize("count, row", [
    (None, ('n', None, "not known")), (220, ('n', 220)), (10 ** 15 - 1, ('n', 10 ** 15 - 1)),
    (10 ** 15, ('n', 1e15, "rounded: Excel keeps 15 digits")), (10 ** 400, ('n', None, "more than 10^308")),
])
def test_counts_too_large_for_excel(count, row):
    assert export._count_row('n', count) == row


# ---------------------------------------------------------------------------
# OTHER SHEETS
# ---------------------------------------------------------------------------

def test_dyads_sheet_of_repaired_people(dyads, tmp_path):
    result, path = _export(dyads, tmp_path, REPAIRED)
    columns, rows = read_table(path, "dyads")
    assert columns == ['dyad', 'value']
    assert [row[0] for row in rows] == result.dyad_names
    assert [row[1] for row in rows] == pytest.approx(result.real_values)


def test_dyads_sheet_of_shuffled_blocks(dyads, tmp_path):
    result, path = _export(dyads, tmp_path, BLOCKS)
    columns, rows = read_table(path, "dyads")
    assert columns == ['dyad', 'value', 'p_value', 'shuffled_percentile_2_5', 'shuffled_median',
                       'shuffled_percentile_97_5', 'block_orders_possible']
    for row, value, p_value, null_values, orders in zip(rows, result.real_values, result.dyad_p_values,
                                                         result.dyad_null_values, result.dyad_orders_possible):
        assert row[1:3] == pytest.approx([value, p_value])
        assert row[3:6] == pytest.approx(list(np.percentile(null_values, [2.5, 50, 97.5])))
        assert row[6] == orders


def test_every_shuffled_version_is_in_the_export(dyads, tmp_path):
    result, path = _export(dyads, tmp_path, BLOCKS)
    columns, rows = read_table(path, "shuffled_versions")
    assert columns == ['version', *result.dyad_names]
    assert [row[0] for row in rows] == list(range(1, N_SURROGATES + 1))
    assert np.array([row[1:] for row in rows]) == pytest.approx(np.array(result.dyad_null_values).T)


def test_random_pairs_of_repaired_people_are_every_pair_with_its_value(dyads, tmp_path):
    result, path = _export(dyads, tmp_path, REPAIRED)
    columns, rows = read_table(path, "random_pairs")
    assert columns == ['pair', 'file_a', 'file_b', 'value']
    assert len(rows) == result.n_pairs_used == 12
    assert [row[0] for row in rows] == list(range(1, 13))
    for _, file_a, file_b, _ in rows:
        assert file_a.split(os.sep)[0] != file_b.split(os.sep)[0]       # never two people of one dyad
    assert sorted(frozenset((a, b)) for _, a, b, _ in rows) == sorted(
        frozenset((os.path.relpath(a, dyads), os.path.relpath(b, dyads))) for a, b in result.pair_files)
    # each set is the mean of real_dyads_used different pairs from this list
    values = np.array([row[3] for row in rows])
    assert min(result.null_values) >= np.sort(values)[:3].mean() - 1e-12


def test_random_pairs_of_welch_are_the_drawn_pairs_in_order(dyads, tmp_path):
    result, path = _export(dyads, tmp_path, WELCH, measure=MEAN_R)
    rows = read_table(path, "random_pairs")[1]
    assert [row[3] for row in rows] == pytest.approx(list(result.null_values))
    assert [(a, b) for _, a, b, _ in rows] == [
        (os.path.relpath(a, dyads), os.path.relpath(b, dyads)) for a, b in result.pair_files]
    assert len(rows) == N_SURROGATES        # drawn with replacement: pairs drawn again are listed again


def test_welch_lists_only_pairs_with_a_value_next_to_their_value(dyads, tmp_path):
    os.remove(dyads / "dyad1" / "P2.xlsx")
    write_person(dyads / "dyad1" / "P2.xlsx", {"Other": np.ones(N_BEATS)})
    result, path = _export(dyads, tmp_path, WELCH, measure=MEAN_R)
    rows = read_table(path, "random_pairs")[1]
    assert any(name.startswith("random pair") for name, _ in result.failures)
    assert len(rows) == len(result.null_values) < N_SURROGATES
    assert not [row for row in rows if os.path.join("dyad1", "P2.xlsx") in row[1:3]]
    assert [row[3] for row in rows] == pytest.approx(list(result.null_values))


def test_counts_of_block_orders_are_numbers_excel_can_store():
    result = surrogates.SurrogateResult(
        method=BLOCKS, measure=MEAN_R, side=surrogates.TWO_SIDED, seed=1, dyad_names=["small", "large", "huge"],
        real_values=[0.1, 0.2, 0.3], real_value=0.2, null_values=np.zeros(3), p_value=0.5, n_surrogates=3,
        n_sets_possible=10, failures=[], block_length=10, dyad_null_values=[np.zeros(3)] * 3,
        dyad_p_values=[0.5] * 3, dyad_orders_possible=[719, 10 ** 20, 10 ** 400],
    )
    orders = [row[-1] for row in export._dyads_table(result)['rows']]
    assert orders == [719, 1e20, None] and type(orders[1]) is float


def test_skipped_dyads_and_pairs_are_listed(dyads, tmp_path):
    os.remove(dyads / "dyad1" / "P2.xlsx")
    write_person(dyads / "dyad1" / "P2.xlsx", {"Other": np.ones(N_BEATS)})
    result, path = _export(dyads, tmp_path, REPAIRED)
    rows = read_table(path, "skipped")[1]
    assert rows == [list(failure) for failure in result.failures]
    assert ["dyad1", "P2.xlsx has no column 'Coupled'"] in rows
    assert read_metadata(path)['skipped'] == len(result.failures)


def test_files_left_out_of_random_pairs_are_listed(dyads, tmp_path):
    workbook = openpyxl.Workbook()
    workbook.active.title = "Other"
    workbook.save(dyads / "dyad1" / "notes.xlsx")
    result, path = _export(dyads, tmp_path, REPAIRED)
    assert read_table(path, "files_left_out")[1] == [[os.path.join("dyad1", "notes.xlsx"), "no sheet 'Sheet'"]]
    assert read_metadata(path)['files_left_out'] == 1


# ---------------------------------------------------------------------------
# WELCH
# ---------------------------------------------------------------------------

def test_welch_has_t_and_the_mean_of_the_random_pairs(dyads, tmp_path):
    result, path = _export(dyads, tmp_path, WELCH, measure=MEAN_R)
    metadata, notes = read_metadata(path), read_notes(path)
    assert (metadata['method'], metadata['measure'], metadata['sides']) == (WELCH, MEAN_R, surrogates.TWO_SIDED)
    assert (metadata['t_statistic'], metadata['p_value']) == (pytest.approx(result.t_statistic), pytest.approx(result.p_value))
    assert metadata['random_pair_mean'] == pytest.approx(np.mean(result.null_values))
    assert (metadata['random_pairs_requested'], metadata['random_pairs_used']) == (N_SURROGATES, N_SURROGATES)
    assert notes['random_pairs_used'] == "pairs drawn more than once count again"
    assert "t = " in metadata['summary']
    assert 'surrogate_sets' not in metadata and 'surrogate_mean' not in metadata


def test_welch_writes_its_group_averages_next_to_the_file(dyads, tmp_path):
    result, path = _export(dyads, tmp_path, WELCH, measure=MEAN_R)
    for name, n in (("real_pairs", 3), ("random_pairs", N_SURROGATES)):
        side_file = tmp_path / f"result_avg_{name}.xlsx"
        assert read_metadata(side_file)['dyads_averaged'] == n
        assert (tmp_path / f"result_avg_{name}.png").exists()


def test_welch_with_standard_correlation_has_no_group_averages(dyads, tmp_path):
    _export(dyads, tmp_path, WELCH, measure=MEAN_R, checkbox_windowed_xcorr=False, max_lag_sxc=40)
    assert sorted(os.listdir(tmp_path)) == ["in", "result.xlsx"]


# ---------------------------------------------------------------------------
# FIGURE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method", [REPAIRED, BLOCKS, WELCH])
def test_figure_is_saved_on_its_own(dyads, tmp_path, method):
    result, _ = _export(dyads, tmp_path, method, measure=MEAN_R)
    assert not (tmp_path / "result.png").exists()       # the xlsx export doesn't write it
    export.export_surrogate_figure(str(tmp_path / "figure.png"), result)
    assert (tmp_path / "figure.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_figure_of_many_dyads_is_taller():
    rng = np.random.default_rng(0)
    n = 60
    result = surrogates.SurrogateResult(
        method=BLOCKS, measure=MEAN_R, side=surrogates.TWO_SIDED, seed=1, dyad_names=[f"d{i}" for i in range(n)],
        real_values=list(rng.normal(size=n)), real_value=0.1, null_values=rng.normal(size=20), p_value=0.5,
        n_surrogates=20, n_sets_possible=10, failures=[], block_length=10,
        dyad_null_values=[rng.normal(size=20) for _ in range(n)], dyad_p_values=[0.5] * n,
        dyad_orders_possible=[10] * n,
    )
    assert export._figure(result).get_size_inches()[1] == pytest.approx(3 + 0.2 * n)


def test_the_saved_figure_is_the_taller_one(tmp_path, monkeypatch):
    saved = []
    monkeypatch.setattr(export, "_figure", lambda result: ("figure of", result))
    monkeypatch.setattr(export, "save_figure_to_png", lambda fig, path: saved.append((fig, path)))
    export.export_surrogate_figure("out.png", "result")
    assert saved == [(("figure of", "result"), "out.png")]


# ---------------------------------------------------------------------------
# SUMMARY SENTENCE
# ---------------------------------------------------------------------------

def test_summary_sentences(dyads):
    params = batch_params(dyads, dyads)
    repaired = surrogate_analysis(REPAIRED, params, str(dyads), 20, 1, MEAN_ABS_R_MAX)
    blocks = surrogate_analysis(BLOCKS, params, str(dyads), 20, 1, MEAN_R, block_length=BLOCK_LENGTH)
    welch = surrogate_analysis(WELCH, params, str(dyads), 20, 1, MEAN_R)
    assert surrogates.result_summary(repaired) == (
        f"mean |r_max| of 3 real dyads compared with 20 sets of 3 re-paired people (one-sided (real higher)): "
        f"{surrogates.format_p(repaired.p_value)}."
    )
    n_significant = sum(p < 0.05 for p in blocks.dyad_p_values)
    assert surrogates.result_summary(blocks) == (
        f"mean r of 3 real dyads compared with 20 shuffled versions of each dyad, in blocks of {BLOCK_LENGTH} "
        f"samples (two-sided): {surrogates.format_p(blocks.p_value)} for the group, and {n_significant} of 3 dyads "
        f"with p < 0.05 on their own."
    )
    assert surrogates.result_summary(welch) == (
        f"mean r of 3 real dyads compared with 20 random pairs with Welch's t-test (two-sided): "
        f"t = {welch.t_statistic:.2f}, {surrogates.format_p(welch.p_value)}."
    )
