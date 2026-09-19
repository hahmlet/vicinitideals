"""Promote a refreshed county copy, roll one back, or read the verdict drift first.

The refresh runbook (``docs/ops/flats-county-refresh.md``) ends here. A
candidate run has been loaded beside the copy in use; the delta summary and
the gate checks are on its snapshot row. This script writes the third
report, reads the gate, and does the one flip Steph's rule governs:

    "Me, when clean; you, when warned."  (2026-09-19)

A clean gate -- every check quiet, both reports present, no unexplained
verdict move -- may be promoted by the agent on that standing word. A gate
with anything standing waits for Steph, or is promoted over with a written
reason that the row keeps.

Usage (inside the api container):

    python scripts/flats_promote.py status
    python scripts/flats_promote.py drift --from-run 2 --to-run 4 [--out /app/data/flats/reports/2026-09-18/drift.md]
    python scripts/flats_promote.py promote --snapshot 3 --by "agent, standing word 2026-09-19" [--override "..."] [--dry-run]
    python scripts/flats_promote.py rollback --by "Steph" --reason "..." [--dry-run]
    python scripts/flats_promote.py prune [--keep 1] [--dry-run]

``drift`` stores its report on the candidate's snapshot (``report.drift``)
and prints it; ``promote`` refuses a standing gate unless ``--override``
says why; ``rollback`` puts the previous copy back in use; ``prune`` drops
the lot rows of retired copies older than the ``--keep`` most recent, so the
database holds the copy in use, the one before it, and any candidates.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import settings  # noqa: E402
from app.models.flats import FlatsRun, FlatsSnapshot  # noqa: E402
from app.services.flats_refresh import (  # noqa: E402
    PromotionBlocked,
    PromotionError,
    drift,
    drift_markdown,
    gate,
    promote,
    prune,
    rollback,
)


async def _status(session: AsyncSession) -> int:
    snapshots = (
        await session.execute(select(FlatsSnapshot).order_by(FlatsSnapshot.snapshot_date.desc(), FlatsSnapshot.id.desc()))
    ).scalars().all()
    runs = (await session.execute(select(FlatsRun).order_by(FlatsRun.id.desc()))).scalars().all()
    if not snapshots:
        print("no snapshots registered")
        return 0
    for snap in snapshots:
        counts = snap.counts or {}
        print(
            f"snapshot {snap.id:>3}  {snap.snapshot_date.isoformat()}  {snap.host:<5} {snap.status:<10} "
            f"RLIS {snap.rlis_release or '?':<8} lots {counts.get('lots') or 0:>8,}  measured {counts.get('measured') or 0:>8,}"
            + (f"  promoted {snap.promoted_at.date().isoformat()} by {snap.promoted_by}" if snap.promoted_at else "")
        )
        for run in runs:
            if run.snapshot_id == snap.id:
                print(f"    run {run.id:>3}  {run.status:<10} rules {run.rules_version or '?'}  code {run.code_version or '?'}")
        if snap.status == "candidate":
            standing = [g for g in gate(snap) if g["tripped"]]
            print("    gate: " + ("clean -- the agent may promote on the standing word" if not standing else "WARNED -- Steph reads the report"))
            for g in gate(snap):
                print(f"      {'!!' if g['tripped'] else 'ok'} {g['code']:<18} {g['detail']}")
    return 0


async def _drift(session: AsyncSession, args: argparse.Namespace) -> int:
    try:
        doc = await drift(session, from_run=args.from_run, to_run=args.to_run, examples=args.examples)
    except PromotionError as exc:
        print(f"refused: {exc}")
        return 2
    md = drift_markdown(doc)
    print(md)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md, encoding="utf-8")
        print(f"wrote {args.out}")
    if args.dry_run:
        await session.rollback()
        print("dry run, rolled back (the report was not stored)")
    else:
        await session.commit()
        print(f"stored on snapshot {doc['to_snapshot']} as report.drift")
    return 0


async def _promote(session: AsyncSession, args: argparse.Namespace) -> int:
    try:
        done = await promote(session, args.snapshot, by=args.by, override=args.override)
    except PromotionBlocked as exc:
        print(f"refused: {exc}")
        snap = await session.get(FlatsSnapshot, args.snapshot)
        if snap is not None:
            for g in gate(snap):
                print(f"  {'!!' if g['tripped'] else 'ok'} {g['code']:<18} {g['detail']}")
        return 3
    except PromotionError as exc:
        print(f"refused: {exc}")
        return 2
    print(
        f"snapshot {done.snapshot.id} ({done.snapshot.snapshot_date.isoformat()}) is the copy in use; "
        f"run {done.run.id} is complete and the Lots pages' default"
    )
    if done.previous is not None:
        print(f"snapshot {done.previous.id} ({done.previous.snapshot_date.isoformat()}) retired; its run stays reachable by ?run=")
    if done.blocks:
        print(f"promoted OVER {', '.join(done.blocks)} by {done.by}: {args.override}")
    else:
        print(f"gate clean; promoted by {done.by}")
    print(f"{done.flagged:,} review decisions marked 'look again'")
    if args.dry_run:
        await session.rollback()
        print("dry run, rolled back")
    else:
        await session.commit()
    return 0


async def _rollback(session: AsyncSession, args: argparse.Namespace) -> int:
    try:
        done = await rollback(session, by=args.by, reason=args.reason)
    except PromotionError as exc:
        print(f"refused: {exc}")
        return 2
    print(
        f"snapshot {done.restored.id} ({done.restored.snapshot_date.isoformat()}) is the copy in use again; "
        f"snapshot {done.demoted.id} ({done.demoted.snapshot_date.isoformat()}) is a candidate"
        + (f" and run {done.demoted_run.id} with it" if done.demoted_run else "")
    )
    if args.dry_run:
        await session.rollback()
        print("dry run, rolled back")
    else:
        await session.commit()
    return 0


async def _prune(session: AsyncSession, args: argparse.Namespace) -> int:
    pruned = await prune(session, keep=args.keep)
    if not pruned:
        print("nothing to prune")
    for row in pruned:
        print(f"snapshot {row['snapshot_id']} ({row['snapshot_date']}): {row['lots']:,} lot rows dropped, {row['runs']} runs retired")
    if args.dry_run:
        await session.rollback()
        print("dry run, rolled back")
    else:
        await session.commit()
        if pruned:
            print("run VACUUM (FULL, ANALYZE) flats.lots; VACUUM (FULL, ANALYZE) flats.lot_results; to give the space back")
    return 0


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-url", default=settings.database_url)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="every snapshot, its runs, and the gate on each candidate")

    dr = sub.add_parser("drift", help="compare the run in use with a candidate run and store the report")
    dr.add_argument("--from-run", type=int, required=True, help="the run in use (the Lots pages' default)")
    dr.add_argument("--to-run", type=int, required=True, help="the candidate run")
    dr.add_argument("--examples", type=int, default=20, help="unexplained moves to list")
    dr.add_argument("--out", type=Path, help="also write the report as markdown here")
    dr.add_argument("--dry-run", action="store_true")

    pr = sub.add_parser("promote", help="make a candidate copy the copy in use")
    pr.add_argument("--snapshot", type=int, required=True)
    pr.add_argument("--by", required=True, help='who: "Steph" or "agent, standing word 2026-09-19"')
    pr.add_argument("--override", default=None, help="promote over a standing gate, with this reason (Steph's call)")
    pr.add_argument("--dry-run", action="store_true")

    rb = sub.add_parser("rollback", help="put the previous copy back in use")
    rb.add_argument("--by", required=True)
    rb.add_argument("--reason", required=True)
    rb.add_argument("--dry-run", action="store_true")

    pn = sub.add_parser("prune", help="drop the lot rows of retired copies older than the most recent --keep")
    pn.add_argument("--keep", type=int, default=1, help="retired copies to keep whole (default 1: the one before the copy in use)")
    pn.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    engine = create_async_engine(args.db_url, echo=False, future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as session:
            if args.command == "status":
                return await _status(session)
            if args.command == "drift":
                return await _drift(session, args)
            if args.command == "promote":
                return await _promote(session, args)
            if args.command == "rollback":
                return await _rollback(session, args)
            return await _prune(session, args)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
