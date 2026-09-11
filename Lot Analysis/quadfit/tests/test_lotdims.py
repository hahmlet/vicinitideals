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

import pytest

pytest.importorskip("shapely")

from shapely.geometry import Polygon  # noqa: E402

from lotdims import (  # noqa: E402
    DEPTH_MEASURES,
    WIDTH_MEASURES,
    center_parallel_width_ft,
    dimensions,
    front_groups,
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

    A corner lot has two candidate fronts and one edge classified rear, and
    that edge is opposite only one of them. Measuring midpoint-to-midpoint from
    the other front reaches it on the diagonal, which is longer than the lot is
    in either direction and would pass a depth standard the parcel fails.

    So the rear has to face the front it is measured from. Where none does, the
    depth is refused -- which is a lot held for review, not a lot dropped.
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
    assert by_front[100.0] is None, "and refused from the front it does not"
    # 107.7 ft is the diagonal, and it is the number a rear-blind version of
    # this returns. It must not appear.
    assert 107.7 not in {round(v, 1) for v in by_front.values() if v}
    # Asked for the depth alone, the orientation that cannot supply one is not
    # reported at all -- a refusal expressed as absence rather than as a lot.
    only_depth = orientations(
        corner, edges, [0.0, 90.0], "A", depth_measure="midpoints"
    )
    assert [o.front_ft for o in only_depth] == [40.0]


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
