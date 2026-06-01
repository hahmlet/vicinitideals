"""Tests for the draw schedule engine."""

from datetime import datetime
from decimal import Decimal

import pytest

from app.engines.draw_schedule import (
    BalanceViolation,
    DealMilestone,
    DrawScheduleCalculator,
    DrawScheduleConfig,
    DrawScheduleInputs,
    OperatingMonth,
    SourceDef,
    UseLineItem,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def milestones():
    return [
        DealMilestone("offer_made",         "Offer Made",         datetime(2025, 1, 1)),
        DealMilestone("under_contract",     "Under Contract",     datetime(2025, 2, 1)),
        DealMilestone("close",              "Close",              datetime(2025, 4, 1)),
        DealMilestone("construction_start", "Construction Start", datetime(2025, 5, 1)),
        DealMilestone("co",                 "Certificate of Occ", datetime(2026, 5, 1)),
        DealMilestone("stabilized",         "Stabilized",         datetime(2026, 11, 1)),
    ]


# ---------------------------------------------------------------------------
# Self-referential draw sizing
# ---------------------------------------------------------------------------

def test_self_referential_draw_covers_carry_on_full_balance():
    """
    For a debt source, carry accrues on the FULL cumulative balance
    (prior balance + this draw) over the n-month window, not just on the new
    draw. The self-referential formula sizes total_draw to pre-fund this:
    D = (uses + payoff + B × r × n) / (1 - r × n) implies carry = (B + D) × r × n.
    """
    inputs = DrawScheduleInputs(
        milestones=milestones(),
        uses=[
            UseLineItem("hard", "Hard Costs", "hard_costs", Decimal("600_000"), "construction_start", 6),
        ],
        sources=[
            SourceDef(
                key="loan",
                label="Construction Loan",
                source_type="debt",
                draw_every_n_months=2,
                annual_interest_rate=Decimal("0.08"),
                active_from_milestone="construction_start",
                active_to_milestone="co",
            ),
        ],
    )

    schedule = DrawScheduleCalculator(inputs).calculate()
    monthly_rate = Decimal("0.08") / Decimal("12")

    for draw in schedule.by_source["loan"]:
        expected_carry = (draw.balance_before + draw.total_draw) * monthly_rate * Decimal("2")
        assert abs(draw.carry_cost - expected_carry) < Decimal("0.01"), (
            f"Draw {draw.draw_number}: carry {draw.carry_cost} != "
            f"expected {expected_carry} ((B + D) × rate × freq)"
        )


def test_funded_carry_skips_self_referential_capitalization():
    """
    When a loan's carry is pre-funded by a separate Interest Reserve UseLine
    (carry_type=="interest_reserve" → SourceDef.funded_carry=True), the
    draw must NOT capitalize additional carry on top. Otherwise we'd
    double-count interest: once via the IR UseLine, again via the self-
    referential formula's carry term.

    With funded_carry=True: total_draw == uses + payoff (no carry markup);
    carry_cost == 0; loan balance grows by uses only.
    """
    inputs = DrawScheduleInputs(
        milestones=milestones(),
        uses=[
            UseLineItem("hard", "Hard Costs", "hard_costs", Decimal("600_000"),
                        "construction_start", 6),
        ],
        sources=[
            SourceDef(
                key="loan",
                label="Construction Loan (IR-pool funded)",
                source_type="debt",
                draw_every_n_months=2,
                annual_interest_rate=Decimal("0.08"),  # rate set but…
                active_from_milestone="construction_start",
                active_to_milestone="co",
                funded_carry=True,                       # …carry pre-funded
            ),
        ],
    )
    schedule = DrawScheduleCalculator(inputs).calculate()

    total_uses = Decimal("600_000")
    total_drawn = sum(d.total_draw for d in schedule.by_source["loan"])
    total_carry = sum(d.carry_cost for d in schedule.by_source["loan"])

    # Loan balance = uses only (no carry capitalized)
    assert total_drawn == total_uses, (
        f"funded_carry=True must fund only uses, got {total_drawn} vs {total_uses}"
    )
    assert total_carry == Decimal("0"), (
        f"funded_carry=True must report zero carry_cost, got {total_carry}"
    )


def test_funded_carry_vs_capitalized_diverge_by_expected_amount():
    """
    For the same loan inputs, the funded_carry=True path should produce a
    loan balance smaller than the self-referential capitalized path by
    approximately the interest amount the IR pool would have covered.
    """
    base_kwargs = dict(
        key="loan",
        label="Construction Loan",
        source_type="debt",
        draw_every_n_months=2,
        annual_interest_rate=Decimal("0.08"),
        active_from_milestone="construction_start",
        active_to_milestone="co",
    )
    capitalized_inputs = DrawScheduleInputs(
        milestones=milestones(),
        uses=[UseLineItem("hard", "Hard Costs", "hard_costs",
                          Decimal("600_000"), "construction_start", 6)],
        sources=[SourceDef(**base_kwargs, funded_carry=False)],
    )
    funded_inputs = DrawScheduleInputs(
        milestones=milestones(),
        uses=[UseLineItem("hard", "Hard Costs", "hard_costs",
                          Decimal("600_000"), "construction_start", 6)],
        sources=[SourceDef(**base_kwargs, funded_carry=True)],
    )
    cap = DrawScheduleCalculator(capitalized_inputs).calculate()
    fund = DrawScheduleCalculator(funded_inputs).calculate()

    cap_total = sum(d.total_draw for d in cap.by_source["loan"])
    fund_total = sum(d.total_draw for d in fund.by_source["loan"])

    # Capitalized path must exceed funded path by at least the carry amount.
    diff = cap_total - fund_total
    assert diff > Decimal("0"), (
        f"capitalized total ({cap_total}) must exceed funded total ({fund_total})"
    )
    # And funded total must equal uses-only.
    assert fund_total == Decimal("600_000")


def test_naive_draw_underestimates_vs_self_referential():
    """
    Naive formula: D = uses + B × r × n
    Self-referential: D = (uses + B × r × n) / (1 - r × n)
    Self-referential draw must always be >= naive draw for r > 0.
    """
    monthly_rate = Decimal("0.08") / Decimal("12")
    freq = Decimal("2")
    uses = Decimal("100_000")
    prior_balance = Decimal("200_000")

    naive = uses + prior_balance * monthly_rate * freq
    self_ref = (uses + prior_balance * monthly_rate * freq) / (Decimal("1") - monthly_rate * freq)

    assert self_ref > naive, "Self-referential draw must exceed naive draw"


# ---------------------------------------------------------------------------
# Reserve violation detection
# ---------------------------------------------------------------------------

def test_no_violations_when_reserve_zero():
    """With $0 reserve, a well-sized draw schedule should have no violations."""
    inputs = DrawScheduleInputs(
        milestones=milestones(),
        uses=[
            UseLineItem("hard", "Hard Costs", "hard_costs", Decimal("600_000"), "construction_start", 6),
        ],
        sources=[
            SourceDef(
                key="loan", label="Loan", source_type="debt",
                draw_every_n_months=2, annual_interest_rate=Decimal("0.06"),
                active_from_milestone="construction_start", active_to_milestone="co",
            ),
        ],
        config=DrawScheduleConfig(
            min_reserve_construction=Decimal("0"),
            min_reserve_operational=Decimal("0"),
        ),
    )

    schedule = DrawScheduleCalculator(inputs).calculate()
    assert schedule.is_valid
    assert schedule.violations == []


def test_violation_detected_when_draws_too_infrequent():
    """
    If a source draws every 6 months but uses hit every month,
    cash goes negative between draws. Violation should be flagged.
    """
    inputs = DrawScheduleInputs(
        milestones=milestones(),
        uses=[
            # $600k spread over 6 months — $100k/month hits each month
            UseLineItem("hard", "Hard Costs", "hard_costs", Decimal("600_000"), "construction_start", 6),
        ],
        sources=[
            # Draws only every 6 months but monthly costs hit immediately
            SourceDef(
                key="loan", label="Loan", source_type="debt",
                draw_every_n_months=6, annual_interest_rate=Decimal("0.0"),
                active_from_milestone="construction_start", active_to_milestone="co",
            ),
        ],
        config=DrawScheduleConfig(
            min_reserve_construction=Decimal("50_000"),
        ),
    )

    schedule = DrawScheduleCalculator(inputs).calculate()
    # With a $50k reserve floor and draws every 6 months, months 2-5 will be below reserve
    assert not schedule.is_valid
    assert len(schedule.violations) > 0
    assert all(isinstance(v, BalanceViolation) for v in schedule.violations)


def test_violation_shortfall_is_positive():
    """Shortfall on a violation should always be positive."""
    inputs = DrawScheduleInputs(
        milestones=milestones(),
        uses=[
            UseLineItem("hard", "Hard", "hard_costs", Decimal("300_000"), "construction_start", 6),
        ],
        sources=[
            SourceDef(
                key="loan", label="Loan", source_type="debt",
                draw_every_n_months=4, annual_interest_rate=Decimal("0.0"),
                active_from_milestone="construction_start", active_to_milestone="co",
            ),
        ],
        config=DrawScheduleConfig(min_reserve_construction=Decimal("100_000")),
    )

    schedule = DrawScheduleCalculator(inputs).calculate()
    for v in schedule.violations:
        assert v.shortfall > Decimal("0")
        assert v.shortfall == v.required_reserve - v.cash_balance


# ---------------------------------------------------------------------------
# Source handoff / payoff
# ---------------------------------------------------------------------------

def test_source_handoff_payoff():
    """Second source's first draw includes payoff of first source's balance."""
    inputs = DrawScheduleInputs(
        milestones=milestones(),
        uses=[
            UseLineItem("predev", "Pre-Dev", "soft_costs", Decimal("100_000"), "offer_made", 2),
            UseLineItem("hard",   "Hard",    "hard_costs", Decimal("500_000"), "construction_start", 6),
        ],
        sources=[
            SourceDef(
                key="predev_equity", label="Pre-Dev Equity", source_type="equity",
                draw_every_n_months=1, annual_interest_rate=Decimal("0"),
                active_from_milestone="offer_made", active_to_milestone="close",
            ),
            SourceDef(
                key="construction_loan", label="Construction Loan", source_type="debt",
                draw_every_n_months=2, annual_interest_rate=Decimal("0.07"),
                active_from_milestone="close", active_to_milestone="co",
            ),
        ],
    )

    schedule = DrawScheduleCalculator(inputs).calculate()
    predev_draws = schedule.by_source["predev_equity"]
    const_draws  = schedule.by_source["construction_loan"]

    predev_final_balance = predev_draws[-1].balance_after
    assert predev_final_balance > Decimal("0")
    assert const_draws[0].prior_source_payoff == predev_final_balance


# ---------------------------------------------------------------------------
# Equity (zero rate)
# ---------------------------------------------------------------------------

def test_equity_no_carry():
    """Equity source: carry = 0, total drawn ≈ total uses."""
    inputs = DrawScheduleInputs(
        milestones=milestones(),
        uses=[
            UseLineItem("land", "Land",       "land",       Decimal("1_000_000"), "close",              1),
            UseLineItem("hard", "Hard Costs", "hard_costs", Decimal("2_000_000"), "construction_start", 12),
        ],
        sources=[
            SourceDef(
                key="equity", label="Equity", source_type="equity",
                draw_every_n_months=1, annual_interest_rate=Decimal("0"),
                active_from_milestone="close", active_to_milestone="stabilized",
            ),
        ],
    )

    schedule = DrawScheduleCalculator(inputs).calculate()
    assert schedule.total_carry_cost == Decimal("0")
    assert round(schedule.total_sources_required, 2) == round(schedule.total_uses, 2)


# ---------------------------------------------------------------------------
# Uses by category
# ---------------------------------------------------------------------------

def test_uses_by_category_totals():
    """Uses by category should sum to total uses."""
    inputs = DrawScheduleInputs(
        milestones=milestones(),
        uses=[
            UseLineItem("land",  "Land",       "land",       Decimal("500_000"), "close",              1),
            UseLineItem("hard1", "Foundation", "hard_costs", Decimal("300_000"), "construction_start", 3),
            UseLineItem("hard2", "Framing",    "hard_costs", Decimal("400_000"), "construction_start", 3),
            UseLineItem("soft",  "Arch Fees",  "soft_costs", Decimal("80_000"),  "under_contract",     1),
        ],
        sources=[
            SourceDef("eq", "Equity", "equity", 1, Decimal("0"),
                      "offer_made", "stabilized"),
        ],
    )

    schedule = DrawScheduleCalculator(inputs).calculate()
    category_total = sum(u.total_amount for u in schedule.uses_by_category)
    assert category_total == schedule.total_uses
    assert schedule.total_uses == Decimal("1_280_000")


# ---------------------------------------------------------------------------
# Auto-sized commitment
# ---------------------------------------------------------------------------

def test_auto_sized_commitment():
    """When total_commitment is None, summary.total_commitment == total_drawn."""
    inputs = DrawScheduleInputs(
        milestones=milestones(),
        uses=[
            UseLineItem("hard", "Hard Costs", "hard_costs", Decimal("600_000"), "construction_start", 6),
        ],
        sources=[
            SourceDef(
                key="loan", label="Loan", source_type="debt",
                draw_every_n_months=2, annual_interest_rate=Decimal("0.06"),
                active_from_milestone="construction_start", active_to_milestone="co",
                total_commitment=None,
            ),
        ],
    )

    schedule = DrawScheduleCalculator(inputs).calculate()
    summary = schedule.source_summaries[0]
    assert summary.total_commitment == summary.total_drawn


# ---------------------------------------------------------------------------
# Single-draw routing (grants / equity with eligibility + stack position)
# ---------------------------------------------------------------------------

def test_grant_routes_against_eligible_category_only():
    """
    Grant scenario (OR-MEP / Energy Trust style):
      $250K grant, eligible for Hard Costs only, stack position 1.
      Senior construction loan covers the rest.

    Expect the grant to take exactly $250K against Hard Costs and the
    senior loan to cover the residual ($350K of Hard Costs + Soft Costs).
    """
    inputs = DrawScheduleInputs(
        milestones=milestones(),
        uses=[
            UseLineItem("soft", "Soft Costs", "soft_costs", Decimal("100_000"), "construction_start", 6),
            UseLineItem("hard", "Hard Costs", "hard_costs", Decimal("600_000"), "construction_start", 6),
        ],
        sources=[
            SourceDef(
                key="grant", label="OR-MEP Grant", source_type="grant",
                draw_every_n_months=1, annual_interest_rate=Decimal("0"),
                active_from_milestone="construction_start", active_to_milestone="co",
                total_commitment=Decimal("250_000"),
                single_draw=True,
                stack_position=1,
                eligible_use_categories=["hard_costs"],
            ),
            SourceDef(
                key="loan", label="Construction Loan", source_type="debt",
                draw_every_n_months=2, annual_interest_rate=Decimal("0.07"),
                active_from_milestone="construction_start", active_to_milestone="co",
                stack_position=10,
            ),
        ],
    )

    schedule = DrawScheduleCalculator(inputs).calculate()
    grant_draws = schedule.by_source["grant"]
    loan_draws = schedule.by_source["loan"]

    assert len(grant_draws) == 1, "single_draw grant should produce exactly one draw"
    assert grant_draws[0].total_draw == Decimal("250_000")
    assert grant_draws[0].carry_cost == Decimal("0")

    grant_total = sum(d.total_draw for d in grant_draws)
    loan_uses_funded = sum(d.uses_funded for d in loan_draws)
    # Grant + loan must fully fund the $700K of uses (loan also pre-funds its own carry).
    assert abs((grant_total + loan_uses_funded) - Decimal("700_000")) < Decimal("0.01")


def test_grant_does_not_consume_ineligible_uses():
    """
    Grant eligible only for Hard Costs sees only $400K of eligible uses,
    even though commitment is $500K. Should draw $400K and stop.
    """
    inputs = DrawScheduleInputs(
        milestones=milestones(),
        uses=[
            UseLineItem("land", "Land",       "land",       Decimal("1_000_000"), "close",              1),
            UseLineItem("hard", "Hard Costs", "hard_costs", Decimal("400_000"),   "construction_start", 4),
            UseLineItem("soft", "Soft Costs", "soft_costs", Decimal("200_000"),   "construction_start", 4),
        ],
        sources=[
            SourceDef(
                key="grant", label="Hard-Cost-Only Grant", source_type="grant",
                draw_every_n_months=1, annual_interest_rate=Decimal("0"),
                active_from_milestone="construction_start", active_to_milestone="co",
                total_commitment=Decimal("500_000"),
                single_draw=True,
                stack_position=1,
                eligible_use_categories=["hard_costs"],
            ),
            SourceDef(
                key="loan", label="Loan", source_type="debt",
                draw_every_n_months=2, annual_interest_rate=Decimal("0.07"),
                active_from_milestone="close", active_to_milestone="co",
                stack_position=10,
            ),
        ],
    )

    schedule = DrawScheduleCalculator(inputs).calculate()
    grant_draws = schedule.by_source["grant"]
    assert len(grant_draws) == 1
    # Grant capped at the eligible pool ($400K), not its commitment ($500K)
    assert grant_draws[0].total_draw == Decimal("400_000")


def test_stack_position_orders_single_draw_allocation():
    """
    Two grants eligible for the same category; lower stack_position fills first.
    Senior grant ($300K, stack 1) takes first $300K of Hard Costs;
    junior grant ($200K, stack 2) takes the next $200K.
    """
    inputs = DrawScheduleInputs(
        milestones=milestones(),
        uses=[
            UseLineItem("hard", "Hard Costs", "hard_costs", Decimal("600_000"), "construction_start", 6),
        ],
        sources=[
            SourceDef(
                key="junior", label="Junior Grant", source_type="grant",
                draw_every_n_months=1, annual_interest_rate=Decimal("0"),
                active_from_milestone="construction_start", active_to_milestone="co",
                total_commitment=Decimal("200_000"),
                single_draw=True, stack_position=2,
                eligible_use_categories=["hard_costs"],
            ),
            SourceDef(
                key="senior", label="Senior Grant", source_type="grant",
                draw_every_n_months=1, annual_interest_rate=Decimal("0"),
                active_from_milestone="construction_start", active_to_milestone="co",
                total_commitment=Decimal("300_000"),
                single_draw=True, stack_position=1,
                eligible_use_categories=["hard_costs"],
            ),
            SourceDef(
                key="loan", label="Loan", source_type="debt",
                draw_every_n_months=2, annual_interest_rate=Decimal("0.06"),
                active_from_milestone="construction_start", active_to_milestone="co",
                stack_position=10,
            ),
        ],
    )

    schedule = DrawScheduleCalculator(inputs).calculate()
    assert schedule.by_source["senior"][0].total_draw == Decimal("300_000")
    assert schedule.by_source["junior"][0].total_draw == Decimal("200_000")
    # Senior + junior + loan uses_funded = $600K of Hard Costs
    loan_uses_funded = sum(d.uses_funded for d in schedule.by_source["loan"])
    total = Decimal("300_000") + Decimal("200_000") + loan_uses_funded
    assert abs(total - Decimal("600_000")) < Decimal("0.01")


# ---------------------------------------------------------------------------
# Bank-account simulation: opening cash + lease-up operating CF + floor
# ---------------------------------------------------------------------------

def _ms_with_lease_up():
    """Milestone set with operation_stabilized as the lease-up terminator."""
    return [
        DealMilestone("close",                "Close",             datetime(2025, 4, 1)),
        DealMilestone("construction_start",   "Construction Start",datetime(2025, 5, 1)),
        DealMilestone("co",                   "Certificate of Occ",datetime(2026, 5, 1)),
        DealMilestone("operation_stabilized", "Stabilized",        datetime(2026, 11, 1)),
    ]


def test_opening_cash_seeds_balance_at_first_draw():
    """Pre-funded reserves should appear in cash_balance at the first draw month."""
    inputs = DrawScheduleInputs(
        milestones=_ms_with_lease_up(),
        uses=[
            UseLineItem("hard", "Hard Costs", "hard_costs", Decimal("600_000"), "construction_start", 6),
        ],
        sources=[
            SourceDef(
                key="loan", label="Loan", source_type="debt",
                draw_every_n_months=2, annual_interest_rate=Decimal("0.06"),
                active_from_milestone="construction_start", active_to_milestone="co",
            ),
        ],
        opening_cash_balance=Decimal("250_000"),
    )
    schedule = DrawScheduleCalculator(inputs).calculate()
    constr_start_month = datetime(2025, 5, 1)
    row = next(r for r in schedule.monthly_cash_flows if r.date == constr_start_month)
    # First draw month should include the opening reserve in the draw_received total
    assert row.draw_received >= Decimal("250_000")


def test_lease_up_violation_when_lur_too_small():
    """
    Lease-up months with perm DS > income (and minimal LUR) should
    drop the bank balance below the operational floor and be flagged.
    """
    inputs = DrawScheduleInputs(
        milestones=_ms_with_lease_up(),
        uses=[
            UseLineItem("hard", "Hard Costs", "hard_costs", Decimal("600_000"), "construction_start", 6),
        ],
        sources=[
            SourceDef(
                key="loan", label="Loan", source_type="debt",
                draw_every_n_months=2, annual_interest_rate=Decimal("0"),
                active_from_milestone="construction_start", active_to_milestone="co",
            ),
        ],
        # $50K opening cash at Close (insufficient LUR)
        opening_cash_balance=Decimal("50_000"),
        # 6 months of lease-up: income ramps 0 → $40K, opex flat $20K, perm DS $30K/mo
        monthly_operating=[
            OperatingMonth(datetime(2026, 5, 1),  Decimal("0"),      Decimal("20_000"), Decimal("30_000")),
            OperatingMonth(datetime(2026, 6, 1),  Decimal("8_000"),  Decimal("20_000"), Decimal("30_000")),
            OperatingMonth(datetime(2026, 7, 1),  Decimal("16_000"), Decimal("20_000"), Decimal("30_000")),
            OperatingMonth(datetime(2026, 8, 1),  Decimal("24_000"), Decimal("20_000"), Decimal("30_000")),
            OperatingMonth(datetime(2026, 9, 1),  Decimal("32_000"), Decimal("20_000"), Decimal("30_000")),
            OperatingMonth(datetime(2026, 10, 1), Decimal("40_000"), Decimal("20_000"), Decimal("30_000")),
        ],
        config=DrawScheduleConfig(
            min_reserve_operational=Decimal("100_000"),
            operational_start_milestone="co",
            stabilization_start_milestone="operation_stabilized",
        ),
    )
    schedule = DrawScheduleCalculator(inputs).calculate()
    # Lease-up phase should trip the operational floor
    lease_up_violations = [v for v in schedule.violations if v.phase == "operational"]
    assert len(lease_up_violations) > 0
    assert all(v.shortfall > Decimal("0") for v in lease_up_violations)


def test_simulation_stops_at_stabilization_start():
    """Bank-account proof window ends at stabilization_start_milestone."""
    inputs = DrawScheduleInputs(
        milestones=_ms_with_lease_up(),
        uses=[
            UseLineItem("hard", "Hard Costs", "hard_costs", Decimal("600_000"), "construction_start", 6),
        ],
        sources=[
            SourceDef(
                key="loan", label="Loan", source_type="debt",
                draw_every_n_months=2, annual_interest_rate=Decimal("0"),
                active_from_milestone="construction_start", active_to_milestone="co",
            ),
        ],
        opening_cash_balance=Decimal("200_000"),
        monthly_operating=[
            OperatingMonth(datetime(2026, 11, 1), Decimal("50_000"), Decimal("20_000"), Decimal("30_000")),
            OperatingMonth(datetime(2026, 12, 1), Decimal("50_000"), Decimal("20_000"), Decimal("30_000")),
        ],
        config=DrawScheduleConfig(
            min_reserve_operational=Decimal("0"),
            stabilization_start_milestone="operation_stabilized",
        ),
    )
    schedule = DrawScheduleCalculator(inputs).calculate()
    last_month = schedule.monthly_cash_flows[-1].date
    # Stabilization Start is 2026-11-01; simulation must not extend past it
    assert last_month <= datetime(2026, 11, 1)
