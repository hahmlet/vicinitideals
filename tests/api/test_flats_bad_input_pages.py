"""Hostile input on the FLATS review pages answers 4xx or a redirect -- never a 500.

Sibling of test_flats_bad_input.py, which covers /flats/lots* and /api/flats/*.
Every path and query parameter of the review pages is fed an overflow integer,
a NUL byte, a negative and a non-number; every free-text form field a NUL byte
and every integer form field an overflow. A valid request's answer is untouched:
these only pin the status.
"""
from __future__ import annotations

import re

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import ui_flats
from app.api.routers import ui_flats_check as check
from app.models.flats import (
    FlatsCrossrefRuling,
    FlatsPageCheck,
    FlatsReadingRuling,
    FlatsRuleSignature,
    FlatsWordRuling,
)
from flats.provenance import sheet
from tests.api.test_ui_flats_lots import _login
from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio

BIG = "99999999999999999999"
ODD = [BIG, "%00", "-3", "abc", "0", "1e999", "nan"]
OK_STATUS = (200, 404, 422)
LAYER = next(iter(ui_flats._layers()))
# min(), not next(iter()): a frozenset's order changes between processes, and
# pytest-xdist refuses a run whose workers collect different test ids.
DOC = min(ui_flats._known_documents())


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


def _value(html: str, name: str) -> str:
    found = re.search(rf'name="{name}" value="([^"]*)"', html)
    assert found, f"no {name} field on card"
    return found.group(1)


def _card(html: str, names: tuple[str, ...]) -> dict[str, str]:
    return {name: _value(html, name) for name in names}


def _with_nul(value: str) -> str:
    return value[:1] + "\x00" + value[1:] if value else "\x00"


def _without_nul(value: str) -> str:
    return value.replace("\x00", "")


async def test_sign_strips_nul_from_note_and_ref_before_insert(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    layer = "or/clackamas/wilsonville"
    number = ui_flats._number(ui_flats._layers()[layer], "R", "setback_side_ft", "")
    assert number is not None
    clean_ref = number.prov.quote or ""
    response = await client.post(
        "/ui/flats/sign",
        data={
            "layer_id": layer,
            "zone": "R",
            "field": "setback_side_ft",
            "when": "",
            "verdict": "verified",
            "note": NUL,
            "ref": _with_nul(clean_ref),
        },
    )
    assert response.status_code == 200

    row = (
        await session.execute(
            select(FlatsRuleSignature)
            .where(
                FlatsRuleSignature.layer == layer,
                FlatsRuleSignature.zone == "R",
                FlatsRuleSignature.field == "setback_side_ft",
                FlatsRuleSignature.when_key == "",
            )
            .order_by(FlatsRuleSignature.id.desc())
        )
    ).scalars().first()
    assert row is not None
    assert row.note == _without_nul(NUL)
    assert row.shown_ref == clean_ref


async def test_sign_passage_strips_nul_from_note_before_insert(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    layer = "or/clackamas/wilsonville"
    page = await client.get(f"/flats/review/{layer}")
    clean_ref = _value(page.text, "ref")
    dirty_ref = _with_nul(clean_ref)
    response = await client.post(
        "/ui/flats/sign-passage",
        data={
            "layer_id": layer,
            "ref": dirty_ref,
            "verdict": "verified",
            "note": NUL,
        },
    )
    assert response.status_code == 200

    row = (
        await session.execute(
            select(FlatsRuleSignature)
            .where(FlatsRuleSignature.layer == layer, FlatsRuleSignature.shown_ref == clean_ref)
            .order_by(FlatsRuleSignature.id.desc())
        )
    ).scalars().first()
    assert row is not None
    assert row.note == _without_nul(NUL)
    assert row.shown_ref == clean_ref


async def test_triage_rule_strips_nul_from_note_before_insert(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    layer = "or/multnomah/gresham"
    page = await client.get(f"/flats/triage?layer={layer}")
    ref = _value(page.text, "ref")
    dirty = (
        "Read it.\x00 Design review procedure only; no dimensional standard "
        "the screening model could hold."
    )
    response = await client.post(
        "/ui/flats/triage/rule",
        data={"layer_id": layer, "ref": ref, "outcome": "procedure", "note": dirty, "layer": layer},
    )
    assert response.status_code == 200

    row = (
        await session.execute(
            select(FlatsCrossrefRuling)
            .where(FlatsCrossrefRuling.layer == layer, FlatsCrossrefRuling.ref == ref)
            .order_by(FlatsCrossrefRuling.id.desc())
        )
    ).scalars().first()
    assert row is not None
    assert row.note == " ".join(_without_nul(dirty).split())


async def test_reading_rule_strips_nul_from_note_before_insert(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    page = await client.get("/flats/reading/nofield")
    card = _card(page.text, ("queue", "layer_id", "path", "section", "fingerprint"))
    dirty = (
        "Read the whole section.\x00 Facade and materials standards for the "
        "district; nothing dimensional the model could hold."
    )
    response = await client.post(
        "/ui/flats/reading/rule",
        data={**card, "outcome": "design", "note": dirty},
    )
    assert response.status_code == 200

    row = (
        await session.execute(
            select(FlatsReadingRuling)
            .where(
                FlatsReadingRuling.layer == card["layer_id"],
                FlatsReadingRuling.path == card["path"],
                FlatsReadingRuling.section == card["section"],
            )
            .order_by(FlatsReadingRuling.id.desc())
        )
    ).scalars().first()
    assert row is not None
    assert row.note == " ".join(_without_nul(dirty).split())


async def test_words_rule_strips_nul_from_note_before_insert(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    page = await client.get("/flats/words/defined")
    card = _card(page.text, ("queue", "layer_id", "term", "fingerprint"))
    dirty = (
        "Definition read in full.\x00 Same edge and exclusions, nothing in it "
        "changes a measured number."
    )
    response = await client.post(
        "/ui/flats/words/rule",
        data={**card, "outcome": "matches", "note": dirty},
    )
    assert response.status_code == 200

    row = (
        await session.execute(
            select(FlatsWordRuling)
            .where(
                FlatsWordRuling.layer == card["layer_id"],
                FlatsWordRuling.term == card["term"],
                FlatsWordRuling.standing == card["queue"],
            )
            .order_by(FlatsWordRuling.id.desc())
        )
    ).scalars().first()
    assert row is not None
    assert row.note == " ".join(_without_nul(dirty).split())


async def test_check_strips_nul_from_answer_text_before_insert(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    _box = sheet.Box(0.4, 0.3, 0.45, 0.32)
    _placed = sheet.Placed(
        status="boxed",
        pages=[1],
        boxes={1: [(_box, "value")]},
        markers=[sheet.Marker("5", "number", sheet.Box(0.451, 0.29, 0.46, 0.3))],
        marker_page=1,
    )
    monkeypatch.setattr(check, "_placed", lambda row: _placed)
    monkeypatch.setattr(check, "_note_box", lambda document, page, body: [])
    await _login(client, session)
    layer = "or/multnomah/gresham"
    row = check._rows(check._layers()[layer], set())[0]
    dirty = "page text says 7,\x00500 sq ft"
    response = await client.post(
        "/ui/flats/check",
        data={
            "layer_id": layer,
            "zone": row["zone"],
            "field": row["field"],
            "when": row["when"],
            "question": "value",
            "answer": "differs",
            "comment": dirty,
        },
    )
    assert response.status_code == 200

    saved = (
        await session.execute(
            select(FlatsPageCheck)
            .where(
                FlatsPageCheck.layer == layer,
                FlatsPageCheck.zone == row["zone"],
                FlatsPageCheck.field == row["field"],
                FlatsPageCheck.when_key == row["when"],
                FlatsPageCheck.question == "value",
            )
            .order_by(FlatsPageCheck.id.desc())
        )
    ).scalars().first()
    assert saved is not None
    assert saved.says == _without_nul(dirty)
