import numpy as np
import pytest

from cross_correlation import FISHER_Z_MAX_R, fisher_z, windowed_cross_correlation

Z_MAX = np.arctanh(FISHER_Z_MAX_R)


def test_ordinary_correlations_are_transformed_normally():
    assert fisher_z([0, 0.5, -0.5]) == pytest.approx([0, np.arctanh(0.5), -np.arctanh(0.5)])


@pytest.mark.parametrize("r, expected", [(1, Z_MAX), (-1, -Z_MAX), (1.2, Z_MAX), (-1.2, -Z_MAX)])
def test_extreme_correlations_keep_their_strength_and_sign(r, expected):
    assert fisher_z([r]) == pytest.approx([expected])


def test_stronger_correlations_never_get_a_smaller_z():
    correlations = [0, 0.5, 0.9, 0.99, 0.999, 1, 1.2]
    assert np.all(np.diff(fisher_z(correlations)) >= 0)


def test_nan_stays_nan():
    assert np.isnan(fisher_z([np.nan])).all()


def test_perfect_correlation_raises_the_window_average():
    signal = np.convolve(np.random.default_rng(0).normal(size=600), np.ones(9) / 9, mode="same")
    for window in windowed_cross_correlation(signal, signal, 150, 75, 2):
        assert window['correlations'][2] == pytest.approx(1)
        assert window['avg_z_transformed_corr'] == pytest.approx(np.mean(fisher_z(window['correlations'])))
        assert window['avg_z_transformed_corr'] > np.arctanh(window['correlations'][1])
