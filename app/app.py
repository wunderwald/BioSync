import customtkinter as tk

import state
import validation
import callbacks
import layout
import gui_updates
import corr_plot

# ------------------
# APP INITIALIZATION
# ------------------

tk.set_appearance_mode("Light")
tk.set_default_color_theme("green")

app = tk.CTk()
app.title("BioSync")
app.withdraw()  # hide until fully built and sized

screen_width  = app.winfo_screenwidth()
screen_height = app.winfo_screenheight()
screen_dpi    = app.winfo_fpixels('1i')

RETINA     = screen_dpi < 75
app.geometry(f"{screen_width}x{int(screen_height * 0.9)}")
app.resizable(False, False)
app.tk.call('tk', 'scaling', 1 if RETINA else 1.5)

# --------------------------------
# STATE — all tk.Vars & containers
# --------------------------------

state.init_state(screen_dpi, screen_width, screen_height, RETINA)

# --------------------------------
# VALIDATION & CALLBACKS
# --------------------------------

validate_numeric_input = validation.make_validator(app)
callbacks.setup_traces()

# --------------------------------
# BUILD UI
# --------------------------------

widget_dict = layout.build_layout(app, validate_numeric_input)

# --------------------------------
# REACTIVE GUI UPDATES
# --------------------------------

gui_updates.register_widgets(widget_dict)
gui_updates.setup_traces()

# --------------------------------
# CORRELATION & PLOTTING ENGINE
# --------------------------------

corr_plot.setup(widget_dict['group_plot'])
state.val_UPDATE_COUNT.trace_add('write', corr_plot.UPDATE)
corr_plot.UPDATE()

# Two update() passes: the first resolves the basic pack layout; the second lets
# CTkTabview finish its internal geometry so the canvas reports its true final size.
app.update()
app.update()
corr_plot.fit_canvas_to_container()

# --------------------------------
# CLEANUP & SHUTDOWN
# --------------------------------

def on_window_closing():
    for widget_id in app.tk.call('after', 'info'):
        try:
            app.after_cancel(widget_id)
        except Exception:
            pass
    try:
        import matplotlib.pyplot as plt
        plt.close('all')
    except Exception:
        pass
    app.destroy()

app.protocol("WM_DELETE_WINDOW", on_window_closing)

# --------------------------------
# RUN
# --------------------------------

app.deiconify()
# On some displays (e.g. large external monitors) the canvas reports 1×1 during the
# pre-show update passes, so fit_canvas_to_container() above is a no-op. Scheduling
# a second call at after(0) guarantees the canvas is primed once the event loop has
# resolved all geometry — this prevents the first real draw (Tab 1 data load) from
# rendering at 2× zoom due to an uninitialised Tk PhotoImage.
app.after(0, corr_plot.fit_canvas_to_container)
app.mainloop()