#!/usr/bin/env python3
"""
Smart build script that analyzes and includes everything needed
"""

import subprocess
import os
import sys
import shutil
from pathlib import Path

# Always run relative to this script's directory
os.chdir(Path(__file__).parent)

def run_pyinstaller_with_analysis(app_name="wx"):
    """Run PyInstaller with module analysis"""
    
    print(f"🔧 Building {app_name} with auto-detection...")
    
    # Clean up
    for path in ["build", "dist", "__pycache__"]:
        shutil.rmtree(path, ignore_errors=True)
    
    # Create a hook script to collect everything
    create_hook_script()
    
    # Use PyInstaller's built-in analysis
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--name", app_name,
        "--additional-hooks-dir", ".",  # Use our hook file
        "--collect-all", "*",  # Try to collect everything (careful!)
        "--debug", "imports",  # Show what's being imported
        "app.py"
    ]
    
    print("Running: " + " ".join(cmd[:10]) + " ...")
    
    try:
        # Let PyInstaller do its analysis
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            print(f"\n✅ Success! Built in dist/")
            
            # Analyze the output for missing modules
            if "ModuleNotFoundError" in result.stdout or "No module named" in result.stdout:
                print("\n⚠ Some modules might be missing in frozen app.")
                print("Check if the app runs properly.")
            
            return True
        else:
            print("\n❌ Build failed!")
            # Extract useful error info
            lines = result.stderr.split('\n')
            for line in lines[-20:]:  # Last 20 lines
                if line.strip():
                    print(line)
            return False
            
    except subprocess.TimeoutExpired:
        print("\n⏱ Build timed out! Command was too greedy.")
        return False
    except Exception as e:
        print(f"\n💥 Error: {e}")
        return False

def create_hook_script():
    """Create a hook file to help PyInstaller"""
    hook_content = '''
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
'''
    
    with open("hook-mymodules.py", "w") as f:
        f.write(hook_content)

def brute_force_build(app_name="wx"):
    """Brute force approach - include everything possible"""
    
    print(f"💪 BRUTE FORCE BUILD for {app_name}")
    print("This will be slow but should catch everything...")
    
    # Get all installed packages
    try:
        import pkg_resources
        installed = [pkg.key for pkg in pkg_resources.working_set]
        print(f"Found {len(installed)} installed packages")
    except:
        installed = []
        print("Could not get installed packages list")
    
    # Filter to likely relevant packages (not TOO many)
    relevant = []
    keywords = ['gui', 'qt', 'tk', 'data', 'excel', 'xls', 'plot', 'chart', 'table', 'pandas', 'numpy', 'matplotlib', 'pillow', 'image']
    
    for pkg in installed:
        pkg_lower = pkg.lower()
        if any(keyword in pkg_lower for keyword in keywords):
            relevant.append(pkg)
    
    print(f"Adding {len(relevant)} potentially relevant packages")
    
    # Build command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--windowed",
        "--clean",
        "--name", app_name,
        "--debug", "all",
    ]
    
    # Add the most important ones (limit to avoid command line too long)
    for pkg in relevant[:50]:  # Limit to 50 packages
        cmd.extend(["--hidden-import", pkg])
    
    cmd.append("app.py")
    
    print(f"\nRunning (truncated): {' '.join(cmd[:20])}...")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"\n✅ Brute force successful! App in dist/")
        return True
    else:
        print("\n❌ Failed even with brute force!")
        return False

def main():
    print("Choose build method:")
    print("1. Smart auto-detect (recommended)")
    print("2. Brute force (slow but thorough)")
    print("3. Minimal (just main script)")
    
    choice = input("\nChoice [1]: ").strip() or "1"
    app_name = input("App name [BioSync]: ").strip() or "BioSync"
    
    if choice == "1":
        success = run_pyinstaller_with_analysis(app_name)
    elif choice == "2":
        success = brute_force_build(app_name)
    else:
        # Minimal build
        cmd = [sys.executable, "-m", "PyInstaller", "--windowed", "--clean", "--name", app_name, "app.py"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        success = result.returncode == 0
    
    # Cleanup
    for spec in Path(".").glob("*.spec"):
        spec.unlink()
    shutil.rmtree("build", ignore_errors=True)
    
    if success:
        print(f"\n🎉 Done! Built in folder dist/")
    else:
        print("\n🔥 Build failed!")

if __name__ == "__main__":
    main()