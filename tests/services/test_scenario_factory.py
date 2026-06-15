"""Unit tests for app.services.scenario_factory.create_scenario.

Verifies that every newly created Scenario + OperationalInputs row starts
with org/user defaults applied — the gap that prompted the wizard refactor.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.deal import Deal, Scenario, ProjectType
from app.models.settings import OrgSetting
from app.services.scenario_factory import create_scenario
from app.settings.defaults import DEFAULT_REGISTRY
from tests.conftest import seed_org


pytestmark = pytest.mark.asyncio


async def _make_deal(session, org, user) -> Deal:
    deal = Deal(
        id=uuid.uuid4(),
        org_id=org.id,
        name="Test Deal",
        created_by_user_id=user.id,
    )
    session.add(deal)
    await session.flush()
    return deal


# ──────────────────────────────────────────────────────────────────────────────
# Fresh-factory tests — verify Type 1 + Type 2 defaults flow into both rows
# ──────────────────────────────────────────────────────────────────────────────

async def test_factory_sets_type1_scenario_fields(session):
    org, user = await seed_org(session)
    deal = await _make_deal(session, org, user)

    scenario, project, inputs = await create_scenario(
        session=session,
        deal_id=deal.id,
        deal_type=ProjectType.value_add,
        user_id=user.id,
        org_id=org.id,
    )

    # Type 1 / target=scenario
    assert scenario.risk_free_rate_pct == Decimal("4.25"), (
        f"Expected risk_free_rate_pct=4.25 (system baseline), got {scenario.risk_free_rate_pct!r}"
    )
    # Type 2 / target=scenario — income_mode
    assert scenario.income_mode == "revenue_opex"


async def test_factory_sets_type1_operational_inputs_fields(session):
    org, user = await seed_org(session)
    deal = await _make_deal(session, org, user)

    scenario, project, inputs = await create_scenario(
        session=session,
        deal_id=deal.id,
        deal_type=ProjectType.value_add,
        user_id=user.id,
        org_id=org.id,
    )

    # Type 1 — operation_reserve_months (int)
    assert inputs.operation_reserve_months == 6
    # Type 1 — debt_sizing_mode (str)
    assert inputs.debt_sizing_mode == "gap_fill"
    # Type 1 — capex_reserve_per_unit_annual (Decimal); ORM default is 0 but
    # registry baseline is 250.00.
    assert inputs.capex_reserve_per_unit_annual == Decimal("250.00")


async def test_factory_sets_type2_operational_inputs_fields(session):
    org, user = await seed_org(session)
    deal = await _make_deal(session, org, user)

    scenario, project, inputs = await create_scenario(
        session=session,
        deal_id=deal.id,
        deal_type=ProjectType.value_add,
        user_id=user.id,
        org_id=org.id,
    )

    # Type 2 — operational_inputs scalars
    assert inputs.noi_escalation_rate_pct == Decimal("3.0")
    assert inputs.lease_up_curve == "linear"
    assert inputs.lease_up_curve_steepness == Decimal("5")
    assert inputs.asset_mgmt_fee_pct == Decimal("0.5")
    assert inputs.construction_floor_pct == Decimal("40.0")
    assert inputs.selling_costs_pct == Decimal("2.0")


async def test_factory_seeds_debt_terms_permanent_debt_jsonb(session):
    org, user = await seed_org(session)
    deal = await _make_deal(session, org, user)

    scenario, project, inputs = await create_scenario(
        session=session,
        deal_id=deal.id,
        deal_type=ProjectType.value_add,
        user_id=user.id,
        org_id=org.id,
    )

    perm = (inputs.debt_terms or {}).get("permanent_debt", {})
    # Type 2 — operational_inputs.debt_terms.permanent_debt sub-path
    assert perm.get("dscr_min") == 1.25
    assert perm.get("ltv_pct") == 70.0
    assert perm.get("amort_years") == 30
    assert perm.get("hold_term_years") == 7


# ──────────────────────────────────────────────────────────────────────────────
# Org override — org-set DB row beats system baseline
# ──────────────────────────────────────────────────────────────────────────────

async def test_factory_uses_org_override(session):
    org, user = await seed_org(session)
    # Org overrides risk_free_rate_pct from 4.25 → 5.5
    session.add(OrgSetting(
        org_id=org.id,
        field_key="risk_free_rate_pct",
        value="5.5",
        user_overridable=False,
    ))
    await session.flush()

    deal = await _make_deal(session, org, user)
    scenario, project, inputs = await create_scenario(
        session=session,
        deal_id=deal.id,
        deal_type=ProjectType.value_add,
        user_id=user.id,
        org_id=org.id,
    )

    assert scenario.risk_free_rate_pct == Decimal("5.5"), (
        f"Org override should win over system baseline, got {scenario.risk_free_rate_pct!r}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Clone path — Type 2 inherits from source, Type 1 re-resolved from current org
# ──────────────────────────────────────────────────────────────────────────────

async def test_clone_inherits_type2_from_source(session):
    org, user = await seed_org(session)
    deal = await _make_deal(session, org, user)

    # Original scenario
    src_scenario, src_project, src_inputs = await create_scenario(
        session=session,
        deal_id=deal.id,
        deal_type=ProjectType.value_add,
        user_id=user.id,
        org_id=org.id,
    )

    # Mutate Type 2 fields on the source to simulate user tuning
    src_inputs.noi_escalation_rate_pct = Decimal("4.5")
    src_inputs.lease_up_curve = "s_curve"
    debt_terms = dict(src_inputs.debt_terms or {})
    perm = dict(debt_terms.get("permanent_debt", {}))
    perm["dscr_min"] = 1.40
    debt_terms["permanent_debt"] = perm
    src_inputs.debt_terms = debt_terms
    session.add(src_inputs)
    await session.flush()

    # Clone
    clone_scenario, clone_project, clone_inputs = await create_scenario(
        session=session,
        deal_id=deal.id,
        deal_type=ProjectType.value_add,
        user_id=user.id,
        org_id=org.id,
        name="Clone of Base",
        version=2,
        source_scenario=src_scenario,
        source_inputs=src_inputs,
    )

    # Type 2 inherits
    assert clone_inputs.noi_escalation_rate_pct == Decimal("4.5")
    assert clone_inputs.lease_up_curve == "s_curve"
    clone_perm = (clone_inputs.debt_terms or {}).get("permanent_debt", {})
    assert clone_perm.get("dscr_min") == 1.40


async def test_clone_reapplies_type1_from_current_org(session):
    org, user = await seed_org(session)
    deal = await _make_deal(session, org, user)

    # Source scenario built before the org override exists
    src_scenario, _, src_inputs = await create_scenario(
        session=session,
        deal_id=deal.id,
        deal_type=ProjectType.value_add,
        user_id=user.id,
        org_id=org.id,
    )
    # Sanity: source has the system baseline
    assert src_scenario.risk_free_rate_pct == Decimal("4.25")
    assert src_inputs.operation_reserve_months == 6

    # Org changes the Type 1 policy after the source scenario was made
    session.add(OrgSetting(
        org_id=org.id,
        field_key="risk_free_rate_pct",
        value="6.0",
        user_overridable=False,
    ))
    session.add(OrgSetting(
        org_id=org.id,
        field_key="operation_reserve_months",
        value="12",
        user_overridable=False,
    ))
    await session.flush()

    # Clone — Type 1 should pick up the new org policy, not the source's stale 4.25/6
    clone_scenario, _, clone_inputs = await create_scenario(
        session=session,
        deal_id=deal.id,
        deal_type=ProjectType.value_add,
        user_id=user.id,
        org_id=org.id,
        name="Clone of Base",
        version=2,
        source_scenario=src_scenario,
        source_inputs=src_inputs,
    )

    assert clone_scenario.risk_free_rate_pct == Decimal("6.0"), (
        "Clone should pick up new org Type 1 value, not source's stale baseline"
    )
    assert clone_inputs.operation_reserve_months == 12


# ──────────────────────────────────────────────────────────────────────────────
# Coverage smoke — every registry field with a target lands somewhere
# ──────────────────────────────────────────────────────────────────────────────

async def test_factory_writes_every_targeted_field(session):
    """Spot-check that every DEFAULT_REGISTRY entry with a target other than
    ``no_destination`` lands on the resulting row. Surfaces accidental
    target-name drift between defaults.py and the actual ORM columns."""
    org, user = await seed_org(session)
    deal = await _make_deal(session, org, user)

    scenario, project, inputs = await create_scenario(
        session=session,
        deal_id=deal.id,
        deal_type=ProjectType.value_add,
        user_id=user.id,
        org_id=org.id,
    )

    missing: list[str] = []
    for field_key, spec in DEFAULT_REGISTRY.items():
        if spec.target == "no_destination":
            continue
        if spec.target == "scenario":
            value = getattr(scenario, spec.column, None)
        elif spec.target == "operational_inputs":
            value = getattr(inputs, spec.column, None)
        elif spec.target == "operational_inputs.debt_terms.permanent_debt":
            perm = (inputs.debt_terms or {}).get("permanent_debt", {})
            value = perm.get(spec.column)
        else:  # unknown target
            missing.append(f"{field_key} (unknown target {spec.target!r})")
            continue
        if value is None or value == "" or value == 0 or value == Decimal("0"):
            missing.append(f"{field_key} → {spec.target}.{spec.column} = {value!r}")

    assert not missing, "Fields not landing post-factory:\n" + "\n".join(missing)
