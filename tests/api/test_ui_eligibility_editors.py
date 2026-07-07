"""UI eligibility editors + per-module dscr_min (Slice 7 cross-surface sync).

Covers the three writeback paths wired up by the eligibility-editor UI work:

1. ``dscr_min`` form field on the debt Source drawer → ``source.dscr_min``
   JSONB key AND the ``OperationalInputs.debt_terms.permanent_debt.dscr_min``
   wizard-staging mirror (previously dead — no form input ever posted it).
2. ``eligible_use_tags`` checkbox group (sentinel-guarded) on the Source
   drawer → ``capital_modules.eligible_use_tags`` column.
3. ``eligible_module_ids`` checkbox group (sentinel-guarded) on the Use-line
   drawer → ``use_lines.eligible_module_ids`` column, plus the regression
   guard: saving a debt Source must NOT strip a use-side whitelist (the
   bidirectional grant sync only applies to fixed-amount vehicle types).

Also covers the Source Vehicle settings form persisting
``source_vehicles.eligible_use_tags`` (create + sentinel-guarded update).
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule
from app.models.deal import OperationalInputs, UseLine
from app.models.project import Project

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _auth(client: AsyncClient, user_id) -> None:
    from tests.conftest import set_client_auth
    set_client_auth(client, user_id)
    # Drawer/wizard forms are HTMX posts in production. Also required here:
    # the onboarding_guard middleware (app/api/main.py) opens its own
    # AsyncSessionLocal (prod engine, not the test override) for non-HTMX
    # requests with a session cookie.
    client.headers["hx-request"] = "true"


async def _seed_scenario(session: AsyncSession):
    from tests.conftest import (
        seed_org, seed_opportunity, seed_deal_model_with_financials,
    )
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, inputs, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()
    return user, deal_model, project, inputs


def _debt_module(scenario_id, label="Perm Loan", **kw):
    return CapitalModule(
        id=uuid4(),
        scenario_id=scenario_id,
        label=label,
        vehicle_type="debt",
        stack_position=kw.pop("stack_position", 1),
        source=kw.pop("source", {"interest_rate_pct": 6.5}),
        carry=kw.pop("carry", {}),
        exit_terms=kw.pop("exit_terms", {}),
        **kw,
    )


def _debt_put_payload(**overrides) -> dict:
    base = {
        "label": "Perm Loan",
        "vehicle_type": "debt",
        "source_interest_rate": "6.5",
        "hold_term_years": "10",
        "amort_term_years": "30",
        "stack_position": "1",
        "compounding_period": "monthly",
        "exit_type": "full_payoff",
        "exit_vehicle": "maturity",
        "construction_carry_type": "none",
        "construction_payment_frequency": "monthly",
        "operation_carry_type": "pi",
        "operation_payment_frequency": "monthly",
        "ds_active_from_milestone": "",
        "ds_active_from_offset_days": "0",
        "ds_draw_every_n_months": "1",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. dscr_min — form field lands in source AND fires the debt_terms mirror
# ---------------------------------------------------------------------------


async def test_dscr_min_persists_to_source_and_debt_terms_mirror(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, deal_model, project, inputs = await _seed_scenario(session)
    module = _debt_module(deal_model.id)
    session.add(module)
    await session.commit()
    module_id, inputs_id = module.id, inputs.id

    await _auth(client, user.id)
    resp = await client.put(
        f"/ui/forms/{deal_model.id}/capital-modules/{module_id}",
        data=_debt_put_payload(dscr_min="1.30"),
    )
    assert resp.status_code in (200, 204), resp.text

    session.expire_all()
    row = await session.get(CapitalModule, module_id)
    assert row is not None
    assert row.source.get("dscr_min") == pytest.approx(1.30)

    # Wizard-staging mirror on OperationalInputs.debt_terms
    oi = await session.get(OperationalInputs, inputs_id)
    assert oi is not None
    perm = (oi.debt_terms or {}).get("permanent_debt") or {}
    assert perm.get("dscr_min") == pytest.approx(1.30), (
        "dscr_min mirror to debt_terms.permanent_debt must fire when the "
        "form posts dscr_min — this writeback was previously dead."
    )


async def test_dscr_min_blank_leaves_source_untouched(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, deal_model, _, _ = await _seed_scenario(session)
    module = _debt_module(deal_model.id)
    session.add(module)
    await session.commit()
    module_id = module.id

    await _auth(client, user.id)
    resp = await client.put(
        f"/ui/forms/{deal_model.id}/capital-modules/{module_id}",
        data=_debt_put_payload(),  # no dscr_min field
    )
    assert resp.status_code in (200, 204), resp.text

    session.expire_all()
    row = await session.get(CapitalModule, module_id)
    assert row is not None
    assert "dscr_min" not in (row.source or {})


# ---------------------------------------------------------------------------
# 2. eligible_use_tags — sentinel-guarded checkbox group on the Source drawer
# ---------------------------------------------------------------------------


async def test_eligible_use_tags_persist_on_module(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, deal_model, _, _ = await _seed_scenario(session)
    module = _debt_module(deal_model.id)
    session.add(module)
    await session.commit()
    module_id = module.id

    await _auth(client, user.id)
    resp = await client.put(
        f"/ui/forms/{deal_model.id}/capital-modules/{module_id}",
        data={
            **_debt_put_payload(),
            "eligible_use_tags_section": "1",
            "eligible_use_tags": ["hard", "soft"],
        },
    )
    assert resp.status_code in (200, 204), resp.text

    session.expire_all()
    row = await session.get(CapitalModule, module_id)
    assert row is not None
    assert sorted(row.eligible_use_tags or []) == ["hard", "soft"]


async def test_eligible_use_tags_cleared_when_all_unchecked(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, deal_model, _, _ = await _seed_scenario(session)
    module = _debt_module(deal_model.id, eligible_use_tags=["hard"])
    session.add(module)
    await session.commit()
    module_id = module.id

    await _auth(client, user.id)
    resp = await client.put(
        f"/ui/forms/{deal_model.id}/capital-modules/{module_id}",
        data=_debt_put_payload(eligible_use_tags_section="1"),
    )
    assert resp.status_code in (200, 204), resp.text

    session.expire_all()
    row = await session.get(CapitalModule, module_id)
    assert row is not None
    assert list(row.eligible_use_tags or []) == []


async def test_eligible_use_tags_untouched_without_sentinel(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, deal_model, _, _ = await _seed_scenario(session)
    module = _debt_module(deal_model.id, eligible_use_tags=["hard"])
    session.add(module)
    await session.commit()
    module_id = module.id

    await _auth(client, user.id)
    resp = await client.put(
        f"/ui/forms/{deal_model.id}/capital-modules/{module_id}",
        data=_debt_put_payload(),  # no sentinel → legacy form; tags preserved
    )
    assert resp.status_code in (200, 204), resp.text

    session.expire_all()
    row = await session.get(CapitalModule, module_id)
    assert row is not None
    assert list(row.eligible_use_tags or []) == ["hard"]


# ---------------------------------------------------------------------------
# 3. eligible_module_ids — use-line picker + debt-save regression guard
# ---------------------------------------------------------------------------


def _use_line(project_id, **kw):
    return UseLine(
        id=uuid4(),
        project_id=project_id,
        label=kw.pop("label", "Site Work"),
        phase=kw.pop("phase", "construction"),
        amount=kw.pop("amount", Decimal("180000")),
        cost_category=kw.pop("cost_category", "hard"),
        timing_type="first_day",
        **kw,
    )


def _use_line_put_payload(**overrides) -> dict:
    base = {
        "label": "Site Work",
        "amount": "180000",
        "cost_category": "hard",
        "timing_type": "first_day",
        "is_deferred": "false",
        "milestone_key": "",
        "milestone_key_to": "",
    }
    base.update(overrides)
    return base


async def test_use_line_eligible_module_ids_persist(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, deal_model, project, _ = await _seed_scenario(session)
    module = _debt_module(deal_model.id)
    use = _use_line(project.id)
    session.add_all([module, use])
    await session.commit()
    module_id, use_id = module.id, use.id

    await _auth(client, user.id)
    resp = await client.put(
        f"/ui/forms/{deal_model.id}/use-lines/{use_id}",
        data={
            **_use_line_put_payload(),
            "eligible_module_ids_section": "1",
            "eligible_module_ids": [str(module_id)],
        },
    )
    assert resp.status_code in (200, 204), resp.text

    session.expire_all()
    row = await session.get(UseLine, use_id)
    assert row is not None
    assert [str(x) for x in (row.eligible_module_ids or [])] == [str(module_id)]


async def test_use_line_eligible_module_ids_cleared_when_unchecked(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, deal_model, project, _ = await _seed_scenario(session)
    module = _debt_module(deal_model.id)
    session.add(module)
    await session.flush()
    use = _use_line(project.id, eligible_module_ids=[module.id])
    session.add(use)
    await session.commit()
    use_id = use.id

    await _auth(client, user.id)
    resp = await client.put(
        f"/ui/forms/{deal_model.id}/use-lines/{use_id}",
        data=_use_line_put_payload(eligible_module_ids_section="1"),
    )
    assert resp.status_code in (200, 204), resp.text

    session.expire_all()
    row = await session.get(UseLine, use_id)
    assert row is not None
    assert list(row.eligible_module_ids or []) == []


async def test_use_line_eligible_module_ids_untouched_without_sentinel(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, deal_model, project, _ = await _seed_scenario(session)
    module = _debt_module(deal_model.id)
    session.add(module)
    await session.flush()
    use = _use_line(project.id, eligible_module_ids=[module.id])
    session.add(use)
    await session.commit()
    module_id, use_id = module.id, use.id

    await _auth(client, user.id)
    resp = await client.put(
        f"/ui/forms/{deal_model.id}/use-lines/{use_id}",
        data=_use_line_put_payload(),  # no sentinel → whitelist preserved
    )
    assert resp.status_code in (200, 204), resp.text

    session.expire_all()
    row = await session.get(UseLine, use_id)
    assert row is not None
    assert [str(x) for x in (row.eligible_module_ids or [])] == [str(module_id)]


async def test_use_line_eligible_module_ids_filters_foreign_ids(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Hand-crafted POST with a module UUID from another scenario is dropped."""
    user, deal_model, project, _ = await _seed_scenario(session)
    module = _debt_module(deal_model.id)
    use = _use_line(project.id)
    session.add_all([module, use])
    await session.commit()
    module_id, use_id = module.id, use.id

    await _auth(client, user.id)
    resp = await client.put(
        f"/ui/forms/{deal_model.id}/use-lines/{use_id}",
        data={
            **_use_line_put_payload(),
            "eligible_module_ids_section": "1",
            # second entry is foreign / unknown — must be dropped
            "eligible_module_ids": [str(module_id), str(uuid4())],
        },
    )
    assert resp.status_code in (200, 204), resp.text

    session.expire_all()
    row = await session.get(UseLine, use_id)
    assert row is not None
    assert [str(x) for x in (row.eligible_module_ids or [])] == [str(module_id)]


async def test_debt_module_save_preserves_use_side_whitelist(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Regression: the grant bidirectional sync must not run for debt saves.

    Before the guard, any debt-module save posted no ``eligible_use_ids``
    and the removal pass silently stripped that module from every Use's
    ``eligible_module_ids`` — clobbering whitelists set on the Use form.
    """
    user, deal_model, project, _ = await _seed_scenario(session)
    module = _debt_module(deal_model.id)
    session.add(module)
    await session.flush()
    use = _use_line(project.id, eligible_module_ids=[module.id])
    session.add(use)
    await session.commit()
    module_id, use_id = module.id, use.id

    await _auth(client, user.id)
    resp = await client.put(
        f"/ui/forms/{deal_model.id}/capital-modules/{module_id}",
        data=_debt_put_payload(),  # debt form: no eligible_use_ids checklist
    )
    assert resp.status_code in (200, 204), resp.text

    session.expire_all()
    row = await session.get(UseLine, use_id)
    assert row is not None
    assert [str(x) for x in (row.eligible_module_ids or [])] == [str(module_id)], (
        "Saving a debt Source must not strip it from use-side whitelists."
    )


async def test_grant_sync_still_removes_unticked_uses(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The fixed-amount sync path is unchanged: unticking clears the backref."""
    user, deal_model, project, _ = await _seed_scenario(session)
    grant = CapitalModule(
        id=uuid4(),
        scenario_id=deal_model.id,
        label="OR-MEP",
        vehicle_type="grant",
        stack_position=3,
        source={"maximum": 250000.0},
        carry={},
        exit_terms={},
    )
    session.add(grant)
    await session.flush()
    use = _use_line(project.id, eligible_module_ids=[grant.id])
    session.add(use)
    await session.commit()
    grant_id, use_id = grant.id, use.id

    await _auth(client, user.id)
    resp = await client.put(
        f"/ui/forms/{deal_model.id}/capital-modules/{grant_id}",
        data={
            "label": "OR-MEP",
            "vehicle_type": "grant",
            "source_amount": "100000",
            "stack_position": "3",
            "ds_active_from_milestone": "",
            "ds_active_from_offset_days": "0",
            "ds_draw_every_n_months": "1",
        },
    )
    assert resp.status_code in (200, 204), resp.text

    session.expire_all()
    row = await session.get(UseLine, use_id)
    assert row is not None
    assert list(row.eligible_module_ids or []) == []


# ---------------------------------------------------------------------------
# 4. Form rendering — new controls actually appear in the drawer HTML
# ---------------------------------------------------------------------------


async def test_debt_edit_form_renders_dscr_min_and_tag_editor(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, deal_model, _, _ = await _seed_scenario(session)
    module = _debt_module(deal_model.id, source={"interest_rate_pct": 6.5, "dscr_min": 1.4})
    session.add(module)
    await session.commit()

    await _auth(client, user.id)
    resp = await client.get(
        f"/ui/models/{deal_model.id}/line-form",
        params={"type": "capital_modules", "id": str(module.id)},
    )
    assert resp.status_code == 200
    html = resp.text
    assert 'name="dscr_min"' in html
    assert "1.4" in html  # saved value round-trips into the input
    assert 'name="eligible_use_tags_section"' in html
    assert 'name="eligible_use_tags"' in html


async def test_use_line_edit_form_renders_source_whitelist_picker(
    client: AsyncClient, session: AsyncSession
) -> None:
    user, deal_model, project, _ = await _seed_scenario(session)
    module = _debt_module(deal_model.id, label="Senior Loan")
    session.add(module)
    await session.flush()
    use = _use_line(project.id, eligible_module_ids=[module.id])
    session.add(use)
    await session.commit()

    await _auth(client, user.id)
    resp = await client.get(
        f"/ui/models/{deal_model.id}/line-form",
        params={"type": "use_lines", "id": str(use.id)},
    )
    assert resp.status_code == 200
    html = resp.text
    assert 'name="eligible_module_ids_section"' in html
    assert f'value="{module.id}"' in html
    assert "Senior Loan" in html
    # Saved whitelist pre-ticks the checkbox
    assert "checked" in html


# ---------------------------------------------------------------------------
# 5. Source Vehicle settings — eligible_use_tags parse/persist
# ---------------------------------------------------------------------------


async def _seed_user(session: AsyncSession):
    from tests.conftest import seed_org
    org, user = await seed_org(session)
    await session.commit()
    return org, user


async def test_vehicle_create_persists_eligible_use_tags(
    client: AsyncClient, session: AsyncSession
) -> None:
    from app.models.source_vehicle import SourceVehicle

    org, user = await _seed_user(session)
    await _auth(client, user.id)
    resp = await client.post(
        "/settings/vehicles",
        data={
            "scope": "org",
            "label": "Tagged Construction Loan",
            "vehicle_type": "debt",
            "eligible_use_tags_section": "1",
            "eligible_use_tags": ["hard"],
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 303), resp.text

    session.expire_all()
    vehicle = (
        await session.execute(
            select(SourceVehicle).where(SourceVehicle.label == "Tagged Construction Loan")
        )
    ).scalar_one()
    assert list(vehicle.eligible_use_tags or []) == ["hard"]


async def test_vehicle_create_drops_unknown_tags(
    client: AsyncClient, session: AsyncSession
) -> None:
    from app.models.source_vehicle import SourceVehicle

    org, user = await _seed_user(session)
    await _auth(client, user.id)
    resp = await client.post(
        "/settings/vehicles",
        data={
            "scope": "org",
            "label": "Bogus Tag Vehicle",
            "vehicle_type": "debt",
            "eligible_use_tags_section": "1",
            "eligible_use_tags": ["hard", "not_a_category"],
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 303), resp.text

    session.expire_all()
    vehicle = (
        await session.execute(
            select(SourceVehicle).where(SourceVehicle.label == "Bogus Tag Vehicle")
        )
    ).scalar_one()
    assert list(vehicle.eligible_use_tags or []) == ["hard"]


async def test_vehicle_update_rewrites_and_clears_tags(
    client: AsyncClient, session: AsyncSession
) -> None:
    from app.models.source_vehicle import SourceVehicle

    org, user = await _seed_user(session)
    vehicle = SourceVehicle(
        scope="org",
        owner_id=org.id,
        label="Retag Me",
        vehicle_type="debt",
        eligible_use_tags=["hard"],
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(vehicle)
    await session.commit()
    vehicle_id = vehicle.id

    await _auth(client, user.id)
    # Rewrite hard → soft
    resp = await client.post(
        f"/settings/vehicles/{vehicle_id}",
        data={
            "label": "Retag Me",
            "vehicle_type": "debt",
            "eligible_use_tags_section": "1",
            "eligible_use_tags": ["soft"],
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 303), resp.text
    session.expire_all()
    row = await session.get(SourceVehicle, vehicle_id)
    assert list(row.eligible_use_tags or []) == ["soft"]

    # All unchecked (sentinel still present) → cleared to permissive
    resp = await client.post(
        f"/settings/vehicles/{vehicle_id}",
        data={
            "label": "Retag Me",
            "vehicle_type": "debt",
            "eligible_use_tags_section": "1",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 303), resp.text
    session.expire_all()
    row = await session.get(SourceVehicle, vehicle_id)
    assert list(row.eligible_use_tags or []) == []


async def test_vehicle_update_without_sentinel_preserves_tags(
    client: AsyncClient, session: AsyncSession
) -> None:
    from app.models.source_vehicle import SourceVehicle

    org, user = await _seed_user(session)
    vehicle = SourceVehicle(
        scope="org",
        owner_id=org.id,
        label="Sticky Tags",
        vehicle_type="debt",
        eligible_use_tags=["acquisition"],
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(vehicle)
    await session.commit()
    vehicle_id = vehicle.id

    await _auth(client, user.id)
    resp = await client.post(
        f"/settings/vehicles/{vehicle_id}",
        data={"label": "Sticky Tags", "vehicle_type": "debt"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 303), resp.text
    session.expire_all()
    row = await session.get(SourceVehicle, vehicle_id)
    assert list(row.eligible_use_tags or []) == ["acquisition"]


async def test_vehicle_edit_form_renders_tag_editor(
    client: AsyncClient, session: AsyncSession
) -> None:
    from app.models.source_vehicle import SourceVehicle

    org, user = await _seed_user(session)
    vehicle = SourceVehicle(
        scope="org",
        owner_id=org.id,
        label="Render Check",
        vehicle_type="debt",
        eligible_use_tags=["hard"],
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(vehicle)
    await session.commit()

    await _auth(client, user.id)
    resp = await client.get(f"/settings/vehicles/{vehicle.id}/form")
    assert resp.status_code == 200
    html = resp.text
    assert 'name="eligible_use_tags_section"' in html
    assert 'name="eligible_use_tags"' in html
    assert 'value="hard"' in html
