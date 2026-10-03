"""Write approvals from the Unknowns page into flags.yaml and colour.yaml.

The screen reads its flag types and its colour rule from the repository. An
approval made at /flats/flags lands in ``flats.flag_decisions`` and is not in
force until it is here, in the files, committed -- the inbox bargain the word
rulings and the signatures already keep. This drain is the only writer of
``status: approved``: an agent proposes, a person approves, and the line in
the file says who and when.

It writes through ``flats.score.flags.decide_type`` / ``decide_rules``, which
edit the files line by line (the comments a person wrote stay put) and refuse
a decision the file would not load back exactly. Then the written file is read
back off disk, and only a file that holds every decision stamps any row: stamp
a row and lose the file, and the approval is gone with no error anywhere,
because a stamped row is never offered again.

Only the latest decision per kind is written. An owner who changes their mind
writes a second row; the earlier one is closed as superseded, never spliced in.

Usage::

    uv run python scripts/flats_drain_flag_decisions.py            # report
    uv run python scripts/flats_drain_flag_decisions.py --write    # write and stamp

    # inside the container, where the repository is rebuilt on every deploy --
    # both outputs on the bind mount, then copied over the repo files and
    # committed:
    python scripts/flats_drain_flag_decisions.py --write
        --registry-out /app/data/flats/flags.new.yaml
        --colour-out /app/data/flats/colour.new.yaml

The report ends with how many kinds are still waiting for approval; there is
no deadline on them (Steph 2026-10-03), the count is said at session start.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import settings  # noqa: E402
from app.models.flats import RULES_SUBJECT, FlatsFlagDecision  # noqa: E402
from flats.score import flags as fp  # noqa: E402


async def pending(session: AsyncSession) -> tuple[list[FlatsFlagDecision], list[FlatsFlagDecision]]:
    """Undrained decisions: the latest per subject, and the ones they supersede."""
    rows = list(
        (
            await session.execute(
                select(FlatsFlagDecision)
                .where(FlatsFlagDecision.exported_at.is_(None))
                .order_by(FlatsFlagDecision.decided_at, FlatsFlagDecision.id)
            )
        ).scalars()
    )
    latest: dict[str, FlatsFlagDecision] = {}
    for row in rows:
        latest[row.subject] = row
    keep = {row.id for row in latest.values()}
    return list(latest.values()), [row for row in rows if row.id not in keep]


def _land(path: Path, text: str) -> None:
    """Write ``text`` and prove it is what the file now holds.

    Raises rather than returning a flag: the caller's next act is to stamp
    rows, and there is no recovery from stamping against a write that did not
    land.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")
    if path.read_text(encoding="utf-8") != text:
        raise RuntimeError(f"{path}: the write did not land -- nothing stamped, run again")


async def drain(
    session: AsyncSession,
    *,
    write: bool,
    registry_path: Path = fp.REGISTRY_PATH,
    colour_path: Path = fp.COLOUR_PATH,
    registry_out: Path | None = None,
    colour_out: Path | None = None,
) -> int:
    registry_text = registry_path.read_text(encoding="utf-8")
    colour_text = colour_path.read_text(encoding="utf-8")
    rows, superseded = await pending(session)

    # Collected, then landed, then stamped: a refusal or a failed write
    # leaves the batch in the queue rather than half of it in limbo.
    drained: list[FlatsFlagDecision] = []
    refused = 0
    for row in rows:
        on = row.decided_at.date()
        try:
            if row.subject == RULES_SUBJECT:
                colour_text = fp.decide_rules(colour_text, row.values, by=row.decided_by, on=on)
            else:
                registry_text = fp.decide_type(
                    registry_text, row.subject, row.values, by=row.decided_by, on=on
                )
        except (ValueError, KeyError) as exc:
            # Left in the queue on purpose: the page validated it against the
            # files as they were, and something has changed since.
            print(f"REFUSED {row.subject}: {str(exc).splitlines()[0]}")
            refused += 1
            continue
        shown = ", ".join(f"{k}={v}" for k, v in row.values.items())
        print(f"APPROVE {row.subject}: {shown}  ({row.decided_by}, {on})")
        if row.note:
            print(f"    {row.note[:150]}")
        drained.append(row)

    if write and drained:
        subjects = {row.subject for row in drained}
        if subjects - {RULES_SUBJECT}:
            _land(registry_out or registry_path, registry_text)
        if RULES_SUBJECT in subjects:
            _land(colour_out or colour_path, colour_text)
        stamped = datetime.now(timezone.utc)
        for row in drained:
            row.exported_at = stamped
        # Closed with the batch, never written: their subject's later row is
        # the decision. Left open, the page would count them as waiting.
        closed = [row for row in superseded if row.subject in subjects]
        for row in closed:
            row.exported_at = stamped
        await session.commit()
        print()
        print(
            f"wrote {len(drained)} approval(s)"
            + (f", closed {len(closed)} superseded row(s)" if closed else "")
            + " -- read the diff, then commit it"
        )

    waiting = sum(t.status is fp.TypeStatus.pending for t in fp.parse_registry(registry_text))
    print()
    print(
        f"{len(drained)} approval(s), {refused} refused"
        + ("" if write else " -- dry run, nothing written")
    )
    print(f"{waiting} kind(s) of unknown still waiting for approval")
    return 0


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="write the files and stamp rows")
    parser.add_argument("--db-url", default=settings.database_url)
    parser.add_argument("--registry-out", type=Path, help="where flags.yaml goes (default: in place)")
    parser.add_argument("--colour-out", type=Path, help="where colour.yaml goes (default: in place)")
    args = parser.parse_args(argv)

    engine = create_async_engine(args.db_url, echo=False, future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as session:
            return await drain(
                session,
                write=args.write,
                registry_out=args.registry_out,
                colour_out=args.colour_out,
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
