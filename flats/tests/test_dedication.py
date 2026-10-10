"""Right-of-way a Washington County middle-housing lot gives up (flats/geom/dedication.py).

CDC 302-2.14 C(1) and its twins: along the site frontage the right-of-way must
reach 25 / 30 / 37 / 45 ft to the centreline (local, neighbourhood route,
collector, arterial), or the lot dedicates the shortfall before its first
building permit. These tests pin what is measured, what is assumed when nothing
can be, and that the strip comes off the envelope like a setback.
"""

from __future__ import annotations

import json

import pytest
import shapely
from shapely.geometry import LineString

from flats.geom import dedication
from flats.geom.corridor import Lines
from flats.geom.street_class import ClassMap
from flats.ingest.quadfit import dedicated, envelope_for, lot_from_row
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

LAYER = "or/washington/_unincorporated"
X0, Y0 = 7_650_000.0, 680_000.0
FRONT = [X0, Y0, X0 + 50, Y0, "F"]
EDGES = [
    FRONT,
    [X0 + 50, Y0, X0 + 50, Y0 + 100, "S"],
    [X0 + 50, Y0 + 100, X0, Y0 + 100, "R"],
    [X0, Y0 + 100, X0, Y0, "S"],
]
DISTANCES = (25.0, 30.0, 37.0, 45.0)


@pytest.fixture(scope="module")
def rules():
    return RuleSet(load_rules())


def resolved(rules, zone: str = "R-6"):
    return rules.resolve(LAYER, zone)


def row(half: float | None, rank: int | None, public: bool = True) -> dict[str, object]:
    return {
        "TLID": "1S2E20AA  -15100",
        "jurisdiction": "washington_unincorporated",
        "zone": "R6",
        "tier": "A",
        "area_sqft": 5000.0,
        "frontage_ft": 50.0,
        "lot_width_ft": 50.0,
        "lot_depth_ft": 100.0,
        "edges_json": json.dumps(EDGES),
        "front_bearings_json": "[0.0]",
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "wkb": shapely.to_wkb(shapely.box(X0 + 5, Y0 + 10, X0 + 45, Y0 + 95)),
        "lot_wkb": shapely.to_wkb(shapely.box(X0, Y0, X0 + 50, Y0 + 100)),
        "road_widths_json": json.dumps([[*dedication.key(*FRONT[:4]), half, rank, public]]),
    }


def sqft(rules, half: float | None, rank: int | None, public: bool = True) -> float:
    lot = lot_from_row(row(half, rank, public))
    env = envelope_for(lot, resolved(rules))
    assert env.source == "flats"
    return env.sqft


def side_span(rules) -> float:
    lot = lot_from_row(row(25.0, 0))
    return 50.0 - 2 * envelope_for(lot, resolved(rules)).setbacks.side_ft


def test_the_depth_is_the_shortfall_and_never_below_zero() -> None:
    assert dedication.depth_ft(25.0, 20.5) == pytest.approx(4.5)
    assert dedication.depth_ft(25.0, 25.0) == 0.0
    assert dedication.depth_ft(25.0, 31.0) == 0.0


def test_an_unmeasured_line_gives_up_the_whole_distance() -> None:
    assert dedication.depth_ft(30.0, None) == 30.0


def test_the_class_picks_the_distance_and_an_unread_class_takes_the_deepest() -> None:
    assert [dedication.required_ft(r, DISTANCES) for r in (0, 1, 2, 3)] == [25, 30, 37, 45]
    assert dedication.required_ft(5, DISTANCES) == 45
    assert dedication.required_ft(None, DISTANCES) == 45


@pytest.mark.parametrize(
    ("name", "rank", "centreline_ft", "due"),
    [
        # 1S201CC12500: Neighborhood Route, centreline 26.4 ft off -> 3.6 ft due.
        ("1S201CC12500", 1, 26.4, 3.6),
        # 1N120AD09600: local streets, 42 ft and 46 ft wide, the centreline midway.
        ("1N120AD09600 front", 0, 21.0, 4.0),
        ("1N120AD09600 side", 0, 23.0, 2.0),
        # The nine sample lots that were right stay right.
        ("lot 5", 1, 24.7, 5.3),
        ("lot 7", 1, 24.0, 6.0),
        ("lot 9", 1, 25.0, 5.0),
        ("lot 11", 1, 26.7, 3.3),
        ("lot 8, a collector already 37.6 ft out", 2, 37.6, 0.0),
    ],
)
def test_the_sample_lots_give_up_what_the_code_asks(name: str, rank: int, centreline_ft: float, due: float) -> None:
    got = dedication.depth_ft(dedication.required_ft(rank, DISTANCES), centreline_ft)
    assert got == pytest.approx(due, abs=0.05), name


def test_a_narrow_local_road_loses_the_strip(rules) -> None:
    full = sqft(rules, 25.0, 0)
    narrow = sqft(rules, 20.5, 0)
    assert full - narrow == pytest.approx(4.5 * side_span(rules))


def test_a_full_width_road_loses_nothing(rules) -> None:
    assert sqft(rules, 25.0, 0) == pytest.approx(sqft(rules, 40.0, 0))


def test_an_unmeasured_road_takes_the_worst_case(rules) -> None:
    assert sqft(rules, 25.0, 0) - sqft(rules, None, 0) == pytest.approx(25.0 * side_span(rules))


def test_an_unread_class_takes_the_deepest_distance(rules) -> None:
    assert sqft(rules, 25.0, 0) - sqft(rules, 25.0, None) == pytest.approx(20.0 * side_span(rules))


def test_a_private_road_gives_up_nothing(rules) -> None:
    assert sqft(rules, None, None, public=False) == pytest.approx(sqft(rules, 40.0, 0))


def test_a_code_without_the_distances_is_untouched(rules) -> None:
    lot = lot_from_row(row(20.0, 0))
    portland = rules.resolve("or/multnomah/portland", "CM2")
    assert dedicated(lot.edges, portland) is lot.edges


def test_every_middle_housing_district_states_the_four_distances(rules) -> None:
    for zone in ("R-5", "R-6", "R-9", "R-15", "R-24", "R-25+", "R-6 NB", "R-9 NB", "R-15 NB", "TO:R9-12", "TO:R12-18", "TO:R18-24"):
        got = resolved(rules, zone)
        assert [got.get(n) for n in dedication.RANK_FIELDS] == [25, 30, 37, 45], zone


def test_the_half_width_is_the_nearest_centreline_distance() -> None:
    street = LineString([(X0 - 500, Y0 - 30), (X0 + 500, Y0 - 30)])
    cmap = ClassMap(
        serves=(LAYER,),
        lines=Lines.build([street], [""]),
        kinds=("",),
        streets=Lines.build([street], [""]),
        types=(1500,),
    )
    width, public = dedication.half_width_ft(FRONT[:4], cmap)
    assert public and width == pytest.approx(30.0)
    private = ClassMap(**{**cmap.__dict__, "types": (1700,)})
    assert dedication.half_width_ft(FRONT[:4], private) == (None, False)
    far = LineString([(X0 - 500, Y0 - 400), (X0 + 500, Y0 - 400)])
    nothing = ClassMap(**{**cmap.__dict__, "streets": Lines.build([far], [""])})
    assert dedication.half_width_ft(FRONT[:4], nothing) == (None, True)


def test_only_unincorporated_washington_county_is_measured() -> None:
    assert dedication.applies(LAYER)
    assert not dedication.applies("or/washington/hillsboro")
    assert not dedication.applies("or/multnomah/portland")
    assert not dedication.applies(None)
