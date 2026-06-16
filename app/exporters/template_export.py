"""Scenario → template extraction.

Strips a scenario down to its structural elements, removing all
property-specific dollar values and dates while preserving:
- Line item labels, ordering, relationships
- Percentage-based rates and policy defaults
- Capital stack structure (vehicle type, carry type, phases)
- Waterfall structure (hurdle rates, splits)
- Milestone relationships (trigger chains, types, labels) without durations/dates
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.exporters.json_export import export_deal_model_json


# ── Field strip rules ─────────────────────────────────────────────────────────
# For each entity type: which keys to zero-out / null-out in the template.
# Everything else carries over as-is.

_OPS_INPUTS_STRIP: frozenset[str] = frozenset({
    # construction/hold months driven by milestone structure, not scalar
    "construction_months",
    "renovation_months",
    "hold_months",
    "entitlement_months",
    "entitlement_cost",
    "lease_up_months",
})

_INCOME_STREAM_STRIP: frozenset[str] = frozenset({
    "amount_per_unit_monthly",
    "unit_count",
})

_EXPENSE_STRIP: frozenset[str] = frozenset({
    "amount_monthly",
    "amount_annual",
})

_USE_LINE_STRIP: frozenset[str] = frozenset({
    "amount",
})

_CAPITAL_SOURCE_STRIP: frozenset[str] = frozenset({
    # Principal and rate-environment values governed by Source Vehicle at load time
    "amount",
    "interest_rate_pct",
    "fixed_amount",
    "pct_of_total_cost",
    "ltv_pct",
    "dscr_min",
    "refi_cap_rate_pct",
    "prepay_penalty_pct",
})

_CAPITAL_CARRY_STRIP: frozenset[str] = frozenset({
    "io_rate_pct",
})

_MILESTONE_STRIP: frozenset[str] = frozenset({
    "duration_days",
    "target_date",
})

_UNIT_MIX_STRIP: frozenset[str] = frozenset({
    "unit_count",
    "avg_sqft",
    "market_rent_per_unit",
    "in_place_rent_per_unit",
    "post_reno_rent_per_unit",
})


def _strip_keys(obj: dict[str, Any], keys: frozenset[str]) -> dict[str, Any]:
    return {k: (None if k in keys else v) for k, v in obj.items()}


def _strip_list(rows: list[dict], keys: frozenset[str]) -> list[dict]:
    return [_strip_keys(r, keys) for r in rows]


def _strip_capital_modules(modules: list[dict]) -> list[dict]:
    result = []
    for m in modules:
        m = dict(m)
        if isinstance(m.get("source"), dict):
            m["source"] = _strip_keys(m["source"], _CAPITAL_SOURCE_STRIP)
        if isinstance(m.get("carry"), dict):
            m["carry"] = _strip_keys(m["carry"], _CAPITAL_CARRY_STRIP)
        result.append(m)
    return result


async def extract_template_json(session: AsyncSession, scenario_id: UUID) -> dict[str, Any]:
    """Export a scenario then strip all property-specific values.

    Returns a dict suitable for storing in ScenarioTemplate.template_json.
    The format mirrors json_export so import helpers can consume it.
    """
    full = await export_deal_model_json(session, scenario_id)

    oi = full.get("operational_inputs") or {}
    template: dict[str, Any] = {
        "schema_version": full.get("schema_version"),
        "export_type": "scenario_template",
        "project_type": (full.get("deal_model") or {}).get("project_type"),
        "operational_inputs": _strip_keys(oi, _OPS_INPUTS_STRIP) if oi else None,
        "income_streams": _strip_list(full.get("income_streams") or [], _INCOME_STREAM_STRIP),
        "expense_lines": _strip_list(full.get("expense_lines") or [], _EXPENSE_STRIP),
        "use_lines": _strip_list(full.get("use_lines") or [], _USE_LINE_STRIP),
        "unit_mix": _strip_list(full.get("unit_mix") or [], _UNIT_MIX_STRIP),
        "milestones": _strip_list(full.get("milestones") or [], _MILESTONE_STRIP),
        "capital_modules": _strip_capital_modules(full.get("capital_modules") or []),
        "waterfall_tiers": full.get("waterfall_tiers") or [],
        "draw_sources": full.get("draw_sources") or [],
    }
    return template
