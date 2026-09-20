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

import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Sequence
from urllib.parse import quote

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import case, func, or_, select
from starlette.concurrency import run_in_threadpool

from app.api.deps import DBSession
from app.config import settings
from app.api.routers.ui_helpers import _base_ctx, _get_counts, _get_user, templates
from app.models.flats import (
    FlatsCrossrefRuling,
    FlatsLot,
    FlatsLotResult,
    FlatsReadingRuling,
    FlatsReviewDecision,
    FlatsRuleSignature,
    FlatsRun,
    FlatsSnapshot,
    FlatsWordRuling,
)
from app.services import flats_refresh as refresh_service
from app.services.flats_refresh import refresh_notices
from flats.encode import legible
from flats.designs.model import Design, DesignStatus, Plat, load_catalog
from flats.encode.attribution import claimed_sections, section_at
from flats.encode.find import passages
from flats.encode.gaps import digest as gaps_digest
from flats.encode.gaps import read_ledger
from flats.encode.load import load_trusted
from flats.encode.triage import Card, feed, fields_in, unscreened
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
                    # Shown beside the depth rather than folded silently into
                    # it: a 118 ft answer for a 36 ft building is startling
                    # until you can see that 42 ft of it is where the cars go.
                    "court": fit.parking_depth_ft,
                    # And beside the width, the same courtesy: 64 ft for a
                    # 36 ft end of building is the six stalls behind it, or
                    # the lane down its flank, and the row says which.
                    "court_width": fit.parking_width_ft,
                    "lane": fit.lane_ft,
                    "stalls": fit.stalls,
                    "width_binding": fit.width_binding,
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
                    # A stall minimum above the design's floor is not a no —
                    # the paper lot already charges the raised count (that is
                    # `fit.stalls`); this is how many the law added.
                    "stalls_raised": (
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
        # The floor the screen charges, and the two bands above it that are
        # reported beside the colour rather than asked of any lot.
        "stalls": design.stalls_required,
        "stalls_target": design.stalls_target,
        "stalls_preferred": design.stalls_preferred,
        # The design's own court, before any city raises it. Named on the page
        # because every depth in the table below now carries it -- and broken
        # into its three pieces, because 47 ft is not a number anyone can
        # check against a car until it reads as 5 off the wall, 18 of stall
        # and 24 of aisle.
        "court": design.parking.court_depth_ft,
        "gap": design.parking.building_gap_ft,
        "stall_depth": design.parking.stall_depth_ft,
        "aisle": design.parking.aisle_ft,
        "court_width": design.court_width_ft,
        "lane": design.parking.lane_width_ft,
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
        # Which of these cards are for land the screen does not cover. This
        # queue keeps switched-off cities on purpose -- it ranks on lots at
        # stake and re-ranking by a second invisible criterion is how a queue
        # stops being explainable -- so the card has to say it. The terminal
        # has said it since the queue was built and this screen did not, which
        # is 156 of 737 cards and nine of the first twenty-five reading exactly
        # like work. Same list the terminal uses.
        "unscreened": unscreened(_layers()),
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


# --- lots: what the screen said about each one -------------------------
#
# The county run lands in ``flats.lots`` / ``flats.lot_results`` and until
# these two pages nothing read it: 289,845 lots and their verdicts, visible
# only through psql. The list counts by colour and filters by city, zone and
# colour; the lot page shows one lot, the facts the screen read off it, and
# what each building design was told -- the verdict first, and the colour it
# would take once the rules are signed beside it, never in its place (the
# 2026-09-17 ruling). Read-only: a ruling on a lot is a ruling on the code
# that produced it, and those live on the signing pages.

#: The colours in the order a lot is best described by them. A lot with one
#: green design and one red is a green lot -- the buyer picks the design --
#: so "either design" takes the lowest rank across the run's designs, the
#: same choice ``flats.ingest.quadfit.per_lot`` makes.
_COLOURS = ("green", "yellow", "unknown", "red")

#: What each colour means, said once and reused on both pages.
_COLOUR_WORDS = {
    "green": "clears every standard we hold",
    "yellow": "clears, with an exception to ask the city for",
    "unknown": "cannot be told yet",
    "red": "misses a standard no exception covers",
}

#: What the verdict the screen actually gave means. Today it is "unknown" on
#: every lot because no rule is signed; the colour beside it is the answer
#: *if* the rules it rests on are confirmed as read.
_VERDICT_WORDS = {
    "unknown": "cannot be told yet — the rules behind it are not signed",
    "green": "clears every signed standard",
    "yellow": "clears, with an exception to ask for",
    "red": "misses a signed standard",
}

#: Reason codes, said to somebody who will not open ``flats/score/screen.py``.
_REASON_WORDS = {
    "RULE_UNVERIFIED": "a rule this rests on has not been signed",
    "RELIEF_UNCONFIRMED": "the exception it would ask for has not been read",
    "FACT_UNOBSERVED": "a fact about the site nothing has measured decides which number applies",
    "FACT_ASSUMED": "a fact about the site was assumed rather than measured",
    "GEOMETRY_UNREADABLE": "the lot's outline could not be read",
    "NO_FRONTAGE": "no street frontage was found",
    "STANDARD_NOT_ENCODED": "a standard the zone states is not encoded",
    "USE_NOT_ENCODED": "whether the zone allows a fourplex is not encoded",
    "USE_PROHIBITED": "the zone forbids the use outright",
    "COURT_WIDTH_UNMEASURED": "the fit was searched without the parking court's width",
    # The county copy's own reasons (flats.ingest.normalize gates and the
    # assign stage): why a lot on the map was never screened.
    "JURISDICTION_NOT_ENCODED": "the city this lot is in has no encoded rules",
    "JURISDICTION_OFF": "the city this lot is in is switched off",
    "OUTSIDE_UGB": "outside the urban growth boundary",
    "NO_ZONE": "no zoning polygon covers this lot",
    "ZONE_NOT_ENCODED": "the zone code on the map is one nobody has ruled on yet",
    "ZONE_POCKET": "the zone code on the map is another jurisdiction's zoning inside this one's line",
    "ZONE_UNENCODABLE": "the zone was read; it asks a measurement the screen cannot take",
    "ZONE_TO_READ": "the zone was seen on the map; its chapter is not encoded yet (use table unread, or use permitted and dimensions unread)",
    "ZONE_REFERENCE_MISSING": "the zone points at a zone the rules do not hold",
    "ZONE_REFERENCE_CYCLE": "the zone's references loop",
    "RULE_AMBIGUOUS": "two readings of a rule this rests on disagree",
    "NOT_MEASURED": "the county map's measurement never reached this lot",
    "quadfit:sliver_area": "the county map's measurement skipped it: under 1,000 sq ft",
    "quadfit:too_narrow_20ft": "the county map's measurement skipped it: under 20 ft wide",
    "quadfit:zone_quadplex_not_allowed": "the county map's measurement skipped it: its rules say the zone does not allow a fourplex",
    "quadfit:zone_not_in_rules": "the county map's measurement skipped it: the zone is not in its rules",
    "quadfit:no_zone_assigned": "the county map's measurement skipped it: no zone was assigned",
    "quadfit:outside_ugb": "the county map's measurement skipped it: outside the growth boundary",
    "quadfit:jurisdiction_unmapped": "the county map's measurement skipped it: the city is not mapped",
    "quadfit:jurisdiction_ineligible_no_rules": "the county map's measurement skipped it: the city has no rules there",
    "quadfit:condo_stack": "the county map's measurement skipped it: a condo stack",
    "quadfit:not_a_taxlot": "the county map's measurement skipped it: not a taxlot",
    "quadfit:unknown": "the county map's measurement did not reach it and no step claims it",
}

#: The badge class each colour wears.
_BADGE = {"green": "badge-green", "yellow": "badge-yellow", "unknown": "badge-gray", "red": "badge-red"}

#: Lots per page of the list. Fifty rows is one screen with the filters
#: still in view; the counts above the table are what say how many there are.
_LOTS_PAGE = 50

#: Pixels across the lot outline drawn on the lot page.
_OUTLINE_PX = 260


def _said_reason(code: str) -> str:
    if code in _REASON_WORDS:
        return _REASON_WORDS[code]
    if code.startswith("quadfit:"):
        return f"the county map's measurement skipped it: {code[8:].replace('_', ' ')}"
    return code.replace("_", " ").lower()


def _city_label(jurisdiction: str) -> str:
    layer = _layers().get(jurisdiction)
    if layer is not None:
        return layer.label
    if jurisdiction.startswith("juris_city:"):
        # A lot in a city the rules do not hold: the loader keeps the county
        # map's city name behind this prefix (scripts/flats_load_bridge.py).
        return f"{jurisdiction[len('juris_city:'):].replace('_', ' ').title()} (no rules encoded)"
    return jurisdiction


def _lot_href(county: str, tlid: str) -> str:
    return f"/flats/lots/{county}/{quote(tlid, safe='')}"


#: Runs the Lots pages will show. A candidate is a refresh loaded beside the
#: copy in use and not yet promoted: reachable by ``?run=``, never the default.
_SHOWN_RUN_STATUSES = ("complete", "candidate")


async def _runs(session: DBSession) -> list[FlatsRun]:
    """Completed and candidate runs, newest first. The list and the lot page
    read one run; another is reachable by ``?run=`` so two can be compared."""
    stmt = (
        select(FlatsRun)
        .where(FlatsRun.status.in_(_SHOWN_RUN_STATUSES))
        .order_by(FlatsRun.id.desc())
    )
    return list((await session.execute(stmt)).scalars())


def _default_run(runs: list[FlatsRun]) -> FlatsRun | None:
    """The newest complete run; a candidate is never shown unasked."""
    return next((r for r in runs if r.status == "complete"), None)


def _chosen_run(runs: list[FlatsRun], run: int | None) -> FlatsRun | None:
    if run:
        return next((r for r in runs if r.id == run), None)
    return _default_run(runs)


async def _refresh(session: DBSession) -> dict[str, Any]:
    """The county-copy banner: warnings computed from rows, and the footer."""
    found = await refresh_notices(session)
    return {
        "level": found.level,
        "notices": [{"level": n.level, "code": n.code, "text": n.text} for n in found.notices],
        "footer": found.footer,
    }


def _rank(column: Any) -> Any:
    """0..3 for the four colours in ``_COLOURS`` order, 4 for anything else."""
    return case(*[(column == c, i) for i, c in enumerate(_COLOURS)], else_=len(_COLOURS))


def _best(run_id: int, design: str | None) -> Any:
    """One row per lot: the lowest verdict rank and the lowest signed-colour
    rank across the run's designs (or the one design asked for)."""
    result = FlatsLotResult
    colour = result.checks["if_signed"].astext
    stmt = select(
        result.lot_id.label("lot_id"),
        func.min(_rank(result.tier)).label("verdict"),
        func.min(_rank(colour)).label("colour"),
    ).where(result.run_id == run_id)
    if design:
        stmt = stmt.where(result.design_key == design)
    return stmt.group_by(result.lot_id).subquery("best")


def _lot_conditions(jurisdiction: str, zone: str, q: str) -> list[Any]:
    lot = FlatsLot
    conditions: list[Any] = []
    if jurisdiction:
        conditions.append(lot.jurisdiction == jurisdiction)
    if zone:
        conditions.append(lot.zone == zone)
    if q.strip():
        like = f"%{q.strip()}%"
        conditions.append(or_(lot.tlid.ilike(like), lot.site_address.ilike(like)))
    return conditions


async def _lot_counts(
    session: DBSession, run_id: int, design: str | None, conditions: list[Any]
) -> dict[str, dict[str, int]]:
    """How many lots wear each verdict and each signed colour under the filter."""
    best = _best(run_id, design)
    stmt = (
        select(best.c.verdict, best.c.colour, func.count())
        .select_from(FlatsLot)
        .join(best, best.c.lot_id == FlatsLot.id)
        .where(*conditions)
        .group_by(best.c.verdict, best.c.colour)
    )
    verdicts = {c: 0 for c in _COLOURS}
    colours = {c: 0 for c in _COLOURS}
    for verdict, colour, n in (await session.execute(stmt)).all():
        if 0 <= verdict < len(_COLOURS):
            verdicts[_COLOURS[verdict]] += n
        if 0 <= colour < len(_COLOURS):
            colours[_COLOURS[colour]] += n
    return {"verdict": verdicts, "if_signed": colours, "lots": sum(colours.values())}


def _result_card(row: FlatsLotResult) -> dict[str, Any]:
    """One design's answer on one lot, flattened for the template. The verdict
    is the first key and the signed colour the second, on purpose."""
    checks = row.checks or {}
    stalls = checks.get("stalls") or {}
    leaning = checks.get("leaning") or {}
    colour = checks.get("if_signed") or "unknown"
    # A row the screen never wrote (the assign stage's ``unknown`` for a lot
    # nobody measured) has no checks to call failing and no fit to call
    # missing; the older bridge rows predate the flag and were all screened.
    screened = checks.get("screened", True)
    return {
        "design": row.design_key,
        "screened": screened,
        "verdict": row.tier,
        "verdict_words": _VERDICT_WORDS.get(row.tier, row.tier),
        "colour": colour,
        "colour_words": _COLOUR_WORDS.get(colour, colour),
        "badge": _BADGE.get(colour, "badge-gray"),
        "reasons": [_said_reason(x) for x in checks.get("reasons") or []],
        "colour_reasons": [_said_reason(x) for x in checks.get("if_signed_reasons") or []],
        "head": checks.get("head"),
        "failing": list(checks.get("failing") or []),
        "unchecked": list(checks.get("unchecked") or []),
        "binding": list(row.binding or []),
        "slack_ft": float(row.slack_ft) if row.slack_ft is not None else None,
        "fits": checks.get("fits") if screened else None,
        "fit": (checks.get("fit") or {}) if screened else {},
        "stalls_charged": stalls.get("charged"),
        "stalls_seated": stalls.get("seated"),
        "band": stalls.get("band"),
        "ask": checks.get("ask"),
        "unknown_facts": list(leaning.get("unknown") or []),
        "assumed_facts": list(leaning.get("assumed") or []),
    }


def _lot_row(lot: FlatsLot, verdict: int, colour: int, results: list[dict[str, Any]]) -> dict[str, Any]:
    facts = lot.facts or {}
    best_colour = _COLOURS[colour] if 0 <= colour < len(_COLOURS) else "unknown"
    best_verdict = _COLOURS[verdict] if 0 <= verdict < len(_COLOURS) else "unknown"
    return {
        "id": lot.id,
        "tlid": lot.tlid,
        "county": lot.county,
        "jurisdiction": lot.jurisdiction,
        "city": _city_label(lot.jurisdiction),
        "zone": lot.zone,
        "zone_raw": lot.zone_raw,
        "address": lot.site_address or "",
        "area": float(lot.area_sqft) if lot.area_sqft is not None else None,
        "verdict": best_verdict,
        "verdict_words": _VERDICT_WORDS.get(best_verdict, best_verdict),
        "colour": best_colour,
        "colour_words": _COLOUR_WORDS.get(best_colour, best_colour),
        "badge": _BADGE.get(best_colour, "badge-gray"),
        "results": results,
        "quadfit": facts.get("quadfit") or {},
        "href": _lot_href(lot.county, lot.tlid),
    }


async def _lot_rows(
    session: DBSession,
    run_id: int,
    design: str | None,
    conditions: list[Any],
    colour: str,
    page: int,
) -> list[dict[str, Any]]:
    best = _best(run_id, design)
    stmt = (
        select(FlatsLot, best.c.verdict, best.c.colour)
        .join(best, best.c.lot_id == FlatsLot.id)
        .where(*conditions)
    )
    if colour in _COLOURS:
        stmt = stmt.where(best.c.colour == _COLOURS.index(colour))
    stmt = (
        stmt.order_by(FlatsLot.jurisdiction, FlatsLot.tlid)
        .offset((page - 1) * _LOTS_PAGE)
        .limit(_LOTS_PAGE)
    )
    lots = (await session.execute(stmt)).all()
    by_lot: dict[int, list[dict[str, Any]]] = {}
    ids = [lot.id for lot, _, _ in lots]
    if ids:
        found = await session.execute(
            select(FlatsLotResult)
            .where(FlatsLotResult.run_id == run_id, FlatsLotResult.lot_id.in_(ids))
            .order_by(FlatsLotResult.design_key)
        )
        for row in found.scalars():
            if design and row.design_key != design:
                continue
            by_lot.setdefault(row.lot_id, []).append(_result_card(row))
    return [_lot_row(lot, verdict, colour_rank, by_lot.get(lot.id, [])) for lot, verdict, colour_rank in lots]


async def _zones_in(session: DBSession, jurisdiction: str, snapshot_id: int | None) -> list[str]:
    """The zone codes the chosen run's copy of the county holds for a city."""
    if not jurisdiction:
        return []
    stmt = (
        select(FlatsLot.zone)
        .where(FlatsLot.jurisdiction == jurisdiction, FlatsLot.zone.is_not(None))
        .distinct()
        .order_by(FlatsLot.zone)
    )
    if snapshot_id is not None:
        stmt = stmt.where(FlatsLot.snapshot_id == snapshot_id)
    return [z for z in (await session.execute(stmt)).scalars() if z]


def _run_card(run: FlatsRun) -> dict[str, Any]:
    counts = (run.params or {}).get("counts") or {}
    return {
        "id": run.id,
        "status": run.status,
        "snapshot_id": run.snapshot_id,
        "finished": run.finished_at.strftime("%Y-%m-%d %H:%M UTC") if run.finished_at else "",
        "code_version": (run.code_version or "")[:8],
        "designs": list(run.design_keys or []),
        "counties": list(run.counties or []),
        "lots": counts.get("lots"),
        "notes": run.notes or "",
    }


def _lots_ctx(
    runs: list[FlatsRun],
    run: FlatsRun | None,
    *,
    jurisdiction: str = "",
    zone: str = "",
    colour: str = "",
    design: str = "",
    q: str = "",
    page: int = 1,
) -> dict[str, Any]:
    cities = sorted(
        ((layer_id, layer.label) for layer_id, layer in _layers().items()), key=lambda kv: kv[1]
    )
    return {
        "runs": [_run_card(r) for r in runs],
        "run": _run_card(run) if run is not None else None,
        "cities": cities,
        "jurisdiction": jurisdiction,
        "zone": zone,
        "colour": colour if colour in _COLOURS else "",
        "design": design,
        "q": q,
        "page": page,
        "per_page": _LOTS_PAGE,
        "colours": _COLOURS,
        "colour_words": _COLOUR_WORDS,
        "verdict_words": _VERDICT_WORDS,
        "badges": _BADGE,
    }

# --- the county copy: every snapshot, the gate, promote / roll back ---------------

#: Badge per snapshot status on the refresh page.
_SNAPSHOT_BADGE = {"current": "badge-green", "candidate": "badge-yellow", "retired": "badge-gray", "failed": "badge-red"}


async def _refresh_ctx(session: DBSession) -> dict[str, Any]:
    """One card per county copy, newest first, with what the page needs to say
    about it: its runs, the gate (candidates only), the delta and drift
    summaries, and how many review decisions its promotion put in doubt."""
    snapshots = list(
        (
            await session.execute(
                select(FlatsSnapshot).order_by(FlatsSnapshot.snapshot_date.desc(), FlatsSnapshot.id.desc())
            )
        ).scalars()
    )
    runs = list((await session.execute(select(FlatsRun).order_by(FlatsRun.id.desc()))).scalars())
    flagged = dict(
        (
            await session.execute(
                select(FlatsReviewDecision.needs_rereview_snapshot_id, func.count())
                .where(FlatsReviewDecision.needs_rereview_snapshot_id.is_not(None))
                .group_by(FlatsReviewDecision.needs_rereview_snapshot_id)
            )
        ).all()
    )
    cards = []
    for snap in snapshots:
        counts = snap.counts or {}
        report = snap.report or {}
        own = [r for r in runs if r.snapshot_id == snap.id]
        cards.append(
            {
                "id": snap.id,
                "snapshot_date": snap.snapshot_date.isoformat(),
                "status": snap.status,
                "badge": _SNAPSHOT_BADGE.get(snap.status, "badge-gray"),
                "host": snap.host,
                "rlis_release": snap.rlis_release,
                "features": counts.get("features") or 0,
                "datasets": len(counts.get("datasets") or {}),
                "lots": counts.get("lots") or 0,
                "measured": counts.get("measured") or 0,
                "promoted_at": snap.promoted_at.strftime("%Y-%m-%d %H:%M") if snap.promoted_at else None,
                "promoted_by": snap.promoted_by,
                "runs": [
                    {"id": r.id, "status": r.status, "rules_version": r.rules_version, "code_version": r.code_version}
                    for r in own
                ],
                "notes": snap.notes or "",
                "flagged": flagged.get(snap.id, 0),
                "gate": refresh_service.gate(snap) if snap.status == "candidate" else [],
                "blocks": refresh_service.blocks(snap) if snap.status == "candidate" else [],
                "delta": report.get("delta") or None,
                "new_zones": counts.get("new_zones") or None,
                "ruled_zones": counts.get("ruled_zones") or None,
                "prohibited_by_zone": counts.get("prohibited_by_zone") or None,
                "drift": report.get("drift") or None,
                "loaded": any(r.status == "candidate" for r in own),
            }
        )
    return {"snapshots": cards}


async def _refresh_page(
    request: Request,
    session: DBSession,
    *,
    error: str | None = None,
    done: str | None = None,
    override: str = "",
    override_for: int | None = None,
    reason: str = "",
    status_code: int = 200,
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    ctx = {
        **_base_ctx(user, dedup_count, "flats_refresh", conflicts_count=conflicts_count),
        **(await _refresh_ctx(session)),
        "refresh": await _refresh(session),
        "error": error,
        "done": done,
        "override": override,
        "override_for": override_for,
        "reason": reason,
    }
    return templates.TemplateResponse(request, "flats_refresh.html", ctx, status_code=status_code)


def _who(user: Any) -> str:
    """Who is promoting, as the row records it. A name over an address: the
    page says "promoted by Steph", not by an email."""
    if user is None:
        return ""
    return (getattr(user, "name", None) or getattr(user, "email", None) or str(getattr(user, "id", ""))).strip()


@router.get("/flats/refresh", response_class=HTMLResponse)
async def flats_refresh(request: Request, session: DBSession, done: str = Query("")) -> HTMLResponse:
    return await _refresh_page(request, session, done=done or None)


@router.post("/flats/refresh/promote", response_class=HTMLResponse)
async def flats_refresh_promote(
    request: Request,
    session: DBSession,
    snapshot: int = Form(...),
    override: str = Form(""),
) -> HTMLResponse:
    """Make a candidate copy the copy in use. Steph's rule: the agent promotes
    a clean gate on the standing word; a warned gate is promoted here, by a
    person, with a written reason the row keeps."""
    user = await _get_user(session, request)
    by = _who(user)
    try:
        done = await refresh_service.promote(session, snapshot, by=by, override=override.strip() or None)
    except refresh_service.PromotionBlocked as exc:
        await session.rollback()
        return await _refresh_page(
            request, session, error=str(exc), override=override, override_for=snapshot, status_code=422
        )
    except refresh_service.PromotionError as exc:
        await session.rollback()
        return await _refresh_page(request, session, error=str(exc), status_code=422)
    await session.commit()
    said = (
        f"Copy {done.snapshot.snapshot_date.isoformat()} is the copy in use; run {done.run.id} is the Lots pages' default"
        + (f"; {done.flagged:,} review decisions marked look again" if done.flagged else "")
        + (f"; promoted over {', '.join(done.blocks)}" if done.blocks else "")
        + "."
    )
    return RedirectResponse(f"/flats/refresh?done={quote(said)}", status_code=303)


@router.post("/flats/refresh/rollback", response_class=HTMLResponse)
async def flats_refresh_rollback(request: Request, session: DBSession, reason: str = Form("")) -> HTMLResponse:
    """Put the previous copy back in use; the demoted one becomes a candidate again."""
    user = await _get_user(session, request)
    try:
        done = await refresh_service.rollback(session, by=_who(user), reason=reason.strip())
    except refresh_service.PromotionError as exc:
        await session.rollback()
        return await _refresh_page(request, session, error=str(exc), reason=reason, status_code=422)
    await session.commit()
    said = (
        f"Copy {done.restored.snapshot_date.isoformat()} is the copy in use again; "
        f"copy {done.demoted.snapshot_date.isoformat()} is a candidate."
    )
    return RedirectResponse(f"/flats/refresh?done={quote(said)}", status_code=303)


@router.get("/flats/lots", response_class=HTMLResponse)
async def flats_lots(
    request: Request,
    session: DBSession,
    jurisdiction: str = Query(""),
    zone: str = Query(""),
    colour: str = Query(""),
    design: str = Query(""),
    q: str = Query(""),
    run: int | None = Query(None),
    page: int = Query(1, ge=1),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    runs = await _runs(session)
    chosen = _chosen_run(runs, run)
    ctx = {
        **_base_ctx(user, dedup_count, "flats_lots", conflicts_count=conflicts_count),
        **_lots_ctx(runs, chosen, jurisdiction=jurisdiction, zone=zone, colour=colour, design=design, q=q, page=page),
        "refresh": await _refresh(session),
        "counts": {"verdict": {}, "if_signed": {}, "lots": 0},
        "lots": [],
        "zones": [],
        "pages": 0,
    }
    if chosen is None:
        return templates.TemplateResponse(request, "flats_lots.html", ctx)
    designs = list(chosen.design_keys or [])
    picked = design if design in designs else None
    ctx["design"] = picked or ""
    ctx["designs"] = designs
    conditions = _lot_conditions(jurisdiction, zone, q)
    counts = await _lot_counts(session, chosen.id, picked, conditions)
    shown = counts["if_signed"].get(colour, counts["lots"]) if colour in _COLOURS else counts["lots"]
    ctx["counts"] = counts
    ctx["shown"] = shown
    ctx["pages"] = max(1, -(-shown // _LOTS_PAGE))
    ctx["lots"] = await _lot_rows(session, chosen.id, picked, conditions, colour, page)
    ctx["zones"] = await _zones_in(session, jurisdiction, chosen.snapshot_id)
    return templates.TemplateResponse(request, "flats_lots.html", ctx)


def _outline(geojson: str | None) -> dict[str, Any] | None:
    """The lot's rings scaled into a ``_OUTLINE_PX`` box, north up.

    EPSG:2913 is a projected grid in feet with y increasing northward, so the
    only transform is a flip and a scale; the box's width in feet is printed
    beside it so the drawing has a size.
    """
    if not geojson:
        return None
    try:
        shape = json.loads(geojson)
    except ValueError:
        return None
    polygons = shape.get("coordinates") or []
    if shape.get("type") == "Polygon":
        polygons = [polygons]
    rings = [ring for polygon in polygons for ring in polygon if len(ring) >= 3]
    if not rings:
        return None
    xs = [x for ring in rings for x, _y in ring]
    ys = [y for ring in rings for _x, y in ring]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    pad = 8
    scale = (_OUTLINE_PX - 2 * pad) / span
    x0, y0 = min(xs), min(ys)
    width_px = (max(xs) - x0) * scale + 2 * pad
    height_px = (max(ys) - y0) * scale + 2 * pad
    paths = []
    for ring in rings:
        points = " ".join(
            f"{pad + (x - x0) * scale:.1f},{height_px - pad - (y - y0) * scale:.1f}" for x, y in ring
        )
        paths.append(points)
    return {
        "paths": paths,
        "width": round(width_px),
        "height": round(height_px),
        "feet_across": round(max(xs) - x0),
        "feet_deep": round(max(ys) - y0),
    }


def _fact_rows(facts: dict[str, Any]) -> list[tuple[str, str]]:
    """The facts the screen read, as label / value pairs a person can scan.
    Only what is present is listed; a missing fact is left out rather than
    printed as None."""

    def ft(value: Any) -> str:
        return f"{float(value):,.0f} ft" if value is not None else ""

    def sqft(value: Any) -> str:
        return f"{float(value):,.0f} sf" if value is not None else ""

    def yes(value: Any) -> str:
        return "" if value is None else ("yes" if value else "no")

    def money(value: Any) -> str:
        return f"${float(value):,.0f}" if value is not None else ""

    observed = facts.get("observed") or {}
    envelope = facts.get("envelope") or {}
    slope = facts.get("slope") or {}
    sewer = facts.get("sewer") or {}
    flood = facts.get("flood") or {}
    roll = facts.get("assessor") or {}
    condo = facts.get("condo") or {}
    unmeasured = facts.get("unmeasured") or {}
    bearings = facts.get("front_bearings_deg") or []
    rows = [
        (
            "Not measured",
            " -- ".join(
                x for x in (_said_reason(unmeasured["reason"]) if unmeasured.get("reason") else "",
                            _said_reason(f"quadfit:{unmeasured['quadfit_step']}") if unmeasured.get("quadfit_step") else "")
                if x
            ),
        ),
        ("Frontage", ft(facts.get("frontage_ft"))),
        ("Lot width", ft(facts.get("lot_width_ft"))),
        ("Lot depth", ft(facts.get("lot_depth_ft"))),
        ("Street side faces", ", ".join(f"{float(b):.0f}°" for b in bearings)),
        ("Outline quality", str(facts.get("geometry_tier") or "")),
        ("Corner lot", yes(observed.get("corner_lot"))),
        ("Alley", yes(observed.get("abuts_alley"))),
        ("Alley at the rear", yes(observed.get("alley_at_rear"))),
        ("Alley at the side", yes(observed.get("alley_at_side"))),
        ("Alley width", ft(facts.get("alley_width_ft"))),
        ("On a cul-de-sac bulb", yes(facts.get("fronts_cul_de_sac"))),
        ("Split between zones", yes(facts.get("split_zone"))),
        (
            "Share in this zone",
            f"{float(facts['zone_frac']) * 100:.0f}%" if facts.get("zone_frac") is not None else "",
        ),
        ("Inside the urban growth boundary", yes(facts.get("inside_ugb"))),
        ("Carries a z overlay", yes(facts.get("has_z_overlay"))),
        ("Buildable envelope", sqft(envelope.get("sqft"))),
        ("Envelope after setbacks", sqft(envelope.get("setback_sqft"))),
        ("Envelope after carving", sqft(envelope.get("carved_sqft"))),
        (
            "Slope (mean / 85th / max)",
            " / ".join(
                f"{float(slope[k]):.0f}%" for k in ("mean_pct", "p85_pct", "max_pct") if slope.get(k) is not None
            )
            + (f" ({slope['source']})" if slope.get("source") else ""),
        ),
        ("Public sewer", yes(observed.get("public_sewer"))),
        ("In a sewer district", yes(sewer.get("in_district"))),
        ("Nearest sewer main", ft(sewer.get("main_dist_ft"))),
        ("In a flood hazard area", yes(flood.get("sfha"))),
        ("In a floodway", yes(flood.get("floodway"))),
        # The assessor's roll, adopted from the county copy on every refresh.
        ("Condo", f"{condo['verdict']}" + (f" ({condo['reason']})" if condo.get("reason") else "") if condo.get("verdict") and condo["verdict"] != "land" else ""),
        ("Assessed value", money(roll.get("assessed_value"))),
        ("Real market value (land / building / total)", " / ".join(money(roll.get(k)) or "-" for k in ("land_value", "building_value", "total_value")) if any(roll.get(k) is not None for k in ("land_value", "building_value", "total_value")) else ""),
        ("Year built", str(roll["year_built"]) if roll.get("year_built") else ""),
        ("Building size", sqft(roll.get("building_sqft")) if roll.get("building_sqft") else ""),
        ("Last sale", (f"{money(roll['sale_price'])} " if roll.get("sale_price") else "") + (f"on {_roll_date(roll['sale_date'])}" if roll.get("sale_date") else "")),
        ("Property code / state class", " / ".join(str(roll[k]) for k in ("prop_code", "state_class") if roll.get(k))),
        ("Land use", str(roll["land_use"]) if roll.get("land_use") else ""),
    ]
    return [(label, value) for label, value in rows if value]


def _roll_date(value: Any) -> str:
    """RLIS's ``YYYYMMDD`` sale date as ``YYYY-MM-DD``; anything else as it came."""
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


async def _lot_decisions(session: DBSession, county: str, tlid: str) -> list[dict[str, Any]]:
    """A person's standing decisions about this lot, newest first, each with
    the "look again" mark promotion sets when the ground under it moved
    (``review_decisions.needs_rereview_*``, migration 0134). The decision
    stands until a person supersedes it; the mark says it was made about
    different ground."""
    rows = await session.execute(
        select(FlatsReviewDecision)
        .where(
            FlatsReviewDecision.county == county,
            FlatsReviewDecision.tlid == tlid,
            FlatsReviewDecision.superseded_at.is_(None),
        )
        .order_by(FlatsReviewDecision.decided_at.desc(), FlatsReviewDecision.id.desc())
    )
    out = []
    for d in rows.scalars():
        out.append(
            {
                "id": d.id,
                "design": d.design_key or "either design",
                "check": d.check_code,
                "verdict": d.verdict,
                "badge": _BADGE.get(d.verdict, "badge-gray"),
                "reason": d.reason,
                "decided_at": d.decided_at.strftime("%Y-%m-%d") if d.decided_at else "",
                "look_again": d.needs_rereview_snapshot_id is not None,
                "look_again_why": d.needs_rereview_reason or "",
                "look_again_snapshot": d.needs_rereview_snapshot_id,
            }
        )
    return out


@router.get("/flats/lots/{county}/{tlid:path}", response_class=HTMLResponse)
async def flats_lot(
    request: Request,
    session: DBSession,
    county: str,
    tlid: str,
    run: int | None = Query(None),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    runs = await _runs(session)
    chosen = _chosen_run(runs, run)
    refresh = await _refresh(session)
    # The lot as the chosen run read it: a run's results point at the lot
    # rows of the county copy it screened, so the row is looked up in that
    # copy. A run that names no copy falls back to the newest row for the id.
    stmt = select(
        FlatsLot,
        func.ST_AsGeoJSON(FlatsLot.geom),
        func.ST_Y(FlatsLot.centroid),
        func.ST_X(FlatsLot.centroid),
    ).where(FlatsLot.county == county, FlatsLot.tlid == tlid)
    if chosen is not None and chosen.snapshot_id is not None:
        stmt = stmt.where(FlatsLot.snapshot_id == chosen.snapshot_id)
    else:
        stmt = stmt.order_by(FlatsLot.snapshot_id.desc()).limit(1)
    found = (await session.execute(stmt)).first()
    if found is None:
        ctx = {
            **_base_ctx(user, dedup_count, "flats_lots", conflicts_count=conflicts_count),
            **_lots_ctx(runs, chosen),
            "refresh": refresh,
            "counts": {"verdict": {}, "if_signed": {}, "lots": 0},
            "lots": [],
            "zones": [],
            "pages": 0,
            "missing": f"{county} {tlid}",
        }
        return templates.TemplateResponse(request, "flats_lots.html", ctx, status_code=404)
    lot, geojson, lat, lon = found
    results: list[dict[str, Any]] = []
    if chosen is not None:
        rows = await session.execute(
            select(FlatsLotResult)
            .where(FlatsLotResult.run_id == chosen.id, FlatsLotResult.lot_id == lot.id)
            .order_by(FlatsLotResult.design_key)
        )
        results = [_result_card(r) for r in rows.scalars()]
    ranks = [_COLOURS.index(r["colour"]) if r["colour"] in _COLOURS else len(_COLOURS) for r in results]
    verdicts = [_COLOURS.index(r["verdict"]) if r["verdict"] in _COLOURS else len(_COLOURS) for r in results]
    card = _lot_row(lot, min(verdicts) if verdicts else 2, min(ranks) if ranks else 2, results)
    facts = lot.facts or {}
    return templates.TemplateResponse(
        request,
        "flats_lot.html",
        {
            **_base_ctx(user, dedup_count, "flats_lots", conflicts_count=conflicts_count),
            **_lots_ctx(runs, chosen),
            "refresh": refresh,
            "lot": card,
            "decisions": await _lot_decisions(session, county, tlid),
            "facts": _fact_rows(facts),
            "quadfit": facts.get("quadfit") or {},
            "quadfit_jurisdiction": facts.get("quadfit_jurisdiction") or "",
            "outline": _outline(geojson),
            "lat": lat,
            "lon": lon,
            "source": facts.get("source") or "",
        },
    )


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
