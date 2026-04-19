"""Construction draw schedule engine.

Models Sources as a Gantt of funding periods tied to deal milestones.
Each source draws every N months; each draw auto-sizes to cover:
  1. Uses (costs) falling in that draw window
  2. Carry (interest on cumulative outstanding balance for that period)
     — solved self-referentially so the draw itself is fully funded
  3. Minimum cash reserve floor (construction or operational)

When a source's active period ends, the next source's opening draw
includes the payoff of the prior source's outstanding balance.

Draw self-referential formula (debt sources):
  D = (uses + B × r × n) / (1 - r × n)
  where B = balance before draw, r = monthly rate, n = draw freq months.
  This accounts for carry on the draw amount itself.

After calculating draws, a month-by-month simulation validates that the
cash balance never drops below the configured reserve. Violations are
reported on the DrawSchedule; the schedule is flagged invalid.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal


# ---------------------------------------------------------------------------
# Input dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DealMilestone:
    """A named event on the deal timeline."""
    key: str            # e.g. "offer_made", "close", "co"
    label: str          # display name
    date: datetime      # must be set before passing to calculator


@dataclass
class UseLineItem:
    """A cost item in the Sources & Uses, tied to a milestone."""
    key: str
    label: str
    category: Literal[
        "land", "closing_costs", "hard_costs", "soft_costs",
        "contingency", "fees", "reserves", "other"
    ]
    total_amount: Decimal
    milestone_key: str   # cost is incurred at/after this milestone
    spread_months: int = 1  # fallback: distribute evenly across this many months
    spread_to_date: datetime | None = None  # if set, use day-level spreading from milestone.date to this date


@dataclass
class SourceDef:
    """A funding source with a draw schedule.

    Draws are auto-sized using the self-referential formula so the draw
    fully covers uses + carry (including carry on the draw itself).
    total_commitment=None means auto-calculated from the draw schedule.
    """
    key: str
    label: str
    source_type: Literal["equity", "debt"]
    draw_every_n_months: int            # draw frequency; 1 = monthly
    annual_interest_rate: Decimal       # 0.0 for equity
    active_from_milestone: str          # source activates at this milestone
    active_to_milestone: str            # source is repaid/closed at this milestone
    active_from_offset_days: int = 0    # offset from milestone date (e.g. +30)
    active_to_offset_days: int = 0      # offset from milestone date
    total_commitment: Decimal | None = None  # None = auto-sized


@dataclass
class DrawScheduleConfig:
    """Reserve floors used to validate the cash balance simulation."""
    min_reserve_construction: Decimal = Decimal("0")  # cash floor during construction
    min_reserve_operational: Decimal = Decimal("0")   # cash floor during operations
    # Milestone key that marks the transition from construction to operational
    operational_start_milestone: str = "co"


@dataclass
class DrawScheduleInputs:
    """Full input set for the draw schedule calculator."""
    milestones: list[DealMilestone]     # ordered chronologically
    uses: list[UseLineItem]
    sources: list[SourceDef]            # ordered by start milestone (Gantt order)
    config: DrawScheduleConfig = field(default_factory=DrawScheduleConfig)


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DrawEvent:
    """A single draw from one source."""
    source_key: str
    source_label: str
    draw_number: int                    # 1-based within this source
    draw_date: datetime

    uses_funded: Decimal                # cost Uses covered by this draw
    prior_source_payoff: Decimal        # payoff of the previous source (first draw only)
    carry_cost: Decimal                 # interest on full outstanding balance this period
    total_draw: Decimal                 # = uses_funded + prior_source_payoff + carry_cost

    balance_before: Decimal             # outstanding balance entering this period
    balance_after: Decimal              # balance after this draw


@dataclass
class MonthlyCashFlow:
    """One month in the intra-period cash simulation."""
    date: datetime
    draw_received: Decimal      # draw received this month (at draw dates only)
    uses_paid: Decimal          # costs paid out this month
    interest_paid: Decimal      # interest on outstanding balance
    net: Decimal                # draw_received - uses_paid - interest_paid
    cash_balance: Decimal       # cumulative running balance
    required_reserve: Decimal   # floor that applies this month
    is_violation: bool          # True if cash_balance < required_reserve


@dataclass
class BalanceViolation:
    """A month where cash balance fell below the required reserve."""
    date: datetime
    cash_balance: Decimal
    required_reserve: Decimal
    shortfall: Decimal          # required_reserve - cash_balance
    phase: str                  # "construction" or "operational"


@dataclass
class SourceSummary:
    """Aggregate stats for one source."""
    source_key: str
    source_label: str
    source_type: str
    active_from: datetime
    active_to: datetime
    total_drawn: Decimal
    total_carry_cost: Decimal
    total_commitment: Decimal           # user-set or auto-calculated
    draw_count: int


@dataclass
class UsesSummary:
    """Aggregate by category for the traditional S&U table."""
    category: str
    total_amount: Decimal


@dataclass
class DrawSchedule:
    """Full output of the draw schedule calculator."""
    events: list[DrawEvent]                     # all draws, chronological
    by_source: dict[str, list[DrawEvent]]       # source_key → draws
    monthly_cash_flows: list[MonthlyCashFlow]   # month-by-month simulation
    source_summaries: list[SourceSummary]
    uses_by_category: list[UsesSummary]

    total_uses: Decimal
    total_carry_cost: Decimal
    total_sources_required: Decimal             # total of all draws

    total_equity: Decimal
    total_debt: Decimal

    violations: list[BalanceViolation]          # months below reserve floor
    is_valid: bool                              # True if no violations


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

class DrawScheduleCalculator:
    """Compute draw schedule from milestones, uses, and source definitions."""

    def __init__(self, inputs: DrawScheduleInputs):
        self.inputs = inputs
        self._milestone_map: dict[str, DealMilestone] = {
            m.key: m for m in inputs.milestones
        }

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def calculate(self) -> DrawSchedule:
        # 1. Build monthly Use cash flows (date → amount)
        monthly_uses = self._spread_uses()

        # 2. Determine the initial reserve buffer the first draw must cover.
        #    The construction reserve floor must be funded from the very first draw.
        config = self.inputs.config
        initial_reserve = max(
            config.min_reserve_construction,
            config.min_reserve_operational,
        )

        # 3. For each source, generate draw events
        all_events: list[DrawEvent] = []
        prior_balance = Decimal("0")
        is_first_source = True

        for source in self.inputs.sources:
            # The first source's first draw includes the reserve floor buffer
            reserve_buffer = initial_reserve if is_first_source else Decimal("0")
            source_events, prior_balance = self._calc_source_draws(
                source, monthly_uses, prior_balance, reserve_buffer=reserve_buffer,
            )
            all_events.extend(source_events)
            is_first_source = False

        # 4. Sort chronologically
        all_events.sort(key=lambda e: (e.draw_date, e.source_key))

        # 5. Month-by-month cash simulation + reserve check
        monthly_cash_flows, violations = self._simulate_cash_balance(
            all_events, monthly_uses
        )

        # 6. Aggregate summaries
        return self._build_summary(all_events, monthly_cash_flows, violations)

    # ------------------------------------------------------------------
    # Internal: spread Uses into monthly buckets
    # ------------------------------------------------------------------

    def _spread_uses(self) -> dict[datetime, Decimal]:
        """Return {month_date: amount} mapping all Use line items.

        When spread_to_date is set, uses day-level precision:
          daily_cost = total / total_days
          each month bucket gets daily_cost × days_in_that_month_within_range
        Otherwise falls back to equal monthly amounts via spread_months.
        """
        monthly: dict[datetime, Decimal] = {}
        for use in self.inputs.uses:
            milestone = self._milestone_map.get(use.milestone_key)
            if not milestone:
                continue

            if use.spread_to_date is not None and use.spread_to_date > milestone.date:
                # Day-level spreading across exact date range
                from_dt: datetime = milestone.date
                to_dt: datetime = use.spread_to_date
                total_days = (to_dt - from_dt).days
                if total_days <= 0:
                    total_days = 1
                daily_amount = use.total_amount / Decimal(total_days)

                # Walk month by month, accumulating day-weighted amounts
                cur = from_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                end_month = to_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                while cur <= end_month:
                    days_in_month = calendar.monthrange(cur.year, cur.month)[1]
                    month_end_dt = cur.replace(day=days_in_month)
                    # Clamp to [from_dt, to_dt]
                    range_start = max(cur, from_dt)
                    range_end = min(month_end_dt, to_dt)
                    days_active = max(0, (range_end - range_start).days)
                    if days_active > 0:
                        bucket = cur
                        monthly[bucket] = monthly.get(bucket, Decimal("0")) + daily_amount * Decimal(days_active)
                    # Advance to next month
                    if cur.month == 12:
                        cur = cur.replace(year=cur.year + 1, month=1)
                    else:
                        cur = cur.replace(month=cur.month + 1)
            else:
                # Month-level fallback (lump sum or spread_months-based)
                months = max(1, use.spread_months)
                monthly_amount = use.total_amount / Decimal(months)
                for m in range(months):
                    bucket = _month_start(_add_months(milestone.date, m))
                    monthly[bucket] = monthly.get(bucket, Decimal("0")) + monthly_amount

        return monthly

    # ------------------------------------------------------------------
    # Internal: generate draws for one source
    # ------------------------------------------------------------------

    def _calc_source_draws(
        self,
        source: SourceDef,
        monthly_uses: dict[datetime, Decimal],
        prior_outstanding: Decimal,
        reserve_buffer: Decimal = Decimal("0"),
    ) -> tuple[list[DrawEvent], Decimal]:
        """
        Generate draw events for a source using the self-referential formula.

        For debt: D = (uses + B × r × n) / (1 - r × n)
        This ensures the draw fully covers carry on its own balance.

        reserve_buffer: extra amount added to the first draw to maintain the
        cash reserve floor (only non-zero for the first source).

        Returns (events, ending_balance) — ending balance is passed to next source.
        """
        from_milestone = self._milestone_map.get(source.active_from_milestone)
        to_milestone = self._milestone_map.get(source.active_to_milestone)
        if not from_milestone or not to_milestone:
            return [], prior_outstanding

        start_date = _month_start(from_milestone.date + timedelta(days=source.active_from_offset_days))
        end_date = _month_start(to_milestone.date + timedelta(days=source.active_to_offset_days))
        freq = source.draw_every_n_months
        # Historical data is stored inconsistently — some rows as a fraction
        # (0.065 = 6.5%), some as a percentage (5.0 = 5%).  Normalise by
        # treating any value >= 1 as a percentage and dividing by 100.  Without
        # this guard, a 12% stored-as-12 rate with monthly freq produces
        # monthly_rate*n >= 1 → denominator falls back to 0.0001 and the
        # self-referential draw formula overflows NUMERIC(18,6).
        _rate_raw = Decimal(str(source.annual_interest_rate or 0))
        _rate_frac = (_rate_raw / Decimal("100")) if _rate_raw >= Decimal("1") else _rate_raw
        monthly_rate = _rate_frac / Decimal("12")

        # Generate draw dates at the specified frequency (normalized to 1st of month)
        draw_dates: list[datetime] = []
        d = start_date
        while d <= end_date:
            draw_dates.append(d)
            d = _add_months(d, freq)
        if not draw_dates or draw_dates[-1] < end_date:
            draw_dates.append(end_date)

        events: list[DrawEvent] = []
        balance = Decimal("0")

        for i, draw_date in enumerate(draw_dates):
            draw_number = i + 1

            # Prospective windowing: this draw pre-funds uses from now until
            # just before the next draw. Cash is on hand before uses fall due.
            if i + 1 < len(draw_dates):
                next_draw = draw_dates[i + 1]
            else:
                next_draw = _add_months(end_date, 1)

            uses_in_window = self._uses_in_window(
                monthly_uses, draw_date, next_draw, inclusive_start=True, exclusive_end=True
            )

            # First draw of first source includes the reserve buffer so cash
            # balance stays above the reserve floor from day one.
            if i == 0 and reserve_buffer > 0:
                uses_in_window += reserve_buffer

            payoff = prior_outstanding if i == 0 else Decimal("0")

            # Self-referential draw sizing for debt:
            # D = (uses + payoff + B × r × n) / (1 - r × n)
            # Carry = interest on (prior balance + this draw) for n months.
            # For equity (r=0): D = uses + payoff.
            n = Decimal(freq)
            existing_balance = balance

            if monthly_rate > 0:
                denominator = Decimal("1") - monthly_rate * n
                if denominator <= 0:
                    denominator = Decimal("0.0001")
                total_draw = (uses_in_window + payoff + existing_balance * monthly_rate * n) / denominator
                carry_cost = total_draw * monthly_rate * n
            else:
                carry_cost = Decimal("0")
                total_draw = uses_in_window + payoff

            balance_before = balance
            balance += total_draw

            events.append(DrawEvent(
                source_key=source.key,
                source_label=source.label,
                draw_number=draw_number,
                draw_date=draw_date,
                uses_funded=uses_in_window,
                prior_source_payoff=payoff,
                carry_cost=carry_cost,
                total_draw=total_draw,
                balance_before=balance_before,
                balance_after=balance,
            ))

        return events, balance

    # ------------------------------------------------------------------
    # Internal: month-by-month cash balance simulation
    # ------------------------------------------------------------------

    def _simulate_cash_balance(
        self,
        events: list[DrawEvent],
        monthly_uses: dict[datetime, Decimal],
    ) -> tuple[list[MonthlyCashFlow], list[BalanceViolation]]:
        """
        Simulate cash balance month by month from first milestone to last.

        Draws are received on their draw_date. Uses are paid each month.
        Interest accrues monthly on the cumulative outstanding debt balance.
        Checks balance against construction/operational reserve floors.
        """
        if not self.inputs.milestones:
            return [], []

        config = self.inputs.config
        op_start_milestone = self._milestone_map.get(config.operational_start_milestone)
        op_start_date = _month_start(op_start_milestone.date) if op_start_milestone else datetime.max

        # Index draws by month (already normalized to 1st in _calc_source_draws)
        draws_by_month: dict[datetime, list[DrawEvent]] = {}
        for e in events:
            draws_by_month.setdefault(e.draw_date, []).append(e)

        # Earliest draw date — don't enforce reserve floor before any source is active
        first_draw_date = min(e.draw_date for e in events) if events else datetime.max

        # Determine simulation range (normalized to 1st of month)
        first_date = _month_start(self.inputs.milestones[0].date)
        last_date = _month_start(self.inputs.milestones[-1].date)

        # Build list of all months to simulate
        months: list[datetime] = []
        d = first_date
        while d <= last_date:
            months.append(d)
            d = _add_months(d, 1)

        cash_balance = Decimal("0")
        monthly_flows: list[MonthlyCashFlow] = []
        violations: list[BalanceViolation] = []

        for month in months:
            # Draws received this month (already include pre-funded carry)
            month_draws = draws_by_month.get(month, [])
            draw_received = sum(e.total_draw for e in month_draws)

            # Uses paid this month
            uses_paid = monthly_uses.get(month, Decimal("0"))

            # Interest is capitalized into the loan balance via carry_cost in each draw —
            # it is NOT a separate cash outflow. The self-referential draw formula ensures
            # the draw pre-funds the carry for the entire window.
            interest_paid = Decimal("0")

            net = draw_received - uses_paid
            cash_balance += net

            # Reserve floor — only enforced once the first source starts drawing
            if month < first_draw_date:
                required_reserve = Decimal("0")
                phase = "construction"
            else:
                phase = "operational" if month >= op_start_date else "construction"
                required_reserve = (
                    config.min_reserve_operational if phase == "operational"
                    else config.min_reserve_construction
                )
            is_violation = cash_balance < required_reserve

            flow = MonthlyCashFlow(
                date=month,
                draw_received=draw_received,
                uses_paid=uses_paid,
                interest_paid=interest_paid,
                net=net,
                cash_balance=cash_balance,
                required_reserve=required_reserve,
                is_violation=is_violation,
            )
            monthly_flows.append(flow)

            if is_violation:
                violations.append(BalanceViolation(
                    date=month,
                    cash_balance=cash_balance,
                    required_reserve=required_reserve,
                    shortfall=required_reserve - cash_balance,
                    phase=phase,
                ))

        return monthly_flows, violations

    # ------------------------------------------------------------------
    # Internal: sum Uses in a date window
    # ------------------------------------------------------------------

    def _uses_in_window(
        self,
        monthly_uses: dict[datetime, Decimal],
        window_start: datetime,
        window_end: datetime,
        inclusive_start: bool = True,
        exclusive_end: bool = False,
    ) -> Decimal:
        total = Decimal("0")
        for bucket_date, amount in monthly_uses.items():
            start_ok = bucket_date >= window_start if inclusive_start else bucket_date > window_start
            end_ok = bucket_date < window_end if exclusive_end else bucket_date <= window_end
            if start_ok and end_ok:
                total += amount
        return total

    # ------------------------------------------------------------------
    # Internal: build DrawSchedule summary
    # ------------------------------------------------------------------

    def _build_summary(
        self,
        events: list[DrawEvent],
        monthly_flows: list[MonthlyCashFlow],
        violations: list[BalanceViolation],
    ) -> DrawSchedule:
        by_source: dict[str, list[DrawEvent]] = {}
        for e in events:
            by_source.setdefault(e.source_key, []).append(e)

        source_summaries: list[SourceSummary] = []
        total_equity = Decimal("0")
        total_debt = Decimal("0")

        for source in self.inputs.sources:
            src_events = by_source.get(source.key, [])
            total_drawn = sum(e.total_draw for e in src_events)
            total_carry = sum(e.carry_cost for e in src_events)
            commitment = source.total_commitment if source.total_commitment is not None else total_drawn

            from_m = self._milestone_map.get(source.active_from_milestone)
            to_m = self._milestone_map.get(source.active_to_milestone)

            source_summaries.append(SourceSummary(
                source_key=source.key,
                source_label=source.label,
                source_type=source.source_type,
                active_from=from_m.date if from_m else datetime.min,
                active_to=to_m.date if to_m else datetime.max,
                total_drawn=total_drawn,
                total_carry_cost=total_carry,
                total_commitment=commitment,
                draw_count=len(src_events),
            ))

            if source.source_type == "equity":
                total_equity += total_drawn
            else:
                total_debt += total_drawn

        category_totals: dict[str, Decimal] = {}
        for use in self.inputs.uses:
            category_totals[use.category] = (
                category_totals.get(use.category, Decimal("0")) + use.total_amount
            )
        uses_by_category = [
            UsesSummary(category=cat, total_amount=amt)
            for cat, amt in category_totals.items()
        ]

        total_uses = sum(u.total_amount for u in self.inputs.uses)
        total_carry = sum(e.carry_cost for e in events)
        total_sources = sum(ss.total_drawn for ss in source_summaries)

        return DrawSchedule(
            events=events,
            by_source=by_source,
            monthly_cash_flows=monthly_flows,
            source_summaries=source_summaries,
            uses_by_category=uses_by_category,
            total_uses=total_uses,
            total_carry_cost=total_carry,
            total_sources_required=total_sources,
            total_equity=total_equity,
            total_debt=total_debt,
            violations=violations,
            is_valid=len(violations) == 0,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _month_start(dt: datetime) -> datetime:
    """Normalize a datetime to the 1st of its month (midnight)."""
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_months(dt: datetime, months: int) -> datetime:
    """Add N months to a datetime, clamping to end of month."""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)
