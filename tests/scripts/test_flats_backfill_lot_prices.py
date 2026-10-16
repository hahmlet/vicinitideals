"""Backfilling ``flats.lot_prices`` for a county copy that is already live.

The script is a one-shot over a snapshot: it writes only ``flats.lot_prices``,
each snapshot in one transaction, and says so in a report. Held here: the
counts it returns match the lots and rows that exist; a dry run does the work
and rolls it back; a second run changes nothing; and the cap and net-area
columns are filled when the zone or the lot carries them.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.flats import FlatsLot, FlatsLotPrice
from flats.ingest import lot_prices
from flats.score import price as price_calc
from scripts.flats_backfill_lot_prices import backfill
from tests.api.test_ui_flats_lots import _seed

pytestmark = pytest.mark.asyncio

A = "1S2E08BA  -09500"  # Portland R5
B = "1N1E29DD  -05600"  # Portland R2.5
C = "11E25AB  -00300"  # Milwaukie R-7

CAPS = {
    ("or/multnomah/portland", "R5"): price_calc.ZoneCap(
        du_per_acre=Decimal(10),
        unit_lot_sqft=Decimal(3000),
        max_units=Decimal(8),
        density_on_net_area=True,
    )
}


@pytest.fixture(autouse=True)
def _caps(monkeypatch):
    """The zone caps the screen would read are the rules' business, not this test's."""
    monkeypatch.setattr(lot_prices, "current_caps", lambda: CAPS)


async def _seeded(session: AsyncSession) -> int:
    await _seed(session)
    lots = {
        lot.tlid: lot
        for lot in (await session.execute(select(FlatsLot))).scalars().all()
    }
    lots[A].facts = {**lots[A].facts, "assessor": {"total_value": 600_000}, "net_area_sqft": 8_000}
    lots[B].facts = {**lots[B].facts, "assessor": {"total_value": 100_000}}
    await session.commit()
    return lots[A].snapshot_id


async def _stored(session: AsyncSession) -> dict[str, tuple]:
    result = await session.execute(
        select(
            FlatsLot.tlid,
            FlatsLotPrice.amount,
            FlatsLotPrice.cap_max_units,
            FlatsLotPrice.cap_du_per_acre_net,
            FlatsLotPrice.net_area_sqft,
        )
        .join(FlatsLot, FlatsLot.id == FlatsLotPrice.lot_id)
        .execution_options(populate_existing=True)
    )
    return {row[0]: tuple(row[1:]) for row in result.all()}


async def test_the_counts_returned_equal_the_lots_and_rows(session: AsyncSession):
    snapshot_id = await _seeded(session)

    report = await backfill(settings.database_url, [snapshot_id])

    got = report["snapshots"][snapshot_id]
    assert report["dry_run"] is False and report["zone_caps"] == len(CAPS)
    assert got["lots"] == got["written"] == got["rows"] == 3
    assert got["priced"] == 2  # C has no county roll: "no price", never a zero
    assert "rolled_back" not in got
    assert len(await _stored(session)) == 3


async def test_the_cap_and_net_area_columns_are_filled_when_the_zone_or_lot_carries_them(
    session: AsyncSession,
):
    snapshot_id = await _seeded(session)

    report = await backfill(settings.database_url, [snapshot_id])

    got = report["snapshots"][snapshot_id]
    assert got["capped"] == got["max_units_capped"] == got["net_density_capped"] == 1
    assert got["with_net_area"] == 1
    stored = await _stored(session)
    assert stored[A] == (Decimal("600000.00"), Decimal("8.00"), True, Decimal("8000.00"))
    # A zone that states no limit, and a lot with no net area, leave those columns empty.
    assert stored[B] == (Decimal("100000.00"), None, False, None)
    assert stored[C] == (None, None, False, None)


async def test_a_dry_run_leaves_the_table_unchanged_and_says_it_rolled_back(
    session: AsyncSession,
):
    snapshot_id = await _seeded(session)

    dry = await backfill(settings.database_url, [snapshot_id], dry_run=True)

    got = dry["snapshots"][snapshot_id]
    assert dry["dry_run"] is True and got["rolled_back"] is True
    assert got["lots"] == got["written"] == got["rows"] == 3  # the work was done, then undone
    assert await _stored(session) == {}

    await backfill(settings.database_url, [snapshot_id])
    before = await _stored(session)
    lot = (await session.execute(select(FlatsLot).where(FlatsLot.tlid == B))).scalar_one()
    lot.facts = {**lot.facts, "assessor": {"total_value": 999_000}}
    await session.commit()

    again = await backfill(settings.database_url, [snapshot_id], dry_run=True)

    assert again["snapshots"][snapshot_id]["rolled_back"] is True
    assert await _stored(session) == before


async def test_a_second_run_is_idempotent(session: AsyncSession):
    snapshot_id = await _seeded(session)

    first = await backfill(settings.database_url, [snapshot_id])
    after_first = await _stored(session)
    second = await backfill(settings.database_url, [snapshot_id])

    assert second["snapshots"] == first["snapshots"]
    assert await _stored(session) == after_first
    assert (
        await session.execute(text("SELECT count(*) FROM flats.lot_prices"))
    ).scalar_one() == 3
