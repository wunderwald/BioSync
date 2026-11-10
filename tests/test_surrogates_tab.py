"""
The Surrogates tab: which test its choices mean, what it says before a run, what stops a run, and the run itself.
"""
import math
import os

import numpy as np
import openpyxl
import pytest

import callbacks
import corr_plot
import gui_updates
import plot
import surrogates
from analysis import AnalysisConfig
from helpers import FakeTimer, FakeWidget, batch_params, write_dyad
from measures import MEAN_ABS_R_MAX, MEAN_R, R_AT_LAG_0
from surrogates import (
    BLOCKS, GREATER, REPAIRED, SURROGATE_DISTRIBUTION, TWO_SIDED, WELCH, SurrogateChoice, choice_problem,
    few_sets_warning, folder_overview, plan_summary, smallest_p,
)


def _config(**overrides):
    settings = dict(
        signal_type='event-based', windowed=True, standardised=False, window_size=150, step_size=75, max_lag=30,
        absolute=False, average_windows=False, use_lag_filter=False, lag_filter_min=-30, lag_filter_max=30,
        max_lag_sxc=30, absolute_sxc=False,
    )
    settings.update(overrides)
    return AnalysisConfig(**settings)


# ---------------------------------------------------------------------------
# PLANNING, WITHOUT THE WINDOW
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("choice, config, expected", [
    (SurrogateChoice(REPAIRED, MEAN_R, 1000), _config(), None),
    (SurrogateChoice(REPAIRED, R_AT_LAG_0, 1000), _config(average_windows=True),
     "Can't compare r at lag 0: it needs a correlation for each lag, and 'average windows' is on."),
    (SurrogateChoice(BLOCKS, R_AT_LAG_0, 1000, 150), _config(use_lag_filter=True, lag_filter_min=2, lag_filter_max=9),
     "Can't compare r at lag 0: the lag filter leaves out lag 0."),
    (SurrogateChoice(WELCH, MEAN_R, 1), _config(), "The t-test needs at least 2 random pairs."),
    (SurrogateChoice(REPAIRED, MEAN_R, 0), _config(), "At least one surrogate is needed."),
    (SurrogateChoice(BLOCKS, MEAN_R, 1000, 0), _config(), "Enter a block length."),
    (SurrogateChoice(BLOCKS, MEAN_R, 1000, 30), _config(), None),
])
def test_choice_problem(choice, config, expected):
    assert choice_problem(choice, config) == expected


@pytest.mark.parametrize("n, side, expected", [(1000, GREATER, 1 / 1001), (1000, TWO_SIDED, 2 / 1001), (0, TWO_SIDED, 1.0)])
def test_smallest_p(n, side, expected):
    assert smallest_p(n, side) == pytest.approx(expected)


@pytest.mark.parametrize("choice, n_dyads, expected", [
    (SurrogateChoice(REPAIRED, MEAN_ABS_R_MAX, 1000), 33,
     "Compares mean |r_max| of the 33 real dyads with 1000 sets of re-paired people, one-sided (real higher). "
     "The smallest possible p is 0.000999."),
    (SurrogateChoice(BLOCKS, MEAN_R, 500, 60), None,
     "Compares mean r of the real dyads with 500 shuffled versions of each dyad, in blocks of 60 samples, "
     "two-sided. The smallest possible p is 0.00399."),
    (SurrogateChoice(WELCH, MEAN_ABS_R_MAX, 100), 1,
     "Compares mean |r_max| of the 1 real dyad with 100 random pairs with Welch's t-test, two-sided."),
])
def test_plan_summary(choice, n_dyads, expected):
    assert plan_summary(choice, _config(), n_dyads) == expected


def _folder(root, files_per_dyad):
    for index, n_files in enumerate(files_per_dyad):
        folder = root / f"dyad{index}"
        folder.mkdir(parents=True)
        for file_index in range(n_files):
            (folder / f"P{file_index}.xlsx").write_text("x")
    return root


@pytest.mark.parametrize("files_per_dyad, dyads, pairs", [
    ([2, 2, 2], 3, 15 - 3),
    ([2, 3, 1], 2, 15 - 1 - 3),         # a folder with one recording is no dyad, but its person can be re-paired
    ([], 0, 0),
])
def test_folder_overview_from_file_names(tmp_path, files_per_dyad, dyads, pairs):
    overview = folder_overview(str(_folder(tmp_path, files_per_dyad)))
    assert overview['n_dyads'] == dyads
    assert overview['n_pairs'] == pairs
    assert overview['n_sets'] == (math.comb(pairs, dyads) if pairs >= dyads else 0)


def test_few_sets_warning():
    assert few_sets_warning(None, 1000) is None
    assert few_sets_warning(1000, 1000) is None
    assert few_sets_warning(35, 1000) == (
        "Only 35 different sets of re-paired people are possible, fewer than the 1000 drawn, so sets repeat and "
        "p can't usefully go below about 1/35."
    )
    assert "Only about 35 different" in few_sets_warning(35, 1000, about=True)


# ---------------------------------------------------------------------------
# THE TAB'S STATE
# ---------------------------------------------------------------------------

@pytest.fixture
def tab(fake_state, monkeypatch):
    for name, value in {
        'val_surrogate_method': REPAIRED, 'val_surrogate_test': SURROGATE_DISTRIBUTION,
        'val_surrogate_measure': MEAN_R, 'val_rp_n_input': "1000", 'val_rp_n': 1000, 'val_window_size': 150,
        'val_block_length_input': "150", 'val_block_length': 150, 'val_checkbox_eb': True,
        'val_checkbox_windowed_xcorr': True, 'val_checkbox_standardise': False, 'val_step_size': 75,
        'val_max_lag': 30, 'val_checkbox_absolute_corr': False, 'val_checkbox_average_windows': False,
        'val_checkbox_lag_filter': False, 'val_lag_filter_min': -30, 'val_lag_filter_max': 30, 'val_max_lag_sxc': 150,
        'val_checkbox_absolute_corr_sxc': False, 'val_INPUT_DATA_VALID': True, 'val_CORRELATION_SETTINGS_VALID': True,
        'val_CORRELATION_SETTINGS_VALID_SXC': True, 'val_job_running': False, 'val_data_length': 4000,
        'val_random_pair_input_folder': '', 'val_exporting': '',
    }.items():
        getattr(fake_state, name).set(value)
    monkeypatch.setitem(callbacks._surrogates, 'method', REPAIRED)
    monkeypatch.setitem(callbacks._surrogates, 'folder', {})
    monkeypatch.setitem(callbacks._block_length, 'follows_window', True)
    monkeypatch.setitem(fake_state.dat_plot_data, 'fig', None)
    return fake_state


def _set_n(tab, n):
    tab.val_rp_n_input.set(str(n))
    callbacks.on_rp_n_input_change(None, None, None)


def _choose(tab, method=None, test=None):
    if method:
        tab.val_surrogate_method.set(method)
    if test:
        tab.val_surrogate_test.set(test)
    callbacks.on_surrogate_method_change()
    callbacks.on_rp_n_input_change(None, None, None)


def test_welch_is_an_option_of_re_paired_people(tab):
    assert callbacks.surrogate_choice() == SurrogateChoice(REPAIRED, MEAN_R, 1000, None)
    tab.val_surrogate_test.set(WELCH)
    assert callbacks.surrogate_choice().method == WELCH
    tab.val_surrogate_method.set(BLOCKS)
    assert callbacks.surrogate_choice() == SurrogateChoice(BLOCKS, MEAN_R, 1000, 150)


def test_usual_number_follows_the_test_until_it_is_changed(tab):
    _choose(tab, test=WELCH)
    assert tab.val_rp_n_input.get() == "100"
    _choose(tab, test=SURROGATE_DISTRIBUTION)
    assert tab.val_rp_n_input.get() == "1000"
    _set_n(tab, 250)
    _choose(tab, test=WELCH)
    assert tab.val_rp_n_input.get() == "250"


def test_shuffled_blocks_keep_the_number_of_re_paired_people(tab):
    _choose(tab, method=BLOCKS)
    assert tab.val_rp_n_input.get() == "1000"


def _set_window(tab, size):
    tab.val_window_size.set(size)
    callbacks.on_window_size_change_update_block_length()
    callbacks.on_block_length_input_change(None, None, None)


def _set_block_length(tab, text):
    tab.val_block_length_input.set(text)
    callbacks.on_block_length_input_change(None, None, None)


def test_block_length_follows_the_window_size_until_it_is_changed(tab):
    _set_window(tab, 100)
    assert tab.val_block_length.get() == 100
    _set_block_length(tab, "60")
    _set_window(tab, 200)
    assert tab.val_block_length.get() == 60
    _set_block_length(tab, "200")      # the same as the window again
    _set_window(tab, 250)
    assert tab.val_block_length.get() == 250


def test_plan_and_readiness(tab, tmp_path):
    callbacks.update_surrogate_plan()
    assert tab.val_surrogate_plan.get().startswith("Compares mean r of the real dyads with 1000 sets")
    assert tab.val_random_pair_is_ready.get() is False          # no folder yet
    _folder(tmp_path / "in", [2] * 6)
    tab.val_random_pair_input_folder.set(str(tmp_path / "in"))
    callbacks.on_surrogate_folder_change()
    assert "the 6 real dyads" in tab.val_surrogate_plan.get()
    assert tab.val_surrogate_problem.get() == ''
    assert tab.val_random_pair_is_ready.get() is True


def test_a_ruled_out_measure_stops_the_run(tab, tmp_path):
    tab.val_random_pair_input_folder.set("in")
    tab.val_surrogate_measure.set(R_AT_LAG_0)
    tab.val_checkbox_average_windows.set(True)
    callbacks.update_surrogate_plan()
    assert "average windows" in tab.val_surrogate_problem.get()
    assert tab.val_surrogate_plan.get() == ''
    assert tab.val_random_pair_is_ready.get() is False


def test_warns_when_few_sets_of_re_paired_people_exist(tab, tmp_path):
    tab.val_random_pair_input_folder.set(str(_folder(tmp_path / "in", [2, 2, 2])))
    callbacks.on_surrogate_folder_change()
    assert tab.val_surrogate_warning.get().startswith("Only about 220 different sets")
    _choose(tab, test=WELCH)            # Welch draws single pairs, not sets
    assert tab.val_surrogate_warning.get() == ''


def test_warns_about_a_folder_without_dyads(tab, tmp_path):
    tab.val_random_pair_input_folder.set(str(_folder(tmp_path / "in", [1, 1])))
    callbacks.on_surrogate_folder_change()
    assert tab.val_surrogate_warning.get() == "The selected folder has no dyad folders with two recordings."


@pytest.mark.parametrize("data_length, block_length, n, expected", [
    (4000, 150, 1000, ''),
    (600, 120, 1000, "allow 119 different orders, fewer than the 1000 drawn"),
    (600, 120, 120, "allow 119 different orders, fewer than the 120 drawn"),
    (600, 120, 119, ''),
    (600, 150, 1000, "fits only 4 blocks of 150 samples, and at least 5 are needed"),
])
def test_warns_about_blocks_of_the_loaded_dyad(tab, data_length, block_length, n, expected):
    tab.val_data_length.set(data_length)
    _choose(tab, method=BLOCKS)
    _set_n(tab, n)
    _set_block_length(tab, str(block_length))
    callbacks.update_surrogate_plan()
    assert expected in tab.val_surrogate_warning.get()
    if not expected:
        assert tab.val_surrogate_warning.get() == ''


# ---------------------------------------------------------------------------
# WIDGETS
# ---------------------------------------------------------------------------

@pytest.fixture
def widgets(monkeypatch):
    keys = ('label_surrogate_method_explanation', 'frame_surrogate_test', 'frame_block_length', 'label_surrogate_n',
            'label_measure_explanation', 'label_surrogate_problem', 'label_surrogate_warning', 'entry_block_length')
    fake = {key: FakeWidget() for key in keys}
    monkeypatch.setattr(gui_updates, "_w", fake)
    return fake


@pytest.mark.parametrize("method, test, block_shown, test_shown, n_label, explained", [
    (REPAIRED, SURROGATE_DISTRIBUTION, False, True, "Surrogates", "strangers"),
    (REPAIRED, WELCH, False, True, "Random pairs", "earlier versions"),
    (BLOCKS, SURROGATE_DISTRIBUTION, True, False, "Surrogates", "blocks"),
    (BLOCKS, WELCH, True, False, "Surrogates", "blocks"),        # Welch is only an option of re-paired people
])
def test_method_widgets(tab, widgets, method, test, block_shown, test_shown, n_label, explained):
    tab.val_surrogate_method.set(method)
    tab.val_surrogate_test.set(test)
    gui_updates.update_surrogate_method_widgets()
    assert widgets['frame_block_length'].visible is block_shown
    assert widgets['frame_surrogate_test'].visible is test_shown
    assert widgets['label_surrogate_n'].text == n_label
    assert explained in widgets['label_surrogate_method_explanation'].text


def test_problem_and_warning_are_only_shown_with_text(tab, widgets):
    tab.val_surrogate_problem.set("Enter a block length.")
    tab.val_surrogate_warning.set("")
    gui_updates.update_surrogate_messages()
    assert widgets['label_surrogate_problem'].visible and not widgets['label_surrogate_warning'].visible
    assert widgets['entry_block_length'].border_color == 'red'
    tab.val_surrogate_problem.set("")
    gui_updates.update_surrogate_messages()
    assert not widgets['label_surrogate_problem'].visible
    assert widgets['entry_block_length'].border_color == '#777777'


# ---------------------------------------------------------------------------
# RUNNING
# ---------------------------------------------------------------------------

@pytest.fixture
def run(tab, tmp_path, monkeypatch):
    for index in range(3):
        write_dyad(tmp_path / "in" / f"dyad{index}", seed=index)
    tab.val_random_pair_input_folder.set(str(tmp_path / "in"))
    tab.val_rp_seed_input.set("7")
    tab.val_job_progress.set(0)
    tab.timer = FakeTimer()
    monkeypatch.setitem(callbacks._tabview, "tabview", tab.timer)
    monkeypatch.setattr(callbacks, "_analysis_params", lambda: batch_params(tmp_path / "in", tmp_path))
    tab.dialogs = []
    for kind in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(callbacks.messagebox, kind, lambda title, text, kind=kind: tab.dialogs.append((kind, title, text)))
    tab.output = tmp_path / "result.xlsx"
    monkeypatch.setattr(callbacks.filedialog, "asksaveasfilename",
                        lambda **kwargs: str(tab.output.with_suffix(kwargs['defaultextension'])))
    return tab


@pytest.mark.parametrize("method, block_length", [(REPAIRED, None), (BLOCKS, 300)])
def test_run_writes_the_chosen_test_and_says_what_it_found(run, method, block_length):
    _choose(run, method=method)
    _set_n(run, 30)
    if block_length:
        _set_block_length(run, str(block_length))
    callbacks.handle_run_surrogate_button()
    run.timer.run_until_idle(60)
    assert not run.output.exists()          # running doesn't export
    callbacks.export_surrogate_data()
    kind, title, text = run.dialogs[0]
    rows = {row[0]: row[1] for row in openpyxl.load_workbook(run.output).worksheets[0].iter_rows(max_col=2, values_only=True)}
    assert rows['Method'] == method and rows['Surrogate sets'] == 30 and rows['Random seed'] == 7
    assert text.splitlines()[0] == rows['Summary']
    assert not os.path.exists(run.output.with_suffix(".png"))      # the plot has its own button
    callbacks.export_surrogate_plot()
    assert os.path.getsize(run.output.with_suffix(".png")) > 0
    if method == REPAIRED:
        assert (kind, title) == ("showinfo", "Surrogate analysis finished")
    else:
        # 3 dyads of about 13 blocks: plenty of orders, so no problem either
        assert rows['Block length (samples)'] == block_length
        assert (kind, title) == ("showinfo", "Surrogate analysis finished")


def test_few_sets_of_re_paired_people_turn_the_message_into_a_warning(run):
    _set_n(run, 1000)       # 3 dyads, 12 pairs: 220 sets
    callbacks.handle_run_surrogate_button()
    run.timer.run_until_idle(60)
    kind, title, text = run.dialogs[0]
    assert (kind, title) == ("showwarning", "Surrogate analysis finished with problems")
    assert "Only 220 different sets of re-paired people are possible" in text


def test_few_block_orders_turn_the_message_into_a_warning(run):
    _choose(run, method=BLOCKS)
    _set_n(run, 150)
    _set_block_length(run, "750")    # 5 blocks per dyad: 119 orders
    callbacks.handle_run_surrogate_button()
    run.timer.run_until_idle(60)
    kind, title, text = run.dialogs[0]
    assert (kind, title) == ("showwarning", "Surrogate analysis finished with problems")
    assert "3 of 3 dyads allow fewer different block orders than the 150 drawn" in text


def test_a_problem_stops_the_run_before_it_starts(run, tmp_path, monkeypatch):
    run.val_surrogate_measure.set(R_AT_LAG_0)
    monkeypatch.setattr(callbacks, "_analysis_params",
                        lambda: batch_params(tmp_path / "in", tmp_path, checkbox_average_windows=True))
    callbacks.handle_run_surrogate_button()
    assert run.val_job_running.get() is False
    assert run.dialogs == [("showwarning", "Can't run the surrogate analysis",
                            "Can't compare r at lag 0: it needs a correlation for each lag, and 'average windows' is on.")]
    assert run.dat_surrogate_run['result'] is None


# ---------------------------------------------------------------------------
# THE RESULT IN THE PLOT AREA
# ---------------------------------------------------------------------------

def _figure_texts(fig):
    return [text.get_text() for text in fig.texts]


def test_plot_says_how_to_get_a_result_before_any_run(tab, monkeypatch):
    tab.val_CURRENT_TAB.set("Surrogates")
    corr_plot.update_plot()
    assert _figure_texts(tab.dat_plot_data["fig"]) == [corr_plot.NO_SURROGATE_RESULT]


@pytest.fixture
def ran(run, tmp_path, monkeypatch):
    """A finished run, with settings that a test can change afterwards."""
    params = batch_params(tmp_path / "in", tmp_path)
    monkeypatch.setattr(callbacks, "_analysis_params", lambda: dict(params))
    run.params = params
    run.redraws = []
    monkeypatch.setattr(callbacks.state, "PARAMS_CHANGED", lambda debounce=False: run.redraws.append(debounce))
    run.val_CURRENT_TAB.set("Surrogates")
    _set_n(run, 20)
    callbacks.handle_run_surrogate_button()
    run.timer.run_until_idle(60)
    return run


def test_finished_run_is_kept_and_shown(ran):
    stored = ran.dat_surrogate_run
    assert stored['result'].n_surrogates == 20 and stored['result'].seed == 7
    assert stored['stale'] is False
    assert ran.redraws                  # the Surrogates tab is open, so its plot is redrawn
    corr_plot.update_plot()
    fig = ran.dat_plot_data["fig"]
    assert fig._suptitle.get_text() == "Last run: in, seed 7."
    assert any("re-paired people" in ax.get_title() for ax in fig.axes)


@pytest.mark.parametrize("change, stale", [
    (lambda run: run.params.update(window_size=100), True),
    (lambda run: run.val_surrogate_measure.set(MEAN_ABS_R_MAX), True),
    (lambda run: _set_n(run, 21), True),
    (lambda run: run.val_random_pair_input_folder.set("elsewhere"), True),
    (lambda run: run.val_rp_seed_input.set("8"), False),                 # the next run, not this result
    (lambda run: run.params.update(sigmoid_correlations=True), False),   # only changes how heatmaps look
])
def test_result_is_marked_when_its_settings_change(ran, change, stale):
    ran.redraws.clear()
    change(ran)
    callbacks.update_surrogate_plan()
    assert ran.dat_surrogate_run['stale'] is stale
    assert bool(ran.redraws) is stale
    corr_plot.update_plot()
    suptitle = ran.dat_plot_data["fig"]._suptitle
    assert ("settings have changed since" in suptitle.get_text()) is stale
    assert (suptitle.get_color() == plot.STALE_COLOR) is stale


def test_changing_a_setting_back_unmarks_the_result(ran):
    ran.params.update(window_size=100)
    callbacks.update_surrogate_plan()
    ran.params.update(window_size=150)
    callbacks.update_surrogate_plan()
    assert ran.dat_surrogate_run['stale'] is False


def test_the_plot_only_redraws_when_the_mark_changes(ran):
    ran.params.update(window_size=100)
    callbacks.update_surrogate_plan()
    ran.redraws.clear()
    ran.params.update(window_size=90)
    callbacks.update_surrogate_plan()
    assert ran.redraws == []


def test_other_tabs_are_not_redrawn_for_a_surrogate_result(ran):
    ran.val_CURRENT_TAB.set("Correlation")
    ran.redraws.clear()
    ran.params.update(window_size=100)
    callbacks.update_surrogate_plan()
    assert ran.dat_surrogate_run['stale'] is True and ran.redraws == []


def test_settings_changed_during_the_run_mark_the_result_at_once(run, tmp_path, monkeypatch):
    params = batch_params(tmp_path / "in", tmp_path)
    monkeypatch.setattr(callbacks, "_analysis_params", lambda: dict(params))
    _set_n(run, 20)
    callbacks.handle_run_surrogate_button()
    params.update(window_size=100)      # while the job runs
    run.timer.run_until_idle(60)
    assert run.dat_surrogate_run['stale'] is True


# ---------------------------------------------------------------------------
# EXPORT
# ---------------------------------------------------------------------------

def test_result_line_says_which_run_the_export_writes(ran):
    assert ran.val_surrogate_result_text.get() == "Last run: in, seed 7."
    ran.params.update(window_size=100)
    callbacks.update_surrogate_plan()
    assert ran.val_surrogate_result_text.get() == (
        "Last run: in, seed 7. The settings have changed since. The export has the settings of that run."
    )


def test_export_has_the_settings_of_the_run_even_after_they_changed(ran):
    ran.params.update(window_size=100)
    _set_n(ran, 50)
    callbacks.update_surrogate_plan()
    callbacks.export_surrogate_data()
    rows = {row[0]: row[1] for row in openpyxl.load_workbook(ran.output).worksheets[0].iter_rows(max_col=2, values_only=True)}
    assert rows['Window size'] == 150 and rows['Surrogate sets'] == 20


@pytest.mark.parametrize("export, extension", [
    (callbacks.export_surrogate_data, ".xlsx"), (callbacks.export_surrogate_plot, ".png"),
])
def test_export_suggests_a_name_and_can_be_cancelled(ran, monkeypatch, export, extension):
    asked = []
    monkeypatch.setattr(callbacks.filedialog, "asksaveasfilename", lambda **kwargs: asked.append(kwargs) or "")
    export()
    assert (asked[0]['initialfile'], asked[0]['defaultextension']) == ("biosync_surrogates_in", extension)
    assert asked[0]['filetypes'][0][1] == f"*{extension}"
    assert not ran.output.exists() and not ran.output.with_suffix(".png").exists()


def test_plot_export_is_the_figure_of_the_last_result(ran, monkeypatch):
    saved = []
    monkeypatch.setattr(callbacks, "export_surrogate_figure", lambda path, result: saved.append((path, result)))
    callbacks.export_surrogate_plot()
    assert saved == [(str(ran.output.with_suffix(".png")), ran.dat_surrogate_run['result'])]
    assert not ran.output.exists()


@pytest.mark.parametrize("export, extension", [
    (callbacks.export_surrogate_data, ".xlsx"), (callbacks.export_surrogate_plot, ".png"),
])
def test_failed_export_shows_an_error(ran, monkeypatch, export, extension):
    monkeypatch.setattr(callbacks.filedialog, "asksaveasfilename", lambda **kwargs: f"/nonexistent/folder/r{extension}")
    ran.dialogs.clear()
    export()
    assert ran.dialogs[0][:2] == ("showerror", "Export failed")
    assert ran.val_exporting.get() == ''


def test_nothing_to_export_before_a_run(run, monkeypatch):
    monkeypatch.setattr(callbacks.filedialog, "asksaveasfilename", lambda **kwargs: pytest.fail("asked for a file"))
    callbacks.export_surrogate_data()
    callbacks.export_surrogate_plot()


@pytest.fixture
def export_widgets(tab, monkeypatch):
    widgets = {'label_surrogate_result': FakeWidget(), 'button_export_surrogate_data': FakeWidget(),
               'button_export_surrogate_plot': FakeWidget()}
    monkeypatch.setattr(gui_updates, "_w", widgets)
    return widgets


@pytest.mark.parametrize("result_text, running, exporting, enabled", [
    ("", False, "", False),
    ("Last run: in, seed 7.", False, "", True),
    ("Last run: in, seed 7.", True, "", False),             # a new result is on its way
    ("Last run: in, seed 7.", False, "surrogate data", False),
    ("Last run: in, seed 7.", False, "surrogate plot", False),
])
def test_export_button_needs_a_result(tab, export_widgets, result_text, running, exporting, enabled):
    tab.val_surrogate_result_text.set(result_text)
    tab.val_job_running.set(running)
    tab.val_exporting.set(exporting)
    gui_updates.update_surrogate_export()
    for key in ('button_export_surrogate_data', 'button_export_surrogate_plot'):
        assert export_widgets[key].state == ("normal" if enabled else "disabled")
    assert export_widgets['label_surrogate_result'].text == (result_text or gui_updates.NO_SURROGATE_RESULT_TEXT)


@pytest.mark.parametrize("kind, busy, idle", [
    ("surrogate data", 'button_export_surrogate_data', 'button_export_surrogate_plot'),
    ("surrogate plot", 'button_export_surrogate_plot', 'button_export_surrogate_data'),
])
def test_export_button_is_busy_while_writing_and_back_afterwards(tab, monkeypatch, kind, busy, idle):
    texts = (('button_export_data', 'Export XLSX'), ('button_export_plot', 'Export Plots'),
             ('button_export_surrogate_data', 'Export XLSX'), ('button_export_surrogate_plot', 'Export PNG'))
    buttons = {key: FakeWidget(toplevel=FakeWidget(), text=text) for key, text in texts}
    monkeypatch.setattr(gui_updates, "_w", {**buttons, 'label_surrogate_result': FakeWidget()})
    monkeypatch.setattr(gui_updates, "_export_button_texts", {})
    monkeypatch.setattr(gui_updates.validation, "check_export_ready", lambda: True)
    tab.val_surrogate_result_text.set("Last run: in, seed 7.")
    tab.val_exporting.set(kind)
    gui_updates.update_export_busy()
    assert (buttons[busy].text, buttons[busy].state) == ("Exporting...", "disabled")
    assert buttons[idle].state == "disabled" and buttons[idle].text != "Exporting..."
    tab.val_exporting.set("")
    gui_updates.update_export_busy()
    assert {key: (buttons[key].text, buttons[key].state) for key, _ in texts[2:]} == {
        key: (text, "normal") for key, text in texts[2:]}
