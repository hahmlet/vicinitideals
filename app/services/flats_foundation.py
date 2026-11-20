"""The foundation model's answer for one lot, for the lot page and the lot report.

FOLLOWUPS 209 (:mod:`flats.foundation`). Reads the lot's MEASURED record from
``flats.lot_foundation`` and prices it now, with the current
``flats/config/foundation.yaml`` (:func:`flats.foundation.report.describe`): no
price is ever stored, so a price or threshold change is a settings edit and a
deploy. A record measured under other building dimensions reads "needs
re-measuring" and carries no figure.

A NOTE, never a colour: nothing the screen, the colour, its reasons or its
flags read comes from here.
"""

from __future__ import annotations

from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import FlatsLotFoundation
from flats.foundation import record, report
from flats.foundation import settings as foundation_settings
from flats.foundation.settings import Settings

_CACHE: dict[str, Any] = {}


def current_settings() -> tuple[Settings, str]:
    """The settings file and its version hash, re-read only when the file changes."""
    path = foundation_settings.PATH
    stamp = path.stat().st_mtime_ns
    if _CACHE.get("stamp") != stamp:
        # parse(), not load(): load() caches per path for the life of the process.
        fresh = foundation_settings.parse(yaml.safe_load(path.read_text(encoding="utf-8")))
        _CACHE.update(stamp=stamp, settings=fresh, version=record.settings_version(path))
    return _CACHE["settings"], _CACHE["version"]


async def lot_foundation(session: AsyncSession, county: str, tlid: str) -> dict[str, Any] | None:
    """The ``foundation`` block for one lot, priced now; None when the lot has no
    measured record."""
    row = await session.get(FlatsLotFoundation, (county, tlid))
    if row is None:
        return None
    s, version = current_settings()
    block = report.describe(row.record, s, version=version)
    block["loaded_at"] = row.loaded_at.isoformat() if row.loaded_at else None
    return block
