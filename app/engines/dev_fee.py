"""Auto Developer Fee recompute.

The Developer Fee Use Line is auto-seeded on every new deal (see
app/api/routers/ui.py deal-create). Its `amount` is recomputed every engine
pass from `dev_fee_pct * basis`:

- basis = "purchase_price"  → pct * inputs.purchase_price
- basis = "tpc_excl_self"   → pct * sum(other use_lines.amount)

Must run BEFORE `_auto_size_debt_modules` so debt sizing reads the updated
Uses total. Mutates the in-memory UseLine and writes the new amount to the
DB so subsequent reads (UI, exports, downstream compute) see the same value.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import OperationalInputs, UseLine

ZERO = Decimal("0")
_MONEY_PLACES = Decimal("0.01")


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return ZERO
    try:
        return Decimal(str(value))
    except Exception:
        return ZERO


def _resolve_purchase_price(
    inputs: OperationalInputs | None,
    use_lines: Iterable[UseLine],
) -> Decimal:
    """Prefer OperationalInputs.purchase_price; fall back to acquisition-phase Uses."""
    if inputs is not None:
        pp = _to_decimal(inputs.purchase_price)
        if pp > ZERO:
            return pp
    total = ZERO
    for u in use_lines:
        if u.is_auto_dev_fee:
            continue
        # Match the UI seed: phase=acquisition AND cost_category=acquisition
        phase_val = getattr(u.phase, "value", u.phase)
        if str(phase_val) == "acquisition" and (u.cost_category or "") == "acquisition":
            total += _to_decimal(u.amount)
    return total


async def recompute_auto_dev_fee(
    use_lines: list[UseLine],
    inputs: OperationalInputs | None,
    session: AsyncSession,
) -> None:
    """Recompute the auto Dev Fee UseLine `amount` for one project.

    No-op if no auto Dev Fee row exists or its pct is null/zero.
    """
    auto_line = next((u for u in use_lines if getattr(u, "is_auto_dev_fee", False)), None)
    if auto_line is None:
        return

    pct_raw = getattr(auto_line, "dev_fee_pct", None)
    if pct_raw is None:
        return
    pct = _to_decimal(pct_raw) / Decimal("100")

    basis = getattr(auto_line, "dev_fee_basis", None) or "tpc_excl_self"
    if basis == "purchase_price":
        base = _resolve_purchase_price(inputs, use_lines)
    else:  # tpc_excl_self
        base = sum(
            (_to_decimal(u.amount) for u in use_lines if not u.is_auto_dev_fee),
            ZERO,
        )

    new_amount = (pct * base).quantize(_MONEY_PLACES)
    current = _to_decimal(auto_line.amount)
    if new_amount != current:
        auto_line.amount = new_amount
        await session.flush()
