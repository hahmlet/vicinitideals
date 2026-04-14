"""Model builder E2E tests — navigate the builder UI and verify panel rendering.

Requires a live app with at least one Organization in the DB.
A test deal+scenario is created once per session via seed.create_e2e_scenario.

Run:
    uv run pytest tests/e2e/test_model_builder.py -m e2e -v
"""

from __future__ import annotations

import pytest

from tests.e2e.helpers import wait_for_htmx
from tests.e2e.seed import create_e2e_scenario

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Session-scoped scenario fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def model_id(base_url: str, api_key: str) -> str:
    """Create one deal/scenario for all model-builder tests in this session."""
    return create_e2e_scenario(base_url, api_key, deal_name="E2E Model Builder Test")


# ---------------------------------------------------------------------------
# 1. Model builder page loads
# ---------------------------------------------------------------------------

def test_model_builder_loads(page, base_url: str, model_id: str) -> None:
    page.goto(f"{base_url}/models/{model_id}/builder")
    page.wait_for_selector(".module-stack", timeout=15_000)


# ---------------------------------------------------------------------------
# 2. Timeline module card is always visible (no gate)
# ---------------------------------------------------------------------------

def test_timeline_module_card_visible(page, base_url: str, model_id: str) -> None:
    page.goto(f"{base_url}/models/{model_id}/builder")
    page.wait_for_selector(".module-stack", timeout=15_000)
    assert page.locator(".module-label:has-text('Timeline')").is_visible()


# ---------------------------------------------------------------------------
# 3. Module panel content element is present
# ---------------------------------------------------------------------------

def test_module_panel_content_present(page, base_url: str, model_id: str) -> None:
    page.goto(f"{base_url}/models/{model_id}/builder")
    page.wait_for_selector("#module-panel-content", timeout=15_000)


# ---------------------------------------------------------------------------
# 4. Module nav cards container is present
# ---------------------------------------------------------------------------

def test_module_nav_cards_present(page, base_url: str, model_id: str) -> None:
    page.goto(f"{base_url}/models/{model_id}/builder")
    page.wait_for_selector("#module-nav-cards", timeout=15_000)


# ---------------------------------------------------------------------------
# 5. Clicking the Timeline card navigates to ?module=timeline
# ---------------------------------------------------------------------------

def test_timeline_module_navigable(page, base_url: str, model_id: str) -> None:
    page.goto(f"{base_url}/models/{model_id}/builder")
    page.wait_for_selector(".module-stack", timeout=15_000)
    # Click the Timeline module card
    page.locator("a.module-card", has=page.locator(".module-label:has-text('Timeline')")).first.click()
    page.wait_for_url(f"**/models/{model_id}/builder?**module=timeline**", timeout=10_000)
    page.wait_for_selector("#module-panel-content", timeout=10_000)


# ---------------------------------------------------------------------------
# 6. Sources & Uses nav card is present (may be locked, but rendered)
# ---------------------------------------------------------------------------

def test_sources_uses_nav_card_present(page, base_url: str, model_id: str) -> None:
    page.goto(f"{base_url}/models/{model_id}/builder")
    page.wait_for_selector("#module-nav-cards", timeout=15_000)
    wait_for_htmx(page)
    # "1 · Sources & Uses" module label should appear somewhere in the nav
    assert page.locator("#module-nav-cards .module-label:has-text('Sources')").count() >= 1
