"""Multi-source Developer Fee engine.

Per-Source fee caps, per-(UseLine x Source) inclusion decisions, funded vs
deferred split, milestone-weighted release schedule, and three acquisition
treatments (excluded / split_rate / separate_fee).

Public entry points:
- ``recompute_auto_dev_fee(use_lines, inputs, session, modules=None,
  milestones=None)``: existing signature kept for backward compat with
  cashflow.py and tests. When ``modules`` is None/empty, behavior matches
  the single-source pre-0103 implementation. When ``modules`` is supplied,
  the multi-source pipeline runs.
- ``compute_dev_fee(...)``: thin alias of recompute_auto_dev_fee that
  emphasizes the new multi-source surface for callers that want it.

The engine writes ``dev_fee_binding_context`` on the auto Dev Fee row with
the binding source, per-source allowance table, headroom, funded/deferred
split, release schedule, structural-diff signal, and any pending custom-Use
decisions. Elected fee always wins over caps — overage is reported in the
context, not silently enforced.

See docs/feature-plans/developer-fee-multi-source.md.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import (
    CapitalModule,
    UseLineSourceFeeBasis,
)
from app.models.deal import OperationalInputs, UseLine

ZERO = Decimal("0")
_MONEY_PLACES = Decimal("0.01")

# Standard auto-generated cost categories the engine recognizes for
# ``basis_exclusions``. Custom UseLines whose cost_category is outside this
# set route through use_line_source_fee_basis for inclusion decisions.
STANDARD_COST_CATEGORIES = frozenset(
    {
        "acquisition",
        "hard_costs",
        "soft_costs",
        "financing_fees",
        "interest_reserve",
        "operating_reserves",
        "developer_overhead",
        "consulting_fees",
    }
)

# Acquisition treatment variants.
ACQ_EXCLUDED = "excluded"
ACQ_SPLIT_RATE = "split_rate"
ACQ_SEPARATE_FEE = "separate_fee"
ACQ_TREATMENTS = (ACQ_EXCLUDED, ACQ_SPLIT_RATE, ACQ_SEPARATE_FEE)


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return ZERO
    try:
        return Decimal(str(value))
    except Exception:
        return ZERO


def _phase_value(use_line: UseLine) -> str:
    phase_val = getattr(use_line, "phase", None)
    return str(getattr(phase_val, "value", phase_val) or "")


def _is_acquisition_use(use_line: UseLine) -> bool:
    """True when the UseLine represents acquisition cost.

    Matches the UI seed convention used by ``_resolve_purchase_price``:
    phase=acquisition AND cost_category=acquisition. We also treat any row
    whose cost_category is "acquisition" as acquisition (covers test fixtures
    that don't set phase explicitly).
    """
    if (use_line.cost_category or "") == "acquisition":
        return True
    return _phase_value(use_line) == "acquisition" and (
        (use_line.cost_category or "") == "acquisition"
    )


def _resolve_purchase_price(
    inputs: OperationalInputs | None,
    use_lines: Iterable[UseLine],
) -> Decimal:
    """Prefer OperationalInputs.purchase_price; fall back to acquisition-phase Uses."""
    if inputs is not None:
        pp = _to_decimal(inputs.purchase_price)
        if pp > ZERO:
            return pp
    total = ZERO
    for u in use_lines:
        if u.is_auto_dev_fee or getattr(u, "is_auto_acquisition_fee", False):
            continue
        if _is_acquisition_use(u):
            total += _to_decimal(u.amount)
    return total


def _project_units(inputs: OperationalInputs | None) -> int:
    """Sum of (existing or new) unit counts from OperationalInputs.

    Used for per_unit_cap evaluation. Conservative: prefers the larger of
    after-conversion vs existing+new since fee caps usually reference the
    final unit count delivered.
    """
    if inputs is None:
        return 0
    after = getattr(inputs, "unit_count_after_conversion", None)
    if after is not None:
        try:
            return int(after)
        except Exception:
            pass
    existing = int(getattr(inputs, "unit_count_existing", 0) or 0)
    new = int(getattr(inputs, "unit_count_new", 0) or 0)
    return existing + new


# ---------------------------------------------------------------------------
# Inheritance resolution: live read of Source Vehicle preset fee_terms.
# ---------------------------------------------------------------------------


async def _load_vehicle_fee_defaults(
    modules: Sequence[CapitalModule],
    session: AsyncSession,
) -> dict[object, dict]:
    """Load fee_terms from each preset referenced by ``CapitalModule.source_vehicle_id``.

    Returns ``{source_vehicle_id: fee_terms_dict}``. Modules with no
    ``source_vehicle_id`` (manual-add, not from a preset) are absent and
    fall back to the module's own ``fee_terms`` column.
    """
    sv_ids = {
        m.source_vehicle_id for m in modules if getattr(m, "source_vehicle_id", None)
    }
    if not sv_ids:
        return {}
    from app.models.source_vehicle import SourceVehicle

    rows = (
        await session.execute(
            select(SourceVehicle.id, SourceVehicle.fee_terms).where(
                SourceVehicle.id.in_(sv_ids)
            )
        )
    ).all()
    return {row.id: dict(row.fee_terms or {}) for row in rows}


def _effective_fee_terms(
    module: CapitalModule,
    defaults_map: dict[object, dict],
) -> dict:
    """Resolve fee_terms for a CapitalModule, applying preset inheritance.

    Returns an empty dict when neither instance override nor the preset
    carries a rule — callers treat that as "no terms" and skip the Vehicle
    in the binding constraint.
    """
    if not getattr(module, "fee_terms_inherited_from_type", True):
        return dict(getattr(module, "fee_terms", {}) or {})
    sv_id = getattr(module, "source_vehicle_id", None)
    if sv_id is not None:
        inherited = defaults_map.get(sv_id)
        if inherited:
            return dict(inherited)
    # No preset linkage or preset has no rule — fall back to instance column.
    return dict(getattr(module, "fee_terms", {}) or {})


# ---------------------------------------------------------------------------
# Use × Vehicle inclusion logic.
# ---------------------------------------------------------------------------


async def _load_use_line_overrides(
    use_lines: Sequence[UseLine],
    session: AsyncSession,
) -> dict[tuple[object, object], bool]:
    """Load `use_line_source_fee_basis` rows for these UseLines.

    Returns ``{(use_line_id, capital_module_id): included_in_basis}``.
    Missing keys signal a pending decision when the UseLine is custom.
    """
    ids = [u.id for u in use_lines if u.id is not None]
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(UseLineSourceFeeBasis).where(
                UseLineSourceFeeBasis.use_line_id.in_(ids)
            )
        )
    ).scalars().all()
    return {(r.use_line_id, r.capital_module_id): r.included_in_basis for r in rows}


def _use_in_vehicle_basis(
    use_line: UseLine,
    module: CapitalModule,
    fee_terms: dict,
    overrides_index: dict[tuple[object, object], bool],
) -> tuple[bool, bool]:
    """Return ``(included, decision_pending)`` for one (UseLine, Vehicle) pair.

    Standard categories follow the Vehicle's ``basis_exclusions``. Custom
    Uses (cost_category outside ``STANDARD_COST_CATEGORIES``) require a
    ``use_line_source_fee_basis`` row; if missing, the engine flags the pair
    as pending and conservatively excludes it.

    The auto Dev Fee row and auto Acquisition Fee row are never in any
    Vehicle's basis (fee-on-fee is handled in the elected-fee iterative
    solve, not in the caps).
    """
    if use_line.is_auto_dev_fee or getattr(use_line, "is_auto_acquisition_fee", False):
        return (False, False)

    category = (use_line.cost_category or "").lower()

    # basis_inclusions_override escape hatch (forward-looking; replaces all
    # inclusion logic when set).
    inclusion_override = fee_terms.get("basis_inclusions_override")
    if isinstance(inclusion_override, list) and inclusion_override:
        return (category in inclusion_override, False)

    exclusions = fee_terms.get("basis_exclusions") or []
    if not isinstance(exclusions, list):
        exclusions = []
    exclusions_set = {str(e).lower() for e in exclusions}

    if category in STANDARD_COST_CATEGORIES:
        return (category not in exclusions_set, False)

    # Custom use: look up override.
    key = (use_line.id, module.id)
    if key in overrides_index:
        return (overrides_index[key], False)
    return (False, True)


# ---------------------------------------------------------------------------
# Per-Vehicle basis and allowable.
# ---------------------------------------------------------------------------


def _vehicle_basis(
    module: CapitalModule,
    use_lines: Sequence[UseLine],
    fee_terms: dict,
    overrides_index: dict[tuple[object, object], bool],
    acquisition_only: bool = False,
    exclude_acquisition: bool = False,
) -> tuple[Decimal, list[tuple[object, object]]]:
    """Sum amounts of UseLines included in this Vehicle's fee basis.

    ``acquisition_only=True`` restricts to acquisition cost_category (for the
    split_rate acquisition portion). ``exclude_acquisition=True`` removes
    acquisition cost_category (for the standard Dev Fee basis in excluded /
    separate_fee / split_rate-construction modes).

    Returns ``(basis_total, pending_pairs)`` where pending_pairs is a list
    of (use_line_id, capital_module_id) tuples for custom Uses missing an
    inclusion decision.
    """
    total = ZERO
    pending: list[tuple[object, object]] = []
    for u in use_lines:
        is_acq = _is_acquisition_use(u)
        if acquisition_only and not is_acq:
            continue
        if exclude_acquisition and is_acq:
            continue
        included, is_pending = _use_in_vehicle_basis(u, module, fee_terms, overrides_index)
        if is_pending:
            pending.append((u.id, module.id))
        if included:
            total += _to_decimal(u.amount)
    return total, pending


def _vehicle_allowable(
    module: CapitalModule,
    fee_terms: dict,
    basis_value: Decimal,
    units: int,
) -> Decimal | None:
    """Compute the maximum allowable fee this Vehicle would accept on `basis_value`.

    Returns None when the Vehicle has no caps at all (skip from binding).
    Otherwise applies the strictest of ``max_pct × basis``, ``per_unit_cap ×
    units``, and ``absolute_cap``.
    """
    max_pct = fee_terms.get("max_pct")
    per_unit_cap = fee_terms.get("per_unit_cap")
    absolute_cap = fee_terms.get("absolute_cap")
    if max_pct is None and per_unit_cap is None and absolute_cap is None:
        return None
    candidates: list[Decimal] = []
    if max_pct is not None:
        candidates.append((_to_decimal(max_pct) / Decimal("100")) * basis_value)
    if per_unit_cap is not None and units > 0:
        candidates.append(_to_decimal(per_unit_cap) * Decimal(units))
    if absolute_cap is not None:
        candidates.append(_to_decimal(absolute_cap))
    if not candidates:
        return None
    return min(candidates)


# ---------------------------------------------------------------------------
# Binding constraint + funded/deferred allocation.
# ---------------------------------------------------------------------------


def _binding_constraint(
    constrained: list[dict],
) -> tuple[Decimal | None, object | None]:
    """Pick the strictest Vehicle from a list of ``allowance`` rows.

    Each row in ``constrained`` is a dict with keys
    ``capital_module_id``, ``allowable``. Returns ``(min_allowable,
    binding_module_id)`` or ``(None, None)`` if no constrained Vehicles.
    """
    if not constrained:
        return (None, None)
    binding = min(constrained, key=lambda r: r["allowable"])
    return (binding["allowable"], binding["capital_module_id"])


def _split_funded_deferred(
    elected_fee: Decimal,
    allowances: list[dict],
) -> tuple[Decimal, Decimal, list[dict]]:
    """Allocate the elected fee across constrained Vehicles up to each cap.

    Greedy, capacity-ordered allocation: each constrained Vehicle funds up
    to its own allowance; unconstrained Vehicles are skipped here (their
    funding is governed by elsewhere in the capital stack). The remainder
    after all constrained Vehicles are filled becomes deferred.

    Returns ``(funded_at_close, deferred, per_source_allocation)``.
    """
    remaining = elected_fee
    per_source: list[dict] = []
    for row in sorted(allowances, key=lambda r: r["allowable"] or ZERO, reverse=True):
        if row["allowable"] is None:
            continue
        cap = row["allowable"]
        contribution = min(cap, remaining) if remaining > ZERO else ZERO
        if contribution < ZERO:
            contribution = ZERO
        remaining -= contribution
        per_source.append(
            {
                "capital_module_id": str(row["capital_module_id"]),
                "vehicle_label": row.get("vehicle_label"),
                "allowable": str(cap),
                "funded_at_close": str(contribution),
                "basis": str(row.get("basis", ZERO)),
            }
        )
    funded = elected_fee - remaining if remaining >= ZERO else elected_fee
    deferred = remaining if remaining > ZERO else ZERO
    return funded, deferred, per_source


# ---------------------------------------------------------------------------
# Release schedule (milestone-weighted dated receipts).
# ---------------------------------------------------------------------------


def _build_release_schedule(
    schedule_cfg: dict,
    elected_fee: Decimal,
    milestone_dates: dict[object, str],
) -> list[dict]:
    """Translate a milestone weight config into a list of dated receipts.

    Returns ``[{milestone_id, date, weight, amount}, ...]`` plus the final
    holdback row when configured. Missing milestone dates are emitted with
    ``date=None`` so the UI can flag them, but the engine does not error.
    """
    if not schedule_cfg:
        return []
    receipts: list[dict] = []
    weights = schedule_cfg.get("weights") or []
    for entry in weights:
        mid = entry.get("milestone_id")
        weight = _to_decimal(entry.get("weight"))
        receipts.append(
            {
                "milestone_id": str(mid) if mid is not None else None,
                "date": milestone_dates.get(mid) if mid is not None else None,
                "weight": str(weight),
                "amount": str((weight * elected_fee).quantize(_MONEY_PLACES)),
                "type": "weighted",
            }
        )
    holdback = schedule_cfg.get("final_holdback") or {}
    holdback_pct = _to_decimal(holdback.get("pct"))
    if holdback_pct > ZERO:
        mid = holdback.get("milestone_id")
        receipts.append(
            {
                "milestone_id": str(mid) if mid is not None else None,
                "date": milestone_dates.get(mid) if mid is not None else None,
                "weight": str(holdback_pct),
                "amount": str((holdback_pct * elected_fee).quantize(_MONEY_PLACES)),
                "type": "final_holdback",
            }
        )
    return receipts


# ---------------------------------------------------------------------------
# Structural diff (set of CapitalModule + UseLine IDs).
# ---------------------------------------------------------------------------


def _compute_structural_signature(
    modules: Sequence[CapitalModule],
    use_lines: Sequence[UseLine],
) -> str:
    """Deterministic hash of (sorted module IDs, sorted use-line IDs).

    Excludes the auto Dev Fee / auto Acquisition Fee rows from the signature
    so recomputes that only change those amounts don't trip the diff.
    """
    mod_ids = sorted(str(m.id) for m in modules if getattr(m, "id", None) is not None)
    use_ids = sorted(
        str(u.id)
        for u in use_lines
        if u.id is not None
        and not u.is_auto_dev_fee
        and not getattr(u, "is_auto_acquisition_fee", False)
    )
    payload = ("|".join(mod_ids) + "::" + "|".join(use_ids)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _diff_signatures(
    prev_sig: str | None,
    modules: Sequence[CapitalModule],
    use_lines: Sequence[UseLine],
) -> tuple[bool, dict, str]:
    """Compare previous structural signature against current shape.

    Returns ``(diff_detected, delta_dict, new_signature)``. Delta lists which
    module IDs and use-line IDs were added/removed when the signature is
    available. When no prior signature exists, ``diff_detected=False`` (first
    compute is the baseline).
    """
    new_sig = _compute_structural_signature(modules, use_lines)
    if not prev_sig:
        return (False, {}, new_sig)
    if prev_sig == new_sig:
        return (False, {}, new_sig)
    # Best-effort delta: we don't have the prior set, just signal the change.
    delta = {"changed": True, "previous_signature": prev_sig, "current_signature": new_sig}
    return (True, delta, new_sig)


# ---------------------------------------------------------------------------
# Single-fee compute (used twice in separate_fee mode).
# ---------------------------------------------------------------------------


def _compute_one_fee(
    *,
    elected_fee: Decimal,
    modules: Sequence[CapitalModule],
    use_lines: Sequence[UseLine],
    overrides_index: dict[tuple[object, object], bool],
    effective_terms_by_module: dict[object, dict],
    units: int,
    acquisition_only: bool,
    exclude_acquisition: bool,
) -> dict:
    """Run the binding-constraint pipeline for one fee (Dev Fee or Acq Fee).

    Returns the binding-context block for this fee: per-source allowance
    table, binding row, overage, funded/deferred split, pending custom-use
    decisions.
    """
    allowances: list[dict] = []
    pending: list[tuple[object, object]] = []
    for module in modules:
        fee_terms = effective_terms_by_module.get(module.id, {})
        if not fee_terms:
            continue
        basis_value, pending_pairs = _vehicle_basis(
            module,
            use_lines,
            fee_terms,
            overrides_index,
            acquisition_only=acquisition_only,
            exclude_acquisition=exclude_acquisition,
        )
        pending.extend(pending_pairs)
        allowable = _vehicle_allowable(module, fee_terms, basis_value, units)
        if allowable is None:
            continue
        allowances.append(
            {
                "capital_module_id": module.id,
                "vehicle_label": module.label,
                "vehicle_type": module.vehicle_type,
                "basis": basis_value,
                "allowable": allowable,
                "max_pct": fee_terms.get("max_pct"),
                "per_unit_cap": fee_terms.get("per_unit_cap"),
                "absolute_cap": fee_terms.get("absolute_cap"),
            }
        )

    binding_cap, binding_id = _binding_constraint(allowances)
    overage = ZERO
    if binding_cap is not None and elected_fee > binding_cap:
        overage = elected_fee - binding_cap

    funded, deferred, per_source = _split_funded_deferred(elected_fee, allowances)

    pending_unique = sorted({(str(u), str(m)) for (u, m) in pending})
    return {
        "elected_fee": str(elected_fee),
        "binding_source_id": str(binding_id) if binding_id is not None else None,
        "binding_dollar_cap": str(binding_cap) if binding_cap is not None else None,
        "overage": str(overage),
        "per_source_allocation": per_source,
        "headroom_by_source": {
            str(a["capital_module_id"]): str(a["allowable"] - elected_fee)
            for a in allowances
        },
        "funded_at_close": str(funded),
        "deferred": str(deferred),
        "pending_custom_use_decisions": [
            {"use_line_id": u, "capital_module_id": m} for (u, m) in pending_unique
        ],
        "allowance_table": [
            {
                "capital_module_id": str(a["capital_module_id"]),
                "vehicle_label": a["vehicle_label"],
                "vehicle_type": a["vehicle_type"],
                "basis": str(a["basis"]),
                "allowable": str(a["allowable"]),
                "max_pct": str(a["max_pct"]) if a["max_pct"] is not None else None,
                "per_unit_cap": str(a["per_unit_cap"]) if a["per_unit_cap"] is not None else None,
                "absolute_cap": str(a["absolute_cap"]) if a["absolute_cap"] is not None else None,
                "is_binding": a["capital_module_id"] == binding_id,
            }
            for a in allowances
        ],
    }


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


async def recompute_auto_dev_fee(
    use_lines: list[UseLine],
    inputs: OperationalInputs | None,
    session: AsyncSession,
    modules: Sequence[CapitalModule] | None = None,
    milestone_dates: dict[object, str] | None = None,
    org_id: object | None = None,
) -> None:
    """Recompute the auto Dev Fee UseLine for one project.

    Backward-compatible signature: when ``modules`` is None/empty, behavior
    is identical to the pre-0103 single-source path — the auto Dev Fee row's
    ``amount`` is recomputed from ``dev_fee_pct × basis`` only and no
    binding context is written.

    When ``modules`` is supplied, the multi-source pipeline runs:
    inheritance resolution, per-Vehicle basis and allowable, binding
    constraint, funded/deferred split, release schedule, structural-diff
    signal, and pending custom-use decisions are written to the auto Dev
    Fee row's ``dev_fee_binding_context``.

    In ``separate_fee`` mode, the auto Acquisition Fee row is also
    recomputed (if present) and its own binding context block is stored
    under ``acquisition_fee_context`` on the Dev Fee row.
    """
    auto_line = next((u for u in use_lines if getattr(u, "is_auto_dev_fee", False)), None)
    if auto_line is None:
        return

    pct_raw = getattr(auto_line, "dev_fee_pct", None)
    if pct_raw is None:
        return
    pct = _to_decimal(pct_raw) / Decimal("100")

    treatment_raw = getattr(auto_line, "dev_fee_acquisition_treatment", None)
    # Unset → legacy "include all non-self UseLines" path (sum_all). Only when
    # the user explicitly picks a treatment do we partition or exclude.
    treatment = treatment_raw if treatment_raw in ACQ_TREATMENTS else None
    basis = getattr(auto_line, "dev_fee_basis", None) or "tpc_excl_self"

    # ------------------------------------------------------------------
    # Compute the elected Dev Fee amount based on treatment + basis.
    # ------------------------------------------------------------------
    if basis == "purchase_price":
        base = _resolve_purchase_price(inputs, use_lines)
        new_amount = (pct * base).quantize(_MONEY_PLACES)
    elif treatment == ACQ_SPLIT_RATE:
        construction_basis = sum(
            (
                _to_decimal(u.amount)
                for u in use_lines
                if not u.is_auto_dev_fee
                and not getattr(u, "is_auto_acquisition_fee", False)
                and not _is_acquisition_use(u)
            ),
            ZERO,
        )
        acquisition_basis = sum(
            (
                _to_decimal(u.amount)
                for u in use_lines
                if not u.is_auto_dev_fee
                and not getattr(u, "is_auto_acquisition_fee", False)
                and _is_acquisition_use(u)
            ),
            ZERO,
        )
        acq_pct_raw = getattr(auto_line, "dev_fee_acquisition_pct", None) or ZERO
        acq_pct = _to_decimal(acq_pct_raw) / Decimal("100")
        new_amount = (
            pct * construction_basis + acq_pct * acquisition_basis
        ).quantize(_MONEY_PLACES)
    elif treatment in (ACQ_EXCLUDED, ACQ_SEPARATE_FEE):
        # Explicit excluded / separate_fee: standard Dev Fee on TPC excl.
        # acquisition and excl. self / acquisition fee row.
        base = sum(
            (
                _to_decimal(u.amount)
                for u in use_lines
                if not u.is_auto_dev_fee
                and not getattr(u, "is_auto_acquisition_fee", False)
                and not _is_acquisition_use(u)
            ),
            ZERO,
        )
        new_amount = (pct * base).quantize(_MONEY_PLACES)
    else:
        # Legacy: treatment unset → sum all non-self UseLines, including
        # acquisition. Pre-0103 behavior, preserved for backward compat.
        base = sum(
            (
                _to_decimal(u.amount)
                for u in use_lines
                if not u.is_auto_dev_fee
                and not getattr(u, "is_auto_acquisition_fee", False)
            ),
            ZERO,
        )
        new_amount = (pct * base).quantize(_MONEY_PLACES)

    if _to_decimal(auto_line.amount) != new_amount:
        auto_line.amount = new_amount

    # ------------------------------------------------------------------
    # Acquisition Fee row (separate_fee mode).
    # ------------------------------------------------------------------
    acq_fee_line = next(
        (u for u in use_lines if getattr(u, "is_auto_acquisition_fee", False)),
        None,
    )
    if treatment == ACQ_SEPARATE_FEE and acq_fee_line is not None:
        acq_fee_pct_raw = getattr(acq_fee_line, "acquisition_fee_pct", None) or ZERO
        acq_fee_pct = _to_decimal(acq_fee_pct_raw) / Decimal("100")
        purchase_price = _resolve_purchase_price(inputs, use_lines)
        acq_fee_amount = (acq_fee_pct * purchase_price).quantize(_MONEY_PLACES)
        if _to_decimal(acq_fee_line.amount) != acq_fee_amount:
            acq_fee_line.amount = acq_fee_amount

    # ------------------------------------------------------------------
    # Multi-source binding pipeline (only when modules supplied).
    # ------------------------------------------------------------------
    if not modules:
        await session.flush()
        return

    defaults_map = await _load_vehicle_fee_defaults(modules, session)
    effective_terms_by_module: dict[object, dict] = {
        m.id: _effective_fee_terms(m, defaults_map) for m in modules
    }
    overrides_index = await _load_use_line_overrides(use_lines, session)

    # Determine basis-mode flags for the standard Dev Fee fee compute.
    if treatment == ACQ_SPLIT_RATE:
        # Two parallel basis-mode computes: construction and acquisition.
        construction_block = _compute_one_fee(
            elected_fee=(pct * sum(
                (
                    _to_decimal(u.amount)
                    for u in use_lines
                    if not u.is_auto_dev_fee
                    and not getattr(u, "is_auto_acquisition_fee", False)
                    and not _is_acquisition_use(u)
                ),
                ZERO,
            )).quantize(_MONEY_PLACES),
            modules=modules,
            use_lines=use_lines,
            overrides_index=overrides_index,
            effective_terms_by_module=effective_terms_by_module,
            units=_project_units(inputs),
            acquisition_only=False,
            exclude_acquisition=True,
        )
        acq_pct_raw = getattr(auto_line, "dev_fee_acquisition_pct", None) or ZERO
        acq_pct = _to_decimal(acq_pct_raw) / Decimal("100")
        acq_block = _compute_one_fee(
            elected_fee=(acq_pct * sum(
                (
                    _to_decimal(u.amount)
                    for u in use_lines
                    if not u.is_auto_dev_fee
                    and not getattr(u, "is_auto_acquisition_fee", False)
                    and _is_acquisition_use(u)
                ),
                ZERO,
            )).quantize(_MONEY_PLACES),
            modules=modules,
            use_lines=use_lines,
            overrides_index=overrides_index,
            effective_terms_by_module=effective_terms_by_module,
            units=_project_units(inputs),
            acquisition_only=True,
            exclude_acquisition=False,
        )
        dev_fee_block = {
            "elected_fee": str(new_amount),
            "split_rate_construction": construction_block,
            "split_rate_acquisition": acq_block,
            "binding_source_id": (
                construction_block.get("binding_source_id")
                or acq_block.get("binding_source_id")
            ),
            "binding_dollar_cap": None,
            "overage": str(
                _to_decimal(construction_block.get("overage")) + _to_decimal(acq_block.get("overage"))
            ),
            "per_source_allocation": (
                construction_block.get("per_source_allocation", [])
                + acq_block.get("per_source_allocation", [])
            ),
            "headroom_by_source": {
                **construction_block.get("headroom_by_source", {}),
                **acq_block.get("headroom_by_source", {}),
            },
            "funded_at_close": str(
                _to_decimal(construction_block.get("funded_at_close"))
                + _to_decimal(acq_block.get("funded_at_close"))
            ),
            "deferred": str(
                _to_decimal(construction_block.get("deferred"))
                + _to_decimal(acq_block.get("deferred"))
            ),
            "pending_custom_use_decisions": (
                construction_block.get("pending_custom_use_decisions", [])
                + acq_block.get("pending_custom_use_decisions", [])
            ),
            "allowance_table": (
                construction_block.get("allowance_table", [])
                + acq_block.get("allowance_table", [])
            ),
        }
    else:
        # excluded / separate_fee / legacy (None): standard Dev Fee basis.
        # In excluded/separate_fee modes acquisition is removed from each
        # Vehicle's per-Vehicle basis; in legacy mode (None) each Vehicle's
        # basis still honors its own basis_exclusions but acquisition is
        # NOT auto-excluded — Vehicles can list "acquisition" in their
        # basis_exclusions if they want it out.
        dev_fee_block = _compute_one_fee(
            elected_fee=new_amount,
            modules=modules,
            use_lines=use_lines,
            overrides_index=overrides_index,
            effective_terms_by_module=effective_terms_by_module,
            units=_project_units(inputs),
            acquisition_only=False,
            exclude_acquisition=treatment in (ACQ_EXCLUDED, ACQ_SEPARATE_FEE),
        )

    # Release schedule.
    release_cfg = dict(getattr(auto_line, "dev_fee_release_schedule", {}) or {})
    release_receipts = _build_release_schedule(
        release_cfg, new_amount, milestone_dates or {}
    )

    # Structural diff against previous signature.
    prev_ctx = dict(getattr(auto_line, "dev_fee_binding_context", {}) or {})
    prev_sig = prev_ctx.get("last_compute_signature")
    diff_detected, delta, new_sig = _diff_signatures(prev_sig, modules, use_lines)

    # Acquisition Fee parallel block (separate_fee mode only).
    acq_fee_context = None
    if treatment == ACQ_SEPARATE_FEE and acq_fee_line is not None:
        acq_fee_context = _compute_one_fee(
            elected_fee=_to_decimal(acq_fee_line.amount),
            modules=modules,
            use_lines=use_lines,
            overrides_index=overrides_index,
            effective_terms_by_module=effective_terms_by_module,
            units=_project_units(inputs),
            acquisition_only=True,
            exclude_acquisition=False,
        )

    binding_ctx = {
        **dev_fee_block,
        "acquisition_treatment": treatment,
        "acquisition_fee_context": acq_fee_context,
        "release_schedule": release_receipts,
        "last_compute_signature": new_sig,
        "structural_diff_detected": diff_detected,
        "structural_diff_delta": delta,
    }
    auto_line.dev_fee_binding_context = binding_ctx
    await session.flush()


# Alias preferred by new callers; the legacy name is kept for cashflow.py
# and the existing test suite.
compute_dev_fee = recompute_auto_dev_fee
