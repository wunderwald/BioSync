"""
The figure of a surrogate test shows what the result says: the real value against the surrogates, p, and for
shuffled blocks each dyad's own test.
"""
import io

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg

import plot
from plot import REAL_COLOR, format_p, plot_surrogate_result
from surrogates import BLOCKS, GREATER, REPAIRED, TWO_SIDED, WELCH, SurrogateResult

N_SURROGATES = 500


def _result(method=REPAIRED, n_dyads=4, real_value=0.6, p_values=None, **overrides):
    rng = np.random.default_rng(0)
    names = [f"dyad{i}" for i in range(n_dyads)]
    real_values = list(np.linspace(0.3, 0.9, n_dyads))
    fields = dict(
        method=method, measure='mean |r_max|', side=GREATER, seed=1, dyad_names=names, real_values=real_values,
        real_value=real_value, null_values=rng.normal(0.5, 0.02, N_SURROGATES), p_value=0.004,
        n_surrogates=N_SURROGATES, n_sets_possible=10 ** 6, failures=[],
    )
    if method == BLOCKS:
        fields.update(
            block_length=150,
            dyad_null_values=[rng.normal(0.5, 0.05, N_SURROGATES) for _ in names],
            dyad_p_values=p_values or [0.5, 0.01, 0.2, 0.001][:n_dyads] + [0.3] * max(0, n_dyads - 4),
        )
    if method == WELCH:
        fields.update(side=TWO_SIDED, measure='mean r', t_statistic=-2.5, null_values=rng.normal(0, 0.05, 100),
                      n_surrogates=100, n_sets_possible=None)
    fields.update(overrides)
    return SurrogateResult(**fields)


def _render(fig):
    """Draws the figure, which is where layout and text problems show up."""
    FigureCanvasAgg(fig).print_png(io.BytesIO())
    return fig


def _titles(fig):
    return [ax.get_title() for ax in fig.axes]


@pytest.mark.parametrize("p_value, text", [(0.0349, "p = 0.035"), (0.001, "p = 0.001"), (0.0004, "p < 0.001"),
                                           (float('nan'), "p = -")])
def test_format_p(p_value, text):
    assert format_p(p_value) == text


# ---------------------------------------------------------------------------
# GROUP TEST
# ---------------------------------------------------------------------------

def test_group_histogram_counts_every_surrogate_set():
    fig = _render(plot_surrogate_result(_result()))
    ax, = fig.axes
    assert sum(patch.get_height() for patch in ax.patches) == N_SURROGATES


def test_real_value_is_a_line_in_the_accent_color():
    ax, = _render(plot_surrogate_result(_result(real_value=0.6))).axes
    lines = [line for line in ax.get_lines() if line.get_color() == REAL_COLOR]
    assert len(lines) == 1 and lines[0].get_xdata()[0] == 0.6


def test_real_value_far_from_the_surrogates_is_still_shown():
    ax, = _render(plot_surrogate_result(_result(real_value=0.95))).axes
    low, high = ax.get_xlim()
    assert low < 0.5 and 0.95 < high


def test_title_names_method_measure_p_and_side():
    title, = _titles(_render(plot_surrogate_result(_result())))
    assert "re-paired people" in title and f"{N_SURROGATES} sets" in title
    assert "mean |r_max|: p = 0.004, one-sided (real higher)" in title


def test_surrogate_sets_without_a_value_are_left_out():
    null_values = np.r_[np.random.default_rng(0).normal(0.5, 0.02, N_SURROGATES - 2), [np.nan, np.nan]]
    ax, = _render(plot_surrogate_result(_result(null_values=null_values))).axes
    assert sum(patch.get_height() for patch in ax.patches) == N_SURROGATES - 2


# ---------------------------------------------------------------------------
# SHUFFLED BLOCKS: EACH DYAD
# ---------------------------------------------------------------------------

def _dyad_axes(fig):
    """The dyad panel and the axis with its p-values on the right."""
    group, dyads, p_axis = fig.axes
    return dyads, p_axis


def test_blocks_show_the_group_and_each_dyad():
    fig = _render(plot_surrogate_result(_result(BLOCKS)))
    assert len(fig.axes) == 3
    assert "blocks of 150 samples" in _titles(fig)[0]
    assert "2 of 4 with p < 0.05" in _titles(fig)[1]


def test_one_row_per_dyad_with_its_name_and_p_value_first_at_the_top():
    dyads, p_axis = _dyad_axes(_render(plot_surrogate_result(_result(BLOCKS))))
    names = [label.get_text() for label in dyads.get_yticklabels()]
    p_texts = [label.get_text() for label in p_axis.get_yticklabels()]
    assert list(dyads.get_yticks()) == [3, 2, 1, 0]
    assert names == ["dyad0", "dyad1", "dyad2", "dyad3"]
    assert p_texts == ["p = 0.500", "p = 0.010", "p = 0.200", "p = 0.001"]


def test_significant_dyads_have_filled_dots_and_others_open_ones():
    result = _result(BLOCKS)
    dyads, _ = _dyad_axes(_render(plot_surrogate_result(result)))
    dots = [line for line in dyads.get_lines() if line.get_marker() == 'o']
    filled = [line.get_markerfacecolor() != 'white' for line in dots]
    assert filled == [p < 0.05 for p in result.dyad_p_values]
    assert [line.get_xdata()[0] for line in dots] == pytest.approx(result.real_values)


def test_bars_span_the_middle_95_percent_of_each_dyads_surrogates():
    result = _result(BLOCKS)
    dyads, _ = _dyad_axes(_render(plot_surrogate_result(result)))
    bars = [line for line in dyads.get_lines() if line.get_color() == plot.SURROGATE_COLOR]
    for bar, null_values in zip(bars, result.dyad_null_values):
        assert list(bar.get_xdata()) == pytest.approx(np.percentile(null_values, [2.5, 97.5]))


def test_many_dyads_name_only_some_rows():
    n = 100
    result = _result(BLOCKS, n_dyads=n, p_values=[0.3] * n)
    dyads, p_axis = _dyad_axes(_render(plot_surrogate_result(result)))
    names = [label.get_text() for label in dyads.get_yticklabels()]
    assert len(names) == len(p_axis.get_yticklabels()) <= plot.MAX_DYAD_LABELS
    assert names[:2] == ["dyad0", "dyad3"]
    assert len([line for line in dyads.get_lines() if line.get_marker() == 'o']) == n


# ---------------------------------------------------------------------------
# WELCH
# ---------------------------------------------------------------------------

def test_welch_shows_every_random_pair_and_real_dyad():
    result = _result(WELCH)
    ax, = _render(plot_surrogate_result(result)).axes
    random_pairs, real_dyads = ax.collections
    assert len(random_pairs.get_offsets()) == 100
    assert list(real_dyads.get_offsets()[:, 0]) == pytest.approx(result.real_values)
    assert [label.get_text() for label in ax.get_yticklabels()] == ["random pairs", "real dyads"]


def test_welch_title_has_t_and_p():
    title, = _titles(_render(plot_surrogate_result(_result(WELCH))))
    assert "Welch's t-test" in title and "t = -2.50, p = 0.004, two-sided" in title


def test_welch_without_real_dyads_still_draws():
    ax, = _render(plot_surrogate_result(_result(WELCH, real_values=[], t_statistic=float('nan'),
                                                p_value=float('nan')))).axes
    assert "t = -, p = -" in ax.get_title()
