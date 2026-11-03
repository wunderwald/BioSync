"""
Random pairs must not contain real pairs or the same person twice, and a seed must repeat a run.
"""
import os
import shutil

import openpyxl
import pytest

import batch_processing
import callbacks
from batch_processing import _eligible_random_pairs
from test_batch import ImmediateTimer, _params, _write_dyad


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
        batch_processing.random_pair_analysis(_params(tmp_path, tmp_path), str(tmp_path), random_pair_count=3)


@pytest.fixture
def dyads(tmp_path):
    for index in range(3):
        _write_dyad(tmp_path / "in" / f"dyad{index}", seed=index)
    return tmp_path / "in"


def _recorded_pairs(monkeypatch):
    """Records which files are analysed, and stops the slow analysis from running."""
    used = []

    def fake_process(file_path_a, file_path_b, *args, **kwargs):
        used.append((file_path_a, file_path_b))
        return None

    monkeypatch.setattr(batch_processing, "_process_dyad", fake_process)
    monkeypatch.setattr(batch_processing, "ttest_ind", lambda *args, **kwargs: (0, 1))
    return used


def test_drawn_pairs_are_always_from_different_folders(dyads, monkeypatch):
    used = _recorded_pairs(monkeypatch)
    batch_processing.random_pair_analysis(_params(dyads, dyads), str(dyads), random_pair_count=300, seed=1)
    random_pairs = used[:300]
    assert all(os.path.dirname(a) != os.path.dirname(b) for a, b in random_pairs)
    assert len({frozenset(pair) for pair in random_pairs}) == 12     # every possible pair turns up


def test_both_people_can_be_person_a(dyads, monkeypatch):
    used = _recorded_pairs(monkeypatch)
    batch_processing.random_pair_analysis(_params(dyads, dyads), str(dyads), random_pair_count=300, seed=1)
    assert len(set(used[:300])) == 24


def test_same_seed_repeats_the_pairs_and_another_seed_does_not(dyads, monkeypatch):
    used = _recorded_pairs(monkeypatch)

    def draw(seed):
        used.clear()
        batch_processing.random_pair_analysis(_params(dyads, dyads), str(dyads), random_pair_count=30, seed=seed)
        return list(used[:30])

    assert draw(7) == draw(7)
    assert draw(7) != draw(8)


def test_same_seed_repeats_the_whole_result(dyads):
    params = _params(dyads, dyads)
    first = batch_processing.random_pair_analysis(params, str(dyads), random_pair_count=5, seed=7)
    second = batch_processing.random_pair_analysis(params, str(dyads), random_pair_count=5, seed=7)
    assert first[:2] == second[:2]
    assert first[2] == second[2]
    assert first[7] == second[7] == 12


@pytest.fixture
def app(fake_state, dyads, tmp_path, monkeypatch):
    for name in ("val_INPUT_DATA_VALID", "val_CORRELATION_SETTINGS_VALID", "val_CORRELATION_SETTINGS_VALID_SXC",
                 "val_checkbox_windowed_xcorr"):
        getattr(fake_state, name).set(True)
    fake_state.val_job_running.set(False)
    fake_state.val_job_progress.set(0)
    fake_state.val_rp_n.set(3)
    fake_state.val_rp_seed_input.set("")
    fake_state.val_random_pair_input_folder.set(str(dyads))
    fake_state.val_random_pair_output_file.set(str(tmp_path / "rp.xlsx"))
    fake_state.timer = ImmediateTimer()
    monkeypatch.setitem(callbacks._tabview, "tabview", fake_state.timer)
    monkeypatch.setattr(callbacks, "_analysis_params", lambda: _params(dyads, tmp_path))
    fake_state.dialogs = []
    for kind in ("showinfo", "showerror"):
        monkeypatch.setattr(callbacks.messagebox, kind, lambda title, text: fake_state.dialogs.append((title, text)))
    fake_state.output = tmp_path / "rp.xlsx"
    return fake_state


def _run_and_read(app):
    callbacks.handle_run_random_pair_button()
    app.timer.run_until_idle(60)
    sheet = openpyxl.load_workbook(app.output).worksheets[0]
    return {row[0]: row[1] for row in sheet.iter_rows(max_col=2, values_only=True) if row[0]}


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


def test_new_rows_come_after_the_existing_ones(app):
    app.val_rp_seed_input.set("1")
    callbacks.handle_run_random_pair_button()
    app.timer.run_until_idle(60)
    sheet = openpyxl.load_workbook(app.output).worksheets[0]
    names = [row[0] for row in sheet.iter_rows(max_col=1, values_only=True) if row[0]]
    assert names[:2] == ['t-statistic', 'p-value']
    assert names[-6:] == [
        'Input dyad directory', 'Random seed', 'Different random pairs possible',
        'Random pairs requested', 'Random pairs used', 'Real dyads used',
    ]


def test_seed_is_read_before_the_job_starts(app):
    app.val_rp_seed_input.set("1234")
    callbacks.handle_run_random_pair_button()
    app.val_rp_seed_input.set("99")
    app.timer.run_until_idle(60)
    metadata = {row[0]: row[1] for row in openpyxl.load_workbook(app.output).worksheets[0].iter_rows(max_col=2, values_only=True) if row[0]}
    assert metadata['Random seed'] == 1234


def test_group_to_dyads_copies_end_to_end(tmp_path, monkeypatch):
    """Real spreadsheets, with the same person's file copied to two folders."""
    root = tmp_path / "in"
    for seed, name in enumerate(("dyad_1_2", "dyad_3_4")):
        _write_dyad(root / name, seed=seed)
    shutil.copy(root / "dyad_1_2" / "P1.xlsx", root / "dyad_3_4" / "P3.xlsx")
    used = _recorded_pairs(monkeypatch)
    batch_processing.random_pair_analysis(_params(root, root), str(root), random_pair_count=100, seed=1)
    pairs = used[:100]
    hashes = [(batch_processing._file_hash(a), batch_processing._file_hash(b)) for a, b in pairs]
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
    callbacks._show_random_pair_summary(_summary(**overrides))
    assert shown[0][0] == kind


@pytest.mark.parametrize("n", [0, 1])
def test_too_small_n_does_not_start(app, n, monkeypatch):
    app.val_rp_n.set(n)
    warnings = []
    monkeypatch.setattr(callbacks.messagebox, "showwarning", lambda title, text: warnings.append(text))
    callbacks.handle_run_random_pair_button()
    assert app.val_job_running.get() is False
    assert "at least 2" in warnings[0]
    assert not app.output.exists()


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
    callbacks.handle_run_random_pair_button()
    app.timer.run_until_idle(60)
    metadata = {row[0]: row[1] for row in openpyxl.load_workbook(app.output).worksheets[0].iter_rows(max_col=2, values_only=True) if row[0]}
    assert metadata['Random pairs requested'] == 20
    assert metadata['Random pairs used'] < 20
    assert metadata['Real dyads used'] == 2
    assert warnings and "random pairs were skipped" in warnings[0]
