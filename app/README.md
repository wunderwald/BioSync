# BioSync

## Entry point

**`app.py`** (~80 lines) — orchestrator only. Creates the CTk window, then calls into the modules below in order:
`state` → `validation` → `callbacks` → `layout` → `gui_updates` → `corr_plot` → `mainloop`.

---

## App modules

| Module | Responsibility |
|---|---|
| `state.py` | All `tk.Var` declarations and data containers (`dat_workbook_data`, `dat_physiological_data`, `dat_correlation_data`, `dat_plot_data`). Also holds screen metrics and the `PARAMS_CHANGED()` trigger. Initialised via `init_state()` after the CTk window exists. |
| `validation.py` | Pure input-validation logic — `check_window_size`, `check_max_lag`, `check_lag_filter`, etc. No widget references; reads/writes only from `state`. |
| `callbacks.py` | All user-event handlers: entry/checkbox/dropdown `on_*` callbacks, file pickers, XLSX data loading, signal pre-processing, export handlers, batch processing, and random-pair analysis. Widget references needed for dropdown updates are injected via `register_dropdowns()` / `register_tabview()` after the layout is built. |
| `layout.py` | Builds every widget across the three tabs (Input Data, Correlation, Export & Batch) inside a single `build_layout()` call. Returns a dict of widget references consumed by `gui_updates` and `corr_plot`. |
| `gui_updates.py` | Reactive layer — functions that update widget appearance (border colours, error labels, show/hide panels, button enable/disable) in response to state-variable changes. Registered as `trace_add` callbacks via `setup_traces()`. Widget references are injected via `register_widgets()`. |
| `corr_plot.py` | Runs windowed or standard cross-correlation + DFA on every `PARAMS_CHANGED` event, updates the matplotlib figure, and refreshes the canvas. Separated into `_update_wxcorr_data`, `_update_sxcorr_data`, `update_plot`, `update_canvas`, and the top-level `UPDATE()` loop. |

---

## Processing modules

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

---

## Initialization order

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

## Key design notes

- **Late-registration pattern**: `callbacks.py` and `gui_updates.py` hold `_dropdowns` / `_widgets` dicts that are populated by `layout.py` after widgets are created. This avoids circular imports while keeping logic decoupled from widget construction.
- **Sigmoid is display-only**: the sigmoid-scaled view is toggled in the *Visualisation* section of the Correlation tab and affects only the on-screen plot. All XLSX exports always contain raw correlation values.
- **Single update trigger**: `state.PARAMS_CHANGED()` increments `val_UPDATE_COUNT`, which triggers `corr_plot.UPDATE()` via a single `trace_add`. Everything re-renders from one place.
