import importlib.util
from pathlib import Path

import pytest

import callbacks
import layout

_spec = importlib.util.spec_from_file_location("build_script", Path(callbacks.__file__).parent / "build.py")
build_script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_script)


class FakeTabview:
    def __init__(self, events):
        self.events = events
        self.selected = None

    def get(self):
        return self.selected

    def update_idletasks(self):
        self.events.append("tab shown")


@pytest.fixture
def tabs(fake_state, monkeypatch):
    events = []
    tabview = FakeTabview(events)
    monkeypatch.setitem(callbacks._tabview, "tabview", tabview)
    monkeypatch.setattr(callbacks.state, "PARAMS_CHANGED", lambda: events.append("plot update"))

    def switch(previous, selected):
        fake_state.val_CURRENT_TAB.set(previous)
        tabview.selected = selected
        events.clear()
        callbacks.on_tab_change()
        assert fake_state.val_CURRENT_TAB.get() == selected
        return list(events)
    return switch


@pytest.mark.parametrize("previous, selected", [
    ("Input Data", "Correlation"), ("Correlation", "Input Data"),
    ("Input Data", "Export & Batch"), ("Export & Batch", "Input Data"),
])
def test_new_tab_is_shown_before_a_plot_change(tabs, previous, selected):
    assert tabs(previous, selected) == ["tab shown", "plot update"]


@pytest.mark.parametrize("previous, selected", [("Correlation", "Export & Batch"), ("Export & Batch", "Correlation")])
def test_tabs_that_share_a_plot_do_not_redraw_it(tabs, previous, selected):
    assert tabs(previous, selected) == []



@pytest.mark.parametrize("content, visible, expected", [(700, 652, True), (652, 652, False), (500, 815, False)])
def test_scrollbar_only_when_the_settings_dont_fit(content, visible, expected):
    assert layout.needs_scrollbar(content, visible) == expected


@pytest.mark.parametrize("platform, version, affected", [
    ("darwin", "8.6.12", True), ("darwin", "8.6.13", False), ("darwin", "8.6.15", False), ("darwin", "9.0.1", False),
    ("darwin", "8.5.9", True), ("win32", "8.6.12", False), ("linux", "8.6.12", False),
])
def test_build_warns_about_the_affected_tk(platform, version, affected):
    assert build_script.is_affected_tk(platform, version) == affected
