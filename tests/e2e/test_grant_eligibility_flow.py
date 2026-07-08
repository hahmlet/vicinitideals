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


def _hide_timeline_wizard(page: Page) -> None:
    page.evaluate(
        "() => { const w = document.getElementById('timeline-wizard');"
        " if (w) { w.style.display = 'none'; w.remove(); } }"
    )


# Adds happen on the combined sources_uses view (the natural editing surface,
# and where the add/edit refresh leaves the panel). The add/edit wizards are
# page-level modals, so openAddLine / openEditLine work regardless of module.
def _open_sources_panel(page: Page, base_url: str, model_id: str) -> None:
    page.goto(f"{base_url}/models/{model_id}/builder?module=sources_uses")
    wait_for_htmx(page)
    page.wait_for_selector("#module-panel-content", timeout=10_000)
    _hide_timeline_wizard(page)


# The "Max" column + the under-utilized row highlight render ONLY in the
# standalone Sources module — the combined sources_uses Sources sub-table omits
# them. Tests that assert on those surfaces must hop here AFTER their add/edit
# steps. A full navigation re-opens the timeline-wizard overlay, so re-hide it.
def _show_sources_module(page: Page, base_url: str, model_id: str) -> None:
    page.goto(f"{base_url}/models/{model_id}/builder?module=sources")
    wait_for_htmx(page)
    page.wait_for_selector("#sources-drag-tbody", timeout=10_000)
    _hide_timeline_wizard(page)


def _label_starts(loc, expected: str) -> bool:
    """Case-insensitive label-prefix check.

    The amount/maximum labels render through CSS ``text-transform:uppercase``,
    so inner_text() returns e.g. 'AMOUNT ($)'. Compare case-insensitively.
    """
    return loc.inner_text().strip().lower().startswith(expected.lower())


def _add_use(page: Page, label: str, amount: str, phase: str = "construction") -> None:
    # openAddLine('uses') shows the overlay immediately but swaps fresh form
    # HTML into #uses-wizard-body via an async htmx GET. On repeat calls the
    # PREVIOUS form (left on step 2, so step-1 is hidden) is still in the DOM
    # until the GET completes — a plain "wait for step-1 label visible" can
    # match the stale form or time out. Stamp a sentinel before the GET, then
    # wait until it's replaced by a fresh form whose step-1 label is visible.
    page.evaluate(
        "() => { const b = document.getElementById('uses-wizard-body');"
        " if (b) b.innerHTML = '<div data-uw-loading></div>';"
        " openAddLine('uses'); }"
    )
    page.wait_for_function(
        "() => { const b = document.getElementById('uses-wizard-body');"
        " if (!b || b.querySelector('[data-uw-loading]')) return false;"
        " const i = b.querySelector('#uw-step-1 input[name=\"label\"]');"
        " return !!(i && i.offsetParent !== null); }",
        timeout=10_000,
    )
    page.fill('#uses-wizard-body #uw-step-1 input[name="label"]', label)
    page.fill('#uses-wizard-body #uw-step-1 input[name="amount"]', amount)
    page.click('#uw-next')
    page.wait_for_selector('#uses-wizard-body #uw-step-2', state="visible", timeout=8_000)
    page.click('#uw-next')
    wait_for_htmx(page)
    # The submit closes the overlay via an htmx after-request hook. That hook can
    # land *after* the next _add_use re-opens the overlay, hiding the freshly
    # loaded form (overlay→none) and stranding it (offsetParent null). Wait for
    # the close to finish here so the next open starts from a clean state.
    page.wait_for_function(
        "() => { const o = document.getElementById('uses-wizard-overlay');"
        " return !o || getComputedStyle(o).display === 'none'; }",
        timeout=8_000,
    )


def _add_grant(page: Page, label: str, amount: str) -> None:
    # The sources add-flow is the step wizard rendered into #source-wizard-body
    # (#sw-form), NOT the #line-item-drawer edit drawer. Selecting the type via
    # #sw-type reveals the amount row (grant is a fixed-amount source type).
    page.evaluate("() => openAddLine('sources')")
    page.wait_for_selector('#sw-form', timeout=5_000)
    # The wizard's inline <script> registers swTypeChanged (the #sw-type onchange
    # handler) after the partial loads — wait for it so selecting the type
    # actually reveals the amount row instead of throwing "not defined".
    page.wait_for_function(
        "() => typeof window.swTypeChanged === 'function'", timeout=5_000
    )
    page.select_option('#sw-type', "grant")
    page.fill('#sw-label', label)
    page.wait_for_selector('#sw-source-amount', state="visible", timeout=5_000)
    page.fill('#sw-source-amount', amount)
    # Grant wizard = [step 1 (Funding Details), step 5 (Draw Schedule)].
    # First Continue advances to the draw step; the last-step button is relabeled
    # "Add Source" and submits the form.
    page.click('#sw-next')
    page.wait_for_selector('#sw-step-5', state="visible", timeout=5_000)
    page.click('#sw-next')
    wait_for_htmx(page)


def _open_grant_edit(page: Page, label: str) -> None:
    # A previously opened edit form may still sit in the drawer body (closeDrawer
    # hides the overlay without clearing it). Its element IDs collide with the
    # incoming form's, so the fresh form's inline script binds its checkbox
    # listeners to the STALE nodes and the visible checkboxes end up inert
    # (uncheck flips the box but never reverts the Amount label). Clear the
    # body first so the script binds to the form we actually interact with —
    # same stale-DOM pattern as the _add_use sentinel above.
    page.evaluate(
        "() => { const b = document.getElementById('line-item-drawer-body');"
        " if (b) b.innerHTML = ''; }"
    )
    row = page.locator(f"tr:has(td:has-text('{label}'))").first
    row.click()
    page.wait_for_selector('#line-item-drawer', timeout=5_000)
    # The drawer container is always present; its form body is loaded by an
    # async htmx GET. Wait for the grant edit form to actually render before
    # callers read fields (e.g. .count() does not auto-wait like locators do).
    wait_for_htmx(page)
    page.wait_for_selector('#lf-amount-label', state="visible", timeout=5_000)


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
    assert _label_starts(label, "Amount"), (
        f"Expected 'Amount' label initially; got {label.inner_text()!r}"
    )

    box = page.locator('.lf-eligibility-checkbox').first
    box.check()
    assert _label_starts(label, "Maximum"), (
        f"Expected 'Maximum' after check; got {label.inner_text()!r}"
    )

    box.uncheck()
    assert _label_starts(label, "Amount"), (
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

    # The Max column lives in the standalone Sources module.
    _show_sources_module(page, base_url, model_id)
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

    # Under-utilization needs the grant's eligible Use total to be LESS than its
    # cap. The deal seed auto-creates a large Acquisition Use, so we must scope
    # eligibility to *only* the small Site Work Use (180k) — checking the first
    # checkbox would tick Acquisition and the grant would fund its full 250k cap.
    _add_use(page, "Site Work", "180000")
    _add_grant(page, "OR-MEP", "250000")
    _open_grant_edit(page, "OR-MEP")
    # Eligibility is permissive by default — a new grant is eligible to ALL uses,
    # so every box renders checked. Just checking Site Work leaves the large
    # Acquisition use eligible and the grant funds its full 250k cap (not
    # under-utilized). Uncheck-all first so ONLY Site Work (180k) is eligible.
    page.click("#lf-elig-uncheck-all")
    site_work_box = page.locator(
        "#lf-eligibility-list label:has-text('Site Work') input.lf-eligibility-checkbox"
    )
    site_work_box.check()
    page.fill('#lf-source-maximum-input', "250000")
    page.click('#line-item-drawer button[type="submit"]')
    wait_for_htmx(page)

    # Force a compute so source.amount gets resolved (engine runs grant_caps).
    resp = page.request.post(f"{base_url}/api/models/{model_id}/compute")
    assert resp.status == 200, f"compute failed: {resp.status} {resp.text()[:200]}"

    # The under-utilized highlight lives in the standalone Sources module.
    _show_sources_module(page, base_url, model_id)

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
    page.wait_for_function(
        "() => typeof window.swTypeChanged === 'function'", timeout=5_000
    )
    page.select_option('#sw-type', "grant")
    page.fill('#sw-label', "OR-MEP")

    # Initial state: Amount label visible
    label = page.locator('#sw-amount-label')
    assert _label_starts(label, "Amount")

    # Tick first eligibility checkbox → label flips
    page.locator('.sw-eligibility-checkbox').first.check()
    assert _label_starts(label, "Maximum")
    # Maximum input should now be visible and required
    max_in = page.locator('#sw-source-maximum')
    assert max_in.is_visible()
    page.fill('#sw-source-maximum', "250000")

    # Submit wizard — grant flow is [step 1, step 5]: Continue to the draw step,
    # then the relabeled "Add Source" button submits.
    page.click('#sw-next')
    page.wait_for_selector('#sw-step-5', state="visible", timeout=5_000)
    page.click('#sw-next')
    wait_for_htmx(page)

    # Eligibility stores a Maximum, not an Amount — only the standalone Sources
    # module surfaces it (the Max column). The sources_uses view shows the
    # (unresolved) commitment, which is blank until compute.
    _show_sources_module(page, base_url, model_id)
    row = page.locator("tr:has(td:has-text('OR-MEP'))").first
    assert "250" in row.inner_text(), (
        f"Max column should show the 250,000 cap for OR-MEP; got {row.inner_text()!r}"
    )


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
    assert _label_starts(label, "Maximum"), (
        "Label should flip to Maximum once any box is checked via Check all"
    )

    page.click('#lf-elig-uncheck-all')
    for i in range(boxes.count()):
        assert not boxes.nth(i).is_checked(), f"box {i} still checked after Uncheck all"
    assert _label_starts(label, "Amount"), (
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

    # Reopen and uncheck the eligibility, reverting to a plain fixed Amount.
    _open_grant_edit(page, "OR-MEP")
    page.locator('.lf-eligibility-checkbox').first.uncheck()
    label = page.locator('#lf-amount-label')
    assert _label_starts(label, "Amount")
    page.fill('#lf-source-amount-input', "100000")
    page.click('#line-item-drawer button[type="submit"]')
    wait_for_htmx(page)

    # The Amount column lives in the standalone Sources module — the combined
    # sources_uses sub-table renders a dash for capped/grant rows. After the
    # revert the source carries a plain amount of 100,000, shown there.
    _show_sources_module(page, base_url, model_id)
    row = page.locator("tr:has(td:has-text('OR-MEP'))").first
    row_text = row.inner_text()
    assert "100" in row_text, (
        f"Amount column should show the reverted 100,000 for OR-MEP; got {row_text!r}"
    )
