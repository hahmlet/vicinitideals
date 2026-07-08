"""Integration tests for app/api/routers/ui_wizards.py — deal setup wizard
and timeline approval.

Covers the previously-untested SYSTEMS-LOGIC routes:

  - GET  /ui/models/{model_id}/setup           (wizard entry / step render)
  - POST /ui/models/{model_id}/setup/step      (step 1-5 persistence + validation)
  - POST /ui/models/{model_id}/setup/complete  (CapitalModule auto-creation,
        exit-vehicle UUID resolution, milestone-FK sync, OpEx/UseLine seeding)
  - POST /ui/projects/{project_id}/approve-timeline
  - POST /ui/projects/{project_id}/timeline-wizard  (name/type rename path only —
        chain-shape assertions live in tests/api/test_milestones_api.py)

The timeline-wizard two-pass chain creation itself is covered by
tests/api/test_milestones_api.py::test_timeline_wizard_still_creates_wired_chain;
here the approve-timeline tests re-verify the chain resolves via
Milestone.computed_start() chain-walk AFTER approval, because the engine
falls back to OperationalInputs.*_months scalars when the chain is broken
(production bug 5d5caf4).

Assertions target DB substance (rows, JSONB payloads, FK wiring, computed
dates), not just status codes.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule, CapitalModuleProject
from app.models.deal import (
    Deal,
    IncomeStream,
    OperatingExpenseLine,
    OperationalInputs,
    Scenario,
    UseLine,
)
from app.models.milestone import Milestone
from app.models.project import Opportunity, Project
from app.models.source_vehicle import SourceVehicle

from tests.conftest import (
    seed_deal_model,
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
    set_client_auth,
)

pytestmark = pytest.mark.asyncio

ANCHOR_DATE = date(2026, 1, 1)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def client(client: AsyncClient) -> AsyncClient:
    """These wizard routes are HTMX fragments in prod, so every test request
    carries the hx-request header. Since 2026-07-08 the require_auth_for_ui
    middleware no longer exempts HTMX requests (the header is
    attacker-settable), so each test must ALSO authenticate via a session
    cookie — ``_seed_setup_model`` / ``set_client_auth`` handle that.
    The header additionally keeps the onboarding_guard middleware (which
    opens its own prod-engine DB session) out of the request path."""
    client.headers["hx-request"] = "true"
    return client


@pytest.fixture
def stub_redis_getdel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize the synchronous Redis call in deal_setup_wizard_get.

    The GET /ui/models/{id}/setup handler does a blocking
    ``redis.from_url(...).getdel(...)``. The route now degrades gracefully
    when Redis is unreachable (try/except with 1s timeouts — no more 500),
    but stubbing getdel keeps these tests hermetic and avoids paying the
    connect-timeout on every request from outside the compose network.
    """
    import redis

    monkeypatch.setattr(redis.Redis, "getdel", lambda self, key: None)


async def _seed_setup_model(session: AsyncSession, client: AsyncClient) -> dict:
    """Org + user + opportunity + Scenario + default Project + inputs.

    Authenticates *client* as the seeded user (session cookie + CSRF header)
    so requests survive the require_auth_for_ui and csrf_protection
    middlewares. Returns plain ids only (safe across the route's
    session.expire_all()).
    """
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
    set_client_auth(client, user.id)
    return {
        "org_id": org.id,
        "user_id": user.id,
        "opp_id": opp.id,
        "deal_id": deal_model.deal_id,
        "model_id": deal_model.id,
        "project_id": project.id,
        "inputs_id": inputs.id,
    }


async def _set_debt_types(
    session: AsyncSession, inputs_id: uuid.UUID, debt_types: list[str]
) -> None:
    inputs = await session.get(OperationalInputs, inputs_id)
    inputs.debt_types = debt_types
    await session.flush()


async def _fresh_inputs(
    session: AsyncSession, inputs_id: uuid.UUID
) -> OperationalInputs:
    session.expire_all()
    return await session.get(OperationalInputs, inputs_id)


# ---------------------------------------------------------------------------
# GET /ui/models/{model_id}/setup
# ---------------------------------------------------------------------------


async def test_setup_get_renders_step1_by_default(
    client: AsyncClient, session: AsyncSession, stub_redis_getdel: None
) -> None:
    ids = await _seed_setup_model(session, client)

    resp = await client.get(f"/ui/models/{ids['model_id']}/setup")
    assert resp.status_code == 200, resp.text
    assert "Income &amp; Sizing" in resp.text  # step 1 title
    assert 'name="step" value="1"' in resp.text


async def test_setup_get_renders_requested_step(
    client: AsyncClient, session: AsyncSession, stub_redis_getdel: None
) -> None:
    ids = await _seed_setup_model(session, client)

    resp = await client.get(f"/ui/models/{ids['model_id']}/setup", params={"step": 2})
    assert resp.status_code == 200, resp.text
    assert "Debt Stack" in resp.text  # step 2 title
    assert 'name="step" value="2"' in resp.text


async def test_setup_get_unknown_model_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user = await seed_org(session)
    set_client_auth(client, user.id)
    resp = await client.get(f"/ui/models/{uuid.uuid4()}/setup")
    assert resp.status_code == 404


async def test_setup_routes_unauthenticated_htmx_401_with_hx_redirect(
    client: AsyncClient, session: AsyncSession, stub_redis_getdel: None
) -> None:
    """The 2026-07-08 auth fix: unauthenticated HTMX requests no longer skip
    the session check. They get 401 with an HX-Redirect header (full-page
    login redirect) instead of a 303 (which would swap the login page into
    a fragment)."""
    ids = await _seed_setup_model(session, client)
    client.cookies.clear()  # drop the session cookie set by the seed helper

    resp = await client.get(f"/ui/models/{ids['model_id']}/setup")
    assert resp.status_code == 401
    assert resp.headers["hx-redirect"] == (
        f"/login?next=/ui/models/{ids['model_id']}/setup"
    )

    post = await client.post(
        f"/ui/models/{ids['model_id']}/setup/step", data={"step": "1"}
    )
    assert post.status_code == 401
    assert post.headers["hx-redirect"].startswith("/login?next=")


# ---------------------------------------------------------------------------
# POST /ui/models/{model_id}/setup/step — step 1 (income + sizing mode)
# ---------------------------------------------------------------------------


async def test_setup_step1_persists_income_and_sizing_mode(
    client: AsyncClient, session: AsyncSession
) -> None:
    ids = await _seed_setup_model(session, client)
    model_id, inputs_id = ids["model_id"], ids["inputs_id"]

    resp = await client.post(
        f"/ui/models/{model_id}/setup/step",
        data={
            "step": "1",
            "income_mode": "noi",
            "debt_sizing_mode": "dscr_capped",
        },
    )
    assert resp.status_code == 200, resp.text
    assert "Debt Stack" in resp.text  # advanced to step 2

    session.expire_all()
    model = await session.get(Scenario, model_id)
    inputs = await session.get(OperationalInputs, inputs_id)
    assert model.income_mode == "noi"
    assert inputs.debt_sizing_mode == "dscr_capped"


async def test_setup_step1_rejects_unknown_income_mode_with_fallback(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Unknown income_mode values are coerced to 'revenue_opex', not persisted raw."""
    ids = await _seed_setup_model(session, client)

    resp = await client.post(
        f"/ui/models/{ids['model_id']}/setup/step",
        data={"step": "1", "income_mode": "bogus_mode"},
    )
    assert resp.status_code == 200, resp.text

    session.expire_all()
    model = await session.get(Scenario, ids["model_id"])
    assert model.income_mode == "revenue_opex"


# ---------------------------------------------------------------------------
# Step 2 — debt stack
# ---------------------------------------------------------------------------


async def test_setup_step2_persists_debt_types_filtering_unknown(
    client: AsyncClient, session: AsyncSession
) -> None:
    ids = await _seed_setup_model(session, client)

    resp = await client.post(
        f"/ui/models/{ids['model_id']}/setup/step",
        data={
            "step": "2",
            "debt_types": ["construction_loan", "junk_loan", "permanent_debt"],
        },
    )
    assert resp.status_code == 200, resp.text
    assert "Milestones &amp; Retirement" in resp.text  # advanced to step 3

    inputs = await _fresh_inputs(session, ids["inputs_id"])
    # Unknown type filtered out, submitted order preserved.
    assert inputs.debt_types == ["construction_loan", "permanent_debt"]


async def test_setup_step2_vehicle_pick_skips_to_review(
    client: AsyncClient, session: AsyncSession
) -> None:
    """When every selected debt type has a Source Vehicle, steps 3-5 are
    skipped (vehicle carries milestones/terms/sizing) and the vehicle's
    rate/carry/amort are staged into debt_terms."""
    ids = await _seed_setup_model(session, client)

    sv = SourceVehicle(
        id=uuid.uuid4(),
        scope="org",
        owner_id=ids["org_id"],
        label="Agency Perm",
        vehicle_type="debt",
        interest_rate_pct=Decimal("5.75"),
        carry_type="pi",
        amort_term_years=35,
    )
    session.add(sv)
    await session.flush()
    sv_id = sv.id

    resp = await client.post(
        f"/ui/models/{ids['model_id']}/setup/step",
        data={
            "step": "2",
            "debt_types": ["permanent_debt"],
            "vehicle_id_permanent_debt": str(sv_id),
        },
    )
    assert resp.status_code == 200, resp.text
    assert "Review Setup" in resp.text  # jumped straight to step 6

    inputs = await _fresh_inputs(session, ids["inputs_id"])
    staged = inputs.debt_terms["permanent_debt"]
    assert staged["vehicle_id"] == str(sv_id)
    assert staged["rate_pct"] == 5.75
    assert staged["loan_type"] == "pi"
    assert staged["amort_years"] == 35


# ---------------------------------------------------------------------------
# Step 3 — milestones & exit vehicle
# ---------------------------------------------------------------------------


async def test_setup_step3_persists_milestone_config(
    client: AsyncClient, session: AsyncSession
) -> None:
    ids = await _seed_setup_model(session, client)
    await _set_debt_types(
        session, ids["inputs_id"], ["construction_loan", "permanent_debt"]
    )

    resp = await client.post(
        f"/ui/models/{ids['model_id']}/setup/step",
        data={
            "step": "3",
            "construction_loan_active_from": "construction",
            "construction_loan_exit_vehicle": "permanent_debt",
            "permanent_debt_active_from": "operation_lease_up",
            "permanent_debt_exit_vehicle": "maturity",
        },
    )
    assert resp.status_code == 200, resp.text
    assert "Debt Terms" in resp.text  # advanced to step 4

    inputs = await _fresh_inputs(session, ids["inputs_id"])
    assert inputs.debt_milestone_config == {
        "construction_loan": {
            "active_from": "construction",
            "exit_vehicle": "permanent_debt",
        },
        "permanent_debt": {
            "active_from": "operation_lease_up",
            "exit_vehicle": "maturity",
        },
    }


async def test_setup_step3_rejects_invalid_exit_vehicle(
    client: AsyncClient, session: AsyncSession
) -> None:
    ids = await _seed_setup_model(session, client)
    await _set_debt_types(
        session, ids["inputs_id"], ["construction_loan", "permanent_debt"]
    )

    # Exit vehicle referencing a debt type that was NOT selected.
    resp = await client.post(
        f"/ui/models/{ids['model_id']}/setup/step",
        data={
            "step": "3",
            "construction_loan_exit_vehicle": "bridge",
        },
    )
    assert resp.status_code == 200, resp.text
    assert "not one of the selected debt types" in resp.text
    # Same step re-rendered, not advanced.
    assert "Milestones &amp; Retirement" in resp.text

    # Self-retirement is rejected too.
    resp2 = await client.post(
        f"/ui/models/{ids['model_id']}/setup/step",
        data={
            "step": "3",
            "permanent_debt_exit_vehicle": "permanent_debt",
        },
    )
    assert resp2.status_code == 200, resp2.text
    assert "cannot retire itself" in resp2.text

    inputs = await _fresh_inputs(session, ids["inputs_id"])
    assert inputs.debt_milestone_config is None  # nothing persisted


# ---------------------------------------------------------------------------
# Step 4 — loan terms
# ---------------------------------------------------------------------------


async def test_setup_step4_persists_terms(
    client: AsyncClient, session: AsyncSession
) -> None:
    ids = await _seed_setup_model(session, client)
    await _set_debt_types(session, ids["inputs_id"], ["permanent_debt"])

    resp = await client.post(
        f"/ui/models/{ids['model_id']}/setup/step",
        data={
            "step": "4",
            "permanent_debt_loan_type": "pi",
            "permanent_debt_rate_pct": "5.5",
            "permanent_debt_amort_years": "30",
            "permanent_debt_hold_term_years": "10",
        },
    )
    assert resp.status_code == 200, resp.text
    assert "Debt Sizing" in resp.text  # advanced to step 5

    inputs = await _fresh_inputs(session, ids["inputs_id"])
    entry = inputs.debt_terms["permanent_debt"]
    assert entry["loan_type"] == "pi"
    assert entry["rate_pct"] == 5.5
    assert entry["amort_years"] == 30
    assert entry["hold_term_years"] == 10


async def test_setup_step4_rejects_out_of_range_values(
    client: AsyncClient, session: AsyncSession
) -> None:
    ids = await _seed_setup_model(session, client)
    await _set_debt_types(session, ids["inputs_id"], ["permanent_debt"])

    # Rate above the 0-30% band → field error, same step re-rendered.
    resp = await client.post(
        f"/ui/models/{ids['model_id']}/setup/step",
        data={"step": "4", "permanent_debt_rate_pct": "45"},
    )
    assert resp.status_code == 200, resp.text
    assert "outside 0" in resp.text  # "outside 0–30%"
    assert "Debt Terms" in resp.text  # NOT advanced

    # Non-numeric rate → field error.
    resp2 = await client.post(
        f"/ui/models/{ids['model_id']}/setup/step",
        data={"step": "4", "permanent_debt_rate_pct": "cheap"},
    )
    assert resp2.status_code == 200, resp2.text
    assert "must be a number" in resp2.text

    # Unknown loan type → field error.
    resp3 = await client.post(
        f"/ui/models/{ids['model_id']}/setup/step",
        data={"step": "4", "permanent_debt_loan_type": "balloon_madness"},
    )
    assert resp3.status_code == 200, resp3.text
    assert "Unknown loan type" in resp3.text

    inputs = await _fresh_inputs(session, ids["inputs_id"])
    assert inputs.debt_terms is None  # nothing persisted on any error path


# ---------------------------------------------------------------------------
# Step 5 — sizing
# ---------------------------------------------------------------------------


async def test_setup_step5_persists_sizing_and_dscr_min(
    client: AsyncClient, session: AsyncSession
) -> None:
    ids = await _seed_setup_model(session, client)
    await _set_debt_types(session, ids["inputs_id"], ["permanent_debt"])

    resp = await client.post(
        f"/ui/models/{ids['model_id']}/setup/step",
        data={
            "step": "5",
            "permanent_debt_sizing_approach": "ltv",
            "permanent_debt_ltv_pct": "65",
            "dscr_minimum": "1.25",
        },
    )
    assert resp.status_code == 200, resp.text
    assert "Review Setup" in resp.text  # advanced to step 6

    inputs = await _fresh_inputs(session, ids["inputs_id"])
    entry = inputs.debt_terms["permanent_debt"]
    assert entry["sizing_approach"] == "ltv"
    assert entry["ltv_pct"] == 65.0
    assert entry["dscr_min"] == 1.25


# ---------------------------------------------------------------------------
# POST /ui/models/{model_id}/setup/complete — the finalize systems logic
# ---------------------------------------------------------------------------


async def test_setup_complete_full_flow_creates_wired_capital_stack(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Drive the whole production flow — timeline wizard → approve-timeline
    (wizard mode) → setup steps 1-5 → complete — then verify the finalize
    handler's systems logic:

      1. one CapitalModule per selected debt type, "(auto)"-labelled
      2. exit_vehicle resolved to the RETIRER MODULE'S UUID (construction →
         permanent) with active_phase_end derived from the retirer's start
      3. carry JSONB built per loan type from wizard debt_terms
      4. milestone FKs synced from active_phase strings to the timeline
         milestones created by the wizard (trigger-chain rows)
      5. junction rows attach every auto module to the default project
      6. Operating Reserve UseLine + canonical OpEx seed lines created
      7. deal_setup_complete flag + debt_structure sync + health thresholds
    """
    ids = await _seed_setup_model(session, client)
    model_id, project_id, inputs_id = (
        ids["model_id"], ids["project_id"], ids["inputs_id"],
    )

    # ── Timeline wizard: anchor at Close + full value-add chain ───────────
    tw = await client.post(
        f"/ui/projects/{project_id}/timeline-wizard",
        data={
            "anchor_type": "close",
            "anchor_date": ANCHOR_DATE.isoformat(),
            "anchor_duration_days": "45",
            "milestone_types": [
                "close", "pre_development", "construction",
                "operation_lease_up", "operation_stabilized", "divestment",
            ],
            "duration_pre_development": "90",
            "duration_construction": "180",
            "duration_operation_lease_up": "120",
            "duration_operation_stabilized": "1825",
            "_wizard": "1",
        },
    )
    assert tw.status_code == 303, tw.text
    assert "wizard=1" in tw.headers["location"]

    # ── Approve timeline in wizard mode → routed into deal setup ──────────
    approve = await client.post(
        f"/ui/projects/{project_id}/approve-timeline", data={"_wizard": "1"}
    )
    assert approve.status_code == 303, approve.text
    assert approve.headers["location"] == (
        f"/models/{model_id}/builder?project={project_id}"
        "&module=deal_setup&wizard=1"
    )

    # ── Setup steps 1-5 ────────────────────────────────────────────────────
    steps = [
        {"step": "1", "income_mode": "revenue_opex", "debt_sizing_mode": "gap_fill"},
        {"step": "2", "debt_types": ["construction_loan", "permanent_debt"]},
        {
            "step": "3",
            "construction_loan_active_from": "construction",
            "construction_loan_exit_vehicle": "permanent_debt",
            "permanent_debt_active_from": "operation_lease_up",
            "permanent_debt_exit_vehicle": "maturity",
        },
        {
            "step": "4",
            "construction_loan_loan_type": "interest_reserve",
            "construction_loan_rate_pct": "6.25",
            "permanent_debt_loan_type": "pi",
            "permanent_debt_rate_pct": "5.5",
            "permanent_debt_amort_years": "30",
            "permanent_debt_hold_term_years": "10",
        },
        {"step": "5", "dscr_minimum": "1.20"},
    ]
    for payload in steps:
        step_resp = await client.post(
            f"/ui/models/{model_id}/setup/step", data=payload
        )
        assert step_resp.status_code == 200, (payload["step"], step_resp.text)

    # ── Finalize ───────────────────────────────────────────────────────────
    done = await client.post(
        f"/ui/models/{model_id}/setup/complete",
        data={"ht_dscr_green": "1.25", "ht_occ_green": "93"},
    )
    assert done.status_code == 204, done.text
    # revenue_opex mode lands on the Property module.
    assert done.headers["hx-redirect"] == (
        f"/models/{model_id}/builder?module=property"
    )

    session.expire_all()

    # 1+2+3 — capital modules with resolved exit vehicles and carry payloads
    modules = list((await session.execute(
        select(CapitalModule).where(CapitalModule.scenario_id == model_id)
    )).scalars())
    by_label = {m.label: m for m in modules}
    assert set(by_label) == {"Construction Loan (auto)", "Permanent Debt (auto)"}
    constr = by_label["Construction Loan (auto)"]
    perm = by_label["Permanent Debt (auto)"]

    assert constr.stack_position == 1
    assert constr.active_phase_start == "construction"
    # Construction is retired by perm → its end is perm's active_from.
    assert constr.active_phase_end == "operation_lease_up"
    assert constr.exit_terms["vehicle"] == str(perm.id)
    assert constr.exit_terms["trigger"] == "Permanent Debt"
    assert constr.carry == {"carry_type": "interest_reserve", "io_rate_pct": 6.25}
    assert constr.source["auto_size"] is True
    assert constr.source["interest_rate_pct"] == 6.25

    assert perm.stack_position == 2
    assert perm.active_phase_start == "operation_lease_up"
    assert perm.active_phase_end == "exit"  # maturity → through exit
    assert perm.exit_terms == {
        "exit_type": "full_payoff",
        "trigger": "end of hold period",
        "vehicle": "maturity",
    }
    assert perm.carry == {
        "carry_type": "pi", "amort_term_years": 30, "io_rate_pct": 5.5,
    }
    assert perm.source["hold_term_years"] == 10  # wizard staging honored
    assert perm.source["dscr_min"] == 1.2  # from step 5 dscr_minimum

    # 4 — milestone FKs synced from phase strings to the wizard's milestones
    milestones = list((await session.execute(
        select(Milestone).where(Milestone.project_id == project_id)
    )).scalars())
    ms_by_type = {
        str(m.milestone_type).replace("MilestoneType.", ""): m for m in milestones
    }
    assert constr.active_from_milestone_id == ms_by_type["construction"].id
    assert constr.active_to_milestone_id == ms_by_type["operation_lease_up"].id
    assert perm.active_from_milestone_id == ms_by_type["operation_lease_up"].id
    assert perm.active_to_milestone_id == ms_by_type["divestment"].id

    # 5 — junction rows for the default project
    junctions = list((await session.execute(
        select(CapitalModuleProject).where(
            CapitalModuleProject.capital_module_id.in_([constr.id, perm.id])
        )
    )).scalars())
    assert {j.project_id for j in junctions} == {project_id}
    assert all(j.auto_size for j in junctions)
    assert len(junctions) == 2

    # 6 — Operating Reserve stub + canonical OpEx seed set
    reserve = (await session.execute(
        select(UseLine).where(
            UseLine.project_id == project_id,
            UseLine.label == "Operating Reserve",
        )
    )).scalar_one()
    assert Decimal(str(reserve.amount)) == Decimal("0")
    assert reserve.phase == "operation"

    opex_labels = set((await session.execute(
        select(OperatingExpenseLine.label).where(
            OperatingExpenseLine.project_id == project_id
        )
    )).scalars())
    # 19 seeds + the pre-existing "Property Management" (skipped, not duplicated)
    assert len(opex_labels) == 20
    assert {"Real Estate Taxes", "Insurance", "Property Management"} <= opex_labels

    # Pre-existing income stream short-circuits revenue seeding (no dupes).
    income_count = len(list((await session.execute(
        select(IncomeStream).where(IncomeStream.project_id == project_id)
    )).scalars()))
    assert income_count == 1

    # unit_mix seeded from OperationalInputs.unit_count_new
    project = await session.get(Project, project_id)
    assert project.unit_mix and project.unit_mix[0]["unit_count"] == 8

    # 7 — flags, structure sync, health thresholds
    inputs = await session.get(OperationalInputs, inputs_id)
    assert inputs.deal_setup_complete is True
    assert inputs.debt_structure == "construction_and_perm"

    model = await session.get(Scenario, model_id)
    assert model.health_thresholds == {"dscr_green": 1.25, "occ_green": 93.0}


async def test_setup_complete_rerun_is_idempotent(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Re-running complete deletes and recreates the (auto) modules instead
    of stacking duplicates, and doesn't duplicate seeds."""
    ids = await _seed_setup_model(session, client)
    model_id, project_id = ids["model_id"], ids["project_id"]
    await _set_debt_types(session, ids["inputs_id"], ["permanent_debt"])

    for _ in range(2):
        done = await client.post(f"/ui/models/{model_id}/setup/complete", data={})
        assert done.status_code == 204, done.text

    session.expire_all()
    modules = list((await session.execute(
        select(CapitalModule).where(CapitalModule.scenario_id == model_id)
    )).scalars())
    assert [m.label for m in modules] == ["Permanent Debt (auto)"]

    reserves = list((await session.execute(
        select(UseLine).where(
            UseLine.project_id == project_id,
            UseLine.label == "Operating Reserve",
        )
    )).scalars())
    assert len(reserves) == 1

    opex_count = len(list((await session.execute(
        select(OperatingExpenseLine.label).where(
            OperatingExpenseLine.project_id == project_id
        )
    )).scalars()))
    assert opex_count == 20  # not 39/40 — seeds are label-idempotent


async def test_setup_step_and_complete_without_project_400(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A Scenario with no default Project can't run the wizard."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model = await seed_deal_model(session, opp, user)  # no Project row
    model_id = deal_model.id
    set_client_auth(client, user.id)

    step = await client.post(
        f"/ui/models/{model_id}/setup/step", data={"step": "1"}
    )
    assert step.status_code == 400

    done = await client.post(f"/ui/models/{model_id}/setup/complete", data={})
    assert done.status_code == 400


async def test_setup_step_unknown_model_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user = await seed_org(session)
    set_client_auth(client, user.id)
    resp = await client.post(
        f"/ui/models/{uuid.uuid4()}/setup/step", data={"step": "1"}
    )
    assert resp.status_code == 404

    resp2 = await client.post(f"/ui/models/{uuid.uuid4()}/setup/complete", data={})
    assert resp2.status_code == 404


# ---------------------------------------------------------------------------
# POST /ui/projects/{project_id}/approve-timeline
# ---------------------------------------------------------------------------


async def _build_timeline(client: AsyncClient, project_id: uuid.UUID) -> None:
    """Drive the timeline wizard so the project has a trigger-chained timeline."""
    resp = await client.post(
        f"/ui/projects/{project_id}/timeline-wizard",
        data={
            "anchor_type": "close",
            "anchor_date": ANCHOR_DATE.isoformat(),
            "anchor_duration_days": "45",
            "milestone_types": [
                "close", "pre_development", "construction",
                "operation_lease_up", "operation_stabilized", "divestment",
            ],
            "duration_pre_development": "90",
            "duration_construction": "180",
            "duration_operation_lease_up": "120",
            "duration_operation_stabilized": "1825",
        },
    )
    assert resp.status_code == 303, resp.text


async def test_approve_timeline_sets_flag_with_resolving_chain(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Approve after the wizard: flag set, redirect to sources, and — the
    systems-logic part — every milestone still resolves a start date via the
    trigger-chain walk (the engine's alternative is the 1-month scalar
    fallback that collapsed carry math in prod bug 5d5caf4)."""
    ids = await _seed_setup_model(session, client)
    model_id, project_id = ids["model_id"], ids["project_id"]

    await _build_timeline(client, project_id)

    resp = await client.post(f"/ui/projects/{project_id}/approve-timeline", data={})
    assert resp.status_code == 303, resp.text
    assert resp.headers["location"] == (
        f"/models/{model_id}/builder?project={project_id}&module=sources"
    )

    session.expire_all()
    project = await session.get(Project, project_id)
    assert project.timeline_approved is True

    rows = list((await session.execute(
        select(Milestone)
        .where(Milestone.project_id == project_id)
        .order_by(Milestone.sequence_order)
    )).scalars())
    assert len(rows) == 6

    # Two-pass creation outcome: exactly one anchor, all others trigger-wired
    # to the previous milestone in submitted order.
    anchor, *chained = rows
    assert anchor.trigger_milestone_id is None
    assert anchor.target_date == ANCHOR_DATE
    for prev, cur in zip(rows, chained):
        assert cur.trigger_milestone_id == prev.id, (
            f"{cur.milestone_type} not chained to {prev.milestone_type}"
        )

    # Chain-walk resolves a start date for EVERY milestone.
    milestone_map = {r.id: r for r in rows}
    durations = [45, 90, 180, 120, 1825, 1]  # divestment forced to 1 day
    offset = 0
    for row, dur in zip(rows, durations):
        start = row.computed_start(milestone_map)
        assert start == ANCHOR_DATE + timedelta(days=offset), (
            f"{row.milestone_type}: expected offset {offset}, got {start}"
        )
        assert row.duration_days == dur
        offset += dur


async def test_approve_timeline_unapprove_reopens(
    client: AsyncClient, session: AsyncSession
) -> None:
    ids = await _seed_setup_model(session, client)
    model_id, project_id = ids["model_id"], ids["project_id"]

    approved = await client.post(
        f"/ui/projects/{project_id}/approve-timeline", data={}
    )
    assert approved.status_code == 303

    session.expire_all()
    assert (await session.get(Project, project_id)).timeline_approved is True

    reopened = await client.post(
        f"/ui/projects/{project_id}/approve-timeline", data={"_unapprove": "1"}
    )
    assert reopened.status_code == 303
    assert reopened.headers["location"] == (
        f"/models/{model_id}/builder?project={project_id}&module=timeline"
    )

    session.expire_all()
    assert (await session.get(Project, project_id)).timeline_approved is False


async def test_approve_timeline_unknown_project_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user = await seed_org(session)
    set_client_auth(client, user.id)
    resp = await client.post(
        f"/ui/projects/{uuid.uuid4()}/approve-timeline", data={}
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Timeline wizard step-0 rename path (name/type update before chain creation)
# ---------------------------------------------------------------------------


async def test_timeline_wizard_renames_deal_and_sets_project_type(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The new-deal wizard's step 0 rides on the timeline-wizard POST:
    new_name renames the Deal AND the linked Opportunity; new_deal_type
    updates Scenario.project_type."""
    ids = await _seed_setup_model(session, client)
    project_id = ids["project_id"]

    resp = await client.post(
        f"/ui/projects/{project_id}/timeline-wizard",
        data={
            "anchor_type": "close",
            "anchor_date": ANCHOR_DATE.isoformat(),
            "anchor_duration_days": "45",
            "milestone_types": ["close", "operation_stabilized"],
            "new_name": "Renamed Tower",
            "new_deal_type": "acquisition",
        },
    )
    assert resp.status_code == 303, resp.text

    session.expire_all()
    deal = await session.get(Deal, ids["deal_id"])
    opp = await session.get(Opportunity, ids["opp_id"])
    model = await session.get(Scenario, ids["model_id"])
    assert deal.name == "Renamed Tower"
    assert opp.name == "Renamed Tower"
    assert str(model.project_type).replace("ProjectType.", "") == "acquisition"
