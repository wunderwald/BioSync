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

state.val_checkbox_lag_filter.set(True)       # the tallest content: lag filter rows and the job panel
state.val_job_running.set(True)
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

print(json.dumps(report), flush=True)
os._exit(0)     # skips Tk's slow and noisy shutdown
