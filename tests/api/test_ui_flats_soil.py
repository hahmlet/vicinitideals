"""The USDA soil survey under the lot (FOLLOWUPS 196): the lot page and the
JSON report say it with its identifiers and its source, every map unit largest
first, and no colour or count moves. A build loads onto its copy's lots, the
green lots first."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import (
    FlatsLot,
    FlatsLotBest,
    FlatsLotResult,
    FlatsLotSoil,
    FlatsSoilComponent,
    FlatsSoilMapUnit,
)
from flats.ingest.soil import COMPONENT_COLUMNS, LOT_COLUMNS, MAP_UNIT_COLUMNS
from scripts.flats_lot_soil import COMPONENTS_FILE, LOT_FILE, MAPUNITS_FILE, META_FILE, _write_csv, load
from tests.api.test_ui_flats_lots import _login, _seed

pytestmark = pytest.mark.asyncio

A = "1S2E08BA  -09500"  # 2833 SE 71ST AVE
B = "1N1E29DD  -05600"  # 4110 NE 12TH AVE

SOURCE = ("USDA Natural Resources Conservation Service (NRCS) soil survey, SSURGO, state download of 2026-10-01: "
          "OR051 Multnomah County Area, Oregon (09/08/2026 19:50:15)")

UNIT_CASCADE = {
    "mukey": "1001", "areasymbol": "OR051", "areaname": "Multnomah County Area, Oregon",
    "saverest": "09/08/2026 19:50:15", "musym": "7B", "muname": "Cascade silt loam, 3 to 8 percent slopes",
    "mukind": "Consociation", "drclassdcd": "Somewhat poorly drained", "hydgrpdcd": "C/D", "hydclprs": 5,
    "wtdepannmin": 46, "brockdepmin": None, "engdwobdcd": "Somewhat limited", "dwellings_dcd": "Somewhat limited",
    "small_commercial_dcd": "Very limited", "wet_season_status": "recorded", "wet_season_cm": 46,
    "wet_season_months": "January,February", "wet_season_cokey": "2001",
}
UNIT_URBAN = {
    "mukey": "1002", "areasymbol": "OR051", "areaname": "Multnomah County Area, Oregon",
    "saverest": "09/08/2026 19:50:15", "musym": "50A", "muname": "Urban land, 0 to 3 percent slopes",
    "mukind": "Consociation", "engdwobdcd": "Not rated", "wet_season_status": "no_data",
}
COMP_CASCADE = {
    "cokey": "2001", "mukey": "1001", "compname": "Cascade", "comppct_r": 90, "majcompflag": "Yes",
    "compkind": "Series", "taxclname": "Fine-silty, mixed, superactive, mesic Oxyaquic Fragixeralfs",
    "taxorder": "Alfisols", "taxsuborder": "Xeralfs", "taxgrtgroup": "Fragixeralfs",
    "taxsubgrp": "Oxyaquic Fragixeralfs", "taxpartsize": "fine-silty", "drainagecl": "Somewhat poorly drained",
    "hydricrating": "No", "hydgrp": "C/D", "water_table_cm": 46, "water_table_month": "January", "lep_max": 4.5,
    "restriction_cm": 76, "restriction_kind": "Fragipan", "dwellings_rating": "Somewhat limited",
    "small_commercial_rating": "Very limited", "wet_season_status": "recorded", "wet_season_cm": 46,
    "wet_season_months": "January,February",
    "months": [{"monthseq": 1, "month": "January", "wet_top_cm": 46, "flood": "None", "pond": None}],
}
COMP_URBAN = {"cokey": "2002", "mukey": "1002", "compname": "Urban land", "comppct_r": 100, "majcompflag": "Yes",
              "wet_season_status": "no_data"}


async def _note(session: AsyncSession, tlid: str, run, rows: list[tuple[str | None, float, float]]) -> None:
    for unit in (UNIT_CASCADE, UNIT_URBAN):
        if await session.get(FlatsSoilMapUnit, unit["mukey"]) is None:
            session.add(FlatsSoilMapUnit(**unit, source=SOURCE))
    await session.flush()
    for comp in (COMP_CASCADE, COMP_URBAN):
        if await session.get(FlatsSoilComponent, comp["cokey"]) is None:
            session.add(FlatsSoilComponent(**comp))
    lot = (await session.execute(select(FlatsLot).where(FlatsLot.tlid == tlid))).scalar_one()
    for mukey, area, share in rows:
        session.add(FlatsLotSoil(lot_id=lot.id, snapshot_id=run.snapshot_id, mukey=mukey, area_sqft=area, share=share))
    await session.commit()


async def test_the_lot_page_says_every_map_unit_with_its_source(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    run = await _seed(session)
    await _note(session, A, run, [("1001", 10_000.0, 0.71566), ("1002", 3_900.0, 0.27911), (None, 73.0, 0.00523)])

    page = await client.get(f"/flats/lots/multnomah/{A.replace(' ', '%20')}")
    bare = await client.get(f"/flats/lots/multnomah/{B.replace(' ', '%20')}")

    assert page.status_code == 200
    block = page.text.split('id="lot-soil"', 1)[1].split("</div>\n      {% if", 1)[0]
    assert "Soil (USDA survey)" in page.text
    assert "farm-field scale" in block and "never changes the lot" in block
    assert 'data-soil-dominant="1001"' in block
    assert "Cascade silt loam, 3 to 8 percent slopes" in block
    # Every map unit, largest first.
    assert block.index('data-mukey="1001"') < block.index('data-mukey="1002"')
    assert "46 cm (1 ft 6 in) below the surface at its highest, November to April (January, February)" in block
    assert "Fragipan at 76 cm (2 ft 6 in)" in block
    assert "4.5% linear extensibility (moderate*)" in block
    assert "Mapped as Urban land, 0 to 3 percent slopes: the survey holds no soil data for it." in block
    assert "No survey coverage: 73 sq ft" in block
    # The technical line keeps every identifier.
    assert "OR051 (survey version 09/08/2026 19:50:15) · musym 7B · mukey 1001 · Consociation" in block
    assert "cokey 2001 · Cascade 90% · major · Fine-silty, mixed, superactive, mesic Oxyaquic Fragixeralfs" in block
    assert "USDA Natural Resources Conservation Service (NRCS) soil survey, SSURGO: Multnomah County Area" in block
    assert "not measured yet" in bare.text.split('id="lot-soil"', 1)[1]


async def test_the_report_carries_the_note_and_no_colour_moves(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    run = await _seed(session)
    before = (await client.get(f"/api/flats/lot/multnomah/{A}")).json()
    colours = sorted((r.design_key, r.tier, json.dumps(r.checks, sort_keys=True))
                     for r in (await session.execute(select(FlatsLotResult))).scalars())
    await _note(session, A, run, [("1001", 13_973.0, 1.0)])
    after = (await client.get(f"/api/flats/lot/multnomah/{A}")).json()

    assert before["soil"] is None
    soil = after["soil"]
    assert soil["never_a_colour"] is True
    assert soil["dominant"]["mukey"] == "1001" and soil["worst"] is None
    unit = soil["units"][0]
    assert (unit["areasymbol"], unit["saverest"], unit["musym"], unit["mukind"]) == (
        "OR051", "09/08/2026 19:50:15", "7B", "Consociation")
    assert unit["wet_season_cm"] == 46 and unit["wet_season_months"] == ["January", "February"]
    assert unit["components"][0]["cokey"] == "2001"
    assert unit["components"][0]["taxgrtgroup"] == "Fragixeralfs"
    assert unit["components"][0]["months"][0]["wet_top_words"] == "46 cm (1 ft 6 in)"
    assert soil["source_name"].startswith("USDA Natural Resources Conservation Service")
    for key in ("colour", "verdict", "designs", "colour_words", "verdict_words"):
        assert after[key] == before[key], key
    assert colours == sorted((r.design_key, r.tier, json.dumps(r.checks, sort_keys=True))
                             for r in (await session.execute(select(FlatsLotResult))).scalars())


def _build(tmp_path: Path) -> Path:
    out = tmp_path / "build"
    out.mkdir()
    (out / META_FILE).write_text(json.dumps({
        "published": "2026-10-01",
        "survey_areas": [{"areasymbol": "OR051", "areaname": "Multnomah County Area, Oregon",
                          "saverest": "09/08/2026 19:50:15"}],
    }), encoding="utf-8")
    _write_csv(out / MAPUNITS_FILE, MAP_UNIT_COLUMNS, [UNIT_CASCADE, UNIT_URBAN])
    _write_csv(out / COMPONENTS_FILE, COMPONENT_COLUMNS, [COMP_CASCADE, COMP_URBAN])
    _write_csv(out / LOT_FILE, LOT_COLUMNS, [
        {"county": "multnomah", "tlid": A, "mukey": "1001", "area_sqft": 9000.0, "share": 0.64, "lot_area_sqft": 13973.0},
        {"county": "multnomah", "tlid": A, "mukey": "1002", "area_sqft": 4973.0, "share": 0.36, "lot_area_sqft": 13973.0},
        {"county": "multnomah", "tlid": B, "mukey": None, "area_sqft": 5000.0, "share": 1.0, "lot_area_sqft": 5000.0},
        {"county": "multnomah", "tlid": "NOT IN THE COPY", "mukey": "1001", "area_sqft": 1.0, "share": 1.0,
         "lot_area_sqft": 1.0},
    ])
    with gzip.open(out / LOT_FILE, "rt", encoding="utf-8") as fh:
        assert fh.readline().strip() == ",".join(LOT_COLUMNS)
    return out


async def test_a_build_loads_green_lots_first_then_the_rest(
    tmp_path: Path, client: AsyncClient, session: AsyncSession, _test_db_url: str
):
    run = await _seed(session)
    lots = {lot.tlid: lot for lot in (await session.execute(select(FlatsLot))).scalars()}
    for tlid, colour in ((A, 0), (B, 1)):
        lot = lots[tlid]
        session.add(FlatsLotBest(run_id=run.id, lot_id=lot.id, jurisdiction=lot.jurisdiction, zone=lot.zone,
                                 tlid=lot.tlid, best_verdict=0, best_colour=colour))
    await session.commit()
    build = _build(tmp_path)

    green = await load(build, _test_db_url, snapshot_id=run.snapshot_id, colour="green", run_id=run.id)
    assert green["lots_in_colour"] == 1 and green["lots_written"] == 1 and green["written"] == 2
    assert green["map_units"] == 2 and green["components"] == 2
    rows = list((await session.execute(select(FlatsLotSoil))).scalars())
    assert {r.lot_id for r in rows} == {lots[A].id}

    everything = await load(build, _test_db_url, snapshot_id=run.snapshot_id)
    assert everything["removed"] == 2 and everything["written"] == 3
    assert everything["lots_with_soil_in_snapshot"] == 2
    session.expire_all()
    rows = list((await session.execute(select(FlatsLotSoil))).scalars())
    assert sorted((r.mukey or "") for r in rows) == ["", "1001", "1002"]
    comp = await session.get(FlatsSoilComponent, "2001")
    assert comp.months[0]["wet_top_cm"] == 46
    unit = await session.get(FlatsSoilMapUnit, "1001")
    assert unit.source.startswith("USDA Natural Resources Conservation Service")

    # The page for the lot with no survey coverage says so plainly.
    await _login(client, session)
    bare = await client.get(f"/flats/lots/multnomah/{B.replace(' ', '%20')}")
    assert "The USDA soil survey has no map unit under this lot." in bare.text

    # A dry run writes nothing; the tables alone can be refreshed.
    again = await load(build, _test_db_url, snapshot_id=run.snapshot_id, tables_only=True)
    assert "written" not in again and again["map_units"] == 2
