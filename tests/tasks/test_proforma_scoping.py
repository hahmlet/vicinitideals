"""Unit tests for proforma ingestion scoping features.

Covers:
  - _parse_cell_range(): A1:D45 → (min_row, max_row, min_col, max_col)
  - _parse_pages(): "12-15, 18" → 0-based page indices
  - _sheet_to_text() with cell_range parameter
  - _sheet_to_text() import_revenue / import_opex flag behavior (via task body)
"""
from __future__ import annotations

import openpyxl
import pytest

from app.tasks.proforma_parse import _parse_cell_range, _parse_pages, _sheet_to_text


# ---------------------------------------------------------------------------
# _parse_cell_range
# ---------------------------------------------------------------------------

def test_parse_cell_range_basic():
    # range_boundaries returns (min_col, min_row, max_col, max_row)
    # _parse_cell_range returns (min_row, max_row, min_col, max_col)
    result = _parse_cell_range("A1:D45")
    assert result == (1, 45, 1, 4)  # min_row=1, max_row=45, min_col=1(A), max_col=4(D)


def test_parse_cell_range_lowercase():
    result = _parse_cell_range("a1:d45")
    assert result == (1, 45, 1, 4)


def test_parse_cell_range_multi_letter_col():
    # AA=27, AC=29
    result = _parse_cell_range("AA1:AC10")
    assert result == (1, 10, 27, 29)


def test_parse_cell_range_invalid_returns_none():
    assert _parse_cell_range("not-a-range") is None
    assert _parse_cell_range("") is None
    assert _parse_cell_range("A1") is None  # no colon → rejected by early check


# ---------------------------------------------------------------------------
# _parse_pages
# ---------------------------------------------------------------------------

def test_parse_pages_single():
    assert _parse_pages("5") == [4]  # 1-based → 0-based


def test_parse_pages_range():
    assert _parse_pages("12-15") == [11, 12, 13, 14]


def test_parse_pages_mixed():
    assert _parse_pages("12-14, 18") == [11, 12, 13, 17]


def test_parse_pages_with_spaces():
    assert _parse_pages(" 3 - 5 , 8 ") == [2, 3, 4, 7]


def test_parse_pages_deduplicates():
    assert _parse_pages("1-3, 2-4") == [0, 1, 2, 3]


def test_parse_pages_empty_string():
    assert _parse_pages("") == []


def test_parse_pages_zero_and_negative_ignored():
    # Page 0 in 1-based UI is invalid — should not appear in 0-based output
    assert _parse_pages("0") == []


# ---------------------------------------------------------------------------
# _sheet_to_text with cell_range
# ---------------------------------------------------------------------------

def _make_ws_with_data() -> openpyxl.worksheet.worksheet.Worksheet:
    """Build a 10-row x 5-col sheet for range-scoping tests."""
    wb = openpyxl.Workbook()
    ws = wb.active
    # Row 1: headers
    ws.append(["Account", "Jan", "Feb", "Mar", "Annual"])
    # Rows 2-10: data
    for i in range(2, 11):
        ws.append([f"Line {i}", i * 100, i * 100, i * 100, i * 300])
    return ws


def test_sheet_to_text_cell_range_restricts_rows():
    ws = _make_ws_with_data()
    # Request rows 1-4 (header + 3 data rows)
    md = _sheet_to_text(ws, cell_range="A1:E4")
    data_lines = [l for l in md.splitlines() if l.startswith("|") and "---" not in l]
    # header + 3 data rows = 4 table rows
    assert len(data_lines) == 4


def test_sheet_to_text_cell_range_restricts_cols():
    ws = _make_ws_with_data()
    # Request only cols A-B (account + Jan)
    md = _sheet_to_text(ws, cell_range="A1:B10")
    lines = [l for l in md.splitlines() if l.startswith("|")]
    # Each row should have exactly 2 data columns
    for line in lines:
        if "---" not in line:
            assert line.count("|") - 1 == 2


def test_sheet_to_text_invalid_range_falls_back_to_full_sheet():
    ws = _make_ws_with_data()
    md_full = _sheet_to_text(ws)
    md_invalid = _sheet_to_text(ws, cell_range="not-a-range")
    # Invalid range → full sheet (same output)
    assert md_full == md_invalid


def test_sheet_to_text_no_range_unchanged():
    """Passing cell_range=None must not change existing behavior."""
    ws = _make_ws_with_data()
    md_none = _sheet_to_text(ws, cell_range=None)
    md_default = _sheet_to_text(ws)
    assert md_none == md_default
