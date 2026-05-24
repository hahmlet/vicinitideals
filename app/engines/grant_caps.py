"""
grant_caps.py — Resolve grant/forgivable_loan/tax_credit "maximum" caps
to actual `source.amount` based on per-Use eligibility.

Behavior (Phase H+, May 2026):
  - Grant with no eligibility set: `source.amount` is the user-entered
    fixed contribution. Legacy path, no change.
  - Grant with `source.maximum` AND at least one Use whose
    `eligible_module_ids` contains this grant's ID:
        source.amount = min(maximum, sum of eligible Use remaining buckets)
    The grant consumes against eligible Uses in priority order
    (stack_position ascending), so two grants on the same Use cannot
    both claim the same dollars.

Consumption order within a single grant:
    1. Use start period ascending
    2. Use amount descending (ties broken largest first)

Active From / Active To are also derived from the eligible Use set so
the UI / draw schedule reflect grant timing automatically:
    active_phase_start = earliest eligible Use phase
    active_phase_end   = latest eligible Use phase covered by cap

The helper is called from `compute_cash_flows` BEFORE
`_auto_size_debt_modules`, so the gap-fill solver sees the correct
grant contribution.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import update as sa_update

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


ZERO = Decimal("0")


# Phase ordering for UseLine.phase strings. Lower rank = earlier in deal.
# Kept independent of cashflow_compile._PERIOD_TYPE_RANK because UseLine.phase
# uses the user-facing string set, not the engine PeriodType enum.
_USE_PHASE_RANK = {
    "pre_construction": 0,
    "acquisition": 1,
    "other": 1,
    "construction": 2,
    "renovation": 2,
    "conversion": 2,
    "operation": 3,
    "operation_lease_up": 3,
    "lease_up": 3,
    "operation_stabilized": 4,
    "stabilized": 4,
    "exit": 99,
}


def _use_phase_rank(use_line: Any) -> int:
    """Best-effort rank for a UseLine's start phase."""
    p = getattr(use_line, "phase", None)
    s = str(getattr(p, "value", p) or "").replace("UseLinePhase.", "")
    return _USE_PHASE_RANK.get(s, 50)


def _to_decimal(v: Any) -> Decimal:
    if v is None or v == "":
        return ZERO
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _grant_has_cap(module: Any) -> bool:
    src = module.source or {}
    if src.get("auto_size"):
        return False
    return src.get("maximum") is not None


def _eligible_uses_for_grant(grant: Any, use_lines: list[Any]) -> list[Any]:
    grant_id_str = str(grant.id)
    out = []
    for ul in use_lines:
        eligible = getattr(ul, "eligible_module_ids", None) or []
        if any(str(x) == grant_id_str for x in eligible):
            out.append(ul)
    return out


async def resolve_grant_caps(
    capital_modules: list[Any],
    use_lines: list[Any],
    session: "AsyncSession",
) -> None:
    """Mutate `source.amount`, `active_phase_start`, `active_phase_end`
    on every grant whose `source.maximum` is set AND at least one Use
    references it via `eligible_module_ids`.

    Tracks a per-Use remaining bucket so multiple grants on the same Use
    consume in stack_position order without double-counting.

    Persists changes via flush to DB; in-memory ORM objects are mutated
    so the gap-fill solver sees correct values immediately.
    """
    # Lazy import to avoid circular import with cashflow.py
    from app.models.capital import CapitalModule

    # Per-Use remaining bucket = full Use amount (engine has not yet
    # consumed anything in this compute pass).
    remaining: dict[Any, Decimal] = {
        ul.id: _to_decimal(getattr(ul, "amount", 0)) for ul in use_lines
    }

    grants = [m for m in capital_modules if _grant_has_cap(m)]
    grants.sort(key=lambda m: int(getattr(m, "stack_position", 0) or 0))

    for grant in grants:
        src = dict(grant.source or {})
        cap = _to_decimal(src.get("maximum"))

        eligible_uses = _eligible_uses_for_grant(grant, use_lines)
        if not eligible_uses or cap <= ZERO:
            # Cap with no eligibility selected → treat as 0 contribution.
            # UI prevents this state; engine defends.
            src["amount"] = ZERO
            grant.source = src
            await session.execute(
                sa_update(CapitalModule)
                .where(CapitalModule.id == grant.id)
                .values(source=src)
            )
            continue

        # Order: phase rank asc, amount desc (largest first within same phase)
        eligible_uses.sort(
            key=lambda u: (_use_phase_rank(u), -_to_decimal(getattr(u, "amount", 0)))
        )

        consumed = ZERO
        covered_uses: list[Any] = []
        for u in eligible_uses:
            if consumed >= cap:
                break
            avail = remaining.get(u.id, ZERO)
            if avail <= ZERO:
                continue
            take = min(avail, cap - consumed)
            remaining[u.id] = avail - take
            consumed += take
            covered_uses.append(u)

        src["amount"] = consumed

        # Active From/To derived from covered Uses (subset of eligible Uses
        # actually consumed by this grant under its cap).
        if covered_uses:
            covered_sorted = sorted(covered_uses, key=_use_phase_rank)
            first_phase = str(getattr(
                covered_sorted[0].phase, "value", covered_sorted[0].phase
            ) or "").replace("UseLinePhase.", "")
            last_phase = str(getattr(
                covered_sorted[-1].phase, "value", covered_sorted[-1].phase
            ) or "").replace("UseLinePhase.", "")
            if first_phase:
                grant.active_phase_start = first_phase
            if last_phase:
                grant.active_phase_end = last_phase

        grant.source = src
        await session.execute(
            sa_update(CapitalModule)
            .where(CapitalModule.id == grant.id)
            .values(
                source=src,
                active_phase_start=grant.active_phase_start,
                active_phase_end=grant.active_phase_end,
            )
        )

    await session.flush()


def grant_is_under_utilized(module: Any) -> bool:
    """True when source.maximum is set AND source.amount < source.maximum.

    Used by S&U table renderer to flag yellow rows. Pure read-only helper
    safe to call outside engine context.
    """
    src = module.source or {}
    maximum = src.get("maximum")
    if maximum is None:
        return False
    amount = src.get("amount") or 0
    try:
        return Decimal(str(amount)) < Decimal(str(maximum))
    except (TypeError, ValueError):
        return False
