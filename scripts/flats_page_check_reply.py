"""Answer the problems a page-check reviewer raised.

A problem stays on the open list until something answers it: a fix moves the
fingerprint and the question comes back by itself, but a flag that was traced
and explained -- or fixed somewhere the fingerprint cannot see -- would stay
"open" forever. This appends one ``replied`` row per problem (the history is
append-only; nothing is deleted). The problem moves to the "Answered" list on
the page-check index, and the card shows the answer under the flag.

The replies file is JSON, the id of the row being answered to the words:

    {"169": "Point I is MUC-1's exemption, not MUC-2's ..."}

Usage:

    uv run python scripts/flats_page_check_reply.py --file replies.json            # dry run
    uv run python scripts/flats_page_check_reply.py --file replies.json --write
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

from app.api.routers import ui_flats_check as check  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.models.flats import FlatsPageCheck  # noqa: E402


async def replies(session, words: dict[int, str], reviewer: str) -> list[FlatsPageCheck]:
    """The reply rows for ``words``; refuses an id that is not a raised problem."""
    targets = {
        r.id: r
        for r in (
            await session.execute(select(FlatsPageCheck).where(FlatsPageCheck.id.in_(words)))
        ).scalars()
    }
    out = []
    for target_id, text in words.items():
        target = targets.get(target_id)
        if target is None or target.answer not in check.PROBLEMS:
            raise SystemExit(f"row {target_id} is not a problem raised: {target and target.answer}")
        out.append(
            FlatsPageCheck(
                layer=target.layer,
                zone=target.zone,
                field=target.field,
                when_key=target.when_key,
                value=target.value,
                fingerprint=target.fingerprint,
                question=f"reply:{target_id}",
                answer=check.REPLIED,
                says=target.says,
                note=text.strip(),
                quote=target.quote,
                page=target.page,
                placed=target.placed,
                book_sha256=target.book_sha256,
                reviewer=reviewer,
            )
        )
    return out


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--reviewer", default="page-check triage")
    parser.add_argument("--write", action="store_true", help="append the rows (default: list only)")
    args = parser.parse_args()
    words = {int(k): v for k, v in json.loads(args.file.read_text(encoding="utf-8")).items()}
    async with AsyncSessionLocal() as session:
        rows = await replies(session, words, args.reviewer)
        for r in rows:
            print(f"reply  {r.question:12} {r.zone:18} {r.field:34} {r.note[:70]}")
        print(f"{len(rows)} repl(ies) {'written' if args.write else 'would be written (dry run)'}")
        if args.write and rows:
            session.add_all(rows)
            await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
