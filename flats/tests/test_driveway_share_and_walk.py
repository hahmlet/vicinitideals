"""Two driveway rules the Washington drafts could only describe (FOLLOWUPS 17(b)).

- **Sherwood 16.14.030 A.2**: "Total width of all driveways shall not exceed
  50 percent of the street frontage." `driveway_max_frontage_pct`, checked
  against the pod's one drive where it meets the street. The pod's 12 ft
  lane needs 24 ft of frontage; the zones allow 25.
- **Durham 3.7.1.6**: an access way "shall include a pedestrian access on
  one side at least an additional 5 feet wide". `driveway_walkway_ft`, added
  to the lane beside the building; beside a court whose aisle is the way in,
  the standoff off the wall is already a walk, so the wider of the two.

And one ruling that narrows the drive rather than widening it:
``driveway_one_lane_ft``, a single lane to the court, cars taking turns
(Tigard TMU, Steph 2026-10-01). It governs outright, below the pod's lane
or above it, and the two-way minimum is not read beside it.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("shapely")

from flats.designs.model import load_catalog  # noqa: E402
from flats.fit.rectangle import Fit  # noqa: E402
from flats.rules.loader import load_rules  # noqa: E402
from flats.rules.model import Provenance, Status  # noqa: E402
from flats.rules.resolver import Resolved, ZoneResolution  # noqa: E402
from flats.rules.resolver import Verdict as RuleVerdict  # noqa: E402
from flats.score.paper import court_across, drive_at_street, side_court  # noqa: E402
from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier as GeometryTier  # noqa: E402
from flats.score.screen import CHECK_FIELD, LotFacts, _driveway_cap_frontages, screen  # noqa: E402
from flats.score.slack import SlackPolicy, Verdict  # noqa: E402

pytestmark = pytest.mark.unit

WHERE = "or/washington/somewhere"
PROV = Provenance(cite="test", url="https://example.invalid", retrieved=date(2026, 9, 30))
POLICY = SlackPolicy(tolerance={"fit_ft": 0.5})
DESIGN = load_catalog().latest("pod56x36")

CLEAR = {
    "quadplex_allowed": True,
    "min_lot_sqft": 3000,
    "setback_front_ft": 10,
    "setback_rear_ft": 10,
    "setback_side_ft": 5,
    "min_frontage_ft": 20,
    "min_lot_width_ft": 20,
    "max_coverage_pct": 60,
    "max_far": 2.0,
    "max_height_ft": 60,
    "max_units": 4,
    "parking_min_per_unit": 1.0,
}


def rules(**overrides) -> ZoneResolution:
    jurisdiction = overrides.pop("jurisdiction", WHERE)
    values = {**CLEAR, **overrides}
    return ZoneResolution(
        jurisdiction=jurisdiction,
        zone="R-6",
        verdict=RuleVerdict.trusted,
        values={
            name: Resolved(
                name=name, value=value, status=Status.verified, prov=PROV,
                layer=WHERE, origin="zone",
            )
            for name, value in values.items()
            if value is not None
        },
    )


def fit(lane: float) -> Fit:
    depth_ft = 36.0
    best = depth_ft + DESIGN.parking.court_depth_ft + 4.0
    return Fit(
        fits=True, width_ft=56.0, depth_ft=depth_ft, best_depth_ft=best,
        slack_ft=best - depth_ft,
        across_ft=max(56.0 + lane, DESIGN.court_width_ft),
    )


def share_screen(lot: LotFacts, **extra):
    zone = rules(driveway_max_frontage_pct=50, **extra)
    lane = court_across(DESIGN, zone).lane_ft
    return screen(
        zone, lot,
        DESIGN, fit(lane), policy=POLICY,
    )


def share_lot(lot: LotFacts, **extra):
    result = share_screen(lot, **extra)
    return next((c for c in result.checks if c.check == "driveway_frontage_share"), None)


def share(frontage: float, **extra):
    return share_lot(
        LotFacts(lot_sqft=12000, frontage_ft=frontage, lot_width_ft=frontage),
        **extra,
    )


def test_the_share_is_a_check_that_names_its_field() -> None:
    assert CHECK_FIELD["driveway_frontage_share"] == "driveway_max_frontage_pct"


def test_the_lowest_class_driveway_uses_its_own_street_frontage() -> None:
    # A short side-street line is not the frontage crossed by the drive.
    lot = LotFacts(
        lot_sqft=12000,
        frontage_ft=162.9,
        lot_width_ft=139.9,
        street_line_min_ft=23.0,
        street_line_max_ft=139.9,
        street_lines_ft=(23.0, 139.9),
        street_line_ranks=(4, 0),
    )
    got = share_lot(lot, corner_access_street="lowest_class")
    assert got is not None and got.verdict is Verdict.passes


def test_a_short_lowest_class_street_frontage_still_fails_the_cap() -> None:
    lot = LotFacts(
        lot_sqft=12000,
        frontage_ft=23.0,
        lot_width_ft=23.0,
        street_line_min_ft=23.0,
        street_line_max_ft=23.0,
        street_lines_ft=(23.0,),
        street_line_ranks=(0,),
    )
    got = share_lot(lot, corner_access_street="lowest_class")
    assert got is not None and got.verdict is Verdict.fails


def test_unranked_frontages_do_not_assume_the_shortest_is_the_driveway_street() -> None:
    lot = LotFacts(
        lot_sqft=12000,
        frontage_ft=162.9,
        lot_width_ft=139.9,
        street_line_min_ft=23.0,
        street_line_max_ft=139.9,
        street_lines_ft=(23.0, 139.9),
        street_line_ranks=(None, None),
    )
    assert share_lot(lot, corner_access_street="lowest_class") is None


def test_private_drive_line_is_the_cap_frontage_without_measured_streets() -> None:
    from flats.ingest.quadfit import private_drive_lines_ft

    private = Edge(0, 0, 70, 0, 70, 0, EdgeClass.front, road_private=True)
    private_continuation = Edge(70, 0, 139.9, 0, 69.9, 0, EdgeClass.front, road_private=True)
    other = Edge(139.9, 0, 139.9, 20, 20, 90, EdgeClass.side)
    edges = LotEdges(
        tier=GeometryTier.irregular,
        edges=(private, private_continuation, other),
        front_bearings=(),
        frontage_ft=139.9,
        convexity=0.5,
    )
    lot = LotFacts(
        lot_sqft=12000,
        frontage_ft=139.9,
        street_line_min_ft=23.1,
        geometry=GeometryTier.irregular,
        private_drive_lines_ft=private_drive_lines_ft(edges),
    )
    result = share_screen(
        lot,
        jurisdiction="or/clackamas/happy-valley",
        driveway_min_width_two_way_ft=20,
    )
    cap = next(c for c in result.checks if c.check == "driveway_frontage_share")
    assert lot.street_lines_ft == ()
    assert lot.private_drive_lines_ft == pytest.approx((139.9,))
    assert cap.verdict is Verdict.passes
    assert cap.threshold == pytest.approx(69.95)
    assert "GEOM-UNREADABLE" in {flag.code for flag in result.flags}


def test_no_private_drive_line_keeps_the_unmeasured_frontage_fallback() -> None:
    lot = LotFacts(
        lot_sqft=12000,
        frontage_ft=139.9,
        street_line_min_ft=23.1,
        geometry=GeometryTier.irregular,
    )
    result = share_screen(
        lot,
        jurisdiction="or/clackamas/happy-valley",
        driveway_min_width_two_way_ft=20,
    )
    cap = next(c for c in result.checks if c.check == "driveway_frontage_share")
    assert _driveway_cap_frontages(rules(jurisdiction="or/clackamas/happy-valley"), lot) == (
        23.1,
    )
    assert cap.verdict is Verdict.fails
    assert cap.threshold == pytest.approx(11.55)


def test_private_drive_fallback_is_limited_to_the_three_bound_cities() -> None:
    lot = LotFacts(
        lot_sqft=12000,
        frontage_ft=139.9,
        street_line_min_ft=23.1,
        private_drive_lines_ft=(139.9,),
    )
    assert _driveway_cap_frontages(rules(), lot) == (23.1,)


def test_measured_street_line_is_capped_at_the_lots_frontage() -> None:
    lot = LotFacts(
        lot_sqft=12000,
        frontage_ft=100.0,
        street_line_min_ft=100.02,
        street_line_max_ft=100.02,
        street_lines_ft=(100.02,),
    )
    cap = share_lot(
        lot,
        driveway_min_width_two_way_ft=20,
    )
    assert _driveway_cap_frontages(rules(), lot) == (100.0,)
    assert cap is not None and cap.threshold == 50.0


def test_the_pods_lane_needs_twice_its_width_of_frontage() -> None:
    lane = DESIGN.parking.lane_ft
    assert share(2 * lane + 1).verdict is Verdict.passes
    assert share(2 * lane - 3).verdict is Verdict.fails


def test_a_wider_stated_drive_needs_more_frontage() -> None:
    # A 20 ft two-way drive on a 30 ft frontage takes two thirds of it.
    assert share(30, driveway_min_width_two_way_ft=20).verdict is Verdict.fails
    assert share(40, driveway_min_width_two_way_ft=20).verdict is Verdict.passes


def test_no_driveway_to_the_street_is_nothing_to_share() -> None:
    zone = rules(parking_alley_access_required=True)
    from flats.score.paper import Alley

    alley = Alley(at_rear=True, width_ft=20.0)
    assert drive_at_street(DESIGN, zone, alley) == 0.0


def test_the_walk_widens_the_lane_beside_the_building() -> None:
    plain = court_across(DESIGN, rules(driveway_min_width_two_way_ft=30)).lane_ft
    walked = court_across(
        DESIGN, rules(driveway_min_width_two_way_ft=30, driveway_walkway_ft=5)
    )
    assert walked.lane_ft == plain + 5
    assert "driveway_walkway_ft" in walked.from_code


def test_beside_a_court_the_standoff_already_is_a_walk() -> None:
    gap = DESIGN.parking.building_gap_ft
    open_side = {"parking_side_prohibited": False}
    base = side_court(DESIGN, rules(**open_side), frontage_ft=200)
    narrow = side_court(
        DESIGN, rules(driveway_walkway_ft=gap - 1, **open_side), frontage_ft=200
    )
    wide = side_court(
        DESIGN, rules(driveway_walkway_ft=gap + 3, **open_side), frontage_ft=200
    )
    assert base is not None and narrow is not None and wide is not None
    assert narrow.band_ft == base.band_ft
    assert wide.band_ft == base.band_ft + 3


def test_the_walk_is_not_part_of_the_drive_at_the_street() -> None:
    zone = rules(driveway_min_width_two_way_ft=30, driveway_walkway_ft=5)
    assert drive_at_street(DESIGN, zone) == 30


def test_one_lane_governs_the_drive_outright() -> None:
    own = DESIGN.parking.lane_ft
    plain = court_across(DESIGN, rules())
    assert plain.lane_ft == own
    narrow = court_across(DESIGN, rules(driveway_one_lane_ft=own - 2))
    assert narrow.lane_ft == own - 2
    assert "driveway_one_lane_ft" in narrow.from_code
    assert drive_at_street(DESIGN, rules(driveway_one_lane_ft=own - 2)) == own - 2
    # A one-lane drive is not a two-way one: the two-way minimum beside it
    # is not read.
    both = rules(driveway_one_lane_ft=own - 2, driveway_min_width_two_way_ft=20)
    assert court_across(DESIGN, both).lane_ft == own - 2
    assert "driveway_min_width_two_way_ft" not in court_across(DESIGN, both).from_code
    assert drive_at_street(DESIGN, both) == own - 2


def test_one_lane_is_still_widened_by_the_walk_beside_it() -> None:
    zone = rules(driveway_one_lane_ft=10, driveway_walkway_ft=5)
    assert court_across(DESIGN, zone).lane_ft == 15
    assert drive_at_street(DESIGN, zone) == 10


def test_one_lane_does_not_bring_back_a_lane_the_alley_removed() -> None:
    from flats.score.paper import Alley

    zone = rules(parking_alley_access_required=True, driveway_one_lane_ft=10)
    alley = Alley(at_rear=True)
    assert court_across(DESIGN, zone, alley).lane_ft == 0
    assert drive_at_street(DESIGN, zone, alley) == 0


def test_sherwood_and_durham_hold_them() -> None:
    layers = load_rules()
    sherwood = layers["or/washington/sherwood"].defaults["driveway_max_frontage_pct"]
    assert sherwood.value == 50
    durham = layers["or/washington/durham"].defaults["driveway_walkway_ft"]
    assert durham.value == 5


# --- the front yard's share in vehicle area ------------------------------------
#
# Portland 33.266.120.C.1.b (40 percent) and Milwaukie 19.607.1.D (50): an
# AREA share of the ground between the front lot line and the building. The
# drive crosses it front to back, so its share is its width against the
# lot's width. Encoded since 2026-08-27 and read by nothing until 2026-10-02.


def front(width: float | None, *, corner: bool = False, **extra):
    zone = rules(parking_front_yard_max_pct=40, **extra)
    lane = court_across(DESIGN, zone, corner=corner).lane_ft
    result = screen(
        zone,
        LotFacts(lot_sqft=12000, frontage_ft=width or 60.0, lot_width_ft=width, corner=corner),
        DESIGN, fit(lane), policy=POLICY,
    )
    return (
        next((c for c in result.checks if c.check == "front_yard_vehicle_share"), None),
        result,
    )


def test_the_front_yard_share_is_a_check_that_names_its_field() -> None:
    assert CHECK_FIELD["front_yard_vehicle_share"] == "parking_front_yard_max_pct"


def test_the_drive_across_the_front_yard_is_held_to_the_share() -> None:
    lane = DESIGN.parking.lane_ft
    got, _ = front(lane / 0.4 + 1)
    assert got is not None and got.verdict is Verdict.passes
    got, _ = front(lane / 0.4 - 3)
    assert got is not None and got.verdict is Verdict.fails


def test_a_drive_off_the_side_street_leaves_the_front_yard_unpaved() -> None:
    got, _ = front(20.0, corner=True, corner_access_street="side")
    assert got is None


def test_an_unmeasured_width_leaves_the_share_unchecked() -> None:
    got, result = front(None)
    assert got is None
    assert "front_yard_vehicle_share" in result.unchecked


# --- 22E01DD03100, the held bound hv_cap2 (2026-11-05) ------------------------
#
# The real lot, as s4 wrote it (quadfit 2026-10-30 dd_c6, EPSG:2913). Its only
# street lines are a 116.87 ft line s4 read as street off a drive on the
# neighbour's land (``drive_off_lot``) and the 23.08 ft jog onto Golden Eye's
# private tract (``drive``): 139.9 ft in all. The screen keeps the worse of the
# reading with and without the doubtful line, and without it the lot has
# 23.1 ft of frontage. Round 2 read the cap on private-drive lines only where
# NO street line was measured, and only off ``Edge.road_private`` (the road
# width file), which no drive line carries: on real data the path never ran,
# and the 23.1 ft reading failed the cap (11.55 ft against a 20 ft drive).
# The truth lies between: by the parcel map the lot meets the Golden Eye tract
# along ~27 ft of the long line and the 23 ft jog, about 50 ft. So the drive
# lines' 139.9 ft stand beside the 23.1 ft as the most the frontage can be:
# a question (YELLOW), never the pass 69.95 ft alone would make.
HV_EDGES = [
    [7687776.62, 646501.27, 7687892.72, 646499.07, "R"],
    [7687892.72, 646499.07, 7687974.66, 646468.85, "R"],
    [7687974.66, 646468.85, 7687988.63, 646397.65, "R"],
    [7687988.63, 646397.65, 7688012.79, 646329.84, "R"],
    [7688012.79, 646329.84, 7688051.06, 646278.21, "S"],
    [7688051.06, 646278.21, 7688086.48, 646242.38, "S"],
    [7688086.48, 646242.38, 7688196.16, 646165.16, "S"],
    [7688196.16, 646165.16, 7688191.24, 646020.23, "R"],
    [7688191.24, 646020.23, 7687650.83, 646038.61, "R"],
    [7687650.83, 646038.61, 7687659.21, 646480.42, "R"],
    [7687659.21, 646480.42, 7687776.06, 646478.2, "F"],
    [7687776.06, 646478.2, 7687776.62, 646501.27, "F"],
]
HV_SANS = [
    [*e[:4], letter]
    for e, letter in zip(HV_EDGES, ["S", "S", "R", "R", "S", "S", "S", "R", "S", "R", "S", "F"], strict=True)
]


def _hv_lot():
    import json

    import shapely
    from shapely.geometry import Polygon

    from flats.encode.load import load_trusted
    from flats.ingest.quadfit import lot_from_row
    from flats.tests.test_quadfit_bridge import row

    ring = Polygon([(e[0], e[1]) for e in HV_EDGES])
    r = row(
        TLID="22E01DD03100",
        jurisdiction="happy_valley",
        zone="MURS",
        tier="C",
        area_sqft=197795.5,
        frontage_ft=139.9,
        lot_width_ft=None,
        lot_depth_ft=None,
        edges_json=json.dumps(HV_EDGES),
        front_bearings_json="[178.91, 88.6]",
        street_kind_json=json.dumps([None] * 10 + ["drive_off_lot", "drive"]),
        sans_drive_json=json.dumps(
            {"doubtful": {"tier": "C", "edges": HV_SANS, "front_bearings": [88.61], "frontage_ft": 23.1}}
        ),
        wkb=shapely.to_wkb(ring.buffer(-10)),
        lot_wkb=shapely.to_wkb(ring),
    )
    return lot_from_row(r, load_trusted(strict=False).rules.layers)


def test_the_real_lot_keeps_its_drive_lines_on_the_reading_without_them() -> None:
    lot = _hv_lot()
    assert lot.second is not None and not lot.second_better
    assert sorted(lot.facts.street_lines_ft) == pytest.approx([23.08, 116.87], abs=0.05)
    assert lot.second.facts.frontage_ft == pytest.approx(23.1)
    assert lot.second.facts.private_drive_lines_ft == pytest.approx((139.9,), abs=0.05)
    hv = rules(jurisdiction="or/clackamas/happy-valley")
    assert _driveway_cap_frontages(hv, lot.second.facts) == pytest.approx((23.08, 139.9), abs=0.05)


def test_the_real_lot_is_a_question_on_the_cap_never_a_pass_or_a_miss() -> None:
    second = _hv_lot().second
    assert second is not None
    result = share_screen(
        second.facts, jurisdiction="or/clackamas/happy-valley", driveway_min_width_two_way_ft=20
    )
    assert not [c for c in result.checks if c.check == "driveway_frontage_share"]
    assert "driveway_frontage_share" in result.unchecked


def test_drive_lines_never_reach_a_city_outside_the_three() -> None:
    second = _hv_lot().second
    assert second is not None
    assert _driveway_cap_frontages(rules(), second.facts) == pytest.approx((23.08,), abs=0.05)


# --- a corner's street-side yard share (FOLLOWUPS 6(b), 2026-11-09) ------------
#
# Portland 33.266.120.C.1.b, second sentence: 20 percent of the land between
# the side street lot line and the side street building line. The drive a
# corner lot's court takes off the side street crosses it; which street is
# the side street is not known, so a pass is read off the shortest and a fail
# off the longest, and between them the share is unchecked.


def side(street_min: float | None, street_max: float | None = None, *, corner: bool = True,
         access: str = "side"):
    zone = rules(parking_side_street_yard_max_pct=20, corner_access_street=access)
    lane = court_across(DESIGN, zone, corner=corner).lane_ft
    result = screen(
        zone,
        LotFacts(lot_sqft=12000, frontage_ft=100.0, lot_width_ft=100.0, corner=corner,
                 street_line_min_ft=street_min,
                 street_line_max_ft=street_max if street_max is not None else street_min),
        DESIGN, fit(lane), policy=POLICY,
    )
    return (
        next((c for c in result.checks if c.check == "side_street_yard_vehicle_share"), None),
        result,
    )


def test_the_side_street_share_is_a_check_that_names_its_field() -> None:
    assert CHECK_FIELD["side_street_yard_vehicle_share"] == "parking_side_street_yard_max_pct"


def test_the_drive_off_the_side_street_is_held_to_the_share() -> None:
    zone = rules(parking_side_street_yard_max_pct=20, corner_access_street="side")
    drive = drive_at_street(DESIGN, zone, corner=True)
    assert drive
    got, _ = side(drive / 0.2 + 1)
    assert got is not None and got.verdict is Verdict.passes
    got, _ = side(drive / 0.2 - 3)
    assert got is not None and got.verdict is Verdict.fails


def test_a_drive_that_fits_only_the_longer_street_is_a_question() -> None:
    zone = rules(parking_side_street_yard_max_pct=20, corner_access_street="side")
    drive = drive_at_street(DESIGN, zone, corner=True)
    got, result = side(drive / 0.2 - 3, drive / 0.2 + 10)
    assert got is None
    assert "side_street_yard_vehicle_share" in result.unchecked


def test_a_drive_off_the_front_or_an_interior_lot_is_not_asked() -> None:
    got, result = side(40.0, access="front")
    assert got is None and "side_street_yard_vehicle_share" not in result.unchecked
    got, result = side(40.0, corner=False)
    assert got is None and "side_street_yard_vehicle_share" not in result.unchecked


def test_an_unmeasured_street_leaves_the_side_share_unchecked() -> None:
    got, result = side(None)
    assert got is None
    assert "side_street_yard_vehicle_share" in result.unchecked
