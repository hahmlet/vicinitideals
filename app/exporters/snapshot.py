"""Scenario snapshot helpers — capture, diff, revert, and export.

Called from the compute endpoint to create an immutable audit record on every
Compute run, and from UI routes to drive the history drawer.

Public API
----------
capture_snapshot(session, scenario_id, triggered_by="compute")
    Increment Scenario.version, serialize current inputs + outputs, insert a
    ScenarioSnapshot row.  Returns the new snapshot.

list_snapshots(session, scenario_id)
    Return all ScenarioSnapshot rows ordered by version ascending.

diff_snapshots(snap_before, snap_after)
    Compare two snapshots and return structured input + output diffs.

revert_to_snapshot(session, scenario_id, snapshot_id)
    Restore a scenario's input rows to the state captured in the snapshot.

export_history_json(session, scenario_id)
    Return the full change-log as a JSON-serializable dict (AI-readable).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exporters.json_export import export_deal_model_json
from app.models.capital import CapitalModule, CapitalModuleProject, DrawSource, WaterfallResult, WaterfallTier
from app.models.cashflow import CashFlowLineItem, OperationalOutputs
from app.models.deal import (
    DealModel,
    IncomeStream,
    OperatingExpenseLine,
    OperationalInputs,
    Scenario,
    ScenarioSnapshot,
    UnitMix,
    UseLine,
)
from app.models.milestone import Milestone
from app.models.project import Project
from app.schemas.capital import CapitalModuleBase, DrawSourceBase, WaterfallTierBase
from app.schemas.deal import (
    IncomeStreamBase,
    OperatingExpenseLineBase,
    OperationalInputsBase,
    UseLineBase,
    UnitMixBase,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

_OUTPUT_KEYS = (
    "dscr",
    "project_irr_levered",
    "noi_stabilized",
    "equity_required",
    "total_project_cost",
    "cap_rate_on_cost_pct",
)


def _coerce(value: Any) -> Any:
    """Make values JSON-safe (Decimal → float, enum → .value, UUID → str)."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "value"):  # enum
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _clean(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(i) for i in obj]
    return _coerce(obj)


def _parse_iso_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _json_safe(obj: Any) -> Any:
    """Convert a Pydantic model_dump() result to JSON-safe types.

    model_dump(mode='json') serializes Decimal as str, which breaks the
    cashflow engine when those strings are stored in JSONB columns.  This
    helper round-trips through json.dumps (using float for Decimal) so the
    returned dict contains only Python native JSON types (float, not str).
    """
    def _default(o: Any) -> Any:
        if isinstance(o, Decimal):
            return float(o)
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")
    return json.loads(json.dumps(obj, default=_default))


def _row_to_payload(row: Any, *, exclude: set[str]) -> dict[str, Any]:
    """Serialize an ORM row to a JSON-safe dict using its table columns."""
    return {
        col.name: _coerce(getattr(row, col.name))
        for col in row.__table__.columns
        if col.name not in exclude
    }


def _serialize_project_snapshot(project: Project) -> dict[str, Any]:
    use_lines = [
        _row_to_payload(row, exclude={"id", "project_id", "updated_at"})
        for row in sorted(project.use_lines, key=lambda item: (item.label or "", str(item.id)))
    ]
    income_streams = [
        _row_to_payload(row, exclude={"id", "project_id", "updated_at"})
        for row in sorted(project.income_streams, key=lambda item: (item.label or "", str(item.id)))
    ]
    expense_lines = [
        _row_to_payload(row, exclude={"id", "project_id", "updated_at"})
        for row in sorted(project.expense_lines, key=lambda item: (item.label or "", str(item.id)))
    ]
    unit_mix = [
        _row_to_payload(row, exclude={"id", "project_id", "updated_at"})
        for row in sorted(project.unit_mix, key=lambda item: (item.label or "", str(item.id)))
    ]
    milestones = [
        {
            "id": str(ms.id),
            "milestone_type": _coerce(ms.milestone_type),
            "duration_days": ms.duration_days,
            "target_date": ms.target_date.isoformat() if ms.target_date else None,
            "sequence_order": ms.sequence_order,
            "label": ms.label,
            "trigger_milestone_id": str(ms.trigger_milestone_id) if ms.trigger_milestone_id else None,
            "trigger_offset_days": ms.trigger_offset_days,
        }
        for ms in sorted(project.milestones, key=lambda item: (item.sequence_order, str(item.id)))
    ]

    return {
        "project_id": str(project.id),
        "operational_inputs": (
            _row_to_payload(project.operational_inputs, exclude={"id", "project_id", "updated_at"})
            if project.operational_inputs is not None
            else None
        ),
        "use_lines": use_lines,
        "income_streams": income_streams,
        "expense_lines": expense_lines,
        "unit_mix": unit_mix,
        "milestones": milestones,
    }


# ── Core serialisation ────────────────────────────────────────────────────────

async def _serialize_inputs(session: AsyncSession, scenario_id: UUID) -> dict[str, Any]:
    """Capture the full input state for a scenario.

    Delegates to the canonical json_export helper so the format is always in
    sync with what json_import can restore.  Strips computed fields (cash_flows,
    outputs) so the snapshot stays input-only.
    """
    full = await export_deal_model_json(session, scenario_id)
    input_keys = {
        "schema_version",
        "export_type",
        "source",
        "project",
        "deal_model",
        "operational_inputs",
        "use_lines",
        "income_streams",
        "expense_lines",
        "unit_mix",
        "milestones",
        "projects",
        "draw_sources",
        "capital_modules",
        "waterfall_tiers",
    }

    # Capture every project's mutable inputs so multi-project reverts are exact.
    projects = list(
        (
            await session.execute(
                select(Project)
                .where(Project.scenario_id == scenario_id)
                .options(
                    selectinload(Project.operational_inputs),
                    selectinload(Project.use_lines),
                    selectinload(Project.income_streams),
                    selectinload(Project.expense_lines),
                    selectinload(Project.unit_mix),
                    selectinload(Project.milestones),
                )
                .order_by(Project.created_at.asc())
            )
        ).scalars()
    )
    project_payloads = [_serialize_project_snapshot(project) for project in projects]

    result = {k: v for k, v in full.items() if k in input_keys}
    draw_sources = list(
        (
            await session.execute(
                select(DrawSource)
                .where(DrawSource.scenario_id == scenario_id)
                .order_by(DrawSource.sort_order.asc(), DrawSource.created_at.asc())
            )
        ).scalars()
    )
    result["draw_sources"] = [
        _row_to_payload(
            row,
            exclude={"id", "scenario_id", "created_at"},
        )
        for row in draw_sources
    ]

    # Capture capital_module_projects junction entries so revert can restore them.
    _cm_ids_for_junc = [
        uuid.UUID(m["id"]) for m in (result.get("capital_modules") or []) if m.get("id")
    ]
    if _cm_ids_for_junc:
        _junc_rows = list(
            (
                await session.execute(
                    select(CapitalModuleProject).where(
                        CapitalModuleProject.capital_module_id.in_(_cm_ids_for_junc)
                    )
                )
            ).scalars()
        )
        result["capital_module_projects"] = [
            _row_to_payload(row, exclude={"id", "created_at", "updated_at"})
            for row in _junc_rows
        ]
    else:
        result["capital_module_projects"] = []

    if project_payloads:
        default_payload = project_payloads[0]
        result["projects"] = project_payloads
        result["operational_inputs"] = default_payload.get("operational_inputs")
        result["use_lines"] = default_payload.get("use_lines")
        result["income_streams"] = default_payload.get("income_streams")
        result["expense_lines"] = default_payload.get("expense_lines")
        result["unit_mix"] = default_payload.get("unit_mix")
        result["milestones"] = default_payload.get("milestones")

    return result


async def _serialize_outputs(session: AsyncSession, scenario_id: UUID) -> dict[str, Any]:
    """Read key output metrics for the snapshot's outputs_json."""
    rows = list((await session.execute(
        select(OperationalOutputs)
        .where(OperationalOutputs.scenario_id == scenario_id)
        .order_by(OperationalOutputs.project_id.nulls_first())
    )).scalars())

    result: dict[str, Any] = {}
    if not rows:
        return result

    by_project: dict[str, Any] = {}
    for row in rows:
        metrics: dict[str, Any] = {
            key: (_coerce(getattr(row, key, None)) if getattr(row, key, None) is not None else None)
            for key in _OUTPUT_KEYS
        }
        metrics["project_id"] = str(row.project_id) if row.project_id is not None else None
        by_project[metrics["project_id"] or "__scenario__"] = metrics

    # Preserve existing top-level metrics for current UI consumers.
    primary = by_project.get("__scenario__") or next(iter(by_project.values()))
    for key in _OUTPUT_KEYS:
        result[key] = primary.get(key)
    result["by_project"] = by_project
    return result


# ── Public API ────────────────────────────────────────────────────────────────

async def capture_snapshot(
    session: AsyncSession,
    scenario_id: UUID,
    triggered_by: str = "compute",
) -> ScenarioSnapshot:
    """Increment Scenario.version and insert a new ScenarioSnapshot row.

    Called AFTER the compute engine has written OperationalOutputs so that
    outputs_json captures the freshly computed metrics.

    If inputs are identical to the most recent snapshot, no new snapshot is
    created and the existing one is returned unchanged (idempotent re-compute).
    """
    scenario = (await session.execute(
        select(Scenario).where(Scenario.id == scenario_id)
    )).scalar_one()

    inputs_json = await _serialize_inputs(session, scenario_id)
    clean_inputs = _clean(inputs_json)

    # Check whether inputs changed since the last snapshot
    last_snap = (await session.execute(
        select(ScenarioSnapshot)
        .where(ScenarioSnapshot.scenario_id == scenario_id)
        .order_by(ScenarioSnapshot.version.desc())
        .limit(1)
    )).scalar_one_or_none()

    if last_snap is not None and last_snap.inputs_json == clean_inputs:
        return last_snap

    # Inputs changed (or first ever snapshot) — create a new version
    scenario.version = (scenario.version or 0) + 1
    session.add(scenario)
    await session.flush()

    outputs_json = await _serialize_outputs(session, scenario_id)

    snap = ScenarioSnapshot(
        id=uuid.uuid4(),
        scenario_id=scenario_id,
        version=scenario.version,
        triggered_by=triggered_by,
        inputs_json=clean_inputs,
        outputs_json=_clean(outputs_json),
    )
    session.add(snap)
    await session.flush()
    return snap


async def list_snapshots(
    session: AsyncSession, scenario_id: UUID
) -> list[ScenarioSnapshot]:
    """Return all snapshots for a scenario, oldest first."""
    result = await session.execute(
        select(ScenarioSnapshot)
        .where(ScenarioSnapshot.scenario_id == scenario_id)
        .order_by(ScenarioSnapshot.version.asc())
    )
    return list(result.scalars().all())


# ── Diff ─────────────────────────────────────────────────────────────────────

def _entity_map(rows: list[dict]) -> dict[str, dict]:
    """Index a list of entity dicts by (label, id) for diffing."""
    out: dict[str, dict] = {}
    for idx, row in enumerate(rows):
        row_id = row.get("id")
        if row_id not in (None, ""):
            key = f"id:{row_id}"
        elif row.get("label") not in (None, ""):
            key = f"label:{row.get('label')}|idx:{idx}"
        else:
            key = f"row:{idx}"
        out[key] = row
    return out


def _scalar_diff(before: dict, after: dict, keys: tuple[str, ...]) -> list[dict]:
    changes = []
    for k in keys:
        bv = before.get(k)
        av = after.get(k)
        if bv != av:
            changes.append({"field": k, "before": bv, "after": av})
    return changes


def _scalar_diff_all(before: dict, after: dict) -> list[dict]:
    """Compare every field present in either dict (no fixed key list)."""
    all_keys = set(before.keys()) | set(after.keys())
    changes = []
    for k in sorted(all_keys):
        bv = before.get(k)
        av = after.get(k)
        if bv != av:
            changes.append({"field": k, "before": bv, "after": av})
    return changes


# Display multiplier applied before rounding-based suppression.
# project_irr_levered is stored as 0.14 (= 14%); displayed ×100 as 14.00%.
_OUTPUT_DISPLAY_MULTIPLIER: dict[str, float] = {
    "dscr": 1.0,
    "project_irr_levered": 100.0,
    "noi_stabilized": 1.0,
    "equity_required": 1.0,
    "total_project_cost": 1.0,
    "cap_rate_on_cost_pct": 1.0,
}


# ── Diff label / format maps ──────────────────────────────────────────────────
# Each entry: (human-readable label, format hint)
# Format hints: currency | percent | number | text | bool | date

_FUNDER_TYPE_LABELS: dict[str, str] = {
    "debt": "Debt",
    "bridge": "Bridge Loan",
    "permanent_debt": "Permanent Debt",
    "mezzanine": "Mezzanine",
    "preferred_equity": "Preferred Equity",
    "common_equity": "Common Equity",
    "owner_investment": "Owner Investment",
    "owner_loan": "Owner Loan",
    "grant": "Grant",
    "tax_credit": "Tax Credit",
    "subordinate_debt": "Subordinate Debt",
}

_MILESTONE_TYPE_LABELS: dict[str, str] = {
    "offer_made": "Offer Made",
    "under_contract": "Under Contract",
    "close": "Close",
    "pre_development": "Pre-Development",
    "construction": "Construction",
    "operation_lease_up": "Lease-Up",
    "operation_stabilized": "Stabilized Operations",
    "divestment": "Divestment",
}

_SOURCE_FIELDS: dict[str, tuple[str, str]] = {
    "amount":               ("Principal",           "currency"),
    "interest_rate_pct":    ("Interest Rate",       "percent"),
    "pct_of_total_cost":    ("% of Total Cost",     "percent"),
    "ltv_pct":              ("LTV %",               "percent"),
    "sizing_approach":      ("Sizing Approach",     "text"),
    "fixed_amount":         ("Fixed Amount",        "currency"),
    "hold_term_years":      ("Hold Term (yrs)",     "number"),
    "dscr_min":             ("Min DSCR",            "number"),
    "auto_size":            ("Auto-size",           "bool"),
    "prepay_penalty_pct":   ("Prepay Penalty %",    "percent"),
    "refi_cap_rate_pct":    ("Refi Cap Rate %",     "percent"),
    "funding_date_trigger": ("Funding Trigger",     "text"),
}
_SOURCE_SKIP: frozenset[str] = frozenset({
    "draws", "notes", "is_bridge", "construction_retirement", "schema_version",
})

_CARRY_FIELDS: dict[str, tuple[str, str]] = {
    "carry_type":        ("Carry Type",        "text"),
    "io_rate_pct":       ("Interest Rate",     "percent"),
    "amort_term_years":  ("Amort. Term (yrs)", "number"),
    "day_count":         ("Day Count",         "text"),
    "payment_frequency": ("Payment Frequency", "text"),
}
_CARRY_SKIP: frozenset[str] = frozenset({
    "capitalized", "io_period_months", "io_to_pi_trigger", "phases", "schema_version",
})

_CAP_MODULE_TOP_FIELDS: dict[str, tuple[str, str]] = {
    "funder_type":        ("Source Type",       "text"),
    "active_phase_start": ("Active From Phase", "text"),
    "active_phase_end":   ("Active To Phase",   "text"),
    "stack_position":     ("Stack Position",    "number"),
}

_INCOME_STREAM_FIELDS: dict[str, tuple[str, str]] = {
    "label":                      ("Name",                   "text"),
    "amount_per_unit_monthly":    ("Rent/Unit/Month",        "currency"),
    "unit_count":                 ("Units",                  "number"),
    "occupancy_rate_pct":         ("Occupancy %",            "percent"),
    "escalation_rate_pct_annual": ("Escalation % (annual)", "percent"),
    "income_type":                ("Income Type",            "text"),
}

_EXPENSE_FIELDS: dict[str, tuple[str, str]] = {
    "label":          ("Name",           "text"),
    "amount_monthly": ("Monthly Amount", "currency"),
    "amount_annual":  ("Annual Amount",  "currency"),
    "pct_of_egr":     ("% of EGR",       "percent"),
}

_USE_LINE_FIELDS: dict[str, tuple[str, str]] = {
    "label":       ("Name",    "text"),
    "phase":       ("Phase",   "text"),
    "amount":      ("Amount",  "currency"),
    "timing_type": ("Timing",  "text"),
    "is_deferred": ("Deferred","bool"),
}

_MILESTONE_FIELDS: dict[str, tuple[str, str]] = {
    "duration_days":       ("Duration (days)",       "number"),
    "target_date":         ("Target Date",           "date"),
    "trigger_offset_days": ("Trigger Offset (days)", "number"),
}

_WATERFALL_FIELDS: dict[str, tuple[str, str]] = {
    "hurdle_rate_pct": ("Hurdle Rate %", "percent"),
    "gp_split_pct":    ("GP Split %",    "percent"),
    "priority":        ("Priority",      "number"),
}

_DRAW_SOURCE_FIELDS: dict[str, tuple[str, str]] = {
    "label":                 ("Name",                    "text"),
    "total_commitment":      ("Total Commitment",        "currency"),
    "annual_interest_rate":  ("Interest Rate",           "percent"),
    "draw_every_n_months":   ("Draw Frequency (months)", "number"),
    "source_type":           ("Source Type",             "text"),
    "funder_type":           ("Funder Type",             "text"),
    "active_from_milestone": ("Active From",             "text"),
    "active_to_milestone":   ("Active To",               "text"),
}

_OPS_INPUTS_FIELDS: dict[str, tuple[str, str]] = {
    "unit_count_existing":         ("Existing Units",         "number"),
    "unit_count_new":              ("New Units",              "number"),
    "unit_count_after_conversion": ("Units After Conversion", "number"),
    "building_sqft":               ("Building Sq Ft",         "number"),
    "lot_sqft":                    ("Lot Sq Ft",              "number"),
    "hold_months":                 ("Hold Months",            "number"),
    "entitlement_months":          ("Entitlement Months",     "number"),
    "entitlement_cost":            ("Entitlement Cost",       "currency"),
    "lease_up_months":             ("Lease-Up Months",        "number"),
    "initial_occupancy_pct":       ("Initial Occupancy %",    "percent"),
    "lease_up_curve":              ("Lease-Up Curve",         "text"),
    "mgmt_fee_pct":                ("Management Fee %",       "percent"),
    "going_in_cap_rate_pct":       ("Going-In Cap Rate %",    "percent"),
    "exit_cap_rate_pct":           ("Exit Cap Rate %",        "percent"),
    "selling_costs_pct":           ("Selling Costs %",        "percent"),
    "construction_months":         ("Construction Months",    "number"),
    "renovation_months":           ("Renovation Months",      "number"),
}

_UNIT_MIX_FIELDS: dict[str, tuple[str, str]] = {
    "unit_count":              ("Units",               "number"),
    "avg_sqft":                ("Avg Sq Ft",           "number"),
    "beds":                    ("Beds",                "number"),
    "baths":                   ("Baths",               "number"),
    "market_rent_per_unit":    ("Market Rent/Unit",    "currency"),
    "in_place_rent_per_unit":  ("In-Place Rent/Unit",  "currency"),
    "unit_strategy":           ("Unit Strategy",       "text"),
    "post_reno_rent_per_unit": ("Post-Reno Rent/Unit", "currency"),
}


def _entity_name(row: dict, entity_type: str) -> str:
    """Return a user-facing name for a data row."""
    if entity_type == "CapitalModule":
        user_label = (row.get("label") or "").strip()
        if user_label:
            return user_label
        ft = str(row.get("funder_type") or "").replace("FunderType.", "")
        return _FUNDER_TYPE_LABELS.get(ft, "Capital Source")
    if entity_type == "Milestone":
        raw = str(row.get("milestone_type") or "").replace("MilestoneType.", "")
        ms_label = _MILESTONE_TYPE_LABELS.get(raw, raw.replace("_", " ").title())
        custom = (row.get("label") or "").strip()
        return f"{ms_label}: {custom}" if custom else ms_label
    if entity_type == "WaterfallTier":
        priority = row.get("priority")
        if priority is not None:
            return f"Waterfall Tier {priority}"
        return "Waterfall Tier"
    return ((row.get("label") or row.get("name") or entity_type) or entity_type).strip()


def _numeric_eq(a: Any, b: Any) -> bool:
    """True if two values are numerically equal within 4 decimal places."""
    try:
        return round(float(a), 4) == round(float(b), 4)
    except (TypeError, ValueError):
        return False


def _blob_diff(
    before: dict,
    after: dict,
    entity_label: str,
    entity_type: str,
    field_map: dict[str, tuple[str, str]],
    skip: frozenset[str] | None = None,
) -> list[dict]:
    """Diff two JSONB dicts field-by-field, emitting only user-visible fields."""
    changes: list[dict] = []
    all_keys = (set(before.keys()) | set(after.keys())) - (skip or frozenset())
    for k in sorted(all_keys):
        if k not in field_map:
            continue
        label, fmt = field_map[k]
        bv = before.get(k)
        av = after.get(k)
        if bv == av:
            continue
        if fmt in ("currency", "percent", "number") and bv is not None and av is not None:
            if _numeric_eq(bv, av):
                continue
        changes.append({
            "entity_label": entity_label,
            "entity_type": entity_type,
            "field_label": label,
            "fmt": fmt,
            "before": bv,
            "after": av,
        })
    return changes


def _compare_rows(
    b_row: dict,
    a_row: dict,
    entity_label: str,
    entity_type: str,
    scalar_fields: dict[str, tuple[str, str]],
    blob_fields: dict[str, tuple[dict[str, tuple[str, str]], frozenset[str]]] | None,
    changes: list[dict],
) -> None:
    """Append field-level diffs between two entity rows into changes."""
    for field_key, (field_label, fmt) in scalar_fields.items():
        bv = b_row.get(field_key)
        av = a_row.get(field_key)
        if bv == av:
            continue
        if fmt in ("currency", "percent", "number") and bv is not None and av is not None:
            if _numeric_eq(bv, av):
                continue
        changes.append({
            "entity_label": entity_label,
            "entity_type": entity_type,
            "field_label": field_label,
            "fmt": fmt,
            "before": bv,
            "after": av,
        })
    if blob_fields:
        for blob_key, (sub_map, skip) in blob_fields.items():
            b_blob = b_row.get(blob_key) or {}
            a_blob = a_row.get(blob_key) or {}
            if b_blob != a_blob:
                changes.extend(_blob_diff(b_blob, a_blob, entity_label, entity_type, sub_map, skip))


def _entity_list_diff_v2(
    before_rows: list[dict],
    after_rows: list[dict],
    entity_type: str,
    scalar_fields: dict[str, tuple[str, str]],
    blob_fields: dict[str, tuple[dict[str, tuple[str, str]], frozenset[str]]] | None = None,
) -> list[dict]:
    """Produce human-readable per-field change rows for a list of entities.

    Two-pass matching:
    - Pass 1: match by stable ID — handles normal edits.
    - Pass 2: for rows unmatched after pass 1, group by display name and pair
      them up.  This suppresses the spurious add+remove noise that appears when
      rows are deleted and re-created with new UUIDs but the same data (e.g.
      the timeline wizard or capital stack editor recreates all items at once).
      Only a genuine net increase/decrease in count for a given name produces an
      added/removed entry.
    """
    changes: list[dict] = []
    b_map = _entity_map(before_rows)
    a_map = _entity_map(after_rows)

    common_keys = set(b_map) & set(a_map)
    b_unmatched = {k: v for k, v in b_map.items() if k not in common_keys}
    a_unmatched = {k: v for k, v in a_map.items() if k not in common_keys}

    # Pass 1: ID-matched pairs
    for key in sorted(common_keys):
        label = _entity_name(a_map[key], entity_type)
        _compare_rows(b_map[key], a_map[key], label, entity_type, scalar_fields, blob_fields, changes)

    # Pass 2: group unmatched by display name
    b_by_name: dict[str, list[dict]] = {}
    for row in b_unmatched.values():
        b_by_name.setdefault(_entity_name(row, entity_type), []).append(row)

    a_by_name: dict[str, list[dict]] = {}
    for row in a_unmatched.values():
        a_by_name.setdefault(_entity_name(row, entity_type), []).append(row)

    for name in sorted(set(b_by_name) | set(a_by_name)):
        b_list = b_by_name.get(name, [])
        a_list = a_by_name.get(name, [])
        n_pairs = min(len(b_list), len(a_list))
        # Paired same-name rows: compare fields (usually no-op for recreated rows)
        for i in range(n_pairs):
            _compare_rows(b_list[i], a_list[i], name, entity_type, scalar_fields, blob_fields, changes)
        # Genuine removals
        for _ in range(len(b_list) - n_pairs):
            changes.append({"entity_label": name, "entity_type": entity_type, "change": "removed"})
        # Genuine additions
        for row in a_list[n_pairs:]:
            changes.append({"entity_label": name, "entity_type": entity_type, "change": "added"})

    return changes


def diff_snapshots(
    snap_before: ScenarioSnapshot, snap_after: ScenarioSnapshot
) -> dict[str, Any]:
    """Compare two snapshots and return structured input + output diffs.

    Returns::
        {
            "version_before": int,
            "version_after": int,
            "input_changes": [...],   # each item has entity_label, field_label, fmt, before, after
            "output_changes": {...}
        }
    """
    b_in = snap_before.inputs_json or {}
    a_in = snap_after.inputs_json or {}

    input_changes: list[dict] = []

    # OperationalInputs — only user-visible fields
    b_oi = b_in.get("operational_inputs") or {}
    a_oi = a_in.get("operational_inputs") or {}
    for field_key, (field_label, fmt) in _OPS_INPUTS_FIELDS.items():
        bv = b_oi.get(field_key)
        av = a_oi.get(field_key)
        if bv == av:
            continue
        if fmt in ("currency", "percent", "number") and bv is not None and av is not None:
            if _numeric_eq(bv, av):
                continue
        input_changes.append({
            "entity_label": "Operating Inputs",
            "entity_type": "OperationalInputs",
            "field_label": field_label,
            "fmt": fmt,
            "before": bv,
            "after": av,
        })

    # IncomeStream
    input_changes.extend(_entity_list_diff_v2(
        b_in.get("income_streams") or [],
        a_in.get("income_streams") or [],
        "IncomeStream",
        _INCOME_STREAM_FIELDS,
    ))

    # ExpenseLine
    input_changes.extend(_entity_list_diff_v2(
        b_in.get("expense_lines") or [],
        a_in.get("expense_lines") or [],
        "ExpenseLine",
        _EXPENSE_FIELDS,
    ))

    # UseLine
    input_changes.extend(_entity_list_diff_v2(
        b_in.get("use_lines") or [],
        a_in.get("use_lines") or [],
        "UseLine",
        _USE_LINE_FIELDS,
    ))

    # UnitMix
    input_changes.extend(_entity_list_diff_v2(
        b_in.get("unit_mix") or [],
        a_in.get("unit_mix") or [],
        "UnitMix",
        _UNIT_MIX_FIELDS,
    ))

    # Milestone
    input_changes.extend(_entity_list_diff_v2(
        b_in.get("milestones") or [],
        a_in.get("milestones") or [],
        "Milestone",
        _MILESTONE_FIELDS,
    ))

    # CapitalModule — expand source and carry blobs into individual fields
    input_changes.extend(_entity_list_diff_v2(
        b_in.get("capital_modules") or [],
        a_in.get("capital_modules") or [],
        "CapitalModule",
        _CAP_MODULE_TOP_FIELDS,
        blob_fields={
            "source": (_SOURCE_FIELDS, _SOURCE_SKIP),
            "carry": (_CARRY_FIELDS, _CARRY_SKIP),
        },
    ))

    # WaterfallTier
    input_changes.extend(_entity_list_diff_v2(
        b_in.get("waterfall_tiers") or [],
        a_in.get("waterfall_tiers") or [],
        "WaterfallTier",
        _WATERFALL_FIELDS,
    ))

    # DrawSource
    input_changes.extend(_entity_list_diff_v2(
        b_in.get("draw_sources") or [],
        a_in.get("draw_sources") or [],
        "DrawSource",
        _DRAW_SOURCE_FIELDS,
    ))

    # Output diff — only _OUTPUT_KEYS; by_project is too noisy for the UI.
    b_out = snap_before.outputs_json or {}
    a_out = snap_after.outputs_json or {}
    output_changes: dict[str, Any] = {}
    for key in _OUTPUT_KEYS:
        bv = b_out.get(key)
        av = a_out.get(key)
        if bv != av:
            output_changes[key] = {"before": bv, "after": av}

    # Suppress rounding noise at 2-decimal display precision.
    visible: dict[str, Any] = {}
    for key, chg in output_changes.items():
        bv, av = chg.get("before"), chg.get("after")
        if bv is None or av is None:
            visible[key] = chg
            continue
        try:
            mult = _OUTPUT_DISPLAY_MULTIPLIER.get(key, 1.0)
            if round(float(bv) * mult, 2) != round(float(av) * mult, 2):
                visible[key] = chg
        except (TypeError, ValueError):
            visible[key] = chg

    return {
        "version_before": snap_before.version,
        "version_after": snap_after.version,
        "input_changes": input_changes,
        "output_changes": visible,
    }


# ── Revert ───────────────────────────────────────────────────────────────────

async def revert_to_snapshot(
    session: AsyncSession, scenario_id: UUID, snapshot_id: UUID
) -> None:
    """Restore a scenario's input rows to the state captured in snapshot_id.

    Deletes all mutable child rows then re-inserts them from inputs_json.
    The caller must commit the session.  OperationalOutputs are deleted
    so the stale metrics are not displayed; user must re-run Compute.
    """
    snap = (await session.execute(
        select(ScenarioSnapshot).where(
            ScenarioSnapshot.id == snapshot_id,
            ScenarioSnapshot.scenario_id == scenario_id,
        )
    )).scalar_one_or_none()
    if snap is None:
        raise ValueError(f"Snapshot {snapshot_id} not found for scenario {scenario_id}")

    inputs = snap.inputs_json or {}

    projects = list(
        (
            await session.execute(
                select(Project)
                .where(Project.scenario_id == scenario_id)
                .order_by(Project.created_at.asc())
            )
        ).scalars()
    )
    if not projects:
        raise ValueError(f"No Project found for scenario {scenario_id}")

    project_ids = [project.id for project in projects]
    project_ids_str = {str(project.id): project.id for project in projects}
    project_payloads = inputs.get("projects") or []
    payload_by_project = {
        str(payload.get("project_id")): payload
        for payload in project_payloads
        if payload.get("project_id") is not None
    }

    # Backward compatibility for snapshots captured before multi-project payloads.
    if not payload_by_project and projects:
        payload_by_project[str(projects[0].id)] = {
            "operational_inputs": inputs.get("operational_inputs"),
            "use_lines": inputs.get("use_lines") or [],
            "income_streams": inputs.get("income_streams") or [],
            "expense_lines": inputs.get("expense_lines") or [],
            "unit_mix": inputs.get("unit_mix") or [],
            "milestones": inputs.get("milestones") or [],
        }

    target_project_ids = [
        project_ids_str[pid]
        for pid in payload_by_project
        if pid in project_ids_str
    ]
    if not target_project_ids:
        target_project_ids = [projects[0].id]

    # ── Delete mutable input rows ────────────────────────────────────────────
    # CashFlowLineItems reference IncomeStreams — delete first
    await session.execute(delete(CashFlowLineItem).where(CashFlowLineItem.scenario_id == scenario_id))
    # UseLines (engine-injected reserve lines will be recreated on next Compute)
    await session.execute(delete(UseLine).where(UseLine.project_id.in_(target_project_ids)))
    # IncomeStreams
    await session.execute(delete(IncomeStream).where(IncomeStream.project_id.in_(target_project_ids)))
    # ExpenseLines
    await session.execute(delete(OperatingExpenseLine).where(
        OperatingExpenseLine.project_id.in_(target_project_ids)
    ))
    # UnitMix
    await session.execute(delete(UnitMix).where(UnitMix.project_id.in_(target_project_ids)))
    # OperationalInputs (scalar row)
    await session.execute(delete(OperationalInputs).where(
        OperationalInputs.project_id.in_(target_project_ids)
    ))
    # Milestones (timeline rows)
    await session.execute(delete(Milestone).where(
        Milestone.project_id.in_(target_project_ids)
    ))
    # Capital — WaterfallResults reference WaterfallTiers and CapitalModules, delete first
    await session.execute(delete(WaterfallResult).where(
        WaterfallResult.scenario_id == scenario_id
    ))
    await session.execute(delete(WaterfallTier).where(
        WaterfallTier.scenario_id == scenario_id
    ))
    await session.execute(delete(DrawSource).where(
        DrawSource.scenario_id == scenario_id
    ))
    await session.execute(delete(CapitalModule).where(
        CapitalModule.scenario_id == scenario_id
    ))
    # Invalidate outputs — user must re-run Compute
    await session.execute(delete(OperationalOutputs).where(
        OperationalOutputs.scenario_id == scenario_id
    ))
    await session.flush()

    # ── Re-insert from snapshot ──────────────────────────────────────────────
    for project in projects:
        payload = payload_by_project.get(str(project.id))
        if payload is None:
            continue

        oi_data = payload.get("operational_inputs")
        if oi_data:
            try:
                parsed_oi = OperationalInputsBase.model_validate(oi_data)
                session.add(OperationalInputs(
                    project_id=project.id,
                    **parsed_oi.model_dump(exclude_unset=True),
                ))
            except Exception:
                logger.warning("snapshot revert: skipped OperationalInputs restore", exc_info=True)

        for use_data in payload.get("use_lines") or []:
            try:
                parsed = UseLineBase.model_validate(use_data)
                session.add(UseLine(project_id=project.id, **parsed.model_dump(exclude_unset=True)))
            except Exception:
                logger.warning("snapshot revert: skipped UseLine restore", exc_info=True)

        for stream_data in payload.get("income_streams") or []:
            try:
                parsed = IncomeStreamBase.model_validate(stream_data)
                session.add(IncomeStream(project_id=project.id, **parsed.model_dump(exclude_unset=True)))
            except Exception:
                logger.warning("snapshot revert: skipped IncomeStream restore", exc_info=True)

        for exp_data in payload.get("expense_lines") or []:
            try:
                parsed = OperatingExpenseLineBase.model_validate(exp_data)
                session.add(OperatingExpenseLine(project_id=project.id, **parsed.model_dump(exclude_unset=True)))
            except Exception:
                logger.warning("snapshot revert: skipped OperatingExpenseLine restore", exc_info=True)

        for mix_data in payload.get("unit_mix") or []:
            try:
                parsed = UnitMixBase.model_validate(mix_data)
                session.add(UnitMix(project_id=project.id, **parsed.model_dump(exclude_unset=True)))
            except Exception:
                logger.warning("snapshot revert: skipped UnitMix restore", exc_info=True)

        milestone_rows: list[tuple[dict[str, Any], Milestone]] = []
        old_to_new_milestone_ids: dict[str, UUID] = {}
        for ms_data in payload.get("milestones") or []:
            try:
                new_ms = Milestone(
                    project_id=project.id,
                    milestone_type=str(ms_data.get("milestone_type") or ""),
                    duration_days=int(ms_data.get("duration_days") or 0),
                    target_date=_parse_iso_date(ms_data.get("target_date")),
                    sequence_order=int(ms_data.get("sequence_order") or 1),
                    label=ms_data.get("label"),
                    trigger_offset_days=int(ms_data.get("trigger_offset_days") or 0),
                    trigger_milestone_id=None,
                )
                session.add(new_ms)
                await session.flush()
                old_id = ms_data.get("id")
                if old_id:
                    old_to_new_milestone_ids[str(old_id)] = new_ms.id
                milestone_rows.append((ms_data, new_ms))
            except Exception:
                logger.warning("snapshot revert: skipped Milestone restore", exc_info=True)

        for ms_data, new_ms in milestone_rows:
            old_trigger_id = ms_data.get("trigger_milestone_id")
            if old_trigger_id and str(old_trigger_id) in old_to_new_milestone_ids:
                new_ms.trigger_milestone_id = old_to_new_milestone_ids[str(old_trigger_id)]

    cap_id_map: dict[str, UUID] = {}
    cap_auto_size: dict[str, bool] = {}  # new_cap_id_str → source.auto_size for fallback junctions
    for mod_data in inputs.get("capital_modules") or []:
        try:
            old_id = mod_data.get("id")
            _src_auto = bool((mod_data.get("source") or {}).get("auto_size"))
            payload = _json_safe(CapitalModuleBase.model_validate(mod_data).model_dump(exclude_unset=True))
            payload.pop("id", None)
            new_mod = CapitalModule(scenario_id=scenario_id, **payload)
            session.add(new_mod)
            await session.flush()
            if old_id:
                cap_id_map[str(old_id)] = new_mod.id
                cap_auto_size[str(new_mod.id)] = _src_auto
        except Exception:
            logger.warning("snapshot revert: skipped CapitalModule restore", exc_info=True)

    for ds_data in inputs.get("draw_sources") or []:
        try:
            old_cap_id = ds_data.get("capital_module_id")
            payload = _json_safe(DrawSourceBase.model_validate(ds_data).model_dump(exclude_unset=True))
            if old_cap_id and str(old_cap_id) in cap_id_map:
                payload["capital_module_id"] = cap_id_map[str(old_cap_id)]
            session.add(DrawSource(scenario_id=scenario_id, **payload))
        except Exception:
            logger.warning("snapshot revert: skipped DrawSource restore", exc_info=True)

    for tier_data in inputs.get("waterfall_tiers") or []:
        try:
            old_cap_id = tier_data.get("capital_module_id")
            payload = _json_safe(WaterfallTierBase.model_validate(tier_data).model_dump(exclude_unset=True))
            payload.pop("id", None)
            if old_cap_id and str(old_cap_id) in cap_id_map:
                payload["capital_module_id"] = cap_id_map[str(old_cap_id)]
            session.add(WaterfallTier(scenario_id=scenario_id, **payload))
        except Exception:
            logger.warning("snapshot revert: skipped WaterfallTier restore", exc_info=True)

    # ── Restore capital_module_projects junction entries ─────────────────────
    junc_data_list = inputs.get("capital_module_projects")
    if junc_data_list:
        for junc_data in junc_data_list:
            try:
                old_cap_id_s = str(junc_data.get("capital_module_id") or "")
                old_proj_id_s = str(junc_data.get("project_id") or "")
                if old_cap_id_s not in cap_id_map:
                    continue
                if old_proj_id_s not in project_ids_str:
                    continue
                session.add(CapitalModuleProject(
                    capital_module_id=cap_id_map[old_cap_id_s],
                    project_id=project_ids_str[old_proj_id_s],
                    amount=junc_data.get("amount") or 0,
                    active_from=junc_data.get("active_from"),
                    active_to=junc_data.get("active_to"),
                    active_from_offset_days=int(junc_data.get("active_from_offset_days") or 0),
                    active_to_offset_days=int(junc_data.get("active_to_offset_days") or 0),
                    auto_size=bool(junc_data.get("auto_size") or False),
                ))
            except Exception:
                logger.warning("snapshot revert: skipped CapitalModuleProject restore", exc_info=True)
    elif cap_id_map:
        # Fallback for old snapshots that predate junction capture.
        # amount=0 always (old source["amount"] is a single-project compute
        # artifact — wrong to broadcast to all projects).
        # auto_size mirrors the module's own source flag: debt stays True so
        # the engine auto-sizes per project; equity (auto_size=null/False)
        # stays False so the engine doesn't attempt to size equity as debt.
        for new_cap_uuid in cap_id_map.values():
            a_size = cap_auto_size.get(str(new_cap_uuid), False)
            for proj_id in project_ids:
                try:
                    session.add(CapitalModuleProject(
                        capital_module_id=new_cap_uuid,
                        project_id=proj_id,
                        amount=0,
                        active_from_offset_days=0,
                        active_to_offset_days=0,
                        auto_size=a_size,
                    ))
                except Exception:
                    logger.warning("snapshot revert: skipped fallback CapitalModuleProject", exc_info=True)

    await session.flush()


# ── Change-log JSON export ────────────────────────────────────────────────────

async def export_history_json(
    session: AsyncSession, scenario_id: UUID
) -> dict[str, Any]:
    """Return the full change-log for a scenario as a JSON-serializable dict.

    Each entry is a structured diff between consecutive snapshots.
    The first snapshot has no diff (it's the baseline).
    """
    scenario = (await session.execute(
        select(Scenario).where(Scenario.id == scenario_id)
    )).scalar_one_or_none()
    if scenario is None:
        raise ValueError(f"Scenario {scenario_id} not found")

    snaps = await list_snapshots(session, scenario_id)
    entries: list[dict] = []

    for i, snap in enumerate(snaps):
        entry: dict[str, Any] = {
            "version": snap.version,
            "computed_at": snap.created_at.isoformat() if snap.created_at else None,
            "triggered_by": snap.triggered_by,
            "label": snap.label,
            "outputs": snap.outputs_json or {},
        }
        if i == 0:
            entry["input_changes"] = []
            entry["output_changes"] = {}
            entry["note"] = "baseline"
        else:
            diff = diff_snapshots(snaps[i - 1], snap)
            entry["input_changes"] = diff["input_changes"]
            entry["output_changes"] = diff["output_changes"]

        entries.append(entry)

    return {
        "scenario_id": str(scenario_id),
        "scenario_name": scenario.name,
        "exported_at": datetime.now(UTC).isoformat(),
        "entries": entries,
    }


__all__ = [
    "capture_snapshot",
    "diff_snapshots",
    "export_history_json",
    "list_snapshots",
    "revert_to_snapshot",
]
