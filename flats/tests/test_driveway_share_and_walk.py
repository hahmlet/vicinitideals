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
from flats.score.screen import CHECK_FIELD, LotFacts, screen  # noqa: E402
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
    values = {**CLEAR, **overrides}
    return ZoneResolution(
        jurisdiction=WHERE,
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


def share(frontage: float, **extra):
    zone = rules(driveway_max_frontage_pct=50, **extra)
    lane = court_across(DESIGN, zone).lane_ft
    result = screen(
        zone, LotFacts(lot_sqft=12000, frontage_ft=frontage, lot_width_ft=frontage),
        DESIGN, fit(lane), policy=POLICY,
    )
    return next((c for c in result.checks if c.check == "driveway_frontage_share"), None)


def test_the_share_is_a_check_that_names_its_field() -> None:
    assert CHECK_FIELD["driveway_frontage_share"] == "driveway_max_frontage_pct"


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
