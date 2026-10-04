"""Flag history and the review queue from the command line (FOLLOWUPS 37 item 4).

``sync`` brings ``flats.flag_instances`` in line with a run -- by default the
run in use -- the same call the nightly task makes; run it right after a
promotion rather than waiting for the night. ``ask`` is the agent's one way
to put a question to the next review session: it names a registered flag
type and a key that fills it, and the question appears on
``/flats/flags/questions``. ``questions`` lists what is waiting and what was
answered. ``check`` runs the nightly check and the pod width report now
(item 5) and prints what failed.

Usage::

    uv run python scripts/flats_flags.py sync [--run 64]
    uv run python scripts/flats_flags.py check
    uv run python scripts/flats_flags.py ask --code FACT-CORNER-LOT \\
        --key "or/multnomah/gresham|corner_lot" --by "agent 2026-10-04" \\
        --question "Does Gresham count a lot on a curve as a corner?"
    uv run python scripts/flats_flags.py questions
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import settings  # noqa: E402
from app.services import flats_flags  # noqa: E402


async def run(session: AsyncSession, args: argparse.Namespace) -> int:
    if args.command == "sync":
        got = await flats_flags.sync_instances(session, args.run)
        await session.commit()
        if got.skipped:
            print(f"nothing synced: {got.skipped}")
            return 1
        print(f"run {got.run_id}: {got.opened:,} opened, {got.updated:,} updated, {got.cleared:,} cleared")
        return 0
    if args.command == "check":
        row = await flats_flags.nightly_check(session)
        await session.commit()
        r = row.report
        print(f"run {row.run_id}: {'passed' if row.ok else 'needs a look'} -- {r.get('rows', 0):,} rows")
        for name in ("skipped", "moved", "incomplete", "unregistered_instances"):
            if r.get(name):
                print(f"  {name}: {r[name]}")
        return 0 if row.ok else 1
    if args.command == "ask":
        try:
            row = await flats_flags.ask(session, code=args.code, key=args.key, question=args.question, by=args.by)
        except flats_flags.FlagWriteError as exc:
            print(f"refused: {exc}")
            return 2
        await session.commit()
        print(f"question {row.id} waiting on /flats/flags/questions")
        return 0
    for answered in (False, True):
        rows = await flats_flags.questions(session, answered=answered)
        print("Answered" if answered else "Waiting", f"({len(rows)})")
        for item in rows:
            q = item["row"]
            lots = ", ".join(f"{n:,} {c}" for c, n in sorted(item["lots"].items())) or "no open lots"
            print(f"  #{q.id} {q.code} {q.key} [{lots}] -- {q.question}")
            if q.answer:
                print(f"      {q.answered_by}: {q.answer}")
    return 0


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db-url", default=settings.database_url)
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync", help="open and clear flag instances against a run")
    sync.add_argument("--run", type=int, default=None, help="the run (default: the run in use)")
    sub.add_parser("check", help="run the nightly check and the pod width report now")
    ask = sub.add_parser("ask", help="put a question on a flag's key to the next review session")
    ask.add_argument("--code", required=True)
    ask.add_argument("--key", required=True)
    ask.add_argument("--question", required=True)
    ask.add_argument("--by", required=True)
    sub.add_parser("questions", help="list the waiting and the answered questions")
    args = parser.parse_args(argv)

    engine = create_async_engine(args.db_url, echo=False, future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as session:
            return await run(session, args)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
