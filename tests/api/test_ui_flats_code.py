"""The code library: the stored ordinances as readable pages, behind the login.

Read off the real store, because what is under test is that every document the
screen cites can be opened and read at the line the citation names. Tualatin
is the city cut into sections (FOLLOWUPS 73), so it carries the section,
proof-copy and page-map cases at once.
"""

from __future__ import annotations

import json
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


async def test_a_checked_table_is_drawn_and_its_printed_lines_kept(client, session):
    # Table 40-3 (FOLLOWUPS 115): cells name the lines they come from, the
    # printed lines stay on the page so every citation still lands, and each
    # table says which reader drew it -- page 303's Docling reading was
    # refused, the one cut along the printed rules passed.
    await _login(client, session)
    page = await client.get(f"/flats/code/{SECTION}")
    assert page.status_code == 200
    assert page.text.count('class="code-table"') == 4
    assert re.search(r'<td data-lines="[\d ]*\b7[0-9]\b[\d ]*"', page.text)
    assert 'data-table="66-97"' in page.text and 'data-table="98-116"' in page.text
    assert 'id="L66"' in page.text and 'id="L97"' in page.text
    assert "Table drawn by Docling and checked" in page.text
    assert "Table drawn by pdfplumber, cut along the printed rules and checked" in page.text


async def test_a_table_every_reader_got_wrong_stays_as_lines_with_the_reason(client, session, monkeypatch):
    # No Tualatin table placed on its lines is refused by every reader today,
    # so the refused case is made: page 303 with only Docling's reading.
    from flats.provenance import tables as checked

    store = ProvenanceStore()
    part = store.parts()[SECTION]
    raw = json.loads((store.root / CITY / checked.PROPOSED).read_text(encoding="utf-8"))
    refused = checked.check(raw["pages"]["303"][0], part, store.load(SECTION).text.splitlines(), 303, "docling")
    assert not refused.shown and refused.first == 98
    monkeypatch.setattr(code, "tables", lambda _store=None: {SECTION: (refused,)})
    await _login(client, session)
    page = await client.get(f"/flats/code/{SECTION}")
    assert page.status_code == 200
    assert 'class="code-table"' not in page.text
    assert "rows 4 and 5 overlap on the page" in page.text
    assert 'id="L98"' in page.text


async def test_raised_marks_are_drawn_raised_and_linked_to_their_note(client, session):
    # Table 58-1 prints a raised 1 after "prohibited." pointing to note 1 on
    # line 39; the note says where it is marked.
    await _login(client, session)
    page = await client.get(f"/flats/code/{CITY}/58/58.200.txt")
    assert page.status_code == 200
    assert re.search(r'<sup class="mark" title="[^"]*"><a href="#L39">1</a></sup>', page.text)
    assert "↩ marked on" in page.text
