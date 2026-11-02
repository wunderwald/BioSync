"""
The export buttons must only be enabled when the results for the active correlation type are current.
While settings are invalid the results are not recomputed, so exporting would write stale data.
"""
import pytest

import gui_updates
import validation


class FakeButton:
    def __init__(self):
        self.state = None

    def configure(self, state):
        self.state = state


@pytest.mark.parametrize("windowed, input_valid, wx_valid, sx_valid, expected", [
    (True,  True,  True,  True,  True),
    (True,  True,  False, True,  False),
    (True,  True,  True,  False, True),     # invalid standard settings don't affect windowed results
    (False, True,  True,  True,  True),
    (False, True,  True,  False, False),    # stale standard results, while windowed settings are valid
    (False, True,  False, True,  True),
    (True,  False, True,  True,  False),    # no data loaded
    (False, False, True,  True,  False),
])
def test_export_ready_depends_on_the_active_correlation_type(
    fake_state, windowed, input_valid, wx_valid, sx_valid, expected
):
    fake_state.val_checkbox_windowed_xcorr.set(windowed)
    fake_state.val_INPUT_DATA_VALID.set(input_valid)
    fake_state.val_CORRELATION_SETTINGS_VALID.set(wx_valid)
    fake_state.val_CORRELATION_SETTINGS_VALID_SXC.set(sx_valid)
    assert validation.check_export_ready() == expected


@pytest.mark.parametrize("sx_valid, expected_state", [(True, "normal"), (False, "disabled")])
def test_both_export_buttons_follow_export_ready(fake_state, monkeypatch, sx_valid, expected_state):
    fake_state.val_checkbox_windowed_xcorr.set(False)
    fake_state.val_INPUT_DATA_VALID.set(True)
    fake_state.val_CORRELATION_SETTINGS_VALID_SXC.set(sx_valid)
    buttons = {'button_export_data': FakeButton(), 'button_export_plot': FakeButton()}
    monkeypatch.setattr(gui_updates, "_w", buttons)

    gui_updates.update_active_state_export_button()

    assert {button.state for button in buttons.values()} == {expected_state}
