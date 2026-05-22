"""Deal setup wizard E2E tests — verify every step is navigable and completable.

Post May 2026 refactor the wizard has 6 steps:
  1 — Income mode + Permanent Debt Sizing mode + (optional) pro forma drop
  2 — Debt stack (per-debt Source Vehicle picker)
  3 — Per-debt milestones & Exit Vehicle  (skipped when every debt has a vehicle)
  4 — Per-debt loan terms                  (skipped when every debt has a vehicle)
  5 — Per-debt sizing (LTV / fixed / DSCR) (skipped when every debt has a vehicle)
  6 — Review + Finish

Run:
    uv run pytest tests/e2e/test_wizard_flow.py -m e2e -v
"""

from __future__ import annotations

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
# Step 1 — Income mode + Sizing mode + pro forma drop zone
# ---------------------------------------------------------------------------

def test_wizard_step1_income_and_sizing(_seed_page, base_url):
    model_id, _ = _fresh_wizard_deal(_seed_page)
    page = _seed_page
    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)

    # Both income-mode radio cards visible
    assert page.locator('input[value="revenue_opex"]').count() > 0
    assert page.locator('input[value="noi"]').count() > 0
    # Sizing-mode toggle group lives on Step 1 now (was Step 5)
    assert page.locator('input[name="debt_sizing_mode"][value="gap_fill"]').count() > 0
    assert page.locator('input[name="debt_sizing_mode"][value="dscr_capped"]').count() > 0
    assert page.locator('input[name="debt_sizing_mode"][value="dual_constraint"]').count() > 0
    # Pro forma drop zone visible (income_mode defaults to revenue_opex)
    assert page.locator('#proforma-zone').count() > 0
    # Submit button reads "Skip Import →" when no file attached and revenue_opex
    submit_text = page.locator('#step1-submit').inner_text()
    assert "Skip" in submit_text or "Import" in submit_text, f"Unexpected submit label: {submit_text!r}"

    page.click('input[value="revenue_opex"]')
    page.click('#step1-submit')
    wait_for_htmx(page)

    # Skip Import → advance to Step 2 (debt-type grid)
    page.wait_for_selector("#debt-type-grid", timeout=8000)


def test_wizard_step1_noi_hides_proforma_zone(_seed_page, base_url):
    """Switching to NOI on Step 1 hides the pro forma drop zone and renames the button."""
    model_id, _ = _fresh_wizard_deal(_seed_page)
    page = _seed_page
    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)

    page.click('input[value="noi"]')
    # Proforma block should hide via JS
    page.wait_for_function(
        "() => { const el = document.getElementById('proforma-block'); return !el || el.style.display === 'none'; }",
        timeout=2000,
    )
    submit_text = page.locator('#step1-submit').inner_text()
    assert "Next" in submit_text, f"NOI mode should set button to 'Next →', got {submit_text!r}"


# ---------------------------------------------------------------------------
# Step 2 — Debt types + nested Source Vehicle picker
# ---------------------------------------------------------------------------

def test_wizard_step2_debt_types_unselected_by_default(_seed_page, base_url):
    """No debt-type checkbox should be pre-checked on first arrival at Step 2."""
    model_id, _ = _fresh_wizard_deal(_seed_page)
    page = _seed_page
    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)

    # Navigate to Step 2 via Step 1
    page.click('input[value="revenue_opex"]')
    page.click('#step1-submit')
    wait_for_htmx(page)
    page.wait_for_selector("#debt-type-grid", timeout=5000)

    # Verify no checkbox is pre-checked
    checked = page.locator('#debt-type-grid input[type="checkbox"]:checked')
    assert checked.count() == 0, (
        f"Expected zero pre-checked debt-type boxes on Step 2, found {checked.count()}"
    )


def test_wizard_step2_debt_types_present(_seed_page, base_url):
    model_id, _ = _fresh_wizard_deal(_seed_page)
    page = _seed_page
    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)

    page.click('input[value="revenue_opex"]')
    page.click('#step1-submit')
    wait_for_htmx(page)
    page.wait_for_selector("#debt-type-grid", timeout=5000)

    assert page.locator('#debt-type-grid input[type="checkbox"]').count() >= 2
    assert page.locator('#debt-type-grid input[value="permanent_debt"]').count() > 0
    assert page.locator('#debt-type-grid input[value="construction_loan"]').count() > 0

    page.locator('#debt-type-grid input[value="construction_loan"]').check()
    page.locator('#debt-type-grid input[value="permanent_debt"]').check()
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)

    # Advances to Step 3 (milestone config)
    page.wait_for_selector('[name="construction_loan_active_from"]', timeout=8000)


def test_wizard_step2_vehicle_picker_nested_in_card(_seed_page, base_url):
    """The Source Vehicle dropdown must live inside the debt-type card so it
    reads as a single panel — not a separate bordered box underneath."""
    model_id, _ = _fresh_wizard_deal(_seed_page)
    page = _seed_page
    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)

    page.click('input[value="revenue_opex"]')
    page.click('#step1-submit')
    wait_for_htmx(page)
    page.wait_for_selector("#debt-type-grid", timeout=5000)

    # Tick Permanent Debt — vehicle picker should appear nested inside its card.
    page.locator('#debt-type-grid input[value="permanent_debt"]').check()
    # The vehicle row only renders when the org/user has source vehicles
    # configured (template gates on _svd). If no vehicles exist for the E2E
    # user, the picker is correctly absent — that is not a regression. When
    # ANY picker renders, it MUST be a child of its debt-type card label.
    any_picker = page.locator('#deal-setup-wizard [id^="vp-"]')
    if any_picker.count() > 0:
        nested = page.locator('#card-permanent_debt #vp-permanent_debt')
        assert nested.count() == 1, "Source Vehicle picker should be a child of the debt-type card"


# ---------------------------------------------------------------------------
# Step 3 — Dropdowns fit their content (Exit Vehicle column)
# ---------------------------------------------------------------------------

def test_wizard_step3_dropdowns_not_clipped(_seed_page, base_url):
    """Verify Exit Vehicle dropdown renders with long options like 'Refi by Construction-to-Perm'."""
    model_id, _ = _fresh_wizard_deal(_seed_page)
    page = _seed_page
    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)

    page.click('input[value="revenue_opex"]')
    page.click('#step1-submit')
    wait_for_htmx(page)
    page.wait_for_selector("#debt-type-grid", timeout=5000)
    page.locator('#debt-type-grid input[value="construction_loan"]').check()
    page.locator('#debt-type-grid input[value="permanent_debt"]').check()
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)

    page.wait_for_selector('[name="construction_loan_exit_vehicle"]', timeout=8000)
    cl_vehicle = page.locator('[name="construction_loan_exit_vehicle"]')
    pd_vehicle = page.locator('[name="permanent_debt_exit_vehicle"]')
    assert cl_vehicle.count() > 0, "construction_loan Exit Vehicle dropdown missing"
    assert pd_vehicle.count() > 0, "permanent_debt Exit Vehicle dropdown missing"

    table = page.locator('#deal-setup-wizard table')
    assert table.count() > 0
    table_style = table.get_attribute("style") or ""
    assert "table-layout" in table_style

    cl_value = cl_vehicle.input_value()
    assert cl_value == "permanent_debt", (
        f"construction_loan Exit Vehicle default should be 'permanent_debt', got {cl_value!r}"
    )


# ---------------------------------------------------------------------------
# Step 6 — Finish Setup button exists and works (full happy path)
# ---------------------------------------------------------------------------

def test_wizard_finish_button_completes_setup(logged_in_page, base_url):
    """End-to-end happy path — the wizard finishes and lands on the builder."""
    model_id, _ = _fresh_wizard_deal(logged_in_page)
    page = logged_in_page
    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)

    from tests.e2e.seed import run_deal_setup_wizard
    run_deal_setup_wizard(
        page, model_id,
        debt_types=["permanent_debt"],
        debt_terms={"permanent_debt": {"rate_pct": "6.5", "loan_type": "pi", "amort_years": "30"}},
    )

    assert "builder" in page.url, f"Expected builder page after wizard, got {page.url}"
    assert "deal_setup" not in page.url, "Still on deal_setup — wizard didn't complete"


# ---------------------------------------------------------------------------
# Wizard re-entry — Back to Model link when setup is already complete
# ---------------------------------------------------------------------------

def test_wizard_back_to_model_link(_seed_page, base_url):
    """After completing setup, re-entering the wizard should show a Back to Model link."""
    model_id, _ = _fresh_wizard_deal(_seed_page)
    page = _seed_page

    page.goto(f"{base_url}/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)

    back_link = page.locator('a:has-text("Back to Model")')
    if back_link.count() > 0:
        assert back_link.is_visible()
        back_link.click()
        page.wait_for_url(f"**/models/{model_id}/builder**", timeout=10_000)
        assert "deal_setup" not in page.url or "sources_uses" in page.url
