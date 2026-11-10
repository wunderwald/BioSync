"""
Batch and random pair analysis run on another thread. They must not use Tk there, must keep the settings they
started with, and must leave the app usable afterwards however they end.
"""
import threading
import time

import pytest

import batch_processing
import surrogates
import callbacks
from measures import MEAN_R
import gui_updates
import state
from helpers import FakeTimer, FakeWidget, batch_params, write_dyad


@pytest.fixture
def app(fake_state, monkeypatch):
    for name in ("val_INPUT_DATA_VALID", "val_CORRELATION_SETTINGS_VALID", "val_CORRELATION_SETTINGS_VALID_SXC",
                 "val_checkbox_windowed_xcorr"):
        getattr(fake_state, name).set(True)
    fake_state.val_job_running.set(False)
    fake_state.val_job_progress.set(0)
    fake_state.val_rp_n.set(3)
    fake_state.val_surrogate_method.set(surrogates.REPAIRED)
    fake_state.val_surrogate_test.set(surrogates.WELCH)
    fake_state.val_surrogate_measure.set(MEAN_R)
    for name in ("val_batch_input_folder", "val_batch_output_folder", "val_random_pair_input_folder"):
        getattr(fake_state, name).set("selected")
    fake_state.timer = FakeTimer()
    monkeypatch.setitem(callbacks._tabview, "tabview", fake_state.timer)
    fake_state.dialogs = []
    for kind in ("showinfo", "showerror"):
        monkeypatch.setattr(callbacks.messagebox, kind, lambda title, text, kind=kind: fake_state.dialogs.append((kind, title, text)))
    return fake_state


def _both_ready(app):
    return app.val_batch_processing_is_ready.get(), app.val_random_pair_is_ready.get()


def test_job_runs_on_another_thread_and_finishes_on_this_one(app):
    threads = {}
    callbacks._start_job(
        "Job",
        lambda progress: threads.update(work=threading.current_thread()) or "result",
        lambda result: threads.update(done=threading.current_thread(), result=result),
    )
    app.timer.run_until_idle()
    assert threads["work"] is not threading.main_thread()
    assert threads["done"] is threading.main_thread()
    assert threads["result"] == "result"


def test_buttons_are_blocked_while_running_and_restored_afterwards(app):
    release = threading.Event()
    callbacks._start_job("Job", lambda progress: release.wait(5), lambda result: None)

    assert app.val_job_running.get() is True
    assert _both_ready(app) == (False, False)

    callbacks._batch_processing_is_ready()      # changing a setting while it runs must not re-enable them
    callbacks._surrogates_are_ready()
    assert _both_ready(app) == (False, False)

    release.set()
    app.timer.run_until_idle()
    assert app.val_job_running.get() is False
    assert _both_ready(app) == (True, True)


def test_failed_job_shows_the_error_and_restores_the_buttons(app):
    def fail(progress):
        raise RuntimeError("disk full")

    callbacks._start_job("Job", fail, lambda result: pytest.fail("not a success"))
    app.timer.run_until_idle()

    assert app.dialogs == [("showerror", "Job failed", "disk full")]
    assert app.val_job_running.get() is False
    assert _both_ready(app) == (True, True)


def test_progress_reaches_the_window_in_order(app):
    seen = []
    real_set = app.val_job_progress_text.set
    app.val_job_progress_text.set = lambda text: (seen.append(text), real_set(text))

    def work(progress):
        progress(0, 2, "dyad0")
        progress(1, 2, "dyad1")
        progress(2, 2, "Group average")

    callbacks._start_job("Job", work, lambda result: None)
    app.timer.run_until_idle()

    assert seen == ["Job", "dyad0 (1 of 2)", "dyad1 (2 of 2)", "Group average"]
    assert app.val_job_progress.get() == 1


def test_job_without_steps_does_not_divide_by_zero(app):
    callbacks._start_job("Job", lambda progress: progress(0, 0, "nothing"), lambda result: None)
    app.timer.run_until_idle()
    assert app.val_job_progress.get() == 0
    assert app.dialogs == []


class FailOffMainThread:
    """Stands in for a tk.Var, and records any use that isn't on the main thread."""
    def __init__(self, value, violations):
        self.value, self.violations = value, violations

    def _check(self):
        if threading.current_thread() is not threading.main_thread():
            self.violations.append(threading.current_thread().name)

    def get(self):
        self._check()
        return self.value

    def set(self, value):
        self._check()
        self.value = value


def _guard_all_vars(monkeypatch):
    violations = []
    for name in vars(state).copy():
        if name.startswith("val_"):
            monkeypatch.setattr(state, name, FailOffMainThread(getattr(state, name).get(), violations))
    return violations


def _guard_settings(monkeypatch, violations, params):
    """Collecting the settings reads tk.Vars, so it has to happen before the job starts."""
    def analysis_params():
        if threading.current_thread() is not threading.main_thread():
            violations.append("_analysis_params")
        return params
    monkeypatch.setattr(callbacks, "_analysis_params", analysis_params)


def test_batch_does_not_touch_state_on_its_thread(app, tmp_path, monkeypatch):
    write_dyad(tmp_path / "in" / "dyad0")
    (tmp_path / "out").mkdir()
    timer = app.timer
    violations = _guard_all_vars(monkeypatch)
    _guard_settings(monkeypatch, violations, batch_params(tmp_path / "in", tmp_path / "out"))

    callbacks.handle_run_batch_button()
    timer.run_until_idle(60)

    assert violations == []
    assert app.dialogs and app.dialogs[0][:2] == ("showinfo", "Batch processing finished")
    assert (tmp_path / "out" / "wx_dyad0_wxcorr.xlsx").exists()


def test_random_pairs_do_not_touch_state_on_their_thread(app, tmp_path, monkeypatch):
    write_dyad(tmp_path / "in" / "dyad0", seed=0)
    write_dyad(tmp_path / "in" / "dyad1", seed=1)
    timer = app.timer
    app.val_random_pair_input_folder.set(str(tmp_path / "in"))
    violations = _guard_all_vars(monkeypatch)
    _guard_settings(monkeypatch, violations, batch_params(tmp_path / "in", tmp_path))

    callbacks.handle_run_surrogate_button()
    timer.run_until_idle(60)

    assert violations == []
    assert app.dialogs and app.dialogs[0][:2] == ("showinfo", "Surrogate analysis finished")
    assert app.dat_surrogate_run['result'] is not None


def test_settings_changed_during_a_run_do_not_affect_it(app, tmp_path, monkeypatch):
    write_dyad(tmp_path / "in" / "dyad0")
    (tmp_path / "out").mkdir()
    settings = batch_params(tmp_path / "in", tmp_path / "out", window_size=150)
    used = []
    real = batch_processing.batch_process

    def slow_batch(params, progress):
        time.sleep(0.1)
        used.append(params['window_size'])
        return real(params, progress)

    monkeypatch.setattr(callbacks, "batch_process", slow_batch)
    monkeypatch.setattr(callbacks, "_analysis_params", lambda: dict(settings))
    callbacks.handle_run_batch_button()
    settings['window_size'] = 100

    app.timer.run_until_idle(60)

    assert used == [150]


def test_batch_reports_each_dyad_and_the_group_average(tmp_path):
    for index in range(2):
        write_dyad(tmp_path / "in" / f"dyad{index}", seed=index)
    (tmp_path / "out").mkdir()
    steps = []
    batch_processing.batch_process(batch_params(tmp_path / "in", tmp_path / "out"), progress=lambda *step: steps.append(step))
    assert steps == [(0, 2, "dyad0"), (1, 2, "dyad1"), (2, 2, "Group average")]


def test_random_pairs_report_every_step(tmp_path):
    for index in range(2):
        write_dyad(tmp_path / "in" / f"dyad{index}", seed=index)
    steps = []
    surrogates.welch_random_pair_test(
        batch_params(tmp_path / "in", tmp_path), str(tmp_path / "in"), 3,
        progress=lambda *step: steps.append(step),
    )
    assert [step[:2] for step in steps] == [(0, 5), (1, 5), (2, 5), (3, 5), (4, 5)]
    assert [step[2] for step in steps] == ["Random pairs"] * 3 + ["dyad0", "dyad1"]


def test_closing_only_asks_while_a_job_runs(app, monkeypatch):
    asked = []
    monkeypatch.setattr(callbacks.messagebox, "askokcancel", lambda title, text: asked.append(title) or False)
    assert callbacks.confirm_close() is True
    assert asked == []
    app.val_job_running.set(True)
    assert callbacks.confirm_close() is False
    assert asked == ["Still running"]


def test_progress_is_only_visible_while_a_job_runs(app, monkeypatch):
    frames = [FakeWidget(), FakeWidget()]
    monkeypatch.setattr(gui_updates, "_w", {'job_progress_panels': [{'frame': frame} for frame in frames]})
    app.val_job_running.set(True)
    gui_updates.update_job_progress_visibility()
    assert all(frame.visible for frame in frames)
    app.val_job_running.set(False)
    gui_updates.update_job_progress_visibility()
    assert not any(frame.visible for frame in frames)


def _steps_until_cancelled(app, steps=3):
    """Runs a job that waits to be cancelled during its first step. Returns the steps it started and a release."""
    started, finished = [], []
    in_first_step = threading.Event()
    release = threading.Event()

    def work(progress):
        for step in range(steps):
            progress(step, steps, f"step {step}")
            started.append(step)
            in_first_step.set()
            release.wait(5)
            finished.append(step)
        return "complete"

    callbacks._start_job("Job", work, lambda result: app.dialogs.append(("success", result, "")))
    assert in_first_step.wait(5)
    return started, finished, release


def test_cancelling_finishes_the_current_step_and_runs_no_more(app):
    started, finished, release = _steps_until_cancelled(app)
    callbacks.cancel_job()
    release.set()
    app.timer.run_until_idle()
    assert started == [0] and finished == [0]
    assert app.dialogs == [("showinfo", "Job cancelled", "Stopped early. Files that were already written are kept.")]


def test_buttons_are_restored_after_cancelling(app):
    _, _, release = _steps_until_cancelled(app)
    callbacks.cancel_job()
    assert _both_ready(app) == (False, False)
    release.set()
    app.timer.run_until_idle()
    assert app.val_job_running.get() is False
    assert _both_ready(app) == (True, True)


def test_cancelling_shows_at_once_and_stays_visible(app):
    _, _, release = _steps_until_cancelled(app)
    callbacks.cancel_job()
    assert app.val_job_cancel_requested.get() is True
    assert app.val_job_progress_text.get().startswith("Cancelling")
    release.set()
    app.timer.run_until_idle()
    assert app.val_job_progress_text.get().startswith("Cancelling")     # a queued step must not overwrite it


def test_next_job_is_not_affected_by_an_earlier_cancel(app):
    _, _, release = _steps_until_cancelled(app)
    callbacks.cancel_job()
    release.set()
    app.timer.run_until_idle()
    app.dialogs.clear()

    def work(progress):
        progress(0, 1, "step")
        return "complete"

    callbacks._start_job("Job", work, lambda result: app.dialogs.append(("success", result, "")))
    assert app.val_job_cancel_requested.get() is False
    app.timer.run_until_idle()
    assert app.dialogs == [("success", "complete", "")]


def test_job_that_finishes_before_noticing_counts_as_finished(app):
    release = threading.Event()

    def work(progress):
        progress(0, 1, "step")
        release.wait(5)
        return "complete"

    callbacks._start_job("Job", work, lambda result: app.dialogs.append(("success", result, "")))
    time.sleep(0.01)
    callbacks.cancel_job()
    release.set()
    app.timer.run_until_idle()
    assert app.dialogs == [("success", "complete", "")]


def test_cancelled_batch_keeps_finished_dyads_and_skips_the_group_average(app, tmp_path, monkeypatch):
    for index in range(3):
        write_dyad(tmp_path / "in" / f"dyad{index}", seed=index)
    (tmp_path / "out").mkdir()
    monkeypatch.setattr(callbacks, "_analysis_params", lambda: batch_params(tmp_path / "in", tmp_path / "out"))
    real = batch_processing.batch_process

    def cancel_during_second_dyad(params, progress):
        def reporting(done, total, text):
            if done == 2:
                callbacks._job_cancel_event.set()
            progress(done, total, text)
        return real(params, reporting)

    monkeypatch.setattr(callbacks, "batch_process", cancel_during_second_dyad)
    callbacks.handle_run_batch_button()
    app.timer.run_until_idle(60)

    written = sorted(path.name for path in (tmp_path / "out").glob("*.xlsx"))
    assert written == ["wx_dyad0_wxcorr.xlsx", "wx_dyad1_wxcorr.xlsx"]
    assert app.dialogs[0][1] == "Batch processing cancelled"


@pytest.mark.parametrize("cancel_at", ["Random pairs", "dyad1"])
def test_cancelled_random_pairs_write_no_results(app, tmp_path, monkeypatch, cancel_at):
    for index in range(2):
        write_dyad(tmp_path / "in" / f"dyad{index}", seed=index)
    real = callbacks.run_surrogate_analysis

    def cancelling(params, choice, input_dir, seed, progress):
        def reporting(done, total, text):
            if text == cancel_at:
                callbacks._job_cancel_event.set()
            progress(done, total, text)
        return real(params, choice, input_dir, seed, reporting)

    monkeypatch.setattr(callbacks, "run_surrogate_analysis", cancelling)
    monkeypatch.setattr(callbacks, "_analysis_params", lambda: batch_params(tmp_path / "in", tmp_path))
    app.val_random_pair_input_folder.set(str(tmp_path / "in"))

    callbacks.handle_run_surrogate_button()
    app.timer.run_until_idle(60)

    assert app.dat_surrogate_run['result'] is None
    assert app.dialogs[0][1] == "Surrogate analysis cancelled"


@pytest.mark.parametrize("requested, expected", [(True, "disabled"), (False, "normal")])
def test_cancel_button_can_only_be_clicked_once_per_run(app, monkeypatch, requested, expected):
    buttons = [FakeWidget(), FakeWidget()]
    monkeypatch.setattr(gui_updates, "_w", {'job_progress_panels': [{'button_cancel': button} for button in buttons]})
    app.val_job_cancel_requested.set(requested)
    gui_updates.update_active_state_cancel_button()
    assert [button.state for button in buttons] == [expected, expected]
