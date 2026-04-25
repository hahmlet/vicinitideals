"""Renormalize broker first/last names and brokerage names in-place.

Applies the same smart-case + whitespace rules used by the Crexi mapper to
existing rows so that long-standing ALL-CAPS entries (e.g. "ERIC SWANSON")
become Title Case ("Eric Swanson"). Short acronyms like "JLL" / "CBRE" are
preserved.

Brokerage handling: if a normalized name would collide (case-insensitively)
with another existing brokerage row, the script does NOT change the row — it
logs the conflict so you can manually merge via the dedup UI.

Run:
    docker exec vicinitideals-api python scripts/normalize_brokers_brokerages.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import AsyncSessionLocal  # noqa: E402
from app.models.broker import Broker, Brokerage  # noqa: E402
from app.services.broker_normalize import normalize_name  # noqa: E402


async def normalize_brokers(session) -> tuple[int, int]:
    examined = 0
    updated = 0
    rows = (await session.execute(select(Broker))).scalars().all()
    for broker in rows:
        examined += 1
        new_first = normalize_name(broker.first_name)
        new_last = normalize_name(broker.last_name)
        changed = False
        if new_first != broker.first_name:
            broker.first_name = new_first
            changed = True
        if new_last != broker.last_name:
            broker.last_name = new_last
            changed = True
        if changed:
            updated += 1
    return examined, updated


async def normalize_brokerages(session) -> tuple[int, int, list[tuple[str, str]]]:
    examined = 0
    updated = 0
    conflicts: list[tuple[str, str]] = []
    rows = (await session.execute(select(Brokerage))).scalars().all()
    for brokerage in rows:
        examined += 1
        new_name = normalize_name(brokerage.name)
        if new_name is None or new_name == brokerage.name:
            continue
        # Would this collide with another existing brokerage (case-insensitive)?
        collision = (
            await session.execute(
                select(Brokerage.id, Brokerage.name).where(
                    func.lower(Brokerage.name) == new_name.lower(),
                    Brokerage.id != brokerage.id,
                )
            )
        ).first()
        if collision is not None:
            conflicts.append((brokerage.name, collision.name))
            continue
        brokerage.name = new_name
        updated += 1
    return examined, updated, conflicts


async def main() -> int:
    async with AsyncSessionLocal() as session:
        b_examined, b_updated = await normalize_brokers(session)
        bg_examined, bg_updated, conflicts = await normalize_brokerages(session)
        await session.commit()

    print(f"Brokers:    examined={b_examined}  updated={b_updated}")
    print(f"Brokerages: examined={bg_examined}  updated={bg_updated}")
    if conflicts:
        print(f"\nBrokerage conflicts ({len(conflicts)}) — manual merge required:")
        for original, existing in conflicts:
            print(f"  {original!r} would collide with existing {existing!r}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
