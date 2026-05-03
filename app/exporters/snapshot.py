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

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exporters.json_export import export_deal_model_json
from app.models.capital import CapitalModule, DrawSource, WaterfallTier
from app.models.cashflow import OperationalOutputs
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
from app.models.project import Project
from app.schemas.capital import CapitalModuleBase, WaterfallTierBase
from app.schemas.deal import (
    IncomeStreamBase,
    OperatingExpenseLineBase,
    OperationalInputsBase,
    UseLineBase,
    UnitMixBase,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

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
    return value


def _clean(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(i) for i in obj]
    return _coerce(obj)


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
        "income_streams",
        "expense_lines",
        "unit_mix",
        "capital_modules",
        "waterfall_tiers",
    }
    return {k: v for k, v in full.items() if k in input_keys}


async def _serialize_outputs(session: AsyncSession, scenario_id: UUID) -> dict[str, Any]:
    """Read key output metrics for the snapshot's outputs_json."""
    row = (await session.execute(
        select(OperationalOutputs)
        .where(OperationalOutputs.scenario_id == scenario_id)
        .order_by(OperationalOutputs.project_id.nulls_first())
        .limit(1)
    )).scalar_one_or_none()

    result: dict[str, Any] = {}
    if row is None:
        return result
    for key in _OUTPUT_KEYS:
        val = getattr(row, key, None)
        result[key] = _coerce(val) if val is not None else None
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
    """
    scenario = (await session.execute(
        select(Scenario).where(Scenario.id == scenario_id)
    )).scalar_one()

    # Increment the version counter
    scenario.version = (scenario.version or 0) + 1
    session.add(scenario)
    await session.flush()

    inputs_json = await _serialize_inputs(session, scenario_id)
    outputs_json = await _serialize_outputs(session, scenario_id)

    snap = ScenarioSnapshot(
        id=uuid.uuid4(),
        scenario_id=scenario_id,
        version=scenario.version,
        triggered_by=triggered_by,
        inputs_json=_clean(inputs_json),
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
    for row in rows:
        key = str(row.get("label") or row.get("id") or "")
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


def _entity_list_diff(
    before_rows: list[dict],
    after_rows: list[dict],
    entity_type: str,
    compare_fields: tuple[str, ...],
) -> list[dict]:
    changes: list[dict] = []
    b_map = _entity_map(before_rows)
    a_map = _entity_map(after_rows)

    all_keys = set(b_map) | set(a_map)
    for key in sorted(all_keys):
        if key in b_map and key not in a_map:
            changes.append({"entity": entity_type, "label": key, "change": "removed"})
        elif key not in b_map and key in a_map:
            changes.append({"entity": entity_type, "label": key, "change": "added",
                            "values": a_map[key]})
        else:
            field_changes = _scalar_diff(b_map[key], a_map[key], compare_fields)
            for fc in field_changes:
                changes.append({"entity": entity_type, "label": key, **fc})
    return changes


def diff_snapshots(
    snap_before: ScenarioSnapshot, snap_after: ScenarioSnapshot
) -> dict[str, Any]:
    """Compare two snapshots and return structured input + output diffs.

    Returns::
        {
            "version_before": int,
            "version_after": int,
            "input_changes": [...],
            "output_changes": {...}
        }
    """
    b_in = snap_before.inputs_json or {}
    a_in = snap_after.inputs_json or {}

    input_changes: list[dict] = []

    # OperationalInputs scalar diff
    b_oi = b_in.get("operational_inputs") or {}
    a_oi = a_in.get("operational_inputs") or {}
    oi_fields = (
        "unit_count_existing", "unit_count_new", "building_sqft", "lot_sqft",
        "purchase_price", "constr_months_total", "lease_up_months",
        "debt_sizing_mode", "dscr_minimum", "noi_stabilized_input",
    )
    for fc in _scalar_diff(b_oi, a_oi, oi_fields):
        input_changes.append({"entity": "OperationalInputs", **fc})

    # IncomeStream diff
    input_changes.extend(_entity_list_diff(
        b_in.get("income_streams") or [],
        a_in.get("income_streams") or [],
        "IncomeStream",
        ("amount_per_unit_monthly", "unit_count", "occupancy_rate_pct",
         "escalation_rate_pct_annual", "income_type"),
    ))

    # ExpenseLine diff
    input_changes.extend(_entity_list_diff(
        b_in.get("expense_lines") or [],
        a_in.get("expense_lines") or [],
        "ExpenseLine",
        ("amount_monthly", "amount_annual", "pct_of_egr"),
    ))

    # CapitalModule diff
    input_changes.extend(_entity_list_diff(
        b_in.get("capital_modules") or [],
        a_in.get("capital_modules") or [],
        "CapitalModule",
        ("funder_type", "stack_position", "auto_size"),
    ))

    # WaterfallTier diff
    input_changes.extend(_entity_list_diff(
        b_in.get("waterfall_tiers") or [],
        a_in.get("waterfall_tiers") or [],
        "WaterfallTier",
        ("hurdle_rate_pct", "gp_split_pct", "priority"),
    ))

    # Output diff
    b_out = snap_before.outputs_json or {}
    a_out = snap_after.outputs_json or {}
    output_changes: dict[str, Any] = {}
    for key in _OUTPUT_KEYS:
        bv = b_out.get(key)
        av = a_out.get(key)
        if bv != av:
            output_changes[key] = {"before": bv, "after": av}

    return {
        "version_before": snap_before.version,
        "version_after": snap_after.version,
        "input_changes": input_changes,
        "output_changes": output_changes,
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

    # Locate the default project for this scenario
    default_project = (await session.execute(
        select(Project)
        .where(Project.scenario_id == scenario_id)
        .order_by(Project.created_at.asc())
        .limit(1)
    )).scalar_one_or_none()
    if default_project is None:
        raise ValueError(f"No Project found for scenario {scenario_id}")

    project_id = default_project.id

    # ── Delete mutable input rows ────────────────────────────────────────────
    # UseLines (engine-injected reserve lines will be recreated on next Compute)
    await session.execute(delete(UseLine).where(UseLine.project_id == project_id))
    # IncomeStreams
    await session.execute(delete(IncomeStream).where(IncomeStream.project_id == project_id))
    # ExpenseLines
    await session.execute(delete(OperatingExpenseLine).where(
        OperatingExpenseLine.project_id == project_id
    ))
    # UnitMix
    await session.execute(delete(UnitMix).where(UnitMix.project_id == project_id))
    # OperationalInputs (scalar row)
    await session.execute(delete(OperationalInputs).where(
        OperationalInputs.project_id == project_id
    ))
    # Capital
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
    oi_data = inputs.get("operational_inputs")
    if oi_data:
        try:
            parsed_oi = OperationalInputsBase.model_validate(oi_data)
            session.add(OperationalInputs(
                project_id=project_id,
                **parsed_oi.model_dump(exclude_unset=True),
            ))
        except Exception:
            pass  # Don't block revert if schema evolved

    for stream_data in inputs.get("income_streams") or []:
        try:
            parsed = IncomeStreamBase.model_validate(stream_data)
            session.add(IncomeStream(project_id=project_id, **parsed.model_dump(exclude_unset=True)))
        except Exception:
            pass

    for exp_data in inputs.get("expense_lines") or []:
        try:
            parsed = OperatingExpenseLineBase.model_validate(exp_data)
            session.add(OperatingExpenseLine(project_id=project_id, **parsed.model_dump(exclude_unset=True)))
        except Exception:
            pass

    cap_id_map: dict[str, UUID] = {}
    for mod_data in inputs.get("capital_modules") or []:
        try:
            old_id = mod_data.get("id")
            payload = CapitalModuleBase.model_validate(mod_data).model_dump(exclude_unset=True)
            payload.pop("id", None)
            new_mod = CapitalModule(scenario_id=scenario_id, **payload)
            session.add(new_mod)
            await session.flush()
            if old_id:
                cap_id_map[str(old_id)] = new_mod.id
        except Exception:
            pass

    for tier_data in inputs.get("waterfall_tiers") or []:
        try:
            old_cap_id = tier_data.get("capital_module_id")
            payload = WaterfallTierBase.model_validate(tier_data).model_dump(exclude_unset=True)
            payload.pop("id", None)
            if old_cap_id and str(old_cap_id) in cap_id_map:
                payload["capital_module_id"] = cap_id_map[str(old_cap_id)]
            session.add(WaterfallTier(scenario_id=scenario_id, **payload))
        except Exception:
            pass

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
