"""Unincorporated Washington County: the readings a reviewer would stop on.

The county's Community Development Code opens Middle Housing to a Quadplex in
the urban residential districts and in three of the transit-oriented ones, and
nowhere else on one lot. Four places in the draft read against the grain of a
quick look, and each is pinned here so a later edit has to argue with it.

- **Transit-oriented districts denser than TO:R18-24.** Table A of Section 375
  lists triplexes, townhouses and "Multi-Dwelling Structures", and 106-143
  defines the last as five or more units. Four units on one lot has no row,
  and 375-5.2 prohibits what is not listed. A townhouse split onto lots of
  its own is listed, so those districts refuse on one lot and admit the pod
  only as the `unit_lots` variant.
- **R-25+ North Bethany.** The same definition refuses the densest North
  Bethany district, which allows only multi-dwelling housing and live/work
  units. The draft does not read four units as a small apartment building.
- **CBD.** New dwellings only through a Planned Development, so the base value
  refuses and the one variant admits behind `planned_development`.
- **The rural and resource districts** refuse with a cite and nothing else: a
  settled refusal owes no dimensions, and inventing some would make a later
  reader think the district had been measured.

Two smaller facts ride along. The zone keys are the spellings on the county's
zoning layer (field `LUD`), which is how a lot finds its zone, so the layer
writes MA-E where the CDC's own heading writes MAE. And the manufactured
dwelling prohibition every R district prints (X-5.2) does not reach the pod,
because 106-131 defines a manufactured dwelling by the highway and by the
trailer, mobile-home and federal construction standards, none of which a
factory-built townhome is built to.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer, Status

pytestmark = pytest.mark.unit

WASHINGTON = "or/washington/_unincorporated"

#: Middle Housing on one lot, per 106-124 and each district's use list.
ONE_LOT = (
    "R-5", "R-6", "R-9", "R-15", "R-24", "R-25+",
    "R-6 NB", "R-9 NB", "R-15 NB", "R-24 NB",
    "TO:R9-12", "TO:R12-18", "TO:R18-24",
    "NMU", "CCMU",
)
#: Townhouses listed, four units on one lot not.
UNIT_LOTS_ONLY = ("TO:R24-40", "TO:R40-80", "TO:BUS")
#: Section 340-356: farm, forest, rural residential, rural commercial and
#: industrial, and mineral-aggregate districts.
RURAL = ("EFU", "EFC", "AF-20", "AF-10", "AF-5", "RR-5", "R-COM", "R-IND", "MA-E")


@pytest.fixture(scope="module")
def washington() -> Layer:
    return load_rules()[WASHINGTON]


def _use(layer: Layer, zone: str):
    return layer.zones[zone].values["quadplex_allowed"]


def test_every_zone_on_the_county_map_is_encoded(washington: Layer) -> None:
    assert len(washington.zones) == 42
    assert "MA-E" in washington.zones
    assert "MAE" not in washington.zones
    # Named in 375-2 but on no lot of the county's zoning layer; ruled in the
    # districts ledger instead (test_districts.BY_HAND).
    assert "TO:R80-120" not in washington.zones


def test_the_pod_goes_on_one_lot_in_fifteen_districts(washington: Layer) -> None:
    for zone in ONE_LOT:
        use = _use(washington, zone)
        assert use.value is True, zone
        assert use.variants == (), zone
    admitted = {z for z in washington.zones if _use(washington, z).value is True}
    assert admitted == set(ONE_LOT)


def test_denser_transit_districts_admit_only_unit_lots(washington: Layer) -> None:
    for zone in UNIT_LOTS_ONLY:
        use = _use(washington, zone)
        assert use.value is False, zone
        assert [(v.value, v.when) for v in use.variants] == [(True, ("unit_lots",))], zone


def test_a_multi_dwelling_structure_is_five_units(washington: Layer) -> None:
    text = ProvenanceStore().quote(f"{WASHINGTON}/cdc.106.definitions.txt#L782-L786")
    assert "Five or more attached primary dwelling units" in text
    use = _use(washington, "R-25+ NB")
    assert use.value is False
    assert use.variants == ()


def test_cbd_admits_the_pod_only_through_a_planned_development(washington: Layer) -> None:
    use = _use(washington, "CBD")
    assert use.value is False
    assert [(v.value, v.when) for v in use.variants] == [(True, ("planned_development",))]


def test_rural_districts_refuse_with_a_cite_and_nothing_else(washington: Layer) -> None:
    for zone in RURAL:
        held = washington.zones[zone]
        assert set(held.values) == {"quadplex_allowed"}, zone
        use = held.values["quadplex_allowed"]
        assert use.value is False, zone
        assert use.variants == (), zone
        assert use.prov.quote, zone


def test_a_manufactured_dwelling_is_a_highway_structure() -> None:
    store = ProvenanceStore()
    prohibition = store.quote(f"{WASHINGTON}/cdc.302.r-5.txt#L224-L227")
    assert "manufactured dwelling" in prohibition
    definition = " ".join(store.quote(f"{WASHINGTON}/cdc.106.definitions.txt#L718-L734").split())
    assert definition.count("constructed for movement on the public highways") >= 2
    assert "federal manufactured housing construction and safety standards" in definition


def test_nothing_in_the_draft_is_verified(washington: Layer) -> None:
    for zone, held in washington.zones.items():
        for field, value in held.values.items():
            assert value.status is not Status.verified, (zone, field)
            for variant in value.variants:
                assert variant.status is not Status.verified, (zone, field)


# FOLLOWUPS 109 chunk 6 and 129: the North Bethany Subarea Plan's map-drawn
# rules. Each is a site fact no default answers; FOLLOWUPS 129 traced the
# Special Setbacks Map segments, the Park Blocks ASC 5 and the Kaiser Main
# Street area (ASC 2), so the bridge answers each from the lot's share inside
# the tracing, and a lot a line cuts stays unknown and held off GREEN.
NORTH_BETHANY_FACTS = {
    "R-6 NB": {"north_bethany_park_blocks"},
    "R-9 NB": {"north_bethany_park_blocks"},
    "R-15 NB": {"north_bethany_special_setbacks", "north_bethany_park_blocks"},
    "R-24 NB": {
        "north_bethany_special_setbacks",
        "north_bethany_park_blocks",
        "north_bethany_kaiser_main_street",
    },
}
NB_AREAS = {
    "north_bethany_special_setbacks": "or/washington/_unincorporated/north-bethany-special-setbacks.geojson",
    "north_bethany_park_blocks": "or/washington/_unincorporated/north-bethany-park-blocks-asc-5.geojson",
    "north_bethany_kaiser_main_street": "or/washington/_unincorporated/north-bethany-kaiser-main-street.geojson",
}


@pytest.mark.parametrize("zone", sorted(NORTH_BETHANY_FACTS))
def test_north_bethany_plan_map_areas_are_drawn_facts(washington: Layer, zone: str) -> None:
    from flats.rules.conditions import DRAWN_CONDITIONS, condition

    rules = washington.zones[zone]
    levers = set().union(*(v.levers for v in rules.values.values()))
    want = NORTH_BETHANY_FACTS[zone]
    assert want <= levers
    drawn = {a.condition: a for a in washington.drawn_areas.values()}
    for name in want:
        fact = condition(name)
        # Unassumed: only the tracing answers it, and a lot it leaves
        # unanswered is read as unknown (FACT_UNOBSERVED).
        assert fact.kind == "site_fact" and fact.assume is None
        assert name in DRAWN_CONDITIONS
        assert drawn[name].file == NB_AREAS[name]
        assert zone in drawn[name].zones


def _nb_features(name: str) -> list[dict]:
    import json

    from flats.rules import loader

    data = json.loads((loader.AREAS_ROOT / NB_AREAS[name]).read_text(encoding="utf-8"))
    assert data["source"]["drawn"] is True
    return data["features"]


def _nb_facts(zone: str, lot) -> dict:
    import shapely

    from flats.encode.load import load_trusted
    from flats.ingest.quadfit import observed_facts
    from flats.tests.test_quadfit_bridge import row

    layers = load_trusted(strict=False).rules.layers
    return observed_facts(
        row(jurisdiction="washington_unincorporated", zone=zone, lot_wkb=shapely.to_wkb(lot)), layers
    )


@pytest.mark.parametrize("name", ["north_bethany_special_setbacks", "north_bethany_kaiser_main_street"])
def test_a_traced_lot_is_drawn_whole_and_a_cut_lot_by_half(name: str) -> None:
    from shapely.geometry import shape

    from flats.geom.drawn import INSIDE_SHARE, OUTSIDE_SHARE

    feats = _nb_features(name)
    assert feats
    for f in feats:
        props = f["properties"]
        if props["answer"] == "inside":
            assert props["drawn_share_of_lot"] == 1
        else:
            assert props["answer"] == "unanswered"
            assert OUTSIDE_SHARE < props["drawn_share_of_lot"] < INSIDE_SHARE
        assert shape(f["geometry"]).is_valid


def test_a_lot_fronting_a_setback_segment_is_inside_and_one_off_the_map_is_not() -> None:
    from shapely.geometry import box, shape

    inside = next(f for f in _nb_features("north_bethany_special_setbacks") if f["properties"]["answer"] == "inside")
    lot = shape(inside["geometry"])
    zone = inside["properties"]["zone"]
    assert _nb_facts(zone, lot)["north_bethany_special_setbacks"] is True
    minx, miny, _, _ = lot.bounds
    far = box(minx - 3000, miny - 3000, minx - 2900, miny - 2900)
    got = _nb_facts("R-15 NB", far)
    assert got["north_bethany_special_setbacks"] is False
    assert got["north_bethany_park_blocks"] is False


def test_the_park_blocks_are_the_asc_5_outline_and_a_lot_it_cuts_is_unanswered() -> None:
    from shapely.geometry import Point, shape

    (f,) = _nb_features("north_bethany_park_blocks")
    area = shape(f["geometry"])
    assert 54 < area.area / 43_560 < 57  # Map 17's ASC 5, about 55 acres
    assert _nb_facts("R-9 NB", area.representative_point().buffer(5))["north_bethany_park_blocks"] is True
    ring = (max(area.geoms, key=lambda g: g.area) if area.geom_type == "MultiPolygon" else area).exterior
    coords = list(ring.coords)
    a, b = max(zip(coords, coords[1:]), key=lambda ab: Point(ab[0]).distance(Point(ab[1])))
    edge = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2).buffer(10)
    assert "north_bethany_park_blocks" not in _nb_facts("R-6 NB", edge)


def test_north_bethany_kaiser_main_street_figures(washington: Layer) -> None:
    rules = washington.zones["R-24 NB"].values
    kaiser = ("north_bethany_kaiser_main_street",)

    def at(field: str):
        return {tuple(v.when): v.value for v in rules[field].variants}[kaiser]

    assert (at("setback_front_ft"), at("setback_front_max_ft"), at("building_frontage_min_pct")) == (5, 10, 75)
