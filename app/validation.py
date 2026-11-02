import re

import state


def is_numeric_input(text):
    return text == "" or text.isdigit()


def is_signed_numeric_input(text):
    """Also accepts a lone '-', which is what the field holds on the way to typing a negative number."""
    return re.fullmatch(r"-?\d*", text) is not None


def make_validator(app):
    """Register and return the numeric input validator against the CTk app instance."""
    return app.register(is_numeric_input)


def make_signed_validator(app):
    """Register and return the signed numeric input validator against the CTk app instance."""
    return app.register(is_signed_numeric_input)


# ----------------
# INPUT VALIDATION
# ----------------

def check_window_size():
    data_length = state.val_data_length.get()
    window_size_is_valid = state.val_window_size.get() >= 1 and state.val_window_size.get() <= data_length
    state.val_WINDOW_SIZE_VALID.set(window_size_is_valid)
    return window_size_is_valid


def check_step_size():
    window_size_is_valid = state.val_WINDOW_SIZE_VALID.get()
    window_size = state.val_window_size.get()
    step_size   = state.val_step_size.get()
    step_size_is_valid = step_size >= 1 and (not window_size_is_valid or step_size <= window_size)
    state.val_STEP_SIZE_VALID.set(step_size_is_valid)
    return step_size_is_valid


def check_max_lag():
    window_size_is_valid = state.val_WINDOW_SIZE_VALID.get()
    max_lag_is_valid = (
        state.val_max_lag.get() > 0 and
        (not window_size_is_valid or (state.val_max_lag.get() <= state.val_window_size.get() // 2))
    )
    state.val_MAX_LAG_VALID.set(max_lag_is_valid)
    return max_lag_is_valid


def check_lag_filter_in_range():
    lf_min  = state.val_lag_filter_min.get()
    lf_max  = state.val_lag_filter_max.get()
    max_lag = state.val_max_lag.get()
    return (
        (lf_min >= -max_lag) and (lf_min <= max_lag) and
        (lf_max >= -max_lag) and (lf_max <= max_lag)
    )


def check_lag_filter_sorted():
    return state.val_lag_filter_max.get() > state.val_lag_filter_min.get()


def check_lag_filter_exists():
    # the int vars keep their last value while a field is being edited, so check what was typed
    typed = (state.val_lag_filter_min_input.get(), state.val_lag_filter_max_input.get())
    return all(re.fullmatch(r"-?\d+", str(value)) for value in typed)


def check_lag_filter():
    # filter is valid when disabled
    if not state.val_checkbox_lag_filter.get():
        state.val_LAG_FILTER_VALID.set(True)
        return True
    lag_filter_is_valid = (
        check_lag_filter_exists() and
        check_lag_filter_sorted() and
        check_lag_filter_in_range()
    )
    state.val_LAG_FILTER_VALID.set(lag_filter_is_valid)
    return lag_filter_is_valid


def check_wx_correlation_settings():
    window_size_is_valid = check_window_size()
    step_size_is_valid   = check_step_size()
    max_lag_is_valid     = check_max_lag()
    lag_filter_is_valid  = check_lag_filter()
    correlation_settings_valid = (
        window_size_is_valid and step_size_is_valid and
        max_lag_is_valid and lag_filter_is_valid
    )
    state.val_CORRELATION_SETTINGS_VALID.set(correlation_settings_valid)
    return correlation_settings_valid


def check_max_lag_sxc():
    data_length = state.val_data_length.get()
    max_lag     = state.val_max_lag_sxc.get()
    max_lag_is_valid = max_lag >= 0 and max_lag < data_length
    state.val_MAX_LAG_VALID_SXC.set(max_lag_is_valid)
    return max_lag_is_valid


def check_sx_correlation_settings():
    max_lag_is_valid = check_max_lag_sxc()
    state.val_CORRELATION_SETTINGS_VALID_SXC.set(max_lag_is_valid)
    return max_lag_is_valid


def check_all_settings():
    """Settings depend on the data length, so this has to run whenever the data changes."""
    check_wx_correlation_settings()
    check_sx_correlation_settings()


def check_active_settings_valid():
    """Only the active correlation type is computed, so the other type's settings don't matter."""
    return (
        state.val_CORRELATION_SETTINGS_VALID.get()
        if state.val_checkbox_windowed_xcorr.get()
        else state.val_CORRELATION_SETTINGS_VALID_SXC.get()
    )


def check_export_ready():
    return state.val_INPUT_DATA_VALID.get() and check_active_settings_valid()
