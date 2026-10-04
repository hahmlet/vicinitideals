"""Flag history and the review queue (FOLLOWUPS 37 item 4).

Steph's flag plan keeps two records the run itself cannot: a flag instance
per lot that says when it opened and when it cleared -- *"cleared flags are
kept, not deleted; their history shows which checks rarely block"* -- and a
queue of questions an agent could not answer alone, put to a person for the
next review session.

The screen raises flags and the run carries them
(``lot_results.checks -> 'flags'``); runs are pruned, so the history lives in
``flats.flag_instances``, written here and nowhere else:

* :func:`sync_instances` -- the run in use against the open rows: a flag the
  run raises that no open row holds opens one, an open row it no longer
  raises is cleared with the run and what the lot became. Idempotent, so the
  nightly task runs it whether or not anything was promoted, and a rollback
  is followed the same way as a promotion.
* :func:`ask` / :func:`answer` -- the one write path into
  ``flats.flag_questions``: a question must name a registered flag type and
  a key that fills its parts. An answer is a note for whoever encodes the
  confirmed value; the flag closes when the screen, reading that value, stops
  raising it.
* :func:`work_queue` -- open resolution keys by priority, then yield (item 5).
* :func:`nightly_check` -- every ruled row recoloured under today's rule set,
  incomplete flags, and the design sensitivity report, as one
  ``flats.flag_reports`` row (item 5).
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import FlatsFlagInstance, FlatsFlagQuestion, FlatsFlagReport, FlatsRun
from app.services.flats_refresh import current_snapshot, run_in_use
from flats.score import flags as fp


class FlagWriteError(ValueError):
    """A write the flag plan's schema refuses."""


@dataclass(frozen=True)
class Synced:
    run_id: int | None
    opened: int = 0
    updated: int = 0
    cleared: int = 0
    #: Why nothing was synced, when nothing was.
    skipped: str = ""


_NOW = text(
    """
    CREATE TEMP TABLE _flag_now AS
    SELECT l.county, l.tlid, r.design_key,
           f->>'code' AS code,
           f->>'key' AS key,
           COALESCE(f->>'by', '') AS raised_by,
           (f->'bounds'->>0)::numeric AS bounds_low,
           (f->'bounds'->>1)::numeric AS bounds_high,
           COALESCE(f->>'source', '') AS source,
           (f->>'severity')::int AS severity,
           r.checks->>'colour' AS colour
    FROM flats.lot_results r
    JOIN flats.lots l ON l.id = r.lot_id
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(r.checks->'flags', '[]'::jsonb)) f
    WHERE r.run_id = :run AND r.checks ? 'colour'
    """
)

_CLEAR = text(
    """
    WITH gone AS (
        SELECT i.id,
               (SELECT r.checks->>'colour'
                  FROM flats.lot_results r JOIN flats.lots l ON l.id = r.lot_id
                 WHERE r.run_id = :run AND l.county = i.county AND l.tlid = i.tlid
                   AND r.design_key = i.design_key
                 LIMIT 1) AS colour
          FROM flats.flag_instances i
         WHERE i.status = 'open' AND i.design_key = ANY(:designs)
           AND NOT EXISTS (
               SELECT 1 FROM _flag_now n
                WHERE n.county = i.county AND n.tlid = i.tlid AND n.design_key = i.design_key
                  AND n.code = i.code AND n.key = i.key)
    )
    UPDATE flats.flag_instances i
       SET status = 'cleared', cleared_run_id = :run, cleared_at = :now,
           resolution_note = CASE
               WHEN gone.colour IS NULL THEN :said || ' did not screen this lot with this design'
               ELSE :said || ' no longer raises it; the lot is ' || gone.colour
           END
      FROM gone
     WHERE i.id = gone.id
    """
)

_UPDATE = text(
    """
    UPDATE flats.flag_instances i
       SET last_seen_run_id = :run, raised_by = n.raised_by, bounds_low = n.bounds_low,
           bounds_high = n.bounds_high, source = n.source, severity = n.severity, colour = n.colour
      FROM _flag_now n
     WHERE i.status = 'open' AND n.county = i.county AND n.tlid = i.tlid
       AND n.design_key = i.design_key AND n.code = i.code AND n.key = i.key
       AND (i.last_seen_run_id IS DISTINCT FROM :run
            OR i.severity IS DISTINCT FROM n.severity OR i.colour IS DISTINCT FROM n.colour)
    """
)

_OPEN = text(
    """
    INSERT INTO flats.flag_instances
        (county, tlid, design_key, code, key, raised_by, bounds_low, bounds_high, source,
         severity, colour, status, opened_run_id, opened_at, last_seen_run_id)
    SELECT n.county, n.tlid, n.design_key, n.code, n.key, n.raised_by, n.bounds_low, n.bounds_high,
           n.source, n.severity, n.colour, 'open', :run, :now, :run
      FROM _flag_now n
     WHERE NOT EXISTS (
           SELECT 1 FROM flats.flag_instances i
            WHERE i.status = 'open' AND i.county = n.county AND i.tlid = n.tlid
              AND i.design_key = n.design_key AND i.code = n.code AND i.key = n.key)
    """
)


async def sync_instances(
    session: AsyncSession, run_id: int | None = None, *, now: dt.datetime | None = None
) -> Synced:
    """Bring ``flats.flag_instances`` in line with a run; flushed, not committed.

    The run defaults to the one in use on the copy in use. A run screened
    before the colour rule carries no flags and is refused -- syncing it
    would clear every open flag on a run that never looked. A run that is not
    complete (a candidate, a retired one) is refused too: the history follows
    what the Lots pages show.
    """
    now = now or dt.datetime.now(dt.UTC)
    if run_id is None:
        snapshot = await current_snapshot(session)
        run = await run_in_use(session, snapshot.id if snapshot is not None else None)
        if run is None:
            return Synced(None, skipped="no run in use")
    else:
        run = await session.get(FlatsRun, run_id)
        if run is None:
            raise FlagWriteError(f"no run {run_id}")
    if run.status != "complete":
        return Synced(run.id, skipped=f"run {run.id} is {run.status}; only the run in use is synced")
    ruled = (
        await session.execute(
            text("SELECT bool_or(checks ? 'colour') FROM (SELECT checks FROM flats.lot_results WHERE run_id = :run LIMIT 200) s"),
            {"run": run.id},
        )
    ).scalar()
    if not ruled:
        return Synced(run.id, skipped=f"run {run.id} was screened before the colour rule and carries no flags")
    await session.execute(text("DROP TABLE IF EXISTS _flag_now"))
    await session.execute(_NOW, {"run": run.id})
    await session.execute(
        text("CREATE INDEX ON _flag_now (county, tlid, design_key, code, key)")
    )
    await session.execute(text("ANALYZE _flag_now"))
    designs = list(run.design_keys or [])
    if not designs:
        designs = list(
            (await session.execute(text("SELECT DISTINCT design_key FROM _flag_now"))).scalars()
        )
    cleared = (await session.execute(_CLEAR, {"run": run.id, "now": now, "designs": designs, "said": f"run {run.id}"})).rowcount
    updated = (await session.execute(_UPDATE, {"run": run.id})).rowcount
    opened = (await session.execute(_OPEN, {"run": run.id, "now": now})).rowcount
    await session.execute(text("DROP TABLE IF EXISTS _flag_now"))
    await session.flush()
    return Synced(run.id, opened=int(opened or 0), updated=int(updated or 0), cleared=int(cleared or 0))


def _checked_key(code: str, key: str, reg: fp.Registry) -> fp.FlagType:
    if code not in reg:
        raise FlagWriteError(f"{code} is not a registered flag type")
    t = reg[code]
    parts = key.split(fp.SEP) if key else []
    if len(parts) != len(t.key) or not all(p.strip() for p in parts):
        raise FlagWriteError(f"{code}: key {key!r} does not fill {'/'.join(t.key)}")
    return t


async def ask(
    session: AsyncSession,
    *,
    code: str,
    key: str,
    question: str,
    by: str,
    reg: fp.Registry | None = None,
) -> FlatsFlagQuestion:
    """Put a question on one flag's resolution key to the next review
    session; flushed, not committed. The type must be registered and the key
    must fill its parts; a key already waiting on an answer is not asked
    twice."""
    reg = reg or fp.registry()
    _checked_key(code, key, reg)
    question = (question or "").strip()
    if len(question) < 10:
        raise FlagWriteError("say what the question is (at least a sentence)")
    if not (by or "").strip():
        raise FlagWriteError("say who is asking")
    waiting = (
        await session.execute(
            select(FlatsFlagQuestion.id).where(
                FlatsFlagQuestion.code == code,
                FlatsFlagQuestion.key == key,
                FlatsFlagQuestion.answered_at.is_(None),
            )
        )
    ).scalar()
    if waiting is not None:
        raise FlagWriteError(f"question {waiting} on {code} {key} is still waiting for an answer")
    row = FlatsFlagQuestion(code=code, key=key, question=question[:4000], asked_by=by.strip()[:200])
    session.add(row)
    await session.flush()
    return row


async def answer(
    session: AsyncSession,
    question_id: int,
    *,
    text_: str,
    by: str,
    user_id: uuid.UUID | None = None,
    now: dt.datetime | None = None,
) -> FlatsFlagQuestion:
    """A person's answer to a waiting question; flushed, not committed."""
    row = await session.get(FlatsFlagQuestion, question_id)
    if row is None:
        raise FlagWriteError(f"no question {question_id}")
    if row.answered_at is not None:
        raise FlagWriteError(f"question {question_id} was answered by {row.answered_by}")
    said = (text_ or "").strip()
    if not said:
        raise FlagWriteError("write the answer")
    row.answer = said[:8000]
    row.answered_by = (by or "").strip()[:200] or "unknown"
    row.answered_user_id = user_id
    row.answered_at = now or dt.datetime.now(dt.UTC)
    session.add(row)
    await session.flush()
    return row


async def open_counts(session: AsyncSession) -> dict[str, dict[str, int]]:
    """Open flags per type, as lots, split by the lot's colour -- the
    plan's population, counted live rather than stored."""
    rows = await session.execute(
        select(
            FlatsFlagInstance.code,
            func.coalesce(FlatsFlagInstance.colour, "unknown"),
            func.count(func.distinct(FlatsFlagInstance.county + "/" + FlatsFlagInstance.tlid)),
        )
        .where(FlatsFlagInstance.status == "open")
        .group_by(FlatsFlagInstance.code, FlatsFlagInstance.colour)
    )
    out: dict[str, dict[str, int]] = {}
    for code, colour, n in rows:
        out.setdefault(code, {})[colour] = int(n)
    return out


async def questions(session: AsyncSession, *, answered: bool) -> list[dict[str, Any]]:
    """The queue (waiting, oldest first) or the answered (newest first), each
    with how many lots the key holds open now and their colours."""
    q = select(FlatsFlagQuestion)
    if answered:
        q = q.where(FlatsFlagQuestion.answered_at.is_not(None)).order_by(
            FlatsFlagQuestion.answered_at.desc()
        ).limit(50)
    else:
        q = q.where(FlatsFlagQuestion.answered_at.is_(None)).order_by(FlatsFlagQuestion.asked_at)
    rows = list((await session.execute(q)).scalars())
    if not rows:
        return []
    held = await session.execute(
        select(
            FlatsFlagInstance.code,
            FlatsFlagInstance.key,
            func.coalesce(FlatsFlagInstance.colour, "unknown"),
            func.count(func.distinct(FlatsFlagInstance.county + "/" + FlatsFlagInstance.tlid)),
        )
        .where(
            FlatsFlagInstance.status == "open",
            func.concat(FlatsFlagInstance.code, " ", FlatsFlagInstance.key).in_(
                [f"{r.code} {r.key}" for r in rows]
            ),
        )
        .group_by(FlatsFlagInstance.code, FlatsFlagInstance.key, FlatsFlagInstance.colour)
    )
    lots: dict[tuple[str, str], dict[str, int]] = {}
    for code, key, colour, n in held:
        lots.setdefault((code, key), {})[colour] = int(n)
    return [{"row": r, "lots": lots.get((r.code, r.key), {})} for r in rows]


async def lot_history(session: AsyncSession, county: str, tlid: str) -> list[FlatsFlagInstance]:
    """Every flag this lot has carried since history began, newest first."""
    return list(
        (
            await session.execute(
                select(FlatsFlagInstance)
                .where(FlatsFlagInstance.county == county, FlatsFlagInstance.tlid == tlid)
                .order_by(FlatsFlagInstance.opened_at.desc(), FlatsFlagInstance.id.desc())
            )
        ).scalars()
    )


# ---------------------------------------------------------------------------
# Item 5: the work queue, the nightly check and the design sensitivity report
# ---------------------------------------------------------------------------

#: Priority order on the work queue (a person's call, stored on the type).
PRIORITY_RANK = {p.value: i for i, p in enumerate(fp.Priority)}

_QUEUE = text(
    """
    WITH kinds AS (
        SELECT * FROM unnest(CAST(:codes AS text[]), CAST(:sevs AS int[]), CAST(:per_lot AS bool[]))
            AS k(code, sev, per_lot)
    ), o AS (
        SELECT i.county, i.tlid, i.design_key, i.code,
               CASE WHEN COALESCE(k.per_lot, false) THEN '' ELSE i.key END AS key,
               COALESCE(i.colour, 'unknown') AS colour,
               COALESCE(i.severity, k.sev, 10) >= :line AS holds
          FROM flats.flag_instances i
          LEFT JOIN kinds k ON k.code = i.code
         WHERE i.status = 'open'
    ), h AS (
        SELECT county, tlid, design_key, count(*) FILTER (WHERE holds) AS n_hold
          FROM o WHERE colour = 'yellow' GROUP BY 1, 2, 3
    )
    SELECT o.code, o.key,
           count(DISTINCT (o.county, o.tlid)) AS lots,
           count(DISTINCT (o.county, o.tlid)) FILTER (WHERE o.colour = 'green') AS green,
           count(DISTINCT (o.county, o.tlid)) FILTER (WHERE o.colour = 'yellow') AS yellow,
           count(DISTINCT (o.county, o.tlid)) FILTER (WHERE o.colour = 'red') AS red,
           count(DISTINCT (o.county, o.tlid)) FILTER (WHERE o.colour = 'yellow' AND o.holds) AS held,
           count(DISTINCT (o.county, o.tlid)) FILTER (
               WHERE o.colour = 'yellow' AND o.holds AND h.n_hold = 1) AS last
      FROM o LEFT JOIN h USING (county, tlid, design_key)
     GROUP BY o.code, o.key
    """
)


async def work_queue(
    session: AsyncSession,
    *,
    reg: fp.Registry | None = None,
    rules: fp.ColourRules | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Open resolution keys sorted by priority, then yield (the flag plan's
    work queue).

    Yield is weighted toward lots where the key is the *last* thing holding
    the lot yellow: answering it turns those lots green on its own. So the
    sort is priority, then those lots, then every yellow lot it holds. A
    per-lot type is one row (each lot is its own key); a shared type is one
    row per key. Population is counted live from the open instances, as
    lots split by colour."""
    reg = reg or fp.registry()
    rules = rules or fp.colour_rules()
    types = list(reg)
    rows = await session.execute(
        _QUEUE,
        {
            "codes": [t.code for t in types],
            "sevs": [t.severity for t in types],
            "per_lot": [t.scope is fp.Scope.per_lot for t in types],
            "line": rules.yellow_at_severity,
        },
    )
    out = []
    for code, key, lots, green, yellow, red, held, last in rows:
        t = reg.types.get(code)
        out.append(
            {
                "code": code,
                "key": key.replace(fp.SEP, " · "),
                "what": t.description if t is not None else code,
                "priority": t.priority.value if t is not None else "now",
                "resolution": t.resolution.value if t is not None else "",
                "scope": t.scope.value if t is not None else "",
                "risk": t.risk.value if t is not None else "",
                "severity": t.severity if t is not None else None,
                "pending": t is not None and t.status is fp.TypeStatus.pending,
                "registered": t is not None,
                "lots": int(lots),
                "colours": {"green": int(green), "yellow": int(yellow), "red": int(red)},
                "held": int(held),
                "last": int(last),
            }
        )
    out.sort(
        key=lambda r: (
            PRIORITY_RANK.get(r["priority"], 0), -r["last"], -r["held"], -r["lots"], r["code"], r["key"]
        )
    )
    return out[:limit]


#: The flag types an untrusted rule set raises (``screen._VERDICT_FLAG`` and
#: RULE-AMBIGUOUS): the screen emits no bind under them, so a width the lot
#: misses is not a bind there either. ``tests/services`` holds this to the
#: screen.
UNTRUSTED_FLAGS = frozenset(
    {
        "RULE-AMBIGUOUS",
        "RULE-UNSIGNED",
        "ZONE-NOT-ENCODED",
        "ZONE-REFERENCE-MISSING",
        "ZONE-REFERENCE-CYCLE",
        "JURISDICTION-NOT-ENCODED",
    }
)
#: Pod width changes the sensitivity report tries, in feet.
WIDTH_STEPS = (-4, -2, -1, 1, 2, 4)
#: How many example lots each finding keeps.
EXAMPLES = 8

_ROWS = text(
    """
    SELECT l.county, l.tlid, r.design_key, r.slack_ft,
           r.checks->>'colour' AS colour, r.checks->'flags' AS flags, r.checks->'binds' AS binds
      FROM flats.lot_results r
      JOIN flats.lots l ON l.id = r.lot_id
     WHERE r.run_id = :run AND r.checks ? 'colour'
    """
)


def _json(v: Any) -> list[dict[str, Any]]:
    if v is None or v == "":
        return []
    if isinstance(v, str):
        v = json.loads(v)
    return list(v or [])


def widened(
    binds: list[fp.Bind], flags: list[fp.Flag], slack: float | None, step: float
) -> list[fp.Bind]:
    """The binds this lot would carry with a pod ``step`` feet wider
    (negative: narrower), read from the fit alone.

    The fit's bind moves by the step and goes when it no longer misses; a
    lot that fits gains a fit bind when its slack is smaller than the step.
    Under a rule set the screen does not trust it emits no bind at all, so
    none is added there. Coverage, floor area and the rest also move with
    the footprint, but their margins on lots that pass are not stored, so
    they are not counted (the report page says so)."""
    out: list[fp.Bind] = []
    fit_bound = False
    for b in binds:
        if b.check == "fit_ft" and b.shortfall is not None:
            fit_bound = True
            short = float(b.shortfall) + step
            if short > 0:
                threshold = float(b.threshold) + step if b.threshold is not None else None
                out.append(replace(b, shortfall=short, threshold=threshold))
            continue
        out.append(b)
    if (
        not fit_bound
        and slack is not None
        and slack >= 0
        and slack - step < 0
        and not any(f.code in UNTRUSTED_FLAGS for f in flags)
    ):
        out.append(fp.Bind("fit_ft", None, None, step - slack, source="the pod width"))
    return out


def _example(county: str, tlid: str, design: str, **more: Any) -> dict[str, Any]:
    return {"county": county, "tlid": tlid, "design": design, **more}


async def nightly_check(
    session: AsyncSession,
    *,
    reg: fp.Registry | None = None,
    rules: fp.ColourRules | None = None,
    steps: tuple[float, ...] = WIDTH_STEPS,
    now: dt.datetime | None = None,
) -> FlatsFlagReport:
    """The flag plan's nightly check and design sensitivity report, written
    as one ``flats.flag_reports`` row; flushed, not committed.

    Every ruled row of the run in use is recoloured from its own binds and
    flags under today's registry and rule set. A row whose colour differs
    from the one the run wrote fails the check (a rule changed since the
    run, or the screen and the rule disagree); so does a flag the write
    gate refuses, or an open instance of a kind nobody registered. Pending
    kinds are counted, never failed: there is no deadline on them (Steph
    2026-10-03). The same pass tries each pod width in ``steps`` and counts
    the colours that move, per design, with example lots and the open
    questions the moving lots carry."""
    reg = reg or fp.registry()
    rules = rules or fp.colour_rules()
    now = now or dt.datetime.now(dt.UTC)
    snapshot = await current_snapshot(session)
    run = await run_in_use(session, snapshot.id if snapshot is not None else None)
    report: dict[str, Any] = {
        "pending_kinds": sorted(t.code for t in reg if t.status is fp.TypeStatus.pending),
        "kinds": len(reg),
        "rule_line": rules.yellow_at_severity,
        "steps": list(steps),
    }
    rows = 0
    moved: dict[str, int] = {}
    moved_examples: list[dict[str, Any]] = []
    bad: dict[str, int] = {}
    bad_examples: list[dict[str, Any]] = []
    stored: dict[str, dict[str, int]] = {}
    sens: dict[str, dict[str, dict[str, Any]]] = {}
    if run is None:
        report["skipped"] = "no run in use"
    else:
        result = await session.stream(_ROWS.execution_options(yield_per=5000), {"run": run.id})
        async for county, tlid, design, slack, was, flags_raw, binds_raw in result:
            rows += 1
            was = was or "unknown"
            mine = stored.setdefault(design, {})
            mine[was] = mine.get(was, 0) + 1
            try:
                flags = [fp.Flag.from_json(f) for f in _json(flags_raw)]
                binds = [fp.Bind.from_json(b) for b in _json(binds_raw)]
                fp.validate(flags, reg)
            except (KeyError, ValueError, TypeError) as exc:
                why = str(exc).split(":", 1)[0].strip("'\" ") or type(exc).__name__
                bad[why] = bad.get(why, 0) + 1
                if len(bad_examples) < EXAMPLES:
                    bad_examples.append(_example(county, tlid, design, why=str(exc)[:300]))
                continue
            today = fp.colour(binds, flags, reg=reg, rules=rules).value
            if today != was:
                k = f"{was}->{today}"
                moved[k] = moved.get(k, 0) + 1
                if len(moved_examples) < EXAMPLES:
                    moved_examples.append(_example(county, tlid, design, stored=was, today=today))
            slack_ft = float(slack) if slack is not None else None
            per = sens.setdefault(design, {})
            for step in steps:
                after = fp.colour(widened(binds, flags, slack_ft, step), flags, reg=reg, rules=rules).value
                if after == today:
                    continue
                s = per.setdefault(str(step), {"moves": {}, "examples": [], "keys": {}})
                k = f"{today}->{after}"
                s["moves"][k] = s["moves"].get(k, 0) + 1
                if len(s["examples"]) < EXAMPLES:
                    s["examples"].append(_example(county, tlid, design, move=k))
                for f in flags:
                    if f.code in reg and fp.severity_of(f, reg) >= rules.yellow_at_severity:
                        key = "" if reg[f.code].scope is fp.Scope.per_lot else f.key
                        name = f"{f.code}{fp.SEP}{key}"
                        s["keys"][name] = s["keys"].get(name, 0) + 1
        for per in sens.values():
            for s in per.values():
                s["keys"] = dict(sorted(s["keys"].items(), key=lambda kv: -kv[1])[:10])
        if rows == 0:
            report["skipped"] = f"run {run.id} was screened before the colour rule and carries no flags"
    unregistered = (
        await session.execute(
            select(FlatsFlagInstance.code, func.count())
            .where(
                FlatsFlagInstance.status == "open",
                FlatsFlagInstance.code.not_in([t.code for t in reg]),
            )
            .group_by(FlatsFlagInstance.code)
        )
    ).all()
    report |= {
        "rows": rows,
        "colours": stored,
        "moved": moved,
        "moved_examples": moved_examples,
        "incomplete": bad,
        "incomplete_examples": bad_examples,
        "unregistered_instances": {code: int(n) for code, n in unregistered},
        "sensitivity": sens,
    }
    ok = rows > 0 and not moved and not bad and not unregistered
    row = FlatsFlagReport(made_at=now, run_id=run.id if run is not None else None, ok=ok, report=report)
    session.add(row)
    await session.flush()
    return row


async def latest_report(session: AsyncSession) -> FlatsFlagReport | None:
    """The newest nightly check, or None before the first night."""
    return (
        await session.execute(
            select(FlatsFlagReport).order_by(FlatsFlagReport.made_at.desc()).limit(1)
        )
    ).scalar()
