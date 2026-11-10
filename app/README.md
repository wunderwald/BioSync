# BioSync: App
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

## Surrogate analysis

The **Surrogates** tab tests whether the real dyads in a folder are more coupled than surrogates, in which coupling can't exist. It uses the settings of the Input Data and Correlation tabs. Each surrogate gives the same number as a real dyad, and p is the share of surrogates at least as extreme as the real value, counting the real value as one of them: `p = (1 + surrogates at least as extreme) / (surrogates + 1)`. So p is never 0, and with 1000 surrogates it can't go below 0.001 (0.002 two-sided).

### Methods

| Method | Surrogates | Question | Result |
|---|---|---|---|
| **Re-paired people** | Sets of pairs of people from different dyads, each as large as the real group | Are partners more in sync than strangers recorded in the same setting? | p for the group |
| **Shuffled blocks** | Partner B's signal cut into blocks of the block length (default: the window size) and put in a random order. Leftover samples stay at the end. | Does the moment-to-moment timing between these two people matter? | p for each dyad, and for the group |
| **Welch's t-test** | Random pairs drawn with replacement, compared with the real dyads by a t-test | As in earlier versions | p for the group |

- **Re-paired people** don't count what all participants share as coupling, such as reactions to the same task at the same moments, or the same slow drift. With few dyads only few different sets exist, and the app warns when that limits p.
- **Shuffled blocks** break that shared time course, so they count it as coupling. Longer blocks keep more of it and make the test stricter: the block length changes the result and has to be reported. A dyad needs at least 5 blocks. The p-values of single dyads aren't corrected for testing many dyads: with 33 dyads, 1 or 2 are expected below 0.05 by chance.
- **Welch's t-test** is only there to repeat results of earlier versions. It treats every random pair as independent, but the same people appear again and again, so its p isn't exact: in simulations it found coupling in 2% to 8% of groups without any, depending on the data.

### Measures

One number per dyad, pair or surrogate:

- **mean r**: the average correlation over all windows and lags.
- **mean |r_max|**: the strongest correlation at any lag in each window, without its sign, averaged over the windows. It is high even for strangers, which the surrogates share, so the comparison is fair, but it can be less sensitive. Not available with "average windows".
- **r at lag 0**: the correlation without delay, averaged over the windows. Not available with "average windows", or when the lag filter leaves out lag 0.

### One-sided or two-sided

The app decides this from the measure and settings, so it can't be chosen after seeing the result:

- **One-sided (real higher):** mean |r_max|, and every measure when "absolute correlation values" is on, because coupling can only make these values higher.
- **Two-sided:** mean r and r at lag 0 of signed correlations, because coupling can also be negative. p is twice the smaller one-sided p, at most 1. Welch's t-test is always two-sided.

### Results

Before a run, the tab says in one sentence what will be tested, in red what stops the run, and in orange what will limit the result. A run doesn't write anything: the plot area of the tab shows the result until the next run. If settings change, the result stays and is marked as coming from the earlier settings. **Export results**, below the run, then writes the last result with the settings it was run with: an xlsx file with the summary, the settings and each dyad's values, and the figure as a PNG next to it. Report the method, the measure, the sides, the number of surrogates, the seed, the block length for shuffled blocks, and p: the export's "Summary" row has them in one sentence.

---

## Developer reference

### Tests

From the repository root, with the virtual environment active:

```bash
pip install -r app/requirements-dev.txt
pytest
```

`tests/surrogate_simulation.py` checks the surrogate tests on simulated dyads with known coupling. The test suite runs a small version; the full run takes about half an hour: `python tests/surrogate_simulation.py --groups 200`.

### Entry point

**`app.py`** (~80 lines) — orchestrator only. Creates the CTk window, then calls into the modules below in order:
`state` → `validation` → `callbacks` → `layout` → `gui_updates` → `corr_plot` → `mainloop`.

### App modules

| Module | Responsibility |
|---|---|
| `state.py` | All `tk.Var` declarations and data containers (`dat_workbook_data`, `dat_physiological_data`, `dat_correlation_data`, `dat_plot_data`). Also holds the `PARAMS_CHANGED()` trigger and `analysis_config()`. Initialised via `init_state()` after the CTk window exists. |
| `validation.py` | Pure input-validation logic — `check_window_size`, `check_max_lag`, `check_lag_filter`, etc. No widget references; reads/writes only from `state`. |
| `callbacks.py` | All user-event handlers: entry/checkbox/dropdown `on_*` callbacks, file pickers, XLSX data loading, signal pre-processing, export handlers, batch processing, and random-pair analysis. Widget references needed for dropdown updates are injected via `register_dropdowns()` / `register_tabview()` after the layout is built. |
| `layout.py` | Builds every widget across the four tabs (Input Data, Correlation, Export & Batch, Surrogates) inside a single `build_layout()` call. Returns a dict of widget references consumed by `gui_updates` and `corr_plot`. |
| `gui_updates.py` | Reactive layer — functions that update widget appearance (border colours, error labels, show/hide panels, button enable/disable) in response to state-variable changes. Registered as `trace_add` callbacks via `setup_traces()`. Widget references are injected via `register_widgets()`. |
| `corr_plot.py` | Runs windowed or standard cross-correlation + DFA when `PARAMS_CHANGED` events change their settings, updates the matplotlib figure (on the Surrogates tab: the last surrogate result, marked when its settings have changed since), and refreshes the canvas. Separated into `_update_wxcorr_data`, `_update_sxcorr_data`, `update_plot`, `update_canvas`, and the top-level `UPDATE()` loop, which `schedule_update()` runs and `flush_update()` runs early. |

### Processing modules

| Module | Responsibility |
|---|---|
| `analysis.py` | `AnalysisConfig` and `analyze_dyad`: the pipeline shared by the GUI, batch and surrogate tests, so that they can't give different results. |
| `signal_processing.py` | Resampling and alignment of raw IBI / EDA signals (`preprocess_dyad`). |
| `cross_correlation.py` | `windowed_cross_correlation` and `standard_cross_correlation` algorithms. The windowed one computes many windows at once, and a test checks that it matches the original window-by-window computation exactly. |
| `measures.py` | The number each dyad contributes to a random-pair or surrogate test: mean r, mean \|r_max\| or r at lag 0 (`dyad_measure`), and which settings rule one out (`measure_problem`). |
| `surrogates.py` | Tests that compare real dyads with surrogates, in which coupling can't exist. `surrogate_analysis` runs any of the three methods and returns a `SurrogateResult`: re-paired people (`repaired_pair_test`), shuffled blocks of partner B's signal (`block_shuffle_test`, which also gives a p-value for each dyad), and random pairs with Welch's t-test (`welch_random_pair_test`, the test of earlier versions, which draws pairs exactly as they did). Each reads every recording once, and leaves files without the selected sheet out of random pairs. It also has what the Surrogates tab shows before a run (`plan_summary`, `choice_problem`, `folder_overview`). |
| `dfa.py` | Detrended Fluctuation Analysis — `dfa`, `dfa_wxcorr`, `dfa_wxcorr_window_averages`. `analysis.py` decides which series it runs on. |
| `plot.py` | Matplotlib figure factories for preprocessing preview, windowed xcorr, and standard xcorr plots, and for surrogate test results (`plot_surrogate_result`). |
| `export.py` | Writes XLSX result files for wxcorr, sxcorr, and surrogate tests (`export_surrogate_result`, with the result figure as PNG). The Welch export keeps the first sheet of earlier versions and adds rows at its end. Always exports raw (non-sigmoid) correlation values. |
| `batch_processing.py` | Iterates a folder of dyads, runs the full analysis pipeline on each, and saves per-dyad XLSX + PNG output. |
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
- **Background jobs**: batch processing and surrogate analysis run on another thread through `callbacks._start_job`. Tk only works on the main thread, so a job gets a copy of the settings up front, must not use `state` or any widget, and reports progress through a queue.
- **Sigmoid is display-only**: the sigmoid-scaled view is toggled in the *Visualisation* section of the Correlation tab and affects only the on-screen plot. All XLSX exports always contain raw correlation values.
- **Single update trigger**: `state.PARAMS_CHANGED()` increments `val_UPDATE_COUNT`, which schedules `corr_plot.UPDATE()` via a single `trace_add`, so repeated changes run it once. Typing passes `debounce=True` to wait 250 ms for a pause. Everything re-renders from one place. Anything that reads the results straight after a change has to call `corr_plot.flush_update()` first.
