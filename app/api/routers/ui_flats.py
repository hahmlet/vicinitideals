"""FLATS rule review — read the encoded zoning standards beside their source.

Every number FLATS screens against was read out of a code document and carries
a quote saying which line of which document it came from. Until now that quote
could only be followed at a terminal, which is why 645 values sit at `draft`
and none at `verified`: reviewing meant checking out the repository.

These pages put the value and the sentence it was read from on one screen. They
are read-only on purpose — signing a value changes a file in the repository, and
a button in a browser cannot commit. What a reviewer gets here is the hard part
(finding the text, comparing it to the number); the signature is still a command.

Routes: /flats, /flats/{layer}, /ui/flats/quote
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from app.api.deps import DBSession
from app.api.routers.ui_helpers import _base_ctx, _get_counts, _get_user, templates
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Incorporation, Layer, Status

router = APIRouter(include_in_schema=False)

#: Lines of the document shown either side of a quoted line. Enough to see the
#: table row above and the footnote below, which is usually where the standard
#: turns out to be qualified.
_CONTEXT = 4


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


def _value_rows(layer: Layer) -> list[dict[str, Any]]:
    """Every encoded value in a layer, as flat rows for the table."""
    rows: list[dict[str, Any]] = []
    blocks: list[tuple[str, dict[str, Any], str | None]] = [
        ("(layer defaults)", layer.defaults, None)
    ]
    for code in sorted(layer.zones):
        zone = layer.zones[code]
        blocks.append((code, zone.values, zone.notes))
    for zone_code, values, notes in blocks:
        for name in sorted(values):
            value = values[name]
            rows.append(
                {
                    "zone": zone_code,
                    "field": name,
                    "value": value.value,
                    "status": value.status.value,
                    "trusted": value.status is Status.verified,
                    "reviewer": value.reviewer,
                    "quote": value.prov.quote,
                    "cite": value.prov.cite,
                    "url": value.prov.url,
                    "variants": len(value.variants),
                    "zone_notes": notes,
                }
            )
    return rows


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
            "rows": _value_rows(layer),
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
