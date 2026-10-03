"""The Unknowns page: approving a kind of flag's numbers and the colour rule.

What these hold to: the page is reachable past the ``/flats/{layer}``
catch-all, only the owner can approve, an approval is a stored row and not a
file edit (the drain does that), and a value the files would refuse is
refused here, before it can sit in the queue as if it could be written.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import RULES_SUBJECT, FlatsFlagDecision
from flats.score import flags as fp
from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


async def _login(client: AsyncClient, session: AsyncSession, *, owner: bool):
    _org, user = await seed_org(session)
    user.is_admin = owner
    await session.commit()
    set_client_auth(client, user.id)
    return user


def _a_code() -> str:
    return next(iter(fp.load_registry())).code


def _type_form(code: str, **over) -> dict:
    t = fp.load_registry()[code]
    return {
        "code": code,
        "risk": t.risk.value,
        "severity": str(t.severity),
        "absorbs": t.absorbs or "",
        "resolution": t.resolution.value,
        "priority": "now",
        "note": "",
        **over,
    }


def _rules_form(**over) -> dict:
    r = fp.load_rules()
    bands = {getattr(k, "value", k): v for k, v in r.risk_bands.items()}
    return {
        "yellow_at_severity": str(r.yellow_at_severity),
        "approval_severity": str(r.approval_severity),
        "near_miss_fit_ft": str(r.near_miss["fit_ft"]),
        "near_miss_severity": str(r.near_miss_severity),
        **{f"risk_{k}": str(round(v * 100)) for k, v in bands.items()},
        "note": "",
        **over,
    }


async def _stored(session: AsyncSession) -> list[FlatsFlagDecision]:
    return list((await session.execute(select(FlatsFlagDecision))).scalars())


async def test_the_page_is_not_swallowed_by_the_layer_route(client, session):
    await _login(client, session, owner=False)

    response = await client.get("/flats/flags")

    assert response.status_code == 200
    assert "Unknowns" in response.text
    assert "The colour rule" in response.text
    # Every kind is listed, and a non-owner gets no approve button.
    assert response.text.count("data-flag=") == len(fp.load_registry())
    assert "data-approve" not in response.text
    assert "read-only for you" in response.text


async def test_the_owner_sees_the_forms_and_waiting_kinds_first(client, session):
    await _login(client, session, owner=True)

    response = await client.get("/flats/flags")

    assert response.status_code == 200
    assert "data-approve" in response.text
    pending = sum(t.status is fp.TypeStatus.pending for t in fp.load_registry())
    if pending:
        first = response.text.index('data-section="')
        assert response.text[first:].startswith('data-section="proposed"')


async def test_an_approval_is_a_stored_row_waiting_for_the_write_in(client, session):
    user = await _login(client, session, owner=True)
    code = _a_code()
    before = fp.load_registry()[code]

    response = await client.post(
        "/ui/flats/flags/type", data=_type_form(code, severity="7", note="checked")
    )

    assert response.status_code == 200
    assert 'data-state="waiting"' in response.text
    assert "in force at the next write-in" in response.text
    rows = await _stored(session)
    assert len(rows) == 1
    row = rows[0]
    assert row.subject == code
    assert row.values["severity"] == 7
    assert row.values["priority"] == "now"
    assert row.note == "checked"
    assert row.decided_by == user.name
    assert row.decided_user_id == user.id
    assert row.exported_at is None
    # Not a file edit: the files change only when the drain writes them.
    assert fp.load_registry()[code] == before

    page = await client.get("/flats/flags")
    assert f'id="flag-{code}"' in page.text
    block = page.text[page.text.index(f'id="flag-{code}"') - 200 :][:400]
    assert 'data-state="waiting"' in block


async def test_a_non_owner_cannot_approve(client, session):
    await _login(client, session, owner=False)

    response = await client.post("/ui/flats/flags/type", data=_type_form(_a_code()))

    assert response.status_code == 403
    assert await _stored(session) == []


async def test_signed_out_cannot_approve(client, session):
    response = await client.post("/ui/flats/flags/type", data=_type_form(_a_code()))

    assert response.status_code in (401, 303, 307)
    assert await _stored(session) == []


async def test_an_unknown_kind_is_not_found(client, session):
    await _login(client, session, owner=True)

    response = await client.post(
        "/ui/flats/flags/type", data={**_type_form(_a_code()), "code": "NO-SUCH-KIND"}
    )

    assert response.status_code == 404
    assert await _stored(session) == []


@pytest.mark.parametrize("over", [{"severity": "11"}, {"risk": "sometimes"}, {"absorbs": "roof"}])
async def test_a_value_the_files_would_refuse_is_refused_here(client, session, over):
    await _login(client, session, owner=True)

    response = await client.post("/ui/flats/flags/type", data=_type_form(_a_code(), **over))

    assert response.status_code == 200
    assert "data-error" in response.text
    assert await _stored(session) == []


async def test_the_colour_rule_is_approved_in_percent_and_stored_as_a_probability(
    client, session
):
    await _login(client, session, owner=True)

    response = await client.post(
        "/ui/flats/flags/rules", data=_rules_form(yellow_at_severity="4", risk_possible="35")
    )

    assert response.status_code == 200
    assert 'data-state="waiting"' in response.text
    rows = await _stored(session)
    assert len(rows) == 1
    assert rows[0].subject == RULES_SUBJECT
    assert rows[0].values["yellow_at_severity"] == 4
    assert rows[0].values["risk_bands"]["possible"] == 0.35
    # Shown back in percent.
    assert 'name="risk_possible"' in response.text
    assert 'value="35"' in response.text


async def test_a_colour_rule_the_file_would_refuse_is_refused_here(client, session):
    await _login(client, session, owner=True)

    response = await client.post(
        "/ui/flats/flags/rules", data=_rules_form(yellow_at_severity="11")
    )

    assert response.status_code == 200
    assert "data-error" in response.text
    assert (await session.execute(select(func.count()).select_from(FlatsFlagDecision))).scalar() == 0
