"""The Lots page's stored per-lot best rows match the live aggregate."""

from __future__ import annotations

import re

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import ui_flats
from app.api.routers.ui_flats import _lot_conditions, _lot_counts, _lot_rows, _price_params
from app.models.flats import FlatsLot, FlatsLotBest, FlatsLotResult
from flats.ingest.lot_best import DELETE_SQL, FILL_SQL
from tests.api.test_ui_flats_lots import DESIGNS, _login, _seed

pytestmark = pytest.mark.asyncio


async def _fill(session: AsyncSession, run_id: int) -> int:
    await session.execute(text(DELETE_SQL.replace("$1", ":r")), {"r": run_id})
    status = await session.execute(text(FILL_SQL.replace("$1", ":r")), {"r": run_id})
    await session.commit()
    return status.rowcount or 0


async def test_refresh_writes_the_run_lot_best_verdict_and_colour(session: AsyncSession):
    run = await _seed(session)
    lot = (
        await session.execute(select(FlatsLot).where(FlatsLot.tlid == "1S2E08BA  -09500"))
    ).scalar_one()
    rows = (
        await session.execute(
            select(FlatsLotResult).where(FlatsLotResult.run_id == run.id, FlatsLotResult.lot_id == lot.id)
        )
    ).scalars().all()
    by_design = {row.design_key: row for row in rows}
    by_design[DESIGNS[0]].tier = "red"
    by_design[DESIGNS[0]].checks = {**by_design[DESIGNS[0]].checks, "if_signed": "red"}
    by_design[DESIGNS[1]].tier = "green"
    by_design[DESIGNS[1]].checks = {**by_design[DESIGNS[1]].checks, "if_signed": "yellow"}
    await session.commit()

    await _fill(session, run.id)

    best = await session.get(FlatsLotBest, {"run_id": run.id, "lot_id": lot.id})
    assert best is not None
    assert best.best_verdict == 0  # green
    assert best.best_colour == 1  # yellow


async def test_stored_lot_best_matches_live_counts_and_list_order(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    run = await _seed(session)
    await _fill(session, run.id)
    price = {**_price_params("0", "30000", "4500", "25"), "as_of": ""}

    live_conditions = _lot_conditions("", "", "", lot=FlatsLot)
    stored_conditions = _lot_conditions("", "", "", lot=FlatsLotBest)
    live_counts = await _lot_counts(session, run.id, None, live_conditions, price, stored=False)
    stored_counts = await _lot_counts(
        session, run.id, None, stored_conditions, price, stored=True, conditions_on_best=True
    )
    assert stored_counts == live_counts

    live_city_conditions = _lot_conditions("or/multnomah/portland", "", "", lot=FlatsLot)
    stored_city_conditions = _lot_conditions("or/multnomah/portland", "", "", lot=FlatsLotBest)
    live_city_counts = await _lot_counts(session, run.id, None, live_city_conditions, price, stored=False)
    stored_city_counts = await _lot_counts(
        session, run.id, None, stored_city_conditions, price, stored=True, conditions_on_best=True
    )
    assert stored_city_counts == live_city_counts

    live_rows = await _lot_rows(session, run.id, None, live_conditions, "", 1, price, stored=False)
    stored_rows = await _lot_rows(
        session, run.id, None, stored_conditions, "", 1, price, stored=True, conditions_on_best=True
    )
    assert [row["id"] for row in stored_rows] == [row["id"] for row in live_rows]
    assert [(row["verdict"], row["colour"]) for row in stored_rows] == [
        (row["verdict"], row["colour"]) for row in live_rows
    ]


async def test_a_run_with_no_lot_best_rows_falls_back_to_live_query(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    await _login(client, session)
    run = await _seed(session)
    assert (
        await session.execute(select(FlatsLotBest.lot_id).where(FlatsLotBest.run_id == run.id).limit(1))
    ).first() is None

    original_best = ui_flats._best

    def _guarded_best(*args, **kwargs):  # type: ignore[no-untyped-def]
        if kwargs.get("stored"):
            raise AssertionError("stored lot_best path should not run without lot_best rows")
        return original_best(*args, **kwargs)

    monkeypatch.setattr(ui_flats, "_best", _guarded_best)

    page = await client.get("/flats/lots")
    assert page.status_code == 200
    assert "1S2E08BA  -09500" in page.text


async def test_the_page_lists_the_same_lots_before_and_after_the_table_fills(
    client: AsyncClient, session: AsyncSession
):
    """Through the route, so a filter that only works on the live query shows."""
    await _login(client, session)
    run = await _seed(session)
    urls = [
        "/flats/lots",
        "/flats/lots?jurisdiction=or/multnomah/portland",
        "/flats/lots?q=09500",
        "/flats/lots?colour=green",
        "/flats/lots?form=apartment",
        "/flats/lots?tight=1",
    ]

    async def shown() -> list[list[str]]:
        pages = []
        for url in urls:
            page = await client.get(url)
            assert page.status_code == 200, url
            pages.append(re.findall(r"(?:1S2E08BA|1N1E29DD|11E25AB)  -\d{5}", page.text))
        return pages

    live = await shown()
    assert any(live)
    await _fill(session, run.id)
    assert await shown() == live
