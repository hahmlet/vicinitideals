"""A planted strip between parking and the lot lines (``parking_lot_line_buffer_ft``).

The screen lets the rear court share the rear yard (``paper.behind_wall_ft``):
the ground behind the building's rear wall is the deeper of the court and
the yard, so a court deeper than the yard runs right up to the rear lot line.
Several codes keep a landscaped strip between a parking or maneuvering area
and every lot line that is not a street. Those were noted "inert" because the
side and rear yards are at least as wide as the strip -- true of the yards,
not of a court that stands IN the rear yard. Read, the strip comes off the
court's run at the rear line: the ground behind the wall is the court plus
the strip.
"""

from __future__ import annotations

import pytest
import yaml

from flats.designs.model import Design
from flats.rules.fields import OPTIONAL_FIELDS, field
from flats.rules.loader import load_rules
from flats.score.paper import Alley, behind_wall_ft, court_across, court_depth, side_column
from flats.score.screen import _court_beyond_rear, _court_over

pytestmark = pytest.mark.unit

FIELD = "parking_lot_line_buffer_ft"

POD = """
version: 1
label: Four-plex pod
typology: townhome_rear_court
footprint: {width_ft: 56, depth_ft: 36}
units: 4
stories: 2
height_ft: 26
parking: {stalls_per_unit: 1.5, config: rear_court}
delivery: {method: modular, crane_required: true, crane_reach_ft: 60}
"""


def pod() -> Design:
    return Design(**{**yaml.safe_load(POD), "id": "pod"})


class Rules:
    """A resolution stub: the numbers, and the fields the code exempts."""

    def __init__(self, *exempted: str, **values: object) -> None:
        self.values = values
        self.exempted = exempted

    def get(self, name: str) -> object:
        return self.values.get(name)


def test_the_field_is_optional_and_a_length() -> None:
    assert FIELD in OPTIONAL_FIELDS
    assert field(FIELD).kind == "length_ft"


def test_the_strip_stands_behind_the_court_not_inside_the_yard() -> None:
    # A 49 ft court behind a wall that must stand 10 ft off the rear line.
    assert behind_wall_ft(49.0, 10.0, Rules()) == 49.0
    assert behind_wall_ft(49.0, 10.0, Rules(**{FIELD: 5})) == 54.0
    # A yard deeper than court and strip together still governs.
    assert behind_wall_ft(5.0, 25.0, Rules(**{FIELD: 5})) == 25.0
    # Nothing parked behind the wall: the yard alone.
    assert behind_wall_ft(0.0, 25.0, Rules(**{FIELD: 5})) == 25.0
    # Where the yard is kept clear of parking the yard already stands
    # behind the court; a narrower strip adds nothing.
    banned = {"parking_required_yard_prohibited": True}
    assert behind_wall_ft(49.0, 10.0, Rules(**banned, **{FIELD: 5})) == 59.0
    assert behind_wall_ft(49.0, 3.0, Rules(**banned, **{FIELD: 5})) == 54.0


def test_the_envelope_is_charged_the_strip_and_the_yard_credit_shrinks() -> None:
    plain = Rules(setback_rear_ft=10, parking_stall_depth_ft=20)
    strip = Rules(setback_rear_ft=10, parking_stall_depth_ft=20, **{FIELD: 5})
    court, _ = court_depth(pod(), plain)
    assert _court_beyond_rear(pod(), strip) == _court_beyond_rear(pod(), plain) + 5
    # The run credited to the yard is 5 less: the court stops short of the line.
    assert _court_over(pod(), plain) == 10.0
    assert _court_over(pod(), strip) == 5.0
    assert court == _court_beyond_rear(pod(), strip) + _court_over(pod(), strip)


def test_a_stall_cannot_back_into_the_alley_across_the_strip() -> None:
    fed = dict(parking_alley_access_required=True, parking_alley_backout_ft=23)
    side = Alley(width_ft=16.0, at_rear=False, at_side=True)
    assert side_column(pod(), Rules(**fed), side) is not None
    assert side_column(pod(), Rules(**fed, **{FIELD: 5}), side) is None
    rear = Alley(width_ft=16.0, rear_whole=True)
    _shallow, used = court_depth(pod(), Rules(**fed), rear)
    assert "parking_alley_backout_ft" in used
    _kept, used = court_depth(pod(), Rules(**fed, **{FIELD: 5}), rear)
    assert "parking_alley_backout_ft" not in used


def test_a_side_yard_narrower_than_the_strip_is_widened_to_it() -> None:
    """The court and its lane are searched inside the envelope, which the
    side setbacks cut. Where a zone states a side yard under the strip
    (Hillsboro's SCC and UC zones, 0 ft against a 4 ft strip) the envelope's
    sides stand the strip off -- conservative, since the building alone could
    stand nearer."""
    from flats.ingest.quadfit import envelope_for, lot_from_row
    from flats.tests.test_quadfit_bridge import Rules as BridgeRules, cut_row

    zero = BridgeRules(setback_front_ft=10, setback_side_ft=0, setback_rear_ft=0)
    strip = BridgeRules(
        setback_front_ft=10, setback_side_ft=0, setback_rear_ft=0, **{FIELD: 4}
    )
    plain = envelope_for(lot_from_row(cut_row()), zero)  # type: ignore[arg-type]
    kept = envelope_for(lot_from_row(cut_row()), strip)  # type: ignore[arg-type]
    assert plain.sqft == pytest.approx(50 * 90)
    assert kept.sqft == pytest.approx(42 * 90)
    assert kept.ground.area == pytest.approx(42 * 86)
    # A side yard already wider than the strip is left alone.
    wide = BridgeRules(setback_front_ft=10, setback_side_ft=5, setback_rear_ft=15, **{FIELD: 4})
    assert envelope_for(lot_from_row(cut_row()), wide).sqft == pytest.approx(40 * 75)  # type: ignore[arg-type]


# --- islands inside the court ---------------------------------------------------


def test_islands_inside_the_court_widen_the_row() -> None:
    # Tualatin 73C.210(4): 25 sq ft a space. Six stalls 20 ft deep need 150
    # sq ft, 7.5 ft along the row.
    plain = court_across(pod(), Rules(parking_stall_depth_ft=20))
    planted = court_across(
        pod(), Rules(parking_stall_depth_ft=20, parking_island_sqft_per_space=25)
    )
    assert planted.stalls == plain.stalls == 6
    assert planted.width_ft == pytest.approx(plain.width_ft + 7.5)
    assert "parking_island_sqft_per_space" in planted.from_code
    assert field("parking_island_sqft_per_space").kind == "area_sqft"
