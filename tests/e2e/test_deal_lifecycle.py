"""Deal lifecycle E2E tests — structural math verification for Variant A.

Variant A: acquisition_minor_reno, positive cash flow, gap_fill debt sizing, with exit.

Seeded deal:
  - Uses:    Purchase Price $800k + Renovation $50k + Closing Costs $15k = $865k
  - Revenue: 10 units × $1,200/mo × 95% occ = $136,800/yr
  - OpEx:    Mgmt $14,400 + Insurance $6,000 + Tax $9,600 = $30,000/yr (+ 19 seeded $0 lines)
  - Debt:    Perm-only bond, auto-sized via gap_fill, DSCR floor 1.25
  - Exit:    Divestment milestone included — IRR should be positive

Math tests re-derive key outputs from displayed UI values and compare to the
engine-computed totals shown in the same page. Differences within rounding
tolerance are accepted.

Run:
    uv run pytest tests/e2e/test_deal_lifecycle.py -m e2e -v
    uv run pytest tests/e2e/test_deal_lifecycle.py -m e2e -v --headed --browser chromium
"""

from __future__ import annotations

import pytest

from tests.e2e.helpers import (
    read_cashflow_table,
    read_footer_total,
    read_sources_total,
    read_stat_currency,
    read_stat_pct,
    read_table_col_amounts,
    wait_for_htmx,
)
from tests.e2e.seed import create_seeded_deal

pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Session-scoped seeded deal fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def lifecycle_deal(base_url: str, _auth_state_path: str) -> tuple[str, str]:
    """Create one fully-seeded deal for all lifecycle tests. Returns (model_id, project_id)."""
    return create_seeded_deal(
        base_url,
        _auth_state_path,
        deal_name="E2E Lifecycle — Variant A",
        deal_type="acquisition_minor_reno",
    )


# ---------------------------------------------------------------------------
# Helper: navigate to a builder module and wait for the panel
# ---------------------------------------------------------------------------

def _goto_module(page, base_url: str, model_id: str, module: str) -> None:
    page.goto(f"{base_url}/models/{model_id}/builder?module={module}")
    page.wait_for_selector("#module-panel-content", timeout=15_000)
    wait_for_htmx(page)


# ---------------------------------------------------------------------------
# 1. Uses rows sum matches the displayed footer total
# ---------------------------------------------------------------------------

def test_uses_rows_sum_matches_total(
    logged_in_page, base_url: str, lifecycle_deal: tuple[str, str]
) -> None:
    """Sum of every Use-line Amount cell == 'Total Uses' footer.

    This verifies the UI correctly accumulates all use lines and that the
    seeding actually persisted the three use lines we created.
    """
    model_id, _ = lifecycle_deal
    _goto_module(logged_in_page, base_url, model_id, "uses")

    # Collect the single col-right td in each uses row (the Amount column)
    row_amounts = read_table_col_amounts(
        logged_in_page,
        row_selector="#module-panel-content .line-table tbody tr",
        col_selector="td.col-right",
        col_index=0,
    )
    assert row_amounts, "No use-line rows found — seeding may have failed"

    footer = read_footer_total(logged_in_page)
    assert footer is not None, "'Total Uses' footer was '—' — no use lines?"

    computed_sum = sum(row_amounts)
    tolerance = max(1.0, footer * 0.005)
    assert abs(computed_sum - footer) <= tolerance, (
        f"Uses sum {computed_sum:.2f} ≠ footer {footer:.2f} (tol {tolerance:.2f})"
    )


# ---------------------------------------------------------------------------
# 2. Revenue rows sum matches the displayed footer total
# ---------------------------------------------------------------------------

def test_revenue_rows_sum_matches_total(
    logged_in_page, base_url: str, lifecycle_deal: tuple[str, str]
) -> None:
    """Sum of the 'Annual (stabilized)' column == 'Annual Revenue' footer.

    Revenue rows show estimated annual EGI per stream (occupancy already applied).
    The footer aggregates the same values via _income_annual on the server.
    """
    model_id, _ = lifecycle_deal
    _goto_module(logged_in_page, base_url, model_id, "revenue")

    # The revenue table has multiple col-right columns per row:
    # Units | $/Unit/Mo | Occupancy | Escalation | Annual (stabilized)
    # We want the LAST col-right — Annual (stabilized)
    row_amounts = read_table_col_amounts(
        logged_in_page,
        row_selector="#module-panel-content .line-table tbody tr",
        col_selector="td.col-right",
        col_index=-1,
    )
    assert row_amounts, "No revenue rows found — seeding may have failed"

    footer = read_footer_total(logged_in_page)
    assert footer is not None, "'Annual Revenue' footer was '—'"

    computed_sum = sum(row_amounts)
    tolerance = max(1.0, footer * 0.005)
    assert abs(computed_sum - footer) <= tolerance, (
        f"Revenue sum {computed_sum:.2f} ≠ footer {footer:.2f} (tol {tolerance:.2f})"
    )


# ---------------------------------------------------------------------------
# 3. OpEx rows sum matches the displayed footer total
# ---------------------------------------------------------------------------

def test_opex_rows_sum_matches_total(
    logged_in_page, base_url: str, lifecycle_deal: tuple[str, str]
) -> None:
    """Sum of the 'Annual Amount' column across ALL OpEx rows == 'Total Annual OpEx' footer.

    The server computes opex_annual = sum(e.annual_amount for e in expense_lines).
    This test confirms the displayed row values add up to the same number,
    catching any row-suppression or rendering bugs.

    Note: 19 rows were auto-seeded at $0 by setup/complete, plus our 3 non-zero
    lines. The seeded $0 rows contribute 0 to both the row sum and the footer.
    """
    model_id, _ = lifecycle_deal
    _goto_module(logged_in_page, base_url, model_id, "opex")

    # OpEx table: Label | Annual Amount | Escalation | (delete)
    # First col-right = Annual Amount
    row_amounts = read_table_col_amounts(
        logged_in_page,
        row_selector="#module-panel-content .line-table tbody tr",
        col_selector="td.col-right",
        col_index=0,
    )
    assert row_amounts, "No OpEx rows found"

    footer = read_footer_total(logged_in_page)
    assert footer is not None, "'Total Annual OpEx' footer was '—'"

    computed_sum = sum(row_amounts)
    tolerance = max(1.0, footer * 0.005)
    assert abs(computed_sum - footer) <= tolerance, (
        f"OpEx sum {computed_sum:.2f} ≠ footer {footer:.2f} (tol {tolerance:.2f})"
    )


# ---------------------------------------------------------------------------
# 4. NOI ≈ revenue − opex (within engine tolerance)
# ---------------------------------------------------------------------------

def test_noi_approximates_revenue_minus_opex(
    logged_in_page, base_url: str, lifecycle_deal: tuple[str, str]
) -> None:
    """Engine NOI ≈ (EGI − OpEx) computed from the values displayed in the UI.

    We read revenue_annual and opex_annual from their module footers, compute
    the naive NOI, then compare to the engine's NOI stat card.

    A 5% tolerance is allowed because the engine escalates expenses to the
    stabilized month rather than using the nominal annual_amount directly.
    """
    model_id, _ = lifecycle_deal

    # Read revenue EGI from its footer
    _goto_module(logged_in_page, base_url, model_id, "revenue")
    revenue = read_footer_total(logged_in_page)
    assert revenue is not None, "Revenue footer missing — no income streams?"
    assert revenue > 0, f"Revenue is {revenue} — expected a positive number"

    # Read opex total from its footer
    _goto_module(logged_in_page, base_url, model_id, "opex")
    opex = read_footer_total(logged_in_page)
    assert opex is not None, "OpEx footer missing — no expense lines?"
    assert opex > 0, f"OpEx is {opex} — expected a positive number"

    naive_noi = revenue - opex

    # Read engine-computed NOI from the owners_profit stat card
    _goto_module(logged_in_page, base_url, model_id, "owners_profit")
    engine_noi = read_stat_currency(logged_in_page, "NOI (Stabilized)")
    assert engine_noi is not None, (
        "NOI stat card shows '—' — has compute been run? Check seeding."
    )

    tolerance = max(500.0, abs(naive_noi) * 0.05)
    assert abs(engine_noi - naive_noi) <= tolerance, (
        f"Engine NOI {engine_noi:.2f} differs from UI-derived NOI {naive_noi:.2f} "
        f"(revenue={revenue:.2f}, opex={opex:.2f}, tol={tolerance:.2f})"
    )


# ---------------------------------------------------------------------------
# 5. Sources total == Uses total (gap_fill should balance the stack)
# ---------------------------------------------------------------------------

def test_sources_balance_uses(
    logged_in_page, base_url: str, lifecycle_deal: tuple[str, str]
) -> None:
    """After compute, capital sources sum == total uses.

    With gap_fill sizing, the debt is auto-sized first and equity fills
    the gap. The total capital stack must equal total uses to the dollar.
    """
    model_id, _ = lifecycle_deal

    # Get uses total
    _goto_module(logged_in_page, base_url, model_id, "uses")
    uses_total = read_footer_total(logged_in_page)
    assert uses_total is not None, "Uses footer is missing"
    assert uses_total > 0, f"Uses total is {uses_total}"

    # Get sources total from the Sources header box
    _goto_module(logged_in_page, base_url, model_id, "sources")
    sources_total = read_sources_total(logged_in_page)
    assert sources_total is not None, (
        "Sources total box is empty — has compute auto-sized the capital modules? "
        "Check that create_seeded_deal ran compute successfully."
    )

    assert abs(sources_total - uses_total) <= 1.0, (
        f"Sources {sources_total:.2f} ≠ Uses {uses_total:.2f} "
        f"(diff={sources_total - uses_total:.2f}) — gap_fill should balance to $0"
    )


# ---------------------------------------------------------------------------
# 6. Project IRR is positive (good deal with exit)
# ---------------------------------------------------------------------------

def test_irr_is_positive(
    logged_in_page, base_url: str, lifecycle_deal: tuple[str, str]
) -> None:
    """Project IRR (Levered) should be > 0 for a positive-cash-flow deal with exit.

    Seeded deal: $136,800 gross revenue, $30,000 opex → ~$106,800 NOI on an
    $865,000 cost base. With a divestment exit, the levered IRR should be
    meaningfully positive.
    """
    model_id, _ = lifecycle_deal
    _goto_module(logged_in_page, base_url, model_id, "owners_profit")

    irr = read_stat_pct(logged_in_page, "Project IRR (Levered)")
    assert irr is not None, (
        "IRR stat card shows '—' — compute may not have run or waterfall failed. "
        "Check that create_seeded_deal completed successfully."
    )
    assert irr > 0, f"IRR {irr:.1f}% is not positive — deal may be structurally wrong"


# ---------------------------------------------------------------------------
# 7. Capital balance at first stabilized period = prior balance + that period's NCF
# ---------------------------------------------------------------------------

def test_capital_balance_transition_at_stabilization(
    logged_in_page, base_url: str, lifecycle_deal: tuple[str, str]
) -> None:
    """Capital balance[first_stab] = capital_balance[last_pre_stab] + net_cf[first_stab].

    The Capital Balance column is a running sum seeded at total_sources.  Every
    period advances it by that period's net cash flow.  This test verifies the
    carry-forward is correct at the single most important boundary: the moment
    the project transitions from construction into stabilized operation.

    We also check that the balance entering stabilization is within 10% of the
    Operating Reserve stat card — confirming the auto-sizing targeted the reserve
    correctly (loose tolerance because the waterfall may allocate slightly
    differently from the stat-card estimate).
    """
    model_id, _ = lifecycle_deal
    _goto_module(logged_in_page, base_url, model_id, "cashflow")

    rows = read_cashflow_table(logged_in_page)
    assert rows, "Cashflow table is empty — compute may not have run"

    # Find the first row whose phase is 'stabilized'
    first_stab_idx = next(
        (i for i, r in enumerate(rows) if r["phase"] == "stabilized"), None
    )
    assert first_stab_idx is not None, (
        "No 'stabilized' phase rows found in cashflow table. "
        "Check that the timeline wizard set up the stabilized milestone."
    )
    assert first_stab_idx > 0, "First stabilized period is period 0 — no prior row to compare"

    first_stab = rows[first_stab_idx]
    prev = rows[first_stab_idx - 1]          # last pre-stabilization row

    # Invariant: capital_balance[t] = capital_balance[t-1] + net_cf[t]
    expected_balance = prev["capital_balance"] + first_stab["net_cf"]
    assert abs(first_stab["capital_balance"] - expected_balance) <= 1.0, (
        f"Capital balance carry-forward failed at first stabilized period {first_stab['period']}: "
        f"prev_balance={prev['capital_balance']:.0f}, "
        f"net_cf={first_stab['net_cf']:.0f}, "
        f"expected={expected_balance:.0f}, "
        f"actual={first_stab['capital_balance']:.0f}"
    )

    # Soft check: balance entering stabilization ≈ operating reserve
    reserve = read_stat_currency(logged_in_page, "Operating Reserve")
    if reserve is not None and reserve > 0:
        tolerance = max(500.0, reserve * 0.10)
        assert abs(prev["capital_balance"] - reserve) <= tolerance, (
            f"Balance entering stabilization ({prev['capital_balance']:.0f}) differs from "
            f"operating reserve stat card ({reserve:.0f}) by more than 10% — "
            f"auto-sizing may not have targeted the reserve correctly"
        )


# ---------------------------------------------------------------------------
# 8. Capital balance floor: positive CF → never drops below stab-entry level
# ---------------------------------------------------------------------------

def test_capital_balance_floor_positive_deal(
    logged_in_page, base_url: str, lifecycle_deal: tuple[str, str]
) -> None:
    """For a positive-cash-flow deal, the capital balance during stabilized operation
    should never fall below the level it entered stabilization at.

    Logic (waterfall engine): capital_balance[t] = capital_balance[t-1] + net_cf[t].
    When every stabilized net_cf ≥ 0, the balance can only stay flat or increase,
    so it can never go below the starting stabilized level.

    If ANY stabilized period has net_cf < 0, this test deliberately fails — that
    would mean the deal has a structural problem (negative operating cash flow
    despite being seeded as a positive deal).

    For negative-cash-flow deal variants (Variant D/E): the inverse assertion
    should hold — some stabilized period WILL drop below the entry balance.
    That is tested separately when those variants are seeded.
    """
    model_id, _ = lifecycle_deal
    _goto_module(logged_in_page, base_url, model_id, "cashflow")

    rows = read_cashflow_table(logged_in_page)
    assert rows, "Cashflow table is empty — compute may not have run"

    first_stab_idx = next(
        (i for i, r in enumerate(rows) if r["phase"] == "stabilized"), None
    )
    assert first_stab_idx is not None, "No stabilized rows found in cashflow table"
    assert first_stab_idx > 0, "First stabilized row has no preceding row"

    # The balance entering stabilization is the floor
    floor = rows[first_stab_idx - 1]["capital_balance"]

    stab_rows = [r for r in rows if r["phase"] == "stabilized"]
    assert stab_rows, "No stabilized rows to check"

    breaches = [
        r for r in stab_rows
        if r["capital_balance"] < floor - 1.0  # $1 rounding tolerance
    ]
    assert not breaches, (
        f"Capital balance dropped below the stabilization-entry floor ({floor:.0f}) "
        f"during {len(breaches)} stabilized period(s). "
        f"First breach: period {breaches[0]['period']}, "
        f"balance={breaches[0]['capital_balance']:.0f}, "
        f"net_cf={breaches[0]['net_cf']:.0f}. "
        f"This should not happen for a positive-cash-flow deal."
    )
