"""Tests for the bank-account simulator."""

from datetime import datetime
from decimal import Decimal

from app.engines.bank_account import simulate


def _months(start: datetime, count: int) -> list[datetime]:
    out: list[datetime] = []
    cur = start
    for _ in range(count):
        out.append(cur)
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return out


def test_zero_activity_balance_stays_at_opening():
    months = _months(datetime(2026, 1, 1), 6)
    r = simulate(months=months, opening_cash=Decimal("100_000"))
    assert r.is_solvent
    assert r.min_balance == Decimal("100_000")
    assert r.max_shortfall == Decimal("0")
    assert all(row.balance == Decimal("100_000") for row in r.monthly)


def test_inflows_and_outflows_net_correctly():
    months = _months(datetime(2026, 1, 1), 3)
    inflows = {months[0]: Decimal("50_000"), months[2]: Decimal("20_000")}
    outflows = {months[1]: Decimal("30_000")}
    r = simulate(
        months=months,
        opening_cash=Decimal("0"),
        monthly_inflows=inflows,
        monthly_outflows=outflows,
    )
    assert r.monthly[0].balance == Decimal("50_000")
    assert r.monthly[1].balance == Decimal("20_000")
    assert r.monthly[2].balance == Decimal("40_000")
    assert r.is_solvent


def test_floor_violation_surfaces_max_shortfall():
    months = _months(datetime(2026, 1, 1), 3)
    outflows = {months[1]: Decimal("80_000")}
    floors = {m: Decimal("50_000") for m in months}
    r = simulate(
        months=months,
        opening_cash=Decimal("100_000"),
        monthly_outflows=outflows,
        monthly_floor=floors,
    )
    # After month 2: balance = 100k - 80k = 20k; floor = 50k → shortfall 30k
    assert not r.is_solvent
    assert r.max_shortfall == Decimal("30_000")
    assert r.max_shortfall_date == months[1]
    assert r.min_balance == Decimal("20_000")


def test_max_shortfall_picks_deepest_not_first():
    months = _months(datetime(2026, 1, 1), 4)
    outflows = {months[0]: Decimal("40_000"), months[2]: Decimal("70_000")}
    floors = {m: Decimal("50_000") for m in months}
    r = simulate(
        months=months,
        opening_cash=Decimal("100_000"),
        monthly_outflows=outflows,
        monthly_floor=floors,
    )
    # Month 0: 60k (no shortfall). Month 2: -10k (shortfall 60k) — deepest.
    assert r.max_shortfall == Decimal("60_000")
    assert r.max_shortfall_date == months[2]


def test_solvent_when_inflows_keep_balance_above_floor():
    months = _months(datetime(2026, 1, 1), 6)
    # Operating: $40K income / $20K opex / $30K perm DS — net -$10K/mo
    inflows = {m: Decimal("40_000") for m in months}
    outflows = {m: Decimal("50_000") for m in months}
    floors = {m: Decimal("30_000") for m in months}
    r = simulate(
        months=months,
        opening_cash=Decimal("100_000"),
        monthly_inflows=inflows,
        monthly_outflows=outflows,
        monthly_floor=floors,
    )
    # 100 → 90 → 80 → 70 → 60 → 50 → 40 — always above 30K floor
    assert r.is_solvent
    assert r.min_balance == Decimal("40_000")


def test_empty_months_returns_safe_report():
    r = simulate(months=[], opening_cash=Decimal("0"))
    assert r.monthly == []
    assert r.is_solvent
    assert r.max_shortfall == Decimal("0")
