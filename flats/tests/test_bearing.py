"""Clackamas ZDO 1005.02(L): yards set by which way a lot line faces.

HDR, SHD and RCHDR answer their rear and side setbacks with "See Subsection
1005.02(L)": a 60-degree line off the top of the building to the north (45.03
ft for the 26 ft pod), a 15-degree one east and west (6.97 ft, owed by no line
on a public road), nothing to the south. Every lot here sits at real EPSG:2913
coordinates in Clackamas County, where true north is about a degree and a
half east of grid north, so the "both norths" sweep is exercised as it runs.
"""

from __future__ import annotations

import json
import math

import pytest
import shapely
from shapely.geometry import LineString, Point, Polygon

from flats.geom.bearing import bearing_cut, true_north_deg
from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier, bearing_deg
from flats.geom.envelope import Setbacks, buildable
from flats.rules.fields import BEARING_FIELDS, DESIGN_HEIGHT_FT, OPTIONAL_FIELDS
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

#: Clackamas Regional Center, in EPSG:2913 feet.
X0, Y0 = 7_675_000.0, 640_000.0
LAYER = "or/clackamas/_unincorporated"
NORTH = round(DESIGN_HEIGHT_FT * math.tan(math.radians(60)), 3)
EAST_WEST = round(DESIGN_HEIGHT_FT * math.tan(math.radians(15)), 3)


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def edge(x1: float, y1: float, x2: float, y2: float, cls: EdgeClass, *, road: bool = False) -> Edge:
    return Edge(
        x1, y1, x2, y2,
        length_ft=math.hypot(x2 - x1, y2 - y1),
        bearing_deg=bearing_deg(x1, y1, x2, y2),
        cls=cls,
        public_road=road,
    )


def ring_edges(lot: Polygon, classes: list[EdgeClass], roads: set[int] = frozenset()) -> tuple[Edge, ...]:
    xy = list(lot.exterior.coords)
    return tuple(
        edge(*xy[i], *xy[i + 1], classes[i], road=i in roads) for i in range(len(xy) - 1)
    )


def owes(env, lot: Polygon, north_ft: float, east_west_ft: float, az: float = 0.0) -> bool:
    """The defining property, checked point by point on the envelope's
    boundary: the ground from the building to ``north_ft`` north of it, and
    ``east_west_ft`` east and west, is all on the lot."""
    r = math.radians(az)
    n = (math.sin(r), math.cos(r))
    e = (math.cos(r), -math.sin(r))
    grown = lot.buffer(0.01)
    for poly in shapely.get_parts(env):
        for x, y in poly.exterior.coords:
            if north_ft > 0 and not grown.contains(
                LineString([(x, y), (x + north_ft * n[0], y + north_ft * n[1])])
            ):
                return False
            if east_west_ft > 0 and not grown.contains(
                LineString(
                    [(x - east_west_ft * e[0], y - east_west_ft * e[1]),
                     (x + east_west_ft * e[0], y + east_west_ft * e[1])]
                )
            ):
                return False
    return True


# --- the encoding -------------------------------------------------------------


def test_the_fields_are_optional_lengths_and_the_angle_is_off_the_vertical() -> None:
    assert BEARING_FIELDS == {"setback_north_ft", "setback_east_west_ft"}
    assert BEARING_FIELDS <= OPTIONAL_FIELDS
    # "Separation = b x .267 (tan 15 degrees)": the height times the tangent.
    assert EAST_WEST == pytest.approx(DESIGN_HEIGHT_FT * 0.267, abs=0.05)  # .267 is tan 15 rounded
    assert NORTH == pytest.approx(DESIGN_HEIGHT_FT * 1.732, abs=0.01)


def test_hdr_resolves_the_bearing_separations_and_side_and_rear_borrow_the_north(rules) -> None:
    for zone in ("HDR", "SHD", "RTL", "CC", "C3", "OC"):
        got = rules.resolve(LAYER, zone)
        assert got.get("setback_north_ft") == NORTH, zone
        assert got.get("setback_east_west_ft") == EAST_WEST, zone
        assert got.get("setback_north_street_credit_ft") == 15, zone
        # A reader that knows no bearing takes the north figure on every line.
        for yard in ("setback_side_ft", "setback_rear_ft"):
            assert got.get(yard) == NORTH, (zone, yard)
            assert got.values[yard].same_as == "setback_north_ft"
            assert got.values[yard].floor_ft is None
        assert got.get("setback_front_ft") == 15
        assert got.get("min_lot_sqft") == 7000
        assert "max_height_ft" in got.exempted
        assert got.missing_required == ()


def test_rchdr_floors_its_rear_and_side_and_the_regional_center_borrows_it(rules) -> None:
    for zone in ("RCHDR", "RCC", "RCO"):
        got = rules.resolve(LAYER, zone)
        assert got.values["setback_rear_ft"].floor_ft == 20, zone
        assert got.values["setback_side_ft"].floor_ft == 15, zone
        assert got.get("setback_front_ft") == 15, zone  # note 8, not the cell's 5


def test_the_review_ruling_is_not_this_branchs(rules) -> None:
    """The use is permitted in every one of these districts and each stands
    RED BY RULING for design review, as its siblings do; the review tiers
    are another branch's (e0) to set."""
    for zone in ("HDR", "SHD", "RCHDR", "RTL", "CC", "C3", "OC", "RCC", "RCO"):
        got = rules.resolve(LAYER, zone)
        assert got.get("quadplex_allowed") is False, zone
        assert "1102.01" in got.values["quadplex_allowed"].prov.cite, zone


def test_vth_stays_held_on_the_column_read_alone(rules) -> None:
    layer = rules.layers[LAYER]
    vth = layer.zone_rulings["VTH"]
    assert vth.outcome == "unencodable"
    assert "HUMAN_TODO 15" in vth.note
    for zone in ("SHD", "RCHDR", "RTL", "CC", "C3", "OC", "RCC", "RCO"):
        assert zone not in layer.zone_rulings


def test_an_angle_off_the_top_belongs_to_a_bearing_field_only() -> None:
    from flats.rules.model import Provenance, Value

    prov = Provenance(
        cite="Clackamas ZDO 1005.02(L)(1)",
        url="https://www.clackamas.us/planning/zdo1005",
        retrieved="2026-10-14",
        quote="or/clackamas/_unincorporated/zdo.1005.txt#L145",
    )
    Value(name="setback_north_ft", value=NORTH, from_top_degrees=60, prov=prov)
    with pytest.raises(ValueError, match="from_top_degrees"):
        Value(name="setback_rear_ft", value=NORTH, from_top_degrees=60, prov=prov)


def test_readiness_checks_the_printed_angle_not_the_distance(rules) -> None:
    from flats.encode.readiness import _printed

    north = rules.layers[LAYER].zones["HDR"].values["setback_north_ft"]
    assert _printed(north) == 60
    rear = rules.layers[LAYER].zones["RCHDR"].values["setback_rear_ft"]
    assert _printed(rear) == 20


def test_the_height_dial_reads_the_angle(monkeypatch) -> None:
    from flats.encode import height

    # The districts are red by ruling today, and the dial reads only zones
    # that take the building; asked as if they did.
    monkeypatch.setattr(height, "_permits", lambda zone: True)
    got = [d for d in height.derived() if d.layer == LAYER and d.field == "setback_north_ft"]
    assert got, "the north separation is a setback computed from the height"
    for d in got:
        assert d.at(DESIGN_HEIGHT_FT) == pytest.approx(NORTH, abs=0.001)
        # Taller building, longer shadow.
        assert d.at(30.0) == pytest.approx(30.0 * math.tan(math.radians(60)), abs=0.001)


# --- the cut -----------------------------------------------------------------


def test_true_north_is_east_of_grid_north_in_clackamas() -> None:
    # West of the projection's central meridian (120.5 W) the meridians lean
    # in toward it going north, so true north points east of grid north.
    got = true_north_deg(X0, Y0)
    assert 1.0 < got < 2.0


def test_an_east_west_lot_owes_45_on_its_north_line_and_7_on_its_ends() -> None:
    # 200 ft east-west, 100 ft deep, the street on the south.
    lot = shapely.box(X0, Y0, X0 + 200, Y0 + 100)
    F, S, R = EdgeClass.front, EdgeClass.side, EdgeClass.rear
    # box() rings run counter-clockwise from the south-east corner:
    # east line, north line, west line, south line.
    edges = LotEdges(Tier.clean, ring_edges(lot, [S, R, S, F], roads={3}), (90.0,), 200.0, 1.0)
    setbacks = Setbacks(front_ft=15, north_ft=NORTH, east_west_ft=EAST_WEST, north_street_credit_ft=15)
    env = buildable(lot, edges, setbacks)
    minx, miny, maxx, maxy = env.bounds
    assert maxy == pytest.approx(Y0 + 100 - NORTH, abs=0.01)
    assert miny == pytest.approx(Y0 + 15, abs=0.01)
    assert minx == pytest.approx(X0 + EAST_WEST, abs=0.01)
    assert maxx == pytest.approx(X0 + 200 - EAST_WEST, abs=0.01)
    assert owes(env, lot, NORTH, EAST_WEST)
    # Turn the same lot so its long side faces east: the 45 ft lands on a
    # 100 ft line, and the envelope is deeper than it is wide.
    tall = shapely.box(X0, Y0, X0 + 100, Y0 + 200)
    turned = LotEdges(Tier.clean, ring_edges(tall, [S, R, S, F], roads={3}), (90.0,), 100.0, 1.0)
    env2 = buildable(tall, turned, setbacks)
    assert env2.area == pytest.approx((100 - 2 * EAST_WEST) * (200 - 15 - NORTH), rel=1e-6)
    assert env.area == pytest.approx((200 - 2 * EAST_WEST) * (100 - 15 - NORTH), rel=1e-6)


def test_a_street_on_the_north_counts_15_ft_and_a_road_owes_no_east_west() -> None:
    # The street is on the NORTH and on the EAST: a corner lot whose front
    # faces north. The north line owes 45 - 15; the east line, on a public
    # road, owes no east-west separation; the west line owes 7.
    lot = shapely.box(X0, Y0, X0 + 120, Y0 + 100)
    F, SS, S, R = EdgeClass.front, EdgeClass.street_side, EdgeClass.side, EdgeClass.rear
    edges = LotEdges(
        Tier.corner, ring_edges(lot, [SS, F, S, R], roads={0, 1}), (90.0, 0.0), 220.0, 1.0
    )
    setbacks = Setbacks(
        front_ft=0, street_side_ft=0, north_ft=NORTH, east_west_ft=EAST_WEST,
        north_street_credit_ft=15,
    )
    env = buildable(lot, edges, setbacks)
    minx, _miny, maxx, maxy = env.bounds
    assert maxy == pytest.approx(Y0 + 100 - (NORTH - 15), abs=0.01)
    assert maxx == pytest.approx(X0 + 120, abs=0.01)
    assert minx == pytest.approx(X0 + EAST_WEST, abs=0.01)
    # The same lot with the roads unread (a private drive, or s4 recorded no
    # kind): no relief anywhere.
    unread = LotEdges(Tier.corner, ring_edges(lot, [SS, F, S, R]), (90.0, 0.0), 220.0, 1.0)
    env2 = buildable(lot, unread, setbacks)
    assert env2.bounds[3] == pytest.approx(Y0 + 100 - NORTH, abs=0.01)
    assert env2.bounds[2] == pytest.approx(X0 + 120 - EAST_WEST, abs=0.01)


def test_a_diagonal_lot_is_cut_by_component() -> None:
    # A 100 ft square turned 45 degrees: every line faces a diagonal. The
    # north-east and north-west lines owe the north separation's component
    # square to them, 45.03 x cos 45 = 31.84; the east-west separation's
    # component is 7 x sin 45 = 4.93, which the north one swamps.
    c = Point(X0, Y0)
    lot = shapely.affinity.rotate(shapely.box(X0 - 50, Y0 - 50, X0 + 50, Y0 + 50), 45, origin=c)
    edges = LotEdges(Tier.clean, (), (), 0.0, 1.0)
    setbacks = Setbacks(north_ft=NORTH, east_west_ft=EAST_WEST)
    cut = bearing_cut(lot, edges.edges, north_ft=NORTH, east_west_ft=EAST_WEST)
    env = lot.difference(cut)
    assert owes(env, lot, NORTH, EAST_WEST)
    xy = list(lot.exterior.coords)
    for (x1, y1), (x2, y2) in zip(xy, xy[1:]):
        line = LineString([(x1, y1), (x2, y2)])
        mid = ((x1 + x2) / 2, (y1 + y2) / 2)
        faces_north = mid[1] > Y0
        expect = NORTH * math.cos(math.radians(45)) if faces_north else EAST_WEST * math.sin(math.radians(45))
        assert env.distance(line) == pytest.approx(expect, abs=0.01)
    # And through buildable, at real coordinates: the same ground.
    assert buildable(lot, edges, setbacks).area == pytest.approx(env.area, rel=1e-9)


def test_a_curved_north_line_is_cut_one_segment_at_a_time() -> None:
    # A lot whose north line is an arc bulging north (a lot on the outside of
    # a curve): 24 segments. Each owes the separation by its own facing, so
    # the envelope's top follows the arc down by 45 ft, flattening to nothing
    # owed where the arc turns to face east and west.
    arc = [
        (X0 + 60 + 60 * math.cos(math.radians(a)), Y0 + 80 + 40 * math.sin(math.radians(a)))
        for a in [i * 180 / 24 for i in range(25)]
    ]
    lot = Polygon([(X0, Y0), (X0 + 120, Y0), *arc])
    cut = bearing_cut(lot, (), north_ft=NORTH, east_west_ft=EAST_WEST)
    env = lot.difference(cut)
    assert not env.is_empty
    assert owes(env, lot, NORTH, EAST_WEST)
    # Maximal, not merely safe: a point just inside the cut, under the
    # crown, is one the code would refuse, and just outside it one it allows.
    crown = Y0 + 80 + 40
    assert env.contains(Point(X0 + 60, crown - NORTH - 0.5))
    assert not env.buffer(-0.01).contains(Point(X0 + 60, crown - NORTH + 0.5))


def test_both_norths_are_swept_and_neither_is_looser() -> None:
    lot = shapely.box(X0, Y0, X0 + 100, Y0 + 100)
    tn = true_north_deg(X0, Y0)
    grid = lot.difference(bearing_cut(lot, (), north_ft=NORTH, east_west_ft=0))
    both = lot.difference(bearing_cut(lot, (), north_ft=NORTH, east_west_ft=0, true_north=tn))
    assert owes(both, lot, NORTH, 0, az=0.0)
    assert owes(both, lot, NORTH, 0, az=tn)
    assert both.area < grid.area
    assert both.within(grid.buffer(0.01))


def test_a_south_line_owes_nothing() -> None:
    lot = shapely.box(X0, Y0, X0 + 100, Y0 + 100)
    env = lot.difference(bearing_cut(lot, (), north_ft=NORTH, east_west_ft=0))
    assert env.bounds[1] == pytest.approx(Y0, abs=1e-6)


def test_an_irregular_lot_takes_the_sweep_on_top_of_the_uniform_buffer() -> None:
    lot = shapely.box(X0, Y0, X0 + 150, Y0 + 120)
    edges = LotEdges(Tier.irregular, (), (), 0.0, 1.0)
    env = buildable(lot, edges, Setbacks(front_ft=10, side_ft=0, rear_ft=0, north_ft=NORTH))
    assert env.bounds[3] == pytest.approx(Y0 + 120 - NORTH, abs=0.01)
    assert env.bounds[1] == pytest.approx(Y0 + 10, abs=0.01)


def test_a_zone_without_the_fields_is_cut_as_before() -> None:
    lot = shapely.box(X0, Y0, X0 + 50, Y0 + 100)
    F, S, R = EdgeClass.front, EdgeClass.side, EdgeClass.rear
    edges = LotEdges(Tier.clean, ring_edges(lot, [S, R, S, F]), (90.0,), 50.0, 1.0)
    env = buildable(lot, edges, Setbacks(front_ft=10, side_ft=5, rear_ft=15))
    assert env.area == pytest.approx(40 * 75)


# --- the bridge ----------------------------------------------------------------


def bridge_row(lot: Polygon, letters: list[str], kinds: list[str | None]) -> dict[str, object]:
    from flats.tests.test_quadfit_bridge import row

    xy = list(lot.exterior.coords)
    raw = [[*xy[i], *xy[i + 1], letters[i]] for i in range(len(xy) - 1)]
    return row(
        jurisdiction="clackamas_unincorporated",
        zone="HDR",
        edges_json=json.dumps(raw),
        street_kind_json=json.dumps(kinds),
        lot_wkb=shapely.to_wkb(lot),
        wkb=shapely.to_wkb(lot),
        area_sqft=lot.area,
    )


def test_the_bridge_cuts_hdr_by_bearing_and_charges_the_court_against_the_rear_it_lost(rules) -> None:
    from flats.ingest.quadfit import envelope_for, lot_edges, lot_from_row, setbacks_for

    got = rules.resolve(LAYER, "HDR")
    s = setbacks_for(got)
    assert (s.side_ft, s.rear_ft) == (0.0, 0.0)  # the stand-in gives way
    assert (s.north_ft, s.east_west_ft, s.north_street_credit_ft) == (NORTH, EAST_WEST, 15)

    # 120 x 160, the street on the south: the rear line faces north and the
    # sweep takes 45 ft off it, which is the strip the court is charged
    # against.
    lot = shapely.box(X0, Y0, X0 + 120, Y0 + 160)
    r = bridge_row(lot, ["S", "R", "S", "F"], [None, None, None, "street"])
    edges = lot_edges(r, lot)
    assert [e.public_road for e in edges.edges] == [False, False, False, True]
    env = envelope_for(lot_from_row(r), got)
    assert env.source == "flats"
    assert env.rear_cut_ft == pytest.approx(NORTH, abs=0.05)
    assert env.setbacks.true_north_deg == pytest.approx(true_north_deg(*lot.centroid.coords[0]))
    assert owes(env.geom, lot, NORTH, EAST_WEST, az=0.0)
    assert owes(env.geom, lot, NORTH, EAST_WEST, az=env.setbacks.true_north_deg)
    # The court is parking, not a structure: (L) does not reach its ground.
    assert env.ground.bounds[3] == pytest.approx(Y0 + 160, abs=0.01)

    # The street on the NORTH: the rear now faces south and owes nothing,
    # so the court is charged in full.
    flipped = bridge_row(lot, ["S", "F", "S", "R"], [None, "street", None, None])
    env2 = envelope_for(lot_from_row(flipped), got)
    # All but the east-west separation's share along true north, which leans
    # a degree and a half off the line: 6.97 x sin 1.46 = 0.18 ft.
    assert env2.rear_cut_ft == pytest.approx(0.0, abs=0.2)
    assert env2.geom.bounds[3] == pytest.approx(Y0 + 160 - max(15.0, NORTH - 15), abs=0.05)


def test_rchdr_keeps_its_floors_under_the_sweep(rules) -> None:
    from flats.ingest.quadfit import setbacks_for

    s = setbacks_for(rules.resolve(LAYER, "RCHDR"))
    assert (s.side_ft, s.rear_ft) == (15.0, 20.0)
    assert s.north_ft == NORTH
