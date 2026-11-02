"""
Time alignment of event-based signals, which have the form [t_offset, ibi_1, ..., ibi_n, rest].
At 5 Hz one sample is 200 ms.
"""
import numpy as np
import pytest

from cross_correlation import standard_cross_correlation
from signal_processing import preprocess_dyad


@pytest.fixture
def ibi():
    noise = np.convolve(np.random.default_rng(0).normal(size=600), np.ones(4) / 2, mode="same")
    return list(800 + 50 * noise)


def _peak_lag(signal_a, signal_b):
    sxcorr = standard_cross_correlation(signal_a, signal_b, max_lag=10)
    return sxcorr["lags"][np.argmax(sxcorr["corr"])]


def _preprocess(signal_a, signal_b):
    return preprocess_dyad(signal_a, signal_b, signal_type="event-based")[:2]


@pytest.mark.parametrize("offset_a, offset_b, expected_lag", [
    (600, 1000, 2),     # A's first beat is 400 ms earlier: A leads by 2 samples
    (1000, 600, -2),
    (0, 1000, 5),
    (500, 500, 0),
])
def test_first_beat_offsets_appear_as_lag(ibi, offset_a, offset_b, expected_lag):
    signal_a, signal_b = _preprocess([offset_a, *ibi, 300], [offset_b, *ibi, 300])
    assert _peak_lag(signal_a, signal_b) == expected_lag


def test_equal_offsets_give_identical_signals(ibi):
    signal_a, signal_b = _preprocess([500, *ibi, 300], [500, *ibi, 300])
    assert np.array_equal(signal_a, signal_b)


def test_signals_only_cover_the_time_both_people_have_beats(ibi):
    signal_a, signal_b = _preprocess([0, *ibi, 300], [1000, *ibi[:300], 300])
    shared_ms = sum(ibi[:299])  # person B's beats span from 1000 ms to 1000 ms + these intervals
    assert len(signal_a) == len(signal_b) == pytest.approx(shared_ms / 200, abs=1)


def test_time_after_the_last_beat_is_not_part_of_the_signal(ibi):
    short_rest = _preprocess([500, *ibi, 46], [500, *ibi, 46])
    long_rest = _preprocess([500, *ibi, 900], [500, *ibi, 900])
    assert np.array_equal(short_rest[0], long_rest[0])


def test_recordings_that_do_not_overlap_are_rejected(ibi):
    with pytest.raises(ValueError, match="do not overlap"):
        _preprocess([0, *ibi[:5], 300], [100000, *ibi[:5], 300])


def _preprocess_removing_invalid(signal_a, signal_b, signal_type="event-based"):
    return preprocess_dyad(signal_a, signal_b, signal_type=signal_type, remove_invalid_samples=True)[:2]


def test_low_first_beat_offset_is_not_removed_as_an_invalid_interval(ibi):
    signal_a, signal_b = _preprocess_removing_invalid([50, *ibi, 300], [450, *ibi, 300])
    assert _peak_lag(signal_a, signal_b) == 2


def test_low_rest_value_does_not_change_the_result(ibi):
    short_rest = _preprocess_removing_invalid([500, *ibi, 46], [500, *ibi, 46])
    long_rest = _preprocess_removing_invalid([500, *ibi, 900], [500, *ibi, 900])
    assert np.array_equal(short_rest[0], long_rest[0])


def test_removing_a_missed_beat_keeps_later_beats_in_place(ibi):
    # a missed beat merges two intervals into one invalid interval, without changing when later beats happen
    missed_beat = [*ibi[:100], ibi[100] + ibi[101], *ibi[102:]]
    assert missed_beat[100] >= 1000

    signal_a, signal_b = _preprocess_removing_invalid([500, *missed_beat, 300], [500, *ibi, 300])

    assert _peak_lag(signal_a, signal_b) == 0
    after_the_gap = int((500 + sum(ibi[:103])) / 200)
    assert signal_a[after_the_gap:] == pytest.approx(signal_b[after_the_gap:], abs=1)   # the spline settles gradually


def test_invalid_values_are_ignored_only_when_asked(ibi):
    with_artefact = [*ibi[:100], 5000, *ibi[101:]]
    kept = _preprocess([500, *with_artefact, 300], [500, *ibi, 300])[0]
    removed = _preprocess_removing_invalid([500, *with_artefact, 300], [500, *ibi, 300])[0]
    assert kept.max() > 1000
    assert removed.max() < 1000


def test_too_few_valid_intervals_are_rejected(ibi):
    with pytest.raises(ValueError, match="fewer than two valid"):
        _preprocess_removing_invalid([500, 5000, 5000, 5000, 300], [500, *ibi, 300])


def test_negative_fixed_rate_samples_are_bridged_without_moving_later_samples():
    signal = np.sin(np.arange(200) / 5) + 2
    damaged = signal.copy()
    damaged[50] = -1
    signal_a, signal_b = _preprocess_removing_invalid(damaged, signal, signal_type="fixed-rate")
    assert len(signal_a) == len(signal)
    assert signal_a[50] == pytest.approx((signal[49] + signal[51]) / 2)
    assert np.array_equal(signal_a[51:], signal[51:])


def test_fixed_rate_signal_without_valid_samples_is_rejected():
    with pytest.raises(ValueError, match="no valid samples"):
        _preprocess_removing_invalid(np.full(50, -1.0), np.ones(50), signal_type="fixed-rate")
