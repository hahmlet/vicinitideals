"""Pytest conftest for E2E tests — Playwright browser fixtures and running-app guard.

All E2E tests require a live app on BASE_URL. Tests are skipped (not failed)
if the app is unreachable, so CI passes cleanly when the stack isn't up.

Usage:
    uv run pytest tests/e2e/ -m e2e

Environment variables:
    E2E_BASE_URL             Override default base URL (default: http://localhost:8001)
    VICINITIDEALS_API_KEY    API key for seeding data (matches .env)
"""

from __future__ import annotations

import os

import httpx
import pytest

BASE_URL: str = os.environ.get("E2E_BASE_URL", "http://localhost:8001")


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    """Inject base_url into every browser context so relative URLs work."""
    return {**browser_context_args, "base_url": BASE_URL}


@pytest.fixture(scope="session", autouse=True)
def _require_live_app() -> None:
    """Skip the entire E2E suite if the app isn't reachable.

    This lets CI skip E2E cleanly when docker compose isn't up,
    rather than failing with a connection error.
    """
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
