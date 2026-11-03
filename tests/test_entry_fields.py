"""
Typing in the settings fields: the lag filter survives max lag edits, and no character can crash a field.
"""
import pytest

import callbacks
import validation


@pytest.mark.parametrize("wanted, max_lag, expected", [
    (None, 30, (-30, 30)),            # never typed: the full range
    (None, 50, (-50, 50)),
    ((-5, 10), 30, (-5, 10)),         # fits: unchanged
    ((-5, 10), 8, (-5, 8)),           # too wide on one side: narrowed there
    ((-5, 10), 3, (-3, 3)),
    ((10, 20), 15, (10, 15)),
    ((10, 20), 5, (-5, 5)),           # nothing left: the full range
    ((-5, 10), 0, (0, 0)),            # max lag field empty while typing
])
def test_filter_is_only_narrowed_as_far_as_the_max_lag_needs(wanted, max_lag, expected):
    assert callbacks.lag_filter_for_max_lag(wanted, max_lag) == expected


@pytest.fixture
def fields(fake_state, monkeypatch):
    """The real traces between the fields, as tk would call them."""
    monkeypatch.setattr(callbacks, "_wanted_lag_filter", None)
    monkeypatch.setattr(callbacks.state, "PARAMS_CHANGED", lambda debounce=False: None)
    triggers = {
        "val_lag_filter_min_input": callbacks.on_min_lag_input_change,
        "val_lag_filter_max_input": callbacks.on_max_lag_filter_input_change,
        "val_max_lag": callbacks.on_max_lag_change_update_filter,
        "val_max_lag_input": callbacks.on_max_lag_input_change,
    }
    for name, handler in triggers.items():
        var = getattr(fake_state, name)

        def set_and_trigger(value, var=var, handler=handler):
            var.value = value
            handler(None, None, None)
        var.set = set_and_trigger
    for name, value in (("val_data_length", 1000), ("val_window_size", 150), ("val_step_size", 75), ("val_checkbox_lag_filter", True)):
        getattr(fake_state, name).value = value
    fake_state.val_max_lag_input.set("30")
    return fake_state


def _type(field, text):
    field.set("")
    for index in range(1, len(text) + 1):
        field.set(text[:index])


def _filter(fields):
    return fields.val_lag_filter_min.get(), fields.val_lag_filter_max.get()


def test_typing_a_larger_max_lag_keeps_the_filter(fields):
    _type(fields.val_lag_filter_min_input, "-5")
    _type(fields.val_lag_filter_max_input, "10")
    _type(fields.val_max_lag_input, "40")       # passes 4 on the way
    assert _filter(fields) == (-5, 10)
    assert (fields.val_lag_filter_min_input.get(), fields.val_lag_filter_max_input.get()) == ("-5", "10")


def test_a_narrower_max_lag_narrows_the_filter_and_a_wider_one_restores_it(fields):
    _type(fields.val_lag_filter_min_input, "-5")
    _type(fields.val_lag_filter_max_input, "10")
    _type(fields.val_max_lag_input, "8")
    assert _filter(fields) == (-5, 8)
    assert fields.val_lag_filter_max_input.get() == "8"
    _type(fields.val_max_lag_input, "30")
    assert _filter(fields) == (-5, 10)


def test_untouched_filter_follows_the_max_lag(fields):
    _type(fields.val_max_lag_input, "50")
    assert _filter(fields) == (-50, 50)
    _type(fields.val_max_lag_input, "20")
    assert _filter(fields) == (-20, 20)


def test_typing_a_new_filter_replaces_the_remembered_one(fields):
    _type(fields.val_lag_filter_max_input, "10")
    _type(fields.val_max_lag_input, "8")
    _type(fields.val_lag_filter_max_input, "6")
    _type(fields.val_max_lag_input, "30")
    assert _filter(fields)[1] == 6


@pytest.mark.parametrize("text, accepted", [("150", True), ("", True), ("²", False), ("1²", False), ("½", False), ("-1", False), ("1.5", False)])
def test_only_characters_int_can_read_are_accepted(text, accepted):
    assert validation.is_numeric_input(text) == accepted
    if accepted and text:
        int(text)


@pytest.mark.parametrize("windowed, kind, folder, expected", [
    (True, "data", "/study/ex1", "biosync_wxc_data_ex1"),
    (False, "data", "/study/ex1", "biosync_xc_data_ex1"),
    (True, "plot", "/study/ex1", "biosync_wxc_plot_ex1"),
    (False, "plot", "", "biosync_xc_plot"),
])
def test_export_names(fake_state, windowed, kind, folder, expected):
    fake_state.val_checkbox_windowed_xcorr.set(windowed)
    fake_state.val_selected_dyad_dir.set(folder)
    assert callbacks._export_file_name(kind) == expected


@pytest.mark.parametrize("export, kind", [(callbacks.export_data, "data"), (callbacks.export_plot, "plot")])
def test_save_dialog_suggests_the_name(fake_state, monkeypatch, export, kind):
    fake_state.val_checkbox_windowed_xcorr.set(False)
    fake_state.val_selected_dyad_dir.set("/study/ex1")
    monkeypatch.setattr(callbacks.corr_plot, "flush_update", lambda: None)
    monkeypatch.setitem(callbacks.state.dat_plot_data, "fig", object())
    suggested = []
    monkeypatch.setattr(callbacks.filedialog, "asksaveasfilename", lambda **kwargs: suggested.append(kwargs["initialfile"]) or "")
    export()
    assert suggested == [f"biosync_xc_{kind}_ex1"]


class FakeButton:
    def __init__(self, text, top):
        self.options = {'text': text, 'state': 'normal'}
        self.top = top

    def cget(self, name):
        return self.options[name]

    def configure(self, **options):
        self.options.update(options)

    def winfo_toplevel(self):
        return self.top


class FakeWindow:
    def __init__(self):
        self.cursor = ""

    def configure(self, cursor):
        self.cursor = cursor

    def update_idletasks(self):
        pass


@pytest.fixture
def export_buttons(fake_state, monkeypatch):
    import gui_updates
    window = FakeWindow()
    buttons = {'button_export_data': FakeButton('Export XLSX', window), 'button_export_plot': FakeButton('Export Plots', window)}
    monkeypatch.setattr(gui_updates, "_w", buttons)
    monkeypatch.setattr(gui_updates, "_export_button_texts", {})
    monkeypatch.setitem(callbacks._tabview, "tabview", window)
    fake_state.val_exporting.set('')
    fake_state.val_INPUT_DATA_VALID.set(True)
    fake_state.val_checkbox_windowed_xcorr.set(True)
    fake_state.val_CORRELATION_SETTINGS_VALID.set(True)
    original_set = fake_state.val_exporting.set

    def set_and_update(value):
        original_set(value)
        gui_updates.update_export_busy()
    fake_state.val_exporting.set = set_and_update
    fake_state.window, fake_state.buttons = window, buttons
    return fake_state


@pytest.mark.parametrize("kind, busy_button", [("data", "button_export_data"), ("plot", "button_export_plot")])
def test_window_shows_it_is_busy_while_exporting(export_buttons, kind, busy_button):
    seen = {}

    def write():
        seen['cursor'] = export_buttons.window.cursor
        seen['states'] = {key: button.cget('state') for key, button in export_buttons.buttons.items()}
        seen['text'] = export_buttons.buttons[busy_button].cget('text')

    callbacks._while_exporting(kind, write)
    assert seen == {'cursor': 'watch', 'states': {'button_export_data': 'disabled', 'button_export_plot': 'disabled'}, 'text': 'Exporting...'}
    assert export_buttons.window.cursor == ""
    assert {key: button.options for key, button in export_buttons.buttons.items()} == {
        'button_export_data': {'text': 'Export XLSX', 'state': 'normal'},
        'button_export_plot': {'text': 'Export Plots', 'state': 'normal'},
    }


def test_failed_export_also_ends_the_busy_state(export_buttons):
    def write():
        raise OSError("disk full")

    with pytest.raises(OSError):
        callbacks._while_exporting("data", write)
    assert export_buttons.window.cursor == "" and export_buttons.buttons['button_export_data'].cget('text') == 'Export XLSX'
