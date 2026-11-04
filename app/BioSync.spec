# PyInstaller build definition. Run it through build.py.
import os
import re
import sys
import tkinter

sys.path.insert(0, SPECPATH)
from build import TCL_DATA, TK_DATA, find_tcl_tk_data

a = Analysis(
    ['app.py'],
    datas=[('theme_dark_grey.json', '.')],  # files the app loads at runtime, see utils.resource_path
)

# PyInstaller only collects Tcl/Tk from where Tcl says it is. If that is wrong, it just warns and builds an app that
# fails on start with "Tcl data directory ... not found". Look in the usual places instead, or stop the build.
collected = {re.split(r'[\\/]', destination)[0] for destination, _, _ in a.datas}
if TCL_DATA not in collected or TK_DATA not in collected:
    found = find_tcl_tk_data(sys.base_prefix, tkinter.TclVersion, tkinter.TkVersion)
    if found:
        print(f"Tcl/Tk scripts weren't collected, adding them from {os.path.dirname(found[0])}")
        excludes = ['demos', '*.lib', 'tclConfig.sh', 'tkConfig.sh']
        if TCL_DATA not in collected:
            a.datas += Tree(found[0], prefix=TCL_DATA, excludes=excludes)
        if TK_DATA not in collected:
            a.datas += Tree(found[1], prefix=TK_DATA, excludes=excludes)
    elif sys.platform != 'darwin':     # macOS can use a system Tcl/Tk instead
        raise SystemExit(
            "The Tcl/Tk scripts of this Python can't be found, so the app wouldn't start. "
            "Install Python from python.org (see app/README.md) and build with it."
        )

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    exclude_binaries=True,
    name='BioSync',
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name='BioSync')

if sys.platform == 'darwin':
    app = BUNDLE(coll, name='BioSync.app', bundle_identifier=None)
