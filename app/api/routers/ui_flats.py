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
/flats/feedback, /flats/{layer}, /ui/flats/quote, /ui/flats/sign,
/ui/flats/sign-passage, /ui/flats/bundle
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Sequence

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.api.deps import DBSession
from app.api.routers.ui_helpers import _base_ctx, _get_counts, _get_user, templates
from app.models.flats import FlatsRuleSignature
from flats.designs.model import Design, DesignStatus, Plat, load_catalog
from flats.encode.verify import fingerprint
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Incorporation, Layer, Status, Value
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

#: The layer-wide block's zone label. Not a zone code, so it cannot collide.
_DEFAULTS = "(layer defaults)"


@lru_cache(maxsize=1)
def _layers() -> dict[str, Layer]:
    """The whole rule hierarchy, parsed once.

    Cached for the life of the process because the YAML is baked into the image:
    it changes on deploy, and a deploy restarts the process.
    """
    return load_rules(strict=False)


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
        "quoted": sum(1 for row in rows if row["quote"]),
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
        "quoted": sum(s["quoted"] for s in summaries),
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


def _span(ref: str) -> tuple[int, int] | None:
    """The line range a citation names, or None if it names no lines."""
    _, _, fragment = ref.partition("#L")
    if not fragment:
        return None
    try:
        parts = [int(x) for x in fragment.replace("L", "").split("-")]
    except ValueError:
        return None
    return parts[0], parts[-1]


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
        if not row["quote"] or decided.get((row["zone"], row["field"], row["when"])):
            continue
        span = _span(row["quote"])
        row["line"] = span[0] if span else 0
        if span is None:
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
            cards.append(
                {
                    "ref": f"{document}#L{chain[0][0]}-L{max(x[1] for x in chain)}",
                    "refs": [f"{document}#L{a}-L{b}" for a, b in chain],
                    "document": document,
                    "cite": here[0]["cite"],
                    "url": here[0]["url"],
                    "lines": _window(document, chain),
                    "error": "",
                    "rows": sorted(here, key=lambda r: (r["line"], r["zone"], r["field"])),
                }
            )
    for row in loose:
        lines, error = _cited_lines(row["quote"])
        cards.append(
            {
                "ref": row["quote"],
                "refs": [row["quote"]],
                "document": row["quote"].partition("#L")[0],
                "cite": row["cite"],
                "url": row["url"],
                "lines": lines,
                "error": error,
                "rows": [row],
            }
        )
    return sorted(cards, key=lambda c: (c["document"], _span(c["ref"]) or (0, 0)))


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
        {
            "n": n,
            "text": whole[n - 1],
            "quoted": any(first <= n <= last for first, last in chain),
        }
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
    return templates.TemplateResponse(
        request,
        "flats_feedback.html",
        {
            **_base_ctx(user, dedup_count, "flats", conflicts_count=conflicts_count),
            "rows": rows,
            "bundle": _bundle_text(rows),
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
    document, span = ref.partition("#L")[0], _span(ref)
    shown = _shown(ref)
    signed = 0
    for row in _value_rows(layer):
        if not _within(row["quote"], document, span):
            continue
        if decided.get((row["zone"], row["field"], row["when"])):
            continue
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
        row["decision"] = seen.verdict if seen else ""
        row["decided_by"] = seen.reviewer if seen else ""
        row["pending"] = bool(seen and seen.exported_at is None)
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
    """
    span = _span(ref)
    document = ref.partition("#L")[0]
    lines = _window(document, [span]) if span else _cited_lines(ref)[0]
    return "\n".join(f"{line['n']:>6}  {line['text']}" for line in lines)


def _mark(layer_id: str, zone: str, field: str, when: str, number: Any) -> str:
    """The fingerprint of exactly what a reviewer was looking at."""
    return fingerprint(
        layer_id,
        zone,
        field,
        number.value,
        cite=number.prov.cite,
        quote=number.prov.quote,
        when=tuple(when.split("+")) if when else (),
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
    if number is None or verdict not in _VERDICTS:
        return templates.TemplateResponse(
            request,
            "partials/flats_decision.html",
            {"row": {"decision": "", "pending": False}, "error": "not a value we hold"},
            status_code=400,
        )
    if verdict in _NEEDS_NOTE and not note.strip():
        return templates.TemplateResponse(
            request,
            "partials/flats_decision.html",
            {
                "row": {"decision": "", "pending": False},
                "error": "say what is wrong with it — a bare rejection is not actionable",
            },
            status_code=400,
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


def _within(quote: str, document: str, span: tuple[int, int] | None) -> bool:
    """Whether a value's citation falls inside the card's window.

    The card addresses a stretch of one document, and this is what decides
    which numbers that stretch covers. It is deliberately containment rather
    than string equality: the window was widened to hold them, and a value
    whose lines sit outside it was not on screen.
    """
    if not quote or quote.partition("#L")[0] != document:
        return False
    if span is None:
        return quote == document
    here = _span(quote)
    return here is not None and span[0] <= here[0] and here[1] <= span[1]


def _cited_lines(ref: str) -> tuple[list[dict[str, Any]], str]:
    """The stored text a citation points at, with a few lines either side.

    The surrounding lines are the point. A setback read off a table row means
    one thing under the heading above it and another under the footnote below,
    and a reviewer shown the row alone cannot tell which.

    Returns the lines and an error message; never both.
    """
    store = _store()
    path, _, fragment = ref.partition("#L")
    if path not in _known_documents():
        return [], "no such stored document"

    first = last = 0
    try:
        if fragment:
            parts = fragment.replace("L", "").split("-")
            first = int(parts[0])
            last = int(parts[-1]) if len(parts) > 1 else first
        whole = store.load(path).text.splitlines()
        quoted = store.quote(ref)
    except (ProvenanceError, ValueError, OSError):
        # The reason is not shown: the reference is user-supplied, and an
        # error carrying a filesystem path back to the browser answers
        # questions about the server that a review page has no business
        # answering.
        return [], "this citation does not resolve to stored text"

    if not first:
        return [{"n": 0, "text": quoted, "quoted": True}], ""

    start = max(first - _CONTEXT, 1)
    end = min(last + _CONTEXT, len(whole))
    return [
        {"n": n, "text": whole[n - 1], "quoted": first <= n <= last}
        for n in range(start, end + 1)
    ], ""


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
