"""The page check: an encoded number asked of the printed page.

What these tests hold to is the bookkeeping around the card, not the box on
it (``flats/tests/test_sheet.py`` covers that): the pages are reachable past
the ``/flats/{layer}`` catch-all, an answer is stored against the number the
*server* holds rather than whatever the browser sent, a "no" reaches the
problems list, and a document with no page map says so instead of drawing.

Placing a box reads a book, and a book is a download. The router's
``_placed`` is replaced with a fixed placement so no test fetches one.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import ui_flats_check as check
from app.models.flats import FlatsPageCheck
from flats.provenance import sheet
from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio

LAYER = "or/multnomah/gresham"

_BOX = sheet.Box(0.4, 0.3, 0.45, 0.32)
_PLACED = sheet.Placed(
    status="boxed",
    pages=[1],
    boxes={1: [(_BOX, "value")]},
    markers=[sheet.Marker("5", "number", sheet.Box(0.451, 0.29, 0.46, 0.3))],
    marker_page=1,
)


@pytest.fixture(autouse=True)
def _no_books(monkeypatch):
    monkeypatch.setattr(check, "_placed", lambda row: _PLACED)
    monkeypatch.setattr(check, "_note_box", lambda document, page, body: [])


async def _login(client: AsyncClient, session: AsyncSession):
    _org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)
    return user


def _first_row() -> dict:
    layer = check._layers()[LAYER]
    rows = check._rows(layer, set())
    assert rows, "fixture assumption: Gresham has numbers on mapped pages"
    return rows[0]


def _form(row: dict, **extra) -> dict:
    return {
        "layer_id": LAYER,
        "zone": row["zone"],
        "field": row["field"],
        "when": row["when"],
        "question": "value",
        **extra,
    }


async def test_the_index_is_not_swallowed_by_the_layer_route(client, session):
    await _login(client, session)

    response = await client.get("/flats/check")

    assert response.status_code == 200
    assert "Page check" in response.text
    assert "Gresham" in response.text


async def test_a_card_shows_the_page_with_the_box_and_asks_one_question(client, session):
    await _login(client, session)

    response = await client.get(f"/flats/check/{LAYER}")

    assert response.status_code == 200
    assert "Page check · " in response.text
    assert "Does the page say" in response.text
    assert "check-box-value" in response.text
    assert f"/flats/sheet/{_first_row()['document']}?page=1" in response.text


async def test_an_answer_is_stored_against_the_number_the_server_holds(client, session):
    user = await _login(client, session)
    row = _first_row()

    # A browser that sends its own "value" has it ignored: there is no such form
    # field, and the stored value is read off the rules.
    response = await client.post(
        "/ui/flats/check", data=_form(row, answer="matches", value="999999")
    )

    assert response.status_code == 200
    assert "the page agrees" in response.text
    saved = (await session.execute(select(FlatsPageCheck))).scalars().one()
    assert saved.value == row["value"]
    assert saved.fingerprint == row["mark"]
    assert saved.reviewer_user_id == user.id
    assert (saved.page, saved.placed) == (1, "boxed")


async def test_a_confirmed_number_is_followed_by_its_footnote(client, session):
    await _login(client, session)
    row = _first_row()

    response = await client.post("/ui/flats/check", data=_form(row, answer="matches"))

    # The placement puts note 5 on the number, so the next card asks about it.
    assert "Note <strong>5</strong>" in response.text
    assert 'value="note:5"' in response.text


async def test_an_answer_that_is_not_on_the_card_is_refused(client, session):
    await _login(client, session)
    row = _first_row()

    response = await client.post("/ui/flats/check", data=_form(row, answer="have_it"))

    assert "pick one of the answers" in response.text
    assert (await session.execute(select(FlatsPageCheck))).first() is None


async def test_skip_moves_on_without_recording(client, session):
    await _login(client, session)
    row = _first_row()

    response = await client.post("/ui/flats/check", data=_form(row, action="skip", skipped="0"))

    assert response.status_code == 200
    assert 'name="skipped" value="1"' in response.text
    assert (await session.execute(select(FlatsPageCheck))).first() is None


async def test_a_no_lands_on_the_problems_list_with_what_the_page_says(client, session):
    await _login(client, session)
    row = _first_row()
    await client.post(
        "/ui/flats/check", data=_form(row, answer="differs", says="7,500 sq ft", note="TR column")
    )

    index = await client.get("/flats/check")
    text = await client.get("/flats/check/problems.txt")

    assert "Problems raised" in index.text
    assert "7,500 sq ft" in index.text
    assert f"{LAYER} | {row['zone']} | {row['field']}" in text.text
    assert "the page says: 7,500 sq ft" in text.text
    assert "our text copy:" in text.text


async def test_handing_on_the_problems_empties_the_next_export(client, session):
    await _login(client, session)
    row = _first_row()
    await client.post("/ui/flats/check", data=_form(row, answer="wrong_box"))

    first = await client.get("/flats/check/problems.txt?mark_handed_on=true")
    second = await client.get("/flats/check/problems.txt")

    assert row["field"] in first.text
    assert second.text == "no open problems\n"


async def test_a_document_with_no_page_map_draws_no_page(client, session):
    await _login(client, session)

    response = await client.get("/flats/sheet/or/nowhere/nothing.txt?page=1")

    assert response.status_code == 404


async def test_a_number_the_rules_do_not_hold_is_refused(client, session):
    await _login(client, session)

    response = await client.post(
        "/ui/flats/check",
        data={"layer_id": LAYER, "zone": "NO-SUCH-ZONE", "field": "setback_front_ft", "answer": "matches"},
    )

    assert response.status_code == 400


async def test_the_page_check_needs_a_signed_in_user(client, session):
    response = await client.get("/flats/check", follow_redirects=False)

    assert response.status_code in (302, 303, 401)


async def test_other_rules_from_the_page_are_tinted_with_what_they_are(client, session, monkeypatch):
    await _login(client, session)
    row = _first_row()
    other = sheet.Box(0.1, 0.6, 0.5, 0.62)
    monkeypatch.setattr(
        check,
        "_encoded_on",
        lambda document, page: (
            (other, "TR · Rear setback = 20 ft", frozenset({"someone-else"})),
            (_BOX, "the card's own number", frozenset({row["mark"]})),
        ),
    )

    response = await client.get(f"/flats/check/{LAYER}")

    assert 'class="check-box check-box-encoded"' in response.text
    assert 'title="TR · Rear setback = 20 ft"' in response.text
    # The card's own number is boxed in red, not tinted as "another rule".
    assert "the card&#39;s own number" not in response.text
    assert "the card's own number" not in response.text


async def test_something_missing_from_the_page_can_be_flagged(client, session):
    await _login(client, session)
    row = _first_row()
    before = await client.get(f"/flats/check/{LAYER}")

    response = await client.post(
        "/ui/flats/check",
        data=_form(row, question="page:839", answer="unmarked", says="F. one approach per two units"),
    )

    assert "flagged" in response.text
    saved = (await session.execute(select(FlatsPageCheck))).scalars().one()
    assert (saved.question, saved.page, saved.answer) == ("page:839", 839, "unmarked")
    # A flag is not an answer to the card: the same question is still asked.
    assert 'name="question" value="value"' in response.text
    assert "Does the page say" in before.text and "Does the page say" in response.text
    text = await client.get("/flats/check/problems.txt")
    assert "the page says: F. one approach per two units" in text.text


async def test_two_flags_on_one_page_are_two_problems(client, session):
    await _login(client, session)
    row = _first_row()
    for says in ("first thing", "second thing"):
        await client.post(
            "/ui/flats/check", data=_form(row, question="page:3", answer="unmarked", says=says)
        )

    index = await client.get("/flats/check")

    assert "first thing" in index.text and "second thing" in index.text


async def test_a_flag_must_say_what_is_missing(client, session):
    await _login(client, session)
    row = _first_row()

    response = await client.post(
        "/ui/flats/check", data=_form(row, question="page:3", answer="unmarked", says="  ")
    )

    assert "say what on the page is missing" in response.text
    assert (await session.execute(select(FlatsPageCheck))).first() is None


async def test_one_comment_box_serves_every_answer(client, session):
    """The card has one comment box: under "No" it is what the page says,
    with "Flag something missing" it is the missing thing, else a note."""
    await _login(client, session)
    row = _first_row()

    await client.post(
        "/ui/flats/check", data=_form(row, answer="differs", comment="7,500 sq ft")
    )
    await client.post(
        "/ui/flats/check",
        data=_form(row, action="flag", flag_page="12", comment="F. one approach per two units"),
    )

    saved = (await session.execute(select(FlatsPageCheck).order_by(FlatsPageCheck.id))).scalars().all()
    assert [(s.question, s.answer, s.says) for s in saved] == [
        ("value", "differs", "7,500 sq ft"),
        ("page:12", "unmarked", "F. one approach per two units"),
    ]


async def test_the_card_asks_once_and_names_the_section_not_its_description(client, session):
    await _login(client, session)
    row = _first_row()

    response = await client.get(f"/flats/check/{LAYER}")

    assert response.text.count("Does the page say") == 1
    assert "Problems raised" not in response.text
    assert "Read the row and the column heading" not in response.text
    assert row["cite"].split(",")[0] in response.text
