"""
Checks on the real window, which the other tests replace with stand-ins. Needs a display.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import callbacks


@pytest.fixture(scope="module")
def report():
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "real_window_check.py"), os.path.dirname(callbacks.__file__)],
        capture_output=True, text=True, timeout=60,
    )
    if "TclError" in result.stderr and "display" in result.stderr:
        pytest.skip("no display")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("key", ['dropdown_select_sheet', 'dropdown_select_column'])
def test_dropdowns_open_when_clicked_anywhere(report, key):
    # A CTkComboBox only opens from its small arrow, and its text can be typed into.
    assert report['dropdowns'][key] == {'type': 'CTkOptionMenu', 'opens_from_text': True, 'opens_from_arrow': True}


def test_tab_changes_keep_the_panel_and_the_plot_the_same_size(report):
    # Any size change resizes the plot, and every plot resize is a slow redraw.
    tabs = report['tabs'].values()
    assert len({tab['tabview_width'] for tab in tabs}) == 1
    assert len({tab['plot_width'] for tab in tabs}) == 1
    assert report['plot_resizes_during_tab_changes'] == 0     # not even for a moment during a change


def test_only_tabs_that_dont_fit_get_a_scrollbar(report):
    assert report['tabs']['Input Data']['scrollbar_shown'] is False
    assert report['tabs']['Export & Batch']['scrollbar_shown'] is True
