import re
import os
import sys
from pathlib import Path
from itertools import combinations
import shutil

# ----------------------------------------
# I/O DATA - SET INPUT & OUTPUT PATHS HERE
# ----------------------------------------
# group data directory: one subdirectory per subject with files per condition
# [path relative to script location]
INPUT_DIR_GROUP = Path('../data/groups/3003')
# output directory: one subdirectory for each possible dyad for each condition with one file per subject
OUTPUT_DIR = Path('../data/groups/dyads_3003')

# the structure of the xlsx files in the input directory
NAMING_PATTERN = r'(?P<type>[^_]+)_(?P<group>[^_]+)_(?P<subject>[^.]+)_(?P<condition>[^.]+)\.xlsx'

# subdirectories this script creates in the output directory
DYAD_DIR_PREFIX = 'dyad_'

# -------
# HELPERS
# -------
def parse_filename(filename):
    """
    Parses a filename using a predefined regular expression pattern and extracts named substrings.
    Args:
        filename (str): The filename to be parsed.
    Returns:
        dict: A dictionary containing the named substrings extracted from the filename if the pattern matches, otherwise empty dict.
    """
    pattern = re.compile(NAMING_PATTERN)
    match = pattern.match(filename)
    if match:
        return match.groupdict()
    else:
        return {}
def find_dict_by_field(dicts, field, value):
    return next((d for d in dicts if d.get(field) == value), None)

def is_inside(path, parent):
    return path == parent or parent in path.parents

# ---------------
# PARSE INPUT DIR
# ---------------
def read_subjects(input_dir):
    """
    Lists the subjects in the input directory with their per-condition files.
    Args:
        input_dir (Path): Directory with one subdirectory per subject.
    Returns:
        list: One dict per subject with 'id', 'dir' and 'conditions'.
    Raises:
        ValueError: If a file name doesn't match NAMING_PATTERN.
    """
    # get list of per-subject directories
    subject_ids = [subdir for subdir in os.listdir(input_dir) if os.path.isdir(os.path.join(input_dir, subdir))]
    subjects = [{'id': subject_id, 'dir': Path.joinpath(input_dir, subject_id)} for subject_id in subject_ids]

    # append information about per-condition files to subject data
    for subject in subjects:
        xlsx_files = [f for f in os.listdir(subject['dir']) if f.endswith('.xlsx')]
        xlsx_files_info = [{'path': Path.joinpath(subject['dir'], f), **parse_filename(f)} for f in xlsx_files]
        for file_info in xlsx_files_info:
            if 'condition' not in file_info:
                raise ValueError(f"File name doesn't match the naming pattern: {file_info['path']}")
        subject['conditions'] = [{'condition': d['condition'], 'path': d['path']} for d in xlsx_files_info]
    return subjects

# ---------------
# PREPARE OUTPUT DIR
# ---------------
def prepare_output_dir(output_dir, input_dir, confirm=input):
    """
    Makes sure the output directory exists and is empty. Only deletes earlier dyad directories of this script,
    and only after asking. Anything else in the output directory stops the script, as it may be the only copy.
    Args:
        output_dir (Path): The output directory.
        input_dir (Path): The input directory, which must not be affected.
        confirm (function): Asks a question and returns the answer.
    Returns:
        bool: True if the output directory is ready, False if the user declined.
    Raises:
        ValueError: If the output directory overlaps the input directory or contains anything unexpected.
    """
    if is_inside(input_dir, output_dir) or is_inside(output_dir, input_dir):
        raise ValueError(f"Input and output directories overlap: {input_dir}, {output_dir}")

    if not output_dir.exists():
        output_dir.mkdir(parents=True)
        return True

    # hidden system files such as .DS_Store are safe to delete
    items = [item for item in output_dir.iterdir() if not item.name.startswith('.')]
    unexpected = [item.name for item in items if not (item.is_dir() and item.name.startswith(DYAD_DIR_PREFIX))]
    if unexpected:
        raise ValueError(f"Output directory contains something this script didn't create: {unexpected[:5]}")
    unexpected = [str(sub) for item in items for sub in item.iterdir() if sub.is_dir()]
    if unexpected:
        raise ValueError(f"Dyad directory contains a subdirectory this script didn't create: {unexpected[:5]}")

    if items:
        try:
            answer = confirm(f"Delete {len(items)} earlier dyad directories in {output_dir}? [y/N] ")
        except EOFError:
            answer = ''
        if answer.strip().lower() != 'y':
            return False

    for item in output_dir.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    return True

# ---------------------
# MAKE AND EXPORT DYADS
# ---------------------
def export_dyads(subjects, output_dir):
    # dyads: all possible combinations of subjcts
    dyads = list(combinations([s for s in subjects], 2))

    # for each dyad , for each condition, create a subdirectory in the output dir with two xlsx files 
    for (subject_0, subject_1) in dyads:
        conditions_sub_0 = [c['condition'] for c in subject_0['conditions']]
        conditions_sub_1 = [c['condition'] for c in subject_1['conditions']]
        common_conditions = set(conditions_sub_0) & set(conditions_sub_1)
        for condition in common_conditions:
            # get xlsx files for current condition
            subject_0_xlsx_path = find_dict_by_field(subject_0['conditions'], 'condition', condition)['path']
            subject_1_xlsx_path = find_dict_by_field(subject_1['conditions'], 'condition', condition)['path']

            # make output subdir
            output_subdir = f"{DYAD_DIR_PREFIX}{subject_0['id']}_{subject_1['id']}_{condition}"
            output_subdir_path = Path.joinpath(output_dir, output_subdir)
            output_subdir_path.mkdir(parents=True, exist_ok=True)
            dest_0 = output_subdir_path / Path(subject_0_xlsx_path).name
            dest_1 = output_subdir_path / Path(subject_1_xlsx_path).name
            shutil.copy(subject_0_xlsx_path, dest_0)
            shutil.copy(subject_1_xlsx_path, dest_1)

def main(input_dir, output_dir, confirm=input):
    """Reads the input first, so that a problem there can't cost the earlier output."""
    input_dir, output_dir = input_dir.resolve(), output_dir.resolve()
    subjects = read_subjects(input_dir)
    if not prepare_output_dir(output_dir, input_dir, confirm):
        print("Nothing changed.")
        return False
    export_dyads(subjects, output_dir)
    return True

if __name__ == '__main__':
    script_dir = Path(__file__).parent
    try:
        main(script_dir / INPUT_DIR_GROUP, script_dir / OUTPUT_DIR)
    except (ValueError, OSError) as e:
        sys.exit(f"Nothing changed: {e}")
