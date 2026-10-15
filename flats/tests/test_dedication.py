"""Road land a lot gives up, or the extra yard it keeps, to reach a distance
from the street's centre line (flats/geom/dedication.py).

Washington County CDC 302-2.14 C(1) and its twins (25 / 30 / 37 / 45 ft by
county class), Sherwood 16.106.030 D (26 / 32 / 32 / 37 / 61 ft by city
class), King City 16.80.060 A (33 / 30 ft on named streets, 25 elsewhere),
Oregon City Table 16.12.016 (half the widest right-of-way of the class, or of
the row the zones on both sides stand in for, FOLLOWUPS 82) and
Milwaukie Table 19.501.2.A (25 / 30 / 40 ft on named streets) and Tigard
18.210.030.A.1 (half the widest right-of-way of Table 18.910.1 by TSP class,
FOLLOWUPS 81). These tests pin
each city's distance, what is assumed when nothing can be read, that the
strip comes off the envelope like a setback, and that every layer one of these
rules reaches is measured. Geometry sits at real Oregon State Plane North
coordinates (feet), where the bridge's lots do.
"""

from __future__ import annotations

import json

import pytest
import shapely
from shapely.geometry import LineString

from flats.geom import dedication
from flats.geom.corridor import Lines
from flats.geom.edges import EdgeClass
from flats.geom.street_class import CLASS_MAPS, PRIVATE_RANK, ClassMap
from flats.ingest.quadfit import (
    ROAD_ZONE_STANDIN,
    dedicated,
    envelope_for,
    lot_from_row,
    road_standin,
    screen_lot,
)
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

WASHCO = "or/washington/_unincorporated"
SHERWOOD = "or/washington/sherwood"
KING_CITY = "or/washington/king-city"
OREGON_CITY = "or/clackamas/oregon-city"
MILWAUKIE = "or/clackamas/milwaukie"
TIGARD = "or/washington/tigard"
# A lot in unincorporated Washington County near Bull Mountain.
X0, Y0 = 7_620_000.0, 650_000.0
FRONT = [X0, Y0, X0 + 50, Y0, "F"]
EDGES = [
    FRONT,
    [X0 + 50, Y0, X0 + 50, Y0 + 100, "S"],
    [X0 + 50, Y0 + 100, X0, Y0 + 100, "R"],
    [X0, Y0 + 100, X0, Y0, "S"],
]


@pytest.fixture(scope="module")
def layers():
    return load_rules()


@pytest.fixture(scope="module")
def rules(layers):
    return RuleSet(layers)


def road(half: float | None, public: bool = True, names=None, classes=None) -> list[object]:
    return [*dedication.key(*FRONT[:4]), half, public, names, classes or {}]


def row(half: float | None, washington: str | None, public: bool = True, names=None, classes=None) -> dict[str, object]:
    got = {"street_class_washington": washington} if classes is None else classes
    return {
        "TLID": "2S109AA  -01200",
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
        "road_widths_json": json.dumps([road(half, public, names, got)]),
    }


def strip(rules, layer: str, zone: str, half: float | None, names=None, classes=None, public: bool = True) -> float:
    """The strip the lot's front line gives up under ``layer``'s ``zone``."""
    lot = lot_from_row(row(half, None, public, names, classes or {}))
    out = dedicated(lot.edges, rules.resolve(layer, zone))
    (front,) = [e for e in out.edges if e.cls is EdgeClass.front]
    return front.dedication_ft


def sqft(rules, half: float | None, washington: str | None, public: bool = True) -> float:
    lot = lot_from_row(row(half, washington, public))
    env = envelope_for(lot, rules.resolve(WASHCO, "R-6"))
    assert env.source == "flats"
    return env.sqft


def side_span(rules) -> float:
    lot = lot_from_row(row(25.0, "local"))
    return 50.0 - 2 * envelope_for(lot, rules.resolve(WASHCO, "R-6")).setbacks.side_ft


# --- the arithmetic -------------------------------------------------------


def test_the_depth_is_the_shortfall_and_never_below_zero() -> None:
    assert dedication.depth_ft(25.0, 20.5) == pytest.approx(4.5)
    assert dedication.depth_ft(25.0, 25.0) == 0.0
    assert dedication.depth_ft(25.0, 31.0) == 0.0


def test_an_unmeasured_line_gives_up_the_whole_distance() -> None:
    assert dedication.depth_ft(30.0, None) == 30.0


def test_a_street_name_reads_the_same_in_the_code_and_in_metros_file() -> None:
    assert dedication.street_key("Johnson Creek Boulevard") == dedication.street_key("SE JOHNSON CREEK BLVD")
    assert dedication.street_key("131st Avenue") == dedication.street_key("SW 131ST AVE")
    assert dedication.street_key("Harrison Street (Milwaukie Expressway to 44th Ave.)") == "HARRISON ST"
    assert dedication.street_key("Royalty Parkway") == dedication.street_key("SW ROYALTY PKWY")
    assert dedication.street_key("Pacific Highway") == dedication.street_key("SW PACIFIC HWY")


# --- Washington County (CDC 302-2.14 C(1)) ---------------------------------


@pytest.mark.parametrize(
    ("name", "bucket", "centreline_ft", "due"),
    [
        # 1S201CC12500: Neighborhood Route, centreline 26.4 ft off -> 3.6 ft due.
        ("1S201CC12500", "neighborhood_route", 26.4, 3.6),
        # 1N120AD09600: local streets, 42 ft and 46 ft wide, the centreline midway.
        ("1N120AD09600 front", "local", 21.0, 4.0),
        ("1N120AD09600 side", "local", 23.0, 2.0),
        # The nine sample lots that were right stay right.
        ("lot 5", "neighborhood_route", 24.7, 5.3),
        ("lot 7", "neighborhood_route", 24.0, 6.0),
        ("lot 9", "neighborhood_route", 25.0, 5.0),
        ("lot 11", "neighborhood_route", 26.7, 3.3),
        ("lot 8, a collector already 37.6 ft out", "collector", 37.6, 0.0),
    ],
)
def test_the_washington_county_sample_lots_give_up_what_the_code_asks(rules, name, bucket, centreline_ft, due) -> None:
    got = strip(rules, WASHCO, "R-6", centreline_ft, classes={"street_class_washington": bucket})
    assert got == pytest.approx(due, abs=0.05), name


def test_washington_county_reads_its_four_classes_and_an_unread_one_is_an_arterial(rules) -> None:
    def at(bucket):
        return strip(rules, WASHCO, "R-6", 0.0, classes={"street_class_washington": bucket})

    assert [at(b) for b in ("local", "neighborhood_route", "collector", "arterial")] == [25, 30, 37, 45]
    assert at(None) == 45
    # A line no county map read at all (the map missing from the snapshot).
    assert strip(rules, WASHCO, "R-6", 0.0, classes={}) == 45


def test_every_middle_housing_district_states_the_four_distances(rules) -> None:
    names = [dedication.CLASS_FIELDS[c] for c in ("local", "neighborhood_route", "collector", "arterial")]
    for zone in ("R-5", "R-6", "R-9", "R-15", "R-24", "R-25+", "R-6 NB", "R-9 NB", "R-15 NB", "TO:R9-12", "TO:R12-18", "TO:R18-24"):
        got = rules.resolve(WASHCO, zone)
        assert [got.get(n) for n in names] == [25, 30, 37, 45], zone
        assert got.get(dedication.CLASS_BY_FIELD) == "washington_county", zone


def test_a_narrow_local_road_loses_the_strip(rules) -> None:
    full = sqft(rules, 25.0, "local")
    narrow = sqft(rules, 20.5, "local")
    assert full - narrow == pytest.approx(4.5 * side_span(rules))


def test_a_full_width_road_loses_nothing(rules) -> None:
    assert sqft(rules, 25.0, "local") == pytest.approx(sqft(rules, 40.0, "local"))


def test_an_unmeasured_road_takes_the_worst_case(rules) -> None:
    assert sqft(rules, 25.0, "local") - sqft(rules, None, "local") == pytest.approx(25.0 * side_span(rules))


def test_an_unread_class_takes_the_deepest_distance(rules) -> None:
    assert sqft(rules, 25.0, "local") - sqft(rules, 25.0, None) == pytest.approx(20.0 * side_span(rules))


def test_a_private_road_gives_up_nothing(rules) -> None:
    assert sqft(rules, None, None, public=False) == pytest.approx(sqft(rules, 40.0, "local"))


def test_a_code_without_the_distances_is_untouched(rules) -> None:
    lot = lot_from_row(row(20.0, "local"))
    for layer, zone in (("or/multnomah/portland", "CM2"), ("or/washington/beaverton", "RMA")):
        assert dedicated(lot.edges, rules.resolve(layer, zone)) is lot.edges, layer


# --- Sherwood (16.106.030 D) -----------------------------------------------


def test_sherwood_adds_its_class_distances(rules) -> None:
    def at(bucket, half=20.0):
        return strip(rules, SHERWOOD, "MDRL", half, classes={"street_class_sherwood": bucket})

    assert [at(b) for b in ("local", "neighborhood_route", "collector", "arterial", "principal_arterial")] == [
        6,
        12,
        12,
        17,
        41,
    ]
    assert at("local", 30.0) == 0.0


def test_sherwood_reads_its_own_map_not_the_countys(rules) -> None:
    # The county map calls it a collector; Sherwood's own map is what 16.106 reads.
    got = strip(
        rules,
        SHERWOOD,
        "MDRL",
        20.0,
        classes={"street_class_washington": "collector", "street_class_sherwood": "local"},
    )
    assert got == 6.0


def test_sherwood_unranked_takes_the_99w_distance(rules) -> None:
    assert strip(rules, SHERWOOD, "MDRL", 20.0, classes={"street_class_sherwood": None}) == 41.0
    assert strip(rules, SHERWOOD, "MDRL", None, classes={"street_class_sherwood": "local"}) == 26.0


def test_sherwoods_map_is_read_for_the_dedication_only() -> None:
    spec = CLASS_MAPS["street_class_sherwood"]
    assert spec.access is False
    assert dedication.BUCKETS["street_class_sherwood"] == {
        0: "local",
        1: "neighborhood_route",
        2: "collector",
        3: "arterial",
        4: "principal_arterial",
    }


# --- King City (16.80.060 A) -----------------------------------------------


@pytest.mark.parametrize(
    ("street", "distance"),
    [
        (["BEEF BEND RD"], 33),
        (["131ST AVE"], 33),
        (["FISCHER RD"], 33),
        (["116TH AVE"], 30),
        (["ROYALTY PKWY"], 30),
        (["PACIFIC HWY"], 61),
        (["MONARCH DR"], 25),
        # A line that may be on either of two streets takes the deeper.
        (["MONARCH DR", "FISCHER RD"], 33),
    ],
)
def test_king_city_reads_its_named_streets(rules, street, distance) -> None:
    assert strip(rules, KING_CITY, "KTTC", 0.0, names=street) == distance


def test_king_city_unread_street_takes_the_deepest(rules) -> None:
    assert strip(rules, KING_CITY, "KTTC", 0.0, names=None) == 61


def test_king_city_county_pockets_read_the_countys_rule(rules, layers) -> None:
    ruling = layers[KING_CITY].zone_rulings["R-9 (WC)"]
    assert ruling.outcome == "pocket" and ruling.of == WASHCO
    county = rules.resolve(WASHCO, ruling.pocket_code("R-9 (WC)") or "R-9")
    assert dedication.rule_of(county).class_by == "washington_county"


# --- Oregon City (16.12.011.B, Table 16.12.016) ----------------------------


def test_oregon_city_takes_half_the_widest_right_of_way(rules) -> None:
    def at(bucket):
        return strip(rules, OREGON_CITY, "R-6", 0.0, classes={"street_class_oregon_city": bucket})

    assert [at(b) for b in ("local", "collector", "minor_arterial", "major_arterial")] == [31, 44, 59, 63]
    # Expressway and Freeway have no row in the table; unranked likewise.
    assert at(None) == 63


def test_oregon_city_holds_the_printed_widths(rules) -> None:
    got = rules.resolve(OREGON_CITY, "R-6")
    assert [got.get(dedication.CLASS_FIELDS[c]) for c in ("local", "collector", "minor_arterial", "major_arterial")] == [
        62,
        88,
        118,
        126,
    ]
    assert got.get(dedication.WIDTH_FIELD) is True


def test_an_oregon_city_street_already_wide_enough_gives_up_nothing(rules) -> None:
    assert strip(rules, OREGON_CITY, "R-6", 31.0, classes={"street_class_oregon_city": "local"}) == 0.0
    assert strip(rules, OREGON_CITY, "R-6", 27.0, classes={"street_class_oregon_city": "local"}) == 4.0


# --- Oregon City: the zone across the street stands in (FOLLOWUPS 82) ------
#
# Table 16.12.016 keys the right-of-way to the class AND to "the comprehensive
# plan designation of the adjacent properties", the wider where the two sides
# differ. Steph 2026-10-14: the measured zone on each side stands in for its
# designation (Table 17.06.030), the lot is flagged OC-ROAD-ZONE-STANDIN at
# severity 2, and the widest row stays wherever the land across is unread or
# its zone maps to no clear designation. 22E32CB08800, an R-6 lot on a local
# street with MUC-1 across, is where these lots sit.
OC_X, OC_Y = 7_663_270.0, 620_550.0


def oc_row(
    across: list[list[str]] | None,
    half: float | None = 25.0,
    bucket: str | None = "local",
    zone: str = "R-6",
    w: float = 100.0,
    d: float = 200.0,
    unresolved: str | None = None,
) -> dict[str, object]:
    """An Oregon City lot ``w`` by ``d``, its street along the south line;
    ``across`` is the rays' ``[jurisdiction, zone]`` pairs for that line."""
    edges = [
        [OC_X, OC_Y, OC_X + w, OC_Y, "F"],
        [OC_X + w, OC_Y, OC_X + w, OC_Y + d, "S"],
        [OC_X + w, OC_Y + d, OC_X, OC_Y + d, "R"],
        [OC_X, OC_Y + d, OC_X, OC_Y, "S"],
    ]
    rays: dict[str, object] | None = None
    if across is not None:
        rays = {"z": across, "split": 0, "none": 0, "near": 0}
        if unresolved:
            rays[unresolved] = 1
    return {
        "TLID": "22E32CB08800",
        "jurisdiction": "oregon_city",
        "zone": zone,
        "tier": "A",
        "area_sqft": w * d,
        "frontage_ft": w,
        "lot_width_ft": w,
        "lot_depth_ft": d,
        "edges_json": json.dumps(edges),
        "front_bearings_json": "[0.0]",
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "ovl_oregon_city_nrod_sqft": 0.0,
        "ovl_fema_sfha": False,
        "ovl_fema_floodway": False,
        "sewer_main_dist_ft": 12.0,
        "in_sewer_district": None,
        "wkb": shapely.to_wkb(shapely.box(OC_X + 5, OC_Y + 10, OC_X + w - 5, OC_Y + d - 15)),
        "lot_wkb": shapely.to_wkb(shapely.box(OC_X, OC_Y, OC_X + w, OC_Y + d)),
        "road_widths_json": json.dumps(
            [[*dedication.key(*edges[0][:4]), half, True, ["MAIN ST"], {"street_class_oregon_city": bucket}]]
        ),
        "street_across_json": json.dumps([rays, None, None, None]),
    }


def oc_lot(layers, across, **kw):
    return lot_from_row(oc_row(across, **kw), layers)


def oc_strip(rules, layers, across, zone: str = "R-6", **kw) -> float:
    lot = oc_lot(layers, across, zone=zone, **kw)
    out = dedicated(lot.edges, rules.resolve(OREGON_CITY, lot.zone), lot.zone)
    (front,) = [e for e in out.edges if e.cls is EdgeClass.front]
    return front.dedication_ft


def city(*zones: str) -> list[list[str]]:
    return [["oregon_city", z] for z in zones]


def test_oregon_city_holds_every_row_of_the_table(rules) -> None:
    rule = dedication.rule_of(rules.resolve(OREGON_CITY, "R-6"))
    # Half of each printed width: the table states the whole street section.
    assert {c: dict(r) for c, r in rule.by_designation.items()} == {
        "major_arterial": {"commercial": 58.0, "industrial": 60.0, "residential": 63.0},
        "minor_arterial": {"commercial": 58.0, "industrial": 59.0, "residential": 50.0},
        "collector": {"commercial": 43.0, "industrial": 44.0, "residential": 42.5},
        "local": {"commercial": 31.0, "industrial": 30.0, "residential": 27.0},
    }
    # The class fields keep each class's widest row.
    assert {c: max(r.values()) for c, r in rule.by_designation.items()} == {
        c: rule.classes[c] for c in rule.by_designation
    }


def test_every_oregon_city_zone_in_table_17_06_030_has_one_designation(layers) -> None:
    got = dedication.DESIGNATIONS["oregon_city"]
    assert {z for z, d in got.items() if d == "residential"} == {"R-10", "R-8", "R-6", "R-5", "R-3.5", "R-2"}
    assert {z for z, d in got.items() if d == "industrial"} == {"CI", "GI"}
    assert {z for z, d in got.items() if d == "commercial"} == {
        "C", "MUD", "WFDD", "NC", "HC", "MUC-1", "MUC-2", "MUE",
    }
    # Public/quasi-public OR park (17.39.010), and the street table has no
    # park row: the I zone maps to nothing and keeps the widest.
    assert "I" not in got
    # Every mapped zone is one the city's layer screens.
    assert set(got) <= set(layers[OREGON_CITY].zones)


def test_residential_on_both_sides_takes_the_residential_row(rules, layers) -> None:
    # Local: 54 ft right-of-way, 27 to the centre line; the street is 25 ft
    # to its centre line, so 2 ft comes off, not the widest row's 6.
    assert oc_strip(rules, layers, city("R-8")) == pytest.approx(2.0)
    assert oc_strip(rules, layers, city("R-10", "R-3.5")) == pytest.approx(2.0)
    assert oc_strip(rules, layers, city("R-8"), bucket="collector", half=40.0) == pytest.approx(2.5)
    assert oc_strip(rules, layers, city("R-8"), bucket="minor_arterial", half=40.0) == pytest.approx(10.0)
    # Residential IS the widest major arterial row: nothing changes.
    assert oc_strip(rules, layers, city("R-8"), bucket="major_arterial", half=40.0) == pytest.approx(23.0)


def test_the_wider_side_governs(rules, layers) -> None:
    # MUC-1 across a local street: the commercial row, 62 ft, is the widest.
    assert oc_strip(rules, layers, city("MUC-1")) == pytest.approx(6.0)
    # A collector: commercial 86 beats residential 85, both short of 88.
    assert oc_strip(rules, layers, city("MUC-1"), bucket="collector", half=40.0) == pytest.approx(3.0)
    # The lot's own zone is a side too: a commercial lot facing houses.
    assert oc_strip(rules, layers, city("R-6"), zone="C") == pytest.approx(6.0)
    # One commercial ray among residential ones takes the commercial row.
    assert oc_strip(rules, layers, city("R-6", "MUC-1")) == pytest.approx(6.0)
    # Industrial across a local street: 60 ft.
    assert oc_strip(rules, layers, city("GI")) == pytest.approx(5.0)


@pytest.mark.parametrize(
    ("across", "unresolved", "why"),
    [
        (None, None, "no rays across"),
        ([], None, "the rays found nothing"),
        (city("R-6"), "near", "a ray stopped nearer than a street's width"),
        (city("R-6"), "split", "a ray found a split-zone lot"),
        (city("R-6"), "none", "a ray found no zoning"),
        ([["clackamas_unincorporated", "R-10"]], None, "the land across is the county's"),
        ([["oregon_city", "R-6"], ["clackamas_unincorporated", "R-10"]], None, "part of it is the county's"),
        (city("I"), None, "public/quasi-public or park"),
        (city("R-6", "I"), None, "one of the rays maps to no row"),
        (city("County"), None, "a zone with no plan classification"),
    ],
)
def test_the_widest_row_stays_where_the_land_across_is_not_read(rules, layers, across, unresolved, why) -> None:
    assert oc_strip(rules, layers, across, unresolved=unresolved) == pytest.approx(6.0), why


def test_the_widest_row_stays_where_the_class_or_own_zone_is_not_read(rules, layers) -> None:
    # Unranked: the deepest of the table, whatever the land beside it.
    assert oc_strip(rules, layers, city("R-6"), bucket=None, half=40.0) == pytest.approx(23.0)
    # The lot's own I zone maps to no row.
    assert oc_strip(rules, layers, city("R-6"), zone="I") == pytest.approx(6.0)


def test_without_the_corpus_nothing_is_read_across(rules) -> None:
    lot = lot_from_row(oc_row(city("R-6")))
    assert all(e.across_zones is None for e in lot.edges.edges)
    out = dedicated(lot.edges, rules.resolve(OREGON_CITY, "R-6"), "R-6")
    assert [e.dedication_ft for e in out.edges if e.cls is EdgeClass.front] == [pytest.approx(6.0)]


def test_a_code_without_designation_rows_has_no_stand_in(rules, layers) -> None:
    # Sherwood keys its distances to the class alone.
    lot = oc_lot(layers, city("R-6"))
    assert road_standin(lot.edges, rules.resolve(SHERWOOD, "MDRL"), "R-6") is None


def test_the_stand_in_reports_the_strip_it_saved(rules, layers) -> None:
    got = rules.resolve(OREGON_CITY, "R-6")
    assert road_standin(oc_lot(layers, city("R-8")).edges, got, "R-6") == pytest.approx((2.0, 6.0))
    # Nothing saved: the widest row stood, or the street is already wide.
    assert road_standin(oc_lot(layers, city("MUC-1")).edges, got, "R-6") is None
    assert road_standin(oc_lot(layers, city("R-8"), half=31.0).edges, got, "R-6") is None


@pytest.fixture(scope="module")
def corpus():
    from flats.encode.load import load_trusted

    return load_trusted(strict=False).rules


def oc_screened(corpus, across):
    from flats.designs.model import load_catalog
    from flats.score import relief, slack

    (s,) = screen_lot(
        oc_lot(corpus.layers, across),
        [load_catalog().latest("pod56x36")],
        rules=corpus,
        policy=slack.load_policy(),
        relief=relief.load_policy(),
        step_deg=30.0,
    )
    return s


def test_an_otherwise_green_lot_stays_green_with_the_flag_beside_it(corpus) -> None:
    """Steph 2026-10-14: the stand-in flag must leave the lot GREEN."""
    from flats.score import flags as flag_plan

    widest = oc_screened(corpus, None)
    standin = oc_screened(corpus, city("R-8"))
    # The same lot read at the widest row: green, and no stand-in.
    assert widest.signed.colour is flag_plan.Colour.green
    assert ROAD_ZONE_STANDIN not in {f.code for f in widest.signed.flags}
    # Read with the zones standing in: still green, the flag beside it, with
    # the strip taken and the strip the widest row would take.
    assert standin.signed.colour is flag_plan.Colour.green
    (flag,) = [f for f in standin.signed.flags if f.code == ROAD_ZONE_STANDIN]
    assert flag.bounds == pytest.approx((2.0, 6.0))
    assert flag_plan.severity_of(flag) == 2 < flag_plan.colour_rules().yellow_at_severity
    assert standin.screening.triage is widest.screening.triage
    # The envelope it was fitted on got back the 4 ft the stand-in saved.
    assert standin.envelope.sqft > widest.envelope.sqft


# --- Milwaukie (Table 19.501.2.A) -----------------------------------------


@pytest.mark.parametrize(
    ("street", "distance"),
    [
        (["KING RD"], 40),
        (["JOHNSON CREEK BLVD"], 30),
        (["LOGUS RD"], 25),
        # Listed at 40 and at 30 for two stretches: the stretch is not read.
        (["HARRISON ST"], 40),
        (["17TH AVE"], 40),
        # A street the table leaves out takes none.
        (["MCLOUGHLIN BLVD"], 0),
        (["WAVERLY CT"], 0),
    ],
)
def test_milwaukie_reads_its_major_streets(rules, street, distance) -> None:
    assert strip(rules, MILWAUKIE, "R-MD", 0.0, names=street) == distance


def test_milwaukie_unread_street_takes_the_deepest(rules) -> None:
    assert strip(rules, MILWAUKIE, "R-MD", 0.0, names=None) == 40
    assert strip(rules, MILWAUKIE, "R-MD", None, names=["KING RD"]) == 40


def test_milwaukie_lists_all_twenty_nine_rows(rules) -> None:
    table = rules.resolve(MILWAUKIE, "R-MD").get(dedication.NAMED_FIELD)
    assert len(table) == 29
    assert sorted({ft for _, ft in table}) == [25, 30, 40]


# --- Tigard (18.210.030.A.1, Table 18.910.1) ------------------------------
#
# Setbacks are measured from "the ultimate right-of-way width as shown in the
# Transportation System Plan"; the TSP sends the widths to Table 18.910.1,
# keyed to its functional class. Each class holds the top of its printed
# range, half of it from the centre line: Local 54 -> 27, Neighborhood Route
# 58 -> 29, Collector 96 -> 48, Arterial 128 -> 64. River Terrace Boulevard
# states its own 110 ft (55); downtown (MU-CBD) local and neighbourhood
# streets hold the widest street character row, 74 ft (37). A street name is
# passed below: Tigard lists one street by name, so an unread name takes the
# deepest distance, as in King City and Milwaukie.


def tigard(rules, bucket, half=20.0, zone="RES-B", names=("MAIN ST",)):
    return strip(
        rules,
        TIGARD,
        zone,
        half,
        names=list(names) if names is not None else None,
        classes={"street_class_tigard": bucket},
    )


def test_tigard_takes_half_the_widest_right_of_way_of_its_class(rules) -> None:
    assert [tigard(rules, b) for b in ("local", "neighborhood_route", "collector", "arterial")] == [7, 9, 28, 44]
    assert tigard(rules, "local", half=27.0) == 0.0
    assert tigard(rules, "local", half=25.5) == pytest.approx(1.5)


def test_tigard_holds_the_printed_widths(rules) -> None:
    got = rules.resolve(TIGARD, "RES-B")
    assert [got.get(dedication.CLASS_FIELDS[c]) for c in ("local", "neighborhood_route", "collector", "arterial")] == [
        54,
        58,
        96,
        128,
    ]
    assert got.get(dedication.WIDTH_FIELD) is True
    assert got.get(dedication.CLASS_BY_FIELD) == "tigard"


def test_tigard_unranked_unread_or_unmeasured_takes_the_arterial_distance(rules) -> None:
    # A Freeway, an "Other" line, a line no TSP line runs on: unranked.
    assert tigard(rules, None) == 44
    # The map missing from the snapshot.
    assert strip(rules, TIGARD, "RES-B", 20.0, names=["MAIN ST"], classes={}) == 44
    # No centre line close enough: the whole deepest distance.
    assert tigard(rules, "local", half=None, names=None) == 64
    # A centre line read but no name: the deepest.
    assert tigard(rules, "local", names=None) == 44


def test_tigard_reads_its_own_map_not_the_countys(rules) -> None:
    got = strip(
        rules,
        TIGARD,
        "RES-B",
        20.0,
        names=["MAIN ST"],
        classes={"street_class_washington": "collector", "street_class_tigard": "local"},
    )
    assert got == 7.0


def test_river_terrace_boulevard_is_half_its_own_110_feet(rules) -> None:
    # Metro's name, read the way the bridge reads it.
    metro = [dedication.street_key("SW RIVER TERRACE BLVD")]
    assert metro == [dedication.street_key("River Terrace Boulevard")]
    for zone in ("RES-B", "RES-C"):
        assert tigard(rules, "collector", zone=zone, names=metro) == 35, zone
        # Its own standard governs whatever class the map reads.
        assert tigard(rules, "arterial", zone=zone, names=metro) == 35, zone


def test_downtown_local_streets_hold_the_widest_street_character_row(rules) -> None:
    assert tigard(rules, "local", zone="MU-CBD") == 17
    assert tigard(rules, "neighborhood_route", zone="MU-CBD") == 17
    # The Collector and Arterial rows are wider already and stand.
    assert tigard(rules, "collector", zone="MU-CBD") == 28
    assert tigard(rules, "arterial", zone="MU-CBD") == 44


def test_tigards_map_is_read_for_the_dedication_only() -> None:
    from flats.geom.street_class import class_rank

    spec = CLASS_MAPS["street_class_tigard"]
    assert spec.access is False
    buckets = dedication.BUCKETS["street_class_tigard"]
    assert buckets == {-1: "local", 0: "local", 1: "neighborhood_route", 2: "collector", 3: "arterial", 4: "arterial"}

    def bucket(value):
        rank = class_rank(value, spec)
        return None if rank is None else buckets.get(rank)

    # The layer's CITY_TSP values, as served 2026-10-15.
    assert [bucket(v) for v in ("LOCAL", "Local", "PRIVATE")] == ["local"] * 3
    assert bucket("NEIGHBORHOOD") == "neighborhood_route"
    assert [bucket(v) for v in ("COLLECTOR", "MAJOR COLLECTOR", "MINOR COLLECTOR")] == ["collector"] * 3
    # Principal Arterial and the Hall Blvd STA stretch take the Arterial row.
    assert [bucket(v) for v in ("ARTERIAL", "STA", "PCPL Arterial")] == ["arterial"] * 3
    # No row: unread, the deepest.
    assert [bucket(v) for v in ("FREEWAY", "Other", "OTHER", None, "")] == [None] * 5


# A Tigard lot on SW 107th Ave near Greenburg Road, where the city's TSP line
# and Metro's centre line were checked to run together.
TX, TY = 7_614_700.0, 648_300.0
T_FRONT = [TX, TY, TX + 50, TY, "F"]
# Metro's centre line of the street the lot fronts, 21 ft out.
T_STREET = LineString([(TX - 500, TY - 21), (TX + 500, TY - 21)])


def _tigard_map(tsps, ranks, names, streets=(T_STREET,), street_names=("SW 107TH AVE",), types=None) -> ClassMap:
    """The city's TSP layer as loaded: its lines named from FULL_NAME
    ("107TH AVE", no direction) and matched to Metro's streets by name."""
    return ClassMap(
        serves=(TIGARD,),
        lines=Lines.build(list(tsps), [dedication.street_key(n) for n in names]),
        kinds=("",) * len(tsps),
        streets=Lines.build(list(streets), list(street_names)),
        types=tuple(types or (1500,) * len(streets)),
        ranks=tuple(ranks),
        key="street_class_tigard",
        by_name=True,
    )


def _tsp(y_off: float, x0: float = -400.0, x1: float = 400.0) -> LineString:
    return LineString([(TX + x0, TY - y_off), (TX + x1, TY - y_off)])


def tigard_rank(city: ClassMap, edge=T_FRONT) -> int | None:
    from flats.geom.street_class import edge_rank

    return edge_rank(edge[:4], city)


def test_tigard_reads_the_class_off_its_own_tsp_line_and_the_width_off_metros() -> None:
    county = _cmap([T_STREET], ["SW 107TH AVE"], (1500,), ranks=(2,))
    city = _tigard_map([_tsp(24)], [1], ["107TH AVE"])
    (got,) = dedication.measure([T_FRONT], TIGARD, [county, city])
    # The half-width is Metro's centre line, not the city's drawing.
    assert got[4] == pytest.approx(21.0) and got[5] is True and got[6] == ["107TH AVE"]
    assert got[7]["street_class_tigard"] == "neighborhood_route"
    # Outside Tigard the city's map is not read.
    (county_only,) = dedication.measure([FRONT], WASHCO, [county, city])
    assert "street_class_tigard" not in county_only[7]


def test_a_tigard_line_far_from_any_tsp_line_is_unread() -> None:
    county = _cmap([T_STREET], ["SW 107TH AVE"], (1500,), ranks=(0,))
    city = _tigard_map([_tsp(300)], [0], ["107TH AVE"])
    (got,) = dedication.measure([T_FRONT], TIGARD, [county, city])
    assert got[4] == pytest.approx(21.0)
    assert got[7]["street_class_tigard"] is None


def test_tigard_full_name_reads_as_metros_street_name() -> None:
    # FULL_NAME carries no direction; Metro's label does.
    assert dedication.street_key("GALLO AVE") == dedication.street_key("SW GALLO AVE") == "GALLO AVE"
    assert dedication.street_key("68TH PKWY") == dedication.street_key("SW 68TH PKWY")
    assert dedication.street_key("Walnut Terrace") == dedication.street_key("SW WALNUT TER")
    assert dedication.street_key(None) == ""


def test_tigard_matches_its_tsp_line_by_name_not_by_whichever_line_is_nearest() -> None:
    # The city drew 107th Ave 39 ft from Metro's line -- past the 30 ft a
    # position match allows -- and a differently named line right on top.
    named = _tigard_map([_tsp(60), _tsp(22)], [1, 3], ["107TH AVE", "WALNUT ST"])
    assert tigard_rank(named) == 1
    # Only the other street's line there: no match, unread.
    other = _tigard_map([_tsp(22)], [3], ["WALNUT ST"])
    assert tigard_rank(other) is None
    # A line the city left unnamed is not matched to a named street either.
    unnamed = _tigard_map([_tsp(22)], [0], [""])
    assert tigard_rank(unnamed) is None


def test_tigard_matches_by_position_only_where_neither_map_names_the_street() -> None:
    near = _tigard_map([_tsp(22)], [0], [""], street_names=("",))
    assert tigard_rank(near) == 0
    # Position alone stays strict: abreast and within 30 ft of Metro's line.
    apart = _tigard_map([_tsp(60)], [0], [""], street_names=("",))
    assert tigard_rank(apart) is None


def test_one_missed_sample_point_does_not_leave_a_tigard_line_unread() -> None:
    # The city's line starts 70 ft along: the first two sample points have
    # no 107th Ave line within 60 ft of Metro's, the other seven do. Until
    # FOLLOWUPS 81 every point had to read, and the line took the deepest.
    late = _tigard_map([_tsp(21, x0=70.0)], [0], ["107TH AVE"])
    assert tigard_rank(late) == 0
    # A sample point with no Metro street beside it is passed over too.
    stub = LineString([(TX + 12, TY - 21), (TX + 500, TY - 21)])
    short = _tigard_map([_tsp(21)], [0], ["107TH AVE"], streets=(stub,))
    assert tigard_rank(short) == 0
    # No point with a street beside it at all: unread.
    far = LineString([(TX - 500, TY - 300), (TX + 500, TY - 300)])
    assert tigard_rank(_tigard_map([_tsp(21)], [0], ["107TH AVE"], streets=(far,))) is None


def test_a_tigard_line_no_point_reads_takes_its_streets_line_close_by() -> None:
    # The city drew 107th Ave 16 ft inside Metro's line and stopped it 58 ft
    # before the lot: past 60 ft of every point's foot on Metro's line, but
    # within 60 ft of the lot line's end.
    before = _tigard_map([_tsp(5, x1=-58.0)], [2], ["107TH AVE"])
    assert tigard_rank(before) == 2
    # Another street's line there does not stand in.
    other = _tigard_map([_tsp(5, x1=-58.0)], [2], ["WALNUT ST"])
    assert tigard_rank(other) is None


def test_two_classes_on_one_tigard_line_take_the_wider() -> None:
    # 107th Ave changes from Local to Collector halfway along the lot.
    split = _tigard_map([_tsp(21, x1=25.0), _tsp(21, x0=25.0)], [0, 2], ["107TH AVE", "107TH AVE"])
    assert tigard_rank(split) == 2
    county = _cmap([T_STREET], ["SW 107TH AVE"], (1500,), ranks=(0,))
    (got,) = dedication.measure([T_FRONT], TIGARD, [county, split])
    assert got[7]["street_class_tigard"] == "collector"


def test_an_unranked_tsp_line_on_the_street_leaves_the_tigard_line_unread() -> None:
    # A Freeway or an "Other" line among those read: the deepest distance.
    mixed = _tigard_map([_tsp(21, x1=25.0), _tsp(21, x0=25.0)], [0, None], ["107TH AVE", "107TH AVE"])
    assert tigard_rank(mixed) is None


def _private_lot(city):
    """A lot line on SW Angus Ct, which Metro types a private road (1700)."""
    county = _cmap([T_STREET], ["SW ANGUS CT"], (1700,), ranks=(0,))
    maps = [county] if city is None else [county, city]
    (got,) = dedication.measure([T_FRONT], TIGARD, maps)
    return got


def _angus(tsps, ranks, names):
    return _tigard_map(tsps, ranks, names, street_names=("SW ANGUS CT",), types=(1700,))


def test_a_tigard_private_street_gives_up_nothing_only_where_both_maps_say_so(rules) -> None:
    # 18.910.020.E: "the term 'streets' shall mean 'public streets'"; a
    # private street's design is the City Engineer's (18.910.030.T.1) and
    # the TSP shows it no ultimate right-of-way. Metro types it private and
    # the city's line along it says PRIVATE: the line is not public.
    got = _private_lot(_angus([_tsp(21)], [PRIVATE_RANK], ["ANGUS CT"]))
    assert got[5] is False
    assert strip(rules, TIGARD, "RES-B", None, names=None, classes={"street_class_tigard": None}, public=False) == 0.0
    # No city line along it at all: the city does not call it public either.
    assert _private_lot(_angus([_tsp(300)], [0], ["ANGUS CT"]))[5] is False
    # A public street meeting the lot line end-on is not along it.
    across = LineString([(TX + 80, TY - 500), (TX + 80, TY + 500)])
    assert _private_lot(_angus([_tsp(21), across], [PRIVATE_RANK, 2], ["ANGUS CT", "HALL BLVD"]))[5] is False


def test_a_street_metro_calls_private_and_tigard_public_takes_the_citys_row() -> None:
    # The city classes the street a Collector: its row, measured to Metro's line.
    got = _private_lot(_angus([_tsp(21)], [2], ["ANGUS CT"]))
    assert got[5] is True and got[4] == pytest.approx(21.0)
    assert got[7]["street_class_tigard"] == "collector"
    # Drawn 40 ft off and unnamed, but running along the line: still the city's.
    got = _private_lot(_angus([_tsp(55)], [1], [""]))
    assert got[5] is True and got[7]["street_class_tigard"] == "neighborhood_route"


def test_a_tigard_private_street_the_maps_disagree_on_otherwise_keeps_the_deepest_row(rules) -> None:
    # An unranked city line along it (a Freeway, an "Other").
    got = _private_lot(_angus([_tsp(21)], [None], ["ANGUS CT"]))
    assert got[5] is True and got[7]["street_class_tigard"] is None
    # The city's map missing from the snapshot: Metro alone is one source.
    got = _private_lot(None)
    assert got[5] is True and "street_class_tigard" not in got[7]
    assert strip(rules, TIGARD, "RES-B", 21.0, names=["ANGUS CT"], classes={}) == 43.0


def test_a_street_tigard_calls_private_and_metro_public_takes_the_local_row(rules) -> None:
    # The two maps disagree: the wider reading, the Local row (54 ft, 27 to
    # the centre line), never nothing.
    county = _cmap([T_STREET], ["SW 107TH AVE"], (1500,), ranks=(0,))
    rank = class_rank_of("PRIVATE")
    assert rank == PRIVATE_RANK
    city = _tigard_map([_tsp(21)], [rank], ["107TH AVE"])
    (got,) = dedication.measure([T_FRONT], TIGARD, [county, city])
    assert got[5] is True and got[7]["street_class_tigard"] == "local"
    assert tigard(rules, "local", half=21.0) == pytest.approx(6.0)


def class_rank_of(value: str) -> int | None:
    from flats.geom.street_class import class_rank

    return class_rank(value, CLASS_MAPS["street_class_tigard"])


# --- the rule ------------------------------------------------------------


def test_the_rule_without_a_named_list_reads_classes() -> None:
    rule = dedication.Rule(classes={"local": 25.0, "arterial": 45.0}, class_by="washington_county", named=(), other=None)
    assert rule.required(None, {"street_class_washington": "local"}) == 25.0
    # A class the zone does not state is unread.
    assert rule.required(None, {"street_class_washington": "collector"}) == 45.0
    # No class_by: no map is read.
    blind = dedication.Rule(classes={"local": 25.0, "arterial": 45.0}, class_by=None, named=(), other=None)
    assert blind.required(None, {"street_class_washington": "local"}) == 45.0


def test_the_rule_with_a_named_list_and_classes_reads_both() -> None:
    rule = dedication.Rule(
        classes={"local": 20.0, "arterial": 40.0}, class_by="washington_county", named=(("KING RD", 50.0),), other=None
    )
    assert rule.required(["KING RD"], {}) == 50.0
    assert rule.required(["ELM ST"], {"street_class_washington": "local"}) == 20.0
    assert rule.deepest() == 50.0


# --- measuring -------------------------------------------------------------


def _cmap(lines, names, types, ranks=None, key="street_class_washington", layer=WASHCO) -> ClassMap:
    return ClassMap(
        serves=(layer,),
        lines=Lines.build(lines, [""] * len(lines)),
        kinds=("",) * len(lines),
        streets=Lines.build(lines, names),
        types=types,
        ranks=ranks or (None,) * len(lines),
        key=key,
    )


def test_the_half_width_is_the_nearest_centreline_distance() -> None:
    street = LineString([(X0 - 500, Y0 - 30), (X0 + 500, Y0 - 30)])
    cmap = _cmap([street], ["SW BULL MOUNTAIN RD"], (1500,))
    width, public, names = dedication.read_line(FRONT[:4], cmap)
    assert public and width == pytest.approx(30.0) and names == ("BULL MOUNTAIN RD",)
    private = ClassMap(**{**cmap.__dict__, "types": (1700,)})
    assert dedication.half_width_ft(FRONT[:4], private) == (None, False)
    far = LineString([(X0 - 500, Y0 - 400), (X0 + 500, Y0 - 400)])
    nothing = ClassMap(**{**cmap.__dict__, "streets": Lines.build([far], [""])})
    assert dedication.read_line(FRONT[:4], nothing) == (None, True, None)


def test_a_stub_no_centreline_runs_beside_reads_the_nearest_one() -> None:
    cross = LineString([(X0 + 20, Y0 - 500), (X0 + 20, Y0 - 5)])
    cmap = _cmap([cross], ["SW 131ST AVE"], (1500,))
    stub = [X0 + 18, Y0, X0 + 22, Y0]
    width, public, names = dedication.read_line(stub, cmap)
    assert public and width is not None and 5.0 <= width <= 20.0
    assert names == ("131ST AVE",)
    private = ClassMap(**{**cmap.__dict__, "types": (1700,)})
    assert dedication.half_width_ft(stub, private) == (None, False)


def test_measure_reads_width_name_and_every_class_map_for_the_layer() -> None:
    street = LineString([(X0 - 500, Y0 - 22), (X0 + 500, Y0 - 22)])
    county = _cmap([street], ["SW EDY RD"], (1400,), ranks=(2,))
    sherwood = _cmap([street], ["SW EDY RD"], (1400,), ranks=(0,), key="street_class_sherwood", layer=SHERWOOD)
    (got,) = dedication.measure([FRONT], SHERWOOD, [county, sherwood])
    assert got[4] == pytest.approx(22.0) and got[5] is True and got[6] == ["EDY RD"]
    assert got[7] == {"street_class_washington": "collector", "street_class_sherwood": "local"}
    # In the county's own layer Sherwood's map is not read.
    (county_only,) = dedication.measure([FRONT], WASHCO, [county, sherwood])
    assert county_only[7] == {"street_class_washington": "collector"}


def _two_maps(tsp, tsp_names, ranks, streets, street_names) -> ClassMap:
    return ClassMap(
        serves=(WASHCO,),
        lines=Lines.build(tsp, tsp_names),
        kinds=("",) * len(tsp),
        streets=Lines.build(streets, street_names),
        types=(1500,) * len(streets),
        ranks=ranks,
        key="street_class_washington",
    )


# The front line reads the local class off a TSP line that stops at the
# corner; the corner cut-off beyond it has no TSP line abreast.
EDY = LineString([(X0 - 500, Y0 - 22), (X0 + 500, Y0 - 22)])
EDY_TSP = LineString([(X0 - 500, Y0 - 22), (X0 + 50, Y0 - 22)])
CUT = [X0 + 50, Y0, X0 + 70, Y0, "F"]


def test_a_corner_piece_takes_the_class_read_for_its_street_on_the_lot() -> None:
    cmap = _two_maps([EDY_TSP], ["SW EDY RD"], (0,), [EDY], ["SW EDY RD"])
    assert dedication.edge_rank(CUT, cmap) is None
    front, cut = dedication.measure([FRONT, CUT], WASHCO, [cmap])
    assert front[6] == cut[6] == ["EDY RD"]
    assert front[7] == cut[7] == {"street_class_washington": "local"}


def test_a_piece_whose_street_is_read_nowhere_else_on_the_lot_stays_unread() -> None:
    cmap = _two_maps([EDY_TSP], ["SW EDY RD"], (0,), [EDY], ["SW EDY RD"])
    (cut,) = dedication.measure([CUT], WASHCO, [cmap])
    assert cut[6] == ["EDY RD"] and cut[7] == {"street_class_washington": None}


_CROSS = LineString([(X0 + 82, Y0 - 500), (X0 + 82, Y0 + 500)])
_CHORD = [X0 + 50, Y0, X0 + 60, Y0 + 10, "F"]
_SIDE = [X0 + 60, Y0 + 10, X0 + 60, Y0 + 100, "F"]


def test_a_piece_on_two_read_streets_takes_the_deeper() -> None:
    # A corner lot: the cut-off between the two street lines runs beside
    # neither street, so it may be on either. Edy Rd reads local on the
    # front, 150th Ave collector on the flank: the piece takes the collector,
    # the deeper of the two (coordinator ruling 2026-10-14).
    cmap = _two_maps(
        [EDY_TSP, _CROSS], ["SW EDY RD", "SW 150TH AVE"], (0, 2), [EDY, _CROSS], ["SW EDY RD", "SW 150TH AVE"]
    )
    front, cut, flank = dedication.measure([FRONT, _CHORD, _SIDE], WASHCO, [cmap])
    assert front[7] == {"street_class_washington": "local"}
    assert flank[7] == {"street_class_washington": "collector"}
    assert cut[6] == ["150TH AVE", "EDY RD"]
    assert cut[7] == {"street_class_washington": "collector"}


def test_a_piece_on_two_streets_one_unread_stays_unread() -> None:
    # The same corner, but the lot has no flank line on 150th Ave, so that
    # street is read on no other line of the lot: the piece may be on an
    # unread street and keeps the worst case.
    cmap = _two_maps(
        [EDY_TSP, _CROSS], ["SW EDY RD", "SW 150TH AVE"], (0, 2), [EDY, _CROSS], ["SW EDY RD", "SW 150TH AVE"]
    )
    front, cut = dedication.measure([FRONT, _CHORD], WASHCO, [cmap])
    assert front[7] == {"street_class_washington": "local"}
    assert cut[6] == ["150TH AVE", "EDY RD"]
    assert cut[7] == {"street_class_washington": None}


def test_a_piece_keeps_a_busier_class_its_own_points_read() -> None:
    # The cut-off's far half is abreast of a collector stretch: the piece is
    # unread (its points disagree), and takes the collector, not the local
    # class its street reads on the front line.
    collector = LineString([(X0 + 60, Y0 - 22), (X0 + 500, Y0 - 22)])
    cmap = _two_maps([EDY_TSP, collector], ["SW EDY RD", "SW EDY RD"], (0, 2), [EDY], ["SW EDY RD"])
    assert dedication.edge_rank(CUT, cmap) is None
    front, cut = dedication.measure([FRONT, CUT], WASHCO, [cmap])
    assert front[7] == {"street_class_washington": "local"}
    assert cut[7] == {"street_class_washington": "collector"}


def test_a_layer_with_no_map_measures_nothing() -> None:
    assert dedication.measure([FRONT], OREGON_CITY, []) == []


# --- reach ---------------------------------------------------------------


def test_every_layer_a_dedication_reaches_is_measured(layers) -> None:
    """A lot gives up a strip only where its line was measured; a layer the
    bridge skips gives every line the whole distance. So every layer whose
    zones state a distance, and every layer whose map carries a pocket of one,
    must be in :data:`dedication.LAYERS`."""

    def states(layer) -> bool:
        return any(f in layer.defaults for f in dedication.FIELDS) or any(
            f in zone.values for zone in layer.zones.values() for f in dedication.FIELDS
        )

    stating = {lid for lid, layer in layers.items() if states(layer)}
    assert stating == {WASHCO, SHERWOOD, KING_CITY, OREGON_CITY, MILWAUKIE, TIGARD}
    reached = set(stating)
    for lid, layer in layers.items():
        for ruling in layer.zone_rulings.values():
            if ruling.outcome == "pocket" and ruling.of in stating:
                reached.add(lid)
    assert {lid for lid in reached if not dedication.applies(lid)} == set()
    assert not dedication.applies("or/multnomah/portland")
    assert not dedication.applies(None)


def test_every_class_by_names_a_map_with_buckets() -> None:
    for by, key in dedication.CLASS_BY_MAP.items():
        assert key in CLASS_MAPS, by
        assert key in dedication.BUCKETS, by
        assert key in dedication.READS, by
