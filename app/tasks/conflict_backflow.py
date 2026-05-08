"""Backflow task: auto-resolve Opportunity vs Parcel field conflicts.

Iterates every Opportunity that has a linked Parcel and applies the
auto-resolution rules from app.reconciliation.conflict_rules.  Fields
that match a rule are acked (and nulled when the parcel side wins) so
they no longer surface in the manual-review queue.

Designed to be run once against existing data after the rules are
deployed.  Safe to re-run — already-acked fields are skipped.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import AsyncSessionLocal
from app.models.opportunity import Opportunity
from app.reconciliation.conflict_rules import _FIELD_MAP, auto_resolve_conflict
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_NULL_FIELDS = frozenset({"units", "gba_sqft", "year_built", "lot_sqft"})
_BATCH_SIZE = 200


async def _backflow_all() -> dict[str, Any]:
    """Resolve auto-resolvable conflicts on all linked Opportunities."""
    rule_counts: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    errors: list[str] = []
    total_opps = 0
    opps_changed = 0

    async with AsyncSessionLocal() as session:
        stmt = (
            select(Opportunity)
            .options(selectinload(Opportunity.parcel))
            .where(Opportunity.parcel_id.isnot(None))
        )
        opps = list((await session.execute(stmt)).scalars().unique())
        total_opps = len(opps)
        logger.info("Conflict backflow: %d linked Opportunities to scan", total_opps)

        for opp in opps:
            p = opp.parcel
            if p is None:
                continue
            try:
                ack = dict(opp.parcel_conflicts_ack or {})
                changed = False
                for field, (opp_attr, parcel_attr) in _FIELD_MAP.items():
                    if field in ack:
                        continue
                    opp_val = getattr(opp, opp_attr, None)
                    par_val = getattr(p, parcel_attr, None)
                    if opp_val is None or par_val is None:
                        continue
                    action = auto_resolve_conflict(field, opp_val, par_val)
                    if action is None:
                        continue
                    if action == "use_parcel" and field in _NULL_FIELDS:
                        setattr(opp, opp_attr, None)
                    ack[field] = action
                    changed = True
                    rule_counts[action] += 1
                    field_counts[field] += 1
                if changed:
                    opp.parcel_conflicts_ack = ack
                    opps_changed += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{opp.id}: {exc}")
                logger.warning("Conflict backflow error for opp %s: %s", opp.id, exc)

        await session.commit()

    report: dict[str, Any] = {
        "total_opportunities_scanned": total_opps,
        "opportunities_updated": opps_changed,
        "fields_auto_resolved": dict(field_counts),
        "by_action": dict(rule_counts),
        "errors": len(errors),
    }
    if errors:
        report["error_details"] = errors[:20]

    logger.info("=" * 60)
    logger.info("CONFLICT BACKFLOW REPORT")
    logger.info("=" * 60)
    logger.info("Opportunities scanned : %d", total_opps)
    logger.info("Opportunities updated : %d", opps_changed)
    logger.info("Fields auto-resolved  : %s", dict(field_counts))
    logger.info("By action             : %s", dict(rule_counts))
    if errors:
        logger.warning("Errors (%d): %s", len(errors), errors[:5])
    logger.info("=" * 60)

    return report


@celery_app.task(
    name="app.tasks.conflict_backflow.conflict_backflow_task",
    queue="default",
)
def conflict_backflow_task() -> dict[str, Any]:
    """Celery entry-point: apply auto-resolution rules to all existing conflicts."""
    return asyncio.get_event_loop().run_until_complete(_backflow_all())
