"""
The sampling rate of fixed-rate data: found from a time column next to the data, or entered by hand. Parameters
are only shown in seconds when it is known.
"""
import pytest

import callbacks
import gui_updates
import validation
from helpers import FakeWidget
from signal_processing import EVENT_BASED_SAMPLING_RATE_HZ, detect_sampling_rate

EDA = [1.2, 1.3, 1.1, 1.4, 1.5]


# ---------------------------------------------------------------------------
# DETECTION
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("columns, expected", [
    ({'Interval Start Time': [0, 0.5, 1, 1.5, 2], 'Mean SC': EDA}, (2.0, 'Interval Start Time')),
    ({'Time (ms)': [0, 250, 500, 750, 1000], 'EDA': EDA}, (4.0, 'Time (ms)')),
    ({'time_ms': [10, 20, 30, 40, 50], 'EDA': EDA}, (100.0, 'time_ms')),
    ({'Time [msec]': [0, 1, 2, 3, 4], 'EDA': EDA}, (1000.0, 'Time [msec]')),
    ({'TIME': [0, 0.1, 0.2, 0.30000000000000004, 0.4], 'EDA': EDA}, (10.0, 'TIME')),       # rounded times
    ({'Time': [1.1, 1.2, 1.3, 1.4, 1.5], 'EDA': EDA}, (10.0, 'Time')),     # steps of 0.09999999999999987
    ({'Timestamp': [100.0, 100.25, 100.5, 100.75, 101.0], 'EDA': EDA}, (4.0, 'Timestamp')),  # any start
    ({'Time': [0, 0.5, 1, None, None], 'EDA': EDA}, (2.0, 'Time')),     # a shorter column is padded
    ({'Segment #': [1, 1, 1, 1, 1], 'Interval Start Time': [0, 2, 4, 6, 8], 'EDA': EDA}, (0.5, 'Interval Start Time')),
])
def test_rate_from_a_time_column(columns, expected):
    data_column = 'Mean SC' if 'Mean SC' in columns else 'EDA'
    assert detect_sampling_rate(columns, data_column) == expected


@pytest.mark.parametrize("columns", [
    {'EDA': EDA},                                               # no time column
    {'Column_1': [0, 0.5, 1, 1.5], 'Column_2': EDA},            # no headers, so no names
    {'Index': [0, 1, 2, 3, 4], 'EDA': EDA},                     # equal steps, but not called time
    {'Time': [0, 0.5, 1.5, 2, 3], 'EDA': EDA},                  # uneven steps, such as events
    {'Time': [2, 1.5, 1, 0.5, 0], 'EDA': EDA},                  # falling
    {'Time': [0, 0, 0, 0, 0], 'EDA': EDA},
    {'Time': [0, 0.5], 'EDA': EDA},                             # too short to tell
    {'Time': ['00:00', '00:01', '00:02'], 'EDA': EDA},          # text
    {'Time': [0, 0.5, None, 1.5, 2], 'EDA': EDA},               # a gap
    {'Time': [True, True, True], 'EDA': EDA},
])
def test_no_rate_is_guessed_without_a_clear_time_column(columns):
    assert detect_sampling_rate(columns, 'EDA') is None


def test_the_data_column_itself_is_never_the_time_column():
    columns = {'Time': [0, 0.5, 1, 1.5, 2]}
    assert detect_sampling_rate(columns, 'Time') is None


def test_ms_must_be_a_word_of_its_own():
    # 'Times' and 'msX' don't say milliseconds; 'Times' still contains 'time'
    assert detect_sampling_rate({'Times': [0, 0.5, 1, 1.5], 'EDA': EDA}, 'EDA') == (2.0, 'Times')


# ---------------------------------------------------------------------------
# THE FIELD
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, allowed", [("", True), ("2", True), ("2.", True), ("2.5", True), (".5", True),
                                           ("2.5.1", False), ("-2", False), ("2e3", False), ("²", False)])
def test_decimal_input(text, allowed):
    assert validation.is_decimal_input(text) is allowed


@pytest.mark.parametrize("text, value", [("", 0.0), (".", 0.0), ("2.", 2.0), ("31.25", 31.25)])
def test_parse_decimal(text, value):
    assert validation.parse_decimal(text) == value


@pytest.fixture
def loaded(fake_state, monkeypatch):
    monkeypatch.setitem(callbacks._rate_detection, 'data', None)
    monkeypatch.setitem(callbacks._rate_detection, 'found', None)
    monkeypatch.setitem(callbacks._rate_detection, 'files_disagree', False)
    monkeypatch.setitem(callbacks._rate_detection, 'filled', None)
    fake_state.val_sampling_rate_input.set('')
    fake_state.val_sampling_rate.set(0.0)
    fake_state.val_selected_sheet.set("Sheet")
    fake_state.val_checkbox_data_has_headers.set(True)

    def load(name, columns_a, columns_b=None):
        fake_state.val_selected_file_a.set(f"{name}/a.xlsx")
        fake_state.val_selected_file_b.set(f"{name}/b.xlsx")
        monkeypatch.setitem(fake_state.dat_workbook_data, "columns_a", columns_a)
        monkeypatch.setitem(fake_state.dat_workbook_data, "columns_b", columns_b or columns_a)
        callbacks.detect_sampling_rate_of_loaded_data('EDA')
        callbacks.on_sampling_rate_input_change(None, None, None)
    fake_state.load = load
    return fake_state


def _type(state, text):
    state.val_sampling_rate_input.set(text)
    callbacks.on_sampling_rate_input_change(None, None, None)


WITH_TIME = {'Time': [0, 0.5, 1, 1.5], 'EDA': EDA}
WITHOUT_TIME = {'EDA': EDA}


def test_found_rate_fills_the_field_and_says_where_it_is_from(loaded):
    loaded.load("dyad1", WITH_TIME)
    assert loaded.val_sampling_rate_input.get() == "2"
    assert loaded.val_sampling_rate.get() == 2.0
    assert loaded.val_sampling_rate_note.get() == "From column 'Time'."


def test_a_changed_rate_says_it_was_entered_and_what_the_column_says(loaded):
    loaded.load("dyad1", WITH_TIME)
    _type(loaded, "4")
    assert loaded.val_sampling_rate_note.get() == "Entered by hand. Column 'Time' says 2 Hz."


def test_without_a_time_column_the_rate_is_optional(loaded):
    loaded.load("dyad1", WITHOUT_TIME)
    assert loaded.val_sampling_rate_input.get() == ""
    assert loaded.val_sampling_rate.get() == 0
    assert loaded.val_sampling_rate_note.get().startswith("No time column found next to the data. Optional")
    _type(loaded, "2")
    assert loaded.val_sampling_rate_note.get() == "Entered by hand."


def test_entered_rate_stays_when_the_same_data_is_processed_again(loaded):
    loaded.load("dyad1", WITH_TIME)
    _type(loaded, "4")
    loaded.load("dyad1", WITH_TIME)      # e.g. after 'standardise' is ticked
    assert loaded.val_sampling_rate_input.get() == "4"


def test_entered_rate_stays_for_other_data_without_a_time_column(loaded):
    loaded.load("dyad1", WITHOUT_TIME)
    _type(loaded, "2")
    loaded.load("dyad2", WITHOUT_TIME)
    assert loaded.val_sampling_rate_input.get() == "2"


def test_a_found_rate_does_not_carry_over_to_data_without_a_time_column(loaded):
    loaded.load("dyad1", WITH_TIME)
    loaded.load("dyad2", WITHOUT_TIME)
    assert loaded.val_sampling_rate_input.get() == ""
    assert loaded.val_sampling_rate.get() == 0


def test_other_data_with_a_time_column_replaces_an_entered_rate(loaded):
    loaded.load("dyad1", WITHOUT_TIME)
    _type(loaded, "3")
    loaded.load("dyad2", WITH_TIME)
    assert loaded.val_sampling_rate_input.get() == "2"


def test_files_with_different_rates_give_no_rate(loaded):
    loaded.load("dyad1", WITH_TIME, {'Time': [0, 0.25, 0.5, 0.75], 'EDA': EDA})
    assert loaded.val_sampling_rate_input.get() == ""
    assert "two files give different rates" in loaded.val_sampling_rate_note.get()


def test_one_file_with_a_time_column_is_enough(loaded):
    loaded.load("dyad1", WITHOUT_TIME, WITH_TIME)
    assert loaded.val_sampling_rate.get() == 2.0


# ---------------------------------------------------------------------------
# SECONDS
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("event_based, rate, samples, text", [
    (True, 0, 150, "30 s"),             # event-based data is resampled at a fixed rate
    (True, 2, 150, "30 s"),             # whatever is in the fixed-rate field
    (False, 2, 150, "75 s"),
    (False, 0, 150, ""),                # unknown: no seconds at all
    (False, 3, 100, "33.3 s"),
    (False, 4, -5, "-1.25 s"),
    (False, 0.5, 600, "1200 s"),
    (False, 2, 1, "0.5 s"),
])
def test_seconds_need_a_known_rate(fake_state, event_based, rate, samples, text):
    fake_state.val_checkbox_eb.set(event_based)
    fake_state.val_sampling_rate.set(rate)
    assert gui_updates._seconds_text(samples) == text


@pytest.mark.parametrize("event_based, field_shown", [(True, False), (False, True)])
def test_the_field_is_only_for_fixed_rate_data(fake_state, monkeypatch, event_based, field_shown):
    widgets = {'label_select_data_type': FakeWidget(), 'frame_sampling_rate': FakeWidget()}
    monkeypatch.setattr(gui_updates, "_w", widgets)
    fake_state.val_checkbox_eb.set(event_based)
    gui_updates.update_sampling_rate_visibility()
    assert widgets['frame_sampling_rate'].visible is field_shown
    assert widgets['label_select_data_type'].visible is not field_shown


def test_event_based_rate_is_still_five_hz():
    assert EVENT_BASED_SAMPLING_RATE_HZ == 5
