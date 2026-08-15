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
