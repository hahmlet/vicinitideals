"""Drift guard: every ORM table must be mentioned in docs/DATA_MODEL.md.

Imports every module under ``app.models`` so ``Base.metadata`` is fully
populated, then asserts each table name appears (as a plain substring) in
``docs/DATA_MODEL.md``. A new table without a doc mention fails here with
a pointer to the Supporting Tables Index (§16), which exists precisely so
small/internal tables have a cheap one-line home.

No DB connection is needed — this only inspects the declarative metadata.
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

DOC = Path(__file__).resolve().parents[2] / "docs" / "DATA_MODEL.md"

# Tables intentionally NOT documented in DATA_MODEL.md. Keep this tiny —
# prefer adding a row to the Supporting Tables Index (§16) instead.
ALLOWLIST: frozenset[str] = frozenset()


def _all_table_names() -> set[str]:
    import app.models as models_pkg
    from app.models.base import Base

    for mod in pkgutil.iter_modules(models_pkg.__path__):
        importlib.import_module(f"app.models.{mod.name}")
    return set(Base.metadata.tables.keys())


def test_every_orm_table_is_documented():
    doc_text = DOC.read_text(encoding="utf-8")
    missing = sorted(
        name
        for name in _all_table_names()
        if name not in ALLOWLIST and name not in doc_text
    )
    assert not missing, (
        "Tables present in Base.metadata but never mentioned in "
        f"docs/DATA_MODEL.md: {missing}. Add a section, or a one-line row "
        "to the Supporting Tables Index (§16). Only allowlist a table here "
        "if it is genuinely internal-only."
    )


def test_allowlist_entries_are_real_tables():
    """A stale allowlist entry (table dropped/renamed) should be pruned."""
    tables = _all_table_names()
    stale = sorted(ALLOWLIST - tables)
    assert not stale, f"Allowlisted names no longer exist in Base.metadata: {stale}"
