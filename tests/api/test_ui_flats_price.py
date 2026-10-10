"""Price per home on the Lots page and the lot page (FOLLOWUPS 66).

Held here: the stored price columns (``flats.lot_prices``) are filled from a
lot's facts and its zone's density limits; the SQL form of the arithmetic
(which the filter and the sort run over the whole county copy, on those stored
columns) answers exactly what the Python form (which labels each row) answers;
the filter keeps lots with no price and drops lots no pod fits; the colour
never moves; and a query that runs past its clock gives a "too slow" page, not
a hang.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import literal, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import ui_flats
from app.models.flats import FlatsLot, FlatsLotPrice
from app.services import flats_price
from flats.ingest import lot_prices
from flats.score import price as price_calc
from tests.api.test_ui_flats_lots import _login, _seed

pytestmark = pytest.mark.asyncio

A = "1S2E08BA  -09500"  # Portland R5, 13,973 sf, green (min colour across designs)
B = "1N1E29DD  -05600"  # Portland R2.5, 5,000 sf, yellow
C = "11E25AB  -00300"  # Milwaukie R-7, 7,200 sf, unknown


async def _price(session: AsyncSession, tlid: str, assessor: dict | None) -> None:
    lot = (await session.execute(select(FlatsLot).where(FlatsLot.tlid == tlid))).scalar_one()
    facts = dict(lot.facts or {})
    if assessor is None:
        facts.pop("assessor", None)
    else:
        facts["assessor"] = assessor
    lot.facts = facts
    await session.commit()


async def _refresh(session: AsyncSession, caps: dict | None = None) -> int:
    """Fill ``flats.lot_prices`` the way the loader does, on the test's own transaction."""
    snapshots = (await session.execute(select(FlatsLot.snapshot_id).distinct())).scalars().all()
    connection = await session.connection()
    raw = (await connection.get_raw_connection()).driver_connection
    written = 0
    for snapshot_id in snapshots:
        written += await lot_prices.refresh(
            raw, snapshot_id, lot_prices.current_caps() if caps is None else caps
        )
    return written


async def _priced(session: AsyncSession) -> None:
    await _price(session, A, {"total_value": 600_000, "sale_price": 250_000, "sale_date": "20190305"})
    await _price(session, B, {"total_value": 100_000})
    await _price(session, C, None)
    await _refresh(session)
    await session.commit()


def _rows(page_text: str) -> list[str]:
    return [t for t in (A, B, C) if t in page_text]


async def test_the_lots_page_shows_a_price_per_home_for_every_lot(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    await _seed(session)
    await _priced(session)

    page = await client.get("/flats/lots")

    assert "Price per home" in page.text
    cells = page.text.split("ppu-cell")
    assert len(cells) == 4
    # B: one pod = four homes, $100,000 / 4 = $25,000. No estimate on one pod.
    assert "$25,000" in page.text
    # A: two pods (after roads) = eight homes, $600,000 / 8 = $75,000, an estimate.
    assert "$75,000" in page.text and "ESTIMATE" in page.text
    # C: no county value -> says so, never a zero.
    assert "no price" in page.text


async def test_the_filter_keeps_cheap_lots_and_lots_with_no_price_and_never_changes_a_colour(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session)
    await _priced(session)

    everything = await client.get("/flats/lots")
    filtered = await client.get("/flats/lots?ppu=1&ppu_max=30000")

    assert set(_rows(everything.text)) == {A, B, C}
    # A ($75,000 a home) is out; B ($25,000) and C (no price) stay.
    assert set(_rows(filtered.text)) == {B, C}
    # Raising the ceiling brings A back.
    assert set(_rows((await client.get("/flats/lots?ppu=1&ppu_max=80000")).text)) == {A, B, C}
    # The colour of a lot that stays is what it was without the filter.
    assert 'id="ppu-on"' in filtered.text
    assert "checked" in filtered.text.split('id="ppu-on"', 1)[1][:80]


async def test_an_adjusted_pod_size_changes_the_price_and_the_cheapest_sort_orders_by_it(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session)
    await _priced(session)

    # A 2,500 sf pod doubles the pods on B? 5,000 / 2,500 = 2 pods = 8 homes -> $12,500.
    page = await client.get("/flats/lots?pod=2500&road=0")
    assert "$12,500" in page.text

    cheapest = await client.get("/flats/lots?sort=ppu")
    text = cheapest.text
    assert text.index(B) < text.index(A) < text.index(C)  # $25,000, $75,000, then no price last


async def test_the_lot_page_shows_the_label_its_source_and_as_of_and_the_last_sale(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session)
    await _priced(session)

    page = await client.get("/flats/lots/multnomah/1S2E08BA%20%20-09500")
    body = page.text.split('id="lot-price"', 1)[1].split("lot-verdict", 1)[0]

    assert "$75,000" in body
    assert "ESTIMATE" in body
    assert "2 pods = 8 homes" in body
    assert "County real market value" in body
    assert "RLIS 2026_08 release" in body
    assert "$250,000" in body and "2019-03-05" in body and "not used" in body

    none = await client.get("/flats/lots/clackamas/11E25AB%20%20-00300")
    assert "No county value on file" in none.text


async def test_the_stored_row_carries_the_price_its_source_as_of_area_and_the_zone_caps(session: AsyncSession):
    await _seed(session)
    await _price(session, A, {"total_value": 600_000})
    await _price(session, B, {"total_value": "not a number"})
    await _price(session, C, None)
    caps = {("or/multnomah/portland", "R5"): price_calc.ZoneCap(du_per_acre=Decimal(10), unit_lot_sqft=Decimal(3000))}

    written = await _refresh(session, caps)

    rows = {
        lot.tlid: row
        for row, lot in (
            await session.execute(select(FlatsLotPrice, FlatsLot).join(FlatsLot, FlatsLot.id == FlatsLotPrice.lot_id))
        ).all()
    }
    assert written == len(rows) == len((await session.execute(select(FlatsLot.id))).all())
    a = rows[A]
    assert a.amount == Decimal("600000.00") and a.source == "County real market value"
    assert "county copy of" in a.as_of and a.area_sqft == Decimal("13973.00")
    assert (a.cap_du_per_acre, a.cap_unit_lot_sqft) == (Decimal("10.00"), Decimal("3000.00"))
    # A value that is not a number, and a lot with no roll at all, are "no price" -- never a zero.
    assert rows[B].amount is None and rows[B].source is None and rows[B].as_of is None
    assert rows[C].amount is None
    # A zone that states no limit has no cap.
    assert rows[B].cap_du_per_acre is None and rows[B].cap_unit_lot_sqft is None
    # Running it again is an update, not a second row.
    assert await _refresh(session, caps) == written
    assert len((await session.execute(select(FlatsLotPrice))).all()) == written
    await session.rollback()


async def test_a_lot_with_no_stored_price_row_reads_as_no_price_and_is_kept_by_the_filter(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session)
    await _priced(session)
    await session.execute(text("DELETE FROM flats.lot_prices"))
    await session.commit()

    page = await client.get("/flats/lots?ppu=1&ppu_max=1&sort=ppu")

    # Nothing is priced, so a ceiling of $1 hides no lot that a pod fits on.
    assert page.status_code == 200
    assert A in page.text and B in page.text


async def test_the_page_limits_are_set_for_the_request_and_a_timeout_gives_a_too_slow_page(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    await _login(client, session)
    await _seed(session)
    await ui_flats._lots_limits(session)
    assert (await session.execute(text("SHOW statement_timeout"))).scalar_one() == "25s"
    assert (await session.execute(text("SHOW work_mem"))).scalar_one() == "128MB"
    await session.rollback()

    class Cancelled(Exception):
        sqlstate = "57014"

    async def too_slow(*args, **kwargs):
        raise DBAPIError("select 1", {}, Cancelled("canceling statement due to statement timeout"))

    monkeypatch.setattr(ui_flats, "_lot_counts", too_slow)
    page = await client.get("/flats/lots?ppu=1")

    assert page.status_code == 200
    assert "took too long" in page.text

    other = DBAPIError("select 1", {}, Exception("deadlock detected"))
    assert not ui_flats._timed_out(other)


async def test_sql_and_python_agree_on_pods_and_price_on_edge_lots(session: AsyncSession):
    """The filter runs the SQL form over the stored columns; the labels run the
    Python form over the facts. Edge areas: the road threshold, an exact pod, a
    sliver, a missing area, a capped zone, and each colour class (green and
    yellow keep one pod)."""
    await _seed(session)
    caps = {
        ("or/multnomah/portland", "R5"): price_calc.ZoneCap(du_per_acre=Decimal(10)),
        ("or/multnomah/portland", "R2.5"): price_calc.ZoneCap(unit_lot_sqft=Decimal(2500)),
    }
    cfg = price_calc.settings()
    lots = (await session.execute(select(FlatsLot).order_by(FlatsLot.id))).scalars().all()
    areas = [None, 0, 100, 4499, 4500, 9000, 13_499.99, 13_500, 13_973, 20_000, 90_000, 1_000_000]
    for lot in lots:
        lot.facts = {**(lot.facts or {}), "assessor": {"total_value": 360_000}}
    for area in areas:
        for lot in lots:
            lot.area_sqft = area
        await session.flush()
        await _refresh(session, caps)
        for lot in lots:
            for rank in (0, 1, 2, 3):
                pods = flats_price.pods_column(cfg, literal(rank))
                per_home = flats_price.per_home_column(cfg, pods)
                got_pods, got_per = (
                    await session.execute(
                        select(pods, per_home).select_from(FlatsLotPrice).where(FlatsLotPrice.lot_id == lot.id)
                    )
                ).one()
                cap = caps.get((ui_flats._pocket_of(lot.facts) or lot.jurisdiction, lot.zone or ""))
                want = price_calc.price_per_home(area, lot.facts, cfg, cap=cap, keep_one=rank <= 1)
                assert int(got_pods) == want.pods, (lot.tlid, area, rank)
                if want.per_home is None:
                    assert got_per is None, (lot.tlid, area, rank)
                else:
                    assert abs(Decimal(got_per) - want.per_home) < Decimal("0.01"), (lot.tlid, area, rank)
    await session.rollback()


async def test_sql_with_no_caps_at_all_is_still_valid(session: AsyncSession):
    await _seed(session)
    await _refresh(session, {})
    pods = flats_price.pods_column(price_calc.settings(), literal(0))
    got = (await session.execute(select(pods).select_from(FlatsLotPrice).limit(1))).scalar_one()
    assert int(got) >= 0
    await session.rollback()
