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
    assert report['tabs']['Surrogates']['scrollbar_shown'] is True


def test_every_tab_name_fits_in_the_tab_bar(report):
    assert report['tab_bar_fits'] is True


def test_surrogates_tab_shows_what_the_choices_need(report):
    surrogates = report['surrogates']
    start, welch, blocks = surrogates['start'], surrogates['welch'], surrogates['blocks']
    assert (start['method'], start['n_label'], start['n']) == ("re-paired people", "Surrogates", "1000")
    assert start['test_shown'] and not start['block_length_shown']
    assert "1000 sets of re-paired people" in start['plan']
    # Welch is the test of earlier versions, with their usual 100 random pairs
    assert (welch['test'], welch['n_label'], welch['n']) == ("random pairs, Welch's t-test", "Random pairs", "100")
    assert (blocks['method'], blocks['test'], blocks['n']) == ("shuffled blocks", "surrogate distribution", "1000")
    assert blocks['block_length_shown'] and not blocks['test_shown']
    assert "blocks of 150 samples" in blocks['plan']


def test_block_length_follows_the_window_size(report):
    assert report['surrogates']['block_length_follows_window'][0] == "100"


def test_a_measure_the_settings_rule_out_is_named_and_blocks_the_run(report):
    ruled_out, allowed = report['surrogates']['ruled_out'], report['surrogates']['allowed_again']
    assert ruled_out['problem_shown'] and not ruled_out['run_enabled'] and ruled_out['plan'] == ""
    assert ruled_out['problem'] == (
        "Can't compare r at lag 0: it needs a correlation for each lag, and 'average windows' is on."
    )
    assert not allowed['problem_shown'] and "r at lag 0" in allowed['plan']


def test_surrogates_tab_keeps_the_panel_width(report):
    assert report['surrogates']['widest'] <= 410


def test_eda_folder_loads_as_fixed_rate(report):
    assert report['eda'] == {'fixed_rate': True, 'valid': True, 'reason': ''}


def test_no_errors_in_callbacks(report):
    assert report['callback_errors'] == []


def test_buttons_that_open_dialogs_run_on_release(report):
    # On press, a dialog would make Tk miss the release and send every later click back to the button
    assert report['click'] == {
        'runs_on_press': [],
        'runs_after_release': ['open_batch_input_folder'],
        'runs_after_release_outside': [],
        'runs_when_disabled': [],
    }


def test_surrogates_tab_plots_its_last_result(report):
    plot = report['surrogate_plot']
    assert plot['before_run'] == ["Run a surrogate analysis to see its result here."]
    assert plot['after_run'] == "Last run: dyads, seed 3." and plot['axes'] == 1
    assert plot['other_tab_axes_titles'] == ["Correlation Heatmap"]     # the other tabs keep the loaded dyad
