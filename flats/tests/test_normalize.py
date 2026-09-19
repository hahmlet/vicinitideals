"""``flats.ingest.normalize`` -- every lot of a snapshot, with what is known before measuring.

A synthetic snapshot: a taxlot file with twelve features across two counties,
a Portland zoning file, a regional zoning file and a growth boundary, read
through a registry and a rule set built for the test. What is checked is
the jurisdiction mapping, the majority zone join and its split flag, the
zone the rules hold versus the code the map said, each of the five gates, the
assessor columns, the condo verdicts, the stack collapse and the funnel.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import shapely

from flats.ingest import normalize as nz
from flats.ingest.sources import load_pipeline
from flats.rules.loader import load_rules

REPO_ROOT = Path(__file__).resolve().parents[2]

PIPELINE_YAML = """
working_srid: 2913
jurisdictions:
  or/multnomah/portland: true
  or/multnomah/_unincorporated: true
  or/clackamas/_unincorporated: true
  or/clackamas/lake-oswego: true
  or/multnomah/maywood-park: false
datasets:
  rlis_taxlots:
    kind: rlis_zip
    label: taxlots
    provides: lots
    url: https://example.test/rlis.zip
    member: TAXLOTS/taxlots.shp
    serves: [or/multnomah, or/clackamas]
  rlis_zoning_metro:
    kind: rlis_zip
    label: regional zoning
    provides: zoning
    url: https://example.test/rlis.zip
    member: ZONING/zoning.shp
    zone_field: ZONE
    fields: [ZONE]
    serves: [or/multnomah, or/clackamas]
  zoning_portland:
    kind: arcgis
    label: Portland zoning
    provides: zoning
    url: https://example.test/arcgis/rest/services/Zoning/MapServer/0
    zone_field: ZONE
    fields: [ZONE]
    serves: [or/multnomah/portland]
  zoning_lake_oswego:
    kind: arcgis
    label: Lake Oswego zoning
    provides: zoning
    url: https://example.test/arcgis/rest/services/LO/MapServer/0
    zone_field: LAYER
    fields: [LAYER]
    serves: [or/clackamas/lake-oswego]
  ugb_metro:
    kind: arcgis
    label: UGB
    provides: boundary
    url: https://example.test/arcgis/rest/services/UGB/MapServer/0
    fields: [UGB]
    serves: [or/multnomah, or/clackamas]
"""


def square(x: float, y: float, w: float = 100.0, h: float = 100.0) -> dict[str, Any]:
    return {"type": "Polygon", "coordinates": [[[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]]]}


def feature(tlid: str, geom: dict[str, Any] | None, **props: Any) -> dict[str, Any]:
    base = {"TLID": tlid, "COUNTY": "M", "JURIS_CITY": "PORTLAND", "SITEADDR": f"{tlid} ST", "LANDVAL": 1000, "BLDGSQFT": 0, "PROP_CODE": "101"}
    base.update(props)
    return {"type": "Feature", "properties": base, "geometry": geom}


def write(path: Path, features: list[dict[str, Any]]) -> Path:
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def layers():
    return load_rules()


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    path = tmp_path_factory.mktemp("cfg") / "pipeline.yaml"
    path.write_text(PIPELINE_YAML, encoding="utf-8")
    return load_pipeline(path)


@pytest.fixture
def snapshot(tmp_path: Path, layers) -> Path:
    snap = tmp_path / "2026-09-18"
    snap.mkdir()
    pdx_zones = list(layers["or/multnomah/portland"].zones)
    r5 = "R5" if "R5" in pdx_zones else pdx_zones[0]
    metro_zones = list(layers["or/multnomah/_unincorporated"].zones)
    m_zone = metro_zones[0]
    c_zone = list(layers["or/clackamas/_unincorporated"].zones)[0]
    taxlots = [
        # Portland, R5 whole, land.
        feature("1N1E01AA  -00100", square(0, 0)),
        # Portland, split-zoned: 60 % R5 / 40 % a code the rules do not hold ("QQ9").
        feature("1N1E01AA  -00200", square(200, 0)),
        # Portland, wholly under the unknown code with Portland's lowercase suffix: "QQ9a" -> "QQ9".
        feature("1N1E01AA  -00300", square(400, 0)),
        # Portland, no zoning polygon covers it.
        feature("1N1E01AA  -00400", square(800, 0)),
        # A condo air parcel (Multnomah code 122, 40 sq ft): out.
        feature("1N1E01AA  -00500", square(0, 200, w=5, h=8), PROP_CODE="122", BLDGSQFT=900),
        # A condo suspect (building three times the lot): kept, marked.
        feature("1N1E01AA  -00600", square(20, 200, w=30, h=30), BLDGSQFT=3000),
        # A stack of three identical footprints: one representative.
        feature("1N1E01AA  -00700", square(200, 200)),
        feature("1N1E01AA  -00701", square(200, 200)),
        feature("1N1E01AA  -00702", square(200, 200)),
        # The street pseudo-lot.
        feature("1N1E01AA  -STR", square(600, 0)),
        # No geometry at all.
        feature("1N1E01AA  -00800", None),
        # Multnomah unincorporated, inside the UGB, regional zoning.
        feature("1N1E02AA  -00100", square(1000, 0), JURIS_CITY="UNINCORPORATED"),
        # Multnomah unincorporated, outside the UGB.
        feature("1N1E02AA  -00200", square(5000, 0), JURIS_CITY=""),
        # Clackamas unincorporated (blank code, county letter picks the layer), inside.
        feature("21E01AA00100", square(1200, 0), COUNTY="C", JURIS_CITY=""),
        # Clackamas, Lake Oswego: switched off by the layer.
        feature("21E01AA00200", square(1400, 0), COUNTY="C", JURIS_CITY="LAKE OSWEGO"),
        # Clackamas, Canby: no layer at all.
        feature("21E01AA00300", square(1600, 0), COUNTY="C", JURIS_CITY="CANBY"),
        # Maywood Park: a layer, switched off in the registry; no regional polygon covers it.
        feature("1N1E03AA  -00100", square(1800, 0), JURIS_CITY="MAYWOOD PARK"),
        # The same TLID twice: the larger polygon stays.
        feature("1N1E04AA  -00100", square(2000, 0, w=50, h=50)),
        feature("1N1E04AA  -00100", square(2000, 0)),
        # Washington County: not ours.
        feature("1S1W01AA  -00100", square(3000, 0), COUNTY="W", JURIS_CITY="BEAVERTON"),
    ]
    write(snap / "rlis_taxlots.geojson", taxlots)
    write(
        snap / "zoning_portland.geojson",
        [
            feature("z1", square(0, 0), ZONE=r5),
            feature("z2", square(200, 0, w=60), ZONE=r5),
            feature("z3", square(260, 0, w=40), ZONE="QQ9"),
            feature("z4", square(400, 0), ZONE="QQ9a"),
            feature("z5", square(0, 200, w=300, h=100), ZONE=r5),
            feature("z6", square(2000, 0), ZONE=r5),
        ],
    )
    write(
        snap / "rlis_zoning_metro.geojson",
        [feature("m1", square(1000, 0), ZONE=m_zone), feature("m2", square(1200, 0), ZONE=c_zone), feature("m3", square(5000, 0), ZONE=m_zone)],
    )
    write(snap / "zoning_lake_oswego.geojson", [feature("lo", square(1400, 0), LAYER="R-7.5")])
    write(snap / "ugb_metro.geojson", [feature("ugb", square(-100, -100, w=3000, h=1000), UGB="Y")])
    (snap / "manifest.json").write_text(
        json.dumps({"snapshot": "2026-09-18", "working_srid": 2913, "datasets": {"rlis_taxlots": {"status": "acquired", "file": "rlis_taxlots.geojson", "sha256": "abc"}}})
    )
    return snap


@pytest.fixture
def result(snapshot: Path, tmp_path: Path, layers, pipeline):
    out = tmp_path / "normalized"
    summary = nz.normalize(snapshot, out, layers=layers, pipeline=pipeline)
    frame = pd.read_parquet(out / "lots.parquet")
    frame = frame.astype(object).where(frame.notna(), None)
    rows = {(r["county"], r["tlid"]): r for r in frame.to_dict("records")}
    return summary, rows, out


def test_the_lot_universe_and_the_funnel(result, layers):
    summary, rows, out = result
    assert sorted(rows) == [
        ("clackamas", "21E01AA00100"),
        ("clackamas", "21E01AA00200"),
        ("clackamas", "21E01AA00300"),
        ("multnomah", "1N1E01AA  -00100"),
        ("multnomah", "1N1E01AA  -00200"),
        ("multnomah", "1N1E01AA  -00300"),
        ("multnomah", "1N1E01AA  -00400"),
        ("multnomah", "1N1E01AA  -00600"),
        ("multnomah", "1N1E01AA  -00700"),
        ("multnomah", "1N1E02AA  -00100"),
        ("multnomah", "1N1E02AA  -00200"),
        ("multnomah", "1N1E03AA  -00100"),
        ("multnomah", "1N1E04AA  -00100"),
    ]
    funnel = {s["step"]: s for s in summary["funnel"]}
    assert funnel["features"]["count"] == 20
    assert funnel["other_county"]["dropped"] == 1
    assert funnel["not_a_taxlot"]["dropped"] == 1
    assert funnel["no_geometry"]["dropped"] == 1
    assert funnel["duplicate_tlid"]["dropped"] == 1
    assert funnel["condo_excluded"]["dropped"] == 1 and funnel["condo_excluded"]["reasons"] == {"CONDO_AIR_PARCEL": 1}
    assert funnel["condo_stack"]["dropped"] == 2
    assert funnel["jurisdiction_unmapped"] == {"step": "jurisdiction_unmapped", "count": 1, "juris_city": {"CANBY": 1}}
    assert summary["lots"] == 13 and summary["by_county"] == {"clackamas": 3, "multnomah": 10}
    assert json.loads((out / "funnel.json").read_text()) == summary["funnel"]
    # The duplicate kept the larger polygon; the stack kept the first TLID with its count.
    assert rows[("multnomah", "1N1E04AA  -00100")]["area_sqft"] == 10_000
    assert rows[("multnomah", "1N1E01AA  -00700")]["stack_count"] == 3
    assert rows[("multnomah", "1N1E01AA  -00100")]["stack_count"] == 1


def test_jurisdiction_zone_and_gate(result, layers):
    summary, rows, _ = result
    r5 = rows[("multnomah", "1N1E01AA  -00100")]
    assert r5["jurisdiction"] == "or/multnomah/portland" and r5["zone"] == r5["zone_raw"] and r5["zone"] in layers["or/multnomah/portland"].zones
    assert r5["zone_frac"] == pytest.approx(1.0) and r5["split_zone"] is False and r5["inside_ugb"] is True and r5["gate"] is None
    split = rows[("multnomah", "1N1E01AA  -00200")]
    assert split["zone"] == r5["zone"] and split["zone_frac"] == pytest.approx(0.6) and split["split_zone"] is True and split["gate"] is None
    unknown = rows[("multnomah", "1N1E01AA  -00300")]
    assert unknown["zone_raw"] == "QQ9a" and unknown["zone"] is None and unknown["gate"] == "ZONE_NOT_ENCODED"
    assert rows[("multnomah", "1N1E01AA  -00400")]["gate"] == "NO_ZONE"
    uninc_m = rows[("multnomah", "1N1E02AA  -00100")]
    assert uninc_m["jurisdiction"] == "or/multnomah/_unincorporated" and uninc_m["zone"] is not None and uninc_m["gate"] is None
    outside = rows[("multnomah", "1N1E02AA  -00200")]
    assert outside["jurisdiction"] == "or/multnomah/_unincorporated" and outside["inside_ugb"] is False and outside["gate"] == "OUTSIDE_UGB"
    uninc_c = rows[("clackamas", "21E01AA00100")]
    assert uninc_c["jurisdiction"] == "or/clackamas/_unincorporated" and uninc_c["gate"] is None, "the county letter picks between the two blank codes"
    lo = rows[("clackamas", "21E01AA00200")]
    assert lo["jurisdiction"] == "or/clackamas/lake-oswego" and lo["zone_raw"] == "R-7.5" and lo["gate"] == "JURISDICTION_OFF"
    assert rows[("clackamas", "21E01AA00300")]["jurisdiction"] is None and rows[("clackamas", "21E01AA00300")]["gate"] == "JURISDICTION_NOT_ENCODED"
    maywood = rows[("multnomah", "1N1E03AA  -00100")]
    assert maywood["jurisdiction"] == "or/multnomah/maywood-park" and maywood["zone_raw"] is None and maywood["gate"] == "JURISDICTION_OFF"
    assert summary["new_zones"] == {"or/multnomah/portland": {"QQ9": 1}}, "the suffix is stripped before the code is counted; the split lot's minority code is not a new zone"
    assert summary["by_gate"] == {"JURISDICTION_NOT_ENCODED": 1, "JURISDICTION_OFF": 2, "NO_ZONE": 1, "OUTSIDE_UGB": 1, "ZONE_NOT_ENCODED": 1, "screenable": 7}
    assert summary["zoning"] == {
        "or/clackamas/_unincorporated": "rlis_zoning_metro",
        "or/clackamas/lake-oswego": "zoning_lake_oswego",
        "or/multnomah/_unincorporated": "rlis_zoning_metro",
        "or/multnomah/maywood-park": "rlis_zoning_metro",
        "or/multnomah/portland": "zoning_portland",
    }, "a city with no service of its own falls back to the regional layer, the registry's most specific match"


def test_assessor_condo_and_geometry_columns(result):
    _, rows, _ = result
    land = rows[("multnomah", "1N1E01AA  -00100")]
    assert land["LANDVAL"] == 1000 and land["PROP_CODE"] == "101" and land["site_address"] == "1N1E01AA  -00100 ST"
    assert land["condo_verdict"] == "land" and land["condo_reason"] is None
    suspect = rows[("multnomah", "1N1E01AA  -00600")]
    assert suspect["condo_verdict"] == "suspect" and suspect["condo_reason"].startswith("SUSPECT_")
    geom = shapely.from_wkb(land["wkb"])
    assert geom.geom_type == "Polygon" and geom.area == 10_000 and land["part_count"] == 1
    for col in nz.ASSESSOR_FIELDS:
        assert col in land


def test_summary_md_reads_in_plain_english(result):
    summary, _, out = result
    text = (out / "summary.md").read_text(encoding="utf-8")
    assert "# County map 2026-09-18: 13 lots" in text
    assert "- 1 out: not a taxlot" in text and "- 2 out: condo stack" in text
    assert "Zone codes on the map that the rules do not hold:" in text and "- or/multnomah/portland: QQ9 (1)" in text
    assert "Cities with no encoded layer: CANBY 1" in text
    assert json.loads((out / "new_zones.json").read_text()) == summary["new_zones"]


def test_jurisdictions_from_the_real_layers(layers):
    j = nz.Jurisdictions.from_layers(layers)
    assert j.layer_for("PORTLAND", "multnomah") == "or/multnomah/portland"
    assert j.layer_for("Portland ", "clackamas") == "or/multnomah/portland", "Portland reaches into Clackamas; the code wins"
    assert j.layer_for("", "multnomah") == "or/multnomah/_unincorporated"
    assert j.layer_for(None, "clackamas") == "or/clackamas/_unincorporated"
    assert j.layer_for("UNINCORPORATED", "clackamas") == "or/clackamas/_unincorporated"
    assert j.layer_for("", None) is None, "a blank code with no county cannot be placed"
    assert j.layer_for("CANBY", "clackamas") is None


def test_zone_normalisation_follows_the_layer(layers):
    pdx = layers["or/multnomah/portland"]
    code = next(iter(pdx.zones))
    assert nz.zone_for(pdx, f" {code}a ") == (code, code)
    assert nz.zone_for(pdx, "ZZ9c") == ("ZZ9", None)
    assert nz.zone_for(pdx, None) == (None, None) and nz.zone_for(pdx, "  ") == (None, None)
    gresham = layers["or/multnomah/gresham"]
    g = next(iter(gresham.zones))
    assert nz.zone_for(gresham, g) == (g, g)
    assert nz.zone_for(gresham, f"{g}a") == (f"{g}a", None), "only Portland's suffix is stripped"
    assert nz.zone_for(None, "R5") == ("R5", None)


def test_gate_order():
    pdx = type("L", (), {"eligible": True, "kind": "city", "ingest": {}, "zones": {"R5": 1}})()
    uninc = type("L", (), {"eligible": True, "kind": "unincorporated", "ingest": {}, "zones": {"R5": 1}})()
    off = type("L", (), {"eligible": False, "kind": "city", "ingest": {}, "zones": {"R5": 1}})()
    assert nz.gate_for(None, on=True, inside_ugb=True, zone_raw="R5", zone="R5") == "JURISDICTION_NOT_ENCODED"
    assert nz.gate_for(off, on=True, inside_ugb=True, zone_raw="R5", zone="R5") == "JURISDICTION_OFF"
    assert nz.gate_for(pdx, on=False, inside_ugb=True, zone_raw="R5", zone="R5") == "JURISDICTION_OFF"
    assert nz.gate_for(uninc, on=True, inside_ugb=False, zone_raw="R5", zone="R5") == "OUTSIDE_UGB"
    assert nz.gate_for(pdx, on=True, inside_ugb=False, zone_raw="R5", zone="R5") is None, "a city lot is screened wherever the boundary runs"
    assert nz.gate_for(pdx, on=True, inside_ugb=True, zone_raw=None, zone=None) == "NO_ZONE"
    assert nz.gate_for(pdx, on=True, inside_ugb=True, zone_raw="QQ9", zone=None) == "ZONE_NOT_ENCODED"
    assert nz.gate_for(pdx, on=True, inside_ugb=True, zone_raw="R5", zone="R5") is None


def test_majority_zone_join():
    lots = [shapely.box(0, 0, 100, 100), shapely.box(200, 0, 300, 100), shapely.box(900, 0, 1000, 100)]
    zones = [shapely.box(0, 0, 100, 100), shapely.box(200, 0, 270, 100), shapely.box(270, 0, 300, 100), shapely.box(-50, -50, 20, 20)]
    codes = ["A", "B", "C", "A"]
    zone, frac = nz.assign_majority_zone(lots, zones, codes)
    assert zone == ["A", "B", None] and frac[0] == pytest.approx(1.0) and frac[1] == pytest.approx(0.7) and frac[2] is None
    assert nz.assign_majority_zone([], zones, codes) == ([], [])
    assert nz.assign_majority_zone(lots, [], []) == ([None] * 3, [None] * 3)
