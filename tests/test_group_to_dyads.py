import importlib.util
from pathlib import Path

import pytest
from openpyxl import Workbook

_spec = importlib.util.spec_from_file_location(
    "group_to_dyads", Path(__file__).parents[1] / "preprocessing" / "group_to_dyads.py"
)
group_to_dyads = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(group_to_dyads)


def _no_questions(question):
    pytest.fail(f"Asked: {question}")


@pytest.fixture
def dirs(tmp_path):
    input_dir = tmp_path / "group"
    for subject in ("s1", "s2", "s3"):
        (input_dir / subject).mkdir(parents=True)
        for condition in ("rest", "task"):
            Workbook().save(input_dir / subject / f"HRV_g1_{subject}_{condition}.xlsx")
    return input_dir, tmp_path / "dyads"


def _earlier_output(output_dir):
    earlier = output_dir / "dyad_old_old_rest"
    earlier.mkdir(parents=True)
    (earlier / "old.xlsx").write_text("old")
    return earlier


def test_all_dyads_for_all_conditions_are_created(dirs):
    input_dir, output_dir = dirs
    assert group_to_dyads.main(input_dir, output_dir, _no_questions) is True
    assert len(list(output_dir.iterdir())) == 6     # 3 pairs, 2 conditions
    assert all(len(list(dyad.iterdir())) == 2 for dyad in output_dir.iterdir())


def test_importing_the_script_has_no_side_effects():
    assert group_to_dyads.DYAD_DIR_PREFIX == "dyad_"


@pytest.mark.parametrize("answer", ["", "n", "no", "maybe"])
def test_earlier_output_stays_unless_confirmed(dirs, answer):
    input_dir, output_dir = dirs
    earlier = _earlier_output(output_dir)
    assert group_to_dyads.main(input_dir, output_dir, lambda question: answer) is False
    assert (earlier / "old.xlsx").read_text() == "old"
    assert len(list(output_dir.iterdir())) == 1


def test_no_answer_available_keeps_earlier_output(dirs):
    input_dir, output_dir = dirs
    earlier = _earlier_output(output_dir)

    def no_terminal(question):
        raise EOFError

    assert group_to_dyads.main(input_dir, output_dir, no_terminal) is False
    assert earlier.exists()


@pytest.mark.parametrize("answer", ["y", "Y", " y "])
def test_confirmed_earlier_output_is_replaced(dirs, answer):
    input_dir, output_dir = dirs
    earlier = _earlier_output(output_dir)
    assert group_to_dyads.main(input_dir, output_dir, lambda question: answer) is True
    assert not earlier.exists()
    assert len(list(output_dir.iterdir())) == 6


def test_question_says_what_would_be_deleted(dirs):
    input_dir, output_dir = dirs
    _earlier_output(output_dir)
    questions = []
    group_to_dyads.main(input_dir, output_dir, lambda question: questions.append(question) or "n")
    assert "1 earlier dyad directories" in questions[0] and str(output_dir.resolve()) in questions[0]


@pytest.mark.parametrize("make_item", [
    lambda d: (d / "my_notes.xlsx").write_text("notes"),
    lambda d: (d / "analysis").mkdir(),
    lambda d: (d / "dyad_file.txt").write_text("a file, not a dyad directory"),
])
def test_output_with_anything_unexpected_is_left_alone(dirs, make_item):
    input_dir, output_dir = dirs
    earlier = _earlier_output(output_dir)
    make_item(output_dir)
    with pytest.raises(ValueError, match="didn't create"):
        group_to_dyads.main(input_dir, output_dir, _no_questions)
    assert earlier.exists()
    assert len(list(output_dir.iterdir())) == 2


def test_subdirectory_inside_a_dyad_is_left_alone(dirs):
    input_dir, output_dir = dirs
    earlier = _earlier_output(output_dir)
    (earlier / "results").mkdir()
    with pytest.raises(ValueError, match="didn't create"):
        group_to_dyads.main(input_dir, output_dir, _no_questions)
    assert (earlier / "results").exists()


@pytest.mark.parametrize("output", ["same", "inside", "parent"])
def test_overlapping_directories_are_refused(dirs, output):
    input_dir, _ = dirs
    output_dir = {"same": input_dir, "inside": input_dir / "out", "parent": input_dir.parent}[output]
    with pytest.raises(ValueError, match="overlap"):
        group_to_dyads.main(input_dir, output_dir, _no_questions)
    assert sum(1 for _ in input_dir.rglob("*.xlsx")) == 6


def test_problem_in_the_input_leaves_earlier_output(dirs):
    input_dir, output_dir = dirs
    earlier = _earlier_output(output_dir)
    (input_dir / "s1" / "badname.xlsx").write_text("x")
    with pytest.raises(ValueError, match="naming pattern"):
        group_to_dyads.main(input_dir, output_dir, lambda question: "y")
    assert earlier.exists()


def test_missing_input_leaves_earlier_output(tmp_path):
    earlier = _earlier_output(tmp_path / "dyads")
    with pytest.raises(OSError):
        group_to_dyads.main(tmp_path / "missing", tmp_path / "dyads", lambda question: "y")
    assert earlier.exists()


def test_hidden_system_file_does_not_block_a_rerun(dirs):
    input_dir, output_dir = dirs
    output_dir.mkdir()
    (output_dir / ".DS_Store").write_text("x")
    assert group_to_dyads.main(input_dir, output_dir, _no_questions) is True
    assert not (output_dir / ".DS_Store").exists()
    assert len(list(output_dir.iterdir())) == 6


def test_macos_and_excel_temporary_files_are_ignored(dirs):
    input_dir, output_dir = dirs
    for subject in ("s1", "s2", "s3"):
        (input_dir / subject / f"._HRV_g1_{subject}_rest.xlsx").write_bytes(b"\x00\x05\x16\x07")
        (input_dir / subject / f"~$HRV_g1_{subject}_extra.xlsx").write_bytes(b"x")
    (input_dir / ".hidden_subject").mkdir()
    group_to_dyads.main(input_dir, output_dir, _no_questions)
    folders = sorted(path.name for path in output_dir.iterdir())
    assert not any("extra" in name for name in folders) and len(folders) == 6
    for folder in output_dir.iterdir():
        files = sorted(path.name for path in folder.iterdir())
        assert len(files) == 2 and not any(name.startswith(("._", "~$")) for name in files)


def test_folder_names_do_not_depend_on_listing_order(dirs, monkeypatch):
    input_dir, output_dir = dirs
    real_listdir = group_to_dyads.os.listdir
    monkeypatch.setattr(group_to_dyads.os, "listdir", lambda path: sorted(real_listdir(path), reverse=True))
    group_to_dyads.main(input_dir, output_dir, _no_questions)
    assert sorted(path.name for path in output_dir.iterdir()) == [
        "dyad_s1_s2_rest", "dyad_s1_s2_task", "dyad_s1_s3_rest", "dyad_s1_s3_task", "dyad_s2_s3_rest", "dyad_s2_s3_task",
    ]


def test_uppercase_extension_is_a_recording(dirs):
    input_dir, output_dir = dirs
    for subject in ("s1", "s2", "s3"):
        (input_dir / subject / f"HRV_g1_{subject}_rest.xlsx").rename(input_dir / subject / f"HRV_g1_{subject}_rest.XLSX")
    group_to_dyads.main(input_dir, output_dir, _no_questions)
    assert len(list((output_dir / "dyad_s1_s2_rest").iterdir())) == 2
