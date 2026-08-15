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

Routes: /flats, /flats/{layer}, /ui/flats/quote, /ui/flats/sign
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.api.deps import DBSession
from app.api.routers.ui_helpers import _base_ctx, _get_counts, _get_user, templates
from app.models.flats import FlatsRuleSignature
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Incorporation, Layer, Status, Value

router = APIRouter(include_in_schema=False)

#: Lines of the document shown either side of a quoted line. Enough to see the
#: table row above and the footnote below, which is usually where the standard
#: turns out to be qualified.
_CONTEXT = 4

#: What a reviewer may say about a value. "verified" is a signature waiting to
#: be drained; "rejected" is the other half of a review — the number does not
#: match the line it cites — and it is recorded rather than dropped, because a
#: review whose only recordable outcome is agreement is not a review.
_VERDICTS = frozenset({"verified", "rejected"})

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
        "values": len(rows),
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
        "values": sum(s["values"] for s in summaries),
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
) -> HTMLResponse:
    """Record what a reviewer decided about one number.

    The value, citation and quote are read from the loaded rules rather than
    from the form. What the browser sends is an address and an opinion; if it
    could send the number as well, a signature could be recorded over text
    nobody displayed.
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


@router.get("/ui/flats/quote", response_class=HTMLResponse)
async def flats_quote(request: Request, ref: str = Query(...)) -> HTMLResponse:
    """The stored text a value cites, with a few lines either side of it.

    The surrounding lines are the point. A setback read off a table row means
    one thing under the heading above it and another under the footnote below,
    and a reviewer shown the row alone cannot tell which.
    """
    store = _store()
    path, _, fragment = ref.partition("#L")
    if path not in _known_documents():
        return templates.TemplateResponse(
            request,
            "partials/flats_quote.html",
            {"ref": ref, "error": "no such stored document", "lines": []},
        )

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
        return templates.TemplateResponse(
            request,
            "partials/flats_quote.html",
            {"ref": ref, "error": "this citation does not resolve to stored text", "lines": []},
        )

    if first:
        start = max(first - _CONTEXT, 1)
        end = min(last + _CONTEXT, len(whole))
        lines = [
            {"n": n, "text": whole[n - 1], "quoted": first <= n <= last}
            for n in range(start, end + 1)
        ]
    else:
        lines = [{"n": 0, "text": quoted, "quoted": True}]

    return templates.TemplateResponse(
        request,
        "partials/flats_quote.html",
        {"ref": ref, "error": "", "lines": lines, "path": path},
    )
