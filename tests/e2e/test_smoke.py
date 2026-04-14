"""Smoke tests — verify that key pages load and the API is healthy.

These tests make no assumptions about data in the DB (no fixtures required)
beyond the app being reachable. They're skipped automatically if the app
isn't running (see conftest._require_live_app).

Run:
    uv run pytest tests/e2e/test_smoke.py -m e2e -v
"""

from __future__ import annotations

import pytest
import httpx

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Session-scoped HTTP client (not a browser — fast JSON/asset checks)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def http(base_url: str, api_key: str):
    with httpx.Client(
        base_url=base_url,
        follow_redirects=True,
        headers={"X-API-Key": api_key},
        timeout=10,
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# 1. Health endpoint
# ---------------------------------------------------------------------------

def test_health_returns_ok(http: httpx.Client) -> None:
    resp = http.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("code") == "ok"


# ---------------------------------------------------------------------------
# 2-6. Nav pages load (sidebar present, no 4xx/5xx)
# ---------------------------------------------------------------------------

def test_deals_page_loads(page, base_url: str) -> None:
    page.goto(f"{base_url}/deals")
    page.wait_for_selector(".sidebar", timeout=10_000)
    page.wait_for_selector("#deals-tbody", timeout=10_000)


def test_opportunities_page_loads(page, base_url: str) -> None:
    page.goto(f"{base_url}/opportunities")
    page.wait_for_selector(".sidebar", timeout=10_000)


def test_parcels_page_loads(page, base_url: str) -> None:
    page.goto(f"{base_url}/parcels")
    page.wait_for_selector(".sidebar", timeout=10_000)


def test_listings_page_loads(page, base_url: str) -> None:
    page.goto(f"{base_url}/listings")
    page.wait_for_selector(".sidebar", timeout=10_000)


def test_portfolios_page_loads(page, base_url: str) -> None:
    page.goto(f"{base_url}/portfolios")
    page.wait_for_selector(".sidebar", timeout=10_000)


# ---------------------------------------------------------------------------
# 7. Static CSS asset
# ---------------------------------------------------------------------------

def test_static_css_loads(http: httpx.Client) -> None:
    resp = http.get("/static/app.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# 8. New deal wizard page (no data required)
# ---------------------------------------------------------------------------

def test_new_deal_wizard_loads(page, base_url: str) -> None:
    page.goto(f"{base_url}/deals/new")
    page.wait_for_selector(".sidebar", timeout=10_000)
    # Wizard has a deal-name input
    page.wait_for_selector("[name=name]", timeout=10_000)
