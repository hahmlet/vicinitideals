"""Seed the reference rows E2E tests read but never create.

`seed_e2e_user` makes a login. This makes the handful of *reference* rows the
suite assumes are already there because production has them — the kind of row a
human curates once and every screen then reads. On a CI database, built empty
from migrations on every run, nothing curates them, so a picker that is full on
production renders as an empty dropdown and the test that asserts a real choice
fails with `assert 1 > 1`.

Every seeder here is guarded on its table being **empty**, which is what makes
this safe to run anywhere: production has ~450 brokers, so the guard is false
and the function returns having done nothing. The guard is deliberately "is
there any row at all", not "is my row missing" — the question being asked is
whether anything curates this table in this environment, and one synthetic row
next to real ones would be a small permanent lie in a picker Steph uses.

Idempotent. Run inside the api container, after migrations:

    python -m app.scripts.seed_e2e_fixtures
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import func, select

from app.db import AsyncSessionLocal
from app.models.broker import Broker, Brokerage


async def seed_brokers(session) -> str:
    """One broker at a firm, so the opportunity wizard's picker has a choice.

    The wizard labels each option ``"Last, First · Firm"``, so the seeded row
    carries a brokerage too — an option with no firm would render through a
    different branch than the one production takes.
    """
    existing = await session.scalar(select(func.count()).select_from(Broker))
    if existing:
        return f"brokers: {existing} already present, left alone"

    firm = Brokerage(name="E2E Test Brokerage")
    session.add(firm)
    await session.flush()

    session.add(
        Broker(
            first_name="Avery",
            last_name="Testerson",
            brokerage_id=firm.id,
            email="avery@e2e.invalid",
            license_state="OR",
            license_status="active",
        )
    )
    return "brokers: seeded 1 (table was empty)"


async def seed_all() -> None:
    async with AsyncSessionLocal() as session:
        lines = [await seed_brokers(session)]
        await session.commit()
    for line in lines:
        print(line)


def main() -> None:
    try:
        asyncio.run(seed_all())
    except Exception as exc:
        print(f"ERROR seeding E2E fixtures: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
