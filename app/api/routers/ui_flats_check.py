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
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select, update
from starlette.concurrency import run_in_threadpool

from app.api.deps import DBSession
from app.api.routers.ui_flats import (
    _cited_lines,
    _known_documents,
    _layers,
    _mark,
    _number,
    _page_index,
    _ranges,
    _store,
    _value_rows,
)
from app.api.routers.ui_helpers import _base_ctx, _get_counts, _get_user, templates
from app.models.flats import FlatsDocumentReadthrough, FlatsPageCheck, FlatsRuleSignature
from flats.encode import dispositions, footnotes, readiness
from flats.provenance import books, pages as page_map, sheet
from flats.rules import conditions
from flats.rules.fields import FIELDS
from flats.rules.model import Layer

router = APIRouter(include_in_schema=False)

#: What a reviewer may say about the boxed number, in the words the buttons use.
VALUE_ANSWERS = {
    "matches": "Yes, the page says this",
    "differs": "No, the page says something else",
    "wrong_box": "The box is on the wrong spot",
    "unclear": "Can't tell from this page",
    # Steph 2026-10-21: a footnote asked as though it were a table cell.
    # Files the card to be asked as a footnote instead.
    "footnote": "This is a footnote",
}

#: The note answers in the words of a card that says how we read the note:
#: the same four answers, so an answer means what it always meant.
READING_ANSWERS = {
    "have_it": "Yes, that is what the note says",
    "missing": "No, we read it wrong or missed part of it",
    "no_change": "It doesn't apply to this number",
    "unclear": "Can't tell",
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

#: Not a reviewer's answer: the question was put back after a fix that the
#: fingerprint cannot see -- a box moved, a footnote read, a card reworded --
#: so the fix is checked rather than assumed. ``note`` keeps what was said
#: before, ``says`` the comment, so the card can show both.
REOPENED = "reopened"

#: Not a reviewer's answer: our answer to a problem the reviewer raised,
#: stored under ``reply:<id of the row it answers>`` with the words in
#: ``note``. A problem with a reply leaves the open list for the answered one,
#: and the card shows the reply under the flag -- otherwise a problem traced,
#: explained or fixed stays listed as open forever, asking to be looked at.
REPLIED = "replied"

#: Answers that mean something needs fixing. They make the problems list.
PROBLEMS = frozenset({"differs", "wrong_box", "missing", "footnote", FLAG})

#: Answers that end the questions about a number. A box on the wrong cell, or
#: a number the page contradicts, has no footnotes worth asking about: they
#: would be the footnotes of a cell that is not this standard.
_STOPS = frozenset({"differs", "wrong_box", "unclear", "footnote"})

#: What the reviewer is told happened.
_SAID = {
    "matches": "checked — the page agrees",
    "no_change": "noted — the footnote leaves it as it is",
    "have_it": "noted — the footnote is already in the rules",
    "unclear": "noted as unclear — it stays on the list to look at again",
    "differs": "problem raised — it goes on the problems list to be traced back",
    "wrong_box": "problem raised — the box was wrong, so the reading is traced back",
    "missing": "problem raised — the footnote goes on the list as something to add",
    "footnote": "filed — it goes on the problems list to be asked as a footnote",
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
def _placed_cached(
    document: str, ranges: tuple, value_json: str, zone: str, field: str = "", when: str = ""
) -> sheet.Placed:
    return sheet.locate(
        _store(),
        document,
        list(ranges),
        json.loads(value_json),
        zone=zone,
        field=field,
        when=tuple(k for k in when.split("+") if k),
    )


def _placed(row: dict[str, Any]) -> sheet.Placed:
    """Where a number's box goes. Cached: every card after this one asks again.

    The box goes on the figure the page prints, which for a derived number is
    not the number held (:func:`_printed`).
    """
    document = row["quote"].partition("#L")[0]
    return _placed_cached(
        document,
        tuple(_ranges(row["quote"])),
        json.dumps(row.get("printed", row["value"]), sort_keys=True, default=str),
        _column_zone(row),
        row["field"],
        row["when"],
    )


def _column_zone(row: dict[str, Any]) -> str:
    """The zone whose column the number is read under.

    Its own, unless the page never prints it and the cite names the zone it
    borrows from: CMF's corridor height is "Table 4.0130 H (TLDR)", and the
    box went on LDR-5's 35 ft, the first of seven (Steph 2026-10-20).
    """
    document = row["quote"].partition("#L")[0]
    # "Table 4.0130 H (TLDR)" after "adopting"; a bare "(D)" or "(II)" is a
    # subsection or a review type, not a column.
    named = re.findall(r"adopt\w*\s[^()]*\(([A-Z][A-Za-z0-9-]*)\)", row.get("cite") or "")
    if not named or not _zone_off_page(document, row["line"], row["zone"]):
        return row["zone"]
    return next((z for z in reversed(named) if not _zone_off_page(document, row["line"], z)), row["zone"])


#: Why the number held is not the figure printed, in the order the citation
#: check picks the printed figure (:func:`flats.encode.readiness._printed`).
_DERIVED = (
    ("per_dwelling", "the page states it per home, and we hold it for our four"),
    ("sqft_per_unit", "the page states it per home, and we hold it for our four"),
    ("per_units", "the page states one space per so many homes, and we hold it per home"),
    ("spaces_total", "the page states spaces for the whole building, and we hold it per home"),
    ("acres", "the page states acres, and we hold square feet"),
    ("acres_per_dwelling", "the page states acres per home, and we hold the total for our four"),
    ("per_height_ft", "the page states it against the building's height, and we hold what that comes to for ours"),
    ("from_top_degrees", "the page states an angle off the top of the building, and we hold what that comes to for ours"),
    ("same_as", "the page sets it equal to another standard, held on that standard's own card"),
    (
        "before_step_back",
        "the page's setback, plus the step-back a building as tall as ours needs (a sloped line it may not rise above)",
    ),
    ("stories", "the page states stories, and we hold feet at the city's height per story"),
    ("before_acre", "the page states it per the city's own size of acre, and we hold it per standard acre"),
    ("before_story", "the page states it for one story plus more per story, and we hold it for our building"),
)
_DERIVED_VARIANT = (
    ("before_step_back", _DERIVED[9][1]),
    ("acres", _DERIVED[4][1]),
    ("per_dwelling", _DERIVED[0][1]),
    ("acres_per_dwelling", _DERIVED[5][1]),
    ("sqft_per_unit", _DERIVED[1][1]),
    ("times", "the page states the figure this is a multiple of"),
    ("spaces_total", _DERIVED[3][1]),
    ("pct_of_lot_width", "the page states a share of the lot's width, and we hold what that comes to"),
    ("reduce_pct", "the page states a reduction by this share, and we hold the number it leaves"),
)


def _printed(layer: Layer, row: dict[str, Any]) -> Any:
    """The figure the page prints for a number we hold.

    Usually the number itself. A derived one -- Gresham's LDR-5 rear setback
    is the table's 15 ft plus the 5 ft a 26 ft building steps back under
    7.0420(G)(1) -- is printed nowhere as held: Steph answered "differs" to
    "does the page say 20 ft?" on all three zones it reaches (2026-10-20). The
    card asks about the printed figure, the same one the citation check reads.
    """
    number = _number(layer, row["zone"], row["field"], row["when"])
    if number is None:
        return row["value"]
    return readiness._printed_variant(number) if row["when"] else readiness._printed(number)


def _derivation(layer: Layer, row: dict[str, Any]) -> tuple[str, str]:
    """The form a derived number is stored in, and why it is not the printed one."""
    number = _number(layer, row["zone"], row["field"], row["when"])
    for attr, why in _DERIVED_VARIANT if row["when"] else _DERIVED:
        if getattr(number, attr, None) is not None:
            return attr, why
    return "", ""


def _derived_why(layer: Layer, row: dict[str, Any]) -> str:
    """Why the number held is not the printed one, in a reviewer's words; "" when it is."""
    return _derivation(layer, row)[1]


#: The page's own figure, in the page's own unit, by the form it is stored in.
#: "1,742 units per acre" for a page that prints 1,742 square feet per home is
#: a question nobody can answer (2026-10-20). A form missing here is said in
#: the standard's unit -- a setback before its step-back is still feet -- and
#: a form mapped to None has no figure of its own worth asking about: the card
#: asks about the number held, as it did before.
_PRINTED_AS: dict[str, str | None] = {
    "per_dwelling": "{n} sq ft per home",
    "sqft_per_unit": "{n} sq ft per home",
    "acres": "{n} acres",
    "acres_per_dwelling": "{n} acres per home",
    "stories": "{n} stories",
    "spaces_total": "{n} spaces in all",
    "per_units": "one space per {n} homes",
    "from_top_degrees": "{n} degrees",
    "reduce_pct": "{n}% less",
    "pct_of_lot_width": "{n}% of the lot's width",
    "times": None,
    "per_height_ft": None,
}


def _printed_said(layer: Layer, row: dict[str, Any], printed: Any) -> str:
    """The printed figure as the page says it; "" where the card should not ask it."""
    attr, _why = _derivation(layer, row)
    if not attr:
        return ""
    form = _PRINTED_AS.get(attr, "")
    if form is None:
        return ""
    if not form:
        return _said(printed, row["field"])
    shown = f"{printed:,.0f}" if float(printed).is_integer() else f"{printed:,}"
    said = form.format(n=shown)
    return said.replace("1 acres", "1 acre") if shown == "1" else said


@lru_cache(maxsize=4096)
def _zone_off_page(document: str, line: int, zone: str) -> bool:
    """Whether the page a number is cited on never names its zone.

    Gresham's corridor CMF height is read off the residential table's TLDR
    column, because note 14 sends that corridor to TLDR's standards. Shown
    the page with nothing said, Steph found no CMF on it (2026-10-20). A card
    whose zone the page does not print says why the number is read there.
    """
    if zone.startswith("("):
        return False
    index = _page_index(document)
    page = index.at(line) if index is not None else None
    if page is None:
        return False
    later = [p.line for p in index.pages if p.line > page.line]
    lines = sheet.lines_of(_store(), document)[page.line - 1 : (min(later) - 1) if later else None]
    # Superscripts are stored inline -- "LDR-54" is LDR-5 with its note 4 --
    # so a digit may follow the name; a letter may not. "PDR6" is printed
    # "PDR-6": a hyphen or space may part letters from digits or not.
    parts = re.findall(r"[A-Za-z]+|\d+|[^\sA-Za-z\d-]", zone)
    name = r"[\s\-\u2010-\u2013]?".join(re.escape(p) for p in parts)
    return re.search(rf"(?<![A-Za-z0-9]){name}(?![A-Za-z])", " ".join(lines), re.IGNORECASE) is None


@lru_cache(maxsize=1024)
def _source_url(document: str) -> str:
    """Where the city publishes the stored document, from its own record."""
    try:
        return _store().load(document).url
    except Exception:  # noqa: BLE001 -- a document we cannot open links nowhere new
        return ""


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


def _condition_words(when: str) -> list[str]:
    """Each condition a variant hangs on, as the first sentence of its definition.

    The keys are our vocabulary ("unit_lots"); a reviewer needs the meaning,
    "the four units are being platted onto lots of their own".
    """
    out = []
    for key in _keys(when):
        try:
            text = conditions.condition(key).describe
        except Exception:  # noqa: BLE001 — an unregistered key reads as itself
            out.append(key.replace("_", " "))
            continue
        first = re.split(r"(?<=[.;:])\s", text, maxsplit=1)[0].rstrip(".;:")
        first = re.split(r",\s+which\b", first, maxsplit=1)[0]
        out.append(first[:1].lower() + first[1:])
    return out


#: Who a number is for, by plain name (Steph 2026-10-20: "I think we can just
#: call this 'townhouse'" -- the four homes platted onto lots of their own).
#: The card says "does not apply to townhomes in the LDR-5 zone".
_WHO: dict[str, str] = {
    "unit_lots": "townhomes",
    "attached_house_division": "attached houses",
}

#: Where a number applies, said the way a reviewer would say it (Steph
#: 2026-10-20: "abuts a street on two or more sides" is "corner lots"). The
#: definition's explanation -- "which swaps an interior side setback..." --
#: is for us, not for the card. A condition missing here falls back to the
#: first clause of its definition.
_WHERE: dict[str, str] = {
    "corner_lot": "on corner lots",
    "attached_wall": "on the party-wall line",
    "alley_at_rear": "where the alley is at the rear",
    "alley_at_side": "where the alley is at the side",
    "abuts_alley": "on lots with alley access",
    "abuts_residential_zone": "next to a residential zone",
    "abuts_lower_density_zone": "next to a lower-density residential zone",
    "abuts_nonresidential_zone": "where every non-street line borders a non-residential zone",
    "abuts_side_yard": "where the side line meets the neighbour's side yard",
    "abuts_park": "next to a park",
    "multi_story": "for buildings of two storeys or more",
    "low_rise": "below the height where the code steps this up",
    "fronts_cul_de_sac": "on cul-de-sac lots",
    "flag_lot": "on flag lots",
    "narrow_frontage": "on narrow-frontage lots",
    "local_street": "on a local street",
    "on_transit_street": "on a transit street",
    "civic_corridor": "on a mapped corridor",
    "civic_corridor_setback": "on a Civic Corridor",
    "civic_corridor_setback_all_streets": "where every street line is on a Civic Corridor",
    "inside_mapped_use_area": "inside an area the code maps within the zone",
    "constrained_sites_overlay": "in the Constrained Sites overlay",
    "willamette_greenway_zone": "in the Willamette Greenway zone",
    "willamette_historic_district": "in the Willamette Historic District",
    "middle_housing_child_lot": "on a lot from a middle housing land division",
    "state_middle_housing": "under the state middle housing law",
    "beyond_ugb_mile": "more than a mile from the urban growth boundary",
    "in_sewer_district": "inside a sewer district",
    "access_easement": "where an access easement crosses the lot",
    "conditional_use": "with conditional use approval",
    "adjustment": "with an adjustment",
    "planned_development": "with a Planned Development approval",
    "mixed_use": "with ground-floor non-residential space",
}

#: A lot-size band, said as a range: "on lots over 10,000 sq ft". Each
#: measure is a frame and the unit the range is said in.
_BANDS: dict[str, tuple[str, str]] = {
    "lot_sqft": ("on lots {}", "sq ft"),
    "lot_width_ft": ("on lots {}", "ft wide"),
    "lot_depth_ft": ("on lots {}", "ft deep"),
    "lrt_station_ft": ("{} from a light-rail station", "ft"),
    "rail_stop_ft": ("{} from a rail stop", "ft"),
    "transit_stop_ft": ("{} from a transit stop", "ft"),
    "frequent_route_ft": ("{} from a frequent bus route", "ft"),
}


def _keys(when: str) -> list[str]:
    """The conditions in a joined key. A band token can end in "+" ("10000+",
    ten thousand and up), so a key starts only where a "+" meets a letter."""
    return [k for k in re.split(r"\+(?=[a-z])", when) if k]


def _band_phrase(key: str) -> str | None:
    measure, _, spec = key.partition(":")
    if measure not in _BANDS or not spec:
        return None
    frame, unit = _BANDS[measure]

    def n(text: str) -> str:
        v = float(text)
        return f"{v:,.0f}" if v.is_integer() else f"{v:,}"

    try:
        if spec.startswith("<="):
            high = spec[2:]
            said = f"under {n(high[1:])} {unit}" if high.startswith("<") else f"{n(high)} {unit} or less"
        elif spec.endswith("+"):
            low = spec[:-1]
            said = f"over {n(low[1:])} {unit}" if low.startswith(">") else f"{n(low)} {unit} or more"
        elif "-" in spec:
            low, high = spec.split("-", 1)
            if low.startswith(">") or high.startswith("<"):
                low_said = f"over {n(low[1:])}" if low.startswith(">") else n(low)
                high_said = f"under {n(high[1:])}" if high.startswith("<") else n(high)
                joiner = " and " if low.startswith(">") and high.startswith("<") else (
                    " up to " if low.startswith(">") else " to "
                )
                said = f"{low_said}{joiner}{high_said} {unit}"
            else:
                said = f"{n(low)}–{n(high)} {unit}"
        elif spec.startswith(">"):
            said = f"over {n(spec[1:])} {unit}"
        else:
            return None
    except ValueError:
        return None
    # "On lots of 5,000 sq ft or less", but "on lots over 10,000 sq ft" and
    # "on lots under 100 ft wide".
    if frame.startswith("on lots") and unit == "sq ft" and said[0].isdigit():
        said = "of " + said
    return frame.format(said)


def _when_parts(when: str) -> tuple[str | None, str]:
    """Who a number is for, and where it applies: ("townhomes", "on corner
    lots"). Either can be empty; both empty is the zone's base number."""
    who, where = [], []
    for key in _keys(when):
        if key in _WHO:
            who.append(_WHO[key])
        elif key in _WHERE:
            where.append(_WHERE[key])
        else:
            where.append(_band_phrase(key) or "where " + _condition_words(key)[0])
    said = where[0] if len(where) == 1 else ", ".join(where[:-1]) + " and " + where[-1] if where else ""
    return (" and ".join(who) or None), said


def _when_phrase(when: str) -> str:
    """The case a number hangs on, as a card's list of other numbers says it:
    "for townhomes on corner lots"; nothing for the zone's base number."""
    who, where = _when_parts(when)
    return " ".join(filter(None, [f"for {who}" if who else "", where]))


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


def _replies(answers: dict[tuple, FlatsPageCheck]) -> dict[int, FlatsPageCheck]:
    """Our latest reply to each answered problem, by the id of the problem's row."""
    out = {}
    for r in answers.values():
        target = r.question.removeprefix("reply:")
        if r.answer == REPLIED and r.question.startswith("reply:") and target.isdigit():
            out[int(target)] = r
    return out


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
    if answer is None or answer.fingerprint != row["mark"] or answer.answer == REOPENED:
        return None
    return answer


# --- the queue --------------------------------------------------------------


_FIELD_ORDER = {name: n for n, name in enumerate(FIELDS)}


def _rows(layer: Layer, signed: set[tuple]) -> list[dict[str, Any]]:
    """Every checkable number in a layer, signed ones first, then by row.

    Signed first because those are the numbers the screen trusts: a signed
    number the page contradicts is a false answer on live lots, and an
    unsigned one is not yet in use.
    """
    out = []
    for row in _value_rows(layer):
        document = (row["quote"] or "").partition("#L")[0]
        why = _checkable(document)
        if why and why != "html":
            continue
        spans = _ranges(row["quote"])
        row["document"] = document
        row["line"] = spans[0][0] if spans else 0
        row["signed"] = (layer.layer, row["zone"], row["field"], row["when"]) in signed
        row["printed"] = _printed(layer, row)
        # A web code has no printed page: its card shows the stored text.
        row["web"] = why == "html"
        row["in_note"] = _in_note(document, row["quote"] or "")
        out.append(row)
    base = {(r["zone"], r["field"]): r for r in out if not r["when"]}
    for row in out:
        row["two_source"] = _two_source(row, base.get((row["zone"], row["field"])))
    _carry(out)
    # By row of the table (Steph 2026-10-19): within a document, one data
    # point across every zone before the next, the data points in the order
    # they first appear. Sorting on the cited line alone flipped Gresham's
    # cards between min and max density, because a collapsed table's range
    # citations interleave. Web numbers queue after every printed one.
    first: dict[tuple, int] = {}
    for r in out:
        group = (r["web"], r["signed"], r["document"], r["field"])
        first[group] = min(first.get(group, r["line"]), r["line"])
    return sorted(
        out,
        key=lambda r: (
            r["web"],
            not r["signed"],
            r["document"],
            first[(r["web"], r["signed"], r["document"], r["field"])],
            # A collapsed table cites several rows from one line; the field
            # list's own order (lot size, min density, max density, ...)
            # breaks the tie the way the printed tables run.
            _FIELD_ORDER.get(r["field"], len(_FIELD_ORDER)),
            r["field"],
            r["line"],
            r["zone"],
        ),
    )


def _two_source(row: dict[str, Any], parent: dict[str, Any] | None) -> str:
    """Why a number cannot be checked against the one page a card shows, or "".

    Steph 2026-10-22, on Gresham CMF's building-share basis, read off the
    Site definition: "this is asking for comparing 2 PDFs and we only show
    one. I am taking it on its word that GDC 7.0420(J)(1)(a) and
    7.0512(A)(2) S2 actually says 'site' and doesn't have a different
    qualification that modifies." Such a number waits for a check that
    shows both sources side by side; the page check asks only what one
    page can answer.

    - ``via``: a cross-reference sends the reader to the quoted text (CMF's
      corridor values, Table 4.0430 note 14 adopting 4.0131).
    - ``borrowed``: the page never names the zone, so what ties the zone to
      the page lives somewhere else.
    - ``modified``: an exception read from another document than the
      zone's own number -- a district or overlay changing the base rule.
    """
    if row.get("via"):
        return "via"
    if not row["web"] and _zone_off_page(row["document"], row["line"], row["zone"]):
        return "borrowed"
    if row["when"] and parent is not None and parent["document"] and parent["document"] != row["document"]:
        return "modified"
    return ""


def _single(row: dict[str, Any]) -> bool:
    """Whether the page check asks about this number (:func:`_two_source`)."""
    parent = row.get("carried_by")
    return not row.get("two_source") and not (parent is not None and parent.get("two_source"))


@lru_cache(maxsize=512)
def _census(document: str) -> footnotes.Census:
    """The footnote census of one stored document, read once per process."""
    return footnotes.census("\n".join(sheet.lines_of(_store(), document)), doc=document)


def _in_note(document: str, quote: str) -> str:
    """The note a quote is read from, where every line it quotes is that note's.

    The census's own reading of the document's notes blocks: a quoted line
    inside a block belongs to the last note opened at or above it. A quote
    that also takes in a table line, the block's heading, or a second note is
    not a footnote's alone, and answers "".
    """
    if not document or "#L" not in quote:
        return ""
    try:
        blocks = _census(document).blocks
    except Exception:  # noqa: BLE001 — no census is no note
        return ""
    marks = set()
    for first, last in _ranges(quote):
        for n in range(first, last + 1):
            block = next((b for b in blocks if any(a < n <= z for a, z in b.covered)), None)
            opened = [b for b in block.bodies if b.line <= n] if block else []
            if not opened:
                return ""
            marks.add(opened[-1].mark)
    return marks.pop() if len(marks) == 1 else ""


def _carry(rows: list[dict[str, Any]]) -> None:
    """Hand each number read off a footnote to the table cell the note qualifies.

    Steph 2026-10-21: "I should only be asked about footnotes in the context
    of being a footnote, not its own ruling." A held exception quoted from
    note 5 alone is asked on the zone's own number for that standard, as note
    5's question, with our reading of the note beside it. That cell must be in
    the same document and read off the table, not off a note itself.
    ``carried_by`` marks the exception; ``carries`` lists them on the cell,
    by note. Where there is no such cell the exception keeps its own card,
    asked as the note it is (``in_note``).
    """
    base = {(r["zone"], r["field"]): r for r in rows if not r["when"]}
    for row in rows:
        row["carries"] = {}
        row.pop("carried_by", None)
    for row in rows:
        parent = base.get((row["zone"], row["field"]))
        if (
            not row["in_note"]
            or not row["when"]
            or parent is None
            or parent["in_note"]
            or not parent["quote"]
            or parent["document"] != row["document"]
            or parent["web"] != row["web"]
        ):
            continue
        row["carried_by"] = parent
        parent["carries"].setdefault(row["in_note"], []).append(row)


#: Marker kinds read off stored text that name a note. A bare letter is a use
#: code ("P" permitted, "C" conditional) far more often than a note.
_NOT_NOTES = frozenset({"letter", "lone"})


@lru_cache(maxsize=512)
def _web_lines(document: str) -> tuple[str, ...]:
    """A web code's stored text, split into lines once per process.

    The store is baked in, like the page maps: reading and hashing the file per
    number made a queue walk cost one file read per web number.
    """
    return tuple(sheet.lines_of(_store(), document))


@lru_cache(maxsize=4096)
def _web_marks(quote: str) -> tuple[str, ...]:
    """The footnote markers printed on a web number's cited lines, in order.

    A web code has no page geometry to find superscripts by, so the markers
    are read from the stored text with the census's own reading.
    """
    document = quote.partition("#L")[0]
    text = _web_lines(document)
    out: list[str] = []
    for first, last in _ranges(quote):
        for m in footnotes._markers(text[first - 1 : last], ()):
            if m.kind not in _NOT_NOTES and m.mark not in out:
                out.append(m.mark)
    return tuple(out)


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

    A note on a table's title reaches every number in the table, so it is
    asked of each, and those questions come last, one run per table and note,
    so the same note is cleared card after card (Steph 2026-10-21: "ask all
    of the title footnotes in a row so I can quickly process them"). Every
    other question keeps its place.
    """
    titled: dict[tuple, list[_Ask]] = {}
    for row in rows:
        if row.get("carried_by") is not None:
            # Asked on its table cell, as that cell's note (:func:`_carry`).
            continue
        if not _single(row):
            continue
        key = (layer.layer, row["zone"], row["field"], row["when"])
        said = _standing(answers.get((*key, "value")), row)
        if said is None:
            yield _Ask(row, "value")
            continue
        if said.answer in _STOPS:
            continue
        if row["web"]:
            notes = [(mark, None) for mark in _web_marks(row["quote"])]
        else:
            placed = _placed(row)
            notes = [(m.mark, m) for m in placed.markers]
        printed = {mark for mark, _m in notes}
        notes += [(mark, None) for mark in row.get("carries", {}) if mark not in printed]
        for mark, marker in notes:
            if _note_answered(answers, layer, row, mark):
                continue
            ask = _Ask(row, f"note:{mark}")
            if marker is not None and marker.on == "title":
                table = (row["document"], marker.page or placed.marker_page, marker.box.y0)
                titled.setdefault((*table, mark), []).append(ask)
            else:
                yield ask
    for run in titled.values():
        yield from run


def _note_answered(
    answers: dict[tuple, FlatsPageCheck], layer: Layer, row: dict[str, Any], mark: str
) -> bool:
    """Whether a number's note question has a standing answer.

    A note we read an exception from was asked, before the exception moved
    onto its cell, as the exception's own "does the page say" card. An answer
    standing on every one of those answers the note too: it is not asked a
    second time. One of them reopened after a fix puts the note back, until
    the note is answered after the reopening.
    """
    key = (layer.layer, row["zone"], row["field"], row["when"])
    own = _standing(answers.get((*key, f"note:{mark}")), row)
    carried = row.get("carries", {}).get(mark, [])
    reopened = _reopened(answers, layer, carried)
    if own is not None:
        return all(own.decided_at > r.decided_at for r in reopened)
    return bool(carried) and not reopened and all(
        _standing(answers.get((layer.layer, r["zone"], r["field"], r["when"], "value")), r) is not None
        for r in carried
    )


def _reopened(
    answers: dict[tuple, FlatsPageCheck], layer: Layer, rows: list[dict[str, Any]]
) -> list[FlatsPageCheck]:
    """The reopen rows standing on these numbers' value questions."""
    out = []
    for r in rows:
        said = answers.get((layer.layer, r["zone"], r["field"], r["when"], "value"))
        if said is not None and said.answer == REOPENED and said.fingerprint == r["mark"]:
            out.append(said)
    return out


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


def _focus(
    rows: list[dict[str, Any]], zone: str, field: str, when: str, question: str = "value"
) -> _Ask | None:
    for row in rows:
        if (row["zone"], row["field"], row["when"]) == (zone, field, when):
            mark = question.partition(":")[2]
            if (
                row["web"]
                and question != "value"
                and mark not in _web_marks(row["quote"])
                and mark not in row.get("carries", {})
            ):
                return None
            return _Ask(row, question)
    return None


#: How many cards "Back" can walk through.
_TRAIL = 30

#: On the forward stack: wherever the queue is, not a particular card.
_QUEUE = ["", "", "", ""]


def _trail(raw: str) -> list[list[str]]:
    """The cards already passed this session, oldest first.

    Carried in the form rather than the server's memory, so Back walks the
    reviewer's own path -- answered and skipped cards alike -- and a second
    tab keeps its own.
    """
    try:
        trail = json.loads(raw or "[]")
    except ValueError:
        return []
    if not isinstance(trail, list):
        return []
    return [
        t for t in trail
        if isinstance(t, list) and len(t) == 4 and all(isinstance(x, str) for x in t)
    ][-_TRAIL:]


def _flags_on(
    answers: dict[tuple, FlatsPageCheck],
    layer_id: str,
    document: str,
    pages: set[int],
    web: tuple[str, str, str] | None = None,
) -> list[dict[str, Any]]:
    """What has been flagged and not yet answered on the pages this card shows, oldest first.

    A flag is its own finding: a second one adds to the list, it does not
    replace the first, and the card shows them so the reviewer can see that.
    A web card has no page, so it shows the flags made on that same number.
    """
    out, replies = [], _replies(answers)
    for r in answers.values():
        if (
            r.layer == layer_id
            and r.answer == FLAG
            and (
                r.page in pages
                if web is None
                else r.page is None and r.placed == "web" and (r.zone, r.field, r.when_key) == web
            )
            and (r.quote or "").partition("#L")[0] == document
        ):
            # A flag answered is resolved, and drops off the card: "we don't
            # need to keep a record if resolved" (Steph 2026-10-22). The
            # problems page still lists it with its answer.
            if r.id in replies:
                continue
            out.append({"page": r.page, "says": r.says, "id": r.id, "reply": ""})
    return sorted(out, key=lambda f: f["id"])


# --- everything else we hold from a page ------------------------------------


def _numbers_only(placed: sheet.Placed) -> dict[int, list[tuple[sheet.Box, str]]]:
    """A placement's boxes, minus the context lines once the number is boxed.

    A citation quotes the table title and heading rows as well as the cell.
    Where the number itself was found, those lines are context, and drawing
    them made a page of tints in which the cell that matters did not stand
    out. Only a number never found as a numeral is shown by its lines.
    """
    if not any(kind == "value" for boxes in placed.boxes.values() for _b, kind in boxes):
        return placed.boxes
    return {
        page: [(b, kind) for b, kind in boxes if kind == "value"]
        for page, boxes in placed.boxes.items()
        if any(kind == "value" for _b, kind in boxes)
    }


def _own_boxes(placed: sheet.Placed) -> list[tuple[int, list[tuple[sheet.Box, str]]]]:
    """The pages a value card shows, and what is drawn on each.

    Only the pages the number is boxed on, when it is boxed: a page that holds
    nothing but the citation's run-in context is a page to scroll past.
    """
    shown = _numbers_only(placed)
    pages = [p for p in placed.pages if p in shown] or placed.pages
    return [(page, shown.get(page, [])) for page in pages[:2]]


def _exempt(layer: Layer, row: dict[str, Any]) -> bool:
    number = _number(layer, row["zone"], row["field"], row["when"])
    return bool(getattr(number, "exempt", False))


@lru_cache(maxsize=1)
def _by_document() -> dict[str, list[dict[str, Any]]]:
    """Every encoded number in every layer, grouped by the document it cites.

    An exempt standard is not here: "this does not reach our building" is a
    decision to leave the passage out, and it is drawn with the other ones
    (:func:`_set_aside_by_document`).
    """
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for layer_id, layer in _layers().items():
        for row in _value_rows(layer):
            document = (row["quote"] or "").partition("#L")[0]
            if document and not _exempt(layer, row):
                out[document].append({**row, "layer_id": layer_id, "printed": _printed(layer, row)})
    return out


@lru_cache(maxsize=1)
def _set_aside_by_document() -> dict[str, list[dict[str, str]]]:
    """Every passage read and left out on purpose, grouped by document.

    The whole corpus; a card only needs one document and asks
    :func:`_set_aside_in`, which is the same answer without surveying every
    layer's reading queue.
    """
    return _set_aside_items(None)


@lru_cache(maxsize=512)
def _set_aside_in(document: str) -> tuple[dict[str, str], ...]:
    """One document's set-aside passages -- identical to its entry in the whole."""
    return tuple(_set_aside_items(document).get(document, []))


def _set_aside_items(only: str | None) -> dict[str, list[dict[str, str]]]:
    """Passages read and left out on purpose, for one document or all of them.

    Four kinds of decision, one tint: a located refusal (``set_aside:``), a
    footnote ruled dismissed, a section the reading queues closed as not
    reaching us, and a standard held as exempt. A reviewer does not need the
    reason to tell "weighed and refused" from "never read", and the second is
    the one the page check is for.

    The reading queue is the slow part (it scans every document a layer owns),
    and a layer's cards only ever cite documents in that layer's own
    directory, so a single document needs only its own layer's queue.
    """
    from flats.encode import dispositions, worklist

    out: dict[str, list[dict[str, str]]] = defaultdict(list)

    def add(quote: str, why: str) -> None:
        document = quote.partition("#L")[0]
        if document and (only is None or document == only) and _ranges(quote):
            out[document].append({"quote": quote, "why": why})

    for layer_id, layer in _layers().items():
        for item in layer.set_aside:
            add(item.quote, item.why)
        for row in _value_rows(layer):
            if row["quote"] and _exempt(layer, row):
                add(row["quote"], f"{_label(row['field'])} -- does not reach this building")
        if only is not None and only.rpartition("/")[0] != layer_id:
            continue
        try:
            for card in worklist.cards(layer, _store()):
                if card.ruling is not None and card.ruling.closed and card.lines:
                    lines = ",".join(f"L{line.line}" for line in card.lines)
                    add(f"{card.path}#{lines}", f"{card.section} -- read, does not reach us")
        except Exception:  # noqa: BLE001 — a layer the reading queue cannot survey draws none
            pass
    # The rulings as written carry their own line; joining them to the
    # footnote census to re-find it costs half a minute a process.
    for rulings in dispositions.rulings().values():
        for ruling in rulings:
            if ruling.state == "dismissed" and ruling.quote:
                add(ruling.quote, "footnote read and dismissed")
    for document, items in out.items():
        seen: set[tuple[str, str]] = set()
        out[document] = [
            i for i in items if (i["quote"], i["why"]) not in seen and not seen.add((i["quote"], i["why"]))
        ]
    return out


def warm() -> None:
    """Fill the per-process caches the first card would otherwise pay for.

    Run from a thread at app startup; a failure only means the first card is
    as slow as it was.
    """
    from flats.encode import dispositions

    try:
        _layers()
        _known_documents()
        dispositions.rulings()
        _by_document()
    except Exception:  # noqa: BLE001 — warming is best effort
        pass


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
        for box, _kind in _numbers_only(placed).get(page, []):
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


@lru_cache(maxsize=256)
def _set_aside_on(document: str, page: int) -> tuple[tuple[sheet.Box, str], ...]:
    """The lines on this page that were read and left out on purpose."""
    index = _page_index(document)
    if index is None:
        return ()
    spots: dict[tuple, dict[str, Any]] = {}
    for item in _set_aside_in(document):
        if not _on_page(index, item["quote"], page):
            continue
        try:
            placed = _placed_cached(document, tuple(_ranges(item["quote"])), "null", "")
        except Exception:  # noqa: BLE001 — a passage that cannot be placed is not drawn
            continue
        for box, _kind in placed.boxes.get(page, []):
            key = tuple(round(v, 3) for v in (box.x0, box.y0, box.x1, box.y1))
            spot = spots.setdefault(key, {"box": box, "why": []})
            if item["why"] not in spot["why"]:
                spot["why"].append(item["why"])
    return tuple(
        (spot["box"], "set aside on purpose: " + "; ".join(spot["why"][:4]))
        for spot in spots.values()
    )


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
        "context": "",
        "cite": printed.cite if printed else f"PDF page {page}",
        "boxes": [{"css": box.css(), "kind": kind} for box, kind in boxes],
        "encoded": encoded,
        "set_aside": [
            {"css": box.pad(0.002).css(), "title": title}
            for box, title in _set_aside_on(document, page)
        ],
    }


def _readthrough_documents() -> list[dict[str, Any]]:
    """Every stored printed document with a page map, including uncited books."""
    out = []
    for document in sorted(_known_documents()):
        index = _page_index(document)
        if index is None or not index.pages:
            continue
        out.append(
            {
                "document": document,
                "name": document.rsplit("/", 1)[-1],
                "page_count": len(index.pages),
            }
        )
    return out


def _readthrough_pages(document: str, index: Any) -> list[dict[str, Any]]:
    """Every mapped page, with its printed label, nearby heading and rule tints."""
    lines = sheet.lines_of(_store(), document)
    out = []
    for position, printed in enumerate(index.pages):
        end = index.pages[position + 1].line - 1 if position + 1 < len(index.pages) else len(lines)
        section = lines[max(printed.line - 1, 0) : max(end, printed.line)]
        headings = [line.strip() for line in section if line.strip()][:2]
        page = _sheet_view(document, printed.n, [])
        page["heading"] = " · ".join(headings)[:240]
        out.append(page)
    return out


def _readthrough_comments(raw: str, valid_pages: set[int]) -> list[dict[str, Any]] | None:
    """Validate a draft payload before storing reviewer-authored comments."""
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, list) or len(parsed) > 200:
        return None
    comments = []
    for item in parsed:
        if not isinstance(item, dict):
            return None
        page, text = item.get("page"), item.get("text")
        if (
            not isinstance(page, int)
            or isinstance(page, bool)
            or page not in valid_pages
            or not isinstance(text, str)
            or not text.strip()
            or len(text) > 4000
        ):
            return None
        clean: dict[str, Any] = {"page": page, "text": text.strip()}
        box = item.get("box")
        if box is not None:
            if (
                not isinstance(box, list)
                or len(box) != 4
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not 0 <= value <= 1
                    for value in box
                )
                or box[0] >= box[2]
                or box[1] >= box[3]
            ):
                return None
            clean["box"] = [round(float(value), 4) for value in box]
        comments.append(clean)
    return comments


def _with_neighbours(document: str, sheets: list[dict[str, Any]], mark: str) -> list[dict[str, Any]]:
    """The cited pages with the page before and the page after them.

    A list that runs to the foot of the page leaves the reader unable to say
    whether it ends there: Steph could not tell whether MUE's permitted uses
    stopped at N or went on to an O overleaf. The neighbours carry tints but
    no box -- the card asks about the cited pages -- and the card scrolls to
    the first cited page, so the page before is there above it, not in the way.
    """
    index = _page_index(document)
    if not sheets or index is None or not index.pages:
        return sheets
    pages = {sh["page"] for sh in sheets}
    first, last, end = min(pages), max(pages), index.pages[-1].n
    out = list(sheets)
    # Every page from where a note is called to where it is printed: with
    # page 9's table and page 11's notes shown, page 10 between them was not
    # (Steph 2026-10-20: "show enough pages to show both the origination of
    # the footnote citation and the footnote, +/- 1 page").
    for n in range(first + 1, min(last, first + _SPAN)):
        if n not in pages:
            out.append({**_sheet_view(document, n, [], mark), "context": "between"})
    if first > 1 and first - 1 not in pages:
        out.append({**_sheet_view(document, first - 1, [], mark), "context": "before"})
    if last < end and last + 1 not in pages:
        out.append({**_sheet_view(document, last + 1, [], mark), "context": "after"})
    return sorted(out, key=lambda sh: sh["page"])


#: The most pages a card fills in between a note's call and the note.
_SPAN = 6


def _calling_page(layer: Layer, row: dict[str, Any]) -> int | None:
    """The page of the table a note-borne number hangs off, when it is not the note's.

    CMF's corner townhouse frontage is quoted from note 11 alone; the card
    showed the notes and not the table whose CMF column calls note 11, so
    Steph could not tell the note reaches CMF (2026-10-20). The table row is
    the one the zone's base number is read from.
    """
    if not row["when"]:
        return None
    base = next(
        (
            r
            for r in _value_rows(layer)
            if (r["zone"], r["field"], r["when"]) == (row["zone"], row["field"], "") and r["quote"]
        ),
        None,
    )
    document = row["quote"].partition("#L")[0]
    if base is None or base["quote"].partition("#L")[0] != document:
        return None
    index = _page_index(document)
    spans = list(_ranges(base["quote"]))
    where = index.at(spans[0][0]) if index is not None and spans else None
    return where.n if where else None


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


def _ruled_notes(layer: Layer, zone: str, field: str) -> list[str]:
    """The words of every note ruled as encoded into this zone's standard."""
    out = []
    for ruling in dispositions.rulings().get(layer.layer, []):
        if ruling.state != "encoded" or f"{zone} {field}" not in ruling.encoded_as or not ruling.quote:
            continue
        # The whole note, not only its cited first line: note 10's "... no
        # alley or shared / access." ended mid-phrase on the card.
        document, _, span = ruling.quote.partition("#L")
        first = int(re.match(r"\d+", span).group()) if re.match(r"\d+", span) else 0
        opening = sheet.lines_of(_store(), document)[first - 1] if first else ""
        mark = re.match(r"\s*\(?(\d+|[A-Za-z])[.)]", opening)
        at, body = _note_text(document, mark.group(1), first) if mark else (None, [])
        if at != first:
            lines, _error = _cited_lines(ruling.quote)
            body = [line["shown"] for line in lines if line["quoted"]]
        words = " ".join(" ".join(line.split()) for line in body)
        if words and words not in out:
            out.append(words)
    return out


def _variants(layer: Layer, zone: str, field: str) -> list[dict[str, str]]:
    """Every number we hold for this standard in this zone: base and variants."""
    values = layer.defaults if zone.startswith("(") else layer.zones[zone].values
    value = values.get(field)
    if value is None:
        return []
    out = [{"when": "normally", "value": _said(value.value, field), "key": ""}]
    out += [
        {
            "when": _when_phrase("+".join(v.key)),
            "value": _said(v.value, field),
            "key": "+".join(v.key),
        }
        for v in value.variants
    ]
    return out


def _states(token: str, value: Any) -> bool:
    """Whether a word of stored text states this number (same reading as the page boxes)."""
    if value is None:
        return token.strip().lower().rstrip(",;:*.") in {"none", "na", "n/a", "n.a"}
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    read = sheet.numeral(token)
    if read is None:
        return False
    number, percent = read
    return abs(number - value) < 1e-9 or (percent and abs(number / 100 - value) < 1e-9)


def _web_text(row: dict[str, Any], note_mark: str = "") -> list[dict[str, Any]]:
    """The stored text around the cited lines, with the number or note marked.

    A web code has no page to draw, so the card shows the text we hold, the
    cited lines lit and the words that state the number or footnote tinted.
    """
    lines, _error = _cited_lines(row["quote"])
    out = []
    for line in lines:
        shown = line["shown"]
        if not note_mark:
            parts = [
                {"text": p, "hit": line["quoted"] and bool(p.strip()) and _states(p, row.get("printed", row["value"]))}
                for p in re.split(r"(\s+)", shown)
                if p
            ]
        else:
            leading = len(shown) - len(shown.lstrip())
            marker_spans = []
            if line["quoted"]:
                marker_spans = sorted(
                    (leading + marker.start, leading + marker.end)
                    for marker in footnotes._markers([shown], ())
                    if marker.kind not in _NOT_NOTES and marker.mark == note_mark
                )
            parts = []
            cursor = 0
            for token in re.finditer(r"\S+", shown):
                if token.start() > cursor:
                    parts.append({"text": shown[cursor : token.start()], "hit": False, "marker": False})
                token_start, token_end = token.span()
                hit = line["quoted"] and _states(token.group(), row.get("printed", row["value"]))
                cursor = token_start
                for start, end in marker_spans:
                    if start < token_start or end > token_end:
                        continue
                    if start > cursor:
                        parts.append({"text": shown[cursor:start], "hit": hit, "marker": False})
                    parts.append({"text": shown[start:end], "hit": False, "marker": True})
                    cursor = end
                if cursor < token_end:
                    parts.append({"text": shown[cursor:token_end], "hit": hit, "marker": False})
                cursor = token_end
            if cursor < len(shown):
                parts.append({"text": shown[cursor:], "hit": False, "marker": False})
        out.append(
            {
                "n": line["n"],
                "cited": line["quoted"],
                "grid": line["grid"],
                "parts": parts,
            }
        )
    return out


#: A choice word said the way a person reads it on a page-check card.
READING_WORDS: dict[tuple[str, str], str] = {
    ("front_lot_line_corner", "shortest"): "the shortest street line is the front",
    ("front_lot_line_corner", "owner"): "the owner picks which street line is the front",
    ("front_lot_line_corner", "entrance"): "the street line the entrance faces is the front",
    ("front_lot_line_corner", "both"): "every street line takes the front setback",
    ("front_lot_line_corner", "depth"): "the street line that gives the lot its minimum depth is the front; the owner picks if both do",
    ("front_lot_line_through", "manager"): "the city's planning manager picks the front; we read both street lines as fronts, with a flag",
    ("front_lot_line_through", "both"): "both street lines take the front setback",
    ("front_lot_line_through", "both_unless_no_access"): "both street lines are fronts, except one cars are barred from, which is the rear",
    ("front_lot_line_through", "owner"): "the owner picks which street line is the front",
    ("corner_access_street", "any"): "any street (no street is named)",
    ("corner_access_street", "side"): "the side street",
    ("corner_access_street", "lowest_class"): "the quieter street (lowest class)",
}


def _card(layer: Layer, ask: _Ask) -> dict[str, Any]:
    """Everything one card shows."""
    row = ask.row
    document = row["document"]
    web = row["web"]
    placed = None if web else _placed(row)
    card: dict[str, Any] = {
        "layer_id": layer.layer,
        "layer_label": _layer_label(layer),
        "zone": row["zone"],
        "field": row["field"],
        "field_label": _label(row["field"]),
        "when": row["when"],
        "when_label": row["when_label"].replace("_", " "),
        "when_words": _condition_words(row["when"]),
        "when_who": _when_parts(row["when"])[0],
        "when_where": _when_parts(row["when"])[1],
        "value": _said(row["value"], row["field"]),
        "signed": row["signed"],
        "cite": row["cite"],
        # The section alone: the cite's description restates the question.
        "section": (row["cite"] or "").split(",")[0].strip(),
        # A layer-wide rule has no zone worth naming on the card.
        # "the I zone", not "I": a one-letter zone name reads as a lettered
        # point on the page (Oregon City's Institutional district did).
        "zone_label": "" if row["zone"].startswith("(") else f"the {row['zone']} zone",
        "quote": row["quote"],
        # The document the card shows, not the value's own: a number borrowed
        # from another chapter (Gresham CMF's corridor height, read off the
        # residential table) linked to the chapter it was not read from
        # (Steph 2026-10-20).
        "url": _source_url(document) or row["url"],
        "question": ask.question,
        "placed": "web" if web else placed.status,
        "placed_words": "" if web else sheet.PLACED.get(placed.status, ""),
        "web": web,
        "web_text": _web_text(row, ask.question.partition(":")[2] if web and ask.question.startswith("note:") else "")
        if web
        else [],
        "sheets": [],
        "answers": list(VALUE_ANSWERS.items()),
    }
    if ask.question == "value":
        # Read off a footnote with no table cell to ask it on: asked as the
        # note it is, not as though the page printed it in the grid.
        card["in_note"] = row.get("in_note", "")
        # The other numbers held for the same standard. Without them a
        # reviewer reading "except townhouses: 20 ft" answers "No" to the
        # 25 ft card, not knowing the 20 is held too (Oregon City R-3.5).
        card["others"] = [
            v for v in _variants(layer, row["zone"], row["field"]) if v["key"] != row["when"]
        ]
        card["no_rule"] = row["value"] is None
        # A yes/no is a reading, not a number on the page: Steph answered
        # "differs" to "fourplex allowed: no" in I and MUE, where the page
        # shown was the general rule that an unlisted use is forbidden. The
        # card says what was read and where, not only the section.
        card["yes_no"] = isinstance(row["value"], bool)
        # A choice word ("both", "any") is a reading too, and usually a reading
        # of what the code leaves unsaid: Steph answered "differs" to Durham's
        # "front on a corner lot: both" and "driveway street: any" (2026-10-19),
        # because the page defines no corner front and names no street. Asked
        # as "does the page say both?" it read as a definition we invented.
        known = FIELDS.get(row["field"])
        card["reading"] = known is not None and known.kind == "enum" and isinstance(row["value"], str)
        if card["reading"]:
            card["value"] = READING_WORDS.get((row["field"], row["value"]), row["value"])
        card["because"] = row["cite"] if card["yes_no"] or card["reading"] else ""
        card["exempt"] = _exempt(layer, row)
        if not web and _zone_off_page(document, row["line"], row["zone"]):
            card["borrowed"] = row["cite"]
        printed = row.get("printed", row["value"])
        if printed != row["value"] and isinstance(printed, (int, float)) and not isinstance(printed, bool):
            # Asked about what the page prints; told what we make of it.
            said = _printed_said(layer, row, printed)
            if said:
                card["printed"] = said
                card["derived_why"] = _derived_why(layer, row)
        if web:
            return card
        if row["when"]:
            # A number held "on lots under 11,000 sq ft" comes from a note the
            # page may print overleaf; the card asked whether the note was
            # read right without showing the note (Steph 2026-10-20, MDR-24).
            card["row_notes"] = _ruled_notes(layer, row["zone"], row["field"])
        for page, boxes in _own_boxes(placed):
            card["sheets"].append(_sheet_view(document, page, boxes, row["mark"]))
        calling = _calling_page(layer, row)
        if card["sheets"] and calling is not None and calling not in {sh["page"] for sh in card["sheets"]}:
            card["sheets"].append({**_sheet_view(document, calling, [], row["mark"]), "context": "that calls the note"})
        card["sheets"] = _with_neighbours(document, card["sheets"], row["mark"])
        card["sheets"] = _via_sheets(row) + card["sheets"]
        card["via"] = any(sh.get("via") for sh in card["sheets"])
        return card

    mark = ask.question.partition(":")[2]
    card["answers"] = list(NOTE_ANSWERS.items())
    card["mark"] = mark
    # The exceptions we read off this note, asked here rather than as cards
    # of their own: "Note 5 applies here. We read it as: ..."
    carried = row.get("carries", {}).get(mark, [])
    card["readings"] = [_reading(r) for r in carried]
    if carried:
        card["answers"] = list(READING_ANSWERS.items())
    at, body = _note_text(document, mark, row["line"])
    card["note_text"] = body
    card["variants"] = _variants(layer, row["zone"], row["field"])
    if web:
        # The cited text is already on the card; there is no page to box.
        card["mark_on"] = "web" if mark in _web_marks(row["quote"]) else "read"
        return card
    marker = next((m for m in placed.markers if m.mark == mark), None)
    # A note we read an exception from whose marker is not found on the
    # cell: said as our reading, not as a marker printed there.
    card["mark_on"] = marker.on if marker else ("read" if carried else "number")
    page = placed.marker_page or (placed.pages[0] if placed.pages else 1)
    boxes = [b for b in placed.boxes.get(page, []) if b[1] == "value"]
    title_page = marker.page if marker and marker.page not in (None, page) else None
    if marker and title_page is None:
        boxes.append((marker.box.pad(0.004), "marker"))
    if title_page is not None:
        # The table runs on from an earlier page, where its title is printed.
        card["mark_page"] = title_page
        card["sheets"].append(
            _sheet_view(document, title_page, [(marker.box.pad(0.004), "marker")], row["mark"])
        )
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
    card["sheets"] = _with_neighbours(document, card["sheets"], row["mark"])
    return card


def _via_sheets(row: dict[str, Any]) -> list[dict[str, Any]]:
    """The pages of the passage that sends the reader to the quoted table, boxed.

    Gresham's CMF corridor setbacks are read off Table 4.0131's TLDR column
    because Table 4.0430 note 14 says so. The card named the note and showed
    only the table, and Steph had "no evidence that the cross-table
    references ... are accurate" (2026-10-22). Shown first, above the table.
    """
    via = row.get("via") or ""
    document = via.partition("#L")[0]
    if not document or _checkable(document):
        return []
    placed = _placed_cached(document, tuple(_ranges(via)), "null", "")
    return [
        {**_sheet_view(document, page, boxes, row["mark"]), "via": True}
        for page, boxes in placed.boxes.items()
        if boxes
    ][:2]


def _reading(row: dict[str, Any]) -> str:
    """One exception read off a note, in plain words: "5 ft for townhouses"."""
    who, where = _when_parts(row["when"])
    words = [_said(row["value"], row["field"]), "for", _label(row["field"]).lower()]
    if who:
        words += ["for", who]
    if where:
        words.append(where)
    return " ".join(words)


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
    replies = _replies(answers)
    two = sum(not _single(r) for r in rows)
    rows = [r for r in rows if _single(r)]
    for row in rows:
        said = _standing(
            answers.get((layer.layer, row["zone"], row["field"], row["when"], "value")), row
        )
        if said is not None:
            checked += 1
            problems += said.answer in PROBLEMS and said.id not in replies
        elif (parent := row.get("carried_by")) is not None:
            # Asked as its cell's note: checked once that note is answered.
            checked += _note_answered(answers, layer, parent, row["in_note"])
    return {
        "numbers": len(rows),
        "checked": checked,
        "left": len(rows) - checked,
        "problems": problems,
        "two_source": two,
    }


async def _answer_id(session: DBSession, layer_id: str, ask: _Ask) -> int | None:
    """The row id of the latest answer given to this question, if any.

    Not the reopen row's: that is ours, and the answer it puts back is the
    reviewer's.
    """
    stmt = (
        select(FlatsPageCheck.id)
        .where(
            FlatsPageCheck.layer == layer_id,
            FlatsPageCheck.zone == ask.row["zone"],
            FlatsPageCheck.field == ask.row["field"],
            FlatsPageCheck.when_key == ask.row["when"],
            FlatsPageCheck.question == ask.question,
            FlatsPageCheck.answer != REOPENED,
        )
        .order_by(FlatsPageCheck.decided_at.desc(), FlatsPageCheck.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _card_ctx(
    session: DBSession,
    layer: Layer,
    *,
    skipped: int = 0,
    focus: tuple[str, str, str, str] | None = None,
    trail: list[list[str]] | None = None,
    ahead: list[list[str]] | None = None,
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
    if card:
        before = _standing(
            answers.get(
                (layer.layer, ask.row["zone"], ask.row["field"], ask.row["when"], ask.question)
            ),
            ask.row,
        )
        latest = answers.get(
            (layer.layer, ask.row["zone"], ask.row["field"], ask.row["when"], ask.question)
        )
        card["asked_again"] = (
            {"answer": _WORDS.get(latest.note, latest.note), "says": latest.says}
            if latest is not None and latest.answer == REOPENED
            else None
        )
        mark = ask.question.partition(":")[2]
        again = _reopened(answers, layer, ask.row.get("carries", {}).get(mark, []))
        if card["asked_again"] is None and again and not _note_answered(answers, layer, ask.row, mark):
            # Reopened on the exception's own card, before it moved here.
            card["asked_again"] = {"answer": _WORDS.get(again[0].note, again[0].note), "says": again[0].says}
        # The id of the reviewer's own last answer to this question, which is
        # how a card is named in a conversation about it (Steph 2026-10-21:
        # "I don't see things like 273 and 282, I just see '3 of 7'"). A
        # reopened card names the answer it reopens; an unanswered one, none.
        card["answer_id"] = before.id if before else await _answer_id(session, layer.layer, ask)
        card["before"] = _WORDS.get(before.answer, before.answer) if before else ""
        card["before_answer"] = before.answer if before else ""
        # Coming back to change an answer starts from what was written.
        card["before_comment"] = (before.says or before.note) if before else ""
        card["flags"] = _flags_on(
            answers,
            layer.layer,
            ask.row["document"],
            {sh["page"] for sh in card["sheets"] if not sh["context"]},
            (ask.row["zone"], ask.row["field"], ask.row["when"]) if card["web"] else None,
        )
    return {
        "layer": {"id": layer.layer, "label": _layer_label(layer)},
        "card": card,
        "counts": _counts(layer, rows, answers),
        "skipped": skipped,
        "trail": json.dumps(trail or []),
        "ahead": json.dumps(ahead or []),
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
    index = _page_index(document) if document in _known_documents() else None
    if index is None:
        return HTMLResponse("no page map for this document", status_code=404)
    # A page the map does not hold is answered before the book is fetched: the
    # fetch is a download, and CI's failed one turned a bad page number into a
    # 409 (f7512199 full gate, 2026-10-19).
    if index.pages and page > max(p.n for p in index.pages):
        return HTMLResponse("that page cannot be drawn", status_code=404)
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


@router.get("/flats/check/readthrough", response_class=HTMLResponse)
async def flats_readthrough_index(request: Request, session: DBSession) -> HTMLResponse:
    """Choose a printed document and see its most recent human read-through."""
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    documents = await run_in_threadpool(_readthrough_documents)
    records = (
        await session.execute(
            select(FlatsDocumentReadthrough).order_by(
                FlatsDocumentReadthrough.submitted_at,
                FlatsDocumentReadthrough.id,
            )
        )
    ).scalars()
    latest: dict[str, FlatsDocumentReadthrough] = {}
    for record in records:
        latest[record.document] = record
    for item in documents:
        record = latest.get(item["document"])
        item["read"] = record
    return templates.TemplateResponse(
        request,
        "flats_readthrough_index.html",
        {
            **_base_ctx(user, dedup_count, "flats_check", conflicts_count=conflicts_count),
            "documents": documents,
        },
    )


@router.get("/flats/check/readthrough/{document:path}", response_class=HTMLResponse)
async def flats_readthrough(
    request: Request,
    session: DBSession,
    document: str,
    submitted: bool = Query(False),
) -> HTMLResponse:
    """Read every mapped page of one document in order."""
    user = await _get_user(session, request)
    if document not in _known_documents():
        return HTMLResponse("no page map for this document", status_code=404)
    index = _page_index(document)
    if index is None or not index.pages:
        return HTMLResponse("no page map for this document", status_code=404)
    dedup_count, conflicts_count = await _get_counts(session)
    pages = await run_in_threadpool(_readthrough_pages, document, index)
    latest = (
        await session.execute(
            select(FlatsDocumentReadthrough)
            .where(FlatsDocumentReadthrough.document == document)
            .order_by(
                FlatsDocumentReadthrough.submitted_at.desc(),
                FlatsDocumentReadthrough.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return templates.TemplateResponse(
        request,
        "flats_readthrough.html",
        {
            **_base_ctx(user, dedup_count, "flats_check", conflicts_count=conflicts_count),
            "document": document,
            "book_sha256": index.source_sha256 or "",
            "pages": pages,
            "last_read": latest,
            "submitted": submitted,
        },
    )


@router.post("/ui/flats/readthrough", response_class=HTMLResponse)
async def flats_readthrough_submit(
    request: Request,
    session: DBSession,
    document: str = Form(...),
    comments_json: str = Form("[]"),
    read_confirmed: str = Form(""),
) -> HTMLResponse:
    """Append one completed document read and its browser-drafted comments."""
    user = await _get_user(session, request)
    if user is None:
        return HTMLResponse("sign in first", status_code=401)
    if read_confirmed != "yes" or document not in _known_documents():
        return HTMLResponse("confirm that you read the document", status_code=400)
    index = _page_index(document)
    if index is None or not index.pages:
        return HTMLResponse("no page map for this document", status_code=404)
    comments = _readthrough_comments(comments_json, {page.n for page in index.pages})
    if comments is None:
        return HTMLResponse("the comments could not be read; review the draft and try again", status_code=400)
    session.add(
        FlatsDocumentReadthrough(
            document=document,
            book_sha256=index.source_sha256 or "",
            page_count=len(index.pages),
            comments=comments,
            comment_count=len(comments),
            reviewer=(user.email or str(user.id))[:80],
            reviewer_user_id=user.id,
        )
    )
    await session.commit()
    return RedirectResponse(
        f"/flats/check/readthrough/{quote(document, safe='/')}?submitted=1",
        status_code=303,
    )


@router.get("/flats/check", response_class=HTMLResponse)
async def flats_check_index(request: Request, session: DBSession) -> HTMLResponse:
    """Every jurisdiction's page check at a glance, and the problems raised."""
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    answers = await _answers(session)
    signed = await _signed(session)
    replies = _replies(answers)

    def build() -> tuple[list[dict[str, Any]], dict[str, int], list[dict[str, Any]], list[dict[str, Any]]]:
        layers = _layers()
        table, totals, problems = [], {"numbers": 0, "checked": 0, "problems": 0, "two_source": 0, "no_map": 0, "html": 0}, []
        answered: list[dict[str, Any]] = []
        for layer_id, layer in sorted(layers.items()):
            rows = _rows(layer, signed)
            counts = _counts(layer, rows, answers)
            elsewhere = {"no_map": 0, "html": sum(r["web"] for r in rows)}
            for row in _value_rows(layer):
                why = _checkable((row["quote"] or "").partition("#L")[0])
                if why == "no_map":
                    elsewhere[why] += 1
            if not rows and not any(elsewhere.values()):
                continue
            table.append({"id": layer_id, "label": _layer_label(layer), **counts, **elsewhere})
            for key in ("numbers", "checked", "problems", "two_source"):
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
                reply = replies.get(answer.id)
                (answered if reply else problems).append(
                    {
                        "layer_id": layer_id,
                        "layer_label": _layer_label(layer),
                        "zone": zone,
                        "field": field,
                        "field_label": _label(field),
                        "when": when,
                        "value": _said(row["value"], field),
                        "id": answer.id,
                        "question": answer.question,
                        "answer": answer.answer,
                        "answer_words": _WORDS.get(answer.answer, ""),
                        "says": answer.says,
                        "note": answer.note,
                        "by": answer.reviewer,
                        "at": answer.decided_at,
                        "handed_on": answer.bundled_at is not None,
                        "reply": reply.note if reply else "",
                        "replied_at": reply.decided_at if reply else None,
                    }
                )
        return (
            table,
            totals,
            sorted(problems, key=lambda p: p["at"], reverse=True),
            sorted(answered, key=lambda p: p["replied_at"], reverse=True),
        )

    table, totals, problems, answered = await run_in_threadpool(build)
    return templates.TemplateResponse(
        request,
        "flats_check_index.html",
        {
            **_base_ctx(user, dedup_count, "flats_check", conflicts_count=conflicts_count),
            "table": table,
            "totals": totals,
            "problems": problems,
            "answered": answered,
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
    replies = _replies(answers)
    for (layer_id, zone, field, when, question), answer in sorted(
        answers.items(), key=lambda kv: kv[1].decided_at
    ):
        layer = layers.get(layer_id)
        if (
            layer is None
            or answer.answer not in PROBLEMS
            or answer.bundled_at is not None
            or answer.id in replies
        ):
            continue
        number = _number(layer, zone, field, when)
        if number is None or answer.fingerprint != _mark(layer_id, zone, field, when, number):
            continue
        lines, _error = _cited_lines(answer.quote)
        where = "web code, no printed page" if answer.placed == "web" else f"PDF page {answer.page}"
        out += [
            f"== {layer_id} | {zone} | {field}{' when ' + when if when else ''} = {answer.value!r}",
            f"   question: {question}   answer: {answer.answer}   by {answer.reviewer} {answer.decided_at:%Y-%m-%d}",
            f"   page: {where}   box: {answer.placed}   cite: {answer.quote}",
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
    question: str = Query("value"),
) -> HTMLResponse:
    """One jurisdiction's page check: one card, one question, four buttons."""
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    layer = _layers().get(layer_id.strip("/"))
    if layer is None:
        return HTMLResponse("no such jurisdiction", status_code=404)
    ctx = await _card_ctx(
        session,
        layer,
        skipped=skipped,
        focus=(zone, field, when, question if question.startswith("note:") else "value") if zone and field else None,
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
    zone: str = Form(""),
    field: str = Form(""),
    when: str = Form(""),
    question: str = Form("value"),
    answer: str = Form(""),
    says: str = Form(""),
    note: str = Form(""),
    comment: str = Form(""),
    flag_page: int = Form(0),
    flag_web: str = Form(""),
    action: str = Form("answer"),
    skipped: int = Form(0),
    trail: str = Form("[]"),
    ahead: str = Form("[]"),
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

    passed, forward = _trail(trail), _trail(ahead)
    # A flag posted on its own names the page, not the card: stay on the value.
    here = [zone, field, when, "value" if question.startswith("page:") else question]

    async def card(**kw: Any) -> HTMLResponse:
        kw.setdefault("trail", passed)
        kw.setdefault("ahead", forward)
        ctx = await _card_ctx(session, layer, **kw)
        return templates.TemplateResponse(request, "partials/flats_check_card.html", ctx)

    if action == "back" and layer is not None:
        # The card before this one, shown again with its standing answer; a
        # new answer to it is a later answer, and the latest one counts. The
        # card left behind goes on the forward stack.
        if not passed:
            return await card(skipped=skipped)
        *rest, last = passed
        b_zone, b_field, b_when, b_question = last
        if b_question.startswith("skip:"):
            # Un-skipping: the queue's place moves back with the reviewer.
            b_question, skipped = b_question.removeprefix("skip:"), max(skipped - 1, 0)
        return await card(
            skipped=skipped,
            focus=(b_zone, b_field, b_when, b_question),
            trail=rest,
            ahead=[*forward, here if number is not None else _QUEUE][-_TRAIL:],
        )
    if layer is None or number is None:
        return HTMLResponse("not a number we hold", status_code=400)
    said = (await _answers(session, layer.layer)).get((layer.layer, zone, field, when, question))
    answered = (
        said is not None
        and said.answer != REOPENED
        and said.fingerprint == _mark(layer.layer, zone, field, when, number)
    )
    if action == "forward" or (action == "skip" and forward):
        # Back over a card, then forward again. Passing a card that still
        # has no answer skips it, as the Skip button would have.
        if not forward:
            return await card(skipped=skipped, focus=tuple(here))
        *rest, target = forward
        if not answered:
            skipped, here = skipped + 1, [zone, field, when, f"skip:{question}"]
        return await card(
            skipped=skipped,
            focus=None if target == _QUEUE else tuple(target),
            trail=[*passed, here][-_TRAIL:],
            ahead=rest,
        )
    if action == "skip" and answered:
        # Leaving a card already answered (reached by Back) is not a skip:
        # the queue never held it, and counting it would pass over the next
        # unanswered card instead.
        return await card(skipped=skipped, trail=[*passed, here][-_TRAIL:])
    if action == "skip":
        return await card(skipped=skipped + 1, trail=[*passed, [zone, field, when, f"skip:{question}"]][-_TRAIL:])
    # The card has one comment box. Under "No" it is what the page says;
    # with "Flag it" it is what the page has that the rules don't; under any
    # other answer it is a note.
    if action == "flag":
        question = "page:web" if flag_web else f"page:{flag_page}"
        answer, says = FLAG, comment or says
    elif comment and answer == "differs":
        says = says or comment
    elif comment:
        note = note or comment
    flag_page = question.partition(":")[2] if question.startswith("page:") else ""
    if flag_page:
        if answer != FLAG or not (flag_page.isdigit() or flag_page == "web"):
            return await card(skipped=skipped, focus=tuple(here), error="pick one of the answers")
        if not says.strip():
            return await card(skipped=skipped, focus=tuple(here), error="say what on the page is missing from the rules")
    else:
        allowed = VALUE_ANSWERS if question == "value" else NOTE_ANSWERS
        if answer not in allowed or not (question == "value" or question.startswith("note:")):
            return await card(skipped=skipped, focus=tuple(here), error="pick one of the answers")
    if user is None:
        return HTMLResponse("sign in first", status_code=401)

    row = {
        "zone": zone,
        "field": field,
        "when": when,
        "value": number.value,
        "quote": number.prov.quote or "",
    }
    document = row["quote"].partition("#L")[0]
    web = bool(document) and _checkable(document) == "html"
    if web and flag_page not in ("", "web"):
        return await card(skipped=skipped, focus=tuple(here), error="a web code has no printed page to flag")
    if flag_page == "web" and not web:
        return await card(skipped=skipped, focus=tuple(here), error="pick one of the answers")
    if web and question.startswith("note:") and question.partition(":")[2] not in _web_marks(row["quote"]):
        own = _focus(await run_in_threadpool(_rows, layer, set()), zone, field, when, question)
        if own is None:
            return await card(skipped=skipped, focus=tuple(here), error="that footnote is not printed on this number")
    if web:
        # No page and no box: the text copy's own hash stands in for the book's.
        page, placed_how, book = None, "web", _store().load(document).sha256
    else:
        placed = await run_in_threadpool(_placed, row)
        placed_how = placed.status
        book = books.expected(_store(), document) if document else ""
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
            placed=placed_how,
            book_sha256=book,
            reviewer=(user.email or str(user.id))[:80],
            reviewer_user_id=user.id,
        )
    )
    await session.commit()
    if answer == FLAG:
        # A flag is not an answer: the same card stays, Back and Forward too.
        return await card(skipped=skipped, focus=tuple(here), said=_SAID[FLAG])
    # A new answer ends the walk back: the next card is the queue's next.
    return await card(
        skipped=skipped, trail=[*passed, here][-_TRAIL:], ahead=[], said=_SAID.get(answer, "recorded")
    )
