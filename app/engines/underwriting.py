"""Deterministic multifamily underwriting engine.

Core calculations:
  - Cashflow generation (month-by-month, phase-based)
  - Debt service, amortization, DSCR
  - Investor pref/promote waterfalls
  - IRR, MOIC, NOI, IRR sensitivity

All calcs are auditable, unit-testable, and disconnected from the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional

from pyxirr import xirr


class Phase(str, Enum):
    """Cashflow phases (timeline)."""
    acquisition = "acquisition"
    pre_construction = "pre_construction"
    construction = "construction"
    renovation = "renovation"
    lease_up = "lease_up"
    stabilized = "stabilized"
    exit = "exit"


@dataclass
class DealInputs:
    """Validated deal inputs."""
    # Sources
    purchase_price: Decimal
    closing_costs_pct: Decimal  # e.g., 0.018 = 1.8%
    hard_costs: Decimal
    soft_costs: Decimal
    contingency: Decimal
    debt_amount: Decimal
    equity_amount: Decimal

    # Uses & timing
    renovation_months: int
    lease_up_months: int
    hold_period_years: int

    # Operations
    unit_count: int
    opex_per_unit_annual: Decimal  # Simplified; in prod would be itemized
    opex_growth_rate_pct: Decimal  # e.g., 0.03 = 3%

    # Revenue (simplified; prod = itemized income streams)
    revenue_per_unit_monthly: Decimal  # Blended stabilized rent + ancillary
    revenue_growth_rate_pct: Decimal
    initial_occupancy_pct: Decimal  # Post-lease-up occupancy
    stable_occupancy_pct: Decimal

    # Debt terms
    debt_interest_rate_pct: Decimal  # Annual (e.g., 0.055 = 5.5%)
    debt_amortization_years: int
    debt_dscr_minimum: Decimal  # e.g., 1.25

    # Exit
    exit_cap_rate_pct: Decimal
    selling_costs_pct: Decimal  # e.g., 0.025 = 2.5%

    # Dates
    close_date: datetime
    construction_start: datetime
    lease_up_start: datetime
    stabilized_start: datetime
    exit_date: datetime

    # Equity return preferences (for waterfall)
    preferred_return_pct: Decimal = Decimal("0.0")  # Pref return to LP
    gp_promote_pct_after_pref: Decimal = Decimal("0.0")  # GP carry after pref is met

    def validate(self) -> list[str]:
        """Return validation warnings/errors."""
        errors = []

        # Check timeline
        if self.construction_start < self.close_date:
            errors.append("construction_start must be >= close_date")
        if self.lease_up_start < self.construction_start:
            errors.append("lease_up_start must be >= construction_start")
        if self.stabilized_start < self.lease_up_start:
            errors.append("stabilized_start must be >= lease_up_start")
        if self.exit_date < self.stabilized_start:
            errors.append("exit_date must be >= stabilized_start")

        return errors


@dataclass
class CashFlowPeriod:
    """One month of cashflow detail."""
    period_num: int
    date: datetime
    phase: Phase

    # Revenue
    gross_revenue: Decimal = Decimal("0")
    vacancy_loss: Decimal = Decimal("0")
    effective_revenue: Decimal = Decimal("0")

    # Expenses
    operating_expenses: Decimal = Decimal("0")
    capex_reserve: Decimal = Decimal("0")

    # NOI
    noi: Decimal = Decimal("0")

    # Debt
    debt_outstanding: Decimal = Decimal("0")
    debt_service_pi: Decimal = Decimal("0")
    debt_service_interest: Decimal = Decimal("0")
    debt_service_principal: Decimal = Decimal("0")

    # Cash
    cash_after_ops: Decimal = Decimal("0")
    net_cash_flow: Decimal = Decimal("0")
    cumulative_cash_flow: Decimal = Decimal("0")

    # Metrics for period
    dscr_for_period: Optional[Decimal] = None


@dataclass
class DealSummary:
    """Deal-level KPIs."""
    irr_equity: Decimal  # Equity IRR
    moic_equity: Decimal  # Equity MOIC (multiple on invested capital)

    equity_invested: Decimal
    equity_returned: Decimal

    noi_yr1_stabilized: Decimal
    noi_yr1_average: Decimal

    dscr_average: Decimal
    dscr_minimum: Decimal

    ltc_max: Decimal  # Max loan-to-cost
    ltvv_exit: Decimal  # Loan-to-value at exit

    total_project_cost: Decimal
    sale_proceeds: Decimal
    profit: Decimal

    validation_passed: bool = True
    validation_issues: list[str] = field(default_factory=list)


class CashFlowCalculator:
    """Generates month-by-month cashflow from deal inputs."""

    def __init__(self, deal: DealInputs):
        self.deal = deal
        self.periods: list[CashFlowPeriod] = []
        self.validation_issues = deal.validate()

    def calculate(self) -> list[CashFlowPeriod]:
        """Generate all cashflow periods from close to exit."""
        if self.validation_issues:
            raise ValueError(f"Deal validation failed: {self.validation_issues}")

        periods = []

        # Generate all months from close to exit
        current_date = self.deal.close_date
        period_num = 0
        debt_balance = self.deal.debt_amount
        cumulative_cf = Decimal("0")

        while current_date <= self.deal.exit_date:
            period_num += 1

            # Determine phase
            phase = self._phase_for_date(current_date)

            # Revenue
            gross_rev, vacancy, eff_rev = self._calc_revenue(
                current_date, period_num
            )

            # OpEx
            opex = self._calc_opex(current_date, period_num)
            capex_reserve = self._calc_capex_reserve(current_date)

            # NOI
            noi = eff_rev - opex - capex_reserve

            # Debt service
            debt_pi, debt_int, debt_prin, debt_balance = self._calc_debt_service(
                debt_balance
            )

            # Cash flow
            cash_after_ops = noi - debt_pi
            cumulative_cf += cash_after_ops

            # Build period
            period = CashFlowPeriod(
                period_num=period_num,
                date=current_date,
                phase=phase,
                gross_revenue=gross_rev,
                vacancy_loss=vacancy,
                effective_revenue=eff_rev,
                operating_expenses=opex,
                capex_reserve=capex_reserve,
                noi=noi,
                debt_outstanding=debt_balance,
                debt_service_pi=debt_pi,
                debt_service_interest=debt_int,
                debt_service_principal=debt_prin,
                cash_after_ops=cash_after_ops,
                net_cash_flow=cash_after_ops,
                cumulative_cash_flow=cumulative_cf,
                dscr_for_period=(
                    noi / debt_pi if debt_pi > 0 else None
                ),
            )

            periods.append(period)
            current_date += timedelta(days=30)  # Simplify: 30-day months

        self.periods = periods
        return periods

    def _phase_for_date(self, date: datetime) -> Phase:
        """Determine cashflow phase for a given date."""
        if date < self.deal.construction_start:
            return Phase.acquisition
        elif date < self.deal.lease_up_start:
            return Phase.construction
        elif date < self.deal.stabilized_start:
            return Phase.lease_up
        elif date < self.deal.exit_date:
            return Phase.stabilized
        else:
            return Phase.exit

    def _calc_revenue(
        self, date: datetime, period_num: int
    ) -> tuple[Decimal, Decimal, Decimal]:
        """Calculate gross revenue and occupancy loss for a month."""
        phase = self._phase_for_date(date)

        if phase in (Phase.acquisition, Phase.construction, Phase.pre_construction):
            return Decimal("0"), Decimal("0"), Decimal("0")

        # Ramp occupancy during lease-up
        if phase == Phase.lease_up:
            months_into_lease_up = (
                date - self.deal.lease_up_start
            ).days // 30
            occupancy = min(
                self.deal.initial_occupancy_pct
                + (months_into_lease_up * Decimal("0.02")),  # Ramp 2%/month
                self.deal.stable_occupancy_pct,
            )
        else:
            occupancy = self.deal.stable_occupancy_pct

        # Apply annual escalation for years past stabilized
        years_past_stable = max(
            Decimal("0"),
            Decimal((date - self.deal.stabilized_start).days / 365),
        )
        monthly_base = (
            self.deal.revenue_per_unit_monthly
            * Decimal(self.deal.unit_count)
        )
        escalation_factor = (
            (Decimal("1") + self.deal.revenue_growth_rate_pct)
            ** years_past_stable
        )
        gross_rev = monthly_base * escalation_factor

        vacancy_loss = gross_rev * (Decimal("1") - occupancy)
        eff_rev = gross_rev - vacancy_loss

        return gross_rev, vacancy_loss, eff_rev

    def _calc_opex(self, date: datetime, period_num: int) -> Decimal:
        """Calculate monthly OpEx."""
        phase = self._phase_for_date(date)

        if phase in (Phase.acquisition, Phase.construction, Phase.pre_construction):
            return Decimal("0")

        # Annual escalation
        years_past_stable = max(
            Decimal("0"),
            Decimal((date - self.deal.stabilized_start).days / 365),
        )
        monthly_opex = (
            self.deal.opex_per_unit_annual
            / 12
            * Decimal(self.deal.unit_count)
        )
        escalation = (
            (Decimal("1") + self.deal.opex_growth_rate_pct)
            ** years_past_stable
        )

        return monthly_opex * escalation

    def _calc_capex_reserve(self, date: datetime) -> Decimal:
        """Calculate monthly CapEx reserve (typically $0 in ops, accumulated for future)."""
        # Simplified: no ongoing capex reserve. In prod, add per-unit reserve.
        return Decimal("0")

    def _calc_debt_service(
        self, debt_balance: Decimal
    ) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """Calculate monthly P&I debt service and return new balance."""
        if debt_balance <= 0:
            return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")

        monthly_rate = self.deal.debt_interest_rate_pct / 12
        num_payments = self.deal.debt_amortization_years * 12

        # Monthly P&I (standard amortization)
        monthly_pi = float(debt_balance) * (
            float(monthly_rate)
            * (1 + float(monthly_rate)) ** num_payments
            / (
                (1 + float(monthly_rate)) ** num_payments - 1
            )
        )

        interest = float(debt_balance) * float(monthly_rate)
        principal = monthly_pi - interest
        new_balance = float(debt_balance) - principal

        return (
            Decimal(str(monthly_pi)),
            Decimal(str(interest)),
            Decimal(str(principal)),
            Decimal(str(max(0, new_balance))),  # Can't go negative
        )


class WaterfallCalculator:
    """Calculates investor waterfall distributions (pref + promote)."""

    @staticmethod
    def calculate_waterfall(
        equity_invested: Decimal,
        total_proceeds: Decimal,
        preferred_return_pct: Decimal,
        gp_promote_pct: Decimal,
        hold_years: int,
    ) -> dict:
        """
        Distribute proceeds through LP pref → GP promote → residual split.

        Returns:
          {
            "lp_pref_return": Decimal,
            "remaining_after_pref": Decimal,
            "gp_promote_amount": Decimal,
            "residual": Decimal,
            "lp_total": Decimal,
            "gp_total": Decimal,
            "lp_moic": Decimal,
          }
        """
        # LP preferred return (accrues annually)
        pref_owed = equity_invested * (
            (Decimal("1") + preferred_return_pct) ** hold_years - Decimal("1")
        )

        lp_pref_dist = min(pref_owed, total_proceeds)
        remaining = max(Decimal("0"), total_proceeds - lp_pref_dist)

        # GP promote on remaining (e.g., 20% carry)
        gp_promote = remaining * gp_promote_pct
        residual = remaining - gp_promote

        # Split residual 50/50 (typical; customize as needed)
        lp_residual = residual / 2
        gp_residual = residual / 2

        lp_total = lp_pref_dist + lp_residual
        gp_total = gp_promote + gp_residual

        moic = lp_total / equity_invested if equity_invested > 0 else Decimal("0")

        return {
            "lp_pref_return": lp_pref_dist,
            "remaining_after_pref": remaining,
            "gp_promote_amount": gp_promote,
            "residual": residual,
            "lp_total": lp_total,
            "gp_total": gp_total,
            "lp_moic": moic,
        }


class MetricsCalculator:
    """Compute deal-level metrics (IRR, MOIC, DSCR, LTC, etc.)."""

    @staticmethod
    def calculate_equity_irr(
        equity_invested: Decimal,
        periods: list[CashFlowPeriod],
        waterfall: dict,
    ) -> Decimal:
        """Calculate equity IRR using xirr."""
        # Build cashflow array: xirr expects (date, amount) tuples
        # Start with equity investment (negative outflow)
        cashflows = [(periods[0].date, -float(equity_invested))]

        # Collect all monthly equity cash flows
        total_distributions = Decimal("0")
        for period in periods:
            # Distribute any positive cash flow to equity (after debt service)
            if period.net_cash_flow > 0:
                cashflows.append((period.date, float(period.net_cash_flow)))
                total_distributions += period.net_cash_flow

        # Final return at exit (waterfall distributions)
        # Only add if it's different from what we already collected
        if len(cashflows) > 1:
            final_return = max(
                float(waterfall["lp_total"]) - float(total_distributions),
                Decimal("0")
            )
            if final_return > 0:
                cashflows.append((periods[-1].date, final_return))
        else:
            # No interim distributions, just return proceeds at exit
            cashflows.append((periods[-1].date, float(waterfall["lp_total"])))

        try:
            if len(cashflows) > 1:
                # Check that we have both positive and negative flows
                has_positive = any(cf[1] > 0 for cf in cashflows)
                has_negative = any(cf[1] < 0 for cf in cashflows)

                if has_positive and has_negative:
                    irr = xirr(cashflows)
                    return Decimal(str(irr))
                else:
                    # Can't compute IRR without both inflows and outflows
                    return Decimal("0")
            else:
                return Decimal("0")
        except (ValueError, ZeroDivisionError, TypeError):
            return Decimal("0")

    @staticmethod
    def calculate_dscr(periods: list[CashFlowPeriod]) -> tuple[Decimal, Decimal]:
        """Return (average DSCR, minimum DSCR) for stabilized years."""
        dscrs = [
            p.dscr_for_period
            for p in periods
            if p.phase == Phase.stabilized and p.dscr_for_period
        ]

        if not dscrs:
            return Decimal("0"), Decimal("0")

        avg_dscr = sum(dscrs) / len(dscrs)
        min_dscr = min(dscrs)

        return avg_dscr, min_dscr

    @staticmethod
    def calculate_ltc(
        debt: Decimal, 
        purchase_price: Decimal,
        hard_costs: Decimal, 
        soft_costs: Decimal, 
        contingency: Decimal
    ) -> Decimal:
        """Loan-to-cost ratio (debt / total project cost)."""
        total_costs = purchase_price + hard_costs + soft_costs + contingency
        return debt / total_costs if total_costs > 0 else Decimal("0")


class UnderwritingEngine:
    """Orchestrates all calculations for a deal."""

    def __init__(self, deal: DealInputs):
        self.deal = deal
        self.cf_calculator = CashFlowCalculator(deal)

    def evaluate(self) -> DealSummary:
        """Run full financial analysis and return summary."""
        # Generate cashflows
        periods = self.cf_calculator.calculate()

        # Waterfall distributions
        total_proceeds = sum(p.net_cash_flow for p in periods[-12:] if len(periods) >= 12) if len(periods) >= 12 else Decimal("0")
        # Add final sale proceeds based on stabilized NOI
        stable_periods = [p for p in periods if p.phase == Phase.stabilized]
        noi_stable_avg = sum(p.noi for p in stable_periods) / len(stable_periods) if stable_periods else Decimal("0")
        
        if noi_stable_avg > 0:
            sale_price = noi_stable_avg / self.deal.exit_cap_rate_pct
            selling_costs = sale_price * self.deal.selling_costs_pct
            sale_proceeds = sale_price - selling_costs - self.deal.debt_amount
            total_proceeds += sale_proceeds
        
        waterfall = WaterfallCalculator.calculate_waterfall(
            equity_invested=self.deal.equity_amount,
            total_proceeds=total_proceeds,
            preferred_return_pct=self.deal.preferred_return_pct,
            gp_promote_pct=self.deal.gp_promote_pct_after_pref,
            hold_years=self.deal.hold_period_years,
        )

        # Key metrics
        equity_irr = MetricsCalculator.calculate_equity_irr(
            self.deal.equity_amount, periods, waterfall
        )

        dscr_avg, dscr_min = MetricsCalculator.calculate_dscr(periods)

        total_cost = (
            self.deal.purchase_price
            + Decimal(self.deal.purchase_price) * self.deal.closing_costs_pct
            + self.deal.hard_costs
            + self.deal.soft_costs
            + self.deal.contingency
        )

        ltc = MetricsCalculator.calculate_ltc(
            self.deal.debt_amount,
            self.deal.purchase_price,
            self.deal.hard_costs,
            self.deal.soft_costs,
            self.deal.contingency,
        )

        # Validation
        validation_issues = []
        if dscr_min < self.deal.debt_dscr_minimum and dscr_min > 0:
            validation_issues.append(
                f"DSCR minimum {dscr_min:.2f} < required {self.deal.debt_dscr_minimum:.2f}"
            )
        if ltc > Decimal("0.75"):  # Common threshold
            validation_issues.append(
                f"LTC {ltc:.2%} exceeds 75% threshold"
            )

        return DealSummary(
            irr_equity=equity_irr,
            moic_equity=waterfall["lp_moic"],
            equity_invested=self.deal.equity_amount,
            equity_returned=waterfall["lp_total"],
            noi_yr1_stabilized=periods[-1].noi if periods else Decimal("0"),
            noi_yr1_average=noi_stable_avg,
            dscr_average=dscr_avg,
            dscr_minimum=dscr_min,
            ltc_max=ltc,
            ltvv_exit=self.deal.debt_amount / noi_stable_avg / self.deal.exit_cap_rate_pct if noi_stable_avg > 0 else Decimal("0"),
            total_project_cost=total_cost,
            sale_proceeds=total_proceeds,
            profit=waterfall["lp_total"] - self.deal.equity_amount,
            validation_passed=len(validation_issues) == 0,
            validation_issues=validation_issues,
        )
