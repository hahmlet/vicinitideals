"""The county copy's ledger: which snapshot is in use, what the monthly check found.

Steph's condition on keeping the screen's copy of the county map in this
database (HUMAN_TODO 20, 2026-09-19) was a failure-state warning that does not
depend on any live connection. Everything here reads and writes rows; the
rules that turn rows into a banner live in :mod:`flats.ingest.status` and
the one request-making piece, the probe, in :mod:`flats.ingest.probe`. This
module is what the scripts, the Celery task and the Lots pages all call, so
the page and the command line can never disagree about what the copy is.

Four things, and nothing that refreshes anything:

* :func:`register_snapshot` -- a ``flats.snapshots`` row from an acquire
  manifest. Keyed on (date, host); re-registering updates the manifest. The
  copy in use is never demoted here -- that is a promotion or a rollback,
  which come with the refresh service (plan phase 4).
* :func:`attach_report` -- one section of a snapshot's report (the delta
  summary today; the drift matrix in phase 4), stored on the row Steph's
  promotion decision is about.
* :func:`run_probe` -- the monthly check against the copy in use, written as
  one ``flats.probes`` row. A probe that cannot complete is a ``failed`` row,
  never an exception: the row is the warning.
* :func:`refresh_notices` -- the banner: the current snapshot, the newest
  snapshot, the waiting candidates and the last two probes, handed to
  :func:`flats.ingest.status.assess`.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import FlatsProbe, FlatsSnapshot
from flats.ingest import status as rules
from flats.ingest.probe import Finding, probe, summarize
from flats.ingest.sources import Pipeline, load_pipeline

#: Snapshot statuses a manifest may be registered under by hand.
REGISTERABLE = ("candidate", "current", "failed")


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
    row.counts = snapshot_counts(manifest)
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
