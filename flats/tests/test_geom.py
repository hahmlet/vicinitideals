"""Edge naming and the buildable envelope.

The through-line: every guess this code makes is made in the direction that
costs a review rather than a lot. An unrecognizable shape gets a smaller
envelope than it deserves, a corner lot gets the stricter of two setbacks, and
a lot with no street found is kept and flagged rather than dropped — that last
one is the exact failure the predecessor pipeline shipped.
"""

from __future__ import annotations

import pytest

shapely = pytest.importorskip("shapely")

from shapely.geometry import LineString, MultiPolygon, Point, Polygon  # noqa: E402

from flats.fit import Fitter  # noqa: E402
from flats.geom import (  # noqa: E402
    EdgeClass,
    Setbacks,
    StreetIndex,
    Tier,
    bearing_deg,
    bearing_delta,
    buildable,
    classify,
    cluster_bearings,
)

pytestmark = pytest.mark.unit

#: 60 ft of frontage, 100 ft deep, south edge on y = 0.
LOT = shapely.box(0, 0, 60, 100)
#: A street centerline 30 ft south of the lot — about half a local ROW.
SOUTH_ST = LineString([(-50, -30), (110, -30)])
WEST_ST = LineString([(-30, -50), (-30, 150)])

THRESHOLD = 40.0


def named(lot=LOT, streets=(SOUTH_ST,), threshold: float = THRESHOLD):
    return classify(lot, StreetIndex(list(streets)), street_threshold_ft=threshold)


# --- bearings ---------------------------------------------------------


@pytest.mark.parametrize(
    ("coords", "expected"),
    [((0, 0, 1, 0), 0.0), ((0, 0, 0, 1), 90.0), ((0, 0, -1, 0), 0.0), ((0, 0, 1, 1), 45.0)],
)
def test_a_lot_line_has_no_front_and_back(coords, expected) -> None:
    # Bearings fold into [0, 180): which way you walk the boundary is an
    # artifact of the polygon's winding, not a fact about the parcel.
    assert bearing_deg(*coords) == pytest.approx(expected)


def test_the_angle_between_two_directions_wraps() -> None:
    assert bearing_delta(10.0, 170.0) == pytest.approx(20.0)
    assert bearing_delta(0.0, 90.0) == pytest.approx(90.0)


def test_a_jog_in_the_curb_is_not_a_second_street() -> None:
    # Length weighting is what makes this hold: a two-foot kink cannot outvote
    # fifty-eight feet of frontage.
    assert len(cluster_bearings([(0.0, 58.0), (12.0, 2.0)])) == 1


def test_two_real_street_directions_stay_apart() -> None:
    assert len(cluster_bearings([(0.0, 60.0), (90.0, 100.0)])) == 2


def test_the_widest_frontage_is_named_first() -> None:
    # The primary street anchors the rotation search, so its bearing leads.
    assert cluster_bearings([(0.0, 60.0), (90.0, 100.0)])[0] == pytest.approx(90.0)


# --- naming the edges -------------------------------------------------


def test_the_edge_facing_the_street_is_the_front() -> None:
    edges = named()

    fronts = edges.of_class(EdgeClass.front)
    assert len(fronts) == 1
    assert fronts[0].bearing_deg == pytest.approx(0.0)
    assert edges.frontage_ft == pytest.approx(60.0)


def test_the_opposite_line_is_the_rear_and_the_others_are_sides() -> None:
    edges = named()

    assert len(edges.of_class(EdgeClass.rear)) == 1
    assert len(edges.of_class(EdgeClass.side)) == 2


def test_a_plain_rectangular_lot_is_trusted() -> None:
    e = named()

    assert e.tier is Tier.clean
    assert e.front_bearings == (0.0,)
    assert e.convexity == pytest.approx(1.0)


def test_two_streets_make_a_corner() -> None:
    e = named(streets=(SOUTH_ST, WEST_ST))

    assert e.tier is Tier.corner
    assert len(e.front_bearings) == 2


def test_a_street_beyond_the_threshold_is_not_frontage() -> None:
    assert named(threshold=10.0).tier is Tier.landlocked


def test_a_lot_with_no_street_is_kept_not_dropped() -> None:
    # The failure this project exists to prevent. No street nearby may mean
    # landlocked or may mean the street layer has a hole, and from here those
    # are indistinguishable — so the lot survives with a flag on it.
    e = named(streets=())

    assert e.tier is Tier.landlocked
    assert e.landlocked
    assert len(e.edges) == 4, "the boundary is still described"
    assert all(edge.cls is EdgeClass.side for edge in e.edges)


def test_an_empty_street_index_answers_rather_than_crashing() -> None:
    assert StreetIndex([]).distance(Point(0, 0)) == float("inf")
    assert len(StreetIndex([])) == 0


def test_a_concave_lot_is_not_trusted() -> None:
    # An L. Per-edge setback strips on a shape like this leave wedges that are
    # not really buildable, so it drops to the conservative construction.
    ell = Polygon([(0, 0), (60, 0), (60, 30), (30, 30), (30, 100), (0, 100)])

    e = named(lot=ell)

    assert e.tier is Tier.irregular
    assert e.convexity < 0.80


def test_a_flag_lot_is_not_trusted() -> None:
    # Body plus a ten-foot driveway pole. Its "frontage" is the driveway, and
    # setbacks measured off it would be meaningless.
    flag = Polygon(
        [(0, 60), (60, 60), (60, 160), (0, 160), (0, 70), (25, 70), (25, 0), (35, 0), (35, 60)]
    )

    assert named(lot=flag).tier is Tier.irregular


# --- cutting the envelope ---------------------------------------------


SETBACKS = Setbacks(front_ft=10, side_ft=5, rear_ft=5)


def test_setbacks_come_off_the_named_edges() -> None:
    env = buildable(LOT, named(), SETBACKS)

    assert env.bounds == pytest.approx((5.0, 10.0, 55.0, 95.0))
    assert env.area == pytest.approx(50 * 85)


def test_no_setbacks_leaves_the_whole_lot() -> None:
    env = buildable(LOT, named(), Setbacks())

    assert env.area == pytest.approx(LOT.area)


def test_setbacks_can_consume_the_lot() -> None:
    # A real answer on a small lot, not an error. It flows through as a fit of
    # zero rather than an exception.
    env = buildable(LOT, named(), Setbacks(front_ft=60, side_ft=40, rear_ft=60))

    assert env.is_empty


def test_a_corner_lot_takes_the_stricter_street_setback() -> None:
    # Geometry cannot say which street line is legally the front, so both take
    # the larger standard. The envelope is smaller than either reading alone.
    corner = named(streets=(SOUTH_ST, WEST_ST))
    strict = Setbacks(front_ft=10, side_ft=5, rear_ft=5, street_side_ft=15)

    env = buildable(LOT, corner, strict)

    assert env.area < buildable(LOT, corner, Setbacks(front_ft=10, side_ft=5, rear_ft=5)).area


def test_a_street_side_standard_only_matters_on_a_corner() -> None:
    plain = Setbacks(front_ft=10, side_ft=5, rear_ft=5, street_side_ft=15)

    assert buildable(LOT, named(), plain).area == pytest.approx(50 * 85)


def test_an_untrusted_shape_gets_the_conservative_envelope() -> None:
    # Uniform shrink by the largest setback. Smaller than a per-edge cut would
    # give, which is the point: on a shape nobody can read, an envelope that is
    # too big produces false GREENs on the least reviewable lots.
    ell = Polygon([(0, 0), (60, 0), (60, 30), (30, 30), (30, 100), (0, 100)])
    edges = named(lot=ell)
    assert edges.tier is Tier.irregular

    env = buildable(ell, edges, SETBACKS)

    assert not env.is_empty
    assert env.area < ell.buffer(-5).area


def test_slivers_are_dropped_from_the_envelope() -> None:
    env = buildable(LOT, named(), SETBACKS, min_part_sqft=50_000)

    assert env.is_empty


def test_an_empty_lot_yields_an_empty_envelope() -> None:
    assert buildable(Polygon(), named(), SETBACKS).is_empty
    assert buildable(None, named(), SETBACKS) == MultiPolygon([])


def test_setbacks_report_their_worst_number() -> None:
    assert Setbacks(front_ft=10, side_ft=5, rear_ft=5, street_side_ft=15).largest_ft == 15
    assert Setbacks(front_ft=20, side_ft=5, rear_ft=5).largest_ft == 20


def test_a_corner_adjustment_is_a_no_op_without_a_street_side_standard() -> None:
    plain = Setbacks(front_ft=10, side_ft=5, rear_ft=5)

    assert plain.on_a_corner() is plain


# --- the chain: lot to verdict input ----------------------------------


def test_a_lot_becomes_an_envelope_becomes_a_fit() -> None:
    # End to end on one parcel: 60x100 lot, street to the south, 10/5/5
    # setbacks leave a 50x85 envelope. A 56x36 pod will not face the street
    # here — 56 ft of width does not fit in 50 — but turned sideways it does.
    env = buildable(LOT, named(), SETBACKS)

    fit = Fitter(env, (0.0,), res=0.5).fit(56, 36)

    assert fit.fits
    assert fit.orientation.value == "depth_facing"
    assert env.buffer(0.01).contains(fit.placement)


def test_a_street_facing_requirement_can_cost_the_lot() -> None:
    # Same parcel, same envelope. If the pod must face the street, it is out —
    # and the margin says by how much, which is what makes it arguable.
    env = buildable(LOT, named(), SETBACKS)

    fit = Fitter(env, (0.0,), res=0.5).fit(56, 36, allow_flip=False)

    assert not fit.fits
    assert fit.best_depth_ft == 0.0
