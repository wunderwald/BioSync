#!/usr/bin/env python3
"""
Builds the standalone app from BioSync.spec. The result is in dist/.
"""

import os
import subprocess
import sys
from pathlib import Path


# Tk 8.6.12 on macOS can ignore clicks until the title bar is clicked (python/cpython#110218).
# The built app includes the Tk of the Python that builds it, so users would get the same problem.
MIN_MACOS_TK_VERSION = (8, 6, 13)


def is_affected_tk(platform, tk_version):
    return platform == "darwin" and tuple(int(part) for part in tk_version.split(".")) < MIN_MACOS_TK_VERSION


def warn_about_tk():
    import tkinter
    tk_version = tkinter.Tcl().eval("info patchlevel")
    if is_affected_tk(sys.platform, tk_version):
        print(f"WARNING: this Python has Tk {tk_version}, where the built app can ignore clicks. See app/README.md.")


# Where the built app keeps the Tcl and Tk script folders. PyInstaller's tkinter runtime hook looks for them there.
TCL_DATA = '_tcl_data'
TK_DATA = '_tk_data'

# Where Python installations keep those folders, relative to the installation: python.org on Windows,
# macOS and Linux, and conda on Windows
TCL_TK_PARENT_FOLDERS = ('tcl', 'lib', os.path.join('Library', 'lib'))


def find_tcl_tk_data(base_prefix, tcl_version, tk_version):
    """
    The Tcl and Tk script folders of a Python installation, or None if they can't be found. PyInstaller only
    looks where Tcl says its scripts are, and builds an app that can't start if that is wrong.
    """
    for parent in TCL_TK_PARENT_FOLDERS:
        tcl_dir = os.path.join(base_prefix, parent, f"tcl{tcl_version}")
        tk_dir = os.path.join(base_prefix, parent, f"tk{tk_version}")
        if os.path.isfile(os.path.join(tcl_dir, "init.tcl")) and os.path.isfile(os.path.join(tk_dir, "tk.tcl")):
            return tcl_dir, tk_dir
    return None


def describe_tcl():
    """Prints where this Python's Tcl is, which explains a build without Tcl/Tk."""
    import tkinter
    library = tkinter.Tcl().eval("info library")
    print(f"Building with {sys.executable}")
    print(f"Tcl says its scripts are in {library} ({'found' if os.path.isdir(library) else 'NOT FOUND'})")


def main():
    describe_tcl()
    warn_about_tk()
    app_dir = Path(__file__).parent
    command = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "BioSync.spec"]
    sys.exit(subprocess.run(command, cwd=app_dir).returncode)


if __name__ == "__main__":
    main()
