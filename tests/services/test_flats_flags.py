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
from flats.score import flags as fp
from flats.score import margins as mg

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


# ---------------------------------------------------------------------------
# Item 5: work queue, nightly check, design sensitivity
# ---------------------------------------------------------------------------

FIT = {"check": "fit_ft", "observed": 55.5, "threshold": 56.0, "shortfall": 0.5}
FIT_FAR = {"check": "fit_ft", "observed": 50.0, "threshold": 56.0, "shortfall": 6.0}


async def _slack(session: AsyncSession, run_id: int, tlid: str, slack: float) -> None:
    row = (
        await session.execute(
            select(FlatsLotResult).join(FlatsLot, FlatsLot.id == FlatsLotResult.lot_id)
            .where(FlatsLotResult.run_id == run_id, FlatsLot.tlid == tlid)
        )
    ).scalar_one()
    row.slack_ft = slack
    await session.flush()


async def test_the_work_queue_puts_the_key_that_turns_lots_green_alone_first(session: AsyncSession) -> None:
    w = await _world(session)
    # A is held yellow by the corner alone; B by the corner and the through
    # lot together. Both kinds share a priority, so yield decides: the corner
    # turns A green on its own, the through lot turns nothing green alone.
    await _run(session, w, 1, {A: ("yellow", [CORNER]), B: ("yellow", [CORNER, THROUGH | {"severity": 5}])})
    await flats_flags.sync_instances(session)

    reg = fp.registry()
    same = fp.Registry(
        [t.model_copy(update={"priority": fp.Priority.now}) if t.code in (CORNER["code"], THROUGH["code"]) else t
         for t in reg]
    )
    queue = await flats_flags.work_queue(session, reg=same)
    first, second = [r for r in queue if r["code"] in (CORNER["code"], THROUGH["code"])]
    assert first["code"] == CORNER["code"] and (first["lots"], first["held"], first["last"]) == (2, 2, 1)
    assert second["code"] == THROUGH["code"] and (second["held"], second["last"]) == (1, 0)
    assert first["key"] == "or/multnomah/x · corner_lot"


async def test_the_work_queue_keeps_one_row_for_a_per_lot_kind(session: AsyncSession) -> None:
    w = await _world(session)
    await _run(session, w, 1, {A: ("yellow", [tight(A)]), B: ("yellow", [tight(B)])})
    await flats_flags.sync_instances(session)

    (row,) = [r for r in await flats_flags.work_queue(session) if r["code"] == "FIT-TIGHT"]
    assert row["key"] == "" and row["lots"] == 2


async def test_the_untrusted_flags_are_the_ones_the_screen_raises() -> None:
    from flats.score import screen

    assert set(screen._VERDICT_FLAG.values()) | {"RULE-AMBIGUOUS"} == flats_flags.UNTRUSTED_FLAGS


async def test_a_wider_pod_moves_the_fit_and_a_narrower_one_clears_it() -> None:
    fit = fp.Bind.from_json(FIT)
    # Short by half a foot: a foot narrower clears it; a foot wider is 1.5.
    assert flats_flags.widened([fit], [], -0.5, -1) == []
    (wider,) = flats_flags.widened([fit], [], -0.5, 1)
    assert (wider.shortfall, wider.threshold) == (1.5, 57.0)
    # A lot with 1.5 ft to spare gains a bind only past 1.5 ft.
    assert flats_flags.widened([], [], 1.5, 1) == []
    (gained,) = flats_flags.widened([], [], 1.5, 2)
    assert gained.check == "fit_ft" and gained.shortfall == 0.5
    # Under a rule set the screen does not trust, no bind is invented.
    untrusted = [fp.Flag("RULE-AMBIGUOUS", "or/multnomah/x|R5|coverage_pct", "RULE_AMBIGUOUS")]
    assert flats_flags.widened([], untrusted, 1.5, 4) == []


async def test_the_nightly_check_passes_when_every_stored_colour_is_todays(session: AsyncSession) -> None:
    w = await _world(session)
    await _run(session, w, 1, {A: ("yellow", [CORNER]), B: ("green", [])})
    await flats_flags.sync_instances(session)

    got = await flats_flags.nightly_check(session)

    assert got.ok and got.run_id == 1
    r = got.report
    assert r["rows"] == 2 and r["moved"] == {} and r["incomplete"] == {}
    assert r["colours"] == {DESIGN: {"yellow": 1, "green": 1}}
    assert r["kinds"] == len(fp.registry())
    assert await flats_flags.latest_report(session) is got


async def test_the_nightly_check_fails_on_a_stored_colour_that_is_not_todays(session: AsyncSession) -> None:
    w = await _world(session)
    # Stored green, but a corner-lot flag holds it yellow under the rule.
    await _run(session, w, 1, {A: ("green", [CORNER]), B: ("yellow", [{"code": "FACT-NOPE", "key": "x", "by": "?"}])})

    got = await flats_flags.nightly_check(session)

    assert not got.ok
    assert got.report["moved"] == {"green->yellow": 1}
    assert got.report["moved_examples"][0]["tlid"] == A
    assert sum(got.report["incomplete"].values()) == 1
    assert got.report["incomplete_examples"][0]["tlid"] == B


async def test_the_nightly_check_says_why_a_run_before_the_rule_has_nothing(session: AsyncSession) -> None:
    w = await _world(session)
    await _run(session, w, 1, {A: ("yellow", [])}, ruled=False)

    got = await flats_flags.nightly_check(session)

    assert not got.ok and got.report["rows"] == 0
    assert got.report["skipped"].startswith("run 1 was screened before the colour rule")


async def test_the_sensitivity_report_counts_what_each_size_moves(session: AsyncSession) -> None:
    w = await _world(session)
    # A misses the fit by half a foot (a near miss: yellow); B fits with
    # 1.5 ft to spare and carries the corner question. Both were screened
    # before the room each way was kept, broadside: the fit ran along the
    # pod's depth.
    await _run(session, w, 1, {A: ("yellow", []), B: ("yellow", [CORNER])})
    row = (
        await session.execute(
            select(FlatsLotResult).join(FlatsLot, FlatsLot.id == FlatsLotResult.lot_id).where(FlatsLot.tlid == A)
        )
    ).scalar_one()
    row.checks = {**row.checks, "binds": [FIT]}
    await _slack(session, 1, A, -0.5)
    await _slack(session, 1, B, 1.5)

    got = await flats_flags.nightly_check(session)

    r = got.report
    for side in ("depth", "both"):
        sens = r[side][DESIGN]
        # A foot shallower: A fits and, with nothing open, is green.
        assert sens["-1"]["moves"] == {"yellow->green": 1}
        # A foot deeper: A is short by 1.5 ft and goes red; B still fits.
        assert sens["1"]["moves"] == {"yellow->red": 1}
        assert sens["1"]["examples"][0]["tlid"] == A
        # Two feet deeper: B is short by half a foot -- a near miss, still yellow.
        assert sens["2"]["moves"] == {"yellow->red": 1}
        # Four feet deeper: B misses too, and the question it carries is named.
        assert sens["4"]["moves"] == {"yellow->red": 2}
        assert sens["4"]["keys"] == {"FACT-CORNER-LOT|or/multnomah/x|corner_lot": 1}
    # The width runs along the street, which such a run never measured: the
    # fit reads as it was, so nothing moves.
    assert r["sensitivity"][DESIGN] == {}
    assert r["sized"] == {}
    assert got.ok


async def test_a_size_reads_the_room_kept_that_way_or_the_fit_where_it_ran() -> None:
    room = {"width": 1.5, "depth": 6.0, "both": 0.5}
    # Kept on the lot's own shape: each side its own room.
    assert flats_flags.size_reading("width", room, "width_facing", 9.0) == (1.5, False)
    assert flats_flags.size_reading("depth", room, "width_facing", 9.0) == (6.0, True)
    assert flats_flags.size_reading("both", room, "width_facing", 9.0) == (0.5, True)
    # Before it was kept: the fit's own room, for the side that ran along
    # the lot -- the depth broadside, the width end-on -- and both ways.
    assert flats_flags.size_reading("depth", None, "width_facing", 9.0) == (9.0, True)
    assert flats_flags.size_reading("width", None, "width_facing", 9.0) == (None, False)
    assert flats_flags.size_reading("width", None, "depth_facing", 9.0) == (9.0, True)
    assert flats_flags.size_reading("depth", None, "depth_facing", 9.0) == (None, False)
    assert flats_flags.size_reading("both", None, None, 9.0) == (9.0, True)


async def test_a_fit_miss_moves_only_with_the_side_the_fit_ran_along() -> None:
    fit = fp.Bind.from_json(FIT)
    # Grown across the run, the search was never made at the new size: the
    # miss is left as it was, neither cleared nor deepened.
    assert flats_flags.widened([fit], [], None, -1, along=False) == [fit]
    assert flats_flags.widened([fit], [], None, 4, along=False) == [fit]
    # And a lot with no room that way gains no fit bind.
    assert flats_flags.widened([], [], None, 4, along=False) == []


async def test_the_report_reads_each_side_off_the_room_kept_on_the_lots_shape(session: AsyncSession) -> None:
    w = await _world(session)
    # A is green, broadside, with room to grow 1.5 ft wider and 6 ft deeper
    # but only half a foot both ways at once: a tight shape. B is green from
    # a run before the room each way was kept, with 10 ft of fit to spare.
    await _run(session, w, 1, {A: ("green", []), B: ("green", [])})
    row = (
        await session.execute(
            select(FlatsLotResult).join(FlatsLot, FlatsLot.id == FlatsLotResult.lot_id).where(FlatsLot.tlid == A)
        )
    ).scalar_one()
    row.checks = {
        **row.checks,
        "fit": {"orientation": "width_facing", "room": {"width": 1.5, "depth": 6.0, "both": 0.5}},
    }
    await _slack(session, 1, A, 6.0)
    await _slack(session, 1, B, 10.0)

    got = await flats_flags.nightly_check(session)

    r = got.report
    assert r["sized"] == {DESIGN: 1}
    wide, deep, both = (r[k][DESIGN] for k in ("sensitivity", "depth", "both"))
    # Two feet wider: short by half a foot, a near miss; four, red.
    assert "1" not in wide
    assert wide["2"]["moves"] == {"green->yellow": 1} and wide["2"]["examples"][0]["tlid"] == A
    assert wide["4"]["moves"] == {"green->red": 1} and wide["4"]["limits"] == {"fit_ft": 1}
    # Four feet deeper still fits; B's 10 ft covers every step.
    assert deep == {}
    # A foot both ways is already half a foot over.
    assert both["1"]["moves"] == {"green->yellow": 1}
    assert both["2"]["moves"] == {"green->red": 1}
    # The summary: one lot measured, and its shape is tight.
    assert r["room"][DESIGN]["size"] == {
        "lots": 1,
        "width": {"median": 1.5, "under_2": 1},
        "depth": {"median": 6.0, "under_2": 0},
        "both": {"median": 0.5, "under_2": 1},
        "tight": 1,
    }
    assert got.ok


# ---------------------------------------------------------------------------
# FOLLOWUPS 37(ii): the room each pass had to spare
# ---------------------------------------------------------------------------

# The test pod is 56 x 36: a foot wider adds 36 sqft to a 2,016 sqft
# footprint, on a 5,000 sqft lot.
GROUND = 56 * 36


def _room(**checks: tuple[float, float, float]) -> dict:
    return {k: list(v) for k, v in checks.items()}


async def test_a_bigger_pod_is_charged_on_coverage_from_the_room_the_lot_had() -> None:
    margins = mg.loads(_room(coverage_pct=(30.0, 31.0, 1.0)))
    one = mg.Change(extra_sqft=36.0, ground_sqft=GROUND, lot_sqft=5000.0)
    four = mg.Change(extra_sqft=144.0, ground_sqft=GROUND, lot_sqft=5000.0)
    # A foot more: 30 % grows to 30.5 %, still under the 31 % cap.
    assert flats_flags.widened([], [], 10.0, 1, margins=margins, change=one) == []
    # Four feet more: 32.1 %, over the cap -- a coverage bind, not a fit one.
    (cov,) = flats_flags.widened([], [], 10.0, 4, margins=margins, change=four)
    assert cov.check == "coverage_pct" and cov.threshold == 31.0
    assert cov.shortfall == pytest.approx(30.0 * (GROUND + 144) / GROUND - 31.0)
    # Under a rule set the screen does not trust, no bind is invented.
    untrusted = [fp.Flag("RULE-AMBIGUOUS", "or/multnomah/x|R5|coverage_pct", "RULE_AMBIGUOUS")]
    assert flats_flags.widened([], untrusted, 10.0, 4, margins=margins, change=four) == []
    # Without the room (a run before the bridge kept it) only the fit reads.
    assert flats_flags.widened([], [], 10.0, 4, margins={}, change=four) == []


async def test_a_smaller_pod_clears_a_coverage_miss_and_leaves_the_rest() -> None:
    cov = fp.Bind("coverage_pct", 41.0, 40.0, 1.0)
    use = fp.Bind("use", None, None, None)
    smaller = mg.Change(extra_sqft=-144.0, ground_sqft=GROUND, lot_sqft=5000.0)
    assert flats_flags.widened([cov, use], [], 10.0, -4, margins={}, change=smaller) == [use]


async def test_a_taller_pod_moves_the_height_limit_and_a_lower_one_the_minimum() -> None:
    room = mg.loads(_room(height_ft=(27.0, 28.0, 1.0), min_height_ft=(26.0, 25.0, 1.0)))
    assert flats_flags.heightened([], [], room, 1) == []
    (tall,) = flats_flags.heightened([], [], room, 2)
    assert (tall.check, tall.observed, tall.shortfall) == ("height_ft", 29.0, 1.0)
    (low,) = flats_flags.heightened([], [], room, -2)
    assert (low.check, low.observed, low.shortfall) == ("min_height_ft", 24.0, 1.0)
    # A lower pod clears a height miss; coverage is not a height.
    over = fp.Bind("height_ft", 30.0, 28.0, 2.0)
    cov = fp.Bind("coverage_pct", 41.0, 40.0, 1.0)
    assert flats_flags.heightened([over, cov], [], {}, -2) == [cov]


async def test_the_report_counts_the_limits_a_bigger_or_taller_pod_crosses(session: AsyncSession) -> None:
    w = await _world(session)
    # Both lots green with ten feet of fit to spare. A kept the room on
    # each standard it passed; B was screened before the room was kept.
    await _run(session, w, 1, {A: ("green", []), B: ("green", [])})
    row = (
        await session.execute(
            select(FlatsLotResult).join(FlatsLot, FlatsLot.id == FlatsLotResult.lot_id).where(FlatsLot.tlid == A)
        )
    ).scalar_one()
    row.checks = {
        **row.checks,
        "fit": {"required_ft": 56.0},
        "margins": _room(coverage_pct=(30.0, 31.0, 1.0), height_ft=(27.0, 28.0, 1.0), far=(0.5, 1.0, 0.5)),
    }
    await _slack(session, 1, A, 10.0)
    await _slack(session, 1, B, 10.0)

    got = await flats_flags.nightly_check(session)

    assert got.ok
    r = got.report
    assert r["height_steps"] == list(flats_flags.HEIGHT_STEPS)
    sens, tall = r["sensitivity"][DESIGN], r["height"][DESIGN]
    # A foot wider keeps coverage under the cap; two feet wider crosses it.
    assert "1" not in sens
    assert sens["2"]["moves"] == {"green->red": 1} and sens["2"]["limits"] == {"coverage_pct": 1}
    assert sens["2"]["examples"][0]["tlid"] == A
    # A foot taller lands on the limit (a pass); two feet over it.
    assert "1" not in tall
    assert tall["2"]["moves"] == {"green->red": 1} and tall["2"]["limits"] == {"height_ft": 1}
    # Nothing narrower or lower moves a green lot.
    assert not any(k.startswith("-") for k in (*sens, *tall))
    # The room: two green lots, one measured; coverage came within 5 % of
    # its cap, floor area kept half its limit.
    room = r["room"][DESIGN]
    assert (room["green"], room["measured"]) == (2, 1)
    assert room["checks"]["coverage_pct"] == {"lots": 1, "median": 1.0, "within_10": 1, "within_5": 1}
    assert room["checks"]["far"] == {"lots": 1, "median": 0.5, "within_10": 0, "within_5": 0}
