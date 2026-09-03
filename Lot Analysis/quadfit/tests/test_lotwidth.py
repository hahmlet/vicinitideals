"""Unit tests for the two lot-width measurements (`lotwidth.py`).

Pure geometry over hand-drawn parcels, so the shapes that matter are the ones
drawn here rather than the ones the corpus happens to hold. The lot that gives
this module its reason is the cul-de-sac wedge: narrow at the street, wide
behind it, and thrown out by a screen that measured the street edge against a
number the city measures across the middle.

What is guarded as hard as the arithmetic is the *refusal*. A width this module
invents is worse than one it declines, because a declined lot goes to a person
and an invented one can go green.
"""

from __future__ import annotations

import pytest

pytest.importorskip("shapely")

from shapely.geometry import Polygon  # noqa: E402

from lotwidth import (  # noqa: E402
    center_parallel_width_ft,
    side_midpoints_width_ft,
    width_ft,
)

pytestmark = pytest.mark.unit


#: 30 ft at the street, 70 ft across the back, 100 ft deep -- the cul-de-sac
#: wedge, and the reason 988 lots were being judged on the wrong line.
WEDGE = Polygon([(0, 0), (30, 0), (50, 100), (-20, 100)])
WEDGE_EDGES = [
    [0, 0, 30, 0, "F"],
    [30, 0, 50, 100, "S"],
    [50, 100, -20, 100, "R"],
    [-20, 100, 0, 0, "S"],
]

#: 50 x 100, square to the street. Frontage and width are the same line.
RECT = Polygon([(0, 0), (50, 0), (50, 100), (0, 100)])
RECT_EDGES = [
    [0, 0, 50, 0, "F"],
    [50, 0, 50, 100, "S"],
    [50, 100, 0, 100, "R"],
    [0, 100, 0, 0, "S"],
]


def test_a_wedge_is_wider_across_the_middle_than_at_the_street():
    """Oregon City's 50 ft number against a lot with 30 ft of street.

    The lot passes, and it has passed all along -- OCMC 17.04.700 measures
    between the midpoints of the side lot lines, which on this parcel is 50 ft.
    The screen was comparing the 30.
    """
    assert side_midpoints_width_ft(WEDGE, WEDGE_EDGES) == 50.0


def test_a_square_lot_measures_the_same_either_way():
    # The control. Where the two lines coincide the new measurement must not
    # move anything, or every rectangle in two cities changes verdict.
    assert side_midpoints_width_ft(RECT, RECT_EDGES) == 50.0
    assert center_parallel_width_ft(RECT, [0.0]) == 50.0


def test_a_lot_with_one_side_line_is_not_measured():
    """A corner lot's second street edge is classified as frontage, which
    leaves one side lot line and no pair to measure between. Two thirds of the
    lots this declines are that shape. Declining is the point: the alternative
    is a distance between a side line and a street edge, which is not the
    distance the section names."""
    one_side = [e for e in WEDGE_EDGES if e[4] != "S"] + [WEDGE_EDGES[1]]
    assert side_midpoints_width_ft(WEDGE, one_side) is None


def test_a_join_across_ground_the_lot_does_not_own_is_not_a_width():
    """"Opposite" is the load-bearing word in 17.04.700, and it is what keeps
    this from measuring the neighbour.

    A lot wrapping around another one has two long outer side lines facing each
    other across 100 ft, and 100 ft is not its width -- most of that distance
    is somebody else's land. The test is containment: the join between the two
    midpoints has to stay on the parcel. What comes back instead is one arm.
    """
    u = Polygon([
        (0, 0), (100, 0), (100, 100), (70, 100), (70, 30), (30, 30), (30, 100),
        (0, 100),
    ])
    edges = [
        [0, 0, 100, 0, "F"],
        [100, 0, 100, 100, "S"],
        [100, 100, 70, 100, "R"],
        [70, 100, 70, 30, "S"],
        [70, 30, 30, 30, "S"],
        [30, 30, 30, 100, "S"],
        [30, 100, 0, 100, "R"],
        [0, 100, 0, 0, "S"],
    ]
    assert side_midpoints_width_ft(u, edges) == 33.54


def test_where_a_lot_offers_two_pairs_the_answer_is_the_narrow_one():
    """An L-shaped lot has no single "principal opposite" pair -- the bottom
    strip is 100 ft across and the upright arm is 40 -- and the pair with the
    most side line behind it is the arm. That is the conservative answer and
    the direction to be wrong in: a width too small can only put a lot in the
    red pile, never turn one green.

    In the pipeline neither this shape nor the one above is ever measured; both
    are concave enough to be tier C, which `width_ft` refuses outright. This is
    what the underlying function does when it is asked anyway.
    """
    ell = Polygon([(0, 0), (100, 0), (100, 40), (40, 40), (40, 100), (0, 100)])
    edges = [
        [0, 0, 100, 0, "F"],
        [100, 0, 100, 40, "S"],
        [100, 40, 40, 40, "S"],
        [40, 40, 40, 100, "S"],
        [40, 100, 0, 100, "R"],
        [0, 100, 0, 0, "S"],
    ]
    assert side_midpoints_width_ft(ell, edges) == 44.72
    assert width_ft("side_midpoints", ell, edges, [0.0], "C") is None


def test_the_chord_is_drawn_along_the_street_not_across_it():
    """Tualatin measures "parallel to the front lot line". A chord drawn at
    right angles to it would return the lot's DEPTH -- 100 ft on a lot 50 wide
    -- and every parcel in the city would clear a 50 ft standard."""
    assert center_parallel_width_ft(RECT, [0.0]) == 50.0
    assert center_parallel_width_ft(RECT, [90.0]) == 100.0


def test_a_corner_lot_is_not_measured_under_tualatins_definition():
    # TDC 31.060 switches to "the horizontal distance between the front lot
    # line and a side lot line" on a corner lot, which is a different pair of
    # lines on a different axis. 289 of Tualatin's 952 lots are corners.
    assert center_parallel_width_ft(RECT, [0.0, 90.0]) is None


def test_a_chord_that_leaves_the_lot_and_returns_measures_only_this_lot():
    """A lot wrapping around a neighbour is re-entered by the chord further
    along, and that second piece is somebody else's width. Only the piece the
    centre of the lot stands on is this lot's.

    This parcel's centroid falls in the notch, on ground it does not own, so
    the centre is taken as a point inside it instead -- one arm, 30 ft across.
    Summing the clipped pieces would report 60, and the span between the outer
    faces is 100.
    """
    ushape = Polygon([
        (0, 0), (100, 0), (100, 100), (70, 100), (70, 30), (30, 30), (30, 100),
        (0, 100),
    ])
    assert center_parallel_width_ft(ushape, [0.0]) == 30.0


def test_an_irregular_lot_is_refused_whatever_the_city():
    """Tier C is the flag-lot and concave pile, where "the two principal
    opposite side lot lines" is a phrase without a referent. Tier D has no
    street to draw a bearing from."""
    assert width_ft("side_midpoints", WEDGE, WEDGE_EDGES, [0.0], "C") is None
    assert width_ft("center_parallel", RECT, RECT_EDGES, [0.0], "D") is None


def test_a_city_with_no_width_definition_is_never_measured():
    # West Linn heads the row "Minimum lot width AT FRONT LOT LINE", so its
    # number IS the street edge s4 measures and this must not touch it.
    assert width_ft(None, RECT, RECT_EDGES, [0.0], "A") is None


def test_an_unknown_measure_is_an_error_not_a_silence():
    # A typo in rules.yaml must not read as "this city has no width rule",
    # which would silently restore the wrong-line comparison it replaced.
    with pytest.raises(ValueError):
        width_ft("midpoints", RECT, RECT_EDGES, [0.0], "A")
