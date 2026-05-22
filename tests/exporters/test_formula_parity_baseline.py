"""Baseline parity tests for the investor-export formula conversion.

Commit 0 of the formula-conversion plan
(``docs/feature-plans/investor-excel-formula-conversion.md``). Locks
in two invariants the subsequent formula-conversion commits will lean
on:

1. **Determinism.** Exporting the same seeded scenario twice produces
   workbooks whose value+formula maps are identical. If this breaks
   (e.g. a sheet builder starts writing ``datetime.now()`` into a
   non-cover cell), every parity assertion downstream becomes
   unreliable.

2. **Today's formula footprint is tiny.** Hyperlink formulas on Cover
   and per-project sheets, plus the ``proforma`` profile's combined
   sheet, are the only formula cells today. We pin the upper bound so
   the next commits' formula additions are visible against the
   baseline.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.exporters.investor_export import export_investor_workbook
from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)
from tests.exporters._parity_helpers import (
    count_formula_cells,
    diff_workbook_values,
)


async def _seed_minimal_scenario(session: AsyncSession):
    """Reuses the seeder pattern from tests/exporters/test_investor_export.py."""
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(
        session, org, user, name="Formula-Parity Smoke"
    )
    deal_model, _, _, _ = await seed_deal_model_with_financials(
        session, opportunity, user
    )
    return deal_model


async def test_export_is_deterministic(session: AsyncSession):
    """Same seed -> two identical workbook value maps after warm-up.

    The *first* export against a freshly seeded scenario triggers the
    cashflow / waterfall engines and persists their outputs. So a naive
    ``export -> export -> diff`` shows real differences caused by the
    first call's side effects, not by export non-determinism.

    Protocol: discard the first export blob, then compare the second
    and third. If these still differ outside the Cover snapshot-date
    cell, a sheet builder is writing time-varying data (e.g.
    ``datetime.now()``) into a non-Cover cell. The conversion plan's
    parity tests can't distinguish "real change" from "wall-clock
    noise" if determinism leaks past Cover.
    """
    scenario = await _seed_minimal_scenario(session)
    # Warm-up — discard blob, engine outputs are now persisted.
    await export_investor_workbook(scenario.id, session)
    blob_a = await export_investor_workbook(scenario.id, session)
    blob_b = await export_investor_workbook(scenario.id, session)

    deltas = diff_workbook_values(blob_a, blob_b)

    # Cover sheet's snapshot-date cell embeds ``datetime.now()`` and is
    # allowed to vary across calls. Cell layout: row 2, col 2 by current
    # Cover builder; widen the allowance to "any string-typed Cover cell
    # whose value changed" to survive minor Cover refactors.
    non_snapshot = [
        d for d in deltas
        if not (d.location.sheet == "Cover"
                and isinstance(d.before, str) and isinstance(d.after, str))
    ]
    assert not non_snapshot, (
        f"export is non-deterministic outside Cover snapshot date:\n"
        + "\n".join(str(d) for d in non_snapshot[:20])
    )


async def test_baseline_formula_cell_count_is_bounded(session: AsyncSession):
    """Pre-conversion formula footprint is small.

    Counts formula cells per sheet on a freshly exported workbook. As
    each conversion commit lands, the counts on the affected sheets
    should rise visibly. Threshold is set deliberately loose (≤ 400)
    so the baseline survives non-conversion edits to the exporter
    (e.g. adding a HYPERLINK to a navigation cell); subsequent commits
    will tighten/replace this assertion with per-sheet expectations
    once the formula bank is wired.
    """
    scenario = await _seed_minimal_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    counts = count_formula_cells(blob)
    total = sum(counts.values())
    assert total <= 400, (
        f"unexpected formula-cell growth before conversion starts: {counts}"
    )
