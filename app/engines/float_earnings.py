"""Float-earnings engine — Treasury yield on Day-1-drawn capital sources.

Models interest income earned on the drawn-but-unspent balance of a parent
capital source that is forced to draw 100% of proceeds on Day 1 of
construction (tax-exempt construction bonds being the canonical case).

Design constraints:
  - Earnings DO NOT shrink reserves (IR / OR / LUR / CFSR). This module
    runs strictly after `_auto_size_debt_modules()` and the bank-account
    proof.
  - All earnings route to the GP/LP profit waterfall as a lump sum at the
    user-chosen waterfall milestone. The waterfall distributes them through
    its normal tier order (debt service → DDF → residual equity split).
  - Compute-time validation surfaces broken preconditions (missing parent,
    parent flipped to `draw_down`) as standard compute warnings.

Conservative assumption: parent balance depletes linearly across the
construction period, matching the `linear` draw-schedule convention used
by the interest-reserve sizer. Earnings flow out of the balance (they
don't compound back into it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

ZERO = Decimal("0")
MONEY_PLACES = Decimal("0.000001")
HUNDRED = Decimal("100")
MONTHS_PER_YEAR = Decimal("12")


def _q(value: Decimal) -> Decimal:
    return value.quantize(MONEY_PLACES)


def _coerce_decimal(value: object) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return ZERO


def _coerce_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def _vehicle_type_of(module) -> str:
    """Strip any "VehicleType." prefix that legacy code may have written."""
    return (module.vehicle_type or "").replace("VehicleType.", "")


@dataclass(frozen=True)
class FloatBalanceRow:
    period: int                # 1-indexed construction month
    opening_balance: Decimal
    monthly_earnings: Decimal
    closing_balance: Decimal


@dataclass(frozen=True)
class FloatValidation:
    earnings_blocked: bool     # parent missing or wrong-state — zero earnings
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FloatEarningsResult:
    float_source_id: UUID
    parent_module_id: UUID | None
    total_earnings: Decimal
    waterfall_milestone_id: UUID | None   # period when earnings hit the waterfall
    schedule: list[FloatBalanceRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------

def validate_float_source(
    *,
    float_module,
    capital_modules,
    milestones,
) -> FloatValidation:
    """Check every precondition; return a structured verdict.

    `earnings_blocked` true when the parent reference is missing or the
    parent is no longer in a state that produces float (draw_type flipped
    away from `fully_drawn`, or `balance_earns_interest` toggled off).
    """
    warnings: list[str] = []
    source = float_module.source or {}
    label = float_module.label or "Float Earnings"

    parent_uuid = _coerce_uuid(source.get("parent_module_id"))
    if parent_uuid is None:
        warnings.append(
            f"Float-earnings source '{label}' has no parent — no earnings computed."
        )
        return FloatValidation(earnings_blocked=True, warnings=warnings)

    parent = next((m for m in capital_modules if m.id == parent_uuid), None)
    if parent is None:
        warnings.append(
            f"Float-earnings source '{label}' references a parent that no longer exists — no earnings computed."
        )
        return FloatValidation(earnings_blocked=True, warnings=warnings)

    parent_source = parent.source or {}
    if parent_source.get("draw_type") != "fully_drawn":
        warnings.append(
            f"Float-earnings source '{label}' paused: parent '{parent.label}' no longer draws at start."
        )
        return FloatValidation(earnings_blocked=True, warnings=warnings)

    if not parent_source.get("balance_earns_interest"):
        warnings.append(
            f"Float-earnings source '{label}' paused: parent '{parent.label}' has 'Balance Earns Interest' turned off."
        )
        return FloatValidation(earnings_blocked=True, warnings=warnings)

    return FloatValidation(earnings_blocked=False, warnings=warnings)


# ----------------------------------------------------------------------------
# Math
# ----------------------------------------------------------------------------

def compute_balance_schedule(
    *,
    parent_principal: Decimal,
    construction_months: int,
    yield_pct: Decimal,
) -> tuple[Decimal, list[FloatBalanceRow]]:
    """Closed-form linear-depletion earnings model.

    For a parent source with principal P drawn day 1, construction over N
    months, and annual yield y%:

        balance(t)   = P × (1 - t/N)              for t in 0..N
        earnings(t)  = balance(t-1) × y/100/12    for t in 1..N
        total        = P × y/100/12 × (N+1)/2

    Returns (total_earnings, period_schedule).
    """
    if parent_principal <= ZERO or construction_months <= 0 or yield_pct <= ZERO:
        return ZERO, []

    monthly_rate = yield_pct / HUNDRED / MONTHS_PER_YEAR
    n = Decimal(construction_months)
    monthly_spend = parent_principal / n

    schedule: list[FloatBalanceRow] = []
    total_earnings = ZERO
    balance = parent_principal

    for t in range(1, construction_months + 1):
        opening = balance
        earnings = _q(opening * monthly_rate)
        balance = opening - monthly_spend
        schedule.append(
            FloatBalanceRow(
                period=t,
                opening_balance=_q(opening),
                monthly_earnings=earnings,
                closing_balance=_q(balance if balance > ZERO else ZERO),
            )
        )
        total_earnings += earnings

    return _q(total_earnings), schedule


# ----------------------------------------------------------------------------
# Top-level entry point
# ----------------------------------------------------------------------------

def compute_scenario_float_earnings(
    *,
    capital_modules,
    milestones,
    construction_months: int,
) -> list[FloatEarningsResult]:
    """Compute float-earnings for every `vehicle_type == "float_earnings"`
    source in the scenario.

    All earnings route to the GP/LP profit waterfall as a lump sum at the
    `waterfall_milestone_id` period. The waterfall distributes them through
    its normal tier order.
    """
    results: list[FloatEarningsResult] = []

    float_modules = [m for m in capital_modules if _vehicle_type_of(m) == "float_earnings"]
    for fm in float_modules:
        source = fm.source or {}
        verdict = validate_float_source(
            float_module=fm,
            capital_modules=capital_modules,
            milestones=milestones,
        )

        if verdict.earnings_blocked:
            results.append(
                FloatEarningsResult(
                    float_source_id=fm.id,
                    parent_module_id=None,
                    total_earnings=ZERO,
                    waterfall_milestone_id=None,
                    schedule=[],
                    warnings=verdict.warnings,
                )
            )
            continue

        parent_uuid = _coerce_uuid(source.get("parent_module_id"))
        parent = next((m for m in capital_modules if m.id == parent_uuid), None)

        parent_principal = _coerce_decimal((parent.source or {}).get("amount"))
        yield_pct = _coerce_decimal(source.get("yield_pct"))

        total, schedule = compute_balance_schedule(
            parent_principal=parent_principal,
            construction_months=construction_months,
            yield_pct=yield_pct,
        )

        # Support legacy key `paydown_milestone_id` for backward compat with
        # existing source JSONB rows written before this simplification.
        waterfall_ms_id = _coerce_uuid(
            source.get("waterfall_milestone_id") or source.get("paydown_milestone_id")
        )

        results.append(
            FloatEarningsResult(
                float_source_id=fm.id,
                parent_module_id=parent.id,
                total_earnings=total,
                waterfall_milestone_id=waterfall_ms_id,
                schedule=schedule,
                warnings=verdict.warnings,
            )
        )

    return results
