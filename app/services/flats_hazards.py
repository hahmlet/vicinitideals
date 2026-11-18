"""The mapped ground-hazard notes of one lot, for the lot page and the lot report.

FOLLOWUPS 198 (:mod:`flats.ingest.hazards`). Landslide, earthquake liquefaction
and flood, read from ``flats.lot_hazards`` and named against the sources the
load recorded in ``flats.hazard_layers``. A NOTE, never a colour: nothing the
screen, the colour or the flags read comes from here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import FlatsHazardLayer, FlatsLot, FlatsLotHazard
from flats.ingest.hazards import describe


def _plain(value: Any) -> Any:
    return float(value) if isinstance(value, Decimal) else value


async def lot_hazards(session: AsyncSession, lot: FlatsLot) -> dict[str, Any]:
    """Every hazard layer on the lot, grouped by hazard: each class with its
    square feet and share, largest first, the worst class, the source; a layer
    with no rows reads "not loaded yet" (never "no hazard")."""
    rows = [
        {c.key: _plain(getattr(r, c.key)) for c in FlatsLotHazard.__table__.columns}
        for r in (await session.execute(select(FlatsLotHazard).where(FlatsLotHazard.lot_id == lot.id))).scalars()
    ]
    note = describe(rows, jurisdiction=lot.jurisdiction)
    sources: dict[str, FlatsHazardLayer] = {}
    if rows:
        found = await session.execute(select(FlatsHazardLayer).where(FlatsHazardLayer.snapshot_id == lot.snapshot_id))
        sources = {s.layer: s for s in found.scalars()}
    for group in note["groups"]:
        for layer in group["layers"]:
            src = sources.get(layer["layer"])
            layer["source"] = src.source if src else None
            layer["loaded_at"] = src.loaded_at.isoformat() if src and src.loaded_at else None
    return note
