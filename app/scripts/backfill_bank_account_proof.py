"""One-time backfill: populate ``operational_outputs.bank_account_proof`` on
existing scenarios by recomputing each scenario's cash flows.

Migration ``0102`` added the ``bank_account_proof`` JSON column with NULL on
every existing row. The engine writes the proof unconditionally on each
``compute_cash_flows`` call, but pre-existing scenarios will not have their
proof populated until they are recomputed. This script walks every active
Scenario, runs ``compute_cash_flows`` once, and commits.

Notes:
- The bank-account auto-emission feature flag ``BANK_ACCOUNT_RESERVE_ENABLED``
  has no effect on the proof persistence path. Whether the flag is on or off,
  the engine still writes ``OperationalOutputs.bank_account_proof``. This
  script therefore does not need the flag enabled to backfill.
- Recomputation is the canonical compute_cash_flows path. It re-runs the
  full engine including auto-sized debt / reserves; existing scenarios may
  see incidental numeric drift if their persisted outputs were stale relative
  to current engine code. That drift is what /compute would have produced on
  the next user click anyway.
- Soft-deleted scenarios (``Scenario.is_active = False``) are skipped.
- Test deals are skipped using the same filter as the deals/opportunities
  UI (``hide_test``): name ILIKE '%e2e%' OR name matching the regex
  ``phase\s+\w+\s+test\s+\w+`` (case-insensitive). Pass ``--include-test``
  to override.
- One commit per scenario so partial failures don't roll back successful
  scenarios.

Run:
    uv run python app/scripts/backfill_bank_account_proof.py                  # dry run
    uv run python app/scripts/backfill_bank_account_proof.py --apply           # commit
    uv run python app/scripts/backfill_bank_account_proof.py --scenario-id X   # one deal
    uv run python app/scripts/backfill_bank_account_proof.py --apply --limit 5 # first N
"""

from __future__ import annotations

import argparse
import asyncio
import traceback
import uuid
from dataclasses import dataclass

from sqlalchemy import not_, select

from app.db import AsyncSessionLocal
from app.engines.cashflow import compute_cash_flows
from app.models.deal import Scenario


# Test-deal filter — mirrors the ``hide_test`` clause in
# ``app/api/routers/ui.py`` (lines ~426-430 and ~3633-3637). Any change there
# should be mirrored here so the backfill skips the same fixture rows.
_TEST_NAME_REGEX = r"phase\s+\w+\s+test\s+\w+"


@dataclass
class _Outcome:
    scenario_id: uuid.UUID
    succeeded: bool
    has_proof: bool
    is_solvent: bool | None
    max_shortfall: str | None
    error: str | None


async def _process_scenario(
    scenario_id: uuid.UUID,
    *,
    apply: bool,
) -> _Outcome:
    """Recompute a single scenario in its own session. Returns outcome record."""
    async with AsyncSessionLocal() as session:
        try:
            result = await compute_cash_flows(deal_model_id=scenario_id, session=session)
        except Exception as exc:
            return _Outcome(
                scenario_id=scenario_id,
                succeeded=False,
                has_proof=False,
                is_solvent=None,
                max_shortfall=None,
                error=f"{type(exc).__name__}: {exc}",
            )

        proof = result.get("bank_account_proof") if isinstance(result, dict) else None
        has_proof = isinstance(proof, dict)
        is_solvent = proof.get("is_solvent") if has_proof else None
        max_shortfall = str(proof.get("max_shortfall")) if has_proof else None

        if apply:
            await session.commit()
        else:
            await session.rollback()

        return _Outcome(
            scenario_id=scenario_id,
            succeeded=True,
            has_proof=has_proof,
            is_solvent=is_solvent,
            max_shortfall=max_shortfall,
            error=None,
        )


async def run(
    *,
    apply: bool,
    scenario_id: uuid.UUID | None,
    limit: int | None,
    include_test: bool,
) -> None:
    # Collect target scenario IDs in a short-lived session, then process each
    # in its own session to keep commit boundaries clean.
    async with AsyncSessionLocal() as session:
        stmt = select(Scenario.id).where(Scenario.is_active.is_(True))
        if not include_test:
            stmt = stmt.where(
                not_(Scenario.name.ilike("%e2e%"))
                & not_(Scenario.name.op("~*")(_TEST_NAME_REGEX))
            )
        if scenario_id is not None:
            stmt = stmt.where(Scenario.id == scenario_id)
        stmt = stmt.order_by(Scenario.id)
        if limit is not None:
            stmt = stmt.limit(limit)
        ids = list((await session.execute(stmt)).scalars())

    if not ids:
        print("No active scenarios match the filter — nothing to do.")
        return

    print(f"Targeting {len(ids)} scenario(s). Mode: {'APPLY' if apply else 'DRY-RUN'}")

    outcomes: list[_Outcome] = []
    for idx, sid in enumerate(ids, start=1):
        outcome = await _process_scenario(sid, apply=apply)
        outcomes.append(outcome)

        if outcome.error:
            print(f"[{idx}/{len(ids)}] {sid} — FAILED: {outcome.error}")
        elif outcome.has_proof:
            label = "SOLVENT" if outcome.is_solvent else f"SHORTFALL ${outcome.max_shortfall}"
            print(f"[{idx}/{len(ids)}] {sid} — proof: {label}")
        else:
            print(f"[{idx}/{len(ids)}] {sid} — no proof window (construction-only or no anchor)")

    # ── Summary ────────────────────────────────────────────────────────────
    total = len(outcomes)
    failed = sum(1 for o in outcomes if not o.succeeded)
    succeeded = total - failed
    with_proof = sum(1 for o in outcomes if o.has_proof)
    solvent = sum(1 for o in outcomes if o.has_proof and o.is_solvent)
    shortfall = sum(1 for o in outcomes if o.has_proof and o.is_solvent is False)

    print()
    print("=" * 60)
    print(f"Total scenarios processed:  {total}")
    print(f"  succeeded:                {succeeded}")
    print(f"  failed:                   {failed}")
    print(f"  with proof window:        {with_proof}")
    print(f"    solvent:                {solvent}")
    print(f"    shortfall:              {shortfall}")
    print(f"  no proof window:          {succeeded - with_proof}")
    print("=" * 60)
    if not apply:
        print("DRY-RUN — no changes committed. Re-run with --apply to persist.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit changes (default: dry-run)")
    parser.add_argument(
        "--scenario-id",
        type=lambda s: uuid.UUID(s),
        default=None,
        help="Process a single scenario by UUID instead of all scenarios.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N scenarios (sorted by id).",
    )
    parser.add_argument(
        "--include-test",
        action="store_true",
        help="Include test/E2E deals (default: skip them, matches UI hide_test filter).",
    )
    args = parser.parse_args()

    try:
        asyncio.run(
            run(
                apply=args.apply,
                scenario_id=args.scenario_id,
                limit=args.limit,
                include_test=args.include_test,
            )
        )
    except KeyboardInterrupt:
        print("\nInterrupted — partial results may be committed if --apply was set.")
    except Exception:
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
