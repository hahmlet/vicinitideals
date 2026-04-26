"""Smoke tests for the LP investor Excel export.

Commit-1 scope: Cover, Assumptions, Glossary. Commits 2/3 will extend the
sheet roster (Underwriting Summary/Pro Forma/Cash Flow/Investor Returns,
then per-project sheets) and these tests will grow to assert the new
sheet names + named-range coverage.

Tests intentionally use the in-memory async SQLite + ``seed_deal_model_with_financials``
fixture from ``tests/conftest.py`` for speed; the exporter's data loader
is exercised end-to-end with real ORM rows.
"""
from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.exporters._doc_validator import parse_doc
from app.exporters.investor_export import (
    MAX_PROJECTS_PER_SCENARIO,
    PROJECT_SHEET_NAME_BUDGET,
    export_investor_workbook,
    make_investor_filename,
)
from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)


COMMIT_1_SHEET_ORDER = ("Cover", "Assumptions", "Glossary & Methodology")


async def _seed_minimal_scenario(session: AsyncSession):
    """Smallest reproducible Scenario for export smoke tests."""
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(session, org, user, name="Smoke-Test Opportunity")
    deal_model, _, _, _ = await seed_deal_model_with_financials(
        session, opportunity, user
    )
    return deal_model


async def test_workbook_has_expected_sheets(session: AsyncSession):
    """Sheets render in the commit-1 order with no orphan/extra sheets."""
    scenario = await _seed_minimal_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)
    assert tuple(wb.sheetnames) == COMMIT_1_SHEET_ORDER


async def test_named_ranges_resolve_to_existing_cells(session: AsyncSession):
    """Every defined name resolves to a real cell on the named sheet."""
    scenario = await _seed_minimal_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)

    assert len(wb.defined_names) > 0, "expected at least one defined name"
    for name in wb.defined_names:
        defined = wb.defined_names[name]
        destinations = list(defined.destinations)
        assert destinations, f"defined name {name!r} has no destinations"
        for sheet_title, ref in destinations:
            assert sheet_title in wb.sheetnames, (
                f"defined name {name!r} points to missing sheet {sheet_title!r}"
            )
            assert ref, f"defined name {name!r} has an empty cell ref"


async def test_no_sheet_protection(session: AsyncSession):
    """Investor export is read-only by convention (LPs need to copy values out).

    Plan §10: do not set Protection() on any sheet — the audience expectation
    is that the file is a values dump that can be reformatted, copied into
    the LP's own model, etc.
    """
    scenario = await _seed_minimal_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        assert not ws.protection.sheet, (
            f"sheet {sheet_name!r} has protection enabled — investor export should be read-only by convention only"
        )


async def test_glossary_sheet_has_investor_metrics(session: AsyncSession):
    """The Glossary sheet sources its term list from FINANCIAL_MODEL.md.

    Every metric tagged ``investor`` in the doc should land as a row.
    """
    scenario = await _seed_minimal_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)

    glossary = wb["Glossary & Methodology"]
    glossary_terms = {
        cell.value for cell in glossary["A"]
        if cell.value and isinstance(cell.value, str)
    }

    expected = {m.name for m in parse_doc().for_audience("investor")}
    missing = expected - glossary_terms
    assert not missing, f"investor-tagged metrics missing from Glossary sheet: {sorted(missing)}"


async def test_filename_slugged(session: AsyncSession):
    scenario = await _seed_minimal_scenario(session)
    from app.models.deal import Deal

    deal = await session.get(Deal, scenario.deal_id)
    name = make_investor_filename(scenario, deal)
    assert name.endswith("-investor.xlsx")
    assert " " not in name


def test_max_project_constants_are_consistent():
    """Plan §2: 5 max projects → 4-char prefix `P{n} ` + 27-char name = 31 (Excel ceiling)."""
    assert MAX_PROJECTS_PER_SCENARIO <= 99, "ordinal would need 3 digits"
    assert PROJECT_SHEET_NAME_BUDGET == 27
    assert len("P99 ") + PROJECT_SHEET_NAME_BUDGET == 31  # 2-digit ordinals fit too


# Silence the "imported but unused" warning when pytest collects this file —
# pytest itself doesn't auto-mark every async def as a test, but our pyproject
# uses asyncio_mode=auto so the coroutine signature is enough.
_ = pytest  # noqa: F401
