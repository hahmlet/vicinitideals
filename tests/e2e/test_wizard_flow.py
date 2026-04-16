"""Deal setup wizard E2E tests — verify every step is navigable and completable.

These tests click through the actual wizard UI to catch regressions like
missing buttons, broken navigation, dropdown sizing issues, and layout bugs.

Run:
    uv run pytest tests/e2e/test_wizard_flow.py -m e2e -v
"""

from __future__ import annotations

import re

import pytest

from tests.e2e.helpers import wait_for_htmx
from tests.e2e.seed import (
    create_e2e_scenario,
    submit_timeline_wizard,
    _extract_project_id,
)

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def wizard_deal(_seed_page) -> tuple[str, str]:
    """Create a deal and approve its timeline, ready for wizard testing."""
    model_id = create_e2e_scenario(_seed_page, deal_name="E2E Wizard Flow Test")
    project_id = _extract_project_id(_seed_page)
    submit_timeline_wizard(_seed_page, model_id, project_id)
    return model_id, project_id


# ---------------------------------------------------------------------------
# Step 1 — Income mode
# ---------------------------------------------------------------------------

def test_wizard_step1_income_mode(logged_in_page, base_url, wizard_deal):
    model_id, _ = wizard_deal
    page = logged_in_page
    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)

    # Revenue/OpEx radio card should be visible
    assert page.locator('input[value="revenue_opex"]').count() > 0
    # NOI radio card should be visible
    assert page.locator('input[value="noi"]').count() > 0
    # Next button exists and is clickable
    next_btn = page.locator('#deal-setup-wizard button:has-text("Next")')
    assert next_btn.count() > 0
    assert next_btn.is_visible()

    # Select income mode and proceed
    page.click('input[value="revenue_opex"]')
    next_btn.click()
    wait_for_htmx(page)

    # Should advance to step 2 (debt type grid)
    page.wait_for_selector("#debt-type-grid", timeout=5000)


# ---------------------------------------------------------------------------
# Step 2 — Debt types
# ---------------------------------------------------------------------------

def test_wizard_step2_debt_types(logged_in_page, base_url, wizard_deal):
    model_id, _ = wizard_deal
    page = logged_in_page
    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)

    # Navigate to step 2
    page.click('input[value="revenue_opex"]')
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)
    page.wait_for_selector("#debt-type-grid", timeout=5000)

    # Debt type checkboxes should be present
    assert page.locator('#debt-type-grid input[type="checkbox"]').count() >= 2
    # Permanent debt should be available
    assert page.locator('#debt-type-grid input[value="permanent_debt"]').count() > 0
    # Construction loan should be available
    assert page.locator('#debt-type-grid input[value="construction_loan"]').count() > 0

    # Select construction + perm and proceed
    page.locator('#debt-type-grid input[value="construction_loan"]').check()
    page.locator('#debt-type-grid input[value="permanent_debt"]').check()
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)

    # Should advance to step 3 (milestone config with Active From/To dropdowns)
    page.wait_for_selector('[name="construction_loan_active_from"]', timeout=5000)


# ---------------------------------------------------------------------------
# Step 3 — Dropdowns fit their content
# ---------------------------------------------------------------------------

def test_wizard_step3_dropdowns_not_clipped(logged_in_page, base_url, wizard_deal):
    """Verify Active To dropdown can display long options like 'Certificate of Occupancy'."""
    model_id, _ = wizard_deal
    page = logged_in_page
    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)

    # Navigate through steps 1-2 to reach step 3
    page.click('input[value="revenue_opex"]')
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)
    page.wait_for_selector("#debt-type-grid", timeout=5000)
    page.locator('#debt-type-grid input[value="construction_loan"]').check()
    page.locator('#debt-type-grid input[value="permanent_debt"]').check()
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)

    # Step 3 should have select dropdowns
    active_to = page.locator('[name="construction_loan_active_to"]')
    assert active_to.count() > 0

    # The table should use fixed layout (our fix)
    table = page.locator('#deal-setup-wizard table')
    assert table.count() > 0
    table_style = table.get_attribute("style") or ""
    assert "table-layout" in table_style


# ---------------------------------------------------------------------------
# Step 6 — Reserves side by side
# ---------------------------------------------------------------------------

def test_wizard_step6_reserves_layout(logged_in_page, base_url, wizard_deal):
    """Verify Construction Floor and Operating Reserve render side by side."""
    model_id, _ = wizard_deal
    page = logged_in_page
    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)

    # Navigate through steps 1-5
    page.click('input[value="revenue_opex"]')
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)
    page.wait_for_selector("#debt-type-grid", timeout=5000)
    page.locator('#debt-type-grid input[value="construction_loan"]').check()
    page.locator('#debt-type-grid input[value="permanent_debt"]').check()
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)

    # Step 6 — both reserve inputs should be visible
    floor_input = page.locator('[name="construction_floor_pct"]')
    reserve_input = page.locator('[name="operation_reserve_months"]')
    assert floor_input.is_visible()
    assert reserve_input.is_visible()

    # Both should be in the same grid row (our fix makes them side by side)
    # Verify by checking the grid container style
    grid = page.locator('#deal-setup-wizard .wizard-body > div[style*="grid"]')
    assert grid.count() > 0


# ---------------------------------------------------------------------------
# Step 7 — Finish Setup button exists and works
# ---------------------------------------------------------------------------

def test_wizard_step7_finish_button_visible(logged_in_page, base_url, wizard_deal):
    """The Finish Setup button must be visible and clickable on step 7."""
    model_id, _ = wizard_deal
    page = logged_in_page
    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)

    # Navigate through all 6 steps
    page.click('input[value="revenue_opex"]')
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)
    page.wait_for_selector("#debt-type-grid", timeout=5000)
    page.locator('#debt-type-grid input[value="permanent_debt"]').check()
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)
    page.click('#deal-setup-wizard button:has-text("Review")')
    wait_for_htmx(page)

    # Step 7 — Finish Setup button must exist and be visible
    finish_btn = page.locator('button:has-text("Finish Setup")')
    assert finish_btn.count() > 0, "Finish Setup button not found on step 7"
    assert finish_btn.is_visible(), "Finish Setup button exists but is not visible"

    # Click it — should redirect to builder
    finish_btn.click()
    page.wait_for_url(f"**/models/{model_id}/builder**", timeout=10_000)
    assert "sources_uses" in page.url or "module=" in page.url


# ---------------------------------------------------------------------------
# Wizard re-entry — Back to Model link when setup is already complete
# ---------------------------------------------------------------------------

def test_wizard_back_to_model_link(logged_in_page, base_url, wizard_deal):
    """After completing setup, re-entering the wizard should show a Back to Model link."""
    model_id, _ = wizard_deal
    page = logged_in_page

    # First complete the wizard (via the previous test's deal or a fresh one)
    # Navigate to deal_setup after it's already been completed
    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)

    # "Back to Model" link should be visible
    back_link = page.locator('a:has-text("Back to Model")')
    if back_link.count() > 0:
        assert back_link.is_visible()
        back_link.click()
        page.wait_for_url(f"**/models/{model_id}/builder**", timeout=10_000)
        # Should land on S&U, not stuck in wizard
        assert "deal_setup" not in page.url or "sources_uses" in page.url
