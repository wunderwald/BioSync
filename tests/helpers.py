"""
Stand-ins for Tk widgets, and test data that several test files share.
"""
import os
import time

import numpy as np
from openpyxl import Workbook


class FakeWidget:
    """
    Stands in for any widget: records the options the app sets with configure, and whether it is shown.
    Options can be read as attributes, for example widget.text after configure(text=...).
    """
    def __init__(self, toplevel=None, **options):
        self.options = dict(options)
        self.visible = False
        self.toplevel = toplevel

    def __getattr__(self, name):
        try:
            return self.__dict__["options"][name]
        except KeyError:
            raise AttributeError(name) from None

    def configure(self, **options):
        self.options.update(options)

    def cget(self, name):
        return self.options[name]

    def grid(self, **kwargs):
        self.visible = True

    def grid_forget(self):
        self.visible = False

    grid_remove = grid_forget

    def winfo_toplevel(self):
        return self.toplevel

    def update_idletasks(self):
        pass


class FakeTimer:
    """Stands in for Tk's timer: scheduled callbacks only run when a test runs them."""
    def __init__(self):
        self.timers = {}
        self.next_id = 0

    def after(self, delay_ms, callback, *args):
        self.next_id += 1
        self.timers[self.next_id] = (delay_ms, callback, args)
        return self.next_id

    def after_cancel(self, timer_id):
        del self.timers[timer_id]

    def get_tk_widget(self):
        """Lets the timer stand in for the plot canvas, whose widget the app schedules on."""
        return self

    def update_idletasks(self):
        """Lets the timer stand in for the tabview, which shows a change before slow work."""

    def delays(self):
        return [delay for delay, _, _ in self.timers.values()]

    def run_timers(self):
        """Runs the callbacks that are scheduled now, but not the ones they schedule."""
        timers, self.timers = self.timers, {}
        for _, callback, args in timers.values():
            callback(*args)

    def run_until_idle(self, timeout_s=10):
        """Runs callbacks until none are scheduled, for example until a background job has finished."""
        deadline = time.monotonic() + timeout_s
        while self.timers:
            assert time.monotonic() < deadline, "job didn't finish"
            self.run_timers()
            time.sleep(0.001)


# ---------------------------------------------------------------------------
# DYADS ON DISK
# ---------------------------------------------------------------------------

N_BEATS = 1000
SHEET = "Sheet"


def ibi(rng):
    noise = np.convolve(rng.normal(size=N_BEATS), np.ones(4) / 2, mode="same")
    return 800 + 50 * noise


def write_person(path, columns):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET
    sheet.append(list(columns))
    for row in zip(*columns.values()):
        sheet.append([float(value) for value in row])
    workbook.save(path)


def write_dyad(folder, seed=0, file_names=("P1.xlsx", "P2.xlsx")):
    """A dyad with a coupled column (the same signal plus noise) and an independent one."""
    os.makedirs(folder)
    rng = np.random.default_rng(seed)
    coupled = ibi(rng)
    for file_name in file_names:
        write_person(
            os.path.join(folder, file_name),
            {"Coupled": coupled + rng.normal(0, 5, N_BEATS), "Independent": ibi(rng)},
        )


def batch_params(input_dir, output_dir, column="Coupled", **overrides):
    params = {
        'batch_input_folder': str(input_dir),
        'output_dir': str(output_dir),
        'selected_sheet': SHEET,
        'has_headers': True,
        'selected_column_a': column,
        'selected_column_b': column,
        'checkbox_windowed_xcorr': True,
        'window_size': 150,
        'step_size': 75,
        'max_lag': 30,
        'max_lag_sxc': 150,
        'standardised_signals': False,
        'checkbox_absolute_corr': False,
        'checkbox_absolute_corr_sxc': False,
        'checkbox_average_windows': False,
        'sigmoid_correlations': False,
        'checkbox_eb': True,
        'checkbox_fr': False,
        'use_lag_filter': False,
        'lag_filter_min': -30,
        'lag_filter_max': 30,
    }
    params.update(overrides)
    return params
