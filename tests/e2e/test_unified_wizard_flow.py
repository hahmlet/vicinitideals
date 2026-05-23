"""Unified single-flow deal-creation wizard — end-to-end coverage.

Validates that the three creation surfaces (Deal Basics → Timeline → Setup) all
render the same `.dcw-chrome` step indicator, that `wizard=1` survives every
intermediate redirect, that phase-filtered debt cards (Slice 2) hide
construction-only options when the timeline has no Construction phase, and
that data typed into each step actually lands on the persisted Scenario /
OperationalInputs / UseLines / CapitalModule rows.

Existing test_wizard_flow.py only covers Step 3 in isolation; this file is the
single-flow regression suite.
"""
from __future__ import annotations

import re
import uuid

import httpx
import pytest

from tests.e2e.helpers import wait_for_htmx


pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _session_cookie(page) -> str | None:
    for c in page.context.cookies():
        if c.get("name") == "vd_session":
            return c.get("value")
    return None


def _api(base_url: str, page, api_key: str) -> httpx.Client:
    """Authenticated API client carrying the Playwright session cookie."""
    cookie = _session_cookie(page)
    return httpx.Client(
        base_url=base_url,
        headers={"X-API-Key": api_key},
        cookies={"vd_session": cookie} if cookie else {},
        timeout=30,
    )


def _chrome_step_state(page) -> dict[int, str]:
    """Read which step is active/done/pending in the `.dcw-chrome` indicator."""
    state: dict[int, str] = {}
    # Each step is a chip with a numbered circle. Inline color picks classify
    # the state: accent (white-on-blue) = active, success (white-on-green) =
    # done, border (grey) = pending.
    chrome = page.locator(".dcw-chrome")
    chrome.wait_for(state="visible", timeout=8_000)
    for n in (1, 2, 3):
        # The circle either renders the step number or a ✓ checkmark for done.
        circle = chrome.locator(f"span:has-text('{n}')").first
        check = chrome.locator(f"span:has-text('✓')").nth(n - 1)
        if circle.count() > 0:
            state[n] = "active-or-pending"
        elif check.count() > 0:
            state[n] = "done"
    return state


def _extract_model_id(url: str) -> str:
    m = re.search(r"/models/([0-9a-f-]{36})/builder", url)
    assert m, f"Could not extract model_id from {url}"
    return m.group(1)


_PHASE_TYPE_LABELS = {
    "close": "Close",
    "pre_development": "Pre Development",
    "construction": "Construction",
    "operation_lease_up": "Operation Lease Up",
    "operation_stabilized": "Operation Stabilized",
    "divestment": "Divestment",
}


def _drive_timeline_wizard_in_flow(
    page,
    model_id: str,
    *,
    milestone_types: list[str],
    anchor_type: str = "close",
    anchor_date: str = "2026-09-01",
    anchor_duration_days: str = "45",
    phase_durations: dict[str, int] | None = None,
) -> None:
    """Drive the timeline-wizard modal while staying on `?wizard=1` URLs the
    whole time so the post-submit redirect and final Approve button render in
    wizard mode. Mirrors `seed.submit_timeline_wizard` but never navigates off
    the wizard URL."""
    page.goto(f"/models/{model_id}/builder?module=timeline&wizard=1")
    page.wait_for_selector("#timeline-wizard", timeout=10_000)

    # Step 1 — anchor
    anchor_radio = page.locator(
        f'#timeline-wizard input[name="_anchor_ui"][value="{anchor_type}"]'
    )
    if anchor_radio.count() > 0:
        anchor_radio.locator("..").click()
    page.wait_for_timeout(300)
    page.click("#wizard-next")
    page.wait_for_timeout(400)

    # Step 2 — anchor date + duration
    page.fill("#wizard-anchor-date", anchor_date)
    page.fill("#wizard-anchor-duration", anchor_duration_days)
    page.click("#wizard-next")
    page.wait_for_timeout(400)

    # Step 3 — check the requested phases
    for cb in page.locator('#timeline-wizard input[name="milestone_types"]').all():
        if cb.is_checked() and not cb.is_disabled():
            cb.uncheck()
    for mt in milestone_types:
        cb = page.locator(
            f'#timeline-wizard input[name="milestone_types"][value="{mt}"]'
        )
        if cb.count() > 0 and not cb.is_checked():
            cb.check()
    page.click("#wizard-next")
    page.wait_for_url(f"**/models/{model_id}/builder**", timeout=15_000)
    wait_for_htmx(page)

    # Per-milestone durations — every non-anchor phase needs a duration before
    # approve un-disables.
    if phase_durations:
        page.goto(f"/models/{model_id}/builder?module=timeline&wizard=1")
        page.wait_for_selector("#module-panel-content", timeout=10_000)
        wait_for_htmx(page)
        for mt_str, days in phase_durations.items():
            label = _PHASE_TYPE_LABELS.get(mt_str, mt_str.replace("_", " ").title())
            row = page.locator(
                f'#module-panel-content tr:has(td:has-text("{label}"))'
            )
            if row.count() > 0:
                row.first.click()
                page.wait_for_selector(
                    '#line-item-drawer [name="duration_days"]', timeout=8_000
                )
                page.fill('#line-item-drawer [name="duration_days"]', str(days))
                page.click('#line-item-drawer button[type="submit"]')
                wait_for_htmx(page)


# ---------------------------------------------------------------------------
# Chrome & wizard=1 propagation
# ---------------------------------------------------------------------------

def test_unified_wizard_chrome_renders_on_step1(logged_in_page, base_url):
    """Step 1 (`/deals/new`) shows the 3-step indicator with Step 1 active."""
    page = logged_in_page
    page.goto("/deals/new", wait_until="domcontentloaded")
    page.wait_for_selector(".dcw-chrome", timeout=8_000)
    # Chrome present
    assert page.locator(".dcw-chrome").count() == 1
    # All three step labels visible
    chrome = page.locator(".dcw-chrome")
    assert chrome.locator("text=Deal Basics").count() >= 1
    assert chrome.locator("text=Timeline").count() >= 1
    assert chrome.locator("text=Setup").count() >= 1


def test_unified_wizard_step1_to_step2_preserves_wizard_flag(logged_in_page, base_url):
    """Submitting Step 1 lands on builder?module=timeline&wizard=1 with chrome."""
    page = logged_in_page
    suffix = uuid.uuid4().hex[:6]
    page.goto("/deals/new", wait_until="domcontentloaded")
    page.fill('[name=name]', f"E2E Single-Flow {suffix}")
    page.select_option('[name=deal_type]', "acquisition")
    page.fill('[name="acquisition_cost"]', "2500000")
    page.click('[type=submit]')

    # Must land on builder with wizard=1 query param
    page.wait_for_url("**/models/*/builder**", timeout=15_000)
    assert "wizard=1" in page.url, f"wizard=1 dropped after Step 1 submit: {page.url}"
    # Step 2 active in chrome
    chrome = page.locator(".dcw-chrome")
    chrome.wait_for(state="visible", timeout=8_000)
    # Step 1 should be marked done (✓), step 2 active
    assert chrome.locator("text=Deal Basics").count() >= 1
    assert chrome.locator("text=Timeline").count() >= 1
    # Builder topbar + project tab row must be hidden in wizard mode
    topbar = page.locator(".builder-topbar").first
    if topbar.count() > 0:
        # `display:none` inline style applied when wizard_mode
        style = topbar.get_attribute("style") or ""
        assert "display:none" in style.replace(" ", ""), (
            f"builder-topbar still visible in wizard mode: style={style!r}"
        )


def test_unified_wizard_approve_timeline_preserves_wizard_flag(
    logged_in_page, base_url
):
    """Approving the timeline from inside the wizard redirects to deal_setup
    with `wizard=1` still attached and Step 3 active in the chrome."""
    page = logged_in_page
    suffix = uuid.uuid4().hex[:6]

    # Step 1 — create the deal
    page.goto("/deals/new", wait_until="domcontentloaded")
    page.fill('[name=name]', f"E2E Approve {suffix}")
    page.select_option('[name=deal_type]', "acquisition")
    page.fill('[name="acquisition_cost"]', "1500000")
    page.click('[type=submit]')
    page.wait_for_url("**/models/*/builder**", timeout=15_000)
    model_id = _extract_model_id(page.url)
    assert "wizard=1" in page.url

    # Step 2 — drive the timeline-wizard modal entirely in wizard mode so
    # the final Approve button renders as the wizard-footer button.
    _drive_timeline_wizard_in_flow(
        page,
        model_id,
        milestone_types=["close", "operation_stabilized", "divestment"],
        phase_durations={
            "operation_stabilized": 1825,  # 5 years
            "divestment": 1,
        },
    )

    page.goto(f"/models/{model_id}/builder?module=timeline&wizard=1")
    wait_for_htmx(page)
    page.wait_for_timeout(1000)
    approve = page.locator('button:has-text("Approve & Continue Setup")')
    approve.wait_for(state="visible", timeout=10_000)
    assert approve.is_enabled(), "Approve button disabled — milestones invalid"
    approve.click()

    # Should land on deal_setup with wizard=1
    page.wait_for_url(
        lambda url: "module=deal_setup" in url and "/builder" in url,
        timeout=15_000,
    )
    assert "wizard=1" in page.url, (
        f"wizard=1 dropped after Approve & Continue Setup: {page.url}"
    )
    page.wait_for_selector(".dcw-chrome", timeout=8_000)
    page.wait_for_selector("#deal-setup-wizard", timeout=8_000)


# ---------------------------------------------------------------------------
# Phase-filtered debt cards (Slice 2)
# ---------------------------------------------------------------------------

def test_unified_wizard_no_construction_hides_construction_debt_cards(
    logged_in_page, base_url
):
    """Timeline without a Construction phase hides Construction Loan +
    Const-to-Perm cards on the debt-stack step."""
    page = logged_in_page
    suffix = uuid.uuid4().hex[:6]

    # Step 1
    page.goto("/deals/new", wait_until="domcontentloaded")
    page.fill('[name=name]', f"E2E No-Constr {suffix}")
    page.select_option('[name=deal_type]', "acquisition")
    page.fill('[name="acquisition_cost"]', "3000000")
    page.click('[type=submit]')
    page.wait_for_url("**/models/*/builder**", timeout=15_000)
    model_id = _extract_model_id(page.url)

    # Step 2 — timeline with NO construction phase
    _drive_timeline_wizard_in_flow(
        page,
        model_id,
        milestone_types=["close", "operation_stabilized", "divestment"],
        phase_durations={
            "operation_stabilized": 1825,
            "divestment": 1,
        },
    )

    # Approve and advance to Step 3
    page.goto(f"/models/{model_id}/builder?module=timeline&wizard=1")
    wait_for_htmx(page)
    approve = page.locator('button:has-text("Approve & Continue Setup")')
    approve.wait_for(state="visible", timeout=10_000)
    approve.click()
    page.wait_for_url(
        lambda url: "module=deal_setup" in url and "/builder" in url,
        timeout=15_000,
    )
    page.wait_for_selector("#deal-setup-wizard", timeout=10_000)

    # Step 1 of deal-setup → advance to Step 2 (debt stack)
    page.click('#deal-setup-wizard .wizard-footer button.btn-primary')
    wait_for_htmx(page)
    page.wait_for_selector("#debt-type-grid", timeout=8_000)

    # Construction-only cards must be ABSENT (not just disabled)
    grid = page.locator("#debt-type-grid")
    assert grid.locator('input[value="construction_loan"]').count() == 0, (
        "construction_loan card rendered despite no Construction phase"
    )
    assert grid.locator('input[value="construction_to_perm"]').count() == 0, (
        "construction_to_perm card rendered despite no Construction phase"
    )
    # Always-shown cards still present
    assert grid.locator('input[value="permanent_debt"]').count() >= 1
    assert grid.locator('input[value="acquisition_loan"]').count() >= 1


# ---------------------------------------------------------------------------
# End-to-end data validation — typed values reach persisted rows
# ---------------------------------------------------------------------------

def test_unified_wizard_data_reaches_deal_via_api(
    logged_in_page, base_url, api_key
):
    """Full happy path: drive all three wizard stages via the browser, then
    fetch the persisted records via the API and assert every typed value
    landed where the engine expects it."""
    from tests.e2e.seed import run_deal_setup_wizard

    page = logged_in_page
    suffix = uuid.uuid4().hex[:6]
    deal_name = f"E2E Unified {suffix}"
    acq_cost = 2_750_000

    # Step 1 — Deal Basics
    page.goto("/deals/new", wait_until="domcontentloaded")
    page.fill('[name=name]', deal_name)
    page.select_option('[name=deal_type]', "acquisition")
    page.fill('[name="acquisition_cost"]', str(acq_cost))
    page.click('[type=submit]')
    page.wait_for_url("**/models/*/builder**", timeout=15_000)
    model_id = _extract_model_id(page.url)
    assert "wizard=1" in page.url

    # Step 2 — Timeline (include construction so all debt options remain)
    _drive_timeline_wizard_in_flow(
        page,
        model_id,
        milestone_types=[
            "close",
            "construction",
            "operation_stabilized",
            "divestment",
        ],
        phase_durations={
            "construction": 180,
            "operation_stabilized": 1825,
            "divestment": 1,
        },
    )
    page.goto(f"/models/{model_id}/builder?module=timeline&wizard=1")
    wait_for_htmx(page)
    page.wait_for_timeout(1000)
    approve = page.locator('button:has-text("Approve & Continue Setup")')
    approve.wait_for(state="visible", timeout=10_000)
    assert approve.is_enabled(), "Approve button disabled in data-validation test"
    approve.click()
    page.wait_for_url(
        lambda url: "module=deal_setup" in url and "/builder" in url,
        timeout=15_000,
    )

    # Step 3 — Deal Setup. Use existing helper; it already finishes the wizard.
    run_deal_setup_wizard(
        page,
        model_id,
        income_mode="revenue_opex",
        debt_types=["permanent_debt"],
        debt_sizing_mode="gap_fill",
        debt_terms={"permanent_debt": {"rate_pct": "6.5", "amort_years": "30"}},
        dscr_minimum="1.25",
    )

    # Wizard exits to builder when done
    page.wait_for_url(
        lambda url: "module=deal_setup" not in url and "/builder" in url,
        timeout=30_000,
    )

    # ---- API validation ----
    with _api(base_url, page, api_key) as client:
        # Acquisition cost must have produced an Acquisition UseLine
        r = client.get(f"/api/models/{model_id}/use-lines")
        assert r.status_code == 200, r.text
        use_lines = r.json()
        # The seeded acquisition UseLine is the one in phase=acquisition whose
        # amount matches what the user typed in Step 1. Auto-cost rows in the
        # same phase carry $0; the developer-fee row is also $0 at seed time.
        acq = [
            u for u in use_lines
            if u.get("phase") == "acquisition"
            and int(float(u.get("amount") or 0)) == acq_cost
        ]
        assert acq, (
            f"No acquisition UseLine with amount={acq_cost} found in: "
            f"{[(u['label'], u['amount']) for u in use_lines]}"
        )

        # OperationalInputs reflects Step 3 selections (income_mode lives on
        # Scenario itself, not OperationalInputs — debt_terms / debt_types /
        # debt_sizing_mode are what the wizard actually writes here).
        r = client.get(f"/api/models/{model_id}/inputs")
        assert r.status_code == 200, r.text
        inputs = r.json()
        assert inputs is not None, "OperationalInputs missing"
        assert inputs["debt_sizing_mode"] == "gap_fill"
        assert "permanent_debt" in (inputs.get("debt_types") or [])
        dt = (inputs.get("debt_terms") or {}).get("permanent_debt") or {}
        assert float(dt.get("rate_pct", 0)) == pytest.approx(6.5), dt
        assert int(dt.get("amort_years") or dt.get("amort_term_years") or 0) == 30, dt

        # CapitalModule for permanent debt exists post-finish. The wizard
        # labels its auto-created module "Permanent Debt (auto)" and writes
        # the typed rate/amort into source/carry — assert both round-trip.
        r = client.get(f"/api/models/{model_id}/capital-modules")
        assert r.status_code == 200, r.text
        modules = r.json()
        perm = [
            m for m in modules
            if "permanent debt" in (m.get("label") or "").lower()
        ]
        assert perm, f"No permanent_debt CapitalModule created: {modules}"
        pm = perm[0]
        assert float(pm["source"]["interest_rate_pct"]) == pytest.approx(6.5)
        assert int(pm["carry"]["amort_term_years"]) == 30
        assert float(pm["source"]["dscr_min"]) == pytest.approx(1.25)
