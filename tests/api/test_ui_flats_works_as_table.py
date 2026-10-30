"""The "Works as" filter reads ``flats.lot_works_as`` and answers exactly as the
old JSON grouping did (FOLLOWUPS 121), and a run with no table rows still
answers from the JSON."""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ui_flats import _FORM_CHOICES, _works_as
from app.models.flats import FlatsLot, FlatsLotResult, FlatsLotWorksAs
from flats.ingest.lot_works_as import DELETE_SQL, FILL_SQL
from tests.api.test_ui_flats_lots import DESIGNS, _box, _checks, _seed

pytestmark = pytest.mark.asyncio


def _forms(apartment: str | None, townhomes: str | None) -> dict:
    out = _checks("yellow")
    out["forms"] = {"apartment": {"colour": apartment}, "townhomes": {"colour": townhomes}}
    return out


async def _fill(session: AsyncSession, run_id: int) -> None:
    await session.execute(text(DELETE_SQL.replace("$1", ":r")), {"r": run_id})
    await session.execute(text(FILL_SQL.replace("$1", ":r")), {"r": run_id})
    await session.commit()


async def _lots(session: AsyncSession, run_id: int, design, form, *, stored: bool) -> set[int]:
    query = select(FlatsLot.id).where(FlatsLot.id.in_(_works_as(run_id, design, form, stored=stored)))
    return {r[0] for r in await session.execute(query)}


async def test_stored_works_as_matches_the_json_for_every_choice(session: AsyncSession):
    run = await _seed(session)
    plan = {  # lot -> {design: (apartment, townhomes)}; None = no forms recorded
        "A": {DESIGNS[0]: ("green", "yellow"), DESIGNS[1]: ("red", "green")},  # both, across designs
        "B": {DESIGNS[0]: ("green", "red"), DESIGNS[1]: ("yellow", "red")},  # apartment only
        "C": {DESIGNS[0]: ("red", "green"), DESIGNS[1]: ("red", "red")},  # townhomes only
        "D": {DESIGNS[0]: ("red", "yellow"), DESIGNS[1]: ("unknown", None)},  # neither
        "E": {DESIGNS[0]: ("green", "green")},  # only one design recorded
        "F": {DESIGNS[0]: None, DESIGNS[1]: None},  # no forms: matches nothing
    }
    for i, (name, per_design) in enumerate(plan.items()):
        lot = FlatsLot(
            tlid=f"WA-{name}", county="multnomah", jurisdiction="or/multnomah/portland", zone_raw="R5", zone="R5",
            site_address=f"{name} WORKS AS ST", area_sqft=5000, geom=_box(7_800_000 + i * 100, 680_000, 50, 100),
            centroid="SRID=4326;POINT(-122.5 45.5)", condo_verdict="land", facts={"source": "quadfit"},
            first_seen_run_id=run.id, updated_run_id=run.id, snapshot_id=run.snapshot_id,
        )
        session.add(lot)
        await session.flush()
        for key, pair in per_design.items():
            checks = _checks("yellow") if pair is None else _forms(*pair)
            session.add(
                FlatsLotResult(lot_id=lot.id, design_key=key, run_id=run.id, tier="unknown",
                               slack_ft=1, binding=[], checks=checks)
            )
    await session.commit()

    assert (await session.execute(select(FlatsLotWorksAs))).first() is None
    await _fill(session, run.id)
    written = (await session.execute(select(FlatsLotWorksAs))).scalars().all()
    assert len(written) == sum(1 for d in plan.values() for p in d.values() if p is not None)

    for design in (None, *DESIGNS):
        for form in _FORM_CHOICES:
            old = await _lots(session, run.id, design, form, stored=False)
            new = await _lots(session, run.id, design, form, stored=True)
            assert new == old, (design, form)

    names = {r[0]: r[1] for r in (await session.execute(select(FlatsLot.id, FlatsLot.tlid))).all()}

    async def tlids(form: str) -> set[str]:
        return {names[i] for i in await _lots(session, run.id, None, form, stored=True)}

    assert await tlids("both") == {"WA-A", "WA-E"}
    assert await tlids("apartment") == {"WA-B"}
    assert await tlids("townhomes") == {"WA-C"}
    assert await tlids("neither") == {"WA-D"}


async def test_a_run_with_no_table_rows_still_answers_from_the_json(session: AsyncSession):
    run = await _seed(session)
    result = (await session.execute(select(FlatsLotResult).limit(1))).scalars().first()
    result.checks = _forms("green", "green")
    lot_id = result.lot_id
    await session.commit()
    assert (await session.execute(select(FlatsLotWorksAs))).first() is None
    assert await _lots(session, run.id, None, "both", stored=False) == {lot_id}
