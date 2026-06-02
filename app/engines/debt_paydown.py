"""Debt paydown engine — apply voluntary principal paydowns at milestones.

The only current caller is the float-earnings engine
(`app/engines/float_earnings.py`), but the API is intentionally generic so
future paydown sources (e.g., condo-sale proceeds, partner buyouts) can plug
in without rewriting.

Phase A mechanics:
  - A `PaydownEvent` is a (debt_module_id, milestone_id, amount, label) tuple.
  - At the resolved milestone period, the cashflow loop injects a
    `capital_event` line item recording the cash outflow.
  - The target debt module's exit balloon is reduced by the paydown amount.
  - Per-period interest is NOT recomputed in v1 — this slightly overstates
    DS after the paydown. The simplification matches the existing refi-event
    handling at `cashflow.py:744+`. Phase B can revisit.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

ZERO = Decimal("0")
MONEY_PLACES = Decimal("0.000001")


def _q(value: Decimal) -> Decimal:
    return value.quantize(MONEY_PLACES)


@dataclass(frozen=True)
class PaydownEvent:
    """A single voluntary principal paydown to apply at a milestone."""
    debt_module_id: UUID
    milestone_id: UUID
    amount: Decimal
    label: str


def collect_paydown_events(float_results) -> list[PaydownEvent]:
    """Convert float-earnings results into paydown events.

    Drops zero-amount entries and entries whose paydown target FKs were
    cleared by the validation step.
    """
    events: list[PaydownEvent] = []
    for r in float_results:
        if (
            r.paydown_amount <= ZERO
            or r.paydown_debt_module_id is None
            or r.paydown_milestone_id is None
        ):
            continue
        events.append(
            PaydownEvent(
                debt_module_id=r.paydown_debt_module_id,
                milestone_id=r.paydown_milestone_id,
                amount=r.paydown_amount,
                label="Float Paydown",
            )
        )
    return events


def resolve_milestone_period(
    *,
    milestone_id: UUID,
    milestone_map: dict,
    milestone_month_map: dict[str, int],
) -> int | None:
    """Map a milestone UUID to the 0-indexed cashflow month where it fires.

    Returns None when the milestone is missing or its type isn't represented
    in the modeled phase plan. Uses `_build_milestone_month_map()`'s output
    so paydown resolution stays consistent with the rest of the engine's
    milestone → month mechanics.
    """
    ms = milestone_map.get(milestone_id) if milestone_map else None
    if ms is None:
        return None

    ms_type = getattr(ms, "milestone_type", None)
    if ms_type is None:
        return None

    key = str(ms_type).replace("MilestoneType.", "")
    return milestone_month_map.get(key)


def events_at_period(
    *,
    events: list[PaydownEvent],
    period_to_event_idx: dict[int, list[int]],
    period: int,
) -> list[PaydownEvent]:
    """Return paydown events firing at this period (per the pre-computed map).

    `period_to_event_idx` is built once before the per-month loop:
        for i, ev in enumerate(events):
            p = resolve_milestone_period(ev.milestone_id, ...)
            if p is not None:
                period_to_event_idx.setdefault(p, []).append(i)
    """
    indices = period_to_event_idx.get(period, [])
    return [events[i] for i in indices]


def paydown_total_for_debt(
    *,
    events: list[PaydownEvent],
    debt_module_id: UUID,
) -> Decimal:
    """Sum paydowns targeting a given debt module — used to reduce the
    module's exit balloon at the payoff calculation step.
    """
    return _q(
        sum(
            (ev.amount for ev in events if ev.debt_module_id == debt_module_id),
            ZERO,
        )
    )


def label_for_event(
    *,
    event: PaydownEvent,
    capital_modules,
) -> str:
    """Build a display label for the line item: 'Float Paydown — RJ Bond'."""
    target = next(
        (m for m in capital_modules if m.id == event.debt_module_id),
        None,
    )
    target_label = getattr(target, "label", None) or "Debt"
    return f"{event.label} — {target_label}"
