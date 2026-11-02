#!/usr/bin/env python3
"""
Builds the standalone app from BioSync.spec. The result is in dist/.
"""

import subprocess
import sys
from pathlib import Path


def main():
    app_dir = Path(__file__).parent
    command = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "BioSync.spec"]
    sys.exit(subprocess.run(command, cwd=app_dir).returncode)


if __name__ == "__main__":
    main()
