"""Regression: source wizard must accept fractional interest rates.

Bug: `source_interest_rate` input had step="0.1", so a 2-decimal value like
6.88 failed HTML5 step validation. requestSubmit() tried to focus the invalid
field but it was hidden (display:none on prior steps), so submit aborted
silently with no network request and no visible error.

Fix: step="0.01" on all three source_interest_rate inputs.

This test walks the debt wizard (steps 1→3→4→5; generic debt skips the
exit step) with a 2-decimal rate (the
granularity the fix allows — 3-decimal values like 6.875 still fail
step="0.01" validation, which is the current product contract) and verifies
a capital module row appears.

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
    # The wizard's inline <script> registers swTypeChanged (the #sw-type onchange
    # handler) after the partial loads; wait for it before interacting so the
    # select is live and the amount/terms rows reveal correctly.
    page.wait_for_function(
        "() => typeof window.swTypeChanged === 'function'", timeout=5_000
    )
    # 'debt' is the single debt vehicle option (#sw-type only offers
    # debt/equity/forgivable_loan/grant/deferred_developer_fee/float_earnings;
    # granular senior/mezz/bridge is chosen later). Generic 'debt' skips the
    # Exit step, so the step sequence is 1 → 3 → 4 → 5.
    page.select_option("#sw-type", "debt")
    page.fill("#sw-label", "Senior @ 6.88%")
    page.click("#sw-next")  # step 1 → step 3 (loan terms)

    # Step 3: loan terms — set the fractional rate that previously broke submit.
    # 6.88 is a 2-decimal value: passes step="0.01", failed the old step="0.1".
    page.wait_for_selector("#sw-step-3", state="visible", timeout=5_000)
    page.fill('#sw-form input[name="source_interest_rate"]', "6.88")
    # Generic 'debt' hides the LTV row (swTypeChanged only shows it for the
    # granular debt vehicles), so there is no ltv_pct field to fill here.
    page.click("#sw-next")  # step 3 → step 4 (carry)

    # Step 4: carry — accept defaults
    page.click("#sw-next")  # step 4 → step 5 (draw)

    # Step 5: draw schedule — accept defaults, click final submit
    page.wait_for_selector("#sw-step-5", state="visible", timeout=5_000)
    page.click("#sw-next")
    wait_for_htmx(page)

    # Wait for the panel to swap in the new source row (htmx re-render after
    # submit can lag the wait_for_htmx settle by a beat on a live instance).
    row = page.locator("tr:has(td:has-text('Senior @ 6.88%'))").first
    row.wait_for(state="attached", timeout=10_000)
    assert row.count() > 0, "Debt source with fractional rate did not save"
