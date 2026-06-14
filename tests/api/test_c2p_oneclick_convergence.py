"""Construction-to-perm one-click convergence.

A construction loan (retired by a permanent loan) on a deal whose operating
window runs a cash shortfall needs the auto-managed Cash Flow Support Reserve
to cover it. The reserve folds into total_uses and grows the perm loan. The
reserve is written at the END of a compute pass — after the perm has already
been sized — so on its own a single pass would leave Sources < Uses by ~the
reserve amount. The engine signals ``needs_recompute`` so the compute
endpoint's fix-point loop re-sizes the perm to fund the reserve, converging
Sources = Uses in one user click.

Regression history: that ``needs_recompute`` signal was once suppressed for
multi-debt construction deals because forcing the loop to iterate was thought
to (a) drift the construction-loan principal below its own base cost in the
bridge/retirement writeback and (b) diverge geometrically for
capitalized-interest carry (runaway bond → overflow → 500). PR #15's reserve
reset + overflow-safe accumulation + the endpoint divergence guard neutralised
both, so the signal was re-enabled. These tests pin that it stays fixed.

Covered:
  - wizard-timeline c2p across IR / CI / IO construction carry → Sources = Uses
    in one compute, idempotent (no runaway, esp. capitalized_interest)
  - acquisition retire-and-replace → construction-loan principal stays at
    base + carry and is pass-stable (no drift below base)

Run:
    uv run pytest tests/api/test_c2p_oneclick_convergence.py -v -s
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule
from app.models.deal import UseLine
from app.models.milestone import Milestone, MilestoneType
from app.models.project import Project
from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_CFSR = "Cash Flow Support Reserve"
_CONSTR_BASE = Decimal("3000000")  # Hard Construction use line


async def _seed_c2p_deal(
    session: AsyncSession, overrides: dict | None = None
) -> tuple[str, str]:
    """Construction loan (interest_reserve, retired by perm) + permanent loan
    (pi, gap_fill), on a deal whose lease-up produces an operating shortfall."""
    overrides = overrides or {}
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, inputs, income, _opex = await seed_deal_model_with_financials(
        session, opp, user
    )
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()

    inputs.purchase_price = Decimal("1000000")
    inputs.closing_costs_pct = Decimal("2.0")
    inputs.renovation_cost_total = _CONSTR_BASE
    inputs.renovation_months = 12
    inputs.lease_up_months = 6
    inputs.initial_occupancy_pct = Decimal("0")
    inputs.debt_sizing_mode = "gap_fill"
    for _k, _v in overrides.items():
        if _k == "income_per_unit_monthly":
            income.amount_per_unit_monthly = Decimal(str(_v))
        else:
            setattr(inputs, _k, _v)
    session.add(income)
    inputs.debt_types = ["construction_loan", "permanent_debt"]
    inputs.debt_terms = {
        "construction_loan": {"loan_type": "interest_reserve", "rate_pct": "7.0", "ltv_pct": "100"},
        "permanent_debt": {"loan_type": "pi", "rate_pct": "6.5", "amort_years": "30"},
    }
    session.add(inputs)

    perm = CapitalModule(
        scenario_id=deal_model.id,
        label="Permanent Loan",
        vehicle_type="debt",
        stack_position=2,
        source={"amount": 0, "interest_rate_pct": 6.5, "auto_size": True, "amort_term_years": 30},
        carry={"carry_type": "pi", "payment_frequency": "monthly"},
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
        active_phase_start="operation_stabilized",
        active_phase_end="exit",
    )
    session.add(perm)
    await session.flush()

    constr = CapitalModule(
        scenario_id=deal_model.id,
        label="Construction Loan",
        vehicle_type="debt",
        stack_position=1,
        source={"amount": 0, "interest_rate_pct": 7.0, "auto_size": True, "ltv_pct": 100},
        carry={"carry_type": "interest_reserve", "payment_frequency": "monthly"},
        # Retired by the perm loan at handoff.
        exit_terms={"exit_type": "full_payoff", "vehicle": str(perm.id)},
        active_phase_start="construction",
        active_phase_end="operation_stabilized",
    )
    session.add(constr)

    session.add_all(
        [
            UseLine(
                project_id=project.id, label="Acquisition", phase="acquisition",
                amount=Decimal("1000000"), cost_category="hard", timing_type="first_day",
            ),
            UseLine(
                project_id=project.id, label="Hard Construction", phase="construction",
                amount=_CONSTR_BASE, cost_category="hard", timing_type="first_day",
            ),
        ]
    )
    await session.commit()
    return str(deal_model.id), str(project.id)


async def _snapshot(session: AsyncSession, model_id: str, project_id: str) -> dict:
    """Sources - Uses gap (as the S&U panel shows it) + construction principal."""
    session.expire_all()
    use_lines = (
        await session.execute(
            select(UseLine).where(UseLine.project_id == project_id)
        )
    ).scalars().all()
    modules = (
        await session.execute(
            select(CapitalModule).where(CapitalModule.scenario_id == model_id)
        )
    ).scalars().all()

    uses = sum(
        Decimal(str(u.amount or 0))
        for u in use_lines
        if str(getattr(u.phase, "value", u.phase) or "") != "exit"
    )
    # Sources panel excludes is_bridge loans (they're refinanced away).
    sources = sum(
        Decimal(str((m.source or {}).get("amount") or 0))
        for m in modules
        if not (m.source or {}).get("is_bridge")
    )
    constr = next((m for m in modules if "construction" in (m.label or "").lower()), None)
    cfsr = next((u for u in use_lines if (u.label or "") == _CFSR), None)
    return {
        "gap": sources - uses,
        "uses": uses,
        "sources": sources,
        "constr_principal": Decimal(str((constr.source or {}).get("amount") or 0)) if constr else None,
        "cfsr": Decimal(str(cfsr.amount or 0)) if cfsr else Decimal("0"),
    }


async def test_c2p_converges_in_one_compute(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    model_id, project_id = await _seed_c2p_deal(session)

    snaps = []
    for i in range(3):
        r = await client.post(f"/api/models/{model_id}/compute", headers=auth_headers)
        assert r.status_code == 200, r.text
        s = await _snapshot(session, model_id, project_id)
        snaps.append(s)
        print(
            f"compute {i+1}: gap={s['gap']:.0f} uses={s['uses']:.0f} "
            f"sources={s['sources']:.0f} constr_P={s['constr_principal']} "
            f"cfsr={s['cfsr']:.0f}"
        )

    # Construction principal must never drop below its base cost on any pass —
    # this is the bridge/retirement-sizing stability the convergence fix must
    # preserve.
    for i, s in enumerate(snaps):
        assert s["constr_principal"] is None or s["constr_principal"] >= _CONSTR_BASE, (
            f"compute {i+1}: construction principal {s['constr_principal']} "
            f"sized below base {_CONSTR_BASE}"
        )

    # One compute should converge Sources = Uses (within $100).
    assert abs(snaps[0]["gap"]) < Decimal("100"), (
        f"one compute left a gap of ${snaps[0]['gap']:.0f} "
        f"(uses={snaps[0]['uses']:.0f}, sources={snaps[0]['sources']:.0f}) — "
        f"construction-to-perm did not converge in a single click"
    )

    # And it must be idempotent: further computes don't move the gap.
    assert abs(snaps[2]["gap"] - snaps[0]["gap"]) < Decimal("100"), (
        f"gap drifted across computes: {[float(s['gap']) for s in snaps]}"
    )


# ---------------------------------------------------------------------------
# Wizard-timeline reproduction (milestone-based phases)
#
# The phase_b E2E case `ir_12mo`, built through the real setup wizard with a
# milestone timeline (pre_development + 365-day construction + 1095-day
# stabilized hold), undersizes the permanent loan in a single compute. The ORM
# scalar-months seed above does NOT reproduce this — the trigger is the
# milestone-based multi-phase timeline. This seed mirrors ir_12mo faithfully:
# value_add, the same five milestones with the same durations, the same debt
# terms, the same three use lines.
# ---------------------------------------------------------------------------

_WIZ_PURCHASE = Decimal("800000")
_WIZ_HARD = Decimal("600000")
_WIZ_CLOSING = Decimal("16000")


async def _seed_c2p_wizard_deal(
    session: AsyncSession,
    overrides: dict | None = None,
    constr_carry_type: str = "interest_reserve",
) -> tuple[str, str]:
    """Construction-to-perm deal built like the wizard: value_add project with a
    milestone timeline (pre_development=60d, construction=365d, stabilized=1095d),
    construction loan (retired by perm) + permanent loan (pi).

    ``constr_carry_type`` selects the construction loan's carry: interest_reserve,
    capitalized_interest, or io_only — mirroring the phase_b ir_12mo / ci_12mo /
    constr_perm_io_12mo cases respectively."""
    overrides = overrides or {}
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, inputs, income, _opex = await seed_deal_model_with_financials(
        session, opp, user
    )
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()

    inputs.purchase_price = _WIZ_PURCHASE
    inputs.closing_costs_pct = Decimal("2.0")
    inputs.renovation_months = 12          # fallback; milestone override wins
    inputs.lease_up_months = 0             # ir_12mo has no lease-up milestone
    inputs.initial_occupancy_pct = Decimal("0")
    inputs.debt_sizing_mode = "gap_fill"
    inputs.debt_types = ["construction_loan", "permanent_debt"]
    inputs.debt_terms = {
        "construction_loan": {"loan_type": constr_carry_type, "rate_pct": "7.0", "ltv_pct": "100"},
        "permanent_debt": {"loan_type": "pi", "rate_pct": "6.5", "amort_years": "30"},
    }
    for _k, _v in overrides.items():
        if _k == "income_per_unit_monthly":
            income.amount_per_unit_monthly = Decimal(str(_v))
        else:
            setattr(inputs, _k, _v)
    session.add_all([inputs, income])

    # Milestone timeline (anchors with explicit dates → computed_start returns
    # target_date directly). Phase months in _apply_milestone_phase_overrides
    # come from the gaps between these dates.
    d0 = date(2026, 1, 1)
    d_constr = d0 + timedelta(days=60)        # pre_development = 60d
    d_stab = d_constr + timedelta(days=365)   # construction    = 365d
    d_exit = d_stab + timedelta(days=1095)    # stabilized      = 1095d
    session.add_all([
        Milestone(project_id=project.id, milestone_type=MilestoneType.close,
                  target_date=d0, duration_days=0, sequence_order=1, label="Close"),
        Milestone(project_id=project.id, milestone_type=MilestoneType.pre_development,
                  target_date=d0, duration_days=60, sequence_order=2, label="Pre-Development"),
        Milestone(project_id=project.id, milestone_type=MilestoneType.construction,
                  target_date=d_constr, duration_days=365, sequence_order=3, label="Construction"),
        Milestone(project_id=project.id, milestone_type=MilestoneType.operation_stabilized,
                  target_date=d_stab, duration_days=1095, sequence_order=4, label="Stabilized"),
        Milestone(project_id=project.id, milestone_type=MilestoneType.divestment,
                  target_date=d_exit, duration_days=1, sequence_order=5, label="Divestment"),
    ])

    perm = CapitalModule(
        scenario_id=deal_model.id,
        label="Permanent Loan",
        vehicle_type="debt",
        stack_position=2,
        source={"amount": 0, "interest_rate_pct": 6.5, "auto_size": True, "amort_term_years": 30},
        carry={"carry_type": "pi", "payment_frequency": "monthly"},
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
        active_phase_start="operation_stabilized",
        active_phase_end="stabilized",
    )
    session.add(perm)
    await session.flush()

    constr = CapitalModule(
        scenario_id=deal_model.id,
        label="Construction Loan",
        vehicle_type="debt",
        stack_position=1,
        source={"amount": 0, "interest_rate_pct": 7.0, "auto_size": True, "ltv_pct": 100},
        carry={"carry_type": constr_carry_type, "payment_frequency": "monthly"},
        exit_terms={"exit_type": "full_payoff", "vehicle": str(perm.id)},
        active_phase_start="construction",
        active_phase_end="operation_stabilized",
    )
    session.add(constr)

    session.add_all([
        UseLine(
            project_id=project.id, label="Purchase Price", phase="acquisition",
            amount=_WIZ_PURCHASE, cost_category="hard", timing_type="first_day",
        ),
        UseLine(
            project_id=project.id, label="Closing Costs", phase="acquisition",
            amount=_WIZ_CLOSING, cost_category="soft", timing_type="first_day",
        ),
        UseLine(
            project_id=project.id, label="Hard Construction", phase="construction",
            amount=_WIZ_HARD, cost_category="hard", timing_type="first_day",
        ),
    ])
    await session.commit()
    return str(deal_model.id), str(project.id)


async def _dump(session: AsyncSession, model_id: str, project_id: str) -> dict:
    """Full breakdown: every use line + every module amount + the gap."""
    session.expire_all()
    use_lines = (
        await session.execute(select(UseLine).where(UseLine.project_id == project_id))
    ).scalars().all()
    modules = (
        await session.execute(
            select(CapitalModule).where(CapitalModule.scenario_id == model_id)
        )
    ).scalars().all()

    uses_rows = [
        (u.label, str(getattr(u.phase, "value", u.phase) or ""), Decimal(str(u.amount or 0)))
        for u in use_lines
    ]
    uses = sum(amt for _l, ph, amt in uses_rows if ph != "exit")
    mod_rows = [
        (
            m.label,
            bool((m.source or {}).get("is_bridge")),
            Decimal(str((m.source or {}).get("amount") or 0)),
        )
        for m in modules
    ]
    sources = sum(amt for _l, bridge, amt in mod_rows if not bridge)
    return {
        "gap": sources - uses,
        "uses": uses,
        "sources": sources,
        "uses_rows": uses_rows,
        "mod_rows": mod_rows,
    }


@pytest.mark.parametrize(
    "constr_carry_type",
    ["interest_reserve", "capitalized_interest", "io_only"],
    ids=["ir", "ci", "io"],
)
async def test_c2p_wizard_timeline_converges_in_one_compute(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
    constr_carry_type: str,
) -> None:
    model_id, project_id = await _seed_c2p_wizard_deal(
        session, constr_carry_type=constr_carry_type
    )

    snaps = []
    for i in range(3):
        r = await client.post(f"/api/models/{model_id}/compute", headers=auth_headers)
        assert r.status_code == 200, r.text
        d = await _dump(session, model_id, project_id)
        snaps.append(d)
        print(f"\n=== [{constr_carry_type}] compute {i+1}: gap={d['gap']:.0f} uses={d['uses']:.0f} sources={d['sources']:.0f} ===")
        for lbl, ph, amt in d["uses_rows"]:
            print(f"    USE  {lbl:<32} [{ph:<14}] {amt:>14.2f}")
        for lbl, bridge, amt in d["mod_rows"]:
            tag = " (bridge)" if bridge else ""
            print(f"    SRC  {lbl:<32}{tag:<9} {amt:>14.2f}")

    # One compute should converge Sources = Uses (within $100).
    assert abs(snaps[0]["gap"]) < Decimal("100"), (
        f"one compute left a gap of ${snaps[0]['gap']:.0f} "
        f"(uses={snaps[0]['uses']:.0f}, sources={snaps[0]['sources']:.0f}) — "
        f"wizard-timeline construction-to-perm did not converge in a single click"
    )

    # Idempotent: re-clicking compute must not move the gap (no runaway, esp.
    # for capitalized_interest where the bond previously diverged → overflow).
    assert abs(snaps[2]["gap"] - snaps[0]["gap"]) < Decimal("100"), (
        f"gap drifted across computes: {[float(s['gap']) for s in snaps]}"
    )


# ---------------------------------------------------------------------------
# Multi-debt retire-and-replace stability (mirrors phase_b `ir_3mo_short`)
#
# An ACQUISITION deal whose construction loan is active from acquisition and
# retired by the perm. The documented worry: forcing the fix-point loop to
# iterate destabilises the bridge/retirement writeback so the construction
# loan principal drifts below its own base cost across passes. This repro
# pins that invariant: P_construction must stay >= base on every pass.
# ---------------------------------------------------------------------------

_ACQ_PURCHASE = Decimal("800000")
_ACQ_RENO = Decimal("500000")
_ACQ_CLOSING = Decimal("16000")


async def _seed_acq_retire_replace_deal(session: AsyncSession) -> tuple[str, str]:
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, inputs, income, _opex = await seed_deal_model_with_financials(
        session, opp, user
    )
    # Acquisition project type (default seed is value_add) — re-tag the model.
    from app.models.deal import ProjectType
    deal_model.project_type = ProjectType.acquisition
    session.add(deal_model)
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()

    inputs.purchase_price = _ACQ_PURCHASE
    inputs.closing_costs_pct = Decimal("2.0")
    inputs.renovation_months = 3
    inputs.lease_up_months = 0
    inputs.initial_occupancy_pct = Decimal("0")
    inputs.debt_sizing_mode = "gap_fill"
    inputs.debt_types = ["construction_loan", "permanent_debt"]
    inputs.debt_terms = {
        "construction_loan": {"loan_type": "interest_reserve", "rate_pct": "7.0", "ltv_pct": "100"},
        "permanent_debt": {"loan_type": "pi", "rate_pct": "6.5", "amort_years": "30"},
    }
    session.add_all([inputs, income])

    d0 = date(2026, 1, 1)
    d_stab = d0 + timedelta(days=90)          # construction = 90d
    d_exit = d_stab + timedelta(days=730)     # stabilized   = 730d
    session.add_all([
        Milestone(project_id=project.id, milestone_type=MilestoneType.close,
                  target_date=d0, duration_days=90, sequence_order=1, label="Close"),
        Milestone(project_id=project.id, milestone_type=MilestoneType.construction,
                  target_date=d0, duration_days=90, sequence_order=2, label="Construction"),
        Milestone(project_id=project.id, milestone_type=MilestoneType.operation_stabilized,
                  target_date=d_stab, duration_days=730, sequence_order=3, label="Stabilized"),
        Milestone(project_id=project.id, milestone_type=MilestoneType.divestment,
                  target_date=d_exit, duration_days=1, sequence_order=4, label="Divestment"),
    ])

    perm = CapitalModule(
        scenario_id=deal_model.id, label="Permanent Loan", vehicle_type="debt",
        stack_position=2,
        source={"amount": 0, "interest_rate_pct": 6.5, "auto_size": True, "amort_term_years": 30},
        carry={"carry_type": "pi", "payment_frequency": "monthly"},
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
        active_phase_start="operation_stabilized", active_phase_end="stabilized",
    )
    session.add(perm)
    await session.flush()

    constr = CapitalModule(
        scenario_id=deal_model.id, label="Construction Loan", vehicle_type="debt",
        stack_position=1,
        source={"amount": 0, "interest_rate_pct": 7.0, "auto_size": True, "ltv_pct": 100},
        carry={"carry_type": "interest_reserve", "payment_frequency": "monthly"},
        exit_terms={"exit_type": "full_payoff", "vehicle": str(perm.id)},
        active_phase_start="acquisition", active_phase_end="operation_stabilized",
    )
    session.add(constr)

    session.add_all([
        UseLine(project_id=project.id, label="Purchase Price", phase="acquisition",
                amount=_ACQ_PURCHASE, cost_category="hard", timing_type="first_day"),
        UseLine(project_id=project.id, label="Closing Costs", phase="acquisition",
                amount=_ACQ_CLOSING, cost_category="soft", timing_type="first_day"),
        UseLine(project_id=project.id, label="Hard Reno", phase="construction",
                amount=_ACQ_RENO, cost_category="hard", timing_type="first_day"),
    ])
    await session.commit()
    return str(deal_model.id), str(project.id)


async def test_acq_retire_replace_construction_principal_stable(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    model_id, project_id = await _seed_acq_retire_replace_deal(session)

    principals = []
    for i in range(3):
        r = await client.post(f"/api/models/{model_id}/compute", headers=auth_headers)
        assert r.status_code == 200, r.text
        d = await _dump(session, model_id, project_id)
        constr_p = next(
            (amt for lbl, _b, amt in d["mod_rows"] if "construction" in lbl.lower()),
            None,
        )
        principals.append(constr_p)
        print(f"\n=== compute {i+1}: gap={d['gap']:.0f} constr_P={constr_p} ===")
        for lbl, ph, amt in d["uses_rows"]:
            print(f"    USE  {lbl:<32} [{ph:<14}] {amt:>14.2f}")
        for lbl, bridge, amt in d["mod_rows"]:
            tag = " (bridge)" if bridge else ""
            print(f"    SRC  {lbl:<32}{tag:<9} {amt:>14.2f}")

    # The construction loan principal must never size below its base reno cost,
    # and must be stable (idempotent) across passes.
    for i, p in enumerate(principals):
        assert p is not None and p >= _ACQ_RENO, (
            f"compute {i+1}: construction principal {p} sized below base {_ACQ_RENO}"
        )
    assert abs(principals[2] - principals[0]) < Decimal("1"), (
        f"construction principal drifted across passes: {principals}"
    )
