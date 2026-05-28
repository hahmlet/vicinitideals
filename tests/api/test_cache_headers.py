"""Tests for Cache-Control: no-store middleware.

Verifies that HTML page responses carry no-store headers to prevent browsers
from serving stale authenticated content after logout via the back button.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from httpx import ASGITransport, AsyncClient

from app.api.main import _NoCacheHTMLMiddleware


# ---------------------------------------------------------------------------
# Middleware unit tests — isolated from the full app stack
# ---------------------------------------------------------------------------

def _make_isolated_app() -> FastAPI:
    """Tiny app with only the no-cache middleware, no DB or auth needed."""
    app = FastAPI()
    app.add_middleware(_NoCacheHTMLMiddleware)

    @app.get("/page")
    async def html_page():
        return HTMLResponse("<html><body>page</body></html>")

    @app.get("/api/data")
    async def json_data():
        return JSONResponse({"ok": True})

    return app


@pytest.mark.asyncio
async def test_html_response_gets_no_store():
    app = _make_isolated_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/page")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"
    assert resp.headers.get("pragma") == "no-cache"


@pytest.mark.asyncio
async def test_json_response_not_affected():
    app = _make_isolated_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/data")
    assert resp.status_code == 200
    assert "no-store" not in resp.headers.get("cache-control", "")


@pytest.mark.asyncio
async def test_htmx_html_response_not_affected():
    """HTMX partials are ephemeral fragments — exempt from no-store."""
    app = _make_isolated_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/page", headers={"hx-request": "true"})
    assert resp.status_code == 200
    assert "no-store" not in resp.headers.get("cache-control", "")


# ---------------------------------------------------------------------------
# Integration tests — real app, routes accessible without a DB session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_page_gets_no_store():
    """/login HTML response includes no-store — confirms middleware wired in real app."""
    from app.api.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/login")

    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert resp.headers.get("cache-control") == "no-store"
    assert resp.headers.get("pragma") == "no-cache"


@pytest.mark.asyncio
async def test_health_json_no_cache_control():
    """/health returns JSON — no Cache-Control header applied."""
    from app.api.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert "no-store" not in resp.headers.get("cache-control", "")


@pytest.mark.asyncio
async def test_unauthenticated_protected_route_redirects():
    """Unauthenticated request to protected route redirects to login (server auth intact)."""
    from app.api.main import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as client:
        resp = await client.get("/deals")
    assert resp.status_code == 303
    assert "/login" in resp.headers.get("location", "")
