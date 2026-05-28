"""Unit tests for xlsx ingester enhancements.

Covers:
  - Enhancement 1: _sheet_to_text() detects "Jan - Dec YYYY" as the total column
  - Enhancement 2: CapEx items snap to valid categories and are included as OpEx
"""
from __future__ import annotations

import openpyxl
import pytest

from app.tasks.proforma_parse import (
    _is_debt_or_total,
    _postprocess_expense_lines,
    _sheet_to_text,
    _snap_category,
)


# ---------------------------------------------------------------------------
# Enhancement 1: year-range column header detection
# ---------------------------------------------------------------------------

def _make_ws(headers: list[str], data_row: list) -> openpyxl.worksheet.worksheet.Worksheet:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    ws.append(data_row)
    return ws


def test_sheet_to_text_jan_dec_range_filtered():
    """'Jan - Dec 2025' column should be detected as the total column."""
    months = ["Jan 2025", "Feb 2025", "Mar 2025", "Apr 2025", "May 2025",
              "Jun 2025", "Jul 2025", "Aug 2025", "Sep 2025", "Oct 2025",
              "Nov 2025", "Dec 2025"]
    headers = ["Account"] + months + ["Jan - Dec 2025"]
    data = ["6100 - Insurance"] + [1000] * 12 + [12000]
    ws = _make_ws(headers, data)

    md = _sheet_to_text(ws)

    # Should have narrowed to 2 columns: Account + Jan - Dec 2025
    lines = [l for l in md.splitlines() if l.startswith("|")]
    assert lines, "Expected markdown table rows"
    col_count = lines[0].count("|") - 1
    assert col_count == 2, f"Expected 2 columns after filtering, got {col_count}"
    assert "12,000" in md or "12000" in md


def test_sheet_to_text_ytd_still_detected():
    """Existing 'YTD' header must still be detected (regression guard)."""
    ws = _make_ws(
        ["Account", "Jan 2025", "YTD"],
        ["Insurance", 1000, 12000],
    )
    md = _sheet_to_text(ws)
    lines = [l for l in md.splitlines() if l.startswith("|")]
    col_count = lines[0].count("|") - 1
    assert col_count == 2


def test_sheet_to_text_single_month_not_detected_as_total():
    """'Dec 2025' alone must NOT trigger column filtering (only 3 letters after strip)."""
    ws = _make_ws(
        ["Account", "Dec 2025"],
        ["Insurance", 12000],
    )
    md = _sheet_to_text(ws)
    lines = [l for l in md.splitlines() if l.startswith("|")]
    col_count = lines[0].count("|") - 1
    # No total col found → all columns kept (2)
    assert col_count == 2


def test_sheet_to_text_half_year_range_detected():
    """'Jan - Jun 2025' is also a valid year-range total column."""
    ws = _make_ws(
        ["Account", "Jan 2025", "Feb 2025", "Jan - Jun 2025"],
        ["Insurance", 500, 500, 3000],
    )
    md = _sheet_to_text(ws)
    lines = [l for l in md.splitlines() if l.startswith("|")]
    col_count = lines[0].count("|") - 1
    assert col_count == 2


# ---------------------------------------------------------------------------
# Enhancement 2: CapEx items are valid expense categories, not excluded
# ---------------------------------------------------------------------------

def test_is_debt_or_total_carpets_not_excluded():
    assert _is_debt_or_total("9005 - Carpets / Floors") is False


def test_is_debt_or_total_capital_reserve_not_excluded():
    """Capital Reserve is now a valid CapEx category — must not be excluded."""
    assert _is_debt_or_total("Capital Reserve") is False


def test_is_debt_or_total_replacement_reserve_not_excluded():
    assert _is_debt_or_total("Replacement Reserve") is False


def test_is_debt_or_total_insurance_not_excluded():
    assert _is_debt_or_total("6100 - Insurance") is False


def test_snap_category_turnover_refurbishment():
    """'Turnover Refurbishment' must snap to Unit Turnover via 'turnover' keyword."""
    assert _snap_category("Turnover Refurbishment") == "Unit Turnover"


def test_snap_category_carpets_floors():
    """'Carpets / Floors' must snap to CapEx Reserve via 'carpet' keyword."""
    assert _snap_category("9005 - Carpets / Floors") == "CapEx Reserve"


def test_snap_category_capital_reserve():
    """'Capital Reserve' must snap to CapEx Reserve."""
    assert _snap_category("Capital Reserve") == "CapEx Reserve"


def test_snap_category_replacement_reserve():
    assert _snap_category("Replacement Reserve") == "CapEx Reserve"


def test_postprocess_snapped_category_forces_is_opex_true():
    """If snap succeeds, is_operating_expense must be True even if LLM said False."""
    lines = [
        {
            "original_label": "Turnover Refurbishment",
            "mapped_category": "Unit Turnover",
            "is_operating_expense": False,
            "annual_amount": 5000,
            "confidence": 0.9,
        },
        {
            "original_label": "Carpets / Floors",
            "mapped_category": "CapEx Reserve",
            "is_operating_expense": False,
            "annual_amount": 3000,
            "confidence": 0.8,
        },
    ]
    result = _postprocess_expense_lines(lines)
    assert len(result) == 2
    assert all(r["is_operating_expense"] is True for r in result)


def test_postprocess_debt_service_stays_excluded():
    """Debt service items that don't snap must remain is_operating_expense=False."""
    lines = [
        {
            "original_label": "Mortgage Interest",
            "mapped_category": None,
            "is_operating_expense": False,
            "annual_amount": 50000,
            "confidence": 0.9,
        },
    ]
    result = _postprocess_expense_lines(lines)
    assert len(result) == 1
    assert result[0]["is_operating_expense"] is False
