"""Apply a scenario template's structural data to a newly-created project.

Templates are produced by ``app/exporters/template_export.py``: a full
deal-json export with property-specific dollar values and dates nulled out.
Apply seeds every entity type the extract preserves:

- income_streams / expense_lines (historical behavior, unchanged)
- debt_types / debt_terms merge into OperationalInputs (unchanged)
- unit_mix (structure only — counts/rents stripped)
- capital_modules + waterfall_tiers + draw_sources via the shared restore
  helpers in ``app/services/deal_restore.py`` (capital-module references are
  remapped to the newly created rows)
- use_lines (engine-auto rows are skipped — the deal-create flow seeds its
  own auto Dev Fee row and the engine regenerates reserve/finance-cost rows)

Milestones are deliberately NOT applied: the deal-create flow already seeds
a full default timeline with real durations per deal type, while template
milestones carry no durations/dates (stripped at extract). Use-line and
capital-module milestone FK anchors are therefore NULLed on apply and fall
back to their phase strings.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule
from app.models.deal import IncomeStream, OperatingExpenseLine, OperationalInputs
from app.models.project import Project
from app.schemas.deal import UnitMixBase
from app.services.deal_restore import (
    restore_capital_modules,
    restore_draw_sources,
    restore_use_lines,
    restore_waterfall_tiers,
)

logger = logging.getLogger(__name__)


def _drop_nones(row: dict[str, Any]) -> dict[str, Any]:
    """Remove template-stripped (nulled) keys so schema defaults apply."""
    return {k: v for k, v in row.items() if v is not None}


async def apply_template_to_project(
    session: AsyncSession,
    template_json: dict[str, Any],
    project_id: UUID,
) -> None:
    """Seed all preserved template entity types into a project/scenario."""
    for s in template_json.get("income_streams") or []:
        stream_type = s.get("stream_type") or "residential_rent"
        label = s.get("label") or "Income"
        try:
            occ = Decimal(str(s.get("stabilized_occupancy_pct") or 95))
        except Exception:
            occ = Decimal("95")
        try:
            esc = Decimal(str(s.get("escalation_rate_pct_annual") or 0))
        except Exception:
            esc = Decimal("0")
        session.add(IncomeStream(
            project_id=project_id,
            stream_type=stream_type,
            label=label,
            stabilized_occupancy_pct=occ,
            bad_debt_pct=Decimal(str(s.get("bad_debt_pct") or 0)),
            concessions_pct=Decimal(str(s.get("concessions_pct") or 0)),
            escalation_rate_pct_annual=esc,
            active_in_phases=s.get("active_in_phases") or [],
            notes=s.get("notes"),
        ))

    for e in template_json.get("expense_lines") or []:
        label = e.get("label") or "Expense"
        try:
            esc = Decimal(str(e.get("escalation_rate_pct_annual") or 3))
        except Exception:
            esc = Decimal("3")
        session.add(OperatingExpenseLine(
            project_id=project_id,
            label=label,
            annual_amount=Decimal("0"),
            per_type="flat",
            scale_with_lease_up=bool(e.get("scale_with_lease_up")),
            escalation_rate_pct_annual=esc,
            active_in_phases=e.get("active_in_phases") or [],
            notes=e.get("notes"),
        ))

    # Seed debt_types and debt_terms (Source Vehicle per loan type) from template.
    tmpl_oi = template_json.get("operational_inputs") or {}
    tmpl_debt_types = tmpl_oi.get("debt_types") or []
    tmpl_debt_terms = tmpl_oi.get("debt_terms") or {}
    if tmpl_debt_types or tmpl_debt_terms:
        oi = (await session.execute(
            select(OperationalInputs).where(OperationalInputs.project_id == project_id)
        )).scalar_one_or_none()
        if oi is not None:
            if tmpl_debt_types:
                oi.debt_types = tmpl_debt_types
            if tmpl_debt_terms:
                merged = dict(oi.debt_terms or {})
                for ft, terms in tmpl_debt_terms.items():
                    if ft not in merged:
                        merged[ft] = terms
                    elif terms.get("vehicle_id") and not merged[ft].get("vehicle_id"):
                        merged[ft] = {**merged[ft], "vehicle_id": terms["vehicle_id"]}
                oi.debt_terms = merged
            session.add(oi)

    project = await session.get(Project, project_id)
    if project is None:
        return
    scenario_id = project.scenario_id

    # ── unit_mix (JSONB on Project) — only when the project has none yet ──
    mix_rows: list[dict] = []
    for m in template_json.get("unit_mix") or []:
        try:
            mix_rows.append(
                UnitMixBase.model_validate(_drop_nones(dict(m))).model_dump(
                    mode="json", exclude_unset=True
                )
            )
        except Exception:
            logger.warning("template apply: skipped unit_mix row", exc_info=True)
    if mix_rows and not project.unit_mix:
        project.unit_mix = mix_rows

    # ── capital modules ──────────────────────────────────────────────────
    # The deal-create flow preloads equity modules before templates apply;
    # skip template modules whose label already exists on the scenario and
    # map their old ids onto the existing module so tier/draw-source wiring
    # still lands on the right row.
    existing_modules = list((await session.execute(
        select(CapitalModule).where(CapitalModule.scenario_id == scenario_id)
    )).scalars())
    existing_by_label = {m.label: m.id for m in existing_modules}

    cap_id_map: dict[str, UUID] = {}
    modules_to_create: list[dict[str, Any]] = []
    for mod in template_json.get("capital_modules") or []:
        mod = dict(mod)
        old_id = mod.get("id")
        label = mod.get("label")
        if label in existing_by_label:
            if old_id:
                cap_id_map[str(old_id)] = existing_by_label[label]
            continue
        # Template milestones are not applied — NULL the milestone anchors
        # (restore helper would do the same with an empty milestone map).
        mod["active_from_milestone_id"] = None
        mod["active_to_milestone_id"] = None
        modules_to_create.append(mod)

    await restore_capital_modules(
        session,
        scenario_id=scenario_id,
        module_payloads=modules_to_create,
        milestone_id_map={},
        cap_id_map=cap_id_map,
        log_context="template apply",
    )

    # ── use lines (skip engine-auto rows; amounts stripped → default 0) ──
    use_rows = [
        _drop_nones(dict(u))
        for u in template_json.get("use_lines") or []
        if not (
            u.get("is_auto_dev_fee")
            or u.get("is_auto_acquisition_fee")
            or u.get("is_auto_finance_cost")
        )
    ]
    await restore_use_lines(
        session,
        project_id=project_id,
        use_line_payloads=use_rows,
        cap_id_map=cap_id_map,
        milestone_id_map={},
        log_context="template apply",
    )

    # ── waterfall tiers + draw sources ───────────────────────────────────
    await restore_waterfall_tiers(
        session,
        scenario_id=scenario_id,
        tier_payloads=[_drop_nones(dict(t)) for t in template_json.get("waterfall_tiers") or []],
        cap_id_map=cap_id_map,
        default_project_id=project_id,
        log_context="template apply",
        on_missing_capital_module="null",
    )

    await restore_draw_sources(
        session,
        scenario_id=scenario_id,
        draw_source_payloads=[_drop_nones(dict(d)) for d in template_json.get("draw_sources") or []],
        cap_id_map=cap_id_map,
        default_project_id=project_id,
        log_context="template apply",
        on_missing_capital_module="null",
    )
