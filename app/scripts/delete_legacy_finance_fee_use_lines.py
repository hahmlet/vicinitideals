"""One-shot cleanup: delete legacy per-fee UseLines.

Before migration 0093 the cashflow engine wrote multiple UseLine rows per
loan ("Construction Loan — Origination Fee", "Permanent Debt — Lender
Legal", etc.) via the old _DEFAULT_LOAN_COSTS table.  The new engine writes
ONE "{module.label} — Total Finance Costs" row per CapitalModule with
is_auto_finance_cost=True.

This script deletes the legacy rows so the next compute pass starts clean.
Run once after deploying migration 0093 + engine rewrite.

Dry-run by default; pass --apply to delete.

    python -m app.scripts.delete_legacy_finance_fee_use_lines
    python -m app.scripts.delete_legacy_finance_fee_use_lines --apply
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import delete, select

from app.db import AsyncSessionLocal
from app.models.deal import UseLine

# Legacy per-fee suffixes that the old engine wrote (one per fee).
# The new format is " — Total Finance Costs" (singular row per module).
_LEGACY_FEE_SUFFIXES: tuple[str, ...] = (
    " — Origination Fee",
    " — Lender Legal",
    " — Title / Survey",
    " — Title",
    " — Appraisal",
    " — Environmental Phase I",
    " — Bond Issuance Fee",
    " — Bond Counsel Legal",
)


async def _main(apply: bool) -> None:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(UseLine))).scalars().all()
        matched = [
            r for r in rows
            if any((r.label or "").endswith(s) for s in _LEGACY_FEE_SUFFIXES)
        ]
        print(f"Scanned {len(rows)} use_lines; {len(matched)} match legacy finance-fee labels.")
        by_label: dict[str, int] = {}
        for r in matched:
            by_label[r.label] = by_label.get(r.label, 0) + 1
        for lbl, n in sorted(by_label.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>4} × {lbl!r}")

        if not matched:
            print("Nothing to delete.")
            return

        if apply:
            ids = [r.id for r in matched]
            await session.execute(delete(UseLine).where(UseLine.id.in_(ids)))
            await session.commit()
            print(f"DELETED {len(ids)} rows.")
        else:
            print("DRY RUN (no commit).  Re-run with --apply to delete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually delete rows.")
    args = parser.parse_args()
    asyncio.run(_main(apply=args.apply))
