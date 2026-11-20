"""The foundation model on the lot page and in the lot report (FOLLOWUPS 209).

A measured record stored in ``flats.lot_foundation`` is priced when the page or
the report is drawn, with the settings of the moment: the report carries a
``foundation`` block (money as strings), null for a lot never measured; a record
measured under other building dimensions reads "needs re-measuring" and carries
no figure; the "if a mapped building here had a basement" figure stays out of
every cost; and no colour, verdict or result moves. The loader upserts by county
and TLID and can be run twice.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import FlatsLotFoundation, FlatsLotResult
from flats.foundation import ground as grounds
from flats.foundation import measure, oldbuild, record, settings
from scripts.flats_foundation import load
from tests.api.test_ui_flats_lots import LOT_B_DRAWING, _login, _seed

pytestmark = pytest.mark.asyncio

A = "1S2E08BA  -09500"  # 2833 SE 71ST AVE
B = "1N1E29DD  -05600"  # 4110 NE 12TH AVE
WHEN = "2026-11-19T12:00:00+00:00"
DRAWING = "the rel9 drawn buildings (test)"


def _doc(tlid: str = A, *, grow_ft: float | None = None, ring: list | None = None) -> dict:
    s = settings.load()
    m = measure.measure(
        grounds.plane(s, 3.0, 1.0), s, tlid=tlid, county="multnomah",
        inputs={"ground_class": "FIRM", "frost_register_in": 12.0, "year_built": 1925},
    )
    box = oldbuild.Outline(((((30.0, -5.0), (55.0, -5.0), (55.0, 12.0), (30.0, 12.0), (30.0, -5.0))),), "B1", 1925)
    m = measure.with_old_buildings(m, True, oldbuild.measure_all([box], s))
    doc = record.document(m, drawing=DRAWING, measured_at=WHEN, run="run 128" if ring else None, ring=ring)
    if grow_ft is not None:  # as if measured under other settings
        geometry = json.loads(doc["lot"]["geometry"])
        geometry["grow_ft"] = grow_ft
        doc["lot"]["geometry"] = json.dumps(geometry, sort_keys=True)
    return json.loads(json.dumps(doc))


async def _store(session: AsyncSession, doc: dict) -> None:
    on = doc["measured_on"]
    session.add(FlatsLotFoundation(
        county=doc["lot"]["county"], tlid=doc["lot"]["tlid"], record_version=doc["record_version"],
        model_version=doc["model_version"], geometry_hash=doc["geometry_hash"], drawing=on["drawing"],
        ground_source=on["ground_source"], cell_m=on["cell_m"], measured_at=datetime.fromisoformat(on["measured_at"]),
        record=doc,
    ))
    await session.commit()


async def _results(session: AsyncSession) -> list:
    return sorted((r.design_key, r.tier, json.dumps(r.checks, sort_keys=True))
                  for r in (await session.execute(select(FlatsLotResult))).scalars())


async def test_the_report_carries_the_block_priced_now_and_no_colour_moves(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    await _seed(session)
    before = (await client.get(f"/api/flats/lot/multnomah/{A}")).json()
    results = await _results(session)
    await _store(session, _doc())
    after = (await client.get(f"/api/flats/lot/multnomah/{A}")).json()
    bare = (await client.get(f"/api/flats/lot/multnomah/{B}")).json()

    assert before["foundation"] is None and bare["foundation"] is None
    f = after["foundation"]
    assert f["status"] == "priced" and f["never_a_colour"] is True
    assert f["settings_version"] == record.settings_version()
    assert f["measured_on"]["drawing"] == DRAWING and f["measured_on"]["ground_source"] == "plane"
    assert f["style"]["words"].startswith("Ordinary ground: a slab on fill or a raised floor")
    names = [m["method"] for m in f["methods"]]
    assert names == ["A dry", "A wet", "B"]
    for m in f["methods"]:
        # Money is a string of dollars and cents, never a float.
        assert isinstance(m["cost_low"], str) and isinstance(m["cost_high"], str)
        assert Decimal(m["cost_low"]) <= Decimal(m["cost_high"])
        assert Decimal(m["cost_low"]).as_tuple().exponent == -2
        assert all(isinstance(ln["low"], str) for ln in m["cost_lines"])
        assert len(m["doors"]) == 8
    assert all(isinstance(c["by"], str) for c in f["cheaper"])
    assert {c["code"] for c in f["challenges"]} >= {"wall_over_old_building"}
    old = f["old_buildings"]
    assert old["in_total"] is False and old["count"] == 1
    assert isinstance(old["if_basement"]["B"]["low"], str) and isinstance(old["weighted"]["A"]["high"], str)
    assert old["if_basement_words"].startswith("If a mapped building here had a basement:")
    assert {fl["code"] for fl in f["flags"]} >= {"wall_crosses_old_building"}
    # Nothing that screens moved.
    for key in ("colour", "verdict", "designs", "colour_words", "verdict_words"):
        assert after[key] == before[key], key
    assert await _results(session) == results


async def test_a_record_under_other_dimensions_needs_re_measuring(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    await _seed(session)
    await _store(session, _doc(grow_ft=9.0))
    f = (await client.get(f"/api/flats/lot/multnomah/{A}")).json()["foundation"]
    assert f["status"] == "needs_remeasuring" and f["remeasure_because"] == ["grow_ft"]
    assert "methods" not in f and "old_buildings" not in f

    page = await client.get(f"/flats/lots/multnomah/{A.replace(' ', '%20')}")
    panel = page.text.split('id="lot-foundation"', 1)[1].split("<!-- end lot-foundation -->", 1)[0]
    assert 'data-foundation-status="needs_remeasuring"' in page.text
    assert "Needs re-measuring" in panel and "$" not in panel


async def test_a_record_measured_on_another_drawing_shows_no_figure(client: AsyncClient, session: AsyncSession):
    # Slice 4: a record stamped with the ring it was measured on is priced only
    # while the lot's drawn building is that ring; once the drawing moves, the
    # report and the page say "measured on an earlier drawing" and show no figure.
    await _login(client, session)
    await _seed(session)
    ring = LOT_B_DRAWING["building"]
    await _store(session, _doc(B, ring=ring))
    same = (await client.get(f"/api/flats/lot/multnomah/{B}")).json()["foundation"]
    assert same["status"] == "priced" and same["drawing_checked"] is True
    assert same["measured_on"]["run"] == "run 128" and same["measured_on"]["drawing_hash"] == record.ring_hash(ring)
    assert "drawn_ring" not in same["measured_on"]

    row = await session.get(FlatsLotFoundation, ("multnomah", B))
    moved = [[x + 6.0, y] for x, y in ring]  # the pod drawn 6 ft along since
    row.record = _doc(B, ring=moved)
    await session.commit()
    f = (await client.get(f"/api/flats/lot/multnomah/{B}")).json()["foundation"]
    assert f["status"] == "needs_remeasuring" and f["remeasure_because"] == ["drawing"]
    assert "methods" not in f and "old_buildings" not in f and "style" not in f
    assert f["status_words"].startswith("Measured on an earlier drawing -- needs re-measuring")

    page = await client.get(f"/flats/lots/multnomah/{B.replace(' ', '%20')}")
    panel = page.text.split('id="lot-foundation"', 1)[1].split("<!-- end lot-foundation -->", 1)[0]
    assert 'data-foundation-status="needs_remeasuring"' in page.text
    assert "Measured on an earlier drawing" in panel and "$" not in panel


async def test_a_lot_with_no_drawing_on_the_page_is_priced_unchecked(client: AsyncClient, session: AsyncSession):
    # Lot A's results carry no drawing: a stamped record is priced, and says the
    # drawing was not checked.
    await _login(client, session)
    await _seed(session)
    await _store(session, _doc(A, ring=LOT_B_DRAWING["building"]))
    f = (await client.get(f"/api/flats/lot/multnomah/{A}")).json()["foundation"]
    assert f["status"] == "priced" and f["drawing_checked"] is False


async def test_the_lot_page_shows_the_panel_beside_the_colour(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    await _seed(session)
    await _store(session, _doc())
    page = await client.get(f"/flats/lots/multnomah/{A.replace(' ', '%20')}")
    bare = await client.get(f"/flats/lots/multnomah/{B.replace(' ', '%20')}")

    assert page.status_code == 200
    panel = page.text.split('id="lot-foundation"', 1)[1].split("<!-- end lot-foundation -->", 1)[0]
    assert "Foundation (not a screen check)" in panel
    assert "No effect on the colour" in panel and "never changes the lot&#39;s colour" in panel
    assert 'data-foundation-status="priced"' in page.text
    assert 'data-foundation-method="A dry"' in panel and 'data-foundation-method="B"' in panel
    assert "Slab on fill (dry season)" in panel or "slab on fill (dry season)" in panel
    assert "Steps at the 8 doors:" in panel
    assert "If a mapped building here had a basement:" in panel
    assert "Weighted by how often a house built 1925 had a basement (80%)" in panel
    assert "Sizes are code minimums" in panel and "not a budget" in panel
    assert 'data-foundation-doors="B"' in panel and 'data-foundation-cost-lines="A dry"' in panel
    assert 'id="lot-verdict"' in page.text
    assert 'data-foundation-status="not_measured"' in bare.text
    assert "not measured yet" in bare.text.split('id="lot-foundation"', 1)[1]


async def test_the_loader_upserts_by_county_and_tlid(tmp_path: Path, session: AsyncSession, _test_db_url: str):
    await _seed(session)
    path = tmp_path / "records.jsonl.gz"
    record.write_jsonl(path, [_doc(A), _doc(B), _doc("NOT IN THE COPY")])

    dry = await load(path, _test_db_url, dry_run=True)
    assert dry["written"] == 3 and dry["new"] == 3
    assert (await session.execute(select(FlatsLotFoundation))).scalars().first() is None

    first = await load(path, _test_db_url)
    assert first["written"] == 3 and first["new"] == 3 and first["rows_in_table"] == 3
    assert first["in_current_copy"] == 2
    again = await load(path, _test_db_url)
    assert again["new"] == 0 and again["rows_in_table"] == 3

    session.expire_all()
    row = await session.get(FlatsLotFoundation, ("multnomah", A))
    assert row is not None and row.tlid == A  # the TLID's spaces kept
    assert row.drawing == DRAWING and row.ground_source == "plane" and row.record_version == record.RECORD_VERSION
    assert row.measured_at == datetime(2026, 11, 19, 12, tzinfo=timezone.utc)
    assert row.record["lot"]["tlid"] == A and "cost" not in json.dumps(row.record)
