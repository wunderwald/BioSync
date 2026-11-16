"""
The app's name in the macOS menu bar: "BioSync", not "Python", when it runs from source. Checked in its own
process, as the name can be set only once, before the first window.
"""
import ast
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import utils

APP_DIR = Path(utils.__file__).parent

MENU_TITLE = textwrap.dedent("""
    import ctypes, ctypes.util, sys, tkinter
    import utils
    if sys.argv[1] == "named":
        utils.set_macos_app_name("BioSync")
    root = tkinter.Tk()
    root.withdraw()
    root.update()
    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    def send(receiver, selector, *args):
        message = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, *([ctypes.c_void_p] * len(args)))
        return message(ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value)(
            receiver, objc.sel_registerName(selector), *args)
    application = send(objc.objc_getClass(b"NSApplication"), b"sharedApplication")
    app_menu = send(send(send(application, b"mainMenu"), b"itemAtIndex:", 0), b"submenu")
    print(ctypes.string_at(send(send(app_menu, b"title"), b"UTF8String")).decode())
    root.destroy()
""")


@pytest.mark.skipif(sys.platform != 'darwin', reason="the menu bar name is a macOS matter")
@pytest.mark.parametrize("named, title", [(True, "BioSync"), (False, "Python")])
def test_menu_bar_says_biosync(named, title):
    result = subprocess.run([sys.executable, "-c", MENU_TITLE, "named" if named else "unnamed"], cwd=APP_DIR,
                            capture_output=True, text=True, timeout=60)
    if result.returncode and "display" in result.stderr:
        pytest.skip("needs a display")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == title       # without the name, the menu bar shows Python's


def test_the_app_is_named_before_its_window_is_created():
    calls = [node.func for node in ast.walk(ast.parse((APP_DIR / "app.py").read_text()))
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    lines = {f"{call.value.id}.{call.attr}": call.lineno for call in calls if isinstance(call.value, ast.Name)}
    assert lines["utils.set_macos_app_name"] < lines["tk.CTk"]


def test_does_nothing_elsewhere(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    utils.set_macos_app_name("BioSync")     # no error, nothing to do
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    utils.set_macos_app_name("BioSync")     # a built app has its bundle's name
