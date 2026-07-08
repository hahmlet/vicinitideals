"""Integration tests for structural model-builder operations
(app/api/routers/ui_model_builder.py).

Covers (none of these had coverage; see test_structural_delete_routes.py
for the variant/new-project/delete class — not duplicated here):

  - POST /ui/deals/{id}/project/{pid}/clone-from   — replace target project data
  - POST /ui/models/{id}/stack-order               — batch stack_position update
  - POST /ui/models/{id}/capital-modules/reorder   — drag-reorder capital modules
  - POST /ui/models/{id}/settings                  — Settings drawer save
  - POST /ui/projects/{id}/rename                  — project rename
  - POST /ui/models/{id}/unit-mix/apply-to-revenue — derive IncomeStreams from unit mix

`{id}` in the /ui/deals and /ui/models URLs is the Scenario id (builder-route
convention). Assertions verify DB substance (rows, amounts, JSONB payloads),
not just status codes.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule
from app.models.deal import (
    IncomeStream,
    IncomeStreamType,
    OperatingExpenseLine,
    OperationalInputs,
    ProjectType,
    Scenario,
    UseLine,
)
from app.models.milestone import Milestone, MilestoneType
from app.models.project import Project

from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
    set_client_auth,
)

pytestmark = pytest.mark.asyncio


async def _seed(session: AsyncSession):
    """Org + user + opp + scenario-with-financials. Commits."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, inputs, income, opex = await seed_deal_model_with_financials(
        session, opp, user
    )
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()
    await session.commit()
    return org, user, opp, deal_model, project, inputs, income, opex


# ---------------------------------------------------------------------------
# POST /ui/deals/{id}/project/{pid}/clone-from
# ---------------------------------------------------------------------------


async def test_clone_from_replaces_target_with_source_copy(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user, opp, deal_model, proj_a, _inputs, _income, _opex = await _seed(session)
    scenario_id, a_id = deal_model.id, proj_a.id

    # Enrich source project A: a use line and a 2-milestone trigger chain.
    ms1 = Milestone(
        project_id=a_id,
        milestone_type=MilestoneType.close,
        duration_days=30,
        sequence_order=1,
    )
    session.add(ms1)
    await session.flush()
    ms2 = Milestone(
        id=uuid.uuid4(),
        project_id=a_id,
        milestone_type=MilestoneType.construction,
        duration_days=90,
        sequence_order=2,
        trigger_milestone_id=ms1.id,
        trigger_offset_days=10,
    )
    session.add(ms2)
    # Flush milestones before the use line that FK-references them — the UOW
    # has no relationship() between UseLine and Milestone, so it won't order
    # the inserts on its own.
    await session.flush()
    whitelist_module_id = uuid.uuid4()
    session.add(
        UseLine(
            project_id=a_id,
            label="Acquisition",
            phase="acquisition",
            amount=Decimal("750000"),
            cost_category="hard",
            timing_type="spread_across_range",
            # Milestone-anchored timing + source whitelist: the copy must
            # carry these and REMAP the FKs onto the clone's milestones.
            active_from_milestone_id=ms1.id,
            spread_to_milestone_id=ms2.id,
            eligible_module_ids=[whitelist_module_id],
        )
    )
    # Target project B pre-loaded with junk that must be wiped.
    proj_b = Project(
        id=uuid.uuid4(), scenario_id=scenario_id, opportunity_id=opp.id, name="Target"
    )
    session.add(proj_b)
    await session.flush()
    b_id = proj_b.id
    session.add_all(
        [
            UseLine(project_id=b_id, label="Old Junk", amount=Decimal("1")),
            IncomeStream(
                project_id=b_id,
                stream_type=IncomeStreamType.residential_rent,
                label="Old Stream",
                unit_count=1,
                amount_per_unit_monthly=Decimal("100"),
            ),
            OperationalInputs(
                project_id=b_id, unit_count_new=1, opex_per_unit_annual=Decimal("1")
            ),
        ]
    )
    await session.commit()
    set_client_auth(client, user.id)

    resp = await client.post(
        f"/ui/deals/{scenario_id}/project/{b_id}/clone-from",
        data={"source_project_id": str(a_id)},
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    # Builder ?project= invariant: without the param, per-project JSONB
    # updates on the landing page silently no-op.
    assert resp.headers["location"] == f"/models/{scenario_id}/builder?project={b_id}"

    session.expire_all()

    # Use lines: junk wiped, source copy landed with the right money.
    b_uses = (
        await session.execute(select(UseLine).where(UseLine.project_id == b_id))
    ).scalars().all()
    assert [u.label for u in b_uses] == ["Acquisition"]
    b_acq = b_uses[0]
    assert Decimal(str(b_acq.amount)) == Decimal("750000")
    assert b_acq.phase == "acquisition"
    assert b_acq.cost_category == "hard"
    # Full-fidelity copy (fixed 2026-07-08): _copy_project_data is now
    # column-driven, so timing_type and the eligible_module_ids whitelist
    # survive the clone instead of reverting to column defaults (which
    # changed engine draw timing / source routing).
    assert b_acq.timing_type == "spread_across_range"
    assert b_acq.eligible_module_ids == [whitelist_module_id]

    # Income streams: junk stream replaced by the seeded "1BR Units" copy.
    b_streams = (
        await session.execute(
            select(IncomeStream).where(IncomeStream.project_id == b_id)
        )
    ).scalars().all()
    assert [s.label for s in b_streams] == ["1BR Units"]
    assert b_streams[0].unit_count == 8
    assert Decimal(str(b_streams[0].amount_per_unit_monthly)) == Decimal("1450")

    # Expense lines copied.
    b_opex = (
        await session.execute(
            select(OperatingExpenseLine).where(
                OperatingExpenseLine.project_id == b_id
            )
        )
    ).scalars().all()
    assert [e.label for e in b_opex] == ["Property Management"]
    assert Decimal(str(b_opex[0].annual_amount)) == Decimal("8640")

    # OperationalInputs replaced (old junk row gone, source values in).
    b_inputs = (
        await session.execute(
            select(OperationalInputs).where(OperationalInputs.project_id == b_id)
        )
    ).scalars().all()
    assert len(b_inputs) == 1
    assert b_inputs[0].unit_count_new == 8
    assert Decimal(str(b_inputs[0].opex_per_unit_annual)) == Decimal("3600")

    # Milestones copied with the trigger chain REMAPPED onto B's new rows.
    b_ms = {
        m.milestone_type: m
        for m in (
            await session.execute(
                select(Milestone).where(Milestone.project_id == b_id)
            )
        ).scalars()
    }
    assert set(b_ms) == {MilestoneType.close, MilestoneType.construction}
    assert b_ms[MilestoneType.construction].trigger_milestone_id == b_ms[MilestoneType.close].id
    assert b_ms[MilestoneType.construction].trigger_offset_days == 10

    # Use-line milestone FKs remapped onto B's NEW milestone rows (not left
    # pointing at A's) — part of the 2026-07-08 column-driven copy fix.
    assert b_acq.active_from_milestone_id == b_ms[MilestoneType.close].id
    assert b_acq.spread_to_milestone_id == b_ms[MilestoneType.construction].id

    # Source project A untouched.
    a_uses = (
        await session.execute(select(UseLine).where(UseLine.project_id == a_id))
    ).scalars().all()
    assert [u.label for u in a_uses] == ["Acquisition"]
    a_ms_count = len(
        (
            await session.execute(
                select(Milestone).where(Milestone.project_id == a_id)
            )
        ).scalars().all()
    )
    assert a_ms_count == 2


async def test_clone_from_guards(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user, _opp, deal_model, proj_a, _inputs, _income, _opex = await _seed(session)
    scenario_id, a_id = deal_model.id, proj_a.id

    # A project in a different scenario (second seeded deal, same org rules).
    org2, user2 = await seed_org(session)
    opp2 = await seed_opportunity(session, org2, user2)
    other_model, _, _, _ = await seed_deal_model_with_financials(session, opp2, user2)
    other_proj = (
        await session.execute(
            select(Project).where(Project.scenario_id == other_model.id)
        )
    ).scalar_one()
    other_proj_id = other_proj.id
    await session.commit()
    set_client_auth(client, user.id)

    # Self-clone rejected.
    self_clone = await client.post(
        f"/ui/deals/{scenario_id}/project/{a_id}/clone-from",
        data={"source_project_id": str(a_id)},
        follow_redirects=False,
    )
    assert self_clone.status_code == 400

    # Missing source rejected.
    missing = await client.post(
        f"/ui/deals/{scenario_id}/project/{a_id}/clone-from",
        data={},
        follow_redirects=False,
    )
    assert missing.status_code == 400

    # Cross-scenario source rejected.
    cross = await client.post(
        f"/ui/deals/{scenario_id}/project/{a_id}/clone-from",
        data={"source_project_id": str(other_proj_id)},
        follow_redirects=False,
    )
    assert cross.status_code == 400

    # Target's seeded data survived every rejected attempt.
    session.expire_all()
    streams = (
        await session.execute(
            select(IncomeStream).where(IncomeStream.project_id == a_id)
        )
    ).scalars().all()
    assert [s.label for s in streams] == ["1BR Units"]


# ---------------------------------------------------------------------------
# POST /ui/models/{id}/stack-order + /ui/models/{id}/capital-modules/reorder
# ---------------------------------------------------------------------------


async def _seed_modules(session: AsyncSession, scenario_id) -> list[uuid.UUID]:
    mods = [
        CapitalModule(
            scenario_id=scenario_id,
            label=f"Module {i}",
            vehicle_type="debt" if i == 1 else "equity",
            stack_position=i,
            source={"amount": 100000 * i},
        )
        for i in (1, 2, 3)
    ]
    session.add_all(mods)
    await session.commit()
    return [m.id for m in mods]


async def _positions(session: AsyncSession, ids: list[uuid.UUID]) -> list[int]:
    session.expire_all()
    out = []
    for mid in ids:
        mod = await session.get(CapitalModule, mid)
        out.append(mod.stack_position)
    return out


async def test_stack_order_persists_positions(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user, _opp, deal_model, _proj, _i, _inc, _op = await _seed(session)
    model_id = deal_model.id
    m1, m2, m3 = await _seed_modules(session, model_id)
    set_client_auth(client, user.id)

    resp = await client.post(
        f"/ui/models/{model_id}/stack-order",
        data={f"pos_{m1}": "3", f"pos_{m2}": "1", f"pos_{m3}": "2"},
    )
    assert resp.status_code == 200, resp.text
    assert await _positions(session, [m1, m2, m3]) == [3, 1, 2]

    # Unknown / unparsable keys are ignored, known ones still applied.
    resp2 = await client.post(
        f"/ui/models/{model_id}/stack-order",
        data={f"pos_{m1}": "not-a-number", f"pos_{m2}": "2", f"pos_{m3}": "1"},
    )
    assert resp2.status_code == 200
    assert await _positions(session, [m1, m2, m3]) == [3, 2, 1]


async def test_reorder_capital_modules_assigns_sequential_positions(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user, _opp, deal_model, _proj, _i, _inc, _op = await _seed(session)
    model_id = deal_model.id
    m1, m2, m3 = await _seed_modules(session, model_id)

    # A module on a DIFFERENT scenario smuggled into the ordered list must
    # not be touched (handler guards mod.scenario_id == model_id).
    org2, user2 = await seed_org(session)
    opp2 = await seed_opportunity(session, org2, user2)
    other_model, _, _, _ = await seed_deal_model_with_financials(session, opp2, user2)
    foreign = CapitalModule(
        scenario_id=other_model.id,
        label="Foreign",
        vehicle_type="equity",
        stack_position=99,
        source={"amount": 5},
    )
    session.add(foreign)
    await session.commit()
    foreign_id = foreign.id
    set_client_auth(client, user.id)

    resp = await client.post(
        f"/ui/models/{model_id}/capital-modules/reorder",
        data={"order": [str(m3), str(foreign_id), str(m1), str(m2)]},
    )
    assert resp.status_code == 200, resp.text
    # Positions assigned 1..N by list order; the foreign id consumes an index
    # but its row is untouched.
    assert await _positions(session, [m3, m1, m2]) == [1, 3, 4]
    foreign_fresh = await session.get(CapitalModule, foreign_id)
    assert foreign_fresh.stack_position == 99


# ---------------------------------------------------------------------------
# POST /ui/models/{id}/settings
# ---------------------------------------------------------------------------


async def test_model_settings_persist_scenario_inputs_and_debt_mirrors(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user, _opp, deal_model, proj, inputs, _inc, _op = await _seed(session)
    model_id, inputs_id, proj_id = deal_model.id, inputs.id, proj.id

    # A stabilized-operation milestone so hold_period writes duration_days,
    # and a perm-debt module so hold/dscr mirror into module source JSON.
    stab = Milestone(
        project_id=proj_id,
        milestone_type=MilestoneType.operation_stabilized,
        duration_days=365,
        sequence_order=1,
    )
    debt = CapitalModule(
        scenario_id=model_id,
        label="Perm Loan",
        vehicle_type="debt",
        stack_position=1,
        source={"amount": 500000, "interest_rate_pct": 6.0},
    )
    session.add_all([stab, debt])
    await session.commit()
    stab_id, debt_id = stab.id, debt.id
    set_client_auth(client, user.id)

    resp = await client.post(
        f"/ui/models/{model_id}/settings",
        data={
            "name": "Renamed Model",
            "deal_type": "new_construction",
            "expense_growth_rate_pct_annual": "4.0",
            "exit_cap_rate_pct": "6.25",
            "going_in_cap_rate_pct": "5.75",
            "capex_reserve_per_unit_annual": "750",
            "risk_free_rate_pct": "4.2",
            "discount_rate_pct": "9.5",
            "hold_period_years": "7",
            "dscr_minimum": "1.25",
            "operation_reserve_months": "9",
            "debt_structure": "construction_to_perm",
            "debt_sizing_mode": "dscr",
            "ht_occ_green": "93",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    assert resp.headers["location"] == f"/models/{model_id}/builder"

    session.expire_all()

    scenario = await session.get(Scenario, model_id)
    assert scenario.name == "Renamed Model"
    assert scenario.project_type == ProjectType.new_construction
    assert float(scenario.risk_free_rate_pct) == pytest.approx(4.2)
    assert float(scenario.discount_rate_pct) == pytest.approx(9.5)
    assert scenario.health_thresholds["occ_green"] == pytest.approx(93.0)

    fresh_inputs = await session.get(OperationalInputs, inputs_id)
    assert float(fresh_inputs.expense_growth_rate_pct_annual) == pytest.approx(4.0)
    assert float(fresh_inputs.exit_cap_rate_pct) == pytest.approx(6.25)
    assert float(fresh_inputs.going_in_cap_rate_pct) == pytest.approx(5.75)
    assert float(fresh_inputs.capex_reserve_per_unit_annual) == pytest.approx(750.0)
    assert fresh_inputs.operation_reserve_months == 9
    assert fresh_inputs.debt_structure == "construction_to_perm"
    assert fresh_inputs.debt_sizing_mode == "dscr"
    # Wizard-staging mirror of hold + DSCR.
    assert fresh_inputs.debt_terms["permanent_debt"]["hold_term_years"] == 7
    assert fresh_inputs.debt_terms["permanent_debt"]["dscr_min"] == pytest.approx(1.25)

    # Hold period lands on the operation_stabilized milestone (years * 365).
    fresh_stab = await session.get(Milestone, stab_id)
    assert fresh_stab.duration_days == 7 * 365

    # Hold + DSCR mirrored into every debt module's source JSON.
    fresh_debt = await session.get(CapitalModule, debt_id)
    assert fresh_debt.source["hold_term_years"] == 7
    assert fresh_debt.source["dscr_min"] == pytest.approx(1.25)
    assert fresh_debt.source["amount"] == 500000  # untouched


# ---------------------------------------------------------------------------
# POST /ui/projects/{id}/rename
# ---------------------------------------------------------------------------


async def test_rename_project_persists_and_escapes(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user, _opp, _deal_model, proj, _i, _inc, _op = await _seed(session)
    proj_id = proj.id
    set_client_auth(client, user.id)

    resp = await client.post(
        f"/ui/projects/{proj_id}/rename",
        data={"name": 'Phase <2> & "B"'},
    )
    assert resp.status_code == 200, resp.text
    # Raw name persisted; response HTML-escaped.
    session.expire_all()
    fresh = await session.get(Project, proj_id)
    assert fresh.name == 'Phase <2> & "B"'
    assert "Phase &lt;2&gt; &amp; &quot;B&quot;" in resp.text

    # Empty submit keeps the existing name.
    resp2 = await client.post(f"/ui/projects/{proj_id}/rename", data={"name": "  "})
    assert resp2.status_code == 200
    session.expire_all()
    fresh2 = await session.get(Project, proj_id)
    assert fresh2.name == 'Phase <2> & "B"'


# ---------------------------------------------------------------------------
# POST /ui/models/{id}/unit-mix/apply-to-revenue — money math
# ---------------------------------------------------------------------------

_UNIT_MIX = [
    {
        "id": "a0000000-0000-0000-0000-000000000001",
        "label": "1BR",
        "unit_count": 6,
        "unit_strategy": "base_escalation",
        "in_place_rent_per_unit": 1200,
        "market_rent_per_unit": 1400,
    },
    {
        "id": "a0000000-0000-0000-0000-000000000002",
        "label": "2BR",
        "unit_count": 4,
        "unit_strategy": "ltl_catchup",
        "in_place_rent_per_unit": 1500,
        "market_rent_per_unit": 1800,
    },
    {
        "id": "a0000000-0000-0000-0000-000000000003",
        "label": "3BR",
        "unit_count": 2,
        "unit_strategy": "value_add_renovation",
        "in_place_rent_per_unit": 1600,
        "market_rent_per_unit": 2000,
        "post_reno_rent_per_unit": 2400,
    },
    {
        "id": "a0000000-0000-0000-0000-000000000004",
        "label": "Zero",
        "unit_count": 0,
        "unit_strategy": "base_escalation",
        "in_place_rent_per_unit": 999,
    },
]


async def _streams_by_label(session: AsyncSession, project_id) -> dict[str, IncomeStream]:
    session.expire_all()
    rows = (
        await session.execute(
            select(IncomeStream).where(IncomeStream.project_id == project_id)
        )
    ).scalars().all()
    return {s.label: s for s in rows}


async def test_apply_unit_mix_derives_income_streams_per_strategy(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user, _opp, deal_model, proj, _i, _inc, _op = await _seed(session)
    model_id, proj_id = deal_model.id, proj.id
    proj.unit_mix = _UNIT_MIX
    session.add(proj)
    await session.commit()
    set_client_auth(client, user.id)

    resp = await client.post(f"/ui/models/{model_id}/unit-mix/apply-to-revenue")
    assert resp.status_code == 200, resp.text

    streams = await _streams_by_label(session, proj_id)
    # Seeded stub stream untouched (additive-only) + 3 generated rows;
    # zero-unit-count rows skipped.
    assert set(streams) == {"1BR Units", "1BR Rent", "2BR Rent", "3BR Rent (Renovated)"}

    one_br = streams["1BR Rent"]  # base_escalation → in-place rent
    assert one_br.unit_count == 6
    assert Decimal(str(one_br.amount_per_unit_monthly)) == Decimal("1200")
    assert Decimal(str(one_br.stabilized_occupancy_pct)) == Decimal("95")
    assert Decimal(str(one_br.escalation_rate_pct_annual)) == Decimal("3")
    assert one_br.active_in_phases == ["lease_up", "stabilized"]

    two_br = streams["2BR Rent"]  # ltl_catchup → in-place now, market target
    assert two_br.unit_count == 4
    assert Decimal(str(two_br.amount_per_unit_monthly)) == Decimal("1500")
    assert Decimal(str(two_br.catchup_target_rent)) == Decimal("1800")

    three_br = streams["3BR Rent (Renovated)"]  # value_add → post-reno rent
    assert three_br.unit_count == 2
    assert Decimal(str(three_br.amount_per_unit_monthly)) == Decimal("2400")
    assert Decimal(str(three_br.renovation_absorption_rate)) == Decimal("1")

    # Additive-only re-apply: manual edits survive, no duplicates.
    one_br.amount_per_unit_monthly = Decimal("1250")
    session.add(one_br)
    await session.commit()
    one_br_id = one_br.id

    resp2 = await client.post(f"/ui/models/{model_id}/unit-mix/apply-to-revenue")
    assert resp2.status_code == 200
    streams2 = await _streams_by_label(session, proj_id)
    assert len(streams2) == 4  # no duplicate rows
    assert streams2["1BR Rent"].id == one_br_id
    assert Decimal(str(streams2["1BR Rent"].amount_per_unit_monthly)) == Decimal("1250")


async def test_apply_unit_mix_targets_project_from_hx_current_url(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The builder ?project= invariant: without a project in HX-Current-URL
    the handler falls back to the DEFAULT (oldest) project — so a second
    project's unit mix is only applied when the header carries ?project=.
    """
    _org, user, opp, deal_model, _proj_a, _i, _inc, _op = await _seed(session)
    model_id = deal_model.id
    # Second (non-default) project holding the unit mix. Committed after the
    # seed so created_at ordering is deterministic (default = project A).
    proj_b = Project(
        id=uuid.uuid4(),
        scenario_id=model_id,
        opportunity_id=opp.id,
        name="Phase B",
        unit_mix=[
            {
                "id": "b0000000-0000-0000-0000-000000000001",
                "label": "B-Unit",
                "unit_count": 3,
                "unit_strategy": "base_escalation",
                "in_place_rent_per_unit": 1000,
            }
        ],
    )
    session.add(proj_b)
    await session.commit()
    b_id = proj_b.id
    set_client_auth(client, user.id)

    # No HX-Current-URL → falls back to default project A, whose unit_mix is
    # empty → nothing is generated anywhere.
    resp = await client.post(f"/ui/models/{model_id}/unit-mix/apply-to-revenue")
    assert resp.status_code == 200, resp.text
    session.expire_all()
    b_streams = (
        await session.execute(
            select(IncomeStream).where(IncomeStream.project_id == b_id)
        )
    ).scalars().all()
    assert b_streams == [], "streams must not land on B without ?project= context"

    # With ?project={B} in HX-Current-URL, rows land on B.
    resp2 = await client.post(
        f"/ui/models/{model_id}/unit-mix/apply-to-revenue",
        headers={"HX-Current-URL": f"http://test/models/{model_id}/builder?project={b_id}"},
    )
    assert resp2.status_code == 200, resp2.text
    streams = await _streams_by_label(session, b_id)
    assert set(streams) == {"B-Unit Rent"}
    assert streams["B-Unit Rent"].unit_count == 3
    assert Decimal(str(streams["B-Unit Rent"].amount_per_unit_monthly)) == Decimal("1000")
