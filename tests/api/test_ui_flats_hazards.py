"""Mapped ground hazards (FOLLOWUPS 198): a build of the held flood layers loads
onto its copy's lots, the lot report carries every class with its printed code,
square feet and share, the lot page says it in words beside the colour -- and
no colour, verdict or check moves."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import shapely
from httpx import AsyncClient
from shapely.geometry import box, mapping
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import FlatsLotResult
from scripts.flats_lot_hazards import build, extract, load
from tests.api.test_ui_flats_lots import _login, _seed

pytestmark = pytest.mark.asyncio

A = "1S2E08BA  -09500"  # 2833 SE 71ST AVE; _seed draws it at 7,650,000 / 680,000
B = "1N1E29DD  -05600"  # 4110 NE 12TH AVE
LOT_A = box(7_650_000, 680_000, 7_650_100, 680_100)  # 10,000 sq ft


def _held(snapshot: Path) -> None:
    """An acquire snapshot holding the FEMA and Title 3 layers over lot A."""
    snapshot.mkdir()
    fema = [
        ({"FLD_ZONE": "AE", "ZONE_SUBTY": None, "SFHA_TF": "T", "STATIC_BFE": 31.0, "V_DATUM": "NAVD88",
          "DEPTH": -9999.0, "LEN_UNIT": "Feet"}, box(7_649_900, 679_900, 7_650_030, 680_200)),
        ({"FLD_ZONE": "X", "ZONE_SUBTY": "AREA OF MINIMAL FLOOD HAZARD", "SFHA_TF": "F", "STATIC_BFE": -9999.0,
          "V_DATUM": None, "DEPTH": -9999.0, "LEN_UNIT": None}, box(7_650_030, 679_900, 7_650_200, 680_200)),
    ]
    title3 = [({"FLOOD96": 1, "FEMA": 1, "WETBUF": 0, "RIPARIAN": 0, "TITLE3": 1}, box(7_649_900, 679_900, 7_650_010, 680_200))]
    for key, feats in (("overlay_fema_flood", fema), ("overlay_metro_title3", title3)):
        doc = {"type": "FeatureCollection", "srid": 2913,
               "features": [{"type": "Feature", "properties": p, "geometry": mapping(g)} for p, g in feats]}
        (snapshot / f"{key}.geojson").write_text(json.dumps(doc), encoding="utf-8")
    (snapshot / "manifest.json").write_text(json.dumps({"datasets": {
        "overlay_fema_flood": {"retrieved_at": "2026-11-01T06:00:00+00:00"},
        "overlay_metro_title3": {"retrieved_at": "2026-11-01T06:05:00+00:00"},
    }}), encoding="utf-8")


async def test_a_build_of_the_flood_layers_loads_and_reports_without_moving_a_colour(
    tmp_path: Path, client: AsyncClient, session: AsyncSession, _test_db_url: str
):
    await _login(client, session)
    run = await _seed(session)
    before = (await client.get(f"/api/flats/lot/multnomah/{A}")).json()
    checks = sorted((r.design_key, r.tier, json.dumps(r.checks, sort_keys=True))
                    for r in (await session.execute(select(FlatsLotResult))).scalars())
    # Nothing loaded: every layer says so, none says "no hazard".
    assert before["hazards"]["measured"] is False
    assert {x["status"] for g in before["hazards"]["groups"] for x in g["layers"]} == {"not_loaded"}

    _held(tmp_path / "2026-11-01")
    meta = extract(tmp_path / "extract", gdbs={}, held=tmp_path / "2026-11-01", keys=["flood_fema", "flood_title3"])
    assert set(meta["layers"]) == {"flood_fema", "flood_title3"}
    pq.write_table(pa.table({
        "county": ["multnomah", "multnomah"],
        "tlid": [A, "NOT IN THE COPY"],
        "jurisdiction": ["or/multnomah/portland", "or/multnomah/portland"],
        "wkb": [shapely.to_wkb(LOT_A), shapely.to_wkb(box(0, 0, 10, 10))],
    }), tmp_path / "lots.parquet")
    summary = build(tmp_path / "extract", tmp_path / "lots.parquet", tmp_path / "build")
    assert summary["largest_sum_gap_share"] < 1e-6
    report = await load(tmp_path / "build", _test_db_url, snapshot_id=run.snapshot_id)
    assert report["layers"] == ["flood_fema", "flood_title3"]
    assert report["file_lots_without_a_lot"] == 1
    assert report["lots_written"] == 1

    after = (await client.get(f"/api/flats/lot/multnomah/{A}")).json()
    note = after["hazards"]
    assert note["measured"] is True and note["never_a_colour"] is True
    flood = next(g for g in note["groups"] if g["hazard"] == "flood")
    fema = next(x for x in flood["layers"] if x["layer"] == "flood_fema")
    assert fema["status"] == "mapped"
    assert fema["class_field"] == "FLD_ZONE"
    assert fema["publication"]["number"] == "NFHL MapServer layer 28"
    assert "as fetched 2026-11-01" in fema["source"]
    classes = [(c["state"], c["class_code"], round(c["area_sqft"]), c["share"]) for c in fema["classes"]]
    assert classes == [("class", "X", 7_000, 0.7), ("class", "AE", 3_000, 0.3)]
    assert fema["worst"]["class_code"] == "AE"
    assert fema["in_100_year_zone"] is True and fema["zones"] == ["AE", "X"]
    assert [c["detail"]["in_100_year"] for c in fema["classes"]] == [False, True]
    assert "base flood elevation 31 feet (NAVD88)" in fema["worst"]["words"]
    title3 = next(x for x in flood["layers"] if x["layer"] == "flood_title3")
    assert [(c["state"], c["class_code"], round(c["area_sqft"])) for c in title3["classes"]] == [
        ("not_mapped", None, 9_000), ("class", "FLOOD96=1 FEMA=1", 1_000)]
    # The DOGAMI layers were not in this build: still "not loaded", never "no hazard".
    liq = next(g for g in note["groups"] if g["hazard"] == "liquefaction")["layers"][0]
    assert liq["status"] == "not_loaded"

    for key in ("colour", "verdict", "designs", "colour_words", "verdict_words"):
        assert after[key] == before[key], key
    assert checks == sorted((r.design_key, r.tier, json.dumps(r.checks, sort_keys=True))
                            for r in (await session.execute(select(FlatsLotResult))).scalars())

    # The lot page says it in words; the other lot says "not measured yet".
    page = await client.get(f"/flats/lots/multnomah/{A.replace(' ', '%20')}")
    bare = await client.get(f"/flats/lots/multnomah/{B.replace(' ', '%20')}")
    block = page.text.split('id="lot-hazards"', 1)[1]
    assert 'data-layer="flood_fema" data-status="mapped"' in block
    assert "70% zone X (area of minimal flood hazard); 30% zone AE, base flood elevation 31 feet (NAVD88)." in block
    assert "never changes the lot&#39;s colour" in block or "never changes the lot's colour" in block
    assert "cannot substitute for site-specific investigations" in block
    assert 'data-layer="liquefaction" data-status="not_loaded"' in block
    assert "not measured yet" in bare.text.split('id="lot-hazards"', 1)[1]

    # A second load of the same layers replaces, never doubles.
    again = await load(tmp_path / "build", _test_db_url, snapshot_id=run.snapshot_id)
    assert again["removed"] == again["written"] == report["written"]
