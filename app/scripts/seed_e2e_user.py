"""Seed the E2E test user so CI/E2E logins succeed against a fresh DB.

Idempotent. Safe to run on any environment — creates the user only if missing.
Default credentials match tests/e2e/conftest.py defaults.

Run inside the api container:
  python -m app.scripts.seed_e2e_user
  python -m app.scripts.seed_e2e_user --email foo@bar.com --password secret

Env var overrides:
  E2E_EMAIL
  E2E_PASSWORD
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import select

from app.api.auth import hash_password
from app.db import AsyncSessionLocal
from app.models.org import Organization, User


async def seed_user(email: str, password: str) -> None:
    async with AsyncSessionLocal() as session:
        org = (await session.execute(
            select(Organization).order_by(Organization.created_at)
        )).scalars().first()
        if org is None:
            org = Organization(name="Ketch Media", slug="ketch-media")
            session.add(org)
            await session.flush()

        existing = (await session.execute(
            select(User).where(User.email == email)
        )).scalar_one_or_none()

        if existing is not None:
            if not existing.hashed_password:
                existing.hashed_password = hash_password(password)
                existing.is_active = True
                await session.commit()
                print(f"E2E user {email} existed without password; password set.")
            else:
                print(f"E2E user {email} already seeded — no change.")
            return

        user = User(
            org_id=org.id,
            name="E2E Test User",
            email=email,
            hashed_password=hash_password(password),
            is_active=True,
        )
        session.add(user)
        await session.commit()
        print(f"Created E2E user {email}.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email",    default=os.environ.get("E2E_EMAIL", "e2e@ketch.media"))
    parser.add_argument("--password", default=os.environ.get("E2E_PASSWORD", "e2e-test-password-2026"))
    args = parser.parse_args()
    try:
        asyncio.run(seed_user(args.email, args.password))
    except Exception as exc:
        print(f"ERROR seeding E2E user: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
