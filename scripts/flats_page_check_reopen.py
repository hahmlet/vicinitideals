"""Put page-check questions back in the queue after a fix the fingerprint misses.

An answer stands while the number, its citation and its quote are unchanged.
Most of what a reviewer's "No" leads to changes none of those -- a box moved
to the right column, a footnote read that was not, a card reworded -- so the
answer would stand and the fix would never be looked at. This appends one
``reopened`` row per question (the history is append-only; nothing is
deleted), and the card asks it again, showing what was said before.

Only standing answers that raised something are reopened: "No", "the box is
wrong", "can't tell", and a footnote "we're missing it". A "Yes" stays done.

Usage:

    uv run python scripts/flats_page_check_reopen.py --layer or/clackamas/oregon-city            # dry run
    uv run python scripts/flats_page_check_reopen.py --layer or/clackamas/oregon-city --write
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.api.routers import ui_flats_check as check  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.models.flats import FlatsPageCheck  # noqa: E402

#: What a reopen puts back: answers that said something was wrong or unclear.
RAISED = frozenset({"differs", "wrong_box", "unclear", "missing"})


async def reopen(session, layer_id: str) -> list[FlatsPageCheck]:
    """The reopen rows for every standing answer in ``layer_id`` that raised something."""
    layer = check._layers()[layer_id]
    rows = {(r["zone"], r["field"], r["when"]): r for r in check._value_rows(layer)}
    answers = await check._answers(session, layer_id)
    out = []
    for (_layer, zone, field, when, question), answer in answers.items():
        row = rows.get((zone, field, when))
        if question.startswith("page:") or row is None or answer.answer not in RAISED:
            continue
        if check._standing(answer, row) is None:
            continue  # already back in the queue: the number or its quote moved
        out.append(
            FlatsPageCheck(
                layer=answer.layer,
                zone=zone,
                field=field,
                when_key=when,
                value=answer.value,
                fingerprint=answer.fingerprint,
                question=question,
                answer=check.REOPENED,
                says=answer.says,
                note=answer.answer,
                quote=answer.quote,
                page=answer.page,
                placed=answer.placed,
                book_sha256=answer.book_sha256,
                reviewer="reopen script",
            )
        )
    return out


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--layer", required=True)
    parser.add_argument("--write", action="store_true", help="append the rows (default: list only)")
    args = parser.parse_args()
    async with AsyncSessionLocal() as session:
        rows = await reopen(session, args.layer)
        for r in rows:
            print(f"reopen  {r.zone:18} {r.field:34} {r.when_key or '-':20} {r.question:10} was {r.note}")
        print(f"{len(rows)} question(s) {'reopened' if args.write else 'would be reopened (dry run)'}")
        if args.write and rows:
            session.add_all(rows)
            await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
