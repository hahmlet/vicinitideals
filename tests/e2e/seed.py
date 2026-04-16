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

COOKIE_NAME = "vd_session"


def _get_session_cookie(page: Page) -> str:
    """Extract session cookie from the Playwright page context."""
    for c in page.context.cookies():
        if c["name"] == COOKIE_NAME:
            return c["value"]
    raise ValueError("No session cookie in page context")


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
    page.goto("/deals/new")
    page.wait_for_selector('[name=name]', timeout=10_000)

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
    """Navigate through the timeline wizard and approve the timeline.

    The timeline wizard is a client-side JS stepper (not HTMX):
      Step 1: Select anchor milestone (radio)
      Step 2: Set anchor date + duration
      Step 3: Select all phases (checkboxes)
      → Submit hidden form → redirect → approve
    """
    if milestone_types is None:
        milestone_types = ["close", "construction", "operation_stabilized", "divestment"]

    # Navigate to timeline module — wizard overlay auto-shows for new deals
    page.goto(f"/models/{model_id}/builder?module=timeline")
    page.wait_for_selector("#timeline-wizard", timeout=10_000)

    # Step 1 — select anchor milestone (radio card)
    anchor_radio = page.locator(f'#timeline-wizard input[name="_anchor_ui"][value="{anchor_type}"]')
    if anchor_radio.count() > 0:
        # Click the parent label to trigger the JS selectAnchor()
        anchor_radio.locator("..").click()
    page.wait_for_timeout(300)

    # Click "Continue →" to advance to step 2
    page.click("#wizard-next")
    page.wait_for_timeout(500)

    # Step 2 — set anchor date and duration
    page.fill("#wizard-anchor-date", anchor_date)
    page.fill("#wizard-anchor-duration", anchor_duration_days)

    # Click "Continue →" to advance to step 3
    page.click("#wizard-next")
    page.wait_for_timeout(500)

    # Step 3 — select milestone checkboxes (some are pre-checked as defaults)
    for mt in milestone_types:
        cb = page.locator(f'#timeline-wizard input[name="milestone_types"][value="{mt}"]')
        if cb.count() > 0 and not cb.is_checked():
            cb.check()

    # Click "Set Up Timeline →" to submit
    page.click("#wizard-next")
    page.wait_for_url(f"**/models/{model_id}/builder**", timeout=15_000)
    wait_for_htmx(page)

    # Set per-milestone durations by clicking each milestone row and editing
    if phase_durations:
        # Phase type labels shown in the milestone table
        _PHASE_TYPE_LABELS = {
            "close": "Close",
            "pre_development": "Pre Development",
            "construction": "Construction",
            "operation_lease_up": "Operation Lease Up",
            "operation_stabilized": "Operation Stabilized",
            "divestment": "Divestment",
            "offer_made": "Offer Made",
            "under_contract": "Under Contract",
        }
        page.goto(f"/models/{model_id}/builder?module=timeline")
        page.wait_for_selector("#module-panel-content", timeout=15_000)
        wait_for_htmx(page)

        for mt_str, days in phase_durations.items():
            label = _PHASE_TYPE_LABELS.get(mt_str, mt_str.replace("_", " ").title())
            # Click the milestone row to open edit drawer
            row = page.locator(f'#module-panel-content tr:has(td:has-text("{label}"))')
            if row.count() > 0:
                row.first.click()
                page.wait_for_selector('#line-item-drawer [name="duration_days"]', timeout=8000)
                page.wait_for_timeout(300)
                page.fill('#line-item-drawer [name="duration_days"]', str(days))
                page.click('#line-item-drawer button[type="submit"]')
                wait_for_htmx(page)
                page.wait_for_timeout(500)

    # Approve the timeline
    page.goto(f"/models/{model_id}/builder?module=timeline")
    page.wait_for_selector("#module-panel-content", timeout=10_000)
    wait_for_htmx(page)

    approve_btn = page.locator('button:has-text("Approve Timeline")')
    if approve_btn.count() > 0:
        # Wait until enabled (milestones need valid positions + durations)
        page.wait_for_timeout(500)
        if approve_btn.is_enabled():
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
    # Map engine-style phase names to the wizard's select option values
    _PHASE_VALUE_MAP = {
        "operation_lease_up": "lease_up",
        "operation_stabilized": "stabilized",
        "divestment": "exit",
    }
    if milestone_config:
        for dt, cfg in milestone_config.items():
            if "active_from" in cfg:
                val = _PHASE_VALUE_MAP.get(cfg["active_from"], cfg["active_from"])
                page.select_option(f'[name="{dt}_active_from"]', val)
            if "active_to" in cfg:
                val = _PHASE_VALUE_MAP.get(cfg["active_to"], cfg["active_to"])
                page.select_option(f'[name="{dt}_active_to"]', val)
            if "retired_by" in cfg:
                val = cfg["retired_by"]
                if val:
                    page.select_option(f'[name="{dt}_retired_by"]', val)
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

def _open_overlay_and_fill(
    page: Page,
    button_text: str,
    overlay_selector: str,
    fields: dict[str, str],
    select_fields: dict[str, str] | None = None,
) -> None:
    """Click an add button, fill the overlay/drawer form, and submit."""
    page.click(f'button:has-text("{button_text}")')
    page.wait_for_selector(f'{overlay_selector} [type="submit"]', timeout=8000)
    page.wait_for_timeout(500)  # HTMX form load + animation

    for name, value in fields.items():
        inp = page.locator(f'{overlay_selector} [name="{name}"]')
        if inp.count() > 0:
            # Use force for fields that may be in a scrollable area
            inp.fill(value, force=True)

    if select_fields:
        for name, value in select_fields.items():
            sel = page.locator(f'{overlay_selector} [name="{name}"]')
            if sel.count() == 0:
                continue
            tag = sel.first.evaluate("el => el.tagName.toLowerCase()")
            if tag == "select":
                sel.first.select_option(value, force=True)
            elif tag == "input":
                input_type = sel.first.get_attribute("type") or ""
                if input_type == "checkbox":
                    # Check the specific value checkbox
                    cb = page.locator(f'{overlay_selector} input[name="{name}"][value="{value}"]')
                    if cb.count() > 0 and not cb.is_checked():
                        cb.check(force=True)
                elif input_type == "radio":
                    rb = page.locator(f'{overlay_selector} input[name="{name}"][value="{value}"]')
                    if rb.count() > 0:
                        rb.check(force=True)
                else:
                    sel.first.fill(value, force=True)

    page.click(f'{overlay_selector} button[type="submit"]')
    wait_for_htmx(page)
    page.wait_for_timeout(500)


def _safe_goto(page: Page, url: str, timeout: int = 30_000) -> None:
    """Navigate with retry on ERR_ABORTED (common after HTMX redirects)."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    except Exception:
        page.wait_for_timeout(2000)
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    page.wait_for_selector("#module-panel-content", timeout=timeout)
    wait_for_htmx(page)


def add_use_line(
    page: Page,
    model_id: str,
    label: str,
    amount: str,
    milestone_key: str = "close",
    timing_type: str = "first_day",
) -> None:
    """Add a use line via the uses wizard overlay (2-step JS wizard)."""
    _safe_goto(page, f"/models/{model_id}/builder?module=sources_uses")

    # Click "+ Use" button to open the uses wizard overlay
    page.click('button:has-text("+ Use")')
    page.wait_for_selector('#uses-wizard-overlay #uw-next', timeout=8000)
    page.wait_for_timeout(500)

    # Step 1: Name & Amount
    page.fill('#uses-wizard-overlay [name="label"]', label)
    page.fill('#uses-wizard-overlay [name="amount"]', amount)
    page.click('#uw-next')  # Continue →
    page.wait_for_timeout(300)

    # Step 2: Timing & Milestones
    ms_sel = page.locator('#uses-wizard-overlay [name="milestone_key"]')
    if ms_sel.count() > 0:
        ms_sel.select_option(milestone_key)
    # timing_type is radio buttons, not a select
    timing_radio = page.locator(f'#uses-wizard-overlay input[name="timing_type"][value="{timing_type}"]')
    if timing_radio.count() > 0:
        timing_radio.check()
    page.click('#uw-next')  # Add Use (submits form)
    wait_for_htmx(page)
    page.wait_for_timeout(500)


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
    _safe_goto(page, f"/models/{model_id}/builder?module=revenue")

    _open_overlay_and_fill(
        page,
        button_text="+ Add Stream",
        overlay_selector="#line-item-drawer",
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
    _safe_goto(page, f"/models/{model_id}/builder?module=opex")

    _open_overlay_and_fill(
        page,
        button_text="+ Add Line",
        overlay_selector="#line-item-drawer",
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
        _safe_goto(page, f"/models/{model_id}/builder?module=sources_uses")

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
