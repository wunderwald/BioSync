"""
Batch and random pair analysis run on another thread. They must not use Tk there, must keep the settings they
started with, and must leave the app usable afterwards however they end.
"""
import threading
import time

import pytest

import batch_processing
import callbacks
import gui_updates
import state
from test_batch import ImmediateTimer, _params, _write_dyad


@pytest.fixture
def app(fake_state, monkeypatch):
    for name in ("val_INPUT_DATA_VALID", "val_CORRELATION_SETTINGS_VALID", "val_CORRELATION_SETTINGS_VALID_SXC",
                 "val_checkbox_windowed_xcorr"):
        getattr(fake_state, name).set(True)
    fake_state.val_job_running.set(False)
    fake_state.val_job_progress.set(0)
    fake_state.val_rp_n.set(3)
    for name in ("val_batch_input_folder", "val_batch_output_folder", "val_random_pair_input_folder", "val_random_pair_output_file"):
        getattr(fake_state, name).set("selected")
    fake_state.timer = ImmediateTimer()
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
    callbacks._random_pair_is_ready()
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
    _write_dyad(tmp_path / "in" / "dyad0")
    (tmp_path / "out").mkdir()
    timer = app.timer
    violations = _guard_all_vars(monkeypatch)
    _guard_settings(monkeypatch, violations, _params(tmp_path / "in", tmp_path / "out"))

    callbacks.handle_run_batch_button()
    timer.run_until_idle(60)

    assert violations == []
    assert app.dialogs and app.dialogs[0][:2] == ("showinfo", "Batch processing finished")
    assert (tmp_path / "out" / "wx_dyad0_wxcorr.xlsx").exists()


def test_random_pairs_do_not_touch_state_on_their_thread(app, tmp_path, monkeypatch):
    _write_dyad(tmp_path / "in" / "dyad0", seed=0)
    _write_dyad(tmp_path / "in" / "dyad1", seed=1)
    timer = app.timer
    app.val_random_pair_input_folder.set(str(tmp_path / "in"))
    app.val_random_pair_output_file.set(str(tmp_path / "rp.xlsx"))
    violations = _guard_all_vars(monkeypatch)
    _guard_settings(monkeypatch, violations, _params(tmp_path / "in", tmp_path))

    callbacks.handle_run_random_pair_button()
    timer.run_until_idle(60)

    assert violations == []
    assert app.dialogs and app.dialogs[0][:2] == ("showinfo", "Random pair analysis finished")
    assert (tmp_path / "rp.xlsx").exists()


def test_settings_changed_during_a_run_do_not_affect_it(app, tmp_path, monkeypatch):
    _write_dyad(tmp_path / "in" / "dyad0")
    (tmp_path / "out").mkdir()
    settings = _params(tmp_path / "in", tmp_path / "out", window_size=150)
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
        _write_dyad(tmp_path / "in" / f"dyad{index}", seed=index)
    (tmp_path / "out").mkdir()
    steps = []
    batch_processing.batch_process(_params(tmp_path / "in", tmp_path / "out"), progress=lambda *step: steps.append(step))
    assert steps == [(0, 2, "dyad0"), (1, 2, "dyad1"), (2, 2, "Group average")]


def test_random_pairs_report_every_step(tmp_path):
    for index in range(2):
        _write_dyad(tmp_path / "in" / f"dyad{index}", seed=index)
    steps = []
    batch_processing.random_pair_analysis(
        _params(tmp_path / "in", tmp_path), str(tmp_path / "in"), random_pair_count=3,
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


class FakeFrame:
    def __init__(self):
        self.visible = False

    def grid(self, **kwargs):
        self.visible = True

    def grid_forget(self):
        self.visible = False


def test_progress_is_only_visible_while_a_job_runs(app, monkeypatch):
    frame = FakeFrame()
    monkeypatch.setattr(gui_updates, "_w", {'subgroup_job_progress': frame})
    app.val_job_running.set(True)
    gui_updates.update_job_progress_visibility()
    assert frame.visible
    app.val_job_running.set(False)
    gui_updates.update_job_progress_visibility()
    assert not frame.visible
