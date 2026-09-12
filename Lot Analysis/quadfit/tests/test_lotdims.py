"""Unit tests for the lot width and lot depth measurements (`lotdims.py`).

Pure geometry over hand-drawn parcels, so the shapes that matter are the ones
drawn here rather than the ones the corpus happens to hold. The lot that gives
this module its reason is the cul-de-sac wedge: narrow at the street, wide
behind it, and thrown out by a screen that measured the street edge against a
number the city measures across the middle.

What is guarded as hard as the arithmetic is the *refusal*. A dimension this
module invents is worse than one it declines, because a declined lot goes to a
person and an invented one can go green.

And what is guarded hardest of all is that each measurement **rules both ways**.
A new measurement that can only rescue is an amnesty and a new measurement that
can only refuse is a cull; each form here is given one parcel it saves and one
it sinks, because a form that has only ever been seen doing one of those has
not been tested, it has been hoped for.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("shapely")

from shapely.geometry import Polygon  # noqa: E402

from lotdims import (  # noqa: E402
    DEPTH_MEASURES,
    WIDTH_MEASURES,
    _frame,
    center_parallel_width_ft,
    dimensions,
    front_groups,
    mid_width_depth_ft,
    orientations,
    pick,
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


# --- the two measurements that were already deployed -------------------------
#
# Carried over unchanged from test_lotwidth.py. Oregon City and Tualatin are
# live in the screen, so these are not tests of new code -- they are the pin
# that says reorganising the module did not move a verdict in two cities.


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
    """With no front in hand, a corner lot's second street edge is classified
    as frontage, which leaves one side lot line and no pair to measure
    between. Declining is the point: the alternative is a distance between a
    side line and a street edge, which is not the distance the section names.

    This is the bare form, as `width_ft` calls it. The pipeline goes through
    `dimensions`, which hands the form a front and the answer changes -- the
    next test."""
    one_side = [e for e in WEDGE_EDGES if e[4] != "S"] + [WEDGE_EDGES[1]]
    assert side_midpoints_width_ft(WEDGE, one_side) is None


def test_a_corner_lot_is_measured_from_its_chosen_front_and_ruled_both_ways():
    """2,724 Oregon City lots and every corner lot in Happy Valley, Portland
    and West Linn were refused by the midpoints form for want of two `S`
    edges, and would have gone to review the day the frontage proxy retired.
    They are corner lots, and the city has already said what their sides are:
    Happy Valley's glossary, "on a corner lot, the longer lot line that abuts
    a street is a side lot line". Once the front is chosen, the longer street
    edge is a side and the pair exists.

    The 40 x 100 corner lot facing its narrowest street (Oregon City's rule)
    is 40 ft wide between the midpoints of its two long lines. Against a 35 ft
    standard it conforms; against 50 it does not -- the same measurement, both
    verdicts, or it would be an amnesty for the lots the proxy used to hold.
    """
    corner = Polygon([(0, 0), (40, 0), (40, 100), (0, 100)])
    edges = [
        [0, 0, 40, 0, "F"],
        [40, 0, 40, 100, "S"],
        [40, 100, 0, 100, "R"],
        [0, 100, 0, 0, "F"],
    ]
    # s4's classifier would call the left edge F and the right edge parallel
    # to it -- no S at all. Strip the S to reproduce that, so the test cannot
    # pass on a classification the pipeline never produces.
    edges = [e[:4] + ["F" if e[4] == "F" else ("R" if e[4] == "R" else "X")]
             for e in edges]
    assert side_midpoints_width_ft(corner, edges) is None, "bare form still refuses"

    got = dimensions(
        corner, edges, [0.0, 90.0], "A",
        width_measure="side_midpoints", depth_measure="midpoints",
        front_rule="narrowest", min_width_ft=35.0,
    )
    assert got is not None
    assert got.front_ft == 40.0 and got.width_ft == 40.0 and got.depth_ft == 100.0
    assert got.width_ft >= 35.0, "conforms to 35"
    assert got.width_ft < 50.0, "and would not conform to 50"

    # A corner lot whose interior side converges on the long street: the
    # midpoints join runs from (0, 50) on the street side to (50, 50) on the
    # interior side. Fifty across the middle, on a lot that is 40 at the kerb.
    splay = Polygon([(0, 0), (40, 0), (60, 100), (0, 100)])
    splay_edges = [
        [0, 0, 40, 0, "F"],
        [40, 0, 60, 100, "S"],
        [60, 100, 0, 100, "R"],
        [0, 100, 0, 0, "F"],
    ]
    wide = dimensions(
        splay, splay_edges, [0.0, 90.0], "A",
        width_measure="side_midpoints", front_rule="narrowest",
    )
    assert wide is not None and wide.front_ft == 40.0
    assert wide.width_ft == pytest.approx(50.0)


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
    with pytest.raises(ValueError):
        orientations(RECT, RECT_EDGES, [0.0], "A", depth_measure="side_midpoints")
    with pytest.raises(ValueError):
        pick(
            orientations(RECT, RECT_EDGES, [0.0], "A", width_measure="mean_width"),
            "whichever_is_kindest",
        )


# --- the control: on a rectangle every city agrees ---------------------------


def test_on_a_rectangle_all_nine_forms_give_the_same_two_numbers():
    """Thirteen cities, nine measurements, one answer on a regular lot.

    This is the test that says the forms are variations on a measurement and
    not nine different quantities. Most parcels in the corpus are close enough
    to this shape that encoding a city's own form must not move its verdicts;
    the forms exist for the parcels that are not, and those are below.
    """
    for m in sorted(WIDTH_MEASURES):
        o = dimensions(
            RECT, RECT_EDGES, [0.0], "A",
            width_measure=m, front_setback_ft=20.0,
        )
        assert o is not None and o.width_ft == 50.0, m
    for m in sorted(DEPTH_MEASURES):
        o = dimensions(RECT, RECT_EDGES, [0.0], "A", depth_measure=m)
        assert o is not None and o.depth_ft == 100.0, m


# --- and on a wedge they part company ----------------------------------------


@pytest.mark.parametrize(
    "measure,expected,why",
    [
        ("building_line", 38.0,
         "Milwaukie measures AT THE BUILDING LINE -- 20 ft back from a street "
         "the lot meets at 30 ft, so 38"),
        ("setback_rectangle", 38.0,
         "Portland's rectangle stands on the setback line and the wedge only "
         "widens behind it, so the narrowest row in the band is the first"),
        ("midway_front_rear", 50.0,
         "Troutdale and three others measure halfway between front and rear"),
        ("mean_width", 50.0,
         "Wilsonville averages every row, and on a linear taper the mean is "
         "the midpoint"),
        ("side_midpoints", 50.0,
         "Oregon City joins the midpoints of the side lot lines"),
        ("center_parallel", 52.67,
         "Tualatin measures at the CENTRE of the lot, which on a taper sits "
         "further back than halfway and so reads wider"),
    ],
)
def test_the_wedge_separates_the_width_forms(measure, expected, why):
    """One parcel, six cities, six numbers between 38 and 52.67 ft.

    Against a 50 ft standard this lot fails in Milwaukie and Portland and
    passes in the other four, and that is not a bug in any of them -- it is
    what their codes say. It is also the answer to why this could not have been
    one measurement with a switch on it: 30 ft of frontage, and not one of the
    six agrees with the 30.
    """
    o = dimensions(
        WEDGE, WEDGE_EDGES, [0.0], "A",
        width_measure=measure, front_setback_ft=20.0,
    )
    assert o is not None and o.width_ft == expected, why


@pytest.mark.parametrize(
    "measure,expected",
    [("midpoints", 58.31), ("average", 35.62), ("mid_width", 41.67)],
)
def test_one_parcel_has_three_depths_because_three_cities_ask_differently(
    measure, expected
):
    """A lot 100 ft along the street narrowing to 40 ft at the back, 50 deep.

    Oregon City's midpoint-to-midpoint line runs diagonally and reads 58 ft;
    Milwaukie's average over the frontage reads 36; Troutdale's single line up
    the middle reads 42. Against an 80 ft standard all three refuse, against a
    50 ft standard only Oregon City passes it. Nothing about the parcel is in
    dispute -- the three numbers are three sentences of Oregon law.
    """
    trap = Polygon([(0, 0), (100, 0), (40, 50), (0, 50)])
    edges = [
        [0, 0, 100, 0, "F"],
        [100, 0, 40, 50, "S"],
        [40, 50, 0, 50, "R"],
        [0, 50, 0, 0, "S"],
    ]
    o = dimensions(trap, edges, [0.0], "A", depth_measure=measure)
    assert o is not None and o.depth_ft == expected


# --- ruling both ways --------------------------------------------------------


def test_portlands_rectangle_refuses_a_lot_the_chord_would_pass():
    """60 ft of street, and 30 ft of buildable width 40 ft back.

    A lot pinched behind its frontage clears any measurement taken on a single
    line -- the building line says 60 ft -- and fails the one Portland
    actually applies, because 33.930.100.A requires a rectangle 40 ft deep to
    fit *entirely within the lot*. This is the refusing direction, and it is
    the half a new measurement is usually missing.
    """
    pinched = Polygon([
        (0, 0), (60, 0), (60, 25), (45, 40), (45, 100), (15, 100), (15, 40),
        (0, 25),
    ])
    edges = [
        [0, 0, 60, 0, "F"],
        [60, 0, 60, 25, "S"],
        [60, 25, 45, 40, "S"],
        [45, 40, 45, 100, "S"],
        [45, 100, 15, 100, "R"],
        [15, 100, 15, 40, "S"],
        [15, 40, 0, 25, "S"],
        [0, 25, 0, 0, "S"],
    ]
    chord = dimensions(
        pinched, edges, [0.0], "A",
        width_measure="building_line", front_setback_ft=10.0,
    )
    rect = dimensions(
        pinched, edges, [0.0], "A",
        width_measure="setback_rectangle", front_setback_ft=10.0,
    )
    assert chord is not None and chord.width_ft == 60.0
    assert rect is not None and rect.width_ft == 30.0


def test_a_shallow_lot_fails_and_a_corner_lot_the_proxy_sank_does_not():
    """The two halves of the depth measurement, on the two real parcels that
    forced it to be built.

    Five adjacent lots on SE Vernie Ave in Milwaukie are 98 ft wide and 64 ft
    deep against an 80 ft standard, and they genuinely fail -- that is the
    refusing half, and nothing in the pipeline had ever been able to say it.

    The other is the reason the first count of these was wrong by a factor of
    six. `frontage_ft` is the SUM of every street-facing edge, so a corner lot
    346 ft along two streets divided into its area gave 79.7 ft, a hair under
    the standard, on a parcel that is 176 by 170. Measured rather than
    inferred, it is nowhere near the line.
    """
    vernie = Polygon([(0, 0), (98, 0), (98, 64), (0, 64)])
    v_edges = [
        [0, 0, 98, 0, "F"],
        [98, 0, 98, 64, "S"],
        [98, 64, 0, 64, "R"],
        [0, 64, 0, 0, "S"],
    ]
    v = dimensions(
        vernie, v_edges, [0.0], "A",
        depth_measure="average", width_measure="building_line",
        front_setback_ft=20.0, front_rule="applicant_choice",
        min_width_ft=60.0, min_depth_ft=80.0,
    )
    assert v is not None
    assert v.width_ft == 98.0, "wide enough"
    assert v.depth_ft == 64.0 and v.depth_ft < 80.0, "and genuinely too shallow"

    corner = Polygon([(0, 0), (176, 0), (176, 170), (0, 170)])
    c_edges = [
        [0, 0, 176, 0, "F"],
        [176, 0, 176, 170, "F"],
        [176, 170, 0, 170, "R"],
        [0, 170, 0, 0, "S"],
    ]
    c = dimensions(
        corner, c_edges, [0.0, 90.0], "A",
        depth_measure="average", width_measure="building_line",
        front_setback_ft=20.0, front_rule="applicant_choice",
        min_width_ft=60.0, min_depth_ft=80.0,
    )
    assert c is not None
    assert c.width_ft >= 60.0 and c.depth_ft >= 80.0, "never close to failing"
    # And the number the rectangle proxy produced is not a dimension this lot
    # has in any direction, which is the whole indictment of it.
    assert c.depth_ft != pytest.approx(79.7, abs=1.0)


# --- which edge is the front -------------------------------------------------


def test_the_applicant_may_not_face_two_directions_at_once():
    """The amnesty this module exists to not commit.

    A corner lot 40 ft by 100 ft is 40 wide and 100 deep facing the short
    street, and 100 wide and 40 deep facing the long one. Against a standard of
    60 ft wide and 60 ft deep it conforms facing neither. Taking the widest
    orientation and the deepest orientation separately would report 100 and
    100 and pass it -- two numbers off two different buildings.

    Milwaukie hands the choice of front to the applicant (MMC 19.200, corner
    lot), so the lot gets every orientation and has to satisfy both standards
    in one of them.
    """
    corner = Polygon([(0, 0), (40, 0), (40, 100), (0, 100)])
    edges = [
        [0, 0, 40, 0, "F"],
        [40, 0, 40, 100, "S"],
        [40, 100, 0, 100, "R"],
        [0, 100, 0, 0, "F"],
    ]
    os = orientations(
        corner, edges, [0.0, 90.0], "A",
        width_measure="midway_front_rear", depth_measure="average",
    )
    assert len(os) == 2, "a corner lot is two candidate fronts"
    assert max(o.width_ft for o in os) == 100.0
    assert max(o.depth_ft for o in os) == 100.0

    got = pick(os, "applicant_choice", min_width_ft=60.0, min_depth_ft=60.0)
    assert got is not None
    assert not (got.width_ft >= 60.0 and got.depth_ft >= 60.0), (
        "no single orientation satisfies both, so none may be reported as doing"
    )
    # Relax one standard and the same lot conforms, facing the street that
    # makes it conform. This is the rescuing half of the same rule.
    wide = pick(os, "applicant_choice", min_width_ft=90.0, min_depth_ft=30.0)
    assert wide is not None and wide.width_ft == 100.0 and wide.depth_ft == 40.0
    deep = pick(os, "applicant_choice", min_width_ft=30.0, min_depth_ft=90.0)
    assert deep is not None and deep.width_ft == 40.0 and deep.depth_ft == 100.0


def test_the_narrowest_street_edge_is_the_front_where_the_city_says_so():
    """Oregon City, Portland, Fairview and Wood Village all choose for the
    applicant: the front is the shortest lot line abutting a street. The lot
    gets one orientation and the standards get no say in which."""
    corner = Polygon([(0, 0), (40, 0), (40, 100), (0, 100)])
    edges = [
        [0, 0, 40, 0, "F"],
        [40, 0, 40, 100, "S"],
        [40, 100, 0, 100, "R"],
        [0, 100, 0, 0, "F"],
    ]
    os = orientations(
        corner, edges, [0.0, 90.0], "A",
        width_measure="midway_front_rear", depth_measure="average",
    )
    got = pick(os, "narrowest")
    assert got is not None and got.front_ft == 40.0
    assert got.width_ft == 40.0 and got.depth_ft == 100.0


def test_a_city_that_does_not_say_is_not_handed_a_rule():
    """Three of the thirteen define a width or a depth and never say which edge
    is the front. On a lot facing one street that changes nothing. On a corner
    lot it is the difference between a depth of 40 ft and a depth of 100 ft,
    so the lot is refused and goes in front of a person.

    Picking `narrowest` by default would have been the tempting choice and it
    is the wrong one twice over: it invents a rule the city did not write, and
    on a minimum-depth standard it invents the *generous* one.
    """
    corner = Polygon([(0, 0), (40, 0), (40, 100), (0, 100)])
    corner_edges = [
        [0, 0, 40, 0, "F"],
        [40, 0, 40, 100, "S"],
        [40, 100, 0, 100, "R"],
        [0, 100, 0, 0, "F"],
    ]
    assert dimensions(
        corner, corner_edges, [0.0, 90.0], "A", depth_measure="average"
    ) is None
    # The same city, an interior lot, and the question does not arise.
    got = dimensions(RECT, RECT_EDGES, [0.0], "A", depth_measure="average")
    assert got is not None and got.depth_ft == 100.0


def test_a_rear_lot_line_belongs_to_one_front_and_not_the_other():
    """The measurement that would otherwise run diagonally across the parcel.

    A corner lot has two candidate fronts, and each has its own rear: the
    line opposite it. Measuring midpoint-to-midpoint from one front to the
    rear of the OTHER reaches it on the diagonal, which is longer than the lot
    is in either direction and would pass a depth standard the parcel fails.

    So the rear has to face the front it is measured from -- and it is found
    by facing it, not by what s4 called it. The x=40 line here is drawn ``S``
    (s4 would say ``R``, it is parallel to the west street) and it is still
    the rear of the west front, because Portland 33.910's rear lot line is
    "a lot line that is opposite a front lot line" and nothing else.
    """
    corner = Polygon([(0, 0), (40, 0), (40, 100), (0, 100)])
    edges = [
        [0, 0, 40, 0, "F"],
        [40, 0, 40, 100, "S"],
        [40, 100, 0, 100, "R"],
        [0, 100, 0, 0, "F"],
    ]
    os = orientations(
        corner, edges, [0.0, 90.0], "A",
        width_measure="midway_front_rear", depth_measure="midpoints",
    )
    by_front = {o.front_ft: o.depth_ft for o in os}
    assert by_front[40.0] == 100.0, "square to the rear it faces"
    assert by_front[100.0] == 40.0, "and square to ITS rear from the other street"
    # 107.7 ft is the diagonal, and it is the number a rear-blind version of
    # this returns. It must not appear.
    assert 107.7 not in {round(v, 1) for v in by_front.values() if v}
    # Where nothing faces the front, the depth is refused -- a lot held for
    # review, not a lot dropped. Take the east line away by making it turn:
    # a triangle's third side faces neither street.
    tri = Polygon([(0, 0), (40, 0), (0, 40)])
    tri_edges = [[0, 0, 40, 0, "F"], [40, 0, 0, 40, "S"], [0, 40, 0, 0, "F"]]
    only_depth = orientations(tri, tri_edges, [0.0, 90.0], "A", depth_measure="midpoints")
    assert only_depth == (), "no line is opposite either front"


def test_the_rear_is_the_line_opposite_the_front_whatever_s4_called_it():
    """The 8,505 lots: a corner lot with an alley (or a narrow enough lot with
    a side street) has its rear line within the street threshold, so s4 marks
    it ``F``, and a depth read from the ``R`` class alone finds nothing to
    measure to. Gresham 3.0100: "a lot line abutting an alley is a rear lot
    line". It is opposite the front, so it is the rear, whatever the label.

    Ruled both ways: the same shape 30 ft deep fails the standard it would
    have been held for review on.
    """
    def lot(depth):
        g = Polygon([(0, 0), (60, 0), (60, depth), (0, depth)])
        edges = [
            [0, 0, 60, 0, "F"],           # the street
            [60, 0, 60, depth, "F"],      # the side street
            [60, depth, 0, depth, "F"],   # the alley, as s4 labelled it
            [0, depth, 0, 0, "R"],        # parallel to the side street
        ]
        return g, edges

    g, edges = lot(100)
    o = dimensions(
        g, edges, [0.0, 90.0], "B",
        width_measure="side_midpoints", depth_measure="midpoints",
        front_rule="narrowest",
    )
    assert o is not None and o.front_ft == 60.0
    assert o.depth_ft == 100.0, "to the alley line, which is the rear"
    # And with the alley told apart by s4 (class A) the answer is the same.
    edges[2][4] = "A"
    o2 = dimensions(
        g, edges, [0.0], "A",
        width_measure="side_midpoints", depth_measure="midpoints",
        front_rule="narrowest",
    )
    assert o2 is not None and (o2.front_ft, o2.depth_ft) == (60.0, 100.0)
    # The other way: a lot 35 ft deep is measured, and measured short.
    g, edges = lot(35)
    shallow = dimensions(
        g, edges, [0.0, 90.0], "B",
        width_measure="side_midpoints", depth_measure="midpoints",
        front_rule="narrowest",
    )
    assert shallow is not None and shallow.front_ft == 35.0, "narrowest is the side"
    assert shallow.depth_ft == 60.0
    facing_street = [o for o in orientations(
        g, edges, [0.0, 90.0], "B", depth_measure="midpoints",
    ) if o.front_ft == 60.0]
    assert facing_street and facing_street[0].depth_ft == 35.0, "shallow, and said so"



def test_a_bend_in_the_front_is_not_the_rear():
    """A frontage that turns more than the bucket allows is two street-facing
    runs, and the run not chosen as the front is parallel enough to the one
    that was to pass the opposite test while sitting a foot or two beyond its
    line. Read as a rear candidate and averaged in with the true rear it
    dragged the rear midpoint up to the street: a 239 ft Portland lot came
    out 1.78 ft deep the first time the rear was read without the ``R``
    label (13,904 lots moved that way). The rear is on the far side of the
    lot, so only the far half is looked at.

    Both ways: the same test retires a jog near the street in a side line
    labelled ``R``, which the label used to admit as a rear (a West Linn lot
    read 0.91 ft deep through one). And a real rear that steps -- two rear
    segments in the far half -- is still averaged, as before.
    """
    # A 60 ft front with a 12 ft piece turning 25 degrees at its end -- too
    # sharp and too short to be the same curve (a 28 ft radius) -- and the
    # rear at 100.
    bent = Polygon([(0, 0), (60, 0), (70.88, 5.07), (70.88, 100), (0, 100)])
    edges = [
        [0, 0, 60, 0, "F"],
        [60, 0, 70.88, 5.07, "F"],
        [70.88, 5.07, 70.88, 100, "S"],
        [70.88, 100, 0, 100, "R"],
        [0, 100, 0, 0, "S"],
    ]
    assert len(front_groups(edges)) == 2, "two runs: the bend breaks the walk"
    facing = [o for o in orientations(
        bent, edges, [0.0, 25.0], "A",
        width_measure="side_midpoints", depth_measure="midpoints",
    ) if o.front_ft == 60.0]
    assert facing, "the straight run is a candidate front"
    # Midpoint to midpoint; the rear midpoint sits 5.44 ft east of the
    # front's, so the join leans: hypot(5.44, 100). Not 1.78.
    assert facing[0].depth_ft == pytest.approx(math.hypot(5.44, 100), abs=0.05), "to the rear, not the bend"

    # A jog in the side line one foot back from the street, labelled R.
    jogged = Polygon([(0, 0), (60, 0), (60, 1), (62, 1), (62, 100), (0, 100)])
    edges = [
        [0, 0, 60, 0, "F"],
        [60, 0, 60, 1, "S"],
        [60, 1, 62, 1, "R"],       # the jog, parallel to the front
        [62, 1, 62, 100, "S"],
        [62, 100, 0, 100, "R"],
        [0, 100, 0, 0, "S"],
    ]
    o = dimensions(
        jogged, edges, [0.0], "A",
        width_measure="side_midpoints", depth_measure="midpoints",
    )
    assert o is not None and o.depth_ft == pytest.approx(100.0, abs=0.5)

    # A stepped rear: 40 ft of it at 90 and 20 ft at 100, both in the far
    # half, so the length-weighted midpoint is where it always was.
    stepped = Polygon([(0, 0), (60, 0), (60, 100), (40, 100), (40, 90), (0, 90)])
    edges = [
        [0, 0, 60, 0, "F"],
        [60, 0, 60, 100, "S"],
        [60, 100, 40, 100, "R"],
        [40, 100, 40, 90, "S"],
        [40, 90, 0, 90, "R"],
        [0, 90, 0, 0, "S"],
    ]
    o = dimensions(
        stepped, edges, [0.0], "A",
        width_measure="side_midpoints", depth_measure="midpoints",
    )
    assert o is not None and o.depth_ft == pytest.approx(93.4, abs=0.1)


# --- the clipped corner ------------------------------------------------------


def test_a_clipped_corner_is_not_a_front_lot_line():
    """A corner lot's corner is cut -- a chamfer, or an arc drawn as a few
    chords -- and every piece of it faces the street. Under "the shortest lot
    line abutting a street" a ten-foot chamfer beat both streets on 3,995
    lots, and the parcel was measured square to it: no rear faces a 45 degree
    line, so no depth, and the width was a chord across nothing.

    The clip is dropped from the candidates. It still counts as frontage.
    """
    chamfered = Polygon([(0, 0), (60, 0), (67, 7), (67, 100), (0, 100)])
    edges = [
        [0, 0, 60, 0, "F"],
        [60, 0, 67, 7, "F"],       # the 9.9 ft chamfer
        [67, 7, 67, 100, "F"],
        [67, 100, 0, 100, "R"],
        [0, 100, 0, 0, "R"],
    ]
    groups = front_groups(edges)
    lengths = sorted(
        round(sum(math.hypot(e[2] - e[0], e[3] - e[1]) for e in m), 1) for _, m in groups
    )
    assert lengths == [60.0, 93.0], "two streets; the chamfer is not a third"
    o = dimensions(
        chamfered, edges, [0.0, 90.0], "B",
        width_measure="midway_front_rear", depth_measure="midpoints",
        front_rule="narrowest",
    )
    assert o is not None and o.front_ft == 60.0, "the shorter STREET, not the chamfer"
    # Midpoint to midpoint: the rear's midpoint sits 3.5 ft east of the front's.
    assert o.depth_ft == pytest.approx(100.0, abs=0.1) and o.width_ft == 67.0

    # An arc surveyed as three chords, each its own run, all of them dropped.
    arc = Polygon([(0, 0), (60, 0), (65, 1), (69, 4), (70, 9), (70, 100), (0, 100)])
    arc_edges = [
        [0, 0, 60, 0, "F"],
        [60, 0, 65, 1, "F"], [65, 1, 69, 4, "F"], [69, 4, 70, 9, "F"],
        [70, 9, 70, 100, "F"],
        [70, 100, 0, 100, "R"],
        [0, 100, 0, 0, "R"],
    ]
    assert len(front_groups(arc_edges)) == 2
    o = dimensions(
        arc, arc_edges, [0.0, 90.0], "B",
        width_measure="midway_front_rear", depth_measure="midpoints",
        front_rule="narrowest",
    )
    assert o is not None and o.front_ft == 60.0


def test_a_short_end_between_two_parallel_streets_is_a_front_not_a_clip():
    """A 20 ft by 200 ft strip with a street along both long sides and across
    one end: the end is between two street-facing runs and under 30 ft, but
    the runs on either side of it are parallel, not a corner. It is the
    narrow front of a narrow lot (Oregon City, 20 x 766 ft, the first time
    the clip rule ran)."""
    strip = Polygon([(0, 0), (20, 0), (20, 200), (0, 200)])
    edges = [
        [0, 0, 20, 0, "F"],        # the end, on a street
        [20, 0, 20, 200, "F"],     # a street along this side
        [20, 200, 0, 200, "R"],
        [0, 200, 0, 0, "F"],       # and along this one
    ]
    groups = front_groups(edges)
    assert sorted(
        round(sum(math.hypot(e[2] - e[0], e[3] - e[1]) for e in m), 1) for _, m in groups
    ) == [20.0, 200.0, 200.0]
    o = dimensions(
        strip, edges, [0.0, 90.0], "B",
        width_measure="side_midpoints", depth_measure="midpoints",
        front_rule="narrowest",
    )
    assert o is not None and (o.front_ft, o.width_ft, o.depth_ft) == (20.0, 20.0, 200.0)


def test_a_short_front_is_still_a_front_when_it_is_not_between_two_streets():
    """The clip test is not "short fronts are not fronts". A 25 ft wide lot on
    a corner -- Portland's narrowest plat -- has a 25 ft front with the side
    street on one end and its own side lot line on the other, and it is the
    front -- the narrowest -- and the one the lot is judged on. Only a chain
    under 20 ft off the end of a long run is taken for a corner arc, so a
    real front is never in reach."""
    narrow = Polygon([(0, 0), (25, 0), (25, 100), (0, 100)])
    edges = [
        [0, 0, 25, 0, "F"],
        [25, 0, 25, 100, "F"],
        [25, 100, 0, 100, "R"],
        [0, 100, 0, 0, "R"],
    ]
    assert len(front_groups(edges)) == 2
    o = dimensions(
        narrow, edges, [0.0, 90.0], "B",
        width_measure="midway_front_rear", depth_measure="midpoints",
        front_rule="narrowest",
    )
    assert o is not None and (o.front_ft, o.width_ft, o.depth_ft) == (25.0, 25.0, 100.0)
    # And a lot that is nothing but short street lines keeps them all, because
    # a lot has to have a front; three clips with no street between them is a
    # shape, not a corner.
    tri = [[0, 0, 20, 0, "F"], [20, 0, 0, 20, "F"], [0, 20, 0, 0, "F"]]
    assert len(front_groups(tri)) == 3


# --- the front lot line on a curve -------------------------------------------


def test_a_curved_frontage_is_one_front_lot_line_not_four():
    """OCMC 17.04.490: "when the lot line abutting a street is curved, the
    front lot line follows the curve".

    A surveyed curve is a chain of short near-collinear segments. Grouping them
    by bearing splits the chain as soon as its total sweep passes the
    tolerance, and then "the front is the narrowest street lot line" picks a
    twenty-foot fragment and squares the whole parcel to it. Walking the
    boundary and breaking only where it turns keeps the curve whole.
    """
    curved = Polygon([(0, 0), (20, 1), (40, 3), (60, 6), (60, 90), (0, 90)])
    edges = [
        [0, 0, 20, 1, "F"],
        [20, 1, 40, 3, "F"],
        [40, 3, 60, 6, "F"],
        [60, 6, 60, 90, "S"],
        [60, 90, 0, 90, "R"],
        [0, 90, 0, 0, "S"],
    ]
    groups = front_groups(edges)
    assert len(groups) == 1, "one street, one front lot line"
    assert len(groups[0][1]) == 3
    o = dimensions(curved, edges, [3.0], "A", width_measure="midway_front_rear")
    assert o is not None and o.front_ft == pytest.approx(60.35, abs=0.05)


def test_a_frontage_on_a_bend_is_one_front_however_it_was_surveyed():
    """A Fairview lot on a curving street: five chords of 38, 13, 138, 27
    and 28 ft turning eleven to thirteen degrees at each joint. The bucket
    alone makes five fronts of it and "narrowest" then picks the 13 ft one;
    the city sees one curved front lot line (OCMC 17.04.490 says so in
    words). Joined on the curve, it is one run and the front is all 243 ft.

    And the joint that must NOT join: a corner arc. Two 100 ft streets at a
    right angle drawn with four 10 ft chords between them on a 25 ft
    radius: between two full-length streets the chain is the corner
    whatever its radius, so the straights stay apart and the chords are
    dropped as a clip.
    """
    # The bend, in local feet: chords rotating 12 degrees a step. The lot
    # runs 300 ft back square to the mean bearing of the front (23.7
    # degrees below the x axis, length-weighted), so the rear is parallel
    # to the front and the sides square to both.
    pts, ang, x, y = [(0.0, 0.0)], 0.0, 0.0, 0.0
    for L in (38, 13, 138, 27, 28):
        x, y = x + L * math.cos(math.radians(ang)), y + L * math.sin(math.radians(ang))
        pts.append((round(x, 2), round(y, 2)))
        ang -= 12.0
    front = [[*pts[i], *pts[i + 1], "F"] for i in range(5)]
    mean = math.radians(5784.0 / 244.0)
    dx, dy = 300 * math.sin(mean), 300 * math.cos(mean)
    far = [(round(pts[-1][0] + dx, 2), round(pts[-1][1] + dy, 2)), (round(dx, 2), round(dy, 2))]
    ring = pts + far
    poly = Polygon(ring)
    edges = front + [
        [*pts[-1], *far[0], "S"],
        [*far[0], *far[1], "R"],
        [*far[1], *pts[0], "S"],
    ]
    groups = front_groups(edges)
    assert len(groups) == 1, "one street, one front lot line"
    assert sum(math.hypot(e[2] - e[0], e[3] - e[1]) for e in groups[0][1]) == pytest.approx(244.0, abs=0.05)
    o = dimensions(
        poly, edges, [groups[0][0]], "A",
        width_measure="midway_front_rear", depth_measure="average",
        front_rule="narrowest",
    )
    assert o is not None and o.front_ft == pytest.approx(244.0, abs=0.05)
    assert o.depth_ft is not None and o.depth_ft > 250, "the whole lot, not a 20 ft sliver"

    # The corner arc: (0,0)-(100,0), four chords round a 25 ft radius to
    # (125,25), then north to (125,125).
    r, cx, cy = 25.0, 100.0, 25.0
    arc = [(cx + r * math.sin(math.radians(a)), cy - r * math.cos(math.radians(a)))
           for a in (0, 22.5, 45, 67.5, 90)]
    arc = [(round(px, 2), round(py, 2)) for px, py in arc]
    ring = [(0.0, 0.0)] + arc + [(125.0, 125.0), (0.0, 125.0)]
    poly = Polygon(ring)
    edges = [[0.0, 0.0, *arc[0], "F"]]
    edges += [[*arc[i], *arc[i + 1], "F"] for i in range(4)]
    edges += [[*arc[-1], 125.0, 125.0, "F"], [125.0, 125.0, 0.0, 125.0, "R"],
              [0.0, 125.0, 0.0, 0.0, "S"]]
    groups = front_groups(edges)
    assert sorted(round(b, 1) for b, _ in groups) == [0.0, 90.0], "two streets, no third front"
    assert sorted(len(m) for _, m in groups) == [1, 1], "and the chords belong to neither"


def test_a_corner_arc_drawn_in_many_short_chords_is_still_the_clip():
    """Six 6.5 ft chords turning 15 degrees each between two 100 ft
    streets. No single chord turns a corner against its neighbours, so a
    rule that looked only at the runs either side of each chord kept all
    six as candidate fronts. The chain is 39 ft between two runs that turn
    90 degrees: a clip. And on a narrow corner lot the 35 ft front is not
    part of the chain -- it is the end of its street, so it bounds the arc
    instead of vanishing with it.
    """
    r, cx, cy = 25.0, 100.0, 25.0
    arc = [(round(cx + r * math.sin(math.radians(a)), 3), round(cy - r * math.cos(math.radians(a)), 3))
           for a in (0, 15, 30, 45, 60, 75, 90)]
    ring = [(0.0, 0.0)] + arc + [(125.0, 125.0), (0.0, 125.0)]
    poly = Polygon(ring)
    edges = [[0.0, 0.0, *arc[0], "F"]]
    edges += [[*arc[i], *arc[i + 1], "F"] for i in range(6)]
    edges += [[*arc[-1], 125.0, 125.0, "F"], [125.0, 125.0, 0.0, 125.0, "R"],
              [0.0, 125.0, 0.0, 0.0, "S"]]
    groups = front_groups(edges)
    assert sorted(round(b, 1) for b, _ in groups) == [0.0, 90.0]
    assert sorted(len(m) for _, m in groups) == [1, 1]
    o = dimensions(
        poly, edges, [0.0, 90.0], "B",
        width_measure="side_midpoints", depth_measure="midpoints",
        front_rule="narrowest",
    )
    assert o is not None and o.front_ft == 100.0

    # The narrow corner lot: 35 ft on the first street, the same arc, 100 on
    # the second.
    ring = [(65.0, 0.0)] + arc + [(125.0, 125.0), (65.0, 125.0)]
    poly = Polygon(ring)
    edges = [[65.0, 0.0, *arc[0], "F"]]
    edges += [[*arc[i], *arc[i + 1], "F"] for i in range(6)]
    edges += [[*arc[-1], 125.0, 125.0, "F"], [125.0, 125.0, 65.0, 125.0, "R"],
              [65.0, 125.0, 65.0, 0.0, "S"]]
    groups = front_groups(edges)
    assert sorted(round(sum(math.hypot(e[2] - e[0], e[3] - e[1]) for e in m), 1)
                  for _, m in groups) == [35.0, 100.0]
    o = dimensions(
        poly, edges, [0.0, 90.0], "B",
        width_measure="side_midpoints", depth_measure="midpoints",
        front_rule="narrowest",
    )
    assert o is not None and o.front_ft == 35.0


def test_a_lot_on_a_cul_de_sac_bulb_has_one_curved_front():
    """A pie-shaped lot on a cul-de-sac: four 10 ft chords on a 38 ft
    radius (a West Linn bulb lot read 38 to 50 across its four), the side
    lot lines running out from the ends of the arc, the rear across the
    back. Every chord is short and every joint turns, and there is no long
    run anywhere to bound them: under the clip rule alone the two middle
    chords went as a corner and the lot was left two 10 ft fronts. The
    chain is smooth from end to end, so it is one front of 40 ft.
    """
    r = 38.0
    arc = [(round(r * math.cos(math.radians(a)), 3), round(r * math.sin(math.radians(a)), 3))
           for a in (120, 105, 90, 75, 60)]
    out = [(70.0, 121.24), (-70.0, 121.24)]
    poly = Polygon(arc + out)
    assert poly.is_valid
    edges = [[*arc[i], *arc[i + 1], "F"] for i in range(4)]
    edges += [[*arc[-1], *out[0], "S"], [*out[0], *out[1], "R"], [*out[1], *arc[0], "S"]]
    groups = front_groups(edges)
    assert len(groups) == 1 and len(groups[0][1]) == 4, "one curved front lot line"
    o = dimensions(
        poly, edges, [groups[0][0]], "A",
        width_measure="side_midpoints", depth_measure="average", front_rule="narrowest",
    )
    assert o is not None and o.front_ft == pytest.approx(4 * 2 * r * math.sin(math.radians(7.5)), abs=0.05)



def test_a_street_wrapped_round_a_lot_is_two_fronts_not_one_that_turns_a_corner_and_a_half():
    """A lot on the outside of a hairpin: the street line is eight chords of
    a 60 ft radius sweeping 130 degrees, with the two side lot lines running
    back to a point. Every joint turns 16 degrees and every one is on a
    wide, smooth curve, so pair by pair the chain joins -- and the one thing
    holding it to a front lot line is the sweep cap, 75 degrees end to end.

    The cap was read off the first and last chord's bearings, and bearings
    here are modulo 180: two lines 130 degrees apart are 50 degrees apart
    on that clock, and the whole wrap passed as one front. Two West Linn
    lots had their entire street line, seven and eight chords, joined into
    one 190 and 217 ft "front" that way and lost both width and depth to it.
    Summed joint by joint the sweep is 130, and the chain is two fronts: the
    first five chords stop at 65 degrees, and the last three are the other.
    """
    r = 60.0
    arc = [(round(r * math.cos(math.radians(a)), 3), round(r * math.sin(math.radians(a)), 3))
           for a in (-65 + 16.25 * i for i in range(9))]
    apex = [(-40.0, 0.0)]
    poly = Polygon(arc + apex)
    assert poly.is_valid
    edges = [[*arc[i], *arc[i + 1], "F"] for i in range(8)]
    edges += [[*arc[-1], *apex[0], "S"], [*apex[0], *arc[0], "S"]]
    groups = front_groups(edges)
    assert [len(m) for _, m in groups] == [5, 3], "the wrap breaks at the sweep cap"
    for _, members in groups:
        turns = [
            abs(math.degrees(math.atan2(b[3] - b[1], b[2] - b[0]))
                - math.degrees(math.atan2(a[3] - a[1], a[2] - a[0])))
            for a, b in zip(members, members[1:])
        ]
        assert sum(turns) <= 75.0


def test_a_corner_arc_at_the_end_of_the_street_is_still_the_clip():
    """A Portland lot: 86 ft of front, then a 13 ft chord turning fifty
    degrees, then the side lot line -- the second street lies past the 50 ft
    the edge classifier looks, so the arc has a street-facing run on one
    side only. A rule that needed a bounding run on both sides kept the
    chord and "narrowest" measured the lot to it, 13 ft wide.

    Both ways, twice. A 25 ft front on a narrow corner lot is the same
    shape -- a short street-facing run off the end of a long one, turning a
    corner -- and it is a front, because no city here plats a lot narrower.
    And a 25 ft chord turning 20 degrees, a 36 ft radius, is a bend in the
    front and joins it.
    """
    corner = Polygon([(0, 0), (100, 0), (108.36, 9.96), (108.36, 100), (0, 100)])
    edges = [
        [0, 0, 100, 0, "F"],
        [100, 0, 108.36, 9.96, "F"],       # 13 ft at 50 degrees: a 15 ft radius
        [108.36, 9.96, 108.36, 100, "S"],
        [108.36, 100, 0, 100, "R"],
        [0, 100, 0, 0, "S"],
    ]
    groups = front_groups(edges)
    assert [len(m) for _, m in groups] == [1] and groups[0][0] == pytest.approx(0.0)
    o = dimensions(
        corner, edges, [g[0] for g in groups], "A",
        width_measure="side_midpoints", depth_measure="midpoints", front_rule="narrowest",
    )
    assert o is not None and o.front_ft == pytest.approx(100.0, abs=0.05)

    narrow = Polygon([(0, 0), (25, 0), (25, 100), (0, 100)])
    edges = [
        [0, 0, 25, 0, "F"],
        [25, 0, 25, 100, "F"],
        [25, 100, 0, 100, "R"],
        [0, 100, 0, 0, "R"],
    ]
    assert sorted(round(b) for b, _ in front_groups(edges)) == [0, 90], "25 ft is a front"
    o = dimensions(
        narrow, edges, [0.0, 90.0], "A",
        width_measure="side_midpoints", depth_measure="midpoints", front_rule="narrowest",
    )
    assert o is not None and o.front_ft == 25.0 and o.depth_ft == 100.0

    bend = Polygon([(0, 0), (100, 0), (123.49, 8.55), (123.49, 100), (0, 100)])
    edges = [
        [0, 0, 100, 0, "F"],
        [100, 0, 123.49, 8.55, "F"],       # 25 ft at 20 degrees: a 36 ft radius
        [123.49, 8.55, 123.49, 100, "S"],
        [123.49, 100, 0, 100, "R"],
        [0, 100, 0, 0, "S"],
    ]
    assert [len(m) for _, m in front_groups(edges)] == [2], "one bent front"


def test_a_corner_beside_a_front_surveyed_in_short_chords_is_found_once_the_chords_are_one_run():
    """A Portland lot whose front is three chords of 10, 40 and 22 ft on a
    gentle curve, with a 13 ft corner chord turning 75 degrees at its start
    and a 26 ft second street beyond that. Every chord of the front is
    short on its own, so on the first pass the corner chord had no run
    beside it that was not short, and it stayed a candidate; joined, the
    front is 72 ft, and the corner beside it is the clip it always was.
    """
    # Front chords (from the corner, heading roughly north): 10 @ 85, 40 @ 92,
    # 22 @ 98 degrees; the corner chord at 20 degrees; the second street at
    # 145 degrees; then the side and rear.
    pts = [(0.0, 0.0)]
    for L, ang in ((26, 145), (13, 20), (10, 85), (40, 92), (22, 98)):
        x, y = pts[-1]
        pts.append((round(x + L * math.cos(math.radians(ang)), 2), round(y + L * math.sin(math.radians(ang)), 2)))
    kinds = ["F", "F", "F", "F", "F"]
    ring = pts + [(pts[-1][0] - 90, pts[-1][1]), (pts[0][0] - 90, pts[0][1])]
    poly = Polygon(ring)
    assert poly.is_valid
    edges = [[*pts[i], *pts[i + 1], k] for i, k in enumerate(kinds)]
    edges += [[*pts[-1], *ring[-2], "S"], [*ring[-2], *ring[-1], "R"], [*ring[-1], *pts[0], "S"]]
    groups = front_groups(edges)
    lens = sorted(round(sum(math.hypot(e[2] - e[0], e[3] - e[1]) for e in m)) for _, m in groups)
    assert lens == [26, 72], "the second street and the joined front; the corner chord is neither"



def test_a_corner_arc_surveyed_in_chords_is_the_clip_even_when_the_second_street_is_out_of_reach():
    """A Wilsonville lot: 79 ft of front, then a 7 ft chord turning 35
    degrees and a 19 ft chord turning 28 more -- a 24 ft radius -- and then
    the side lot line, tangent to the last chord. Its second street lies
    past the edge classifier's reach. The two chords are 26 ft together,
    over the single-chord cap, so the shape has to do the work: two or
    more chords on a circle tighter than a street bend, turning one way,
    running into the side line at a tangent.

    And the other way: a 47 ft front surveyed as 25 ft and 22 ft with a
    25 degree bend (a 51 ft radius) beside a 100 ft side street is one bent
    front, not a chord and a clip -- the first chord is not between two
    streets just because the second is the end of the run.
    """
    pts = [(0.0, 0.0), (79.0, 0.0)]
    for L, ang in ((7.0, 35.0), (19.0, 63.0)):
        x, y = pts[-1]
        pts.append((round(x + L * math.cos(math.radians(ang)), 2), round(y + L * math.sin(math.radians(ang)), 2)))
    # the side lot line leaves the last chord at 78 degrees: a 15 degree turn, a tangent
    x, y = pts[-1]
    pts.append((round(x + 100 * math.cos(math.radians(78)), 2), round(y + 100 * math.sin(math.radians(78)), 2)))
    ring = pts + [(0.0, pts[-1][1])]
    poly = Polygon(ring)
    assert poly.is_valid
    kinds = ["F", "F", "F", "S", "R", "S"]
    edges = [[*ring[k], *ring[(k + 1) % len(ring)], kinds[k]] for k in range(len(ring))]
    groups = front_groups(edges)
    assert [(round(b), len(m)) for b, m in groups] == [(0, 1)], "the front alone"

    bent = [(0.0, 0.0), (100.0, 0.0), (125.0, 0.0)]
    x, y = bent[-1]
    bent.append((round(x + 22 * math.cos(math.radians(25)), 2), round(y + 22 * math.sin(math.radians(25)), 2)))
    bent += [(bent[-1][0], 100.0), (0.0, 100.0)]
    # street down the west side (the 100 ft run), the bent front along the south
    edges = [
        [0, 100, 0, 0, "F"],
        [*bent[0], *bent[1], "F"],
        [*bent[1], *bent[2], "F"],
        [*bent[2], *bent[3], "F"],
        [*bent[3], *bent[4], "S"],
        [*bent[4], *bent[5], "R"],
    ]
    groups = front_groups(edges)
    lens = sorted((round(sum(math.hypot(e[2] - e[0], e[3] - e[1]) for e in m)), len(m)) for _, m in groups)
    assert lens == [(100, 1), (147, 3)], "the side street, and one front of 100 + 25 + 22"


def test_the_end_of_a_side_lot_line_is_not_a_front_for_lying_near_the_street():
    """A Portland lot, 62 ft of front on the south street, 206 ft deep: the
    west side lot line is surveyed in two pieces, and the classifier marks
    the 30 ft nearest the street as street-facing because it lies within
    reach of it. It continues straight into the rest of the side line and
    turns a corner into the front. "Narrowest" read it as a 30 ft front and
    measured 200 ft of width across the lot.

    Both ways: a real 30 ft front on a corner lot -- the street down its
    side, the front turning a corner into it -- continues into no lot line
    that is not street-facing, and stays.
    """
    edges = [
        [0, 0, 62.3, 0, "F"],
        [62.3, 0, 62.3, 206, "R"],
        [62.3, 206, 0, 206, "R"],
        [0, 206, 0, 30.2, "R"],
        [0, 30.2, 0, 0, "F"],
    ]
    groups = front_groups(edges)
    assert [(round(b), round(sum(math.hypot(e[2] - e[0], e[3] - e[1]) for e in m))) for b, m in groups] == [(0, 62)]

    corner = [
        [0, 0, 30, 0, "F"],
        [30, 0, 30, 100, "R"],
        [30, 100, 0, 100, "R"],
        [0, 100, 0, 0, "F"],
    ]
    assert sorted(round(b) for b, _ in front_groups(corner)) == [0, 90]

    # and a lot whose only street-facing edges are two such tails meeting
    # at its corner keeps them, because a lot has to have a front
    only = [
        [0, 0, 30, 0, "F"],
        [30, 0, 100, 0, "R"],
        [100, 0, 100, 100, "R"],
        [100, 100, 0, 100, "R"],
        [0, 100, 0, 30, "R"],
        [0, 30, 0, 0, "F"],
    ]
    assert len(front_groups(only)) == 2



def test_a_corner_still_breaks_the_run():
    """The same walk must not glue two streets together. A right-angle turn is
    a new front lot line, and a lot that reported one 140 ft front instead of a
    40 and a 100 would be measured square to neither street."""
    edges = [
        [0, 0, 40, 0, "F"],
        [40, 0, 40, 100, "S"],
        [40, 100, 0, 100, "R"],
        [0, 100, 0, 0, "F"],
    ]
    groups = front_groups(edges)
    assert len(groups) == 2
    assert sorted(round(b, 1) for b, _ in groups) == [0.0, 90.0]


def test_a_front_that_straddles_the_start_of_the_edge_list_is_still_one_front():
    """The boundary is a ring and the edge list is not. A frontage whose
    segments are the last and first entries is one street, and splitting it
    there is an artefact of where somebody started walking the polygon."""
    edges = [
        [0, 0, 30, 0, "F"],
        [30, 0, 30, 50, "S"],
        [30, 50, 0, 50, "R"],
        [0, 50, -30, 50, "R"],
        [-30, 50, -30, 0, "S"],
        [-30, 0, 0, 0, "F"],
    ]
    groups = front_groups(edges)
    assert len(groups) == 1 and len(groups[0][1]) == 2


# --- the refusals ------------------------------------------------------------


def test_a_building_line_width_needs_a_building_line():
    """Milwaukie's width is taken at the setback. Without one there is no
    building line, and measuring at the kerb instead is the exact error the
    module was written to stop -- so it is refused, loudly, by returning
    nothing at all rather than a plausible number."""
    assert dimensions(
        WEDGE, WEDGE_EDGES, [0.0], "A", width_measure="building_line"
    ) is None
    assert dimensions(
        WEDGE, WEDGE_EDGES, [0.0], "A", width_measure="setback_rectangle"
    ) is None


def test_an_irregular_or_streetless_lot_is_refused_for_depth_too():
    for tier in ("C", "D"):
        assert orientations(
            RECT, RECT_EDGES, [0.0], tier,
            width_measure="mean_width", depth_measure="average",
        ) == ()


def test_a_lot_with_no_street_edge_has_no_front_to_measure_from():
    landlocked = [
        [0, 0, 50, 0, "S"],
        [50, 0, 50, 100, "S"],
        [50, 100, 0, 100, "R"],
        [0, 100, 0, 0, "S"],
    ]
    assert front_groups(landlocked) == []
    assert orientations(
        RECT, landlocked, [], "A", depth_measure="average"
    ) == ()


def test_asking_for_nothing_measures_nothing():
    # A city that states neither a width nor a depth must not be rotated,
    # sampled and handed a pair of numbers nobody asked for.
    assert orientations(RECT, RECT_EDGES, [0.0], "A") == ()
    assert dimensions(RECT, RECT_EDGES, [0.0], "A") is None


def test_a_front_that_wobbles_between_survey_pins_still_stands_on_its_own_line():
    """A street surveyed in three chords that bow a few feet toward the lot.

    The three chords are one front lot line, and the frame puts that line on
    their mean: a horizontal line 3 ft up, with the middle chord standing
    1.5 ft above it. Troutdale's depth is one column up the middle of the
    lot, and a column is taken only where the lot stands on the front line
    -- within half a foot of it. Here, at the middle, the lot starts 1.5 ft
    above the line and, on that tolerance, stood on nothing: 288 Troutdale
    lots lost their depth the day their chords were joined into one front,
    on a rule written for a straight one. The lot stands on its front line
    as far up as the front line itself goes, and the depth is still measured
    from the mean line, so this lot is 97 ft deep and not unmeasured.
    """
    bowed = Polygon([(0, 0), (22, 4), (47, 5), (70, 0), (70, 100), (0, 100)])
    edges = [
        [0, 0, 22, 4, "F"],
        [22, 4, 47, 5, "F"],
        [47, 5, 70, 0, "F"],
        [70, 0, 70, 100, "S"],
        [70, 100, 0, 100, "R"],
        [0, 100, 0, 0, "S"],
    ]
    groups = front_groups(edges)
    assert len(groups) == 1 and len(groups[0][1]) == 3, "one bowed front of three chords"
    o = dimensions(
        bowed, edges, [groups[0][0]], "A",
        width_measure="midway_front_rear", depth_measure="mid_width",
        front_rule="applicant_choice",
    )
    assert o is not None and o.depth_ft == pytest.approx(97.0, abs=0.5)
    o = dimensions(
        bowed, edges, [groups[0][0]], "A",
        width_measure="mean_width", depth_measure="average",
        front_rule="narrowest",
    )
    assert o is not None and o.depth_ft == pytest.approx(97.0, abs=0.5)
    # A straight front has no rise, and the half-foot tolerance is all there is:
    # the far-corner column of the leaning lot below is still refused, not zero.
    frame = _frame(bowed, edges[:3], groups[0][0])
    assert frame is not None and 1.5 < frame.rise < 2.5
    assert mid_width_depth_ft(frame.rg, frame.fy, frame.fx0, frame.fx1) is None, (
        "on the straight-front tolerance alone the middle column stood on nothing"
    )


def test_a_lot_line_a_thousandth_of_a_foot_out_of_square_is_still_100_ft_deep():
    """The averaged depth must not be dragged down by a corner it cannot measure.

    Sampled at the far end of the front lot line, a lot whose side lot line
    leans inward by any amount at all is a single point wide: the vertical cut
    touches the corner and nothing else. That column has no depth to report --
    and reporting it as *zero* is the one answer that is certainly wrong, since
    the lot at that corner runs the full distance to its rear lot line.

    This was measured, not imagined. An independent implementation of the same
    MMC 19.200 sentence, written before this module existed, counts that corner
    as a zero-depth sample. Across 4,212 Milwaukie parcels the two agree to a
    median of 0.004 ft -- except on 971 of them, where this module reads higher
    by almost exactly one forty-first of the lot's depth, which is one zero in
    a mean of forty-one samples: 199.98 ft against 195.11, 202.82 against
    197.88, 100.34 against 95.46.

    So the skip is load-bearing and it is pinned here. The lot below is a plain
    100 ft deep rectangle whose left lot line is one thousandth of a foot out
    of square over its whole length -- ordinary surveyed geometry. Its depth is
    100 ft. Counting the corner would call it 97.6.
    """
    leaning = Polygon([(0, 0), (50, 0), (50, 100), (0.001, 100)])
    edges = [
        [0, 0, 50, 0, "F"],
        [50, 0, 50, 100, "S"],
        [50, 100, 0.001, 100, "R"],
        [0.001, 100, 0, 0, "S"],
    ]
    got = dimensions(leaning, edges, [0.0], "A", depth_measure="average")
    assert got is not None
    assert got.depth_ft == pytest.approx(100.0, abs=0.05)
