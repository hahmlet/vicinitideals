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
    "north_bethany_park_blocks": "or/washington/_unincorporated/north-bethany-park-blocks-asc-5-lots.geojson",
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


@pytest.mark.parametrize(
    "name", ["north_bethany_special_setbacks", "north_bethany_kaiser_main_street", "north_bethany_park_blocks"]
)
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


def _asc_5_outline():
    import json

    from shapely.geometry import shape

    from flats.rules import loader

    path = loader.AREAS_ROOT / "or/washington/_unincorporated/north-bethany-park-blocks-asc-5.geojson"
    (f,) = json.loads(path.read_text(encoding="utf-8"))["features"]
    return shape(f["geometry"])


def test_asc_5_holds_only_the_lots_its_access_and_parking_rules_reach() -> None:
    """FOLLOWUPS 132: ASC 5 items 4 and 5 are measured, not held area-wide.

    A lot facing the Park Blocks (item 4) or with streets on two opposite
    sides (item 5) is inside and held; every lot inside the outline is in the
    file whole only for one of those reasons; a lot the outline cuts stays
    unanswered at its share inside.
    """
    from shapely.geometry import shape

    outline = _asc_5_outline()
    assert 54 < outline.area / 43_560 < 57  # Map 17's ASC 5, about 55 acres
    feats = _nb_features("north_bethany_park_blocks")
    inside = [f for f in feats if f["properties"]["answer"] == "inside"]
    cut = [f for f in feats if f["properties"]["answer"] == "unanswered"]
    assert inside and cut
    for f in inside:
        lot = shape(f["geometry"])
        assert lot.intersection(outline).area / lot.area >= 0.9
        assert "item 4" in f["properties"]["why"] or "item 5" in f["properties"]["why"] or "median tract" in f["properties"]["why"]
    for f in cut:
        assert f["properties"]["why"] == "the ASC 5 outline cuts the lot"
    # Item 4 reaches a lot facing the median across the couplet.
    facing = next(f for f in inside if f["properties"]["why"].startswith("item 4"))
    assert _nb_facts(facing["properties"]["zone"], shape(facing["geometry"]))["north_bethany_park_blocks"] is True
    # A lot the outline cuts is unanswered, so the screen leaves the fact open.
    # Stood in for by its part inside plus as much ground again far off the
    # map: half the lot inside, which the screen leaves open.
    from shapely.geometry import box

    (one,) = [f for f in cut if f["properties"]["taxlot"] == "1N117BC00100"]
    part = shape(one["geometry"]).buffer(0)
    minx, miny, _, _ = part.bounds
    side = part.area ** 0.5
    lot = part.union(box(minx - 5000, miny - 5000, minx - 5000 + side, miny - 5000 + side))
    assert "north_bethany_park_blocks" not in _nb_facts("R-15 NB", lot)


def test_a_lot_inside_asc_5_that_neither_rule_reaches_reads_its_district() -> None:
    from shapely.geometry import box, shape
    from shapely.ops import unary_union

    outline = _asc_5_outline()
    held = unary_union([shape(f["geometry"]) for f in _nb_features("north_bethany_park_blocks")])
    free = outline.difference(held.buffer(5))
    spot = free.representative_point()
    lot = box(spot.x - 4, spot.y - 4, spot.x + 4, spot.y + 4)
    assert lot.within(outline)
    assert _nb_facts("R-9 NB", lot)["north_bethany_park_blocks"] is False


def test_asc_5_line_numbers_name_items_4_and_5() -> None:
    from flats.provenance.store import ProvenanceStore

    text = " ".join(
        ProvenanceStore().quote(f"{WASHINGTON}/community-plan.north-bethany-subarea.txt#L2299,L2359-L2364").split()
    )
    assert "The following requirements apply in the Park Blocks ASC" in text
    assert "Vehicular access to residential properties adjacent to the Park Blocks is not permitted" in text
    assert "Parking lots between the street and the adjacent buildings are prohibited." in text


def test_north_bethany_kaiser_main_street_figures(washington: Layer) -> None:
    rules = washington.zones["R-24 NB"].values
    kaiser = ("north_bethany_kaiser_main_street",)

    def at(field: str):
        return {tuple(v.when): v.value for v in rules[field].variants}[kaiser]

    assert (at("setback_front_ft"), at("setback_front_max_ft"), at("building_frontage_min_pct")) == (5, 10, 75)


# --- Bethany ASC 1 and 1A (FOLLOWUPS 130) ------------------------------------

BETHANY_AREAS = {
    "bethany_asc_1": "or/washington/_unincorporated/bethany-asc-1.geojson",
    "bethany_asc_1a": "or/washington/_unincorporated/bethany-asc-1a.geojson",
}


def _bethany_file(name: str) -> dict:
    import json

    from flats.rules import loader

    data = json.loads((loader.AREAS_ROOT / BETHANY_AREAS[name]).read_text(encoding="utf-8"))
    assert data["source"]["drawn"] is True
    return data


def _bethany_area(name: str):
    from shapely.geometry import shape

    (feat,) = _bethany_file(name)["features"]
    return shape(feat["geometry"])


def _box(p, half: float = 4.0):
    from shapely.geometry import box

    return box(p.x - half, p.y - half, p.x + half, p.y + half)


@pytest.mark.parametrize("name", sorted(BETHANY_AREAS))
def test_bethany_asc_outlines_are_drawn_facts(washington: Layer, name: str) -> None:
    area = washington.drawn_areas[name]
    assert area.condition == name
    assert area.file == BETHANY_AREAS[name]
    assert "community-plan.bethany.txt#" in area.quote
    assert _bethany_area(name).is_valid


def test_a_lot_in_asc_1a_is_in_asc_1_and_one_off_the_map_is_in_neither() -> None:
    from shapely.geometry import Point

    asc_1, asc_1a = _bethany_area("bethany_asc_1"), _bethany_area("bethany_asc_1a")
    assert asc_1a.difference(asc_1).area < 0.01 * asc_1a.area
    p = asc_1a.representative_point()
    got = _nb_facts("R-24", _box(p))
    assert got["bethany_asc_1"] is True and got["bethany_asc_1a"] is True
    q = asc_1.difference(asc_1a.buffer(50)).representative_point()
    got = _nb_facts("R-9", _box(q))
    assert got["bethany_asc_1"] is True and got["bethany_asc_1a"] is False
    got = _nb_facts("R-9", _box(Point(p.x - 9000, p.y - 9000)))
    assert got["bethany_asc_1"] is False and got["bethany_asc_1a"] is False


def test_the_one_lot_the_asc_1_outline_cuts_is_carried_whole() -> None:
    source = _bethany_file("bethany_asc_1")["source"]
    assert "1N120DA20300" in source["how"]
    assert not any(c.get("unanswered") for c in source["counts"].values())


def _bethany_screen(conditions: tuple[str, ...], *, inside_ugb: bool = True):
    from flats.score import relief, slack
    from flats.score.configure import Configuration
    from flats.score.screen import screen
    from flats.tests.test_clear_objective import facts, rules
    from flats.tests.test_round2_rulings import DESIGN, fit

    return screen(
        rules(),
        facts(inside_ugb=inside_ugb),
        DESIGN,
        fit(),
        policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}),
        relief=relief.load_policy(),
        config=Configuration(conditions=conditions),
    )


def test_asc_1_carries_its_flag_below_the_yellow_line_and_keeps_the_colour() -> None:
    """Steph 2026-10-30: "Leave it. Green with a flag"."""
    from flats.score.flags import Colour, colour_rules, load_registry

    entry = load_registry()["BETHANY-ASC1-PD-CONDITIONS"]
    assert entry.severity < colour_rules().yellow_at_severity
    plain = _bethany_screen(())
    got = _bethany_screen(("bethany_asc_1",))
    assert plain.colour is Colour.green and got.colour is Colour.green
    assert got.triage == plain.triage
    (flag,) = [f for f in got.flags if f.code == "BETHANY-ASC1-PD-CONDITIONS"]
    # One answer for every lot in ASC 1 -- R&O 94-104 -- so the key is the place.
    assert flag.by == "BETHANY_ASC1_PD" and flag.key == "or/test/round2"
    assert not [f for f in plain.flags if f.code == "BETHANY-ASC1-PD-CONDITIONS"]


def test_asc_1a_type_iii_is_green_with_clear_objective_inside_the_ugb() -> None:
    from flats.score.flags import Colour
    from flats.score.screen import CLOSER_LOOK_REVIEW_CONDITIONS

    got = _bethany_screen(("bethany_asc_1", "bethany_asc_1a"))
    assert got.colour is Colour.green
    (flag,) = [f for f in got.flags if f.code == "CLEAR-OBJECTIVE"]
    assert "bethany_asc_1a" in flag.key and "Type III" in flag.source
    outside = _bethany_screen(("bethany_asc_1", "bethany_asc_1a"), inside_ugb=False)
    assert outside.colour is Colour.yellow
    assert CLOSER_LOOK_REVIEW_CONDITIONS in outside.reasons
    assert [f for f in outside.flags if f.code == "REVIEW-CONDITIONS"]


def test_asc_1_and_1a_line_numbers_name_the_rules() -> None:
    text = " ".join(
        ProvenanceStore().quote(f"{WASHINGTON}/community-plan.bethany.txt#L870-L872,L876-L877,L1035-L1037").split()
    )
    assert "has been designated as an Area of Special Concern (Area of Special Concern No. 1)" in text
    assert "All development in ASC 1 shall comply with the conditions of approval for the Central Bethany" in text
    assert "Order No. 94-104" in text
    text = " ".join(ProvenanceStore().quote(f"{WASHINGTON}/community-plan.bethany.txt#L1047-L1048,L1055-L1058").split())
    assert "Area of Special Concern 1A" in text
    assert "All development applications in ASC 1A shall be processed through the Type III procedure" in text


# --- Raleigh Hills - Garden Home and Bull Mountain (FOLLOWUPS 109 chunk 7) ---

C7_AREAS = {
    "washington_plan_rule_unmeasured": "or/washington/_unincorporated/washington-plan-rule-unmeasured-lots.geojson",
    "washington_plan_review": "or/washington/_unincorporated/washington-plan-review.geojson",
}
C7_HELD_ZONES = ("R-5", "R-6", "R-9", "R-15", "R-24")


def _c7_file(name: str) -> dict:
    import json

    from flats.rules import loader

    data = json.loads((loader.AREAS_ROOT / C7_AREAS[name]).read_text(encoding="utf-8"))
    assert data["source"]["drawn"] is True
    return data


@pytest.mark.parametrize("name", sorted(C7_AREAS))
def test_chunk_7_plan_areas_are_unassumed_drawn_facts(washington: Layer, name: str) -> None:
    from flats.rules.conditions import DRAWN_CONDITIONS, condition

    area = washington.drawn_areas[name]
    assert area.condition == name and area.file == C7_AREAS[name]
    fact = condition(name)
    assert fact.kind == "site_fact" and fact.assume is None
    assert name in DRAWN_CONDITIONS


def test_the_plan_hold_sits_on_the_garage_entrance_yard_of_r5_to_r24_only(washington: Layer) -> None:
    for zone in C7_HELD_ZONES:
        field = washington.zones[zone].values["setback_garage_entrance_ft"]
        assert field.qualified_by == "washington_plan_rule_unmeasured", zone
        assert zone in washington.drawn_areas["washington_plan_rule_unmeasured"].zones
    # North Bethany restates the yard for its own ASC 5 hold; chunk 7 does not reach it.
    for zone in ("R-6 NB", "R-9 NB", "R-15 NB", "R-24 NB"):
        levers = set().union(*(v.levers for v in washington.zones[zone].values.values()))
        assert "washington_plan_rule_unmeasured" not in levers, zone


def test_every_held_lot_is_whole_residential_and_names_its_rule() -> None:
    from shapely.geometry import shape

    data = _c7_file("washington_plan_rule_unmeasured")
    feats = data["features"]
    assert len(feats) == 101
    plans = {f["properties"]["plan"] for f in feats}
    assert plans == {"Raleigh Hills - Garden Home", "Bull Mountain"}
    for f in feats:
        p = f["properties"]
        assert p["answer"] == "inside" and p["drawn_share_of_lot"] == 1
        assert p["zone"] in C7_HELD_ZONES and p["why"] and "#L" in p["quote"]
        assert shape(f["geometry"]).is_valid
    whys = " ".join(f["properties"]["why"] for f in feats)
    for rule in ("ASC S", "ASC T", "ASC M", "ASC U", "ASC 1", "Pacific Highway", "pedestrian"):
        assert rule in whys, rule
    assert sum(data["source"]["counts"].values()) == 101


def test_a_held_lot_is_inside_and_a_lot_off_the_maps_is_not() -> None:
    from shapely.geometry import box, shape

    feats = _c7_file("washington_plan_rule_unmeasured")["features"]
    (mayo,) = [f for f in feats if f["properties"]["taxlot"] == "1S125AA07500"]
    assert "SW MAYO ST" in mayo["properties"]["why"]
    lot = shape(mayo["geometry"])
    assert _nb_facts("R-5", lot)["washington_plan_rule_unmeasured"] is True
    minx, miny, _, _ = lot.bounds
    far = box(minx - 9000, miny - 9000, minx - 8900, miny - 8900)
    got = _nb_facts("R-5", far)
    assert got["washington_plan_rule_unmeasured"] is False


def test_bull_mountain_asc_8_is_green_with_clear_objective_inside_the_ugb() -> None:
    from flats.score.flags import Colour
    from flats.score.screen import CLOSER_LOOK_REVIEW_CONDITIONS

    got = _bethany_screen(("washington_plan_review",))
    assert got.colour is Colour.green
    (flag,) = [f for f in got.flags if f.code == "CLEAR-OBJECTIVE"]
    assert "washington_plan_review" in flag.key and "Area of Special Concern 8" in flag.source
    outside = _bethany_screen(("washington_plan_review",), inside_ugb=False)
    assert outside.colour is Colour.yellow
    assert CLOSER_LOOK_REVIEW_CONDITIONS in outside.reasons


def test_the_asc_8_outline_carries_its_cut_lots_and_the_r25_site() -> None:
    from shapely.geometry import shape

    data = _c7_file("washington_plan_review")
    by = {f["properties"]["asc"]: f for f in data["features"]}
    assert set(by) == {"8", "L"}
    assert by["L"]["properties"]["taxlot"] == "1S113BC00200"
    assert 4.0 < shape(by["L"]["geometry"]).area / 43_560 < 4.1
    for tl in ("2S116D000200", "2S115CB00400", "2S115C000901"):
        assert tl in data["source"]["how"]
    lot = shape(by["8"]["geometry"]).representative_point().buffer(4, cap_style=3)
    assert _nb_facts("R-9", lot)["washington_plan_review"] is True


def test_chunk_7_line_numbers_name_the_rules() -> None:
    def q(ref: str) -> str:
        return " ".join(ProvenanceStore().quote(f"{WASHINGTON}/{ref}").split())

    rh = "community-plan.raleigh-hills-garden-home.txt"
    bm = "community-plan.bull-mountain.txt"
    text = q(f"{rh}#L1218-L1223")
    assert "Access for development in ASC S shall be restricted to one point on Mayo Street and two points on" in text
    assert "ASC T from this area shall be restricted to two points on Taylors Ferry" in text
    assert "limited to one point on Raab" in q(f"{rh}#L971-L972")
    assert "Permanent access onto Beaverton - Hillsdale Highway shall not be permitted" in q(f"{rh}#L855-L856")
    assert "Type 1 Screening and Buffering" in q(f"{rh}#L936-L937,L956-L958")
    assert "Case #74-96C" in q(f"{rh}#L1083-L1086")
    assert "shall be constructed as part of the development of the affected properties" in q(f"{rh}#L1335-L1340")
    assert "Type III review provisions of the CDC" in q(f"{rh}#L1134-L1137")
    text = q(f"{bm}#L769-L779")
    assert "no more than three access points to Beef Bend Road" in text
    assert "No development application for the easterly portion of ASC No. 1 shall be submitted until this traffic study is accepted" in text
    assert "oriented toward or accessed from Pacific" in q(f"{bm}#L998-L1000")
    assert "master planning - planned development provisions in the CDC" in q(f"{bm}#L1002-L1005")
    assert "shall be constructed as part of the development of the affected properties" in q(f"{bm}#L1254-L1262")
