"""Schema-tolerance tests for proforma OpEx parser.

Local LLM (Ollama qwen2.5) occasionally returns malformed JSON:
  - confidence as bool instead of float
  - missing is_operating_expense
  - annual_amount = null
The schema must coerce/default these rather than fail validation, otherwise
the whole parse fails after 3 retries and the user sees no OpEx.
"""
from __future__ import annotations

import pytest

from app.tasks.proforma_parse import (
    ExpenseLineResult,
    ParsedExpenses,
    UnitTypeResult,
    _snap_category,
    _postprocess_expense_lines,
)


def test_expense_line_coerces_bool_confidence():
    line = ExpenseLineResult.model_validate(
        {"original_label": "Insurance", "annual_amount": 12500, "confidence": True, "is_operating_expense": True}
    )
    assert line.confidence == 1.0


def test_expense_line_defaults_missing_is_operating_expense():
    line = ExpenseLineResult.model_validate(
        {"original_label": "Office/Admin", "annual_amount": 12000, "confidence": 1.0}
    )
    assert line.is_operating_expense is True


def test_expense_line_null_amount_defaults_to_zero():
    line = ExpenseLineResult.model_validate(
        {"original_label": "Administrative", "annual_amount": None, "confidence": 0.0, "is_operating_expense": True}
    )
    assert line.annual_amount == 0.0


def test_parsed_expenses_full_failing_payload_now_validates():
    payload = {
        "expense_lines": [
            {"original_label": "Administrative", "annual_amount": None, "confidence": False, "is_operating_expense": True},
            {"original_label": "Insurance", "annual_amount": 12500, "confidence": True, "is_operating_expense": True},
            {"original_label": "Office/Admin", "annual_amount": 12000, "confidence": True},
        ]
    }
    parsed = ParsedExpenses.model_validate(payload)
    assert len(parsed.expense_lines) == 3
    assert parsed.expense_lines[0].annual_amount == 0.0
    assert parsed.expense_lines[1].confidence == 1.0
    assert parsed.expense_lines[2].is_operating_expense is True


def test_postprocess_drops_zero_amount_rows():
    raw = [
        {"original_label": "Administrative", "annual_amount": 0, "confidence": 0.0, "is_operating_expense": True},
        {"original_label": "Insurance", "annual_amount": 12500, "confidence": 1.0, "is_operating_expense": True},
    ]
    out = _postprocess_expense_lines(raw)
    assert len(out) == 1
    assert out[0]["original_label"] == "Insurance"


def test_unit_type_coerces_string_count():
    ut = UnitTypeResult.model_validate(
        {"name": "2x1", "count": "5", "avg_sqft": "880", "avg_monthly_rent": "1403", "confidence": True}
    )
    assert ut.count == 5
    assert ut.avg_sqft == 880.0
    assert ut.confidence == 1.0


@pytest.mark.parametrize(
    ("raw_label", "expected_category"),
    [
        ("Internet service", "Telephone / Internet"),
        ("Telephone lines", "Telephone / Internet"),
        ("Accounting", "Accounting"),
        ("Bookkeeping", "Accounting"),
        ("Replacement Reserve", "CapEx Reserve"),
        ("CapEx", "CapEx Reserve"),
        ("Utilities", "Utilities — All"),
    ],
)
def test_snap_category_maps_new_standard_opex_keywords(raw_label: str, expected_category: str):
    assert _snap_category(raw_label) == expected_category
