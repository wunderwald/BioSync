"""
Random pairs must not contain real pairs or the same person twice, and a seed must repeat a run.
"""
import os
import shutil

import numpy as np
import openpyxl
import pytest

import callbacks
from measures import MEAN_R
import surrogates
from surrogates import _eligible_random_pairs
from helpers import FakeTimer, batch_params, write_dyad


def _dyad(root, name, files):
    """Writes small distinct files: their content is what identifies a recording."""
    folder = root / name
    folder.mkdir(parents=True)
    for file_name, content in files.items():
        (folder / file_name).write_text(content)


def _pairs(root):
    folders = sorted(os.listdir(root))
    pairs = _eligible_random_pairs(str(root), folders)
    return {frozenset(open(path).read() for path in pair) for pair in pairs}


def _fs(*pairs):
    return {frozenset(pair) for pair in pairs}


def test_only_recordings_from_different_dyads_are_paired(tmp_path):
    _dyad(tmp_path, "d0", {"a.xlsx": "A", "b.xlsx": "B"})
    _dyad(tmp_path, "d1", {"a.xlsx": "C", "b.xlsx": "D"})
    assert _pairs(tmp_path) == _fs("AC", "AD", "BC", "BD")


def test_extra_files_in_a_folder_count_as_real_pairs(tmp_path):
    _dyad(tmp_path, "d0", {"a.xlsx": "A", "b.xlsx": "B", "c.xlsx": "E"})
    _dyad(tmp_path, "d1", {"a.xlsx": "C"})
    assert _pairs(tmp_path) == _fs("AC", "BC", "EC")


def test_copies_of_a_recording_are_not_paired_with_themselves(tmp_path):
    _dyad(tmp_path, "d0", {"s1.xlsx": "A", "s2.xlsx": "B"})
    _dyad(tmp_path, "d1", {"s1.xlsx": "A", "s3.xlsx": "C"})
    pairs = _pairs(tmp_path)
    assert all(len(pair) == 2 for pair in pairs)
    assert pairs == _fs("BC")


def test_copy_under_another_name_is_the_same_recording(tmp_path):
    _dyad(tmp_path, "d0", {"a.xlsx": "A", "b.xlsx": "B"})
    _dyad(tmp_path, "d1", {"renamed.xlsx": "A", "c.xlsx": "C"})
    assert _pairs(tmp_path) == _fs("BC")


def test_same_name_with_other_content_is_another_recording(tmp_path):
    _dyad(tmp_path, "d0", {"a.xlsx": "A"})
    _dyad(tmp_path, "d1", {"a.xlsx": "B"})
    assert _pairs(tmp_path) == _fs("AB")


def test_group_to_dyads_folders_of_one_group_have_no_random_pairs(tmp_path):
    _dyad(tmp_path, "dyad_1_2", {"s1.xlsx": "A", "s2.xlsx": "B"})
    _dyad(tmp_path, "dyad_1_3", {"s1.xlsx": "A", "s3.xlsx": "C"})
    _dyad(tmp_path, "dyad_2_3", {"s2.xlsx": "B", "s3.xlsx": "C"})
    assert _pairs(tmp_path) == set()


def test_analysis_refuses_when_no_random_pair_is_possible(tmp_path):
    _dyad(tmp_path, "d0", {"a.xlsx": "A", "b.xlsx": "B"})
    with pytest.raises(ValueError, match="No random pairs are possible"):
        surrogates.welch_random_pair_test(batch_params(tmp_path, tmp_path), str(tmp_path), 3)


@pytest.fixture
def dyads(tmp_path):
    for index in range(3):
        write_dyad(tmp_path / "in" / f"dyad{index}", seed=index)
    return tmp_path / "in"


def _recorded_pairs(monkeypatch):
    """Records which random pairs are drawn, as (file A, file B), and stops the slow analysis from running."""
    used = []
    draw = surrogates._draw_random_pairs

    def recording(*args):
        pairs = draw(*args)
        used.extend(tuple(pair) for pair in pairs)
        return pairs

    def no_analysis(*args):
        raise ValueError("not analysed in this test")

    monkeypatch.setattr(surrogates, "_draw_random_pairs", recording)
    monkeypatch.setattr(surrogates, "_analysed_pair", no_analysis)
    monkeypatch.setattr(surrogates, "ttest_ind", lambda *args, **kwargs: (0, 1))
    return used


def test_drawn_pairs_are_always_from_different_folders(dyads, monkeypatch):
    used = _recorded_pairs(monkeypatch)
    surrogates.welch_random_pair_test(batch_params(dyads, dyads), str(dyads), 300, seed=1)
    random_pairs = used[:300]
    assert all(os.path.dirname(a) != os.path.dirname(b) for a, b in random_pairs)
    assert len({frozenset(pair) for pair in random_pairs}) == 12     # every possible pair turns up


def test_both_people_can_be_person_a(dyads, monkeypatch):
    used = _recorded_pairs(monkeypatch)
    surrogates.welch_random_pair_test(batch_params(dyads, dyads), str(dyads), 300, seed=1)
    assert len(set(used[:300])) == 24


def test_same_seed_repeats_the_pairs_and_another_seed_does_not(dyads, monkeypatch):
    used = _recorded_pairs(monkeypatch)

    def draw(seed):
        used.clear()
        surrogates.welch_random_pair_test(batch_params(dyads, dyads), str(dyads), 30, seed=seed)
        return list(used[:30])

    assert draw(7) == draw(7)
    assert draw(7) != draw(8)


def test_same_seed_repeats_the_whole_result(dyads):
    params = batch_params(dyads, dyads)
    first = surrogates.welch_random_pair_test(params, str(dyads), 5, seed=7)
    second = surrogates.welch_random_pair_test(params, str(dyads), 5, seed=7)
    assert (first.t_statistic, first.p_value) == (second.t_statistic, second.p_value)
    assert np.array_equal(first.null_values, second.null_values)
    assert first.n_pairs_possible == second.n_pairs_possible == 12


@pytest.fixture
def app(fake_state, dyads, tmp_path, monkeypatch):
    for name in ("val_INPUT_DATA_VALID", "val_CORRELATION_SETTINGS_VALID", "val_CORRELATION_SETTINGS_VALID_SXC",
                 "val_checkbox_windowed_xcorr"):
        getattr(fake_state, name).set(True)
    fake_state.val_job_running.set(False)
    fake_state.val_job_progress.set(0)
    fake_state.val_rp_n.set(3)
    fake_state.val_surrogate_method.set(surrogates.REPAIRED)
    fake_state.val_surrogate_test.set(surrogates.WELCH)
    fake_state.val_surrogate_measure.set(MEAN_R)
    fake_state.val_rp_seed_input.set("")
    fake_state.val_random_pair_input_folder.set(str(dyads))
    fake_state.timer = FakeTimer()
    monkeypatch.setitem(callbacks._tabview, "tabview", fake_state.timer)
    monkeypatch.setattr(callbacks, "_analysis_params", lambda: batch_params(dyads, tmp_path))
    fake_state.dialogs = []
    for kind in ("showinfo", "showerror"):
        monkeypatch.setattr(callbacks.messagebox, kind, lambda title, text: fake_state.dialogs.append((title, text)))
    fake_state.output = tmp_path / "rp.xlsx"
    monkeypatch.setattr(callbacks.filedialog, "asksaveasfilename", lambda **kwargs: str(fake_state.output))
    return fake_state


def _run(app):
    """Runs the analysis, and exports its result as a user would."""
    callbacks.handle_run_surrogate_button()
    app.timer.run_until_idle(60)
    callbacks.export_surrogate_results()


def _rows(app):
    sheet = openpyxl.load_workbook(app.output).worksheets[0]
    return {row[0]: row[1] for row in sheet.iter_rows(max_col=2, values_only=True) if row[0]}


def _run_and_read(app):
    _run(app)
    return _rows(app)


def test_entered_seed_is_used_and_recorded(app):
    app.val_rp_seed_input.set("1234")
    metadata = _run_and_read(app)
    assert metadata['Random seed'] == 1234
    assert metadata['Different random pairs possible'] == 12


def test_empty_seed_gets_a_new_recorded_seed_which_repeats_the_run(app):
    first = _run_and_read(app)
    second = _run_and_read(app)
    assert isinstance(first['Random seed'], int)
    assert first['Random seed'] != second['Random seed']

    app.val_rp_seed_input.set(str(first['Random seed']))
    repeated = _run_and_read(app)
    assert repeated['Random seed'] == first['Random seed']
    assert repeated['p-value'] == first['p-value']
    assert repeated['t-statistic'] == first['t-statistic']


def test_seed_of_zero_is_a_seed(app):
    app.val_rp_seed_input.set("0")
    assert _run_and_read(app)['Random seed'] == 0


# The rows of the first sheet before the surrogate tests were added (commit b76a0dd), which pipelines read by position
EARLIER_ROWS = [
    't-statistic', 'p-value', 'xcorr type', 'Data type', 'Window size', 'Max lag', 'Step size',
    'Absolute correlation values', 'Standardised (z-score)', 'Lag filter used', 'Lag filter minimum',
    'Lag filter maximum', 'Input dyad directory', 'Random seed', 'Different random pairs possible',
    'Random pairs requested', 'Random pairs used', 'Real dyads used',
]


def test_new_rows_come_after_the_existing_ones(app):
    app.val_rp_seed_input.set("1")
    _run(app)
    sheet = openpyxl.load_workbook(app.output).worksheets[0]
    names = [row[0] for row in sheet.iter_rows(max_col=1, values_only=True) if row[0]]
    assert names[:len(EARLIER_ROWS)] == EARLIER_ROWS
    assert names[len(EARLIER_ROWS):] == ['Files not used for random pairs', 'Method', 'Measure', 'Sides', 'Summary']
    assert [cell.value for cell in sheet[1][3:5]] == ['random pair correlation', 'real pair correlation']


def test_seed_is_read_before_the_job_starts(app):
    app.val_rp_seed_input.set("1234")
    callbacks.handle_run_surrogate_button()
    app.val_rp_seed_input.set("99")
    app.timer.run_until_idle(60)
    callbacks.export_surrogate_results()
    assert _rows(app)['Random seed'] == 1234


def test_group_to_dyads_copies_end_to_end(tmp_path, monkeypatch):
    """Real spreadsheets, with the same person's file copied to two folders."""
    root = tmp_path / "in"
    for seed, name in enumerate(("dyad_1_2", "dyad_3_4")):
        write_dyad(root / name, seed=seed)
    shutil.copy(root / "dyad_1_2" / "P1.xlsx", root / "dyad_3_4" / "P3.xlsx")
    used = _recorded_pairs(monkeypatch)
    surrogates.welch_random_pair_test(batch_params(root, root), str(root), 100, seed=1)
    pairs = used[:100]
    hashes = [(surrogates._file_hash(a), surrogates._file_hash(b)) for a, b in pairs]
    assert all(a != b for a, b in hashes)
    assert all(os.path.dirname(a) != os.path.dirname(b) for a, b in pairs)


def _summary(**overrides):
    return {**dict(failures=[], p_value=0.3, random_pairs_requested=20, random_pairs_used=20, real_dyads_used=5), **overrides}


@pytest.mark.parametrize("overrides, expected", [
    ({}, []),
    ({'random_pairs_used': 1}, ["at least 2 random pairs and 2 real dyads, and got 1 and 5", "19 of 20 random pairs were skipped"]),
    ({'real_dyads_used': 1, 'p_value': float('nan')}, ["at least 2 random pairs and 2 real dyads, and got 20 and 1"]),
    ({'p_value': float('nan')}, ["no p-value"]),
    ({'random_pairs_used': 10}, ["10 of 20 random pairs were skipped"]),
])
def test_unreliable_results_are_named(overrides, expected):
    problems = callbacks._random_pair_problems(_summary(**overrides))
    assert len(problems) == len(expected)
    assert all(part in problem for part, problem in zip(expected, problems))


@pytest.mark.parametrize("overrides, kind", [({}, "showinfo"), ({'random_pairs_used': 10}, "showwarning")])
def test_problems_turn_the_message_into_a_warning(monkeypatch, overrides, kind):
    shown = []
    for name in ("showinfo", "showwarning"):
        monkeypatch.setattr(callbacks.messagebox, name, lambda title, text, name=name: shown.append((name, text)))
    callbacks._show_surrogate_summary(_summary(**overrides))
    assert shown[0][0] == kind


@pytest.mark.parametrize("n", [0, 1])
def test_too_small_n_does_not_start(app, n, monkeypatch):
    app.val_rp_n.set(n)
    warnings = []
    monkeypatch.setattr(callbacks.messagebox, "showwarning", lambda title, text: warnings.append(text))
    callbacks.handle_run_surrogate_button()
    assert app.val_job_running.get() is False
    assert "at least 2" in warnings[0]
    assert app.dat_surrogate_run['result'] is None


def test_failed_pairs_give_a_warning_and_are_recorded(app, dyads, monkeypatch):
    from openpyxl import Workbook
    workbook = Workbook()
    workbook.active.title = "Sheet"
    workbook.active.append(["Other"])
    workbook.save(dyads / "dyad0" / "P1.xlsx")
    warnings = []
    monkeypatch.setattr(callbacks.messagebox, "showwarning", lambda title, text: warnings.append(text))
    app.val_rp_n.set(20)
    app.val_rp_seed_input.set("1")
    metadata = _run_and_read(app)
    assert metadata['Random pairs requested'] == 20
    assert metadata['Random pairs used'] < 20
    assert metadata['Real dyads used'] == 2
    assert warnings and "random pairs were skipped" in warnings[0]


# ---------------------------------------------------------------------------
# RECORDINGS THAT CAN'T BE IN A RANDOM PAIR
# ---------------------------------------------------------------------------

@pytest.fixture
def dyads_with_stray_files(dyads):
    """A result file without the data sheet in one dyad folder, as left by a batch run, and an unreadable file."""
    workbook = openpyxl.Workbook()
    workbook.active.title = "Results"
    workbook.save(dyads / "dyad1" / "wx_dyad1_wxcorr.xlsx")
    (dyads / "dyad2" / "broken.xlsx").write_text("not a spreadsheet")
    return dyads


def _left_out_names(result):
    return sorted((os.path.basename(path), reason) for path, reason in result.left_out_files)


EXPECTED_LEFT_OUT = [("broken.xlsx", "can't be read"), ("wx_dyad1_wxcorr.xlsx", "no sheet 'Sheet'")]


def test_files_without_the_sheet_are_not_drawn(dyads_with_stray_files, monkeypatch):
    used = _recorded_pairs(monkeypatch)
    result = surrogates.welch_random_pair_test(
        batch_params(dyads_with_stray_files, dyads_with_stray_files), str(dyads_with_stray_files), 300, seed=1
    )
    drawn_files = {os.path.basename(path) for pair in used for path in pair}
    assert drawn_files == {"P1.xlsx", "P2.xlsx"}
    assert result.n_pairs_possible == 12
    assert _left_out_names(result) == EXPECTED_LEFT_OUT


def test_files_without_the_sheet_are_named_but_not_failures(dyads_with_stray_files):
    params = batch_params(dyads_with_stray_files, dyads_with_stray_files)
    for result in (
        surrogates.welch_random_pair_test(params, str(dyads_with_stray_files), 20, seed=1),
        surrogates.repaired_pair_test(params, str(dyads_with_stray_files), 20, seed=1),
    ):
        assert _left_out_names(result) == EXPECTED_LEFT_OUT
        assert result.failures == []
        assert result.dyad_names == ["dyad0", "dyad1", "dyad2"]


def test_no_random_pair_because_of_left_out_files_says_so(tmp_path):
    write_dyad(tmp_path / "in" / "dyad0")
    workbook = openpyxl.Workbook()
    workbook.active.title = "Results"
    os.makedirs(tmp_path / "in" / "dyad1")
    workbook.save(tmp_path / "in" / "dyad1" / "result.xlsx")
    with pytest.raises(ValueError, match="don't have the sheet 'Sheet'"):
        surrogates.welch_random_pair_test(batch_params(tmp_path / "in", tmp_path), str(tmp_path / "in"), 3)


def test_left_out_files_are_shown_and_recorded(app, dyads_with_stray_files, monkeypatch):
    shown = []
    for kind in ("showinfo", "showwarning"):
        monkeypatch.setattr(callbacks.messagebox, kind, lambda title, text: shown.append(text))
    app.val_rp_seed_input.set("1")
    metadata = _run_and_read(app)
    expected = [os.path.join("dyad1", "wx_dyad1_wxcorr.xlsx") + " (no sheet 'Sheet')",
                os.path.join("dyad2", "broken.xlsx") + " (can't be read)"]
    assert metadata['Files not used for random pairs'] == "; ".join(expected)
    assert "Not used for random pairs:\n" + "\n".join(expected) in shown[0]


def test_without_left_out_files_the_row_has_a_dash(app):
    assert _run_and_read(app)['Files not used for random pairs'] == '-'


# ---------------------------------------------------------------------------
# ONE ENTRY POINT FOR ALL METHODS
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method, extra", [
    (surrogates.REPAIRED, {}),
    (surrogates.BLOCKS, {'block_length': 150}),
    (surrogates.WELCH, {}),
])
def test_every_method_runs_through_one_function(dyads, method, extra):
    result = surrogates.surrogate_analysis(
        method, batch_params(dyads, dyads), str(dyads), 5, 1, surrogates.MEAN_R, **extra
    )
    assert result.method == method
    assert result.seed == 1
    assert result.dyad_names == ["dyad0", "dyad1", "dyad2"]


def test_shuffled_blocks_need_a_block_length(dyads):
    with pytest.raises(ValueError, match="block length"):
        surrogates.surrogate_analysis(surrogates.BLOCKS, batch_params(dyads, dyads), str(dyads), 5, 1, surrogates.MEAN_R)


def test_unknown_method(dyads):
    with pytest.raises(ValueError, match="Unknown method"):
        surrogates.surrogate_analysis("coin flip", batch_params(dyads, dyads), str(dyads), 5, 1, surrogates.MEAN_R)


def test_a_pair_drawn_again_is_analysed_once(dyads, monkeypatch):
    analysed = []
    original = surrogates._analysed_pair

    def recording(recordings, file_path_a, file_path_b, *args):
        analysed.append((file_path_a, file_path_b))
        return original(recordings, file_path_a, file_path_b, *args)

    monkeypatch.setattr(surrogates, "_analysed_pair", recording)
    result = surrogates.welch_random_pair_test(batch_params(dyads, dyads), str(dyads), 100, seed=1)
    assert len(analysed) == len(set(analysed)) <= 24 + 3
    assert len(result.null_values) == 100


# Results of the version before the surrogate tests were added (commit b76a0dd), for 4 dyads, 12 random pairs and
# seed 3. A seed must keep repeating results of earlier versions.
EARLIER_VERSION_RESULTS = {   # settings: (t, p)
    'windowed': ({}, (-9.499747520785395, 0.0011676895666690478)),
    'standard': ({'checkbox_windowed_xcorr': False}, (-3.951765366455192, 0.022070650988482526)),
}


@pytest.mark.parametrize("variant", EARLIER_VERSION_RESULTS)
def test_seed_repeats_the_result_of_earlier_versions(tmp_path, variant):
    settings, t_and_p = EARLIER_VERSION_RESULTS[variant]
    for index in range(4):
        write_dyad(tmp_path / "in" / f"dyad{index}", seed=index)
    params = batch_params(tmp_path / "in", tmp_path / "in", **settings)
    result = surrogates.welch_random_pair_test(params, str(tmp_path / "in"), 12, seed=3)
    assert (result.t_statistic, result.p_value) == pytest.approx(t_and_p, rel=1e-12)
