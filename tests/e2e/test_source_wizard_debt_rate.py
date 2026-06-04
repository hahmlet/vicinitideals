"""Regression: source wizard must accept fractional interest rates.

Bug: `source_interest_rate` input had step="0.1", so values like 6.875
failed HTML5 step validation. requestSubmit() tried to focus the invalid
field but it was hidden (display:none on prior steps), so submit aborted
silently with no network request and no visible error.

Fix: step="0.01" on all three source_interest_rate inputs.

This test walks the full 5-step debt wizard with a 3-decimal rate and
verifies a capital module row appears.

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_source_wizard_debt_rate.py -m e2e -v
"""

from __future__ import annotations

import uuid

import pytest
from playwright.sync_api import Page

from tests.e2e.helpers import wait_for_htmx
from tests.e2e.seed import create_e2e_scenario

pytestmark = pytest.mark.e2e


def _open_sources_panel(page: Page, base_url: str, model_id: str) -> None:
    page.goto(f"{base_url}/models/{model_id}/builder?module=sources_uses")
    wait_for_htmx(page)
    page.wait_for_selector("#module-panel-content", timeout=10_000)
    page.evaluate(
        "() => { const w = document.getElementById('timeline-wizard');"
        " if (w) { w.style.display = 'none'; w.remove(); } }"
    )


def _add_use(page: Page, label: str, amount: str) -> None:
    page.evaluate("() => openAddLine('uses')")
    page.wait_for_selector('#uses-wizard-body input[name="label"]', timeout=5_000)
    page.fill('#uses-wizard-body input[name="label"]', label)
    page.fill('#uses-wizard-body input[name="amount"]', amount)
    page.click('#uw-next')
    wait_for_htmx(page)
    page.click('#uw-next')
    wait_for_htmx(page)


def test_debt_wizard_accepts_fractional_rate(
    logged_in_page: Page, base_url: str
) -> None:
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(
        logged_in_page, deal_name=f"E2E DebtRate {suffix}", deal_type="acquisition"
    )
    page = logged_in_page
    _open_sources_panel(page, base_url, model_id)

    _add_use(page, "Acquisition", "500000")

    page.evaluate("() => openAddLine('sources')")
    page.wait_for_selector("#sw-form", timeout=5_000)

    page.select_option("#sw-type", "senior_debt")
    page.fill("#sw-label", "Senior @ 6.875%")
    page.click("#sw-next")  # step 1 → step 2

    # Step 2: exit terms — leave defaults (maturity)
    page.click("#sw-next")  # step 2 → step 3

    # Step 3: loan terms — set the fractional rate that previously broke submit
    page.fill('#sw-form input[name="source_interest_rate"]', "6.875")
    page.fill('#sw-form input[name="ltv_pct"]', "65")
    page.click("#sw-next")  # step 3 → step 4

    # Step 4: carry — accept defaults
    page.click("#sw-next")  # step 4 → step 5

    # Step 5: draw schedule — accept defaults, click final submit
    page.click("#sw-next")
    wait_for_htmx(page)

    row = page.locator("tr:has(td:has-text('Senior @ 6.875%'))").first
    assert row.count() > 0, "Debt source with fractional rate did not save"
