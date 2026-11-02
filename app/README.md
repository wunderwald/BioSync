# BioSync — App
by [Moritz Wunderwald](mailto:code@moritzwunderwald.de), 2025-2026

Interactive visual toolbox for windowed cross-correlation analysis, optimized for IBI and EDA biosignal data. Load dyad recordings, tune parameters, inspect results, and export or batch-process datasets.

---

## Requirements

- Python 3.10+

---

## Installation

```bash
cd app
pip install -r requirements.txt
```

Using a virtual environment is optional but recommended to keep dependencies isolated:

```bash
cd app
python -m venv .venv

# activate (macOS / Linux)
source .venv/bin/activate

# activate (Windows)
.venv\Scripts\activate

pip install -r requirements.txt
```

The environment only needs to be created once. On subsequent sessions, just re-run the `activate` line before launching the app.

---

## Running

```bash
python app.py
```

---

## Building a standalone executable

BioSync ships a `build.py` script that wraps PyInstaller. Run it from inside the `app/` directory:

```bash
python build.py
```

You will be prompted to choose a build method and an app name. The finished executable is placed in `dist/`.

| Method | When to use |
|---|---|
| Smart auto-detect *(recommended)* | Standard builds — PyInstaller analyses imports automatically |
| Brute force | When the smart build produces a broken app due to hidden imports |
| Minimal | Quick test builds; may be missing some dependencies at runtime |

---

## Comparing with results from older versions

Earlier versions took the files in a dyad folder in the order the file system listed them. They are now sorted alphabetically (ignoring case), and Excel lock files and hidden files are ignored. This can change results from the same data:

- **The sign of τ can flip.** The first file is person A and the second is person B, so a dyad whose order changed now has A and B swapped.
- **Folders with more than two files can pair differently.** The first two files are used, and the app warns about the others. For example, `simulated_data/dyad_recording` now uses `HRV_a` + `HRV_b`, where it previously used `HRV_a` + `HRV_other`.

Earlier versions also ignored the time from the start of the recording to each person's first beat, which is the first value of an event-based column. Both people are now resampled onto one time grid that uses it, assuming they started recording at the same moment:

- **τ can shift by a few samples** (200 ms each) for event-based data, by the difference between the two first values.

Correlations of ±1 or beyond used to count as a z-value of 0. All correlations beyond ±0.999 are now limited to that value (z of about ±3.8) before the Fisher z-transform:

- **`avg_z_transformed_corr` and `var_z_transformed_corr` can change** for windows that contain such values. This is rare at the default settings.

---

## Developer reference

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
| `state.py` | All `tk.Var` declarations and data containers (`dat_workbook_data`, `dat_physiological_data`, `dat_correlation_data`, `dat_plot_data`). Also holds screen metrics and the `PARAMS_CHANGED()` trigger. Initialised via `init_state()` after the CTk window exists. |
| `validation.py` | Pure input-validation logic — `check_window_size`, `check_max_lag`, `check_lag_filter`, etc. No widget references; reads/writes only from `state`. |
| `callbacks.py` | All user-event handlers: entry/checkbox/dropdown `on_*` callbacks, file pickers, XLSX data loading, signal pre-processing, export handlers, batch processing, and random-pair analysis. Widget references needed for dropdown updates are injected via `register_dropdowns()` / `register_tabview()` after the layout is built. |
| `layout.py` | Builds every widget across the three tabs (Input Data, Correlation, Export & Batch) inside a single `build_layout()` call. Returns a dict of widget references consumed by `gui_updates` and `corr_plot`. |
| `gui_updates.py` | Reactive layer — functions that update widget appearance (border colours, error labels, show/hide panels, button enable/disable) in response to state-variable changes. Registered as `trace_add` callbacks via `setup_traces()`. Widget references are injected via `register_widgets()`. |
| `corr_plot.py` | Runs windowed or standard cross-correlation + DFA on every `PARAMS_CHANGED` event, updates the matplotlib figure, and refreshes the canvas. Separated into `_update_wxcorr_data`, `_update_sxcorr_data`, `update_plot`, `update_canvas`, and the top-level `UPDATE()` loop. |

### Processing modules

| Module | Responsibility |
|---|---|
| `signal_processing.py` | Resampling and alignment of raw IBI / EDA signals (`preprocess_dyad`). |
| `cross_correlation.py` | `windowed_cross_correlation` and `standard_cross_correlation` algorithms. |
| `dfa.py` | Detrended Fluctuation Analysis — `dfa`, `dfa_wxcorr`, `dfa_wxcorr_window_averages`. |
| `plot.py` | Matplotlib figure factories for preprocessing preview, windowed xcorr, and standard xcorr plots. |
| `export.py` | Writes XLSX result files for wxcorr, sxcorr, and random-pair analysis. Always exports raw (non-sigmoid) correlation values. |
| `batch_processing.py` | Iterates a folder of dyads, runs the full analysis pipeline on each, and saves per-dyad XLSX + PNG output. Also contains `random_pair_analysis`. |
| `xlsx.py` | Thin wrappers around openpyxl for reading and writing Excel files. |
| `utils.py` | Small helpers (`is_numeric_array`, `count_subdirectories`, …). |

### Initialization order

```
tk theme (no window needed)
  └─ app = tk.CTk()
       └─ state.init_state()          # tk.Vars require a live window
            └─ validation.make_validator(app)
            └─ callbacks.setup_traces()
                 └─ layout.build_layout()   # creates all widgets; injects refs into callbacks
                      └─ gui_updates.register_widgets() + setup_traces()
                           └─ corr_plot.setup()   # creates matplotlib canvas
                                └─ UPDATE() + mainloop()
```

### Key design notes

- **Late-registration pattern**: `callbacks.py` and `gui_updates.py` hold `_dropdowns` / `_widgets` dicts that are populated by `layout.py` after widgets are created. This avoids circular imports while keeping logic decoupled from widget construction.
- **Sigmoid is display-only**: the sigmoid-scaled view is toggled in the *Visualisation* section of the Correlation tab and affects only the on-screen plot. All XLSX exports always contain raw correlation values.
- **Single update trigger**: `state.PARAMS_CHANGED()` increments `val_UPDATE_COUNT`, which triggers `corr_plot.UPDATE()` via a single `trace_add`. Everything re-renders from one place.
