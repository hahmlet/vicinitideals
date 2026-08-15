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

Usage:

    uv run python scripts/flats_drain_signatures.py            # dry run
    uv run python scripts/flats_drain_signatures.py --write    # write and stamp
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


async def drain(session: AsyncSession, *, write: bool) -> int:
    layers = load_rules(strict=False)
    log = VerificationLog.load()
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

    signed = rejected = stale = 0
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
            entry = sign(
                row.layer,
                row.zone,
                row.field,
                value,
                reviewer=row.reviewer,
                reviewed=row.decided_at.date() if row.decided_at else date.today(),
                note=row.note,
                when=tuple(row.when_key.split("+")) if row.when_key else (),
            )
            print(f"SIGN    {where} = {row.value} ({row.reviewer})")
            if write:
                log.append(entry)
            signed += 1
        else:
            print(f"REJECT  {where} = {row.value} ({row.reviewer}) {row.note}")
            if write:
                REJECTIONS.parent.mkdir(parents=True, exist_ok=True)
                with REJECTIONS.open("a", encoding="utf-8", newline="") as fh:
                    fh.write(
                        json.dumps(
                            {
                                "layer": row.layer,
                                "zone": row.zone,
                                "field": row.field,
                                "when": row.when_key,
                                "value": row.value,
                                "quote": row.quote,
                                "reviewer": row.reviewer,
                                "decided": row.decided_at.isoformat(),
                                "note": row.note,
                            }
                        )
                        + "\n"
                    )
            rejected += 1

        if write:
            row.exported_at = datetime.now(timezone.utc)

    if write:
        await session.commit()
    print(
        f"\n{signed} signature(s), {rejected} rejection(s), {stale} stale"
        + ("" if write else " — dry run, nothing written")
    )
    return 0


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write and stamp rows")
    parser.add_argument("--db-url", default=settings.database_url)
    args = parser.parse_args(argv)

    engine = create_async_engine(args.db_url, echo=False, future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as session:
            return await drain(session, write=args.write)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
