from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.config import settings

EXPECTED_PATHS = [
    "/api/projects",
    "/api/projects/{project_id}",
    "/api/projects/{project_id}/summary",
    "/api/portfolios",
    "/api/portfolios/{portfolio_id}/summary",
    "/api/models/{model_id}/outputs",
    "/api/models/{model_id}/cashflow",
    "/api/models/{model_id}/export/json",
    "/health",
    "/api/scenarios/variables",
    "/api/dedup/pending",
    "/api/ingest/trigger",
]


@pytest.mark.asyncio
async def test_openapi_schema_has_expected_contract_endpoints(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.get("/openapi.json", headers=auth_headers)

    assert response.status_code == 200
    paths = response.json()["paths"]
    missing = [path for path in EXPECTED_PATHS if path not in paths]
    assert not missing, f"Missing from OpenAPI spec: {missing}"


@pytest.mark.asyncio
async def test_healthcheck_uses_structured_contract_envelope(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.get("/health", headers=auth_headers)

    assert response.status_code == 200
    assert set(response.json()) == {"code", "message", "detail"}
    assert response.json()["code"] == "ok"
    assert response.json()["detail"] == {"status": "ok"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "method", "path", "json_payload", "expected_status", "expected_code"),
    [
        # 403: use non-UI path so API key middleware fires (all /api/ paths are UI-exempt)
        ({"X-API-Key": "wrong-key"}, "GET", "/projects", None, 403, "forbidden"),
        # 400: /api/ path but valid key → user-ID middleware still runs
        (
            {"X-API-Key": settings.vicinitideals_api_key, "X-User-ID": "not-a-uuid"},
            "GET",
            "/api/projects",
            None,
            400,
            "bad_request",
        ),
        # 404: real route, valid auth, non-existent resource
        (
            None,
            "GET",
            "/api/projects/00000000-0000-0000-0000-000000000000",
            None,
            404,
            "not_found",
        ),
        # 422: real route, valid auth, missing required fields
        (None, "POST", "/api/projects", {}, 422, "validation_error"),
    ],
)
async def test_error_responses_keep_code_message_detail_shape(
    client: AsyncClient,
    auth_headers: dict[str, str],
    headers: dict[str, str] | None,
    method: str,
    path: str,
    json_payload: dict | None,
    expected_status: int,
    expected_code: str,
) -> None:
    request_headers = auth_headers if headers is None else headers
    response = await client.request(method, path, headers=request_headers, json=json_payload)

    assert response.status_code == expected_status
    payload = response.json()
    assert set(payload) == {"code", "message", "detail"}
    assert payload["code"] == expected_code
    assert isinstance(payload["message"], str)
