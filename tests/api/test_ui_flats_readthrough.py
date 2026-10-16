"""Whole-document page-check submissions and coverage records."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import ui_flats_check as check
from app.models.flats import FlatsDocumentReadthrough
from flats.provenance.pages import Page
from flats.provenance import sheet
from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio

DOCUMENT = "or/multnomah/test/code.pdf"
_INDEX = SimpleNamespace(
    pages=(Page(1, 1, "1"), Page(2, 3, "2")),
    source_sha256="a" * 64,
)


@pytest.fixture(autouse=True)
def _readthrough_book(monkeypatch):
    monkeypatch.setattr(check, "_known_documents", lambda: frozenset({DOCUMENT}))
    monkeypatch.setattr(check, "_page_index", lambda document: _INDEX if document == DOCUMENT else None)
    monkeypatch.setattr(
        check,
        "_encoded_on",
        lambda document, page: ((sheet.Box(0.1, 0.2, 0.3, 0.4), "Rule label", frozenset({"mark"})),),
    )
    monkeypatch.setattr(check, "_set_aside_on", lambda document, page: ())
    monkeypatch.setattr(check.sheet, "lines_of", lambda store, document: ["Chapter heading", "Body", "Section heading", "More text"])


async def _login(client: AsyncClient, session: AsyncSession):
    _org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)
    return user


async def test_readthrough_lists_mapped_documents_and_every_page(client, session):
    await _login(client, session)

    index = await client.get("/flats/check/readthrough")
    book = await client.get(f"/flats/check/readthrough/{DOCUMENT}")
    cards = await client.get("/flats/check")

    assert index.status_code == 200
    assert DOCUMENT in index.text
    assert "Not read yet" in index.text
    assert "/flats/check/readthrough" in cards.text
    assert book.status_code == 200
    assert 'data-read-page="1"' in book.text
    assert 'data-read-page="2"' in book.text
    assert "check-box-encoded" in book.text
    assert "Chapter heading" in book.text
    assert "Section heading" in book.text
    assert "/flats/sheet/" + DOCUMENT + "?page=1" in book.text


async def test_submission_is_append_only_and_coverage_shows_latest_reader(
    client, session
):
    user = await _login(client, session)
    comments = [{"page": 2, "text": "A missing exception", "box": [0.1, 0.2, 0.4, 0.3]}]
    data = {
        "document": DOCUMENT,
        "comments_json": json.dumps(comments),
        "read_confirmed": "yes",
    }

    response = await client.post("/ui/flats/readthrough", data=data)

    assert response.status_code == 303
    assert response.headers["location"].endswith("?submitted=1")
    first = (
        await session.execute(
            select(FlatsDocumentReadthrough).order_by(FlatsDocumentReadthrough.id)
        )
    ).scalars().one()
    assert first.document == DOCUMENT
    assert first.page_count == 2
    assert first.book_sha256 == "a" * 64
    assert first.comments == comments
    assert first.comment_count == 1
    assert first.reviewer_user_id == user.id

    coverage = await client.get("/flats/check/readthrough")
    assert first.reviewer in coverage.text
    assert ">1</td>" in coverage.text

    second = await client.post(
        "/ui/flats/readthrough",
        data={**data, "comments_json": "[]"},
    )
    assert second.status_code == 303
    saved = (
        await session.execute(
            select(FlatsDocumentReadthrough).order_by(FlatsDocumentReadthrough.id)
        )
    ).scalars().all()
    assert len(saved) == 2
    assert saved[0].comments == comments
    assert saved[1].comment_count == 0


async def test_submission_rejects_comments_outside_the_document(client, session):
    await _login(client, session)

    response = await client.post(
        "/ui/flats/readthrough",
        data={
            "document": DOCUMENT,
            "comments_json": json.dumps([{"page": 9, "text": "Forged page"}]),
            "read_confirmed": "yes",
        },
    )

    assert response.status_code == 400
    assert (await session.execute(select(FlatsDocumentReadthrough))).first() is None
