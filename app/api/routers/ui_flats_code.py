"""The code library: every stored ordinance, readable, one line per sentence.

The order is PDF, readable authoritative text, cited encoding (Steph,
2026-10-23). The middle step had no face. Its text sat in
``flats/provenance/docs`` where a reviewer could only reach it one citation
at a time, through the six-line window a card opens. This is the whole text,
read as a book: a shelf of jurisdictions, a contents page per jurisdiction,
and a page per document whose every line carries the number every citation
names, so ``/flats/code/or/clackamas/tualatin/40/40.300.txt#L58`` is both a
link and a citation.

Each line also says what the encoding reads off it. A number nobody cites is
what the reading queues exist to find, and a reader who can see which
sentences carry a value can see which ones do not.

Rendered from the store baked into the image, so a deploy is a new edition and
there is nothing to sync. Every page prints the hash of the text it shows and
the book it came out of, which is what lets someone holding a printout ask
whether it is still the edition the screen reads.

Behind the login like the rest of FLATS. Making it public is Steph's decision
(FOLLOWUPS 73).

Registered ahead of ``ui_flats``: that router ends in a catch-all
``/flats/{layer_id:path}`` that would otherwise swallow ``/flats/code``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import DBSession
from app.api.routers.ui_flats import _known_documents, _layers, _page_index, _store
from app.api.routers.ui_helpers import _base_ctx, _get_counts, _get_user, templates
from flats.encode import legible
from flats.encode.readiness import _quoted_parts
from flats.provenance.store import INDEX, ProvenanceError, parse_quote
from flats.rules.fields import FIELDS

router = APIRouter(include_in_schema=False)

#: Matches a search needs before it is cut off. A one-letter query matches
#: every line of a city's code, and a page of forty thousand rows helps nobody.
SEARCH_LIMIT = 200


@dataclass(frozen=True, slots=True)
class Entry:
    """One readable document on a jurisdiction's contents page."""

    path: str
    #: The section number for a section file, the file name otherwise.
    name: str
    #: The document's first line: a section's heading as the code prints it.
    heading: str
    #: The proof copy a section was cut from; empty for a whole document.
    proof: str = ""


@dataclass(frozen=True, slots=True)
class Shelf:
    """One jurisdiction's documents, in reading order."""

    layer: str
    label: str
    #: (chapter title, its entries). A cut chapter is its sections; a document
    #: nobody has cut yet is a chapter of one.
    chapters: tuple[tuple[str, tuple[Entry, ...]], ...]

    @property
    def documents(self) -> int:
        return sum(len(entries) for _, entries in self.chapters)

    @property
    def cut(self) -> bool:
        return any(entry.proof for _, entries in self.chapters for entry in entries)

    def order(self) -> list[str]:
        return [entry.path for _, entries in self.chapters for entry in entries]


def _heading(path: str) -> str:
    try:
        text = _store().text_path(path).read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        if line.strip():
            return " ".join(line.split())[:140]
    return ""


def _label(layer: str) -> str:
    found = _layers().get(layer)
    if found is not None and found.label:
        return found.label
    return layer.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ").title()


@lru_cache(maxsize=1)
def _library() -> dict[str, Shelf]:
    """Every jurisdiction that holds a stored document, keyed by layer id.

    Built once per process: the store is baked into the image, so a deploy is
    the only thing that changes it.
    """
    store = _store()
    parts = store.parts()
    by_layer: dict[str, dict[str, list[Entry]]] = defaultdict(lambda: defaultdict(list))
    for path in store.documents():
        layer = store.layer_of(path)
        part = parts.get(path)
        if part is not None:
            entry = Entry(path, part.number, _heading(path), part.proof)
            by_layer[layer][part.proof].append(entry)
        else:
            name = path.rsplit("/", 1)[-1].removesuffix(".txt")
            by_layer[layer][path].append(Entry(path, name, _heading(path)))
    out: dict[str, Shelf] = {}
    for layer, books in by_layer.items():
        chapters = []
        for book in sorted(books):
            entries = books[book]
            if entries[0].proof:
                entries.sort(key=lambda e: parts[e.path].first)
            title = book.rsplit("/", 1)[-1].removesuffix(".txt")
            chapters.append((title, tuple(entries)))
        out[layer] = Shelf(layer, _label(layer), tuple(chapters))
    return dict(sorted(out.items()))


@lru_cache(maxsize=1)
def _readers() -> dict[str, dict[int, tuple[dict[str, str], ...]]]:
    """For every stored document, which encoded values cite each of its lines.

    Every citation the trusted rule set carries, exceptions and step-backs
    included -- the same walk the readiness ladder checks, so a line shown here
    as read is a line the ladder holds to its number.
    """
    found: dict[str, dict[int, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for layer_id, layer in _layers().items():
        for zone, field, quote, number, _drawn in _quoted_parts(layer):
            if not quote:
                continue
            try:
                ref = parse_quote(quote)
            except ProvenanceError:
                continue
            base = field.split(" [", 1)[0]
            definition = FIELDS.get(base)
            shown = (definition.label if definition and definition.label else base).replace("_", " ")
            reader = {
                "layer": layer_id,
                "zone": zone,
                "field": field,
                "label": shown + field[len(base):],
                "number": "" if number is None else str(number),
            }
            for n in ref.numbers:
                found[ref.path][n].append(reader)
    return {path: {n: tuple(r) for n, r in lines.items()} for path, lines in found.items()}


def _where(document: str) -> tuple[str, Shelf | None]:
    store = _store()
    layer = store.layer_of(document)
    return layer, _library().get(layer)


def _page_rows(document: str) -> dict[int, dict[str, Any]]:
    """The book pages that start on each line, keyed by line number."""
    index = _page_index(document)
    if index is None:
        return {}
    part = _store().part_of(document)
    book = part.proof if part is not None else document
    out: dict[int, dict[str, Any]] = {}
    for page in index.pages:
        out.setdefault(page.line, {"n": page.n, "cite": page.cite, "book": book})
    return out


def _document(document: str) -> dict[str, Any]:
    store = _store()
    doc = store.load(document)
    layer, shelf = _where(document)
    part = store.part_of(document)
    readers = _readers().get(document, {})
    starts = _page_rows(document)
    lines = []
    for n, text in enumerate(doc.text.splitlines(), start=1):
        lines.append(
            {
                "n": n,
                "text": text,
                "grid": legible.is_grid(text),
                "page": starts.get(n),
                "readers": readers.get(n, ()),
            }
        )
    order = shelf.order() if shelf else []
    at = order.index(document) if document in order else -1
    sections = []
    if document in store.proofs():
        sections = [
            p for p in sorted(store.parts().values(), key=lambda p: p.first) if p.proof == document
        ]
    return {
        "document": document,
        "layer": layer,
        "label": shelf.label if shelf else _label(layer),
        "name": store.section_of(document) or document.rsplit("/", 1)[-1].removesuffix(".txt"),
        "heading": _heading(document),
        "url": doc.url,
        "retrieved": doc.retrieved,
        "sha256": doc.sha256,
        "extractor": doc.extractor,
        "part": part,
        "sections": sections,
        "lines": lines,
        "cited": sum(1 for line in lines if line["readers"]),
        "previous": order[at - 1] if at > 0 else "",
        "next": order[at + 1] if 0 <= at < len(order) - 1 else "",
        "readable": _readable(layer) if part is not None else "",
    }


def _readable(layer: str) -> str:
    """The cleaning a jurisdiction's section files were made with."""
    index = _store().root / layer / INDEX
    try:
        return json.loads(index.read_text(encoding="utf-8")).get("readable", "")
    except (OSError, ValueError):
        return ""


def _search(shelf: Shelf, q: str) -> list[dict[str, Any]]:
    """Lines of one jurisdiction's code containing every word of the query."""
    words = [w.lower() for w in q.split() if w.strip()]
    if not words:
        return []
    store = _store()
    hits: list[dict[str, Any]] = []
    for _, entries in shelf.chapters:
        for entry in entries:
            text = store.text_path(entry.path).read_text(encoding="utf-8")
            for n, line in enumerate(text.splitlines(), start=1):
                low = line.lower()
                if all(w in low for w in words):
                    hits.append({"path": entry.path, "name": entry.name, "n": n, "text": line.strip()})
                    if len(hits) >= SEARCH_LIMIT:
                        return hits
    return hits


def _counties() -> list[tuple[str, list[Shelf]]]:
    grouped: dict[str, list[Shelf]] = defaultdict(list)
    for layer, shelf in _library().items():
        parts = layer.split("/")
        county = parts[1].replace("-", " ").title() if len(parts) > 2 else "Statewide"
        grouped[county].append(shelf)
    return sorted(grouped.items(), key=lambda kv: (kv[0] == "Statewide", kv[0]))


@router.get("/flats/code", response_class=HTMLResponse)
async def flats_code_index(request: Request, session: DBSession) -> HTMLResponse:
    """The shelf: every jurisdiction whose code the screen reads."""
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    counties = await run_in_threadpool(_counties)
    return templates.TemplateResponse(
        request,
        "flats_code_index.html",
        {
            **_base_ctx(user, dedup_count, "flats_code", conflicts_count=conflicts_count),
            "counties": counties,
        },
    )


@router.get("/flats/code/{path:path}", response_class=HTMLResponse)
async def flats_code(
    request: Request, session: DBSession, path: str, q: str = Query("", max_length=200)
) -> HTMLResponse:
    """A jurisdiction's contents page, or one of its documents.

    The path is checked against what the store holds before anything is built
    from it -- a jurisdiction the library lists or a document the store
    fetched or cut -- so nothing typed into the address bar reaches the disk.
    """
    user = await _get_user(session, request)
    path = path.strip("/")
    library = await run_in_threadpool(_library)
    if path in library:
        shelf = library[path]
        hits = await run_in_threadpool(_search, shelf, q) if q.strip() else []
        dedup_count, conflicts_count = await _get_counts(session)
        return templates.TemplateResponse(
            request,
            "flats_code_city.html",
            {
                **_base_ctx(user, dedup_count, "flats_code", conflicts_count=conflicts_count),
                "shelf": shelf,
                "q": q,
                "hits": hits,
                "limit": SEARCH_LIMIT,
            },
        )
    if path not in _known_documents():
        return HTMLResponse("no such stored document", status_code=404)
    try:
        ctx = await run_in_threadpool(_document, path)
    except (ProvenanceError, OSError) as exc:
        return HTMLResponse(f"that document cannot be read: {exc}", status_code=409)
    dedup_count, conflicts_count = await _get_counts(session)
    return templates.TemplateResponse(
        request,
        "flats_code_document.html",
        {**_base_ctx(user, dedup_count, "flats_code", conflicts_count=conflicts_count), **ctx},
    )
