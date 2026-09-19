"""Register a county map snapshot with the app, or list the ones it knows.

The acquire stage (``flats/ingest/acquire.py``) leaves a dated directory and a
manifest on the analysis box. The app knows nothing about it until this
script registers the manifest as a ``flats.snapshots`` row -- the row the
loader points lot rows at, the monthly probe compares against, and the Lots
pages name in their footer. Registering is bookkeeping: no lot moves.

A new snapshot is registered as a ``candidate``. ``--status current`` is for a
database with no copy in use yet (the first registration, a rebuilt
database); once a copy is in use, a candidate becomes current by promotion,
not by re-registering it. Re-registering an existing (date, host) pair
updates its manifest and counts -- the way to record a second acquire pass
that filled a hole.

Usage (inside the api container, where the manifest was copied to
``/app/data/flats/sources/<date>/manifest.json``):

    python scripts/flats_snapshot.py register \\
        --manifest /app/data/flats/sources/2026-09-18/manifest.json \\
        --host 137 --status candidate [--notes "..."] [--dry-run]
    python scripts/flats_snapshot.py report --snapshot 3 --section delta         --summary /app/data/flats/deltas/2026-09-18/summary.json
    python scripts/flats_snapshot.py list

``report`` stores one section of the snapshot's report -- the delta summary
``flats.ingest.delta`` wrote (``load-changes`` in the bridge loader carries
the rows themselves) -- on the row, where the promotion page reads it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import settings  # noqa: E402
from app.models.flats import FlatsSnapshot  # noqa: E402
from app.services.flats_refresh import REGISTERABLE, RegisterError, attach_report, register_snapshot  # noqa: E402


async def _register(session: AsyncSession, args: argparse.Namespace) -> int:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    try:
        row = await register_snapshot(
            session, manifest, host=args.host, status=args.status, notes=args.notes or ""
        )
    except RegisterError as exc:
        print(f"refused: {exc}")
        return 2
    by_status = ", ".join(f"{k} {v}" for k, v in sorted(row.counts.get("by_status", {}).items()))
    print(
        f"snapshot {row.id}: {row.snapshot_date.isoformat()} on {row.host}, {row.status}, "
        f"RLIS {row.rlis_release or '?'}, {row.counts.get('features', 0):,} features ({by_status})"
    )
    if args.dry_run:
        await session.rollback()
        print("dry run, rolled back")
    else:
        await session.commit()
    return 0


async def _report(session: AsyncSession, args: argparse.Namespace) -> int:
    doc = json.loads(args.summary.read_text(encoding="utf-8"))
    try:
        row = await attach_report(session, args.snapshot, args.section, doc)
    except RegisterError as exc:
        print(f"refused: {exc}")
        return 1
    keys = ", ".join(sorted(row.report))
    print(f"snapshot {row.id}: {row.snapshot_date.isoformat()} on {row.host}, {row.status}; report sections: {keys}")
    if args.section == "delta":
        print(
            f"  delta {doc.get('from')} -> {doc.get('to')}: {doc.get('rows', 0):,} rows, "
            f"{doc.get('unchanged', 0):,} unchanged, {doc.get('rereview', 0):,} for re-review; "
            f"by kind {doc.get('by_kind')}"
        )
        check = doc.get("crosscheck") or {}
        if check:
            print(f"  against Metro's list: min recall {check.get('min_recall')}, {'agree' if check.get('agrees') else 'DISAGREE'}")
    if args.dry_run:
        await session.rollback()
        print("dry run, rolled back")
    else:
        await session.commit()
    return 0


async def _list(session: AsyncSession) -> int:
    rows = (
        await session.execute(select(FlatsSnapshot).order_by(FlatsSnapshot.snapshot_date.desc()))
    ).scalars().all()
    if not rows:
        print("no snapshots registered")
        return 0
    for row in rows:
        print(
            f"{row.id:>4}  {row.snapshot_date.isoformat()}  {row.host:<6} {row.status:<10} "
            f"RLIS {row.rlis_release or '?':<8} {row.counts.get('features') or row.counts.get('lots') or 0:>10,}  "
            f"{(row.notes or '')[:60]}"
        )
    return 0


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-url", default=settings.database_url)
    sub = parser.add_subparsers(dest="command", required=True)

    reg = sub.add_parser("register", help="upsert a flats.snapshots row from an acquire manifest")
    reg.add_argument("--manifest", type=Path, required=True)
    reg.add_argument("--host", required=True, help="where the files live (137 for the analysis box)")
    reg.add_argument("--status", choices=REGISTERABLE, default="candidate")
    reg.add_argument("--notes", default="")
    reg.add_argument("--dry-run", action="store_true")

    rep = sub.add_parser("report", help="store one section of a snapshot's report (a delta summary.json)")
    rep.add_argument("--snapshot", type=int, required=True, help="flats.snapshots id the report is about")
    rep.add_argument("--section", default="delta", choices=("delta", "drift"))
    rep.add_argument("--summary", type=Path, required=True, help="the JSON document to store under that section")
    rep.add_argument("--dry-run", action="store_true")

    sub.add_parser("list", help="every registered snapshot, newest first")
    args = parser.parse_args(argv)

    engine = create_async_engine(args.db_url, echo=False, future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as session:
            if args.command == "register":
                return await _register(session, args)
            if args.command == "report":
                return await _report(session, args)
            return await _list(session)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
