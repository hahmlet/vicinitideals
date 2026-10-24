"""The code library: the stored ordinances as readable pages, behind the login.

Read off the real store, because what is under test is that every document the
screen cites can be opened and read at the line the citation names. Tualatin
is the city cut into sections (FOLLOWUPS 73), so it carries the section,
proof-copy and page-map cases at once.
"""

from __future__ import annotations

import re

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import ui_flats_code as code
from flats.provenance.store import ProvenanceStore
from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio

CITY = "or/clackamas/tualatin"
SECTION = f"{CITY}/40/40.300.txt"


async def _login(client: AsyncClient, session: AsyncSession) -> None:
    _org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)


async def test_the_shelf_lists_every_jurisdiction_holding_a_document(client, session):
    await _login(client, session)
    page = await client.get("/flats/code")
    assert page.status_code == 200
    held = {ProvenanceStore().layer_of(p) for p in ProvenanceStore().documents()}
    shown = set(re.findall(r'data-shelf="([^"]+)"', page.text))
    assert shown == held
    assert 'href="/flats/code"' in page.text  # in the sidebar


async def test_a_cut_city_lists_its_sections_under_their_chapters(client, session):
    await _login(client, session)
    page = await client.get(f"/flats/code/{CITY}")
    assert page.status_code == 200
    assert f'href="/flats/code/{SECTION}"' in page.text
    assert f'href="/flats/code/{CITY}/40-41.residential.txt"' in page.text  # the proof copy


async def test_a_section_page_numbers_every_line_and_prints_its_fingerprint(client, session):
    await _login(client, session)
    page = await client.get(f"/flats/code/{SECTION}")
    assert page.status_code == 200
    doc = ProvenanceStore().load(SECTION)
    count = len(doc.text.splitlines())
    assert f'id="L{count}"' in page.text and f'id="L{count + 1}"' not in page.text
    assert f'data-fingerprint="{doc.sha256}"' in page.text
    # its book's pages, linked to the PDF the page map pins
    assert f"/flats/book/{CITY}/40-41.residential.txt#page=" in page.text
    # the cul-de-sac standard cites L58 (test_culdesac), and the line says so
    row = page.text.split('id="L58"', 1)[1].split("</tr>", 1)[0]
    assert 'class="readers"' in row


async def test_every_cited_line_is_marked_on_its_page(client, session):
    readers = code._readers()
    assert readers.get(SECTION), "Tualatin's residential standards cite this section"
    await _login(client, session)
    page = await client.get(f"/flats/code/{SECTION}")
    marked = {int(n) for n in re.findall(r'<tr id="L(\d+)" data-line="\d+" class="read"', page.text)}
    assert marked == set(readers[SECTION])


async def test_search_finds_lines_and_links_them(client, session):
    await _login(client, session)
    page = await client.get(f"/flats/code/{CITY}", params={"q": "cul-de-sac"})
    assert page.status_code == 200
    assert "data-search-results" in page.text
    assert re.search(rf'href="/flats/code/{re.escape(CITY)}/[^"#]+#L\d+"', page.text)


@pytest.mark.parametrize(
    "path",
    ["or/clackamas/nowhere", f"{CITY}/../../../../etc/passwd", f"{CITY}/40/40.300.txt.meta.json", f"{CITY}/sections.json"],
)
async def test_anything_the_store_did_not_fetch_is_refused(client, session, path):
    await _login(client, session)
    page = await client.get(f"/flats/code/{path}")
    assert page.status_code == 404


async def test_the_outline_nests_labels_and_hangs_bodies_under_them():
    lines = [
        "TDC 31.070.  Interpretation.",
        "(1)  The City Manager interprets the code.",
        "(2)  A party must apply.",
        "The application must describe:",
        "(a)  traffic;",
        "(h)  parking;",
        "(i)  occupants; and",
        "(3)  A decision follows.",
        "(a)  findings;",
        "(i)  of fact;",
        "(ii)  of law.",
        "MINIMUM SETBACKS",
        "Front 15 feet",
        "(Ord. 590-83 §1, 04-11-83; Ord. No. 1486-24, § 2, 6-10-24)",
    ]
    assert code.outline(lines) == [
        (0, ""),
        (0, "label"),
        (0, "label"),
        (1, "body"),
        (1, "label"),
        (1, "label"),
        (1, "label"),  # (i) after (h) is the ninth letter
        (0, "label"),
        (1, "label"),
        (2, "label"),  # (i) under (a) is the first numeral
        (2, "label"),
        (0, ""),  # a heading in capitals starts the outline over
        (0, ""),
        (0, "history"),
    ]


async def test_lines_the_extraction_kept_indented_are_left_as_printed():
    assert code.outline(["    (a)  indented already", "A.   B.   C."]) == [(0, ""), (0, "")]
