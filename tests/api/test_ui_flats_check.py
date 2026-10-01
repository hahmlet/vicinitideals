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

import html
import re

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

    assert "flag saved" in response.text
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


async def test_a_boxed_number_does_not_also_tint_its_citations_context_lines(client, session, monkeypatch):
    """Oregon City Table 16.12.035.D: the citation quotes the table title and
    heading rows. With 36 boxed, they were drawn yellow too -- "the line it
    was read from" -- and the page before, holding only the run-in line, was
    shown as well."""
    await _login(client, session)
    line = sheet.Box(0.1, 0.5, 0.9, 0.52)
    placed = sheet.Placed(
        status="boxed",
        pages=[1, 2],
        boxes={1: [(line, "line")], 2: [(line, "line"), (_BOX, "value")]},
    )
    monkeypatch.setattr(check, "_placed", lambda row: placed)

    response = await client.get(f"/flats/check/{LAYER}")

    assert "check-box-value" in response.text
    assert "check-box check-box-line" not in response.text
    assert "?page=2" in response.text and "?page=1" not in response.text


def test_a_condition_is_named_in_words_not_by_its_key():
    from app.api.routers.ui_flats_check import _condition_words

    assert _condition_words("unit_lots") == [
        "the four units are being platted onto lots of their own rather than sharing one"
    ]
    assert _condition_words("") == []


async def test_back_returns_to_the_answered_card_to_change_it(client, session):
    """Back shows the card just answered, with the answer and comment given;
    a new answer to it is a later answer and the later one counts."""
    await _login(client, session)
    row = _first_row()
    answered = await client.post(
        "/ui/flats/check", data=_form(row, answer="differs", comment="7,500 sq ft")
    )
    trail = re.search(r'name="trail" value="([^"]*)"', answered.text).group(1)
    assert "data-back" in answered.text

    back = await client.post(
        "/ui/flats/check",
        data={"layer_id": LAYER, "action": "back", "trail": html.unescape(trail)},
    )

    assert f'name="field" value="{row["field"]}"' in back.text
    assert "your answer: No" in back.text
    assert ">7,500 sq ft</textarea>" in back.text
    changed = await client.post("/ui/flats/check", data=_form(row, answer="matches"))
    assert changed.status_code == 200
    answers = await check._answers(session, LAYER)
    key = (LAYER, row["zone"], row["field"], row["when"], "value")
    assert answers[key].answer == "matches"


async def test_back_after_a_skip_un_skips(client, session):
    await _login(client, session)
    row = _first_row()
    skipped = await client.post("/ui/flats/check", data=_form(row, action="skip", skipped="0"))
    trail = html.unescape(re.search(r'name="trail" value="([^"]*)"', skipped.text).group(1))

    back = await client.post(
        "/ui/flats/check",
        data={"layer_id": LAYER, "action": "back", "trail": trail, "skipped": "1"},
    )

    assert f'name="field" value="{row["field"]}"' in back.text
    assert 'name="skipped" value="0"' in back.text
    assert "data-back" not in back.text


async def test_a_second_flag_adds_to_the_first_and_both_show_on_the_card(client, session):
    await _login(client, session)
    row = _first_row()
    page = check._card(check._layers()[LAYER], check._Ask(row, "value"))["sheets"][0]["page"]
    for says in ("first thing", "second thing"):
        response = await client.post(
            "/ui/flats/check",
            data=_form(row, action="flag", flag_page=str(page), comment=says),
        )

    assert "Flagged on this page (2)" in response.text
    assert response.text.index("first thing") < response.text.index("second thing")


async def test_an_answered_flag_leaves_the_open_list_and_shows_its_answer(client, session):
    # A flag traced and explained moves no fingerprint, so without a reply it
    # would sit on the open list forever asking to be looked at again.
    await _login(client, session)
    row = _first_row()
    page = check._card(check._layers()[LAYER], check._Ask(row, "value"))["sheets"][0]["page"]
    await client.post(
        "/ui/flats/check", data=_form(row, action="flag", flag_page=str(page), comment="what about G2?")
    )
    flag = (
        await session.execute(select(FlatsPageCheck).where(FlatsPageCheck.answer == check.FLAG))
    ).scalar_one()
    session.add(
        FlatsPageCheck(
            layer=flag.layer, zone=flag.zone, field=flag.field, when_key=flag.when_key,
            value=flag.value, fingerprint=flag.fingerprint, question=f"reply:{flag.id}",
            answer=check.REPLIED, says=flag.says, note="G2 sets no maximum side yard.",
            quote=flag.quote, page=flag.page, placed=flag.placed, reviewer="triage",
        )
    )
    await session.commit()

    index = await client.get("/flats/check")
    open_list, _, answered = index.text.partition("data-answered")
    assert "what about G2?" not in open_list
    assert "what about G2?" in answered and "G2 sets no maximum side yard." in answered
    assert "what about G2?" not in (await client.get("/flats/check/problems.txt")).text
    card = await client.get(
        f"/flats/check/{LAYER}", params={"zone": row["zone"], "field": row["field"], "when": row["when"]}
    )
    assert "Answered: G2 sets no maximum side yard." in card.text


def _hidden(text: str, name: str) -> str:
    return html.unescape(re.search(rf'name="{name}" value="([^"]*)"', text).group(1))


async def test_forward_returns_to_the_card_back_was_pressed_on(client, session):
    await _login(client, session)
    row = _first_row()
    answered = await client.post("/ui/flats/check", data=_form(row, answer="matches"))
    front = {k: _hidden(answered.text, k) for k in ("zone", "field", "when", "question")}

    back = await client.post(
        "/ui/flats/check",
        data={**front, "layer_id": LAYER, "action": "back", "trail": _hidden(answered.text, "trail")},
    )
    assert "data-forward" in back.text
    forward = await client.post(
        "/ui/flats/check",
        data={
            **_form(row),
            "action": "forward",
            "trail": _hidden(back.text, "trail"),
            "ahead": _hidden(back.text, "ahead"),
        },
    )

    assert {k: _hidden(forward.text, k) for k in front} == front
    assert "data-forward" not in forward.text and "data-back" in forward.text
    # Passing an answered card does not skip it.
    assert _hidden(forward.text, "skipped") == "0"


async def test_skip_on_a_card_already_answered_does_not_pass_over_the_next(client, session):
    # Back to an answered card, then Skip instead of Forward: the reviewer is
    # leaving a card the queue no longer holds, so nothing is skipped.
    await _login(client, session)
    row = _first_row()
    await client.post("/ui/flats/check", data=_form(row, answer="matches"))

    left = await client.post("/ui/flats/check", data=_form(row, action="skip", skipped="0"))

    assert _hidden(left.text, "skipped") == "0"
    assert "skip:" not in _hidden(left.text, "trail")


async def test_passing_an_unanswered_card_on_the_way_forward_skips_it(client, session):
    await _login(client, session)
    row = _first_row()
    skipped = await client.post("/ui/flats/check", data=_form(row, action="skip", skipped="0"))
    front = {k: _hidden(skipped.text, k) for k in ("zone", "field", "when", "question")}
    back = await client.post(
        "/ui/flats/check",
        data={**front, "layer_id": LAYER, "action": "back", "skipped": "1",
              "trail": _hidden(skipped.text, "trail")},
    )
    assert _hidden(back.text, "skipped") == "0"

    # Skip on a card reached by Back goes forward, the way the reviewer came.
    again = await client.post(
        "/ui/flats/check",
        data={**_form(row), "action": "skip", "skipped": "0",
              "trail": _hidden(back.text, "trail"), "ahead": _hidden(back.text, "ahead")},
    )

    assert {k: _hidden(again.text, k) for k in front} == front
    assert _hidden(again.text, "skipped") == "1"


async def test_a_new_answer_after_back_ends_the_walk_forward(client, session):
    await _login(client, session)
    row = _first_row()
    answered = await client.post("/ui/flats/check", data=_form(row, answer="matches"))
    back = await client.post(
        "/ui/flats/check",
        data={"layer_id": LAYER, "action": "back", "trail": _hidden(answered.text, "trail"),
              "zone": _hidden(answered.text, "zone"), "field": _hidden(answered.text, "field"),
              "when": _hidden(answered.text, "when"), "question": _hidden(answered.text, "question")},
    )

    changed = await client.post(
        "/ui/flats/check",
        data={**_form(row, answer="differs", comment="7,500"),
              "trail": _hidden(back.text, "trail"), "ahead": _hidden(back.text, "ahead")},
    )

    assert "data-forward" not in changed.text
    assert "data-back" in changed.text


async def test_a_passage_set_aside_on_purpose_has_its_own_tint(client, session, monkeypatch):
    """Steph 2026-10-01: an untinted clause must mean nobody weighed it. One
    read and declined is tinted grey, so a blind miss stands out from a
    conscious refusal without the reviewer needing the reason."""
    await _login(client, session)
    declined = sheet.Box(0.1, 0.7, 0.5, 0.72)
    monkeypatch.setattr(
        check, "_set_aside_on", lambda document, page: ((declined, "set aside on purpose: garages"),)
    )

    response = await client.get(f"/flats/check/{LAYER}")

    assert 'class="check-box check-box-set-aside"' in response.text
    assert 'title="set aside on purpose: garages"' in response.text
    assert "read and set aside on purpose" in response.text


def test_what_was_set_aside_includes_the_located_refusals():
    oregon_city = check._layers()["or/clackamas/oregon-city"]
    by_document = check._set_aside_by_document()

    for item in oregon_city.set_aside:
        held = by_document[item.quote.partition("#L")[0]]
        assert {"quote": item.quote, "why": item.why} in held


async def test_an_exempt_standard_is_asked_as_not_applying(client, session, monkeypatch):
    await _login(client, session)
    monkeypatch.setattr(check, "_exempt", lambda layer, row: True)

    response = await client.get(f"/flats/check/{LAYER}")

    assert "does <strong>not apply to our building</strong>" in response.text


def test_the_card_names_the_other_numbers_held_for_the_same_standard():
    layer = check._layers()["or/clackamas/oregon-city"]
    zone, field = next(
        (z, f)
        for z, block in layer.zones.items()
        for f, v in block.values.items()
        if v.variants
    )

    held = check._variants(layer, zone, field)

    assert held[0]["when"] == "normally"
    assert all(v["when"].startswith("in the case where ") for v in held[1:])
    assert "_" not in " ".join(v["when"] for v in held), "conditions in words, not keys"


async def test_a_yes_or_no_is_asked_as_a_reading_with_where_it_was_read(client, session, monkeypatch):
    """Steph answered "differs" to "fourplex allowed: no" in Oregon City's I
    and MUE, shown only the general rule that an unlisted use is forbidden."""
    await _login(client, session)
    row = {**_first_row(), "value": False, "cite": "OCMC 17.39.020 (permitted uses), with 17.06.010.A"}
    monkeypatch.setattr(check, "_rows", lambda layer, answered: [row])

    response = await client.get(f"/flats/check/{LAYER}")

    assert "Is that what the page says?" in response.text
    assert "Read from: OCMC 17.39.020 (permitted uses), with 17.06.010.A" in response.text


async def test_a_reopened_no_is_asked_again_with_what_was_said_before(client, session):
    """Steph 2026-10-01: a "No" whose fix moved a box or reworded the card
    changes no fingerprint, so it would stand forever. Reopening puts it back
    in the queue; a "Yes" stays done."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "reopen", Path(__file__).resolve().parents[2] / "scripts" / "flats_page_check_reopen.py"
    )
    reopen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reopen)

    await _login(client, session)
    rows = check._rows(check._layers()[LAYER], set())
    no, yes = rows[0], rows[1]
    await client.post("/ui/flats/check", data=_form(no, answer="differs", says="the page says 7,500"))
    await client.post("/ui/flats/check", data=_form(yes, answer="matches"))

    added = await reopen.reopen(session, LAYER)
    assert [(r.zone, r.field, r.note) for r in added] == [(no["zone"], no["field"], "differs")]
    session.add_all(added)
    await session.commit()

    response = await client.get(f"/flats/check/{LAYER}")

    assert "data-asked-again" in response.text
    assert "the page says 7,500" in response.text
    assert "No, the page says something else" in response.text
    # Off the problems list until answered again; the history keeps the "No".
    assert f"{LAYER} | {no['zone']} | {no['field']}" not in (await client.get("/flats/check/problems.txt")).text
    assert await reopen.reopen(session, LAYER) == [], "a reopened question is not reopened twice"
