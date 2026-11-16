import os
from itertools import combinations, zip_longest

import math

import numpy as np
from openpyxl import Workbook, load_workbook

# Excel's limits
MAX_ROWS = 1048576
MAX_COLUMNS = 16384

def typed_cell(value):
    """
    The value to store in a cell of a table that programs read: numbers as numbers, booleans as TRUE/FALSE,
    text as text, and nothing, NaN or infinity as an empty cell, which pandas and R read as missing.
    """
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or isinstance(value, bool) or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None
    return str(value)


def matrix_table(matrix: dict):
    """
    A matrix as a table for write_tables: 'title', 'corner' (the top left cell), 'row_labels', 'column_labels'
    and 'rows'. Its row labels become the first column.
    """
    return {
        'title': matrix['title'],
        'columns': [matrix['corner'], *matrix['column_labels']],
        'rows': [[label, *row] for label, row in zip(matrix['row_labels'], matrix['rows'])],
    }


def write_tables(output_path: str, sheets: list):
    """
    Write an Excel file of tables, one per sheet, so that each sheet can be read in one call, such as
    pandas.read_excel(path, sheet_name=title). Each sheet is a dict with 'title', 'columns' (the first row) and
    'rows'. Cells are written as typed_cell says.
    """
    wb = Workbook()
    wb.remove(wb.active)
    for table in sheets:
        if len(table['rows']) + 1 > MAX_ROWS or len(table['columns']) > MAX_COLUMNS:
            raise ValueError(f"Too much data for an Excel sheet: {len(table['rows'])} rows, "
                             f"{len(table['columns'])} columns in '{table['title']}'.")
        sheet = wb.create_sheet(table['title'])
        sheet.append([typed_cell(column) for column in table['columns']])
        for row in table['rows']:
            sheet.append([typed_cell(value) for value in row])
    wb.save(output_path)


def read_xlsx(input_path: str):
    """
    Read the values of all sheets in an xlsx file. Cells with formulas give the value Excel last calculated.
    Args:
        input_path (str): The file path where the Excel file is saved.
    Returns:
        workbook (dict): Sheet names in file order, each with a list of its rows
    """
    wb = load_workbook(input_path, read_only=True, data_only=True)
    try:
        workbook = {}
        for sheet in wb.worksheets:
            sheet.reset_dimensions()  # the size stored in the file can be wrong, which would cut off data
            workbook[sheet.title] = list(sheet.iter_rows(values_only=True))
    finally:
        wb.close()
    return workbook

def read_sheet_names(input_path: str):
    try:
        wb = load_workbook(input_path, read_only=True)
    except Exception:
        return None  # an unreadable file can't be part of a pair
    sheet_names = wb.sheetnames
    wb.close()
    return sheet_names

def choose_dyad_files(directory: str, file_names: list):
    """
    Choose the two files of a dyad from a folder's files, which are the result of utils.list_dyad_files.
    With more than two files, this is the first pair with the same sheets, as those are probably the same kind of
    recording. If there is no such pair, it is the first two files.
    Args:
        directory (str): The path to the dyad folder.
        file_names (list): At least two file names, in their fixed order.
    Returns:
        file_a (str), file_b (str), sheets_match (bool): sheets_match is False if the first two files were a fallback
    """
    if len(file_names) == 2:
        return file_names[0], file_names[1], True
    sheet_names = {name: read_sheet_names(os.path.join(directory, name)) for name in file_names}
    for name_a, name_b in combinations(file_names, 2):
        if sheet_names[name_a] is not None and sheet_names[name_a] == sheet_names[name_b]:
            return name_a, name_b, True
    return file_names[0], file_names[1], False

def get_sheet_names(workbook: dict):
    """
    Get the names of the sheets in the workbook.
    Args:
        workbook (dict): Result of read_xlsx
    Returns:
        sheet_names (list): List of sheet names
    """
    sheet_names = list(workbook)
    return sheet_names

def _unique_column_name(name: str, columns: dict):
    if name not in columns:
        return name
    count = 2
    while f"{name} ({count})" in columns:
        count += 1
    return f"{name} ({count})"

def get_columns(workbook: dict, sheet_name: str, headers: bool=True):
    """
    Get the columns from the sheet in the workbook.
    Args:
        workbook (dict): Result of read_xlsx
        sheet_name (str): The name of the sheet
        headers (bool): If True, the first row is considered as headers. Default is True.
    Returns:
        columns (dict): A dictionary where keys are column names and values are lists of data. Columns without
            data are left out, and repeated names get a suffix, such as "IBI (2)".
    """
    columns = {}
    for index, column in enumerate(zip_longest(*workbook[sheet_name])):
        # skip empty columns
        if all(value is None for value in column):
            continue

        # create header-data pairs, 
        if headers:
            column_name = f"Column_{index+1}" if column[0] is None else f"{column[0]}"
            column_data = list(column[1:])
        else:
            column_name = f"Column_{index+1}"
            column_data = list(column)

        # remove trailing None values
        while column_data and column_data[-1] is None:
            column_data = column_data[:-1]

        # skip columns with only a header
        if not column_data:
            continue

        # add to the dictionary
        columns[_unique_column_name(column_name, columns)] = column_data
    return columns