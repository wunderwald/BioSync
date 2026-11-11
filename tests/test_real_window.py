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
    start, repaired = surrogates['start'], surrogates['repaired']
    welch, blocks = surrogates['welch'], surrogates['blocks']
    # shuffled blocks with mean r is the default
    assert (start['method'], start['n_label'], start['n']) == ("shuffled blocks", "Surrogates", "1000")
    assert start['block_length_shown'] and not start['test_shown']
    assert "mean r" in start['plan'] and "blocks of" in start['plan']
    assert (repaired['method'], repaired['n']) == ("re-paired people", "1000")
    assert repaired['test_shown'] and not repaired['block_length_shown']
    assert "1000 sets of re-paired people" in repaired['plan']
    # Welch is the test of earlier versions, with their usual 100 random pairs
    assert (welch['test'], welch['n_label'], welch['n']) == ("random pairs, Welch's t-test", "Random pairs", "100")
    assert (blocks['method'], blocks['test'], blocks['n']) == ("shuffled blocks", "surrogate distribution", "1000")
    assert blocks['block_length_shown'] and not blocks['test_shown']
    assert "blocks of 150 samples" in blocks['plan']


def test_surrogate_choices_in_order(report):
    assert report['surrogates']['buttons'] == {
        'segmented_surrogate_method': ["Shuffled blocks", "Re-paired people"],
        'segmented_surrogate_measure': ["mean r", "mean |r|", "mean |r_max|", "r at lag 0"],
    }


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


def test_fixed_rate_shows_seconds_only_with_a_known_rate(report):
    unknown, entered = report['sampling_rate']['unknown'], report['sampling_rate']['entered']
    assert unknown['field_shown'] and not unknown['resampling_note_shown']
    assert unknown['note'].startswith("No time column found next to the data")
    assert unknown['window_seconds'] == ''
    assert entered['window_seconds'] == '75 s'      # 150 samples at 2 Hz
    assert entered['note'] == "Entered by hand."


def test_export_comes_after_the_run_and_needs_a_result(report):
    before, after = report['surrogate_plot']['export_before'], report['surrogate_plot']['export_after']
    assert before == {'buttons': ['Export XLSX', 'disabled', 'Export PNG', 'disabled'],
                      'text': "Run the analysis to export its result.", 'below_run': True, 'side_by_side': True}
    assert after == {'buttons': ['Export XLSX', 'normal', 'Export PNG', 'normal'],
                     'text': "Last run: dyads, seed 3.", 'below_run': True, 'side_by_side': True}


def test_correlation_tab_shows_signal_properties_above_the_lag_hint(report):
    for kind, hint in (('windowed', 'How to read tau_max'), ('standard', 'How to read lag')):
        tab = report['correlation_tab'][kind]
        assert tab['order'] is True, kind
        assert tab['hint_shown'] is (kind == 'windowed') and tab['lag_info_shown'] is (kind == 'standard')
        texts = tab['texts']
        properties = texts.index("Signal Properties")
        assert texts[properties + 1:properties + 5:2] == ["Stationarity", "Persistence"]
        assert texts[properties + 2].startswith("KPSS")
        assert texts[properties + 4].startswith("DFA")
        assert any(text.startswith(hint) for text in texts[properties + 5:])


def test_correlation_tab_sections_are_separate_outlined_cards(report):
    for kind, tab in report['correlation_tab'].items():
        assert tab['outlined'] == [True, True, True], kind
        assert all(gap > 0 for gap in tab['gaps_between_cards']), kind
        assert all(inset > 1 for inset in tab['panel_inset']), kind     # the parameter panel doesn't cover the outline
        assert tab['cards_in_view'], kind


def test_sigmoid_scaling_is_hidden(report):
    for tab in report['correlation_tab'].values():
        assert not [text for text in tab['texts'] if 'igmoid' in text or text == "Visualisation"]
