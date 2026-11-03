# BioSync — App
by [Moritz Wunderwald](mailto:code@moritzwunderwald.de), 2025-2026

Interactive visual toolbox for windowed cross-correlation analysis, optimized for IBI and EDA biosignal data. Load dyad recordings, tune parameters, inspect results, and export or batch-process datasets.

---

## Requirements

- **Python 3.11.9 from python.org** ([macOS](https://www.python.org/ftp/python/3.11.9/python-3.11.9-macos11.pkg), [Windows](https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe)). On Windows, tick **Add python.exe to PATH** in the installer.
  - On macOS, Python before 3.11.7 includes Tk 8.6.12, which makes the window ignore clicks until its title bar is clicked ([python/cpython#110218](https://github.com/python/cpython/issues/110218)).
  - Newer Python versions haven't been tested, and Python from Homebrew or the Microsoft Store doesn't work reliably.
- Optional, for an easy start: [GitHub Desktop](https://desktop.github.com/download/) to download and update the code, and [VS Code](https://code.visualstudio.com/Download) to run it.

The commands below use `python3.11` on macOS. On Windows, use `py -3.11` instead.

---

## Getting the code

Clone `https://github.com/wunderwald/BioSync`, for example in GitHub Desktop with **Add → Clone Repository…**, then open the folder in VS Code.

---

## Installation

In a terminal (in VS Code: **Terminal → New Terminal**):

```bash
cd app
python3.11 -m pip install -r requirements.txt
```

Using a virtual environment is optional but recommended to keep dependencies isolated:

```bash
cd app
python3.11 -m venv .venv

# activate (macOS / Linux)
source .venv/bin/activate

# activate (Windows)
.venv\Scripts\activate

python -m pip install -r requirements.txt
```

The environment only needs to be created once. On subsequent sessions, just re-run the `activate` line before launching the app.

---

## Running

Open `app/app.py` in VS Code and click the play button, or from inside `app/`:

```bash
python3.11 app.py
```

If VS Code reports a missing module, check the Python version shown at the bottom right when `app.py` is open, and choose Python 3.11.

---

## Building a standalone app

BioSync ships a `build.py` script that runs PyInstaller with `BioSync.spec`. From inside the `app/` directory:

```bash
python3.11 -m pip install -r requirements-build.txt
python3.11 build.py
```

The build doesn't ask anything. The result is in `app/dist/`:

- **macOS:** `BioSync.app`. The first time it is opened, macOS may say it can't check the developer: right-click the app, choose **Open**, then **Open** again.
- **Windows:** the folder `BioSync`, with `BioSync.exe` inside. Keep the whole folder together.

A Windows app has to be built on Windows, and a macOS app on a Mac. If the build warns about Tk, the Python used is too old, and the app would ignore clicks. Files the app loads at runtime, such as the theme, are listed in `datas` in `BioSync.spec`.

---

## Updating

Pull the newest version, for example with **Fetch origin** and **Pull origin** in GitHub Desktop. Then run the installation command again, because the required packages may have changed, and rebuild a built app.

---

## Comparing with results from older versions

Earlier versions took the files in a dyad folder in the order the file system listed them. They are now sorted alphabetically (ignoring case), and Excel lock files and hidden files are ignored. This can change results from the same data:

- **The sign of τ can flip.** The first file is person A and the second is person B, so a dyad whose order changed now has A and B swapped.
- **Folders with more than two files can pair differently.** The first two files with the same sheets are used, or the first two files if no two match, and the app warns about the others. For example, `simulated_data/dyad_recording` now uses `HRV_a` + `HRV_b`, where it previously used `HRV_a` + `HRV_other`.

Earlier versions also ignored the time from the start of the recording to each person's first beat, which is the first value of an event-based column. Both people are now resampled onto one time grid that uses it, assuming they started recording at the same moment:

- **τ can shift by a few samples** (200 ms each) for event-based data, by the difference between the two first values.

Correlations of ±1 or beyond used to count as a z-value of 0. All correlations beyond ±0.999 are now limited to that value (z of about ±3.8) before the Fisher z-transform:

- **`avg_z_transformed_corr` and `var_z_transformed_corr` can change** for windows that contain such values. This is rare at the default settings.

Windows where a signal doesn't change have no correlation. They used to report τ at the lowest lag and a z-value of 0, and one such window made its group-average window and its random-pair average `nan`:

- **Flat windows are now `nan` in every column**, including τ and the z-values.
- **Averages leave them out**, so group averages and random-pair averages can change for data that contains them.
- **A signal with the same value throughout is now rejected** as invalid data. In a batch, that dyad is skipped and listed in the summary.

Exports now store numbers as numbers instead of text, in the same cells. The values don't change, but a script that handles them as text, for example with string functions, needs adjusting. Booleans, labels, `-` and `nan` are still text.

The app now has one column selector, listing the columns both files have in the selected sheet. Person A and B are always analysed in the same column, so a dyad whose files name that column differently can't be loaded until the names match. Older runs could use two different columns.

DFA now describes each person's signal, and the correlation over time where that can be trusted:

- **The `Alpha (DFA scaling exponent)` row of standard exports is now `-`.** It was computed across lags, not over time, and didn't change with coupling.
- **New rows at the end of the metadata** give `DFA alpha, signal A` and `signal B`, the value over time for windowed exports, and a `DFA note` with the reason when a value is missing. Event-based signals use the original intervals, because resampling raises alpha.
- **`dfa_lags` and `dfa_alpha` can now contain numbers**, for windows that don't overlap with at least 200 windows. They used to always be `-`.
- **Series with fewer than 200 values are refused.**

Random pairs are now drawn differently, so their t-statistic and p-value can change for the same data:

- **Real pairs and self-pairs are left out.** Recordings are told apart by their file content, so copies from `preprocessing/group_to_dyads.py` count as one recording. Any two recordings that share a dyad folder are a real pair. Folders from one `group_to_dyads` group have only real pairs, so they can't be used alone.
- **Every run uses a seed**, which the export records with the number of different pairs possible. Entering the seed again repeats the run for the same files.

Group averages report τ = 0 with "Average Values in Windows", as single dyads do. They used to report the lowest lag. They also say how many windows they cover, and that longer dyads are cut to the shortest.

Batch checks every dyad against the settings, not only the one loaded in the app. A dyad that doesn't fit, for example because it is shorter than the window size, is skipped and listed with the reason, and no files are written for it. It used to fail with an unclear error, or, in standard mode, be exported with `nan` values. A batch also skips its own output folder when that is inside the input folder, and asks before deleting results of an earlier run in the output folder.

The data type is now guessed when data is loaded: values that clearly aren't heartbeat intervals in ms, such as EDA in microsiemens, select fixed-rate. Anything unclear stays event-based, as before.

Spreadsheets are now read differently:

- **Repeated column names can select a different column.** A name used twice used to mean the last column with that name. It now means the first, and the others are listed as `name (2)` and so on.
- **Cells with formulas now give their calculated value.** They used to count as text, which made the column invalid.
- **The first sheet in the dropdown is now the first sheet both files share.** It used to vary between runs. Results only change if you relied on the default sheet.

---

## Developer reference

### Export format

Existing analysis pipelines read these files, so **the first sheet's layout must not change**: not its columns, their order, or its text. Numbers are stored as numbers; booleans, labels, `-` and `nan` are text. Add new data on another sheet.

Windowed exports have a second sheet, `correlations`: one row per window (labelled with its start index) and one column per lag (labelled with the lag in samples). Flat windows contain the text `nan`. If a recording has too many windows for the first sheet (about 8,000), the `w_*` columns are left out, and the metadata says so.

### Tests

From the repository root, with the virtual environment active:

```bash
pip install -r app/requirements-dev.txt
pytest
```

### Entry point

**`app.py`** (~80 lines) — orchestrator only. Creates the CTk window, then calls into the modules below in order:
`state` → `validation` → `callbacks` → `layout` → `gui_updates` → `corr_plot` → `mainloop`.

### App modules

| Module | Responsibility |
|---|---|
| `state.py` | All `tk.Var` declarations and data containers (`dat_workbook_data`, `dat_physiological_data`, `dat_correlation_data`, `dat_plot_data`). Also holds the `PARAMS_CHANGED()` trigger and `analysis_config()`. Initialised via `init_state()` after the CTk window exists. |
| `validation.py` | Pure input-validation logic — `check_window_size`, `check_max_lag`, `check_lag_filter`, etc. No widget references; reads/writes only from `state`. |
| `callbacks.py` | All user-event handlers: entry/checkbox/dropdown `on_*` callbacks, file pickers, XLSX data loading, signal pre-processing, export handlers, batch processing, and random-pair analysis. Widget references needed for dropdown updates are injected via `register_dropdowns()` / `register_tabview()` after the layout is built. |
| `layout.py` | Builds every widget across the three tabs (Input Data, Correlation, Export & Batch) inside a single `build_layout()` call. Returns a dict of widget references consumed by `gui_updates` and `corr_plot`. |
| `gui_updates.py` | Reactive layer — functions that update widget appearance (border colours, error labels, show/hide panels, button enable/disable) in response to state-variable changes. Registered as `trace_add` callbacks via `setup_traces()`. Widget references are injected via `register_widgets()`. |
| `corr_plot.py` | Runs windowed or standard cross-correlation + DFA when `PARAMS_CHANGED` events change their settings, updates the matplotlib figure, and refreshes the canvas. Separated into `_update_wxcorr_data`, `_update_sxcorr_data`, `update_plot`, `update_canvas`, and the top-level `UPDATE()` loop, which `schedule_update()` runs and `flush_update()` runs early. |

### Processing modules

| Module | Responsibility |
|---|---|
| `analysis.py` | `AnalysisConfig` and `analyze_dyad`: the pipeline shared by the GUI, batch and random pairs, so that they can't give different results. |
| `signal_processing.py` | Resampling and alignment of raw IBI / EDA signals (`preprocess_dyad`). |
| `cross_correlation.py` | `windowed_cross_correlation` and `standard_cross_correlation` algorithms. The windowed one computes many windows at once, and a test checks that it matches the original window-by-window computation exactly. |
| `dfa.py` | Detrended Fluctuation Analysis — `dfa`, `dfa_wxcorr`, `dfa_wxcorr_window_averages`. `analysis.py` decides which series it runs on. |
| `plot.py` | Matplotlib figure factories for preprocessing preview, windowed xcorr, and standard xcorr plots. |
| `export.py` | Writes XLSX result files for wxcorr, sxcorr, and random-pair analysis. Always exports raw (non-sigmoid) correlation values. |
| `batch_processing.py` | Iterates a folder of dyads, runs the full analysis pipeline on each, and saves per-dyad XLSX + PNG output. Also contains `random_pair_analysis`. |
| `xlsx.py` | Thin wrappers around openpyxl for reading and writing Excel files. `read_xlsx` returns the values of all sheets and closes the file. |
| `utils.py` | Small helpers (`is_numeric_array`, `count_subdirectories`, `resource_path`, …). |

### Initialization order

```
tk theme (no window needed)
  └─ app = tk.CTk()
       └─ state.init_state()          # tk.Vars require a live window
            └─ validation.make_validator(app)
            └─ validation.make_signed_validator(app)
            └─ callbacks.setup_traces()
                 └─ layout.build_layout()   # creates all widgets; injects refs into callbacks
                      └─ gui_updates.register_widgets() + setup_traces()
                           └─ corr_plot.setup()   # creates matplotlib canvas
                                └─ UPDATE() + mainloop()
```

### Key design notes

- **Late-registration pattern**: `callbacks.py` and `gui_updates.py` hold `_dropdowns` / `_widgets` dicts that are populated by `layout.py` after widgets are created. This avoids circular imports while keeping logic decoupled from widget construction.
- **Background jobs**: batch and random pair analysis run on another thread through `callbacks._start_job`. Tk only works on the main thread, so a job gets a copy of the settings up front, must not use `state` or any widget, and reports progress through a queue.
- **Sigmoid is display-only**: the sigmoid-scaled view is toggled in the *Visualisation* section of the Correlation tab and affects only the on-screen plot. All XLSX exports always contain raw correlation values.
- **Single update trigger**: `state.PARAMS_CHANGED()` increments `val_UPDATE_COUNT`, which schedules `corr_plot.UPDATE()` via a single `trace_add`, so repeated changes run it once. Typing passes `debounce=True` to wait 250 ms for a pause. Everything re-renders from one place. Anything that reads the results straight after a change has to call `corr_plot.flush_update()` first.
