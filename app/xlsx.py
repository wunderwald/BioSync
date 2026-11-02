from itertools import zip_longest

from openpyxl import Workbook, load_workbook

def write_xlsx(vectors: dict, single_values: dict, output_path: str, sheet_title: str="xcorr data"):
    """
    Write data to an Excel file.
    Args:
        vectors (dict): A dictionary where keys are column names and values are lists of time series data.
        single_value (dict): A dictionary where keys are column names and values are single data values.
        output_path (str): The file path where the Excel file will be saved.
    Returns:
        None
    """

    # Create a new workbook
    wb = Workbook()
    sheet = wb.active
    sheet.title = sheet_title

    # Write the single valued data to columns 
    # (column 1 -> names, column 2 -> values)
    row_index = 1
    for name, value in single_values.items():
        sheet.cell(row=row_index, column=1, value=name)  
        sheet.cell(row=row_index, column=2, value=str(value))  
        row_index += 1
    
    # Write the time series data to columns
    # (one vector with title per column, starting in column 4)
    column_index = 4
    for name in vectors.keys():
        sheet.cell(row=1, column=column_index, value=name)
        for row_index, value in enumerate(vectors[name]):  
            sheet.cell(row=row_index+2, column=column_index, value=str(value))
        column_index += 1

    # Save the workbook
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