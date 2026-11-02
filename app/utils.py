import os


def count_subdirectories(directory):
    """
    Returns the number of subdirectories in the given directory.

    Parameters:
    directory (str): The path to the directory.

    Returns:
    int: The number of subdirectories.
    """
    try:
        return sum(os.path.isdir(os.path.join(directory, entry)) for entry in os.listdir(directory))
    except FileNotFoundError:
        print(f"The directory {directory} does not exist.")
        return 0
    except PermissionError:
        print(f"Permission denied to access the directory {directory}.")
        return 0


def list_dyad_files(directory):
    """
    Returns the xlsx file names in a dyad folder in a fixed order, which decides who is person A and B.
    os.listdir has no defined order. Excel lock files (~$) and hidden files (.) are ignored.

    Parameters:
    directory (str): The path to the dyad folder.

    Returns:
    list: The file names, sorted alphabetically ignoring case.
    """
    file_names = [
        f for f in os.listdir(directory)
        if f.endswith('.xlsx') and not f.startswith(('~$', '.'))
    ]
    return sorted(file_names, key=str.casefold)


def is_numeric_array(arr):
    if not isinstance(arr, (list, tuple)):
        return False
    try:
        return all(isinstance(x, (int, float)) for x in arr)
    except Exception:
        return False
