"""
Builds the real window, invisible, and reports how its widgets behave. Run by test_real_window.py in a
separate process, so that the real Tk state doesn't mix with the other tests' fake state.
"""
import json
import os
import sys
import time

app_dir = sys.argv[1]
os.chdir(app_dir)
sys.path.insert(0, app_dir)

import customtkinter as tk

import callbacks
import corr_plot
import gui_updates
import layout
import state
import validation

# record which dialog-opening buttons run, instead of opening real dialogs
runs = []
for name in ("open_batch_input_folder", "handle_run_batch_button"):
    setattr(callbacks, name, lambda name=name: runs.append(name))

tk.set_appearance_mode("Light")
tk.set_default_color_theme("theme_dark_grey.json")
app = tk.CTk()
app.withdraw()
app.geometry("1280x720+0+0")     # small enough for some tabs to need scrolling
state.init_state(retina=True)
callbacks.setup_traces()
widgets = layout.build_layout(app, validation.make_validator(app), validation.make_signed_validator(app))
gui_updates.register_widgets(widgets)
gui_updates.setup_traces()
corr_plot.setup(widgets['group_plot'])
corr_plot.UPDATE()
app.attributes('-alpha', 0.0)
app.deiconify()
errors = []
app.report_callback_exception = lambda kind, error, trace: errors.append(f"{kind.__name__}: {error}")


def settle():
    end = time.time() + 0.3
    while time.time() < end:
        app.update()


settle()
tabview = callbacks._tabview['tabview']
plot = corr_plot.canvas.get_tk_widget()
report = {'dropdowns': {}, 'tabs': {}}

for key in ('dropdown_select_sheet', 'dropdown_select_column'):
    dropdown = widgets[key]
    report['dropdowns'][key] = {
        'type': type(dropdown).__name__,
        'opens_from_text': bool(dropdown._text_label.bind('<Button-1>')),
        'opens_from_arrow': bool(dropdown._canvas.bind('<Button-1>')),
    }

# a click on a button that opens a dialog: nothing may happen until the mouse button is released
def click(button, x=5, y=5, release_at=None):
    button._canvas.event_generate("<ButtonPress-1>", x=x, y=y)
    settle()
    pressed = list(runs)
    button._canvas.event_generate("<ButtonRelease-1>", x=release_at[0] if release_at else x, y=release_at[1] if release_at else y)
    settle()
    return pressed


tabview._segmented_button_callback("Export & Batch")
settle()
picker = widgets['label_batch_input_folder'].master.grid_slaves(row=2, column=0)[0]
report['click'] = {
    'runs_on_press': click(picker),
    'runs_after_release': list(runs),
}
runs.clear()
click(picker, release_at=(-50, -50))
report['click']['runs_after_release_outside'] = list(runs)
runs.clear()
click(widgets['button_batch'])
report['click']['runs_when_disabled'] = list(runs)
tabview._segmented_button_callback("Input Data")
settle()

# load EDA-like data: a real Tk variable rejects values the stand-ins in the other tests accept
import tempfile
import numpy as np
from openpyxl import Workbook
eda_folder = tempfile.mkdtemp()
for name in ("A.xlsx", "B.xlsx"):
    workbook = Workbook()
    workbook.active.title = "EDA"
    workbook.active.append(["EDA"])
    for value in 1 + 0.3 * np.sin(np.arange(3000) / 50):
        workbook.active.append([float(value)])
    workbook.save(os.path.join(eda_folder, name))
callbacks.filedialog.askdirectory = lambda **kwargs: eda_folder
callbacks.open_dir_picker()
corr_plot.flush_update()
settle()
report['eda'] = {
    'fixed_rate': state.val_checkbox_fr.get(), 'valid': state.val_INPUT_DATA_VALID.get(), 'reason': state.val_input_error.get(),
}

state.val_checkbox_lag_filter.set(True)       # the tallest content: lag filter rows and the job panel
state.val_job_running.set(True)
settle()
plot_resizes = []
plot.bind('<Configure>', lambda event: plot_resizes.append((event.width, event.height)), add='+')
for name in ("Input Data", "Correlation", "Export & Batch", "Input Data"):
    tabview._segmented_button_callback(name)
    settle()
    scrollbar = next(child for child in tabview.tab(name).winfo_children()[0].winfo_children()
                     if 'Scrollbar' in type(child).__name__)
    report['tabs'][name] = {
        'tabview_width': tabview.winfo_width(),
        'plot_width': plot.winfo_width(),
        'scrollbar_shown': bool(scrollbar.winfo_ismapped()),
    }

report['plot_resizes_during_tab_changes'] = len(plot_resizes)
report['callback_errors'] = errors
print(json.dumps(report), flush=True)
os._exit(0)     # skips Tk's slow and noisy shutdown
