"""Regression guard: cashflow.py must not issue bulk sa_update() against
CapitalModule or CapitalModuleProject.

Background:
    Bulk ``session.execute(sa_update(CapitalModule)...)`` expires the JSONB
    column attrs on every matching ORM-tracked row in the identity map.
    A later sync read (``module.source.get(...)`` inside a list-comp,
    f-string in a diag, etc.) then triggers a lazy refresh — which crosses
    the asyncpg greenlet boundary and raises ``sqlalchemy.exc.MissingGreenlet``,
    surfaced to users as a 500 on ``/compute``.

    The same anti-pattern was previously fixed in ``app/engines/grant_caps.py``
    (commit fe020e1, see ``tests/engines/test_grant_cap_resolution.py``).
    Several copies of the pattern remained in cashflow.py: bridge sizing,
    dscr_capped / dual_constraint / gap_fill writebacks, retired/retirer
    pair writeback, junction-amount sync, and module-amount reconcile.

    All have been converted to ORM dirty tracking — assignment to
    ``module.source = src`` marks the attribute dirty and the next
    ``session.flush()`` writes it.

    This test asserts no regression by scanning the file for the literal
    ``sa_update`` token in code positions. Comments and docstrings naming
    the historical anti-pattern are allowed.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import app.engines.cashflow as cashflow


@pytest.mark.unit
def test_cashflow_does_not_issue_bulk_sa_update() -> None:
    src = Path(cashflow.__file__).read_text(encoding="utf-8")

    code_lines: list[tuple[int, str]] = []
    for lineno, raw in enumerate(src.splitlines(), start=1):
        stripped = raw.lstrip()
        if stripped.startswith("#"):
            continue
        code_lines.append((lineno, raw))

    pattern = re.compile(r"\bsa_update\s*\(")
    offending = [(lineno, line) for lineno, line in code_lines if pattern.search(line)]

    assert not offending, (
        "cashflow.py must not call sa_update(...) — bulk UPDATE expires JSONB "
        "attrs on ORM CapitalModule / CapitalModuleProject rows in the session "
        "identity map and triggers MissingGreenlet on the next sync read. Use "
        "ORM dirty tracking (`module.source = src`) instead. Offending lines:\n"
        + "\n".join(f"  {ln}: {ln_src.rstrip()}" for ln, ln_src in offending)
    )


@pytest.mark.unit
def test_cashflow_does_not_import_sa_update_alias() -> None:
    """The ``update as sa_update`` import was the gateway for the anti-pattern.

    Drop the import too so a stray ``from sqlalchemy import update`` doesn't
    silently re-enable the pattern via a different alias.
    """
    src = Path(cashflow.__file__).read_text(encoding="utf-8")
    assert "update as sa_update" not in src
    # Bare `import update` is also disallowed in this module's import surface.
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("from sqlalchemy") and " update" in stripped:
            assert "update as sa_update" not in stripped
