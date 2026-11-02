#!/usr/bin/env python3
"""
Builds the standalone app from BioSync.spec. The result is in dist/.
"""

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


def main():
    warn_about_tk()
    app_dir = Path(__file__).parent
    command = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "BioSync.spec"]
    sys.exit(subprocess.run(command, cwd=app_dir).returncode)


if __name__ == "__main__":
    main()
