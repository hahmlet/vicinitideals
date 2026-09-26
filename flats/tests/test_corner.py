"""Which street is the front of a corner lot, where the code names it.

FOLLOWUPS 4(e), Steph 2026-09-26: *"Some cities allow developer choice,
others have strict standards. So we need to abide if Portland has guidance on
which is front and which is side."* Until then every street edge of a corner
lot was a front, both interior lines were rears, and the lane always ran
beside the building.
"""

from __future__ import annotations

import shapely

import pytest

from flats.designs.model import load_catalog
from flats.geom.corner import front_bearings, is_corner, line_length, name_front
from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier, bearing_deg
from flats.geom.envelope import Setbacks, buildable
from flats.score.paper import Alley, court_across, front_lot_line_rule, side_street_fed

pytestmark = pytest.mark.unit


def edge(x1: float, y1: float, x2: float, y2: float, cls: EdgeClass, *, alley: bool = False) -> Edge:
    return Edge(
        x1,
        y1,
        x2,
        y2,
        length_ft=((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5,
        bearing_deg=bearing_deg(x1, y1, x2, y2),
        cls=cls,
        alley=alley,
    )


def corner_lot(width: float = 50.0, depth: float = 100.0, *, north_alley: bool = False) -> LotEdges:
    """A ``width`` x ``depth`` lot, one street along the south line (bearing
    0) and one along the west (bearing 90), the way s4 names it: both
    streets front, both interior lines rear."""
    return LotEdges(
        tier=Tier.corner,
        edges=(
            edge(0, 0, width, 0, EdgeClass.front),
            edge(width, 0, width, depth, EdgeClass.rear),
            edge(width, depth, 0, depth, EdgeClass.rear, alley=north_alley),
            edge(0, depth, 0, 0, EdgeClass.front),
        ),
        front_bearings=(90.0, 0.0),
        frontage_ft=width + depth,
        convexity=1.0,
    )


# --- which street -------------------------------------------------------------


def test_the_shortest_rule_fronts_the_shorter_street_line() -> None:
    # Portland 33.910: the south line is 50 ft, the west 100 -- the south
    # street is the front, whichever s4 listed first (the longer, here).
    lot = corner_lot()
    assert line_length(lot, 0.0) == pytest.approx(50.0)
    assert line_length(lot, 90.0) == pytest.approx(100.0)
    assert front_bearings(lot, "shortest") == (0.0,)


def test_two_lines_within_a_foot_leave_the_choice_to_the_applicant() -> None:
    assert set(front_bearings(corner_lot(80.0, 80.5), "shortest")) == {0.0, 90.0}
    assert front_bearings(corner_lot(80.0, 81.5), "shortest") == (0.0,)


def test_the_owners_choice_tries_both_streets() -> None:
    for rule in ("owner", "entrance"):
        assert set(front_bearings(corner_lot(), rule)) == {0.0, 90.0}


def test_nothing_is_named_where_the_code_or_the_lot_does_not_settle_it() -> None:
    lot = corner_lot()
    # Every street line a front (Clackamas ZDO 202), or the rule unread.
    assert front_bearings(lot, "both") == ()
    assert front_bearings(lot, None) == ()
    # A street that bends is one street, not a corner (364c360e).
    bend = LotEdges(Tier.corner, lot.edges, (0.0, 30.0), 150.0, 1.0)
    assert not is_corner(bend) and front_bearings(bend, "shortest") == ()
    # One street.
    assert front_bearings(LotEdges(Tier.clean, lot.edges, (0.0,), 50.0, 1.0), "shortest") == ()
    # An alley's line is named against either frontage and its setback
    # resolved on that name; the front is left alone rather than renamed
    # under the resolution.
    assert front_bearings(corner_lot(north_alley=True), "shortest") == ()


def test_naming_the_front_makes_the_other_street_a_street_side_and_its_neighbour_a_side() -> None:
    named = name_front(corner_lot(), 0.0)
    south, east, north, west = (e.cls for e in named.edges)
    assert south is EdgeClass.front
    assert west is EdgeClass.street_side
    # East runs with the west street: beside the front, a side line.
    assert east is EdgeClass.side
    # North is opposite the front: still the rear.
    assert north is EdgeClass.rear


# --- the envelope ---------------------------------------------------------------


def test_a_named_front_cuts_the_second_street_at_its_own_setback_and_nothing_twice() -> None:
    lot = shapely.box(0, 0, 50, 100)
    yards = Setbacks(front_ft=10, side_ft=5, rear_ft=10, street_side_ft=5)
    both_fronts = buildable(lot, corner_lot(), yards)
    named = buildable(lot, name_front(corner_lot(), 0.0), yards)
    # Undecided: 10 off both streets, 10 off both interior lines.
    assert both_fronts.area == pytest.approx((50 - 10 - 10) * (100 - 10 - 10))
    # Named: 10 front, 5 street side, 5 side, 10 rear.
    assert named.area == pytest.approx((50 - 5 - 5) * (100 - 10 - 10))
    # A code with no street-side figure takes the front one on that street.
    no_street_side = Setbacks(front_ft=10, side_ft=5, rear_ft=10)
    assert buildable(lot, name_front(corner_lot(), 0.0), no_street_side).area == pytest.approx(
        (50 - 10 - 5) * (100 - 10 - 10)
    )


# --- the driveway off the side street -------------------------------------------


class Rules:
    def __init__(self, **values: object) -> None:
        self.values = values
        self.exempted = ()

    def get(self, name: str, default: object = None) -> object:
        return self.values.get(name, default)


DESIGN = load_catalog().latest("pod56x36")


def test_the_side_street_takes_the_driveway_where_the_code_lets_it() -> None:
    for value in ("any", "side"):
        rules = Rules(corner_access_street=value)
        assert side_street_fed(rules, None, True)  # type: ignore[arg-type]
        across = court_across(DESIGN, rules, corner=True)  # type: ignore[arg-type]
        assert across.lane_ft == 0.0
        assert "corner_access_street" in across.from_code
    # Not on a lot with one street.
    assert court_across(DESIGN, Rules(corner_access_street="any")).lane_ft > 0  # type: ignore[arg-type]


def test_a_code_asking_for_the_lowest_class_street_keeps_the_lane() -> None:
    # Nothing measures a street's functional class yet: the side street may
    # be the busier one, so the lane stays beside the building.
    rules = Rules(corner_access_street="lowest_class")
    assert not side_street_fed(rules, None, True)  # type: ignore[arg-type]
    assert court_across(DESIGN, rules, corner=True).lane_ft > 0  # type: ignore[arg-type]
    assert court_across(DESIGN, Rules(), corner=True).lane_ft > 0  # type: ignore[arg-type]


def test_the_alley_answer_comes_before_the_side_street() -> None:
    rules = Rules(corner_access_street="any", parking_alley_access_required=True)
    alley = Alley(20.0)
    assert not side_street_fed(rules, alley, True)  # type: ignore[arg-type]
    across = court_across(DESIGN, rules, alley, corner=True)  # type: ignore[arg-type]
    assert across.lane_ft == 0.0
    assert "parking_alley_access_required" in across.from_code
    assert "corner_access_street" not in across.from_code


def test_the_rule_is_read_as_the_code_states_it() -> None:
    assert front_lot_line_rule(Rules(front_lot_line_corner="shortest")) == "shortest"  # type: ignore[arg-type]
    assert front_lot_line_rule(Rules()) is None  # type: ignore[arg-type]
