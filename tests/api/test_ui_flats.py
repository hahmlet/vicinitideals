"""FLATS rule-review pages.

The pages exist so a reviewer can compare an encoded standard against the line
of code it was read from without checking out the repository. What these tests
hold to is that pairing: the value renders, the quote renders, and a quote that
cannot be resolved says so instead of rendering nothing.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


async def _login(client: AsyncClient, session: AsyncSession):
    _org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)
    return user


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
    await _login(client, session)
    page = await client.get("/flats/review/or/clackamas/wilsonville")
    ref = _first_ref(page.text)

    response = await client.post(
        "/ui/flats/sign-passage",
        data={"layer_id": "or/clackamas/wilsonville", "ref": ref, "verdict": "verified"},
        headers={"hx-request": "true"},
    )

    assert response.status_code == 200
    rows = (await session.execute(text_query())).all()
    assert len(rows) > 1, "a code passage states more than one standard"
    # Every one of them cites the passage that was on screen, and the numbers
    # come from the rule files rather than from the form.
    assert {r[5] for r in rows} == {"verified"}


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
    from app.api.routers.ui_flats import _within

    window = (138, 161)

    assert _within("doc.txt#L142", "doc.txt", window)
    assert _within("doc.txt#L138-L140", "doc.txt", window)
    assert not _within("doc.txt#L63", "doc.txt", window), "outside the window"
    assert not _within("doc.txt#L155-L170", "doc.txt", window), "runs past the end"
    assert not _within("other.txt#L142", "doc.txt", window), "another document"


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

    assert "Nothing open" in bundle.text


async def test_handing_the_bundle_on_clears_it_without_erasing_it(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _problem(client, note="wrong column")

    await client.post("/ui/flats/bundle", headers={"hx-request": "true"})
    open_now = await client.get("/flats/feedback")
    ever = await client.get("/flats/feedback?all=1")

    assert "Nothing open" in open_now.text
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
    body = page.text.split("have been acted on")[-1].split("The bundle")[0]
    assert "nobody has touched it" not in body.split("Everything you marked")[0]
