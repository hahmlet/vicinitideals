"""Bug: a unit type added by hand on the pro forma review page was never saved.

proforma-confirm keeps only unit rows whose index is listed in
``unit_type_include[]`` as soon as any row sends one. Every extracted row
carries a checked include box, but the "+ Add unit type" row (addUnitRow()
in the review template) had an empty first cell -- no include box -- so
whenever the parser found at least one unit type, a hand-added unit type
was silently dropped on Save. Fixed in the template:
app/templates/partials/proforma_review.html (addUnitRow now adds a checked
``unit_type_include[]`` box whose value is the row's index).
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import IncomeStream
from app.models.project import Project

from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
    set_client_auth,
)

pytestmark = pytest.mark.asyncio


class _FakeRedis:
    def __init__(self, store: dict, decode: bool):
        self._s, self._d = store, decode

    def get(self, key):
        v = self._s.get(key)
        if v is None:
            return None
        return v.decode() if self._d else v

    def getdel(self, key):
        v = self.get(key)
        self._s.pop(key, None)
        return v

    def set(self, key, value, ex=None):
        self._s[key] = value.encode() if isinstance(value, str) else value
        return True


async def test_added_unit_row_carries_include_box_and_is_saved(
    client: AsyncClient, session: AsyncSession, monkeypatch
) -> None:
    import redis  # type: ignore

    store: dict = {}
    monkeypatch.setattr(
        redis, "from_url",
        lambda _u, decode_responses=False, **_k: _FakeRedis(store, decode_responses),
    )

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    scen, _i, _inc, _opx = await seed_deal_model_with_financials(session, opp, user)
    project = (
        await session.execute(select(Project).where(Project.scenario_id == scen.id))
    ).scalar_one()
    await session.commit()
    model_id, project_id = scen.id, project.id
    set_client_auth(client, user.id)
    hx = {"hx-request": "true"}

    # Parser found one unit type -> review page renders it with include box 0.
    tid = "t1"
    store[f"proforma:{tid}:progress"] = json.dumps({"status": "done"}).encode()
    store[f"proforma:{tid}:result"] = json.dumps({
        "unit_types": [{"name": "1BR", "count": 6, "avg_sqft": 650,
                        "avg_monthly_rent": 1250, "confidence": 0.9}],
        "expense_lines": [], "warnings": [],
    }).encode()
    page = await client.get(f"/ui/models/{model_id}/proforma-status/{tid}", headers=hx)
    assert page.status_code == 200
    assert re.search(r'name="unit_type_include\[\]" value="0" checked', page.text)

    # The hand-added row's markup must send its own include index.
    add_fn = re.search(r"function addUnitRow\(\)\s*\{(.*?)\n\}", page.text, re.S)
    assert add_fn is not None
    body = add_fn.group(1)
    assert 'name="unit_type_include[]"' in body
    assert 'value="${idx}"' in body
    assert "tbody.querySelectorAll('tr').length" in body

    # What the browser now submits: extracted row 0 + added row 1, both checked.
    resp = await client.post(
        f"/ui/models/{model_id}/proforma-confirm",
        data={
            "rent_type": "in_place",
            "unit_type_include[]": ["0", "1"],
            "unit_type_name[]": ["1BR", "2BR"],
            "unit_type_count[]": ["6", "2"],
            "unit_type_sqft[]": ["650", "900"],
            "unit_type_rent[]": ["1250", "1700"],
            "unit_type_market_rent[]": ["", ""],
            "unit_type_mode[]": ["unit", "unit"],
            "unit_type_stream_type[]": ["commercial_rent", "commercial_rent"],
        },
        headers=hx,
    )
    assert resp.status_code == 200, resp.text[:500]
    session.expire_all()
    streams = list((await session.execute(
        select(IncomeStream).where(IncomeStream.project_id == project_id)
        .order_by(IncomeStream.label)
    )).scalars())
    assert [(s.label, s.unit_count, s.amount_per_unit_monthly) for s in streams] == [
        ("1BR Rent", 6, Decimal("1250")),
        ("2BR Rent", 2, Decimal("1700")),
    ]
