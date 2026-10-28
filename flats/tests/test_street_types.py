"""Gresham's Downtown street types, traced off Map 4.1140 (flats.geom.street_types).

The mechanism on a drawn map of its own (a grid of typed centrelines), then
the traced file itself: what it is drawn from, and that real lot lines on
real streets read the type the map gives them.
"""

from __future__ import annotations

import json

import pytest
from shapely.geometry import LineString

from flats.geom.street_types import (
    CONDITION,
    SERVES,
    TRACED,
    TYPES,
    StreetTypes,
    load_street_types,
    observed_street_types,
)
from flats.rules.loader import AREAS_ROOT

pytestmark = pytest.mark.unit

#: A toy map: an east-west street at y=0 and one at y=400, a north-south one
#: at x=0. Their types are set per test.
EW_SOUTH = LineString([(-1000, 0), (1000, 0)])
EW_NORTH = LineString([(-1000, 400), (1000, 400)])
NS_WEST = LineString([(0, -1000), (0, 1000)])


def toy(south: str, north: str = "downtown_local", west: str = "downtown_local") -> StreetTypes:
    return StreetTypes.build(
        [EW_SOUTH, EW_NORTH, NS_WEST], ["SOUTH ST", "NORTH ST", "WEST AVE"], [south, north, west]
    )


#: A lot 100 ft wide and 340 ft deep between the two east-west streets, 30 ft
#: back from each centreline, east of the north-south one by 200 ft.
FRONT = [200.0, 30.0, 300.0, 30.0, "F"]
SIDE_E = [300.0, 30.0, 300.0, 370.0, "S"]
REAR = [300.0, 370.0, 200.0, 370.0, "R"]
SIDE_W = [200.0, 370.0, 200.0, 30.0, "S"]
BACK_STREET = [300.0, 370.0, 200.0, 370.0, "F"]
BACK_ALLEY = [300.0, 370.0, 200.0, 370.0, "A"]
#: The same lot on the corner with the north-south street.
CORNER_SIDE = [30.0, 370.0, 30.0, 30.0, "F"]
CORNER_FRONT = [30.0, 30.0, 300.0, 30.0, "F"]


def lot(*edges):
    return [list(e) for e in edges]


def test_a_line_takes_the_type_of_the_street_it_abuts() -> None:
    m = toy("urban_boulevard", "downtown_local")
    assert m.edge_type(FRONT) == "urban_boulevard"
    assert m.edge_type(BACK_STREET) == "downtown_local"
    # No centreline beside it: unplaced.
    assert m.edge_type([200.0, 200.0, 300.0, 200.0, "F"]) is None


@pytest.mark.parametrize("barring", ["urban_boulevard", "beech", "main", "stanley"])
def test_a_lot_on_one_barring_street_alone_is_barred(barring: str) -> None:
    assert toy(barring).barred(lot(FRONT, SIDE_E, REAR, SIDE_W)) is True


@pytest.mark.parametrize("open_type", ["downtown_local", "cleveland"])
def test_a_lot_on_a_street_that_bars_nothing_is_not(open_type: str) -> None:
    assert toy(open_type).barred(lot(FRONT, SIDE_E, REAR, SIDE_W)) is False


def test_a_side_street_or_a_rear_alley_is_the_way_in() -> None:
    m = toy("urban_boulevard", "downtown_local")
    # The through lot: a boulevard in front, a local street behind.
    assert m.barred(lot(FRONT, SIDE_E, BACK_STREET, SIDE_W)) is False
    # The rear alley 4.1142(A)(6) and (C)(9) point to.
    assert m.barred(lot(FRONT, SIDE_E, BACK_ALLEY, SIDE_W)) is False
    # The corner with a local side street.
    corner = toy("urban_boulevard", west="downtown_local")
    assert corner.barred(lot(CORNER_FRONT, SIDE_E, REAR, CORNER_SIDE)) is False


def test_two_barring_streets_are_still_barred() -> None:
    m = toy("urban_boulevard", "beech")
    assert m.barred(lot(FRONT, SIDE_E, BACK_STREET, SIDE_W)) is True


def test_main_avenue_bars_the_use_not_only_the_access() -> None:
    """Table 4.1130: "Not allowed on this street type". A rear alley does not
    reopen a lot whose only street is Main, and a Main corner is unanswered."""
    m = toy("main", "downtown_local")
    assert m.barred(lot(FRONT, SIDE_E, BACK_ALLEY, SIDE_W)) is True
    assert m.barred(lot(FRONT, SIDE_E, BACK_STREET, SIDE_W)) is None


def test_a_line_nobody_can_place_leaves_it_unanswered() -> None:
    m = toy("urban_boulevard")
    # A street line in the middle of the block (a street RLIS does not carry,
    # like Stanley): no traced centreline beside it.
    ghost = [200.0, 200.0, 300.0, 200.0, "F"]
    assert m.barred(lot(ghost, SIDE_E, REAR, SIDE_W)) is None
    # ... and beside a barring one it still cannot be called barred.
    assert m.barred(lot(FRONT, SIDE_E, ghost, SIDE_W)) is None
    # No street line at all.
    assert m.barred(lot(SIDE_E, REAR, SIDE_W)) is None


def test_an_unknown_street_type_is_refused() -> None:
    with pytest.raises(ValueError):
        StreetTypes.build([EW_SOUTH], ["SOUTH ST"], ["boulevard"])


def test_only_downtown_townhouse_zones_of_gresham_are_answered() -> None:
    edges = lot(FRONT, SIDE_E, REAR, SIDE_W)
    assert observed_street_types(edges, SERVES, "DCC") == {}
    assert observed_street_types(edges, "or/multnomah/troutdale", "DMU") == {}
    assert observed_street_types([], SERVES, "DMU") == {}


# --- the traced map -----------------------------------------------------------


def test_the_tracing_cites_its_map_and_is_drawn() -> None:
    data = json.loads((AREAS_ROOT / TRACED).read_text(encoding="utf-8"))
    src = data["source"]
    assert src["map"].startswith("GDC Map 4.1140")
    assert "[4.1100]-23" in src["page"]
    assert src["sha256"] == "03c8849474f589724e081d69b063c424ee28e4b7f324e8fcc381bd75753064fb"
    assert src["drawn"] is True and src["traced_by"] and src["traced_on"]
    assert data["crs"]["properties"]["name"].endswith("2913")
    assert {f["properties"]["street_type"] for f in data["features"]} <= TYPES


def _typed(name: str) -> set[str]:
    m = load_street_types()
    return {t for n, t in zip(m.streets.names, m.types) if n == name}


def test_the_frame_is_urban_boulevard_and_main_stops_at_fourth() -> None:
    for frame in ("NE BURNSIDE RD", "NE DIVISION ST", "W POWELL BLVD", "E POWELL BLVD",
                  "NW EASTMAN PKWY", "NE HOGAN DR"):
        assert _typed(frame) == {"urban_boulevard"}, frame
    # 4.1142(D): Main Avenue from Powell to 4th; north of 4th it is local.
    assert _typed("N MAIN AVE") == {"main", "downtown_local"}
    assert _typed("NE BEECH AVE") == {"beech"}
    assert _typed("NE CLEVELAND AVE") == {"cleveland"}


def test_real_lot_lines_read_their_street_type() -> None:
    m = load_street_types()
    # 30 ft east of N Main Ave between NW 1st and NW 2nd (Main, Powell to 4th).
    assert m.edge_type([7707063.0, 673780.0, 7707063.0, 673880.0, "F"]) == "main"
    # 30 ft east of N Main Ave north of NE 4th: Downtown Local.
    assert m.edge_type([7707087.0, 674950.0, 7707087.0, 675050.0, "F"]) == "downtown_local"
    # 30 ft north of NE 8th St.
    assert m.edge_type([7708700.0, 675373.0, 7708820.0, 675373.0, "F"]) == "downtown_local"
    # 30 ft north of E Powell Blvd.
    assert m.edge_type([7708000.0, 673581.0, 7708120.0, 673581.0, "F"]) == "urban_boulevard"
    answer = observed_street_types(
        [[7708000.0, 673581.0, 7708120.0, 673581.0, "F"], [7708120.0, 673581.0, 7708120.0, 673741.0, "S"]],
        SERVES,
        "DCL",
    )
    assert answer == {CONDITION: True}
