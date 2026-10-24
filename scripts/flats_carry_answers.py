"""Carry page-check answers and signing-inbox rows onto citations a re-cut moved.

An answer stands while its fingerprint matches the number, its citation and
its quote. A re-cut of the code text (``python -m flats.encode.recut``) moves
quotes without changing a word or a page -- it refuses any move that would --
so every answer standing on a moved quote would come back as if the number had
changed. The re-cut writes what moved to ``data/flats/carry/*.json``; this
appends, for each row standing on an old fingerprint, a copy on the new one.

Append-only, like every writer of these tables: the old rows stay, and simply
stop matching anything. Copies keep their reviewer and their ``decided_at`` --
the order of answers is what decides which one stands -- and a reply's
``reply:<id>`` is pointed at the copy of the row it answered.

Usage:

    uv run python scripts/flats_carry_answers.py data/flats/carry/2026-10-23.or.clackamas.tualatin.json
    uv run python scripts/flats_carry_answers.py data/flats/carry/... --write
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db import AsyncSessionLocal  # noqa: E402
from app.models.flats import FlatsPageCheck, FlatsRuleSignature  # noqa: E402

#: Copied from the source row unchanged.
_PAGE_CHECK = (
    "layer", "zone", "field", "when_key", "value", "question", "answer", "says", "note",
    "page", "placed", "book_sha256", "reviewer", "reviewer_user_id", "decided_at", "bundled_at",
)
_SIGNATURE = (
    "layer", "zone", "field", "when_key", "value", "cite", "verdict", "note", "reviewer",
    "reviewer_user_id", "decided_at", "shown", "shown_ref", "bundled_at",
)


async def carry(session, moves: list[dict]) -> tuple[list[FlatsPageCheck], list[FlatsRuleSignature]]:
    """Add the copies to ``session`` (flushed, not committed) and return them."""
    by_old = {m["old_fingerprint"]: m for m in moves}
    if not by_old:
        return [], []
    checks = list(
        (
            await session.execute(
                select(FlatsPageCheck)
                .where(FlatsPageCheck.fingerprint.in_(by_old))
                .order_by(FlatsPageCheck.id)
            )
        ).scalars()
    )
    new_checks: list[FlatsPageCheck] = []
    copied: dict[int, FlatsPageCheck] = {}
    for row in checks:
        move = by_old[row.fingerprint]
        if row.quote and row.quote != move["old_quote"]:
            continue  # shown under another quote; not this move's to carry
        copy = FlatsPageCheck(**{k: getattr(row, k) for k in _PAGE_CHECK})
        copy.fingerprint = move["new_fingerprint"]
        copy.quote = move["new_quote"]
        session.add(copy)
        await session.flush()
        copied[row.id] = copy
        new_checks.append(copy)
    for copy in new_checks:
        target = copy.question.removeprefix("reply:")
        if copy.question.startswith("reply:") and target.isdigit() and int(target) in copied:
            copy.question = f"reply:{copied[int(target)].id}"

    signatures = list(
        (
            await session.execute(
                select(FlatsRuleSignature)
                .where(FlatsRuleSignature.fingerprint.in_(by_old))
                .where(FlatsRuleSignature.exported_at.is_(None))
                .order_by(FlatsRuleSignature.id)
            )
        ).scalars()
    )
    new_signatures: list[FlatsRuleSignature] = []
    for row in signatures:
        move = by_old[row.fingerprint]
        if row.quote != move["old_quote"]:
            continue
        copy = FlatsRuleSignature(**{k: getattr(row, k) for k in _SIGNATURE})
        copy.fingerprint = move["new_fingerprint"]
        copy.quote = move["new_quote"]
        session.add(copy)
        new_signatures.append(copy)
    await session.flush()
    return new_checks, new_signatures


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", type=Path)
    parser.add_argument("--write", action="store_true", help="commit the copies (default: count only)")
    args = parser.parse_args()
    moves = json.loads(args.file.read_text(encoding="utf-8"))
    async with AsyncSessionLocal() as session:
        checks, signatures = await carry(session, moves)
        for c in checks:
            print(f"page check  {c.zone:18} {c.field:34} {c.question:14} {c.answer}")
        for s in signatures:
            print(f"signature   {s.zone:18} {s.field:34} {s.verdict}")
        print(
            f"{len(moves)} moved quotes; {len(checks)} page check row(s), {len(signatures)} "
            f"signature(s) {'carried' if args.write else 'would be carried (dry run)'}"
        )
        if args.write:
            await session.commit()
        else:
            await session.rollback()


if __name__ == "__main__":
    asyncio.run(main())
