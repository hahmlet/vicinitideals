"""Check an encoded number against the printed page, not the text copy.

Signing asks whether a number matches our *text copy* of the code. That is the
wrong place to catch the commonest real error: the right number read off the
wrong row or column of a table. Extraction flattens the grid that says which
number belongs to which zone, so a misfiled number reads perfectly in the text
copy. On the printed table it is obvious.

So each card here shows the page as the city prints it -- rendered from the
book the page map pins -- with a box drawn on the cell the quote came from
(``flats.provenance.sheet``), and asks one question: does it say this? Then one
card per footnote printed on that number, its row or its column: does the note
change it?

A "no" is not fixed here. It lands on the problems list with what the reviewer
said the page says, and whoever fixes it goes back to the text copy to find out
why the two disagree -- a wrong column, a mis-read footnote, a stale edition.

Registered ahead of ``ui_flats``: that router ends in a catch-all
``/flats/{layer_id:path}`` that would otherwise swallow ``/flats/check``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from sqlalchemy import select, update
from starlette.concurrency import run_in_threadpool

from app.api.deps import DBSession
from app.api.routers.ui_flats import (
    _cited_lines,
    _known_documents,
    _layers,
    _mark,
    _number,
    _ranges,
    _store,
    _value_rows,
)
from app.api.routers.ui_helpers import _base_ctx, _get_counts, _get_user, templates
from app.models.flats import FlatsPageCheck, FlatsRuleSignature
from flats.provenance import books, pages as page_map, sheet
from flats.rules.fields import FIELDS
from flats.rules.model import Layer

router = APIRouter(include_in_schema=False)

#: What a reviewer may say about the boxed number, in the words the buttons use.
VALUE_ANSWERS = {
    "matches": "Yes, the page says this",
    "differs": "No, the page says something else",
    "wrong_box": "The box is on the wrong spot",
    "unclear": "Can't tell from this page",
}

#: What a reviewer may say about one footnote printed on the number.
NOTE_ANSWERS = {
    "no_change": "No, it doesn't change this number",
    "have_it": "Yes, and we already have that",
    "missing": "Yes, and we're missing it",
    "unclear": "Can't tell",
}

#: A flag on the page itself: something printed there that the rules do not
#: hold. Not an answer to the card's question, so it never moves the queue.
FLAG = "unmarked"

#: Answers that mean something needs fixing. They make the problems list.
PROBLEMS = frozenset({"differs", "wrong_box", "missing", FLAG})

#: Answers that end the questions about a number. A box on the wrong cell, or
#: a number the page contradicts, has no footnotes worth asking about: they
#: would be the footnotes of a cell that is not this standard.
_STOPS = frozenset({"differs", "wrong_box", "unclear"})

#: What the reviewer is told happened.
_SAID = {
    "matches": "checked — the page agrees",
    "no_change": "noted — the footnote leaves it as it is",
    "have_it": "noted — the footnote is already in the rules",
    "unclear": "noted as unclear — it stays on the list to look at again",
    "differs": "problem raised — it goes on the problems list to be traced back",
    "wrong_box": "problem raised — the box was wrong, so the reading is traced back",
    "missing": "problem raised — the footnote goes on the list as something to add",
    FLAG: "flag saved to the problems list — this card's own question is still open, answer it above",
}

#: Every answer's words, for the problems list.
_WORDS = {**VALUE_ANSWERS, **NOTE_ANSWERS, FLAG: "Flagged: not in the rules"}

#: Units by field-name suffix, for saying a number out loud.
_UNITS = (("_sqft", "sq ft"), ("_ft", "ft"), ("_pct", "%"), ("_du_per_acre", "units per acre"))

#: The sign-off verdict that counts as signed, for ordering the queue.
_SIGNED = "verified"


# --- which numbers can be checked -------------------------------------------


@lru_cache(maxsize=512)
def _page_index(document: str) -> Any:
    """The document's page map, read once per process -- the store is baked in."""
    try:
        return page_map.read(_store(), document)
    except Exception:  # noqa: BLE001 — a bad sidecar reads as no map
        return None


@lru_cache(maxsize=512)
def _web_only(document: str) -> bool:
    """Whether this document is published as a web page rather than a book."""
    try:
        return page_map._is_html(_store().load(document).url)
    except Exception:  # noqa: BLE001
        return False


def _checkable(document: str) -> str:
    """"" when a card can show this document's pages, else why not."""
    if not document or document not in _known_documents():
        return "no_map"
    if _page_index(document) is not None:
        return ""
    return "html" if _web_only(document) else "no_map"


@lru_cache(maxsize=4096)
def _placed_cached(document: str, ranges: tuple, value_json: str, zone: str) -> sheet.Placed:
    return sheet.locate(_store(), document, list(ranges), json.loads(value_json), zone=zone)


def _placed(row: dict[str, Any]) -> sheet.Placed:
    """Where a number's box goes. Cached: every card after this one asks again."""
    document = row["quote"].partition("#L")[0]
    return _placed_cached(
        document,
        tuple(_ranges(row["quote"])),
        json.dumps(row["value"], sort_keys=True, default=str),
        row["zone"],
    )


def _unit(field: str) -> str:
    for suffix, unit in _UNITS:
        if field.endswith(suffix):
            return unit
    return ""


def _said(value: Any, field: str) -> str:
    """A number as a person would say it: "5,000 sq ft", "35 ft", "yes"."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return "none"
    if isinstance(value, (int, float)):
        shown = f"{value:,.0f}" if float(value).is_integer() else f"{value:,}"
        unit = _unit(field)
        return f"{shown}{unit}" if unit == "%" else f"{shown} {unit}".strip()
    return str(value).replace("_", " ")


def _label(field: str) -> str:
    known = FIELDS.get(field)
    return known.shown if known else field.replace("_", " ")


def _layer_label(layer: Layer) -> str:
    return layer.label or layer.layer.rsplit("/", 1)[-1]


# --- answers ----------------------------------------------------------------


async def _answers(session: DBSession, layer_id: str | None = None) -> dict[tuple, FlatsPageCheck]:
    """The latest answer per (layer, zone, field, when, question)."""
    stmt = select(FlatsPageCheck).order_by(FlatsPageCheck.decided_at, FlatsPageCheck.id)
    if layer_id:
        stmt = stmt.where(FlatsPageCheck.layer == layer_id)
    rows = (await session.execute(stmt)).scalars()
    # Flags are keyed by their own id: two things flagged on one page are two
    # findings, not a later answer replacing an earlier one.
    return {(r.layer, r.zone, r.field, r.when_key, _flag_key(r)): r for r in rows}


def _flag_key(r: FlatsPageCheck) -> str:
    return f"{r.question}#{r.id}" if r.question.startswith("page:") else r.question


async def _signed(session: DBSession, layer_id: str | None = None) -> set[tuple]:
    """Addresses whose latest sign-off is a confirmation, for ordering."""
    stmt = select(FlatsRuleSignature).order_by(FlatsRuleSignature.decided_at)
    if layer_id:
        stmt = stmt.where(FlatsRuleSignature.layer == layer_id)
    latest: dict[tuple, FlatsRuleSignature] = {}
    for r in (await session.execute(stmt)).scalars():
        latest[(r.layer, r.zone, r.field, r.when_key)] = r
    return {k for k, r in latest.items() if r.verdict == _SIGNED}


def _standing(answer: FlatsPageCheck | None, row: dict[str, Any]) -> FlatsPageCheck | None:
    """An answer that is still about this number, or None.

    Change the number, its citation or its quote and the fingerprint moves,
    so the answer stops standing and the question comes back -- which is how a
    fix gets checked rather than assumed.
    """
    if answer is None or answer.fingerprint != row["mark"]:
        return None
    return answer


# --- the queue --------------------------------------------------------------


def _rows(layer: Layer, signed: set[tuple]) -> list[dict[str, Any]]:
    """Every checkable number in a layer, signed ones first, then page order.

    Signed first because those are the numbers the screen trusts: a signed
    number the page contradicts is a false answer on live lots, and an
    unsigned one is not yet in use.
    """
    out = []
    for row in _value_rows(layer):
        document = (row["quote"] or "").partition("#L")[0]
        if _checkable(document):
            continue
        spans = _ranges(row["quote"])
        row["document"] = document
        row["line"] = spans[0][0] if spans else 0
        row["signed"] = (layer.layer, row["zone"], row["field"], row["when"]) in signed
        out.append(row)
    return sorted(out, key=lambda r: (not r["signed"], r["document"], r["line"], r["zone"], r["field"]))


@dataclass
class _Ask:
    row: dict[str, Any]
    question: str


def _questions(
    layer: Layer, rows: list[dict[str, Any]], answers: dict[tuple, FlatsPageCheck]
) -> Any:
    """The unanswered questions, in order, generated lazily.

    A number's footnote questions are only known once its box is placed, and
    placing reads a page -- so this walks the queue and places as it goes, and
    the caller stops as soon as it has the card it needs.
    """
    for row in rows:
        key = (layer.layer, row["zone"], row["field"], row["when"])
        said = _standing(answers.get((*key, "value")), row)
        if said is None:
            yield _Ask(row, "value")
            continue
        if said.answer in _STOPS:
            continue
        for marker in _placed(row).markers:
            if _standing(answers.get((*key, f"note:{marker.mark}")), row) is None:
                yield _Ask(row, f"note:{marker.mark}")


def _next(
    layer: Layer,
    rows: list[dict[str, Any]],
    answers: dict[tuple, FlatsPageCheck],
    skipped: int,
) -> _Ask | None:
    for n, ask in enumerate(_questions(layer, rows, answers)):
        if n >= skipped:
            return ask
    return None


def _focus(rows: list[dict[str, Any]], zone: str, field: str, when: str) -> _Ask | None:
    for row in rows:
        if (row["zone"], row["field"], row["when"]) == (zone, field, when):
            return _Ask(row, "value")
    return None


# --- everything else we hold from a page ------------------------------------


@lru_cache(maxsize=1)
def _by_document() -> dict[str, list[dict[str, Any]]]:
    """Every encoded number in every layer, grouped by the document it cites."""
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for layer_id, layer in _layers().items():
        for row in _value_rows(layer):
            document = (row["quote"] or "").partition("#L")[0]
            if document:
                out[document].append({**row, "layer_id": layer_id})
    return out


def _on_page(index: Any, quote: str, page: int) -> bool:
    for a, b in _ranges(quote):
        for n in range(a, b + 1):
            where = index.at(n)
            if where is not None and where.n == page:
                return True
    return False


@lru_cache(maxsize=256)
def _encoded_on(document: str, page: int) -> tuple[tuple[sheet.Box, str, frozenset], ...]:
    """Where each rule we hold from this page is printed, and what it is.

    Drawn faintly under the card's own box so the page reads as a map of what
    the rules took from it: a clause with nothing on it is one nobody encoded,
    which a reviewer can only see with the page in front of them. Each spot
    carries the rules read from it and their marks, so a card can leave out
    its own.
    """
    index = _page_index(document)
    if index is None:
        return ()
    spots: dict[tuple, dict[str, Any]] = {}
    for row in _by_document().get(document, []):
        if not _on_page(index, row["quote"], page):
            continue
        try:
            placed = _placed(row)
        except Exception:  # noqa: BLE001 — a rule that cannot be placed is not drawn
            continue
        label = f"{row['zone']} · {_label(row['field'])} = {_said(row['value'], row['field'])}"
        if row["when"]:
            label += f" (when {row['when_label'].replace('_', ' ')})"
        for box, _kind in placed.boxes.get(page, []):
            key = tuple(round(v, 3) for v in (box.x0, box.y0, box.x1, box.y1))
            spot = spots.setdefault(key, {"box": box, "labels": [], "marks": set()})
            if label not in spot["labels"]:
                spot["labels"].append(label)
            spot["marks"].add(row["mark"])
    out = []
    for spot in spots.values():
        labels = spot["labels"]
        title = "\n".join(labels[:12]) + ("\n…" if len(labels) > 12 else "")
        out.append((spot["box"], title, frozenset(spot["marks"])))
    return tuple(out)


# --- the card ---------------------------------------------------------------


def _sheet_view(
    document: str, page: int, boxes: list[tuple[sheet.Box, str]], mark: str = ""
) -> dict[str, Any]:
    index = _page_index(document)
    printed = next((p for p in index.pages if p.n == page), None) if index else None
    encoded = [
        {"css": box.pad(0.002).css(), "title": title}
        for box, title, marks in _encoded_on(document, page)
        if marks != {mark}
    ]
    return {
        "src": f"/flats/sheet/{document}?page={page}",
        "page": page,
        "cite": printed.cite if printed else f"PDF page {page}",
        "boxes": [{"css": box.css(), "kind": kind} for box, kind in boxes],
        "encoded": encoded,
    }


def _note_text(document: str, mark: str, after: int) -> tuple[int | None, list[str]]:
    """Where note ``mark`` is printed in our text copy, and what it says."""
    text = sheet.lines_of(_store(), document)
    at = sheet.note_line(text, mark, after)
    if at is None:
        return None, []
    body = [text[at - 1].strip()]
    for line in text[at : at + 12]:
        if not line.strip() or sheet.note_line([line], str(int(mark) + 1) if mark.isdigit() else "\0", 1):
            break
        body.append(line.strip())
    return at, body


def _variants(layer: Layer, zone: str, field: str) -> list[dict[str, str]]:
    """Every number we hold for this standard in this zone: base and variants."""
    values = layer.defaults if zone.startswith("(") else layer.zones[zone].values
    value = values.get(field)
    if value is None:
        return []
    out = [{"when": "normally", "value": _said(value.value, field)}]
    out += [
        {"when": ", ".join(v.key).replace("_", " "), "value": _said(v.value, field)}
        for v in value.variants
    ]
    return out


def _card(layer: Layer, ask: _Ask) -> dict[str, Any]:
    """Everything one card shows."""
    row = ask.row
    document = row["document"]
    placed = _placed(row)
    card: dict[str, Any] = {
        "layer_id": layer.layer,
        "layer_label": _layer_label(layer),
        "zone": row["zone"],
        "field": row["field"],
        "field_label": _label(row["field"]),
        "when": row["when"],
        "when_label": row["when_label"].replace("_", " "),
        "value": _said(row["value"], row["field"]),
        "signed": row["signed"],
        "cite": row["cite"],
        # The section alone: the cite's description restates the question.
        "section": (row["cite"] or "").split(",")[0].strip(),
        # A layer-wide rule has no zone worth naming on the card.
        "zone_label": "" if row["zone"].startswith("(") else row["zone"],
        "quote": row["quote"],
        "url": row["url"],
        "question": ask.question,
        "placed": placed.status,
        "placed_words": sheet.PLACED.get(placed.status, ""),
        "sheets": [],
        "answers": list(VALUE_ANSWERS.items()),
    }
    if ask.question == "value":
        for page in placed.pages[:2]:
            card["sheets"].append(
                _sheet_view(document, page, placed.boxes.get(page, []), row["mark"])
            )
        return card

    mark = ask.question.partition(":")[2]
    marker = next((m for m in placed.markers if m.mark == mark), None)
    card["answers"] = list(NOTE_ANSWERS.items())
    card["mark"] = mark
    card["mark_on"] = marker.on if marker else "number"
    page = placed.marker_page or (placed.pages[0] if placed.pages else 1)
    boxes = [b for b in placed.boxes.get(page, []) if b[1] == "value"]
    if marker:
        boxes.append((marker.box.pad(0.004), "marker"))
    at, body = _note_text(document, mark, row["line"])
    card["note_text"] = body
    card["variants"] = _variants(layer, row["zone"], row["field"])
    note_page = None
    if at is not None and (index := _page_index(document)) is not None:
        where = index.at(at)
        note_page = where.n if where else None
    if note_page == page:
        boxes += _note_box(document, note_page, body)
    card["sheets"].append(_sheet_view(document, page, boxes, row["mark"]))
    if note_page and note_page != page:
        card["sheets"].append(
            _sheet_view(document, note_page, _note_box(document, note_page, body), row["mark"])
        )
    return card


def _note_box(document: str, page: int, body: list[str]) -> list[tuple[sheet.Box, str]]:
    """A box around the note's first line on its page, where it can be found."""
    if not body:
        return []
    try:
        printed = sheet.read(books.ensure(_store(), document), page)
    except (books.BookError, Exception):  # noqa: BLE001 — no box is an answer
        return []
    line = sheet.find(printed, body[0])
    return [(line.box.pad(0.002), "note")] if line else []


def _counts(layer: Layer, rows: list[dict[str, Any]], answers: dict[tuple, FlatsPageCheck]) -> dict[str, int]:
    checked = problems = 0
    for row in rows:
        said = _standing(
            answers.get((layer.layer, row["zone"], row["field"], row["when"], "value")), row
        )
        if said is not None:
            checked += 1
            problems += said.answer in PROBLEMS
    return {"numbers": len(rows), "checked": checked, "left": len(rows) - checked, "problems": problems}


async def _card_ctx(
    session: DBSession,
    layer: Layer,
    *,
    skipped: int = 0,
    focus: tuple[str, str, str] | None = None,
    said: str = "",
    error: str = "",
) -> dict[str, Any]:
    answers = await _answers(session, layer.layer)
    signed = await _signed(session, layer.layer)
    rows = await run_in_threadpool(_rows, layer, signed)
    ask = _focus(rows, *focus) if focus else None
    if ask is None:
        ask = await run_in_threadpool(_next, layer, rows, answers, skipped)
    card = await run_in_threadpool(_card, layer, ask) if ask else None
    if card and ask.question == "value":
        before = _standing(
            answers.get((layer.layer, ask.row["zone"], ask.row["field"], ask.row["when"], "value")),
            ask.row,
        )
        card["before"] = before.answer if before else ""
    return {
        "layer": {"id": layer.layer, "label": _layer_label(layer)},
        "card": card,
        "counts": _counts(layer, rows, answers),
        "skipped": skipped,
        "said": said,
        "error": error,
    }


# --- routes -----------------------------------------------------------------


@router.get("/flats/sheet/{document:path}", response_model=None)
async def flats_sheet(
    request: Request, session: DBSession, document: str, page: int = Query(1, ge=1)
) -> FileResponse | HTMLResponse:
    """One page of a book, as an image a card can draw boxes over.

    Rendered on the server rather than in the browser: the box has to land on
    the pixel the server measured, and the browser's own PDF viewer offers no
    way to draw on its page.
    """
    await _get_user(session, request)
    if document not in _known_documents() or _page_index(document) is None:
        return HTMLResponse("no page map for this document", status_code=404)
    try:
        book = await run_in_threadpool(books.ensure, _store(), document)
        image = await run_in_threadpool(sheet.render, book, page)
    except books.BookError as exc:
        return HTMLResponse(str(exc), status_code=409)
    except Exception:  # noqa: BLE001 — a page out of range, a broken render
        return HTMLResponse("that page cannot be drawn", status_code=404)
    return FileResponse(
        image,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/flats/check", response_class=HTMLResponse)
async def flats_check_index(request: Request, session: DBSession) -> HTMLResponse:
    """Every jurisdiction's page check at a glance, and the problems raised."""
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    answers = await _answers(session)
    signed = await _signed(session)

    def build() -> tuple[list[dict[str, Any]], dict[str, int], list[dict[str, Any]]]:
        layers = _layers()
        table, totals, problems = [], {"numbers": 0, "checked": 0, "problems": 0, "no_map": 0, "html": 0}, []
        for layer_id, layer in sorted(layers.items()):
            rows = _rows(layer, signed)
            counts = _counts(layer, rows, answers)
            elsewhere = {"no_map": 0, "html": 0}
            for row in _value_rows(layer):
                why = _checkable((row["quote"] or "").partition("#L")[0])
                if why:
                    elsewhere[why] += 1
            if not rows and not any(elsewhere.values()):
                continue
            table.append({"id": layer_id, "label": _layer_label(layer), **counts, **elsewhere})
            for key in ("numbers", "checked", "problems"):
                totals[key] += counts[key]
            for key in ("no_map", "html"):
                totals[key] += elsewhere[key]
            by_address = {(r["zone"], r["field"], r["when"]): r for r in rows}
            for (lid, zone, field, when, question), answer in answers.items():
                row = by_address.get((zone, field, when))
                if lid != layer_id or row is None or answer.answer not in PROBLEMS:
                    continue
                if _standing(answer, row) is None:
                    continue
                problems.append(
                    {
                        "layer_id": layer_id,
                        "layer_label": _layer_label(layer),
                        "zone": zone,
                        "field": field,
                        "field_label": _label(field),
                        "when": when,
                        "value": _said(row["value"], field),
                        "question": answer.question,
                        "answer": answer.answer,
                        "answer_words": _WORDS.get(answer.answer, ""),
                        "says": answer.says,
                        "note": answer.note,
                        "by": answer.reviewer,
                        "at": answer.decided_at,
                        "handed_on": answer.bundled_at is not None,
                    }
                )
        return table, totals, sorted(problems, key=lambda p: p["at"], reverse=True)

    table, totals, problems = await run_in_threadpool(build)
    return templates.TemplateResponse(
        request,
        "flats_check_index.html",
        {
            **_base_ctx(user, dedup_count, "flats_check", conflicts_count=conflicts_count),
            "table": table,
            "totals": totals,
            "problems": problems,
        },
    )


@router.get("/flats/check/problems.txt", response_class=PlainTextResponse)
async def flats_check_problems(
    request: Request, session: DBSession, mark_handed_on: bool = Query(False)
) -> PlainTextResponse:
    """The problems list as text, each with our text copy of the lines cited.

    For whoever traces the problems back: the reviewer said the page and the
    rules disagree, and the text copy is where the disagreement started.
    ``mark_handed_on`` stamps them as handed on, so the next export is only
    what is new.
    """
    await _get_user(session, request)
    answers = await _answers(session)
    layers = _layers()
    out: list[str] = []
    ids: list[int] = []
    for (layer_id, zone, field, when, question), answer in sorted(
        answers.items(), key=lambda kv: kv[1].decided_at
    ):
        layer = layers.get(layer_id)
        if layer is None or answer.answer not in PROBLEMS or answer.bundled_at is not None:
            continue
        number = _number(layer, zone, field, when)
        if number is None or answer.fingerprint != _mark(layer_id, zone, field, when, number):
            continue
        lines, _error = _cited_lines(answer.quote)
        out += [
            f"== {layer_id} | {zone} | {field}{' when ' + when if when else ''} = {answer.value!r}",
            f"   question: {question}   answer: {answer.answer}   by {answer.reviewer} {answer.decided_at:%Y-%m-%d}",
            f"   page: PDF page {answer.page}   box: {answer.placed}   cite: {answer.quote}",
        ]
        if answer.says:
            out.append(f"   the page says: {answer.says}")
        if answer.note:
            out.append(f"   note: {answer.note}")
        out.append("   our text copy:")
        out += [f"   {'>' if line['quoted'] else ' '}{line['n']:>6}  {line['text']}" for line in lines]
        out.append("")
        ids.append(answer.id)
    if mark_handed_on and ids:
        await session.execute(
            update(FlatsPageCheck)
            .where(FlatsPageCheck.id.in_(ids))
            .values(bundled_at=datetime.now(timezone.utc))
        )
        await session.commit()
    return PlainTextResponse("\n".join(out) or "no open problems\n")


@router.get("/flats/check/{layer_id:path}", response_class=HTMLResponse)
async def flats_check(
    request: Request,
    session: DBSession,
    layer_id: str,
    skipped: int = Query(0, ge=0),
    zone: str = Query(""),
    field: str = Query(""),
    when: str = Query(""),
) -> HTMLResponse:
    """One jurisdiction's page check: one card, one question, four buttons."""
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    layer = _layers().get(layer_id.strip("/"))
    if layer is None:
        return HTMLResponse("no such jurisdiction", status_code=404)
    ctx = await _card_ctx(
        session, layer, skipped=skipped, focus=(zone, field, when) if zone and field else None
    )
    return templates.TemplateResponse(
        request,
        "flats_check.html",
        {**_base_ctx(user, dedup_count, "flats_check", conflicts_count=conflicts_count), **ctx},
    )


@router.post("/ui/flats/check", response_class=HTMLResponse)
async def flats_check_answer(
    request: Request,
    session: DBSession,
    layer_id: str = Form(...),
    zone: str = Form(...),
    field: str = Form(...),
    when: str = Form(""),
    question: str = Form("value"),
    answer: str = Form(""),
    says: str = Form(""),
    note: str = Form(""),
    comment: str = Form(""),
    flag_page: int = Form(0),
    action: str = Form("answer"),
    skipped: int = Form(0),
) -> HTMLResponse:
    """Record one answer, or skip, and hand back the next card.

    The number, its citation, the page and the box are all recomputed here
    from the server's own copies. What the browser sends is an address and an
    answer; evidence arriving from the browser is evidence somebody could have
    written.
    """
    user = await _get_user(session, request)
    layer = _layers().get(layer_id.strip("/"))
    number = _number(layer, zone, field, when) if layer else None

    async def card(**kw: Any) -> HTMLResponse:
        ctx = await _card_ctx(session, layer, **kw)
        return templates.TemplateResponse(request, "partials/flats_check_card.html", ctx)

    if layer is None or number is None:
        return HTMLResponse("not a number we hold", status_code=400)
    if action == "skip":
        return await card(skipped=skipped + 1)
    # The card has one comment box. Under "No" it is what the page says;
    # with "Flag it" it is what the page has that the rules don't; under any
    # other answer it is a note.
    if action == "flag":
        question, answer, says = f"page:{flag_page}", FLAG, comment or says
    elif comment and answer == "differs":
        says = says or comment
    elif comment:
        note = note or comment
    flag_page = question.partition(":")[2] if question.startswith("page:") else ""
    if flag_page:
        if answer != FLAG or not flag_page.isdigit():
            return await card(skipped=skipped, error="pick one of the answers")
        if not says.strip():
            return await card(skipped=skipped, error="say what on the page is missing from the rules")
    else:
        allowed = VALUE_ANSWERS if question == "value" else NOTE_ANSWERS
        if answer not in allowed or not (question == "value" or question.startswith("note:")):
            return await card(skipped=skipped, error="pick one of the answers")
    if user is None:
        return HTMLResponse("sign in first", status_code=401)

    row = {
        "zone": zone,
        "field": field,
        "when": when,
        "value": number.value,
        "quote": number.prov.quote or "",
    }
    placed = await run_in_threadpool(_placed, row)
    document = row["quote"].partition("#L")[0]
    if flag_page:
        page = int(flag_page)
    elif question == "value":
        page = placed.first
    else:
        page = placed.marker_page or placed.first
    session.add(
        FlatsPageCheck(
            layer=layer.layer,
            zone=zone,
            field=field,
            when_key=when,
            value=number.value,
            fingerprint=_mark(layer.layer, zone, field, when, number),
            question=question[:40],
            answer=answer,
            says=says.strip()[:500],
            note=note.strip()[:2000],
            quote=row["quote"],
            page=page,
            placed=placed.status,
            book_sha256=books.expected(_store(), document) if document else "",
            reviewer=(user.email or str(user.id))[:80],
            reviewer_user_id=user.id,
        )
    )
    await session.commit()
    return await card(skipped=skipped, said=_SAID.get(answer, "recorded"))
