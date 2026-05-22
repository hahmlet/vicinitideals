"""One-shot: collapse legacy funder_type strings on source_vehicles.vehicle_type
onto the canonical 4-value set (equity / debt / forgivable_loan / grant).

Background: settings.py Source Vehicle handlers stored the raw `funder_type`
form value (senior_debt, mezzanine_debt, bridge, …) in the vehicle_type column.
The deal-setup wizard filters `vehicle_type IN ('debt','forgivable_loan')` so
those rows never showed up in the picker.

Run from VM 114:
    docker exec vicinitideals-api python -m app.scripts.migrate_source_vehicle_types
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.source_vehicle import SourceVehicle

LOG = logging.getLogger("migrate_sv_types")

_LEGACY_TO_CANONICAL: dict[str, tuple[str, str | None]] = {
    # legacy vehicle_type -> (canonical vehicle_type, equity_role override or None)
    "permanent_debt": ("debt", None),
    "senior_debt": ("debt", None),
    "mezzanine_debt": ("debt", None),
    "bridge": ("debt", None),
    "construction_loan": ("debt", None),
    "pre_development_loan": ("debt", None),
    "acquisition_loan": ("debt", None),
    "bond": ("debt", None),
    "owner_loan": ("debt", None),
    "soft_loan": ("forgivable_loan", None),
    "preferred_equity": ("equity", "lp"),
    "common_equity": ("equity", "gp"),
    "owner_investment": ("equity", "gp"),
    "tax_credit": ("grant", None),
    "other": ("debt", None),
}

_CANONICAL = {"equity", "debt", "forgivable_loan", "grant"}


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(SourceVehicle))).scalars().all()
        changed = 0
        for v in rows:
            vt = (v.vehicle_type or "").strip().lower()
            if vt in _CANONICAL:
                continue
            mapping = _LEGACY_TO_CANONICAL.get(vt)
            if mapping is None:
                LOG.warning("  SKIP unknown vehicle_type=%r id=%s label=%r", vt, v.id, v.label)
                continue
            canonical, er_override = mapping
            old_vt, old_er = v.vehicle_type, v.equity_role
            v.vehicle_type = canonical
            if er_override is not None and not v.equity_role:
                v.equity_role = er_override
            LOG.info(
                "  REMAP %s [%s] %s/%s -> %s/%s",
                v.label, v.id, old_vt, old_er, v.vehicle_type, v.equity_role,
            )
            changed += 1
        if changed:
            await session.commit()
        LOG.info("Done. %d row(s) remapped.", changed)


if __name__ == "__main__":
    asyncio.run(main())
