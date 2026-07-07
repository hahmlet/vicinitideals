"""E2E: eligibility editors + per-module DSCR Min (Slice 7 UI gaps).

User flows:
- Debt Source edit drawer: set DSCR Min + Use Category Eligibility tags →
  save → reopen → both values persisted and re-rendered.
- Use-line edit drawer: tick a Funding Source in the whitelist picker →
  save → reopen → checkbox still ticked (use_lines.eligible_module_ids).

The parser/DB writeback is covered by tests/api/test_ui_eligibility_editors.py;
here we verify the real drawer forms post the fields and round-trip them.

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_eligibility_editors_flow.py -m e2e -v
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
    page.wait_for_function(
        "() => { const o = document.getElementById('uses-wizard-overlay');"
        " return !o || getComputedStyle(o).display === 'none'; }",
        timeout=8_000,
    )


def _add_debt(page: Page, label: str, rate: str = "6.50") -> None:
    """Walk the add-source wizard for generic 'debt' (steps 1 → 3 → 4 → 5)."""
    page.evaluate("() => openAddLine('sources')")
    page.wait_for_selector("#sw-form", timeout=5_000)
    page.wait_for_function(
        "() => typeof window.swTypeChanged === 'function'", timeout=5_000
    )
    page.select_option("#sw-type", "debt")
    page.fill("#sw-label", label)
    page.click("#sw-next")  # step 1 → step 3 (loan terms)
    page.wait_for_selector("#sw-step-3", state="visible", timeout=5_000)
    page.fill('#sw-form input[name="source_interest_rate"]', rate)
    page.click("#sw-next")  # step 3 → step 4 (carry)
    page.click("#sw-next")  # step 4 → step 5 (draw)
    page.wait_for_selector("#sw-step-5", state="visible", timeout=5_000)
    page.click("#sw-next")
    wait_for_htmx(page)
    row = page.locator(f"tr:has(td:has-text('{label}'))").first
    row.wait_for(state="attached", timeout=10_000)


def _open_edit_drawer(page: Page, label: str, ready_selector: str) -> None:
    """Click the row for `label` and wait for its drawer form to render."""
    row = page.locator(f"tr:has(td:has-text('{label}'))").first
    row.click()
    page.wait_for_selector("#line-item-drawer", timeout=5_000)
    wait_for_htmx(page)
    page.wait_for_selector(ready_selector, state="visible", timeout=8_000)


# ---------------------------------------------------------------------------
# 1. Debt drawer: DSCR Min + Use Category tags round-trip
# ---------------------------------------------------------------------------


def test_debt_drawer_dscr_min_and_tags_roundtrip(
    logged_in_page: Page, base_url: str
) -> None:
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(
        logged_in_page, deal_name=f"E2E DscrTags {suffix}", deal_type="acquisition"
    )
    page = logged_in_page
    _open_sources_panel(page, base_url, model_id)

    _add_use(page, "Hard Shell Costs", "300000")
    _add_debt(page, "Senior Loan DT")

    # Open the debt edit drawer — DSCR Min lives in the Loan Terms section.
    _open_edit_drawer(page, "Senior Loan DT", '#line-item-drawer input[name="dscr_min"]')

    dscr_in = page.locator('#line-item-drawer input[name="dscr_min"]')
    assert dscr_in.input_value() == "", (
        f"New debt source should have a blank DSCR Min; got {dscr_in.input_value()!r}"
    )
    dscr_in.fill("1.35")

    # Tag editor: all unchecked by default (permissive). Restrict to hard costs.
    tag_boxes = page.locator('#line-item-drawer input[name="eligible_use_tags"]')
    assert tag_boxes.count() >= 3, (
        f"Expected >=3 cost-category tag checkboxes; got {tag_boxes.count()}"
    )
    for i in range(tag_boxes.count()):
        assert not tag_boxes.nth(i).is_checked(), (
            "New source should start permissive (no tags checked)"
        )
    hard_box = page.locator(
        '#line-item-drawer input[name="eligible_use_tags"][value="hard"]'
    )
    hard_box.check()

    page.click('#line-item-drawer button[type="submit"]')
    wait_for_htmx(page)

    # Reopen — both values must round-trip.
    _open_edit_drawer(page, "Senior Loan DT", '#line-item-drawer input[name="dscr_min"]')
    dscr_in = page.locator('#line-item-drawer input[name="dscr_min"]')
    assert dscr_in.input_value() == "1.35", (
        f"DSCR Min did not persist; got {dscr_in.input_value()!r}"
    )
    hard_box = page.locator(
        '#line-item-drawer input[name="eligible_use_tags"][value="hard"]'
    )
    assert hard_box.is_checked(), "Checked 'hard' tag did not persist on reopen"
    soft_box = page.locator(
        '#line-item-drawer input[name="eligible_use_tags"][value="soft"]'
    )
    assert not soft_box.is_checked(), "'soft' tag should remain unchecked"


# ---------------------------------------------------------------------------
# 2. Debt drawer: unchecking all tags clears back to permissive
# ---------------------------------------------------------------------------


def test_debt_drawer_unchecking_tags_reverts_to_permissive(
    logged_in_page: Page, base_url: str
) -> None:
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(
        logged_in_page, deal_name=f"E2E TagClear {suffix}", deal_type="acquisition"
    )
    page = logged_in_page
    _open_sources_panel(page, base_url, model_id)

    _add_debt(page, "Senior Loan TC")
    _open_edit_drawer(page, "Senior Loan TC", '#line-item-drawer input[name="dscr_min"]')
    page.locator(
        '#line-item-drawer input[name="eligible_use_tags"][value="soft"]'
    ).check()
    page.click('#line-item-drawer button[type="submit"]')
    wait_for_htmx(page)

    # Reopen and clear the tag.
    _open_edit_drawer(page, "Senior Loan TC", '#line-item-drawer input[name="dscr_min"]')
    soft_box = page.locator(
        '#line-item-drawer input[name="eligible_use_tags"][value="soft"]'
    )
    assert soft_box.is_checked(), "Saved tag should render checked on reopen"
    soft_box.uncheck()
    page.click('#line-item-drawer button[type="submit"]')
    wait_for_htmx(page)

    _open_edit_drawer(page, "Senior Loan TC", '#line-item-drawer input[name="dscr_min"]')
    tag_boxes = page.locator('#line-item-drawer input[name="eligible_use_tags"]')
    for i in range(tag_boxes.count()):
        assert not tag_boxes.nth(i).is_checked(), (
            "All tags should be unchecked (permissive) after clearing"
        )


# ---------------------------------------------------------------------------
# 3. Use-line drawer: Funding Source whitelist round-trip
# ---------------------------------------------------------------------------


def test_use_line_source_whitelist_roundtrip(
    logged_in_page: Page, base_url: str
) -> None:
    suffix = uuid.uuid4().hex[:6]
    model_id = create_e2e_scenario(
        logged_in_page, deal_name=f"E2E UseWL {suffix}", deal_type="acquisition"
    )
    page = logged_in_page
    _open_sources_panel(page, base_url, model_id)

    _add_use(page, "Whitelisted Work", "120000")
    _add_debt(page, "Senior Loan WL")

    # Open the Use-line edit drawer — the Funding Sources picker renders when
    # the scenario has capital modules.
    _open_edit_drawer(
        page, "Whitelisted Work",
        '#line-item-drawer input[name="eligible_module_ids"]',
    )
    wl_boxes = page.locator('#line-item-drawer input[name="eligible_module_ids"]')
    assert wl_boxes.count() >= 1, "Expected at least one Funding Source checkbox"

    target = page.locator(
        "#ul-source-whitelist label:has-text('Senior Loan WL') "
        'input[name="eligible_module_ids"]'
    )
    assert not target.is_checked(), "New Use should start permissive (unchecked)"
    target.check()
    page.click('#line-item-drawer button[type="submit"]')
    wait_for_htmx(page)

    # Reopen — the whitelist tick must round-trip.
    _open_edit_drawer(
        page, "Whitelisted Work",
        '#line-item-drawer input[name="eligible_module_ids"]',
    )
    target = page.locator(
        "#ul-source-whitelist label:has-text('Senior Loan WL') "
        'input[name="eligible_module_ids"]'
    )
    assert target.is_checked(), (
        "Funding Source whitelist tick did not persist on the Use line"
    )
