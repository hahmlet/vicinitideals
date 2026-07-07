"""Form-save logic for CapitalModule rows (Sources panel)."""
from __future__ import annotations

import uuid as _uuid_mod
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.dev_fee import BASIS_BUCKET_KEYS
from app.models.capital import CapitalModule, DrawSource, WaterfallTier  # noqa: F401
from app.models.deal import OperationalInputs, UseLine
from app.models.project import Project
from app.utils.form_helpers import _fd, _fi

# active_phase_start → milestone key that ends the phase window. Used to
# derive the deprecated `active_phase_end` server-side from the Exit Vehicle.
# Keys must stay within app.schemas.vocab.ACTIVE_PHASE_KEYS (contract-tested).
_APS_TO_MS = {
    "acquisition": "close", "close": "close",
    "pre_construction": "pre_development",
    "construction": "construction",
    "lease_up": "operation_lease_up", "operation_lease_up": "operation_lease_up",
    "stabilized": "operation_stabilized", "operation_stabilized": "operation_stabilized",
    "exit": "divestment", "divestment": "divestment",
}


async def save_capital_module(
    session: AsyncSession,
    model_id: UUID,
    project_id: UUID | None,
    default_project,
    item_id: str,
    form,
) -> None:
    """Persist a CapitalModule create or update from form data."""
    source_d: dict = {}
    if src_amt := _fd(form.get("source_amount")):
        source_d["amount"] = float(src_amt)
    # Grant cap (per-Use eligibility). When set, source.amount is engine-
    # computed each compute pass and ignored from form input above.
    if src_max := _fd(form.get("source_maximum")):
        source_d["maximum"] = float(src_max)
    if src_pct := _fd(form.get("source_pct")):
        source_d["pct_of_total_cost"] = float(src_pct)
    if src_rate := _fd(form.get("source_interest_rate")):
        source_d["interest_rate_pct"] = float(src_rate)
    # Per-Source override for the auto Total Finance Costs UseLine.
    # Blank / 0 falls back to engine global default (DEFAULT_FINANCE_COST_PCT).
    if "source_finance_cost_pct" in form:
        _fc_raw = form.get("source_finance_cost_pct")
        if _fc_raw is None or str(_fc_raw).strip() == "":
            source_d["finance_cost_pct"] = None
        else:
            _fc_val = _fd(_fc_raw)
            source_d["finance_cost_pct"] = float(_fc_val) if _fc_val is not None else None
    if cp := form.get("compounding_period"):
        source_d["compounding_period"] = cp
    if amort := _fi(form.get("amort_term_years"), None):
        source_d["amort_term_years"] = amort
    if hold_term := _fi(form.get("hold_term_years"), None):
        source_d["hold_term_years"] = hold_term
    if ppct := _fd(form.get("prepay_penalty_pct")):
        source_d["prepay_penalty_pct"] = float(ppct)
    if ltv := _fd(form.get("ltv_pct")):
        source_d["ltv_pct"] = float(ltv)
    if draw_type_raw := (form.get("draw_type") or "").strip():
        source_d["draw_type"] = draw_type_raw if draw_type_raw in ("draw_down", "fully_drawn") else None
    # Float-earnings on Day-1 draws — opt-in flag on parent source.
    # Engine reads this flag together with `draw_type=fully_drawn` to
    # decide whether to compute T-bond yield on the drawn balance.
    if form.get("balance_earns_interest") in ("on", "true", "1"):
        source_d["balance_earns_interest"] = True
    # Float-earnings child-source fields (only meaningful when
    # `vehicle_type == "float_earnings"`; engine ignores them otherwise).
    if parent_mod_raw := (form.get("parent_module_id") or "").strip():
        try:
            source_d["parent_module_id"] = str(UUID(parent_mod_raw))
        except ValueError:
            pass
    if yield_pct := _fd(form.get("yield_pct")):
        source_d["yield_pct"] = float(yield_pct)
    if wf_ms_raw := (form.get("waterfall_milestone_id") or "").strip():
        try:
            source_d["waterfall_milestone_id"] = str(UUID(wf_ms_raw))
        except ValueError:
            pass
    constr_carry_type = form.get("construction_carry_type", "none")
    # Carry rate: use source rate so the engine finds it in both places
    _carry_rate = _fd(form.get("source_interest_rate"))

    _carry_schedule_mode = (form.get("carry_schedule_mode") or "simple").strip()
    if _carry_schedule_mode == "schedule":
        # Parse N-phase carry schedule from form arrays.
        _sched_labels = form.getlist("carry_phase_label[]")
        _sched_types = form.getlist("carry_phase_type[]")
        _sched_dur_types = form.getlist("carry_phase_duration_type[]")
        _sched_months = form.getlist("carry_phase_months[]")
        _sched_milestones = form.getlist("carry_phase_milestone_key[]")
        _sched_rates = form.getlist("carry_phase_rate_pct[]")
        _sched_amorts = form.getlist("carry_phase_amort_years[]")
        _schedule_phases: list[dict] = []
        for _si in range(len(_sched_types)):
            _p_ct = (_sched_types[_si] if _si < len(_sched_types) else "none").strip()
            if not _p_ct or _p_ct == "none":
                continue
            _p_dur_type = (_sched_dur_types[_si] if _si < len(_sched_dur_types) else "remainder").strip()
            if _p_dur_type == "months":
                _p_dur: dict = {"type": "months", "months": int((_sched_months[_si] if _si < len(_sched_months) else "") or 0)}
            elif _p_dur_type == "milestone":
                _p_dur = {"type": "milestone", "milestone_key": (_sched_milestones[_si] if _si < len(_sched_milestones) else "").strip()}
            else:
                _p_dur = {"type": "remainder"}
            _p: dict = {
                "label": (_sched_labels[_si] if _si < len(_sched_labels) else "").strip() or _p_ct,
                "carry_type": _p_ct,
                "duration": _p_dur,
            }
            _p_rate = _fd(_sched_rates[_si] if _si < len(_sched_rates) else None)
            if _p_rate is not None:
                _p["rate_pct"] = float(_p_rate)
            _p_amort = _fi(_sched_amorts[_si] if _si < len(_sched_amorts) else None, None)
            if _p_amort:
                _p["amort_term_years"] = _p_amort
            _schedule_phases.append(_p)
        carry_d: dict = {"schedule": _schedule_phases}
    else:
        constr_phase: dict = {
            "name": "construction",
            "carry_type": constr_carry_type,
            "payment_frequency": form.get("construction_payment_frequency", "monthly"),
        }
        if _carry_rate is not None:
            constr_phase["io_rate_pct"] = float(_carry_rate)
        if constr_carry_type == "converts_to_permanent":
            if perm_rate := _fd(form.get("perm_rate_pct")):
                constr_phase["perm_rate_pct"] = float(perm_rate)
            if perm_term := _fi(form.get("perm_term_years"), None):
                constr_phase["perm_term_years"] = perm_term
            if perm_trig := form.get("perm_conversion_trigger"):
                constr_phase["perm_conversion_trigger"] = perm_trig
        _op_phase: dict = {
            "name": "operation",
            "carry_type": form.get("operation_carry_type", "none"),
            "payment_frequency": form.get("operation_payment_frequency", "monthly"),
        }
        if _carry_rate is not None:
            _op_phase["io_rate_pct"] = float(_carry_rate)
        if amort:
            _op_phase["amort_term_years"] = amort
        carry_d = {"phases": [constr_phase, _op_phase]}
    # Exit Vehicle: "maturity" | "sale" | "<module_uuid>" (retiring source).
    # Validate: must be one of the literals OR a UUID of another module on
    # the same scenario. Fall back to "maturity" if invalid.
    #
    # Non-debt vehicle types (equity, grants, etc.) are forced to
    # "maturity" as a no-op sentinel — their UI hides Exit Vehicle entirely.
    _vehicle_type = form.get("vehicle_type", "debt") or "debt"
    _equity_role = (form.get("equity_role") or "").strip() or None
    if _vehicle_type != "debt":
        _vehicle_value = "maturity"
    else:
        _vehicle_raw = (form.get("exit_vehicle") or "").strip()
        _vehicle_value = "maturity"
        if _vehicle_raw in {"maturity", "sale"}:
            _vehicle_value = _vehicle_raw
        elif _vehicle_raw:
            try:
                _vehicle_uuid = UUID(_vehicle_raw)
                _sibling = (await session.execute(
                    select(CapitalModule.id).where(
                        CapitalModule.scenario_id == model_id,
                        CapitalModule.id == _vehicle_uuid,
                    )
                )).scalar_one_or_none()
                if _sibling is not None and (not item_id or str(_sibling) != item_id):
                    _vehicle_value = str(_sibling)
            except (ValueError, AttributeError):
                pass
    exit_d = {
        "exit_type": form.get("exit_type", "full_payoff"),
        "vehicle": _vehicle_value,
    }

    # Derive `active_phase_end` + `active_to_milestone` from the vehicle.
    # `active_phase_end` is deprecated as a user input but still written
    # server-side from the vehicle so legacy read-paths (Gantt, reports)
    # keep working without a DB migration. Mapping is the module-level
    # _APS_TO_MS (hoisted so the vocab contract test can import it).
    _retirer_aps: str | None = None
    if _vehicle_value not in {"maturity", "sale"} and _vehicle_value:
        try:
            _retirer = await session.get(CapitalModule, UUID(_vehicle_value))
            if _retirer is not None:
                _retirer_aps = _retirer.active_phase_start
        except (ValueError, AttributeError):
            _retirer_aps = None
    if _vehicle_value == "sale":
        _derived_end_phase = "exit"
        _derived_to_ms = "divestment"
    elif _retirer_aps:
        _derived_end_phase = _retirer_aps
        _derived_to_ms = _APS_TO_MS.get(_retirer_aps, _retirer_aps)
    else:
        # "maturity" or unresolved → perpetuity sentinel; Gantt shows through exit.
        _derived_end_phase = "exit"
        _derived_to_ms = "divestment"
    explicit_pos = _fi(form.get("stack_position"), None)
    if not item_id and (not explicit_pos or explicit_pos == 0):
        # Auto-assign: place at end of current stack
        max_pos_result = await session.execute(
            select(func.max(CapitalModule.stack_position)).where(CapitalModule.scenario_id == model_id)
        )
        max_pos = max_pos_result.scalar_one_or_none() or 0
        explicit_pos = max_pos + 1
    final_pos = explicit_pos or 1
    # Uniqueness: if another module already holds this position, resolve the conflict.
    conflict_stmt = (
        select(CapitalModule)
        .where(CapitalModule.scenario_id == model_id, CapitalModule.stack_position == final_pos)
    )
    if item_id:
        conflict_stmt = conflict_stmt.where(CapitalModule.id != UUID(item_id))
    _conflict_mod = (await session.execute(conflict_stmt)).scalars().first()
    if _conflict_mod is not None:
        if item_id:
            # Edit: honor the user's chosen position — swap with the conflicting
            # module so it takes the edited module's previous slot.
            _editing_row = await session.get(CapitalModule, UUID(item_id))
            _old_pos = (_editing_row.stack_position if _editing_row else None) or final_pos
            _conflict_mod.stack_position = _old_pos
            session.add(_conflict_mod)
        else:
            # Create: bump the new module to the end of the stack.
            max_pos_result = await session.execute(
                select(func.max(CapitalModule.stack_position)).where(CapitalModule.scenario_id == model_id)
            )
            final_pos = (max_pos_result.scalar_one_or_none() or 0) + 1
    # Record which vehicle pre-filled this module (nullable; SET NULL on vehicle delete)
    _sv_id_raw = (form.get("source_vehicle_id") or "").strip()
    _sv_uuid: UUID | None = None
    if _sv_id_raw:
        try:
            _sv_uuid = UUID(_sv_id_raw)
        except (ValueError, AttributeError):
            pass

    # Developer Fee Rule (fee_terms JSONB + inheritance flag).
    # Section only renders on the edit form; presence of hidden sentinel
    # `fee_terms_section` controls whether we touch these columns. Wizard
    # creation skips this path entirely (defaults from migration: empty
    # dict + inherited_from_type=True).
    _ft_section_present = form.get("fee_terms_section") == "1"
    _ft_inherited = form.get("fee_terms_inherited") == "on"
    _ft_dict: dict = {}
    if _ft_section_present and not _ft_inherited:
        if (_mp := _fd(form.get("fee_terms_max_pct"))) is not None:
            _ft_dict["max_pct"] = float(_mp)
        if (_puc := _fd(form.get("fee_terms_per_unit_cap"))) is not None:
            _ft_dict["per_unit_cap"] = float(_puc)
        if (_ac := _fd(form.get("fee_terms_absolute_cap"))) is not None:
            _ft_dict["absolute_cap"] = float(_ac)
        # UI shows inclusions (all-checked default = full basis); persist
        # as the inverse `basis_exclusions` list of bucket keys the
        # engine reads. Only writes the field when at least one bucket
        # is excluded — keeps the JSONB minimal.
        _incl = {x.strip() for x in form.getlist("fee_terms_basis_inclusions[]") if x.strip()}
        _excl = sorted(BASIS_BUCKET_KEYS - _incl)
        if _excl:
            _ft_dict["basis_exclusions"] = _excl
        if form.get("fee_terms_regulated") == "on":
            _ft_dict["regulated"] = True
        if (_notes := (form.get("fee_terms_notes") or "").strip()):
            _ft_dict["notes"] = _notes

    data = {
        "label": form.get("label", ""),
        "vehicle_type": _vehicle_type,
        "equity_role": _equity_role,
        "stack_position": final_pos,
        "source": source_d,
        "carry": carry_d,
        "exit_terms": exit_d,
        "active_phase_end": _derived_end_phase,
        "source_vehicle_id": _sv_uuid,
    }
    if _ft_section_present:
        data["fee_terms"] = _ft_dict
        data["fee_terms_inherited_from_type"] = _ft_inherited
    # Draw schedule fields from form.  `ds_active_to_milestone` is ignored —
    # the repayment milestone is derived from Exit Vehicle (above).
    _ds_from_ms = form.get("ds_active_from_milestone") or ""
    _ds_to_ms = _derived_to_ms
    _ds_from_offset = _fi(form.get("ds_active_from_offset_days"), 0) or 0
    _ds_to_offset = _fi(form.get("ds_active_to_offset_days"), 0) or 0
    _ds_frequency = _fi(form.get("ds_draw_every_n_months"), 1) or 1
    _ds_rate = source_d.get("interest_rate_pct", 0.0)

    if item_id:
        row = await session.get(CapitalModule, UUID(item_id))
        if row:
            # Preserve internal-only source keys (auto_size) not exposed in the UI form
            if (row.source or {}).get("auto_size"):
                source_d["auto_size"] = True
            data["source"] = source_d
            for k, v in data.items():
                setattr(row, k, v)
            # Fixed-amount sources (grant/forgivable_loan/tax_credit/equity): mirror the
            # new source.amount onto the active-project junction row so the engine
            # actually picks up the change. Without this the junction's stale amount
            # overlays source.amount in memory at engine load and the new value is
            # silently dropped.
            if data["vehicle_type"] in ("grant", "forgivable_loan", "tax_credit", "equity"):
                from app.models.capital import CapitalModuleProject as _CMP_edit
                _new_amt = Decimal(str(source_d.get("amount") or 0))
                _auto_size_for_row = bool((row.source or {}).get("auto_size"))
                _active_pid = project_id if project_id is not None else (
                    default_project.id if default_project else None
                )
                if _active_pid is not None:
                    _j_row = (await session.execute(
                        select(_CMP_edit).where(
                            _CMP_edit.capital_module_id == row.id,
                            _CMP_edit.project_id == _active_pid,
                        )
                    )).scalar_one_or_none()
                    if _j_row is None:
                        session.add(_CMP_edit(
                            capital_module_id=row.id,
                            project_id=_active_pid,
                            amount=_new_amt,
                            active_from=None,
                            active_to=row.active_phase_end,
                            auto_size=_auto_size_for_row,
                        ))
                    else:
                        _j_row.amount = _new_amt
            # Mirror perm-debt hold_term_years / dscr_min to wizard staging
            # so re-opening Deal Setup wizard shows the latest value.
            if data["vehicle_type"] == "debt" and (
                "hold_term_years" in source_d or "dscr_min" in source_d
            ):
                _default_proj = (await session.execute(
                    select(Project).where(Project.scenario_id == model_id)
                    .order_by(Project.created_at.asc()).limit(1)
                )).scalar_one_or_none()
                if _default_proj is not None:
                    _oi = (await session.execute(
                        select(OperationalInputs).where(
                            OperationalInputs.project_id == _default_proj.id
                        )
                    )).scalar_one_or_none()
                    if _oi is not None:
                        _dt = dict(_oi.debt_terms or {})
                        _pd_entry = dict(_dt.get("permanent_debt", {}))
                        if "hold_term_years" in source_d:
                            _pd_entry["hold_term_years"] = source_d["hold_term_years"]
                        if "dscr_min" in source_d:
                            _pd_entry["dscr_min"] = source_d["dscr_min"]
                        _dt["permanent_debt"] = _pd_entry
                        _oi.debt_terms = _dt
                        session.add(_oi)
        # Update matching DrawSource (active window, offsets, frequency)
        _ds_id_raw = str(form.get("ds_id") or "").strip()
        if _ds_id_raw:
            try:
                _ds_row = await session.get(DrawSource, UUID(_ds_id_raw))
                if _ds_row and _ds_row.scenario_id == model_id:
                    if _ds_from_ms:
                        _ds_row.active_from_milestone = _ds_from_ms
                    if _ds_to_ms:
                        _ds_row.active_to_milestone = _ds_to_ms
                    _ds_row.active_from_offset_days = _ds_from_offset
                    _ds_row.active_to_offset_days = _ds_to_offset
                    _ds_row.draw_every_n_months = _ds_frequency
                    _ds_row.annual_interest_rate = Decimal(str(_ds_rate))
                    _ds_row.label = data["label"]
            except (ValueError, TypeError):
                pass
    else:
        _cm_id = _uuid_mod.uuid4()
        cm = CapitalModule(id=_cm_id, scenario_id=model_id, **data)
        session.add(cm)
        # Create CapitalModuleProject junction row(s) — the engine's per-project
        # query INNER JOINs on this table, so a module with no junction row is
        # invisible to sizing/cashflow. Put the full source.amount on the active
        # project; zero rows on other projects so the source appears in their
        # coverage lists without double-counting.
        from app.models.capital import CapitalModuleProject as _CMP_create
        _all_projects = (await session.execute(
            select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at.asc())
        )).scalars().all()
        _src_amt_dec = Decimal(str(source_d.get("amount") or 0))
        _is_auto = bool(source_d.get("auto_size"))
        _primary_pid = project_id if project_id is not None else (default_project.id if default_project else None)
        # Project-specific vehicle types get one junction row (primary project only).
        # Shared types (debt/equity/forgivable_loan) get a row per project so the
        # source appears in every project's coverage list.
        _PROJECT_SPECIFIC_VT = {"deferred_developer_fee", "grant", "float_earnings"}
        _junc_projects = (
            [_p for _p in _all_projects if _p.id == _primary_pid]
            if _vehicle_type in _PROJECT_SPECIFIC_VT
            else _all_projects
        )
        for _p in _junc_projects:
            _amt = _src_amt_dec if (_p.id == _primary_pid) else Decimal("0")
            session.add(_CMP_create(
                capital_module_id=_cm_id,
                project_id=_p.id,
                amount=_amt,
                active_from=None,
                active_to=_derived_end_phase,
                auto_size=_is_auto,
            ))
        # Auto-create linked DrawSource.  Non-debt vehicle types map to source_type="equity".
        _src_type = "debt" if data["vehicle_type"] == "debt" else "equity"
        # Determine sort order for new DrawSource
        _max_sort = (await session.execute(
            select(func.max(DrawSource.sort_order)).where(DrawSource.scenario_id == model_id)
        )).scalar_one_or_none() or 0
        ds = DrawSource(
            scenario_id=model_id,
            label=data["label"],
            source_type=_src_type,
            sort_order=_max_sort + 1,
            draw_every_n_months=_ds_frequency,
            annual_interest_rate=Decimal(str(_ds_rate)),
            active_from_milestone=_ds_from_ms or "construction",
            active_to_milestone=_ds_to_ms or "maturity",
            active_from_offset_days=_ds_from_offset,
            active_to_offset_days=_ds_to_offset,
            capital_module_id=_cm_id,
        )
        session.add(ds)

    # ── Per-Use eligibility sync (source-side editor writes use-side column) ──
    # Form field `eligible_use_ids[]` lists Use UUIDs this grant funds.
    # Maintains `use_lines.eligible_module_ids` bidirectional consistency:
    #   - For each ticked Use → append this module's ID
    #   - For each previously-linked Use no longer ticked → remove this module's ID
    # Also validates the cap/eligibility combination: maximum requires
    # at least one Use checked, and any ticked Use requires a maximum.
    _module_uuid_for_sync: UUID | None = None
    if item_id:
        try:
            _module_uuid_for_sync = UUID(item_id)
        except (ValueError, AttributeError):
            _module_uuid_for_sync = None
    else:
        _module_uuid_for_sync = _cm_id if "_cm_id" in locals() else None

    if _module_uuid_for_sync is not None:
        _raw_ids = form.getlist("eligible_use_ids")
        _new_eligible: set[UUID] = set()
        for _rid in _raw_ids:
            _rid = (_rid or "").strip()
            if not _rid:
                continue
            try:
                _new_eligible.add(UUID(_rid))
            except (ValueError, AttributeError):
                continue

        _has_maximum = source_d.get("maximum") is not None
        # Validation: maximum + eligibility must agree
        if _has_maximum and not _new_eligible:
            raise HTTPException(
                status_code=422,
                detail="Maximum requires at least one eligible Use to be selected.",
            )
        if _new_eligible and not _has_maximum:
            raise HTTPException(
                status_code=422,
                detail="Eligible Uses selected — Maximum must be entered.",
            )

        # Apply bi-directional sync against all Uses on this scenario
        _all_uses = (await session.execute(
            select(UseLine)
            .join(Project, UseLine.project_id == Project.id)
            .where(Project.scenario_id == model_id)
        )).scalars().all()
        _mod_id_str = str(_module_uuid_for_sync)
        for _ul in _all_uses:
            _cur = [x for x in (_ul.eligible_module_ids or [])]
            _cur_strs = [str(x) for x in _cur]
            _should_include = _ul.id in _new_eligible
            _is_present = _mod_id_str in _cur_strs
            if _should_include and not _is_present:
                _ul.eligible_module_ids = _cur + [_module_uuid_for_sync]
            elif (not _should_include) and _is_present:
                _ul.eligible_module_ids = [
                    x for x in _cur if str(x) != _mod_id_str
                ]
