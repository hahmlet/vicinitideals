"""Road land a lot gives up, or the extra yard it keeps, to reach a distance
from the street's centre line (flats/geom/dedication.py).

Washington County CDC 302-2.14 C(1) and its twins (25 / 30 / 37 / 45 ft by
county class), Sherwood 16.106.030 D (26 / 32 / 32 / 37 / 61 ft by city
class), King City 16.80.060 A (33 / 30 ft on named streets, 25 elsewhere),
Oregon City Table 16.12.016 (half the widest right-of-way of the class) and
Milwaukie Table 19.501.2.A (25 / 30 / 40 ft on named streets). These tests pin
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
from flats.geom.street_class import CLASS_MAPS, ClassMap
from flats.ingest.quadfit import dedicated, envelope_for, lot_from_row
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

WASHCO = "or/washington/_unincorporated"
SHERWOOD = "or/washington/sherwood"
KING_CITY = "or/washington/king-city"
OREGON_CITY = "or/clackamas/oregon-city"
MILWAUKIE = "or/clackamas/milwaukie"
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
    for layer, zone in (("or/multnomah/portland", "CM2"), ("or/washington/tigard", "RES-B"), ("or/washington/beaverton", "RMA")):
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
    assert stating == {WASHCO, SHERWOOD, KING_CITY, OREGON_CITY, MILWAUKIE}
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
