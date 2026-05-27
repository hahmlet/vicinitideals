from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source_vehicle import SourceVehicle
from tests.conftest import seed_org


pytestmark = pytest.mark.asyncio
def _set_user_header(client: AsyncClient, user_id) -> None:
    client.headers["X-User-ID"] = str(user_id)


async def test_org_source_vehicle_create_defaults_auto_size_on(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    org, user = await seed_org(session)
    user.is_org_admin = True
    session.add(user)
    await session.commit()
    _set_user_header(client, user.id)

    payload = {
        "name": "City Senior Loan",
        "vehicle_type": "debt",
        "interest_rate_pct": 6.0,
    }
    resp = await client.post("/api/settings/source-vehicles/org", json=payload)
    assert resp.status_code == 200

    created = (
        await session.execute(
            select(SourceVehicle).where(
                SourceVehicle.scope == "org",
                SourceVehicle.owner_id == org.id,
                SourceVehicle.label == "City Senior Loan",
            )
        )
    ).scalar_one()
    assert (created.source_config or {}).get("auto_size") is True


async def test_user_source_vehicle_create_respects_explicit_auto_size_off(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    _, user = await seed_org(session)
    await session.commit()
    _set_user_header(client, user.id)

    payload = {
        "name": "LP Equity Off",
        "vehicle_type": "equity",
        "equity_role": "lp",
        "auto_size": False,
    }
    resp = await client.post("/api/settings/source-vehicles/user", json=payload)
    assert resp.status_code == 200

    created = (
        await session.execute(
            select(SourceVehicle).where(
                SourceVehicle.scope == "user",
                SourceVehicle.owner_id == user.id,
                SourceVehicle.label == "LP Equity Off",
            )
        )
    ).scalar_one()
    assert (created.source_config or {}).get("auto_size") is False


async def test_org_source_vehicle_update_preserves_existing_auto_size_when_omitted(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    org, user = await seed_org(session)
    user.is_org_admin = True
    session.add(user)
    await session.flush()

    vehicle = SourceVehicle(
        scope="org",
        owner_id=org.id,
        label="Preserve Off",
        vehicle_type="debt",
        source_config={"auto_size": False, "interest_rate_pct": 5.8},
    )
    session.add(vehicle)
    await session.commit()

    _set_user_header(client, user.id)

    update_payload = {
        "name": "Preserve Off Updated",
        "vehicle_type": "debt",
        "interest_rate_pct": 6.2,
    }
    resp = await client.put(f"/api/settings/source-vehicles/org/{vehicle.id}", json=update_payload)
    assert resp.status_code == 200

    await session.refresh(vehicle)
    assert vehicle.label == "Preserve Off Updated"
    assert (vehicle.source_config or {}).get("auto_size") is False
