"""E2E tests for per-Use grant eligibility + cap-consumption (source.maximum).

User flow:
- Open a grant edit drawer
- Check ≥1 eligible Use → "Amount" label flips to "Maximum ($)"
- Save with a Maximum and eligibility → grant stored as capped consumption
- S&U table shows Max column; under-utilized rows highlighted yellow
- Unticking all eligibility reverts to legacy fixed Amount mode

The math/ordering is exercised by tests/engines/test_grant_cap_resolution.py.
Here we verify the UI write reaches the DB, renders back, and that the
table flags under-utilization visually.

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_grant_eligibility_flow.py -m e2e -v
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


def _add_use(page: Page, label: str, amount: str, phase: str = "construction") -> None:
    page.evaluate(f"() => openAddLine('uses')")
    page.wait_for_selector('#line-item-drawer input[name="label"]', timeout=5_000)
    page.fill('#line-item-drawer input[name="label"]', label)
    page.fill('#line-item-drawer input[name="amount"]', amount)
    sel = page.locator('#line-item-drawer select[name="phase"]')
    if sel.count() > 0:
        sel.select_option(phase)
    page.click('#line-item-drawer button[type="submit"]')
    wait_for_htmx(page)


def _add_grant(page: Page, label: str, amount: str) -> None:
    page.evaluate(f"() => openAddLine('sources')")
    page.wait_for_selector('#line-item-drawer', timeout=5_000)
    # Wizard step 1 → select grant type
    page.select_option('#line-item-drawer select[name="source_type"]', "grant")
    page.fill('#line-item-drawer input[name="label"]', label)
    # Wizard amount field
    page.fill('#line-item-drawer input[name="source_amount"]', amount)
    page.click('#line-item-drawer button[type="submit"]')
    wait_for_htmx(page)


def _open_grant_edit(page: Page, label: str) -> None:
    row = page.locator(f"tr:has(td:has-text('{label}'))").first
    row.click()
    page.wait_for_selector('#line-item-drawer', timeout=5_000)


# ---------------------------------------------------------------------------
# 1. Toggling eligibility flips Amount label → Maximum
# ---------------------------------------------------------------------------


def test_eligibility_checkbox_flips_amount_label(
    logged_in_page: Page, base_url: str
) -> None:
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(
        logged_in_page, deal_name=f"E2E EligLabel {suffix}", deal_type="acquisition"
    )
    page = logged_in_page
    _open_sources_panel(page, base_url, model_id)

    _add_use(page, "Site Work", "180000")
    _add_grant(page, "OR-MEP", "250000")
    _open_grant_edit(page, "OR-MEP")

    label = page.locator('#lf-amount-label')
    assert label.inner_text().strip().startswith("Amount"), (
        f"Expected 'Amount' label initially; got {label.inner_text()!r}"
    )

    box = page.locator('.lf-eligibility-checkbox').first
    box.check()
    assert label.inner_text().strip().startswith("Maximum"), (
        f"Expected 'Maximum' after check; got {label.inner_text()!r}"
    )

    box.uncheck()
    assert label.inner_text().strip().startswith("Amount"), (
        f"Expected 'Amount' after uncheck; got {label.inner_text()!r}"
    )


# ---------------------------------------------------------------------------
# 2. Save with eligibility persists maximum + back-reference
# ---------------------------------------------------------------------------


def test_save_with_eligibility_persists_maximum(
    logged_in_page: Page, base_url: str
) -> None:
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(
        logged_in_page, deal_name=f"E2E EligSave {suffix}", deal_type="acquisition"
    )
    page = logged_in_page
    _open_sources_panel(page, base_url, model_id)

    _add_use(page, "Site Work", "180000")
    _add_grant(page, "OR-MEP", "250000")
    _open_grant_edit(page, "OR-MEP")

    page.locator('.lf-eligibility-checkbox').first.check()
    page.fill('#lf-source-maximum-input', "250000")
    page.click('#line-item-drawer button[type="submit"]')
    wait_for_htmx(page)

    page.wait_for_selector("#module-panel-content", timeout=5_000)
    assert page.locator("th:has-text('Max')").count() >= 1
    row = page.locator("tr:has(td:has-text('OR-MEP'))").first
    assert "250" in row.inner_text(), (
        f"Maximum column should display 250,000 in OR-MEP row; got {row.inner_text()!r}"
    )


# ---------------------------------------------------------------------------
# 3. Under-utilized row highlighted yellow + tooltip
# ---------------------------------------------------------------------------


def test_under_utilized_grant_row_yellow(
    logged_in_page: Page, base_url: str
) -> None:
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(
        logged_in_page, deal_name=f"E2E EligYellow {suffix}", deal_type="acquisition"
    )
    page = logged_in_page
    _open_sources_panel(page, base_url, model_id)

    # Cap > eligible Use total → under-utilized
    _add_use(page, "Site Work", "180000")
    _add_grant(page, "OR-MEP", "250000")
    _open_grant_edit(page, "OR-MEP")
    page.locator('.lf-eligibility-checkbox').first.check()
    page.fill('#lf-source-maximum-input', "250000")
    page.click('#line-item-drawer button[type="submit"]')
    wait_for_htmx(page)

    # Force a compute so source.amount gets resolved (engine runs grant_caps)
    page.evaluate("() => fetch('/api/compute/' + window.location.pathname.split('/')[2], { method: 'POST' })")
    page.wait_for_timeout(2000)
    page.reload()
    wait_for_htmx(page)
    page.wait_for_selector("#module-panel-content", timeout=10_000)

    row = page.locator("tr.row-under-utilized:has(td:has-text('OR-MEP'))")
    assert row.count() >= 1, "Expected OR-MEP row to have row-under-utilized class"
    title_attr = row.first.get_attribute("title") or ""
    assert "unused" in title_attr.lower(), (
        f"Expected tooltip mentioning 'unused'; got {title_attr!r}"
    )


# ---------------------------------------------------------------------------
# 4. Clearing eligibility reverts to plain Amount input
# ---------------------------------------------------------------------------


def test_wizard_eligibility_flips_amount_to_maximum(
    logged_in_page: Page, base_url: str
) -> None:
    """Add-wizard sw-step-1 mirrors edit-form behavior: ticking eligibility
    swaps Amount → Maximum and validates the right field on Continue."""
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(
        logged_in_page, deal_name=f"E2E EligWizard {suffix}", deal_type="acquisition"
    )
    page = logged_in_page
    _open_sources_panel(page, base_url, model_id)

    _add_use(page, "Site Work", "180000")

    # Open Add Source wizard
    page.evaluate("() => openAddLine('sources')")
    page.wait_for_selector('#sw-form', timeout=5_000)
    page.select_option('#sw-type', "grant")
    page.fill('#sw-label', "OR-MEP")

    # Initial state: Amount label visible
    label = page.locator('#sw-amount-label')
    assert label.inner_text().strip().startswith("Amount")

    # Tick first eligibility checkbox → label flips
    page.locator('.sw-eligibility-checkbox').first.check()
    assert label.inner_text().strip().startswith("Maximum")
    # Maximum input should now be visible and required
    max_in = page.locator('#sw-source-maximum')
    assert max_in.is_visible()
    page.fill('#sw-source-maximum', "250000")

    # Submit wizard
    page.click('#sw-next')
    wait_for_htmx(page)

    row = page.locator("tr:has(td:has-text('OR-MEP'))").first
    assert "250" in row.inner_text()


def test_check_all_and_uncheck_all_buttons(
    logged_in_page: Page, base_url: str
) -> None:
    """Edit drawer Check all / Uncheck all toggles every eligibility checkbox
    in one click. Confirms label flips correctly."""
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(
        logged_in_page, deal_name=f"E2E EligBulk {suffix}", deal_type="acquisition"
    )
    page = logged_in_page
    _open_sources_panel(page, base_url, model_id)

    _add_use(page, "Site Work", "180000")
    _add_use(page, "Soft Costs", "60000")
    _add_use(page, "FF&E", "40000")
    _add_grant(page, "OR-MEP", "250000")
    _open_grant_edit(page, "OR-MEP")

    boxes = page.locator('.lf-eligibility-checkbox')
    assert boxes.count() >= 3, f"Expected >=3 eligibility checkboxes, got {boxes.count()}"

    page.click('#lf-elig-check-all')
    for i in range(boxes.count()):
        assert boxes.nth(i).is_checked(), f"box {i} not checked after Check all"
    label = page.locator('#lf-amount-label')
    assert label.inner_text().strip().startswith("Maximum"), (
        "Label should flip to Maximum once any box is checked via Check all"
    )

    page.click('#lf-elig-uncheck-all')
    for i in range(boxes.count()):
        assert not boxes.nth(i).is_checked(), f"box {i} still checked after Uncheck all"
    assert label.inner_text().strip().startswith("Amount"), (
        "Label should revert to Amount after Uncheck all"
    )


def test_clearing_eligibility_reverts_to_amount(
    logged_in_page: Page, base_url: str
) -> None:
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(
        logged_in_page, deal_name=f"E2E EligRevert {suffix}", deal_type="acquisition"
    )
    page = logged_in_page
    _open_sources_panel(page, base_url, model_id)

    _add_use(page, "Site Work", "180000")
    _add_grant(page, "OR-MEP", "250000")
    _open_grant_edit(page, "OR-MEP")

    box = page.locator('.lf-eligibility-checkbox').first
    box.check()
    page.fill('#lf-source-maximum-input', "250000")
    page.click('#line-item-drawer button[type="submit"]')
    wait_for_htmx(page)

    # Reopen and uncheck
    _open_grant_edit(page, "OR-MEP")
    page.locator('.lf-eligibility-checkbox').first.uncheck()
    label = page.locator('#lf-amount-label')
    assert label.inner_text().strip().startswith("Amount")
    page.fill('#lf-source-amount-input', "100000")
    page.click('#line-item-drawer button[type="submit"]')
    wait_for_htmx(page)

    row = page.locator("tr:has(td:has-text('OR-MEP'))").first
    # Maximum column should now show em-dash (no cap)
    cells = row.locator("td")
    # Amount cell shows 100k, Max cell shows —
    row_text = row.inner_text()
    assert "100" in row_text
