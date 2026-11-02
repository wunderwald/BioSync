# PyInstaller build definition. Run it through build.py.
import sys

a = Analysis(
    ['app.py'],
    datas=[('theme_dark_grey.json', '.')],  # files the app loads at runtime, see utils.resource_path
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
