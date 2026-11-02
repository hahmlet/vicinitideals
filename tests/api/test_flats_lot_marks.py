"""Person-entered tree marks overlay GREEN display colours without changing a run."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import FlatsLot, FlatsLotMark, FlatsLotResult
from tests.api.test_ui_flats_lots import DESIGNS, _login, _seed
from tests.conftest import seed_org

pytestmark = pytest.mark.asyncio

TLID = "1S2E08BA  -09500"
LOT_URL = "/flats/lots/multnomah/1S2E08BA%20%20-09500"
REPORT_URL = "/api/flats/lot/multnomah/1S2E08BA%20%20-09500"


async def _lot(session: AsyncSession) -> FlatsLot:
    return (
        await session.execute(select(FlatsLot).where(FlatsLot.tlid == TLID))
    ).scalar_one()


def _form(lot: FlatsLot, run_id: int, note: str) -> dict[str, str | int]:
    return {
        "lot_id": lot.id,
        "county": lot.county,
        "tlid": lot.tlid,
        "run": run_id,
        "note": note,
    }


async def test_mark_changes_green_display_and_clear_restores_it(
    client: AsyncClient, session: AsyncSession
):
    user = await _login(client, session)
    run = await _seed(session)
    lot = await _lot(session)
    before = (await client.get(REPORT_URL)).json()
    assert before["colour"] == "green"
    assert "trees_mark" not in before

    added = await client.post("/ui/flats/lot-marks", data=_form(lot, run.id, "Mature oak by the drive"))
    assert added.status_code == 200
    assert added.headers.get("hx-refresh") == "true"  # colour above the panel reloads
    assert 'id="trees-open-mark"' in added.text
    assert "Mature oak by the drive" in added.text

    mark = (await session.execute(select(FlatsLotMark))).scalar_one()
    await session.refresh(mark)
    assert mark.created_by == user.id
    assert mark.note == "Mature oak by the drive"
    report = (await client.get(REPORT_URL)).json()
    assert report["colour"] == "yellow"
    assert report["colour_reasons"] == [
        f"Marked as having trees that may need a tree permit: Mature oak by the drive ({user.name}, {mark.created_at.date().isoformat()})"
    ]
    assert report["trees_mark"]["note"] == mark.note
    lookup = (
        await client.get("/api/flats/lookup", params={"q": TLID})
    ).json()
    assert lookup["matches"][0]["colour"] == "yellow"
    by_design = {row["design"]: row for row in report["designs"]}
    assert by_design[DESIGNS[0]]["colour"] == "yellow"
    assert report["colour_reasons"][0] in by_design[DESIGNS[0]]["colour_reasons"]
    assert by_design[DESIGNS[1]]["colour"] == "yellow"

    listing = await client.get("/flats/lots", params={"run": run.id, "colour": "yellow"})
    assert TLID in listing.text
    assert "yellow 2" in listing.text
    green_listing = await client.get("/flats/lots", params={"run": run.id, "colour": "green"})
    assert TLID not in green_listing.text

    cleared = await client.post(
        f"/ui/flats/lot-marks/{mark.id}/clear",
        data={
            "lot_id": lot.id,
            "county": lot.county,
            "tlid": lot.tlid,
            "run": run.id,
            "clear_note": "Tree checked",
        },
    )
    assert cleared.status_code == 200
    assert cleared.headers.get("hx-refresh") == "true"
    assert 'class="trees-history-row"' in cleared.text
    assert "Tree checked" in cleared.text
    after = (await client.get(REPORT_URL)).json()
    assert after["colour"] == "green"
    assert "trees_mark" not in after
    assert "colour_reasons" not in after

    stored = await session.get(FlatsLotMark, mark.id)
    assert stored is not None
    assert stored.cleared_by == user.id
    assert stored.cleared_at is not None
    assert stored.clear_note == "Tree checked"


async def test_second_open_tree_mark_is_refused(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    run = await _seed(session)
    lot = await _lot(session)

    first = await client.post("/ui/flats/lot-marks", data=_form(lot, run.id, "First tree"))
    second = await client.post("/ui/flats/lot-marks", data=_form(lot, run.id, "Second tree"))

    assert first.status_code == second.status_code == 200
    assert "already exists" in second.text
    assert len((await session.execute(select(FlatsLotMark))).scalars().all()) == 1


async def test_red_lot_stays_red_when_marked(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    run = await _seed(session)
    lot = await _lot(session)
    results = (
        await session.execute(select(FlatsLotResult).where(FlatsLotResult.lot_id == lot.id))
    ).scalars().all()
    for row in results:
        row.checks = {**row.checks, "if_signed": "red"}
    await session.commit()

    await client.post("/ui/flats/lot-marks", data=_form(lot, run.id, "Tree on site"))

    report = (await client.get(REPORT_URL)).json()
    assert report["colour"] == "red"
    assert all(result["colour"] == "red" for result in report["designs"])


async def test_note_strips_nul_and_enforces_the_2000_character_limit(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    run = await _seed(session)
    lot = await _lot(session)

    too_long = await client.post("/ui/flats/lot-marks", data=_form(lot, run.id, "x" * 2001))
    assert too_long.status_code == 200
    assert "2,000 characters or fewer" in too_long.text
    assert (await session.execute(select(FlatsLotMark))).scalars().all() == []

    response = await client.post("/ui/flats/lot-marks", data=_form(lot, run.id, "tree\u0000"))
    assert response.status_code == 200
    mark = (await session.execute(select(FlatsLotMark))).scalar_one()
    assert mark.note == "tree"

    await client.post(
        f"/ui/flats/lot-marks/{mark.id}/clear",
        data={"lot_id": lot.id, "county": lot.county, "tlid": lot.tlid, "run": run.id},
    )
    accepted = await client.post("/ui/flats/lot-marks", data=_form(lot, run.id, "x" * 2000))
    assert accepted.status_code == 200
    latest = (
        await session.execute(select(FlatsLotMark).order_by(FlatsLotMark.id.desc()))
    ).scalars().first()
    assert latest is not None and len(latest.note) == 2000


async def test_anonymous_add_and_clear_posts_are_refused(client: AsyncClient, session: AsyncSession):
    run = await _seed(session)
    lot = await _lot(session)
    user = (await seed_org(session))[1]
    mark = FlatsLotMark(lot_id=lot.id, kind="trees", note="Existing tree", created_by=user.id)
    session.add(mark)
    await session.commit()

    add = await client.post("/ui/flats/lot-marks", data=_form(lot, run.id, "New tree"))
    clear = await client.post(
        f"/ui/flats/lot-marks/{mark.id}/clear",
        data={"lot_id": lot.id, "county": lot.county, "tlid": lot.tlid, "run": run.id},
    )

    assert add.status_code in (401, 303)
    assert clear.status_code in (401, 303)
    stored = await session.get(FlatsLotMark, mark.id)
    assert stored is not None and stored.cleared_at is None
    assert len((await session.execute(select(FlatsLotMark))).scalars().all()) == 1
