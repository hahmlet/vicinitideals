"""Integration tests for the V1 follow-up form surfaces:

- CapitalModule edit (`/ui/forms/{model}/capital-modules/{id}`) accepts
  the new `fee_terms_*` fields and persists them to fee_terms JSONB +
  fee_terms_inherited_from_type.
- UseLine edit (`/ui/forms/{model}/use-lines/{id}`) on the auto Dev Fee row
  accepts `dev_fee_acquisition_treatment`, `dev_fee_acquisition_pct`,
  `acquisition_fee_pct`, and `release_milestone_key[] / release_weight_pct[]`.
- Source Vehicle preset ``fee_terms`` persistence (`/settings/vehicles`)
  GET renders + POST creates + POST updates a row.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule
from app.models.deal import UseLine, UseLinePhase
from app.models.project import Project


pytestmark = pytest.mark.asyncio


async def _auth(client: AsyncClient, user_id) -> None:
    from tests.conftest import set_client_auth
    set_client_auth(client, user_id)


# ---------------------------------------------------------------------------
# CapitalModule fee_terms via the form handler
# ---------------------------------------------------------------------------

async def _seed_module(session: AsyncSession) -> tuple[UUID, UUID, UUID, UUID]:
    """Returns (model_id, project_id, capital_module_id)."""
    from tests.conftest import (
        seed_org,
        seed_opportunity,
        seed_deal_model_with_financials,
    )

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()
    mod = CapitalModule(
        id=uuid4(),
        scenario_id=deal_model.id,
        label="Construction Loan",
        vehicle_type="debt",
        stack_position=1,
        source={"amount": 5_000_000},
        carry={},
        exit_terms={},
        active_phase_end="exit",
    )
    session.add(mod)
    await session.commit()
    return deal_model.id, project.id, mod.id, user.id


async def test_capital_module_form_persists_fee_terms_override(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    model_id, project_id, mod_id, user_id = await _seed_module(session)
    await _auth(client, user_id)

    resp = await client.put(
        f"/ui/forms/{model_id}/capital-modules/{mod_id}",
        params={"project": str(project_id)},
        data={
            "label": "Construction Loan",
            "vehicle_type": "debt",
            "source_amount": "5000000",
            "exit_type": "full_payoff",
            "exit_vehicle": "maturity",
            "construction_carry_type": "none",
            "operation_carry_type": "none",
            "stack_position": "1",
            "fee_terms_section": "1",
            "fee_terms_inherited": "off",  # any non-"on" value disables inheritance
            "fee_terms_max_pct": "15",
            "fee_terms_absolute_cap": "1500000",
            "fee_terms_basis_exclusions[]": ["acquisition", "operating_reserves"],
            "fee_terms_notes": "LIHTC 15% cap incl. acq",
        },
    )
    assert resp.status_code == 200, resp.text

    session.expire_all()
    row = await session.get(CapitalModule, mod_id)
    assert row is not None
    assert row.fee_terms_inherited_from_type is False
    ft = row.fee_terms or {}
    assert float(ft["max_pct"]) == 15.0
    assert float(ft["absolute_cap"]) == 1_500_000.0
    assert set(ft["basis_exclusions"]) == {"acquisition", "operating_reserves"}
    assert ft["notes"] == "LIHTC 15% cap incl. acq"


async def test_capital_module_form_preserves_fee_terms_when_section_absent(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    model_id, project_id, mod_id, user_id = await _seed_module(session)
    await _auth(client, user_id)

    # Pre-set a custom fee_terms.
    row = await session.get(CapitalModule, mod_id)
    row.fee_terms = {"max_pct": 12.0, "regulated": True}
    row.fee_terms_inherited_from_type = False
    await session.commit()

    # Form POST with NO fee_terms_section field — must leave fee_terms intact.
    resp = await client.put(
        f"/ui/forms/{model_id}/capital-modules/{mod_id}",
        params={"project": str(project_id)},
        data={
            "label": "Construction Loan",
            "vehicle_type": "debt",
            "source_amount": "5000000",
            "exit_type": "full_payoff",
            "exit_vehicle": "maturity",
            "construction_carry_type": "none",
            "operation_carry_type": "none",
            "stack_position": "1",
        },
    )
    assert resp.status_code == 200, resp.text

    session.expire_all()
    row = await session.get(CapitalModule, mod_id)
    assert row.fee_terms_inherited_from_type is False
    assert float((row.fee_terms or {}).get("max_pct")) == 12.0


# ---------------------------------------------------------------------------
# UseLine auto Dev Fee row: acquisition treatment + release schedule
# ---------------------------------------------------------------------------

async def _seed_auto_dev_fee(session: AsyncSession) -> tuple[UUID, UUID, UUID, UUID]:
    from tests.conftest import (
        seed_org,
        seed_opportunity,
        seed_deal_model_with_financials,
    )

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()
    auto = UseLine(
        id=uuid4(),
        project_id=project.id,
        label="Developer Fee",
        phase=UseLinePhase.construction,
        cost_category="soft",
        amount=Decimal("0"),
        timing_type="spread",
        is_deferred=False,
        is_auto_dev_fee=True,
        dev_fee_pct=Decimal("12.0"),
        dev_fee_basis="tpc_excl_self",
    )
    session.add(auto)
    await session.commit()
    return deal_model.id, project.id, auto.id, user.id


async def test_dev_fee_row_persists_split_rate_treatment(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    model_id, project_id, ul_id, user_id = await _seed_auto_dev_fee(session)
    await _auth(client, user_id)

    resp = await client.put(
        f"/ui/forms/{model_id}/use-lines/{ul_id}",
        data={
            "dev_fee_pct": "12.0",
            "dev_fee_basis": "tpc_excl_self",
            "dev_fee_acquisition_treatment": "split_rate",
            "dev_fee_acquisition_pct": "1.5",
        },
    )
    assert resp.status_code == 200, resp.text

    session.expire_all()
    row = await session.get(UseLine, ul_id)
    assert row.dev_fee_acquisition_treatment == "split_rate"
    assert float(row.dev_fee_acquisition_pct) == 1.5


async def test_dev_fee_row_separate_fee_materializes_acq_row(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    model_id, project_id, ul_id, user_id = await _seed_auto_dev_fee(session)
    await _auth(client, user_id)

    resp = await client.put(
        f"/ui/forms/{model_id}/use-lines/{ul_id}",
        data={
            "dev_fee_pct": "12.0",
            "dev_fee_basis": "tpc_excl_self",
            "dev_fee_acquisition_treatment": "separate_fee",
            "acquisition_fee_pct": "1.0",
        },
    )
    assert resp.status_code == 200, resp.text

    session.expire_all()
    dev_row = await session.get(UseLine, ul_id)
    assert dev_row.dev_fee_acquisition_treatment == "separate_fee"
    acq_row = (await session.execute(
        select(UseLine)
        .join(Project, UseLine.project_id == Project.id)
        .where(
            Project.scenario_id == model_id,
            UseLine.is_auto_acquisition_fee == True,  # noqa: E712
        )
    )).scalars().first()
    assert acq_row is not None
    assert float(acq_row.acquisition_fee_pct) == 1.0


async def test_dev_fee_row_release_schedule_persists(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    model_id, project_id, ul_id, user_id = await _seed_auto_dev_fee(session)
    await _auth(client, user_id)

    resp = await client.put(
        f"/ui/forms/{model_id}/use-lines/{ul_id}",
        data=[
            ("dev_fee_pct", "12.0"),
            ("dev_fee_basis", "tpc_excl_self"),
            ("dev_fee_release_section", "1"),
            ("release_milestone_key[]", "construction"),
            ("release_weight_pct[]", "60"),
            ("release_milestone_key[]", "operation_stabilized"),
            ("release_weight_pct[]", "30"),
            ("final_holdback_pct", "10"),
            ("final_holdback_milestone_key", "operation_stabilized"),
        ],
    )
    assert resp.status_code == 200, resp.text

    session.expire_all()
    row = await session.get(UseLine, ul_id)
    sched = row.dev_fee_release_schedule or {}
    weights = sched.get("weights") or []
    assert len(weights) == 2
    assert {w["milestone_key"] for w in weights} == {"construction", "operation_stabilized"}
    hb = sched.get("final_holdback") or {}
    assert float(hb["pct"]) == 10.0
    assert hb["milestone_key"] == "operation_stabilized"


# ---------------------------------------------------------------------------
# Capital Vehicle Defaults Org settings page
# ---------------------------------------------------------------------------

async def test_vehicle_preset_create_persists_fee_terms(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """Posting Dev Fee Rule fields on the vehicle preset form persists
    them to ``SourceVehicle.fee_terms`` for inheritance by future
    CapitalModules created from this preset."""
    from tests.conftest import seed_org
    from app.models.source_vehicle import SourceVehicle
    org, user = await seed_org(session)
    await session.commit()
    await _auth(client, user.id)

    resp = await client.post(
        "/settings/vehicles",
        data=[
            ("scope", "org"),
            ("label", "LIHTC Bond"),
            ("vehicle_type", "debt"),
            ("equity_role", ""),
            ("default_waterfall_position", "0"),
            ("draw_cadence", "monthly"),
            ("day_count_convention", "actual_360"),
            ("fee_terms_max_pct", "15"),
            ("fee_terms_absolute_cap", "2000000"),
            ("fee_terms_basis_exclusions[]", "acquisition"),
            ("fee_terms_basis_exclusions[]", "operating_reserves"),
            ("fee_terms_regulated", "on"),
            ("fee_terms_notes", "LIHTC bond cap"),
        ],
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text

    rows = (await session.execute(
        select(SourceVehicle).where(SourceVehicle.label == "LIHTC Bond")
    )).scalars().all()
    assert len(rows) == 1
    ft = rows[0].fee_terms or {}
    assert float(ft["max_pct"]) == 15.0
    assert float(ft["absolute_cap"]) == 2000000.0
    assert set(ft["basis_exclusions"]) == {"acquisition", "operating_reserves"}
    assert ft.get("regulated") is True
    assert ft.get("notes") == "LIHTC bond cap"


async def test_vehicle_preset_update_replaces_fee_terms(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """Updating the preset form rewrites ``fee_terms`` from the submitted
    fields. Omitted fields are dropped — empty form = no cap."""
    from tests.conftest import seed_org
    from app.models.source_vehicle import SourceVehicle
    org, user = await seed_org(session)
    vehicle = SourceVehicle(
        scope="org",
        owner_id=user.org_id,
        label="Bridge Loan",
        vehicle_type="debt",
        default_waterfall_position=0,
        draw_cadence="monthly",
        day_count_convention="actual_360",
        fee_terms={"max_pct": 15.0, "notes": "stale"},
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(vehicle)
    await session.commit()
    await _auth(client, user.id)

    resp = await client.post(
        f"/settings/vehicles/{vehicle.id}",
        data=[
            ("label", "Bridge Loan"),
            ("vehicle_type", "debt"),
            ("equity_role", ""),
            ("default_waterfall_position", "0"),
            ("draw_cadence", "monthly"),
            ("day_count_convention", "actual_360"),
            ("fee_terms_max_pct", "12"),
            ("fee_terms_notes", "tightened cap"),
        ],
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text

    session.expire_all()
    refreshed = await session.get(SourceVehicle, vehicle.id)
    ft = refreshed.fee_terms or {}
    assert float(ft["max_pct"]) == 12.0
    assert ft.get("notes") == "tightened cap"
    assert "absolute_cap" not in ft
    assert "regulated" not in ft
