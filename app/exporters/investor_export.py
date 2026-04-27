"""Investor-ready Excel export for a Scenario.

Generates a single ``.xlsx`` workbook per Scenario formatted for an LP /
lender / sponsor audience. See ``docs/feature-plans/investor-excel-export-v2.md``
for the full design (sheet order, named-range convention, doc-driven
glossary, build sequencing).

**Build status.** Commit 1 of the build sequence ships the audit-spine
sheets (Cover, Assumptions, Glossary). Commits 2/3 add the
underwriting-rollup sheets (Underwriting Summary, Pro Forma, Cash Flow,
Investor Returns) and the per-project sheets respectively. Sheet order
on disk grows toward the §2 final order as those commits land.

**Why this exists alongside ``excel_export.py``.** The round-trip exporter
is deprecated (see its docstring); it served the importer round-trip use
case. This module is the LP-facing artifact and is not intended to be
re-imported.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exporters._doc_validator import MetricEntry, parse_doc
from app.exporters._workbook_helpers import (
    ACCOUNTING,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    ALIGN_WRAP,
    BRAND,
    DATE_FMT,
    FONT_HINT,
    FONT_LABEL,
    FONT_SUBTITLE,
    FONT_TITLE,
    FONT_VALUE,
    INT_COMMA,
    PCT,
    THIN_BORDER,
    CellRegistry,
    freeze_top,
    header_row,
    kv_row,
    print_landscape,
    section_label,
    set_widths,
)
from app.engines.underwriting_rollup import (
    rollup_summary,
    rollup_waterfall,
)
from app.models.capital import (
    CapitalModule,
    CapitalModuleProject,
    WaterfallResult,
    WaterfallTier,
)
from app.models.cashflow import CashFlow, CashFlowLineItem, OperationalOutputs
from app.models.deal import (
    Deal,
    DealModel,
    OperationalInputs,
    UnitMix,
    UseLine,
    normalize_opex_label,
)
from app.models.org import Organization
from app.models.project import Project

# Hard cap from the plan; enforced upstream so we never need 3-digit ordinals.
MAX_PROJECTS_PER_SCENARIO = 5

# Sheet-name prefix is exactly 4 chars (`P` + 1- or 2-digit ordinal + space),
# leaving 27 chars for the project name within Excel's 31-char ceiling.
PROJECT_SHEET_NAME_BUDGET = 27


# ── Public entry point ────────────────────────────────────────────────────────


async def export_investor_workbook(
    deal_model_id: UUID, session: AsyncSession
) -> bytes:
    """Build the investor workbook for a Scenario and return the bytes.

    Raises ``ValueError`` if the Scenario doesn't exist. The caller wraps
    the bytes in a ``StreamingResponse`` with the appropriate
    Content-Disposition (see ``download_investor_export`` in ui.py).
    """
    ctx = await _load_all(session, deal_model_id)
    if ctx is None:
        raise ValueError(f"Scenario {deal_model_id} was not found")

    wb = Workbook()
    registry = CellRegistry()

    # Commit 2 sheet roster (matches plan §2 final order minus per-project
    # sheets, which land in commit 3). Per-project sheets are inserted
    # between Assumptions and Glossary as they're built.
    cover = wb.active
    cover.title = "Cover"
    _build_cover(cover, registry, ctx)

    uw_summary = wb.create_sheet("Underwriting Summary")
    _build_uw_summary(uw_summary, registry, ctx)

    uw_proforma = wb.create_sheet("Underwriting Pro Forma")
    _build_uw_proforma(uw_proforma, registry, ctx)

    uw_cashflow = wb.create_sheet("Underwriting Cash Flow")
    _build_uw_cashflow(uw_cashflow, registry, ctx)

    investor_returns = wb.create_sheet("Investor Returns")
    _build_investor_returns(investor_returns, registry, ctx)

    assumptions = wb.create_sheet("Assumptions")
    _build_assumptions(assumptions, registry, ctx)

    # Per-project sheets sit between Assumptions and Glossary (plan §2 final
    # order). Sheet names are `P{n} {Name}` truncated to Excel's 31-char
    # ceiling — see _project_sheet_name. The Underwriting Summary's per-
    # project mini-table already emits =HYPERLINK() targets pointing at
    # these names, so they resolve once these sheets exist.
    projects: list[Project] = ctx["projects"]
    for idx, project in enumerate(projects, start=1):
        sheet_name = _project_sheet_name(idx, project.name)
        ws_proj = wb.create_sheet(sheet_name)
        _build_project_sheet(ws_proj, registry, ctx, idx, project)

    glossary = wb.create_sheet("Glossary & Methodology")
    _build_glossary(glossary, registry, ctx)

    registry.emit(wb)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def make_investor_filename(scenario: DealModel, deal: Deal | None) -> str:
    """Investor-export filename: ``<deal>-<scenario>-investor.xlsx`` (slugged)."""
    deal_part = (deal.name if deal else None) or "deal"
    scen_part = scenario.name or "scenario"
    deal_slug = re.sub(r"[^a-z0-9]+", "-", deal_part.lower()).strip("-") or "deal"
    scen_slug = re.sub(r"[^a-z0-9]+", "-", scen_part.lower()).strip("-") or "scenario"
    return f"{deal_slug}-{scen_slug}-investor.xlsx"


# ── Data loader ───────────────────────────────────────────────────────────────


async def _load_all(session: AsyncSession, scenario_id: UUID) -> dict | None:
    """Load the context dict the sheet builders read from.

    Shape mirrors plan §5.4 but only the fields commit 1 needs are populated
    today. Commits 2/3 will extend with cash flows, line items, waterfall
    rows, and rollup outputs.
    """
    scenario = (
        await session.execute(select(DealModel).where(DealModel.id == scenario_id))
    ).scalar_one_or_none()
    if scenario is None:
        return None

    deal = (
        await session.execute(select(Deal).where(Deal.id == scenario.deal_id))
    ).scalar_one_or_none()

    org: Organization | None = None
    if deal is not None and deal.org_id is not None:
        org = (
            await session.execute(
                select(Organization).where(Organization.id == deal.org_id)
            )
        ).scalar_one_or_none()

    projects = list(
        (
            await session.execute(
                select(Project)
                .where(Project.scenario_id == scenario_id)
                .order_by(Project.created_at.asc())
            )
        ).scalars()
    )
    project_ids = [p.id for p in projects]

    inputs_by_project: dict[UUID, OperationalInputs] = {}
    use_lines_by_project: dict[UUID, list[UseLine]] = {pid: [] for pid in project_ids}
    unit_mix_by_project: dict[UUID, list[UnitMix]] = {pid: [] for pid in project_ids}

    if project_ids:
        for inp in (
            await session.execute(
                select(OperationalInputs).where(
                    OperationalInputs.project_id.in_(project_ids)
                )
            )
        ).scalars():
            inputs_by_project[inp.project_id] = inp
        for ul in (
            await session.execute(
                select(UseLine)
                .where(UseLine.project_id.in_(project_ids))
                .order_by(UseLine.phase, UseLine.label)
            )
        ).scalars():
            use_lines_by_project.setdefault(ul.project_id, []).append(ul)
        for um in (
            await session.execute(
                select(UnitMix)
                .where(UnitMix.project_id.in_(project_ids))
                .order_by(UnitMix.label)
            )
        ).scalars():
            unit_mix_by_project.setdefault(um.project_id, []).append(um)

    capital_modules = list(
        (
            await session.execute(
                select(CapitalModule)
                .where(CapitalModule.scenario_id == scenario_id)
                .order_by(CapitalModule.stack_position)
            )
        ).scalars()
    )

    junctions: list[CapitalModuleProject] = []
    if capital_modules:
        module_ids = [m.id for m in capital_modules]
        junctions = list(
            (
                await session.execute(
                    select(CapitalModuleProject).where(
                        CapitalModuleProject.capital_module_id.in_(module_ids)
                    )
                )
            ).scalars()
        )

    # ── Cashflow / waterfall / rollup data (commit 2) ──────────────────────
    # Per-project cashflow + line items so the UW Pro Forma / Cash Flow
    # sheets can aggregate to annual buckets and the Investor Returns sheet
    # can read waterfall tier distributions.
    cash_flows_by_project: dict[UUID, list[CashFlow]] = {pid: [] for pid in project_ids}
    cash_flow_items_by_project: dict[UUID, list[CashFlowLineItem]] = {
        pid: [] for pid in project_ids
    }
    outputs_by_project: dict[UUID, OperationalOutputs] = {}
    if project_ids:
        for cf in (
            await session.execute(
                select(CashFlow)
                .where(CashFlow.scenario_id == scenario_id)
                .order_by(CashFlow.project_id, CashFlow.period)
            )
        ).scalars():
            if cf.project_id is not None:
                cash_flows_by_project.setdefault(cf.project_id, []).append(cf)
        for li in (
            await session.execute(
                select(CashFlowLineItem)
                .where(CashFlowLineItem.scenario_id == scenario_id)
                .order_by(CashFlowLineItem.project_id, CashFlowLineItem.period)
            )
        ).scalars():
            if li.project_id is not None:
                cash_flow_items_by_project.setdefault(li.project_id, []).append(li)
        for o in (
            await session.execute(
                select(OperationalOutputs).where(
                    OperationalOutputs.scenario_id == scenario_id
                )
            )
        ).scalars():
            if o.project_id is not None:
                outputs_by_project[o.project_id] = o

    waterfall_tiers = list(
        (
            await session.execute(
                select(WaterfallTier)
                .where(WaterfallTier.scenario_id == scenario_id)
                .order_by(WaterfallTier.priority)
            )
        ).scalars()
    )
    waterfall_results = list(
        (
            await session.execute(
                select(WaterfallResult)
                .where(WaterfallResult.scenario_id == scenario_id)
                .order_by(WaterfallResult.period)
            )
        ).scalars()
    )

    # Rollup helpers do their own DB roundtrips — call once and stash so
    # every sheet builder reads the same snapshot. ``rollup_summary``
    # returns ``{"per_project": [...], "totals": {...}}``;
    # ``rollup_waterfall`` returns the joined tier table.
    summary = await rollup_summary(scenario_id, session)
    waterfall_rollup = await rollup_waterfall(scenario_id, session)

    return {
        "scenario": scenario,
        "deal": deal,
        "org": org,
        "projects": projects,
        "operational_inputs": inputs_by_project,
        "use_lines": use_lines_by_project,
        "unit_mix": unit_mix_by_project,
        "capital_modules": capital_modules,
        "junctions": junctions,
        "cash_flows": cash_flows_by_project,
        "cash_flow_items": cash_flow_items_by_project,
        "outputs": outputs_by_project,
        "waterfall_tiers": waterfall_tiers,
        "waterfall_results": waterfall_results,
        "rollup_summary": summary,
        "rollup_waterfall": waterfall_rollup,
        "snapshot_at": datetime.now(),
    }


# ── Sheet builders ────────────────────────────────────────────────────────────


_NOI_BASIS_LABELS: dict[str, str] = {
    "revenue_opex": "Revenue/OpEx",
    "noi": "Simplified NOI",
}

# Repo URL for in-workbook hyperlinks back to the FINANCIAL_MODEL.md headings.
# If the repo moves, update here. Anchor format follows GitHub's markdown
# heading convention (see _github_anchor_for).
_FINANCIAL_MODEL_URL = (
    "https://github.com/hahmlet/vicinitideals/blob/main/docs/FINANCIAL_MODEL.md"
)


def _github_anchor_for(metric) -> str:
    """Derive GitHub's auto-generated anchor for a tagged metric heading.

    GitHub renders ``### Total Project Cost (TPC) [investor, lender, app]``
    with the anchor ``#total-project-cost-tpc-investor-lender-app``: lowercase,
    drop everything that isn't alphanumeric / space / hyphen / underscore,
    replace runs of whitespace with single hyphens.
    """
    audiences = sorted(metric.audiences)
    heading = f"{metric.name} [{', '.join(audiences)}]"
    cleaned = re.sub(r"[^a-z0-9\s_-]", "", heading.lower())
    return re.sub(r"\s+", "-", cleaned).strip("-")


def _noi_basis_label(income_mode: str | None) -> str:
    """Translate the engine's `income_mode` enum to the LP-facing NOI Basis label.

    Engine stores `revenue_opex` (default) or `noi`; the LP cares about the
    semantic distinction between full P&L roll-up vs. direct-NOI input.
    """
    return _NOI_BASIS_LABELS.get(str(income_mode or "").lower(), str(income_mode or "—"))


def _build_cover(ws, registry: CellRegistry, ctx: dict) -> None:
    """Cover sheet: deal/scenario title, sponsor, project list."""
    set_widths(ws, [28, 60])
    scenario: DealModel = ctx["scenario"]
    deal: Deal | None = ctx["deal"]
    org: Organization | None = ctx["org"]
    projects: list[Project] = ctx["projects"]

    # Title block (no merged subtitle row — removed per LP feedback,
    # Snapshot Date carries the timestamp in the metadata block below)
    ws.cell(row=1, column=1, value=f"{(deal.name if deal else '—')} — {scenario.name}")
    ws.cell(row=1, column=1).font = FONT_TITLE
    ws.cell(row=1, column=1).alignment = ALIGN_LEFT
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=2)
    ws.row_dimensions[1].height = 28

    # Metadata block — `Scenario Active` row removed (LP doesn't need scenario-
    # active state; that's an internal toggle).
    section_label(ws, 3, "Deal", span_cols=2)
    kv_row(ws, 4, "Sponsor / Organization", org.name if org else "—",
           name="s_sponsor_name", registry=registry)
    kv_row(ws, 5, "Deal Name", deal.name if deal else "—",
           name="s_deal_name", registry=registry)
    kv_row(ws, 6, "Scenario Name", scenario.name,
           name="s_scenario_name", registry=registry)
    snapshot_at: datetime = ctx["snapshot_at"]
    kv_row(ws, 7, "Snapshot Date", snapshot_at.date().isoformat(),
           name="s_snapshot_date", registry=registry)
    kv_row(ws, 8, "Project Count", len(projects),
           name="s_project_count", registry=registry, fmt=INT_COMMA)
    kv_row(ws, 9, "NOI Basis", _noi_basis_label(scenario.income_mode),
           name="s_noi_basis", registry=registry)

    # Project list — one row per project, labelled `Project N`
    # (LP-friendlier than the engine's `P1` ordinal shorthand).
    section_label(ws, 11, "Projects", span_cols=2)
    for idx, proj in enumerate(projects, start=1):
        row = 11 + idx
        ws.cell(row=row, column=1, value=f"Project {idx}").font = FONT_LABEL
        ws.cell(row=row, column=2, value=proj.name or f"Project {idx}").font = FONT_VALUE

    freeze_top(ws, row=3)
    print_landscape(ws)


# ── Aggregation helpers (commit 2) ────────────────────────────────────────────


def _period_to_year(period: int) -> int:
    """Year-bucket convention from plan §5.3.

    Period 0 = acquisition close → Y0. Periods 1-12 = Y1, etc. Y0 carries
    capital events (acquisition outflows, partial-year operations) that
    aren't visible if rolled into Y1.
    """
    if period == 0:
        return 0
    return (period - 1) // 12 + 1


def _max_year(rows: list[CashFlow]) -> int:
    if not rows:
        return 0
    return max(_period_to_year(cf.period) for cf in rows)


def _aggregate_annual(monthly: list[CashFlow]) -> dict[int, dict[str, Decimal]]:
    """Aggregate per-period CashFlow rows into annual buckets.

    Returns ``{year: {field: Decimal}}`` for the standard cashflow fields.
    Skipping ``cumulative_cash_flow`` because it's a balance series, not
    additive — the consumers compute their own running totals.
    """
    fields = (
        "gross_revenue",
        "vacancy_loss",
        "effective_gross_income",
        "operating_expenses",
        "capex_reserve",
        "noi",
        "debt_service",
        "net_cash_flow",
    )
    out: dict[int, dict[str, Decimal]] = {}
    for cf in monthly:
        year = _period_to_year(cf.period)
        bucket = out.setdefault(year, {f: Decimal(0) for f in fields})
        for field in fields:
            bucket[field] += _coerce_decimal(getattr(cf, field, 0) or 0)
    return out


def _annual_line_items(
    items: list[CashFlowLineItem],
) -> dict[int, dict[str, Decimal]]:
    """Aggregate CashFlowLineItem rows by (year, label) for the Pro Forma sheet.

    OpEx categories like "Real Estate Taxes" / "Insurance" / "Property Mgmt"
    show up here as separate rows. Capital events (acquisition outflows,
    sale proceeds) likewise — the cash-flow sheet picks those out by
    label prefix.
    """
    out: dict[int, dict[str, Decimal]] = {}
    for li in items:
        year = _period_to_year(li.period)
        bucket = out.setdefault(year, {})
        bucket[li.label] = bucket.get(li.label, Decimal(0)) + _coerce_decimal(
            li.net_amount or 0
        )
    return out


def _waterfall_by_tier(
    rollup: list[dict],
) -> dict[str, dict[str, Decimal]]:
    """Aggregate the waterfall rollup into ``{tier_type: totals}``.

    Each tier-type bucket carries ``cash_total`` and ``module_count`` (unique
    Capital Modules that received distributions through this tier).
    """
    out: dict[str, dict[str, Decimal]] = {}
    seen_modules: dict[str, set[str]] = {}
    for row in rollup:
        tier = row.get("tier_type") or "unknown"
        bucket = out.setdefault(tier, {"cash_total": Decimal(0)})
        bucket["cash_total"] += _coerce_decimal(row.get("cash_distributed") or 0)
        module_id = row.get("capital_module_id")
        if module_id:
            seen_modules.setdefault(tier, set()).add(module_id)
    for tier, modules in seen_modules.items():
        out[tier]["module_count"] = Decimal(len(modules))
    return out


def _aggregate_scenario_annual(
    cash_flows_by_project: dict[UUID, list[CashFlow]],
) -> dict[int, dict[str, Decimal]]:
    """Sum all projects' annual cashflow buckets into scenario totals."""
    combined: dict[int, dict[str, Decimal]] = {}
    for cf_list in cash_flows_by_project.values():
        per_year = _aggregate_annual(cf_list)
        for year, fields in per_year.items():
            bucket = combined.setdefault(year, {})
            for field, value in fields.items():
                bucket[field] = bucket.get(field, Decimal(0)) + value
    return combined


# ── Underwriting Summary sheet ────────────────────────────────────────────────


def _build_uw_summary(ws, registry: CellRegistry, ctx: dict) -> None:
    """Underwriting Summary: hero KPIs + scenario S&U + per-project mini-table.

    KPI sources reference ``rollup_summary`` totals + ``rollup_irr``. The
    per-project mini-table uses ``=HYPERLINK("#'P1 Liberty'!A1", ...)``
    Excel syntax to navigate to per-project sheets — those sheets land in
    commit 3, so the hyperlink is already present and resolves once those
    sheets exist.
    """
    set_widths(ws, [32, 24, 18, 14, 14, 14, 14])
    summary = ctx.get("rollup_summary") or {}
    totals = summary.get("totals") or {}
    per_project = summary.get("per_project") or []
    rollup_waterfall: list[dict] = ctx.get("rollup_waterfall") or []
    projects: list[Project] = ctx["projects"]
    capital_modules: list[CapitalModule] = ctx["capital_modules"]
    junctions: list[CapitalModuleProject] = ctx["junctions"]
    use_lines_by_project: dict[UUID, list[UseLine]] = ctx["use_lines"]

    # ── Primary KPI block ──────────────────────────────────────────────────
    section_label(ws, 1, "Primary KPIs", span_cols=2)
    row = 2
    kv_row(
        ws, row, "Total Project Cost",
        _coerce_decimal(totals.get("total_project_cost") or 0),
        name="s_total_project_cost", registry=registry,
        fmt=ACCOUNTING, hero=True,
    ); row += 1
    kv_row(
        ws, row, "Total Uses",
        _coerce_decimal(totals.get("total_uses") or 0),
        name="s_total_uses", registry=registry,
        fmt=ACCOUNTING, hero=True,
    ); row += 1
    kv_row(
        ws, row, "Equity Required",
        _coerce_decimal(totals.get("equity_required") or 0),
        name="s_equity_required", registry=registry,
        fmt=ACCOUNTING, hero=True,
    ); row += 1
    # Combined DSCR = Σ NOI / Σ DS across projects. Per LP feedback the
    # right number for a Primary-KPI block is a singular combined coverage
    # figure, not the weakest project's DSCR. Engine doesn't store DS as
    # a per-project scalar, so derive it from per-project (NOI ÷ DSCR).
    combined_dscr = _combined_dscr(per_project)
    kv_row(
        ws, row, "Stabilized DSCR (combined)",
        combined_dscr,
        name="s_combined_dscr", registry=registry,
        fmt="0.000", hero=True,
    ); row += 1
    kv_row(
        ws, row, "Combined Stabilized NOI",
        _sum_per_project_field(per_project, "noi_stabilized"),
        name="s_combined_noi", registry=registry,
        fmt=ACCOUNTING, hero=True,
    ); row += 1
    kv_row(
        ws, row, "Combined Levered IRR",
        _coerce_pct(totals.get("combined_irr_pct") or 0),
        name="s_combined_irr", registry=registry,
        fmt=PCT, hero=True,
    ); row += 1
    # Hold = max of milestone chain (engine writes total_timeline_months as
    # the count of generated cashflow rows = sum of phase durations from
    # acquisition close through divestment, or stabilized when no divestment
    # exists). This is the actual modeled horizon, distinct from the
    # OperationalInputs.hold_period_years input on the Assumptions sheet
    # (which represents the user's intent for *stabilized* hold only).
    longest_hold = _longest_hold_months(per_project)
    kv_row(
        ws, row, "Total Modeled Duration (months)",
        longest_hold,
        name="s_modeled_duration_months", registry=registry,
        fmt=INT_COMMA, hero=True,
    ); row += 1
    # Combined Unlevered IRR — computed from per-project unlevered CF series
    # summed by period (NCF + DS = NOI − capital_outflows + capital_inflows),
    # then XIRR. Sibling to Combined Levered IRR for the standard
    # leverage-amplification read.
    unlevered_irr = _combined_unlevered_irr(ctx["cash_flows"])
    kv_row(
        ws, row, "Combined Unlevered IRR",
        unlevered_irr,
        name="s_combined_unlevered_irr", registry=registry,
        fmt=PCT, hero=True,
    ); row += 1
    # Equity Multiple (combined LP+GP) — total equity-module distributions
    # divided by total equity commitments. Returns None ("—") when the
    # waterfall hasn't run or there's no equity stack seeded.
    equity_multiple = _combined_em(rollup_waterfall, capital_modules)
    kv_row(
        ws, row, "Combined Equity Multiple",
        equity_multiple,
        name="s_combined_equity_multiple", registry=registry,
        fmt="0.00\\x", hero=True,
    ); row += 1
    # Cash-on-Cash Year 1 — sum of equity distributions in periods 1-12
    # divided by total equity commitments. The standard first-year-yield
    # metric LPs ask about ahead of a deal close.
    coc_y1 = _coc_year_one(rollup_waterfall, capital_modules)
    kv_row(
        ws, row, "Cash-on-Cash (Year 1)",
        coc_y1,
        name="s_coc_year_one", registry=registry,
        fmt=PCT, hero=True,
    ); row += 1

    # ── Scenario Sources & Uses ────────────────────────────────────────────
    su_row = row + 2
    section_label(ws, su_row, "Scenario Sources & Uses", span_cols=4)
    header_row(ws, su_row + 1, ["Side", "Label", "Amount", "Notes"])
    line = su_row + 2

    # Uses — sum across projects, by phase
    uses_by_phase: dict[str, Decimal] = {}
    for pid, uls in use_lines_by_project.items():
        for ul in uls:
            phase = str(getattr(ul.phase, "value", ul.phase) or "")
            if phase == "exit":
                continue
            uses_by_phase[phase] = uses_by_phase.get(phase, Decimal(0)) + _coerce_decimal(
                ul.amount or 0
            )
    for phase, amount in sorted(uses_by_phase.items()):
        ws.cell(row=line, column=1, value="Use").font = FONT_VALUE
        ws.cell(row=line, column=2, value=phase.replace("_", " ").title()).font = FONT_VALUE
        ws.cell(row=line, column=3, value=_to_excel_number(amount)).number_format = ACCOUNTING
        ws.cell(row=line, column=4, value="(summed across projects)").font = FONT_HINT
        line += 1
    uses_total = sum(uses_by_phase.values(), Decimal(0))
    ws.cell(row=line, column=1, value="Use").font = FONT_LABEL
    ws.cell(row=line, column=2, value="Total Uses (excl. exit)").font = FONT_LABEL
    registry.write(
        ws, line, 3, uses_total,
        name="s_su_uses_total", fmt=ACCOUNTING, font=FONT_LABEL, align=ALIGN_RIGHT,
    )
    line += 2

    # Sources — capital modules, deduplicated for shared modules via junctions
    junction_amount: dict[UUID, Decimal] = {}
    for j in junctions:
        junction_amount[j.capital_module_id] = junction_amount.get(
            j.capital_module_id, Decimal(0)
        ) + _coerce_decimal(j.amount or 0)
    sources_total = Decimal(0)
    for module in capital_modules:
        amount = junction_amount.get(module.id) or _coerce_decimal(
            (module.source or {}).get("amount") or 0
        )
        ws.cell(row=line, column=1, value="Source").font = FONT_VALUE
        ws.cell(row=line, column=2, value=module.label or _funder_type_label(module)).font = FONT_VALUE
        ws.cell(row=line, column=3, value=_to_excel_number(amount)).number_format = ACCOUNTING
        ws.cell(row=line, column=4, value=_funder_type_label(module)).font = FONT_HINT
        sources_total += amount
        line += 1
    ws.cell(row=line, column=1, value="Source").font = FONT_LABEL
    ws.cell(row=line, column=2, value="Total Sources").font = FONT_LABEL
    registry.write(
        ws, line, 3, sources_total,
        name="s_su_sources_total", fmt=ACCOUNTING, font=FONT_LABEL, align=ALIGN_RIGHT,
    )
    line += 1

    gap = uses_total - sources_total
    ws.cell(row=line, column=1, value="Δ").font = FONT_LABEL
    ws.cell(row=line, column=2, value="Sources Gap (Uses − Sources)").font = FONT_LABEL
    registry.write(
        ws, line, 3, gap,
        name="s_sources_gap", fmt=ACCOUNTING, font=FONT_LABEL, align=ALIGN_RIGHT,
    )
    line += 2

    # ── Per-project mini-summary ───────────────────────────────────────────
    pp_row = line + 1
    section_label(ws, pp_row, "Per-Project Mini-Summary", span_cols=7)
    header_row(
        ws, pp_row + 1,
        ["Project", "TPC", "Equity Req'd", "Stab NOI", "DSCR", "Levered IRR", "Sheet"],
    )
    pp_data = pp_row + 2
    for idx, project in enumerate(projects, start=1):
        proj_id = str(project.id)
        record = next(
            (p for p in per_project if str(p.get("project_id") or "") == proj_id),
            {},
        )
        ws.cell(row=pp_data, column=1, value=project.name or f"Project {idx}").font = FONT_VALUE
        ws.cell(row=pp_data, column=2, value=_to_excel_number(record.get("total_project_cost"))).number_format = ACCOUNTING
        ws.cell(row=pp_data, column=3, value=_to_excel_number(record.get("equity_required"))).number_format = ACCOUNTING
        ws.cell(row=pp_data, column=4, value=_to_excel_number(record.get("noi_stabilized"))).number_format = ACCOUNTING
        ws.cell(row=pp_data, column=5, value=_to_excel_number(record.get("dscr"))).number_format = "0.000"
        levered = record.get("project_irr_levered")
        ws.cell(row=pp_data, column=6, value=_to_excel_number(_coerce_pct(levered) if levered is not None else None)).number_format = PCT
        # Sheet hyperlink — resolves once commit 3's per-project sheets land.
        sheet_label = _project_sheet_name(idx, project.name)
        ws.cell(
            row=pp_data, column=7,
            value=f'=HYPERLINK("#\'{sheet_label}\'!A1", "→ open")',
        ).font = FONT_VALUE
        pp_data += 1

    # ── Valuation Reconciliation ───────────────────────────────────────────
    # Two ways to value the asset at exit. Should land within a few percent
    # of each other if the deal's exit cap rate matches the implied DCF
    # discounting; a wide delta is a yellow flag for either the cap-rate
    # input or the underlying CF projection.
    val_row = pp_data + 1
    section_label(ws, val_row, "Valuation Reconciliation", span_cols=3)
    header_row(ws, val_row + 1, ["Method", "Value", "Notes"])

    # Direct Cap: Stabilized NOI ÷ Exit Cap Rate. Pulls Exit Cap from the
    # default project's OperationalInputs (scenario-level field today).
    default_inputs = (
        ctx["operational_inputs"].get(projects[0].id) if projects else None
    )
    exit_cap_pct_raw = (
        _coerce_decimal(getattr(default_inputs, "exit_cap_rate_pct", 0) or 0)
    )
    combined_noi = _sum_per_project_field(per_project, "noi_stabilized")
    direct_cap_value = (
        (combined_noi * Decimal(100) / exit_cap_pct_raw) if exit_cap_pct_raw > 0 else None
    )

    # DCF / Modeled Exit: sum of "Sale" line items in the exit period(s).
    # When the engine writes a synthesized exit event (always — see
    # _compute_capital_events_for_phase), this captures it. If no sale
    # event was generated the row shows "—".
    cash_flow_items: dict[UUID, list[CashFlowLineItem]] = ctx["cash_flow_items"]
    modeled_exit_value = Decimal(0)
    has_sale_event = False
    for items in cash_flow_items.values():
        for li in items:
            label = (li.label or "").strip()
            if label.startswith("Sale") or label.startswith("Exit"):
                modeled_exit_value += _coerce_decimal(li.net_amount or 0)
                has_sale_event = True

    cur = val_row + 2
    ws.cell(row=cur, column=1, value="Direct Cap (NOI ÷ Exit Cap)").font = FONT_LABEL
    if direct_cap_value is not None:
        registry.write(
            ws, cur, 2, direct_cap_value,
            name="s_direct_cap_value", fmt=ACCOUNTING,
            font=FONT_VALUE, align=ALIGN_RIGHT,
        )
        ws.cell(
            row=cur, column=3,
            value=f"Σ Stab NOI ÷ {exit_cap_pct_raw}% Exit Cap",
        ).font = FONT_HINT
    else:
        ws.cell(row=cur, column=2, value=_DASH).font = FONT_VALUE
        ws.cell(row=cur, column=3, value="(no Exit Cap configured)").font = FONT_HINT
    cur += 1

    ws.cell(row=cur, column=1, value="Modeled Exit (DCF / engine sale)").font = FONT_LABEL
    if has_sale_event:
        registry.write(
            ws, cur, 2, modeled_exit_value,
            name="s_modeled_exit_value", fmt=ACCOUNTING,
            font=FONT_VALUE, align=ALIGN_RIGHT,
        )
        ws.cell(row=cur, column=3, value="Σ engine-written Sale events").font = FONT_HINT
    else:
        ws.cell(row=cur, column=2, value=_DASH).font = FONT_VALUE
        ws.cell(row=cur, column=3, value="(no exit event in cash flows)").font = FONT_HINT
    cur += 1

    if direct_cap_value is not None and has_sale_event:
        delta = modeled_exit_value - direct_cap_value
        ws.cell(row=cur, column=1, value="Δ (Modeled − Direct Cap)").font = FONT_LABEL
        registry.write(
            ws, cur, 2, delta,
            name="s_valuation_delta", fmt=ACCOUNTING,
            font=FONT_VALUE, align=ALIGN_RIGHT,
        )
        delta_pct = (delta / direct_cap_value) if direct_cap_value > 0 else None
        if delta_pct is not None:
            ws.cell(
                row=cur, column=3,
                value=f"{(delta_pct * 100):.1f}% of Direct Cap",
            ).font = FONT_HINT

    freeze_top(ws, row=2)
    print_landscape(ws)


# ── Underwriting Pro Forma sheet ──────────────────────────────────────────────


def _build_uw_proforma(ws, registry: CellRegistry, ctx: dict) -> None:
    """Annual P&L summed across projects: Y0 → Y10 (or longest hold)."""
    cash_flows: dict[UUID, list[CashFlow]] = ctx["cash_flows"]
    cash_flow_items: dict[UUID, list[CashFlowLineItem]] = ctx["cash_flow_items"]

    annual = _aggregate_scenario_annual(cash_flows)
    max_year = min(max(annual) if annual else 0, 10)
    year_cols = list(range(0, max(max_year, 1) + 1))

    set_widths(ws, [30, *([14] * (len(year_cols) + 1))])

    section_label(ws, 1, "Pro Forma — Annual P&L (combined across projects)", span_cols=len(year_cols) + 1)
    header_row(ws, 2, ["Line Item", *[f"Y{y}" for y in year_cols]])

    rows: list[tuple[str, str, str | None]] = [
        ("Gross Revenue", "gross_revenue", "r_uw_gross_revenue"),
        ("Vacancy Loss", "vacancy_loss", None),
        ("Effective Gross Income", "effective_gross_income", "r_uw_egi"),
        ("Operating Expenses", "operating_expenses", "r_uw_opex"),
        ("CapEx Reserve", "capex_reserve", None),
        ("NOI", "noi", "r_uw_noi"),
        ("Debt Service", "debt_service", "r_uw_debt_service"),
        ("Net Cash Flow", "net_cash_flow", "r_uw_net_cash_flow"),
    ]
    cur_row = 3
    for label, field, range_name in rows:
        ws.cell(row=cur_row, column=1, value=label).font = FONT_LABEL
        for col_offset, year in enumerate(year_cols):
            value = annual.get(year, {}).get(field, Decimal(0))
            cell = ws.cell(row=cur_row, column=2 + col_offset, value=_to_excel_number(value))
            cell.number_format = ACCOUNTING
            cell.font = FONT_VALUE
            cell.alignment = ALIGN_RIGHT
        if range_name and year_cols:
            registry.register_range(
                range_name,
                ws.title,
                cur_row,
                cur_row,
                col=2,
                end_col=1 + len(year_cols),
            )
        cur_row += 1

    # OER (Operating Expense Ratio) = OpEx / EGI per year. Standard CRE
    # operating-efficiency metric — typical multifamily targets 35-45%; a
    # number above 50% is a yellow flag for the LP. Rendered as a derived
    # ratio row immediately below CapEx Reserve, before the NOI line.
    ws.cell(row=cur_row, column=1, value="OER (OpEx ÷ EGI)").font = FONT_LABEL
    for col_offset, year in enumerate(year_cols):
        opex = annual.get(year, {}).get("operating_expenses", Decimal(0))
        egi = annual.get(year, {}).get("effective_gross_income", Decimal(0))
        oer = (opex / egi) if egi > 0 else None
        cell = ws.cell(
            row=cur_row, column=2 + col_offset,
            value=_to_excel_number(oer) if oer is not None else _DASH,
        )
        cell.number_format = PCT
        cell.font = FONT_VALUE
        cell.alignment = ALIGN_RIGHT
    if year_cols:
        registry.register_range(
            "r_uw_oer", ws.title, cur_row, cur_row,
            col=2, end_col=1 + len(year_cols),
        )
    cur_row += 1

    # Revenue + OpEx breakouts: separate tables driven by line items.
    # Category-aware aggregation — Revenue from `income` line items
    # (per-stream labels, Option C: same label across projects = one row),
    # OpEx from `expense` line items (per-category labels). Capital events
    # show on the Underwriting Cash Flow sheet, not here.
    by_category = _aggregate_scenario_line_items_by_category(cash_flow_items)

    cur_row += 1
    cur_row = _write_breakout_table(
        ws, registry, cur_row,
        title="Revenue Breakout (by stream)",
        rows=by_category.get("income", {}),
        year_cols=year_cols,
        empty_hint="(no revenue line items recorded — run Compute to populate)",
    )

    cur_row += 1
    cur_row = _write_breakout_table(
        ws, registry, cur_row,
        title="OpEx Breakout (by category)",
        rows=by_category.get("expense", {}),
        year_cols=year_cols,
        empty_hint="(no OpEx line items recorded — run Compute to populate)",
    )

    freeze_top(ws, row=3)
    print_landscape(ws)


def _write_breakout_table(
    ws,
    registry: CellRegistry,
    start_row: int,
    *,
    title: str,
    rows: dict[int, dict[str, Decimal]],
    year_cols: list[int],
    empty_hint: str,
) -> int:
    """Render one labelled annual-buckets table and return the row after it.

    Shared by the Pro Forma sheet's Revenue and OpEx sections so they
    stay visually identical. ``rows`` shape mirrors the per-category
    output from ``_aggregate_scenario_line_items_by_category``: a
    ``{year: {label: amount}}`` dict for the chosen category.
    """
    section_label(ws, start_row, title, span_cols=len(year_cols) + 1)
    cur = start_row + 1

    # Drop labels whose total across all year columns is exactly $0 — clean
    # presentation. Legacy free-text OpEx data has placeholder rows from
    # before the dropdown enforcement landed; surfacing them as $0 lines
    # mixed with real values makes the LP read the table as duplicated /
    # half-finished. A row is kept if it has any non-zero year.
    labels = sorted({
        label
        for year_data in rows.values()
        for label in year_data
        if any(rows.get(y, {}).get(label, Decimal(0)) != 0 for y in year_cols)
    })
    if not labels:
        ws.cell(row=cur, column=1, value=empty_hint).font = FONT_HINT
        return cur + 1

    for label in labels:
        ws.cell(row=cur, column=1, value=label).font = FONT_VALUE
        for col_offset, year in enumerate(year_cols):
            value = rows.get(year, {}).get(label, Decimal(0))
            cell = ws.cell(row=cur, column=2 + col_offset, value=_to_excel_number(value))
            cell.number_format = ACCOUNTING
            cell.font = FONT_VALUE
            cell.alignment = ALIGN_RIGHT
        cur += 1
    _ = registry  # accepted for future per-row named ranges; not used today
    return cur


# ── Underwriting Cash Flow sheet ──────────────────────────────────────────────


def _build_uw_cashflow(ws, registry: CellRegistry, ctx: dict) -> None:
    """Annual cash flow: NOI / Capital Events / Levered / Unlevered / DS / DSCR / Cum LCF."""
    cash_flows: dict[UUID, list[CashFlow]] = ctx["cash_flows"]
    cash_flow_items: dict[UUID, list[CashFlowLineItem]] = ctx["cash_flow_items"]

    annual = _aggregate_scenario_annual(cash_flows)
    annual_items = _aggregate_scenario_line_items(cash_flow_items)
    capital_events_by_year = _capital_events_by_year(annual_items)
    max_year = min(max(annual) if annual else 0, 10)
    year_cols = list(range(0, max(max_year, 1) + 1))

    set_widths(ws, [30, *([14] * len(year_cols))])
    section_label(
        ws, 1, "Cash Flow — Annual (scenario-wide)", span_cols=len(year_cols) + 1
    )
    header_row(ws, 2, ["Line Item", *[f"Y{y}" for y in year_cols]])

    cur_row = 3

    def write_series(label: str, source: dict[int, Decimal], range_name: str | None,
                     fmt: str = ACCOUNTING) -> None:
        nonlocal cur_row
        ws.cell(row=cur_row, column=1, value=label).font = FONT_LABEL
        for col_offset, year in enumerate(year_cols):
            value = source.get(year, Decimal(0))
            cell = ws.cell(row=cur_row, column=2 + col_offset, value=_to_excel_number(value))
            cell.number_format = fmt
            cell.font = FONT_VALUE
            cell.alignment = ALIGN_RIGHT
        if range_name and year_cols:
            registry.register_range(
                range_name, ws.title, cur_row, cur_row, col=2,
                end_col=1 + len(year_cols),
            )
        cur_row += 1

    noi_series = {y: annual.get(y, {}).get("noi", Decimal(0)) for y in year_cols}
    debt_series = {y: annual.get(y, {}).get("debt_service", Decimal(0)) for y in year_cols}
    ncf_series = {y: annual.get(y, {}).get("net_cash_flow", Decimal(0)) for y in year_cols}

    write_series("NOI", noi_series, "r_uw_cf_noi")
    write_series("Capital Events (acq + exit)", capital_events_by_year, "r_uw_cf_capital_events")
    write_series("Debt Service", debt_series, "r_uw_cf_debt_service")
    write_series("Levered Cash Flow", ncf_series, "r_uw_cf_levered")

    unlevered_series = {
        y: noi_series.get(y, Decimal(0)) + capital_events_by_year.get(y, Decimal(0))
        for y in year_cols
    }
    write_series("Unlevered Cash Flow", unlevered_series, "r_uw_cf_unlevered")

    dscr_series = {}
    for y in year_cols:
        ds = debt_series.get(y, Decimal(0))
        dscr_series[y] = (
            (noi_series.get(y, Decimal(0)) / ds) if ds and ds != 0 else Decimal(0)
        )
    write_series("DSCR (annual)", dscr_series, "r_uw_cf_dscr", fmt="0.000")

    cumulative: dict[int, Decimal] = {}
    running = Decimal(0)
    for y in year_cols:
        running += ncf_series.get(y, Decimal(0)) + capital_events_by_year.get(y, Decimal(0))
        cumulative[y] = running
    write_series("Cumulative Cash Flow", cumulative, "r_uw_cf_cumulative")

    freeze_top(ws, row=3)
    print_landscape(ws)


# ── Investor Returns sheet ────────────────────────────────────────────────────


# Funder-type classification — drives which columns are meaningful per row.
# Debt sources care about cost-of-capital (rate, amort, balloon, debt service);
# equity sources care about returns (IRR, EM, distributions); grants/credits
# are contributed-only.
_DEBT_FUNDER_TYPES: frozenset[str] = frozenset({
    "permanent_debt", "senior_debt", "mezzanine_debt", "bridge",
    "construction_loan", "pre_development_loan", "acquisition_loan",
    "soft_loan", "bond", "owner_loan",
})
_EQUITY_FUNDER_TYPES: frozenset[str] = frozenset({
    "preferred_equity", "common_equity", "owner_investment",
})


def _funder_class(funder_type) -> str:
    """Return one of `Debt` / `Equity` / `Grant` / `Other` for display."""
    raw = (str(getattr(funder_type, "value", funder_type)) or "").lower()
    if raw in _DEBT_FUNDER_TYPES:
        return "Debt"
    if raw in _EQUITY_FUNDER_TYPES:
        return "Equity"
    if raw in ("grant", "tax_credit"):
        return "Grant"
    return "Other"


_DASH = "—"  # rendered when a column is not meaningful for a row's funder class


def _write_optional(ws, row, col, value, registry: CellRegistry, *, name: str, fmt: str) -> None:
    """Write a numeric value at (row, col) if non-None, else write the
    em-dash ``"—"`` literal. Either way the named range is registered so
    workbook structure stays stable for downstream formulas; the cell value
    is the dash string when data is missing instead of a misleading $0."""
    if value is None:
        cell = ws.cell(row=row, column=col, value=_DASH)
        cell.font = FONT_VALUE
        cell.alignment = ALIGN_RIGHT
        registry.register(name, ws.title, row, col)
    else:
        registry.write(
            ws, row, col, value,
            name=name, fmt=fmt,
            font=FONT_VALUE, align=ALIGN_RIGHT,
        )


def _build_investor_returns(ws, registry: CellRegistry, ctx: dict) -> None:
    """Source Returns — per-CapitalModule view with per-class column semantics.

    Layout: ``Module | Funder Type | Class | Principal | Rate | Total DS |
    Distributions | Return $ | Return %``.

    Per-class fill: only the columns meaningful to a row's funder class
    carry numeric values; the rest render the em-dash ``"—"`` so the LP
    can tell at a glance that "$0" never means "missing data".

      Debt rows: Rate = ``source.interest_rate_pct``; Total DS = sum of
        ``WaterfallResult.cash_distributed`` for ``debt_service``-tier rows
        on this module (or "—" when no waterfall is computed); Distributions
        = "—" (debt doesn't receive distributions); Return $ = Total DS −
        Principal (= lifetime interest paid, or "—" when no DS data);
        Return % = Rate (cost of capital).
      Equity rows: Rate = pref rate from carry config (or "—"); Total DS =
        "—"; Distributions = ``cumulative_distributed`` from waterfall;
        Return $ = Distributions − Principal; Return % = ``party_irr_pct``
        from the latest waterfall period for this module.
      Grant / tax-credit / other: Principal only — every other column "—".

    Duplicate-label disambiguation: when two modules share the exact same
    label (the engine creates one ``Owner Equity`` per project, so a
    2-project deal renders two visually-identical rows), the displayed
    label is rewritten to ``"<label> (<project_name>)"`` looked up via
    the ``junctions`` table. Keeps the LP from reading two rows as one
    duplicated row.
    """
    rollup: list[dict] = ctx.get("rollup_waterfall") or []
    summary = ctx.get("rollup_summary") or {}
    totals = summary.get("totals") or {}
    capital_modules: list[CapitalModule] = ctx["capital_modules"]
    junctions: list[CapitalModuleProject] = ctx["junctions"]
    projects_by_id: dict[UUID, Project] = {p.id: p for p in ctx["projects"]}

    set_widths(ws, [30, 18, 10, 16, 10, 16, 16, 16, 12])

    section_label(ws, 1, "Source Returns — Per Capital Module", span_cols=9)
    header_row(
        ws, 2,
        ["Module", "Funder Type", "Class", "Principal", "Rate",
         "Total DS", "Distributions", "Return ($)", "Return (%)"],
    )

    # Junction-aggregated principals (one shared debt module covering N
    # projects has its principal split across N junction rows; the
    # module-level principal is their sum).
    junction_principal: dict[UUID, Decimal] = {}
    junction_projects: dict[UUID, list[UUID]] = {}
    for j in junctions:
        junction_principal[j.capital_module_id] = junction_principal.get(
            j.capital_module_id, Decimal(0)
        ) + _coerce_decimal(j.amount or 0)
        junction_projects.setdefault(j.capital_module_id, []).append(j.project_id)

    # Pre-aggregate waterfall: per-module cumulative distributions, latest
    # party IRR, and per-module debt-service totals (debt_service tier rows).
    module_distributions: dict[str, Decimal] = {}
    module_irr: dict[str, Decimal] = {}
    module_latest_period: dict[str, int] = {}
    module_debt_service_total: dict[str, Decimal] = {}
    for row in rollup:
        mid = row.get("capital_module_id")
        if not mid:
            continue
        cum = _coerce_decimal(row.get("cumulative_distributed") or 0)
        if cum > module_distributions.get(mid, Decimal(0)):
            module_distributions[mid] = cum
        period = row.get("period") or 0
        if period >= module_latest_period.get(mid, -1):
            module_latest_period[mid] = period
            irr = row.get("party_irr_pct")
            if irr is not None:
                module_irr[mid] = _coerce_pct(irr)
        if (row.get("tier_type") or "") == "debt_service":
            module_debt_service_total[mid] = (
                module_debt_service_total.get(mid, Decimal(0))
                + _coerce_decimal(row.get("cash_distributed") or 0)
            )

    # Pre-walk module labels to disambiguate duplicates by project context.
    label_counts: dict[str, int] = {}
    for module in capital_modules:
        raw = module.label or _funder_type_label(module)
        label_counts[raw] = label_counts.get(raw, 0) + 1

    def _display_label(module: CapitalModule) -> str:
        raw = module.label or _funder_type_label(module)
        if label_counts.get(raw, 0) <= 1:
            return raw
        # Disambiguate via the first project in the module's junction rows.
        proj_ids = junction_projects.get(module.id) or []
        if proj_ids:
            proj = projects_by_id.get(proj_ids[0])
            if proj and proj.name:
                return f"{raw} ({proj.name})"
        return raw

    cur_row = 3
    if not capital_modules:
        ws.cell(
            row=cur_row, column=1,
            value="(no capital modules — add Sources on the Capital Stack module to populate)",
        ).font = FONT_HINT
        cur_row += 1

    for m_idx, module in enumerate(capital_modules, start=1):
        source = module.source or {}
        carry = module.carry or {}
        mid_str = str(module.id)
        principal = junction_principal.get(module.id)
        if principal is None:
            principal = _coerce_decimal(source.get("amount") or 0)
        rate_raw = source.get("interest_rate_pct") or carry.get("io_rate_pct") or 0
        rate = _coerce_pct(rate_raw) if rate_raw else None
        funder_class = _funder_class(module.funder_type)

        # Per-class column fill — write em-dash strings where a column doesn't
        # apply, so missing data never reads as "$0" or "0%".
        if funder_class == "Debt":
            total_ds = module_debt_service_total.get(mid_str)
            distributions = None  # debt has no distributions
            if total_ds is not None and total_ds > 0:
                return_dollars = total_ds - principal
            else:
                return_dollars = None  # no DS data ⇒ blank, not -principal
            return_pct = rate
        elif funder_class == "Equity":
            total_ds = None
            distributions = module_distributions.get(mid_str)
            return_dollars = (distributions - principal) if distributions is not None else None
            return_pct = module_irr.get(mid_str)
        else:
            # Grant / tax_credit / other — only Principal is meaningful
            total_ds = None
            distributions = None
            return_dollars = None
            return_pct = None

        ws.cell(row=cur_row, column=1, value=_display_label(module)).font = FONT_VALUE
        ws.cell(row=cur_row, column=2, value=_funder_type_label(module)).font = FONT_VALUE
        ws.cell(row=cur_row, column=3, value=funder_class).font = FONT_VALUE

        registry.write(
            ws, cur_row, 4, principal,
            name=f"s_module_{m_idx}_principal_returns", fmt=ACCOUNTING,
            font=FONT_VALUE, align=ALIGN_RIGHT,
        )
        _write_optional(
            ws, cur_row, 5, rate, registry,
            name=f"s_module_{m_idx}_rate_returns", fmt=PCT,
        )
        _write_optional(
            ws, cur_row, 6, total_ds, registry,
            name=f"s_module_{m_idx}_total_ds", fmt=ACCOUNTING,
        )
        _write_optional(
            ws, cur_row, 7, distributions, registry,
            name=f"s_module_{m_idx}_distributions", fmt=ACCOUNTING,
        )
        _write_optional(
            ws, cur_row, 8, return_dollars, registry,
            name=f"s_module_{m_idx}_return_dollars", fmt=ACCOUNTING,
        )
        _write_optional(
            ws, cur_row, 9, return_pct, registry,
            name=f"s_module_{m_idx}_return_pct", fmt=PCT,
        )
        cur_row += 1

    # ── Aggregate rollup (only meaningful when a waterfall is populated) ──
    cur_row += 1
    section_label(ws, cur_row, "Scenario-Level Aggregates", span_cols=2)
    cur_row += 1

    kv_row(
        ws, cur_row, "Combined Levered IRR (scenario)",
        _coerce_pct(totals.get("combined_irr_pct") or 0),
        name="s_returns_combined_irr", registry=registry, fmt=PCT,
    ); cur_row += 1

    by_tier = _waterfall_by_tier(rollup)
    promote_total = by_tier.get("residual", {}).get("cash_total", Decimal(0)) + by_tier.get(
        "catch_up", {}
    ).get("cash_total", Decimal(0))
    kv_row(
        ws, cur_row, "GP Promote $ (catch-up + residual)",
        promote_total,
        name="s_gp_promote_dollars", registry=registry, fmt=ACCOUNTING,
    ); cur_row += 1

    if not rollup:
        cur_row += 1
        ws.cell(
            row=cur_row, column=1,
            value=(
                "(no waterfall distributions yet — Source Returns above show "
                "principal + cost-of-capital semantics; add equity tiers + "
                "compute to populate IRR / promote.)"
            ),
        ).font = FONT_HINT
        ws.merge_cells(start_row=cur_row, start_column=1, end_row=cur_row, end_column=8)

    freeze_top(ws, row=3)
    print_landscape(ws)


# ── Per-project sheets (commit 3) ─────────────────────────────────────────────


def _build_project_sheet(
    ws,
    registry: CellRegistry,
    ctx: dict,
    project_idx: int,
    project: Project,
) -> None:
    """One sheet per project: header → Pro Forma → Cash Flow → S&U.

    Named ranges use the ``p{n}_`` prefix from plan §4 — outputs only.
    Per-project *inputs* live on the Assumptions sheet (Block B) and use
    the same prefix; outputs are distinct names so the registry doesn't
    collide. Layout matches the underwriting rollup sheets so an LP can
    open a project sheet and read it the same way as the scenario summary.
    """
    inputs_by_project: dict[UUID, OperationalInputs] = ctx["operational_inputs"]
    use_lines_by_project: dict[UUID, list[UseLine]] = ctx["use_lines"]
    cash_flows_by_project: dict[UUID, list[CashFlow]] = ctx["cash_flows"]
    cash_flow_items_by_project: dict[UUID, list[CashFlowLineItem]] = ctx["cash_flow_items"]
    outputs_by_project: dict[UUID, "OperationalOutputs"] = ctx["outputs"]
    capital_modules: list[CapitalModule] = ctx["capital_modules"]
    junctions: list[CapitalModuleProject] = ctx["junctions"]

    inputs = inputs_by_project.get(project.id)
    use_lines = use_lines_by_project.get(project.id, [])
    cash_flows = cash_flows_by_project.get(project.id, [])
    line_items = cash_flow_items_by_project.get(project.id, [])
    outputs = outputs_by_project.get(project.id)

    annual = _aggregate_annual(cash_flows)
    annual_items = _annual_line_items(line_items)
    capital_events_by_year = _capital_events_by_year(annual_items)
    max_year = min(max(annual) if annual else 0, 10)
    year_cols = list(range(0, max(max_year, 1) + 1))

    set_widths(ws, [30, *([14] * len(year_cols))])

    # ── Project header ─────────────────────────────────────────────────────
    ws.cell(
        row=1, column=1,
        value=f"P{project_idx} — {project.name or 'Project'}",
    ).font = FONT_TITLE
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(year_cols) + 1)
    ws.row_dimensions[1].height = 24

    # Top-of-sheet hyperlinks back to the rollup + glossary
    ws.cell(
        row=2, column=1,
        value='=HYPERLINK("#\'Underwriting Summary\'!A1", "← Underwriting Summary")',
    ).font = FONT_SUBTITLE
    ws.cell(
        row=2, column=2,
        value='=HYPERLINK("#\'Glossary & Methodology\'!A1", "Glossary →")',
    ).font = FONT_SUBTITLE

    section_label(ws, 4, "Project KPIs", span_cols=2)
    cur = 5
    kv_row(
        ws, cur, "Project Type",
        getattr(project, "deal_type", "") or "",
        name=f"p{project_idx}_uw_project_type", registry=registry,
    ); cur += 1
    kv_row(
        ws, cur, "Total Project Cost",
        _safe_decimal(outputs, "total_project_cost"),
        name=f"p{project_idx}_total_project_cost", registry=registry,
        fmt=ACCOUNTING, hero=True,
    ); cur += 1
    kv_row(
        ws, cur, "Equity Required",
        _safe_decimal(outputs, "equity_required"),
        name=f"p{project_idx}_equity_required", registry=registry,
        fmt=ACCOUNTING, hero=True,
    ); cur += 1
    kv_row(
        ws, cur, "Stabilized NOI",
        _safe_decimal(outputs, "noi_stabilized"),
        name=f"p{project_idx}_noi_stabilized", registry=registry,
        fmt=ACCOUNTING, hero=True,
    ); cur += 1
    kv_row(
        ws, cur, "DSCR",
        _safe_decimal(outputs, "dscr"),
        name=f"p{project_idx}_dscr", registry=registry,
        fmt="0.000", hero=True,
    ); cur += 1
    kv_row(
        ws, cur, "Cap Rate on Cost",
        _pct_value(outputs, "cap_rate_on_cost_pct"),
        name=f"p{project_idx}_cap_rate", registry=registry,
        fmt=PCT, hero=True,
    ); cur += 1
    kv_row(
        ws, cur, "Debt Yield",
        _pct_value(outputs, "debt_yield_pct"),
        name=f"p{project_idx}_debt_yield", registry=registry,
        fmt=PCT, hero=True,
    ); cur += 1
    kv_row(
        ws, cur, "Levered IRR",
        _pct_value(outputs, "project_irr_levered"),
        name=f"p{project_idx}_levered_irr", registry=registry,
        fmt=PCT, hero=True,
    ); cur += 1
    kv_row(
        ws, cur, "Unlevered IRR",
        _pct_value(outputs, "project_irr_unlevered"),
        name=f"p{project_idx}_unlevered_irr", registry=registry,
        fmt=PCT, hero=True,
    ); cur += 1
    kv_row(
        ws, cur, "Total Timeline (months)",
        _safe_decimal(outputs, "total_timeline_months"),
        name=f"p{project_idx}_timeline_months", registry=registry,
        fmt=INT_COMMA,
    ); cur += 1

    # ── Project Pro Forma ──────────────────────────────────────────────────
    pf_row = cur + 2
    section_label(
        ws, pf_row, "Project Pro Forma — Annual",
        span_cols=len(year_cols) + 1,
    )
    header_row(ws, pf_row + 1, ["Line Item", *[f"Y{y}" for y in year_cols]])
    pf_data = pf_row + 2
    pf_rows: list[tuple[str, str, str | None]] = [
        ("Gross Revenue", "gross_revenue", f"r_p{project_idx}_gross_revenue"),
        ("Vacancy Loss", "vacancy_loss", None),
        ("EGI", "effective_gross_income", f"r_p{project_idx}_egi"),
        ("Operating Expenses", "operating_expenses", f"r_p{project_idx}_opex"),
        ("CapEx Reserve", "capex_reserve", None),
        ("NOI", "noi", f"r_p{project_idx}_noi"),
    ]
    for label, field, range_name in pf_rows:
        ws.cell(row=pf_data, column=1, value=label).font = FONT_LABEL
        for col_offset, year in enumerate(year_cols):
            value = annual.get(year, {}).get(field, Decimal(0))
            cell = ws.cell(row=pf_data, column=2 + col_offset, value=_to_excel_number(value))
            cell.number_format = ACCOUNTING
            cell.font = FONT_VALUE
            cell.alignment = ALIGN_RIGHT
        if range_name and year_cols:
            registry.register_range(
                range_name, ws.title, pf_data, pf_data,
                col=2, end_col=1 + len(year_cols),
            )
        pf_data += 1

    # ── Project Cash Flow ──────────────────────────────────────────────────
    cf_row = pf_data + 1
    section_label(
        ws, cf_row, "Project Cash Flow — Annual",
        span_cols=len(year_cols) + 1,
    )
    header_row(ws, cf_row + 1, ["Line Item", *[f"Y{y}" for y in year_cols]])
    cf_data = cf_row + 2

    noi_series = {y: annual.get(y, {}).get("noi", Decimal(0)) for y in year_cols}
    debt_series = {y: annual.get(y, {}).get("debt_service", Decimal(0)) for y in year_cols}
    ncf_series = {y: annual.get(y, {}).get("net_cash_flow", Decimal(0)) for y in year_cols}

    def write_proj_series(label: str, source: dict[int, Decimal], range_name: str | None,
                          fmt: str = ACCOUNTING) -> None:
        nonlocal cf_data
        ws.cell(row=cf_data, column=1, value=label).font = FONT_LABEL
        for col_offset, year in enumerate(year_cols):
            value = source.get(year, Decimal(0))
            cell = ws.cell(row=cf_data, column=2 + col_offset, value=_to_excel_number(value))
            cell.number_format = fmt
            cell.font = FONT_VALUE
            cell.alignment = ALIGN_RIGHT
        if range_name and year_cols:
            registry.register_range(
                range_name, ws.title, cf_data, cf_data,
                col=2, end_col=1 + len(year_cols),
            )
        cf_data += 1

    write_proj_series("NOI", noi_series, f"r_p{project_idx}_cf_noi")
    write_proj_series(
        "Capital Events", capital_events_by_year, f"r_p{project_idx}_cf_capital_events"
    )
    write_proj_series("Debt Service", debt_series, f"r_p{project_idx}_cf_debt_service")
    write_proj_series("Levered Cash Flow", ncf_series, f"r_p{project_idx}_cf_levered")

    unlevered_series = {
        y: noi_series.get(y, Decimal(0)) + capital_events_by_year.get(y, Decimal(0))
        for y in year_cols
    }
    write_proj_series(
        "Unlevered Cash Flow", unlevered_series, f"r_p{project_idx}_cf_unlevered"
    )

    cumulative: dict[int, Decimal] = {}
    running = Decimal(0)
    for y in year_cols:
        running += ncf_series.get(y, Decimal(0)) + capital_events_by_year.get(y, Decimal(0))
        cumulative[y] = running
    write_proj_series("Cumulative Cash Flow", cumulative, f"r_p{project_idx}_cf_cumulative")

    # ── Project S&U ────────────────────────────────────────────────────────
    su_row = cf_data + 1
    section_label(ws, su_row, "Project Sources & Uses", span_cols=4)
    header_row(ws, su_row + 1, ["Side", "Label", "Amount", "Notes"])
    su_data = su_row + 2

    uses_total = Decimal(0)
    by_phase: dict[str, Decimal] = {}
    for ul in use_lines:
        phase = str(getattr(ul.phase, "value", ul.phase) or "")
        if phase == "exit":
            continue
        amt = _coerce_decimal(ul.amount or 0)
        by_phase[phase] = by_phase.get(phase, Decimal(0)) + amt
        uses_total += amt
    for phase, amount in sorted(by_phase.items()):
        ws.cell(row=su_data, column=1, value="Use").font = FONT_VALUE
        ws.cell(row=su_data, column=2, value=phase.replace("_", " ").title()).font = FONT_VALUE
        ws.cell(row=su_data, column=3, value=_to_excel_number(amount)).number_format = ACCOUNTING
        su_data += 1
    ws.cell(row=su_data, column=1, value="Use").font = FONT_LABEL
    ws.cell(row=su_data, column=2, value="Total Uses").font = FONT_LABEL
    registry.write(
        ws, su_data, 3, uses_total,
        name=f"p{project_idx}_uw_total_uses", fmt=ACCOUNTING,
        font=FONT_LABEL, align=ALIGN_RIGHT,
    )
    su_data += 2

    # Sources for THIS project — junction-scoped (each capital module's
    # share for this project, not the scenario-wide commitment).
    junction_for_project: dict[UUID, Decimal] = {}
    for j in junctions:
        if j.project_id != project.id:
            continue
        junction_for_project[j.capital_module_id] = junction_for_project.get(
            j.capital_module_id, Decimal(0)
        ) + _coerce_decimal(j.amount or 0)

    sources_total = Decimal(0)
    for module in capital_modules:
        if module.id not in junction_for_project:
            continue
        amount = junction_for_project[module.id]
        ws.cell(row=su_data, column=1, value="Source").font = FONT_VALUE
        ws.cell(
            row=su_data, column=2,
            value=module.label or _funder_type_label(module),
        ).font = FONT_VALUE
        ws.cell(row=su_data, column=3, value=_to_excel_number(amount)).number_format = ACCOUNTING
        ws.cell(
            row=su_data, column=4,
            value=_funder_type_label(module),
        ).font = FONT_HINT
        sources_total += amount
        su_data += 1

    if not junction_for_project:
        ws.cell(
            row=su_data, column=1,
            value="(no capital module attached to this project)",
        ).font = FONT_HINT
        su_data += 1

    ws.cell(row=su_data, column=1, value="Source").font = FONT_LABEL
    ws.cell(row=su_data, column=2, value="Total Sources").font = FONT_LABEL
    registry.write(
        ws, su_data, 3, sources_total,
        name=f"p{project_idx}_uw_total_sources", fmt=ACCOUNTING,
        font=FONT_LABEL, align=ALIGN_RIGHT,
    )
    su_data += 1

    gap = uses_total - sources_total
    ws.cell(row=su_data, column=1, value="Δ").font = FONT_LABEL
    ws.cell(row=su_data, column=2, value="Gap (Uses − Sources)").font = FONT_LABEL
    registry.write(
        ws, su_data, 3, gap,
        name=f"p{project_idx}_uw_gap", fmt=ACCOUNTING,
        font=FONT_LABEL, align=ALIGN_RIGHT,
    )

    # Suppress the inputs param when truthy via a no-op reference — keeps
    # the function signature stable for future per-project pulls without
    # ruff flagging the unused local.
    _ = inputs

    freeze_top(ws, row=4)
    print_landscape(ws)


# ── Sheet-builder support helpers (commit 2) ──────────────────────────────────


def _aggregate_scenario_line_items(
    items_by_project: dict[UUID, list[CashFlowLineItem]],
) -> dict[int, dict[str, Decimal]]:
    combined: dict[int, dict[str, Decimal]] = {}
    for items in items_by_project.values():
        per_year = _annual_line_items(items)
        for year, by_label in per_year.items():
            bucket = combined.setdefault(year, {})
            for label, amount in by_label.items():
                bucket[label] = bucket.get(label, Decimal(0)) + amount
    return combined


def _aggregate_scenario_line_items_by_category(
    items_by_project: dict[UUID, list[CashFlowLineItem]],
) -> dict[str, dict[int, dict[str, Decimal]]]:
    """Returns ``{category: {year: {label: amount}}}``.

    Aggregates across projects per LP feedback Option C: same exact label
    across projects → one combined row, no project-name suffixing. Labels
    are stripped of leading/trailing whitespace defensively so e.g.
    ``"CapEx Reserve"`` and ``"CapEx Reserve "`` collapse into one row.

    Categories follow ``LineItemCategory``: ``income`` / ``expense`` /
    ``debt_service`` / ``capex_reserve`` / ``capital_event``. The Pro Forma
    splits this into separate Revenue (income) and OpEx (expense) tables;
    capital events are summed for the Cash Flow sheet's "Capital Events"
    row.
    """
    out: dict[str, dict[int, dict[str, Decimal]]] = {}
    for items in items_by_project.values():
        for li in items:
            year = _period_to_year(li.period)
            category = str(getattr(li.category, "value", li.category) or "")
            label = (li.label or "").strip()
            # Expense labels get folded onto the canonical OpEx vocabulary
            # so legacy free-text duplicates ("Water / Sewer" vs "Water/Sewer",
            # "Property Tax" vs "Real Estate Taxes") collapse into one row.
            # Income labels stay as-is — Phase B1 Option C dedup already
            # handles cross-project name collisions for revenue streams.
            if category == "expense":
                label = normalize_opex_label(label)
            cat_dict = out.setdefault(category, {})
            year_dict = cat_dict.setdefault(year, {})
            year_dict[label] = year_dict.get(label, Decimal(0)) + _coerce_decimal(
                li.net_amount or 0
            )
    return out


_CAPITAL_EVENT_PREFIXES = ("Refi —", "Acquisition", "Sale", "Prepay", "Exit", "Purchase Price", "Closing Costs")


def _capital_events_by_year(
    annual_items: dict[int, dict[str, Decimal]],
) -> dict[int, Decimal]:
    """Sum capital-event line items per year (acquisition outflows, exit proceeds).

    Used by the per-project sheets which still consume the legacy
    ``annual_items`` shape. The category-aware path
    (``_aggregate_scenario_line_items_by_category``) is preferred for new
    code — filter by ``"capital_event"`` category there.
    """
    out: dict[int, Decimal] = {}
    for year, by_label in annual_items.items():
        total = Decimal(0)
        for label, amount in by_label.items():
            if any(label.startswith(p) for p in _CAPITAL_EVENT_PREFIXES):
                total += amount
        out[year] = total
    return out


def _worst_dscr(per_project: list[dict]) -> Decimal | None:
    """Lowest non-null DSCR across projects (covenant binds at the weakest one).

    Retained for callers that want the per-loan worst-case view; the
    Underwriting Summary now leads with the combined DSCR instead (see
    ``_combined_dscr``) per LP feedback.
    """
    candidates = [
        _coerce_decimal(p.get("dscr"))
        for p in per_project
        if p.get("dscr") is not None
    ]
    return min(candidates) if candidates else None


def _combined_dscr(per_project: list[dict]) -> Decimal | None:
    """Combined DSCR = Σ NOI_stabilized / Σ Debt Service across projects.

    The engine doesn't materialize a per-project ``debt_service`` scalar;
    we reverse-derive ``ds_per_project = noi_stabilized / dscr`` and sum
    both sides to get a coverage figure that's a singular ratio rather
    than a worst-case across loans. Returns None when nothing has a
    non-zero DSCR (compute hasn't run, or no debt is sized).
    """
    total_noi = Decimal(0)
    total_ds = Decimal(0)
    for p in per_project:
        noi = _coerce_decimal(p.get("noi_stabilized") or 0)
        dscr = _coerce_decimal(p.get("dscr") or 0)
        if dscr <= 0 or noi <= 0:
            continue
        total_noi += noi
        total_ds += noi / dscr
    return (total_noi / total_ds) if total_ds > 0 else None


def _combined_unlevered_irr(
    cash_flows_by_project: dict[UUID, list[CashFlow]],
) -> Decimal | None:
    """Combined unlevered IRR — XIRR over per-period unlevered CF totals.

    Sums each project's unlevered cash flow (NCF + DS) per period, then
    runs the engine's pyxirr helper. Mirrors the rollup engine's path
    for the levered version (``rollup_irr``) but reverses out debt
    service so the result represents the asset-level return.
    Returns None on the typical no-pyxirr / no-sign-change cases.
    """
    from app.engines.cashflow import _compute_xirr  # late import — keep this module's imports lean

    period_totals: dict[int, Decimal] = {}
    for cf_list in cash_flows_by_project.values():
        for cf in cf_list:
            ncf = _coerce_decimal(cf.net_cash_flow or 0)
            ds = _coerce_decimal(cf.debt_service or 0)
            unlevered = ncf + ds
            period_totals[cf.period] = period_totals.get(cf.period, Decimal(0)) + unlevered
    if not period_totals:
        return None
    series = [period_totals[p] for p in sorted(period_totals)]
    pct_whole = _compute_xirr(series)
    if pct_whole == 0:
        return None
    # _compute_xirr returns percent as whole number (e.g. 12.34 = 12.34%);
    # PCT format wants a fraction.
    return pct_whole / Decimal(100)


def _combined_em(
    rollup_waterfall: list[dict],
    capital_modules: list[CapitalModule],
) -> Decimal | None:
    """Combined Equity Multiple = Σ equity distributions ÷ Σ equity contributions.

    Walks the waterfall rollup for cumulative_distributed per equity
    module, sums those, divides by the sum of equity-module commitments
    (``source.amount``). Returns None when there's no equity stack OR no
    waterfall data — better than reading a misleading 0 in the LP's eye.
    """
    by_module: dict[str, Decimal] = {}
    for row in rollup_waterfall:
        mid = row.get("capital_module_id")
        if not mid:
            continue
        cum = _coerce_decimal(row.get("cumulative_distributed") or 0)
        if cum > by_module.get(mid, Decimal(0)):
            by_module[mid] = cum

    total_dist = Decimal(0)
    total_contrib = Decimal(0)
    for module in capital_modules:
        if _funder_class(module.funder_type) != "Equity":
            continue
        commitment = _coerce_decimal((module.source or {}).get("amount") or 0)
        if commitment <= 0:
            continue
        total_contrib += commitment
        total_dist += by_module.get(str(module.id), Decimal(0))
    return (total_dist / total_contrib) if total_contrib > 0 else None


def _coc_year_one(
    rollup_waterfall: list[dict],
    capital_modules: list[CapitalModule],
) -> Decimal | None:
    """Cash-on-Cash Year 1 = Σ equity distributions in periods 1-12 ÷ contributions.

    Per CRE convention "year 1" = first 12 months from deal close. If the
    deal is still mid-construction during year 1, this comes out 0 or
    negative — that's the honest number; the LP reads it in context.
    Returns None when there's no equity stack with non-zero commitments.
    """
    y1_per_module: dict[str, Decimal] = {}
    for row in rollup_waterfall:
        mid = row.get("capital_module_id")
        period = row.get("period") or 0
        if not mid or period < 1 or period > 12:
            continue
        amount = _coerce_decimal(row.get("cash_distributed") or 0)
        y1_per_module[mid] = y1_per_module.get(mid, Decimal(0)) + amount

    total_y1_dist = Decimal(0)
    total_contrib = Decimal(0)
    for module in capital_modules:
        if _funder_class(module.funder_type) != "Equity":
            continue
        commitment = _coerce_decimal((module.source or {}).get("amount") or 0)
        if commitment <= 0:
            continue
        total_contrib += commitment
        total_y1_dist += y1_per_module.get(str(module.id), Decimal(0))
    return (total_y1_dist / total_contrib) if total_contrib > 0 else None


def _sum_per_project_field(per_project: list[dict], field: str) -> Decimal:
    return sum(
        (_coerce_decimal(p.get(field) or 0) for p in per_project),
        Decimal(0),
    )


def _longest_hold_months(per_project: list[dict]) -> int | None:
    candidates = [
        int(p.get("total_timeline_months") or 0)
        for p in per_project
        if p.get("total_timeline_months")
    ]
    return max(candidates) if candidates else None


def _project_sheet_name(idx: int, project_name: str | None) -> str:
    """Build the per-project sheet name (commit 3 will create these sheets).

    Format ``P{n} {Name}`` truncated to Excel's 31-char ceiling. The exact
    rule comes from plan §2: prefix is `P` + 1- or 2-digit ordinal + space
    (4 chars max), then up to ``PROJECT_SHEET_NAME_BUDGET`` chars of name.
    """
    name = (project_name or "").strip()
    truncated = name[:PROJECT_SHEET_NAME_BUDGET].rstrip()
    return f"P{idx} {truncated}".rstrip()


def _is_lp_funder(funder_type) -> bool:
    label = (str(getattr(funder_type, "value", funder_type)) or "").lower()
    return "common_equity" in label or "preferred" in label or "lp" in label


def _is_gp_funder(funder_type) -> bool:
    label = (str(getattr(funder_type, "value", funder_type)) or "").lower()
    return "owner_equity" in label or label == "gp" or "developer" in label


def _lp_gp_irr_from_rollup(
    rollup: list[dict], capital_modules: list[CapitalModule]
) -> tuple[Decimal | None, Decimal | None]:
    """Pull LP and GP IRR percentages from the latest waterfall row per module.

    Returns (LP IRR fraction, GP IRR fraction) — None when no eligible rows.
    """
    by_module: dict[str, dict] = {}
    for row in rollup:
        mid = row.get("capital_module_id")
        if not mid:
            continue
        prior = by_module.get(mid)
        if prior is None or (row.get("period") or 0) > (prior.get("period") or 0):
            by_module[mid] = row
    module_index = {str(m.id): m for m in capital_modules}

    lp_vals: list[Decimal] = []
    gp_vals: list[Decimal] = []
    for mid, row in by_module.items():
        module = module_index.get(mid)
        if module is None or row.get("party_irr_pct") is None:
            continue
        irr_fraction = _coerce_pct(row.get("party_irr_pct"))
        if _is_lp_funder(module.funder_type):
            lp_vals.append(irr_fraction)
        elif _is_gp_funder(module.funder_type):
            gp_vals.append(irr_fraction)

    lp_irr = sum(lp_vals, Decimal(0)) / Decimal(len(lp_vals)) if lp_vals else None
    gp_irr = sum(gp_vals, Decimal(0)) / Decimal(len(gp_vals)) if gp_vals else None
    return lp_irr, gp_irr


def _equity_multiples_from_rollup(
    rollup: list[dict], capital_modules: list[CapitalModule]
) -> tuple[Decimal | None, Decimal | None]:
    """Compute LP / GP equity multiples from cumulative distributed totals.

    EM = total distributions ÷ total contributions. We don't have direct
    contribution data here, so use ``cumulative_distributed`` as the
    numerator and the module's source amount as the denominator (the
    committed amount is the contribution proxy for equity modules).
    """
    by_module: dict[str, Decimal] = {}
    for row in rollup:
        mid = row.get("capital_module_id")
        if not mid:
            continue
        cum = _coerce_decimal(row.get("cumulative_distributed") or 0)
        prev = by_module.get(mid)
        if prev is None or cum > prev:
            by_module[mid] = cum

    lp_dist = lp_contrib = Decimal(0)
    gp_dist = gp_contrib = Decimal(0)
    for module in capital_modules:
        commitment = _coerce_decimal((module.source or {}).get("amount") or 0)
        cum = by_module.get(str(module.id), Decimal(0))
        if _is_lp_funder(module.funder_type):
            lp_dist += cum
            lp_contrib += commitment
        elif _is_gp_funder(module.funder_type):
            gp_dist += cum
            gp_contrib += commitment

    lp_em = (lp_dist / lp_contrib) if lp_contrib > 0 else None
    gp_em = (gp_dist / gp_contrib) if gp_contrib > 0 else None
    return lp_em, gp_em


def _to_excel_number(value):
    """Coerce a Decimal/None to a plain float-or-blank for openpyxl cells.

    Returns "" for None so empty cells render blank, not as the literal
    string "None". Mirrors ``_workbook_helpers.to_excel_value`` but is
    inlined here for the hot per-cell path.
    """
    if value is None:
        return ""
    if isinstance(value, Decimal):
        f = float(value)
        return int(f) if f == int(f) else round(f, 6)
    return value


def _build_assumptions(ws, registry: CellRegistry, ctx: dict) -> None:
    """Assumptions sheet: scenario-level / per-project / capital-stack blocks."""
    scenario: DealModel = ctx["scenario"]
    projects: list[Project] = ctx["projects"]
    inputs_by_project: dict[UUID, OperationalInputs] = ctx["operational_inputs"]
    use_lines_by_project: dict[UUID, list[UseLine]] = ctx["use_lines"]
    unit_mix_by_project: dict[UUID, list[UnitMix]] = ctx["unit_mix"]
    capital_modules: list[CapitalModule] = ctx["capital_modules"]
    junctions: list[CapitalModuleProject] = ctx["junctions"]

    # Layout: 1 (label) + up to MAX_PROJECTS_PER_SCENARIO project columns.
    label_w = 36
    project_col_widths = [22] * MAX_PROJECTS_PER_SCENARIO
    set_widths(ws, [label_w, *project_col_widths])

    # ── Block A: Scenario-level ────────────────────────────────────────────
    # Default project's OperationalInputs carries scenario-level conceptual
    # fields (hold years, exit cap, reserve months, etc.) since these don't
    # vary per project today. When per-project becomes meaningful, this
    # block becomes the "default project" snapshot.
    default_project = projects[0] if projects else None
    default_inputs = (
        inputs_by_project.get(default_project.id) if default_project else None
    )

    section_label(ws, 1, "A. Scenario-Level Assumptions", span_cols=2)
    row = 2
    kv_row(ws, row, "Scenario Name", scenario.name,
           name="s_assumptions_scenario_name", registry=registry); row += 1
    kv_row(ws, row, "NOI Basis", _noi_basis_label(scenario.income_mode),
           name="s_assumptions_noi_basis", registry=registry); row += 1
    # `project_type` is typed Mapped[ProjectType] but stored as String(60)
    # — SQLAlchemy doesn't auto-coerce on read, so it comes back as a bare
    # string in production. Use the same safe pattern as _funder_type_label.
    project_type_label = getattr(
        scenario.project_type, "value", scenario.project_type
    ) or ""
    kv_row(ws, row, "Project Type (default)", str(project_type_label),
           name="s_assumptions_project_type", registry=registry); row += 1
    kv_row(
        ws, row, "Hold Period (years)",
        _safe_decimal(default_inputs, "hold_period_years"),
        name="s_hold_years", registry=registry, fmt=INT_COMMA,
    ); row += 1
    kv_row(
        ws, row, "Exit Cap Rate",
        _pct_value(default_inputs, "exit_cap_rate_pct"),
        name="s_exit_cap_rate", registry=registry, fmt=PCT,
    ); row += 1
    kv_row(
        ws, row, "OpEx Growth Rate (annual)",
        _pct_value(default_inputs, "expense_growth_rate_pct_annual"),
        name="s_opex_growth_rate", registry=registry, fmt=PCT,
    ); row += 1
    kv_row(
        ws, row, "Operating Reserve (months)",
        _safe_decimal(default_inputs, "operation_reserve_months"),
        name="s_operating_reserve_months", registry=registry, fmt=INT_COMMA,
    ); row += 1
    kv_row(
        ws, row, "Initial Occupancy",
        _pct_value(default_inputs, "initial_occupancy_pct"),
        name="s_initial_occupancy", registry=registry, fmt=PCT,
    ); row += 1
    kv_row(
        ws, row, "Asset Mgmt Fee",
        _pct_value(default_inputs, "asset_mgmt_fee_pct"),
        name="s_asset_mgmt_fee", registry=registry, fmt=PCT,
    ); row += 1

    # ── Block B: Per-project ───────────────────────────────────────────────
    block_b_row = row + 2
    section_label(
        ws, block_b_row, "B. Per-Project Assumptions",
        span_cols=1 + max(len(projects), 1),
    )
    header_row(ws, block_b_row + 1, ["Concept", *_project_column_labels(projects)])

    metrics = _per_project_metric_specs()
    for offset, (label, key, fmt, prefix) in enumerate(metrics):
        r = block_b_row + 2 + offset
        ws.cell(row=r, column=1, value=label).font = FONT_LABEL
        ws.cell(row=r, column=1).alignment = ALIGN_LEFT
        for proj_idx, project in enumerate(projects, start=1):
            value = _per_project_value(
                key,
                project,
                inputs_by_project.get(project.id),
                use_lines_by_project.get(project.id, []),
                unit_mix_by_project.get(project.id, []),
            )
            registry.write(
                ws,
                r,
                1 + proj_idx,
                value,
                name=f"p{proj_idx}_{prefix}",
                fmt=fmt,
                font=FONT_VALUE,
                align=ALIGN_RIGHT,
            )
    next_row = block_b_row + 2 + len(metrics)

    # ── Block C: Capital Stack ─────────────────────────────────────────────
    block_c_row = next_row + 2
    section_label(ws, block_c_row, "C. Capital Stack", span_cols=6)
    header_row(
        ws,
        block_c_row + 1,
        ["Module", "Funder Type", "Principal", "Rate", "Auto-Sized?", "Covers"],
    )

    junction_count_by_module: dict[UUID, int] = {}
    for j in junctions:
        junction_count_by_module[j.capital_module_id] = (
            junction_count_by_module.get(j.capital_module_id, 0) + 1
        )

    for m_idx, module in enumerate(capital_modules, start=1):
        r = block_c_row + 1 + m_idx
        source = module.source or {}
        carry = module.carry or {}
        principal = source.get("amount") or 0
        rate = source.get("interest_rate_pct") or carry.get("io_rate_pct") or 0
        auto_size = bool(source.get("auto_size"))
        is_shared = junction_count_by_module.get(module.id, 0) > 1

        ws.cell(row=r, column=1, value=module.label or "—").font = FONT_VALUE
        ws.cell(row=r, column=2, value=_funder_type_label(module)).font = FONT_VALUE
        registry.write(
            ws, r, 3, _coerce_decimal(principal),
            name=f"s_module_{m_idx}_principal", fmt=ACCOUNTING,
            font=FONT_VALUE, align=ALIGN_RIGHT,
        )
        registry.write(
            ws, r, 4, _coerce_pct(rate),
            name=f"s_module_{m_idx}_rate", fmt=PCT,
            font=FONT_VALUE, align=ALIGN_RIGHT,
        )
        ws.cell(row=r, column=5, value="Yes" if auto_size else "No").font = FONT_VALUE
        ws.cell(
            row=r, column=6,
            value=("shared (covers " + str(junction_count_by_module.get(module.id, 0)) + ")")
            if is_shared else "single project",
        ).font = FONT_VALUE

    if not capital_modules:
        ws.cell(
            row=block_c_row + 2, column=1,
            value="(no capital modules configured)",
        ).font = FONT_HINT

    freeze_top(ws, row=2)
    print_landscape(ws)


def _build_glossary(ws, registry: CellRegistry, ctx: dict) -> None:
    """Glossary & Methodology sheet — driven by FINANCIAL_MODEL.md.

    Filters parsed metrics down to ``audience='investor'`` per plan §3.8.
    Lender-only metrics intentionally omitted (they'll surface in a future
    lender-package extract). The bidirectional doc/export validator
    (commits 2/3) verifies that every named range in the workbook traces
    to a row here.
    """
    set_widths(ws, [28, 60, 50, 36])
    section_label(ws, 1, "Glossary & Methodology", span_cols=4)
    header_row(ws, 2, ["Term", "Definition", "Calculation", "Reference"])

    report = parse_doc()
    investor_metrics = sorted(
        report.for_audience("investor"),
        key=lambda m: m.name.lower(),
    )

    for row_offset, metric in enumerate(investor_metrics):
        r = 3 + row_offset
        definition, calc = _split_definition_and_calc(metric)
        ws.cell(row=r, column=1, value=metric.name).font = FONT_LABEL
        ws.cell(row=r, column=1).alignment = ALIGN_LEFT
        ws.cell(row=r, column=1).border = THIN_BORDER

        ws.cell(row=r, column=2, value=definition).font = FONT_VALUE
        ws.cell(row=r, column=2).alignment = ALIGN_WRAP
        ws.cell(row=r, column=2).border = THIN_BORDER

        ws.cell(row=r, column=3, value=calc).font = FONT_VALUE
        ws.cell(row=r, column=3).alignment = ALIGN_WRAP
        ws.cell(row=r, column=3).border = THIN_BORDER

        # GitHub-anchored hyperlink → opens the doc heading in a browser.
        # Friendly label first, URL behind the click — most LPs won't have
        # local repo access but anyone with a web browser can follow it.
        anchor = _github_anchor_for(metric)
        link_url = f"{_FINANCIAL_MODEL_URL}#{anchor}"
        link_label = f"FINANCIAL_MODEL.md § {metric.name}"
        # Escape any double quotes in the label to keep the formula valid.
        safe_label = link_label.replace('"', '""')
        ws.cell(
            row=r,
            column=4,
            value=f'=HYPERLINK("{link_url}","{safe_label}")',
        ).font = FONT_VALUE
        ws.cell(row=r, column=4).alignment = ALIGN_LEFT
        ws.cell(row=r, column=4).border = THIN_BORDER

        ws.row_dimensions[r].height = 60

    # Footer caption documenting the contract
    foot = 3 + len(investor_metrics) + 1
    ws.cell(
        row=foot, column=1,
        value=(
            "Doc-driven glossary. Source of truth is docs/FINANCIAL_MODEL.md; "
            "the investor-export build runs a bidirectional validator that fails "
            "if any named range here lacks a doc entry or vice versa."
        ),
    ).font = FONT_HINT
    ws.merge_cells(start_row=foot, start_column=1, end_row=foot, end_column=4)

    freeze_top(ws, row=3)
    print_landscape(ws)


# ── Per-project assumptions metric specs ──────────────────────────────────────


def _per_project_metric_specs() -> list[tuple[str, str, str | None, str]]:
    """Rows for Block B of the Assumptions sheet.

    Each tuple: (label, lookup_key, number_format, named-range suffix).
    """
    return [
        ("Project Name", "project_name", None, "project_name"),
        ("Project Type", "project_type", None, "project_type"),
        ("Acquisition Price", "acquisition_price", ACCOUNTING, "acquisition_price"),
        ("Unit Count (existing)", "unit_count_existing", INT_COMMA, "unit_count_existing"),
        ("Unit Count (new)", "unit_count_new", INT_COMMA, "unit_count_new"),
        ("Avg In-Place Rent", "avg_in_place_rent", ACCOUNTING, "avg_in_place_rent"),
        ("Avg Market Rent", "avg_market_rent", ACCOUNTING, "avg_market_rent"),
        ("Stabilized Occupancy", "stabilized_occupancy_pct", PCT, "stabilized_occupancy"),
        ("Going-In Cap Rate", "going_in_cap_rate_pct", PCT, "going_in_cap_rate"),
        ("Exit Cap Rate", "exit_cap_rate_pct", PCT, "exit_cap_rate"),
        ("Construction Months", "construction_months", INT_COMMA, "construction_months"),
        ("Lease-Up Months", "lease_up_months", INT_COMMA, "lease_up_months"),
        ("Hold Period (years)", "hold_period_years", INT_COMMA, "hold_years"),
    ]


def _per_project_value(
    key: str,
    project: Project,
    inputs: OperationalInputs | None,
    use_lines: list[UseLine],
    unit_mix: list[UnitMix],
):
    raw = _per_project_value_raw(key, project, inputs, use_lines, unit_mix)
    # The DB stores percentages as whole numbers ("5.5" for 5.5%). The Block B
    # cell uses Excel's PCT format which expects fractions ("0.055"). Without
    # this divide-by-100 the per-project Exit Cap Rate column displays "5"
    # which Excel renders as "500.00%" — silently wrong. Block A's kv_row uses
    # _pct_value for this same conversion; this is the per-project equivalent.
    if isinstance(raw, Decimal) and key.endswith("_pct"):
        return raw / Decimal(100)
    return raw


def _per_project_value_raw(
    key: str,
    project: Project,
    inputs: OperationalInputs | None,
    use_lines: list[UseLine],
    unit_mix: list[UnitMix],
):
    if key == "project_name":
        return project.name or ""
    if key == "project_type":
        return getattr(project, "deal_type", "") or ""
    if key == "acquisition_price":
        # Heuristic: sum acquisition-phase Use lines. Commit 4 will switch
        # to Project.acquisition_price once the schema refactor lands.
        return sum(
            (_coerce_decimal(ul.amount) for ul in use_lines if _is_acquisition_phase(ul)),
            Decimal(0),
        ) or None
    if key == "avg_in_place_rent":
        return _weighted_avg_rent(unit_mix, "in_place_rent_per_unit")
    if key == "avg_market_rent":
        return _weighted_avg_rent(unit_mix, "market_rent_per_unit")
    if key == "unit_count_existing":
        return sum((um.unit_count or 0) for um in unit_mix) or None
    if inputs is None:
        return None
    return _safe_decimal(inputs, key)


def _weighted_avg_rent(unit_mix: list[UnitMix], field: str) -> Decimal | None:
    total_units = 0
    weighted = Decimal(0)
    for um in unit_mix:
        rent = getattr(um, field, None)
        units = um.unit_count or 0
        if rent is None or units <= 0:
            continue
        weighted += _coerce_decimal(rent) * Decimal(units)
        total_units += units
    if total_units <= 0:
        return None
    return weighted / Decimal(total_units)


def _is_acquisition_phase(ul: UseLine) -> bool:
    phase = str(getattr(ul.phase, "value", ul.phase) or "")
    return phase == "acquisition"


def _project_column_labels(projects: list[Project]) -> list[str]:
    labels: list[str] = []
    for idx, project in enumerate(projects, start=1):
        labels.append(f"P{idx} {(project.name or '').strip() or '—'}")
    # Pad out to MAX_PROJECTS_PER_SCENARIO so the header row width is stable.
    while len(labels) < MAX_PROJECTS_PER_SCENARIO:
        labels.append("")
    return labels


def _funder_type_label(module: CapitalModule) -> str:
    raw = getattr(module, "funder_type", None)
    if raw is None:
        return "—"
    name = getattr(raw, "value", str(raw))
    return name.replace("FunderType.", "").replace("_", " ").title()


# ── Validator-driven glossary helpers ─────────────────────────────────────────


_BOLD_DEFINITION = re.compile(r"\*\*Definition\.\*\*\s*(.*?)(?=\n\s*\n|\Z)", re.DOTALL)
_BOLD_CALC = re.compile(
    r"\*\*Calculation\.\*\*\s*(?:```[\w]*\n(.*?)```|(.*?)(?=\n\s*\n|\Z))",
    re.DOTALL,
)


def _split_definition_and_calc(metric: MetricEntry) -> tuple[str, str]:
    """Pull the labelled paragraphs out of a metric body.

    Falls back to the first paragraph (definition) and "" (calc) when the
    body doesn't follow the structured shape. Lenient on purpose so the
    bidirectional validator can grow before every entry is fully shaped.
    """
    body = metric.body
    definition_match = _BOLD_DEFINITION.search(body)
    if definition_match:
        definition = _collapse_whitespace(definition_match.group(1))
    else:
        definition = _collapse_whitespace(body.split("\n\n", 1)[0])

    calc_match = _BOLD_CALC.search(body)
    calc = ""
    if calc_match:
        calc = (calc_match.group(1) or calc_match.group(2) or "").strip()
    return definition, calc


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ── Coercion helpers (Decimal / pct / safe attr lookup) ───────────────────────


def _safe_decimal(obj, attr: str) -> Decimal | None:
    """Read ``obj.attr`` and coerce numerics to ``Decimal``; return None for missing."""
    if obj is None:
        return None
    value = getattr(obj, attr, None)
    if value is None:
        return None
    return _coerce_decimal(value)


def _pct_value(obj, attr: str) -> Decimal | None:
    """Read a percent-stored-as-whole-number field and convert to fraction.

    The DB stores percentages as e.g. ``5.5`` for 5.5%. Excel's PCT format
    expects fractions (0.055), so we divide by 100 here.
    """
    raw = _safe_decimal(obj, attr)
    if raw is None:
        return None
    return raw / Decimal(100)


def _coerce_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _coerce_pct(value) -> Decimal:
    return _coerce_decimal(value) / Decimal(100)


# Re-exports for callers that want to inline format strings without importing
# from the helpers module.
__all__ = [
    "DATE_FMT",
    "MAX_PROJECTS_PER_SCENARIO",
    "PROJECT_SHEET_NAME_BUDGET",
    "BRAND",
    "export_investor_workbook",
    "make_investor_filename",
]
