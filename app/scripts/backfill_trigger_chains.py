"""One-time backfill: wire ``trigger_milestone_id`` on legacy milestones.

Pre-``5d5caf4`` the timeline wizard created every non-anchor milestone with
``target_date=None`` AND ``trigger_milestone_id=None``. ``Milestone.computed_start``
returns ``None`` for those rows, so ``_milestone_dates_from_orm`` cannot build
phase windows and the cashflow engine falls back to ``OperationalInputs.*_months``
(NULL on wizard deals → 1-month-per-phase defaults). Phase B carry, lease-up,
reserve math all collapse.

Backfill rule (mirrors the Pass-2 logic in ``timeline_wizard_submit``):

For each timeline (group of milestones sharing the same ``opportunity_id`` or
``project_id``):

1. Find the anchor — the single milestone with ``target_date IS NOT NULL``.
   Skip the group if zero or >1 anchors exist (ambiguous — needs manual review).
2. Sort the remaining milestones by canonical ``MilestoneType`` order.
3. For each non-anchor row with ``trigger_milestone_id IS NULL``, set it to
   the previous row in the sorted sequence (anchor for the first non-anchor).
   ``trigger_offset_days`` stays at the existing default (0).
4. Rows that already have ``trigger_milestone_id`` set are left alone.

Run:
    uv run python app/scripts/backfill_trigger_chains.py            # dry run
    uv run python app/scripts/backfill_trigger_chains.py --apply    # commit
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from collections import defaultdict

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.milestone import Milestone, MilestoneType

# Canonical phase order (matches enum declaration in app/models/milestone.py).
_CANONICAL_ORDER: list[MilestoneType] = [
    MilestoneType.offer_made,
    MilestoneType.under_contract,
    MilestoneType.close,
    MilestoneType.pre_development,
    MilestoneType.construction,
    MilestoneType.operation_lease_up,
    MilestoneType.operation_stabilized,
    MilestoneType.divestment,
]
_ORDER_RANK: dict[MilestoneType, int] = {mt: i for i, mt in enumerate(_CANONICAL_ORDER)}


def _group_key(m: Milestone) -> tuple[str, uuid.UUID]:
    if m.project_id is not None:
        return ("project", m.project_id)
    if m.opportunity_id is not None:
        return ("opportunity", m.opportunity_id)
    return ("orphan", m.id)


async def run(apply: bool) -> None:
    groups_total = 0
    groups_already_chained = 0
    groups_no_anchor = 0
    groups_multi_anchor = 0
    groups_orphan = 0
    groups_patched = 0
    rows_patched = 0

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(select(Milestone))
        ).scalars().all()

        groups: dict[tuple[str, uuid.UUID], list[Milestone]] = defaultdict(list)
        for m in rows:
            groups[_group_key(m)].append(m)

        groups_total = len(groups)

        for key, members in sorted(groups.items(), key=lambda kv: str(kv[0])):
            kind, parent_id = key

            if kind == "orphan":
                groups_orphan += len(members)
                continue

            anchors = [m for m in members if m.target_date is not None]
            if len(anchors) == 0:
                groups_no_anchor += 1
                print(f"[skip] {kind}={parent_id} — no anchor (no target_date set)")
                continue
            if len(anchors) > 1:
                groups_multi_anchor += 1
                anchor_types = ", ".join(a.milestone_type.value for a in anchors)
                print(f"[skip] {kind}={parent_id} — {len(anchors)} anchors ({anchor_types})")
                continue

            missing = [
                m for m in members
                if m.target_date is None and m.trigger_milestone_id is None
            ]
            if not missing:
                groups_already_chained += 1
                continue

            ordered = sorted(
                members,
                key=lambda m: _ORDER_RANK.get(m.milestone_type, 999),
            )

            prev: Milestone | None = None
            patched_here = 0
            for m in ordered:
                if m.target_date is not None:
                    prev = m
                    continue
                if m.trigger_milestone_id is not None:
                    prev = m
                    continue
                if prev is None:
                    # No predecessor in canonical order yet (e.g. milestones
                    # exist that sort before the anchor). Leave it — it has
                    # nothing to chain off and isn't covered by the wizard
                    # Pass-2 invariant.
                    continue
                print(
                    f"[patch] {kind}={parent_id} "
                    f"milestone={m.milestone_type.value} ({m.id}) "
                    f"→ trigger={prev.milestone_type.value} ({prev.id})"
                )
                if apply:
                    m.trigger_milestone_id = prev.id
                patched_here += 1
                rows_patched += 1
                prev = m

            if patched_here:
                groups_patched += 1

        if apply and rows_patched:
            await session.commit()
            print(f"\nCOMMITTED {rows_patched} row updates.")
        else:
            print(f"\nDRY RUN — no changes written.")

    print("\n=== summary ===")
    print(f"timeline groups total       : {groups_total}")
    print(f"  already fully chained     : {groups_already_chained}")
    print(f"  patched                   : {groups_patched}")
    print(f"  skipped (no anchor)       : {groups_no_anchor}")
    print(f"  skipped (multiple anchors): {groups_multi_anchor}")
    print(f"  orphan milestones (no parent): {groups_orphan}")
    print(f"rows patched                : {rows_patched}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes. Without this flag the script is a dry-run.",
    )
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    main()
