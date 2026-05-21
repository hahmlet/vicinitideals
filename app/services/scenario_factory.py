"""Single entry point for creating a Scenario + Project + OperationalInputs
triple with org/user defaults pre-applied.

All deal-creation paths (from-listing, from-opportunity, plain new, clone)
must funnel through ``create_scenario`` so every new deal starts with the
same default coverage. Type 1 (Org-Set) and Type 2 (Org-Default) field
values flow into the row at create time, scenarios that skip wizard steps
still end up populated, and the engine never reads NULL from a field that
had a default available.

See ``app/settings/defaults.py`` DEFAULT_REGISTRY for the source of truth
on which field lands where.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import (
    DealModel,
    OperationalInputs,
    ProjectType,
    Scenario,
)
from app.models.project import Project
from app.settings.defaults import DEFAULT_REGISTRY, DefaultSpec
from app.settings.resolver import resolve_all_defaults

__all__ = ["create_scenario", "apply_defaults_to_existing"]


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _safe_cast(spec: DefaultSpec, raw: str | None) -> Any | None:
    """Apply ``spec.cast`` to ``raw``; return None if cast fails or raw is None."""
    if raw is None or raw == "":
        return None
    try:
        return spec.cast(raw)
    except (ValueError, TypeError, InvalidOperation):
        return None


def _apply_scenario_defaults(
    scenario: Scenario,
    resolved: dict[str, str | None],
) -> None:
    """Write Type 1 + Type 2 defaults whose target is the Scenario row."""
    for field_key, spec in DEFAULT_REGISTRY.items():
        if spec.target != "scenario":
            continue
        cast_value = _safe_cast(spec, resolved.get(field_key))
        if cast_value is None:
            continue
        # Only write when caller hasn't already set the field explicitly.
        # (Caller-set values win — e.g. income_mode forced by deal-creation form.)
        if getattr(scenario, spec.column, None) in (None, ""):
            setattr(scenario, spec.column, cast_value)


def _apply_operational_inputs_defaults(
    inputs: OperationalInputs,
    resolved: dict[str, str | None],
) -> None:
    """Write Type 1 + Type 2 defaults whose target is the OperationalInputs row
    or one of its JSONB sub-paths."""
    debt_terms: dict[str, Any] = dict(inputs.debt_terms or {})
    perm_debt: dict[str, Any] = dict(debt_terms.get("permanent_debt", {}))
    perm_debt_dirty = False

    for field_key, spec in DEFAULT_REGISTRY.items():
        cast_value = _safe_cast(spec, resolved.get(field_key))
        if cast_value is None:
            continue

        if spec.target == "operational_inputs":
            current = getattr(inputs, spec.column, None)
            # Treat 0 / 0.0 / Decimal(0) as "unset" for fields where 0 is the
            # SQLAlchemy default but the registry has a meaningful baseline.
            if current in (None, "", 0, Decimal("0")):
                setattr(inputs, spec.column, cast_value)
        elif spec.target == "operational_inputs.debt_terms.permanent_debt":
            if spec.column not in perm_debt:
                perm_debt[spec.column] = cast_value
                perm_debt_dirty = True
        # target == "no_destination" → handled outside the factory (waterfall
        # tiers, dev fee use line, etc. are seeded by caller-side helpers).
        # target == "scenario" → handled by _apply_scenario_defaults.

    if perm_debt_dirty:
        debt_terms["permanent_debt"] = perm_debt
        inputs.debt_terms = debt_terms


def _inherit_type2_from_source(
    target_scenario: Scenario,
    target_inputs: OperationalInputs,
    source_scenario: Scenario,
    source_inputs: OperationalInputs | None,
) -> None:
    """Overlay Type 2 fields from a source clone onto the target.

    Type 1 (Org-Set) values stay at whatever the org currently says — we
    intentionally re-resolve them from the org rather than copying stale
    source values, so org policy updates propagate to clones.

    Type 2 values inherit from the source: that's the whole point of cloning
    (preserve the deal's specific tuning).
    """
    for field_key, spec in DEFAULT_REGISTRY.items():
        if spec.type != 2:
            continue
        if spec.target == "scenario":
            src_val = getattr(source_scenario, spec.column, None)
            if src_val is not None:
                setattr(target_scenario, spec.column, src_val)
        elif spec.target == "operational_inputs" and source_inputs is not None:
            src_val = getattr(source_inputs, spec.column, None)
            if src_val not in (None, "", 0, Decimal("0")):
                setattr(target_inputs, spec.column, src_val)
        elif (
            spec.target == "operational_inputs.debt_terms.permanent_debt"
            and source_inputs is not None
        ):
            src_perm = (source_inputs.debt_terms or {}).get("permanent_debt", {})
            if spec.column in src_perm:
                debt_terms = dict(target_inputs.debt_terms or {})
                perm = dict(debt_terms.get("permanent_debt", {}))
                perm[spec.column] = src_perm[spec.column]
                debt_terms["permanent_debt"] = perm
                target_inputs.debt_terms = debt_terms


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

async def create_scenario(
    *,
    session: AsyncSession,
    deal_id: uuid.UUID,
    deal_type: ProjectType,
    user_id: uuid.UUID | None,
    org_id: uuid.UUID,
    name: str = "Base Case",
    version: int = 1,
    is_active: bool = True,
    project_name: str | None = "Default Project",
    opportunity_id: uuid.UUID | None = None,
    source_scenario: Scenario | None = None,
    source_inputs: OperationalInputs | None = None,
    source_vehicle_id: uuid.UUID | None = None,
) -> tuple[Scenario, Project | None, OperationalInputs | None]:
    """Create a fresh Scenario (and optionally Project + OperationalInputs)
    with org/user defaults pre-applied.

    If ``project_name`` is ``None``, only the Scenario row is created — used
    by the deep-clone path which copies Projects from a source Scenario via
    its own per-project logic.

    If ``source_scenario`` is given, Type 2 (Org-Default) values from the
    source overlay the resolved defaults — clone semantics. Type 1 values
    always come from current org policy.

    Caller still owns: top-level ``Deal`` row, ``Opportunity`` row, seeded
    ``UseLine`` rows (acquisition cost, dev fee), ``Milestone`` rows,
    ``CapitalModule`` rows (via ``vehicle_preload.preload_equity_modules``).

    Returns
    -------
    (Scenario, Project | None, OperationalInputs | None)
        Project and OperationalInputs are None when ``project_name`` is None.
        All created rows are flushed but the caller controls the final commit.
    """
    # Resolve current effective defaults for this user/org context. If we
    # have no user, fall through to org/system baseline only.
    if user_id is not None:
        resolved = await resolve_all_defaults(user_id, org_id, session)
    else:
        # Build a defaults dict using only system baseline values — used by
        # tests and edge cases that lack a real user.
        resolved = {k: v.value for k, v in DEFAULT_REGISTRY.items()}

    # ── Scenario row ────────────────────────────────────────────────────────
    scenario = DealModel(
        deal_id=deal_id,
        name=name,
        project_type=deal_type,
        version=version,
        is_active=is_active,
        created_by_user_id=user_id,
    )
    if source_vehicle_id is not None:
        scenario.source_vehicle_id = source_vehicle_id
    _apply_scenario_defaults(scenario, resolved)
    if source_scenario is not None:
        # Type 2 overlay on Scenario columns (income_mode, etc.)
        _inherit_type2_from_source(scenario, OperationalInputs(), source_scenario, None)
    session.add(scenario)
    await session.flush()

    if project_name is None:
        # Scenario-only mode — caller (clone path) will create its own
        # Project + OperationalInputs rows.
        return scenario, None, None

    # ── Project row ─────────────────────────────────────────────────────────
    project = Project(
        scenario_id=scenario.id,
        opportunity_id=opportunity_id,
        name=project_name,
    )
    session.add(project)
    await session.flush()

    # ── OperationalInputs row ───────────────────────────────────────────────
    inputs = OperationalInputs(project_id=project.id)
    _apply_operational_inputs_defaults(inputs, resolved)

    # Clone-time Type 2 overlay on OperationalInputs (post-defaults, so
    # source wins on overlap).
    if source_scenario is not None and source_inputs is not None:
        _inherit_type2_from_source(scenario, inputs, source_scenario, source_inputs)

    session.add(inputs)
    await session.flush()

    return scenario, project, inputs


async def force_type1_on_existing(
    *,
    session: AsyncSession,
    scenario: Scenario | None,
    inputs: OperationalInputs | None,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    """Unconditionally overwrite Type 1 (Org-Set) fields on the given rows
    with the current org/user resolved values. Used by the clone path so a
    cloned Scenario picks up the latest org policy even when the source row
    had a stale baseline.

    Skips fields whose target is ``no_destination`` and only touches Type 1
    entries from ``DEFAULT_REGISTRY``.
    """
    resolved = await resolve_all_defaults(user_id, org_id, session)
    for field_key, spec in DEFAULT_REGISTRY.items():
        if spec.type != 1:
            continue
        cast_value = _safe_cast(spec, resolved.get(field_key))
        if cast_value is None:
            continue
        if spec.target == "scenario" and scenario is not None:
            setattr(scenario, spec.column, cast_value)
        elif spec.target == "operational_inputs" and inputs is not None:
            setattr(inputs, spec.column, cast_value)
        elif (
            spec.target == "operational_inputs.debt_terms.permanent_debt"
            and inputs is not None
        ):
            debt_terms = dict(inputs.debt_terms or {})
            perm = dict(debt_terms.get("permanent_debt", {}))
            perm[spec.column] = cast_value
            debt_terms["permanent_debt"] = perm
            inputs.debt_terms = debt_terms
    if scenario is not None:
        session.add(scenario)
    if inputs is not None:
        session.add(inputs)
    await session.flush()


async def apply_defaults_to_existing(
    *,
    session: AsyncSession,
    scenario: Scenario,
    inputs: OperationalInputs,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    """Apply defaults to a legacy Scenario + OperationalInputs pair that
    pre-dates the factory. Used by the backfill script and by the wizard's
    fallback path when it encounters an empty OperationalInputs row.

    Only writes to fields that are currently unset (None / empty / zero).
    Existing non-default values are left alone.
    """
    resolved = await resolve_all_defaults(user_id, org_id, session)
    _apply_scenario_defaults(scenario, resolved)
    _apply_operational_inputs_defaults(inputs, resolved)
    session.add(scenario)
    session.add(inputs)
    await session.flush()
