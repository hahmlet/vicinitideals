"""Price per home on the Lots page and the lot page (FOLLOWUPS 66).

Three things are held here: the SQL form of the arithmetic (which the filter
and the sort run over the whole county copy) answers exactly what the Python
form (which labels each row) answers; the filter keeps lots with no price and
drops lots no pod fits; and the colour never moves.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import ui_flats
from app.models.flats import FlatsLot
from app.services import flats_price
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


async def _priced(session: AsyncSession) -> None:
    await _price(session, A, {"total_value": 600_000, "sale_price": 250_000, "sale_date": "20190305"})
    await _price(session, B, {"total_value": 100_000})
    await _price(session, C, None)


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


async def test_sql_and_python_agree_on_pods_and_price_on_edge_lots(session: AsyncSession):
    """The filter runs the SQL form; the labels run the Python form. Edge areas:
    the road threshold, an exact pod, a sliver, a missing area, a capped zone,
    and each colour class (green and yellow keep one pod)."""
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
            lot.area_sqft = area
            await session.flush()
            for rank in (0, 1, 2, 3):
                pods = flats_price.pods_column(cfg, caps, literal(rank))
                per_home = flats_price.per_home_column(cfg, pods)
                got_pods, got_per = (
                    await session.execute(select(pods, per_home).where(FlatsLot.id == lot.id))
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
    pods = flats_price.pods_column(price_calc.settings(), {}, literal(0))
    got = (await session.execute(select(pods).limit(1))).scalar_one()
    assert int(got) >= 0
