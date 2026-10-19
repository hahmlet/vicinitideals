"""Hostile input on the FLATS review pages answers 4xx or a redirect -- never a 500.

Sibling of test_flats_bad_input.py, which covers /flats/lots* and /api/flats/*.
Every path and query parameter of the review pages is fed an overflow integer,
a NUL byte, a negative and a non-number; every free-text form field a NUL byte
and every integer form field an overflow. A valid request's answer is untouched:
these only pin the status.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import ui_flats
from tests.api.test_ui_flats_lots import _login
from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio

BIG = "99999999999999999999"
ODD = [BIG, "%00", "-3", "abc", "0", "1e999", "nan"]
OK_STATUS = (200, 404, 422)
LAYER = next(iter(ui_flats._layers()))
DOC = next(iter(ui_flats._known_documents()))


def _urls() -> list[str]:
    urls: list[str] = []
    for v in ODD:
        urls += [
            f"/flats/check/{v}",
            f"/flats/check/{LAYER}?skipped={v}&zone={v}&field={v}&when={v}",
            f"/flats/why/{v}?zone={v}&field={v}",
            f"/flats/why/{LAYER}?zone={v}&field={v}",
            f"/flats/find/{v}?zone={v}&field={v}",
            f"/flats/find/{LAYER}?zone={v}&field={v}",
            f"/flats/review/{v}",
            f"/flats/plans/{v}?plat={v}",
            f"/flats/triage?layer={v}&field={v}&doc={v}&ruled={v}&skipped={v}",
            f"/flats/reading/{v}?layer={v}&field={v}&ruled={v}&skipped={v}",
            f"/flats/reading/rent?layer={v}&field={v}&skipped={v}",
            f"/flats/words/{v}?layer={v}&field={v}&ruled={v}&skipped={v}",
            f"/flats/words/term?layer={v}&field={v}&skipped={v}",
            f"/flats/sheet/{v}?page={v}",
            f"/flats/sheet/{DOC}?page={v}",
            f"/flats/book/{v}",
            f"/ui/flats/book?ref={v}&page={v}",
            f"/ui/flats/book?ref={DOC}%23L{v}&page={v}",
            f"/ui/flats/quote?ref={v}",
            f"/ui/flats/quote?ref={DOC}%23L{v}",
            f"/ui/flats/quote?ref={DOC}%23L{v}-{v}",
            f"/flats/check/readthrough/{v}?submitted={v}",
            f"/flats/check/readthrough/{DOC}?submitted={v}",
        ]
    urls += [
        "/flats/gaps",
        "/flats/gaps?x=%00",
        f"/ui/flats/book?ref={DOC}&page=0",
        f"/ui/flats/book?ref={DOC}&page=-3",
        f"/ui/flats/book?ref={DOC}&page=9999",
        f"/ui/flats/book?ref={DOC}&page=1",
    ]
    return urls


@pytest.mark.parametrize("url", _urls())
async def test_hostile_get_never_answers_500(client: AsyncClient, session: AsyncSession, url: str):
    await _login(client, session)

    response = await client.get(url)

    assert response.status_code in OK_STATUS or response.status_code in (301, 302, 303, 307, 308), (
        url,
        response.status_code,
    )


NUL = "a\x00b"

POSTS: list[tuple[str, dict[str, str]]] = []
for _bad in (NUL, BIG):
    POSTS += [
        (
            "/ui/flats/sign",
            {"layer_id": LAYER, "zone": _bad, "field": _bad, "when": _bad, "verdict": "confirmed",
             "note": _bad, "ref": _bad, "shape": _bad, "anchor": _bad},
        ),
        ("/ui/flats/sign-passage", {"layer_id": LAYER, "ref": _bad, "verdict": "confirmed", "note": _bad}),
        ("/ui/flats/sign-passage", {"layer_id": _bad, "ref": _bad, "verdict": _bad, "note": _bad}),
        (
            "/ui/flats/reading/rule",
            {"queue": "rent", "layer_id": LAYER, "path": _bad, "section": _bad, "fingerprint": _bad,
             "outcome": _bad, "note": _bad, "action": "rule", "layer": _bad, "field": _bad,
             "skipped": _bad},
        ),
        (
            "/ui/flats/words/rule",
            {"queue": "term", "layer_id": LAYER, "term": _bad, "fingerprint": _bad, "outcome": _bad,
             "note": _bad, "values_touched": _bad, "lots": _bad, "fields_touched": _bad,
             "layer": _bad, "field": _bad, "skipped": _bad},
        ),
        (
            "/ui/flats/triage/rule",
            {"layer_id": LAYER, "ref": _bad, "outcome": _bad, "note": _bad, "layer": _bad,
             "field": _bad, "doc": _bad, "skipped": _bad},
        ),
        (
            "/ui/flats/check",
            {"layer_id": LAYER, "zone": _bad, "field": _bad, "when": _bad, "question": _bad,
             "answer": _bad, "says": _bad, "note": _bad, "comment": _bad, "flag_page": _bad,
             "flag_web": _bad, "action": "answer", "skipped": _bad, "trail": _bad, "ahead": _bad},
        ),
        (
            "/ui/flats/flags/type",
            {"code": _bad, "risk": _bad, "severity": _bad, "absorbs": _bad, "resolution": _bad,
             "priority": _bad, "note": _bad},
        ),
        (
            "/ui/flats/flags/rules",
            {"yellow_at_severity": _bad, "approval_severity": _bad, "near_miss_fit_ft": _bad,
             "near_miss_severity": _bad, "risk_remote": _bad, "risk_unlikely": _bad,
             "risk_possible": _bad, "risk_likely": _bad, "risk_near_certain": _bad, "note": _bad},
        ),
        (f"/ui/flats/flags/questions/{BIG}/answer", {"answer": _bad}),
        ("/ui/flats/flags/questions/-3/answer", {"answer": _bad}),
    ]


@pytest.mark.parametrize("owner", [True, False])
@pytest.mark.parametrize(("url", "data"), POSTS)
async def test_hostile_post_never_answers_500(
    client: AsyncClient, session: AsyncSession, url: str, data: dict[str, str], owner: bool
):
    _org, user = await seed_org(session)
    user.is_admin = owner
    await session.commit()
    set_client_auth(client, user.id)

    response = await client.post(url, data=data)

    assert response.status_code < 500, (url, response.status_code)
