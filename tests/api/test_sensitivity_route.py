"""Integration tests for the sensitivity-analysis UI route
(app/api/routers/ui_model_builder.py::run_sensitivity_analysis).

Route under test:
  - POST /ui/models/{model_id}/sensitivity/run
  - GET  /ui/panel/{model_id}?module=sensitivity  (the partial that renders
    the persisted matrix)

This route runs ``compute_sensitivity_matrix`` (app/engines/sensitivity_matrix.py)
synchronously in-request — it does NOT enqueue Celery work, so the full
contract is testable in-process. The Celery sweep task
(app.tasks.scenario.run_scenario) is a different code path already covered
by tests/tasks/test_scenario.py and is deliberately not duplicated here.

Assertions target DB substance (persisted matrix JSON, restored inputs),
not just status codes.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cashflow import OperationalOutputs
from app.models.deal import OperationalInputs, UseLine
from app.models.project import Project

from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
    set_client_auth,
)

pytestmark = pytest.mark.asyncio


async def _seed(session: AsyncSession, *, rich: bool = True):
    """Org + user + opp + scenario-with-financials, tuned so the engine
    produces real (nonzero) cash flows.

    Returns (user, deal_model, project, inputs) — capture ids from these
    BEFORE issuing requests (session.expire_all() in handlers).
    """
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

    # Seed quirk: the helper leaves active_in_phases=[] which yields zero
    # engine revenue. Activate the stream so NOI is nonzero.
    income.active_in_phases = ["lease_up", "stabilized"]
    # Pin both axis bases so the 5x5 windows are deterministic.
    inputs.noi_escalation_rate_pct = Decimal("3.0")  # exit_cap already 5.5
    session.add_all([income, inputs])

    if rich:
        inputs.purchase_price = Decimal("1000000")
        session.add(
            UseLine(
                project_id=project.id,
                label="Acquisition",
                phase="acquisition",
                amount=Decimal("1000000"),
                cost_category="hard",
                timing_type="first_day",
            )
        )
    await session.commit()
    return user, deal_model, project, inputs


async def _persisted_matrices(session: AsyncSession, model_id) -> list:
    """All non-null sensitivity_matrix payloads persisted for a scenario."""
    session.expire_all()
    rows = (
        await session.execute(
            select(OperationalOutputs).where(
                OperationalOutputs.scenario_id == model_id
            )
        )
    ).scalars().all()
    return [r.sensitivity_matrix for r in rows if r.sensitivity_matrix is not None]


# ---------------------------------------------------------------------------
# Happy path — full contract: 25-cell compute, persistence, input restore
# ---------------------------------------------------------------------------


async def test_run_sensitivity_persists_5x5_matrix_and_restores_inputs(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, deal_model, _project, inputs = await _seed(session)
    model_id, inputs_id = deal_model.id, inputs.id
    set_client_auth(client, user.id)

    resp = await client.post(
        f"/ui/models/{model_id}/sensitivity/run",
        data={
            "axis_x": "noi_escalation_rate_pct",
            "axis_y": "exit_cap_rate_pct",
            "metric": "noi_stabilized",
        },
    )
    assert resp.status_code == 200, resp.text
    assert "Sensitivity Analysis" in resp.text

    matrices = await _persisted_matrices(session, model_id)
    assert len(matrices) == 1, "matrix must be persisted on OperationalOutputs"
    sm = matrices[0]

    assert sm["axis_x"]["field"] == "noi_escalation_rate_pct"
    assert sm["axis_y"]["field"] == "exit_cap_rate_pct"
    assert sm["metric"]["field"] == "noi_stabilized"
    assert sm["metric"]["format"] == "currency"

    # 0.25-step windows centered on the base inputs (3.0% / 5.5%)
    assert sm["axis_x"]["values"] == [2.5, 2.75, 3.0, 3.25, 3.5]
    assert sm["axis_y"]["values"] == [5.0, 5.25, 5.5, 5.75, 6.0]
    assert sm["base_x_index"] == 2
    assert sm["base_y_index"] == 2

    grid = sm["values"]
    assert len(grid) == 5 and all(len(row) == 5 for row in grid)
    for row in grid:
        for cell in row:
            assert isinstance(cell, float), f"engine failed for a cell: {grid}"
            assert cell > 0

    # Money math: stabilized NOI cannot depend on the exit cap rate — exit
    # cap only prices the sale. Every column must be constant down the Y axis.
    for xi in range(5):
        col = [grid[yi][xi] for yi in range(5)]
        assert col == pytest.approx([col[0]] * 5), (
            f"NOI varied with exit cap at x={xi}: {col}"
        )
    # Ceiling sanity: gross potential revenue is 8 units x $1,450 x 12
    # = $139,200/yr; NOI (post-opex) must sit strictly below it.
    assert grid[2][2] < 139_200

    # Restore contract: the run mutates OperationalInputs 25 times but must
    # put the base values back and leave them persisted.
    session.expire_all()
    fresh = await session.get(OperationalInputs, inputs_id)
    assert Decimal(str(fresh.exit_cap_rate_pct)) == Decimal("5.5")
    assert Decimal(str(fresh.noi_escalation_rate_pct)) == Decimal("3.0")

    # The GET partial renders the persisted matrix (axis ticks + base marker).
    panel = await client.get(
        f"/ui/panel/{model_id}", params={"module": "sensitivity"}
    )
    assert panel.status_code == 200, panel.text
    assert "5.00%" in panel.text  # first Y-axis tick, pct-formatted
    assert "base" in panel.text  # base-case cell marker


# ---------------------------------------------------------------------------
# Rejection paths — bad axis/metric combos must not persist anything
# ---------------------------------------------------------------------------


async def test_run_sensitivity_identical_axes_rejected_without_persisting(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, deal_model, _project, _inputs = await _seed(session, rich=False)
    model_id = deal_model.id
    set_client_auth(client, user.id)

    resp = await client.post(
        f"/ui/models/{model_id}/sensitivity/run",
        data={
            "axis_x": "exit_cap_rate_pct",
            "axis_y": "exit_cap_rate_pct",
            "metric": "noi_stabilized",
        },
    )
    assert resp.status_code == 200, resp.text
    assert await _persisted_matrices(session, model_id) == []

    # KNOWN GAP (asserting current behavior, not endorsing it): the handler
    # passes extra_ctx={"sensitivity_error": str(e)} but NO template renders
    # a `sensitivity_error` variable (grep app/templates/ — zero hits), so
    # the engine's "axis_x and axis_y must differ" message is silently
    # swallowed and the user just sees an unchanged panel. If a fix wires
    # the error into the panel, flip this assertion.
    assert "must differ" not in resp.text


async def test_run_sensitivity_unknown_metric_rejected_without_persisting(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, deal_model, _project, _inputs = await _seed(session, rich=False)
    model_id = deal_model.id
    set_client_auth(client, user.id)

    resp = await client.post(
        f"/ui/models/{model_id}/sensitivity/run",
        data={
            "axis_x": "noi_escalation_rate_pct",
            "axis_y": "exit_cap_rate_pct",
            "metric": "not_a_metric",
        },
    )
    assert resp.status_code == 200, resp.text
    assert await _persisted_matrices(session, model_id) == []


async def test_run_sensitivity_ui_offered_hold_period_axis_is_unsupported(
    client: AsyncClient, session: AsyncSession
) -> None:
    """KNOWN MISMATCH (asserting current behavior): the Sensitivity panel
    <select> offers value="hold_period_years" for both axes
    (app/templates/partials/model_builder_panel.html ~line 2203/2213) but
    AXIS_SPECS in app/engines/sensitivity_matrix.py has no such axis — the
    engine raises "Unknown axis", the handler swallows it (see the
    sensitivity_error gap above), and the user gets a silent no-op. Any
    user picking "Hold Period (yrs)" in production hits this today.
    """
    user, deal_model, _project, _inputs = await _seed(session, rich=False)
    model_id = deal_model.id
    set_client_auth(client, user.id)

    resp = await client.post(
        f"/ui/models/{model_id}/sensitivity/run",
        data={
            "axis_x": "noi_escalation_rate_pct",
            "axis_y": "hold_period_years",
            "metric": "noi_stabilized",
        },
    )
    assert resp.status_code == 200, resp.text
    assert await _persisted_matrices(session, model_id) == []


async def test_run_sensitivity_unknown_model_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)
    resp = await client.post(
        f"/ui/models/{uuid.uuid4()}/sensitivity/run",
        data={"metric": "noi_stabilized"},
    )
    assert resp.status_code == 404
