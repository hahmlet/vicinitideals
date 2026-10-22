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


def _asks(html: str) -> int:
    """How many value questions a page asks: a printed number ("Does the page
    say") or a choice word asked as our reading (``data-reading``)."""
    return html.count("Does the page say") + html.count("data-reading>")


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
    # Steph 2026-10-19: sortable headers and a left-to-check column, to find
    # the small cities that can be finished in one sitting.
    assert 'data-col="left"' in response.text and "Left to check" in response.text
    assert 'data-col="numbers"' in response.text


async def test_a_card_shows_the_page_with_the_box_and_asks_one_question(client, session):
    await _login(client, session)

    response = await client.get(f"/flats/check/{LAYER}")

    assert response.status_code == 200
    assert "Page check · " in response.text
    assert _asks(response.text) == 1
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
    # Named by the answer's own row id, as the problem is talked about.
    saved = (await session.execute(select(FlatsPageCheck))).scalars().one()
    assert f"#{saved.id}</span>" in index.text
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
    assert _asks(before.text) == 1 and _asks(response.text) == 1
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

    assert _asks(response.text) == 1
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
    # Page 1 comes back only as the page before, for context: not cited.
    assert "?page=2" in response.text
    assert re.search(r'data-context="before">.*?\?page=1', response.text, re.S)
    assert len(re.findall(r"data-cited>", response.text)) == 1


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
    first = (await session.execute(select(FlatsPageCheck))).scalars().one()
    assert f"#{first.id}</span>" in back.text, "the card names the answer by its id"
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


async def test_an_answered_flag_leaves_the_open_list_and_the_card(client, session):
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
    # Resolved, so gone from the card: "we don't need to keep a record if
    # resolved" (Steph 2026-10-22). The index's Answered list still has it.
    assert "what about G2?" not in card.text
    assert "Answered: G2 sets no maximum side yard." not in card.text


async def test_the_card_names_the_zone_as_a_zone(client, session):
    # Oregon City's "I" (Institutional) read as a lettered point on the page.
    await _login(client, session)
    row = next(r for r in check._rows(check._layers()[LAYER], set()) if not r["zone"].startswith("("))
    card = await client.get(
        f"/flats/check/{LAYER}", params={"zone": row["zone"], "field": row["field"], "when": row["when"]}
    )
    assert f"<strong>the {row['zone']} zone</strong>" in card.text


def test_the_card_shows_the_page_before_and_after_the_cited_one(monkeypatch):
    # Steph could not tell whether MUE's use list ended at N or ran on to an O
    # overleaf: the page shown ended mid-list.
    layer = check._layers()[LAYER]
    row = _first_row()
    last = check._page_index(row["document"]).pages[-1].n
    cited = min(5, last - 1)
    monkeypatch.setattr(
        check, "_placed",
        lambda row: sheet.Placed(status="boxed", pages=[cited], boxes={cited: [(_BOX, "value")]}),
    )
    sheets = check._card(layer, check._Ask(row, "value"))["sheets"]

    assert [(s["page"], s["context"]) for s in sheets] == [
        (cited - 1, "before"), (cited, ""), (cited + 1, "after")
    ]
    assert not sheets[0]["boxes"] and not sheets[2]["boxes"] and sheets[1]["boxes"]


async def test_a_quote_split_across_pages_says_which_pages_it_is_boxed_on(client, session, monkeypatch):
    # Gresham Table 4.0130's row B is on one page and its note 2 four pages
    # on; only the first was in view (Steph 2026-10-22).
    await _login(client, session)
    row = _first_row()
    last = check._page_index(row["document"]).pages[-1].n
    a, b = 2, min(6, last)
    monkeypatch.setattr(
        check, "_placed",
        lambda row: sheet.Placed(status="line", pages=[a, b], boxes={a: [(_BOX, "line")], b: [(_BOX, "line")]}),
    )
    card = await client.get(
        f"/flats/check/{LAYER}", params={"zone": row["zone"], "field": row["field"], "when": row["when"]}
    )
    pointer = card.text.partition("data-boxed-pages>")[2].partition("</div>")[0]
    assert f'href="#check-sheet-{a}"' in pointer and f'href="#check-sheet-{b}"' in pointer
    assert f'id="check-sheet-{b}"' in card.text


def test_a_number_read_off_another_table_shows_the_passage_that_sends_us_there():
    # CMF's corridor front setback is quoted from Table 4.0131's TLDR column;
    # Table 4.0430 note 14 is why, and the card showed only the table: "I have
    # no evidence that the cross-table references ... are accurate".
    layer = check._layers()[LAYER]
    row = next(
        r for r in check._rows(layer, set())
        if r["zone"] == "CMF" and r["field"] == "setback_front_ft" and r["when"] == "civic_corridor"
    )
    assert row["via"] == "or/multnomah/gresham/4.0400.corridor.txt#L485-L488"
    first = check._card(layer, check._Ask(row, "value"))["sheets"][0]
    assert first.get("via") and first["boxes"]
    assert first["src"].startswith("/flats/sheet/or/multnomah/gresham/4.0400.corridor.txt")


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


def test_one_documents_set_aside_matches_the_whole_corpus_answer():
    """The per-document path must give exactly what the all-layer one does."""
    whole = check._set_aside_by_document()
    by_layer: dict[str, str] = {}
    for document in sorted(whole):
        by_layer.setdefault(document.rpartition("/")[0], document)
    sample = list(by_layer.values())[:6]
    assert sample

    for document in sample:
        assert list(check._set_aside_in(document)) == whole[document]
    assert check._set_aside_in("or/nowhere/none.txt") == ()


def test_a_cards_set_aside_surveys_one_layers_reading_queue_not_all(monkeypatch):
    from flats.encode import worklist

    document = next(iter(check._set_aside_by_document()))
    calls: list[str] = []
    real = worklist.cards

    def counting(layer, *args, **kwargs):
        calls.append(layer.layer)
        return real(layer, *args, **kwargs)

    monkeypatch.setattr(worklist, "cards", counting)
    check._set_aside_in.cache_clear()
    try:
        check._set_aside_in(document)
        check._set_aside_in(document)
    finally:
        check._set_aside_in.cache_clear()

    assert calls == [document.rpartition("/")[0]]


async def test_an_exempt_standard_is_asked_as_not_applying(client, session, monkeypatch):
    await _login(client, session)
    monkeypatch.setattr(check, "_exempt", lambda layer, row: True)

    response = await client.get(f"/flats/check/{LAYER}")

    assert "does <strong>not apply to our building</strong>" in response.text


async def test_a_townhouse_number_is_said_as_for_townhouses(client, session, monkeypatch):
    """Steph 2026-10-20: the four homes platted onto lots of their own are
    "townhouses" on a card -- "min. lot area does not apply to townhouses in
    the LDR-7 zone" -- not a sentence about platting."""
    await _login(client, session)
    row = next(r for r in check._rows(check._layers()[LAYER], set()) if r["when"] == "unit_lots")
    monkeypatch.setattr(check, "_rows", lambda layer, answered: [row])
    monkeypatch.setattr(check, "_exempt", lambda layer, row: True)

    response = await client.get(f"/flats/check/{LAYER}")

    assert "does <strong>not apply to townhomes</strong>" in response.text
    assert check._when_phrase("unit_lots") == "for townhomes"
    assert check._when_phrase("") == ""


@pytest.mark.parametrize(
    ("when", "who", "where"),
    [
        # Steph 2026-10-20: "min. frontage does not apply to townhomes in the
        # LDR-5 zone on corner lots" -- not "abuts a street on two or more
        # sides, which swaps an interior side setback for...".
        ("corner_lot+unit_lots", "townhomes", "on corner lots"),
        ("corner_lot", None, "on corner lots"),
        ("lot_sqft:>10000+", None, "on lots over 10,000 sq ft"),
        ("lot_sqft:<=10000", None, "on lots of 10,000 sq ft or less"),
        ("lot_sqft:<=<3000", None, "on lots under 3,000 sq ft"),
        ("lot_sqft:1500-2999", None, "on lots of 1,500–2,999 sq ft"),
        ("lot_sqft:3000-<5000", None, "on lots of 3,000 to under 5,000 sq ft"),
        ("lot_sqft:>7000-8000", None, "on lots over 7,000 up to 8,000 sq ft"),
        ("lot_sqft:>12000-<20000", None, "on lots over 12,000 and under 20,000 sq ft"),
        ("lot_width_ft:<=<100", None, "on lots under 100 ft wide"),
        ("lot_width_ft:70+", None, "on lots 70 ft wide or more"),
        ("lrt_station_ft:>400", None, "over 400 ft from a light-rail station"),
        (
            "corner_lot+lot_sqft:>10000++lot_width_ft:<=<100",
            None,
            "on corner lots, on lots over 10,000 sq ft and on lots under 100 ft wide",
        ),
    ],
)
def test_a_case_is_said_in_plain_words(when, who, where):
    assert check._when_parts(when) == (who, where)


def test_every_condition_a_card_can_name_reads_as_plain_words():
    """No card says "in the case where abuts a street..." or carries the
    definition's explanation ("which swaps ...") -- every case is a plain name,
    a range, or the first clause of its definition with no "which"."""
    seen = set()
    for layer in check._layers().values():
        for row in check._rows(layer, set()):
            if row["when"]:
                seen.add(row["when"])
    for when in seen:
        said = check._when_phrase(when)
        assert said, when
        assert "in the case where" not in said, (when, said)
        assert ", which" not in said, (when, said)
        assert ":" not in said and "_" not in said, (when, said)


def test_the_answers_carry_the_key_that_presses_them():
    """Steph 2026-10-20: 1-4 press the answers in order; each button says its key."""
    from pathlib import Path

    card = (Path(check.__file__).resolve().parents[2] / "templates" / "partials" / "flats_check_card.html").read_text(
        encoding="utf-8"
    )
    assert '<kbd class="check-key">{{ loop.index }}</kbd>' in card
    assert 'class="check-dock"' in card


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
    assert all(v["when"].startswith(("in the case where ", "for ", "where ")) for v in held[1:])
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
    # The id shown is Steph's "No", not the reopen row's.
    said_no = (
        await session.execute(select(FlatsPageCheck).where(FlatsPageCheck.answer == "differs"))
    ).scalars().one()
    assert f"#{said_no.id}</span>" in response.text
    assert "No, the page says something else" in response.text
    # Off the problems list until answered again; the history keeps the "No".
    assert f"{LAYER} | {no['zone']} | {no['field']}" not in (await client.get("/flats/check/problems.txt")).text
    assert await reopen.reopen(session, LAYER) == [], "a reopened question is not reopened twice"

    # Named by id, a "Yes" given about the wrong text is asked again too
    # (Rivergrove note 2, 2026-10-20); nothing else is.
    answers = await check._answers(session, LAYER)
    standing_yes = next(a for a in answers.values() if a.answer == "matches")
    named = await reopen.reopen(session, LAYER, frozenset({standing_yes.id}))
    assert [(r.zone, r.field, r.note) for r in named] == [(yes["zone"], yes["field"], "matches")]


WEB_LAYER = "or/clackamas/lake-oswego"


def _web_row() -> dict:
    """A Lake Oswego number whose cited lines state it in words we can tint."""
    layer = check._layers()[WEB_LAYER]
    for row in check._rows(layer, set()):
        assert row["web"], "fixture assumption: Lake Oswego is published only as web pages"
        if any(p["hit"] for line in check._web_text(row) for p in line["parts"]):
            return row
    raise AssertionError("no Lake Oswego number is stated in its cited lines")


def _web_footnote_row() -> tuple[dict, str]:
    """A Lake Oswego number whose cited lines carry a readable footnote."""
    layer = check._layers()[WEB_LAYER]
    for row in check._rows(layer, set()):
        if row["web"]:
            marks = check._web_marks(row["quote"])
            if marks:
                return row, marks[0]
    raise AssertionError("no Lake Oswego number has a cited footnote")


@pytest.fixture
def _no_pages(monkeypatch):
    def refuse(row):
        raise AssertionError("a web code has no page to place a box on")

    monkeypatch.setattr(check, "_placed", refuse)


async def test_a_web_code_card_shows_the_stored_text_not_a_page(client, session, _no_pages):
    await _login(client, session)
    row = _web_row()

    response = await client.get(
        f"/flats/check/{WEB_LAYER}", params={"zone": row["zone"], "field": row["field"], "when": row["when"]}
    )

    assert response.status_code == 200
    assert "data-web-code" in response.text
    assert "web code &mdash; no printed page" in response.text
    assert "check-web-cited" in response.text
    assert "check-web-num" in response.text
    assert "/flats/sheet/" not in response.text
    assert "data-flag" in response.text
    assert "name=\"flag_web\"" in response.text
    assert "data-answer=\"matches\"" in response.text


async def test_a_web_code_answer_is_stored_in_the_same_table_with_no_page(client, session, _no_pages):
    user = await _login(client, session)
    row = _web_row()

    response = await client.post(
        "/ui/flats/check",
        data={
            "layer_id": WEB_LAYER,
            "zone": row["zone"],
            "field": row["field"],
            "when": row["when"],
            "question": "value",
            "answer": "differs",
            "says": "something else",
        },
    )

    assert response.status_code == 200
    saved = (await session.execute(select(FlatsPageCheck))).scalars().one()
    assert (saved.page, saved.placed) == (None, "web")
    assert saved.fingerprint == row["mark"]
    assert saved.quote == row["quote"]
    assert saved.reviewer_user_id == user.id
    assert len(saved.book_sha256) == 64
    text = await client.get("/flats/check/problems.txt")
    assert "web code, no printed page" in text.text


async def test_a_web_code_footnote_not_printed_on_the_number_is_refused(client, session, _no_pages):
    await _login(client, session)
    row = _web_row()
    form = {"layer_id": WEB_LAYER, "zone": row["zone"], "field": row["field"], "when": row["when"]}

    response = await client.post("/ui/flats/check", data={**form, "question": "note:99", "answer": "no_change"})

    assert "not printed on this number" in response.text
    assert (await session.execute(select(FlatsPageCheck))).first() is None


async def test_a_web_code_flag_is_stored_like_a_page_flag_with_no_page(client, session, _no_pages):
    await _login(client, session)
    row = _web_row()
    form = {"layer_id": WEB_LAYER, "zone": row["zone"], "field": row["field"], "when": row["when"]}

    response = await client.post(
        "/ui/flats/check",
        data={**form, "question": "value", "action": "flag", "flag_web": "1", "comment": "a setback nobody encoded"},
    )

    assert "flag saved" in response.text
    assert "a setback nobody encoded" in response.text
    assert 'name="question" value="value"' in response.text
    saved = (await session.execute(select(FlatsPageCheck))).scalars().one()
    assert (saved.question, saved.answer, saved.page, saved.placed) == ("page:web", "unmarked", None, "web")
    assert len(saved.book_sha256) == 64
    text = await client.get("/flats/check/problems.txt")
    assert "web code, no printed page" in text.text
    assert "the page says: a setback nobody encoded" in text.text


async def test_a_flag_on_a_printed_card_cannot_name_the_web(client, session):
    await _login(client, session)
    row = _first_row()

    response = await client.post(
        "/ui/flats/check",
        data=_form(row, action="flag", flag_web="1", comment="nope"),
    )

    assert "pick one of the answers" in response.text
    assert (await session.execute(select(FlatsPageCheck))).first() is None


async def test_a_web_code_footnote_is_asked_after_the_number_and_answered_with_no_page(
    client, session, _no_pages, monkeypatch
):
    await _login(client, session)
    row = check._rows(check._layers()[WEB_LAYER], set())[0]
    monkeypatch.setattr(check, "_web_marks", lambda quote: ("2",))
    form = {"layer_id": WEB_LAYER, "zone": row["zone"], "field": row["field"], "when": row["when"]}

    after = await client.post("/ui/flats/check", data={**form, "question": "value", "answer": "matches"})

    assert "Note <strong>2</strong> is printed in the cited text of this number" in after.text
    assert "data-flag" in after.text
    assert "data-web-code" in after.text
    await client.post("/ui/flats/check", data={**form, "question": "note:2", "answer": "have_it"})
    saved = (await session.execute(select(FlatsPageCheck).order_by(FlatsPageCheck.id))).scalars().all()
    assert [(s.question, s.answer, s.page, s.placed) for s in saved] == [
        ("value", "matches", None, "web"),
        ("note:2", "have_it", None, "web"),
    ]


async def test_a_web_footnote_card_highlights_its_marker(client, session, _no_pages):
    await _login(client, session)
    row, mark = _web_footnote_row()
    form = {"layer_id": WEB_LAYER, "zone": row["zone"], "field": row["field"], "when": row["when"]}

    response = await client.post(
        "/ui/flats/check",
        data={**form, "question": f"note:{mark}", "answer": "invalid"},
    )

    assert f"Note <strong>{mark}</strong> is printed in the cited text of this number" in response.text
    assert f'<span class="check-web-mark">{mark}</span>' in response.text


async def test_printed_numbers_queue_before_web_numbers_and_keep_their_card(client, session):
    await _login(client, session)
    rows = check._rows(check._layers()["or/clackamas/happy-valley"], set())
    flags = [r["web"] for r in rows]
    assert flags == sorted(flags), "printed numbers come first"
    assert not flags[0] and flags[-1], "fixture assumption: Happy Valley has both kinds"

    response = await client.get(f"/flats/check/{LAYER}")

    assert "data-web-code" not in response.text
    assert "check-box-value" in response.text
    assert f"/flats/sheet/{_first_row()['document']}?page=1" in response.text

async def test_walking_every_web_number_reads_each_stored_text_once(monkeypatch):
    """The queue walk once read a file per web number (~1,500 reads); it must
    cost one read per distinct document. Counts reads, not seconds."""
    from types import SimpleNamespace

    from flats.provenance.store import ProvenanceStore

    reads: list[str] = []
    real = ProvenanceStore.load

    def counting(self, document, *a, **kw):
        reads.append(document)
        return real(self, document, *a, **kw)

    monkeypatch.setattr(ProvenanceStore, "load", counting)
    for cached in (check._web_lines, check._web_marks):
        cached.cache_clear()

    web_documents: set[str] = set()
    for layer in check._layers().values():
        rows = [r for r in check._rows(layer, set()) if r["web"]]
        web_documents |= {r["document"] for r in rows}
        answers = {
            (layer.layer, r["zone"], r["field"], r["when"], "value"): SimpleNamespace(
                fingerprint=r["mark"], answer="matches", id=0
            )
            for r in rows
        }
        reads.clear()
        for _ in check._questions(layer, rows, answers):
            pass
        assert len(reads) <= len({r["document"] for r in rows}), "a web text was read per number"
    assert web_documents, "fixture assumption: some numbers are in web-published codes"


async def test_a_choice_word_is_asked_as_a_reading_not_as_printed_words(client, session):
    # Steph 2026-10-19, Durham: "front on a corner lot: both" and "driveway
    # street: any" were asked as "does the page say both?" -- the page defines
    # no corner front and names no street, so it read as an invented definition.
    await _login(client, session)
    layer_id = "or/washington/durham"
    row = next(r for r in check._rows(check._layers()[layer_id], set()) if r["field"] == "front_lot_line_corner")
    card = await client.get(
        f"/flats/check/{layer_id}", params={"zone": row["zone"], "field": row["field"], "when": row["when"]}
    )
    assert card.status_code == 200
    assert "every street line takes the front setback" in card.text
    assert "This is our reading, not words printed on the page" in card.text
    assert "no front lot line defined" in card.text
    assert "Does the page say <strong" not in card.text


def test_the_queue_goes_by_row_one_data_point_at_a_time():
    # Steph 2026-10-19: Gresham's cards flipped between min and max density.
    # Within a document the queue finishes one standard before the next and
    # never comes back to it.
    rows = [r for r in check._rows(check._layers()[LAYER], set()) if not r["web"]]
    seen: set[tuple[str, str]] = set()
    previous = None
    for r in rows:
        here = (r["document"], r["field"])
        if here != previous:
            assert here not in seen, f"{here} comes back after leaving"
            seen.add(here)
        previous = here


def test_a_web_code_marks_the_word_that_says_a_standard_does_not_apply():
    # Steph 2026-10-20: "none", "NA" and "N/A" are boxed as a number is.
    assert [t for t in ("None", "NA", "N/A", "n.a.", "20", "Nonconforming") if check._states(t, None)] == [
        "None",
        "NA",
        "N/A",
        "n.a.",
    ]
    assert check._states("20", 20) and not check._states("NA", 20)


def test_a_derived_number_is_asked_as_the_page_prints_it():
    """Steph 2026-10-20 answered "differs" to "does the page say 20 ft?" for
    Gresham LDR-5's rear setback: the table prints 15 ft, and the 20 is that
    plus the 7.0420(G)(1) step-back. The card asks about the 15 and boxes it
    under the rear column, then says what we hold."""
    layer = check._layers()[LAYER]
    row = next(
        r for r in check._rows(layer, set()) if (r["zone"], r["field"], r["when"]) == ("LDR-5", "setback_rear_ft", "")
    )
    assert (row["value"], row["printed"]) == (20, 15)

    card = check._card(layer, check._Ask(row, "value"))

    assert (card["printed"], card["value"]) == ("15 ft", "20 ft")
    assert "step-back" in card["derived_why"]
    assert card["placed"] in ("boxed", "column")


def test_a_number_printed_as_held_says_nothing_about_derivation():
    layer = check._layers()[LAYER]
    row = next(
        r for r in check._rows(layer, set()) if (r["zone"], r["field"], r["when"]) == ("TLDR", "setback_rear_ft", "")
    )
    card = check._card(layer, check._Ask(row, "value"))
    assert row["printed"] == row["value"] == 15
    assert "printed" not in card


def test_a_number_read_off_another_zones_page_says_why_and_links_that_page():
    """Gresham's corridor CMF height is read off the residential table's TLDR
    column (note 14). Steph found no CMF on the page and the source link went
    to the corridor chapter (2026-10-20). The card says why it is read there,
    and the link follows the page shown."""
    layer = check._layers()[LAYER]
    rows = {(r["zone"], r["field"], r["when"]): r for r in check._rows(layer, set())}
    row = rows[("CMF", "max_height_ft", "civic_corridor")]
    assert "4.0100" in row["document"]

    card = check._card(layer, check._Ask(row, "value"))

    assert card["borrowed"] == row["cite"]
    assert card["url"] == check._source_url(row["document"])
    # A zone the page prints with its note mark run on ("LDR-54") is on it.
    tldr = check._card(layer, check._Ask(rows[("LDR-5", "setback_rear_ft", "")], "value"))
    assert "borrowed" not in tldr


def test_a_number_read_off_a_note_shows_the_table_that_calls_it(monkeypatch):
    """CMF's corner townhouse frontage is quoted from note 11 alone; the card
    shows the table whose CMF column calls the note, and every page between
    (Steph 2026-10-20)."""
    layer = check._layers()["or/multnomah/gresham"]
    row = next(
        r
        for r in check._rows(layer, set())
        if (r["zone"], r["field"], r["when"]) == ("CMF", "min_frontage_ft", "corner_lot+unit_lots")
    )
    # Note 11 is printed on page 12 of the corridor chapter; its table on 8.
    monkeypatch.setattr(check, "_placed", lambda r: sheet.Placed(status="boxed", pages=[12], boxes={12: [(_BOX, "value")]}))
    assert check._calling_page(layer, row) == 8

    card = check._card(layer, check._Ask(row, "value"))

    assert [(sh["page"], sh.get("context")) for sh in card["sheets"]] == [
        (7, "before"),
        (8, "that calls the note"),
        (9, "between"),
        (10, "between"),
        (11, "between"),
        (12, ""),
        (13, "after"),
    ]


def test_a_borrowed_number_is_read_under_the_zone_it_borrows():
    """CMF's corridor height is read off Table 4.0130 H's TLDR column; the box
    went on LDR-5's 35 ft, the first of seven (Steph 2026-10-20)."""
    layer = check._layers()["or/multnomah/gresham"]
    rows = {(r["zone"], r["field"], r["when"]): r for r in check._rows(layer, set())}
    assert check._column_zone(rows[("CMF", "max_height_ft", "civic_corridor")]) == "TLDR"
    # A zone printed on its own page keeps its own column.
    assert check._column_zone(rows[("TLDR", "max_height_ft", "")]) == "TLDR"


def test_a_number_held_from_a_note_shows_the_note():
    """MDR-24's minimum density is waived under 11,000 sq ft by note 5, which
    Gresham prints on the next page; the card shows the note's words
    (Steph 2026-10-20)."""
    layer = check._layers()["or/multnomah/gresham"]
    row = next(
        r
        for r in check._rows(layer, set())
        if (r["zone"], r["field"]) == ("MDR-24", "min_density_du_per_acre") and r["when"]
    )
    card = check._card(layer, check._Ask(row, "value"))
    assert any("11,000 square feet" in text for text in card["row_notes"])

    # The whole note, past its cited first line.
    row = next(
        r
        for r in check._rows(layer, set())
        if (r["zone"], r["field"], r["when"]) == ("MDR-24", "min_frontage_ft", "corner_lot+unit_lots")
    )
    card = check._card(layer, check._Ask(row, "value"))
    assert any(text.endswith("no alley or shared access.") for text in card["row_notes"]), card["row_notes"]


def test_a_figure_printed_in_another_unit_is_asked_in_that_unit():
    """A density stored from "1,742 square feet per dwelling" is asked as
    that, not as "1,742 units per acre" (2026-10-20); a figure with no unit
    of its own to ask asks about the number held."""
    layer = check._layers()["or/clackamas/_unincorporated"]
    rows = {(r["zone"], r["field"], r["when"]): r for r in check._rows(layer, set())}
    card = check._card(layer, check._Ask(rows[("HDR", "min_density_du_per_acre", "")], "value"))
    assert card["printed"] == "1,742 sq ft per home"
    assert check._printed_said(layer, rows[("PMU2", "min_lot_sqft", "")], 2) == "2 acres"

    portland = check._layers()["or/multnomah/portland"]
    ir = next(r for r in check._rows(portland, set()) if (r["zone"], r["field"], r["when"]) == ("IR", "setback_side_ft", ""))
    assert "printed" not in check._card(portland, check._Ask(ir, "value"))


def test_a_note_on_a_tables_title_is_asked_of_every_number_in_one_run(monkeypatch):
    """Steph 2026-10-21 (FOLLOWUPS 103(e)): "ask all of the title footnotes
    in a row so I can quickly process them". Every other question keeps its
    place; the title's note is asked last, number after number."""
    layer = check._layers()[LAYER]
    rows = [
        {"zone": z, "field": "setback_front_ft", "when": "", "web": False, "quote": "x#L1", "document": "d", "mark": "m"}
        for z in ("A", "B", "C")
    ]
    title = sheet.Marker("1", "title", sheet.Box(0.6, 0.08, 0.61, 0.09))
    own = {
        "A": [sheet.Marker("5", "number", _BOX), title],
        "B": [title, sheet.Marker("2", "column", _BOX)],
        "C": [title],
    }
    monkeypatch.setattr(
        check, "_placed", lambda row: sheet.Placed(status="boxed", markers=own[row["zone"]], marker_page=12)
    )

    class Said:
        answer, fingerprint = "matches", "m"

    answers = {(LAYER, z, "setback_front_ft", "", "value"): Said() for z in ("A", "B", "C")}
    answers[(LAYER, "C", "setback_front_ft", "", "note:1")] = Said()

    asked = [(a.row["zone"], a.question) for a in check._questions(layer, rows, answers)]

    # C's note 1 is answered already and is not asked again.
    assert asked == [("A", "note:5"), ("B", "note:2"), ("A", "note:1"), ("B", "note:1")]


def _footnoted_rows() -> list[dict]:
    """A zone's front setback read off the table, and an exception to it read
    off note 5 alone, in the same document."""
    rows = [
        {"zone": "A", "field": "setback_front_ft", "when": "", "web": False, "quote": "d#L10",
         "document": "d", "mark": "m", "in_note": "", "value": 10},
        {"zone": "A", "field": "setback_front_ft", "when": "fronts_cul_de_sac", "web": False,
         "quote": "d#L40", "document": "d", "mark": "m", "in_note": "5", "value": 5},
    ]
    check._carry(rows)
    return rows


class _Said:
    def __init__(self, answer: str = "matches", at: int = 0):
        from datetime import datetime, timedelta

        self.answer, self.fingerprint, self.id, self.question = answer, "m", 1, "value"
        self.decided_at = datetime(2026, 10, 21) + timedelta(minutes=at)
        self.note, self.says = "differs", ""


def test_a_number_read_off_a_footnote_is_asked_as_its_cells_note(monkeypatch):
    """Steph 2026-10-21: "I should only be asked about footnotes in the
    context of being a footnote, not its own ruling." The exception has no
    card of its own; the cell's card asks note 5, even where the marker on
    the cell was not found."""
    layer = check._layers()[LAYER]
    rows = _footnoted_rows()
    monkeypatch.setattr(check, "_placed", lambda row: sheet.Placed(status="boxed", markers=[], marker_page=1))

    asked = [(a.row["when"], a.question) for a in check._questions(layer, rows, {})]
    assert asked == [("", "value")]

    answers = {(LAYER, "A", "setback_front_ft", "", "value"): _Said()}
    asked = [(a.row["when"], a.question) for a in check._questions(layer, rows, answers)]
    assert asked == [("", "note:5")]
    counts = check._counts(layer, rows, answers)
    assert (counts["numbers"], counts["checked"]) == (2, 1)

    # Answering the note answers the exception too.
    answers[(LAYER, "A", "setback_front_ft", "", "note:5")] = _Said("have_it")
    assert list(check._questions(layer, rows, answers)) == []
    assert check._counts(layer, rows, answers)["checked"] == 2


def test_an_answer_already_given_on_the_footnotes_own_card_still_stands(monkeypatch):
    """The exception's old "does the page say" answer is not thrown away and
    the note is not asked a second time."""
    layer = check._layers()[LAYER]
    rows = _footnoted_rows()
    monkeypatch.setattr(check, "_placed", lambda row: sheet.Placed(status="boxed", markers=[], marker_page=1))
    answers = {
        (LAYER, "A", "setback_front_ft", "", "value"): _Said(),
        (LAYER, "A", "setback_front_ft", "fronts_cul_de_sac", "value"): _Said(),
    }

    assert list(check._questions(layer, rows, answers)) == []
    assert check._counts(layer, rows, answers)["checked"] == 2


def test_a_footnote_with_no_cell_to_ask_it_on_keeps_its_card():
    rows = _footnoted_rows()[1:]
    check._carry(rows)

    assert "carried_by" not in rows[0]
    assert rows[0]["in_note"] == "5"


async def test_this_is_a_footnote_is_an_answer_that_files_a_problem(client, session):
    await _login(client, session)
    row = _first_row()

    card = await client.get(f"/flats/check/{LAYER}")
    assert 'data-answer="footnote"' in card.text
    await client.post("/ui/flats/check", data=_form(row, answer="footnote"))

    saved = (await session.execute(select(FlatsPageCheck))).scalars().one()
    assert saved.answer == "footnote"
    index = await client.get("/flats/check")
    assert "This is a footnote" in index.text


def test_a_footnote_reopened_on_its_own_card_is_asked_on_its_cells_note(monkeypatch):
    """A reopen on the exception's old card is not lost when the question
    moves: the cell's note is asked again, even over an older answer to it,
    until it is answered after the reopening."""
    layer = check._layers()[LAYER]
    rows = _footnoted_rows()
    monkeypatch.setattr(check, "_placed", lambda row: sheet.Placed(status="boxed", markers=[], marker_page=1))
    answers = {
        (LAYER, "A", "setback_front_ft", "", "value"): _Said(),
        (LAYER, "A", "setback_front_ft", "", "note:5"): _Said("no_change", at=1),
        (LAYER, "A", "setback_front_ft", "fronts_cul_de_sac", "value"): _Said(check.REOPENED, at=2),
    }

    assert [a.question for a in check._questions(layer, rows, answers)] == ["note:5"]
    assert check._counts(layer, rows, answers)["checked"] == 1

    answers[(LAYER, "A", "setback_front_ft", "", "note:5")] = _Said("have_it", at=3)
    assert list(check._questions(layer, rows, answers)) == []
    assert check._counts(layer, rows, answers)["checked"] == 2


def test_a_number_that_needs_two_sources_is_not_asked_on_one_page(monkeypatch):
    """Steph 2026-10-22: "this is asking for comparing 2 PDFs and we only show
    one." A number sent to its page by a cross-reference, read off a page that
    never names its zone, or changed by a district written in another
    document waits for the two-source check: not asked, not counted, and
    counted apart."""
    layer = check._layers()[LAYER]
    monkeypatch.setattr(check, "_zone_off_page", lambda document, line, zone: zone == "B")
    base = {"field": "setback_front_ft", "when": "", "web": False, "quote": "d#L10", "document": "d",
            "mark": "m", "in_note": "", "value": 10, "line": 10}
    rows = [
        {**base, "zone": "A"},
        {**base, "zone": "A", "when": "rockwood_design_district", "quote": "e#L5", "document": "e"},
        {**base, "zone": "B"},
        {**base, "zone": "C", "via": "f#L1"},
    ]
    parents = {(r["zone"], r["field"]): r for r in rows if not r["when"]}
    for r in rows:
        r["two_source"] = check._two_source(r, parents.get((r["zone"], r["field"])))
    check._carry(rows)
    monkeypatch.setattr(check, "_placed", lambda row: sheet.Placed(status="boxed", markers=[], marker_page=1))

    assert [r["two_source"] for r in rows] == ["", "modified", "borrowed", "via"]
    assert [(a.row["zone"], a.row["when"]) for a in check._questions(layer, rows, {})] == [("A", "")]
    counts = check._counts(layer, rows, {})
    assert (counts["numbers"], counts["two_source"]) == (1, 3)
