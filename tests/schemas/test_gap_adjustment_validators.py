"""Validator tests for the Gap Adjustment reserved-label protection.

Confirms the user-facing Create/Update Pydantic schemas reject the three
reserved labels reserved for the slider feature, while still accepting any
other label.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.deal import (
    IncomeStreamCreate,
    IncomeStreamUpdate,
    OperatingExpenseLineCreate,
    OperatingExpenseLineUpdate,
    UseLineCreate,
    UseLineUpdate,
)
from app.schemas.gap_adjustment_names import (
    OPEX_ADJUSTMENT_LABEL,
    PURCHASE_PRICE_ADJUSTMENT_LABEL,
    REVENUE_ADJUSTMENT_LABEL,
    ALL_RESERVED_LABELS,
    is_reserved_label,
)

_PROJECT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


# ---------------------------------------------------------------------------
# is_reserved_label helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,expected",
    [
        (REVENUE_ADJUSTMENT_LABEL, True),
        (OPEX_ADJUSTMENT_LABEL, True),
        (PURCHASE_PRICE_ADJUSTMENT_LABEL, True),
        ("Market Rent", False),
        ("Gap Adjustment", False),  # partial match doesn't collide
        ("gap adjustment — revenue", False),  # case-sensitive
        (" Gap Adjustment — Revenue", False),  # leading whitespace
        ("Gap Adjustment — Revenue ", False),  # trailing whitespace
        ("", False),
        (None, False),
    ],
)
def test_is_reserved_label(label: str | None, expected: bool) -> None:
    assert is_reserved_label(label) is expected


def test_three_reserved_labels_total() -> None:
    assert len(ALL_RESERVED_LABELS) == 3


# ---------------------------------------------------------------------------
# IncomeStream Create/Update — reject reserved labels
# ---------------------------------------------------------------------------


def test_income_stream_create_rejects_revenue_label() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        IncomeStreamCreate(
            project_id=_PROJECT_ID,
            stream_type="residential_rent",
            label=REVENUE_ADJUSTMENT_LABEL,
            unit_count=10,
            amount_per_unit_monthly=Decimal("1500"),
        )


def test_income_stream_create_rejects_opex_label_too() -> None:
    """All three reserved labels are blocked, not just the natural one."""
    with pytest.raises(ValidationError, match="reserved"):
        IncomeStreamCreate(
            project_id=_PROJECT_ID,
            stream_type="residential_rent",
            label=OPEX_ADJUSTMENT_LABEL,
            unit_count=10,
            amount_per_unit_monthly=Decimal("1500"),
        )


def test_income_stream_create_accepts_normal_label() -> None:
    schema = IncomeStreamCreate(
        project_id=_PROJECT_ID,
        stream_type="residential_rent",
        label="12 Residential Units",
        unit_count=12,
        amount_per_unit_monthly=Decimal("1450"),
    )
    assert schema.label == "12 Residential Units"


def test_income_stream_update_rejects_rename_to_revenue_label() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        IncomeStreamUpdate(label=REVENUE_ADJUSTMENT_LABEL)


def test_income_stream_update_accepts_label_unset() -> None:
    """Update without changing label still validates (label=None)."""
    schema = IncomeStreamUpdate(amount_per_unit_monthly=Decimal("1525"))
    assert schema.label is None


# ---------------------------------------------------------------------------
# OperatingExpenseLine Create/Update — reject reserved labels
# ---------------------------------------------------------------------------


def test_opex_line_create_rejects_opex_label() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        OperatingExpenseLineCreate(
            project_id=_PROJECT_ID,
            label=OPEX_ADJUSTMENT_LABEL,
            annual_amount=Decimal("12000"),
        )


def test_opex_line_create_accepts_normal_label() -> None:
    schema = OperatingExpenseLineCreate(
        project_id=_PROJECT_ID,
        label="Property Taxes",
        annual_amount=Decimal("18000"),
    )
    assert schema.label == "Property Taxes"


def test_opex_line_update_rejects_rename_to_opex_label() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        OperatingExpenseLineUpdate(label=OPEX_ADJUSTMENT_LABEL)


# ---------------------------------------------------------------------------
# UseLine Create/Update — reject reserved labels
# ---------------------------------------------------------------------------


def test_use_line_create_rejects_pp_label() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        UseLineCreate(
            label=PURCHASE_PRICE_ADJUSTMENT_LABEL,
            phase="acquisition",
            amount=Decimal("-50000"),
        )


def test_use_line_create_accepts_normal_label() -> None:
    schema = UseLineCreate(
        label="Land Acquisition",
        phase="acquisition",
        amount=Decimal("1200000"),
    )
    assert schema.label == "Land Acquisition"


def test_use_line_update_rejects_rename_to_pp_label() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        UseLineUpdate(label=PURCHASE_PRICE_ADJUSTMENT_LABEL)


def test_use_line_update_allows_negative_amount() -> None:
    """Negative amounts are explicitly supported (slider sets PP adjustment row
    to a negative amount to reduce total Uses)."""
    schema = UseLineUpdate(amount=Decimal("-50000"))
    assert schema.amount == Decimal("-50000")


# ---------------------------------------------------------------------------
# Cross-cutting: every reserved label rejected on every Create schema
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reserved_label", sorted(ALL_RESERVED_LABELS))
def test_every_create_schema_rejects_every_reserved_label(reserved_label: str) -> None:
    """Defense in depth: a reserved label is blocked regardless of which
    schema the user goes through. Prevents a future code path from sneaking
    a phantom-shaped row past validation."""
    with pytest.raises(ValidationError, match="reserved"):
        IncomeStreamCreate(
            project_id=_PROJECT_ID,
            stream_type="residential_rent",
            label=reserved_label,
            unit_count=1,
            amount_fixed_monthly=Decimal("100"),
        )
    with pytest.raises(ValidationError, match="reserved"):
        OperatingExpenseLineCreate(
            project_id=_PROJECT_ID,
            label=reserved_label,
            annual_amount=Decimal("100"),
        )
    with pytest.raises(ValidationError, match="reserved"):
        UseLineCreate(
            label=reserved_label,
            phase="acquisition",
            amount=Decimal("0"),
        )
