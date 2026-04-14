"""Shared helpers for E2E tests — navigation, HTMX waits, auth."""

from __future__ import annotations

from playwright.sync_api import Page


def wait_for_htmx(page: Page, timeout: int = 8000) -> None:
    """Wait for in-flight HTMX requests to settle using network idle.

    Falls back cleanly if no requests are in flight.
    """
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass


def navigate_to_deal(page: Page, base_url: str, deal_id: str) -> None:
    """Navigate to a deal's model builder page and wait for HTMX to settle."""
    page.goto(f"{base_url}/deals/{deal_id}")
    page.wait_for_load_state("domcontentloaded")
    wait_for_htmx(page)


def login(page: Page, base_url: str, email: str, password: str) -> None:
    """Log in via the login form.

    Waits for redirect to /deals after successful login.
    Note: Requires T4-T7 auth implementation to be deployed.
    """
    page.goto(f"{base_url}/login")
    page.wait_for_load_state("domcontentloaded")
    page.fill("[name=email]", email)
    page.fill("[name=password]", password)
    page.click("[type=submit]")
    page.wait_for_url(f"{base_url}/deals**", timeout=10_000)
