"""Regression tests for the cross-surface sync audit hot-bug batch.

Covers four bugs that let the API/UI surfaces drift from the canonical
model vocabularies:

1. ``PUT /api/models/{id}/income-streams/{stream_id}`` was accidentally
   wired to the ``_assert_not_phantom_row`` helper instead of
   ``update_income_stream`` (decorator stacked on the wrong function).
2. The bulk-import Excel template offered ``pre_development`` — not a
   valid ``UseLinePhase`` value — in its Phase dropdown.
3. The shared vehicle form partial omitted the ``float_earnings``
   vehicle type present in the canonical ``VehicleType`` enum.
4. Source-vehicle 400 error strings listed only 4 of the 6 canonical
   vehicle types.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import VehicleType
from app.models.deal import UseLinePhase

pytestmark = pytest.mark.asyncio

_REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Bug 1 — income-stream PUT
# ---------------------------------------------------------------------------


async def test_put_income_stream_updates_row(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """PUT must reach update_income_stream and mutate the row (was wired to
    the phantom-row helper, which ignored the path params entirely)."""
    from tests.conftest import seed_org, seed_deal_model_with_financials, seed_opportunity

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, income, _ = await seed_deal_model_with_financials(session, opp, user)
    await session.commit()

    resp = await client.put(
        f"/api/models/{deal_model.id}/income-streams/{income.id}",
        json={"label": "Renamed via PUT"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["label"] == "Renamed via PUT"

    await session.refresh(income)
    assert income.label == "Renamed via PUT"


async def test_openapi_has_no_helper_endpoint() -> None:
    """The phantom-row helper must not be registered as a route, and the
    income-stream path must expose both PUT and PATCH like its siblings."""
    from app.api.main import create_app

    spec = create_app().openapi()

    for path, ops in spec["paths"].items():
        for op in ops.values():
            if isinstance(op, dict):
                assert "_assert_not_phantom_row" not in op.get("operationId", ""), path

    stream_path = "/api/models/{model_id}/income-streams/{stream_id}"
    assert "put" in spec["paths"][stream_path]
    assert "patch" in spec["paths"][stream_path]


async def test_put_income_stream_still_rejects_phantom(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """The phantom-row guard must apply to PUT exactly as it does to PATCH."""
    from decimal import Decimal
    from uuid import uuid4

    from sqlalchemy import select

    from app.models.deal import IncomeStream
    from app.models.project import Project
    from app.schemas.gap_adjustment_names import REVENUE_ADJUSTMENT_LABEL
    from tests.conftest import seed_org, seed_deal_model_with_financials, seed_opportunity

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (
        await session.execute(select(Project).where(Project.scenario_id == deal_model.id))
    ).scalars().first()
    phantom = IncomeStream(
        id=uuid4(),
        project_id=project.id,
        stream_type="residential_rent",
        label=REVENUE_ADJUSTMENT_LABEL,
        amount_fixed_monthly=Decimal("1000"),
        active_in_phases=["stabilized", "exit"],
    )
    session.add(phantom)
    await session.commit()

    resp = await client.put(
        f"/api/models/{deal_model.id}/income-streams/{phantom.id}",
        json={"label": "should not apply"},
    )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Bug 2 — import template phase dropdown
# ---------------------------------------------------------------------------


async def test_import_template_phase_dropdown_matches_enum(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Every phase offered by the template's dropdown must be a valid
    UseLinePhase value (the template used to offer ``pre_development``)."""
    import openpyxl

    from tests.conftest import seed_org, seed_deal_model_with_financials, seed_opportunity

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    await session.commit()

    resp = await client.get(
        f"/ui/models/{deal_model.id}/import-template.xlsx",
        headers={**auth_headers, "hx-request": "true"},
    )
    assert resp.status_code == 200, resp.text

    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    ws = wb["Uses"]
    phase_formulas = [
        dv.formula1 for dv in ws.data_validations.dataValidation
        if dv.sqref and str(dv.sqref).startswith("B")
    ]
    assert phase_formulas, "Phase DataValidation missing from Uses sheet"
    offered = set(phase_formulas[0].strip('"').split(","))
    canonical = {p.value for p in UseLinePhase}
    assert offered == canonical, f"template offers {offered - canonical} beyond enum"


# ---------------------------------------------------------------------------
# Bug 3 — vehicle form template vehicle types
# ---------------------------------------------------------------------------


async def test_vehicle_form_offers_all_vehicle_types() -> None:
    """The shared vehicle form partial must offer every canonical
    VehicleType (it omitted float_earnings)."""
    html = (_REPO_ROOT / "app" / "templates" / "partials" / "vehicle_form.html").read_text(
        encoding="utf-8"
    )
    select_block = html.split('name="vehicle_type"', 1)[1].split("</select>", 1)[0]
    offered = set(re.findall(r'<option value="([a-z_]+)"', select_block))
    canonical = {v.value for v in VehicleType}
    assert offered == canonical, (
        f"vehicle_form.html missing {canonical - offered}, extra {offered - canonical}"
    )


# ---------------------------------------------------------------------------
# Bug 4 — source-vehicle 400 detail
# ---------------------------------------------------------------------------


async def test_vehicle_type_error_names_all_canonical_types(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """400 detail for a missing vehicle_type must enumerate all six
    canonical types (it listed only four)."""
    from tests.conftest import seed_org

    org, user = await seed_org(session)
    user.is_org_admin = True
    session.add(user)
    await session.commit()
    client.headers["X-User-ID"] = str(user.id)

    resp = await client.post(
        "/api/settings/source-vehicles/org",
        json={"name": "No Type"},
    )
    assert resp.status_code == 400
    for vt in VehicleType:
        assert vt.value in resp.text, f"{vt.value} missing from error body: {resp.text}"


# ---------------------------------------------------------------------------
# Slice 2 — opportunity source default + email-ingest debug-log gate
# ---------------------------------------------------------------------------


async def test_create_project_defaults_source_manual(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """API-created opportunities must carry the same 'manual' origin label as
    the UI HTMX and email-ingest creation paths."""
    from app.models.opportunity import Opportunity
    from tests.conftest import seed_org

    org, user = await seed_org(session)
    await session.commit()

    resp = await client.post(
        "/api/projects",
        json={"name": "Source Default Check", "org_id": str(org.id)},
    )
    assert resp.status_code == 201, resp.text

    opp = await session.get(Opportunity, resp.json()["id"])
    assert opp.source == "manual"


async def test_email_debug_log_gate(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Debug-log route must 404 when EMAIL_INGEST_DEBUG_EMAIL is unset, and
    open only for the configured operator email."""
    import uuid as _uuid

    from app.config import settings as app_settings
    from app.models.email_ingest import InboundEmail, InboundEmailStatus
    from tests.conftest import seed_org

    org, user = await seed_org(session)
    user.email = "operator@example.com"
    session.add(user)
    email_row = InboundEmail(
        id=_uuid.uuid4(),
        org_id=org.id,
        sender_email="broker@example.com",
        subject="Deal",
        status=InboundEmailStatus.pending.value,
        proforma_task_ids=[],
        attachments_meta=[],
        debug_log="extraction trace",
    )
    session.add(email_row)
    await session.commit()

    url = f"/ui/email-inbox/{email_row.id}/debug-log.txt"
    headers = {"X-User-ID": str(user.id), "hx-request": "true"}

    monkeypatch.setattr(app_settings, "email_ingest_debug_email", "")
    resp = await client.get(url, headers=headers)
    assert resp.status_code == 404, "unset config must disable the route"

    monkeypatch.setattr(app_settings, "email_ingest_debug_email", user.email)
    resp = await client.get(url, headers=headers)
    assert resp.status_code == 200, resp.text
    assert "extraction trace" in resp.text

    monkeypatch.setattr(app_settings, "email_ingest_debug_email", "someone.else@example.com")
    resp = await client.get(url, headers=headers)
    assert resp.status_code == 404
