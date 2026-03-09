
# hook-mymodules.py
# This helps PyInstaller find hidden modules

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Common problematic packages
datas, binaries, hiddenimports = [], [], []

# Try to include common data science/ML packages
try:
    import pandas
    datas += collect_all('pandas')
    hiddenimports += collect_submodules('pandas')
except:
    pass

try:
    import numpy
    datas += collect_all('numpy')
except:
    pass

try:
    import matplotlib
    datas += collect_all('matplotlib')
except:
    pass

try:
    import sklearn
    hiddenimports += collect_submodules('sklearn')
except:
    pass

try:
    import openpyxl
    hiddenimports += collect_submodules('openpyxl')
except:
    pass

# GUI frameworks
for gui in ['PyQt5', 'PySide6', 'tkinter', 'customtkinter']:
    try:
        __import__(gui)
        hiddenimports.append(gui)
    except:
        pass

# Common data modules
common_modules = [
    'xlsxwriter', 'xlrd', 'xlwt',
    'PIL', 'pillow',
    'json', 'csv', 'sqlite3',
    'requests', 'urllib3',
    'logging', 'threading', 'multiprocessing'
]

for mod in common_modules:
    try:
        __import__(mod)
        hiddenimports.append(mod)
    except:
        pass
