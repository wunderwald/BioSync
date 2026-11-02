import re
import zipfile

import pytest
from openpyxl import Workbook

import callbacks
import state
import xlsx


def _write(path, sheets):
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        sheet = wb.create_sheet(name)
        for row in rows:
            sheet.append(row)
    wb.save(path)
    return path


def _columns(tmp_path, rows, headers=True):
    return xlsx.get_columns(xlsx.read_xlsx(_write(tmp_path / "f.xlsx", {"S": rows})), "S", headers=headers)


def test_values_and_headers_are_read(tmp_path):
    assert _columns(tmp_path, [["a", "b"], [1, 2.5], [3, 4]]) == {"a": [1, 3], "b": [2.5, 4]}


def test_without_headers_the_first_row_is_data(tmp_path):
    assert _columns(tmp_path, [[1, 2], [3, 4]], headers=False) == {"Column_1": [1, 3], "Column_2": [2, 4]}


def test_columns_of_different_lengths(tmp_path):
    assert _columns(tmp_path, [["a", "b"], [1, 2], [3, None], [5]]) == {"a": [1, 3, 5], "b": [2]}


def test_header_only_column_is_left_out(tmp_path):
    assert _columns(tmp_path, [["a", "only header"], [1, None], [2, None]]) == {"a": [1, 2]}


def test_empty_column_is_left_out_and_keeps_numbering(tmp_path):
    assert _columns(tmp_path, [[1, None, 2], [3, None, 4]], headers=False) == {"Column_1": [1, 3], "Column_3": [2, 4]}


def test_data_without_a_header_gets_a_name(tmp_path):
    assert _columns(tmp_path, [["a", None], [1, 2]]) == {"a": [1], "Column_2": [2]}


def test_repeated_headers_keep_every_column(tmp_path):
    columns = _columns(tmp_path, [["IBI", "IBI", "other", "IBI"], [1, 2, 3, 4]])
    assert columns == {"IBI": [1], "IBI (2)": [2], "other": [3], "IBI (3)": [4]}


def test_empty_sheet_has_no_columns(tmp_path):
    assert _columns(tmp_path, []) == {}


def test_sheets_keep_their_file_order(tmp_path):
    names = ["Z", "A", "M", "B"]
    workbook = xlsx.read_xlsx(_write(tmp_path / "f.xlsx", {name: [[1]] for name in names}))
    assert xlsx.get_sheet_names(workbook) == names


def test_wrong_size_stored_in_the_file_does_not_cut_off_data(tmp_path):
    path = _write(tmp_path / "f.xlsx", {"S": [["a"], [1], [2], [3]]})
    patched = tmp_path / "patched.xlsx"
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(patched, "w") as target:
        for item in source.namelist():
            data = source.read(item)
            if item.startswith("xl/worksheets/"):
                data = re.sub(rb'<dimension ref="[^"]*"', b'<dimension ref="A1:A1"', data)
            target.writestr(item, data)
    assert xlsx.get_columns(xlsx.read_xlsx(patched), "S") == {"a": [1, 2, 3]}


def test_formula_gives_the_value_excel_calculated(tmp_path):
    path = _write(tmp_path / "f.xlsx", {"S": [["a"], [1], ["=1+1"]]})
    patched = tmp_path / "patched.xlsx"
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(patched, "w") as target:
        for item in source.namelist():
            data = source.read(item)
            if item.startswith("xl/worksheets/"):
                data, count = re.subn(rb"(<f>1\+1</f>)<v\s*/>|(<f>1\+1</f>)<v></v>", rb"<f>1+1</f><v>2</v>", data)
                assert count == 1
            target.writestr(item, data)
    assert xlsx.get_columns(xlsx.read_xlsx(patched), "S") == {"a": [1, 2]}


def test_file_is_closed_after_reading(tmp_path):
    path = _write(tmp_path / "f.xlsx", {"S": [["a"], [1]]})
    workbook = xlsx.read_xlsx(path)
    path.unlink()   # fails on Windows if the file is still open
    assert xlsx.get_columns(workbook, "S") == {"a": [1]}


class FakeDropdown:
    def configure(self, values):
        self.values = values


@pytest.fixture
def gui_files(fake_state, monkeypatch):
    dropdowns = {key: FakeDropdown() for key in ("sheet", "col_a", "col_b")}
    monkeypatch.setattr(callbacks, "_dropdowns", dropdowns)
    monkeypatch.setitem(state.dat_workbook_data, "sheet_names", [])
    fake_state.warnings = []
    monkeypatch.setattr(callbacks.messagebox, "showwarning", lambda title, text: fake_state.warnings.append(title))
    return fake_state


def _load_sheets(monkeypatch, names_a, names_b):
    monkeypatch.setitem(state.dat_workbook_data, "workbook_a", {name: [["a"], [1]] for name in names_a})
    monkeypatch.setitem(state.dat_workbook_data, "workbook_b", {name: [["a"], [1]] for name in names_b})
    callbacks.update_sheet_names()


def test_default_sheet_is_the_first_one_both_files_share(gui_files, monkeypatch):
    _load_sheets(monkeypatch, ["Only A", "Z", "A"], ["A", "Z", "Only B"])
    assert state.dat_workbook_data["sheet_names"] == ["Z", "A"]
    assert gui_files.val_selected_sheet.get() == "Z"
    assert gui_files.warnings == []


def test_files_without_a_common_sheet_give_a_warning_instead_of_a_crash(gui_files, monkeypatch):
    _load_sheets(monkeypatch, ["A"], ["B"])
    assert gui_files.val_selected_sheet.get() == "- None -"
    assert gui_files.warnings == ["No common sheet"]


def test_sheet_without_data_leaves_nothing_selected(gui_files, monkeypatch):
    _load_sheets(monkeypatch, ["S"], ["S"])
    state.dat_workbook_data["workbook_a"]["S"] = [["only header"]]
    monkeypatch.setitem(state.dat_workbook_data, "has_headers", True)
    gui_files.val_selected_column_a.set("old")

    callbacks.update_column_names()

    assert gui_files.val_selected_column_a.get() == "- None -"
    assert gui_files.val_selected_column_b.get() == "a"
