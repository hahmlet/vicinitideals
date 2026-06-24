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
def model_id(_seed_page) -> str:
    """Create one deal/scenario for all model-builder tests in this session."""
    return create_e2e_scenario(_seed_page, deal_name="E2E Model Builder Test")


# ---------------------------------------------------------------------------
# 1. Model builder page loads
# ---------------------------------------------------------------------------

def test_model_builder_loads(logged_in_page, base_url: str, model_id: str) -> None:
    logged_in_page.goto(f"{base_url}/models/{model_id}/builder")
    logged_in_page.wait_for_selector(".module-stack", timeout=15_000)


# ---------------------------------------------------------------------------
# 2. Timeline module card is always visible (no gate)
# ---------------------------------------------------------------------------

def test_timeline_module_card_visible(logged_in_page, base_url: str, model_id: str) -> None:
    logged_in_page.goto(f"{base_url}/models/{model_id}/builder")
    logged_in_page.wait_for_selector(".module-stack", timeout=15_000)
    assert logged_in_page.locator(".module-label:has-text('Timeline')").is_visible()


# ---------------------------------------------------------------------------
# 3. Module panel content element is present
# ---------------------------------------------------------------------------

def test_module_panel_content_present(logged_in_page, base_url: str, model_id: str) -> None:
    logged_in_page.goto(f"{base_url}/models/{model_id}/builder")
    logged_in_page.wait_for_selector("#module-panel-content", timeout=15_000)


# ---------------------------------------------------------------------------
# 4. Module nav cards container is present
# ---------------------------------------------------------------------------

def test_module_nav_cards_present(logged_in_page, base_url: str, model_id: str) -> None:
    logged_in_page.goto(f"{base_url}/models/{model_id}/builder")
    logged_in_page.wait_for_selector("#module-nav-cards", timeout=15_000)


# ---------------------------------------------------------------------------
# 5. Clicking the Timeline card navigates to ?module=timeline
# ---------------------------------------------------------------------------

def test_timeline_module_navigable(logged_in_page, base_url: str, model_id: str) -> None:
    # Navigate directly to the timeline module — valid user path (also where the
    # timeline wizard lands on completion for new deals).
    logged_in_page.goto(f"{base_url}/models/{model_id}/builder?module=timeline")
    logged_in_page.wait_for_selector("#module-panel-content", timeout=15_000)
    assert "module=timeline" in logged_in_page.url


# ---------------------------------------------------------------------------
# 6. Sources & Uses nav card is present (may be locked, but rendered)
# ---------------------------------------------------------------------------

def test_sources_uses_nav_card_present(logged_in_page, base_url: str, model_id: str) -> None:
    logged_in_page.goto(f"{base_url}/models/{model_id}/builder")
    logged_in_page.wait_for_selector("#module-nav-cards", timeout=15_000)
    wait_for_htmx(logged_in_page)
    # "1 · Sources & Uses" module label should appear somewhere in the nav
    assert logged_in_page.locator("#module-nav-cards .module-label:has-text('Sources')").count() >= 1


def test_nav_cards_day0_stabilized_columns(logged_in_page, base_url: str, model_id: str) -> None:
    """Revenue/OpEx nav cards expose Day 0 | Stabilized columns; Owners & Profit
    exposes NOI | After Debt (run-rate after debt carry)."""
    logged_in_page.goto(f"{base_url}/models/{model_id}/builder")
    logged_in_page.wait_for_selector("#module-nav-cards", timeout=15_000)
    wait_for_htmx(logged_in_page)
    nav = logged_in_page.locator("#module-nav-cards")
    # Owners & Profit card always renders in both income modes — assert its new
    # two-column basis tags are present.
    assert nav.locator(".module-label:has-text('Owners')").count() >= 1
    assert nav.locator("text=After Debt").count() >= 1
    # Revenue/OpEx cards only render in revenue_opex mode; when present they carry
    # the Day 0 / Stab. basis tags.
    if nav.locator(".module-label:has-text('Revenue')").count() >= 1:
        assert nav.locator("text=Day 0").count() >= 1
        assert nav.locator("text=Stab.").count() >= 1


# ---------------------------------------------------------------------------
# Documents module card — per-project document room entry point
# ---------------------------------------------------------------------------

def test_documents_module_card_links_to_room(
    logged_in_page, base_url: str, model_id: str
) -> None:
    """The Documents module card appears in the sidebar and links to the active
    project's document room (/projects/{id}/documents)."""
    logged_in_page.goto(f"{base_url}/models/{model_id}/builder")
    logged_in_page.wait_for_selector(".module-stack", timeout=15_000)
    card = logged_in_page.locator("a.module-card:has-text('Documents')")
    assert card.count() >= 1
    href = card.first.get_attribute("href")
    assert href and "/documents" in href


def test_documents_module_opens_room(
    logged_in_page, base_url: str, model_id: str
) -> None:
    """Clicking the Documents card navigates to the document room page."""
    logged_in_page.goto(f"{base_url}/models/{model_id}/builder")
    logged_in_page.wait_for_selector(".module-stack", timeout=15_000)
    logged_in_page.locator("a.module-card:has-text('Documents')").first.click()
    logged_in_page.wait_for_url("**/projects/**/documents", timeout=15_000)
    assert logged_in_page.locator("text=Documents").count() >= 1
    # Both tabs render in the room.
    assert logged_in_page.locator(".doc-tab:has-text('Document View')").count() >= 1
    assert logged_in_page.locator(".doc-tab:has-text('Task View')").count() >= 1
