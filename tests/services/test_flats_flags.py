"""Flag history and the review queue (``app.services.flats_flags``, FOLLOWUPS 37 item 4).

Steph's flag plan: "Cleared flags are kept, not deleted; their history shows
which checks rarely block", and a question an agent cannot answer alone waits
in a queue for the next review session. What is held here is the row-level
contract: a sync opens what the run in use raises and clears what it stopped
raising, naming the run and what the lot became; it is idempotent; it refuses
a run that never looked (screened before the colour rule) or one nobody
shows; a flag that comes back opens a new row. A question names a registered
type and a key that fills it, is not asked twice while waiting, and is
answered once.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import (
    FlatsDesign,
    FlatsFlagInstance,
    FlatsLot,
    FlatsLotResult,
    FlatsRun,
    FlatsSnapshot,
)
from app.services import flats_flags
from app.services.flats_flags import FlagWriteError

pytestmark = pytest.mark.asyncio

DESIGN = "pod56x36@2"
A = "1S2E08BA  -09500"
B = "1N1E29DD  -05600"
CORNER = {"code": "FACT-CORNER-LOT", "key": "or/multnomah/x|corner_lot", "by": "FACT_UNOBSERVED", "source": "unobserved"}
THROUGH = {"code": "FACT-THROUGH-LOT", "key": "or/multnomah/x|through_lot", "by": "FACT_UNOBSERVED"}


def tight(tlid: str) -> dict:
    return {"code": "FIT-TIGHT", "key": f"{tlid}|{DESIGN}", "by": "TIGHT_FIT", "bounds": [-0.5, 0.5]}


async def _world(session: AsyncSession) -> dict:
    snap = FlatsSnapshot(snapshot_date=dt.date(2026, 10, 1), host="137", status="current", manifest={}, counts={})
    session.add(snap)
    session.add(
        FlatsDesign(
            key=DESIGN, design_id="pod56x36", version=2, label="pod", typology="pod",
            width_ft=56, depth_ft=36, units=4, stories=2, height_ft=28,
        )
    )
    await session.flush()
    lots = {
        t: FlatsLot(tlid=t, county="multnomah", jurisdiction="or/multnomah/x", zone="R5", area_sqft=5000,
                    facts={}, snapshot_id=snap.id)
        for t in (A, B)
    }
    session.add_all(lots.values())
    await session.flush()
    return {"snap": snap, "lots": lots}


async def _run(session: AsyncSession, w: dict, run_id: int, rows: dict[str, tuple[str, list[dict]] | None],
               *, status: str = "complete", ruled: bool = True) -> FlatsRun:
    run = FlatsRun(id=run_id, status=status, snapshot_id=w["snap"].id, design_keys=[DESIGN], counties=["multnomah"])
    session.add(run)
    await session.flush()
    for tlid, got in rows.items():
        if got is None:
            continue
        colour, flags = got
        checks: dict = {"verdict": "unknown", "if_signed": colour}
        if ruled:
            checks |= {"colour": colour, "flags": flags, "binds": []}
        session.add(FlatsLotResult(lot_id=w["lots"][tlid].id, design_key=DESIGN, run_id=run.id, tier="review",
                                   binding=[], checks=checks))
    await session.flush()
    return run


async def _rows(session: AsyncSession) -> list[FlatsFlagInstance]:
    return list((await session.execute(select(FlatsFlagInstance).order_by(FlatsFlagInstance.id))).scalars())


async def test_a_sync_opens_what_the_run_in_use_raises_and_is_idempotent(session: AsyncSession) -> None:
    w = await _world(session)
    await _run(session, w, 1, {A: ("yellow", [CORNER, tight(A)]), B: ("yellow", [CORNER])})

    got = await flats_flags.sync_instances(session)
    assert (got.run_id, got.opened, got.updated, got.cleared) == (1, 3, 0, 0)
    rows = await _rows(session)
    assert {(r.tlid, r.code) for r in rows} == {(A, "FACT-CORNER-LOT"), (A, "FIT-TIGHT"), (B, "FACT-CORNER-LOT")}
    fit = next(r for r in rows if r.code == "FIT-TIGHT")
    assert (float(fit.bounds_low), float(fit.bounds_high)) == (-0.5, 0.5)
    assert all(r.status == "open" and r.opened_run_id == 1 and r.colour == "yellow" for r in rows)

    again = await flats_flags.sync_instances(session)
    assert (again.opened, again.updated, again.cleared) == (0, 0, 0)


async def test_a_flag_the_next_run_stops_raising_is_cleared_and_kept(session: AsyncSession) -> None:
    w = await _world(session)
    await _run(session, w, 1, {A: ("yellow", [CORNER, tight(A)]), B: ("yellow", [CORNER])})
    await flats_flags.sync_instances(session)
    # Run 2 measured the corner: A clears it and is green; B lost its lot row.
    await _run(session, w, 2, {A: ("green", [tight(A)]), B: None})

    got = await flats_flags.sync_instances(session)
    assert (got.run_id, got.opened, got.updated, got.cleared) == (2, 0, 1, 2)
    rows = {(r.tlid, r.code): r for r in await _rows(session)}
    a = rows[(A, "FACT-CORNER-LOT")]
    assert a.status == "cleared" and a.cleared_run_id == 2
    assert a.resolution_note == "run 2 no longer raises it; the lot is green"
    assert rows[(B, "FACT-CORNER-LOT")].resolution_note == "run 2 did not screen this lot with this design"
    still = rows[(A, "FIT-TIGHT")]
    assert still.status == "open" and still.opened_run_id == 1 and still.last_seen_run_id == 2
    assert still.colour == "green"


async def test_a_flag_that_comes_back_opens_a_new_row(session: AsyncSession) -> None:
    w = await _world(session)
    await _run(session, w, 1, {A: ("yellow", [CORNER])})
    await flats_flags.sync_instances(session)
    await _run(session, w, 2, {A: ("green", [])})
    await flats_flags.sync_instances(session)
    await _run(session, w, 3, {A: ("yellow", [CORNER])})

    got = await flats_flags.sync_instances(session)
    assert got.opened == 1
    rows = [r for r in await _rows(session) if r.code == "FACT-CORNER-LOT"]
    assert [(r.status, r.opened_run_id, r.cleared_run_id) for r in rows] == [("cleared", 1, 2), ("open", 3, None)]


async def test_a_lowered_severity_rides_into_the_open_row(session: AsyncSession) -> None:
    w = await _world(session)
    await _run(session, w, 1, {A: ("yellow", [THROUGH])})
    await flats_flags.sync_instances(session)
    await _run(session, w, 2, {A: ("green", [{**THROUGH, "severity": 0}])})

    got = await flats_flags.sync_instances(session)
    assert (got.opened, got.updated, got.cleared) == (0, 1, 0)
    (row,) = await _rows(session)
    assert (row.severity, row.colour, row.opened_run_id) == (0, "green", 1)


async def test_a_run_that_never_looked_or_nobody_shows_is_refused(session: AsyncSession) -> None:
    w = await _world(session)
    await _run(session, w, 1, {A: ("yellow", [CORNER])})
    await flats_flags.sync_instances(session)
    # A run from before the colour rule: no flags anywhere, nothing cleared.
    await _run(session, w, 2, {A: ("yellow", [])}, ruled=False)
    old = await flats_flags.sync_instances(session)
    assert old.skipped.startswith("run 2 was screened before the colour rule")
    # A candidate is nobody's default yet.
    await _run(session, w, 3, {A: ("green", [])}, status="candidate")
    waiting = await flats_flags.sync_instances(session, 3)
    assert waiting.skipped == "run 3 is candidate; only the run in use is synced"
    assert [r.status for r in await _rows(session)] == ["open"]


async def test_open_counts_are_lots_by_colour(session: AsyncSession) -> None:
    w = await _world(session)
    await _run(session, w, 1, {A: ("yellow", [CORNER, tight(A)]), B: ("red", [CORNER])})
    await flats_flags.sync_instances(session)
    counts = await flats_flags.open_counts(session)
    assert counts == {"FACT-CORNER-LOT": {"yellow": 1, "red": 1}, "FIT-TIGHT": {"yellow": 1}}


async def test_a_question_names_a_registered_type_and_a_key_that_fills_it(session: AsyncSession) -> None:
    with pytest.raises(FlagWriteError, match="not a registered flag type"):
        await flats_flags.ask(session, code="FACT-NOPE", key="x|y", question="Is this a real kind?", by="agent")
    with pytest.raises(FlagWriteError, match="does not fill"):
        await flats_flags.ask(session, code="FACT-CORNER-LOT", key="or/multnomah/x", question="Which corner?", by="agent")
    with pytest.raises(FlagWriteError, match="at least a sentence"):
        await flats_flags.ask(session, code="FACT-CORNER-LOT", key=CORNER["key"], question="?", by="agent")


async def test_a_waiting_question_is_not_asked_twice_and_is_answered_once(session: AsyncSession) -> None:
    w = await _world(session)
    await _run(session, w, 1, {A: ("yellow", [CORNER]), B: ("red", [CORNER])})
    await flats_flags.sync_instances(session)
    q = await flats_flags.ask(
        session, code="FACT-CORNER-LOT", key=CORNER["key"],
        question="Does the city count a lot on a curve as a corner?", by="agent session 2026-10-04",
    )
    with pytest.raises(FlagWriteError, match="still waiting"):
        await flats_flags.ask(session, code="FACT-CORNER-LOT", key=CORNER["key"],
                              question="Same question again, worded differently.", by="agent")
    (waiting,) = await flats_flags.questions(session, answered=False)
    assert waiting["row"].id == q.id and waiting["lots"] == {"yellow": 1, "red": 1}

    await flats_flags.answer(session, q.id, text_="Only where the curve turns 45 degrees or more.", by="Steph")
    assert await flats_flags.questions(session, answered=False) == []
    (done,) = await flats_flags.questions(session, answered=True)
    assert done["row"].answered_by == "Steph"
    with pytest.raises(FlagWriteError, match="was answered by Steph"):
        await flats_flags.answer(session, q.id, text_="again", by="Steph")
    # Answered, the key may be asked about again.
    await flats_flags.ask(session, code="FACT-CORNER-LOT", key=CORNER["key"],
                          question="And a lot on a cul-de-sac bulb?", by="agent")
