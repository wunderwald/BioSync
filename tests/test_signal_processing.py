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
