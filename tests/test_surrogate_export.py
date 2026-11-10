"""
The export of a surrogate test: what it says on its first sheet, the dyads and shuffled versions sheets, skipped
dyads, and the figure, which is saved on its own.
"""
import os

import numpy as np
import openpyxl
import pytest

import export
import surrogates
from helpers import N_BEATS, batch_params, write_dyad, write_person
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
    return result, openpyxl.load_workbook(path)


def _rows(workbook):
    return {row[0]: row[1] for row in workbook.worksheets[0].iter_rows(max_col=2, values_only=True) if row[0]}


def _column(sheet, header):
    headers = [cell.value for cell in sheet[1]]
    index = headers.index(header)
    return [row[index] for row in sheet.iter_rows(min_row=2, values_only=True) if row[index] is not None]


def _sheet_rows(sheet):
    return list(sheet.iter_rows(values_only=True))


# ---------------------------------------------------------------------------
# FIRST SHEET
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method", [REPAIRED, BLOCKS])
def test_first_sheet_has_the_result_and_how_it_was_made(dyads, tmp_path, method):
    result, workbook = _export(dyads, tmp_path, method)
    rows = _rows(workbook)
    assert workbook.sheetnames[0] == "Surrogate Analysis"
    assert rows['p-value'] == pytest.approx(result.p_value)
    assert rows['Method'] == method
    assert rows['Measure'] == MEAN_ABS_R_MAX
    assert rows['Sides'] == surrogates.GREATER
    assert rows['Summary'] == surrogates.result_summary(result)
    assert rows['Real group mean'] == pytest.approx(result.real_value)
    assert rows['Surrogate mean'] == pytest.approx(np.mean(result.null_values))
    assert rows['Random seed'] == 4
    assert rows['Surrogate sets'] == N_SURROGATES
    assert rows['Real dyads used'] == 3
    assert rows['Window size'] == 150 and rows['Max lag'] == 30
    assert _column(workbook.worksheets[0], 'surrogate set mean') == pytest.approx(list(result.null_values))
    assert _column(workbook.worksheets[0], 'real dyad value') == pytest.approx(result.real_values)


def test_repaired_rows(dyads, tmp_path):
    result, workbook = _export(dyads, tmp_path, REPAIRED)
    rows = _rows(workbook)
    assert rows['Different random pairs possible'] == rows['Random pairs used'] == 12
    assert rows['Different surrogate sets possible'] == result.n_sets_possible == 220
    assert rows['Files not used for random pairs'] == '-'
    assert 'Block length (samples)' not in rows


def test_blocks_rows(dyads, tmp_path):
    result, workbook = _export(dyads, tmp_path, BLOCKS)
    rows = _rows(workbook)
    assert rows['Block length (samples)'] == BLOCK_LENGTH
    assert rows['Dyads with p < 0.05'] == sum(p < 0.05 for p in result.dyad_p_values)
    assert rows['Different surrogate sets possible'] == "more than 10^15"
    assert 'Random pairs used' not in rows


@pytest.mark.parametrize("count, written", [(None, '-'), (220, 220), (10 ** 15 - 1, 10 ** 15 - 1),
                                            (10 ** 15, "more than 10^15"), (10 ** 400, "more than 10^15")])
def test_counts_too_large_for_excel_are_text(count, written):
    assert export._count(count) == written


# ---------------------------------------------------------------------------
# OTHER SHEETS
# ---------------------------------------------------------------------------

def test_dyads_sheet_of_repaired_people(dyads, tmp_path):
    result, workbook = _export(dyads, tmp_path, REPAIRED)
    assert workbook.sheetnames == ["Surrogate Analysis", "dyads"]
    header, *rows = _sheet_rows(workbook["dyads"])
    assert header == ('dyad', 'value')
    assert [row[0] for row in rows] == result.dyad_names
    assert [row[1] for row in rows] == pytest.approx(result.real_values)


def test_dyads_sheet_of_shuffled_blocks(dyads, tmp_path):
    result, workbook = _export(dyads, tmp_path, BLOCKS)
    header, *rows = _sheet_rows(workbook["dyads"])
    assert header == ('dyad', 'value', 'p-value', 'shuffled 2.5%', 'shuffled median', 'shuffled 97.5%',
                      'block orders possible')
    for row, value, p_value, null_values, orders in zip(rows, result.real_values, result.dyad_p_values,
                                                         result.dyad_null_values, result.dyad_orders_possible):
        assert row[1:3] == pytest.approx((value, p_value))
        assert row[3:6] == pytest.approx(tuple(np.percentile(null_values, [2.5, 50, 97.5])))
        assert row[6] == orders


def test_every_shuffled_version_is_in_the_export(dyads, tmp_path):
    result, workbook = _export(dyads, tmp_path, BLOCKS)
    header, *rows = _sheet_rows(workbook["shuffled versions"])
    assert header == ('version', *result.dyad_names)
    assert [row[0] for row in rows] == list(range(1, N_SURROGATES + 1))
    assert np.array([row[1:] for row in rows]) == pytest.approx(np.array(result.dyad_null_values).T)


def test_skipped_dyads_and_pairs_get_a_sheet(dyads, tmp_path):
    os.remove(dyads / "dyad1" / "P2.xlsx")
    write_person(dyads / "dyad1" / "P2.xlsx", {"Other": np.ones(N_BEATS)})
    result, workbook = _export(dyads, tmp_path, REPAIRED)
    header, *rows = _sheet_rows(workbook["skipped"])
    assert header == ('dyad or pair', 'reason')
    assert rows == [tuple(failure) for failure in result.failures]
    assert ("dyad1", "P2.xlsx has no column 'Coupled'") in rows
    assert _rows(workbook)['Dyads or pairs skipped'] == len(result.failures)


def test_no_skipped_sheet_without_skipped_dyads(dyads, tmp_path):
    _, workbook = _export(dyads, tmp_path, BLOCKS)
    assert "skipped" not in workbook.sheetnames


# ---------------------------------------------------------------------------
# WELCH
# ---------------------------------------------------------------------------

def test_welch_keeps_its_earlier_file_and_adds_rows_and_sheets(dyads, tmp_path):
    result, workbook = _export(dyads, tmp_path, WELCH, measure=MEAN_R)
    rows = _rows(workbook)
    assert workbook.sheetnames == ["Random Pair Analysis", "dyads"]
    assert list(rows)[:2] == ['t-statistic', 'p-value']
    assert list(rows)[-4:] == ['Method', 'Measure', 'Sides', 'Summary']
    assert rows['Method'] == WELCH and rows['Measure'] == MEAN_R and rows['Sides'] == surrogates.TWO_SIDED
    assert "t = " in rows['Summary']
    assert os.path.exists(tmp_path / "result_avg_real_pairs.xlsx")


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
