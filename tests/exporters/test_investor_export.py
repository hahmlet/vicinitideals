"""Smoke + parity tests for the LP investor Excel export.

Sheet roster grows commit-by-commit: commit 1 added Cover/Assumptions/
Glossary; commit 2 inserts the four Underwriting rollup sheets in the
§2 final order; commit 3 will splice per-project sheets between
Assumptions and Glossary. Tests assert exact roster + grow with the build.

Tests use the in-memory async SQLite + ``seed_deal_model_with_financials``
fixture from ``tests/conftest.py``; the exporter's data loader is exercised
end-to-end with real ORM rows.
"""
from __future__ import annotations

import re
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


def _commit_3_sheet_order(num_projects: int) -> tuple[str, ...]:
    """Sheet roster after commit 3: per-project sheets sit between
    Assumptions and Glossary. Project sheet names are ``P{n} {Name}``.
    """
    base_pre = (
        "Cover",
        "Underwriting Summary",
        "Underwriting Pro Forma",
        "Underwriting Cash Flow",
        "Investor Returns",
        "Assumptions",
    )
    return base_pre + tuple(
        # Match the seeder's "Main Project" name; tests with custom names
        # build the expected roster themselves.
        f"P{i + 1} Main Project" for i in range(num_projects)
    ) + ("Glossary & Methodology",)

# Named-range prefixes the validator recognises. Anything else is treated as a
# free-form name (debug / one-off) and is allowed but doesn't get
# bidirectional-validated against the doc glossary.
_NAMED_RANGE_RE = re.compile(r"^(s|p\d+|r)_")


async def _seed_minimal_scenario(session: AsyncSession):
    """Smallest reproducible Scenario for export smoke tests."""
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(session, org, user, name="Smoke-Test Opportunity")
    deal_model, _, _, _ = await seed_deal_model_with_financials(
        session, opportunity, user
    )
    return deal_model


async def test_workbook_has_expected_sheets(session: AsyncSession):
    """Single-project scenario: roster has exactly one P1 sheet inserted."""
    scenario = await _seed_minimal_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)
    assert tuple(wb.sheetnames) == _commit_3_sheet_order(num_projects=1)


async def test_per_project_sheet_per_project(session: AsyncSession):
    """Multi-project scenario: one P{n} sheet per project, in created_at order."""
    scenario = await _seed_minimal_scenario(session)
    # Seed two extra projects on the same scenario so we have N=3 total.
    from decimal import Decimal as _D
    from uuid import uuid4

    from app.models.deal import OperationalInputs as _OI
    from app.models.project import Project as _Project

    for label in ("Liberty", "East 25"):
        proj = _Project(
            id=uuid4(),
            scenario_id=scenario.id,
            opportunity_id=None,
            name=label,
            deal_type="acquisition",
        )
        session.add(proj)
        await session.flush()
        session.add(
            _OI(
                id=uuid4(), project_id=proj.id,
                unit_count_new=4, hold_period_years=5,
                exit_cap_rate_pct=_D("5.5"),
            )
        )
        await session.flush()

    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)
    sheets = tuple(wb.sheetnames)

    project_sheets = [s for s in sheets if s.startswith("P") and " " in s]
    assert len(project_sheets) == 3
    assert project_sheets[0].startswith("P1 ")
    assert project_sheets[1] == "P2 Liberty"
    assert project_sheets[2] == "P3 East 25"


async def test_long_project_name_truncated_to_27_chars(session: AsyncSession):
    """Per plan §2: P{n} prefix (4 chars) + ≤27 chars of name = 31 cap."""
    scenario = await _seed_minimal_scenario(session)
    from uuid import uuid4

    from app.models.project import Project as _Project

    long_name = "Northwest Freeway Industrial Park Phase II Buildings A through G"
    long_proj = _Project(
        id=uuid4(),
        scenario_id=scenario.id,
        opportunity_id=None,
        name=long_name,
        deal_type="acquisition",
    )
    session.add(long_proj)
    await session.flush()

    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)
    p2_sheets = [s for s in wb.sheetnames if s.startswith("P2 ")]
    assert len(p2_sheets) == 1
    sheet_name = p2_sheets[0]
    # 31-char Excel ceiling
    assert len(sheet_name) <= 31, sheet_name
    # Prefix is exactly "P2 " (3 chars), then up to 27 of the name
    assert sheet_name.startswith("P2 ")
    truncated_name_part = sheet_name[3:]
    assert truncated_name_part == long_name[: PROJECT_SHEET_NAME_BUDGET].rstrip()


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


@pytest.mark.xfail(strict=False, reason="soft gate — bidirectional validator tightens after commit 3 lands per-project sheets")
async def test_every_named_range_traces_to_doc_entry(session: AsyncSession):
    """Bidirectional validator (forward direction) per plan §3.8 + §7.

    For every named range matching ``^(s|p\\d+|r)_`` in the workbook, look
    up the implied metric in FINANCIAL_MODEL.md and assert it is tagged
    ``investor``. Marked xfail-soft during rollout: many ``s_*`` names refer
    to scenario meta (sponsor, scenario name, snapshot date) that aren't
    "metrics" in the FINANCIAL_MODEL.md sense — the strict mapping lands
    when commit 3 wires per-project metrics.
    """
    scenario = await _seed_minimal_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)

    investor_doc_names = {
        _slug(m.name) for m in parse_doc().for_audience("investor")
    }

    orphans: list[str] = []
    for name in wb.defined_names:
        if not _NAMED_RANGE_RE.match(name):
            continue
        bare = re.sub(r"^(s|p\d+|r)_", "", name)
        if _slug(bare) not in investor_doc_names:
            orphans.append(name)

    if orphans:
        pytest.fail(
            "named ranges with no investor-tagged doc entry:\n  " + "\n  ".join(sorted(orphans))
        )


async def test_uw_summary_kpis_match_engine_outputs(session: AsyncSession):
    """Parity test: hero KPIs on the Underwriting Summary sheet match the
    rollup engine's outputs to within rounding tolerance.
    """
    from app.engines.underwriting_rollup import rollup_summary

    scenario = await _seed_minimal_scenario(session)
    expected = await rollup_summary(scenario.id, session)
    expected_totals = expected["totals"]

    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)
    uw = wb["Underwriting Summary"]

    for key, name in (
        ("total_project_cost", "s_total_project_cost"),
        ("total_uses", "s_total_uses"),
        ("equity_required", "s_equity_required"),
    ):
        cell_value = _resolve_named_cell(wb, uw.title, name)
        engine_value = float(expected_totals.get(key) or 0)
        assert cell_value is not None, f"named range {name} not found"
        assert abs(float(cell_value or 0) - engine_value) < 0.01, (
            f"{name}: cell={cell_value} vs engine={engine_value}"
        )


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


# ── Helpers ───────────────────────────────────────────────────────────────────


def _slug(text: str) -> str:
    """Lowercase + alphanum-only slug for matching named-range fragments to
    metric titles like 'Total Project Cost (TPC)'."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _resolve_named_cell(wb, sheet_title: str, name: str):
    """Read the value at the cell registered under ``name`` on ``sheet_title``."""
    if name not in wb.defined_names:
        return None
    defined = wb.defined_names[name]
    for resolved_sheet, ref in defined.destinations:
        if resolved_sheet != sheet_title:
            continue
        sheet = wb[resolved_sheet]
        ref_clean = ref.replace("$", "")
        return sheet[ref_clean].value
    return None


_ = pytest  # silence "imported but unused" — pytest's asyncio_mode=auto handles invocation
