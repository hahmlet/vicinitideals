"""An area a code draws inside a zone and publishes only as a picture.

Tualatin's CC zone refuses housing (TDC 53.200(1), Table 53-1) except on the
ten blocks of Comprehensive Plan Map 10-3 the Residential Sub-District names
(58.200(2)(a), Table 58-1). No public layer holds the blocks, so the layer
traces them (``drawn_areas``) and the bridge answers ``inside_mapped_use_area``
from each lot's share inside the tracing.

What is guarded: the loader takes only a registered drawn condition, a zone
block of the layer, one area per (condition, zone), and a FeatureCollection
in quadfit's coordinate system; a lot the outline cuts through is left
unanswered rather than called either way; and the Tualatin tracing is the
ten blocks the code lists, no more and no fewer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import shapely
from shapely.geometry import LineString, Point, box

from flats.encode.load import load_trusted
from flats.geom.drawn import INSIDE_SHARE, OUTSIDE_SHARE, load_area, observed_drawn, share_inside
from flats.ingest.quadfit import observed_facts
from flats.rules import loader
from flats.rules.conditions import CONDITIONS, DRAWN_CONDITIONS
from flats.rules.loader import RuleLoadError, load_rules
from flats.tests.test_quadfit_bridge import row
from flats.tests.test_rules import PORTLAND, portland

pytestmark = pytest.mark.unit

TUALATIN = "or/clackamas/tualatin"
TRACING = "or/clackamas/tualatin/residential-sub-district.geojson"
SUB_DISTRICT_BLOCKS = {2, 3, 15, 16, 17, 18, 19, 20, 22, 23}


# --- the registry ---------------------------------------------------------------


def test_every_drawn_condition_is_a_registered_condition() -> None:
    assert DRAWN_CONDITIONS == (
        "inside_mapped_use_area",
        "north_of_marine_drive",
        "rockwood_design_district",
        "willamette_historic_district",
    )
    assert set(DRAWN_CONDITIONS) <= set(CONDITIONS)


# --- the share --------------------------------------------------------------------

AREA = box(0, 0, 100, 100)


@pytest.mark.parametrize(
    ("lot", "expected"),
    [
        (box(10, 10, 60, 60), True),  # wholly inside
        (box(91, 10, 101, 20), True),  # 90 percent inside, the edge of True
        (box(200, 200, 250, 250), False),  # wholly outside
        (box(99, 10, 109, 20), False),  # 10 percent inside, the edge of False
        (box(80, 10, 120, 20), None),  # half and half: the line cuts it
        (box(70, 10, 110, 20), None),  # three quarters in
    ],
)
def test_the_share_inside_decides_and_the_middle_is_unanswered(lot, expected) -> None:
    assert observed_drawn(lot, AREA) is expected


def test_the_thresholds_are_the_ones_the_module_states() -> None:
    assert (INSIDE_SHARE, OUTSIDE_SHARE) == (0.9, 0.1)


def test_a_lot_with_no_area_is_unanswered() -> None:
    assert share_inside(LineString([(0, 0), (10, 10)]), AREA) is None
    assert observed_drawn(Point(5, 5), AREA) is None


# --- the block in a layer file --------------------------------------------------

BLOCK = (
    "drawn_areas:\n"
    "  sub_district:\n"
    "    condition: inside_mapped_use_area\n"
    "    zones: [CM2]\n"
    f"    file: {TRACING}\n"
    "    source: Map 10-3, traced from the taxlots it draws\n"
    '    quote: "or/clackamas/tualatin/58.central-tualatin-overlay.txt#L20-L22,L31-L34"\n'
    "    cite: TDC 58.110\n"
    "    note: >-\n"
    "      The blocks the code names as the sub-district, where the use table\n"
    "      admits housing in the zone.\n"
)


def test_the_block_loads(tmp_path: Path) -> None:
    root = tmp_path / "jurisdictions"
    portland(root, "  CM2:\n    quadplex_allowed: true\n", extra=BLOCK)
    got = load_rules(root)[PORTLAND].drawn_areas["sub_district"]
    assert got.condition == "inside_mapped_use_area"
    assert got.zones == ("CM2",)
    assert got.file == TRACING
    assert got.cite == "TDC 58.110"
    assert got.note.startswith("The blocks the code names")


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (("    condition: inside_mapped_use_area\n", "    condition: corner_lot\n"), "condition: one of"),
        (("    zones: [CM2]\n", "    zones: [CM9]\n"), "not a zone block here: CM9"),
        (("    zones: [CM2]\n", "    zones: []\n"), "a list of this layer's zone blocks"),
        ((f"    file: {TRACING}\n", "    file: or/nowhere.geojson\n"), "no such file"),
        (("    source: Map 10-3, traced from the taxlots it draws\n", ""), "source"),
        (
            ('    quote: "or/clackamas/tualatin/58.central-tualatin-overlay.txt#L20-L22,L31-L34"\n', ""),
            "quote",
        ),
        (
            (
                "      The blocks the code names as the sub-district, where the use table\n"
                "      admits housing in the zone.\n",
                "      Blocks.\n",
            ),
            "at least",
        ),
        (("    cite: TDC 58.110\n", "    cite: TDC 58.110\n    when: [corner_lot]\n"), "unexpected when"),
    ],
)
def test_a_malformed_block_is_refused(tmp_path: Path, edit: tuple[str, str], message: str) -> None:
    root = tmp_path / "jurisdictions"
    portland(root, "  CM2:\n    quadplex_allowed: true\n", extra=BLOCK.replace(*edit))
    with pytest.raises(RuleLoadError, match=message):
        load_rules(root)


def test_one_zone_is_answered_by_one_area_per_condition(tmp_path: Path) -> None:
    second = BLOCK.split("\n", 1)[1].replace("  sub_district:", "  another:")
    root = tmp_path / "jurisdictions"
    portland(root, "  CM2:\n    quadplex_allowed: true\n", extra=BLOCK + second)
    with pytest.raises(RuleLoadError, match="CM2 already answered for inside_mapped_use_area by sub_district"):
        load_rules(root)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"type": "FeatureCollection", "features": []}, "at least one feature"),
        (
            {
                "type": "FeatureCollection",
                "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
                "features": [{"type": "Feature", "properties": {}, "geometry": shapely.geometry.mapping(AREA)}],
            },
            "drawn in EPSG::2913",
        ),
        (
            {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "properties": {}, "geometry": shapely.geometry.mapping(AREA)}],
            },
            "the crs member says nothing",
        ),
    ],
)
def test_a_tracing_must_be_drawn_in_quadfits_coordinates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: dict, message: str
) -> None:
    areas = tmp_path / "areas"
    (areas / "x").mkdir(parents=True)
    (areas / "x" / "a.geojson").write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setattr(loader, "AREAS_ROOT", areas)
    root = tmp_path / "jurisdictions"
    portland(root, "  CM2:\n    quadplex_allowed: true\n", extra=BLOCK.replace(TRACING, "x/a.geojson"))
    with pytest.raises(RuleLoadError, match=message):
        load_rules(root)


# --- the Tualatin tracing ---------------------------------------------------------


@pytest.fixture(scope="module")
def corpus() -> dict:
    return load_rules()


def test_the_tracing_is_the_ten_blocks_the_code_lists() -> None:
    data = json.loads((loader.AREAS_ROOT / TRACING).read_text(encoding="utf-8"))
    blocks = {int(f["properties"]["block"]) for f in data["features"]}
    assert blocks == SUB_DISTRICT_BLOCKS


def test_tualatin_cc_reads_the_tracing(corpus: dict) -> None:
    layer = corpus[TUALATIN]
    (area,) = layer.drawn_areas.values()
    assert area.condition == "inside_mapped_use_area" and area.zones == ("CC",)
    assert area.file == TRACING
    assert "CC" in layer.zones and "CC" not in layer.zone_rulings


def test_cc_refuses_the_building_outside_the_sub_district_and_permits_it_inside(corpus: dict) -> None:
    allowed = corpus[TUALATIN].zones["CC"].values["quadplex_allowed"]
    assert allowed.value is False
    assert [(v.value, v.when) for v in allowed.variants] == [(True, ("inside_mapped_use_area",))]


# --- the bridge -------------------------------------------------------------------


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).rules.layers


def cc(lot) -> dict:
    return row(jurisdiction="tualatin", zone="CC", lot_wkb=shapely.to_wkb(lot))


def _edge_midpoint(area) -> Point:
    """The middle of the longest straight run of the tracing's outline."""
    ring = max(area.geoms, key=lambda g: g.area).exterior
    coords = list(ring.coords)
    a, b = max(zip(coords, coords[1:]), key=lambda ab: Point(ab[0]).distance(Point(ab[1])))
    return Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def test_a_lot_inside_a_block_is_inside(layers) -> None:
    area = load_area(TRACING)
    p = max(area.geoms, key=lambda g: g.area).representative_point()
    lot = p.buffer(5)
    assert area.contains(lot)
    assert observed_facts(cc(lot), layers)["inside_mapped_use_area"] is True


def test_a_lot_far_from_every_block_is_outside(layers) -> None:
    minx, miny, _, _ = load_area(TRACING).bounds
    lot = box(minx - 2000, miny - 2000, minx - 1900, miny - 1900)
    assert observed_facts(cc(lot), layers)["inside_mapped_use_area"] is False


def test_a_lot_the_outline_cuts_is_unanswered(layers) -> None:
    lot = _edge_midpoint(load_area(TRACING)).buffer(10)
    share = share_inside(lot, load_area(TRACING))
    assert OUTSIDE_SHARE < share < INSIDE_SHARE
    assert "inside_mapped_use_area" not in observed_facts(cc(lot), layers)


def test_a_lot_of_another_zone_is_not_asked(layers) -> None:
    p = max(load_area(TRACING).geoms, key=lambda g: g.area).representative_point()
    got = observed_facts(row(jurisdiction="tualatin", zone="RL", lot_wkb=shapely.to_wkb(p.buffer(5))), layers)
    assert "inside_mapped_use_area" not in got


def test_a_row_without_the_lot_shape_is_not_asked(layers) -> None:
    assert "inside_mapped_use_area" not in observed_facts(row(jurisdiction="tualatin", zone="CC"), layers)


# --- areas the zoning layer does not carry (2026-10-04) -----------------------------

WEST_LINN = "or/clackamas/west-linn"
GRESHAM = "or/multnomah/gresham"
WHD = "or/clackamas/west-linn/willamette-historic-district.geojson"
MARINE = "or/multnomah/gresham/north-of-marine-drive.geojson"
ROCKWOOD = "or/multnomah/gresham/rockwood-design-district.geojson"


def test_west_linn_and_gresham_declare_their_areas(corpus: dict) -> None:
    (whd,) = corpus[WEST_LINN].drawn_areas.values()
    assert (whd.condition, whd.file) == ("willamette_historic_district", WHD)
    assert {"R-10", "R-5"} <= set(whd.zones)
    areas = corpus[GRESHAM].drawn_areas
    marine = areas["north_of_marine_drive"]
    assert (marine.condition, marine.file) == ("north_of_marine_drive", MARINE)
    assert "LDR-5" in marine.zones
    rockwood = areas["rockwood_design_district"]
    assert (rockwood.condition, rockwood.file) == ("rockwood_design_district", ROCKWOOD)
    assert {"CMU", "SC", "MDR-12"} <= set(rockwood.zones)


def test_a_gresham_lot_in_rockwood_is_inside_and_one_downtown_is_not(layers) -> None:
    area = load_area(ROCKWOOD)
    inside = area.representative_point().buffer(5)

    def gresham(lot) -> dict:
        return observed_facts(row(jurisdiction="gresham", zone="CMU", lot_wkb=shapely.to_wkb(lot)), layers)

    assert gresham(inside)["rockwood_design_district"] is True
    assert gresham(box(7_706_000, 670_000, 7_706_100, 670_100))["rockwood_design_district"] is False


def test_the_historic_district_is_the_citys_one_polygon() -> None:
    area = load_area(WHD)
    assert area.geom_type == "Polygon"
    assert 19 < area.area / 43_560 < 21  # about 20 acres


def test_a_west_linn_lot_inside_the_district_is_inside_and_one_outside_is_not(layers) -> None:
    area = load_area(WHD)
    inside = area.representative_point().buffer(5)
    minx, miny, _, _ = area.bounds
    outside = box(minx - 2000, miny - 2000, minx - 1900, miny - 1900)

    def wl(lot) -> dict:
        return observed_facts(row(jurisdiction="west_linn", zone="R-5", lot_wkb=shapely.to_wkb(lot)), layers)

    assert wl(inside)["willamette_historic_district"] is True
    assert wl(outside)["willamette_historic_district"] is False


def test_north_of_marine_drive_is_the_side_of_the_road_not_the_address(layers) -> None:
    area = load_area(MARINE)
    # The north edge of the area is the road: a point a hundred feet off the
    # road on each side, at the middle of the line.
    road = min(area.exterior.coords, key=lambda c: abs(c[0] - 7_696_000))

    def gresham(lot) -> dict:
        return observed_facts(row(jurisdiction="gresham", zone="LDR-5", lot_wkb=shapely.to_wkb(lot)), layers)

    north = Point(road[0], road[1] + 100).buffer(20)
    south = Point(road[0], road[1] - 100).buffer(20)
    assert gresham(north)["north_of_marine_drive"] is True
    assert gresham(south)["north_of_marine_drive"] is False
    # Downtown Gresham is miles south of the river.
    assert gresham(box(7_706_000, 670_000, 7_706_100, 670_100))["north_of_marine_drive"] is False
