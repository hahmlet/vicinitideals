"""FLATS rule review — read the encoded zoning standards beside their source.

Every number FLATS screens against was read out of a code document and carries
a quote saying which line of which document it came from. Until now that quote
could only be followed at a terminal, which is why 645 values sit at `draft`
and none at `verified`: reviewing meant checking out the repository.

These pages put the value and the sentence it was read from on one screen, and
take the reviewer's verdict on it.

The verdict does not become trust here. Verification is a signature hashed over
the number and its citation, and it lives in the repository so that editing
either silently withdraws it — a property no database row has. What a browser
verdict does is land in ``flats.rule_signatures``, an inbox; a drain writes the
confirmations into ``flats/config/verifications.jsonl`` for commit, and the next
deploy is what promotes the value. An undrained signature is visibly pending
rather than silently ineffective.

There is a second surface here. **Plans** asks the question the other way
round: not "what does this zone require" but "what would a lot have to be
for this building to be legal here". A design is a fixed thing — 56 ft by
36, four units, two storeys, 26 ft — so the smallest lot it could sit on in
a zone is arithmetic over the encoded standards, and it needs no parcel
data at all. Laid out across every zone, it says which markets a design can
play in before a single lot is screened.

The plat path is a control on that page rather than a fact about a city: a
four-unit attached building can be permitted as one quadplex lot or as four
townhouse lots, cities state different standards for the two, and which one
is being built is a decision about the product.

Routes: /flats, /flats/plans, /flats/plans/{design}, /flats/review/{layer},
/flats/gaps, /flats/find/{layer}, /flats/feedback, /flats/why/{layer},
/flats/reading, /flats/reading/{queue}, /flats/{layer},
/ui/flats/quote,
/ui/flats/sign, /ui/flats/sign-passage, /ui/flats/bundle, /ui/flats/book,
/ui/flats/reading/rule,
/flats/book/{document}
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Sequence

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from app.api.deps import DBSession
from app.config import settings
from app.api.routers.ui_helpers import _base_ctx, _get_counts, _get_user, templates
from app.models.flats import (
    FlatsCrossrefRuling,
    FlatsReadingRuling,
    FlatsRuleSignature,
    FlatsWordRuling,
)
from flats.encode import legible
from flats.designs.model import Design, DesignStatus, Plat, load_catalog
from flats.encode.attribution import claimed_sections, section_at
from flats.encode.find import passages
from flats.encode.gaps import digest as gaps_digest
from flats.encode.gaps import read_ledger
from flats.encode.load import load_trusted
from flats.encode.triage import Card, feed, fields_in
from flats.encode.worklist import KINDS, QUEUES
from flats.encode.worklist import Card as ReadingCard
from flats.encode.worklist import card_key
from flats.encode.worklist import context as reading_context
from flats.encode.worklist import counts as reading_counts
from flats.encode.worklist import feed as reading_feed
from flats.encode.worklist import orders as reading_orders
from flats.encode.verify import fingerprint
from flats.encode.words import STANDINGS as WORD_STANDINGS
from flats.encode.words import QUEUES as WORD_QUEUES
from flats.encode.words import Card as WordCard
from flats.encode.words import feed as word_feed
from flats.encode.words import orders as word_orders
from flats.encode.words import tally as word_tally
from flats.provenance import books, pages as page_map
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.fields import FIELDS
from flats.rules.ledger import CoverageRow, read_coverage
from flats.rules.loader import MIN_RULING
from flats.rules.model import (
    CROSSREF_OUTCOMES,
    CROSSREF_WORK,
    READING_OUTCOMES,
    READING_WORK,
    WORD_OUTCOMES,
    WORD_WORK,
    Incorporation,
    Layer,
    Reading,
    Ruling,
    Status,
    Value,
)
from flats.rules.resolver import RuleSet
from flats.score.paper import paper_fit

router = APIRouter(include_in_schema=False)

#: Lines of the document shown either side of a quoted line. Enough to see the
#: table row above and the footnote below, which is usually where the standard
#: turns out to be qualified.
_CONTEXT = 4

#: What a reviewer may say about a value. "verified" is a signature waiting to
#: be drained; "rejected" is the other half of a review — the number does not
#: match the line it cites — and it is recorded rather than dropped, because a
#: review whose only recordable outcome is agreement is not a review.
#:
#: "unclear" is the third thing a real reviewer says: the page does not answer
#: the question. That is a finding about the encoding — a quote pointing at the
#: wrong table, a standard that turns out to be conditional — and collapsing it
#: into "rejected" loses the distinction between a wrong number and an
#: unanswerable one.
_VERDICTS = frozenset({"verified", "rejected", "unclear"})

#: Verdicts that mean nothing without an explanation. Recording "wrong" with no
#: word about what is wrong produces a queue an encoder cannot act on, which is
#: the same as producing nothing.
_NEEDS_NOTE = frozenset({"rejected", "unclear"})

#: What the reviewer is told happened, in terms of what happens next rather
#: than of what was stored. "Recorded" is true of all three and useful about
#: none of them.
_SAID = {
    "verified": "confirmed — this one is done; the confirmation goes to the verification log",
    "unclear": "queried — it joins the batch an agent works through, and comes back answered",
    "rejected": "problem raised — it joins the batch as something to fix, not to explain",
}

#: What each gap cause means, said to somebody who is not going to run a
#: command about it. The encoder's phrasing names modules and flags; a reviewer
#: deciding where to spend an afternoon needs the shape of the work.
_CAUSE_WORDS = {
    "unofficial": "cites somebody's restatement of the code, not the code",
    "contested": "the file and the document state different numbers",
    "quotable": "the document says it plainly — a citation can be attached",
    "conditional": "the document qualifies it, by footnote or by lot size",
    "multi": "the document states more than one number for it",
    "undeclared": "cites a document nothing has fetched",
    "unread": "a document we hold prints it — nobody has read the line",
    "unsourced": "no document we hold states it — the chapter is still to find",
    "uncheckable": "a yes/no or a category, which only a person can cite",
    "unmapped": "a zone code the ordinance never uses — no document will state it",
}

#: The layer-wide block's zone label. Not a zone code, so it cannot collide.
_DEFAULTS = "(layer defaults)"


@lru_cache(maxsize=1)
def _layers() -> dict[str, Layer]:
    """The whole rule hierarchy, with trust applied, parsed once.

    Cached for the life of the process because everything it reads is baked
    into the image -- the YAML, the verification log, the dispute log -- and a
    deploy restarts the process.

    ``load_trusted`` rather than ``load_rules``: parsing alone leaves every
    value ``draft``, because trust may not be typed into a rule file. The
    signature logs are what promote and demote, so a screen reading the parse
    output would report a corpus nobody had ever confirmed or rejected, however
    many signatures had been drained into the repository.
    """
    return load_trusted(strict=False).layers


@lru_cache(maxsize=1)
def _store() -> ProvenanceStore:
    return ProvenanceStore()


@lru_cache(maxsize=1)
def _known_documents() -> frozenset[str]:
    """Every document path the provenance store holds.

    The quote reference arrives as a query parameter, so it is attacker-chosen
    text that ends up joined onto a filesystem root. Membership of this set is
    the gate: a reference naming anything the store did not fetch is refused
    before a path is built from it, which leaves no room for "..", an absolute
    path, or a symlink to argue about.
    """
    return frozenset(_store().documents())


def _blocks(layer: Layer) -> list[tuple[str, dict[str, Value], str | None]]:
    out: list[tuple[str, dict[str, Value], str | None]] = [
        (_DEFAULTS, layer.defaults, None)
    ]
    for code in sorted(layer.zones):
        zone = layer.zones[code]
        out.append((code, zone.values, zone.notes))
    return out


def _value_rows(layer: Layer) -> list[dict[str, Any]]:
    """Every encoded number in a layer, as flat rows for the table.

    One row per *number*, not per field. A standard with an exception is two
    sentences in the code and two separate things to confirm, and a reviewer who
    checked the base has not thereby checked the exception — so each addresses,
    displays and signs on its own.
    """
    rows: list[dict[str, Any]] = []
    for zone_code, values, notes in _blocks(layer):
        for name in sorted(values):
            value = values[name]
            numbers = [(value, ())] + [(v, v.key) for v in value.variants]
            for number, when in numbers:
                rows.append(
                    {
                        # What a verdict on this number would be a verdict
                        # *about*. Change the number, its citation or its
                        # quote and this moves, which is how a decision stops
                        # applying to a value it was never made about.
                        "mark": fingerprint(
                            layer.layer,
                            zone_code,
                            name,
                            number.value,
                            cite=number.prov.cite,
                            quote=number.prov.quote,
                            when=when,
                        ),
                        "zone": zone_code,
                        "field": name,
                        "value": number.value,
                        "when": "+".join(when),
                        "when_label": ", ".join(when),
                        "status": number.status.value,
                        "trusted": number.status is Status.verified,
                        "reviewer": number.reviewer,
                        "quote": number.prov.quote,
                        "cite": number.prov.cite,
                        "url": number.prov.url,
                        "variants": len(value.variants),
                        "zone_notes": notes,
                    }
                )
    return rows


def _number(layer: Layer, zone: str, field: str, when: str) -> Any:
    """The exact number a reviewer's verdict is about, found by its address.

    Refusing an address that names nothing is what keeps the inbox honest: a
    row about a value that does not exist could never be drained, and would sit
    in the queue looking like work somebody did.
    """
    for zone_code, values, _notes in _blocks(layer):
        if zone_code != zone or field not in values:
            continue
        value = values[field]
        if not when:
            return value
        for variant in value.variants:
            if "+".join(variant.key) == when:
                return variant
    return None


def _layer_summary(layer: Layer) -> dict[str, Any]:
    rows = _value_rows(layer)
    borrowed = sum(1 for zone in layer.zones.values() if isinstance(zone.like, Incorporation))
    return {
        "id": layer.layer,
        "label": layer.label,
        "kind": layer.kind,
        "eligible": layer.eligible,
        "zones": len(layer.zones),
        # Not "values". Jinja resolves an attribute before a key, so a dict
        # with a "values" key renders dict.values — the bound method, printed
        # as "<built-in method values of dict object at 0x...>" once per row.
        "standards": len(rows),
        "verified": sum(1 for row in rows if row["trusted"]),
        # Read and refused. Counted separately from both, because a rejected
        # number is neither confirmed nor merely unread, and a jurisdiction
        # carrying open rejections must not read as one nobody has looked at.
        "disputed": sum(1 for row in rows if row["status"] == Status.disputed.value),
        "quoted": sum(1 for row in rows if row["quote"]),
        # Standards this jurisdiction claims and cannot show. They are not in
        # `standards` — they are not rules — and a page that omitted them would
        # report a thinly encoded jurisdiction as a small one.
        "unread": len(layer.wanted),
        "borrowed": borrowed,
        "documents": len(layer.code),
    }


@router.get("/flats", response_class=HTMLResponse)
async def flats_index(request: Request, session: DBSession) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    summaries = [_layer_summary(layer) for _, layer in sorted(_layers().items())]
    totals = {
        "layers": len(summaries),
        "zones": sum(s["zones"] for s in summaries),
        "standards": sum(s["standards"] for s in summaries),
        "verified": sum(s["verified"] for s in summaries),
        "disputed": sum(s["disputed"] for s in summaries),
        "quoted": sum(s["quoted"] for s in summaries),
        "unread": sum(s["unread"] for s in summaries),
    }
    return templates.TemplateResponse(
        request,
        "flats_rules.html",
        {
            **_base_ctx(user, dedup_count, "flats", conflicts_count=conflicts_count),
            "summaries": summaries,
            "totals": totals,
        },
    )


async def _decisions(session: DBSession, layer_id: str) -> dict[tuple[str, str, str], Any]:
    """The latest verdict on each number in this layer, by address.

    Latest wins because changing your mind is allowed and supersedes rather than
    duplicates; the older rows stay so the history of who believed what survives.
    """
    rows = (
        await session.execute(
            select(FlatsRuleSignature)
            .where(FlatsRuleSignature.layer == layer_id)
            .order_by(FlatsRuleSignature.decided_at)
        )
    ).scalars()
    return {(r.zone, r.field, r.when_key): r for r in rows}


# --- plans: what a lot would have to be ------------------------------


@lru_cache(maxsize=1)
def _catalog() -> Any:
    """The design catalog, parsed once. Same reasoning as ``_layers``."""
    return load_catalog()


@lru_cache(maxsize=1)
def _ruleset() -> RuleSet:
    return RuleSet(_layers())


def _designs() -> list[Design]:
    """Catalog entries a plan may be drawn for, active ones first.

    Archived designs stay listed. Results on disk name them, and a page that
    hid them would make an old answer unreadable rather than superseded.
    """
    got = list(_catalog())
    return sorted(got, key=lambda d: (d.status is not DesignStatus.active, d.label, d.version))


def _for_plat(design: Design, plat: str) -> Design:
    """The same building costed for the other plat path.

    Not a second catalog entry. The building has not changed — only how its
    four units are being platted — and making that a catalog entry would double
    the design matrix every screening run walks.
    """
    want = Plat.unit_lots if plat == Plat.unit_lots.value else Plat.one_lot
    return design if design.plat is want else design.model_copy(update={"plat": want})


def _plan_rows(design: Design) -> list[dict[str, Any]]:
    """One row per encoded zone: the lot this design would need there.

    Every zone is listed, including the ones that do not allow a fourplex at
    all. A zone that says no is a fact about the market and belongs on the
    page; dropping it would make the list read as though nobody had looked.
    """
    rules = _ruleset()
    rows: list[dict[str, Any]] = []
    for layer_id, layer in sorted(_layers().items()):
        for zone_code in sorted(layer.zones):
            got = rules.resolve(layer_id, zone_code, design.conditions)
            fit = paper_fit(design, got)
            allowed = got.get("quadplex_allowed")
            cap = got.get("max_units")
            stalls = got.get("parking_min_per_unit")
            rows.append(
                {
                    "layer": layer_id,
                    "jurisdiction": layer.label,
                    "zone": zone_code,
                    "allowed": allowed,
                    "capped": bool(isinstance(cap, (int, float)) and cap < design.units),
                    "width": fit.min_width_ft,
                    "depth": fit.min_depth_ft,
                    "area": fit.min_area_sqft,
                    "binding": fit.binding,
                    "orientation": fit.orientation,
                    "height_ok": fit.height_ok,
                    "unknown": fit.unknown,
                    "complete": fit.complete,
                    # Stated but unread. The number is used and labelled —
                    # a corpus of 650 encoded standards and no signatures
                    # would otherwise render as an empty page.
                    "unsigned": len(fit.unsigned),
                    "certain": fit.certain,
                    # A stall minimum above what the design parks is not a no —
                    # it is the number the site plan has to find room for.
                    "stalls_short": (
                        round(stalls * design.units - design.stalls_required, 2)
                        if isinstance(stalls, (int, float))
                        and stalls * design.units > design.stalls_required
                        else 0
                    ),
                }
            )
    return rows


def _plan_tally(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """What the rows add up to. Counted here so the template stays a table."""
    allowed = [r for r in rows if r["allowed"] and not r["capped"]]
    # Not "clear". A dict key that shadows a dict method renders the method:
    # Jinja resolves the attribute first, so `tally.clear` prints
    # "<built-in method clear of dict object at 0x...>" where a count belongs.
    on_paper = [r for r in allowed if r["height_ok"] is not False and r["complete"]]
    areas = sorted(r["area"] for r in on_paper if r["area"] is not None)
    return {
        "zones": len(rows),
        "allowed": len(allowed),
        "on_paper": len(on_paper),
        "too_tall": sum(1 for r in allowed if r["height_ok"] is False),
        "incomplete": sum(1 for r in allowed if not r["complete"]),
        "reviewed": sum(1 for r in on_paper if r["certain"]),
        "smallest": areas[0] if areas else None,
        "median": areas[len(areas) // 2] if areas else None,
    }


def _design_card(design: Design, plat: str) -> dict[str, Any]:
    costed = _for_plat(design, plat)
    return {
        "key": design.key,
        "label": design.label,
        "status": design.status.value,
        "width": design.footprint.width_ft,
        "depth": design.footprint.depth_ft,
        "ground": design.ground_sqft,
        "units": design.units,
        "stories": design.stories,
        "height": design.height_ft,
        "stalls": design.stalls_required,
        "typology": design.typology.value,
        "delivery": design.delivery.method.value,
        "plat": costed.plat.value,
        **_plan_tally(_plan_rows(costed)),
    }


@router.get("/flats/plans", response_class=HTMLResponse)
async def flats_plans(
    request: Request, session: DBSession, plat: str = Query("one_lot")
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    cards = [_design_card(d, plat) for d in _designs()]
    return templates.TemplateResponse(
        request,
        "flats_plans.html",
        {
            **_base_ctx(user, dedup_count, "flats_plans", conflicts_count=conflicts_count),
            "designs": cards,
            "plat": plat if plat == Plat.unit_lots.value else Plat.one_lot.value,
        },
    )


@router.get("/flats/plans/{design_key}", response_class=HTMLResponse)
async def flats_plan(
    request: Request, session: DBSession, design_key: str, plat: str = Query("one_lot")
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    catalog = _catalog()
    base = catalog.get(design_key) if design_key in catalog else None
    if base is None:
        return templates.TemplateResponse(
            request,
            "flats_plans.html",
            {
                **_base_ctx(user, dedup_count, "flats_plans", conflicts_count=conflicts_count),
                "designs": [_design_card(d, plat) for d in _designs()],
                "plat": Plat.one_lot.value,
                "missing": design_key,
            },
            status_code=404,
        )
    design = _for_plat(base, plat)
    rows = _plan_rows(design)
    return templates.TemplateResponse(
        request,
        "flats_plan.html",
        {
            **_base_ctx(user, dedup_count, "flats_plans", conflicts_count=conflicts_count),
            "design": _design_card(base, plat),
            "assumptions": list(base.assumptions),
            "notes": base.notes,
            "rows": rows,
            "tally": _plan_tally(rows),
            "plat": design.plat.value,
        },
    )


# --- review: one passage of code, and every number read out of it -------


#: A table caption, wherever the codifier put it. Municode repeats it across
#: three columns and eCode prints it once; either way it is the line that says
#: which zones the columns below belong to, and it is the single most useful
#: thing to show above a window of cells.
_CAPTION = re.compile(r"^\s*Table\s+[0-9A-Z]", re.I)

#: A section heading: "19.302.4 Development Standards", "§ 4.0130", "Section
#: 4.122". The same shape the encoder tracks, kept separately here because a
#: reviewer needs the words after the number and the encoder does not.
_HEADING = re.compile(
    r"^\s*(?:§\s*)?(?:Sec(?:tion|\.)?\s+)?(?P<sec>\d{1,3}\.\d{2,4}(?:\.\d{1,4})?)"
    r"(?P<rest>[ .\u2014-]+\S.*)?$"
)

#: How far above the window to look. Far enough to clear a long table, close
#: enough that the heading found is plausibly the one governing these lines.
_LOOK_BACK = 400


#: A capitalised word — what separates a heading from a wrapped line of
#: prose that happens to open on a number. Gresham prints "14.52 units per
#: acre" mid-paragraph, and read as a heading it files everything below it
#: under a section that does not exist.
_TITLED = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")


def _titled(line: str) -> bool:
    """Whether a line is a section heading rather than a sentence."""
    found = _HEADING.match(line)
    rest = found.group("rest") if found else None
    return bool(rest) and len(line) <= 120 and bool(_TITLED.search(rest))


def _above(document: str, first: int) -> dict[str, str]:
    """The section heading and table caption a window sits under.

    A setback read off a table row means one thing under "Table 19.302.4 High
    Density Residential Development Standards" and another under the plan
    district's table three pages later, and the window itself — cells and
    numbers — says neither. The reviewer is being asked whether a number
    belongs to this zone, which is a question about the heading.

    Both are reported when both exist: the caption says which columns, the
    section says which chapter, and a mismatch between them is itself a
    finding.
    """
    try:
        whole = _store().load(document).text.splitlines()
    except (ProvenanceError, OSError):
        return {}
    out: dict[str, str] = {}
    for n in range(min(first, len(whole)) - 1, max(first - _LOOK_BACK, 0) - 1, -1):
        line = whole[n].strip()
        if not line:
            continue
        if "caption" not in out and _CAPTION.match(line):
            out["caption"] = line[:160]
        if "section" not in out and _titled(line):
            out["section"] = line[:160]
        if len(out) == 2:
            break
    return out


#: A line of a grid: a label, a gap wide enough to be a column boundary, and
#: something in the next column. Cheap and deliberately loose — it decides
#: whether a card is flagged for a closer look, not whether a value is trusted.
_GRID = re.compile(r"^\S.*\S\s{3,}\S")


def _from_a_table(lines: Sequence[dict[str, Any]]) -> bool:
    """Whether the cited lines are grid rows rather than sentences.

    Worth saying out loud on the card. Extraction flattens a grid: the columns
    are gone, and which one a number belonged to is inferred from a heading
    rather than from where the ink sat. Every silent failure this system has
    had — rotated headers dropped, a footnote marker welded onto a value, a
    letter-spaced scan — has been in a table. A sentence carries its own
    context and a cell does not.
    """
    cited = [line for line in lines if line.get("quoted")]
    hits = sum(1 for line in cited if _GRID.match(line["text"].strip()))
    return bool(cited) and hits * 2 >= len(cited)


@lru_cache(maxsize=128)
def _page_index(document: str) -> Any:
    """A document's page map, if it has one and it still fits the stored text."""
    try:
        return page_map.read(_store(), document)
    except (ProvenanceError, OSError):
        return None


def _pages(document: str, first: int, last: int) -> list[dict[str, Any]]:
    """Which pages of the book a span of lines was printed on.

    A line number is ours; a page number is the document's. The distinction
    matters the moment an encoded standard has to be defended to somebody who
    does not have this system in front of them — a planner, an architect, a
    lawyer reading the same code off paper. They cannot check "line 3,041".
    They can turn to page 28-5.

    Empty for the HTML half of the corpus, which has no pages. Their citations
    address a section anchor instead, which is what those codifiers give.
    """
    index = _page_index(document)
    if index is None:
        return []
    return [
        {"n": page.n, "label": page.label, "cite": page.cite}
        for page in index.span(first, last)
    ]


def _pages_in(document: str, ranges: Sequence[tuple[int, int]]) -> list[dict[str, Any]]:
    """The pages every stretch of a citation was printed on, in book order.

    Each range asked separately and the answers unioned, rather than one sweep
    across the hull. A citation naming a table row and the footnote pages under
    it is two or three pages; taken as the hull, Wilsonville's
    ``#L572-L574,L8314,L8318`` answers with two hundred and two, which is the
    whole back half of the chapter.

    That is the failure this function is least able to afford. A page number
    exists so a standard can be defended to somebody who does not have this
    system in front of them, and "pages CD4:15 through CD4:216" tells a planner
    to read the chapter.
    """
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for first, last in ranges:
        for page in _pages(document, first, last):
            if page["n"] not in seen:
                seen.add(page["n"])
                out.append(page)
    return sorted(out, key=lambda page: page["n"])


def _page_note(quote: str) -> str:
    """A quote's pages, as one phrase for a written citation."""
    found = _pages_in(quote.partition("#L")[0], _ranges(quote))
    if not found:
        return ""
    # Both numbers, where both exist. The printed one is what a code cites and
    # what somebody holding the book will look for; the PDF one is what opens
    # the right sheet in a viewer, and the two are rarely the same.
    return ", ".join(
        f"p. {page['label']} (PDF page {page['n']})" if page["label"] else f"PDF page {page['n']}"
        for page in found
    )


@lru_cache(maxsize=64)
def _document_lines(document: str) -> tuple[str, ...]:
    """A whole stored document, cached. Empty where it cannot be read."""
    try:
        return tuple(_store().load(document).text.splitlines())
    except (ProvenanceError, OSError):
        return ()


def _misattributed(cite: str, quote: str) -> dict[str, str] | None:
    """Whether a citation names a section its own quoted text is not in.

    The failure no other check can see. The quote resolves, the text states the
    number, and the citation sends a reader to a section where none of it is
    printed — Wilsonville's RN zone cited 4.127 against lines that are 4.113,
    the citywide setbacks, which apply only where a master plan does not
    provide otherwise. Right number, wrong authority, and the reviewer is the
    only one who can say which half to correct.
    """
    span = _span(quote)
    lines = _document_lines(quote.partition("#L")[0]) if span else ()
    if not lines:
        return None
    claimed = claimed_sections(cite or "")
    found = section_at(lines, span[0])
    if not claimed or not found:
        return None
    if any(one.startswith(found) or found.startswith(one) for one in claimed):
        return None
    return {"claimed": ", ".join(claimed), "found": found}


def _span(ref: str) -> tuple[int, int] | None:
    """The line range a citation names, or None if it names no lines.

    A citation may name several disjoint ranges -- a table row and the
    footnote printed pages under it -- and they arrive comma separated::

        4.planning.txt#L13405-L13414,L13416-L13420

    What comes back is the hull covering all of them, which is what every
    caller wants: the stretch of document a reading was taken from.

    Splitting only on ``-`` raised on ``int("13414,13416")`` and returned
    None. None means "names no lines", so :func:`_within` matched nothing,
    the signing route wrote zero rows, and it reported success. 962 of 2,150
    cited values -- 45 percent of the corpus -- could not be signed at all,
    and nothing said so.
    """
    ranges = _ranges(ref)
    if not ranges:
        return None
    return min(a for a, _ in ranges), max(b for _, b in ranges)


def _ranges(ref: str) -> list[tuple[int, int]]:
    """Every line range a citation names, in the order it names them.

    The hull is what a signature is addressed to; these are what a reader is
    shown. Keeping them apart is not a nicety: the two stretches of
    ``#L874-L875,L4408-L4410`` are a table row and the footnote qualifying it,
    and a window drawn from the hull is three and a half thousand lines of
    unrelated code with two of them marked.
    """
    _, _, fragment = ref.partition("#L")
    out: list[tuple[int, int]] = []
    for part in fragment.replace("L", "").split(","):
        edges: list[int] = []
        for edge in part.split("-"):
            edge = edge.strip()
            if not edge:
                continue
            try:
                edges.append(int(edge))
            except ValueError:
                # One unreadable edge is not a reason to discard the ranges
                # that did parse.
                continue
        if edges:
            out.append((edges[0], edges[-1]))
    return out


#: How far apart two citations may sit and still be one reading. A zone's
#: dimensional standards are cited line by line — Tualatin's RL lot size at
#: L166, its front setback at L211 — and shown separately they are eleven
#: openings of one table. Sixteen lines is wide enough to chain a table and
#: narrow enough that the next section starts a new card.
_GAP = 16

#: The longest window a card will show. Past this the chain has stopped being
#: a passage and become a chapter, and the reviewer loses the highlighted
#: lines in the scroll.
_SPAN = 140


def _cluster(spans: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    """Citations chained into readings, in the order the document prints them."""
    out: list[list[tuple[int, int]]] = []
    for first, last in sorted(spans):
        if out:
            running = out[-1]
            reach = max(x[1] for x in running)
            if first - reach <= _GAP and last - running[0][0] <= _SPAN:
                running.append((first, last))
                continue
        out.append([(first, last)])
    return out


def _stands(seen: Any, mark: str) -> bool:
    """Whether an existing verdict still covers this number.

    A verdict is about a value, not about a field. Correct a setback in
    response to somebody's note and their verdict no longer applies to what is
    there — so the item returns to the queue rather than sitting decided, which
    is what makes a round of fixes checkable instead of merely claimed.

    A verdict recorded before fingerprints existed carries none, and is taken
    at face value: resurfacing six hundred of them would bury the handful that
    genuinely changed.
    """
    return bool(seen) and (not seen.fingerprint or seen.fingerprint == mark)


def _passages(layer: Layer, decided: dict) -> list[dict[str, Any]]:
    """The layer's unreviewed numbers, gathered under the text they were read from.

    A zoning table states a dozen standards, and the rules table makes a
    reviewer open it a dozen times — once per value, scattered down a list
    ordered by zone, each opening four lines of the same page. Grouping
    inverts it: the passage is shown once and every number claiming it sits
    beside it. That is both far less clicking and a better check, because two
    numbers read off the same table that disagree with each other are only
    visible when they are adjacent.

    Citations are clustered by proximity rather than by exact match, since a
    table row is cited line by line and no two of those lines are the same
    reference. Ordered by document and line, so a pass reads the code front to
    back.
    """
    quoted: dict[str, list[dict[str, Any]]] = {}
    loose: list[dict[str, Any]] = []
    for row in _value_rows(layer):
        if not row["quote"]:
            continue
        seen = decided.get((row["zone"], row["field"], row["when"]))
        if _stands(seen, row["mark"]):
            continue
        # Decided once, then changed. The reviewer is owed what they said and
        # what it says now, side by side — that comparison is the whole point
        # of asking them to look again.
        row["was"] = seen
        span = _span(row["quote"])
        row["line"] = span[0] if span else 0
        # A citation naming two stretches pages apart -- a table row and the
        # footnote qualifying it -- gets a card of its own rather than joining
        # a cluster. ``_span`` answers with the range covering both, and a
        # cluster keyed on that would draw a window three thousand lines deep
        # and claim every unrelated standard printed in between.
        if span is None or "," in row["quote"].partition("#L")[2]:
            loose.append(row)
        else:
            quoted.setdefault(row["quote"].partition("#L")[0], []).append(row)

    cards: list[dict[str, Any]] = []
    for document, rows in quoted.items():
        by_span: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for row in rows:
            by_span.setdefault(_span(row["quote"]), []).append(row)
        for chain in _cluster(list(by_span)):
            here = [row for span in chain for row in by_span[span]]
            lines = _window(document, chain)
            cards.append(
                {
                    "ref": f"{document}#L{chain[0][0]}-L{max(x[1] for x in chain)}",
                    "refs": [f"{document}#L{a}-L{b}" for a, b in chain],
                    "document": document,
                    "cite": here[0]["cite"],
                    "url": here[0]["url"],
                    "lines": lines,
                    "pages": _pages_in(document, chain),
                    "misattributed": _misattributed(here[0]["cite"], here[0]["quote"]),
                    "error": "",
                    "rows": sorted(here, key=lambda r: (r["line"], r["zone"], r["field"])),
                    **_above(document, chain[0][0]),
                    "gridded": _from_a_table(lines),
                }
            )
    # Grouped by citation, not one card per value: two standards read off the
    # same table row and its footnote are one passage, and shown as two cards
    # they are the same lines opened twice with no sign they are the same
    # reading.
    together: dict[str, list[dict[str, Any]]] = {}
    for row in loose:
        together.setdefault(row["quote"], []).append(row)
    for quote, here in together.items():
        lines, error = _cited_lines(quote)
        cards.append(
            {
                "ref": quote,
                "refs": [quote],
                "document": quote.partition("#L")[0],
                "cite": here[0]["cite"],
                "url": here[0]["url"],
                "lines": lines,
                "error": error,
                "rows": sorted(here, key=lambda r: (r["line"], r["zone"], r["field"])),
            }
        )
    return sorted(cards, key=lambda c: (c["document"], _span(c["ref"]) or (0, 0)))


def _line(n: int, text: str, quoted: bool) -> dict[str, Any]:
    """One line of a document as the review pages show it.

    Shared by the card and by the on-demand citation view, because the two sit
    inches apart on the same screen and a line squeezed in one and not the
    other reads as two different documents.

    ``text`` stays exactly as stored -- it is what a feedback bundle quotes and
    what a reviewer falls back to when the tidied version reads oddly. ``shown``
    is the same line with the extractor's artefacts taken out, and only where
    taking them out is lossless: a sentence's horizontal spacing carries
    nothing, a table row's runs of spaces are the columns.
    """
    grid = legible.is_grid(text)
    return {
        "n": n,
        "text": text,
        "shown": text.rstrip() if grid else legible.legible(text),
        "grid": grid,
        "quoted": quoted,
    }


def _window(document: str, chain: list[tuple[int, int]]) -> list[dict[str, Any]]:
    """One stretch of the document, with every cited line in it marked.

    Marking them all is the point of showing them together: the reviewer sees
    which lines of the table are claimed and, just as usefully, which are not.
    """
    try:
        whole = _store().load(document).text.splitlines()
    except (ProvenanceError, OSError):
        return []
    start = max(min(x[0] for x in chain) - _CONTEXT, 1)
    end = min(max(x[1] for x in chain) + _CONTEXT, len(whole))
    return [
        _line(n, whole[n - 1], any(first <= n <= last for first, last in chain))
        for n in range(start, end + 1)
    ]


# --- the feedback bundle -----------------------------------------------


def _bundle_text(rows: Sequence[Any]) -> str:
    """A reviewer's problems as one block of text an encoder can work from.

    Self-contained on purpose. Each item carries the address, the number, its
    citation, the code text that was on screen and the note — so it can be read
    by someone who was not there, after the document has been re-fetched and
    every line number in it has moved. A bundle that said "see the review page"
    would be worth nothing a week later.

    The fingerprint is included because it is how the fix gets checked: change
    the encoding and it stops matching, which is what makes the item resurface
    as answered rather than merely old.
    """
    out = [
        "# FLATS rule review — feedback",
        "",
        f"{len(rows)} item(s). Each is one encoded value, the text it was read from, "
        "and what the reviewer found wrong with it.",
        "",
    ]
    for n, row in enumerate(rows, 1):
        when = f" [{row.when_key.replace('+', ', ')}]" if row.when_key else ""
        out += [
            "---",
            "",
            f"## {n}. {row.layer} · {row.zone} · {row.field}{when}",
            "",
            f"- **encoded value:** `{row.value}`",
            f"- **verdict:** {row.verdict}",
            f"- **citation:** {row.cite}",
            f"- **quote:** `{row.quote}`",
            f"- **printed at:** {_page_note(row.quote) or '(no page map for this source)'}",
            f"- **reviewed:** {row.decided_at:%Y-%m-%d} by {row.reviewer}",
            f"- **fingerprint:** `{row.fingerprint or '(none recorded)'}`",
            "",
            "**Reviewer note**",
            "",
            (row.note or "(none)").strip(),
            "",
            "**What was on screen**",
            "",
            "```",
            (row.shown or "(not recorded — this verdict predates the feedback capture)").rstrip(),
            "```",
            "",
        ]
    return "\n".join(out)


# --- the work ordered ---------------------------------------------------
#
# The rule-review bundle above carries what a reviewer found *wrong*. This
# carries what a reviewer asked to be *done*, which until now went nowhere.
#
# Five reading outcomes and two triage outcomes order work -- encode this,
# open that chapter, we need a field, go and fetch this document -- and each
# was recorded in the queue that asked the question. That is the right place
# for a decision and the wrong place for a job: the work was spread across
# five screens, phrased as answers, and nobody doing a day of encoding could
# see it as a list.

#: The most statements printed under one reading order. A section with two
#: hundred is a chapter, and pasting a chapter into a work order buries the
#: other nineteen jobs beside it.
WORK_LINES = 12

#: The most glossary entries printed under one word order. A code that files a
#: word under nine headings has said something worth knowing in the first few;
#: the rest is the same job, and pasting them all buries the next order.
WORK_WORDS = 5


def _work_text(
    reading: Sequence[Any], fetches: Sequence[Any], words: Sequence[Any] = ()
) -> str:
    """Every ruling that ordered work, as a job somebody can pick up.

    Grouped by what is being asked for rather than by city, because those are
    different days: encoding numbers, opening chapters and fixing the
    extractor want different heads, and a list interleaving them makes the
    reader re-decide what kind of work they are doing on every item.

    Nothing here needs closing by hand. Cards are derived from the corpus and
    the current encoding, so encoding the value stops the line being uncited
    and the order stops existing on its own -- the same bargain the queues
    strike, and the reason this can be regenerated rather than maintained.

    Self-contained, like the feedback bundle and for the same reason: the
    document, the section, the statements and the reviewer's note all travel
    with the item, so it can be worked by somebody who was not there, after
    the document has been re-fetched and every line number in it has moved.
    """
    total = len(reading) + len(fetches) + len(words)
    out = [
        "# FLATS — work ordered by review",
        "",
        f"{total} job(s). Each is a decision somebody already made that asks "
        "for something to be done, grouped by the kind of doing and ordered "
        "by the cost of leaving it undone.",
        "",
        "These are answers, not questions: no card here is still waiting to "
        "be reviewed. A job disappears from this list when the work lands — "
        "encode the value and its line stops being uncited, so the card it "
        "came from stops existing. Nothing has to be ticked off.",
        "",
    ]

    for outcome, job in READING_WORK.items():
        here = [c for c in reading if c.outcome == outcome]
        if not here:
            continue
        out += ["", f"## {job} ({len(here)})", ""]
        for card in here:
            head = f"{card.layer} · {card.section or '(no heading)'}"
            out += [
                f"### {head}",
                "",
                f"- **document:** `{card.path}`",
                f"- **queue:** {card.kind} · **lots:** {card.lots:,}"
                f" · **statements:** {len(card.lines)}",
                f"- **standards named:** {', '.join(card.fields) or '(none)'}",
                f"- **fingerprint when ruled:** `{card.ruling.fingerprint or '(none)'}`"
                + ("  ⚠ the section has moved since" if card.moved else ""),
                "",
                "**Why**",
                "",
                (card.ruling.note or "(none)").strip(),
                "",
                "**What the code says**",
                "",
                "```",
            ]
            for ln in card.by_interest[:WORK_LINES]:
                held = f"   [we hold {ln.shown_held}]" if ln.held else ""
                out.append(f"{ln.line:>6}  {ln.text}{held}")
            if len(card.lines) > WORK_LINES:
                out.append(f"       … and {len(card.lines) - WORK_LINES} more")
            out += ["```", ""]

    for outcome, job in CROSSREF_WORK.items():
        here = [c for c in fetches if c.outcome == outcome]
        if not here:
            continue
        out += ["", f"## {job} ({len(here)})", ""]
        for card in here:
            out += [
                f"### {card.layer} · {card.kind} {card.ref}",
                "",
                f"- **called:** {card.title or '(nothing names it)'}",
                f"- **lots:** {card.lots:,} · **standards it stands beside:** "
                f"{', '.join(card.fields) or '(none)'}",
                "",
                "**Why**",
                "",
                # ``Ruling`` is a str subclass -- the note *is* the object, with
                # the outcome hung off it. Reading's ``Reading`` is a model and
                # carries ``.note``; the two are not interchangeable.
                (str(card.ruling or "") or "(none)").strip(),
                "",
            ]

    for outcome, job in WORD_WORK.items():
        here = [c for c in words if c.outcome == outcome]
        if not here:
            continue
        out += ["", f"## {job} ({len(here)})", ""]
        for card in here:
            out += [
                f"### {card.layer} · “{card.term}”",
                "",
                f"- **standing when asked:** {card.standing}"
                + ("" if card.exact else " (no entry for the word itself)"),
                f"- **numbers measured in it:** {card.values} · **lots:** {card.lots:,}",
                f"- **standards it sets the meaning of:** {', '.join(card.fields) or '(none)'}",
                f"- **fingerprint when ruled:** `{card.ruling.fingerprint or '(none)'}`"
                + ("  ⚠ what the city says has moved since" if card.moved else ""),
                "",
                "**Why**",
                "",
                (card.ruling.note or "(none)").strip(),
                "",
            ]
            if card.says:
                out += ["**What the city says**", "", "```"]
                for entry in card.says[:WORK_WORDS]:
                    out.append(f"{entry.cite}  {entry.term}: {entry.text}")
                if len(card.says) > WORK_WORDS:
                    out.append(f"       … and {len(card.says) - WORK_WORDS} more")
                out += ["```", ""]

    if total == 0:
        out += ["Nothing ordered. Every decision on record either closed its card "
                "or has already been acted on."]
    return "\n".join(out)


def _answered(rows: Sequence[Any]) -> list[dict[str, Any]]:
    """Raised problems whose value has since changed.

    A round of fixes is worth nothing to a reviewer who cannot tell which of
    their notes were acted on. The fingerprint answers it without anybody
    having to claim anything: it covers the value, its citation and its quote,
    so if what the repository now holds fingerprints differently, the encoding
    moved after the note was written. What moved, and to what, is shown — the
    reviewer still has to agree it moved the right way.

    Notes taken before fingerprints existed carry none and are left out: they
    cannot be told apart from notes nobody has touched, and guessing would
    report fixes that never happened.
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        layer = _layers().get(row.layer)
        if layer is None or not row.fingerprint:
            continue
        number = _number(layer, row.zone, row.field, row.when_key)
        mark = _mark(layer.layer, row.zone, row.field, row.when_key, number) if number else ""
        if mark == row.fingerprint:
            continue
        out.append(
            {
                "was": row,
                "gone": number is None,
                "value": number.value if number else "",
                "cite": number.prov.cite if number else "",
                "quote": number.prov.quote if number else "",
            }
        )
    return out


# --- what is not encoded -------------------------------------------------


@lru_cache(maxsize=1)
def _gaps() -> dict[str, Any]:
    """The written answer to "what is missing", and whether it still holds.

    Measuring is a minute per jurisdiction — every value corroborated against
    every stored document — so it is written down by a command and read back
    here. The digest is over the encoded values and their citations, so a page
    can say the measurement has been overtaken instead of quietly presenting
    last week's work list as today's.
    """
    ledger = read_ledger() or {"layers": {}, "digest": ""}
    ledger["current"] = ledger.get("digest") == gaps_digest(_layers())
    return ledger


@lru_cache(maxsize=1)
def _coverage() -> dict[str, Any]:
    """What the holes cost, in lots, from the generated coverage ledger.

    The gap list says what is missing; this says which missing thing is worth
    an afternoon. They rank differently and the difference is the whole point:
    a jurisdiction with four gaps over eleven lots is finished for any purpose
    that matters, and one with a single unencoded zone can be sitting on
    fourteen thousand.

    Only what the parcel corpus has seen is counted, so an encoded jurisdiction
    with no rows is not a jurisdiction with no lots — it is one nothing has
    counted yet, and the page has to say which is which.
    """
    rows = read_coverage()
    if rows is None:
        return {"measured": False, "layers": [], "worst": [], "uncounted": []}

    layers = _layers()
    by_layer: dict[str, dict[str, Any]] = {}
    for row in rows:
        one = by_layer.setdefault(
            row.jurisdiction,
            {
                "layer": row.jurisdiction,
                "label": getattr(layers.get(row.jurisdiction), "label", row.jurisdiction),
                "known": row.jurisdiction in layers,
                "lots": 0,
                "blocked": 0,
                "missing": [],
                "partial": 0,
            },
        )
        one["lots"] += row.lots
        one["blocked"] += row.blocking
        if row.status in ("zone_missing", "jurisdiction_missing"):
            one["missing"].append({"zone": row.zone, "lots": row.lots})
        elif row.blocking:
            one["partial"] += 1
    for one in by_layer.values():
        one["missing"].sort(key=lambda z: -z["lots"])

    return {
        "measured": True,
        "layers": sorted(by_layer.values(), key=lambda one: -one["blocked"]),
        "worst": [_blocker(row) for row in rows if row.blocking][:15],
        # Encoded, but no lot has ever been counted against it. Silence about
        # these would read as "nothing blocked here", which is the exact
        # mistake the coverage ledger exists to prevent.
        "uncounted": sorted(
            {
                layer_id
                for layer_id, layer in _layers().items()
                if layer.kind in ("city", "unincorporated")
            }
            - {row.jurisdiction for row in rows}
        ),
        # Which counties the corpus actually reached, read off the data rather
        # than written down — the sentence that says what is not covered has to
        # move when the coverage does, or it becomes the lie it was warning about.
        "counties": sorted(
            {
                row.jurisdiction.split("/")[1].replace("-", " ").title()
                for row in rows
                if row.jurisdiction.count("/") >= 2
            }
        ),
        "lots": sum(row.lots for row in rows),
        "blocked": sum(row.blocking for row in rows),
    }


def _blocker(row: CoverageRow) -> dict[str, Any]:
    """One coverage row, said in the words a reviewer would use."""
    missing = [one for one in row.missing_required.split(";") if one]
    untrusted = [one for one in row.untrusted_fields.split(";") if one]
    if row.status == "jurisdiction_missing":
        why = "nothing at all is encoded for this jurisdiction"
    elif row.status == "zone_missing":
        why = "this zone has no encoding — the jurisdiction has others"
    elif missing:
        why = "no value for " + ", ".join(missing)
    elif untrusted:
        why = f"{len(untrusted)} value(s) encoded but not yet confirmed by a person"
    else:
        why = "a cited document has changed since this was confirmed"
    return {
        "layer": row.jurisdiction,
        "zone": row.zone,
        "lots": row.lots,
        "status": row.status,
        "why": why,
        "known": row.jurisdiction in _layers(),
    }


@router.get("/flats/gaps", response_class=HTMLResponse)
async def flats_gaps(request: Request, session: DBSession) -> HTMLResponse:
    """Every value nothing backs, sorted by what would unstick it.

    The review queue can only show what has a quote. A standard with no
    citation never reaches it — so without this page the holes are the one
    thing the system does not show, and a jurisdiction can look finished
    because the half nobody encoded is invisible.
    """
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    ledger = _gaps()
    rows = [
        {"layer": layer_id, **one}
        for layer_id, one in sorted(ledger["layers"].items())
        if one["gaps"]
    ]
    wrong = [
        {"layer": layer_id, "label": one["label"], **item}
        for layer_id, one in sorted(ledger["layers"].items())
        for item in one.get("misattributed", ())
    ]
    return templates.TemplateResponse(
        request,
        "flats_gaps.html",
        {
            **_base_ctx(user, dedup_count, "flats_gaps", conflicts_count=conflicts_count),
            "rows": sorted(rows, key=lambda r: -len(r["gaps"])),
            "total": sum(len(r["gaps"]) for r in rows),
            "current": ledger["current"],
            "causes": _CAUSE_WORDS,
            "coverage": _coverage(),
            "misattributed": wrong,
        },
    )


def _queue() -> dict[tuple[str, str, str], dict[str, Any]]:
    """Every standard held out of screening, addressed the way a link is.

    Keyed by (layer, zone, field) because that is what a row on the gaps page
    knows about itself and all a URL needs to carry.
    """
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for layer_id, layer in _layers().items():
        for want in layer.wanted:
            out[(layer_id, want.zone, want.field)] = {
                "layer": layer_id,
                "label": layer.label,
                "zone": want.zone,
                "field": want.field,
                "believed": want.value.value,
                "cite": want.cite,
                "url": want.url,
                "documents": [layer.document_path(doc.id) for doc in layer.code],
            }
    return out


def _candidates(item: dict[str, Any], limit: int = 60) -> tuple[list[dict[str, Any]], int]:
    """Lines in this jurisdiction's fetched code that could be the passage.

    The search itself is ``flats.encode.find`` — the same one the gaps ledger
    runs to decide whether a held-out standard is a chapter nobody fetched or a
    line nobody read. Sharing it is not tidiness: a page that ranked or matched
    differently from the ledger would send somebody to a hunt the ledger says
    is elsewhere, and the queue would stop meaning anything.

    What this adds is the page. A citation resolves to a line, and a line in a
    flattened table is a word; the printed sheet is where the columns and the
    footnote still are, so each candidate carries the page it sits on.
    """
    out: list[dict[str, Any]] = []
    dropped = 0
    for document in item["documents"]:
        found, more = passages(
            chr(10).join(_document_lines(document)),
            path=document,
            field=item["field"],
            believed=item["believed"],
            zone=item["zone"],
            limit=limit - len(out),
        )
        dropped += more
        for one in found:
            pages = _pages(document, one.line, one.line)
            out.append(
                {
                    "document": document,
                    "line": one.line,
                    "text": one.text,
                    "quote": one.quote,
                    "after": list(one.under),
                    "page": pages[0]["n"] if pages else 0,
                    "page_label": pages[0]["label"] if pages else "",
                }
            )
        if len(out) >= limit:
            break
    return out, dropped


@router.get("/flats/find/{layer_id:path}", response_class=HTMLResponse)
async def flats_find(
    request: Request,
    session: DBSession,
    layer_id: str,
    zone: str = Query(""),
    field: str = Query(""),
) -> HTMLResponse:
    """The hunt for one held-out standard, with the fetched code searched for it.

    The queue says a number has no passage behind it. This says where the
    passage might be: every line in the jurisdiction's own documents that
    prints that number, each with the page it sits on and the citation to
    paste. Where the answer is there, it is a minute's work; where it is not,
    that is the finding — the chapter stating it has never been fetched, and
    no amount of reading the ones that have will produce it.
    """
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    item = _queue().get((layer_id, zone, field))
    if item is None:
        return HTMLResponse("no such standard in the queue", status_code=404)
    candidates, dropped = _candidates(item)
    return templates.TemplateResponse(
        request,
        "flats_find.html",
        {
            **_base_ctx(user, dedup_count, "flats", conflicts_count=conflicts_count),
            "item": item,
            "candidates": candidates,
            "dropped": dropped,
        },
    )


@router.get("/flats/feedback", response_class=HTMLResponse)
async def flats_feedback(
    request: Request, session: DBSession, all: int = Query(0)
) -> HTMLResponse:
    """Everything a reviewer found wrong and has not yet handed on.

    Confirmations are not here. They travel a different road — the drain writes
    them into the repository's verification log — and mixing them in would bury
    the twelve items somebody has to act on under six hundred that need nothing.
    """
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    query = (
        select(FlatsRuleSignature)
        .where(FlatsRuleSignature.verdict.in_(("rejected", "unclear")))
        .order_by(FlatsRuleSignature.decided_at)
    )
    if not all:
        query = query.where(FlatsRuleSignature.bundled_at.is_(None))
    rows = list((await session.execute(query)).scalars())
    # Every problem ever raised, open or handed on: a fix lands after the batch
    # goes out, so the item to recheck is usually one the reviewer has already
    # cleared off the open list.
    raised = list(
        (
            await session.execute(
                select(FlatsRuleSignature)
                .where(FlatsRuleSignature.verdict.in_(("rejected", "unclear")))
                .order_by(FlatsRuleSignature.decided_at)
            )
        ).scalars()
    )
    # What somebody asked to be *done*, which is a different road from what
    # somebody found wrong, and until now had no road at all. Both scans are
    # cached in the process, so this is a page load, not a rebuild.
    ordered = await run_in_threadpool(
        reading_orders, _layers(), _store(), overrides=await _reading_inbox(session)
    )
    scanned = await run_in_threadpool(
        feed, store=_store(), ruled=True, overrides=await _inbox_rulings(session)
    )
    ordered_fetches = [c for c in scanned if c.outcome in CROSSREF_WORK]
    # Word rulings order work of a fourth kind, and the loudest of it: "this
    # city measures it differently" says numbers already in production were
    # read against the wrong thing.
    ordered_words = await run_in_threadpool(
        word_orders, overrides=await _word_inbox(session)
    )
    return templates.TemplateResponse(
        request,
        "flats_feedback.html",
        {
            **_base_ctx(user, dedup_count, "flats_handoff", conflicts_count=conflicts_count),
            "rows": rows,
            "answered": _answered(raised),
            "bundle": _bundle_text(rows),
            "ordered": ordered,
            "ordered_fetches": ordered_fetches,
            "ordered_words": ordered_words,
            "work": _work_text(ordered, ordered_fetches, ordered_words),
            "reading_work": READING_WORK,
            "crossref_work": CROSSREF_WORK,
            "word_work": WORD_WORK,
            "showing_all": bool(all),
        },
    )


@router.post("/ui/flats/bundle", response_class=HTMLResponse)
async def flats_bundle(request: Request, session: DBSession) -> HTMLResponse:
    """Mark the open feedback as handed on.

    Stamping rather than deleting. The item stays readable, and the stamp is
    what lets the next bundle be the next batch rather than the same one again.
    """
    await _get_user(session, request)
    rows = list(
        (
            await session.execute(
                select(FlatsRuleSignature).where(
                    FlatsRuleSignature.verdict.in_(("rejected", "unclear")),
                    FlatsRuleSignature.bundled_at.is_(None),
                )
            )
        ).scalars()
    )
    stamped = datetime.now(timezone.utc)
    for row in rows:
        row.bundled_at = stamped
    await session.commit()
    return templates.TemplateResponse(
        request,
        "partials/flats_bundled.html",
        {"count": len(rows)},
    )


# --- the chain of authority ---------------------------------------------


def _says(layer: Layer, zone: str, field: str) -> tuple[Any, str]:
    """What one layer states about a standard, and where it states it.

    Returns the value and whether it came from the zone's own block or from the
    layer's defaults. A layer that says nothing returns (None, "").
    """
    got = layer.zones.get(zone)
    if got and field in got.values:
        return got.values[field], "zone"
    if field in layer.defaults:
        return layer.defaults[field], "defaults"
    return None, ""


def _evidence(number: Any) -> dict[str, Any]:
    """One number and everything needed to check it against the book."""
    quote = number.prov.quote or ""
    lines, error = _cited_lines(quote) if quote else ([], "")
    return {
        "value": number.value,
        "when": ", ".join(getattr(number, "key", ()) or ()),
        "status": number.status.value,
        "reviewer": number.reviewer,
        "reviewed": number.reviewed,
        "cite": number.prov.cite,
        "url": number.prov.url,
        "quote": quote,
        "document": quote.partition("#L")[0],
        "pages": _pages_in(quote.partition("#L")[0], _ranges(quote)),
        "page_note": _page_note(quote),
        "lines": lines,
        "error": error,
    }


def _chain(layer_id: str, zone: str, field: str) -> dict[str, Any]:
    """Every layer that bears on one standard, and what each one does to it.

    The question this answers is not "what is the setback" — the rules table
    says that — but "why". A number in this system is the end of a chain:
    the state says middle housing must be allowed, the county's code sets a
    setback, the city's own code overrides it, and an exception in a third
    document moves it again for corner lots. Somebody defending an encoding to
    a planner, an architect or a lawyer has to be able to walk that chain, and
    to open each document at the page it is printed on.

    Silent layers are listed too. "The county says nothing about this" is part
    of the answer, and a page that showed only the winner would read as though
    nobody had looked.
    """
    rules = _ruleset()
    resolution = rules.resolve(layer_id, zone)
    resolved = resolution.values.get(field)
    steps: list[dict[str, Any]] = []
    for layer in rules.chain_for(layer_id):
        number, origin = _says(layer, zone, field)
        won = bool(resolved) and resolved.layer == layer.layer
        steps.append(
            {
                "layer": layer.layer,
                "label": layer.label,
                "kind": layer.kind,
                "origin": origin,
                "won": won,
                "silent": number is None,
                "preempts": bool(number is not None and getattr(number, "preempts", False)),
                "base": _evidence(number) if number is not None else None,
                "exceptions": [_evidence(v) for v in (number.variants if number else ())],
            }
        )
    return {
        "layer_id": layer_id,
        "zone": zone,
        "field": field,
        "answer": resolved,
        "steps": steps,
        "verdict": resolution.verdict.value,
        # Taken off the encoded exceptions rather than off the resolution's
        # levers. A lever is something a developer elects; a lot-size band is
        # something a lot simply is, and both change which number applies, so
        # both belong in the sentence that says what would change it.
        "conditions": sorted(
            {e["when"] for step in steps for e in step["exceptions"] if e["when"]}
        ),
    }


@router.get("/flats/why/{layer_id:path}", response_class=HTMLResponse)
async def flats_why(
    request: Request,
    session: DBSession,
    layer_id: str,
    zone: str = Query(...),
    field: str = Query(...),
) -> HTMLResponse:
    """Why this jurisdiction's answer for this standard is what it is.

    Built to be printed. The people who have to be convinced by it — a city
    planner across a counter, an architect sizing a building, a lawyer reading
    the same code off paper — are not going to be handed a login.
    """
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    layer = _layers().get(layer_id.strip("/"))
    if layer is None or field not in FIELDS:
        return templates.TemplateResponse(
            request,
            "flats_rules.html",
            {
                **_base_ctx(user, dedup_count, "flats", conflicts_count=conflicts_count),
                "summaries": [_layer_summary(x) for _, x in sorted(_layers().items())],
                "totals": {},
                "missing": f"{layer_id} {field}",
            },
            status_code=404,
        )
    number = _number(layer, zone, field, "")
    seen = (await _decisions(session, layer.layer)).get((zone, field, ""))
    stands = bool(number) and _stands(seen, _mark(layer.layer, zone, field, "", number))
    return templates.TemplateResponse(
        request,
        "flats_why.html",
        {
            **_base_ctx(user, dedup_count, "flats", conflicts_count=conflicts_count),
            "layer": _layer_summary(layer),
            "chain": _chain(layer.layer, zone, field),
            "decision": {
                "verdict": seen.verdict if stands else "",
                "by": seen.reviewer if stands else "",
                "pending": bool(
                    stands and seen.exported_at is None and seen.verdict in _NEEDS_NOTE
                ),
                "restated": bool(seen and not stands),
            },
            "asked": datetime.now(timezone.utc),
        },
    )


@router.get("/flats/review/{layer_id:path}", response_class=HTMLResponse)
async def flats_review(request: Request, session: DBSession, layer_id: str) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    layer = _layers().get(layer_id.strip("/"))
    if layer is None:
        return templates.TemplateResponse(
            request,
            "flats_rules.html",
            {
                **_base_ctx(user, dedup_count, "flats", conflicts_count=conflicts_count),
                "summaries": [_layer_summary(x) for _, x in sorted(_layers().items())],
                "totals": {},
                "missing": layer_id,
            },
            status_code=404,
        )
    decided = await _decisions(session, layer.layer)
    passages = _passages(layer, decided)
    return templates.TemplateResponse(
        request,
        "flats_review.html",
        {
            **_base_ctx(user, dedup_count, "flats", conflicts_count=conflicts_count),
            "layer": _layer_summary(layer),
            "passages": passages,
            "left": sum(len(p["rows"]) for p in passages),
            "reviewed": len(decided),
        },
    )


@router.post("/ui/flats/sign-passage", response_class=HTMLResponse)
async def flats_sign_passage(
    request: Request,
    session: DBSession,
    layer_id: str = Form(...),
    ref: str = Form(...),
    verdict: str = Form(...),
    note: str = Form(""),
) -> HTMLResponse:
    """Record one verdict over every number the displayed passage states.

    The command line refuses to glob field names, and is right to: signing
    what you did not display is how a signature comes to certify text nobody
    read. Here the passage *is* the display — the card shows the lines and
    every number claiming them — so a verdict over that set is a verdict over
    what was on screen. The set is rebuilt from the rules rather than sent by
    the browser, for the same reason the single-value route rebuilds the
    number: the form carries an address and an opinion, never the evidence.
    """
    user = await _get_user(session, request)
    layer = _layers().get(layer_id.strip("/"))
    if layer is None or verdict not in _VERDICTS:
        return templates.TemplateResponse(
            request,
            "partials/flats_passage_done.html",
            {"signed": 0, "error": "not a passage we hold", "verdict": ""},
            status_code=400,
        )

    if verdict in _NEEDS_NOTE and not note.strip():
        return templates.TemplateResponse(
            request,
            "partials/flats_passage_done.html",
            {
                "signed": 0,
                "verdict": "",
                "error": "say what is wrong with it — a bare rejection is not actionable",
            },
            status_code=400,
        )

    decided = await _decisions(session, layer.layer)
    # The card, rebuilt the way the page built it, and signed over exactly the
    # rows it listed. Deciding membership by containment in the card's line
    # range is not the same thing and was not safe: a citation may name two
    # stretches pages apart, the range covering both swallows every standard
    # printed in between, and "Confirm all" on a card showing one number came
    # to sign a hundred more that were never on screen.
    cards = [card for card in _passages(layer, decided) if card["ref"] == ref]
    if not cards:
        return templates.TemplateResponse(
            request,
            "partials/flats_passage_done.html",
            {
                "signed": 0,
                "verdict": "",
                "error": "that passage is not in the queue any more — reload the page",
            },
            status_code=409,
        )
    shown = _shown(ref)
    signed = 0
    for row in [row for card in cards for row in card["rows"]]:
        number = _number(layer, row["zone"], row["field"], row["when"])
        if number is None:
            continue
        session.add(
            FlatsRuleSignature(
                layer=layer.layer,
                zone=row["zone"],
                field=row["field"],
                when_key=row["when"],
                value=number.value,
                cite=number.prov.cite,
                quote=number.prov.quote or "",
                verdict=verdict,
                note=note[:2000],
                reviewer=(user.email or str(user.id))[:80],
                reviewer_user_id=user.id,
                shown=shown,
                shown_ref=ref,
                fingerprint=_mark(layer.layer, row["zone"], row["field"], row["when"], number),
            )
        )
        signed += 1
    await session.commit()
    return templates.TemplateResponse(
        request,
        "partials/flats_passage_done.html",
        {"signed": signed, "error": "", "verdict": verdict},
    )


# Registered above the /flats/{layer_id:path} catch-all below, which is not
# style: FastAPI matches routes in registration order, so the catch-all
# answers /flats/book/... itself and tries to load the document path as a
# jurisdiction, which is what a reviewer sees as the app inside the app.
# --- the source page itself ----------------------------------------------



# --------------------------------------------------------------------------
# Fetch triage
# --------------------------------------------------------------------------
#
# One review vertical, deliberately alone on its own page. The queue it works
# is references to chapters the store cannot open, and the only question it
# asks is whether the chapter can change a number this screen uses. Everything
# a reviewer needs to answer that is on the card; nothing else is.

#: The order the outcome buttons are offered in. Not alphabetical and not the
#: dict's order: the two that leave the row open lead, because a reviewer
#: reaching this page is looking for gaps and the rest are ways of saying "not
#: a gap". ``read`` is absent -- it is the legacy tag for rulings written
#: before the vocabulary and nothing new should be filed under it.
_TRIAGE_ORDER = (
    "fetch",
    "other_building",
    "other_path",
    "narrows_only",
    "preempted",
    "procedure",
    # Portland's Title 11: it reaches, it is full of numbers, and every one of
    # them discharges in cash. Sits after `procedure` because it is the same
    # answer one step further on -- not "no number in it", but "a number that
    # takes money instead of ground".
    "fee_in_lieu",
    "misread",
    "later",
)


async def _inbox_rulings(session: DBSession) -> dict[tuple[str, str], Ruling]:
    """The latest decision per reference from the review inbox.

    Rules load from the repository; this is what has been decided since and not
    yet drained into it. Applied over the rule files rather than merged with
    them, because a reviewer who changes their mind writes a new row and the
    newest is the one that counts.
    """
    rows = (
        await session.execute(
            select(FlatsCrossrefRuling).order_by(FlatsCrossrefRuling.decided_at)
        )
    ).scalars()
    return {(r.layer, r.ref): Ruling(r.note, r.outcome) for r in rows}


def _triage_ctx(
    rows: Sequence[Card],
    *,
    layer: str,
    field: str,
    doc: str,
    ruled: bool,
    skipped: int = 0,
    pending: int = 0,
    error: str = "",
    note: str = "",
) -> dict[str, Any]:
    layers = _layers()
    # Skipping walks the queue rather than reordering it: the card a reviewer
    # could not answer stays exactly where it was for whoever comes next, and
    # the offset lives in the URL so a reload does not silently rewind.
    ahead = rows[skipped:] if skipped < len(rows) else []
    return {
        "card": ahead[0] if ahead else None,
        "remaining": len(ahead),
        # The queue is still ranked on lots behind standards with slack; the
        # figure is no longer printed. A reviewer answering "can this chapter
        # change a number" was being handed a six-figure number they could do
        # nothing with, on every card.
        "min_note": MIN_RULING,
        # Over ``ahead`` and not ``rows``: it is printed directly under the
        # count of what is left, and two numbers side by side describing
        # different sets read as one number contradicting the other.
        "binding": sum(1 for c in ahead if c.binding),
        "outcomes": [(k, CROSSREF_OUTCOMES[k]) for k in _TRIAGE_ORDER],
        "jurisdictions": sorted(layers),
        "labels": {k: (v.label or k.rsplit("/", 1)[-1]) for k, v in layers.items()},
        "field_menu": fields_in(rows)[:14],
        "sel": {"layer": layer, "field": field, "doc": doc, "ruled": ruled},
        "error": error,
        "note": note,
        "pending": pending,
        "skipped": skipped,
    }


@router.get("/flats/triage", response_class=HTMLResponse)
async def flats_triage(
    request: Request,
    session: DBSession,
    layer: str = Query(""),
    field: str = Query(""),
    doc: str = Query(""),
    ruled: bool = Query(False),
    skipped: int = Query(0, ge=0),
) -> HTMLResponse:
    """The fetch-triage queue, worst first.

    Filters compose and are the whole point: "Gresham today", "setbacks
    everywhere", "I have this chapter open". A reviewer who cannot choose the
    shape of a session works whatever the queue puts in front of them, which
    over fourteen hundred rows means working Portland forever.
    """
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    overrides = await _inbox_rulings(session)
    rows = await run_in_threadpool(
        feed,
        layer=layer or None,
        field=field or None,
        doc=doc or None,
        ruled=ruled,
        overrides=overrides,
    )
    pending = await _pending_count(session)
    return templates.TemplateResponse(
        request,
        "flats_triage.html",
        {
            **_base_ctx(user, dedup_count, "flats_triage", conflicts_count=conflicts_count),
            **_triage_ctx(
                rows,
                layer=layer,
                field=field,
                doc=doc,
                ruled=ruled,
                skipped=skipped,
                pending=pending,
            ),
        },
    )


async def _pending_count(session: DBSession) -> int:
    """Decisions recorded and not yet written into the rule files.

    Surfaced rather than hidden. An undrained ruling has not taken effect —
    the screen still reads the chapter as unfetched — and a reviewer is
    entitled to know the difference between "decided" and "in force".
    """
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(FlatsCrossrefRuling)
                .where(FlatsCrossrefRuling.exported_at.is_(None))
            )
        ).scalar_one()
    )


@router.post("/ui/flats/triage/rule", response_class=HTMLResponse)
async def flats_triage_rule(
    request: Request,
    session: DBSession,
    layer_id: str = Form(...),
    ref: str = Form(...),
    outcome: str = Form(""),
    note: str = Form(""),
    action: str = Form("rule"),
    layer: str = Form(""),
    field: str = Form(""),
    doc: str = Form(""),
    ruled: bool = Form(False),
    skipped: int = Form(0),
) -> HTMLResponse:
    """Record one decision, or skip past it, and hand back the next card.

    Decisions land in the review inbox rather than in the rule files. The
    container rebuilds those files from git on every deploy, so a ruling
    spliced into a running container is gone at the next release; a row here
    survives, and the drain writes it into the repository for commit.

    The note is required and a refusal keeps what was typed. A tagged row with
    no reasoning is worse than an open one — the open row still shows the
    sentence, and the tagged row shows a word nobody can check.
    """
    user = await _get_user(session, request)

    async def render(error: str = "", keep: str = "", at: int = 0) -> HTMLResponse:
        overrides = await _inbox_rulings(session)
        rows = await run_in_threadpool(
            feed,
            layer=layer or None,
            field=field or None,
            doc=doc or None,
            ruled=ruled,
            overrides=overrides,
        )
        return templates.TemplateResponse(
            request,
            "partials/flats_triage_card.html",
            _triage_ctx(
                rows,
                layer=layer,
                field=field,
                doc=doc,
                ruled=ruled,
                skipped=at,
                pending=await _pending_count(session),
                error=error,
                note=keep,
            ),
            status_code=400 if error else 200,
        )

    # Skipping is a real answer to "I cannot rule on this yet" and needs to
    # cost nothing. It advances past the card without recording anything,
    # leaving it in place for whoever comes next.
    if action == "skip":
        return await render(at=skipped + 1)

    if outcome not in CROSSREF_OUTCOMES or outcome == "read":
        return await render("pick one of the outcomes", keep=note, at=skipped)
    tidy = " ".join(note.split())
    if len(tidy) < MIN_RULING:
        return await render(
            f"say why, in at least {MIN_RULING} characters — a tag on its own "
            f"is a row closed rather than answered",
            keep=note,
            at=skipped,
        )
    if layer_id.strip("/") not in _layers():
        return await render("not a jurisdiction we hold", keep=note, at=skipped)

    overrides = await _inbox_rulings(session)
    rows = await run_in_threadpool(
        feed, layer=layer_id.strip("/"), overrides=overrides, ruled=True
    )
    card = next((c for c in rows if c.ref == ref.strip()), None)

    session.add(
        FlatsCrossrefRuling(
            layer=layer_id.strip("/"),
            ref=ref.strip(),
            outcome=outcome,
            note=tidy,
            lots=card.lots if card else None,
            fields_touched=";".join(card.fields) if card else "",
            decided_by=getattr(user, "email", "") or "unknown",
        )
    )
    await session.commit()
    return await render(at=skipped)


@router.get("/flats/book/{document:path}", response_model=None)
async def flats_book(
    request: Request, session: DBSession, document: str
) -> FileResponse | HTMLResponse:
    """The PDF a document was read out of, so a browser can render its pages.

    Served from here rather than linked to the codifier for two reasons. A city
    web server is not a dependency a review session should have, and several of
    these books answer an ordinary browser request with a redirect chain or a
    rate limit. And the file served here is checked: its bytes hash to what the
    page map recorded, so page 239 is the page the map counted, not page 239 of
    a later edition that renumbered everything.
    """
    await _get_user(session, request)
    if document not in _known_documents():
        return HTMLResponse("no such stored document", status_code=404)
    try:
        # First view of a book is a twenty-megabyte download from a city web
        # server. Doing that on the event loop would stall every other request
        # in the worker behind one reviewer opening one page.
        path = await run_in_threadpool(books.ensure, _store(), document)
    except books.BookError as exc:
        return HTMLResponse(str(exc), status_code=409)
    return FileResponse(
        path,
        media_type="application/pdf",
        # inline, or the browser downloads it instead of rendering it in place.
        headers={
            "Content-Disposition": "inline",
            # The bytes are pinned to a hash, so a cached copy can never be the
            # wrong edition. Re-downloading 20 MB per card would make the
            # feature slower than the thing it replaces.
            "Cache-Control": "private, max-age=86400",
        },
    )


# --- reading queues ---------------------------------------------------------
#
# The uncited ledger counts every measured statement in a document we hold that
# no encoded value quotes: 4,693 rows, one per statement, grouped by city. It
# is the right ledger and an unworkable list, and for one reason -- the unit it
# prints is not the unit anybody decides in. One decision covers a section, and
# the same 4,693 lines are 649 sections.
#
# So these screens regroup by section and split by the question being asked.
# One queue, one question, one row of buttons. A reviewer opens a queue and
# knows what kind of reading the next hour is.


async def _reading_inbox(session: DBSession) -> dict[str, dict[str, Reading]]:
    """The latest reading decision per card, by layer, from the review inbox.

    Rules load from the repository; this is what has been decided since and not
    yet drained into it. Applied over the rule files rather than merged with
    them, because a reviewer who changes their mind writes a new row and the
    newest is the one that counts.
    """
    rows = (
        await session.execute(
            select(FlatsReadingRuling).order_by(FlatsReadingRuling.decided_at)
        )
    ).scalars()
    out: dict[str, dict[str, Reading]] = {}
    for r in rows:
        out.setdefault(r.layer, {})[card_key(r.path, r.section)] = Reading(
            queue=r.queue,
            outcome=r.outcome,
            note=r.note,
            fingerprint=r.fingerprint or "",
        )
    return out


async def _reading_pending(session: DBSession) -> int:
    """Decisions recorded and not yet written into the rule files.

    Surfaced rather than hidden. An undrained ruling has not taken effect, and
    a reviewer is entitled to know the difference between "decided" and "in
    force".
    """
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(FlatsReadingRuling)
                .where(FlatsReadingRuling.exported_at.is_(None))
            )
        ).scalar_one()
    )


def _reading_ctx(
    queue: str,
    rows: Sequence[ReadingCard],
    *,
    layer: str,
    field: str,
    ruled: bool,
    skipped: int = 0,
    pending: int = 0,
    error: str = "",
    note: str = "",
) -> dict[str, Any]:
    layers = _layers()
    # Skipping walks the queue rather than reordering it: the card a reviewer
    # could not answer stays exactly where it was for whoever comes next, and
    # the offset lives in the URL so a reload does not silently rewind.
    ahead = rows[skipped:] if skipped < len(rows) else []
    title, question = QUEUES[queue]
    # The document's own lines around the statements, fetched for the one card
    # on screen. A statement lifted out of a table is unreadable alone, and
    # putting that behind a link labelled with a line number meant nobody saw
    # it. One document read per page view; the store caches the file.
    around = reading_context(ahead[0], _store()) if ahead else ()
    fields: dict[str, int] = {}
    for card in rows:
        for name in card.fields:
            fields[name] = fields.get(name, 0) + 1
    return {
        "queue": queue,
        "queue_title": title,
        "queue_question": question,
        "card": ahead[0] if ahead else None,
        "around": around,
        "remaining": len(ahead),
        # The lines behind what is left, not behind the whole queue. Two
        # numbers side by side describing different sets read as one number
        # contradicting the other.
        "lines_ahead": sum(len(c.lines) for c in ahead),
        "min_note": MIN_RULING,
        "outcomes": list(READING_OUTCOMES[queue].items()),
        "jurisdictions": sorted(layers),
        "labels": {k: (v.label or k.rsplit("/", 1)[-1]) for k, v in layers.items()},
        "field_menu": sorted(fields.items(), key=lambda kv: (-kv[1], kv[0]))[:14],
        "sel": {"layer": layer, "field": field, "ruled": ruled},
        "error": error,
        "note": note,
        "pending": pending,
        "skipped": skipped,
    }


@router.get("/flats/reading", response_class=HTMLResponse)
async def flats_reading_index(request: Request, session: DBSession) -> HTMLResponse:
    """Pick a mode for the session.

    The landing page exists because the first decision of the day is not about
    a card, it is about what kind of reading to do. Four counts and four
    questions; everything else is one click away.
    """
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    tally = await run_in_threadpool(reading_counts)
    return templates.TemplateResponse(
        request,
        "flats_reading_index.html",
        {
            **_base_ctx(user, dedup_count, "flats_reading", conflicts_count=conflicts_count),
            "queues": [
                {
                    "key": kind,
                    "title": QUEUES[kind][0],
                    "question": QUEUES[kind][1],
                    "cards": tally[kind][0],
                    "lines": tally[kind][1],
                }
                for kind in KINDS
            ],
            "pending": await _reading_pending(session),
        },
    )


@router.get("/flats/reading/{queue}", response_class=HTMLResponse)
async def flats_reading(
    request: Request,
    session: DBSession,
    queue: str,
    layer: str = Query(""),
    field: str = Query(""),
    ruled: bool = Query(False),
    skipped: int = Query(0, ge=0),
) -> HTMLResponse:
    """One queue, worst first.

    Ranked by disagreement before consequence. Most cards confirm a figure we
    already hold and a handful print a different one; sorted by lots alone,
    Portland's bulk would bury every finding in the corpus.
    """
    if queue not in KINDS:
        return RedirectResponse("/flats/reading", status_code=303)
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    overrides = await _reading_inbox(session)
    rows = await run_in_threadpool(
        reading_feed,
        queue,
        layer=layer or None,
        field=field or None,
        ruled=ruled,
        overrides=overrides,
    )
    return templates.TemplateResponse(
        request,
        "flats_reading.html",
        {
            **_base_ctx(user, dedup_count, "flats_reading", conflicts_count=conflicts_count),
            **_reading_ctx(
                queue,
                rows,
                layer=layer,
                field=field,
                ruled=ruled,
                skipped=skipped,
                pending=await _reading_pending(session),
            ),
        },
    )


@router.post("/ui/flats/reading/rule", response_class=HTMLResponse)
async def flats_reading_rule(
    request: Request,
    session: DBSession,
    queue: str = Form(...),
    layer_id: str = Form(...),
    path: str = Form(...),
    section: str = Form(""),
    fingerprint: str = Form(""),
    outcome: str = Form(""),
    note: str = Form(""),
    action: str = Form("rule"),
    layer: str = Form(""),
    field: str = Form(""),
    ruled: bool = Form(False),
    skipped: int = Form(0),
) -> HTMLResponse:
    """Record one decision, or skip past it, and hand back the next card.

    Decisions land in the review inbox rather than in the rule files. The
    container rebuilds those files from git on every deploy, so a ruling
    spliced into a running container is gone at the next release; a row here
    survives, and the drain writes it into the repository for commit.

    The note is required and a refusal keeps what was typed. A tagged card with
    no reasoning is worse than an open one — the open one still shows the
    sentences, and the tagged one shows a word nobody can check.
    """
    user = await _get_user(session, request)

    async def render(error: str = "", keep: str = "", at: int = 0) -> HTMLResponse:
        overrides = await _reading_inbox(session)
        rows = await run_in_threadpool(
            reading_feed,
            queue if queue in KINDS else KINDS[0],
            layer=layer or None,
            field=field or None,
            ruled=ruled,
            overrides=overrides,
        )
        return templates.TemplateResponse(
            request,
            "partials/flats_reading_card.html",
            _reading_ctx(
                queue if queue in KINDS else KINDS[0],
                rows,
                layer=layer,
                field=field,
                ruled=ruled,
                skipped=at,
                pending=await _reading_pending(session),
                error=error,
                note=keep,
            ),
            status_code=400 if error else 200,
        )

    # Skipping is a real answer to "I cannot rule on this yet" and needs to
    # cost nothing. It advances past the card without recording anything,
    # leaving it in place for whoever comes next.
    if action == "skip":
        return await render(at=skipped + 1)

    if queue not in KINDS:
        return await render("that queue does not exist", keep=note, at=skipped)
    if outcome not in READING_OUTCOMES[queue]:
        return await render(
            "pick one of the answers this queue asks for", keep=note, at=skipped
        )
    if len(" ".join(note.split())) < MIN_RULING:
        return await render(
            f"say why, in at least {MIN_RULING} characters — a card closed with "
            f"a word nobody can check is worse than an open one",
            keep=note,
            at=skipped,
        )
    if layer_id not in _layers():
        return await render("that is not a jurisdiction we hold", keep=note, at=skipped)

    session.add(
        FlatsReadingRuling(
            layer=layer_id,
            path=path,
            section=section,
            queue=queue,
            outcome=outcome,
            note=" ".join(note.split()),
            fingerprint=fingerprint,
            decided_by=getattr(user, "email", "") or "unknown",
        )
    )
    await session.commit()
    return await render(at=skipped)


# --- word review -------------------------------------------------------------
#
# The queue underneath signing. Signing asks whether a number matches the
# sentence it was taken from; this asks whether the sentence measures what we
# think it measures. Four cities in this corpus give four incompatible tests
# for "corner lot" and seven subtract seven different lists from a "net acre",
# so a number read perfectly can still be the wrong number -- and finding that
# out after three hundred signatures means signing some of them again.


async def _word_inbox(session: DBSession) -> dict[str, dict[str, Reading]]:
    """The latest word decision per card, by layer, from the review inbox.

    Rules load from the repository; this is what has been decided since and not
    yet drained into it. ``Reading`` is reused rather than a third model being
    invented for it: the shape a word ruling needs is exactly what queue asked,
    what was answered, why, and against what text.
    """
    rows = (
        await session.execute(
            select(FlatsWordRuling).order_by(FlatsWordRuling.decided_at)
        )
    ).scalars()
    out: dict[str, dict[str, Reading]] = {}
    for r in rows:
        out.setdefault(r.layer, {})[r.term] = Reading(
            queue=r.standing,
            outcome=r.outcome,
            note=r.note,
            fingerprint=r.fingerprint or "",
        )
    return out


async def _word_pending(session: DBSession) -> int:
    """Word decisions recorded and not yet written into the rule files."""
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(FlatsWordRuling)
                .where(FlatsWordRuling.exported_at.is_(None))
            )
        ).scalar_one()
    )


def _word_ctx(
    queue: str,
    rows: Sequence[WordCard],
    *,
    layer: str,
    field: str,
    ruled: bool,
    skipped: int = 0,
    pending: int = 0,
    error: str = "",
    note: str = "",
) -> dict[str, Any]:
    layers = _layers()
    ahead = rows[skipped:] if skipped < len(rows) else []
    title, question = WORD_QUEUES[queue]
    fields: dict[str, int] = {}
    for card in rows:
        for name in card.fields:
            fields[name] = fields.get(name, 0) + 1
    return {
        "queue": queue,
        "queue_title": title,
        "queue_question": question,
        "card": ahead[0] if ahead else None,
        "remaining": len(ahead),
        # The numbers behind what is *left*, not behind the whole queue. Two
        # counts side by side describing different sets read as one number
        # contradicting the other.
        "values_ahead": sum(c.values for c in ahead),
        "min_note": MIN_RULING,
        "outcomes": list(WORD_OUTCOMES[queue].items()),
        "jurisdictions": sorted(layers),
        "labels": {k: (v.label or k.rsplit("/", 1)[-1]) for k, v in layers.items()},
        "field_menu": sorted(fields.items(), key=lambda kv: (-kv[1], kv[0]))[:14],
        "sel": {"layer": layer, "field": field, "ruled": ruled},
        "error": error,
        "note": note,
        "pending": pending,
        "skipped": skipped,
    }


@router.get("/flats/words", response_class=HTMLResponse)
async def flats_words_index(request: Request, session: DBSession) -> HTMLResponse:
    """Pick a standing for the session.

    Three, and they are three different jobs — go and fetch a book nobody has
    opened, decide what a silent code lets us assume, compare a definition to
    how we measure. Mixing them is the tax the verticals design exists to
    avoid.
    """
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    overrides = await _word_inbox(session)
    tally = await run_in_threadpool(word_tally, overrides=overrides)
    return templates.TemplateResponse(
        request,
        "flats_words_index.html",
        {
            **_base_ctx(user, dedup_count, "flats_words", conflicts_count=conflicts_count),
            "standings": [
                {
                    "key": kind,
                    "title": WORD_QUEUES[kind][0],
                    "question": WORD_QUEUES[kind][1],
                    "cards": tally[kind][0],
                    # Not "values". Jinja resolves an attribute before a key, so
                    # a dict with a "values" key renders dict.values -- the bound
                    # method, printed as "<built-in method values ...>".
                    "numbers": tally[kind][1],
                }
                for kind in WORD_STANDINGS
            ],
            "pending": await _word_pending(session),
        },
    )


@router.get("/flats/words/{queue}", response_class=HTMLResponse)
async def flats_words(
    request: Request,
    session: DBSession,
    queue: str,
    layer: str = Query(""),
    field: str = Query(""),
    ruled: bool = Query(False),
    skipped: int = Query(0, ge=0),
) -> HTMLResponse:
    """One standing, heaviest first.

    Ranked by the numbers resting on the word here, then by lots. Consequence
    is the sort and never a filter — a small city's word is still wrong if it
    is wrong.
    """
    if queue not in WORD_STANDINGS:
        return RedirectResponse("/flats/words", status_code=303)
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    overrides = await _word_inbox(session)
    rows = await run_in_threadpool(
        word_feed,
        queue,
        layer=layer or None,
        field=field or None,
        ruled=ruled,
        overrides=overrides,
    )
    return templates.TemplateResponse(
        request,
        "flats_words.html",
        {
            **_base_ctx(user, dedup_count, "flats_words", conflicts_count=conflicts_count),
            **_word_ctx(
                queue,
                rows,
                layer=layer,
                field=field,
                ruled=ruled,
                skipped=skipped,
                pending=await _word_pending(session),
            ),
        },
    )


@router.post("/ui/flats/words/rule", response_class=HTMLResponse)
async def flats_words_rule(
    request: Request,
    session: DBSession,
    queue: str = Form(...),
    layer_id: str = Form(...),
    term: str = Form(...),
    fingerprint: str = Form(""),
    outcome: str = Form(""),
    note: str = Form(""),
    action: str = Form("rule"),
    values_touched: int = Form(0),
    lots: int = Form(0),
    fields_touched: str = Form(""),
    layer: str = Form(""),
    field: str = Form(""),
    ruled: bool = Form(False),
    skipped: int = Form(0),
) -> HTMLResponse:
    """Record one decision about a word, or skip past it, and hand back the next.

    Decisions land in the review inbox rather than in the rule files, because
    the container rebuilds those from git on every deploy and a ruling spliced
    into a running container would be gone at the next release.

    The outcome is checked against the standing that asked, not against the
    whole vocabulary. "Nobody has read this city's definitions" is not an
    answer to a word the city plainly defines, and a screen that accepts it
    silently records a decision nobody made.
    """
    user = await _get_user(session, request)

    async def render(error: str = "", keep: str = "", at: int = 0) -> HTMLResponse:
        overrides = await _word_inbox(session)
        rows = await run_in_threadpool(
            word_feed,
            queue if queue in WORD_STANDINGS else WORD_STANDINGS[0],
            layer=layer or None,
            field=field or None,
            ruled=ruled,
            overrides=overrides,
        )
        return templates.TemplateResponse(
            request,
            "partials/flats_word_card.html",
            _word_ctx(
                queue if queue in WORD_STANDINGS else WORD_STANDINGS[0],
                rows,
                layer=layer,
                field=field,
                ruled=ruled,
                skipped=at,
                pending=await _word_pending(session),
                error=error,
                note=keep,
            ),
            status_code=400 if error else 200,
        )

    if action == "skip":
        return await render(at=skipped + 1)

    if queue not in WORD_STANDINGS:
        return await render("that queue does not exist", keep=note, at=skipped)
    if outcome not in WORD_OUTCOMES[queue]:
        return await render(
            "pick one of the answers this queue asks for", keep=note, at=skipped
        )
    if len(" ".join(note.split())) < MIN_RULING:
        return await render(
            f"say why, in at least {MIN_RULING} characters — a word closed with "
            f"a word nobody can check is worse than an open one",
            keep=note,
            at=skipped,
        )
    if layer_id not in _layers():
        return await render("that is not a jurisdiction we hold", keep=note, at=skipped)

    session.add(
        FlatsWordRuling(
            layer=layer_id,
            term=term,
            standing=queue,
            outcome=outcome,
            note=" ".join(note.split()),
            fingerprint=fingerprint,
            lots=lots,
            values_touched=values_touched,
            fields_touched=fields_touched,
            decided_by=getattr(user, "email", "") or "unknown",
        )
    )
    await session.commit()
    return await render(at=skipped)


@router.get("/flats/{layer_id:path}", response_class=HTMLResponse)
async def flats_layer(request: Request, session: DBSession, layer_id: str) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    layer = _layers().get(layer_id.strip("/"))
    if layer is None:
        return templates.TemplateResponse(
            request,
            "flats_rules.html",
            {
                **_base_ctx(user, dedup_count, "flats", conflicts_count=conflicts_count),
                "summaries": [_layer_summary(x) for _, x in sorted(_layers().items())],
                "totals": {},
                "missing": layer_id,
            },
            status_code=404,
        )
    decided = await _decisions(session, layer.layer)
    rows = _value_rows(layer)
    for row in rows:
        seen = decided.get((row["zone"], row["field"], row["when"]))
        stands = _stands(seen, row["mark"])
        row["decision"] = seen.verdict if stands else ""
        row["decided_by"] = seen.reviewer if stands else ""
        row["pending"] = bool(stands and seen.exported_at is None)
        row["restated"] = bool(seen and not stands)
    return templates.TemplateResponse(
        request,
        "flats_layer.html",
        {
            **_base_ctx(user, dedup_count, "flats", conflicts_count=conflicts_count),
            "layer": _layer_summary(layer),
            "notes": layer.notes,
            "documents": [
                {"url": doc.url, "title": doc.title, "id": doc.id} for doc in layer.code
            ],
            "rows": rows,
        },
    )


def _shown(ref: str) -> str:
    """The code text a card displayed, rebuilt from its citation.

    Rebuilt rather than posted back, for the same reason the number is: what
    the browser sends is an address and an opinion, and evidence that arrives
    from the browser is evidence somebody could have written. Stored verbatim
    so a note stays readable months later, by someone who was not there, after
    the document has been re-fetched and every line in it has moved.

    Every range the citation names, each with its own context -- the same
    rendering :func:`_cited_lines` gives the card. This used to take the hull
    from :func:`_span` and draw one window across it, which is the thing the
    :func:`_ranges` docstring warns about in as many words: for Wilsonville's
    ``#L572-L574,L8314,L8318`` the hull is seven thousand seven hundred lines,
    six of them cited. So the column that exists to say "this is what the
    reviewer was looking at" held most of a municipal code, and a reader
    checking a signature months later would have had to find the six lines
    themselves -- which is the work the column was recording them to save.

    It also put text on screen that no card ever showed. That is how this
    surfaced: seven thousand unread lines of Wilsonville swept up two glyphs
    pypdf could not decode, and Postgres refuses a NUL byte inside text, so
    signing those two cards failed outright with an encoding error naming a
    roofing-materials table nobody had cited.
    """
    return "\n".join(
        f"{line['n']:>6}  {line['text']}" for line in _cited_lines(ref)[0]
    )


def _mark(layer_id: str, zone: str, field: str, when: str, number: Any) -> str:
    """The fingerprint of exactly what a reviewer was looking at.

    The conditions come off the number itself, never off the address. A band
    token is "lot_sqft:>10000+", so the "+" that joins a key into an address
    also occurs inside one, and splitting it back apart does not always return
    what went in. Rebuilding a fingerprint from a lossy round trip would make a
    verdict stop matching the value it was just recorded against — the item
    would resurface as changed the moment it was signed.
    """
    return fingerprint(
        layer_id,
        zone,
        field,
        number.value,
        cite=number.prov.cite,
        quote=number.prov.quote,
        when=getattr(number, "key", ()),
    )


@router.post("/ui/flats/sign", response_class=HTMLResponse)
async def flats_sign(
    request: Request,
    session: DBSession,
    layer_id: str = Form(...),
    zone: str = Form(...),
    field: str = Form(...),
    when: str = Form(""),
    verdict: str = Form(...),
    note: str = Form(""),
    ref: str = Form(""),
    shape: str = Form(""),
    anchor: str = Form(""),
) -> HTMLResponse:
    """Record what a reviewer decided about one number, and why.

    The value, citation, quote and the code text that was on screen are all
    read from the server's own copies rather than from the form. What the
    browser sends is an address and an opinion; if it could send the evidence
    as well, a signature could be recorded over text nobody displayed.
    """
    user = await _get_user(session, request)
    layer = _layers().get(layer_id.strip("/"))
    number = _number(layer, zone, field, when) if layer else None

    def refused(why: str, *, keep: str = "") -> HTMLResponse:
        """The same refusal in whichever shape asked for it.

        The bar hands back the note the reviewer was in the middle of writing.
        Losing it is how a reviewer learns to click Confirm instead.
        """
        if shape == "bar":
            return templates.TemplateResponse(
                request,
                "partials/flats_verdict_bar.html",
                {
                    "chain": {"layer_id": layer_id.strip("/"), "zone": zone, "field": field},
                    "decision": {"verdict": "", "by": "", "pending": False, "restated": False},
                    "error": why,
                    "note": keep,
                    "note_open": verdict in _NEEDS_NOTE,
                },
                status_code=400,
            )
        if shape == "row":
            # The row hands back the whole control, not a verdict badge. A
            # refusal that swapped in a one-line message would take the note
            # box away at the moment the reviewer is being told to write one.
            return templates.TemplateResponse(
                request,
                "partials/flats_row_verdict.html",
                {
                    "chain": {
                        "layer_id": layer_id.strip("/"),
                        "zone": zone,
                        "field": field,
                        "when": when,
                        "anchor": anchor,
                    },
                    "row": {"decision": "", "pending": False},
                    "error": why,
                    "note": keep,
                    "note_open": verdict in _NEEDS_NOTE,
                },
                status_code=400,
            )
        return templates.TemplateResponse(
            request,
            "partials/flats_decision.html",
            {"row": {"decision": "", "pending": False}, "error": why},
            status_code=400,
        )

    if number is None or verdict not in _VERDICTS:
        return refused("not a value we hold")
    if verdict in _NEEDS_NOTE and not note.strip():
        return refused(
            "say what is wrong with it — a bare rejection is not actionable", keep=note
        )

    session.add(
        FlatsRuleSignature(
            layer=layer.layer,
            zone=zone,
            field=field,
            when_key=when,
            value=number.value,
            cite=number.prov.cite,
            quote=number.prov.quote or "",
            verdict=verdict,
            note=note[:2000],
            reviewer=(user.email or str(user.id))[:80],
            reviewer_user_id=user.id,
            shown=_shown(ref or number.prov.quote or ""),
            shown_ref=ref or number.prov.quote or "",
            fingerprint=_mark(layer.layer, zone, field, when, number),
        )
    )
    await session.commit()
    if shape == "bar":
        return templates.TemplateResponse(
            request,
            "partials/flats_verdict_bar.html",
            {
                "chain": {"layer_id": layer.layer, "zone": zone, "field": field},
                "decision": {
                    "verdict": verdict,
                    "by": user.email,
                    "pending": verdict in _NEEDS_NOTE,
                    "restated": False,
                },
                "error": "",
                "note": "",
                "said": _SAID.get(verdict, ""),
            },
        )
    if shape == "row":
        return templates.TemplateResponse(
            request,
            "partials/flats_row_verdict.html",
            {
                "chain": {
                    "layer_id": layer.layer,
                    "zone": zone,
                    "field": field,
                    "when": when,
                    "anchor": anchor,
                },
                "row": {"decision": verdict, "pending": True},
                "error": "",
                "note": "",
                "said": _SAID.get(verdict, ""),
            },
        )
    return templates.TemplateResponse(
        request,
        "partials/flats_decision.html",
        {
            "row": {
                "decision": verdict,
                "decided_by": user.email,
                "pending": True,
                "zone": zone,
                "field": field,
                "when": when,
            },
            "layer_id": layer.layer,
            "error": "",
        },
    )


def _cited_lines(ref: str) -> tuple[list[dict[str, Any]], str]:
    """The stored text a citation points at, with a few lines either side.

    The surrounding lines are the point. A setback read off a table row means
    one thing under the heading above it and another under the footnote below,
    and a reviewer shown the row alone cannot tell which.

    Returns the lines and an error message; never both.
    """
    store = _store()
    path = ref.partition("#L")[0]
    if path not in _known_documents():
        return [], "no such stored document"

    # Every range the citation names, each with its own context, rather than
    # one window covering the lot. Parsed on "," first: splitting only on "-"
    # raised on int("875,4408") and reported the citation as unresolvable,
    # which is what a reviewer saw on every citation naming three stretches.
    spans = _ranges(ref)
    try:
        whole = store.load(path).text.splitlines()
        quoted = "" if spans else store.quote(ref)
    except (ProvenanceError, ValueError, OSError):
        # The reason is not shown: the reference is user-supplied, and an
        # error carrying a filesystem path back to the browser answers
        # questions about the server that a review page has no business
        # answering.
        return [], "this citation does not resolve to stored text"

    if not spans:
        return [_line(0, quoted, True)], ""

    wanted: set[int] = set()
    for first, last in spans:
        wanted.update(range(max(first - _CONTEXT, 1), min(last + _CONTEXT, len(whole)) + 1))
    # The line numbers jump where a stretch was skipped, which is the honest
    # rendering: the reader can see that what is between them was not cited.
    return [
        _line(n, whole[n - 1], any(a <= n <= b for a, b in spans))
        for n in sorted(wanted)
    ], ""


@router.get("/ui/flats/book", response_class=HTMLResponse)
async def flats_book_view(
    request: Request,
    session: DBSession,
    ref: str = Query(...),
    page: int = Query(1),
) -> HTMLResponse:
    """The embedded viewer for one citation, swapped in when a reviewer asks.

    On demand rather than on load: a review queue is twenty-five cards, and
    twenty-five embedded books is forty megabytes nobody asked for.
    """
    await _get_user(session, request)
    document = ref.partition("#L")[0]
    if document not in _known_documents():
        return HTMLResponse("", status_code=404)
    index = page_map.read(_store(), document)
    return templates.TemplateResponse(
        request,
        "partials/flats_book.html",
        {
            "document": document,
            "page": page,
            "pages": len(index.pages) if index else 0,
            "url": _store().load(document).url,
        },
    )


@router.get("/ui/flats/quote", response_class=HTMLResponse)
async def flats_quote(request: Request, ref: str = Query(...)) -> HTMLResponse:
    """One citation's stored text, fetched on demand from the rules table."""
    lines, error = _cited_lines(ref)
    return templates.TemplateResponse(
        request,
        "partials/flats_quote.html",
        {
            "ref": ref,
            "error": error,
            "lines": lines,
            "path": ref.partition("#L")[0],
        },
    )
