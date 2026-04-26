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
from app.models.capital import CapitalModule, CapitalModuleProject
from app.models.deal import (
    Deal,
    DealModel,
    OperationalInputs,
    UnitMix,
    UseLine,
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

    # Commit 1 sheet roster. Commits 2/3 will insert UW + per-project sheets
    # between Cover and Assumptions to reach the §2 final order.
    cover = wb.active
    cover.title = "Cover"
    _build_cover(cover, registry, ctx)

    assumptions = wb.create_sheet("Assumptions")
    _build_assumptions(assumptions, registry, ctx)

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
        "snapshot_at": datetime.now(),
    }


# ── Sheet builders ────────────────────────────────────────────────────────────


def _build_cover(ws, registry: CellRegistry, ctx: dict) -> None:
    """Cover sheet: deal/scenario title, sponsor, project list."""
    set_widths(ws, [28, 60])
    scenario: DealModel = ctx["scenario"]
    deal: Deal | None = ctx["deal"]
    org: Organization | None = ctx["org"]
    projects: list[Project] = ctx["projects"]
    snapshot_at: datetime = ctx["snapshot_at"]

    # Title block
    ws.cell(row=1, column=1, value=f"{(deal.name if deal else '—')} — {scenario.name}")
    ws.cell(row=1, column=1).font = FONT_TITLE
    ws.cell(row=1, column=1).alignment = ALIGN_LEFT
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=2)
    ws.row_dimensions[1].height = 28

    ws.cell(
        row=2, column=1,
        value=f"Snapshot as of {snapshot_at.strftime('%Y-%m-%d %H:%M')} PT",
    )
    ws.cell(row=2, column=1).font = FONT_SUBTITLE
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=2)

    # Metadata block
    section_label(ws, 4, "Deal", span_cols=2)
    kv_row(ws, 5, "Sponsor / Organization", org.name if org else "—",
           name="s_sponsor_name", registry=registry)
    kv_row(ws, 6, "Deal Name", deal.name if deal else "—",
           name="s_deal_name", registry=registry)
    kv_row(ws, 7, "Scenario Name", scenario.name,
           name="s_scenario_name", registry=registry)
    kv_row(ws, 8, "Snapshot Date", snapshot_at.date().isoformat(),
           name="s_snapshot_date", registry=registry)
    kv_row(ws, 9, "Project Count", len(projects),
           name="s_project_count", registry=registry, fmt=INT_COMMA)
    kv_row(ws, 10, "Income Mode", scenario.income_mode,
           name="s_income_mode", registry=registry)
    kv_row(ws, 11, "Scenario Active", "Yes" if scenario.is_active else "No",
           name="s_is_active", registry=registry)

    # Project list — bullets, one per row
    section_label(ws, 13, "Projects", span_cols=2)
    for idx, proj in enumerate(projects, start=1):
        row = 13 + idx
        ws.cell(row=row, column=1, value=f"  •  P{idx}").font = FONT_LABEL
        ws.cell(row=row, column=2, value=proj.name or f"Project {idx}").font = FONT_VALUE

    # Status block — Calc Status placeholder; real wiring lands in commit 2
    # alongside the Underwriting Summary rollup which already loads the
    # status-pill data path.
    status_row = 13 + max(len(projects), 1) + 2
    section_label(ws, status_row, "Status", span_cols=2)
    kv_row(
        ws,
        status_row + 1,
        "Calculation Status",
        "(populated by Underwriting Summary in next build phase)",
        name="s_calc_status_text",
        registry=registry,
    )

    # Footer hint
    foot_row = status_row + 3
    ws.cell(
        row=foot_row,
        column=1,
        value=(
            "Investor-Ready Excel Export — read-only by convention. "
            "All values hard-coded in this phase; see Glossary for source-of-truth references."
        ),
    ).font = FONT_HINT
    ws.merge_cells(start_row=foot_row, start_column=1, end_row=foot_row, end_column=2)

    freeze_top(ws, row=4)
    print_landscape(ws)


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
    kv_row(ws, row, "Income Mode", scenario.income_mode,
           name="s_assumptions_income_mode", registry=registry); row += 1
    kv_row(ws, row, "Project Type (default)", scenario.project_type.value,
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

        ws.cell(
            row=r,
            column=4,
            value=f"FINANCIAL_MODEL.md (line {metric.line})",
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
