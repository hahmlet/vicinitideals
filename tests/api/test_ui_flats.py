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
