import os
import sys


def resource_path(file_name):
    """
    Returns the path of a file that ships with the app, wherever the app was launched from.
    A PyInstaller build unpacks these files to the folder in sys._MEIPASS.
    """
    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, file_name)


def set_macos_app_name(name):
    """
    Names the app in the macOS menu bar. Run from source, the app is Python's, so the menu bar says "Python"; a
    built app has the name of its bundle. Tk reads the name when the first window is created, so this has to run
    before. It changes the name in the running program only, through the Objective-C runtime, and does nothing
    elsewhere or if anything is unexpected.
    """
    if sys.platform != 'darwin' or getattr(sys, 'frozen', False):
        return
    try:
        import ctypes
        import ctypes.util
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))
        ctypes.cdll.LoadLibrary(ctypes.util.find_library('Foundation'))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]

        def send(receiver, selector, *args, restype=ctypes.c_void_p):
            # objc_msgSend takes the types of each call, which must be given exactly on Apple silicon
            message = ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p,
                                       *(ctypes.c_char_p if isinstance(arg, bytes) else ctypes.c_void_p for arg in args))
            return message(ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value)(
                receiver, objc.sel_registerName(selector), *args)

        def text(value):
            return send(objc.objc_getClass(b"NSString"), b"stringWithUTF8String:", value.encode())

        bundle = send(objc.objc_getClass(b"NSBundle"), b"mainBundle")
        for dictionary in (send(bundle, b"localizedInfoDictionary"), send(bundle, b"infoDictionary")):
            # only a mutable dictionary can be changed; changing another one would end the program
            if dictionary and send(dictionary, b"respondsToSelector:", objc.sel_registerName(b"setObject:forKey:"),
                                   restype=ctypes.c_bool):
                send(dictionary, b"setObject:forKey:", text(name), text("CFBundleName"))
    except Exception:
        pass        # the name is cosmetic


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


# Every file BioSync writes is called BioSync_<analysis>_<subject>, see output_name
OUTPUT_PREFIX = "BioSync"
WINDOWED, STANDARD, SURROGATES = "wcc", "scc", "surrogates"


def output_name(analysis, subject=None):
    """
    The name of a file BioSync writes, without extension: BioSync_<analysis>_<subject>, or BioSync_<analysis>
    without a subject. analysis is WINDOWED, STANDARD or SURROGATES; subject is a dyad or folder name.
    """
    return f"{OUTPUT_PREFIX}_{analysis}_{subject}" if subject else f"{OUTPUT_PREFIX}_{analysis}"


def is_biosync_output(file_name):
    """True for files BioSync wrote, also with the lower-case prefix of earlier versions' suggested names."""
    return file_name.casefold().startswith(f"{OUTPUT_PREFIX}_".casefold())


def list_dyad_files(directory):
    """
    Returns the xlsx file names in a dyad folder in a fixed order, which decides who is person A and B.
    os.listdir has no defined order. Excel lock files (~$), hidden files (.) and BioSync's own results
    (BioSync_..., see output_name) are ignored, and the extension can be in any case (.xlsx, .XLSX).

    Parameters:
    directory (str): The path to the dyad folder.

    Returns:
    list: The file names, sorted alphabetically ignoring case.
    """
    file_names = [
        f for f in os.listdir(directory)
        if f.lower().endswith('.xlsx') and not f.startswith(('~$', '.')) and not is_biosync_output(f)
    ]
    return sorted(file_names, key=str.casefold)


def is_numeric_array(arr):
    if not isinstance(arr, (list, tuple)):
        return False
    try:
        return all(isinstance(x, (int, float)) for x in arr)
    except Exception:
        return False
