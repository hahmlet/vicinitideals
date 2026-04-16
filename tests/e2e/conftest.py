"""Pytest conftest for E2E tests — Playwright browser fixtures and running-app guard.

All E2E tests require a live app on BASE_URL. Tests are skipped (not failed)
if the app is unreachable, so CI passes cleanly when the stack isn't up.

Usage:
    uv run pytest tests/e2e/ -m e2e

Environment variables:
    E2E_BASE_URL             Override default base URL (default: http://localhost:8001)
    E2E_EMAIL                Login email for authenticated tests (default: e2e@ketch.media)
    E2E_PASSWORD             Login password for authenticated tests
    VICINITIDEALS_API_KEY    API key for seeding data (matches .env)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Generator

import httpx
import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page

BASE_URL: str = os.environ.get("E2E_BASE_URL", "http://localhost:8001")
E2E_EMAIL: str = os.environ.get("E2E_EMAIL", "e2e@ketch.media")
E2E_PASSWORD: str = os.environ.get("E2E_PASSWORD", "e2e-test-password-2026")


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    """Inject base_url into every browser context so relative URLs work."""
    return {**browser_context_args, "base_url": BASE_URL}


@pytest.fixture(scope="session", autouse=True)
def _require_live_app() -> None:
    """Skip the entire E2E suite if the app isn't reachable."""
    try:
        resp = httpx.get(f"{BASE_URL}/health", timeout=5)
        if resp.status_code != 200:
            pytest.skip(f"App health check returned {resp.status_code} at {BASE_URL}")
    except Exception as exc:
        pytest.skip(f"Live app not reachable at {BASE_URL}: {exc}")


@pytest.fixture(scope="session")
def api_key() -> str:
    return os.environ.get(
        "VICINITIDEALS_API_KEY",
        "changeme-generate-with-openssl-rand-hex-32",
    )


# ---------------------------------------------------------------------------
# Authenticated session
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def _auth_state_path(browser: "Browser", tmp_path_factory: pytest.TempPathFactory) -> str:
    """Log in once per test session; return path to saved storage state."""
    tmp = tmp_path_factory.mktemp("auth")
    state_path = str(tmp / "auth.json")
    ctx = browser.new_context(base_url=BASE_URL)
    page = ctx.new_page()
    page.goto("/login")
    page.fill('[name=email]', E2E_EMAIL)
    page.fill('[name=password]', E2E_PASSWORD)
    page.click('[type=submit]')
    page.wait_for_url("**/deals**", timeout=10_000)
    ctx.storage_state(path=state_path)
    ctx.close()
    return state_path


@pytest.fixture
def logged_in_page(browser: "Browser", _auth_state_path: str) -> Generator["Page", None, None]:
    """A fresh page pre-loaded with a valid session cookie."""
    ctx = browser.new_context(base_url=BASE_URL, storage_state=_auth_state_path)
    page = ctx.new_page()
    yield page
    ctx.close()


# ---------------------------------------------------------------------------
# Session-scoped seed page — used by fixtures that create test data
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def _seed_page(browser: "Browser", _auth_state_path: str) -> Generator["Page", None, None]:
    """A session-scoped page for seeding test data via Playwright interactions."""
    ctx = browser.new_context(base_url=BASE_URL, storage_state=_auth_state_path)
    page = ctx.new_page()
    yield page
    ctx.close()
