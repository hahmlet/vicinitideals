"""E2E seed helpers — create test fixtures via Playwright browser interactions.

All deal creation and wizard flows use actual browser clicks and form fills,
matching real user behavior. This catches UI regressions that raw API calls miss.

Usage:
    from tests.e2e.seed import create_e2e_scenario, create_seeded_deal

    model_id = create_e2e_scenario(page)
    model_id, project_id = create_seeded_deal(page)
"""

from __future__ import annotations

import re

from playwright.sync_api import Page

from tests.e2e.helpers import wait_for_htmx


# ---------------------------------------------------------------------------
# Deal creation
# ---------------------------------------------------------------------------

def create_e2e_scenario(
    page: Page,
    *,
    deal_name: str = "E2E Test Deal",
    deal_type: str = "acquisition_minor_reno",
) -> str:
    """Create a new deal via the UI and return the model_id UUID string."""
    page.goto("/deals")
    page.wait_for_load_state("domcontentloaded")

    # Click the "New Deal" button (opens form/modal)
    page.click("text=New Deal")
    page.wait_for_selector('[name=name]', timeout=5000)

    page.fill('[name=name]', deal_name)
    page.select_option('[name=deal_type]', deal_type)
    page.click('[type=submit]')

    # Redirects to /models/{model_id}/builder
    page.wait_for_url("**/models/*/builder**", timeout=10_000)
    url = page.url
    match = re.search(r"/models/([0-9a-f-]{36})/builder", url)
    assert match, f"Could not extract model_id from URL: {url}"
    return match.group(1)


def _extract_project_id(page: Page) -> str:
    """Extract project_id from the builder page's timeline wizard form action."""
    html = page.content()
    match = re.search(r"/ui/projects/([0-9a-f-]{36})/timeline-wizard", html)
    assert match, "Could not find project_id in builder page HTML"
    return match.group(1)


# ---------------------------------------------------------------------------
# Timeline wizard
# ---------------------------------------------------------------------------

def submit_timeline_wizard(
    page: Page,
    model_id: str,
    project_id: str,
    *,
    anchor_type: str = "close",
    anchor_date: str = "2026-09-01",
    anchor_duration_days: str = "45",
    milestone_types: list[str] | None = None,
    phase_durations: dict[str, int] | None = None,
) -> None:
    """Navigate through the timeline wizard and approve the timeline."""
    if milestone_types is None:
        milestone_types = ["close", "construction", "operation_stabilized", "divestment"]

    # Navigate to timeline module
    page.goto(f"/models/{model_id}/builder?module=timeline")
    page.wait_for_selector("#module-panel-content", timeout=10_000)
    wait_for_htmx(page)

    # Open the timeline wizard
    page.click("text=Create Timeline")
    page.wait_for_selector("#timeline-wizard", timeout=5000)

    # Step 1 — select milestones
    for mt in milestone_types:
        cb = page.locator(f'#timeline-wizard input[value="{mt}"]')
        if cb.count() > 0 and not cb.is_checked():
            cb.check()

    # Click Next to go to step 2
    page.click('#timeline-wizard button:has-text("Next")')
    page.wait_for_timeout(500)

    # Step 2 — set anchor date and duration
    anchor_date_input = page.locator('#timeline-wizard [name=anchor_date]')
    if anchor_date_input.count() > 0:
        anchor_date_input.fill(anchor_date)

    anchor_dur_input = page.locator('#timeline-wizard [name=anchor_duration_days]')
    if anchor_dur_input.count() > 0:
        anchor_dur_input.fill(anchor_duration_days)

    # Set per-milestone durations if provided
    if phase_durations:
        for mt_str, days in phase_durations.items():
            dur_input = page.locator(f'#timeline-wizard [name="duration_{mt_str}"]')
            if dur_input.count() > 0:
                dur_input.fill(str(days))

    # Submit the wizard
    page.click('#timeline-wizard button:has-text("Save")')
    page.wait_for_url(f"**/models/{model_id}/builder**", timeout=10_000)
    wait_for_htmx(page)

    # Approve the timeline
    page.goto(f"/models/{model_id}/builder?module=timeline")
    page.wait_for_selector("#module-panel-content", timeout=10_000)
    wait_for_htmx(page)

    approve_btn = page.locator('button:has-text("Approve Timeline")')
    if approve_btn.count() > 0 and approve_btn.is_enabled():
        approve_btn.click()
        page.wait_for_url(f"**/models/{model_id}/builder**", timeout=10_000)
        wait_for_htmx(page)


# ---------------------------------------------------------------------------
# Deal setup wizard (steps 1–7)
# ---------------------------------------------------------------------------

def run_deal_setup_wizard(
    page: Page,
    model_id: str,
    *,
    income_mode: str = "revenue_opex",
    debt_types: list[str] | None = None,
    milestone_config: dict[str, dict[str, str]] | None = None,
    debt_terms: dict[str, dict] | None = None,
    debt_sizing_mode: str = "gap_fill",
    dscr_minimum: str = "1.25",
    construction_floor_pct: str = "5.0",
    operation_reserve_months: str = "6",
) -> None:
    """Click through all 7 steps of the deal setup wizard."""
    if debt_types is None:
        debt_types = ["permanent_debt"]

    # Navigate to Deal Setup
    page.goto(f"/models/{model_id}/builder?module=deal_setup")
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)
    wait_for_htmx(page)

    # Step 1 — Income mode
    # Click the radio card for the desired income mode
    page.click(f'#deal-setup-wizard input[value="{income_mode}"]')
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)

    # Step 2 — Debt types
    page.wait_for_selector('#debt-type-grid', timeout=5000)
    for dt in debt_types:
        cb = page.locator(f'#debt-type-grid input[value="{dt}"]')
        if cb.count() > 0 and not cb.is_checked():
            cb.check()
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)

    # Step 3 — Milestone config (Active From / Active To / Retired By)
    if milestone_config:
        for dt, cfg in milestone_config.items():
            if "active_from" in cfg:
                page.select_option(f'[name="{dt}_active_from"]', cfg["active_from"])
            if "active_to" in cfg:
                page.select_option(f'[name="{dt}_active_to"]', cfg["active_to"])
            if "retired_by" in cfg:
                page.select_option(f'[name="{dt}_retired_by"]', cfg["retired_by"])
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)

    # Step 4 — Debt terms (rate, carry type, amort)
    if debt_terms:
        for dt, terms in debt_terms.items():
            if "rate_pct" in terms:
                rate_input = page.locator(f'[name="{dt}_rate_pct"]')
                if rate_input.count() > 0:
                    rate_input.fill(str(terms["rate_pct"]))
            if "loan_type" in terms:
                lt_select = page.locator(f'[name="{dt}_loan_type"]')
                if lt_select.count() > 0:
                    lt_select.select_option(terms["loan_type"])
            if "amort_years" in terms:
                amort_input = page.locator(f'[name="{dt}_amort_years"]')
                if amort_input.count() > 0:
                    amort_input.fill(str(terms["amort_years"]))
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)

    # Step 5 — Debt sizing mode
    if debt_sizing_mode == "dscr_capped":
        page.click('text=DSCR-Capped')
        dscr_input = page.locator('[name="dscr_minimum"]')
        if dscr_input.count() > 0:
            dscr_input.fill(dscr_minimum)
    # else gap_fill is the default selection
    page.click('#deal-setup-wizard button:has-text("Next")')
    wait_for_htmx(page)

    # Step 6 — Reserves & Floors
    floor_input = page.locator('[name="construction_floor_pct"]')
    if floor_input.count() > 0:
        floor_input.fill(construction_floor_pct)
    reserve_input = page.locator('[name="operation_reserve_months"]')
    if reserve_input.count() > 0:
        reserve_input.fill(operation_reserve_months)
    page.click('#deal-setup-wizard button:has-text("Review")')
    wait_for_htmx(page)

    # Step 7 — Review → Finish Setup
    page.wait_for_selector('button:has-text("Finish Setup")', timeout=5000)
    page.click('button:has-text("Finish Setup")')
    # Wizard completes with HX-Redirect to the builder
    page.wait_for_url(f"**/models/{model_id}/builder**", timeout=10_000)
    wait_for_htmx(page)


# ---------------------------------------------------------------------------
# Line item creation via drawer forms
# ---------------------------------------------------------------------------

def _open_add_drawer_and_fill(
    page: Page,
    button_text: str,
    fields: dict[str, str],
    select_fields: dict[str, str] | None = None,
) -> None:
    """Click an add button, fill the drawer form, and submit."""
    page.click(f'button:has-text("{button_text}")')
    page.wait_for_selector('.drawer', timeout=5000)
    page.wait_for_timeout(300)  # animation

    for name, value in fields.items():
        inp = page.locator(f'.drawer [name="{name}"]')
        if inp.count() > 0:
            inp.fill(value)

    if select_fields:
        for name, value in select_fields.items():
            sel = page.locator(f'.drawer [name="{name}"]')
            if sel.count() > 0:
                sel.select_option(value)

    page.click('.drawer button[type="submit"]')
    wait_for_htmx(page)
    page.wait_for_timeout(500)


def add_use_line(
    page: Page,
    model_id: str,
    label: str,
    amount: str,
    milestone_key: str = "close",
    timing_type: str = "first_day",
) -> None:
    """Add a use line via the S&U module drawer."""
    page.goto(f"/models/{model_id}/builder?module=sources_uses")
    page.wait_for_selector("#module-panel-content", timeout=10_000)
    wait_for_htmx(page)

    _open_add_drawer_and_fill(
        page,
        button_text="+ Use",
        fields={"label": label, "amount": amount},
        select_fields={"milestone_key": milestone_key, "timing_type": timing_type},
    )


def add_income_stream(
    page: Page,
    model_id: str,
    label: str = "Residential Rent",
    stream_type: str = "residential_rent",
    unit_count: str = "10",
    amount_per_unit_monthly: str = "1200",
    occupancy_pct: str = "95",
    escalation_pct: str = "3",
) -> None:
    """Add an income stream via the Revenue module drawer."""
    page.goto(f"/models/{model_id}/builder?module=revenue")
    page.wait_for_selector("#module-panel-content", timeout=10_000)
    wait_for_htmx(page)

    _open_add_drawer_and_fill(
        page,
        button_text="+ Income",
        fields={
            "label": label,
            "unit_count": unit_count,
            "amount_per_unit_monthly": amount_per_unit_monthly,
            "stabilized_occupancy_pct": occupancy_pct,
            "escalation_rate_pct_annual": escalation_pct,
        },
        select_fields={
            "stream_type": stream_type,
            "active_in_phases": "stabilized",
        },
    )


def add_expense_line(
    page: Page,
    model_id: str,
    label: str,
    annual_amount: str,
    escalation_pct: str = "3",
) -> None:
    """Add an expense line via the OpEx module drawer."""
    page.goto(f"/models/{model_id}/builder?module=opex")
    page.wait_for_selector("#module-panel-content", timeout=10_000)
    wait_for_htmx(page)

    _open_add_drawer_and_fill(
        page,
        button_text="+ Expense",
        fields={
            "label": label,
            "per_value": annual_amount,
            "escalation_rate_pct_annual": escalation_pct,
        },
        select_fields={
            "per_type": "flat",
            "active_in_phases": "stabilized",
        },
    )


def click_compute(page: Page, model_id: str) -> None:
    """Click the Compute button and wait for the result badge."""
    # Ensure we're on the builder page
    if f"/models/{model_id}/builder" not in page.url:
        page.goto(f"/models/{model_id}/builder?module=sources_uses")
        page.wait_for_selector("#module-panel-content", timeout=10_000)
        wait_for_htmx(page)

    page.click('button:has-text("Compute")')
    # Wait for either success or failure badge
    page.wait_for_selector('#compute-result .badge', timeout=30_000)
    wait_for_htmx(page)


# ---------------------------------------------------------------------------
# Full deal seeder (combines all the above)
# ---------------------------------------------------------------------------

def create_seeded_deal(
    page: Page,
    *,
    deal_name: str = "E2E Lifecycle Test Deal",
    deal_type: str = "acquisition_minor_reno",
) -> tuple[str, str]:
    """Create a fully seeded deal via browser interactions.

    Steps: create deal → timeline wizard → approve → setup wizard →
           add use lines → add income → add expenses → compute

    Returns (model_id, project_id).
    """
    model_id = create_e2e_scenario(page, deal_name=deal_name, deal_type=deal_type)
    project_id = _extract_project_id(page)

    # Timeline
    submit_timeline_wizard(page, model_id, project_id)

    # Deal setup wizard (perm-only, gap-fill)
    run_deal_setup_wizard(
        page,
        model_id,
        debt_types=["permanent_debt"],
        debt_terms={"permanent_debt": {"rate_pct": "6.5", "amort_years": "30"}},
        construction_floor_pct="0",
        operation_reserve_months="3",
    )

    # Use lines
    add_use_line(page, model_id, "Purchase Price", "800000", milestone_key="close")
    add_use_line(page, model_id, "Renovation", "50000", milestone_key="construction")
    add_use_line(page, model_id, "Closing Costs", "15000", milestone_key="close")

    # Income
    add_income_stream(page, model_id)

    # Expenses
    add_expense_line(page, model_id, "Property Management", "14400")
    add_expense_line(page, model_id, "Insurance", "6000")
    add_expense_line(page, model_id, "Property Tax", "9600", escalation_pct="2")

    # Compute
    click_compute(page, model_id)

    return model_id, project_id
