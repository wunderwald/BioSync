"""
The GUI, batch and random pairs must give identical results, and existing pipelines must keep working on exports.
"""
import dataclasses

import matplotlib
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
import openpyxl
import pytest
from openpyxl import Workbook

import analysis
import batch_processing
import callbacks
import corr_plot
import export
import gui_updates
import plot
import state
import xlsx
from helpers import EXPORT_WINDOW, FakeWidget, export_params, read_column, read_metadata, read_notes, read_table

SHEET = "Sheet"
SETTINGS = [
    {},
    {"standardised_signals": True},
    {"checkbox_absolute_corr": True},
    {"checkbox_average_windows": True},
    {"use_lag_filter": True, "lag_filter_min": -5, "lag_filter_max": 10},
    {"window_size": 100, "step_size": 20, "max_lag": 15},
    {"checkbox_windowed_xcorr": False},
    {"checkbox_windowed_xcorr": False, "checkbox_absolute_corr_sxc": True, "max_lag_sxc": 40},
    {"checkbox_windowed_xcorr": False, "standardised_signals": True},
    {"checkbox_eb": False, "checkbox_fr": True},
]
# Writing files is slow, so file comparisons use the settings that change what an export contains
FILE_SETTINGS = [
    {},
    {"use_lag_filter": True, "lag_filter_min": -5, "lag_filter_max": 10, "standardised_signals": True, "checkbox_absolute_corr": True},
    {"checkbox_average_windows": True, "checkbox_eb": False, "checkbox_fr": True},
    {"checkbox_windowed_xcorr": False, "checkbox_absolute_corr_sxc": True, "max_lag_sxc": 40},
    {"checkbox_windowed_xcorr": False, "checkbox_eb": False, "checkbox_fr": True, "standardised_signals": True},
]
VAR_FOR_PARAM = {
    "checkbox_windowed_xcorr": "val_checkbox_windowed_xcorr", "window_size": "val_window_size",
    "step_size": "val_step_size", "max_lag": "val_max_lag", "max_lag_sxc": "val_max_lag_sxc",
    "standardised_signals": "val_checkbox_standardise", "checkbox_absolute_corr": "val_checkbox_absolute_corr",
    "checkbox_absolute_corr_sxc": "val_checkbox_absolute_corr_sxc",
    "checkbox_average_windows": "val_checkbox_average_windows", "sigmoid_correlations": "val_checkbox_show_sigmoid_correlations",
    "checkbox_eb": "val_checkbox_eb", "checkbox_fr": "val_checkbox_fr", "use_lag_filter": "val_checkbox_lag_filter",
    "lag_filter_min": "val_lag_filter_min", "lag_filter_max": "val_lag_filter_max",
}
DEFAULTS = {
    "checkbox_windowed_xcorr": True, "window_size": 150, "step_size": 75, "max_lag": 30, "max_lag_sxc": 100,
    "standardised_signals": False, "checkbox_absolute_corr": False, "checkbox_absolute_corr_sxc": False,
    "checkbox_average_windows": False, "sigmoid_correlations": False, "checkbox_eb": True, "checkbox_fr": False,
    "use_lag_filter": False, "lag_filter_min": -30, "lag_filter_max": 30,
}


@pytest.fixture
def dyad_files(tmp_path):
    rng = np.random.default_rng(0)
    coupled = 800 + 50 * np.convolve(rng.normal(size=1000), np.ones(4) / 2, mode="same")
    paths = []
    for name in ("P1.xlsx", "P2.xlsx"):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = SHEET
        sheet.append(["IBI"])
        for value in coupled + rng.normal(0, 5, 1000):
            sheet.append([float(value)])
        paths.append(tmp_path / name)
        workbook.save(paths[-1])
    return paths


@pytest.fixture
def gui(fake_state, dyad_files, monkeypatch):
    """Returns a function that loads the dyad through the GUI's code path with the given settings."""
    def load(settings):
        for param, value in {**DEFAULTS, **settings}.items():
            getattr(fake_state, VAR_FOR_PARAM[param]).set(value)
        fake_state.val_CORRELATION_SETTINGS_VALID.set(True)
        fake_state.val_CORRELATION_SETTINGS_VALID_SXC.set(True)
        fake_state.val_selected_dyad_dir.set(str(dyad_files[0].parent))
        fake_state.val_selected_file_a.set(str(dyad_files[0]))
        fake_state.val_selected_file_b.set(str(dyad_files[1]))
        fake_state.val_selected_sheet.set(SHEET)
        fake_state.val_selected_column.set("IBI")
        fake_state.val_checkbox_data_has_headers.set(True)
        fake_state.val_batch_input_folder.set("")
        fake_state.val_batch_output_folder.set("")
        columns = [xlsx.get_columns(xlsx.read_xlsx(path), SHEET) for path in dyad_files]
        monkeypatch.setitem(state.dat_workbook_data, "columns_a", columns[0])
        monkeypatch.setitem(state.dat_workbook_data, "columns_b", columns[1])
        for key in ("raw_signal_a", "raw_signal_b", "signal_a", "signal_b", "signal_a_std", "signal_b_std"):
            monkeypatch.setitem(state.dat_physiological_data, key, [])
        monkeypatch.setitem(state.dat_correlation_data, "wxcorr", [])
        monkeypatch.setitem(state.dat_correlation_data, "sxcorr", [])
        monkeypatch.setitem(state.dat_correlation_data, "dfa_signals", None)
        monkeypatch.setitem(state.dat_correlation_data, "dfa_windows", None)
        monkeypatch.setitem(state.dat_correlation_data, "stationarity_windows", None)
        monkeypatch.setitem(state.dat_correlation_data, "stationarity_signal", None)
        monkeypatch.setattr(corr_plot, "_computed_wx_settings", None)
        monkeypatch.setattr(corr_plot, "_computed_sx_settings", None)
        monkeypatch.setattr(callbacks.validation, "check_all_settings", lambda: None)
        callbacks.preprocess_data()
        assert fake_state.val_INPUT_DATA_VALID.get()
        corr_plot.update_corr()
    return load


def _batch_params():
    return {**callbacks._analysis_params(), "has_headers": True}


def _sheets(path):
    return {
        sheet.title: [[cell for cell in row] for row in sheet.iter_rows(values_only=True)]
        for sheet in openpyxl.load_workbook(path).worksheets
    }


@pytest.mark.parametrize("settings", SETTINGS)
def test_gui_and_batch_settings_are_the_same(gui, settings):
    gui(settings)
    assert analysis.AnalysisConfig.from_params(_batch_params()) == state.analysis_config()


@pytest.mark.parametrize("settings", SETTINGS)
def test_gui_and_batch_give_identical_results(gui, dyad_files, settings):
    gui(settings)
    batch = batch_processing._process_dyad(*dyad_files, None, _batch_params(), export=False)
    if state.val_checkbox_windowed_xcorr.get():
        assert len(batch) == len(state.dat_correlation_data["wxcorr"]) > 0
        for from_batch, from_gui in zip(batch, state.dat_correlation_data["wxcorr"]):
            assert from_batch.keys() == from_gui.keys()
            for key in from_batch:
                assert np.array_equal(from_batch[key], from_gui[key])
    else:
        assert np.array_equal(batch["corr"], state.dat_correlation_data["sxcorr"]["corr"])
        assert np.array_equal(batch["lags"], state.dat_correlation_data["sxcorr"]["lags"])


@pytest.mark.parametrize("settings", FILE_SETTINGS)
def test_gui_and_batch_write_identical_files(gui, dyad_files, tmp_path, settings):
    gui(settings)
    state.val_sampling_rate.set(2.5)       # as if entered; it is used for fixed-rate data only
    windowed = state.val_checkbox_windowed_xcorr.get()
    gui_file = tmp_path / "gui.xlsx"
    (callbacks._export_wxcorr_data if windowed else callbacks._export_sxcorr_data)(str(gui_file))

    output_dir = tmp_path / "out"
    output_dir.mkdir()
    dyad_dir = str(dyad_files[0].parent)
    batch_processing._process_dyad(*dyad_files, str(output_dir), _batch_params(), export=True, dyad_dir=dyad_dir)
    name = f"BioSync_{'wcc' if windowed else 'scc'}_{dyad_files[0].parent.name}.xlsx"

    assert _sheets(gui_file) == _sheets(output_dir / name)
    metadata = read_metadata(gui_file)
    kpss = [value for key, value in metadata.items() if key.startswith('kpss_')]
    assert len(kpss) == 2 and all(isinstance(value, float) for value in kpss)
    assert (metadata['sheet'], metadata['column'], metadata['file_a']) == (SHEET, "IBI", dyad_files[0].name)
    assert metadata['sampling_rate_hz'] == (5 if settings.get('checkbox_eb', True) else 2.5)


def _windows(n):
    return [dict(EXPORT_WINDOW, start_idx=75 * i, center_idx=75 * i + 75) for i in range(n)]


def _export(path, wxcorr=None, **overrides):
    export.export_wxcorr_data(str(path), export_params(wxcorr=wxcorr or _windows(2), **overrides))


def _config(**overrides):
    return dataclasses.replace(export_params()['config'], **overrides)


def test_windowed_file_is_a_set_of_tables(tmp_path):
    _export(tmp_path / "f.xlsx")
    workbook = openpyxl.load_workbook(tmp_path / "f.xlsx")
    assert workbook.sheetnames == ["metadata", "windows", "correlations", "signals", "dfa_per_lag"]
    assert read_table(tmp_path / "f.xlsx", "windows") == (
        ['window', 'start_index', 'center_index', 'r_max', 'tau_max', 'avg_z_transformed_corr',
         'var_z_transformed_corr', 'kpss_p_a', 'kpss_p_b'],
        [[1, 0, 75, 0.5, -1, 0.25, 0.75, None, None], [2, 75, 150, 0.5, -1, 0.25, 0.75, None, None]],
    )
    assert read_table(tmp_path / "f.xlsx", "signals") == (['sample', 'signal_a', 'signal_b'], [[0, 1.5, 3.5], [1, 2.5, 4.5]])


def test_metadata_has_typed_values_and_empty_cells_with_a_reason(tmp_path):
    _export(tmp_path / "f.xlsx")
    columns, rows = read_table(tmp_path / "f.xlsx", "metadata")
    assert columns == ['name', 'value', 'note']
    assert [(name, value) for name, value, _ in rows[:18]] == [
        ('analysis', 'windowed cross-correlation'), ('dyad_folder', 'dyad'), ('file_a', 'a.xlsx'), ('file_b', 'b.xlsx'),
        ('sheet', 'IBI'), ('column', 'ms'), ('data_type', 'event-based'), ('sampling_rate_hz', 5),
        ('standardised', False), ('window_size_samples', 150), ('step_size_samples', 75), ('max_lag_samples', 1),
        ('absolute_correlations', False), ('average_windows', False), ('lag_filter', False),
        ('lag_filter_min_samples', None), ('lag_filter_max_samples', None), ('windows', 2),
    ]
    assert read_notes(tmp_path / "f.xlsx")['lag_filter_min_samples'] == "lag filter not used"
    assert all(value != '-' and value not in ("True", "False", "nan") for _, value, _ in rows)


def test_lag_filter_gives_its_range_and_the_lag_labels(tmp_path):
    _export(tmp_path / "f.xlsx", _windows(1), config=_config(use_lag_filter=True, lag_filter_min=7, lag_filter_max=5))
    metadata = read_metadata(tmp_path / "f.xlsx")
    assert (metadata['lag_filter'], metadata['lag_filter_min_samples'], metadata['lag_filter_max_samples']) == (True, 5, 7)
    assert read_table(tmp_path / "f.xlsx", "correlations")[0] == ['window start index / lag', 5, 6, 7]


@pytest.mark.parametrize("signal_type, rate, value, note", [
    ('event-based', 0, 5, "intervals resampled to this rate"),
    ('fixed-rate', 2.5, 2.5, "from the sampling rate field of the Input Data tab"),
    ('fixed-rate', 0, None, "not known: enter it on the Input Data tab to have it here"),
])
def test_sampling_rate(tmp_path, signal_type, rate, value, note):
    _export(tmp_path / "f.xlsx", config=_config(signal_type=signal_type), sampling_rate=rate)
    assert read_metadata(tmp_path / "f.xlsx")['sampling_rate_hz'] == value
    assert read_notes(tmp_path / "f.xlsx")['sampling_rate_hz'] == note


def test_standardised_signals_are_the_ones_correlated(tmp_path):
    _export(tmp_path / "f.xlsx", config=_config(standardised=True))
    assert read_table(tmp_path / "f.xlsx", "signals")[1] == [[0, -1.0, -1.0], [1, 1.0, 1.0]]
    assert read_metadata(tmp_path / "f.xlsx")['standardised'] is True


def test_correlation_sheet_has_numbers_and_empty_cells_for_flat_windows(tmp_path):
    windows = _windows(2)
    windows[1].update(correlations=[np.nan] * 3, r_max=np.nan, tau_max=np.nan)
    _export(tmp_path / "f.xlsx", windows)
    assert _sheets(tmp_path / "f.xlsx")["correlations"] == [
        ['window start index / lag', -1, 0, 1],
        [0, 0.5, -0.25, 0.125],
        [75, None, None, None],
    ]
    assert read_column(tmp_path / "f.xlsx", "windows", "r_max") == [0.5, None]


def test_many_windows_fit(tmp_path, monkeypatch):
    """Earlier, each window had two columns on the first sheet, which ran out with long recordings."""
    monkeypatch.setattr(xlsx, "MAX_COLUMNS", 50)
    _export(tmp_path / "f.xlsx", _windows(100))
    assert len(read_table(tmp_path / "f.xlsx", "windows")[1]) == len(read_table(tmp_path / "f.xlsx", "correlations")[1]) == 100


def test_standard_file_is_a_set_of_tables(tmp_path):
    path = tmp_path / "f.xlsx"
    export.export_sxcorr_data(str(path), export_params(windowed=False))
    assert openpyxl.load_workbook(path).sheetnames == ["metadata", "correlations", "signals"]
    assert read_table(path, "correlations") == (['lag', 'correlation'], [[-1, 0.1], [0, 0.5], [1, 0.2]])
    metadata = read_metadata(path)
    assert (metadata['analysis'], metadata['max_lag_samples'], metadata['absolute_correlations']) == (
        'standard cross-correlation', 1, False)
    assert 'window_size_samples' not in metadata


@pytest.mark.parametrize("value, cell", [
    (np.nan, None), (np.inf, None), (None, None), (True, True), (np.True_, True), (False, False), ("-", "-"),
    (np.float64(0.5), 0.5), (np.int64(2), 2),
])
def test_typed_cells(value, cell):
    assert xlsx.typed_cell(value) == cell and type(xlsx.typed_cell(value)) is type(cell)


def test_failed_export_shows_an_error(gui, monkeypatch):
    gui({})
    errors = []
    monkeypatch.setattr(callbacks.filedialog, "asksaveasfilename", lambda **kwargs: "/nonexistent/folder/f.xlsx")
    monkeypatch.setattr(callbacks.messagebox, "showerror", lambda title, text: errors.append(title))
    callbacks.export_data()
    assert errors == ["Export failed"]


SECONDS_LABELS = (
    'label_window_size_seconds', 'label_step_size_seconds', 'label_max_lag_seconds', 'label_max_lag_sxc_seconds',
    'label_lag_filter_min_seconds', 'label_lag_filter_max_seconds', 'label_block_length_seconds',
)


@pytest.fixture
def labels(gui, monkeypatch):
    widgets = {key: FakeWidget() for key in SECONDS_LABELS}
    monkeypatch.setattr(gui_updates, "_w", widgets)
    return widgets


def test_event_based_parameters_show_seconds(gui, labels, fake_state):
    gui({"use_lag_filter": True, "lag_filter_min": -5, "lag_filter_max": 12})
    fake_state.val_block_length.set(300)
    gui_updates.update_parameter_labels()
    assert {key: widget.text for key, widget in labels.items()} == {
        'label_window_size_seconds': '30 s', 'label_step_size_seconds': '15 s', 'label_max_lag_seconds': '6 s',
        'label_max_lag_sxc_seconds': '20 s', 'label_lag_filter_min_seconds': '-1 s', 'label_lag_filter_max_seconds': '2.4 s',
        'label_block_length_seconds': '60 s',
    }


def test_fixed_rate_parameters_have_no_seconds_because_the_rate_is_unknown(gui, labels, fake_state):
    gui({"checkbox_eb": False, "checkbox_fr": True, "use_lag_filter": True})
    fake_state.val_block_length.set(300)
    gui_updates.update_parameter_labels()
    assert {widget.text for widget in labels.values()} == {''}


@pytest.mark.parametrize("ticked", [True, False])
def test_lag_filter_rows_follow_the_checkbox(gui, monkeypatch, ticked):
    rows = [FakeWidget() for _ in range(8)]
    error = FakeWidget()
    error.visible = True
    monkeypatch.setattr(gui_updates, "_w", {'lag_filter_rows': rows, 'error_label_lag_filter': error})
    gui({"use_lag_filter": ticked})
    gui_updates.update_lag_filter_visibility()
    assert all(widget.visible == ticked for widget in rows)
    assert error.visible == ticked


@pytest.mark.parametrize("retina, title_size", [(True, 12), (False, 16)])
def test_plot_text_is_readable(retina, title_size):
    plot.plot_init(is_retina=retina)
    assert matplotlib.rcParams['axes.titlesize'] == title_size
    assert matplotlib.rcParams['xtick.labelsize'] >= 10


def test_long_preview_title_stays_inside_the_figure():
    plot.plot_init(is_retina=True)
    title = "Data in column 'IBI_ms' of sheet 'IBI Series' of 'a_very_long_file_name.xlsx' " * 3
    fig = plot.plot_preprocessed_signals([1, 2, 3], [1, 2, 3], {'a': title, 'b': title})
    fig.set_size_inches(10.5, 8.6)
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    for ax in fig.axes:
        extent = ax.title.get_window_extent(canvas.get_renderer())
        assert extent.x0 >= 0 and extent.x1 <= fig.bbox.width


@pytest.mark.parametrize("retina", [True, False])
def test_batch_figure_has_room_for_its_text(retina, tmp_path, recwarn):
    plot.plot_init(is_retina=retina)
    signal = np.convolve(np.random.default_rng(0).normal(size=600), np.ones(9) / 9, mode="same")
    windows = analysis.windowed_cross_correlation(signal, np.roll(signal, 3), 150, 75, 30)
    fig = plot.plot_windowed_cross_correlation(windows, 150, 30, 75, signal, signal)
    plot.save_figure_to_png(fig, tmp_path / "f.png")
    assert not [w for w in recwarn.list if "constrained_layout" in str(w.message)]


def test_group_average_is_a_set_of_tables_and_says_how_many_windows_it_covers(tmp_path):
    from helpers import batch_params
    path = tmp_path / "f.xlsx"
    export.export_avg_wxcorr_data(str(path), _windows(20), 3, batch_params("", "", max_lag=1, use_lag_filter=False),
                                  window_counts=[105, 20, 98])
    assert openpyxl.load_workbook(path).sheetnames == ["metadata", "windows", "correlations"]
    metadata = read_metadata(path)
    assert (metadata['analysis'], metadata['dyads_averaged']) == ('windowed cross-correlation, group average', 3)
    assert (metadata['windows_averaged'], metadata['windows_per_dyad_min'], metadata['windows_per_dyad_max']) == (20, 20, 105)
    assert "shortest dyad" in read_notes(path)['windows_averaged']
    assert read_table(path, "correlations")[0] == ['window start index / lag', -1, 0, 1]
    assert 'kpss_p_a' not in read_table(path, "windows")[0]


def test_batch_group_average_reports_the_window_counts(tmp_path):
    import batch_processing
    from helpers import batch_params, write_person
    rng = np.random.default_rng(0)
    for name, n_beats in (("long", 1000), ("short", 400)):
        (tmp_path / "in" / name).mkdir(parents=True)
        ibi = 800 + 50 * np.convolve(rng.normal(size=n_beats), np.ones(4) / 2, mode="same")
        for person in ("P1", "P2"):
            write_person(tmp_path / "in" / name / f"{person}.xlsx", {"Coupled": ibi + rng.normal(0, 5, n_beats)})
    (tmp_path / "out").mkdir()
    batch_processing.batch_process(batch_params(tmp_path / "in", tmp_path / "out"))

    def windows(name):
        return openpyxl.load_workbook(tmp_path / "out" / name)["correlations"].max_row - 1

    short, long = windows("BioSync_wcc_short.xlsx"), windows("BioSync_wcc_long.xlsx")
    metadata = read_metadata(tmp_path / "out" / "BioSync_wcc_group-average.xlsx")
    assert short < long
    assert metadata['windows_averaged'] == windows("BioSync_wcc_group-average.xlsx") == short
    assert (metadata['windows_per_dyad_min'], metadata['windows_per_dyad_max']) == (short, long)
