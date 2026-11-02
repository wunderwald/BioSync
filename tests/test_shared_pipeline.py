"""
The GUI, batch and random pairs must give identical results, and existing pipelines must keep working on exports.
"""
from pathlib import Path

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
import layout
import plot
import state
import xlsx

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
        fake_state.val_selected_column_a.set("IBI")
        fake_state.val_selected_column_b.set("IBI")
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
        monkeypatch.setitem(state.dat_correlation_data, "dfa_alpha_sxcorr", None)
        monkeypatch.setitem(state.dat_correlation_data, "dfa_alpha_window_averages_wxcorr", None)
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


@pytest.mark.parametrize("settings", SETTINGS)
def test_gui_and_batch_write_identical_files(gui, dyad_files, tmp_path, settings):
    gui(settings)
    windowed = state.val_checkbox_windowed_xcorr.get()
    gui_file = tmp_path / "gui.xlsx"
    (callbacks._export_wxcorr_data if windowed else callbacks._export_sxcorr_data)(str(gui_file))

    output_dir = tmp_path / "out"
    output_dir.mkdir()
    dyad_dir = str(dyad_files[0].parent)
    batch_processing._process_dyad(*dyad_files, str(output_dir), _batch_params(), export=True, dyad_dir=dyad_dir)
    name = f"wx_{dyad_files[0].parent.name}_wxcorr.xlsx" if windowed else f"{dyad_files[0].parent.name}_sxcorr.xlsx"

    assert _sheets(gui_file) == _sheets(output_dir / name)


def _windows(n):
    return [
        {
            'start_idx': i, 'center_idx': i + 75, 'correlations': [0.5, -0.25, 0.125], 'r_max': 0.5, 'tau_max': -1,
            'avg_z_transformed_corr': 0.25, 'var_z_transformed_corr': 0.75,
        }
        for i in range(n)
    ]


def _export(path, wxcorr, **overrides):
    export.export_wxcorr_data(str(path), {
        'selected_dyad_dir': 'dyad', 'input_file_a': 'a.xlsx', 'input_file_b': 'b.xlsx', 'checkbox_fr': False,
        'is_standardised': False, 'window_size': 150, 'max_lag': 1, 'step_size': 75, 'checkbox_absolute_corr': False,
        'checkbox_average_windows': False, 'checkbox_lag_filter': False, 'lag_filter_min': -1, 'lag_filter_max': 1,
        'signal_a': np.array([1.5, 2.5]), 'signal_a_std': [], 'signal_b': np.array([3.5, 4.5]), 'signal_b_std': [],
        'wxcorr': wxcorr, **overrides,
    })


def test_first_sheet_keeps_the_layout_pipelines_rely_on(tmp_path):
    _export(tmp_path / "f.xlsx", _windows(2))
    workbook = openpyxl.load_workbook(tmp_path / "f.xlsx")
    assert workbook.sheetnames[0] == workbook.active.title == "xcorr data"
    rows = list(workbook.active.iter_rows(values_only=True))
    assert [(row[0], row[1]) for row in rows[:14]] == [
        ('xcorr type', 'windowed cross-correlation'), ('Input dyad directory', 'dyad'), ('Input file A', 'a.xlsx'),
        ('Input file B', 'b.xlsx'), ('Data type', 'event-based (resampled to 5hz)'), ('Standardised (z-score)', 'False'),
        ('Window size', 150), ('Max lag', 1), ('Step size', 75), ('Absolute correlation values', 'False'),
        ('Per-window averages', 'False'), ('Lag filter used', 'False'), ('Lag filter minimum', '-'), ('Lag filter maximum', '-'),
    ]
    assert rows[0][2] is None
    assert list(rows[0][3:]) == [
        'signal_a', 'signal_b', 'window start index', 'peak correlation (r_max)', 'lag of peak correlation (tau_max)',
        'avg_z_transformed_corr', 'var_z_transformed_corr', 'w_0_correlations', 'w_0_meta', 'w_1_correlations',
        'w_1_meta', 'dfa_lags', 'dfa_alpha',
    ]
    assert list(rows[1][3:]) == [
        1.5, 3.5, 0, 0.5, -1, 0.25, 0.75, 0.5, 'start_idx=0', 0.5, 'start_idx=1', '-', '-',
    ]


def test_correlation_sheet_has_numbers_and_lag_labels(tmp_path):
    _export(tmp_path / "f.xlsx", [_windows(1)[0], {**_windows(1)[0], 'start_idx': 75, 'correlations': [np.nan] * 3}])
    rows = _sheets(tmp_path / "f.xlsx")["correlations"]
    assert rows == [
        ['window start index / lag', -1, 0, 1],
        [0, 0.5, -0.25, 0.125],
        [75, 'nan', 'nan', 'nan'],
    ]


def test_correlation_sheet_labels_follow_the_lag_filter(tmp_path):
    _export(tmp_path / "f.xlsx", _windows(1), checkbox_lag_filter=True, lag_filter_min=5, lag_filter_max=7)
    assert _sheets(tmp_path / "f.xlsx")["correlations"][0][1:] == [5, 6, 7]


def test_grand_average_has_the_correlation_sheet(tmp_path):
    averaged = [{**window, 'tau_max': 0} for window in _windows(1)]
    export.export_avg_wxcorr_data(str(tmp_path / "f.xlsx"), averaged, 2, {'max_lag': 1, 'use_lag_filter': False})
    sheets = _sheets(tmp_path / "f.xlsx")
    assert list(sheets) == ["Grand Avg WXCorr", "correlations"]
    assert sheets["correlations"][0] == ['window start index / lag', -1, 0, 1]


def test_too_many_windows_for_the_first_sheet_still_export(tmp_path, monkeypatch):
    monkeypatch.setattr(xlsx, "MAX_COLUMNS", 50)
    windows = _windows(25)
    _export(tmp_path / "f.xlsx", windows)
    sheets = _sheets(tmp_path / "f.xlsx")
    assert 'w_0_correlations' not in sheets["xcorr data"][0]
    assert len(sheets["correlations"]) == len(windows) + 1
    metadata = {row[0]: row[1] for row in sheets["xcorr data"]}
    assert "left out" in metadata['Per-window columns']


def test_most_windows_that_fit_keep_their_columns(monkeypatch):
    monkeypatch.setattr(xlsx, "MAX_COLUMNS", 50)

    def add(n_windows):
        vectors, metadata = {name: [] for name in "abcdefg"}, {}
        export._add_per_window_columns(vectors, metadata, _windows(n_windows), n_columns_after=2)
        return vectors, metadata

    # 3 columns of metadata, 7 summary columns and 2 columns after the windows leave 38 columns
    vectors, metadata = add(19)
    assert metadata == {} and 3 + len(vectors) + 2 == 50
    vectors, metadata = add(20)
    assert 'Per-window columns' in metadata and len(vectors) == 7


def test_flat_window_value_is_text_excel_can_open(tmp_path):
    assert xlsx._cell_value(np.nan) == "nan"
    assert xlsx._cell_value(np.inf) == "inf"
    assert xlsx._cell_value(True) == "True" and xlsx._cell_value(np.True_) == "True"
    assert xlsx._cell_value(None) == "None" and xlsx._cell_value("-") == "-"
    assert xlsx._cell_value(np.float64(0.5)) == 0.5 and type(xlsx._cell_value(np.float64(0.5))) is float
    assert type(xlsx._cell_value(np.int64(2))) is int


def test_failed_export_shows_an_error(gui, monkeypatch):
    gui({})
    errors = []
    monkeypatch.setattr(callbacks.filedialog, "asksaveasfilename", lambda **kwargs: "/nonexistent/folder/f.xlsx")
    monkeypatch.setattr(callbacks.messagebox, "showerror", lambda title, text: errors.append(title))
    callbacks.export_data()
    assert errors == ["Export failed"]


class FakeWidget:
    def configure(self, text):
        self.text = text


SECONDS_LABELS = (
    'label_window_size_seconds', 'label_step_size_seconds', 'label_max_lag_seconds', 'label_max_lag_sxc_seconds',
    'label_lag_filter_min_seconds', 'label_lag_filter_max_seconds',
)


@pytest.fixture
def labels(gui, monkeypatch):
    widgets = {key: FakeWidget() for key in SECONDS_LABELS}
    monkeypatch.setattr(gui_updates, "_w", widgets)
    return widgets


def test_event_based_parameters_show_seconds(gui, labels):
    gui({"use_lag_filter": True, "lag_filter_min": -5, "lag_filter_max": 12})
    gui_updates.update_parameter_labels()
    assert {key: widget.text for key, widget in labels.items()} == {
        'label_window_size_seconds': '30 s', 'label_step_size_seconds': '15 s', 'label_max_lag_seconds': '6 s',
        'label_max_lag_sxc_seconds': '20 s', 'label_lag_filter_min_seconds': '-1 s', 'label_lag_filter_max_seconds': '2.4 s',
    }


def test_fixed_rate_parameters_have_no_seconds_because_the_rate_is_unknown(gui, labels):
    gui({"checkbox_eb": False, "checkbox_fr": True, "use_lag_filter": True})
    gui_updates.update_parameter_labels()
    assert {widget.text for widget in labels.values()} == {''}


class FakeRowWidget:
    def __init__(self):
        self.visible = False

    def grid(self):
        self.visible = True

    def grid_remove(self):
        self.visible = False

    def grid_forget(self):
        self.visible = False


@pytest.mark.parametrize("ticked", [True, False])
def test_lag_filter_rows_follow_the_checkbox(gui, monkeypatch, ticked):
    rows = [FakeRowWidget() for _ in range(8)]
    error = FakeRowWidget()
    error.visible = True
    monkeypatch.setattr(gui_updates, "_w", {'lag_filter_rows': rows, 'error_label_lag_filter': error})
    gui({"use_lag_filter": ticked})
    gui_updates.update_lag_filter_visibility()
    assert all(widget.visible == ticked for widget in rows)
    assert error.visible == ticked


def test_dropdowns_open_when_clicked_anywhere():
    # A CTkComboBox only opens from its small arrow. Its text is an editable field, and typing
    # there changes the selection without recomputing anything.
    source = Path(layout.__file__).read_text(encoding="utf-8")
    assert "CTkComboBox" not in source and source.count("CTkOptionMenu(") == 3


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
