"""Mapped ground hazards per lot (FOLLOWUPS 198): the measuring, the four
states, the words -- and that nothing which screens reads them."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import shapely
from shapely.geometry import box

from flats.ingest import hazards as hz
from flats.ingest.sources import load_pipeline

REG = hz.load_registry()
LOT = box(0, 0, 100, 100)  # 10,000 sq ft


def _feat(spec_key: str, code: str | None, geom, label: str | None = None, state: str = hz.CLASS, **attrs):
    spec = REG.layers[spec_key]
    if label is None and code is not None:
        found = spec.class_def(code)
        label = found.label if found else None
    return hz.Feature(state, code, label, attrs, geom)


def _sum(rows) -> float:
    return sum(r["area_sqft"] for r in rows)


# --- the registry ---------------------------------------------------------------


def test_every_layer_names_a_dated_publication_and_the_caveat_is_dogami_s() -> None:
    assert "cannot substitute for site-specific investigations" in REG.caveat
    assert "No warranty" in REG.caveat
    for spec in REG.layers.values():
        pub = REG.publications[spec.publication]
        assert pub.publisher and pub.title and pub.number and pub.date and pub.page.startswith("https://"), spec.key
    assert REG.publications["o_19_09"].number == "Open-File Report O-19-09"
    assert REG.layers["liquefaction"].class_field == "Class"
    assert REG.layers["landslide_overview"].publication == "o_16_02"
    assert "1:500,000" in REG.layers["landslide_overview"].title


def test_the_screen_registry_still_loads_and_holds_the_fema_datum() -> None:
    pipeline = load_pipeline()
    assert "hazard_notes" not in pipeline.datasets
    assert {"V_DATUM", "DEPTH", "LEN_UNIT"} <= set(pipeline.datasets["overlay_fema_flood"].fields)
    for spec in REG.layers.values():
        if spec.held:
            assert spec.held in pipeline.datasets, spec.key


def test_nothing_that_screens_imports_the_hazard_notes() -> None:
    root = Path(hz.__file__).resolve().parents[1]
    readers = []
    for path in root.rglob("*.py"):
        if "tests" in path.parts or path.name == "hazards.py":
            continue
        if re.search(r"ingest\.hazards|ingest import hazards", path.read_text(encoding="utf-8")):
            readers.append(str(path))
    assert readers == []


# --- measuring an area layer ------------------------------------------------------


def test_classes_split_the_lot_worst_first_and_the_rest_is_not_mapped() -> None:
    spec = REG.layers["liquefaction"]
    feats = [
        _feat("liquefaction", "2", box(0, 0, 60, 100)),  # Low, 6,000
        _feat("liquefaction", "4", box(40, 0, 80, 100)),  # High, overlaps Low by 2,000
    ]
    rows = hz.measure_area(spec, LOT, 10_000.0, feats)
    by = {(r["state"], r["class_code"]): r for r in rows}
    assert by[(hz.CLASS, "4")]["area_sqft"] == pytest.approx(4_000)
    assert by[(hz.CLASS, "2")]["area_sqft"] == pytest.approx(4_000)  # the overlap went to High
    assert by[(hz.NOT_MAPPED, None)]["area_sqft"] == pytest.approx(2_000)
    assert _sum(rows) == pytest.approx(10_000)
    assert sum(r["share"] for r in rows) == pytest.approx(1.0)
    assert rows[0]["state"] == hz.CLASS  # classes first, largest first


def test_a_lot_with_no_feature_is_not_mapped_never_none() -> None:
    rows = hz.measure_area(REG.layers["liquefaction"], LOT, 10_000.0, [])
    assert rows == [{"state": hz.NOT_MAPPED, "class_code": None, "class_label": None, "area_sqft": 10_000.0,
                     "detail": None, "share": 1.0}]
    note = hz.describe_layer(REG.layers["liquefaction"], [{**rows[0], "layer": "liquefaction"}], REG)
    assert note["status"] == "not_mapped"
    assert "no hazard" in note["words"] and "not the same as" in note["words"]


def test_detailed_coverage_leaves_the_rest_outside() -> None:
    spec = REG.layers["landslide_deep"]
    coverage = box(0, 0, 50, 100)
    rows = hz.measure_area(spec, LOT, 10_000.0, [_feat("landslide_deep", "Moderate", box(-10, -10, 200, 200))], coverage)
    by = {r["state"]: r for r in rows}
    assert by[hz.CLASS]["area_sqft"] == pytest.approx(5_000)
    assert by[hz.OUTSIDE]["area_sqft"] == pytest.approx(5_000)
    assert _sum(rows) == pytest.approx(10_000)
    # No coverage at all: the whole lot is outside, nothing else.
    rows = hz.measure_area(spec, LOT, 10_000.0, [], None)
    assert [(r["state"], r["area_sqft"]) for r in rows] == [(hz.OUTSIDE, 10_000.0)]


def test_the_statewide_overview_is_used_only_where_the_detailed_map_is_not() -> None:
    spec = REG.layers["landslide_overview"]
    coverage = box(0, 0, 30, 100)
    rows = hz.measure_area(spec, LOT, 10_000.0, [_feat("landslide_overview", "3", box(-1, -1, 101, 101))], coverage)
    by = {r["state"]: r for r in rows}
    assert by[hz.CLASS]["area_sqft"] == pytest.approx(7_000)
    assert by[hz.SUPERSEDED]["area_sqft"] == pytest.approx(3_000)
    note = hz.describe_layer(spec, [{**r, "layer": spec.key} for r in rows], REG)
    assert note["words"].startswith("70% High; 30% covered by the detailed lidar map instead")
    whole = hz.measure_area(spec, LOT, 10_000.0, [], box(-5, -5, 105, 105))
    assert [r["state"] for r in whole] == [hz.SUPERSEDED]


def test_fema_zones_rank_and_area_not_included_is_outside() -> None:
    spec = REG.layers["flood_fema"]
    feats = [
        hz.Feature(*hz.classify(spec, {"FLD_ZONE": "AE", "ZONE_SUBTY": None}), {"SFHA_TF": "T", "STATIC_BFE": 52.0,
                   "V_DATUM": "NAVD88", "DEPTH": -9999.0, "LEN_UNIT": "Feet"}, box(0, 0, 25, 100)),
        hz.Feature(*hz.classify(spec, {"FLD_ZONE": "X", "ZONE_SUBTY": "AREA OF MINIMAL FLOOD HAZARD"}),
                   {"SFHA_TF": "F", "STATIC_BFE": -9999.0}, box(25, 0, 75, 100)),
        hz.Feature(*hz.classify(spec, {"FLD_ZONE": "AREA NOT INCLUDED"}), {}, box(75, 0, 100, 100)),
    ]
    rows = hz.measure_area(spec, LOT, 10_000.0, feats)
    assert [(r["state"], r["class_code"]) for r in rows] == [(hz.CLASS, "X"), (hz.CLASS, "AE"), (hz.OUTSIDE, "AREA NOT INCLUDED")]
    assert _sum(rows) == pytest.approx(10_000)
    note = hz.describe_layer(spec, [{**r, "layer": spec.key} for r in rows], REG)
    assert note["status"] == "mapped"
    assert note["worst"]["class_code"] == "AE" and note["worst"]["level"] == "high"
    assert "base flood elevation 52 feet (NAVD88)" in note["worst"]["words"]
    assert "flood depth" not in note["worst"]["words"]  # -9999 is FEMA's no-data
    assert hz.fema_level("AE", "FLOODWAY", "T") == "very_high"
    assert hz.fema_level("X", "0.2 PCT ANNUAL CHANCE FLOOD HAZARD", "F") == "moderate"
    assert hz.fema_level("D", None, "F") == "undetermined"
    assert hz.fema_level("X", None, "F") == "undetermined"  # an unread subtype is never "minimal"


def test_a_lot_mapped_only_low_says_mapped_as() -> None:
    spec = REG.layers["liquefaction"]
    rows = hz.measure_area(spec, LOT, 10_000.0, [_feat("liquefaction", "0", box(-1, -1, 200, 200))])
    note = hz.describe_layer(spec, [{**r, "layer": spec.key} for r in rows], REG)
    assert note["status"] == "mapped_low"
    assert note["words"] == "Mapped as: 100% None."


def test_a_printed_label_that_disagrees_is_kept_as_printed() -> None:
    spec = REG.layers["liquefaction"]
    state, code, label = hz.classify(spec, {"Class": 2, "LQ_Label": "Moderate"})
    assert (state, code, label) == (hz.CLASS, "2", "Moderate")
    # The rank comes from the Hazus class number (the field named in the registry).
    assert hz.level_of(spec, code, label, None) == "low"
    assert hz.classify(spec, {"Class": 3.0, "LQ_Label": None}) == (hz.CLASS, "3", "Moderate")
    assert hz.level_of(spec, "9", None, None) == "undetermined"


def test_title3_keeps_only_flood_flags() -> None:
    spec = REG.layers["flood_title3"]
    assert hz.classify(spec, {"FLOOD96": 0, "FEMA": 0, "WETBUF": 1}) is None
    assert hz.classify(spec, {"FLOOD96": 1, "FEMA": 0}) == (hz.CLASS, "FLOOD96=1 FEMA=0", "1996 flood inundation area")


# --- line and point layers ----------------------------------------------------------


def test_scarps_and_historic_points_are_counted() -> None:
    scarps = REG.layers["landslide_scarps"]
    line = shapely.LineString([(50, -50), (50, 150)])
    rows = hz.measure_count(scarps, LOT, [hz.Feature(hz.CLASS, "Scarp", "Scarp", {"REF_ID_COD": "X1"}, line)])
    assert rows[0]["state"] == hz.CLASS and rows[0]["detail"]["count"] == 1
    assert rows[0]["detail"]["length_ft"] == pytest.approx(100)
    none = hz.measure_count(REG.layers["landslide_historic"], LOT, [])
    note = hz.describe_layer(REG.layers["landslide_historic"], [{**none[0], "layer": "landslide_historic"}], REG)
    assert note["status"] == "none_found" and note["words"] == "No mapped historic landslide point lies on the lot."


# --- the lot as a whole ------------------------------------------------------------


def test_measure_lots_writes_every_layer_and_skips_west_linn_elsewhere() -> None:
    liq = hz.VectorLayer(REG.layers["liquefaction"], [_feat("liquefaction", "3", box(0, 0, 50, 100))])
    wl = hz.VectorLayer(REG.layers["flood_west_linn"], [hz.Feature(hz.CLASS, "Flood management area",
                                                                   "Flood management area", {}, box(0, 0, 10, 10))])
    lots = [
        {"county": "clackamas", "tlid": "21E35AB  -01700", "jurisdiction": "or/clackamas/west-linn", "geom": LOT},
        {"county": "multnomah", "tlid": "1S2E08BA  -09500", "jurisdiction": "or/multnomah/portland", "geom": LOT},
    ]
    rows = list(hz.measure_lots(lots, [liq, wl], {}))
    assert set(rows[0]) == set(hz.LOT_COLUMNS)
    layers = {(r["tlid"], r["layer"]) for r in rows}
    assert ("21E35AB  -01700", "flood_west_linn") in layers
    assert ("1S2E08BA  -09500", "flood_west_linn") not in layers
    liq_rows = [r for r in rows if r["tlid"] == "1S2E08BA  -09500"]
    assert sum(r["area_sqft"] for r in liq_rows) == pytest.approx(10_000)
    assert {r["hazard"] for r in rows} == {"liquefaction", "flood"}


def test_portland_s_1996_flood_area_is_a_flood_note_on_portland_lots_only() -> None:
    spec = REG.layers["flood_pdx_1996"]
    assert spec.hazard == "flood" and spec.held == "overlay_pdx_flood_1996"
    assert "24.50.040 E" in REG.publications[spec.publication].title
    area = hz.VectorLayer(spec, [hz.Feature(hz.CLASS, "1996 flood area", "1996 flood area", {}, box(0, 0, 30, 100))])
    lots = [
        {"county": "multnomah", "tlid": "1S2E08BA  -09500", "jurisdiction": "or/multnomah/portland", "geom": LOT},
        {"county": "multnomah", "tlid": "1N3E31CD  -11902", "jurisdiction": "or/multnomah/gresham", "geom": LOT},
    ]
    rows = [r for r in hz.measure_lots(lots, [area], {}) if r["state"] == hz.CLASS]
    assert [(r["tlid"], r["layer"], r["area_sqft"]) for r in rows] == [("1S2E08BA  -09500", "flood_pdx_1996", 3_000.0)]
    note = hz.describe(rows, jurisdiction="or/multnomah/portland")
    flood = next(g for g in note["groups"] if g["hazard"] == "flood")
    assert "flood_pdx_1996" in {x["layer"] for x in flood["layers"]}
    gresham = hz.describe([], jurisdiction="or/multnomah/gresham")
    assert "flood_pdx_1996" not in {x["layer"] for g in gresham["groups"] for x in g["layers"]}


def test_a_layer_never_loaded_reads_not_loaded_and_the_note_is_never_a_colour() -> None:
    note = hz.describe([], jurisdiction="or/multnomah/portland")
    assert note["measured"] is False and note["never_a_colour"] is True
    layers = [x for g in note["groups"] for x in g["layers"]]
    assert {x["status"] for x in layers} == {"not_loaded"}
    assert "flood_west_linn" not in {x["layer"] for x in layers}
    assert "flood_west_linn" in {x["layer"] for g in hz.describe([], jurisdiction="or/clackamas/west-linn")["groups"]
                                 for x in g["layers"]}
    rows = [{"layer": "liquefaction", "state": hz.CLASS, "class_code": "5", "class_label": "Very High",
             "area_sqft": 10_000.0, "share": 1.0, "detail": None}]
    note = hz.describe(rows, jurisdiction="or/multnomah/portland")
    liq = next(x for g in note["groups"] for x in g["layers"] if x["layer"] == "liquefaction")
    assert liq["status"] == "mapped" and liq["worst"]["level"] == "very_high"
    assert liq["publication"]["number"] == "Open-File Report O-19-09"
    fema = next(x for g in note["groups"] for x in g["layers"] if x["layer"] == "flood_fema")
    assert fema["status"] == "not_loaded" and fema["words"] == "Not loaded yet."
    assert "colour" not in json.dumps(note).lower().replace("never_a_colour", "")


# --- FD2 foundation screen: nearest slide, 100-year zone, any polygon ------------------


def test_the_distance_to_the_nearest_mapped_slide_is_kept_per_class_for_any_shape() -> None:
    inv = REG.layers["landslide_inventory"]
    assert inv.nearest_ft == 1000
    deposit = _feat("landslide_inventory", "Deposit", box(160, 0, 300, 100), UNIQUE_ID="D1")  # 60 ft east
    flank = _feat("landslide_inventory", "Scarp flank", box(90, 0, 120, 100), UNIQUE_ID="F1")  # overlaps 10 ft
    far = _feat("landslide_inventory", "Deposit", box(5_000, 0, 5_100, 100), UNIQUE_ID="D2")
    layer = hz.VectorLayer(inv, [deposit, flank, far])
    # Any polygon: a 40 x 50 ft footprint placed inside the lot.
    footprint = box(10, 10, 50, 60)
    rows = list(hz.measure_shape(footprint, [layer], {}))
    near = {r["class_code"]: r["detail"] for r in rows if r["state"] == hz.NEAREST}
    assert near["Deposit"] == {"distance_ft": 110.0, "on_shape": False, "searched_ft": 1000}
    assert near["Scarp flank"]["distance_ft"] == 40.0
    area = [r for r in rows if r["state"] != hz.NEAREST]
    assert sum(r["area_sqft"] for r in area) == pytest.approx(2_000)  # the footprint, not a lot
    assert all(r["area_sqft"] == 0 and r["share"] == 0 for r in rows if r["state"] == hz.NEAREST)
    # On the whole lot: the flank covers part of it, the deposit is 60 ft off.
    lot_rows = [{**r, "layer": inv.key} for r in hz.measure_shape(LOT, [layer], {})]
    note = hz.describe_layer(inv, lot_rows, REG)
    by = {n["class_code"]: n for n in note["nearest"]}
    assert by["Deposit"]["distance_ft"] == 60.0 and by["Scarp flank"]["on_shape"] is True
    assert "Nearest mapped landslide deposit 60 ft away; a mapped scarp flank touches or covers it." in note["words"]
    assert all(c["state"] != hz.NEAREST for c in note["classes"])
    assert note["status"] == "mapped"
    # Nothing within the search: None, said as "none within", never 0 or "no hazard".
    alone = hz.VectorLayer(inv, [far])
    rows = [{**r, "layer": inv.key} for r in hz.measure_shape(LOT, [alone], {})]
    note = hz.describe_layer(inv, rows, REG)
    assert {n["class_code"]: n["distance_ft"] for n in note["nearest"]} == {"Deposit": None, "Scarp flank": None}
    assert note["words"].endswith("No mapped landslide deposit within 1,000 ft; no mapped scarp flank within 1,000 ft.")
    # Not loaded: the distance is unknown, not "none within".
    assert hz.describe_layer(inv, [], REG)["nearest"] is None


def test_a_historic_point_nearby_is_measured_too() -> None:
    hist = REG.layers["landslide_historic"]
    pt = hz.Feature(hz.CLASS, hist.code, hist.code, {"UNIQUE_ID": "H1"}, shapely.Point(150, 50))
    rows = [{**r, "layer": hist.key} for r in hz.measure_shape(LOT, [hz.VectorLayer(hist, [pt])], {})]
    note = hz.describe_layer(hist, rows, REG)
    assert note["status"] == "none_found"
    assert note["nearest"][0]["distance_ft"] == 50.0
    assert note["words"] == ("No mapped historic landslide point lies on the lot. "
                             "Nearest mapped historic landslide point 50 ft away.")


def test_fema_keeps_a_plain_100_year_answer_beside_the_zone_letters() -> None:
    assert [hz.fema_in_100_year(z) for z in ("AE", "A", "AO", "VE", "X", "D", "0.2 PCT ANNUAL CHANCE FLOOD HAZARD", None)] == [
        True, True, True, True, False, False, False, None]
    spec = REG.layers["flood_fema"]
    ae = hz.Feature(*hz.classify(spec, {"FLD_ZONE": "AE"}), {"SFHA_TF": "T"}, box(0, 0, 25, 100))
    x = hz.Feature(*hz.classify(spec, {"FLD_ZONE": "X", "ZONE_SUBTY": "AREA OF MINIMAL FLOOD HAZARD"}), {"SFHA_TF": "F"},
                   box(25, 0, 100, 100))
    rows = list(hz.measure_shape(LOT, [hz.VectorLayer(spec, [ae, x])], {}))
    assert {r["class_code"]: r["detail"]["in_100_year"] for r in rows} == {"AE": True, "X": False}
    note = hz.describe_layer(spec, [{**r, "layer": spec.key} for r in rows], REG)
    assert note["in_100_year_zone"] is True and note["zones"] == ["AE", "X"]
    only_x = [{**r, "layer": spec.key} for r in hz.measure_shape(LOT, [hz.VectorLayer(spec, [x])], {})]
    assert hz.describe_layer(spec, only_x, REG)["in_100_year_zone"] is False  # zone X only (the rest unmapped)
    nothing = [{**r, "layer": spec.key} for r in hz.measure_shape(LOT, [hz.VectorLayer(spec, [])], {})]
    assert hz.describe_layer(spec, nothing, REG)["in_100_year_zone"] is None  # unmapped is unknown, not "no"
    assert hz.describe_layer(spec, [], REG)["in_100_year_zone"] is None


# --- rasters ---------------------------------------------------------------------


def test_a_raster_is_cut_cell_exact_in_its_own_crs(tmp_path: Path) -> None:
    rasterio = pytest.importorskip("rasterio")
    import numpy as np
    from pyproj import Transformer
    from rasterio.transform import from_origin

    # A lot near Portland in EPSG:2913, and a 10 ft raster in Oregon Lambert (EPSG:2994).
    lot = box(7_650_000, 680_000, 7_650_100, 680_100)
    tr = Transformer.from_crs(2913, 2994, always_xy=True)
    x0, y0 = tr.transform(7_649_900, 680_200)
    arr = np.ones((40, 40), dtype=np.uint8)  # Low
    arr[:, 30:] = 3  # High from 300 ft east of x0
    arr[:2, :] = 0  # nodata strip
    path = tmp_path / "shallow.tif"
    with rasterio.open(path, "w", driver="GTiff", height=40, width=40, count=1, dtype="uint8", crs="EPSG:2994",
                       transform=from_origin(x0, y0, 10, 10), nodata=0) as ds:
        ds.write(arr, 1)
    layer = hz.RasterLayer(REG.layers["landslide_shallow"], str(path))
    feats = layer.features(lot)
    assert {f.code for f in feats} <= {"1", "3"}
    rows = hz.measure_area(REG.layers["landslide_shallow"], lot, 10_000.0, feats, box(7_640_000, 670_000, 7_660_000, 690_000))
    assert _sum(rows) == pytest.approx(10_000, rel=1e-6)
    by = {r["class_code"]: r for r in rows if r["state"] == hz.CLASS}
    assert by["1"]["class_label"] == "Low"
    # The lot sits wholly west of the High part (it spans 100-200 ft east of x0
    # in 2913; the axes of the two CRSs differ by well under a degree here).
    assert by["1"]["area_sqft"] == pytest.approx(10_000, rel=0.02)


def test_a_masked_raster_cell_is_never_a_class(tmp_path: Path) -> None:
    """A geodatabase raster has no nodata value; its empty cells sit behind a
    per-dataset mask, which the GeoTIFF copy keeps. Masked cells are not mapped."""
    rasterio = pytest.importorskip("rasterio")
    import numpy as np
    from rasterio.transform import from_origin

    lot = box(7_650_000, 680_000, 7_650_100, 680_100)
    arr = np.zeros((40, 40), dtype=np.uint8)
    arr[:, 20:] = 2  # Moderate in the east half, masked zeros in the west
    path = tmp_path / "masked.tif"
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
        with rasterio.open(path, "w", driver="GTiff", height=40, width=40, count=1, dtype="uint8", crs="EPSG:2913",
                           transform=from_origin(7_649_950, 680_150, 5, 5)) as ds:
            ds.write(arr, 1)
            ds.write_mask(np.where(arr > 0, 255, 0).astype(np.uint8))
    feats = hz.RasterLayer(REG.layers["landslide_shallow"], str(path)).features(lot)
    assert {f.code for f in feats} == {"2"}
    rows = hz.measure_area(REG.layers["landslide_shallow"], lot, 10_000.0, feats, box(7_640_000, 670_000, 7_660_000, 690_000))
    by = {(r["state"], r["class_code"]): r["area_sqft"] for r in rows}
    assert by[(hz.CLASS, "2")] == pytest.approx(5_000)
    assert by[(hz.NOT_MAPPED, None)] == pytest.approx(5_000)
