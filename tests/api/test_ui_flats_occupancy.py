"""What stands on the lot (FOLLOWUPS 125): the Lots page filters on the label,
the lot page and the JSON report say it, and no colour or count moves.

Ruling 2026-10-14-existing-buildings-stay-green: the label is a label."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import shapely
from httpx import AsyncClient
from shapely.geometry import box
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import FlatsLot, FlatsLotOccupancy, FlatsLotResult
from scripts.flats_lot_occupancy import FOOTPRINTS_FILE, META_FILE, build, load
from tests.api.test_ui_flats_lots import _login, _seed

pytestmark = pytest.mark.asyncio

A = "1S2E08BA  -09500"  # 2833 SE 71ST AVE
B = "1N1E29DD  -05600"  # 4110 NE 12TH AVE


async def _label(session: AsyncSession, run, tlid: str, label: str, **extra) -> None:
    lot = (await session.execute(select(FlatsLot).where(FlatsLot.tlid == tlid))).scalar_one()
    session.add(
        FlatsLotOccupancy(
            lot_id=lot.id, snapshot_id=run.snapshot_id, label=label,
            building_count=extra.pop("building_count", 1), main_count=1,
            footprint_sqft=1100, largest_sqft=1100, coverage=0.0787,
            building_value=extra.pop("building_value", 62_000), total_value=480_000, year_built=1922,
            source="Metro RLIS Building Footprint Database, fetched 2026-11-08", **extra,
        )
    )
    await session.commit()


def _table(html: str) -> str:
    return html.split('id="lot-table"', 1)[1]


async def test_the_filter_keeps_only_lots_with_that_label(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    run = await _seed(session)
    await _label(session, run, A, "teardown")
    await _label(session, run, B, "vacant", building_count=0, building_value=0)

    teardown = await client.get("/flats/lots", params={"occupancy": "teardown"})
    vacant = await client.get("/flats/lots", params={"occupancy": "vacant"})
    house = await client.get("/flats/lots", params={"occupancy": "house"})
    anything = await client.get("/flats/lots", params={"occupancy": "bogus"})

    assert teardown.status_code == 200
    assert "2833 SE 71ST AVE" in _table(teardown.text)
    assert "4110 NE 12TH AVE" not in _table(teardown.text)
    assert "4110 NE 12TH AVE" in _table(vacant.text)
    assert "2833 SE 71ST AVE" not in _table(vacant.text)
    assert "No lots match" in house.text
    # An unknown choice filters nothing.
    for address in ("2833 SE 71ST AVE", "4110 NE 12TH AVE", "10722 SE 32ND AVE"):
        assert address in _table(anything.text)
    assert 'id="occupancy-filter"' in teardown.text
    assert '<option value="teardown" selected>' in teardown.text


async def test_the_label_never_moves_a_colour(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    run = await _seed(session)
    before = (await client.get(f"/api/flats/lot/multnomah/{A}")).json()
    colours = sorted((r.design_key, r.tier, json.dumps(r.checks, sort_keys=True))
                     for r in (await session.execute(select(FlatsLotResult))).scalars())
    await _label(session, run, A, "teardown")
    after = (await client.get(f"/api/flats/lot/multnomah/{A}")).json()

    assert before["occupancy"] is None
    assert after["occupancy"]["label"] == "teardown"
    assert after["occupancy"]["never_a_colour"] is True
    for key in ("colour", "verdict", "designs", "colour_words", "verdict_words"):
        assert after[key] == before[key], key
    assert colours == sorted((r.design_key, r.tier, json.dumps(r.checks, sort_keys=True))
                             for r in (await session.execute(select(FlatsLotResult))).scalars())


async def test_the_lot_page_says_what_stands_there(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    run = await _seed(session)
    await _label(session, run, A, "unclear", disagreement="roll_building_no_footprint", building_count=0)

    page = await client.get(f"/flats/lots/multnomah/{A.replace(' ', '%20')}")
    bare = await client.get(f"/flats/lots/multnomah/{B.replace(' ', '%20')}")

    assert page.status_code == 200
    block = page.text.split('id="lot-occupancy"', 1)[1].split("</table>", 1)[0]
    assert 'data-occupancy="unclear"' in block
    assert "Why unclear: the tax roll carries a building value, but the footprint map shows no building" in block
    assert "$62,000 of $480,000" in block
    assert "never changes the lot" in page.text.split('id="lot-occupancy"', 1)[1]
    assert "not measured yet" in bare.text.split('id="lot-occupancy"', 1)[1]


async def test_a_build_loads_onto_its_copy_s_lots(
    tmp_path: Path, client: AsyncClient, session: AsyncSession, _test_db_url: str
):
    run = await _seed(session)
    # The fetch's files: one footprint on lot A (whose polygon _seed draws at 7,650,000 / 680,000).
    fetch = tmp_path / "fetch"
    fetch.mkdir()
    (fetch / META_FILE).write_text(json.dumps({"label": "Metro RLIS Building Footprint Database",
                                               "fetched_at": "2026-11-08T06:47:03+00:00"}), encoding="utf-8")
    house = box(7_650_010, 680_010, 7_650_050, 680_040)
    with gzip.open(fetch / FOOTPRINTS_FILE, "wt", encoding="utf-8") as fh:
        fh.write(json.dumps({"p": {"FID": 1}, "g": json.loads(shapely.to_geojson(house))}) + "\n")
    lots = pa.table({
        "county": ["multnomah", "multnomah", "multnomah"],
        "tlid": [A, B, "NOT IN THE COPY"],
        "wkb": [shapely.to_wkb(box(7_650_000, 680_000, 7_650_089, 680_157)),
                shapely.to_wkb(box(7_640_000, 690_000, 7_640_050, 690_100)),
                shapely.to_wkb(box(0, 0, 10, 10))],
        "area_sqft": [13973.0, 5000.0, 100.0],
        "LANDVAL": [400_000.0, 300_000.0, 1.0],
        "BLDGVAL": [70_000.0, 0.0, 0.0],
        "TOTALVAL": [470_000.0, 300_000.0, 1.0],
        "YEARBUILT": [1922, 0, 0],
        "BLDGSQFT": [900.0, 0.0, 0.0],
    })
    pq.write_table(lots, tmp_path / "lots.parquet")

    summary = build(fetch, tmp_path / "lots.parquet", tmp_path / "out")
    assert summary["labels"]["multnomah"] == {"teardown": 1, "vacant": 2}
    report = await load(tmp_path / "out", _test_db_url, snapshot_id=run.snapshot_id)

    assert report["written"] == 2 and report["file_rows_without_a_lot"] == 1
    assert report["labels"] == {"teardown": 1, "vacant": 1}
    rows = {r.label for r in (await session.execute(select(FlatsLotOccupancy))).scalars()}
    assert rows == {"teardown", "vacant"}
    again = await load(tmp_path / "out", _test_db_url, snapshot_id=run.snapshot_id)
    assert again["removed"] == 2 and again["written"] == 2
