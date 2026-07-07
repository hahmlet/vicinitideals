"""deal-json-v3 round-trip tests.

Covers the Slice 4 remediation:
- export → import → re-export deep-compare (v3 blocks survive, ID remaps
  are consistent: milestone trigger chains and use-line eligible_module_ids
  point at the NEW rows)
- v1 / v2 legacy payloads still import unchanged
- snapshot capture → revert preserves the fields the narrow Bases used to
  silently drop (eligible_use_tags, source_vehicle_id, entitlement_cost,
  health_thresholds)
- template extract → apply parity for the newly applied entity types
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exporters.json_export import EXPORT_SCHEMA_VERSION, export_deal_model_json
from app.exporters.json_import import (
    import_deal_from_json,
    validate_deal_import_payload,
)
from app.exporters.snapshot import capture_snapshot, revert_to_snapshot
from app.exporters.template_apply import apply_template_to_project
from app.exporters.template_export import extract_template_json
from app.models.capital import CapitalModule, DrawSource, WaterfallTier
from app.models.deal import OperationalInputs, Scenario, UseLine, UseLinePhase
from app.models.milestone import Milestone, MilestoneType
from app.models.project import Project
from app.models.source_vehicle import SourceVehicle
from tests.conftest import (
    seed_deal_model,
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)

# ── Fixture graph ─────────────────────────────────────────────────────────────


async def _seed_full_scenario(session: AsyncSession):
    """Scenario with every v3 entity type populated and cross-referenced."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    scenario, inputs, _income, _opex = await seed_deal_model_with_financials(
        session, opp, user
    )
    project = (
        await session.execute(
            select(Project)
            .where(Project.scenario_id == scenario.id)
            .order_by(Project.created_at.asc())
            .limit(1)
        )
    ).scalar_one()

    # v3 fields the old Bases dropped
    scenario.health_thresholds = {"occ_green": 0.92, "dscr_green": 1.25}
    scenario.min_reserve_construction = Decimal("50000")
    scenario.risk_free_rate_pct = Decimal("4.25")
    scenario.discount_rate_pct = Decimal("8")
    inputs.entitlement_cost = Decimal("123456")
    inputs.going_in_cap_rate_pct = Decimal("5.75")
    inputs.affordable_housing_project = True

    project.unit_mix = [
        {"label": "1BR", "unit_count": 8, "market_rent_per_unit": 1500.0},
        {"label": "2BR", "unit_count": 4, "market_rent_per_unit": 2100.0},
    ]

    vehicle = SourceVehicle(
        scope="org",
        owner_id=org.id,
        label="Test Bank Loan",
        vehicle_type="debt",
    )
    session.add(vehicle)
    await session.flush()

    m1 = Milestone(
        project_id=project.id,
        milestone_type=MilestoneType.pre_development,
        duration_days=30,
        target_date=date(2026, 1, 1),
        sequence_order=1,
        trigger_offset_days=0,
    )
    session.add(m1)
    await session.flush()
    m2 = Milestone(
        project_id=project.id,
        milestone_type=MilestoneType.construction,
        duration_days=180,
        sequence_order=2,
        trigger_milestone_id=m1.id,
        trigger_offset_days=15,
    )
    session.add(m2)
    await session.flush()

    module = CapitalModule(
        scenario_id=scenario.id,
        label="Senior Loan",
        vehicle_type="debt",
        stack_position=1,
        source={"amount": 850000.0, "interest_rate_pct": 6.5, "auto_size": True,
                "hold_term_years": 10},
        carry={"carry_type": "io_only", "io_rate_pct": 6.5,
               "payment_frequency": "monthly", "capitalized": False},
        eligible_use_tags=["hard", "soft"],
        source_vehicle_id=vehicle.id,
        active_from_milestone_id=m1.id,
        active_to_milestone_id=m2.id,
    )
    session.add(module)
    await session.flush()

    use_line = UseLine(
        project_id=project.id,
        label="Sitework",
        phase=UseLinePhase.construction,
        cost_category="hard",
        amount=Decimal("250000"),
        eligible_module_ids=[module.id],
        active_from_milestone_id=m1.id,
        spread_to_milestone_id=m2.id,
        timing_type="spread",
    )
    dev_fee_line = UseLine(
        project_id=project.id,
        label="Developer Fee",
        phase=UseLinePhase.construction,
        cost_category="soft",
        amount=Decimal("0"),
        is_auto_dev_fee=True,
        dev_fee_pct=Decimal("4"),
        dev_fee_basis="tpc_excl_self",
    )
    draw_source = DrawSource(
        scenario_id=scenario.id,
        project_id=project.id,
        sort_order=1,
        label="Senior Debt Draws",
        source_type="debt",
        draw_every_n_months=2,
        annual_interest_rate=Decimal("6.5"),
        active_from_milestone="close",
        active_to_milestone="operation_stabilized",
        total_commitment=Decimal("850000"),
        capital_module_id=module.id,
    )
    tier = WaterfallTier(
        scenario_id=scenario.id,
        project_id=project.id,
        capital_module_id=module.id,
        priority=1,
        tier_type="return_of_equity",
        lp_split_pct=Decimal("90"),
        gp_split_pct=Decimal("10"),
    )
    session.add_all([use_line, dev_fee_line, draw_source, tier])
    await session.flush()

    return org, user, opp, scenario, project, module, vehicle, m1, m2


# ── Deep-compare helpers ──────────────────────────────────────────────────────

# Keys whose values are legitimately different after an import (fresh UUIDs,
# fresh timestamps). Remap CORRECTNESS is asserted separately.
_VOLATILE_KEYS = frozenset({
    "id",
    "project_id",
    "scenario_id",
    "deal_id",
    "opportunity_id",
    "model_id",
    "created_at",
    "updated_at",
    "exported_at",
    "created_by_user_id",
    "trigger_milestone_id",
    "capital_module_id",
    "active_from_milestone_id",
    "active_to_milestone_id",
    "spread_to_milestone_id",
    "eligible_module_ids",
})


def _normalize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: _normalize(v) for k, v in obj.items() if k not in _VOLATILE_KEYS
        }
    if isinstance(obj, list):
        return [_normalize(item) for item in obj]
    return obj


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_v3_export_emits_new_blocks(session: AsyncSession):
    _org, _user, _opp, scenario, *_ = await _seed_full_scenario(session)
    scenario_id = scenario.id
    await session.commit()

    payload = await export_deal_model_json(session, scenario_id)

    assert payload["schema_version"] == "deal-json-v3"
    assert EXPORT_SCHEMA_VERSION == "deal-json-v3"
    assert len(payload["use_lines"]) == 2
    assert len(payload["milestones"]) == 2
    assert len(payload["draw_sources"]) == 1
    # milestone trigger chain exported with stable keys
    by_seq = sorted(payload["milestones"], key=lambda m: m["sequence_order"])
    assert by_seq[1]["trigger_milestone_id"] == by_seq[0]["id"]
    # widened Base fields present on the module
    module_payload = payload["capital_modules"][0]
    assert module_payload["eligible_use_tags"] == ["hard", "soft"]
    assert module_payload["source_vehicle_id"] is not None
    assert module_payload["active_from_milestone_id"] == by_seq[0]["id"]
    # widened scenario / inputs fields
    assert payload["deal_model"]["health_thresholds"] == {
        "occ_green": 0.92, "dscr_green": 1.25,
    }
    assert Decimal(str(payload["operational_inputs"]["entitlement_cost"])) == Decimal("123456")
    assert payload["operational_inputs"]["affordable_housing_project"] is True
    # engine-owned Dev Fee flags round-trip on the use line
    dev_fee = next(u for u in payload["use_lines"] if u["label"] == "Developer Fee")
    assert dev_fee["is_auto_dev_fee"] is True
    assert Decimal(str(dev_fee["dev_fee_pct"])) == Decimal("4")


@pytest.mark.asyncio
async def test_v3_roundtrip_import_remaps_ids_and_reexport_matches(session: AsyncSession):
    org, _user, _opp, scenario, _project, module, vehicle, _m1, _m2 = (
        await _seed_full_scenario(session)
    )
    # Capture ids into plain locals BEFORE expire_all — attribute access on an
    # expired instance triggers a sync refresh → MissingGreenlet under asyncpg.
    org_id, scenario_id = org.id, scenario.id
    module_id, vehicle_id = module.id, vehicle.id
    await session.commit()
    # Expire so the export re-reads DB-normalized values (Numeric scale etc.)
    # and the deep-compare against the post-import re-export is stable.
    session.expire_all()

    first_export = await export_deal_model_json(session, scenario_id)

    result = await import_deal_from_json(session, org_id=org_id, payload=first_export)
    new_scenario_id = result.model.id
    assert new_scenario_id != scenario_id
    assert result.counts["use_lines"] == 2
    assert result.counts["milestones"] == 2
    assert result.counts["draw_sources"] == 1
    assert result.counts["unit_mix"] == 2

    new_project = (
        await session.execute(
            select(Project)
            .where(Project.scenario_id == new_scenario_id)
            .order_by(Project.created_at.asc())
            .limit(1)
        )
    ).scalar_one()

    # ── ID remap consistency ────────────────────────────────────────────
    new_milestones = list(
        (
            await session.execute(
                select(Milestone)
                .where(Milestone.project_id == new_project.id)
                .order_by(Milestone.sequence_order.asc())
            )
        ).scalars()
    )
    assert len(new_milestones) == 2
    assert new_milestones[1].trigger_milestone_id == new_milestones[0].id
    assert new_milestones[1].trigger_offset_days == 15

    new_module = (
        await session.execute(
            select(CapitalModule).where(CapitalModule.scenario_id == new_scenario_id)
        )
    ).scalar_one()
    assert new_module.id != module_id
    assert new_module.eligible_use_tags == ["hard", "soft"]
    assert new_module.source_vehicle_id == vehicle_id
    assert new_module.active_from_milestone_id == new_milestones[0].id
    assert new_module.active_to_milestone_id == new_milestones[1].id

    new_use_lines = list(
        (
            await session.execute(
                select(UseLine).where(UseLine.project_id == new_project.id)
            )
        ).scalars()
    )
    sitework = next(u for u in new_use_lines if u.label == "Sitework")
    assert list(sitework.eligible_module_ids) == [new_module.id]
    assert sitework.active_from_milestone_id == new_milestones[0].id
    assert sitework.spread_to_milestone_id == new_milestones[1].id
    dev_fee = next(u for u in new_use_lines if u.label == "Developer Fee")
    assert dev_fee.is_auto_dev_fee is True

    new_draw = (
        await session.execute(
            select(DrawSource).where(DrawSource.scenario_id == new_scenario_id)
        )
    ).scalar_one()
    assert new_draw.capital_module_id == new_module.id
    assert new_draw.project_id == new_project.id

    new_tier = (
        await session.execute(
            select(WaterfallTier).where(WaterfallTier.scenario_id == new_scenario_id)
        )
    ).scalar_one()
    assert new_tier.capital_module_id == new_module.id
    assert new_tier.project_id == new_project.id

    assert (new_project.unit_mix or []) and len(new_project.unit_mix) == 2

    # ── Re-export deep compare (normalized) ─────────────────────────────
    await session.commit()
    session.expire_all()
    second_export = await export_deal_model_json(session, new_scenario_id)

    for block in (
        "deal_model",
        "operational_inputs",
        "income_streams",
        "expense_lines",
        "use_lines",
        "unit_mix",
        "milestones",
        "capital_modules",
        "waterfall_tiers",
        "draw_sources",
    ):
        assert _normalize(second_export[block]) == _normalize(first_export[block]), (
            f"round-trip drift in block {block!r}"
        )


@pytest.mark.asyncio
async def test_v1_legacy_payload_still_imports(session: AsyncSession):
    org, _user = await seed_org(session)
    payload = {
        "schema_version": "deal-json-v1",
        "project": {"Name": "Legacy V1 Deal"},
        "deal_model": {
            "name": "Legacy V1 Model",
            "project_type": "value_add",
            "operational_inputs": {"unit_count_new": 4},
            "income_streams": [
                {
                    "stream_type": "residential_rent",
                    "label": "Market Rent",
                    "unit_count": 4,
                    "amount_per_unit_monthly": "1200",
                }
            ],
            "capital_stack": [
                {"id": str(uuid.uuid4()), "label": "Equity", "vehicle_type": "equity"}
            ],
        },
    }

    validation = validate_deal_import_payload(payload)
    assert validation.valid, validation.errors
    assert any("v1" in w for w in validation.warnings)

    result = await import_deal_from_json(session, org_id=org.id, payload=payload)
    assert result.model.name == "Legacy V1 Model"
    assert result.counts["income_streams"] == 1
    assert result.counts["capital_modules"] == 1
    # v3-only blocks default empty
    assert result.counts["use_lines"] == 0
    assert result.counts["milestones"] == 0


@pytest.mark.asyncio
async def test_v2_legacy_payload_still_imports_with_tier_remap(session: AsyncSession):
    org, _user = await seed_org(session)
    old_module_id = str(uuid.uuid4())
    payload = {
        "schema_version": "deal-json-v2",
        "project": {"Name": "Legacy V2 Deal"},
        "deal_model": {"name": "Legacy V2 Model", "project_type": "acquisition"},
        "operational_inputs": {
            "unit_count_new": 8,
            "debt_types": ["permanent_debt"],
            "debt_sizing_mode": "gap_fill",
        },
        "income_streams": [
            {"stream_type": "residential_rent", "label": "Rent", "unit_count": 8}
        ],
        "capital_modules": [
            {
                "id": old_module_id,
                "label": "Perm Loan",
                "vehicle_type": "debt",
                "source": {"amount": "500000", "hold_term_years": 10},
            }
        ],
        "waterfall_tiers": [
            {
                "priority": 1,
                "tier_type": "return_of_equity",
                "capital_module_id": old_module_id,
                "lp_split_pct": "90",
                "gp_split_pct": "10",
            }
        ],
        "unit_mix": [{"label": "Studio", "unit_count": 8}],
    }

    validation = validate_deal_import_payload(payload)
    assert validation.valid, validation.errors

    result = await import_deal_from_json(session, org_id=org.id, payload=payload)
    new_scenario_id = result.model.id

    new_module = (
        await session.execute(
            select(CapitalModule).where(CapitalModule.scenario_id == new_scenario_id)
        )
    ).scalar_one()
    new_tier = (
        await session.execute(
            select(WaterfallTier).where(WaterfallTier.scenario_id == new_scenario_id)
        )
    ).scalar_one()
    assert str(new_module.id) != old_module_id
    assert new_tier.capital_module_id == new_module.id
    # v2 export already carried unit_mix — import now persists it
    new_project = (
        await session.execute(
            select(Project).where(Project.scenario_id == new_scenario_id).limit(1)
        )
    ).scalar_one()
    assert (new_project.unit_mix or [{}])[0].get("label") == "Studio"


@pytest.mark.asyncio
async def test_unknown_schema_version_rejected(session: AsyncSession):
    validation = validate_deal_import_payload(
        {
            "schema_version": "deal-json-v99",
            "deal_model": {"name": "x", "project_type": "acquisition"},
        }
    )
    assert not validation.valid
    assert any("Unsupported schema_version" in e for e in validation.errors)


@pytest.mark.asyncio
async def test_snapshot_revert_preserves_previously_dropped_fields(session: AsyncSession):
    (
        _org,
        _user,
        _opp,
        scenario,
        project,
        module,
        vehicle,
        _m1,
        _m2,
    ) = await _seed_full_scenario(session)
    await session.flush()

    snap = await capture_snapshot(session, scenario.id)

    # Mutate everything the revert must restore
    inputs = (
        await session.execute(
            select(OperationalInputs).where(OperationalInputs.project_id == project.id)
        )
    ).scalar_one()
    inputs.entitlement_cost = Decimal("999")
    module.eligible_use_tags = []
    module.source_vehicle_id = None
    sitework = (
        await session.execute(
            select(UseLine).where(
                UseLine.project_id == project.id, UseLine.label == "Sitework"
            )
        )
    ).scalar_one()
    sitework.eligible_module_ids = []
    await session.flush()

    await revert_to_snapshot(session, scenario.id, snap.id)
    await session.commit()

    restored_inputs = (
        await session.execute(
            select(OperationalInputs).where(OperationalInputs.project_id == project.id)
        )
    ).scalar_one()
    assert restored_inputs.entitlement_cost == Decimal("123456")

    restored_module = (
        await session.execute(
            select(CapitalModule).where(CapitalModule.scenario_id == scenario.id)
        )
    ).scalar_one()
    assert restored_module.eligible_use_tags == ["hard", "soft"]
    assert restored_module.source_vehicle_id == vehicle.id

    # eligible_module_ids remapped onto the NEW module row (revert recreates
    # modules with fresh UUIDs)
    restored_sitework = (
        await session.execute(
            select(UseLine).where(
                UseLine.project_id == project.id, UseLine.label == "Sitework"
            )
        )
    ).scalar_one()
    assert list(restored_sitework.eligible_module_ids) == [restored_module.id]

    # milestone anchors on the module remapped onto the recreated milestones
    restored_ms = list(
        (
            await session.execute(
                select(Milestone)
                .where(Milestone.project_id == project.id)
                .order_by(Milestone.sequence_order.asc())
            )
        ).scalars()
    )
    assert restored_module.active_from_milestone_id == restored_ms[0].id
    assert restored_module.active_to_milestone_id == restored_ms[1].id

    # health_thresholds live on the Scenario row itself — untouched by revert
    refreshed_scenario = (
        await session.execute(select(Scenario).where(Scenario.id == scenario.id))
    ).scalar_one()
    assert refreshed_scenario.health_thresholds == {
        "occ_green": 0.92, "dscr_green": 1.25,
    }


@pytest.mark.asyncio
async def test_template_extract_receives_v3_blocks_and_apply_seeds_them(
    session: AsyncSession,
):
    org, user, _opp, scenario, *_ = await _seed_full_scenario(session)
    scenario_id = scenario.id
    await session.commit()

    template = await extract_template_json(session, scenario_id)

    # extract now receives real data for the previously always-empty keys
    assert len(template["use_lines"]) == 2
    assert len(template["milestones"]) == 2
    assert len(template["draw_sources"]) == 1
    assert len(template["capital_modules"]) == 1
    assert len(template["unit_mix"]) == 2
    # property-specific values stripped
    assert all(u["amount"] is None for u in template["use_lines"])
    assert all(m["duration_days"] is None for m in template["milestones"])
    assert template["capital_modules"][0]["source"]["amount"] is None

    # ── apply into a fresh project ───────────────────────────────────────
    opp2 = await seed_opportunity(session, org, user, name="Template Target")
    scenario2 = await seed_deal_model(session, opp2, user, name="Templated")
    project2 = Project(
        scenario_id=scenario2.id, opportunity_id=opp2.id, name="Target Project"
    )
    session.add(project2)
    await session.flush()

    await apply_template_to_project(session, template, project2.id)
    await session.flush()

    # capital module cloned, with milestone anchors nulled (template
    # milestones are not applied)
    new_module = (
        await session.execute(
            select(CapitalModule).where(CapitalModule.scenario_id == scenario2.id)
        )
    ).scalar_one()
    assert new_module.label == "Senior Loan"
    assert new_module.eligible_use_tags == ["hard", "soft"]
    assert new_module.active_from_milestone_id is None

    # tier + draw source wired onto the NEW module and project
    new_tier = (
        await session.execute(
            select(WaterfallTier).where(WaterfallTier.scenario_id == scenario2.id)
        )
    ).scalar_one()
    assert new_tier.capital_module_id == new_module.id
    assert new_tier.project_id == project2.id

    new_draw = (
        await session.execute(
            select(DrawSource).where(DrawSource.scenario_id == scenario2.id)
        )
    ).scalar_one()
    assert new_draw.capital_module_id == new_module.id
    assert new_draw.project_id == project2.id

    # use lines: engine-auto Dev Fee row skipped, structural row seeded with
    # amount defaulted to 0 and eligible_module_ids remapped
    new_use_lines = list(
        (
            await session.execute(
                select(UseLine).where(UseLine.project_id == project2.id)
            )
        ).scalars()
    )
    labels = {u.label for u in new_use_lines}
    assert "Sitework" in labels
    assert "Developer Fee" not in labels
    sitework2 = next(u for u in new_use_lines if u.label == "Sitework")
    assert Decimal(sitework2.amount) == Decimal("0")
    assert list(sitework2.eligible_module_ids) == [new_module.id]
    assert sitework2.active_from_milestone_id is None

    # unit mix structure applied (values stripped)
    assert len(project2.unit_mix or []) == 2
    assert all(row.get("unit_count") is None for row in project2.unit_mix)

    # income/expense seeding (historical behavior) still works
    from app.models.deal import IncomeStream

    streams = list(
        (
            await session.execute(
                select(IncomeStream).where(IncomeStream.project_id == project2.id)
            )
        ).scalars()
    )
    assert len(streams) == 1


@pytest.mark.asyncio
async def test_template_apply_maps_duplicate_module_labels_to_existing(
    session: AsyncSession,
):
    """A preloaded module with the same label absorbs the template wiring."""
    org, user, _opp, scenario, *_ = await _seed_full_scenario(session)
    scenario_id = scenario.id
    await session.commit()
    template = await extract_template_json(session, scenario_id)

    opp2 = await seed_opportunity(session, org, user, name="Dup Target")
    scenario2 = await seed_deal_model(session, opp2, user, name="Dup Templated")
    project2 = Project(
        scenario_id=scenario2.id, opportunity_id=opp2.id, name="Dup Project"
    )
    session.add(project2)
    await session.flush()
    preloaded = CapitalModule(
        scenario_id=scenario2.id,
        label="Senior Loan",
        vehicle_type="debt",
        stack_position=1,
        source={"amount": 1.0, "hold_term_years": 5},
    )
    session.add(preloaded)
    await session.flush()

    await apply_template_to_project(session, template, project2.id)
    await session.flush()

    modules = list(
        (
            await session.execute(
                select(CapitalModule).where(CapitalModule.scenario_id == scenario2.id)
            )
        ).scalars()
    )
    assert len(modules) == 1  # no duplicate created
    new_tier = (
        await session.execute(
            select(WaterfallTier).where(WaterfallTier.scenario_id == scenario2.id)
        )
    ).scalar_one()
    assert new_tier.capital_module_id == preloaded.id


# ── Ported from tests/exporters/test_benchmark_fixtures.py (deleted) ─────────


@pytest.mark.asyncio
async def test_export_deal_model_json_includes_expense_line_notes(session: AsyncSession):
    """Expense lines with `notes` must survive export_deal_model_json."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    scenario, _inputs, _income, opex = await seed_deal_model_with_financials(
        session, opp, user
    )
    opex.notes = "Owner-paid utility"
    await session.flush()

    payload = await export_deal_model_json(session, scenario.id)

    assert payload["expense_lines"][0]["label"] == "Property Management"
    assert payload["expense_lines"][0]["notes"] == "Owner-paid utility"
    assert payload["deal_model"]["expense_lines"][0]["notes"] == "Owner-paid utility"
