"""Move browser review verdicts out of the database and into the repository.

A reviewer confirming a standard on ``/flats`` writes a row to
``flats.rule_signatures``. That row is not trust: rules load from
``flats/config/verifications.jsonl``, whose entries are hashed over the value
and its citation so that editing either silently withdraws the signature. A
database row has no such property — it would keep certifying a number after
somebody changed it.

So this script is the bridge, and it re-checks rather than copies. For each
confirmation it re-reads the value from the rule files and compares what is
there now against what the reviewer was shown. If they differ the row is left in
the queue and reported: the reviewer confirmed a number that no longer exists,
and the right answer is another look, not a signature.

Rejections are the other half of a review — the number does not match the line
it cites — and they go to ``flats/config/review_rejections.jsonl`` so the
encoder has a work list and the record survives outside the database.

There is one hazard worth naming, because it destroys work silently. Stamping a
row ``exported`` and writing its line are two writes, and in production they land
in different places: the database is a named volume that survives everything,
while the container's filesystem is rebuilt on the next deploy. Stamp the rows,
lose the file, and the reviewer's afternoon is gone with no error anywhere — the
rows will never be offered again. So the lines are written first, read back, and
only a file that actually contains them is allowed to stamp anything. Point
``--log`` and ``--rejections`` at the bind-mounted ``/app/data`` when draining
inside the container, and commit what lands there.

Usage:

    uv run python scripts/flats_drain_signatures.py            # dry run
    uv run python scripts/flats_drain_signatures.py --write    # write and stamp

    # inside the container, where the repository is not writable — both paths
    # are on the bind mount, so what lands there survives the next deploy:
    python scripts/flats_drain_signatures.py --write
        --log /app/data/flats/verifications.new.jsonl
        --rejections /app/data/flats/rejections.new.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import settings  # noqa: E402
from app.models.flats import FlatsRuleSignature  # noqa: E402
from flats.encode.verify import (  # noqa: E402
    LOG_PATH,
    VerificationLog,
    sign,
    variant_for,
)
from flats.rules.loader import load_rules  # noqa: E402

#: Where a rejected value goes. Not the verification log: nothing was verified,
#: and an entry there would have to lie about what happened.
REJECTIONS = LOG_PATH.parent / "review_rejections.jsonl"


def _current(layers, row: FlatsRuleSignature):
    """The standard this row is about and the exact number under review.

    Two things, because they are different: a signature is built from the whole
    value (the log addresses a variant through it), while the staleness check is
    against the one number the reviewer actually read.
    """
    layer = layers.get(row.layer)
    if layer is None:
        return None, None
    if row.zone.startswith("("):
        values = layer.defaults
    else:
        zone = layer.zones.get(row.zone)
        if zone is None:
            return None, None
        values = zone.values
    value = values.get(row.field)
    if value is None:
        return None, None
    if not row.when_key:
        return value, value
    try:
        return value, variant_for(value, row.when_key.split("+"))
    except (KeyError, ValueError):
        return value, None


def _matches(row: FlatsRuleSignature, number) -> bool:
    """Whether the file still says what the reviewer was shown.

    Compared through JSON so a 15 stored as an int and a 15.0 read back as a
    float are the same number — the reviewer read "15" either way.
    """
    return (
        json.dumps(number.value, sort_keys=True) == json.dumps(row.value, sort_keys=True)
        and number.prov.cite == row.cite
        and (number.prov.quote or "") == row.quote
    )


def _land(
    entries: list, rejections: list[dict], log_path: Path, rejections_path: Path
) -> None:
    """Write both files and prove the lines are in them.

    Raises rather than returning a flag, because the caller's next act is to
    stamp rows ``exported`` and there is no recovery from doing that against a
    write that did not land. A full disk, a read-only mount and a path inside a
    container that is about to be rebuilt all fail here instead of there.
    """
    for path, lines in (
        (log_path, [e.to_json() for e in entries]),
        (rejections_path, [json.dumps(r) for r in rejections]),
    ):
        if not lines:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="") as fh:
            fh.writelines(line + "\n" for line in lines)
        landed = path.read_text(encoding="utf-8")
        missing = [line for line in lines if line not in landed]
        if missing:
            raise RuntimeError(
                f"{path}: {len(missing)} of {len(lines)} line(s) did not land — "
                "nothing has been stamped, so this can be run again"
            )


async def drain(
    session: AsyncSession,
    *,
    write: bool,
    log_path: Path | None = None,
    rejections_path: Path | None = None,
) -> int:
    layers = load_rules(strict=False)
    log = log_path or LOG_PATH
    rejects = rejections_path or REJECTIONS
    rows = list(
        (
            await session.execute(
                select(FlatsRuleSignature)
                .where(FlatsRuleSignature.exported_at.is_(None))
                .order_by(FlatsRuleSignature.decided_at)
            )
        ).scalars()
    )
    if not rows:
        print("nothing pending")
        return 0

    # Collected rather than written as we go: a row is stamped only after its
    # line is on disk, so a failure halfway through leaves the whole batch in
    # the queue instead of half of it in limbo.
    entries, rejections, drained = [], [], []
    stale = 0
    for row in rows:
        value, number = _current(layers, row)
        where = f"{row.layer} {row.zone} {row.field}"
        if row.when_key:
            where += f" [{row.when_key}]"
        if number is None or not _matches(row, number):
            # Left in the queue on purpose. The reviewer confirmed something
            # that is no longer there, and a signature over it would certify
            # text nobody read.
            print(f"STALE   {where}: the file no longer states what was reviewed")
            stale += 1
            continue

        if row.verdict == "verified":
            entries.append(
                sign(
                    row.layer,
                    row.zone,
                    row.field,
                    value,
                    reviewer=row.reviewer,
                    reviewed=row.decided_at.date() if row.decided_at else date.today(),
                    note=row.note,
                    when=tuple(row.when_key.split("+")) if row.when_key else (),
                )
            )
            print(f"SIGN    {where} = {row.value} ({row.reviewer})")
        else:
            rejections.append(
                {
                    "layer": row.layer,
                    "zone": row.zone,
                    "field": row.field,
                    "when": row.when_key,
                    "value": row.value,
                    "quote": row.quote,
                    "reviewer": row.reviewer,
                    "decided": row.decided_at.isoformat() if row.decided_at else "",
                    "note": row.note,
                }
            )
            print(f"REJECT  {where} = {row.value} ({row.reviewer}) {row.note}")
        drained.append(row)

    if write and drained:
        _land(entries, rejections, log, rejects)
        stamped = datetime.now(timezone.utc)
        for row in drained:
            row.exported_at = stamped
        await session.commit()
        if entries:
            print()
            print(f"{len(entries)} signature(s) -> {log}")
        if rejections:
            print(f"{len(rejections)} rejection(s) -> {rejects}")
        print("commit those file(s): the rows are stamped and will not be offered again")

    print()
    print(
        f"{len(entries)} signature(s), {len(rejections)} rejection(s), {stale} stale"
        + ("" if write else " — dry run, nothing written")
    )
    return 0


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write and stamp rows")
    parser.add_argument("--db-url", default=settings.database_url)
    parser.add_argument(
        "--log",
        type=Path,
        default=LOG_PATH,
        help="where signatures go — point at a bind mount when run in a container",
    )
    parser.add_argument("--rejections", type=Path, default=REJECTIONS)
    args = parser.parse_args(argv)

    engine = create_async_engine(args.db_url, echo=False, future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as session:
            return await drain(
                session,
                write=args.write,
                log_path=args.log,
                rejections_path=args.rejections,
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
