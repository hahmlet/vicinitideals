"""One-shot cleanup: repoint 4 orphaned Float Earnings CapitalModules.

The Edgemont variant rebuild (ee74b9f3, commit 976b1a7 and its clone
7ac42b24) left 4 float_earnings CapitalModule.source JSONB blobs pointing at
a parent_module_id that no longer exists (the pre-consolidation, per-project
RJ Bond module) and a waterfall_milestone_id that predates the rebuilt
milestone set. Each float_earnings module must point at:
  - parent_module_id: the scenario's shared/unified RJ Bond CapitalModule
  - waterfall_milestone_id: that specific project's operation_stabilized
    Milestone (float_earnings is 1:1 with a project's stabilization date)

The 4 targets and their correct values were derived by cross-referencing the
working pattern in the original host scenario (4bc8fd71), matching by
stack_position + amount.

Dry-run by default; pass --apply to update.

    python -m app.scripts.repoint_float_earnings_modules
    python -m app.scripts.repoint_float_earnings_modules --apply
"""

from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.capital import CapitalModule

# (capital_module_id, correct parent_module_id, correct waterfall_milestone_id)
_FIXES: tuple[tuple[str, str, str], ...] = (
    (
        "2c084aed-4aa0-41dc-a04f-d57c31a8ea3d",
        "8999f01d-a24e-4584-8baf-b8321497dd27",
        "a1470e3e-5281-4ee2-a7fe-1393bb3ac086",
    ),
    (
        "a74cbced-fc1c-4ac7-aeca-e8c398db22d4",
        "8999f01d-a24e-4584-8baf-b8321497dd27",
        "8c08f459-d4bb-4d8b-bc30-00d9bf8bcbce",
    ),
    (
        "cf9074e5-d742-4fe1-8b46-0e94bae72101",
        "fa50cd88-21a7-4d33-93e0-b90365696beb",
        "65869d81-7366-446e-ae72-7d7ec51c6bd9",
    ),
    (
        "170ece59-bd26-4146-997b-a13f821735ea",
        "fa50cd88-21a7-4d33-93e0-b90365696beb",
        "5cce9fd2-a7ed-4f86-9f71-f576f5139873",
    ),
)


async def _main(apply: bool) -> None:
    async with AsyncSessionLocal() as session:
        for module_id, parent_id, milestone_id in _FIXES:
            module = await session.get(CapitalModule, UUID(module_id))
            if module is None:
                print(f"SKIP {module_id}: not found.")
                continue
            src = dict(module.source or {})
            before_parent = src.get("parent_module_id")
            before_milestone = src.get("waterfall_milestone_id")
            print(
                f"{module_id} ({module.label}): "
                f"parent_module_id {before_parent!r} -> {parent_id!r}, "
                f"waterfall_milestone_id {before_milestone!r} -> {milestone_id!r}"
            )
            if apply:
                src["parent_module_id"] = parent_id
                src["waterfall_milestone_id"] = milestone_id
                module.source = src

        if apply:
            await session.commit()
            print("APPLIED.")
        else:
            print("DRY RUN (no commit).  Re-run with --apply to update.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually update rows.")
    args = parser.parse_args()
    asyncio.run(_main(apply=args.apply))
