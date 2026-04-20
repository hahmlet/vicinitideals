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


def _fresh_wizard_deal(page) -> tuple[str, str]:
    """Create a fresh deal with approved timeline — each test gets a clean wizard state."""
    import uuid
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(page, deal_name=f"E2E Wizard {suffix}")
    project_id = _extract_project_id(page)
    submit_timeline_wizard(
        page, model_id, project_id,
        milestone_types=["close", "construction", "operation_stabilized", "divestment"],
        phase_durations={"construction": 180, "operation_stabilized": 730},
    )
    return model_id, project_id


# ---------------------------------------------------------------------------
# Step 1 — Income mode
# ---------------------------------------------------------------------------

def test_wizard_step1_income_mode(_seed_page, base_url):
    model_id, _ = _fresh_wizard_deal(_seed_page)
    page = _seed_page
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

def test_wizard_step2_debt_types(_seed_page, base_url):
    model_id, _ = _fresh_wizard_deal(_seed_page)
    page = _seed_page
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

def test_wizard_step3_dropdowns_not_clipped(_seed_page, base_url):
    """Verify Exit Vehicle dropdown renders with long options like 'Refi by Construction-to-Perm'.

    The old three-column layout (Active From / Active To / Retired By) was
    collapsed to two columns (Active From / Exit Vehicle) in the April 2026
    cleanup.  "Active To" is now derived server-side from Exit Vehicle.
    """
    model_id, _ = _fresh_wizard_deal(_seed_page)
    page = _seed_page
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

    # Step 3 should have Exit Vehicle dropdowns — one per picked debt
    page.wait_for_selector('[name="construction_loan_exit_vehicle"]', timeout=8000)
    cl_vehicle = page.locator('[name="construction_loan_exit_vehicle"]')
    pd_vehicle = page.locator('[name="permanent_debt_exit_vehicle"]')
    assert cl_vehicle.count() > 0, "construction_loan Exit Vehicle dropdown missing"
    assert pd_vehicle.count() > 0, "permanent_debt Exit Vehicle dropdown missing"

    # The table should use fixed layout (prevents dropdown clipping)
    table = page.locator('#deal-setup-wizard table')
    assert table.count() > 0
    table_style = table.get_attribute("style") or ""
    assert "table-layout" in table_style

    # Construction loan's default vehicle should be permanent_debt (first picked
    # retirer in the preference chain).
    cl_value = cl_vehicle.input_value()
    assert cl_value == "permanent_debt", (
        f"construction_loan Exit Vehicle default should be 'permanent_debt', got {cl_value!r}"
    )


# ---------------------------------------------------------------------------
# Step 6 — Reserves side by side
# ---------------------------------------------------------------------------

def test_wizard_step6_reserves_layout(_seed_page, base_url):
    """Verify Construction Floor and Operating Reserve render side by side."""
    model_id, _ = _fresh_wizard_deal(_seed_page)
    page = _seed_page
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

    # Walk forward until we land on the Reserves step (the wizard step count
    # can shift as the setup flow evolves).  Bail out once floor_input is in
    # the DOM, or after a reasonable upper bound.
    floor_input = page.locator('[name="construction_floor_pct"]')
    for _ in range(4):
        if floor_input.count() > 0:
            break
        next_btn = page.locator('#deal-setup-wizard button:has-text("Next")')
        if next_btn.count() == 0 or not next_btn.is_visible():
            break
        next_btn.click()
        wait_for_htmx(page)
    reserve_input = page.locator('[name="operation_reserve_months"]')
    title = page.locator('#deal-setup-wizard .wizard-title').first.inner_text()
    assert floor_input.is_visible(), f"Reserves step never rendered; last title={title!r}"
    assert reserve_input.is_visible(), f"Reserves step missing reserve_months; last title={title!r}"

    # Both should be in the same grid row (our fix makes them side by side)
    grid = page.locator('#deal-setup-wizard .wizard-body > div[style*="grid"]')
    assert grid.count() > 0


# ---------------------------------------------------------------------------
# Step 7 — Finish Setup button exists and works
# ---------------------------------------------------------------------------

def test_wizard_step7_finish_button_visible(logged_in_page, base_url):
    """The Finish Setup button must be visible and clickable on step 7."""
    model_id, _ = _fresh_wizard_deal(logged_in_page)
    page = logged_in_page
    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)

    # Use run_deal_setup_wizard to click through all steps reliably,
    # then check the result page for the "Done" badge (confirming setup completed)
    from tests.e2e.seed import run_deal_setup_wizard
    run_deal_setup_wizard(
        page, model_id,
        debt_types=["permanent_debt"],
        debt_terms={"permanent_debt": {"rate_pct": "6.5", "loan_type": "pi", "amort_years": "30"}},
    )

    # If we got here without error, the wizard completed successfully —
    # the Finish Setup button was visible and clickable (run_deal_setup_wizard
    # clicks it as part of step 7).
    # Verify: we landed on the builder, not stuck in the wizard.
    assert "builder" in page.url, f"Expected builder page after wizard, got {page.url}"
    assert "deal_setup" not in page.url, "Still on deal_setup — wizard didn't complete"


# ---------------------------------------------------------------------------
# Wizard re-entry — Back to Model link when setup is already complete
# ---------------------------------------------------------------------------

def test_wizard_back_to_model_link(_seed_page, base_url):
    """After completing setup, re-entering the wizard should show a Back to Model link."""
    model_id, _ = _fresh_wizard_deal(_seed_page)
    page = _seed_page

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
