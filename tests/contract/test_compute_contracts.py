from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.asyncio
async def test_compute_endpoints_return_non_null_outputs_and_cashflows(
    client: AsyncClient,
    test_session_factory: async_sessionmaker[AsyncSession],
    auth_headers: dict[str, str],
) -> None:
    from tests.api.test_routers import _seed_model_for_run_tests

    async with test_session_factory() as session:
        model_id, user = await _seed_model_for_run_tests(session, include_capital=True)
        await session.commit()
    # Org-scoped routes 404 on a random X-User-ID — use the seeded user.
    auth_headers = {**auth_headers, "X-User-ID": str(user.id)}

    compute_response = await client.post(f"/api/models/{model_id}/compute", headers=auth_headers)
    assert compute_response.status_code == 200
    compute_payload = compute_response.json()
    assert compute_payload["cash_flow_count"] > 0
    assert compute_payload["observability"]["run_type"] == "cashflow"

    outputs_response = await client.get(f"/api/models/{model_id}/outputs", headers=auth_headers)
    assert outputs_response.status_code == 200
    outputs = outputs_response.json()
    assert outputs is not None
    assert Decimal(str(outputs["total_project_cost"])) > Decimal("0")
    assert Decimal(str(outputs["noi_stabilized"])) > Decimal("0")
    assert outputs["project_irr_unlevered"] is not None

    cashflow_response = await client.get(f"/api/models/{model_id}/cashflow", headers=auth_headers)
    assert cashflow_response.status_code == 200
    cashflows = cashflow_response.json()
    assert cashflows
    assert all(entry["net_cash_flow"] is not None for entry in cashflows)


@pytest.mark.asyncio
async def test_waterfall_compute_endpoints_return_non_null_distribution_outputs(
    client: AsyncClient,
    test_session_factory: async_sessionmaker[AsyncSession],
    auth_headers: dict[str, str],
) -> None:
    from tests.api.test_routers import _seed_model_for_run_tests

    async with test_session_factory() as session:
        model_id, user = await _seed_model_for_run_tests(session, include_capital=True)
        await session.commit()
    # Org-scoped routes 404 on a random X-User-ID — use the seeded user.
    auth_headers = {**auth_headers, "X-User-ID": str(user.id)}

    cashflow_response = await client.post(f"/api/models/{model_id}/compute", headers=auth_headers)
    assert cashflow_response.status_code == 200

    waterfall_response = await client.post(f"/api/models/{model_id}/waterfall/compute", headers=auth_headers)
    assert waterfall_response.status_code == 200
    waterfall_payload = waterfall_response.json()
    assert waterfall_payload["waterfall_result_count"] > 0
    assert waterfall_payload["observability"]["run_type"] == "waterfall"

    report_response = await client.get(f"/api/models/{model_id}/waterfall/report", headers=auth_headers)
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["investor_count"] > 0
    assert report["investors"]
    assert report["investors"][0]["timeline"]

    outputs_response = await client.get(f"/api/models/{model_id}/outputs", headers=auth_headers)
    assert outputs_response.status_code == 200
    outputs = outputs_response.json()
    assert outputs is not None
    assert outputs["project_irr_levered"] is not None
    # The seed is all-equity (no debt module), so annual debt service is zero
    # and the engine correctly reports DSCR = 0 (app/engines/cashflow.py sets
    # dscr = ZERO when annual_operation_debt_service == 0). The contract here
    # is non-null, not leverage-dependent magnitude.
    assert outputs["dscr"] is not None
    assert Decimal(str(outputs["dscr"])) >= Decimal("0")
