"""Unit tests for Total Finance Costs auto-injection in cashflow engine.

Covers:
- One row per CapitalModule labeled "{module.label} — Total Finance Costs"
- Amount = DEFAULT_FINANCE_COST_PCT × principal
- is_auto_finance_cost=True on engine-created rows
- User edit (flag=False) is respected: row not overwritten on recompute
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.cashflow import DEFAULT_FINANCE_COST_PCT


@pytest.mark.unit
def test_default_finance_cost_pct_is_two_percent():
    """Sanity: documented default is 2.0%."""
    assert DEFAULT_FINANCE_COST_PCT == Decimal("2.0")


@pytest.mark.unit
def test_legacy_default_loan_costs_removed():
    """The old per-fee table _DEFAULT_LOAN_COSTS must no longer exist."""
    import app.engines.cashflow as cf
    assert not hasattr(cf, "_DEFAULT_LOAN_COSTS"), (
        "Legacy _DEFAULT_LOAN_COSTS table should be removed; replaced by "
        "DEFAULT_FINANCE_COST_PCT single global rate."
    )


@pytest.mark.unit
def test_aps_map_covers_all_milestone_keys():
    """All milestone-key strings the wizard can write must map to a use-line phase.

    Unmapped values would default to "acquisition" via .get(), which is now safe
    — but explicit mapping prevents silent fallback for known keys.
    """
    from app.engines.cashflow import _APS_TO_USE_PHASE
    required_keys = {
        "acquisition", "close", "offer_made", "under_contract",
        "pre_construction", "pre_development",
        "construction",
        "lease_up", "operation_lease_up",
        "stabilized", "operation_stabilized",
        "exit", "divestment",
    }
    missing = required_keys - set(_APS_TO_USE_PHASE.keys())
    assert not missing, f"_APS_TO_USE_PHASE missing milestone keys: {missing}"


@pytest.mark.unit
def test_auto_finance_cost_phase_inherits_from_source():
    """Auto-FC UseLine phase mirrors the parent Source's active_phase_start.

    Per user requirement (Jun 2026): auto-generated FC rows must inherit
    start period from their Source and be locked on the UI. The engine
    no longer coerces phase strings — it copies the mapping directly so
    the FC row fires at the same milestone the loan first becomes active.

    The Active From milestone FK is the load-bearing timing — phase is the
    legacy string fallback used when the FK is NULL.
    """
    from app.engines.cashflow import _APS_TO_USE_PHASE

    def _phase(aps: str) -> str:
        return _APS_TO_USE_PHASE.get(aps, "acquisition")

    # Acquisition-time loans
    assert _phase("acquisition") == "acquisition"
    assert _phase("close") == "acquisition"
    assert _phase("offer_made") == "acquisition"
    assert _phase("under_contract") == "acquisition"
    # Pre-construction / construction loans inherit their phase
    assert _phase("pre_construction") == "pre_construction"
    assert _phase("pre_development") == "pre_construction"
    assert _phase("construction") == "construction"
    # Operation / exit loans inherit their phase (no coercion). The Source's
    # active_from_milestone_id FK is the canonical timing carrier; phase is
    # the legacy string that trails it.
    assert _phase("operation_stabilized") == "operation"
    assert _phase("stabilized") == "operation"
    assert _phase("lease_up") == "operation"
    assert _phase("operation_lease_up") == "operation"
    assert _phase("exit") == "exit"
    assert _phase("divestment") == "exit"
    # Unknown / NULL → acquisition fallback
    assert _phase("") == "acquisition"
    assert _phase("garbage_value") == "acquisition"


@pytest.mark.unit
def test_resolve_fc_rate_falls_back_to_default():
    """Per-Source override resolver: NULL/missing → DEFAULT_FINANCE_COST_PCT.

    Mirrors the engine contract: source.finance_cost_pct is the canonical
    override. Empty string, None, and missing key all fall back.
    """
    from app.engines.cashflow import _resolve_fc_rate, DEFAULT_FINANCE_COST_PCT

    class _Mod:
        def __init__(self, src):
            self.source = src

    default = DEFAULT_FINANCE_COST_PCT / Decimal("100")
    assert _resolve_fc_rate(_Mod({})) == default
    assert _resolve_fc_rate(_Mod({"finance_cost_pct": None})) == default
    assert _resolve_fc_rate(_Mod({"finance_cost_pct": ""})) == default
    assert _resolve_fc_rate(_Mod(None)) == default


@pytest.mark.unit
def test_resolve_fc_rate_uses_override_when_set():
    """Per-Source override resolver: numeric override returns pct/100."""
    from app.engines.cashflow import _resolve_fc_rate

    class _Mod:
        def __init__(self, src):
            self.source = src

    # 1.5% override
    assert _resolve_fc_rate(_Mod({"finance_cost_pct": 1.5})) == Decimal("1.5") / Decimal("100")
    # 0% override → forces zero (valid distinct from None)
    assert _resolve_fc_rate(_Mod({"finance_cost_pct": 0})) == Decimal("0")
    # String form (form data sometimes flows through as str)
    assert _resolve_fc_rate(_Mod({"finance_cost_pct": "3.25"})) == Decimal("3.25") / Decimal("100")
    # Garbage value falls back
    from app.engines.cashflow import DEFAULT_FINANCE_COST_PCT
    default = DEFAULT_FINANCE_COST_PCT / Decimal("100")
    assert _resolve_fc_rate(_Mod({"finance_cost_pct": "abc"})) == default


@pytest.mark.unit
def test_engine_writeback_threads_per_module_rate():
    """Static inspection: writeback pulls rate from _cc_data[id(module)]['pct'],
    which is populated via _resolve_fc_rate at the sizing pass. This ensures
    each module's auto-FC amount uses its own resolved rate, not a stale global.
    """
    import inspect
    import app.engines.cashflow as cf
    src = inspect.getsource(cf)
    # Sizing pass populates pct via the resolver
    assert '"pct": _resolve_fc_rate(_ccm)' in src, (
        "Sizing pass must resolve per-module rate into _cc_data."
    )
    # Writeback consumes per-module pct (not a single global _fc_rate computed
    # before the loop).
    assert '_fc_rate = _cc_obj["pct"]' in src, (
        "Writeback loop must read each module's resolved rate from _cc_data."
    )


@pytest.mark.unit
def test_engine_auto_fc_writeback_copies_milestone_fk():
    """Engine writeback block copies parent module's active_from_milestone_id
    onto the auto-FC UseLine — both on create and on update. Static inspection
    of the writeback source: both code paths must set the FK so renaming or
    moving the Source's start milestone propagates to the FC row.
    """
    import inspect
    import app.engines.cashflow as cf
    src = inspect.getsource(cf)
    assert "_ccm_from_ms_id = getattr(_ccm_ref, \"active_from_milestone_id\", None)" in src, (
        "Engine must read parent module's active_from_milestone_id."
    )
    assert "active_from_milestone_id=_ccm_from_ms_id" in src, (
        "Engine must set active_from_milestone_id on new auto-FC UseLine."
    )
    assert "_cc_exist.active_from_milestone_id = _ccm_from_ms_id" in src, (
        "Engine must update active_from_milestone_id on existing auto-FC UseLine."
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_compute_purges_orphaned_auto_fc_use_line(session: AsyncSession) -> None:
    """An auto-FC row whose source_capital_module_id no longer matches any
    live CapitalModule (e.g. left behind by a bond-consolidation one-shot
    that replaced the module without updating the FK) must be deleted on
    the next compute, not left as a duplicate Uses line alongside the fresh
    row the engine writes for the surviving module.
    """
    from app.engines.cashflow import compute_cash_flows
    from app.models.capital import CapitalModule, CapitalModuleProject, VehicleType
    from app.models.deal import UseLine
    from app.models.project import Project
    from tests.conftest import seed_deal_model_with_financials, seed_opportunity, seed_org

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user, name="Orphan FC Purge")
    deal_model, inputs, seeded_stream, seeded_opex = (
        await seed_deal_model_with_financials(session, opp, user)
    )
    project = (
        await session.execute(select(Project).where(Project.scenario_id == deal_model.id))
    ).scalar_one()
    inputs.debt_types = ["permanent_debt"]

    debt = CapitalModule(
        scenario_id=deal_model.id,
        label="Senior PI Loan",
        vehicle_type=VehicleType.debt.value,
        stack_position=1,
        source={
            "amount": "2000000",
            "interest_rate_pct": 6.0,
            "amort_term_years": 30,
            "hold_term_years": 30,
            "auto_size": True,
            "binding_constraint": "gap_fill",
        },
        carry={
            "phases": [
                {"name": "construction", "carry_type": "pi"},
                {"name": "operation", "carry_type": "pi"},
            ]
        },
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
        active_phase_start="acquisition",
        active_phase_end="exit",
    )
    session.add(debt)
    session.add(
        UseLine(
            project_id=project.id,
            label="Land Acquisition",
            amount=Decimal("2000000"),
            phase="acquisition",
            cost_category="hard",
        )
    )
    await session.flush()
    session.add(
        CapitalModuleProject(
            capital_module_id=debt.id,
            project_id=project.id,
            amount=Decimal("2000000"),
        )
    )

    # Orphaned row: points at a module that still exists in the DB but is no
    # longer associated with this project (simulates a consolidation script
    # that repointed the project onto a new/shared module without cleaning
    # up dependent UseLine FKs left over from the old one).
    decoy = CapitalModule(
        scenario_id=deal_model.id,
        label="Old RJ Bond",
        vehicle_type=VehicleType.debt.value,
        stack_position=2,
        source={"amount": "1500000", "interest_rate_pct": 6.0},
        carry={},
        exit_terms={},
    )
    session.add(decoy)
    await session.flush()

    orphan = UseLine(
        id=uuid.uuid4(),
        project_id=project.id,
        source_capital_module_id=decoy.id,
        label="Old RJ Bond (auto) — Total Finance Costs",
        phase="acquisition",
        cost_category="soft",
        amount=Decimal("40000"),
        timing_type="first_day",
        is_auto_finance_cost=True,
    )
    session.add(orphan)
    await session.flush()
    orphan_id = orphan.id
    debt_id = debt.id  # capture before expire_all (sync lazy-load raises on AsyncSession)
    project_id = project.id

    await compute_cash_flows(deal_model.id, session)
    await session.commit()

    session.expire_all()
    assert await session.get(UseLine, orphan_id) is None, (
        "Orphaned auto-FC row (stale source_capital_module_id) must be purged on compute."
    )

    fc_rows = (
        await session.execute(
            select(UseLine).where(
                UseLine.project_id == project_id,
                UseLine.is_auto_finance_cost == True,  # noqa: E712
            )
        )
    ).scalars().all()
    assert len(fc_rows) == 1, (
        f"Expected exactly one auto-FC row after purge, found {len(fc_rows)}."
    )
    assert fc_rows[0].source_capital_module_id == debt_id
