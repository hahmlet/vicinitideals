"""The county copy's ledger: which snapshot is in use, what the monthly check found.

Steph's condition on keeping the screen's copy of the county map in this
database (HUMAN_TODO 20, 2026-09-19) was a failure-state warning that does not
depend on any live connection. Everything here reads and writes rows; the
rules that turn rows into a banner live in :mod:`flats.ingest.status` and
the one request-making piece, the probe, in :mod:`flats.ingest.probe`. This
module is what the scripts, the Celery task and the Lots pages all call, so
the page and the command line can never disagree about what the copy is.

Seven things, and nothing that refreshes anything:

* :func:`register_snapshot` -- a ``flats.snapshots`` row from an acquire
  manifest. Keyed on (date, host); re-registering updates the manifest. The
  copy in use is never demoted here -- that is :func:`promote` or
  :func:`rollback`.
* :func:`attach_report` -- one section of a snapshot's report (the delta
  summary, the drift matrix), stored on the row Steph's promotion decision
  is about.
* :func:`run_probe` -- the monthly check against the copy in use, written as
  one ``flats.probes`` row. A probe that cannot complete is a ``failed`` row,
  never an exception: the row is the warning.
* :func:`refresh_notices` -- the banner: the current snapshot, the newest
  snapshot, the waiting candidates and the last two probes, handed to
  :func:`flats.ingest.status.assess`.
* :func:`drift` -- old run against candidate run, lot by lot and design by
  design: which verdicts and colours moved, and whether each move is
  explained by the ground (a ``lot_changes`` row or a zone change), by the
  rules version, by the code version, or by nothing -- the last is a bug and
  blocks an agent's promotion.
* :func:`promote` / :func:`rollback` -- the status flip Steph's rule governs
  ("me, when clean; you, when warned"): :func:`blocks` says which gate codes
  stand; a blocked promotion needs a written override; who promoted and on
  what grounds is written on the row. Since 2026-09-22 one code warns without
  holding the copy back -- a zone code nobody has ruled on (:func:`warns`):
  its own lots sit as "a new zone, under evaluation" while the rest of the
  county goes live. Promotion marks every active review
  decision whose lot split, merged, was renumbered, deleted, vacated or
  changed zone as "look again".
* :func:`promote_run` / :func:`rollback_run` -- the same rule for a
  re-screen of the copy in use (the rules or the screen changed, the ground
  did not): the new run is loaded as a candidate on the current copy, its
  drift against the run in use is read through the same gate, and promoting
  it makes it the Lots pages' default while the run it replaces stays
  reachable by ``?run=``; rolling it back puts the earlier run back. A
  re-screen never lands on the live run in place -- the loader refuses that
  -- so every change to what the site shows goes through the gate and can
  be undone.
* :func:`prune` -- the lot rows of copies older than the previous one, so
  the database holds the copy in use, the one before it, and the candidates.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import FlatsLot, FlatsProbe, FlatsRun, FlatsSnapshot
from flats.ingest import status as rules
from flats.ingest.checks import CODES as CHECK_CODES
from flats.ingest.checks import WARN_ONLY, blocking, tripped
from flats.ingest.checks import warnings as warn_only_codes
from flats.ingest.probe import Finding, probe, summarize
from flats.ingest.sources import Pipeline, load_pipeline

#: Snapshot statuses a manifest may be registered under by hand.
REGISTERABLE = ("candidate", "current", "failed")
#: Change kinds that put a decision about the lot in doubt (the delta's REREVIEW_KINDS).
REREVIEW_KINDS = ("split", "merge", "renumbered", "deleted", "vacated")
#: Gate codes beyond the six checks the loader writes: the two reports the
#: runbook produces before a promotion, and the drift the reports could not explain.
GATE_CODES = (*CHECK_CODES, "no_delta", "no_drift", "verdict_drift")

#: What each gate code asks, in the words the page shows beside it.
GATE_WORDS = {
    "layers_incomplete": "every layer downloaded whole",
    "count_drift": "layer counts in the normal range",
    "new_zones": "no zone code nobody has ruled on",
    "lots_drift": "lot count near the copy in use",
    "zone_changes": "no city mostly rezoned",
    "rlis_agreement": "Metro's change list agrees with ours",
    "no_delta": "the delta was run and stored",
    "no_drift": "the verdict drift was run and stored",
    "verdict_drift": "every verdict move explained",
}


# --- reading a manifest ---------------------------------------------------------


def snapshot_counts(manifest: dict[str, Any]) -> dict[str, Any]:
    """Per-dataset status and feature count, lifted out of the manifest."""
    datasets = manifest.get("datasets") or {}
    out: dict[str, Any] = {"datasets": {}, "by_status": {}, "features": 0}
    for key, entry in sorted(datasets.items()):
        status = entry.get("status")
        out["datasets"][key] = {
            "status": status,
            "features": entry.get("features"),
            "unfetched": len(entry.get("unfetched_ids") or []),
        }
        out["by_status"][status] = out["by_status"].get(status, 0) + 1
        if status in ("acquired", "present") and entry.get("features"):
            out["features"] += int(entry["features"])
    return out


def rlis_release(manifest: dict[str, Any]) -> str | None:
    """The RLIS quarterly release the copy's lot fabric came from, if recorded."""
    for archive in (manifest.get("archives") or {}).values():
        if archive.get("release"):
            return str(archive["release"])
    return None


def acquired_at(manifest: dict[str, Any]) -> dt.datetime | None:
    """When the last dataset in the copy was fetched."""
    stamps = [
        str(entry["retrieved_at"])
        for entry in (manifest.get("datasets") or {}).values()
        if entry.get("retrieved_at")
    ]
    if not stamps:
        return None
    return dt.datetime.fromisoformat(max(stamps).replace("Z", "+00:00"))


# --- snapshots --------------------------------------------------------------------


class RegisterError(ValueError):
    """The manifest cannot be registered the way it was asked."""


async def current_snapshot(session: AsyncSession) -> FlatsSnapshot | None:
    return (
        await session.execute(select(FlatsSnapshot).where(FlatsSnapshot.status == "current"))
    ).scalar_one_or_none()


async def register_snapshot(
    session: AsyncSession,
    manifest: dict[str, Any],
    *,
    host: str,
    status: str,
    notes: str = "",
) -> FlatsSnapshot:
    """Upsert the ``flats.snapshots`` row for a manifest; flushed, not committed."""
    if status not in REGISTERABLE:
        raise RegisterError(f"status must be one of {', '.join(REGISTERABLE)}, not {status!r}")
    try:
        snapshot_date = dt.date.fromisoformat(str(manifest["snapshot"]))
    except (KeyError, ValueError) as exc:
        raise RegisterError("the manifest names no snapshot date") from exc

    existing = (
        await session.execute(
            select(FlatsSnapshot).where(
                FlatsSnapshot.snapshot_date == snapshot_date, FlatsSnapshot.host == host
            )
        )
    ).scalar_one_or_none()
    if existing is not None and existing.status == "current" and status != "current":
        raise RegisterError(
            f"snapshot {existing.id} ({snapshot_date.isoformat()}, {host}) is the copy in use; "
            "it is not re-registered as anything else -- promote another copy or roll back"
        )
    if status == "current":
        in_use = await current_snapshot(session)
        if in_use is not None and (existing is None or in_use.id != existing.id):
            raise RegisterError(
                f"snapshot {in_use.id} ({in_use.snapshot_date.isoformat()}) is already the copy in use; "
                "register this one as a candidate and promote it"
            )

    row = existing or FlatsSnapshot(snapshot_date=snapshot_date, host=host)
    row.status = status
    row.manifest = manifest
    # The manifest's counts replace their own keys; what the loader wrote
    # beside them (lots, measured, new_zones, baseline_snapshot_id) stays.
    row.counts = {**(row.counts or {}), **snapshot_counts(manifest)}
    row.rlis_release = rlis_release(manifest)
    row.acquired_at = acquired_at(manifest)
    if notes:
        row.notes = notes
    session.add(row)
    await session.flush()
    return row


async def attach_report(session: AsyncSession, snapshot_id: int, section: str, doc: dict[str, Any]) -> FlatsSnapshot:
    """Store one section of a snapshot's report (``delta``, later ``drift``); flushed, not committed.

    The report is what Steph reads before a promotion; each section is
    replaced whole when its stage is re-run, the others are left as they were.
    """
    row = await session.get(FlatsSnapshot, snapshot_id)
    if row is None:
        raise RegisterError(f"no snapshot {snapshot_id}; register it first")
    row.report = {**(row.report or {}), section: doc}
    session.add(row)
    await session.flush()
    return row


# --- the monthly probe ------------------------------------------------------------


async def run_probe(
    session: AsyncSession,
    *,
    client: httpx.Client | None = None,
    pipeline: Pipeline | None = None,
    log: Callable[[str], None] | None = None,
) -> FlatsProbe:
    """Check every registry source against the copy in use; write one row.

    The row is flushed, not committed. Whatever goes wrong -- no copy in use,
    the registry unreadable, the network gone -- becomes a ``failed`` row with
    the reason in its one finding, because a probe that raises leaves no row
    and no row would read as "not checked yet" rather than "could not check".
    """
    started = time.monotonic()
    current = await current_snapshot(session)
    against = current
    note: list[Finding] = []
    if current is not None and not (current.manifest or {}).get("datasets"):
        # The copy in use recorded no manifest (run 2's, registered by
        # migration 0132 from quadfit's raw file). The newest copy that did
        # is the best record of what the sources looked like when we last
        # took them, so the check compares against that one and says so.
        against = (
            await session.execute(
                select(FlatsSnapshot)
                .where(FlatsSnapshot.status != "failed", FlatsSnapshot.manifest["datasets"].is_not(None))
                .order_by(FlatsSnapshot.snapshot_date.desc(), FlatsSnapshot.id.desc())
            )
        ).scalars().first()
        if against is not None:
            note = [
                Finding(
                    "-",
                    "ok",
                    f"compared against snapshot {against.id} ({against.snapshot_date.isoformat()}, "
                    f"{against.status}): the copy in use ({current.snapshot_date.isoformat()}) recorded no manifest",
                )
            ]
    findings: list[Finding]
    if current is None:
        status = "failed"
        findings = [Finding("-", "failed", "no county map copy is in use; nothing to compare against")]
    elif against is None:
        status = "failed"
        findings = [
            Finding(
                "-",
                "failed",
                f"the copy in use ({current.snapshot_date.isoformat()}) recorded no manifest and no other copy has one",
            )
        ]
    else:
        try:
            found = probe(pipeline or load_pipeline(), against.manifest, client, log=log)
            status = summarize(found)
            findings = note + found
        except Exception as exc:  # the row is the report; nothing here may raise
            status = "failed"
            findings = [Finding("-", "failed", f"{type(exc).__name__}: {exc}")]
    row = FlatsProbe(
        snapshot_id=against.id if against is not None else None,
        status=status,
        findings=[f.as_dict() for f in findings],
        seconds=round(time.monotonic() - started, 1),
    )
    session.add(row)
    await session.flush()
    return row


# --- the banner -------------------------------------------------------------------


@dataclass(frozen=True)
class RefreshNotices:
    """What the Lots pages show about the copy: the warnings and the footer."""

    notices: list[rules.Notice]
    footer: str
    current: FlatsSnapshot | None

    @property
    def level(self) -> str | None:
        return self.notices[0].level if self.notices else None


def _as_rule_snapshot(row: FlatsSnapshot) -> rules.Snapshot:
    registered = row.registered_at.date() if row.registered_at is not None else row.snapshot_date
    return rules.Snapshot(
        id=row.id,
        snapshot_date=row.snapshot_date,
        status=row.status,
        registered_at=registered,
        rlis_release=row.rlis_release,
        manifest=row.manifest or {},
        notes=row.notes or "",
        new_zones=(row.counts or {}).get("new_zones") or {},
    )


def _as_rule_probe(row: FlatsProbe) -> rules.Probe:
    return rules.Probe(
        ran_at=row.ran_at.date(),
        status=row.status,
        findings=tuple(row.findings or ()),
    )


async def refresh_notices(session: AsyncSession, *, today: dt.date | None = None) -> RefreshNotices:
    """The banner for the Lots pages, computed from rows and nothing else."""
    today = today or dt.datetime.now(dt.UTC).date()
    snapshots = (
        await session.execute(
            select(FlatsSnapshot).order_by(FlatsSnapshot.snapshot_date.desc(), FlatsSnapshot.id.desc())
        )
    ).scalars().all()
    probes = (
        await session.execute(select(FlatsProbe).order_by(FlatsProbe.ran_at.desc(), FlatsProbe.id.desc()).limit(3))
    ).scalars().all()

    current = next((s for s in snapshots if s.status == "current"), None)
    latest = snapshots[0] if snapshots else None
    candidates = [_as_rule_snapshot(s) for s in snapshots if s.status == "candidate"]
    rule_probes = [_as_rule_probe(p) for p in probes]
    notices = rules.assess(
        current=_as_rule_snapshot(current) if current else None,
        latest=_as_rule_snapshot(latest) if latest else None,
        candidates=candidates,
        probes=rule_probes,
        today=today,
    )
    return RefreshNotices(
        notices=notices,
        footer=rules.footer(_as_rule_snapshot(current) if current else None, rule_probes),
        current=current,
    )


# --- promotion --------------------------------------------------------------------


class PromotionError(ValueError):
    """The promotion (or rollback, or drift) cannot be done the way it was asked."""


class PromotionBlocked(PromotionError):
    """The gate is not clean and no override was written."""

    def __init__(self, codes: list[str]) -> None:
        super().__init__(
            "the gate is not clean: " + ", ".join(codes) + " -- Steph reads the report; an override needs a written reason"
        )
        self.codes = codes


@dataclass(frozen=True)
class Promotion:
    snapshot: FlatsSnapshot
    run: FlatsRun
    previous: FlatsSnapshot | None
    blocks: list[str]
    flagged: int
    by: str


@dataclass(frozen=True)
class Rollback:
    restored: FlatsSnapshot
    demoted: FlatsSnapshot
    demoted_run: FlatsRun | None
    by: str


@dataclass(frozen=True)
class RunPromotion:
    """A re-screen made the run in use; ``previous`` is the run it replaced, still reachable."""

    run: FlatsRun
    previous: FlatsRun | None
    snapshot: FlatsSnapshot
    blocks: list[str]
    by: str


@dataclass(frozen=True)
class RunRollback:
    restored: FlatsRun
    demoted: FlatsRun
    snapshot: FlatsSnapshot
    by: str


def blocks(snapshot: FlatsSnapshot, run: FlatsRun | None = None) -> list[str]:
    """The gate codes that keep an agent from promoting this copy, in gate order.

    The checks the loader wrote (:mod:`flats.ingest.checks`) less the
    warn-only ones, then ``no_delta`` / ``no_drift`` when the two reports the
    runbook produces before a promotion are not on the row, then
    ``verdict_drift`` when the drift report found a move nothing explains. An
    empty list is "clean": the agent may promote on Steph's standing word --
    which since 2026-09-22 includes a copy whose only standing row is a zone
    code nobody has ruled on (:func:`warns`).

    Given ``run`` -- a re-screen loaded as a candidate run on the copy in
    use -- the delta is not owed (the ground is the same copy's, compared
    when the copy was promoted) and the drift report must be the one that
    compared THIS run, not an earlier one left on the row.
    """
    out = blocking(snapshot.checks)
    report = snapshot.report or {}
    if run is None and not report.get("delta"):
        out.append("no_delta")
    drift_report = drift_for(snapshot, run)
    if not drift_report:
        out.append("no_drift")
    elif drift_report.get("unexplained"):
        out.append("verdict_drift")
    return out


def warns(snapshot: FlatsSnapshot) -> list[str]:
    """The gate codes that stand but do not hold the copy back.

    Steph, 2026-09-22 (HUMAN_TODO 22): a zone code nobody has ruled on warns,
    the copy goes live, and only that code's own lots sit -- shown as a new
    zone under evaluation, never green and never red -- until the code is
    read and written down, which is the same week. The page and the banner
    name the code either way, so nothing about it is invisible.
    """
    return warn_only_codes(snapshot.checks)


def drift_for(snapshot: FlatsSnapshot, run: FlatsRun | None = None) -> dict[str, Any]:
    """The drift report on the row -- only when it is about ``run``, if one is named."""
    doc = (snapshot.report or {}).get("drift") or {}
    if run is not None and doc.get("to_run") != run.id:
        return {}
    return doc


def gate(snapshot: FlatsSnapshot, run: FlatsRun | None = None) -> list[dict[str, Any]]:
    """Every gate code with whether it stands, whether it blocks, and why.

    ``tripped`` is "this check found something" and ``blocking`` is "this
    stops the agent promoting"; they are the same row except for a warn-only
    code (:data:`flats.ingest.checks.WARN_ONLY`), which the page shows amber
    and the gate lets through. For a re-screen (``run``) the delta row is not
    shown: it is the copy's, not the run's."""
    checks = snapshot.checks or {}
    report = snapshot.report or {}
    standing = set(blocks(snapshot, run))
    found_codes = set(tripped(checks))
    rows = []
    for code in CHECK_CODES:
        found = checks.get(code) or {}
        rows.append(
            {
                "code": code,
                "words": GATE_WORDS[code],
                "tripped": code in found_codes,
                "blocking": code in standing,
                "warn_only": code in WARN_ONLY,
                "detail": found.get("detail") or "not written yet -- the loader writes it at the end of a candidate load",
            }
        )
    delta = report.get("delta") or {}
    if run is None:
        rows.append(
            {
                "code": "no_delta",
                "words": GATE_WORDS["no_delta"],
                "tripped": "no_delta" in standing,
                "blocking": "no_delta" in standing,
                "warn_only": False,
                "detail": (
                    f"{delta.get('rows', 0):,} lot changes {delta.get('from')} -> {delta.get('to')}, "
                    f"{delta.get('rereview', 0):,} put a decision in doubt"
                    if delta
                    else "no delta report on this copy; run the delta and store its summary"
                ),
            }
        )
    drift_report = drift_for(snapshot, run)
    if drift_report:
        detail = (
            f"{drift_report.get('moved', 0):,} of {drift_report.get('compared', 0):,} verdicts moved "
            f"(ground {drift_report.get('by_cause', {}).get('data', 0):,}, surroundings "
            f"{drift_report.get('by_cause', {}).get('surroundings', 0):,}, re-measured "
            f"{drift_report.get('by_cause', {}).get('remeasured', 0):,}, rules "
            f"{drift_report.get('by_cause', {}).get('rules', 0):,}, code "
            f"{drift_report.get('by_cause', {}).get('code', 0):,}, unexplained {drift_report.get('unexplained', 0):,})"
        )
    elif run is not None:
        detail = f"no drift report for run {run.id}; run drift from the run in use to it"
    else:
        detail = "no drift report on this copy; run drift against the run in use"
    rows.append(
        {
            "code": "no_drift",
            "words": GATE_WORDS["no_drift"],
            "tripped": "no_drift" in standing,
            "blocking": "no_drift" in standing,
            "warn_only": False,
            "detail": detail,
        }
    )
    rows.append(
        {
            "code": "verdict_drift",
            "words": GATE_WORDS["verdict_drift"],
            "tripped": "verdict_drift" in standing,
            "blocking": "verdict_drift" in standing,
            "warn_only": False,
            "detail": (
                f"{drift_report.get('unexplained', 0):,} moves nothing explains"
                if drift_report
                else "waiting on the drift report"
            ),
        }
    )
    return rows


async def candidate_run(session: AsyncSession, snapshot_id: int) -> FlatsRun | None:
    """The newest candidate run loaded from this copy."""
    return (
        await session.execute(
            select(FlatsRun)
            .where(FlatsRun.snapshot_id == snapshot_id, FlatsRun.status == "candidate")
            .order_by(FlatsRun.id.desc())
        )
    ).scalars().first()


async def run_in_use(session: AsyncSession, snapshot_id: int | None = None) -> FlatsRun | None:
    """The newest complete run -- the one the Lots pages show by default --
    or, given a snapshot, its newest complete run."""
    stmt = select(FlatsRun).where(FlatsRun.status == "complete").order_by(FlatsRun.id.desc())
    if snapshot_id is not None:
        stmt = stmt.where(FlatsRun.snapshot_id == snapshot_id)
    return (await session.execute(stmt)).scalars().first()


def _note(existing: str | None, line: str) -> str:
    return f"{existing}\n{line}" if existing else line


_FLAG_DECISIONS = text(
    """
    WITH moved AS (
        SELECT county, tlid, kind || COALESCE(' ' || role, '') AS why
        FROM flats.lot_changes
        WHERE snapshot_to = :snap AND snapshot_from = :prev AND kind = ANY(:kinds)
        UNION ALL
        SELECT n.county, n.tlid,
               'zone ' || COALESCE(o.zone, o.zone_raw, '?') || ' -> ' || COALESCE(n.zone, n.zone_raw, '?')
        FROM flats.lots n
        JOIN flats.lots o ON o.snapshot_id = :prev AND o.county = n.county AND o.tlid = n.tlid
        WHERE n.snapshot_id = :snap AND n.zone IS DISTINCT FROM o.zone
    ),
    reasons AS (
        SELECT county, tlid, string_agg(DISTINCT why, '; ') AS reason FROM moved GROUP BY county, tlid
    )
    UPDATE flats.review_decisions d
    SET needs_rereview_snapshot_id = :snap, needs_rereview_reason = r.reason
    FROM reasons r
    WHERE d.county = r.county AND d.tlid = r.tlid AND d.superseded_at IS NULL
    """
)


async def promote(
    session: AsyncSession,
    snapshot_id: int,
    *,
    by: str,
    override: str | None = None,
    now: dt.datetime | None = None,
) -> Promotion:
    """Make a candidate copy the copy in use; flushed, not committed.

    One flip, three rows: the candidate run becomes ``complete`` (and so the
    Lots pages' default, being the newest), the copy in use becomes
    ``retired`` (its run stays reachable by ``?run=``), the candidate becomes
    ``current`` with who promoted it and when. A gate that is not clean
    refuses unless ``override`` says why, and the reason is written on the
    row beside the codes it overrode. Then every active review decision
    whose lot the delta shows split, merged, renumbered, deleted or vacated,
    or whose zone changed between the two copies, is marked "look again".
    """
    if not by or not by.strip():
        raise PromotionError("say who is promoting (--by); the row records it")
    now = now or dt.datetime.now(dt.UTC)
    snapshot = await session.get(FlatsSnapshot, snapshot_id)
    if snapshot is None:
        raise PromotionError(f"no snapshot {snapshot_id}")
    if snapshot.status != "candidate":
        raise PromotionError(f"snapshot {snapshot_id} is {snapshot.status}; only a candidate is promoted")
    run = await candidate_run(session, snapshot_id)
    if run is None:
        raise PromotionError(f"nothing has been loaded from snapshot {snapshot_id}; load a candidate run first")
    standing = blocks(snapshot)
    if standing and not (override and override.strip()):
        raise PromotionBlocked(standing)

    previous = await current_snapshot(session)
    stamp = now.date().isoformat()
    if previous is not None:
        previous.status = "retired"
        previous.notes = _note(previous.notes, f"retired {stamp}: snapshot {snapshot.id} ({snapshot.snapshot_date.isoformat()}) promoted by {by}")
        session.add(previous)
        await session.flush()  # exactly one row may be current: the old one steps down before the new one steps up
    snapshot.status = "current"
    snapshot.promoted_at = now
    snapshot.promoted_by = by[:200]
    if standing:
        snapshot.notes = _note(snapshot.notes, f"promoted {stamp} over {', '.join(standing)} by {by}: {override.strip()}")
    session.add(snapshot)
    run.status = "complete"
    if run.finished_at is None:
        run.finished_at = now
    session.add(run)
    await session.flush()

    flagged = 0
    if previous is not None:
        result = await session.execute(
            _FLAG_DECISIONS, {"snap": snapshot.id, "prev": previous.id, "kinds": list(REREVIEW_KINDS)}
        )
        flagged = int(result.rowcount or 0)
    return Promotion(snapshot=snapshot, run=run, previous=previous, blocks=standing, flagged=flagged, by=by)


async def rollback(session: AsyncSession, *, by: str, reason: str, now: dt.datetime | None = None) -> Rollback:
    """Undo the last promotion; flushed, not committed.

    The copy in use goes back to ``candidate`` (its run too, so the Lots
    pages stop showing it by default), and the copy retired most recently
    is the copy in use again. Refuses when the copy in use was never
    promoted (nothing to go back to) or the previous copy's lots were pruned.
    """
    if not reason or not reason.strip():
        raise PromotionError("say why (--reason); a rollback without a reason is a promotion nobody can explain")
    now = now or dt.datetime.now(dt.UTC)
    current = await current_snapshot(session)
    if current is None:
        raise PromotionError("no copy is in use; nothing to roll back")
    if current.promoted_at is None:
        raise PromotionError(f"snapshot {current.id} was never promoted; there is no earlier copy to go back to")
    previous = (
        await session.execute(
            select(FlatsSnapshot)
            .where(FlatsSnapshot.status == "retired")
            .order_by(FlatsSnapshot.snapshot_date.desc(), FlatsSnapshot.id.desc())
        )
    ).scalars().first()
    if previous is None:
        raise PromotionError("no retired copy to go back to")
    kept = (
        await session.execute(select(func.count()).select_from(FlatsLot).where(FlatsLot.snapshot_id == previous.id))
    ).scalar_one()
    if not kept:
        raise PromotionError(f"snapshot {previous.id} ({previous.snapshot_date.isoformat()}) has no lot rows left; it was pruned")
    stamp = now.date().isoformat()
    demoted_run = await run_in_use(session, current.id)
    # Every complete run on the copy steps down, not just the newest: a
    # re-screen promoted on this copy is complete too, and a complete run on
    # a candidate copy would be the Lots pages' default.
    for run in (
        await session.execute(select(FlatsRun).where(FlatsRun.snapshot_id == current.id, FlatsRun.status == "complete"))
    ).scalars():
        run.status = "candidate"
        session.add(run)
    current.status = "candidate"
    current.notes = _note(current.notes, f"rolled back {stamp} by {by}: {reason.strip()}")
    session.add(current)
    await session.flush()  # the partial unique index on status = 'current' again
    previous.status = "current"
    previous.notes = _note(previous.notes, f"restored {stamp} by {by} (rollback of snapshot {current.id})")
    session.add(previous)
    await session.flush()
    return Rollback(restored=previous, demoted=current, demoted_run=demoted_run, by=by)


async def promote_run(
    session: AsyncSession,
    run_id: int,
    *,
    by: str,
    override: str | None = None,
    now: dt.datetime | None = None,
) -> RunPromotion:
    """Make a re-screen of the copy in use the run the Lots pages show; flushed, not committed.

    The run must be a candidate loaded on the ``current`` copy (a candidate
    run on a candidate copy is promoted with the copy, by :func:`promote`).
    The gate is the loader's checks and the drift report for this run
    against the run in use -- the delta is the copy's and is not owed
    twice. One flip: the run becomes ``complete`` and, being the newest,
    the default; the run it replaces stays ``complete`` and reachable by
    ``?run=``. Nothing on the ground moved, so no decision is marked.
    """
    if not by or not by.strip():
        raise PromotionError("say who is promoting (--by); the row records it")
    now = now or dt.datetime.now(dt.UTC)
    run = await session.get(FlatsRun, run_id)
    if run is None:
        raise PromotionError(f"no run {run_id}")
    if run.status != "candidate":
        raise PromotionError(f"run {run_id} is {run.status}; only a candidate run is promoted")
    if run.snapshot_id is None:
        raise PromotionError(f"run {run_id} belongs to no copy")
    snapshot = await session.get(FlatsSnapshot, run.snapshot_id)
    if snapshot is None or snapshot.status != "current":
        raise PromotionError(
            f"run {run_id} reads snapshot {run.snapshot_id}, which is "
            f"{'missing' if snapshot is None else snapshot.status}; a re-screen is promoted on the copy in use "
            f"(a candidate copy is promoted whole, with --snapshot)"
        )
    previous = await run_in_use(session, snapshot.id)
    standing = blocks(snapshot, run)
    if standing and not (override and override.strip()):
        raise PromotionBlocked(standing)

    stamp = now.date().isoformat()
    run.status = "complete"
    if run.finished_at is None:
        run.finished_at = now
    line = f"promoted {stamp} by {by}" + (f" (replaces run {previous.id}, still reachable by ?run=)" if previous else "")
    if standing:
        line += f"; over {', '.join(standing)}: {override.strip()}"
    run.notes = _note(run.notes, line)
    session.add(run)
    snapshot.notes = _note(
        snapshot.notes,
        f"re-screen: run {run.id} promoted {stamp} by {by}"
        + (f" over {', '.join(standing)}" if standing else "")
        + (f"; run {previous.id} replaced" if previous else ""),
    )
    session.add(snapshot)
    await session.flush()
    return RunPromotion(run=run, previous=previous, snapshot=snapshot, blocks=standing, by=by)


async def rollback_run(
    session: AsyncSession, run_id: int, *, by: str, reason: str, now: dt.datetime | None = None
) -> RunRollback:
    """Undo a re-screen's promotion; flushed, not committed.

    The run goes back to ``candidate`` (the Lots pages stop showing it by
    default) and the complete run before it on the same copy is the
    default again. Refuses when the run is not the run in use, or when
    there is no earlier complete run on the copy to fall back to -- that is
    a copy rollback, :func:`rollback`.
    """
    if not reason or not reason.strip():
        raise PromotionError("say why (--reason); a rollback without a reason is a promotion nobody can explain")
    now = now or dt.datetime.now(dt.UTC)
    run = await session.get(FlatsRun, run_id)
    if run is None:
        raise PromotionError(f"no run {run_id}")
    if run.snapshot_id is None:
        raise PromotionError(f"run {run_id} belongs to no copy")
    snapshot = await session.get(FlatsSnapshot, run.snapshot_id)
    if snapshot is None or snapshot.status != "current":
        raise PromotionError(f"run {run_id} is not on the copy in use; roll the copy back instead")
    in_use = await run_in_use(session, snapshot.id)
    if in_use is None or in_use.id != run.id:
        raise PromotionError(
            f"run {run_id} is not the run in use"
            + (f" (run {in_use.id} is)" if in_use else "")
            + "; only the run the Lots pages show is rolled back"
        )
    earlier = (
        await session.execute(
            select(FlatsRun)
            .where(FlatsRun.snapshot_id == snapshot.id, FlatsRun.status == "complete", FlatsRun.id < run.id)
            .order_by(FlatsRun.id.desc())
        )
    ).scalars().first()
    if earlier is None:
        raise PromotionError(f"run {run_id} is the only complete run on the copy in use; there is no earlier run to go back to")
    stamp = now.date().isoformat()
    run.status = "candidate"
    run.notes = _note(run.notes, f"rolled back {stamp} by {by}: {reason.strip()} (run {earlier.id} is the default again)")
    session.add(run)
    snapshot.notes = _note(snapshot.notes, f"re-screen: run {run.id} rolled back {stamp} by {by}; run {earlier.id} in use again")
    session.add(snapshot)
    await session.flush()
    return RunRollback(restored=earlier, demoted=run, snapshot=snapshot, by=by)


_DRIFT_MATRIX = text(
    """
    SELECT o.tier AS tier_from, n.tier AS tier_to,
           COALESCE(o.checks->>'if_signed', 'unknown') AS colour_from,
           COALESCE(n.checks->>'if_signed', 'unknown') AS colour_to,
           COALESCE((o.checks->>'screened')::boolean, true) AS screened_from,
           COALESCE((n.checks->>'screened')::boolean, true) AS screened_to,
           (c.county IS NOT NULL) AS lot_changed,
           (ln.zone IS DISTINCT FROM lo.zone) AS zone_changed,
           count(*) AS n
    FROM flats.lot_results n
    JOIN flats.lots ln ON ln.id = n.lot_id AND ln.snapshot_id = :to_snapshot
    JOIN flats.lots lo ON lo.snapshot_id = :from_snapshot AND lo.county = ln.county AND lo.tlid = ln.tlid
    JOIN flats.lot_results o ON o.lot_id = lo.id AND o.run_id = :from_run AND o.design_key = n.design_key
    LEFT JOIN LATERAL (
        SELECT c.county FROM flats.lot_changes c
        WHERE c.snapshot_to = :ground_to AND c.county = ln.county AND c.tlid = ln.tlid
          AND c.kind <> 'attr_change'
        LIMIT 1
    ) c ON true
    WHERE n.run_id = :to_run
    GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
    """
)

#: Every moved answer the ground does not explain, with the measured facts on
#: both sides, so the cause can be read from what the measurement saw.
_DRIFT_GROUNDLESS = text(
    """
    SELECT ln.county, ln.tlid, n.design_key,
           o.tier AS tier_from, n.tier AS tier_to,
           COALESCE(o.checks->>'if_signed', 'unknown') AS colour_from,
           COALESCE(n.checks->>'if_signed', 'unknown') AS colour_to,
           lo.facts AS facts_from, ln.facts AS facts_to
    FROM flats.lot_results n
    JOIN flats.lots ln ON ln.id = n.lot_id AND ln.snapshot_id = :to_snapshot
    JOIN flats.lots lo ON lo.snapshot_id = :from_snapshot AND lo.county = ln.county AND lo.tlid = ln.tlid
    JOIN flats.lot_results o ON o.lot_id = lo.id AND o.run_id = :from_run AND o.design_key = n.design_key
    WHERE n.run_id = :to_run
      AND (o.tier <> n.tier OR COALESCE(o.checks->>'if_signed', 'unknown') <> COALESCE(n.checks->>'if_signed', 'unknown'))
      AND COALESCE((o.checks->>'screened')::boolean, true)
      AND COALESCE((n.checks->>'screened')::boolean, true)
      AND ln.zone IS NOT DISTINCT FROM lo.zone
      AND NOT EXISTS (
          SELECT 1 FROM flats.lot_changes c
          WHERE c.snapshot_to = :ground_to AND c.county = ln.county AND c.tlid = ln.tlid
            AND c.kind <> 'attr_change'
      )
    ORDER BY ln.county, ln.tlid, n.design_key
    """
)

#: Facts that are not what the measurement saw: the screen's and quadfit's
#: outputs, the assessor's roll (the screen reads nothing from it), the
#: register's own bookkeeping.
_NOT_SURROUNDINGS = frozenset({"source", "quadfit", "quadfit_jurisdiction", "assessor", "condo", "snapshot_zone", "unmeasured"})
#: A number re-read from a re-projected copy of the same ground differs in
#: the last digits (zone_frac 0.9999999999999999 vs 1.0; a sewer distance by
#: a millionth of a foot; an envelope by a third of a percent). Within either
#: tolerance two numbers are the same measurement.
_SAME_ABS = 0.05
_SAME_REL = 0.02


def _same_number(a: float, b: float, tolerant: bool) -> bool:
    if not tolerant:
        return a == b
    return abs(a - b) <= max(_SAME_ABS, _SAME_REL * max(abs(a), abs(b)))


def _facts_differ(a: Any, b: Any, tolerant: bool) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a != b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return not _same_number(float(a), float(b), tolerant)
    if isinstance(a, dict) and isinstance(b, dict):
        return any(_facts_differ(a.get(k), b.get(k), tolerant) for k in set(a) | set(b))
    if isinstance(a, list) and isinstance(b, list):
        return len(a) != len(b) or any(_facts_differ(x, y, tolerant) for x, y in zip(a, b))
    return a != b


def facts_moved(before: dict[str, Any] | None, after: dict[str, Any] | None, *, tolerant: bool = True) -> list[str]:
    """The measured facts that differ between two readings of the same lot, as
    dotted paths (``observed.corner_lot``, ``sewer.in_district``,
    ``lot_width_ft``); empty when the two readings are the same measurement
    within tolerance -- or, with ``tolerant=False``, the same to the last
    digit. What the screen and quadfit *concluded* is not a fact and is left
    out, as is the roll."""
    before = before or {}
    after = after or {}
    moved: list[str] = []
    for key in sorted(set(before) | set(after)):
        if key in _NOT_SURROUNDINGS:
            continue
        a, b = before.get(key), after.get(key)
        if (isinstance(a, dict) or isinstance(b, dict)) and (a is None or isinstance(a, dict)) and (b is None or isinstance(b, dict)):
            a, b = a or {}, b or {}
            moved += [f"{key}.{k}" for k in sorted(set(a) | set(b)) if _facts_differ(a.get(k), b.get(k), tolerant)]
        elif _facts_differ(a, b, tolerant):
            moved.append(key)
    return moved

_DRIFT_ONLY = text(
    """
    SELECT count(*) FROM flats.lot_results a
    JOIN flats.lots la ON la.id = a.lot_id AND la.snapshot_id = :a_snapshot
    WHERE a.run_id = :a_run AND NOT EXISTS (
        SELECT 1 FROM flats.lot_results b
        JOIN flats.lots lb ON lb.id = b.lot_id AND lb.snapshot_id = :b_snapshot
        WHERE b.run_id = :b_run AND lb.county = la.county AND lb.tlid = la.tlid AND b.design_key = a.design_key
    )
    """
)


async def drift(session: AsyncSession, *, from_run: int, to_run: int, examples: int = 20) -> dict[str, Any]:
    """Old run against new, lot by lot and design by design; stored on the new run's snapshot.

    A result row is compared with the row of the same lot and design in the
    other run (lots matched by county and TLID across the two copies). A move
    is a changed tier or a changed signed colour. Each move is put to one
    cause, in this order: the ground (a ``lot_changes`` row for the lot in
    the new copy other than an attribute-only change -- the screen reads
    nothing from the assessor's roll, so a new assessment explains no move
    -- or a different zone), the surroundings (a measured fact that differs
    between the two readings beyond float noise: the streets it fronts, an
    alley, a flood or sewer line, a zoning line -- layers the delta of the
    taxlots never sees; :func:`facts_moved`), a re-measurement (a fact
    differs only within tolerance -- a bearing by half a degree, a slope by
    a hundredth -- yet the answer sat on a line and flipped: the verdict is
    unstable on that lot, not wrong), the rules version, the code version
    -- and a move with none of those is ``unexplained``, which is a bug in
    the screen and blocks an agent's promotion. A row the screen
    never wrote on either side (an assign-stage ``unknown`` for a lot nobody
    measured) is counted apart, not as a move; lots only one run holds are
    counted too.

    Two runs of the SAME copy (a re-screen: the rules or the screen changed,
    the ground did not) compare the same lot rows, so the ground and the
    surroundings explain nothing there by construction -- the loader wrote
    the newer measurement over the older on the one row -- and every move is
    the rules', the screen's, or unexplained. The screen's version is
    ``screen_version`` (a hash of the screen's own files, stamped by the
    exporter) when both runs carry one, else the repo HEAD, which says "a
    commit landed", not "the screen changed". An earlier drift report on the
    row (the one the copy was promoted on) is kept under ``drift_earlier``.
    """
    old = await session.get(FlatsRun, from_run)
    new = await session.get(FlatsRun, to_run)
    if old is None or new is None:
        raise PromotionError(f"no run {from_run if old is None else to_run}")
    if old.snapshot_id is None or new.snapshot_id is None:
        raise PromotionError("both runs must belong to a snapshot")
    if old.id == new.id:
        raise PromotionError(f"run {from_run} against itself; nothing to compare")
    same_copy = old.snapshot_id == new.snapshot_id
    params = {
        "from_run": old.id,
        "to_run": new.id,
        "from_snapshot": old.snapshot_id,
        "to_snapshot": new.snapshot_id,
        # The ground cannot have moved between two runs of one copy; a
        # lot_changes row on that copy is the previous quarter's, not this run's.
        "ground_to": -1 if same_copy else new.snapshot_id,
    }
    rows = (await session.execute(_DRIFT_MATRIX, params)).all()

    same_rules = (old.rules_version or "") == (new.rules_version or "")
    if old.screen_version and new.screen_version:
        same_code = old.screen_version == new.screen_version
    else:
        same_code = (old.code_version or "") == (new.code_version or "")
    compared = unchanged = unscreened = 0
    by_cause = {"data": 0, "surroundings": 0, "remeasured": 0, "rules": 0, "code": 0, "unexplained": 0}
    tier_moves: dict[str, int] = {}
    colour_moves: dict[str, int] = {}
    groundless = 0
    for r in rows:
        n = int(r.n)
        if not (r.screened_from and r.screened_to):
            unscreened += n
            continue
        compared += n
        moved = r.tier_from != r.tier_to or r.colour_from != r.colour_to
        if not moved:
            unchanged += n
            continue
        if r.lot_changed or r.zone_changed:
            by_cause["data"] += n
        else:
            groundless += n
        if r.tier_from != r.tier_to:
            key = f"{r.tier_from}->{r.tier_to}"
            tier_moves[key] = tier_moves.get(key, 0) + n
        if r.colour_from != r.colour_to:
            key = f"{r.colour_from}->{r.colour_to}"
            colour_moves[key] = colour_moves.get(key, 0) + n

    # The moves the ground does not explain, one row each: the measured
    # facts say whether the map around the lot moved.
    surroundings_facts: dict[str, int] = {}
    remeasured_facts: dict[str, int] = {}
    sample: list[dict[str, Any]] = []
    if groundless:
        seen = 0
        for r in (await session.execute(_DRIFT_GROUNDLESS, params)).all():
            seen += 1
            moved_facts = facts_moved(r.facts_from, r.facts_to)
            nudged_facts = [] if moved_facts else facts_moved(r.facts_from, r.facts_to, tolerant=False)
            if moved_facts:
                cause = "surroundings"
                for path in moved_facts:
                    surroundings_facts[path] = surroundings_facts.get(path, 0) + 1
            elif nudged_facts:
                cause = "remeasured"
                for path in nudged_facts:
                    remeasured_facts[path] = remeasured_facts.get(path, 0) + 1
            elif not same_rules:
                cause = "rules"
            elif not same_code:
                cause = "code"
            else:
                cause = "unexplained"
            by_cause[cause] += 1
            if cause == "unexplained" and len(sample) < examples:
                sample.append(
                    {
                        "county": r.county,
                        "tlid": r.tlid,
                        "design": r.design_key,
                        "tier": [r.tier_from, r.tier_to],
                        "colour": [r.colour_from, r.colour_to],
                    }
                )
        # The two queries share their joins; a move the matrix counted and
        # the row query did not return would be a bug here, and is not hidden.
        by_cause["unexplained"] += max(0, groundless - seen)

    only_in_new = (
        await session.execute(
            _DRIFT_ONLY,
            {"a_run": new.id, "a_snapshot": new.snapshot_id, "b_run": old.id, "b_snapshot": old.snapshot_id},
        )
    ).scalar_one()
    only_in_old = (
        await session.execute(
            _DRIFT_ONLY,
            {"a_run": old.id, "a_snapshot": old.snapshot_id, "b_run": new.id, "b_snapshot": new.snapshot_id},
        )
    ).scalar_one()

    doc = {
        "from_run": old.id,
        "to_run": new.id,
        "from_snapshot": old.snapshot_id,
        "to_snapshot": new.snapshot_id,
        "same_copy": same_copy,
        "rules_version": [old.rules_version, new.rules_version],
        "code_version": [old.code_version, new.code_version],
        "screen_version": [old.screen_version, new.screen_version],
        "compared": compared,
        "unchanged": unchanged,
        "moved": compared - unchanged,
        "by_cause": by_cause,
        "surroundings_facts": dict(sorted(surroundings_facts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "remeasured_facts": dict(sorted(remeasured_facts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "unexplained": by_cause["unexplained"],
        "unscreened_side": unscreened,
        "only_in_new": int(only_in_new),
        "only_in_old": int(only_in_old),
        "tier_moves": dict(sorted(tier_moves.items(), key=lambda kv: -kv[1])),
        "colour_moves": dict(sorted(colour_moves.items(), key=lambda kv: -kv[1])),
        "examples": sample,
        "computed_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    }
    snapshot = await session.get(FlatsSnapshot, new.snapshot_id)
    earlier = (snapshot.report or {}).get("drift") if snapshot is not None else None
    if earlier and (earlier.get("from_run"), earlier.get("to_run")) != (old.id, new.id):
        kept = [d for d in (snapshot.report or {}).get("drift_earlier") or [] if d.get("to_run") != earlier.get("to_run")]
        await attach_report(session, new.snapshot_id, "drift_earlier", (kept + [earlier])[-5:])
    await attach_report(session, new.snapshot_id, "drift", doc)
    return doc


def drift_markdown(doc: dict[str, Any]) -> str:
    """The drift report as the page Steph reads."""
    lines = [
        f"# Verdict drift: run {doc['from_run']} (snapshot {doc['from_snapshot']}) -> run {doc['to_run']} (snapshot {doc['to_snapshot']})",
        "",
        f"{doc['compared']:,} lot-and-design answers compared; {doc['unchanged']:,} unchanged, {doc['moved']:,} moved.",
        f"Moves explained by the ground {doc['by_cause']['data']:,}, by the surroundings "
        f"{doc['by_cause'].get('surroundings', 0):,} (a measured fact that differs: the streets, an alley, a flood or "
        f"sewer line, a zoning line), by a re-measurement {doc['by_cause'].get('remeasured', 0):,} (a fact differs "
        f"only within tolerance and the answer sat on a line), by the rules version {doc['by_cause']['rules']:,}, "
        f"by the code version {doc['by_cause']['code']:,}; **unexplained {doc['unexplained']:,}**.",
        f"{doc['unscreened_side']:,} answers had no screen on one side (a lot the county map holds but nobody measured); "
        f"{doc['only_in_new']:,} answers only the new run holds, {doc['only_in_old']:,} only the old.",
        f"Rules version {doc['rules_version'][0]} -> {doc['rules_version'][1]}; code {doc['code_version'][0]} -> {doc['code_version'][1]}"
        + (
            f"; screen {doc['screen_version'][0]} -> {doc['screen_version'][1]}"
            if doc.get("screen_version") and any(doc["screen_version"])
            else ""
        )
        + ".",
        *(
            ["Both runs read the same copy: the ground did not move, so every move is the rules', the screen's, or unexplained."]
            if doc.get("same_copy")
            else []
        ),
        "",
        "## Verdict moves",
        "",
    ]
    lines += [f"- {k}: {v:,}" for k, v in doc["tier_moves"].items()] or ["- none"]
    lines += ["", "## Colour-if-signed moves", ""]
    lines += [f"- {k}: {v:,}" for k, v in doc["colour_moves"].items()] or ["- none"]
    if doc.get("surroundings_facts"):
        lines += ["", "## What moved around the lots", ""]
        lines += [f"- {k}: {v:,}" for k, v in doc["surroundings_facts"].items()]
    if doc.get("remeasured_facts"):
        lines += ["", "## What was re-measured within tolerance on a lot whose answer sat on a line", ""]
        lines += [f"- {k}: {v:,}" for k, v in doc["remeasured_facts"].items()]
    if doc["examples"]:
        lines += ["", "## Unexplained moves (first few)", ""]
        lines += [
            f"- {e['county']} {e['tlid']} {e['design']}: {e['tier'][0]} -> {e['tier'][1]}, "
            f"{e['colour'][0]} -> {e['colour'][1]}"
            for e in doc["examples"]
        ]
    return "\n".join(lines) + "\n"


async def prune(session: AsyncSession, *, keep: int = 1) -> list[dict[str, Any]]:
    """Drop the lot rows (and so the results) of retired copies older than the ``keep`` most recent; flushed, not committed.

    The copy in use and every candidate are never touched. A pruned copy's
    runs are marked ``retired`` so the Lots pages stop listing them; the
    snapshot row itself, its manifest, checks and reports stay.
    """
    retired = (
        await session.execute(
            select(FlatsSnapshot)
            .where(FlatsSnapshot.status == "retired")
            .order_by(FlatsSnapshot.snapshot_date.desc(), FlatsSnapshot.id.desc())
        )
    ).scalars().all()
    pruned: list[dict[str, Any]] = []
    for snap in retired[max(keep, 0):]:
        lots = (
            await session.execute(select(func.count()).select_from(FlatsLot).where(FlatsLot.snapshot_id == snap.id))
        ).scalar_one()
        if not lots:
            continue
        await session.execute(text("DELETE FROM flats.lots WHERE snapshot_id = :id"), {"id": snap.id})
        runs = await session.execute(
            text("UPDATE flats.runs SET status = 'retired' WHERE snapshot_id = :id AND status = 'complete'"), {"id": snap.id}
        )
        snap.notes = _note(snap.notes, f"pruned {dt.datetime.now(dt.UTC).date().isoformat()}: {lots:,} lot rows dropped")
        session.add(snap)
        pruned.append({"snapshot_id": snap.id, "snapshot_date": snap.snapshot_date.isoformat(), "lots": int(lots), "runs": int(runs.rowcount or 0)})
    await session.flush()
    return pruned
