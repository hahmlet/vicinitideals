"""Float-earnings engine — Treasury yield on Day-1-drawn capital sources.

Models interest income earned on the drawn-but-unspent balance of a parent
capital source that is forced to draw 100% of proceeds on Day 1 of
construction (tax-exempt construction bonds being the canonical case).

Design constraints (per `docs/feature-plans/interest-earned-on-day-1-draws.md`):
  - Earnings DO NOT shrink reserves (IR / OR / LUR / CFSR). This module
    runs strictly after `_auto_size_debt_modules()` and the bank-account
    proof.
  - Earnings route to one or both of (a) developer fee top-up, (b) debt
    principal paydown at a user-chosen milestone. The split is user-set.
  - Phase A ships paydown only — dev fee top-up is forced to 0 in the UI
    until the in-flight developer-fee balance work lands.
  - Compute-time validation surfaces broken preconditions (missing parent,
    parent flipped to `draw_down`, deleted paydown target/milestone) as
    standard compute warnings. No live UI banners.

Conservative assumption: parent balance depletes linearly across the
construction period, matching the `linear` draw-schedule convention used
by the interest-reserve sizer. Earnings flow out of the balance (they
don't compound back into it) because the dollars are routed downstream.
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
    paydown_blocked: bool      # debt/milestone FK broken — zero paydown only
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FloatEarningsResult:
    float_source_id: UUID
    parent_module_id: UUID | None
    total_earnings: Decimal
    paydown_amount: Decimal
    dev_fee_topup_amount: Decimal
    paydown_debt_module_id: UUID | None
    paydown_milestone_id: UUID | None
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

    `paydown_blocked` true only when the user opted into a debt paydown
    split but the target debt module or milestone is missing. Earnings
    still flow to the dev fee top-up share in that case.
    """
    warnings: list[str] = []
    source = float_module.source or {}
    label = float_module.label or "Float Earnings"

    parent_uuid = _coerce_uuid(source.get("parent_module_id"))
    if parent_uuid is None:
        warnings.append(
            f"Float-earnings source '{label}' has no parent — no earnings computed."
        )
        return FloatValidation(earnings_blocked=True, paydown_blocked=True, warnings=warnings)

    parent = next((m for m in capital_modules if m.id == parent_uuid), None)
    if parent is None:
        warnings.append(
            f"Float-earnings source '{label}' references a parent that no longer exists — no earnings computed."
        )
        return FloatValidation(earnings_blocked=True, paydown_blocked=True, warnings=warnings)

    parent_source = parent.source or {}
    if parent_source.get("draw_type") != "fully_drawn":
        warnings.append(
            f"Float-earnings source '{label}' paused: parent '{parent.label}' no longer draws at start."
        )
        return FloatValidation(earnings_blocked=True, paydown_blocked=True, warnings=warnings)

    if not parent_source.get("balance_earns_interest"):
        warnings.append(
            f"Float-earnings source '{label}' paused: parent '{parent.label}' has 'Balance Earns Interest' turned off."
        )
        return FloatValidation(earnings_blocked=True, paydown_blocked=True, warnings=warnings)

    # Paydown FK integrity — only checked when user opted into a paydown split.
    paydown_blocked = False
    debt_split = _coerce_decimal(source.get("debt_paydown_split_pct"))
    if debt_split > ZERO:
        paydown_uuid = _coerce_uuid(source.get("paydown_debt_module_id"))
        if paydown_uuid is None:
            warnings.append(
                f"Float-earnings '{label}': paydown skipped — no debt module selected."
            )
            paydown_blocked = True
        elif not any(m.id == paydown_uuid for m in capital_modules):
            warnings.append(
                f"Float-earnings '{label}': paydown skipped — target debt module deleted."
            )
            paydown_blocked = True

        milestone_uuid = _coerce_uuid(source.get("paydown_milestone_id"))
        if milestone_uuid is None:
            warnings.append(
                f"Float-earnings '{label}': paydown skipped — no milestone selected."
            )
            paydown_blocked = True
        elif not any(ms.id == milestone_uuid for ms in milestones):
            warnings.append(
                f"Float-earnings '{label}': paydown skipped — target milestone deleted."
            )
            paydown_blocked = True

    return FloatValidation(
        earnings_blocked=False,
        paydown_blocked=paydown_blocked,
        warnings=warnings,
    )


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


def split_earnings(
    *,
    total: Decimal,
    dev_fee_split_pct: Decimal,
    debt_paydown_split_pct: Decimal,
) -> tuple[Decimal, Decimal]:
    """Apply the user-entered split. Returns (dev_fee_amount, paydown_amount).

    When neither split is set, defaults to 100% paydown — safest in Phase A
    since dev fee top-up requires balance modeling that hasn't shipped yet.
    """
    dev_pct = max(ZERO, dev_fee_split_pct or ZERO)
    debt_pct = max(ZERO, debt_paydown_split_pct or ZERO)
    total_pct = dev_pct + debt_pct
    if total_pct <= ZERO:
        return ZERO, _q(total)
    dev_amount = _q(total * dev_pct / total_pct)
    paydown_amount = _q(total - dev_amount)
    return dev_amount, paydown_amount


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

    Caller responsibilities:
      - render each result's `warnings` into the standard compute warnings UI
      - feed `paydown_amount` + `paydown_debt_module_id` +
        `paydown_milestone_id` into `app/engines/debt_paydown.apply_paydown()`
      - feed `dev_fee_topup_amount` into the developer-fee balance writer
        (Phase B; ignored in Phase A — defaults force 100% to paydown)

    This function does NOT mutate the inputs.
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
                    paydown_amount=ZERO,
                    dev_fee_topup_amount=ZERO,
                    paydown_debt_module_id=None,
                    paydown_milestone_id=None,
                    schedule=[],
                    warnings=verdict.warnings,
                )
            )
            continue

        parent_uuid = _coerce_uuid(source.get("parent_module_id"))
        parent = next((m for m in capital_modules if m.id == parent_uuid), None)
        # `parent` cannot be None here — validate_float_source would have set earnings_blocked.

        parent_principal = _coerce_decimal((parent.source or {}).get("amount"))
        yield_pct = _coerce_decimal(source.get("yield_pct"))

        total, schedule = compute_balance_schedule(
            parent_principal=parent_principal,
            construction_months=construction_months,
            yield_pct=yield_pct,
        )

        dev_amount, paydown_amount = split_earnings(
            total=total,
            dev_fee_split_pct=_coerce_decimal(source.get("dev_fee_split_pct")),
            debt_paydown_split_pct=_coerce_decimal(source.get("debt_paydown_split_pct")),
        )

        paydown_debt_id = _coerce_uuid(source.get("paydown_debt_module_id"))
        paydown_ms_id = _coerce_uuid(source.get("paydown_milestone_id"))

        if verdict.paydown_blocked:
            paydown_amount = ZERO
            paydown_debt_id = None
            paydown_ms_id = None

        results.append(
            FloatEarningsResult(
                float_source_id=fm.id,
                parent_module_id=parent.id,
                total_earnings=total,
                paydown_amount=paydown_amount,
                dev_fee_topup_amount=dev_amount,
                paydown_debt_module_id=paydown_debt_id,
                paydown_milestone_id=paydown_ms_id,
                schedule=schedule,
                warnings=verdict.warnings,
            )
        )

    return results
