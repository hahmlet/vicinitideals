"""Bank-account simulator (pure, stateless).

Models the bank-account balance month-by-month over an arbitrary window.
Designed for the reserve-proof check: confirm that pre-funded reserves
plus draws plus operating income are enough to keep the balance at or
above the configured floor through Stabilization Start.

The simulator is intentionally I/O-free: callers (cashflow.py, the draw-
schedule UI handler, future workflows) assemble already-computed monthly
streams and pass them in as plain {month: Decimal} maps. No coupling to
SourceDef / UseLineItem / CashFlow ORM rows — this lets the same module
serve every consumer without baking in any one engine's debt model.

Sign convention:
  inflows  — positive numbers; draws, operating income, capital injections
  outflows — positive numbers; uses, opex, debt service
The simulator does the subtraction.

Floor:
  Single floor value, evaluated every month. Caller decides the per-month
  floor (construction reserve vs operational reserve) and passes it as a
  dict {month: floor_amount}.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class BankAccountMonth:
    """One month of the bank-account simulation."""
    date: datetime
    inflow: Decimal
    outflow: Decimal
    net: Decimal
    balance: Decimal
    floor: Decimal
    shortfall: Decimal  # max(0, floor - balance)


@dataclass
class BankAccountReport:
    """Full simulation output."""
    monthly: list[BankAccountMonth] = field(default_factory=list)
    opening_cash: Decimal = Decimal("0")
    min_balance: Decimal = Decimal("0")
    min_balance_date: datetime | None = None
    # Max shortfall across the window — the additional reserve the engine
    # would need to seed at Close to keep the balance at-or-above floor
    # through every simulated month. >0 means the proof failed; the gap
    # IS the Cash Flow Support Reserve amount.
    max_shortfall: Decimal = Decimal("0")
    max_shortfall_date: datetime | None = None
    is_solvent: bool = True  # max_shortfall == 0


def simulate(
    *,
    months: list[datetime],
    opening_cash: Decimal,
    monthly_inflows: dict[datetime, Decimal] | None = None,
    monthly_outflows: dict[datetime, Decimal] | None = None,
    monthly_floor: dict[datetime, Decimal] | None = None,
) -> BankAccountReport:
    """Run a month-by-month bank-account simulation.

    months : ordered list of month-start dates covering the proof window.
    opening_cash : balance at the start of months[0] (pre-funded reserves
        + any seed capital that arrived before the window).
    monthly_inflows / monthly_outflows : dicts keyed by month-start date.
        Missing months default to 0.
    monthly_floor : per-month required reserve floor. Missing months
        default to 0.

    Returns a BankAccountReport with the running balance, the deepest
    shortfall, and a flag that's True iff balance >= floor for every
    month. max_shortfall is the gap the caller would need to plug.
    """
    inflows = monthly_inflows or {}
    outflows = monthly_outflows or {}
    floors = monthly_floor or {}

    balance = opening_cash
    rows: list[BankAccountMonth] = []
    min_balance = opening_cash
    min_balance_date: datetime | None = months[0] if months else None
    max_shortfall = Decimal("0")
    max_shortfall_date: datetime | None = None

    for m in months:
        inflow = inflows.get(m, Decimal("0"))
        outflow = outflows.get(m, Decimal("0"))
        floor = floors.get(m, Decimal("0"))
        net = inflow - outflow
        balance += net
        shortfall = max(Decimal("0"), floor - balance)

        rows.append(BankAccountMonth(
            date=m,
            inflow=inflow,
            outflow=outflow,
            net=net,
            balance=balance,
            floor=floor,
            shortfall=shortfall,
        ))

        if balance < min_balance:
            min_balance = balance
            min_balance_date = m
        if shortfall > max_shortfall:
            max_shortfall = shortfall
            max_shortfall_date = m

    return BankAccountReport(
        monthly=rows,
        opening_cash=opening_cash,
        min_balance=min_balance,
        min_balance_date=min_balance_date,
        max_shortfall=max_shortfall,
        max_shortfall_date=max_shortfall_date,
        is_solvent=(max_shortfall == 0),
    )


__all__ = ["BankAccountMonth", "BankAccountReport", "simulate"]
