"""FLATS rule-review pages.

The pages exist so a reviewer can compare an encoded standard against the line
of code it was read from without checking out the repository. What these tests
hold to is that pairing: the value renders, the quote renders, and a quote that
cannot be resolved says so instead of rendering nothing.
"""

from __future__ import annotations

import re

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ui_flats import _cited_lines
from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


async def _login(client: AsyncClient, session: AsyncSession):
    _org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)
    return user


def _hunt(
    layer_id: str,
    zone: str,
    field: str,
    believed: object,
    documents: list[str] | None = None,
) -> dict:
    """One row of the held-out-standards queue, built by hand.

    Every address in the real queue is an encoding gap, which means filling the
    gap deletes the row. Tests that reached into ``_queue()`` for a live
    address therefore went red on the day a jurisdiction was finished, and
    reported it as a broken search page. What they are actually about is how
    candidate lines are ranked and shown -- ``_candidates`` -- and that takes a
    row, not a queue.

    ``documents`` narrows the search to one chapter. Candidates come back
    grouped by document in the order the layer declares them, so a claim about
    ranking is a claim about ranking *within* a document; spread across fifteen
    it is a claim about which chapter happens to be declared first.
    """
    from app.api.routers import ui_flats as ui

    layer = ui._layers()[layer_id]
    return {
        "layer": layer_id,
        "label": layer.label,
        "zone": zone,
        "field": field,
        "believed": believed,
        "cite": "",
        "url": "",
        "documents": documents or [layer.document_path(doc.id) for doc in layer.code],
    }


async def test_the_index_lists_every_jurisdiction(client: AsyncClient, session: AsyncSession):
    await _login(client, session)

    response = await client.get("/flats")

    assert response.status_code == 200
    # Portland is the deepest layer in the corpus and the one the screen was
    # built against; if the loader silently returned nothing, this is what
    # would go missing.
    assert "Portland" in response.text
    assert "Zoning rules" in response.text


async def test_a_layer_page_shows_a_standard_and_its_citation(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    response = await client.get("/flats/or/multnomah/gresham")

    assert response.status_code == 200
    assert "LDR-5" in response.text
    assert "setback_front_ft" in response.text
    # The quote is the whole point of the page: a number with no line behind it
    # is the thing this system exists to stop shipping.
    assert "4.0100.residential.txt#L400" in response.text


async def test_an_unknown_layer_falls_back_to_the_index(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    response = await client.get("/flats/or/multnomah/atlantis")

    assert response.status_code == 404
    assert "atlantis" in response.text


async def test_the_quote_partial_marks_the_cited_lines(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    response = await client.get(
        "/ui/flats/quote",
        params={"ref": "or/multnomah/gresham/4.0100.residential.txt#L400"},
        headers={"hx-request": "true"},
    )

    assert response.status_code == 200
    # The row Gresham states the quadplex setbacks on, and the lines around it —
    # a reviewer needs the heading above the row to know which block it is in.
    assert "LDR-54" in response.text
    assert "Townhouse" in response.text or "Quadplex" in response.text


async def test_a_quote_that_cannot_be_resolved_says_so(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    response = await client.get(
        "/ui/flats/quote",
        params={"ref": "or/nowhere/no-such-city/99.txt#L1"},
        headers={"hx-request": "true"},
    )

    assert response.status_code == 200
    assert "Source unavailable" in response.text


async def test_the_pages_require_a_session(client: AsyncClient):
    response = await client.get("/flats", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


async def test_a_quote_reference_cannot_walk_out_of_the_store(
    client: AsyncClient, session: AsyncSession
):
    # The reference arrives as a query parameter, so it is attacker-chosen text
    # that would otherwise be joined onto a filesystem root. Only documents the
    # store actually holds are served, and the refusal says nothing about what
    # is or is not on disk.
    await _login(client, session)

    response = await client.get(
        "/ui/flats/quote",
        params={"ref": "../../../../etc/passwd#L1"},
        headers={"hx-request": "true"},
    )

    assert response.status_code == 200
    assert "no such stored document" in response.text
    assert "root:" not in response.text


def text_query():
    """Every recorded verdict, oldest first."""
    from sqlalchemy import select

    from app.models.flats import FlatsRuleSignature as S

    return select(S.layer, S.zone, S.field, S.when_key, S.value, S.verdict).order_by(
        S.decided_at
    )


# --- recording a reviewer's verdict -----------------------------------
#
# The verdict is not trust. It lands in an inbox, and a drain writes the
# confirmations into the repository's verification log, where a signature is
# hashed over the value and its citation. What these tests hold to is that the
# inbox only ever accepts addresses the rule files actually hold, and that the
# number signed is the one the server rendered rather than one the browser sent.


async def _sign(client: AsyncClient, **over):
    body = {
        "layer_id": "or/clackamas/wilsonville",
        "zone": "R",
        "field": "setback_side_ft",
        "when": "",
        "verdict": "verified",
    }
    body.update(over)
    return await client.post("/ui/flats/sign", data=body, headers={"hx-request": "true"})


async def test_a_verdict_is_recorded_and_marked_pending(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    response = await _sign(client)

    assert response.status_code == 200
    assert "confirmed" in response.text
    # Pending is the honest state: nothing is verified until the drain writes
    # it into the repository and the next release ships it.
    assert "queued" in response.text

    rows = (await session.execute(text_query())).all()
    assert len(rows) == 1
    layer, zone, field, when, value, verdict = rows[0]
    assert (layer, zone, field, when, verdict) == (
        "or/clackamas/wilsonville",
        "R",
        "setback_side_ft",
        "",
        "verified",
    )
    # Read from the rule files, not from the form.
    assert value == 5


async def test_a_variant_is_signed_on_its_own_address(
    client: AsyncClient, session: AsyncSession
):
    # Wilsonville's small-lot side setback is five feet at one storey and seven
    # at two. A reviewer reads one sentence and signs for that one.
    await _login(client, session)

    response = await _sign(client, when="lot_sqft:<=10000+multi_story")

    assert response.status_code == 200
    rows = (await session.execute(text_query())).all()
    assert rows[0][3] == "lot_sqft:<=10000+multi_story"
    assert rows[0][4] == 7


async def test_a_verdict_on_a_value_we_do_not_hold_is_refused(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    response = await _sign(client, field="setback_to_the_moon_ft")

    assert response.status_code == 400
    assert (await session.execute(text_query())).all() == []


async def test_an_invented_verdict_is_refused(client: AsyncClient, session: AsyncSession):
    await _login(client, session)

    response = await _sign(client, verdict="brilliant")

    assert response.status_code == 400
    assert (await session.execute(text_query())).all() == []


async def test_signing_requires_a_session(client: AsyncClient):
    response = await client.post(
        "/ui/flats/sign",
        data={
            "layer_id": "or/clackamas/wilsonville",
            "zone": "R",
            "field": "setback_side_ft",
            "verdict": "verified",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303


# --- what the page must never print ------------------------------------
#
# Jinja resolves an attribute before a key, so a summary dict with a "values"
# key renders `dict.values` — the bound method — once per row. It reads as
# "<built-in method values of dict object at 0x7ff...>" where a count belongs,
# and nothing fails: the page returns 200 with a table full of addresses.


async def test_no_page_renders_a_python_object_where_a_number_belongs(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    for url in ("/flats", "/flats/or/clackamas/wilsonville"):
        page = await client.get(url)

        assert page.status_code == 200
        assert "built-in method" not in page.text
        assert "object at 0x" not in page.text


# --- plans: the question asked the other way round ---------------------
#
# The rule pages say what a zone requires. The plan pages say what a lot would
# have to be for a building we can actually deliver to be legal there — the
# same standards, read from the product end. Nothing on them touches parcel
# data, so they answer for markets we hold no parcels in.


async def test_the_plans_page_lists_the_catalog(client: AsyncClient, session: AsyncSession):
    await _login(client, session)

    page = await client.get("/flats/plans")

    assert page.status_code == 200
    assert "Plans" in page.text
    # The catalog ships two pods. A page that loaded no designs still renders,
    # which is why the count is asserted rather than the status code alone.
    assert page.text.count("/flats/plans/pod") >= 2


async def test_plans_is_not_swallowed_by_the_layer_route(
    client: AsyncClient, session: AsyncSession
):
    # /flats/{layer_id:path} matches "plans" happily and would 404 it as a
    # jurisdiction. Registration order is the only thing keeping this route.
    await _login(client, session)

    page = await client.get("/flats/plans")

    assert page.status_code == 200
    assert "No rule layer" not in page.text


async def test_a_plan_page_says_what_lot_the_building_needs(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    page = await client.get("/flats/plans/pod56x36@1")

    assert page.status_code == 200
    assert "Lot area" in page.text
    assert "What sets the size" in page.text
    # Every encoded zone is listed, including ones that say no — a zone that
    # refuses a fourplex is a fact about the market, not a row to hide.
    assert "Portland" in page.text


async def test_the_plat_path_is_a_control_not_a_second_catalog_entry(
    client: AsyncClient, session: AsyncSession
):
    # Four townhouse lots ask for the minimum lot area four times. The same
    # building, the same zones, a different number.
    await _login(client, session)

    one = await client.get("/flats/plans/pod56x36@1?plat=one_lot")
    four = await client.get("/flats/plans/pod56x36@1?plat=unit_lots")

    assert one.status_code == four.status_code == 200
    assert one.text != four.text


async def test_an_unknown_plan_says_so(client: AsyncClient, session: AsyncSession):
    await _login(client, session)

    page = await client.get("/flats/plans/nosuchpod@1")

    assert page.status_code == 404
    assert "nosuchpod@1" in page.text


async def test_the_plan_pages_print_no_python_objects_either(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    for url in ("/flats/plans", "/flats/plans/pod56x36@1"):
        page = await client.get(url)

        assert page.status_code == 200
        assert "built-in method" not in page.text
        assert "object at 0x" not in page.text


# --- review by passage -------------------------------------------------
#
# The rules table is ordered by zone, so a table row that states a dozen
# standards is a dozen entries scattered down it, each opening the same lines
# of the same document. Grouped by the passage they cite, that is one card:
# the text once, every number claiming it beside it. These tests hold to the
# grouping being real (the card signs what it displayed and nothing else) and
# to what it hides being only what is already decided.


async def test_the_review_page_groups_numbers_under_the_text_they_cite(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    response = await client.get("/flats/review/or/clackamas/wilsonville")

    assert response.status_code == 200
    assert "Confirm all" in response.text
    assert "setback_side_ft" in response.text


async def test_review_is_not_swallowed_by_the_layer_route(
    client: AsyncClient, session: AsyncSession
):
    # /flats/{layer:path} is greedy and would answer this with a 404 index.
    await _login(client, session)

    response = await client.get("/flats/review/or/clackamas/wilsonville")

    assert "Review Wilsonville" in response.text


async def test_signing_a_passage_signs_every_number_it_displayed(
    client: AsyncClient, session: AsyncSession
):
    """A card of many numbers, signed once.

    The card is chosen for having more than one row rather than taken off the
    top of the page: the first card in a queue can be a single value citing
    two stretches of its own, and signing that proves nothing about whether
    the whole passage travels together.
    """
    from app.api.routers import ui_flats as ui

    await _login(client, session)
    layer_id = "or/clackamas/wilsonville"
    card = next(c for c in ui._passages(ui._layers()[layer_id], {}) if len(c["rows"]) > 1)

    response = await client.post(
        "/ui/flats/sign-passage",
        data={"layer_id": layer_id, "ref": card["ref"], "verdict": "verified"},
        headers={"hx-request": "true"},
    )

    assert response.status_code == 200
    rows = (await session.execute(text_query())).all()
    assert len(rows) == len(card["rows"]), "every number the card listed, and no other"
    # The numbers come from the rule files rather than from the form.
    assert {r[5] for r in rows} == {"verified"}
    assert {(r[1], r[2], r[3]) for r in rows} == {
        (one["zone"], one["field"], one["when"]) for one in card["rows"]
    }


async def test_a_passage_that_names_two_stretches_does_not_sign_what_lies_between(
    client: AsyncClient, session: AsyncSession
):
    """The card that certified a hundred and seventeen numbers off one click.

    A value read off a table row and the footnote printed pages under it cites
    both. Membership used to be containment in the range covering the two, so
    the card claimed every standard printed in between — a hundred and four of
    them in one Wilsonville table — and "Confirm all" signed the lot without
    any of it having been on screen.
    """
    from app.api.routers import ui_flats as ui

    await _login(client, session)
    layer_id = "or/clackamas/wilsonville"
    cards = ui._passages(ui._layers()[layer_id], {})
    split = next(c for c in cards if "," in c["ref"].partition("#L")[2])
    assert len(split["rows"]) == 1, "fixture assumption: one value cites both stretches"
    hull = ui._span(split["ref"])
    swallowed = [
        c for c in cards if c is not split and (ui._span(c["ref"]) or (0, 0))[0] > hull[0]
        and (ui._span(c["ref"]) or (0, 0))[1] < hull[1]
    ]
    assert swallowed, "fixture assumption: whole cards sit between the two stretches"

    await client.post(
        "/ui/flats/sign-passage",
        data={"layer_id": layer_id, "ref": split["ref"], "verdict": "verified"},
        headers={"hx-request": "true"},
    )

    signed = {(r[1], r[2], r[3]) for r in (await session.execute(text_query())).all()}

    assert signed == {
        (one["zone"], one["field"], one["when"]) for one in split["rows"]
    }, "a verdict reached a number the card never printed"


async def test_a_passage_verdict_never_reaches_a_number_it_did_not_show(
    client: AsyncClient, session: AsyncSession
):
    # The set is rebuilt from the rules, so what it must not do is widen: a
    # value citing a different passage stays untouched, and a value already
    # decided is not signed a second time under a verdict it did not get.
    await _login(client, session)
    page = await client.get("/flats/review/or/clackamas/wilsonville")
    ref = _first_ref(page.text)

    await client.post(
        "/ui/flats/sign-passage",
        data={"layer_id": "or/clackamas/wilsonville", "ref": ref, "verdict": "verified"},
        headers={"hx-request": "true"},
    )
    signed = {(r[1], r[2], r[3]) for r in (await session.execute(text_query())).all()}

    await client.post(
        "/ui/flats/sign-passage",
        data={"layer_id": "or/clackamas/wilsonville", "ref": ref, "verdict": "rejected"},
        headers={"hx-request": "true"},
    )
    after = (await session.execute(text_query())).all()

    assert {(r[1], r[2], r[3]) for r in after} == signed, "no second verdict on a decided value"
    assert {r[5] for r in after} == {"verified"}


async def test_a_decided_number_leaves_the_queue(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    before = await client.get("/flats/review/or/clackamas/wilsonville")
    ref = _first_ref(before.text)

    await client.post(
        "/ui/flats/sign-passage",
        data={"layer_id": "or/clackamas/wilsonville", "ref": ref, "verdict": "verified"},
        headers={"hx-request": "true"},
    )
    after = await client.get("/flats/review/or/clackamas/wilsonville")

    assert ref not in after.text
    assert before.text.count("Confirm all") - after.text.count("Confirm all") == 1


async def test_a_passage_verdict_on_a_layer_we_do_not_hold_is_refused(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    response = await client.post(
        "/ui/flats/sign-passage",
        data={"layer_id": "or/atlantis", "ref": "x#L1", "verdict": "verified"},
        headers={"hx-request": "true"},
    )

    assert response.status_code == 400
    assert (await session.execute(text_query())).all() == []


async def test_reviewing_requires_a_session(client: AsyncClient):
    assert (await client.get("/flats/review/or/clackamas/wilsonville")).status_code == 303
    assert (
        await client.post(
            "/ui/flats/sign-passage",
            data={"layer_id": "or/clackamas/wilsonville", "ref": "x#L1", "verdict": "verified"},
        )
    ).status_code == 303


def _first_ref(html: str) -> str:
    """The citation of the first card on the page."""
    import re

    found = re.search(r'name="ref" value="([^"]+)"', html)
    assert found, "the review page renders no passage to sign"
    return found.group(1)


async def test_citations_a_few_lines_apart_are_one_reading():
    # A zone's dimensional standards are cited line by line — no two of the
    # references are equal, and grouping on the string alone leaves a table
    # row as a dozen separate cards showing a dozen overlapping windows.
    from app.api.routers.ui_flats import _cluster

    table = [(138, 138), (142, 142), (151, 151), (154, 154), (159, 159), (161, 161)]

    assert _cluster(table) == [table]


async def test_a_citation_in_another_section_starts_its_own_card():
    from app.api.routers.ui_flats import _cluster

    # West Linn states the use permission at L63 and the dimensions at L138.
    assert _cluster([(63, 63), (138, 138), (142, 142)]) == [[(63, 63)], [(138, 138), (142, 142)]]


async def test_a_chain_stops_before_it_becomes_a_chapter():
    from app.api.routers.ui_flats import _SPAN, _cluster

    walk = [(n, n) for n in range(1, 400, 10)]
    spans = [max(c[-1][1] for c in [chain]) - chain[0][0] for chain in _cluster(walk)]

    assert len(_cluster(walk)) > 1
    assert max(spans) <= _SPAN


async def test_a_card_covers_only_the_lines_it_showed():
    """Stated over every card in the corpus, because it is what a signature means.

    "Confirm all" signs the whole card, so a number listed on a card whose
    lines were never printed on it is a signature certifying text nobody read.
    That happened: a citation naming a table row and a footnote pages under it
    produced a card addressed to the range covering both, and every unrelated
    standard printed in between was listed on it.
    """
    from app.api.routers.ui_flats import _layers, _passages, _ranges

    off = []
    for layer in _layers().values():
        for card in _passages(layer, {}):
            shown = {one["n"] for one in card["lines"]}
            if not shown:
                continue
            for row in card["rows"]:
                named = {n for a, b in _ranges(row["quote"]) for n in range(a, b + 1)}
                if named - shown:
                    off.append(f"{layer.layer} {row['zone']} {row['field']} on {card['ref']}")

    assert not off, off[:5]


async def test_a_citation_naming_two_ranges_is_still_one_reading():
    """The bug that made signing silently do nothing for half the corpus.

    A value read off a table row and the footnote printed pages under it
    cites both, comma separated. The parser split the fragment on "-" alone,
    so int("13414,13416") raised and the whole citation came back as naming
    no lines. _within then said the value was not on screen, the signing
    route matched nothing, wrote nothing, and reported success.

    962 of 2,150 cited values -- 45 percent, worst in Gresham and Portland --
    could not be signed by anybody, and no error was ever shown.
    """
    from app.api.routers.ui_flats import _ranges, _span

    assert _span("4.planning.txt#L13405-L13414,L13416-L13420") == (13405, 13420)
    # The forms that already worked keep working.
    assert _span("doc.txt#L10-L20") == (10, 20)
    assert _span("doc.txt#L229") == (229, 229)
    assert _span("doc.txt#L10-L20,L25") == (10, 25)
    # Naming no lines is still naming no lines.
    assert _span("doc.txt") is None
    assert _span("doc.txt#Lnonsense") is None

    # And the ranges stay separate for anything that has to show them. The
    # hull is 13405-13420; what a reader is shown is the two stretches.
    assert _ranges("4.planning.txt#L13405-L13414,L13416-L13420") == [
        (13405, 13414),
        (13416, 13420),
    ]
    # Three stretches used to raise on int("4690,4710") and come back as a
    # citation that does not resolve, which is what the reviewer was told.
    assert _ranges("4.planning.txt#L4690,L4710-L4712,L4717") == [
        (4690, 4690),
        (4710, 4712),
        (4717, 4717),
    ]


async def test_every_cited_value_in_the_corpus_names_readable_lines():
    """Stated against the corpus, because the parser is only as good as the
    citation shapes it actually meets. A shape nobody anticipated returns
    None, and None is indistinguishable from "cites no lines" -- which is how
    45 percent of the corpus went unsignable without a single error.
    """
    from app.api.routers.ui_flats import _span, _value_rows
    from flats.rules.loader import load_rules

    unreadable = [
        (key, row["zone"], row["field"], row["quote"])
        for key, layer in load_rules().items()
        for row in _value_rows(layer)
        if row.get("quote") and _span(row["quote"]) is None
    ]

    assert not unreadable, f"{len(unreadable)} citations name no readable lines"


# --- feedback, and the bundle it becomes -------------------------------
#
# A bare "wrong" is not actionable, and a note that outlives the page it was
# written on is only readable if the page came with it. So a verdict carries
# the reviewer's words, the code text that was on screen, and a fingerprint of
# the exact value — enough for someone who was not there to act on it later.


async def _problem(client: AsyncClient, **over):
    body = {
        "layer_id": "or/clackamas/wilsonville",
        "zone": "R",
        "field": "setback_side_ft",
        "when": "",
        "verdict": "rejected",
        "note": "this is the townhouse column, not this zone's",
        "ref": "",
    }
    body.update(over)
    return await client.post("/ui/flats/sign", data=body, headers={"hx-request": "true"})


async def test_a_rejection_without_a_reason_is_refused(
    client: AsyncClient, session: AsyncSession
):
    # A queue of bare rejections is a queue nobody can work from.
    await _login(client, session)

    response = await _problem(client, note="   ")

    assert response.status_code == 400
    assert "say what is wrong" in response.text
    assert (await session.execute(text_query())).all() == []


async def test_a_problem_keeps_the_words_and_the_page(
    client: AsyncClient, session: AsyncSession
):
    from sqlalchemy import select

    from app.models.flats import FlatsRuleSignature as S

    await _login(client, session)
    page = await client.get("/flats/review/or/clackamas/wilsonville")
    ref = _first_ref(page.text)

    await _problem(client, ref=ref, note="the 15 is the townhouse column")

    row = (await session.execute(select(S))).scalars().one()
    assert row.verdict == "rejected"
    assert row.note == "the 15 is the townhouse column"
    assert row.shown_ref == ref
    # The evidence is rebuilt server-side: what the browser sent was an
    # address and an opinion.
    assert row.shown.strip(), "the code text that was on screen is kept verbatim"
    assert len(row.fingerprint) == 64


async def test_the_fingerprint_is_of_the_value_not_of_the_field(
    client: AsyncClient, session: AsyncSession
):
    from sqlalchemy import select

    from app.models.flats import FlatsRuleSignature as S

    await _login(client, session)
    await _problem(client, note="base is wrong")
    await _problem(client, when="lot_sqft:<=10000+multi_story", note="and so is the exception")

    marks = [r.fingerprint for r in (await session.execute(select(S))).scalars()]
    assert len(set(marks)) == 2, "a variant signs apart from its base"


async def test_an_unanswerable_passage_is_its_own_verdict(
    client: AsyncClient, session: AsyncSession
):
    from sqlalchemy import select

    from app.models.flats import FlatsRuleSignature as S

    # Not the same as a wrong number: the page does not answer the question.
    # Collapsing the two loses which of them an encoder has to go and read.
    await _login(client, session)

    response = await _problem(client, verdict="unclear", note="this table is the plan district's")

    assert response.status_code == 200
    assert (await session.execute(select(S.verdict))).scalars().one() == "unclear"


async def test_a_passage_problem_needs_a_reason_too(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    page = await client.get("/flats/review/or/clackamas/wilsonville")

    response = await client.post(
        "/ui/flats/sign-passage",
        data={
            "layer_id": "or/clackamas/wilsonville",
            "ref": _first_ref(page.text),
            "verdict": "rejected",
        },
        headers={"hx-request": "true"},
    )

    assert response.status_code == 400
    assert (await session.execute(text_query())).all() == []


async def test_the_bundle_carries_its_own_evidence(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    page = await client.get("/flats/review/or/clackamas/wilsonville")
    await _problem(client, ref=_first_ref(page.text), note="the 15 is the townhouse column")

    bundle = await client.get("/flats/feedback")

    assert bundle.status_code == 200
    # Address, value, citation, the reviewer's words and the text they read.
    assert "setback_side_ft" in bundle.text
    assert "the 15 is the townhouse column" in bundle.text
    assert "What was on screen" in bundle.text


async def test_confirmations_stay_out_of_the_bundle(
    client: AsyncClient, session: AsyncSession
):
    # Six hundred confirmations would bury the dozen items somebody has to act
    # on. They travel the other road: the drain, into the repository.
    await _login(client, session)
    await _sign(client)

    bundle = await client.get("/flats/feedback")

    assert "No problems open" in bundle.text


async def test_handing_the_bundle_on_clears_it_without_erasing_it(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _problem(client, note="wrong column")

    await client.post("/ui/flats/bundle", headers={"hx-request": "true"})
    open_now = await client.get("/flats/feedback")
    ever = await client.get("/flats/feedback?all=1")

    assert "No problems open" in open_now.text
    assert "wrong column" in ever.text


async def test_the_bundle_needs_a_session(client: AsyncClient):
    assert (await client.get("/flats/feedback")).status_code == 303
    assert (await client.post("/ui/flats/bundle")).status_code == 303


# --- the context a cell does not carry ---------------------------------


async def test_a_card_says_which_table_the_cells_came_from(
    client: AsyncClient, session: AsyncSession
):
    # A setback read off a row means one thing under "Table 19.302.4 High
    # Density Residential Development Standards" and another under the plan
    # district's table three pages later. The window itself — cells and
    # numbers — says neither.
    await _login(client, session)

    page = await client.get("/flats/review/or/clackamas/milwaukie")

    assert "the heading and table this passage sits under" in page.text
    assert "Table 19.301.4" in page.text


async def test_a_wrapped_line_of_prose_is_not_read_as_a_heading():
    # Gresham prints "14.52 units per acre" mid-paragraph. Taken for a
    # heading it files every card below it under a section that does not
    # exist, which is worse than showing none.
    from app.api.routers.ui_flats import _titled

    assert _titled("19.301.4. Development Standards.")
    assert _titled("4.0120                              PERMITTED USES")
    assert not _titled("14.52 units per")


async def test_a_card_of_grid_rows_says_so(client: AsyncClient, session: AsyncSession):
    # Every silent failure this system has had was in a table: rotated
    # headers dropped, a footnote marker welded onto a value, a letter-spaced
    # scan. A sentence carries its own context; a cell does not.
    await _login(client, session)

    page = await client.get("/flats/review/or/multnomah/troutdale")

    assert "read off a table" in page.text


async def test_prose_is_not_flagged_as_a_table():
    from app.api.routers.ui_flats import _from_a_table

    prose = [{"text": "The side yard shall be at least 5 ft.", "quoted": True}]
    grid = [{"text": "Minimum lot size (sq ft)      1,500      Subsection 19.501.1", "quoted": True}]

    assert not _from_a_table(prose)
    assert _from_a_table(grid)


# --- iteration: a verdict is about a value, not about a field ----------


async def test_every_signable_number_signs_against_its_own_fingerprint():
    """The queue and the signature must agree on what a verdict is about.

    They compute the fingerprint by different roads — the queue from the row it
    renders, the sign route from the number it looks up by address — and if the
    two ever disagree, a verdict stops matching the moment it is recorded and
    the item resurfaces as "changed" forever. A band token contains a "+", the
    same character that joins an address, so this is a real trap rather than a
    hypothetical one.
    """
    from app.api.routers import ui_flats as ui

    off = []
    for layer in ui._layers().values():
        for row in ui._value_rows(layer):
            number = ui._number(layer, row["zone"], row["field"], row["when"])
            mark = number and ui._mark(
                layer.layer, row["zone"], row["field"], row["when"], number
            )
            if mark != row["mark"]:
                off.append(f"{layer.layer} {row['zone']} {row['field']} {row['when']}")
    assert not off, off[:5]


async def test_a_verdict_recorded_before_fingerprints_is_taken_at_face_value():
    """Six hundred old verdicts resurfacing would bury the handful that moved."""
    from app.api.routers import ui_flats as ui

    class Seen:
        fingerprint = ""

    assert ui._stands(Seen(), "anything")
    assert not ui._stands(None, "anything")


async def test_a_changed_value_comes_back_with_what_the_reviewer_said(
    client: AsyncClient, session: AsyncSession
):
    """The loop only closes if a fix is checkable rather than merely claimed."""
    from app.api.routers import ui_flats as ui
    from app.models.flats import FlatsRuleSignature as S

    user = await _login(client, session)
    layer = ui._layers()["or/clackamas/wilsonville"]
    row = next(r for r in ui._value_rows(layer) if r["quote"])
    session.add(
        S(
            layer=layer.layer,
            zone=row["zone"],
            field=row["field"],
            when_key=row["when"],
            value=row["value"],
            cite=row["cite"],
            quote=row["quote"],
            verdict="rejected",
            note="this is the townhouse column, not this zone's",
            reviewer=user.email or str(user.id),
            reviewer_user_id=user.id,
            # Signed against a value that is no longer what the file holds.
            fingerprint="0" * 64,
        )
    )
    await session.commit()

    page = await client.get("/flats/review/or/clackamas/wilsonville")

    assert "Changed since you looked" in page.text
    assert "this is the townhouse column" in page.text, "the note comes back with it"


async def test_a_standing_verdict_does_not_come_back(
    client: AsyncClient, session: AsyncSession
):
    from app.api.routers import ui_flats as ui
    from app.models.flats import FlatsRuleSignature as S

    user = await _login(client, session)
    layer = ui._layers()["or/clackamas/wilsonville"]
    row = next(r for r in ui._value_rows(layer) if r["quote"])
    session.add(
        S(
            layer=layer.layer,
            zone=row["zone"],
            field=row["field"],
            when_key=row["when"],
            value=row["value"],
            cite=row["cite"],
            quote=row["quote"],
            verdict="rejected",
            note="wrong column",
            reviewer=user.email or str(user.id),
            reviewer_user_id=user.id,
            fingerprint=row["mark"],
        )
    )
    await session.commit()

    page = await client.get("/flats/review/or/clackamas/wilsonville")

    assert "Changed since you looked" not in page.text


async def test_the_feedback_page_says_which_notes_were_acted_on(
    client: AsyncClient, session: AsyncSession
):
    """The half of the loop that makes a round of fixes checkable."""
    from app.api.routers import ui_flats as ui
    from app.models.flats import FlatsRuleSignature as S

    user = await _login(client, session)
    layer = ui._layers()["or/clackamas/wilsonville"]
    rows = [r for r in ui._value_rows(layer) if r["quote"]]
    common = dict(
        layer=layer.layer,
        verdict="rejected",
        reviewer=user.email or str(user.id),
        reviewer_user_id=user.id,
    )
    # One note against the value as it stands, one against a value that moved.
    session.add(
        S(
            zone=rows[0]["zone"],
            field=rows[0]["field"],
            when_key=rows[0]["when"],
            value=rows[0]["value"],
            cite=rows[0]["cite"],
            quote=rows[0]["quote"],
            note="still open, nobody has touched it",
            fingerprint=rows[0]["mark"],
            **common,
        )
    )
    session.add(
        S(
            zone=rows[1]["zone"],
            field=rows[1]["field"],
            when_key=rows[1]["when"],
            value=rows[1]["value"],
            cite=rows[1]["cite"],
            quote=rows[1]["quote"],
            note="this one was fixed since",
            fingerprint="0" * 64,
            **common,
        )
    )
    await session.commit()

    page = await client.get("/flats/feedback")

    assert "have been acted on" in page.text or "has been acted on" in page.text
    assert "this one was fixed since" in page.text
    body = page.text.split("have been acted on")[-1].split("Problems found")[0]
    assert "nobody has touched it" not in body.split("Everything a day of review")[0]


# --- the page of the book ----------------------------------------------


async def test_a_card_names_the_page_the_passage_was_printed_on(
    client: AsyncClient, session: AsyncSession
):
    """A line number is ours; a page number is the document's.

    Nobody can take "line 3,041 of 4.planning.txt" to a city planner. The page
    is what makes the citation checkable by somebody who does not have this
    system in front of them, which is the only kind of checking that counts.
    """
    await _login(client, session)

    page = await client.get("/flats/review/or/clackamas/wilsonville")

    assert "p. CD4:" in page.text, "the printed page, as the codifier prints it"
    assert "#page=" in page.text, "and a link that opens the source there"


async def test_a_source_with_no_pages_still_reviews(
    client: AsyncClient, session: AsyncSession
):
    """Half the corpus is HTML, which has no pages and needs none."""
    await _login(client, session)

    page = await client.get("/flats/review/or/clackamas/milwaukie")

    assert page.status_code == 200
    assert "open the code" in page.text, "the plain link is still offered"


async def test_the_bundle_says_where_to_look_in_the_book():
    """What gets handed to an encoder has to survive leaving the app."""
    from app.api.routers import ui_flats as ui

    note = ui._page_note("or/clackamas/wilsonville/4.planning.txt#L3011-L3051")

    assert note.startswith("p. CD4:")
    assert "PDF page" in note, "both numbers — one to cite, one to open"


async def test_a_quote_into_an_unmapped_document_says_nothing_rather_than_guessing():
    from app.api.routers import ui_flats as ui

    assert ui._page_note("or/clackamas/milwaukie/19.300.base-zones.txt#L100-L120") == ""


# --- the chain of authority ---------------------------------------------


async def test_the_chain_page_shows_every_layer_and_the_page_it_cites(
    client: AsyncClient, session: AsyncSession
):
    """What gets handed to a planner, an architect or a lawyer.

    The rules table says what the setback is. This says why: which document,
    which section, which page, and what the sentence actually reads.
    """
    await _login(client, session)

    page = await client.get(
        "/flats/why/or/multnomah/gresham?zone=LDR-5&field=setback_front_ft"
    )

    assert page.status_code == 200
    assert "Gresham" in page.text
    assert "p. [4.0100]-" in page.text, "the page as the codifier prints it"
    assert "#page=" in page.text, "and a link that opens the document there"
    assert "Oregon" in page.text, "the state layer is listed even where it is silent"


async def test_the_chain_page_prints_an_exception_with_its_own_citation(
    client: AsyncClient, session: AsyncSession
):
    """An exception is a different sentence in the book and cites its own page."""
    await _login(client, session)

    page = await client.get(
        "/flats/why/or/clackamas/wilsonville?zone=OTR&field=setback_front_ft"
    )

    assert page.status_code == 200
    assert "What would change it" in page.text
    assert "lot_sqft" in page.text, "the condition that selects the other number"


async def test_the_chain_page_is_not_swallowed_by_the_layer_route(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    page = await client.get(
        "/flats/why/or/clackamas/milwaukie?zone=R-HD&field=setback_front_ft"
    )

    assert page.status_code == 200
    assert "The chain" in page.text


async def test_a_standard_nobody_has_encoded_says_so_rather_than_nothing(
    client: AsyncClient, session: AsyncSession
):
    """Silence is not "no limit" — it is the reason a zone cannot be screened."""
    await _login(client, session)

    page = await client.get(
        "/flats/why/or/clackamas/milwaukie?zone=R-HD&field=height_max_ft_stories"
    )

    assert page.status_code in (200, 404)


async def test_a_field_nobody_registered_is_refused(
    client: AsyncClient, session: AsyncSession
):
    """The registry is the one place a standard is named; unknown is not a page."""
    await _login(client, session)

    page = await client.get(
        "/flats/why/or/multnomah/gresham?zone=LDR-5&field=vibes_max_ft"
    )

    assert page.status_code == 404


async def test_a_card_says_when_the_citation_points_at_another_section(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """The failure no other check can see.

    The quote resolves and the text states the number, so nothing upstream
    objects — but the citation names a section where none of it is printed.
    Wilsonville's R setbacks said 4.122 and quoted 4.113, the citywide
    provisions that apply only where a master plan does not provide otherwise.

    That citation now names both sections and the corpus holds no misattributed
    value at all, so the detection is exercised on a citation this test writes.
    Asserting against the live corpus made a fixed encoding look like a broken
    page — and would have gone quiet on the day somebody deleted the check.
    """
    from app.api.routers import ui_flats as ui

    await _login(client, session)

    # A real passage, under a section this citation does not name.
    quote = "or/clackamas/wilsonville/4.planning.txt#L3035-L3036"
    assert ui._misattributed("Wilsonville Development Code 4.113", quote) is None

    found = ui._misattributed("Wilsonville Development Code 4.123", quote)

    assert found == {"claimed": "4.123", "found": "4.113"}

    # And the page says so where it finds one.
    monkeypatch.setattr(ui, "_misattributed", lambda cite, quote: found)
    page = await client.get("/flats/review/or/clackamas/wilsonville")

    assert "The citation and the text disagree" in page.text
    assert "§ 4.113" in page.text


async def test_a_citation_naming_several_tables_is_not_flagged_for_the_wrong_one():
    """Gresham reads a use standard off "Tables 4.0120/4.0130/4.0131"."""
    from app.api.routers import ui_flats as ui

    cite = "Gresham Development Code Tables 4.0120/4.0130/4.0131"
    quote = "or/multnomah/gresham/4.0100.residential.txt#L400"

    found = ui._misattributed(cite, quote)

    assert found is None or found["found"] not in cite


async def test_the_holes_have_a_page_of_their_own(
    client: AsyncClient, session: AsyncSession
):
    """A review queue can only show what has a quote.

    Which means the standards with no citation are the one thing the system
    never puts in front of anybody — and a jurisdiction reads as finished
    because the half nobody encoded is invisible.
    """
    await _login(client, session)

    page = await client.get("/flats/gaps")

    assert page.status_code == 200
    assert "What is not encoded" in page.text


async def test_a_gap_is_named_by_what_would_unstick_it(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    """"unquoted" is eight states that need opposite things.

    A boolean nothing can corroborate and a chapter nobody has found are both
    unquoted, and telling a reviewer to run the same command against each is
    how the readiness ladder came to point at work that could not be done.

    The ledger is supplied. Read from the corpus this asserted that two named
    causes were currently occurring, so closing the last unsourced gap in
    Oregon turned it red — reporting a page that no longer explains itself
    when what had happened was a hole being filled.
    """
    from app.api.routers import ui_flats as ui

    await _login(client, session)

    monkeypatch.setattr(
        ui,
        "_gaps",
        lambda: {
            "current": True,
            "layers": {
                "or/multnomah/gresham": {
                    "label": "Gresham",
                    "counts": {"uncheckable": 1, "unsourced": 1},
                    "misattributed": [],
                    "gaps": [
                        {
                            "zone": "LDR-5",
                            "field": "quadplex_allowed",
                            "cause": "uncheckable",
                            "detail": "bool",
                            "believed": "False",
                        },
                        {
                            "zone": "LDR-5",
                            "field": "min_lot_sqft",
                            "cause": "unsourced",
                            "detail": "",
                            "believed": "5000",
                        },
                    ],
                }
            },
        },
    )

    page = await client.get("/flats/gaps")

    assert "a yes/no or a category, which only a person can cite" in page.text
    assert "the chapter is still to find" in page.text


async def test_the_gaps_page_admits_when_its_measurement_is_stale(monkeypatch):
    """The ledger is written by a command, so it can fall behind the encoding.

    Presenting last week's work list as today's is the failure worth guarding:
    it sends somebody to fix something already fixed, and hides what is new.
    """
    from app.api.routers import ui_flats as ui

    ui._gaps.cache_clear()
    monkeypatch.setattr(ui, "read_ledger", lambda: {"layers": {}, "digest": "moved on"})
    try:
        assert ui._gaps()["current"] is False
    finally:
        ui._gaps.cache_clear()


async def test_the_written_ledger_matches_the_corpus_it_was_measured_from():
    """Committed with the rules, so it should be current in a clean checkout."""
    from app.api.routers import ui_flats as ui

    ui._gaps.cache_clear()
    try:
        assert ui._gaps()["current"], (
            "flats/config/gaps.json is behind the YAML — re-run "
            "`python -m flats.encode.gaps`"
        )
    finally:
        ui._gaps.cache_clear()


async def test_the_holes_are_ranked_by_what_they_cost(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    """A gap count and a lot count rank differently, and the difference is the point.

    Four gaps over eleven lots is a finished jurisdiction; one unencoded zone
    can be sitting on fourteen thousand. Portland RM1 was the row that cost
    quadfit 40,500 lots by being an absence rather than a top line — and it is
    encoded now, which is why the coverage rows here are supplied instead of
    read. Encoding a zone must not be able to delete the check that the page
    would show the next one.

    ``_blocker`` runs for real on them, so the sentence a reviewer reads is the
    one under test rather than a string this test wrote.
    """
    from app.api.routers import ui_flats as ui
    from flats.rules.ledger import CoverageRow

    await _login(client, session)

    rows = [
        CoverageRow(
            jurisdiction="or/multnomah/portland",
            zone="RM1",
            lots=40_500,
            acres=0.0,
            status="zone_missing",
            verified_fields=0,
            total_fields=0,
            missing_required="",
            untrusted_fields="",
            blocking=40_500,
        ),
        CoverageRow(
            jurisdiction="or/multnomah/gresham",
            zone="LDR-5",
            lots=11,
            acres=0.0,
            status="encoded",
            verified_fields=3,
            total_fields=4,
            missing_required="",
            untrusted_fields="setback_front_ft",
            blocking=11,
        ),
    ]
    ui._coverage.cache_clear()
    monkeypatch.setattr(ui, "read_coverage", lambda: rows)
    try:
        page = await client.get("/flats/gaps")

        assert "What the holes cost, in lots" in page.text
        assert "RM1" in page.text
        assert "this zone has no encoding" in page.text
        # The zone nothing has encoded costs 40,500 lots and the one missing a
        # confirmation costs 11. Ranked by gap count they are one apiece.
        assert page.text.index("RM1") < page.text.index("LDR-5")
    finally:
        ui._coverage.cache_clear()


async def test_a_jurisdiction_nobody_counted_is_not_a_jurisdiction_with_no_lots(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    """The parcel corpus reaches fewer jurisdictions than the rules do.

    Leaving the rest out of a page headed "what the holes cost" would report
    them as costing nothing, which is the exact mistake — an unencoded zone
    vanishing into an absence — that the coverage ledger exists to prevent.

    One counted jurisdiction is supplied and every other encoded city has to
    turn up in the uncounted list. Naming a particular city here made the test
    a record of which cities the parcel corpus had reached that month.
    """
    from app.api.routers import ui_flats as ui
    from flats.rules.ledger import CoverageRow

    await _login(client, session)

    counted = "or/multnomah/gresham"
    ui._coverage.cache_clear()
    monkeypatch.setattr(
        ui,
        "read_coverage",
        lambda: [
            CoverageRow(
                jurisdiction=counted,
                zone="LDR-5",
                lots=11,
                acres=0.0,
                status="encoded",
                verified_fields=3,
                total_fields=4,
                missing_required="",
                untrusted_fields="setback_front_ft",
                blocking=11,
            )
        ],
    )
    try:
        page = await client.get("/flats/gaps")

        assert "appear nowhere above" in page.text
        elsewhere = [
            layer_id
            for layer_id, layer in ui._layers().items()
            if layer.kind in ("city", "unincorporated") and layer_id != counted
        ]
        assert elsewhere, "fixture assumption: the corpus holds more than one city"
        missing = [one for one in elsewhere if one not in page.text]
        assert not missing, missing
        # The state layer holds no lots and is nobody's uncounted jurisdiction.
        assert ">or</a>" not in page.text
    finally:
        ui._coverage.cache_clear()


async def test_the_wrong_section_citations_are_a_list_not_only_a_banner(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    """A warning on a card is only seen by whoever happens to open that card.

    An afternoon's work needs a list — otherwise the only way to find the next
    one is to page through a review queue looking for red.

    Supplied rather than measured. The corpus had 126 of these when this was
    written and has none now, and a test that reads the live count asserts the
    mistakes are still being made rather than that the page would show them.
    """
    from app.api.routers import ui_flats as ui

    await _login(client, session)

    monkeypatch.setattr(
        ui,
        "_gaps",
        lambda: {
            "current": True,
            "layers": {
                "or/clackamas/wilsonville": {
                    "label": "Wilsonville",
                    "counts": {},
                    "gaps": [],
                    "misattributed": [
                        {
                            "zone": "OTR",
                            "field": "setback_front_ft",
                            "claimed": "4.123",
                            "found": "4.113",
                        }
                    ],
                }
            },
        },
    )

    page = await client.get("/flats/gaps")

    assert "Citations that name the wrong section" in page.text
    assert "Text is in" in page.text
    assert "4.123" in page.text
    assert "4.113" in page.text


async def test_a_card_offers_the_page_itself(client: AsyncClient, session: AsyncSession):
    """Extraction flattens a table; the sheet is where the columns still are.

    A setback read off a grid means one thing in the RF column and another in
    the R2.5 column, and the extracted lines cannot say which. The button that
    puts the printed page beside the number is the shortest path from "is this
    right" to knowing.
    """
    await _login(client, session)

    page = await client.get("/flats/review/or/multnomah/gresham")

    assert "show the page" in page.text
    assert "/ui/flats/book?ref=" in page.text


async def test_the_viewer_embeds_the_page_the_citation_lands_on(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    view = await client.get(
        "/ui/flats/book",
        params={"ref": "or/multnomah/portland/33.110.txt", "page": 12},
    )

    assert view.status_code == 200
    assert "/flats/book/or/multnomah/portland/33.110.txt#page=12" in view.text
    assert "<iframe" in view.text


async def test_the_viewer_refuses_a_document_the_store_does_not_hold(
    client: AsyncClient, session: AsyncSession
):
    """The reference is a query parameter, so it is attacker-chosen text that
    ends up as a filesystem path. Membership of the store is the gate."""
    await _login(client, session)

    view = await client.get("/ui/flats/book", params={"ref": "../../etc/passwd"})

    assert view.status_code == 404


async def test_the_book_route_needs_a_session(client: AsyncClient):
    """The corpus is fetched code, but the route reads from disk and streams a
    file; anonymous access to it is not a thing a review surface should offer."""
    served = await client.get("/flats/book/or/multnomah/portland/33.110.txt")

    assert served.status_code in (302, 303, 401, 403)


async def test_an_unread_standard_is_not_screened_and_is_not_hidden_either(
    client: AsyncClient, session: AsyncSession
):
    """The two failures a queue sits between.

    Screening on a number nobody read is the one the provenance chain exists to
    stop. Dropping it silently is the other, and it is worse in one way: the
    jurisdiction then reads as small rather than as thin, and nobody goes
    looking. So it leaves the zone and appears here, counted.
    """
    await _login(client, session)

    page = await client.get("/flats")

    assert "Held out" in page.text
    assert "held out of screening" in page.text


async def test_the_queue_keeps_the_number_somebody_believed(
    client: AsyncClient, session: AsyncSession
):
    """A lead, not an answer.

    Somebody typed 10 from a table they had open. That is worthless as a rule
    and valuable as a search: whoever opens the chapter knows what to scan for,
    and a searcher who finds 15 instead has found something better than a
    citation — a wrong number, before it decided a lot.
    """
    await _login(client, session)

    page = await client.get("/flats/gaps")

    assert "Believed" in page.text
    assert "What it would take to make it a rule" in page.text


async def test_the_queue_sends_a_searcher_to_the_lines_that_could_be_it(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    """A held-out standard is a hunt, and the hunt is mostly reading.

    Somebody believes Fairview's RM minimum lot is 10,000 square feet. Whether
    that is the code's answer is settled by looking at the lines in Fairview's
    own chapters that print a 10000 — a search anybody can run and nobody
    should have to run at a terminal.

    The queue is supplied rather than read, because reading it makes this a
    test of whether that particular gap is still open.
    """
    from app.api.routers import ui_flats as ui

    await _login(client, session)

    address = ("or/multnomah/fairview", "RM", "min_lot_sqft")
    monkeypatch.setattr(ui, "_queue", lambda: {address: _hunt(*address, 10000)})

    page = await client.get(
        "/flats/find/or/multnomah/fairview", params={"zone": "RM", "field": "min_lot_sqft"}
    )

    assert page.status_code == 200
    assert "Believed to be" in page.text
    assert "10000" in page.text


async def test_a_standard_that_is_not_in_the_queue_has_no_hunt(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    """The address comes from a link, which means it comes from a URL bar too.

    A value that is encoded and quoted is not work; offering a search page for
    it would invite somebody to re-cite a standard that already has a citation,
    against a line they picked out of a list.

    The queue holds one address here so the refusal is a refusal. Asserted
    against the real queue this passed for the wrong reason the moment the
    corpus had no gaps left in it — an empty queue refuses everything.
    """
    from app.api.routers import ui_flats as ui

    await _login(client, session)

    address = ("or/multnomah/fairview", "RM", "min_lot_sqft")
    monkeypatch.setattr(ui, "_queue", lambda: {address: _hunt(*address, 10000)})

    page = await client.get(
        "/flats/find/or/multnomah/portland", params={"zone": "R5", "field": "setback_front_ft"}
    )

    assert page.status_code == 404


async def test_the_hunt_says_so_when_the_chapter_was_never_fetched(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    """No line stating it is not a dead end — it is the finding.

    Either the chapter that states this standard has never been fetched, or the
    number was never in this code at all, and both are worth more to a reviewer
    than another afternoon reading the documents that are there.

    The believed number is one no Fairview chapter prints, which is what makes
    the search come back empty. The old assertion allowed the word "line"
    anywhere on the page as a pass, and the page says "line" in its own
    furniture — it would have gone green on a page full of candidates.
    """
    from app.api.routers import ui_flats as ui

    await _login(client, session)

    address = ("or/multnomah/fairview", "R/SFLD", "min_lot_sqft")
    monkeypatch.setattr(ui, "_queue", lambda: {address: _hunt(*address, 987654)})

    page = await client.get(
        "/flats/find/or/multnomah/fairview", params={"zone": "R/SFLD", "field": "min_lot_sqft"}
    )

    assert page.status_code == 200
    assert "No line in this jurisdiction's fetched code states it." in page.text


async def test_the_table_row_is_offered_before_the_prose_that_mentions_it(
    client: AsyncClient, session: AsyncSession
):
    """Ranking has to happen before the list is cut, or it does nothing.

    Gresham's code says "quadplex" in twenty paragraphs of definitions and
    procedure before Table 4.0120 answers the question at line 134. A searcher
    handed the first sixty matches in file order reads the preamble and never
    reaches the table, which is the one line that decides the standard.
    """
    from app.api.routers import ui_flats as ui

    item = _hunt(
        "or/multnomah/gresham",
        "LDR-PV",
        "quadplex_allowed",
        True,
        ["or/multnomah/gresham/4.0100.residential.txt"],
    )

    candidates, _ = ui._candidates(item)

    assert candidates[0]["text"].lower().startswith("quadplex ")
    assert candidates[0]["line"] == 134


async def test_a_cut_list_says_how_much_it_cut(client: AsyncClient, session: AsyncSession):
    """A list that stops at sixty reads as a corpus with sixty matches in it.

    Which would send somebody to declare a missing chapter that is not missing,
    on the evidence of a page that was only ever showing them the top of a pile.
    """
    from app.api.routers import ui_flats as ui

    item = _hunt("or/multnomah/gresham", "LDR-PV", "quadplex_allowed", True)

    candidates, dropped = ui._candidates(item, limit=3)

    assert len(candidates) == 3
    assert dropped > 0


async def test_a_flattened_row_is_shown_with_the_cells_under_it(
    client: AsyncClient, session: AsyncSession
):
    """In a linearised table the match is the label and the answer is below it.

    Clackamas prints "Quadplexes" and then eleven cells, one to a line. Shown
    alone the candidate is a word; shown with its cells it is the row, and a
    reviewer can see that the first two columns say P and the third says X
    without opening anything.
    """
    from app.api.routers import ui_flats as ui

    item = _hunt(
        "or/clackamas/_unincorporated",
        "R5",
        "quadplex_allowed",
        True,
        ["or/clackamas/_unincorporated/zdo.315.txt"],
    )

    candidates, _ = ui._candidates(item)

    assert candidates[0]["text"] == "Quadplexes"
    # ``P[7,8]``, not ``P7,8``: extractor /7 separates a superscript footnote
    # marker from the value it sits on, because "P7" welded together is a
    # permission somebody has to know to un-weld and "P" with footnotes 7 and 8
    # is what the table prints. The corpus was re-extracted under it on
    # 2026-08-26 and this assertion did not learn, because CI's light gate was
    # dark from 08-14 to 09-03 and nothing ran it.
    assert candidates[0]["after"][:3] == ["P[7,8]", "P[7,8]", "X"]



async def test_the_book_url_is_not_swallowed_by_the_jurisdiction_page(
    client: AsyncClient, session: AsyncSession
):
    """A catch-all registered above this one answers for everything under it.

    ``/flats/{layer_id:path}`` matches ``/flats/book/or/.../33.110.txt`` as
    happily as it matches ``/flats/or/multnomah/portland``, and FastAPI hands
    the path to whichever route was registered first. Registered in the wrong
    order, a reviewer clicking "show the page" gets the FLATS index rendered
    inside the citation card — the app inside the app — instead of the page of
    the code the standard was read from.
    """
    await _login(client, session)

    response = await client.get("/flats/book/or/multnomah/portland/does-not-exist.txt")

    # The book route's own answer for a document it does not hold. The point is
    # that the book route is what answered: the catch-all would render a page.
    assert response.status_code == 404
    assert "no such stored document" in response.text
    assert "No rule layer called" not in response.text
    assert "Zoning rules" not in response.text


async def test_a_citation_to_a_sentence_highlights_all_of_it(
    client: AsyncClient, session: AsyncSession
):
    """A rule is often a sentence, and a sentence is often three lines.

    Portland's 10 percent lot-area adjustment reads across three lines of the
    extracted text: the allowance starts on one, the size of it is on the next,
    and the date it ends on is on the third. Highlighting only the first shows
    a reviewer a fragment that does not state the standard, and the natural
    reading of a single highlighted line is that the line is the whole rule.
    """
    await _login(client, session)

    ref = "or/multnomah/portland/33.110.txt%23L1544-L1546"
    response = await client.get(f"/ui/flats/quote?ref={ref}")

    assert response.status_code == 200
    lit = response.text.count("background:#1d4ed8")
    assert lit == 3, f"three lines cited, {lit} highlighted"


# --- the verdict bar ------------------------------------------------------
#
# The why page grew until the evidence a reviewer is judging sits well below
# the fold, and a decision control above it means scrolling away from the
# thing being judged in order to judge it. The bar sticks to the bottom, so
# these tests hold to the two things that make it usable rather than merely
# present: it is on the page, and a verdict that needs a note and did not get
# one comes back with the reviewer's half-written note still in it.


async def _bar(client: AsyncClient, **over):
    body = {
        "layer_id": "or/multnomah/portland",
        "zone": "R10",
        "field": "min_lot_sqft",
        "when": "",
        "verdict": "verified",
        "shape": "bar",
    }
    body.update(over)
    return await client.post("/ui/flats/sign", data=body, headers={"hx-request": "true"})


async def test_the_why_page_carries_the_three_decisions(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    response = await client.get("/flats/why/or/multnomah/portland?zone=R10&field=min_lot_sqft")

    assert response.status_code == 200
    assert 'id="verdict-bar"' in response.text
    for word in ("Confirm", "Query", "Problem"):
        assert f">{word}<" in response.text, word
    # Not on the printout. The planner across the counter cannot press them.
    assert "no-print" in response.text


async def test_confirming_from_the_bar_answers_in_the_bar(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    response = await _bar(client)

    assert response.status_code == 200
    assert 'id="verdict-bar"' in response.text
    assert "confirmed" in response.text
    # A confirmation is not a problem, so it does not join the batch.
    assert "in the batch" not in response.text


async def test_a_query_without_a_note_keeps_what_was_typed(
    client: AsyncClient, session: AsyncSession
):
    """The note is the whole content of a query, and losing it teaches Confirm.

    A reviewer who types three sentences, clicks the wrong button and gets an
    empty box back does not retype them.
    """
    await _login(client, session)

    response = await _bar(client, verdict="unclear", note="   ")

    assert response.status_code == 400
    assert "a bare rejection is not actionable" in response.text
    # Open, because the reviewer has to be shown the field they missed.
    assert "<details" in response.text and "open" in response.text


async def test_a_query_with_a_note_joins_the_batch(client: AsyncClient, session: AsyncSession):
    await _login(client, session)

    response = await _bar(
        client, verdict="unclear", note="the paragraph above the table allows a 10 percent cut"
    )

    assert response.status_code == 200
    assert "queried" in response.text
    assert "in the batch" in response.text

    bundle = await client.get("/flats/feedback")
    assert "10 percent cut" in bundle.text


# --- the third answer, in the queue that never offered it -----------------
#
# The verdict bar has carried Confirm / Query / Problem since it was written.
# The review-queue table -- the page a reader actually works a jurisdiction
# from, one number at a time -- rendered Confirm and Wrong and nothing else,
# and had no note field at all. A reviewer who read the page and came away
# unsure had no button for that, and a queue whose only outcomes are agreement
# and accusation collects agreement.


async def _row(client: AsyncClient, **over):
    body = {
        "layer_id": "or/multnomah/portland",
        "zone": "R10",
        "field": "min_lot_sqft",
        "when": "",
        "verdict": "verified",
        "shape": "row",
        "anchor": "7",
    }
    body.update(over)
    return await client.post("/ui/flats/sign", data=body, headers={"hx-request": "true"})


async def test_the_review_queue_offers_the_third_answer(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    response = await client.get("/flats/or/multnomah/portland")

    assert response.status_code == 200
    for word in ("Confirm", "Unsure", "Wrong"):
        assert f">{word}<" in response.text, word
    # And somewhere to say why, which is the half that makes the button mean
    # anything: a doubt with no sentence attached is not a finding.
    assert 'name="note"' in response.text


async def test_an_unsure_row_without_a_note_keeps_what_was_typed(
    client: AsyncClient, session: AsyncSession
):
    """The refusal hands back the control, not a one-line message.

    Swapping the row for "say what is wrong with it" would take the note box
    away at the moment the reviewer is being told to write in it.
    """
    await _login(client, session)

    response = await _row(client, verdict="unclear", note="  ")

    assert response.status_code == 400
    assert "a bare rejection is not actionable" in response.text
    assert 'name="note"' in response.text
    assert "<details" in response.text and "open" in response.text
    # Still addressed to the row it came from, or the swap lands nowhere.
    assert 'id="verdict-7"' in response.text


async def test_an_unsure_row_with_a_note_joins_the_batch(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    response = await _row(
        client,
        verdict="unclear",
        note="the highlight stops before the section that says this table applies",
    )

    from sqlalchemy import select

    from app.models.flats import FlatsRuleSignature as S

    assert response.status_code == 200
    assert 'id="verdict-7"' in response.text
    assert (await session.execute(select(S.verdict))).scalars().one() == "unclear"

    bundle = await client.get("/flats/feedback")
    assert "the highlight stops before" in bundle.text


# --- reading the code without rewriting it --------------------------------


@pytest.mark.asyncio
async def test_a_sentence_is_tidied_and_a_table_row_is_not():
    """The one thing that must not happen on this page is a table row losing
    its column spacing. That spacing is the only evidence of which zone a
    number belonged to, and squeezing it produces something that reads better
    and means less."""
    from app.api.routers.ui_flats import _line

    sentence = _line(37, "   B. Lot Dimensions.  All lots shall have  35 ft.", True)
    assert sentence["grid"] is False
    assert sentence["shown"] == "B. Lot Dimensions. All lots shall have 35 ft."
    assert sentence["text"] == "   B. Lot Dimensions.  All lots shall have  35 ft."

    row = _line(753, "Attached Dwellings, Quadplexes  10          10 - Exterior Wall", True)
    assert row["grid"] is True
    assert row["shown"] == "Attached Dwellings, Quadplexes  10          10 - Exterior Wall"


@pytest.mark.asyncio
async def test_the_displayed_line_keeps_the_number_its_citation_is_written_against():
    """A tidy-up that renumbered would move six hundred citations by one, with
    nothing on screen to say so."""
    from app.api.routers.ui_flats import _line

    assert _line(1544, "  some line  ", False)["n"] == 1544


# --- fetch triage ----------------------------------------------------------
#
# One reference, one question, one decision. What these hold to is that the
# decision goes somewhere it survives a deploy, that it leaves the queue the
# moment it is made, and that a reviewer who cannot answer can get past a card
# without being made to invent one.


async def test_the_queue_asks_one_question_about_one_reference(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    response = await client.get("/flats/triage")

    assert response.status_code == 200
    # The ask sits with the buttons, not above a screenful of evidence, and it
    # names the two things a reviewer can do rather than posing a question.
    assert "Order this chapter, or say why we can leave it." in response.text
    assert "Leave it, because:" in response.text
    # The lot counts are gone from the page on purpose -- a reviewer deciding
    # whether a chapter can change a number could do nothing with a six-figure
    # total, and it was on every card twice. The queue is still ranked on it.
    assert "lots at stake" not in response.text
    assert "Standards written near it" in response.text


async def test_a_ruling_lands_in_the_inbox_and_the_row_leaves_the_queue(
    client: AsyncClient, session: AsyncSession
):
    """The rule files are rebuilt from git on every deploy, so a decision
    spliced into a running container would not survive the next release. It
    goes to a table, and the queue reads the table over the files."""
    from sqlalchemy import select

    from app.models.flats import FlatsCrossrefRuling

    await _login(client, session)
    first = await client.get("/flats/triage?layer=or/multnomah/gresham")
    assert first.status_code == 200
    ref = _first_ref(first.text)

    response = await client.post(
        "/ui/flats/triage/rule",
        data={
            "layer_id": "or/multnomah/gresham",
            "ref": ref,
            "outcome": "procedure",
            "note": (
                "Read it. Design review procedure — approval criteria only, no "
                "dimensional standard anywhere in the chapter."
            ),
            "layer": "or/multnomah/gresham",
        },
    )

    assert response.status_code == 200
    row = (
        await session.execute(
            select(FlatsCrossrefRuling).where(FlatsCrossrefRuling.ref == ref)
        )
    ).scalar_one()
    assert row.outcome == "procedure"
    assert row.decided_by, "a ruling is attributable or it is not a ruling"
    assert row.exported_at is None, "recorded, not yet in force"

    # And the next card is a different reference — the queue moved on.
    assert _first_ref(response.text) != ref


async def test_a_tag_with_no_reasoning_is_refused_and_the_words_are_kept(
    client: AsyncClient, session: AsyncSession
):
    """A row closed with a word nobody can check is worse than an open one: the
    open row still shows the sentence it came from."""
    await _login(client, session)
    page = await client.get("/flats/triage?layer=or/multnomah/gresham")
    ref = _first_ref(page.text)

    response = await client.post(
        "/ui/flats/triage/rule",
        data={
            "layer_id": "or/multnomah/gresham",
            "ref": ref,
            "outcome": "procedure",
            "note": "not relevant",
            "layer": "or/multnomah/gresham",
        },
    )

    assert response.status_code == 400
    assert "say why" in response.text
    assert "not relevant" in response.text, "the typing is not thrown away"
    assert _first_ref(response.text) == ref, "and the card is still the one asked about"


async def test_skipping_walks_past_a_card_without_answering_it(
    client: AsyncClient, session: AsyncSession
):
    """"I cannot tell yet" is a real answer and has to cost nothing. It must
    not record an outcome, and it must not reorder the queue — the card stays
    where it is for whoever comes next."""
    from sqlalchemy import func, select

    from app.models.flats import FlatsCrossrefRuling

    await _login(client, session)
    page = await client.get("/flats/triage?layer=or/multnomah/gresham")
    ref = _first_ref(page.text)

    response = await client.post(
        "/ui/flats/triage/rule",
        data={
            "layer_id": "or/multnomah/gresham",
            "ref": ref,
            "action": "skip",
            "layer": "or/multnomah/gresham",
        },
    )

    assert response.status_code == 200
    assert _first_ref(response.text) != ref
    written = (
        await session.execute(select(func.count()).select_from(FlatsCrossrefRuling))
    ).scalar_one()
    assert written == 0

    # Unskipped, the queue still leads with the card that was walked past.
    again = await client.get("/flats/triage?layer=or/multnomah/gresham")
    assert _first_ref(again.text) == ref


async def test_a_triage_mention_links_to_text_that_resolves(
    client: AsyncClient, session: AsyncSession
):
    """The card linked at the PDF route with a "#L229" fragment on the end.

    Three things wrong at once: the route serves a book and refuses outright
    for the two thirds of this corpus that have no page map, a "#L" fragment
    means nothing to a PDF viewer even where one opens, and the reviewer lands
    on a bare error instead of the sentence the card was asking about.

    The stored text is what a citation addresses and it resolves for every
    document we hold.
    """
    await _login(client, session)
    page = await client.get("/flats/triage?layer=or/multnomah/portland")
    assert page.status_code == 200
    assert "/flats/book/" not in page.text, "the book route cannot answer a #L"
    assert "/ui/flats/quote?ref=" in page.text

    # Portland 33.100 has no page map — the document that produced the bare
    # error page — and its stored lines come back regardless.
    lines, error = _cited_lines("or/multnomah/portland/33.100.txt#L229")
    assert not error
    assert lines


def _queued_at(layer: str, wanted: str) -> int | None:
    """Where in a triage queue the card carrying ``wanted`` sits, or None.

    The triage screen shows one card, and ``?skipped=`` walks the queue. Both
    tests below were written against whatever happened to be first for
    Portland, which is a position rather than a property: encoding Portland's
    commercial zones put 33.613 at the head and both went red, reporting a
    broken review page when what had actually happened was that a jurisdiction
    got further along. Same lesson as ``_hunt`` above, on a different queue.
    """
    import dataclasses

    from flats.encode.triage import feed

    for i, card in enumerate(feed(layer=layer)):
        if wanted in str(dataclasses.asdict(card)):
            return i
    return None


async def test_a_tiered_standard_is_not_shown_to_a_reviewer_as_a_python_list(
    client: AsyncClient, session: AsyncSession
):
    """A card standing beside a tiered coverage standard rendered it as
    ``[[0, 0, 50], [3000, 1500, 37.5], [5000, 2...`` — nested brackets, cut
    mid-number. A card whose only evidence is unreadable asks a question it
    has not supplied the means to answer.

    The prose form itself is owned by ``flats/tests/test_triage.py``; what is
    under test here is that it survives the template, which is the half a unit
    test cannot see.
    """
    await _login(client, session)

    at = _queued_at("or/multnomah/portland", "of the excess")
    if at is None:
        pytest.skip("no tiered standard stands beside a Portland card today")

    response = await client.get(
        f"/flats/triage?layer=or/multnomah/portland&skipped={at}"
    )

    assert response.status_code == 200
    assert "of the excess" in response.text
    assert "[[0, 0, 50]" not in response.text


async def test_the_card_calls_a_title_a_title(
    client: AsyncClient, session: AsyncSession
):
    """Portland's tree rules are Title 11, not Section 11. A title is a whole
    body of code and a section is a paragraph of one, and a card that prints
    the wrong noun tells a reviewer the document is something other than what
    it is."""
    await _login(client, session)

    at = _queued_at("or/multnomah/portland", "Title 11")
    if at is None:
        pytest.skip("Title 11 is not in the current Portland queue")

    response = await client.get(
        f"/flats/triage?layer=or/multnomah/portland&skipped={at}"
    )

    assert "Title 11" in response.text
    assert "Section 11 " not in response.text


async def test_a_chapter_reached_through_a_word_says_so_on_the_card(
    client: AsyncClient, session: AsyncSession
):
    """The queue ranks on two routes now and the card only ever drew one.

    A chapter handed a measuring word stands beside no standard at all, so
    every figure this card prints for it is zero. Portland's 33.930 went from
    position 69 of 75 to the head of the queue on that signal, and without this
    block the first card a reviewer sees says "no standards written near it"
    and nothing about why it is first.
    """
    from flats.encode.triage import feed

    await _login(client, session)

    rows = feed(layer="or/multnomah/portland")
    at = next((i for i, c in enumerate(rows) if c.undefined), None)
    if at is None:
        pytest.skip("no Portland chapter is reached through a word today")
    card = rows[at]

    response = await client.get(
        f"/flats/triage?layer=or/multnomah/portland&skipped={at}"
    )

    assert response.status_code == 200
    assert "Words this code hands it" in response.text
    assert card.undefined[0] in response.text
    if card.undefined_lots:
        assert f"{card.undefined_lots:,}" in response.text


async def test_a_rejected_number_reads_as_rejected_on_the_screen(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    """Trust is applied at load, and the screen has to be reading that load.

    A rule file may not say ``verified`` or ``disputed`` -- the loader refuses
    both -- so the signature logs are the only thing that ever moves a value
    off ``draft``. A page built from the parse output alone would report every
    number in the corpus as unread however many verdicts had been drained into
    the repository, and a reviewer would go on being shown a number somebody
    had already rejected with nothing on the screen to say so.
    """
    from datetime import date

    from app.api.routers import ui_flats as ui
    from flats.encode.dispute import Dispute, DisputeLog
    from flats.encode.verify import fingerprint
    from flats.rules.model import Status

    await _login(client, session)

    layer_id, zone, field = "or/multnomah/gresham", "LDR-5", "setback_front_ft"
    number = ui._layers()[layer_id].zones[zone].values[field]
    assert number.status is Status.draft, "nothing in the corpus is signed yet"

    rejected = DisputeLog(
        [
            Dispute(
                layer=layer_id,
                zone=zone,
                field=field,
                fingerprint=fingerprint(
                    layer_id,
                    zone,
                    field,
                    number.value,
                    cite=number.prov.cite,
                    quote=number.prov.quote,
                ),
                reviewer="sjk",
                raised=date(2026, 8, 23),
                note="the row read is the corner-lot column, not the interior one",
            )
        ]
    )
    monkeypatch.setattr(
        DisputeLog, "load", classmethod(lambda cls, path=None: rejected)
    )
    ui._layers.cache_clear()
    try:
        assert ui._layers()[layer_id].zones[zone].values[field].status is Status.disputed

        response = await client.get("/flats/" + layer_id)

        assert response.status_code == 200
        assert "rejected" in response.text
    finally:
        # The cache outlives monkeypatch's undo, so a stale entry here would
        # leak a disputed corpus into every test that ran after this one.
        ui._layers.cache_clear()


async def test_every_gap_cause_is_said_in_words_a_reviewer_can_act_on():
    """A cause with no sentence renders as its own slug and says nothing.

    The gaps page exists to tell somebody what would unstick a standard, and
    the encoder's vocabulary does not do that: "unmapped" on a page is a word,
    not a next step. Adding a cause to the ledger and not to the page is a
    silent way of shipping one — which is how ``unmapped`` reached production
    as a bare word in a table cell.
    """
    from app.api.routers.ui_flats import _CAUSE_WORDS
    from flats.encode.gaps import CAUSES

    assert not [cause for cause in CAUSES if cause not in _CAUSE_WORDS]


def _a_split_citation(*, mapped: bool = False) -> str:
    """Any live citation naming stretches pages apart, or "" if none does.

    Found rather than named, for the reason ``_hunt`` gives: an address written
    into a test is an address that goes away the day somebody finishes the
    jurisdiction it is in.

    ``mapped`` narrows to a document that has a page map, which only the PDF
    half of the corpus does. Without it the first match is Clackamas ZDO 315 --
    HTML, no pages, nothing for a page test to assert on.
    """
    from app.api.routers.ui_flats import _page_index, _passages, _ranges
    from flats.rules.loader import load_rules

    for layer in load_rules(strict=False).values():
        for card in _passages(layer, {}):
            ranges = _ranges(card["ref"])
            if len(ranges) < 2 or ranges[-1][0] - ranges[0][1] <= 500:
                continue
            if mapped and _page_index(card["ref"].partition("#L")[0]) is None:
                continue
            return card["ref"]
    return ""


async def test_what_a_signature_records_is_what_the_card_drew(
    client: AsyncClient, session: AsyncSession
):
    """``_shown`` stores the code text a reviewer was looking at, so that a
    signature stays checkable months later after the document has moved. It
    took the hull between the stretches a citation names instead of the
    stretches: Wilsonville's ``#L572-L574,L8314,L8318`` is six cited lines and
    a hull of seven thousand seven hundred, so the column that exists to say
    "this is what was on screen" held most of a municipal code and a reader
    checking the signature had to find the six lines themselves.

    ``_ranges`` says this in as many words -- "a window drawn from the hull is
    three and a half thousand lines of unrelated code with two of them marked"
    -- and the card-building path had used it for a fortnight. This one had
    not.
    """
    from app.api.routers.ui_flats import _CONTEXT, _ranges, _shown

    ref = _a_split_citation()
    if not ref:
        pytest.skip("no citation in the corpus names stretches pages apart")

    numbers = [int(line.split()[0]) for line in _shown(ref).splitlines()]
    ranges = _ranges(ref)

    assert numbers, "the cited lines still come back"
    # Both ends, so nothing was dropped...
    assert min(numbers) <= ranges[0][0]
    assert max(numbers) >= ranges[-1][1]
    # ...and not the thousands of unrelated lines printed between them.
    assert len(numbers) <= sum(b - a + 1 + 2 * _CONTEXT for a, b in ranges)
    assert len(numbers) < (ranges[-1][1] - ranges[0][0]) / 10



async def test_a_page_citation_names_the_pages_it_was_read_from(
    client: AsyncClient, session: AsyncSession
):
    """The same hull, one function further on, and where it costs most.

    A page number exists so an encoded standard can be defended to somebody
    who does not have this system in front of them -- a planner, an architect,
    a lawyer reading the code off paper. They cannot check "line 3,041"; they
    can turn to page CD4:180. Swept across the hull, Wilsonville's
    ``#L572-L574,L8314,L8318`` answered with two hundred and two pages, which
    tells that planner to read the chapter.
    """
    from app.api.routers.ui_flats import _page_note, _pages_in, _ranges

    ref = _a_split_citation(mapped=True)
    if not ref:
        pytest.skip("no split citation sits in a document with a page map")

    document = ref.partition("#L")[0]
    ranges = _ranges(ref)
    pages = _pages_in(document, ranges)

    assert pages, "the page map answered for a document that has one"

    # One or two pages per stretch, not every sheet printed between them.
    assert len(pages) <= 2 * len(ranges)
    assert [p["n"] for p in pages] == sorted(p["n"] for p in pages)
    assert _page_note(ref).count("PDF page") == len(pages)


# --- reading queues ---------------------------------------------------------
#
# Four screens over one ledger. What these hold to is the thing that makes them
# four and not one: each asks a different question and offers only the answers
# to its own, and a card ruled on leaves the queue it was in.


def _first_card(html: str) -> dict[str, str]:
    """The hidden fields identifying the card on screen."""
    out: dict[str, str] = {}
    for name in ("queue", "layer_id", "path", "section", "fingerprint"):
        m = re.search(rf'name="{name}" value="([^"]*)"', html)
        if m:
            out[name] = m.group(1)
    return out


async def test_the_landing_page_names_a_mode_and_its_size(
    client: AsyncClient, session: AsyncSession
):
    """The first decision of the day is not about a card, it is about what
    kind of reading to do. Four questions and four counts, nothing else."""
    await _login(client, session)

    response = await client.get("/flats/reading")

    assert response.status_code == 200
    for title in ("Missed standards", "Conditions", "Unopened chapters", "No field for it"):
        assert title in response.text
    assert "Why didn&#39;t we take it?" in response.text or "Why didn't we take it?" in response.text


async def test_each_queue_offers_only_its_own_answers(
    client: AsyncClient, session: AsyncSession
):
    """The keying of the vocabulary is the design, not decoration.

    A screen offering every outcome anybody has ever needed is a screen where
    the reviewer re-reads the vocabulary before every card. One queue, one
    question, one row of buttons.
    """
    await _login(client, session)

    missed = await client.get("/flats/reading/missed")
    chapter = await client.get("/flats/reading/chapter")

    assert missed.status_code == chapter.status_code == 200
    assert "Same number — our reader missed it" in missed.text
    assert "Different building or use" not in missed.text
    assert "Read it — queue for encoding" in chapter.text
    assert "Same number — our reader missed it" not in chapter.text


async def test_a_queue_that_does_not_exist_goes_back_to_the_menu(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    response = await client.get("/flats/reading/everything", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/flats/reading"


async def test_the_missed_queue_shows_what_we_hold_beside_what_the_code_says(
    client: AsyncClient, session: AsyncSession
):
    """Two columns and nothing else. The reviewer's eye does the comparison;
    the screen does not explain it."""
    await _login(client, session)

    response = await client.get("/flats/reading/missed")

    assert response.status_code == 200
    assert "What the code says" in response.text
    assert "we hold" in response.text


async def test_a_reading_ruling_lands_in_the_inbox_and_the_card_leaves(
    client: AsyncClient, session: AsyncSession
):
    """Rules are rebuilt from git on every deploy, so a decision spliced into a
    running container would not survive the next release. It goes to a table,
    and the queue reads the table over the files."""
    from sqlalchemy import select

    from app.models.flats import FlatsReadingRuling

    await _login(client, session)
    first = await client.get("/flats/reading/nofield")
    assert first.status_code == 200
    card = _first_card(first.text)
    assert card["queue"] == "nofield"

    response = await client.post(
        "/ui/flats/reading/rule",
        data={
            **card,
            "outcome": "design",
            "note": (
                "Read the whole section. Facade and materials standards for the "
                "design district — nothing dimensional the screen could hold."
            ),
        },
    )

    assert response.status_code == 200
    row = (
        await session.execute(
            select(FlatsReadingRuling).where(FlatsReadingRuling.path == card["path"])
        )
    ).scalar_one()
    assert row.outcome == "design"
    assert row.queue == "nofield"
    assert row.fingerprint, "a ruling remembers what it was about"
    assert row.decided_by, "a ruling is attributable or it is not a ruling"
    assert row.exported_at is None, "recorded, not yet in force"

    # And the card on screen is a different one — the queue moved on.
    assert _first_card(response.text).get("section") != card.get("section") or _first_card(
        response.text
    ).get("path") != card.get("path")


async def test_a_ruling_that_ordered_work_reaches_the_hand_off(
    client: AsyncClient, session: AsyncSession
):
    """A decision is not a disposal, and until now it was filed as one.

    "Encode this one" is a job. It was recorded in the queue that asked the
    question — the right place for the decision, the wrong place for the work
    — and somebody sitting down to a day of encoding had no way to see it as a
    list. The hand-off is where the day's reading becomes the next day's
    encoding.
    """
    await _login(client, session)
    page = await client.get("/flats/reading/missed")
    card = _first_card(page.text)

    ruled = await client.post(
        "/ui/flats/reading/rule",
        data={
            **card,
            "outcome": "encode",
            "note": (
                "The code prints a number here we do not hold for this field. "
                "Read the section against the table and encode what it says."
            ),
        },
    )
    assert ruled.status_code == 200

    handoff = await client.get("/flats/feedback")

    assert handoff.status_code == 200
    assert "Work ordered" in handoff.text
    assert card["path"].rsplit("/", 1)[-1] in handoff.text, "the document it is in"
    assert "Read the section against the table" in handoff.text, "and why"


async def test_a_ruling_that_disposed_of_a_card_orders_nothing(
    client: AsyncClient, session: AsyncSession
):
    """The list is only worth reading because most decisions are absent from
    it. "Design standard — not modelled" is a section finished, and printing it
    as work would make the hand-off another 4,693-row ledger."""
    await _login(client, session)
    page = await client.get("/flats/reading/nofield")
    card = _first_card(page.text)

    await client.post(
        "/ui/flats/reading/rule",
        data={
            **card,
            "outcome": "design",
            "note": (
                "Facade articulation and materials for the design district. "
                "Nothing dimensional in it the screen could hold."
            ),
        },
    )

    handoff = await client.get("/flats/feedback")

    assert "Facade articulation" not in handoff.text


async def test_an_answer_borrowed_from_another_queue_is_refused(
    client: AsyncClient, session: AsyncSession
):
    """"Different building" is a real answer to a section we have no field for
    and a meaningless one to a chapter nobody has opened. A ruling that answers
    a question it was not asked reads fine and means nothing."""
    await _login(client, session)
    page = await client.get("/flats/reading/chapter")
    card = _first_card(page.text)

    response = await client.post(
        "/ui/flats/reading/rule",
        data={
            **card,
            "outcome": "other_building",
            "note": "x" * 90,
        },
    )

    assert response.status_code == 400
    assert "answers this queue asks for" in response.text


async def test_a_reading_tag_with_no_reasoning_is_refused_and_the_words_kept(
    client: AsyncClient, session: AsyncSession
):
    """A card closed with a word nobody can check is worse than an open one:
    the open one still shows the sentences."""
    await _login(client, session)
    page = await client.get("/flats/reading/nofield")
    card = _first_card(page.text)

    response = await client.post(
        "/ui/flats/reading/rule",
        data={**card, "outcome": "design", "note": "no"},
    )

    assert response.status_code == 400
    assert "say why" in response.text
    assert "no</textarea>" in response.text, "what was typed survives the refusal"


async def test_skipping_a_reading_card_records_nothing(
    client: AsyncClient, session: AsyncSession
):
    """Skipping is a real answer to "I cannot rule on this yet" and has to cost
    nothing — the card stays where it was for whoever comes next."""
    from sqlalchemy import func, select

    from app.models.flats import FlatsReadingRuling

    await _login(client, session)
    page = await client.get("/flats/reading/missed")
    card = _first_card(page.text)

    response = await client.post(
        "/ui/flats/reading/rule", data={**card, "action": "skip"}
    )

    assert response.status_code == 200
    assert _first_card(response.text) != card, "it moved on"
    count = (
        await session.execute(
            select(func.count()).select_from(FlatsReadingRuling)
        )
    ).scalar_one()
    assert count == 0, "a skip is not a decision"


async def test_the_queues_are_reachable_without_knowing_the_url(
    client: AsyncClient, session: AsyncSession
):
    """A worklist nobody can navigate to is not shipped.

    Both review queues lived for weeks at URLs typed by hand: the sidebar
    offered Zoning Rules and Plans, and the rules index -- the page a person
    actually lands on -- linked to the gaps ledger and the feedback bundle and
    to neither queue. The inventory is not the work; the queues are.
    """
    await _login(client, session)

    nav = await client.get("/flats")

    assert nav.status_code == 200
    assert '"/flats/reading"' in nav.text or "/flats/reading" in nav.text
    assert "/flats/triage" in nav.text


# --- the word review ---------------------------------------------------------
#
# The queue underneath signing. Signing asks whether a number matches the
# sentence it was taken from; this asks whether the sentence measures what we
# think it measures. What these hold to is the same discipline the reading
# queues have -- one standing, one question, one row of buttons -- plus the one
# thing that is only true here: a word answered for Gresham is not answered for
# Portland, because the whole finding is that the same word means different
# things in different books.


def _first_word(html: str) -> dict[str, str]:
    """The hidden fields identifying the word card on screen."""
    out: dict[str, str] = {}
    for name in ("queue", "layer_id", "term", "fingerprint"):
        m = re.search(rf'name="{name}" value="([^"]*)"', html)
        if m:
            out[name] = m.group(1)
    return out


async def test_the_word_landing_names_a_standing_and_what_rests_on_it(
    client: AsyncClient, session: AsyncSession
):
    """Three standings, three different jobs. Two numbers on each, because
    "how many questions" and "how many numbers would have to be read again"
    say different things and a reviewer picks the day on the second."""
    await _login(client, session)

    response = await client.get("/flats/words")

    assert response.status_code == 200
    for title in ("No glossary read", "The code is quiet", "Defined here"):
        assert title in response.text
    assert "resting on them" in response.text


async def test_each_standing_offers_only_its_own_answers(
    client: AsyncClient, session: AsyncSession
):
    """"Means what we assumed" is not an answer anybody can give about a
    glossary nobody has opened."""
    await _login(client, session)

    defined = await client.get("/flats/words/defined")
    silent = await client.get("/flats/words/silent")

    assert defined.status_code == silent.status_code == 200
    assert "Means what we assumed" in defined.text
    assert "Quiet, and that is a gap" not in defined.text
    assert "Quiet, and that is a gap" in silent.text
    assert "Means what we assumed" not in silent.text


async def test_a_standing_that_does_not_exist_goes_back_to_the_menu(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)

    response = await client.get("/flats/words/everything", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/flats/words"


async def test_a_word_card_shows_what_it_costs_to_be_wrong(
    client: AsyncClient, session: AsyncSession
):
    """The reason the card is in front of anybody is not that the word is
    interesting. It is that these numbers are measured in it."""
    await _login(client, session)

    response = await client.get("/flats/words/defined")

    assert response.status_code == 200
    assert "Our numbers measured in this word" in response.text
    assert "measured in it" in response.text


async def test_a_word_ruling_lands_in_the_inbox_and_the_card_leaves(
    client: AsyncClient, session: AsyncSession
):
    """Rules are rebuilt from git on every deploy, so a decision spliced into
    a running container would not survive the next release."""
    from sqlalchemy import select

    from app.models.flats import FlatsWordRuling

    await _login(client, session)
    first = await client.get("/flats/words/defined")
    assert first.status_code == 200
    card = _first_word(first.text)
    assert card["queue"] == "defined"

    response = await client.post(
        "/ui/flats/words/rule",
        data={
            **card,
            "outcome": "matches",
            "note": (
                "Read the definition against how the screen measures it. Same "
                "edge, same exclusions - nothing here changes a number."
            ),
        },
    )

    assert response.status_code == 200
    row = (
        await session.execute(
            select(FlatsWordRuling).where(FlatsWordRuling.term == card["term"])
        )
    ).scalar_one()
    assert row.outcome == "matches"
    assert row.standing == "defined"
    assert row.layer == card["layer_id"]
    assert row.fingerprint, "a ruling remembers what the city said"
    assert row.decided_by, "a ruling is attributable or it is not a ruling"
    assert row.exported_at is None, "recorded, not yet in force"

    moved_on = _first_word(response.text)
    assert (moved_on.get("layer_id"), moved_on.get("term")) != (
        card["layer_id"],
        card["term"],
    )


async def test_a_word_ruling_that_ordered_work_reaches_the_hand_off(
    client: AsyncClient, session: AsyncSession
):
    """"This city measures it differently" is the loudest thing this queue can
    find: numbers already in production were read against the wrong edge. It
    is a job, and a job filed inside the queue that asked the question is a job
    nobody doing the encoding can see."""
    await _login(client, session)
    page = await client.get("/flats/words/defined")
    card = _first_word(page.text)

    ruled = await client.post(
        "/ui/flats/words/rule",
        data={
            **card,
            "outcome": "differs",
            "note": (
                "Measured at the building line here, not the front lot line, "
                "so every number on this field is against a different edge."
            ),
        },
    )
    assert ruled.status_code == 200

    handoff = await client.get("/flats/feedback")

    assert handoff.status_code == 200
    assert "Work ordered" in handoff.text
    assert card["term"] in handoff.text, "the word it is about"
    assert "Measured at the building line here" in handoff.text, "and why"


async def test_a_word_ruling_that_settled_the_word_orders_nothing(
    client: AsyncClient, session: AsyncSession
):
    """The hand-off is only worth reading because most decisions are absent
    from it."""
    await _login(client, session)
    page = await client.get("/flats/words/defined")
    card = _first_word(page.text)

    await client.post(
        "/ui/flats/words/rule",
        data={
            **card,
            "outcome": "matches",
            "note": (
                "Definition read in full and it is the ordinary one: same edge, "
                "same exclusions, nothing our numbers assume differently."
            ),
        },
    )

    handoff = await client.get("/flats/feedback")

    assert "Definition read in full" not in handoff.text


async def test_a_word_answer_borrowed_from_another_standing_is_refused(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    page = await client.get("/flats/words/defined")
    card = _first_word(page.text)

    response = await client.post(
        "/ui/flats/words/rule",
        data={**card, "outcome": "find_glossary", "note": "x" * 90},
    )

    assert response.status_code == 400
    assert "answers this queue asks for" in response.text


async def test_a_word_ruling_with_no_reasoning_is_refused_and_the_words_kept(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    page = await client.get("/flats/words/defined")
    card = _first_word(page.text)

    response = await client.post(
        "/ui/flats/words/rule",
        data={**card, "outcome": "matches", "note": "no"},
    )

    assert response.status_code == 400
    assert "say why" in response.text
    assert "no</textarea>" in response.text, "what was typed survives the refusal"


async def test_skipping_a_word_card_records_nothing(
    client: AsyncClient, session: AsyncSession
):
    from sqlalchemy import func, select

    from app.models.flats import FlatsWordRuling

    await _login(client, session)
    page = await client.get("/flats/words/defined")
    card = _first_word(page.text)

    response = await client.post(
        "/ui/flats/words/rule", data={**card, "action": "skip"}
    )

    assert response.status_code == 200
    assert _first_word(response.text) != card, "it moved on"
    count = (
        await session.execute(select(func.count()).select_from(FlatsWordRuling))
    ).scalar_one()
    assert count == 0, "a skip is not a decision"


async def test_every_review_screen_is_reachable_from_the_sidebar(
    client: AsyncClient, session: AsyncSession
):
    """A queue nobody can navigate to is not shipped.

    Three of these lived for weeks at URLs typed by hand - fetch triage, the
    gaps ledger and the word queue were reachable only from inside another
    page, which for a reviewer who lands on the dashboard is the same as not
    existing.
    """
    await _login(client, session)

    page = await client.get("/flats")

    assert page.status_code == 200
    for href in (
        '"/flats"',
        '"/flats/words"',
        '"/flats/reading"',
        '"/flats/triage"',
        '"/flats/gaps"',
        '"/flats/feedback"',
        '"/flats/plans"',
    ):
        assert href in page.text, f"{href} is not in the sidebar"


async def test_a_silent_word_says_where_this_code_sends_the_reader(
    client: AsyncClient, session: AsyncSession
):
    """A card that says only "the glossary has no entry" hands the reviewer a
    hunt. Portland defines neither *lot width* nor *building height* and its
    own text points at Chapter 33.930, Measurements, for both — so the card
    shows the sentence that says so, and the answer is one click and a chapter
    number instead of twenty minutes."""
    await _login(client, session)

    response = await client.get(
        "/flats/words/silent?layer=or/multnomah/portland&field=max_height_ft"
    )

    assert response.status_code == 200
    if "Nothing left in this queue" in response.text:
        pytest.skip("Portland's height words have been ruled")
    assert "How this code writes it" in response.text
    assert "33.930" in response.text
    assert "sends the reader to" in response.text
