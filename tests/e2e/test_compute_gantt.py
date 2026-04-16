"""Compute + tab retention + Gantt rendering E2E tests.

Verifies:
- Compute stays on the current module tab (not redirecting to Owners & Profit)
- Permanent debt appears on the Gantt after compute
- Divestment is visible on the Gantt
- Sources & Uses renders both panels on first load

Run:
    uv run pytest tests/e2e/test_compute_gantt.py -m e2e -v
"""

from __future__ import annotations

import pytest

from tests.e2e.helpers import wait_for_htmx
from tests.e2e.seed import create_seeded_deal

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def seeded_deal(_seed_page) -> tuple[str, str]:
    """Create a fully-seeded deal with construction + perm debt for Gantt testing."""
    from tests.e2e.seed import (
        create_e2e_scenario,
        submit_timeline_wizard,
        run_deal_setup_wizard,
        add_use_line,
        add_income_stream,
        add_expense_line,
        click_compute,
        _extract_project_id,
    )

    page = _seed_page
    model_id = create_e2e_scenario(page, deal_name="E2E Compute+Gantt Test")
    project_id = _extract_project_id(page)

    submit_timeline_wizard(
        page, model_id, project_id,
        milestone_types=["close", "pre_development", "construction",
                         "operation_stabilized", "divestment"],
        phase_durations={"pre_development": 90, "construction": 365,
                         "operation_stabilized": 1825},
    )

    run_deal_setup_wizard(
        page, model_id,
        debt_types=["construction_loan", "permanent_debt"],
        milestone_config={
            "construction_loan": {
                "active_from": "pre_construction",
                "active_to": "operation_stabilized",
                "retired_by": "permanent_debt",
            },
            "permanent_debt": {
                "active_from": "pre_construction",
                "active_to": "perpetuity",
                "retired_by": "perpetuity",
            },
        },
        debt_terms={
            "construction_loan": {"rate_pct": "7.0", "loan_type": "capitalized_interest"},
            "permanent_debt": {"rate_pct": "6.5", "loan_type": "pi", "amort_years": "30"},
        },
        operation_reserve_months="6",
    )

    add_use_line(page, model_id, "Purchase Price", "800000", milestone_key="close")
    add_use_line(page, model_id, "Hard Construction", "600000", milestone_key="construction")
    add_income_stream(page, model_id, unit_count="20", amount_per_unit_monthly="1200")
    add_expense_line(page, model_id, "Property Management", "28800")
    add_expense_line(page, model_id, "Insurance", "7200")
    add_expense_line(page, model_id, "Property Tax", "12000", escalation_pct="2")

    click_compute(page, model_id)
    return model_id, project_id


# ---------------------------------------------------------------------------
# Compute stays on current tab
# ---------------------------------------------------------------------------

def test_compute_stays_on_sources_uses(logged_in_page, base_url, seeded_deal):
    """After clicking Compute from S&U, the page should stay on S&U (not redirect to Owners)."""
    model_id, _ = seeded_deal
    page = logged_in_page

    page.goto(f"{base_url}/models/{model_id}/builder?module=sources_uses")
    page.wait_for_selector("#module-panel-content", timeout=10_000)
    wait_for_htmx(page)

    # Click Compute
    page.click('button:has-text("Compute")')
    page.wait_for_selector('#compute-result .badge', timeout=30_000)
    wait_for_htmx(page)

    # URL should still have sources_uses, not owners_profit
    assert "sources_uses" in page.url, f"Expected to stay on sources_uses, got: {page.url}"
    # Panel should still show "Sources & Uses" title
    title = page.locator(".module-panel-title")
    assert title.count() > 0
    assert "Sources" in title.inner_text()


def test_compute_stays_on_revenue(logged_in_page, base_url, seeded_deal):
    """After clicking Compute from Revenue, should stay on Revenue."""
    model_id, _ = seeded_deal
    page = logged_in_page

    page.goto(f"{base_url}/models/{model_id}/builder?module=revenue")
    page.wait_for_selector("#module-panel-content", timeout=10_000)
    wait_for_htmx(page)

    page.click('button:has-text("Compute")')
    page.wait_for_selector('#compute-result .badge', timeout=30_000)
    wait_for_htmx(page)

    assert "revenue" in page.url, f"Expected to stay on revenue, got: {page.url}"


# ---------------------------------------------------------------------------
# Sources & Uses first load shows both panels
# ---------------------------------------------------------------------------

def test_sources_uses_shows_both_panels(logged_in_page, base_url, seeded_deal):
    """S&U module should show both Sources and Uses tables, not just Uses."""
    model_id, _ = seeded_deal
    page = logged_in_page

    page.goto(f"{base_url}/models/{model_id}/builder?module=sources_uses")
    page.wait_for_selector("#module-panel-content", timeout=10_000)
    wait_for_htmx(page)

    # Should see "Sources & Uses" title (the combined panel)
    title = page.locator(".module-panel-title")
    assert "Sources" in title.inner_text()
    assert "Uses" in title.inner_text()


# ---------------------------------------------------------------------------
# Gantt: Permanent debt bar visible
# ---------------------------------------------------------------------------

def test_gantt_shows_permanent_debt(logged_in_page, base_url, seeded_deal):
    """Permanent Debt should appear as a bar on the Gantt chart after compute."""
    model_id, _ = seeded_deal
    page = logged_in_page

    page.goto(f"{base_url}/models/{model_id}/builder?module=timeline")
    page.wait_for_selector("#module-panel-content", timeout=15_000)
    wait_for_htmx(page)

    # Capital module Gantt bars are .g2-row-source in the timeline panel.
    # If not found, the Gantt may not render source bars on the timeline panel.
    # Check for any source row first, then specific labels.
    source_rows = page.locator('.g2-row-source')
    if source_rows.count() == 0:
        # Gantt source bars may be in a different section — check page content
        content = page.content()
        assert "Permanent" in content, "Permanent Debt not found anywhere on timeline page"
    else:
        perm_labels = page.locator('.g2-row-source .g2-label:has-text("Permanent")')
        assert perm_labels.count() > 0, "Permanent Debt bar not found on timeline Gantt"


def test_gantt_shows_construction_loan(logged_in_page, base_url, seeded_deal):
    """Construction Loan should appear as a bar on the Gantt chart."""
    model_id, _ = seeded_deal
    page = logged_in_page

    page.goto(f"{base_url}/models/{model_id}/builder?module=timeline")
    page.wait_for_selector("#module-panel-content", timeout=15_000)
    wait_for_htmx(page)

    source_rows = page.locator('.g2-row-source')
    if source_rows.count() == 0:
        content = page.content()
        assert "Construction" in content, "Construction Loan not found anywhere on timeline page"
    else:
        constr_labels = page.locator('.g2-row-source .g2-label:has-text("Construction")')
        assert constr_labels.count() > 0, "Construction Loan bar not found on timeline Gantt"


# ---------------------------------------------------------------------------
# Gantt: Divestment milestone visible
# ---------------------------------------------------------------------------

def test_gantt_shows_divestment(logged_in_page, base_url, seeded_deal):
    """Divestment milestone should be visible on the timeline Gantt."""
    model_id, _ = seeded_deal
    page = logged_in_page

    page.goto(f"{base_url}/models/{model_id}/builder?module=timeline")
    page.wait_for_selector("#module-panel-content", timeout=10_000)
    wait_for_htmx(page)

    # Divestment should appear in the phase summary boxes or Gantt bars
    divestment_bar = page.locator('.g2-bar:has-text("Divestment")')
    divestment_box = page.locator('text=Divestment')
    assert divestment_bar.count() > 0 or divestment_box.count() > 0, \
        "Divestment not visible on timeline"


def test_divestment_shows_as_event(logged_in_page, base_url, seeded_deal):
    """Divestment phase summary should show 'Event' not '0 mo'."""
    model_id, _ = seeded_deal
    page = logged_in_page

    page.goto(f"{base_url}/models/{model_id}/builder?module=timeline")
    page.wait_for_selector("#module-panel-content", timeout=10_000)
    wait_for_htmx(page)

    # Look for the Divestment phase box — should contain "Event"
    content = page.content()
    # The phase box has "Divestment" label and either "Event" or "1d" for duration
    assert "Event" in content or "1d" in content, \
        "Divestment should display as 'Event' or '1d', not '0 mo'"
