import importlib.util
import os
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


def _make_tcl_tk(base, parent):
    tcl_dir, tk_dir = base / parent / "tcl8.6", base / parent / "tk8.6"
    tcl_dir.mkdir(parents=True)
    tk_dir.mkdir(parents=True)
    (tcl_dir / "init.tcl").write_text("")
    (tk_dir / "tk.tcl").write_text("")
    return str(tcl_dir), str(tk_dir)


@pytest.mark.parametrize("parent", ["tcl", "lib", os.path.join("Library", "lib")])
def test_build_finds_tcl_tk_where_python_installers_put_it(tmp_path, parent):
    expected = _make_tcl_tk(tmp_path, parent)
    assert build_script.find_tcl_tk_data(str(tmp_path), "8.6", "8.6") == expected


def test_build_ignores_tcl_tk_folders_without_their_scripts(tmp_path):
    (tmp_path / "tcl" / "tcl8.6").mkdir(parents=True)
    (tmp_path / "tcl" / "tk8.6").mkdir(parents=True)
    assert build_script.find_tcl_tk_data(str(tmp_path), "8.6", "8.6") is None


def test_build_finds_this_pythons_tcl_tk():
    import sys
    import tkinter
    assert build_script.find_tcl_tk_data(sys.base_prefix, tkinter.TclVersion, tkinter.TkVersion) is not None
