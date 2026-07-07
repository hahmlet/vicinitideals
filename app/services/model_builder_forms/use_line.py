"""Form-save logic for UseLine rows (Sources & Uses panel)."""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule
from app.models.deal import UseLine
from app.models.project import Project
from app.utils.form_helpers import _fd, _fi


async def _parse_eligible_module_ids(
    session: AsyncSession, model_id: UUID, form
) -> list[UUID] | None:
    """Parse the use-side Source whitelist (`eligible_module_ids`) from the form.

    Returns None when the form did not render the picker (hidden sentinel
    `eligible_module_ids_section` absent) so callers leave the column
    untouched. An empty list means the user unchecked everything —
    permissive default (any Source may fund this Use).

    Submitted IDs are validated against this scenario's CapitalModules so a
    hand-crafted POST cannot attach foreign module UUIDs.
    """
    if form.get("eligible_module_ids_section") != "1":
        return None
    raw_ids: list[UUID] = []
    for raw in form.getlist("eligible_module_ids"):
        raw = (raw or "").strip()
        if not raw:
            continue
        try:
            raw_ids.append(UUID(raw))
        except (ValueError, AttributeError):
            continue
    if not raw_ids:
        return []
    valid_ids = set((await session.execute(
        select(CapitalModule.id).where(
            CapitalModule.scenario_id == model_id,
            CapitalModule.id.in_(raw_ids),
        )
    )).scalars())
    return [x for x in raw_ids if x in valid_ids]


async def save_use_line(
    session: AsyncSession,
    model_id: UUID,
    project_id: UUID | None,
    item_id: str,
    form,
) -> None:
    """Persist a UseLine create or update from form data."""
    _ms_key = form.get("milestone_key") or None
    _ms_key_to = form.get("milestone_key_to") or None
    # If "to" == "from" or blank, treat as single-point (no range)
    if _ms_key_to == _ms_key:
        _ms_key_to = None
    # Derive phase from milestone_key for backward compat with anything that reads phase
    _milestone_to_phase = {
        "close": "acquisition", "pre_development": "pre_construction",
        "construction": "construction", "renovation": "construction",
        "conversion": "construction", "operation_lease_up": "operation",
        "operation_stabilized": "operation", "divestment": "exit",
        "maturity": "other",
    }
    _phase = _milestone_to_phase.get(_ms_key or "", "") or form.get("phase", "acquisition")
    _cost_cat = form.get("cost_category") or "soft"
    # Safety net: hard costs land at close milestone (phase=acquisition)
    # if the user accepted the form's default. Hard costs almost always
    # belong on the construction milestone — fund-as-built, not at
    # close. This normalizes the data on save without overriding any
    # explicit non-acquisition phase the user picked.
    if _cost_cat == "hard" and _phase == "acquisition":
        _phase = "construction"
    # Resolve milestone_key strings → milestone UUID FKs. Migration 0086
    # dropped the legacy milestone_key column in favor of FKs; without
    # this lookup the user's Active From pick is silently lost for any
    # row whose phase string can't distinguish lease-up vs stabilized.
    from app.services.capital_module_milestones import (
        map_aps_to_milestone_type as _map_aps_to_mt,
        _find_milestone_id_for_project as _find_ms_for_proj,
    )
    _ms_id = None
    _ms_id_to = None
    if project_id and _ms_key and _ms_key != "maturity":
        _mt_from = _map_aps_to_mt(_ms_key)
        if _mt_from is not None:
            _ms_id = await _find_ms_for_proj(session, project_id, _mt_from)
    if project_id and _ms_key_to and _ms_key_to != "maturity":
        _mt_to = _map_aps_to_mt(_ms_key_to)
        if _mt_to is not None:
            _ms_id_to = await _find_ms_for_proj(session, project_id, _mt_to)
    # Use-side Source whitelist. None = picker absent from form (leave column
    # alone); [] = explicitly cleared; [ids] = whitelist these Sources only.
    _eligible_module_ids = await _parse_eligible_module_ids(session, model_id, form)
    data: dict = {
        "label": form.get("label", ""),
        "phase": _phase,
        "active_from_milestone_id": _ms_id,
        "spread_to_milestone_id": _ms_id_to,
        "amount": _fd(form.get("amount")) or Decimal("0"),
        "timing_type": form.get("timing_type") or "first_day",
        "is_deferred": form.get("is_deferred") == "true",
        "cost_category": _cost_cat,
        "notes": form.get("notes") or None,
    }
    if _eligible_module_ids is not None:
        data["eligible_module_ids"] = _eligible_module_ids
    if item_id:
        row = await session.get(UseLine, UUID(item_id))
        if row:
            if row.is_auto_dev_fee:
                # Auto Dev Fee row: user edits % and basis only.
                # Label, phase, amount ($) are managed by the engine.
                pct_raw = _fd(form.get("dev_fee_pct"))
                if pct_raw is not None:
                    row.dev_fee_pct = pct_raw
                basis_raw = form.get("dev_fee_basis")
                if basis_raw in ("purchase_price", "tpc_excl_self"):
                    row.dev_fee_basis = basis_raw
                if form.get("notes") is not None:
                    row.notes = form.get("notes") or None
                # Acquisition treatment (4 variants: legacy None preserved
                # when no form key submitted).
                if "dev_fee_acquisition_treatment" in form:
                    _t = (form.get("dev_fee_acquisition_treatment") or "").strip()
                    row.dev_fee_acquisition_treatment = _t or None
                    if _t == "split_rate":
                        _ap = _fd(form.get("dev_fee_acquisition_pct"))
                        row.dev_fee_acquisition_pct = _ap
                    else:
                        row.dev_fee_acquisition_pct = None
                    # Manage parallel auto Acquisition Fee row.
                    _proj = await session.get(Project, row.project_id) if row.project_id else None
                    _scen_id = _proj.scenario_id if _proj else None
                    if _scen_id is not None:
                        _existing_acq = (await session.execute(
                            select(UseLine).join(Project, UseLine.project_id == Project.id)
                            .where(
                                Project.scenario_id == _scen_id,
                                UseLine.is_auto_acquisition_fee == True,  # noqa: E712
                            )
                        )).scalars().first()
                        if _t == "separate_fee":
                            _acq_pct = _fd(form.get("acquisition_fee_pct"))
                            if _existing_acq is None:
                                session.add(UseLine(
                                    project_id=row.project_id,
                                    label="Acquisition Fee",
                                    phase="acquisition",
                                    amount=Decimal("0"),
                                    timing_type="first_day",
                                    cost_category="soft",
                                    is_auto_acquisition_fee=True,
                                    acquisition_fee_pct=_acq_pct,
                                ))
                            else:
                                if _acq_pct is not None:
                                    _existing_acq.acquisition_fee_pct = _acq_pct
                        else:
                            if _existing_acq is not None:
                                await session.delete(_existing_acq)
                # Release schedule (milestone weights + final holdback).
                if form.get("dev_fee_release_section") == "1":
                    _ms_keys = form.getlist("release_milestone_key[]")
                    _ms_weights = form.getlist("release_weight_pct[]")
                    _weights: list[dict] = []
                    for _i in range(len(_ms_keys)):
                        _k = (_ms_keys[_i] or "").strip()
                        _w = _fd(_ms_weights[_i] if _i < len(_ms_weights) else None)
                        if _k and _w is not None and _w > 0:
                            _weights.append({"milestone_key": _k, "weight": float(_w)})
                    _hold_pct = _fd(form.get("final_holdback_pct"))
                    _hold_ms = (form.get("final_holdback_milestone_key") or "").strip() or None
                    _sched: dict = {}
                    if _weights:
                        _sched["weights"] = _weights
                    if _hold_pct is not None and _hold_pct > 0:
                        _hb: dict = {"pct": float(_hold_pct)}
                        if _hold_ms:
                            _hb["milestone_key"] = _hold_ms
                        _sched["final_holdback"] = _hb
                    row.dev_fee_release_schedule = _sched
            elif row.is_auto_acquisition_fee:
                _acq_pct_raw = _fd(form.get("acquisition_fee_pct"))
                if _acq_pct_raw is not None:
                    row.acquisition_fee_pct = _acq_pct_raw
            else:
                # User edit on an auto Total Finance Costs row turns off
                # the auto flag so engine stops recomputing.  User can
                # delete the row to reset; next compute regenerates it.
                #
                # EXCEPT Active From: timing is locked to the parent
                # Source — drop phase from the form payload so the row's
                # active_from_milestone_id (set by the engine from the
                # Source's FK) stays authoritative. UI also hides the
                # picker for auto-FC rows; this is the server-side guard.
                if getattr(row, "is_auto_finance_cost", False):
                    data.pop("phase", None)
                    data.pop("active_from_milestone_id", None)
                    data.pop("spread_to_milestone_id", None)
                    row.is_auto_finance_cost = False
                for k, v in data.items():
                    setattr(row, k, v)
    elif project_id:
        session.add(UseLine(project_id=project_id, **data))
