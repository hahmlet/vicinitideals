"""Deferred Developer Fee balance schedule (Phase B float-earnings).

The multi-source Developer Fee engine (``app/engines/dev_fee.py``) computes
``funded_at_close`` vs ``deferred`` per scenario at close. Phase B tracks
the deferred portion period-by-period as it gets paid down post-close
from two sources:

1. **Waterfall residual** — operating cash that reaches the
   ``deferred_developer_fee`` tier in the CF waterfall.
2. **Float-earnings topup** — at a float-earnings source's
   ``paydown_milestone_id``, the source's ``dev_fee_topup_amount`` (set
   by the user-entered split on the float source) reduces the balance
   directly.

Both reduce the same outstanding balance; neither accrues interest
(matches LIHTC deferred-Dev-Fee norm). When the balance hits zero,
remaining paydown attempts are no-ops and excess is left in the
waterfall for downstream tiers (equity residual).

Pure functions — no DB access, no session. Caller assembles inputs from
the dev_fee binding context, the float earnings results, and the
waterfall distribution pass, then writes the result onto
``OperationalOutputs.dev_fee_balance_series``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable


_MONEY_PLACES = Decimal("0.000001")
ZERO = Decimal("0")


def _q(value: Decimal | int | float | str) -> Decimal:
    """Quantize to the engine money precision."""
    return Decimal(str(value)).quantize(_MONEY_PLACES)


@dataclass(frozen=True)
class DeferredBalanceRow:
    """One period in the deferred Dev Fee balance schedule."""

    period: int
    opening_balance: Decimal
    paydown_from_waterfall: Decimal
    paydown_from_float_topup: Decimal
    closing_balance: Decimal

    @property
    def paydown_total(self) -> Decimal:
        return self.paydown_from_waterfall + self.paydown_from_float_topup


@dataclass(frozen=True)
class DeferredBalanceResult:
    """Full Phase B deferred Dev Fee schedule for a scenario."""

    opening_at_close: Decimal
    rows: tuple[DeferredBalanceRow, ...]
    fully_paid_period: int | None  # None if balance never reached zero

    def total_paid(self) -> Decimal:
        return sum((r.paydown_total for r in self.rows), ZERO)

    def remaining_at_horizon(self) -> Decimal:
        return self.rows[-1].closing_balance if self.rows else self.opening_at_close


def compute_deferred_balance_schedule(
    *,
    deferred_at_close: Decimal,
    period_count: int,
    waterfall_paydowns_by_period: dict[int, Decimal] | None = None,
    float_topups_by_period: dict[int, Decimal] | None = None,
) -> DeferredBalanceResult:
    """Build the period-by-period deferred Dev Fee balance schedule.

    Args:
        deferred_at_close: Outstanding balance at the start of period 1
            (taken from the auto Dev Fee row's
            ``dev_fee_binding_context["deferred"]``).
        period_count: Number of periods (months) to simulate. Typically the
            scenario's full operating-phase horizon; rows continue to be
            emitted past ``fully_paid_period`` with zero activity so the
            UI can render a flat tail.
        waterfall_paydowns_by_period: Period → amount routed to deferred
            Dev Fee by the ``deferred_developer_fee`` waterfall tier.
            Caller has already capped these at the available cash; this
            helper additionally caps at the running balance.
        float_topups_by_period: Period → amount applied from a
            float-earnings source's ``dev_fee_topup_amount`` at its
            paydown milestone. Same balance-capping applies.

    Returns:
        ``DeferredBalanceResult`` with one row per period and the period
        in which the balance first reached zero (or None if the horizon
        ended with balance > 0).

    Invariants:
        - ``opening_balance`` of period N+1 equals ``closing_balance`` of
          period N.
        - Neither paydown source can drive ``closing_balance`` below zero
          (excess is silently truncated; caller is responsible for routing
          the unused dollars elsewhere — e.g. back to the waterfall for
          the next tier).
        - Both sources may pay in the same period; their combined effect
          is still capped at the opening balance.
    """
    waterfall_paydowns_by_period = waterfall_paydowns_by_period or {}
    float_topups_by_period = float_topups_by_period or {}

    opening = _q(deferred_at_close) if deferred_at_close else ZERO
    if opening <= ZERO or period_count <= 0:
        return DeferredBalanceResult(
            opening_at_close=opening,
            rows=tuple(),
            fully_paid_period=None,
        )

    balance = opening
    rows: list[DeferredBalanceRow] = []
    fully_paid: int | None = None

    for period in range(1, period_count + 1):
        period_open = balance
        wf_attempt = _q(waterfall_paydowns_by_period.get(period, ZERO))
        ft_attempt = _q(float_topups_by_period.get(period, ZERO))

        # Cap the combined paydown at the opening balance. Float topup
        # gets priority — it's a discrete event the user explicitly
        # scheduled — and the waterfall takes whatever the balance has
        # room for after.
        if ft_attempt > period_open:
            ft_applied = period_open
            wf_applied = ZERO
        else:
            ft_applied = ft_attempt
            remaining_room = period_open - ft_applied
            wf_applied = wf_attempt if wf_attempt <= remaining_room else remaining_room

        balance = period_open - ft_applied - wf_applied
        if balance < ZERO:
            balance = ZERO

        rows.append(
            DeferredBalanceRow(
                period=period,
                opening_balance=period_open,
                paydown_from_waterfall=wf_applied,
                paydown_from_float_topup=ft_applied,
                closing_balance=balance,
            )
        )

        if fully_paid is None and balance == ZERO and period_open > ZERO:
            fully_paid = period

    return DeferredBalanceResult(
        opening_at_close=opening,
        rows=tuple(rows),
        fully_paid_period=fully_paid,
    )


def serialize_balance_result(result: DeferredBalanceResult) -> dict:
    """Convert the dataclass result into the JSONB shape persisted on
    ``OperationalOutputs.dev_fee_balance_series``.

    Returns None-equivalent (empty dict signal handled by caller) when the
    result carries no balance — caller passes None to the column instead.
    """
    return {
        "opening_at_close": str(result.opening_at_close),
        "fully_paid_period": result.fully_paid_period,
        "total_paid": str(result.total_paid()),
        "remaining_at_horizon": str(result.remaining_at_horizon()),
        "periods": [
            {
                "period": r.period,
                "opening_balance": str(r.opening_balance),
                "paydown_from_waterfall": str(r.paydown_from_waterfall),
                "paydown_from_float_topup": str(r.paydown_from_float_topup),
                "closing_balance": str(r.closing_balance),
            }
            for r in result.rows
        ],
    }


def float_topups_by_milestone(
    *,
    float_results: Iterable,
    milestone_to_period: dict,
) -> dict[int, Decimal]:
    """Aggregate per-float-source ``dev_fee_topup_amount`` into a
    period-keyed dict the balance schedule consumes.

    Args:
        float_results: iterable of ``FloatEarningsResult`` instances
            from ``compute_scenario_float_earnings``.
        milestone_to_period: mapping from milestone UUID → period number,
            built by the caller from the same lookup the debt_paydown
            module uses.

    Sources whose ``paydown_milestone_id`` doesn't resolve to a period
    (deleted milestone, etc.) are silently skipped — the float-earnings
    validation step already surfaced a warning for the user.
    """
    out: dict[int, Decimal] = {}
    for fr in float_results:
        topup = _q(getattr(fr, "dev_fee_topup_amount", ZERO) or ZERO)
        if topup <= ZERO:
            continue
        ms_id = getattr(fr, "paydown_milestone_id", None)
        if ms_id is None:
            continue
        period = milestone_to_period.get(ms_id)
        if period is None:
            continue
        out[period] = out.get(period, ZERO) + topup
    return out
