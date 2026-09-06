"""Write word-review decisions from the review inbox into the rule files.

Rules load from the repository. A decision made in a browser lands in
``flats.word_rulings`` and has not taken effect until it is here, in a
jurisdiction YAML, committed — the container rebuilds those files from git on
every deploy, so the database is the only place a decision can survive the trip
and the repository is the only place it can bind.

The direction is the safe one. An undrained row is visible in the queue as
"decided, not yet in force"; a row drained but uncommitted shows up as a dirty
working tree. Neither state is silent.

Run it::

    uv run python scripts/flats_drain_word_rulings.py            # report
    uv run python scripts/flats_drain_word_rulings.py --write    # and write
    uv run python scripts/flats_drain_word_rulings.py --layer or/multnomah/gresham

Then read the diff and commit it. Deliberately not automated past this point:
the rulings are prose that goes into a file full of hand-written prose, and a
person should look at it before it becomes history.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db import AsyncSessionLocal  # noqa: E402
from app.models.flats import FlatsWordRuling  # noqa: E402
from flats.encode.words import rule  # noqa: E402


async def pending(
    session: AsyncSession, layer: str | None = None
) -> list[FlatsWordRuling]:
    """Undrained decisions, oldest first, latest-per-card only.

    A reviewer who changes their mind writes a second row. Draining both would
    splice the superseded reasoning into the file and then overwrite it, which
    leaves the right answer in place and the wrong one in the git history
    looking like a considered edit.
    """
    stmt = select(FlatsWordRuling).where(FlatsWordRuling.exported_at.is_(None))
    if layer:
        stmt = stmt.where(FlatsWordRuling.layer == layer)
    rows = list(
        (await session.execute(stmt.order_by(FlatsWordRuling.decided_at)))
        .scalars()
        .all()
    )
    latest: dict[tuple[str, str], FlatsWordRuling] = {}
    for row in rows:
        latest[(row.layer, row.term)] = row
    return list(latest.values())


async def drain(layer: str | None, write: bool) -> int:
    async with AsyncSessionLocal() as session:
        rows = await pending(session, layer)
        if not rows:
            print("nothing pending")
            return 0

        superseded = 0
        for row in rows:
            print(
                f"{row.layer}  {row.term!r}  [{row.standing}/{row.outcome}]  "
                f"by {row.decided_by}"
            )
            print(f"    {row.note[:150]}")
            if not write:
                continue
            try:
                path = rule(
                    row.layer,
                    row.term,
                    row.standing,
                    row.outcome,
                    row.note,
                    row.fingerprint or "",
                )
            except (ValueError, FileNotFoundError) as exc:
                print(f"    REFUSED: {exc}")
                continue
            print(f"    -> {path}")
            row.exported_at = datetime.now(timezone.utc)

        if write:
            # Stamp the superseded rows too. They were never written, and
            # leaving them pending means the queue reports work outstanding
            # that draining again would not do.
            stale = select(FlatsWordRuling).where(FlatsWordRuling.exported_at.is_(None))
            if layer:
                stale = stale.where(FlatsWordRuling.layer == layer)
            keep = {r.id for r in rows}
            for row in (await session.execute(stale)).scalars().all():
                if row.id not in keep:
                    row.exported_at = datetime.now(timezone.utc)
                    superseded += 1
            await session.commit()
            print(
                f"\nwrote {len(rows)} ruling(s)"
                + (f", {superseded} superseded row(s) closed" if superseded else "")
                + "\nread the diff, then commit it"
            )
        else:
            print(f"\n{len(rows)} pending — re-run with --write to apply")
        return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--layer")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    return asyncio.run(drain(args.layer, args.write))


if __name__ == "__main__":
    raise SystemExit(main())
