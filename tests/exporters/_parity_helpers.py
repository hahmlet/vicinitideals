"""Parity helpers for the investor-export formula conversion.

Each commit in the formula-conversion plan
(``docs/feature-plans/investor-excel-formula-conversion.md``) flips
hard-coded cell values to formulas. To prevent silent regressions the
test suite captures a "before" workbook, then after the conversion
captures an "after" workbook and asserts the *computed* values are
unchanged (within tolerance) — only the cell *type* changes
(``value`` → ``formula``).

This module provides the diff primitive used by those tests.

Two distinct workbook readers are needed:

- ``data_only=False`` — returns the cell as-written. For a value cell
  this is the value; for a formula cell this is the formula string
  starting with ``=``. Used to assert formulas were emitted.
- ``data_only=True`` — returns the *cached* computed value openpyxl
  stored when the workbook was last saved by a formula engine
  (Excel / LibreOffice). For workbooks openpyxl wrote without
  recalc the cached values are stale, so the parity helper here
  compares cell-as-written for value cells, and accepts that
  formula cells need a recalc step (provided separately) before they
  can be value-compared.

The helper is intentionally light: workbook iteration + cell coercion +
tolerance comparison. Nothing here knows about specific sheets or
named ranges.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


# Tolerance for numeric comparison. 0.01 absolute covers Decimal/float
# round-trip noise; 1e-6 relative covers very large values like Total
# Project Cost where 0.01 absolute is meaninglessly tight.
ABSOLUTE_TOLERANCE = 0.01
RELATIVE_TOLERANCE = 1e-6


@dataclass(frozen=True)
class CellLocation:
    """Sheet + 1-based row/col, stringified for human-readable diff output."""

    sheet: str
    row: int
    col: int

    def __str__(self) -> str:
        return f"{self.sheet}!{get_column_letter(self.col)}{self.row}"


@dataclass(frozen=True)
class CellDelta:
    """A single cell whose value differs between two workbook snapshots."""

    location: CellLocation
    before: Any
    after: Any

    def __str__(self) -> str:
        return f"{self.location}: {self.before!r} -> {self.after!r}"


def _coerce(value: Any) -> Any:
    """Normalize a cell value for comparison.

    - ``None`` and ``""`` collapse to ``None`` (both render blank).
    - ``bool`` stays as-is.
    - ``Decimal`` -> ``float`` (openpyxl writes Decimals as floats).
    - Everything else passes through.
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return float(value)
    return value


def _is_formula(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("=")


def _values_match(a: Any, b: Any) -> bool:
    """Compare two coerced cell values with numeric tolerance.

    Strings (incl. formulas) compare exactly. Numerics compare within
    the absolute-OR-relative tolerance defined at module top.
    """
    if a is None and b is None:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if abs(a - b) <= ABSOLUTE_TOLERANCE:
            return True
        denom = max(abs(a), abs(b))
        return denom > 0 and abs(a - b) / denom <= RELATIVE_TOLERANCE
    return a == b


def _iter_cells(blob: bytes, *, data_only: bool):
    """Yield (sheet, row, col, value) for every cell in the workbook.

    Only iterates the populated bounding box per sheet — empty rows
    past ``ws.max_row`` and empty cols past ``ws.max_column`` are
    skipped, which is what openpyxl already does for ``ws.iter_rows``.
    """
    wb = load_workbook(BytesIO(blob), data_only=data_only)
    for sheet in wb.sheetnames:
        ws = wb[sheet]
        for row in ws.iter_rows(values_only=False):
            for cell in row:
                yield sheet, cell.row, cell.column, cell.value


def workbook_cell_map(
    blob: bytes, *, data_only: bool = False
) -> dict[CellLocation, Any]:
    """Build a {CellLocation: coerced value} map for a workbook blob.

    ``data_only=False`` returns formula strings for formula cells;
    ``data_only=True`` returns the cached computed value (or ``None``
    if openpyxl has no cache, which is the common case for workbooks
    written by openpyxl without subsequent recalc).
    """
    return {
        CellLocation(sheet=s, row=r, col=c): _coerce(v)
        for s, r, c, v in _iter_cells(blob, data_only=data_only)
        if _coerce(v) is not None
    }


def diff_workbook_values(
    before_blob: bytes, after_blob: bytes
) -> list[CellDelta]:
    """Return cells whose values differ between two workbook snapshots.

    Compares both in ``data_only=False`` mode (cell-as-written). Diff
    includes:

    - Cells present in ``before`` but missing in ``after`` (or vice versa)
    - Cells whose value/formula changed beyond tolerance

    Order: sorted by sheet, then row, then column for stable test output.
    """
    before = workbook_cell_map(before_blob, data_only=False)
    after = workbook_cell_map(after_blob, data_only=False)

    deltas: list[CellDelta] = []
    all_locations = set(before) | set(after)
    for loc in sorted(all_locations, key=lambda l: (l.sheet, l.row, l.col)):
        b = before.get(loc)
        a = after.get(loc)
        if _values_match(b, a):
            continue
        deltas.append(CellDelta(location=loc, before=b, after=a))
    return deltas


def diff_only_value_cells(
    before_blob: bytes, after_blob: bytes
) -> list[CellDelta]:
    """Diff that ignores cells that became formulas.

    Use this when you've intentionally converted some cells to formulas
    and want to assert *no other cell* changed. A cell that was a value
    in ``before`` and is a formula in ``after`` is skipped (its
    computed value is asserted separately via a recalc-based test).
    """
    deltas = diff_workbook_values(before_blob, after_blob)
    return [d for d in deltas if not _is_formula(d.after)]


def count_formula_cells(blob: bytes) -> dict[str, int]:
    """Count formula cells per sheet. Used to show conversion progress."""
    counts: dict[str, int] = {}
    for sheet, _row, _col, value in _iter_cells(blob, data_only=False):
        if _is_formula(value):
            counts[sheet] = counts.get(sheet, 0) + 1
    return counts
