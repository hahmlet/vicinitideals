"""E2E tests for the auto Developer Fee feature.

Covers the user-visible surfaces:
- Deal create seeds a Developer Fee row in the Uses panel
- Row displays the locked-% indicator
- Drawer opens with editable %, locked $
- Saving a new % persists and re-renders the row
- Direct delete via the API endpoint is rejected (403)

The dollar-recompute math is covered by tests/engines/test_dev_fee.py — we
don't re-prove the engine math here, only that the UI write reaches the DB
and renders back into the panel.

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_dev_fee.py -m e2e -v
"""

from __future__ import annotations

import re
import uuid

import pytest
from playwright.sync_api import Page

from tests.e2e.helpers import wait_for_htmx
from tests.e2e.seed import create_e2e_scenario

pytestmark = pytest.mark.e2e


def _open_uses_panel(page: Page, base_url: str, model_id: str) -> None:
    page.goto(f"{base_url}/models/{model_id}/builder?module=sources_uses")
    wait_for_htmx(page)
    page.wait_for_selector("#module-panel-content", timeout=10_000)
    # Timeline wizard overlay auto-opens on new value_add / new_construction
    # deals (no timeline yet) and intercepts clicks. Hide it so row clicks
    # for the Dev Fee tests reach their target.
    page.evaluate(
        "() => { const w = document.getElementById('timeline-wizard');"
        " if (w) { w.style.display = 'none'; w.remove(); } }"
    )


def _dev_fee_row(page: Page):
    """Locator for the Developer Fee row in the Uses table."""
    return page.locator("tr:has(td:has-text('Developer Fee'))").first


# ---------------------------------------------------------------------------
# 1. Auto-seeded row renders with locked % indicator
# ---------------------------------------------------------------------------


def test_dev_fee_row_appears_with_pct_chip(
    logged_in_page: Page, base_url: str
) -> None:
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(
        logged_in_page, deal_name=f"E2E DevFee {suffix}", deal_type="acquisition"
    )
    page = logged_in_page
    _open_uses_panel(page, base_url, model_id)

    row = _dev_fee_row(page)
    assert row.count() >= 1, "Developer Fee row not rendered in Uses table"
    # Locked % indicator — the panel template renders "🔒 5.0%" next to the label
    label_cell = row.locator("td").first
    text = label_cell.inner_text()
    assert "Developer Fee" in text
    assert re.search(r"\b\d+(\.\d+)?%", text), (
        f"Expected % indicator next to Developer Fee label; got: {text!r}"
    )


# ---------------------------------------------------------------------------
# 2. Auto row has no delete button in the Uses table
# ---------------------------------------------------------------------------


def test_dev_fee_row_has_no_delete_button(
    logged_in_page: Page, base_url: str
) -> None:
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(
        logged_in_page, deal_name=f"E2E DevFee NoDel {suffix}", deal_type="value_add"
    )
    page = logged_in_page
    _open_uses_panel(page, base_url, model_id)

    row = _dev_fee_row(page)
    assert row.count() >= 1, "Developer Fee row not rendered"
    delete_btn = row.locator("button:has-text('✕')")
    assert delete_btn.count() == 0, (
        "Developer Fee row should not expose a delete button — "
        "the auto row is policy-locked; user disables via 0%."
    )


# ---------------------------------------------------------------------------
# 3. Drawer shows locked $ and editable %; saving a new % persists
# ---------------------------------------------------------------------------


def test_dev_fee_drawer_locks_dollar_and_persists_pct(
    logged_in_page: Page, base_url: str
) -> None:
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(
        logged_in_page,
        deal_name=f"E2E DevFee Drawer {suffix}",
        deal_type="new_construction",
    )
    page = logged_in_page
    _open_uses_panel(page, base_url, model_id)

    row = _dev_fee_row(page)
    assert row.count() >= 1
    row.click()
    page.wait_for_selector("#line-item-drawer input[name='dev_fee_pct']", timeout=5000)

    # The $ field is disabled / readonly — verify both the explicit dev_fee_pct
    # input exists and that there is no editable `name=amount` for this row.
    pct_input = page.locator("#line-item-drawer input[name='dev_fee_pct']")
    assert pct_input.count() == 1
    amount_input = page.locator("#line-item-drawer input[name='amount']:not([type=hidden])")
    # The auto-row branch of the drawer doesn't emit a writable amount input.
    assert amount_input.count() == 0, (
        "Auto Developer Fee drawer must not expose a writable $ amount field."
    )

    # Change the %
    pct_input.fill("7.5")
    page.click("#line-item-drawer button[type=submit]")
    wait_for_htmx(page)
    # Drawer should close after a successful PUT (hx-on::after-request).
    page.wait_for_selector("#line-item-drawer", state="hidden", timeout=5000)

    # Panel re-renders — Developer Fee row must now show 7.5%
    row2 = _dev_fee_row(page)
    text = row2.locator("td").first.inner_text()
    assert "7.5" in text, (
        f"Expected updated % (7.5%) in the Developer Fee row; got: {text!r}"
    )


# ---------------------------------------------------------------------------
# 4. Direct API delete is rejected with 403
# ---------------------------------------------------------------------------


def test_api_delete_of_auto_dev_fee_returns_403(
    logged_in_page: Page, base_url: str
) -> None:
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(
        logged_in_page, deal_name=f"E2E DevFee NoDel API {suffix}", deal_type="acquisition"
    )
    page = logged_in_page
    _open_uses_panel(page, base_url, model_id)

    # Find the row's ID by scanning the row's onclick handler — it embeds the
    # use_line UUID inside openEditLine('use_lines', '<UUID>', ...).
    row = _dev_fee_row(page)
    onclick = row.get_attribute("onclick") or ""
    match = re.search(r"openEditLine\('use_lines',\s*'([0-9a-f-]{36})'", onclick)
    assert match, f"Could not extract Dev Fee use_line id from row onclick={onclick!r}"
    ul_id = match.group(1)

    resp = page.request.delete(f"{base_url}/api/models/{model_id}/use-lines/{ul_id}")
    assert resp.status == 403, (
        f"API delete on auto Dev Fee row must return 403; got {resp.status}: {resp.text()}"
    )


# ---------------------------------------------------------------------------
# 5. Setting % to 0 is the documented "disable" path; should persist as 0
# ---------------------------------------------------------------------------


def test_zero_pct_persists_as_disable(
    logged_in_page: Page, base_url: str
) -> None:
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(
        logged_in_page, deal_name=f"E2E DevFee Zero {suffix}", deal_type="value_add"
    )
    page = logged_in_page
    _open_uses_panel(page, base_url, model_id)

    _dev_fee_row(page).click()
    page.wait_for_selector("#line-item-drawer input[name='dev_fee_pct']", timeout=5000)
    page.locator("#line-item-drawer input[name='dev_fee_pct']").fill("0")
    page.click("#line-item-drawer button[type=submit]")
    wait_for_htmx(page)
    page.wait_for_selector("#line-item-drawer", state="hidden", timeout=5000)

    text = _dev_fee_row(page).locator("td").first.inner_text()
    assert "0%" in text or "0.0%" in text, (
        f"After setting % to 0 the row should show 0% (disabled state); got: {text!r}"
    )
