"""One-time backfill: add an auto Developer Fee Use Line to existing Projects.

After deploying migration 0085 + the dev-fee feature, every NEW deal gets an
auto-seeded Developer Fee Use Line. This script back-fills existing Projects
that pre-date the feature.

Run:
    uv run python app/scripts/backfill_dev_fee_use_lines.py            # dry run
    uv run python app/scripts/backfill_dev_fee_use_lines.py --apply    # commit

For each Project missing an auto Dev Fee row:
- Resolve the Scenario's project_type
- Look up org defaults for that deal type (uses scenario.created_by_user_id)
- If the resolved user_id is None, fall back to a synthetic resolve against
  org-only settings (system baseline if no org row).
- Insert a Developer Fee UseLine with amount=0; the engine recomputes on the
  next compute pass.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import AsyncSessionLocal
from app.models.deal import Deal, DealModel, UseLine, UseLinePhase
from app.models.project import Project
from app.models.settings import OrgSetting
from app.settings.defaults import SYSTEM_BASELINE
from app.settings.resolver import resolve_dev_fee_config


async def _resolve_for_org_only(org_id: uuid.UUID, deal_type: str, session) -> dict[str, str]:
    """Resolver variant when no user_id is available — org row → baseline only."""
    valid_types = ("acquisition", "value_add", "conversion", "new_construction")
    key_type = deal_type if deal_type in valid_types else "acquisition"
    keys = {
        "enabled": "dev_fee_enabled",
        "pct": f"dev_fee_pct_{key_type}",
        "basis": f"dev_fee_basis_{key_type}",
        "timing": f"dev_fee_timing_{key_type}",
        "phase": f"dev_fee_phase_{key_type}",
    }
    org_rows = (
        await session.execute(
            select(OrgSetting).where(OrgSetting.org_id == org_id)
        )
    ).scalars().all()
    org_map = {r.field_key: r.value for r in org_rows}
    return {slot: org_map.get(fkey, SYSTEM_BASELINE[fkey]) for slot, fkey in keys.items()}


async def run(apply: bool) -> None:
    inserted = 0
    skipped_existing = 0
    skipped_disabled = 0
    errors = 0

    async with AsyncSessionLocal() as session:
        projects = (
            await session.execute(
                select(Project).options(
                    selectinload(Project.use_lines),
                )
            )
        ).scalars().all()

        for project in projects:
            try:
                if any(getattr(u, "is_auto_dev_fee", False) for u in project.use_lines):
                    skipped_existing += 1
                    continue

                scenario = await session.get(DealModel, project.scenario_id)
                if scenario is None:
                    errors += 1
                    continue

                project_type_val = (
                    scenario.project_type.value
                    if hasattr(scenario.project_type, "value")
                    else str(scenario.project_type)
                )

                # Explicit fetch of parent Deal for org_id — Scenario.deal
                # is a lazy relationship and would trigger a greenlet error.
                parent_deal = await session.get(Deal, scenario.deal_id)
                org_id = parent_deal.org_id if parent_deal is not None else None
                if org_id is None:
                    errors += 1
                    continue

                if scenario.created_by_user_id is not None:
                    cfg = await resolve_dev_fee_config(
                        scenario.created_by_user_id,
                        org_id,
                        project_type_val,
                        session,
                    )
                else:
                    cfg = await _resolve_for_org_only(org_id, project_type_val, session)

                if str(cfg["enabled"]).lower() != "true":
                    skipped_disabled += 1
                    continue

                pct = Decimal(cfg["pct"])
                basis = cfg["basis"]
                timing = cfg["timing"]
                phase_str = cfg["phase"]
                try:
                    phase_enum = UseLinePhase(phase_str)
                except ValueError:
                    phase_enum = UseLinePhase.construction

                row = UseLine(
                    id=uuid.uuid4(),
                    project_id=project.id,
                    label="Developer Fee",
                    phase=phase_enum,
                    cost_category="soft",
                    amount=Decimal("0"),
                    timing_type=timing,
                    is_deferred=False,
                    is_auto_dev_fee=True,
                    dev_fee_pct=pct,
                    dev_fee_basis=basis,
                )
                session.add(row)
                inserted += 1
            except Exception as e:  # noqa: BLE001 — defensive logging in batch script
                errors += 1
                print(f"  ! project {project.id}: {e!r}")

        if apply:
            await session.commit()
        else:
            await session.rollback()

    print("=" * 60)
    print(f"Projects scanned        : {len(projects)}")
    print(f"Already had auto Dev Fee: {skipped_existing}")
    print(f"Skipped (disabled cfg)  : {skipped_disabled}")
    print(f"Inserted                : {inserted}")
    print(f"Errors                  : {errors}")
    print(f"Mode                    : {'APPLIED ✓' if apply else 'DRY RUN (no commit)'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes. Without this flag the script runs as a dry run.",
    )
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    main()
