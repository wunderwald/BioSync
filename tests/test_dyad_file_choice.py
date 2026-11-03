"""
Folders with more than two files use the first two with the same sheets, in the GUI, batch and random pairs alike.
"""
import os

import numpy as np
import pytest
from openpyxl import Workbook

import batch_processing
import callbacks
import utils
import xlsx
from helpers import N_BEATS, batch_params, ibi, write_dyad, write_person


def _write_sheets(path, sheet_names):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name in sheet_names:
        workbook.create_sheet(name).append([1])
    workbook.save(path)


def _choose(folder, layouts):
    for name, sheets in layouts.items():
        _write_sheets(folder / name, sheets)
    return xlsx.choose_dyad_files(str(folder), utils.list_dyad_files(str(folder)))


def test_two_files_are_used_without_reading_them(tmp_path):
    # the files don't even exist, and exactly two files are always the dyad
    assert xlsx.choose_dyad_files(str(tmp_path), ["a.xlsx", "b.xlsx"]) == ("a.xlsx", "b.xlsx", True)


def test_first_two_files_are_used_when_they_match(tmp_path):
    layouts = {"a.xlsx": ["S"], "b.xlsx": ["S"], "c.xlsx": ["S"]}
    assert _choose(tmp_path, layouts) == ("a.xlsx", "b.xlsx", True)


@pytest.mark.parametrize("layouts, expected", [
    ({"a.xlsx": ["S"], "b.xlsx": ["T"], "c.xlsx": ["S"]}, ("a.xlsx", "c.xlsx", True)),
    ({"a.xlsx": ["X"], "b.xlsx": ["S"], "c.xlsx": ["S"]}, ("b.xlsx", "c.xlsx", True)),
    ({"a.xlsx": ["S", "T"], "b.xlsx": ["S"], "c.xlsx": ["S", "T"]}, ("a.xlsx", "c.xlsx", True)),
    ({"a.xlsx": ["S"], "b.xlsx": ["T"], "c.xlsx": ["T"], "d.xlsx": ["S"]}, ("a.xlsx", "d.xlsx", True)),
])
def test_first_pair_with_the_same_sheets_is_used(tmp_path, layouts, expected):
    assert _choose(tmp_path, layouts) == expected


def test_sheet_order_is_part_of_the_layout(tmp_path):
    layouts = {"a.xlsx": ["S", "T"], "b.xlsx": ["T", "S"], "c.xlsx": ["S", "T"]}
    assert _choose(tmp_path, layouts) == ("a.xlsx", "c.xlsx", True)


def test_first_two_files_are_the_fallback(tmp_path):
    layouts = {"a.xlsx": ["S"], "b.xlsx": ["T"], "c.xlsx": ["U"]}
    assert _choose(tmp_path, layouts) == ("a.xlsx", "b.xlsx", False)


def test_unreadable_files_are_not_paired_with_each_other(tmp_path):
    (tmp_path / "a.xlsx").write_text("not a spreadsheet")
    (tmp_path / "b.xlsx").write_text("not a spreadsheet")
    _write_sheets(tmp_path / "c.xlsx", ["S"])
    _write_sheets(tmp_path / "d.xlsx", ["S"])
    assert xlsx.choose_dyad_files(str(tmp_path), utils.list_dyad_files(str(tmp_path))) == ("c.xlsx", "d.xlsx", True)


def test_files_are_closed_after_choosing(tmp_path, opened_workbooks):
    _choose(tmp_path, {"a.xlsx": ["S"], "b.xlsx": ["S"], "c.xlsx": ["T"]})
    assert len(opened_workbooks) == 3
    assert all(workbook._archive.fp is None for workbook in opened_workbooks)


def _write_mismatched_dyad(folder):
    """First file has another sheet, the other two are a coupled pair."""
    os.makedirs(folder)
    rng = np.random.default_rng(0)
    coupled = ibi(rng)
    _write_sheets(os.path.join(folder, "A_notes.xlsx"), ["Notes"])
    for name in ("P1.xlsx", "P2.xlsx"):
        write_person(os.path.join(folder, name), {"Coupled": coupled + rng.normal(0, 5, N_BEATS)})


def test_batch_uses_the_matching_pair_and_says_so(tmp_path):
    _write_mismatched_dyad(tmp_path / "in" / "dyad0")
    (tmp_path / "out").mkdir()
    summary = batch_processing.batch_process(batch_params(tmp_path / "in", tmp_path / "out"))
    assert summary['processed'] == ["dyad0"] and summary['failed'] == []
    assert "used P1.xlsx and P2.xlsx" in summary['warnings'][0]


def test_batch_says_when_it_fell_back(tmp_path):
    folder = tmp_path / "in" / "dyad0"
    os.makedirs(folder)
    for name, sheets in {"a.xlsx": ["X"], "b.xlsx": ["Y"], "c.xlsx": ["Z"]}.items():
        _write_sheets(folder / name, sheets)
    (tmp_path / "out").mkdir()
    summary = batch_processing.batch_process(batch_params(tmp_path / "in", tmp_path / "out"))
    assert "because no two have the same sheets" in summary['warnings'][0]


def test_random_pairs_use_the_matching_pair_for_real_dyads(tmp_path, monkeypatch):
    _write_mismatched_dyad(tmp_path / "in" / "dyad0")
    write_dyad(tmp_path / "in" / "dyad1", seed=1)
    used = []
    real = batch_processing._process_dyad

    def recording(file_path_a, file_path_b, *args, **kwargs):
        used.append((os.path.basename(file_path_a), os.path.basename(file_path_b)))
        return real(file_path_a, file_path_b, *args, **kwargs)

    monkeypatch.setattr(batch_processing, "_process_dyad", recording)
    monkeypatch.setattr(batch_processing, "ttest_ind", lambda *args, **kwargs: (0, 1))
    batch_processing.random_pair_analysis(batch_params(tmp_path / "in", tmp_path), str(tmp_path / "in"), random_pair_count=0)
    assert used == [("P1.xlsx", "P2.xlsx"), ("P1.xlsx", "P2.xlsx")]


@pytest.mark.parametrize("layouts, expected_files, expected_reason", [
    ({"a.xlsx": ["X"], "b.xlsx": ["S"], "c.xlsx": ["S"]}, ("b.xlsx", "c.xlsx"), "the first two with the same sheets"),
    ({"a.xlsx": ["X"], "b.xlsx": ["Y"], "c.xlsx": ["Z"]}, ("a.xlsx", "b.xlsx"), "no two have the same sheets"),
])
def test_folder_picker_loads_the_chosen_pair_and_says_why(fake_state, tmp_path, monkeypatch, layouts, expected_files, expected_reason):
    for name, sheets in layouts.items():
        _write_sheets(tmp_path / name, sheets)
    warnings = []
    monkeypatch.setattr(callbacks.filedialog, "askdirectory", lambda **kwargs: str(tmp_path))
    monkeypatch.setattr(callbacks.messagebox, "showwarning", lambda title, text: warnings.append(text))
    monkeypatch.setattr(callbacks, "show_loaded_workbooks", lambda: None)
    monkeypatch.setattr(callbacks.state, "PARAMS_CHANGED", lambda: None)

    callbacks.open_dir_picker()

    assert os.path.basename(fake_state.val_selected_file_a.get()) == expected_files[0]
    assert os.path.basename(fake_state.val_selected_file_b.get()) == expected_files[1]
    assert expected_reason in warnings[0]


def test_uppercase_extension_is_found(tmp_path):
    for name in ("P1.XLSX", "p2.Xlsx", "notes.txt", "~$P1.XLSX", "._P1.XLSX"):
        (tmp_path / name).write_text("x")
    assert utils.list_dyad_files(str(tmp_path)) == ["P1.XLSX", "p2.Xlsx"]


def test_uppercase_files_can_be_read(tmp_path):
    _write_sheets(tmp_path / "A.XLSX", ["S"])
    assert xlsx.get_sheet_names(xlsx.read_xlsx(str(tmp_path / "A.XLSX"))) == ["S"]


@pytest.fixture
def picker(fake_state, tmp_path, monkeypatch):
    """A loaded dyad, and a folder picker that returns the folder a test chooses."""
    loaded = tmp_path / "loaded"
    loaded.mkdir()
    fake_state.val_selected_dyad_dir.set(str(loaded))
    fake_state.val_selected_file_a.set(str(loaded / "A.xlsx"))
    fake_state.val_selected_file_b.set(str(loaded / "B.xlsx"))
    monkeypatch.setitem(callbacks.state.dat_workbook_data, "workbook_a", "loaded workbook A")
    monkeypatch.setitem(callbacks.state.dat_workbook_data, "workbook_b", "loaded workbook B")
    fake_state.messages = []
    for kind in ("showwarning", "showerror"):
        monkeypatch.setattr(callbacks.messagebox, kind, lambda title, text, kind=kind: fake_state.messages.append((kind, text)))
    fake_state.shown = []
    monkeypatch.setattr(callbacks, "show_loaded_workbooks", lambda: fake_state.shown.append(True))
    monkeypatch.setattr(callbacks.state, "PARAMS_CHANGED", lambda: None)

    def choose(folder):
        monkeypatch.setattr(callbacks.filedialog, "askdirectory", lambda **kwargs: str(folder))
        callbacks.open_dir_picker()
    fake_state.choose = choose
    fake_state.loaded = loaded
    return fake_state


def _assert_old_dyad_is_kept(picker):
    assert picker.val_selected_dyad_dir.get() == str(picker.loaded)
    assert picker.val_selected_file_a.get() == str(picker.loaded / "A.xlsx")
    assert callbacks.state.dat_workbook_data["workbook_a"] == "loaded workbook A"
    assert picker.shown == []


@pytest.mark.parametrize("n_files", [0, 1])
def test_folder_with_too_few_files_keeps_the_loaded_dyad_and_says_so(picker, tmp_path, n_files):
    folder = tmp_path / "new"
    folder.mkdir()
    for index in range(n_files):
        _write_sheets(folder / f"{index}.xlsx", ["S"])
    picker.choose(folder)
    _assert_old_dyad_is_kept(picker)
    assert picker.messages[0][0] == "showwarning" and f"Found {n_files} xlsx" in picker.messages[0][1]


@pytest.mark.parametrize("broken", ["a.xlsx", "b.xlsx"])
def test_unreadable_file_clears_the_data_and_gives_the_reason(picker, tmp_path, monkeypatch, broken):
    folder = tmp_path / "new"
    folder.mkdir()
    for name in ("a.xlsx", "b.xlsx"):
        _write_sheets(folder / name, ["S"])
    (folder / broken).write_text("not a spreadsheet")
    cleared = []
    monkeypatch.setattr(callbacks, "set_invalid_data", lambda reason: cleared.append(reason))
    picker.choose(folder)
    assert picker.val_selected_dyad_dir.get() == str(folder)     # nothing of the old dyad stays
    assert callbacks.state.dat_workbook_data["workbook_a"] is None or callbacks.state.dat_workbook_data["workbook_b"] is None
    assert len(cleared) == 1 and broken in cleared[0] and "can't be read" in cleared[0]
    assert picker.messages == []


def test_good_folder_replaces_the_loaded_dyad(picker, tmp_path):
    folder = tmp_path / "new"
    folder.mkdir()
    for name in ("a.xlsx", "b.xlsx"):
        _write_sheets(folder / name, ["S"])
    picker.choose(folder)
    assert picker.val_selected_dyad_dir.get() == str(folder)
    assert xlsx.get_sheet_names(callbacks.state.dat_workbook_data["workbook_b"]) == ["S"]
    assert picker.shown == [True] and picker.messages == []
