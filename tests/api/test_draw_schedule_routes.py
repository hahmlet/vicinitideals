"""Integration tests for the draw-schedule UI routes (app/api/routers/ui_model_outputs.py).

Covers:
  - GET    /ui/models/{id}/draw-schedule                    (panel render + reconciler seed)
  - POST   /ui/models/{id}/draw-schedule/sources            (create — reconciled away, documented)
  - PATCH  /ui/models/{id}/draw-schedule/sources/{sid}      (active-window update)
  - DELETE /ui/models/{id}/draw-schedule/sources/{sid}      (delete + reconciler re-seed, documented)
  - POST   /ui/models/{id}/draw-schedule/settings           (reserve floors persisted)
  - POST   /ui/models/{id}/draw-schedule/calculate          (engine run + writeback math)

Auth notes: these handlers do not resolve a user themselves, but the
``require_auth_for_ui`` middleware 303-redirects unauthenticated non-HTMX
requests to /login for every /ui/ path — so tests authenticate with the
session cookie via ``set_client_auth`` (CSRF is only enforced on
HTMX-flagged requests, which these are not).

Reconciler behavior (intentional, per test_draw_source_reconciler.py):
``_load_draw_schedule_ctx`` deletes DrawSources with ``capital_module_id=NULL``
and re-seeds DrawSources for CapitalModules that lack one. Because the POST
and DELETE handlers reload that ctx after mutating, standalone creates are
un-done and CM-backed deletes are re-seeded within the same request. Tests
below assert that actual behavior and document it.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule, DrawSource
from app.models.deal import Scenario, UseLine
from app.models.milestone import Milestone, MilestoneType
from app.models.project import Project

from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
    set_client_auth,
)

pytestmark = pytest.mark.asyncio


async def _seed_draw_deal(
    session: AsyncSession,
    *,
    with_milestones: bool = True,
    with_debt_module: bool = True,
):
    """Scenario + project + anchored milestones + use lines + one 0%-interest
    auto-sizing debt module.

    With a 0% rate and no interest-reserve carry the draw engine's total
    drawn for the loan must equal total uses exactly (no carry cost) — this
    makes the calculate writeback assertable to the dollar.

    Returns plain ids (model_id, project_id, user_id, cm_id) captured before
    any HTTP round-trip can expire ORM state.
    """
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _inputs, _income, _opex = await seed_deal_model_with_financials(
        session, opp, user
    )
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()

    if with_milestones:
        session.add_all(
            [
                # Anchor milestones (no trigger chain) — computed_start()
                # resolves straight from target_date.
                Milestone(
                    opportunity_id=opp.id,
                    milestone_type=MilestoneType.close,
                    target_date=date(2026, 1, 1),
                    duration_days=30,
                    sequence_order=1,
                ),
                Milestone(
                    project_id=project.id,
                    milestone_type=MilestoneType.construction,
                    target_date=date(2026, 3, 1),
                    duration_days=180,
                    sequence_order=2,
                ),
                Milestone(
                    project_id=project.id,
                    milestone_type=MilestoneType.operation_stabilized,
                    target_date=date(2026, 10, 1),
                    duration_days=365,
                    sequence_order=3,
                ),
            ]
        )

    session.add_all(
        [
            UseLine(
                project_id=project.id,
                label="Acquisition",
                phase="acquisition",
                amount=Decimal("1000000"),
                cost_category="acquisition",
                timing_type="first_day",
            ),
            UseLine(
                project_id=project.id,
                label="Hard Costs",
                phase="construction",
                amount=Decimal("500000"),
                cost_category="hard",
                timing_type="first_day",
            ),
        ]
    )

    cm_id = None
    if with_debt_module:
        cm = CapitalModule(
            scenario_id=deal_model.id,
            label="Construction Loan",
            vehicle_type="debt",
            stack_position=1,
            source={"amount": 0, "interest_rate_pct": 0.0, "auto_size": True},
            carry={},
            exit_terms={},
            active_phase_start="acquisition",
            active_phase_end="operation_stabilized",
        )
        session.add(cm)
        await session.flush()
        cm_id = cm.id

    await session.commit()
    return deal_model.id, project.id, user.id, cm_id


# ---------------------------------------------------------------------------
# GET /ui/models/{id}/draw-schedule — panel render
# ---------------------------------------------------------------------------


async def test_panel_renders_and_reconciler_seeds_draw_source(
    client: AsyncClient, session: AsyncSession
) -> None:
    model_id, _project_id, user_id, cm_id = await _seed_draw_deal(session)
    set_client_auth(client, user_id)

    resp = await client.get(f"/ui/models/{model_id}/draw-schedule")
    assert resp.status_code == 200, resp.text
    assert "Construction Loan" in resp.text

    # Loading the panel runs the reconciler, which must have backfilled a
    # DrawSource for the debt CapitalModule (debt auto-sizes: commitment None).
    session.expire_all()
    ds = (
        await session.execute(
            select(DrawSource).where(
                DrawSource.scenario_id == model_id,
                DrawSource.capital_module_id == cm_id,
            )
        )
    ).scalar_one()
    assert ds.source_type == "debt"
    assert ds.total_commitment is None
    assert ds.annual_interest_rate == Decimal("0")


async def test_panel_404_for_unknown_model(
    client: AsyncClient, session: AsyncSession
) -> None:
    _model_id, _project_id, user_id, _cm_id = await _seed_draw_deal(session)
    set_client_auth(client, user_id)

    resp = await client.get(f"/ui/models/{uuid.uuid4()}/draw-schedule")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /ui/models/{id}/draw-schedule/sources — create
# ---------------------------------------------------------------------------


async def test_add_standalone_source_is_reconciled_away(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Current behavior: the POST handler creates a DrawSource with
    ``capital_module_id=NULL``, then reloads the panel ctx whose reconciler
    deletes exactly those rows as orphans — so a standalone "add source"
    never persists. This is the documented orphan-cleanup design
    (test_draw_source_reconciler.py); the route survives only for CM-backed
    flows. If sources are ever meant to exist without a CapitalModule again,
    this test will flag the conflict.
    """
    model_id, _project_id, user_id, _cm_id = await _seed_draw_deal(session)
    set_client_auth(client, user_id)

    resp = await client.post(
        f"/ui/models/{model_id}/draw-schedule/sources",
        data={
            "label": "Mezz Bridge",
            "source_type": "debt",
            "draw_every_n_months": "1",
            "annual_interest_rate": "0.08",
            "active_from_milestone": "close",
            "active_to_milestone": "operation_stabilized",
            "total_commitment": "250,000",
        },
    )
    assert resp.status_code == 200, resp.text

    session.expire_all()
    created = (
        await session.execute(
            select(DrawSource).where(
                DrawSource.scenario_id == model_id,
                DrawSource.label == "Mezz Bridge",
            )
        )
    ).scalar_one_or_none()
    assert created is None, (
        "Standalone DrawSource unexpectedly survived the reconciler — "
        "orphan cleanup behavior changed"
    )


async def test_add_source_404_unknown_model(
    client: AsyncClient, session: AsyncSession
) -> None:
    _model_id, _project_id, user_id, _cm_id = await _seed_draw_deal(session)
    set_client_auth(client, user_id)

    resp = await client.post(
        f"/ui/models/{uuid.uuid4()}/draw-schedule/sources",
        data={
            "label": "X",
            "active_from_milestone": "close",
            "active_to_milestone": "divestment",
        },
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /ui/models/{id}/draw-schedule/sources/{sid} — active window
# ---------------------------------------------------------------------------


async def test_patch_updates_active_window(
    client: AsyncClient, session: AsyncSession
) -> None:
    model_id, _project_id, user_id, cm_id = await _seed_draw_deal(session)
    set_client_auth(client, user_id)

    # First load seeds the CM-backed DrawSource.
    resp = await client.get(f"/ui/models/{model_id}/draw-schedule")
    assert resp.status_code == 200
    session.expire_all()
    ds_id = (
        await session.execute(
            select(DrawSource.id).where(DrawSource.capital_module_id == cm_id)
        )
    ).scalar_one()

    resp = await client.patch(
        f"/ui/models/{model_id}/draw-schedule/sources/{ds_id}",
        data={
            "active_from_milestone": "construction",
            "active_to_milestone": "operation_stabilized",
        },
    )
    assert resp.status_code == 200, resp.text

    session.expire_all()
    ds = (
        await session.execute(select(DrawSource).where(DrawSource.id == ds_id))
    ).scalar_one()
    assert ds.active_from_milestone == "construction"
    assert ds.active_to_milestone == "operation_stabilized"


async def test_patch_foreign_source_id_is_noop(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A source id that doesn't belong to the model is silently ignored
    (handler renders the panel without applying anything)."""
    model_id, _project_id, user_id, cm_id = await _seed_draw_deal(session)
    set_client_auth(client, user_id)
    await client.get(f"/ui/models/{model_id}/draw-schedule")  # seed DS

    resp = await client.patch(
        f"/ui/models/{model_id}/draw-schedule/sources/{uuid.uuid4()}",
        data={
            "active_from_milestone": "construction",
            "active_to_milestone": "divestment",
        },
    )
    assert resp.status_code == 200

    session.expire_all()
    ds = (
        await session.execute(
            select(DrawSource).where(DrawSource.capital_module_id == cm_id)
        )
    ).scalar_one()
    # Original reconciler-seeded window untouched.
    assert ds.active_from_milestone == "close"


# ---------------------------------------------------------------------------
# DELETE /ui/models/{id}/draw-schedule/sources/{sid}
# ---------------------------------------------------------------------------


async def test_delete_cm_backed_source_is_reseeded_by_reconciler(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Current behavior: deleting a CM-backed DrawSource removes that row,
    but the panel-ctx reload in the same request re-seeds a fresh DrawSource
    for the still-present CapitalModule (new id, reconciler defaults). Net
    effect: the row cannot be deleted while its CapitalModule exists —
    deleting the capital module is the real removal path.
    """
    model_id, _project_id, user_id, cm_id = await _seed_draw_deal(session)
    set_client_auth(client, user_id)
    await client.get(f"/ui/models/{model_id}/draw-schedule")  # seed DS

    session.expire_all()
    old_id = (
        await session.execute(
            select(DrawSource.id).where(DrawSource.capital_module_id == cm_id)
        )
    ).scalar_one()

    resp = await client.delete(
        f"/ui/models/{model_id}/draw-schedule/sources/{old_id}"
    )
    assert resp.status_code == 200, resp.text

    session.expire_all()
    rows = list(
        (
            await session.execute(
                select(DrawSource).where(DrawSource.capital_module_id == cm_id)
            )
        ).scalars()
    )
    assert len(rows) == 1, "reconciler must re-seed exactly one DrawSource"
    assert rows[0].id != old_id, "row was re-created, not preserved"


# ---------------------------------------------------------------------------
# POST /ui/models/{id}/draw-schedule/settings — reserve floors
# ---------------------------------------------------------------------------


async def test_settings_persist_reserve_floors(
    client: AsyncClient, session: AsyncSession
) -> None:
    model_id, _project_id, user_id, _cm_id = await _seed_draw_deal(session)
    set_client_auth(client, user_id)

    resp = await client.post(
        f"/ui/models/{model_id}/draw-schedule/settings",
        data={
            "min_reserve_construction": "25,000",
            "min_reserve_operational": "10000",
        },
    )
    assert resp.status_code == 200, resp.text

    session.expire_all()
    model = await session.get(Scenario, model_id)
    assert model.min_reserve_construction == Decimal("25000")
    assert model.min_reserve_operational == Decimal("10000")


async def test_settings_bad_number_falls_back_to_zero(
    client: AsyncClient, session: AsyncSession
) -> None:
    model_id, _project_id, user_id, _cm_id = await _seed_draw_deal(session)
    set_client_auth(client, user_id)

    resp = await client.post(
        f"/ui/models/{model_id}/draw-schedule/settings",
        data={
            "min_reserve_construction": "not-a-number",
            "min_reserve_operational": "",
        },
    )
    assert resp.status_code == 200

    session.expire_all()
    model = await session.get(Scenario, model_id)
    assert model.min_reserve_construction == Decimal("0")
    assert model.min_reserve_operational == Decimal("0")


# ---------------------------------------------------------------------------
# POST /ui/models/{id}/draw-schedule/calculate — engine math + writeback
# ---------------------------------------------------------------------------


async def test_calculate_sizes_zero_rate_debt_to_total_uses(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Real math substance: a single 0%-interest auto-sizing debt source
    covering the full timeline must draw exactly the sum of the use lines
    ($1.5M) — no carry, no reserves. The engine's writeback persists that
    total onto DrawSource.total_commitment AND folds it back into
    CapitalModule.source["amount"].
    """
    model_id, project_id, user_id, cm_id = await _seed_draw_deal(session)
    set_client_auth(client, user_id)

    resp = await client.post(f"/ui/models/{model_id}/draw-schedule/calculate")
    assert resp.status_code == 200, resp.text
    assert "Engine error" not in resp.text
    assert "No timeline yet" not in resp.text
    assert "No sources defined" not in resp.text

    session.expire_all()
    total_uses = sum(
        ul.amount
        for ul in (
            await session.execute(
                select(UseLine).where(UseLine.project_id == project_id)
            )
        ).scalars()
    )
    assert total_uses == Decimal("1500000")

    ds = (
        await session.execute(
            select(DrawSource).where(DrawSource.capital_module_id == cm_id)
        )
    ).scalar_one()
    assert ds.total_commitment == total_uses, (
        f"0%-rate auto-sized debt must draw exactly total uses; "
        f"got {ds.total_commitment} vs {total_uses}"
    )

    cm = await session.get(CapitalModule, cm_id)
    assert Decimal(str(cm.source["amount"])) == total_uses


async def test_calculate_without_milestones_returns_empty_state(
    client: AsyncClient, session: AsyncSession
) -> None:
    model_id, _project_id, user_id, _cm_id = await _seed_draw_deal(
        session, with_milestones=False
    )
    set_client_auth(client, user_id)

    resp = await client.post(f"/ui/models/{model_id}/draw-schedule/calculate")
    assert resp.status_code == 200
    assert "No timeline yet" in resp.text


async def test_calculate_without_sources_returns_empty_state(
    client: AsyncClient, session: AsyncSession
) -> None:
    model_id, _project_id, user_id, _cm_id = await _seed_draw_deal(
        session, with_debt_module=False
    )
    set_client_auth(client, user_id)

    resp = await client.post(f"/ui/models/{model_id}/draw-schedule/calculate")
    assert resp.status_code == 200
    assert "No sources defined" in resp.text


async def test_calculate_404_unknown_model(
    client: AsyncClient, session: AsyncSession
) -> None:
    _model_id, _project_id, user_id, _cm_id = await _seed_draw_deal(session)
    set_client_auth(client, user_id)

    resp = await client.post(f"/ui/models/{uuid.uuid4()}/draw-schedule/calculate")
    assert resp.status_code == 404
