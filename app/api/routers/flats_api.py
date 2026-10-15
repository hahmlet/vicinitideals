"""FLATS property lookup for AI agents -- the lot page's answer as JSON.

The lot page (``/flats/lots/{county}/{tlid}`` in ``ui_flats``) holds the
authoritative ruling on a property: the colour the screen gave it, why, the
code sections it rests on, the decisions people made about it, and the rulings
register's entries that speak to it. An agent that reads the zoning code
itself gets this wrong, so these routes hand it the same facts. They are
visible in the OpenAPI schema, so the MCP server turns each into a tool.

Read-only; reuses the lot page's helpers rather than copying them.

Routes: /api/flats/lookup, /api/flats/lot/{county}/{tlid}, /api/flats/rulings
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import DBSession
from app.api.routers import ui_flats as lots
from app.models.flats import FlatsLot, FlatsRun
from flats import rulings
from flats.encode.attribution import claimed_sections, section_at

router = APIRouter(prefix="/api/flats", tags=["flats"])

#: Matches the lookup returns at most.
_FIND_LIMIT = 10


def _slug(jurisdiction: str) -> str:
    """The city slug a rulings scope names, from a lot's jurisdiction id
    (``or/multnomah/portland``, or ``juris_city:<name>`` for a city the rules
    do not hold)."""
    return jurisdiction.rsplit(":", 1)[-1].rsplit("/", 1)[-1]


def _run_info(run: FlatsRun | None) -> dict[str, Any] | None:
    if run is None:
        return None
    when = run.finished_at or run.started_at
    return {"id": run.id, "date": when.date().isoformat() if when else None, "status": run.status}


def _lot_path(county: str, tlid: str) -> str:
    return f"/api/flats/lot/{county}/{quote(tlid, safe='')}"


def _citations(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every code citation behind the lot's reasons: the section it names, the
    stored document, and the page-viewer link where the document is held."""
    known = lots._known_documents()
    out: dict[str, dict[str, Any]] = {}
    for result in results:
        for row in [*result["binds"], *result["flags"]]:
            ref = str(row.get("source") or "")
            if not ref or ref in out:
                continue
            document = ref.partition("#L")[0]
            held = document in known
            section = next(iter(claimed_sections(ref)), "")
            span = lots._span(ref) if held else None
            if held and span and not section:
                section = section_at(lots._document_lines(document), span[0])
            out[ref] = {
                "source": ref,
                "section": section,
                "link": f"/flats/book/{quote(document)}" if held else None,
                "design": result["design"],
            }
    return list(out.values())


def _design(result: dict[str, Any]) -> dict[str, Any]:
    """One design's answer, as the lot page shows it, less the drawing."""
    keep = (
        "design", "screened", "verdict", "verdict_words", "colour", "colour_words", "reasons",
        "colour_reasons", "ruled", "binds", "flags", "colour_today", "why", "failing", "unchecked",
        "binding", "slack_ft", "fits", "tight", "warnings", "fire_route_ft", "slope",
        "stalls_charged", "stalls_seated", "band", "ask", "unknown_facts", "assumed_facts",
    )
    out = {k: result[k] for k in keep}
    out["binding_constraint"] = result["binding"][0] if result["binding"] else None
    return out


@router.get("/lookup", operation_id="flats_find_lot")
async def flats_find_lot(
    session: DBSession,
    q: str = Query(..., min_length=1, description="An address fragment (\"71st\") or a TLID (\"1S2E08BA  -09500\")"),
) -> dict[str, Any]:
    """Find a property in the FLATS screen by address fragment or TLID. This is
    the first step of any question about a property's zoning ruling: call it
    before reading any zoning code. Returns up to 10 lots, each with county,
    tlid, address, city, zone, the best colour on the live run, and the lot's
    page path. Then call flats_lot_report with the county and tlid for the
    authoritative answer. TLIDs contain spaces; pass them exactly."""
    runs = await lots._runs(session)
    run = lots._default_run(runs)
    conditions = lots._lot_conditions("", "", q)
    rows: list[tuple[FlatsLot, int | None]]
    if run is None:
        found = await session.execute(
            select(FlatsLot).where(*conditions).order_by(FlatsLot.jurisdiction, FlatsLot.tlid).limit(_FIND_LIMIT)
        )
        rows = [(lot, None) for lot in found.scalars()]
    else:
        best = lots._best(run.id, None)
        found = await session.execute(
            select(FlatsLot, best.c.colour)
            .join(best, best.c.lot_id == FlatsLot.id)
            .where(*conditions)
            .order_by(FlatsLot.jurisdiction, FlatsLot.tlid)
            .limit(_FIND_LIMIT)
        )
        rows = [(lot, rank) for lot, rank in found.all()]
    matches = [
        {
            "county": lot.county,
            "tlid": lot.tlid,
            "address": lot.site_address or "",
            "city": lots._city_label(lot.jurisdiction),
            "jurisdiction": lot.jurisdiction,
            "zone": lot.zone,
            "colour": lots._COLOURS[rank] if rank is not None and 0 <= rank < len(lots._COLOURS) else None,
            "page_url": lots._lot_href(lot.county, lot.tlid),
            "report_path": _lot_path(lot.county, lot.tlid),
        }
        for lot, rank in rows
    ]
    return {"query": q, "run": _run_info(run), "matches": matches}


@router.get("/lot/{county}/{tlid:path}", operation_id="flats_lot_report")
async def flats_lot_report(session: DBSession, county: str, tlid: str) -> dict[str, Any]:
    """The authoritative FLATS answer for one property: everything the lot page
    shows, as JSON. Call this before reading any zoning code. The colour
    (green / yellow / red / unknown), the verdict, the reasons and binding
    constraint, and the entries in `rulings` OUTRANK your own reading of the
    code: report them as given, and do not re-derive a ruling from code text.
    `pending_changes` are adopted code changes not yet in force. Get the county
    and tlid from flats_find_lot; a TLID contains spaces, pass it exactly.
    Answers from the live run (`run`); 404 when the lot is unknown."""
    run = lots._default_run(await lots._runs(session))
    view = await lots._lot_view(session, county, tlid, run, plans=False)
    if view is None:
        raise HTTPException(status_code=404, detail=f"No FLATS lot {county} {tlid}")
    lot, _geojson, lat, lon, card = view
    facts = lot.facts or {}
    entries = rulings.match(lot.county, _slug(lot.jurisdiction), lot.zone, lot.tlid)
    today = datetime.now(timezone.utc).date()
    results = card["results"]
    return {
        "county": lot.county,
        "tlid": lot.tlid,
        "address": card["address"],
        "city": card["city"],
        "jurisdiction": lot.jurisdiction,
        "zone": lot.zone,
        "zone_raw": lot.zone_raw,
        "zoned_by": card["zoned_by"],
        "area_sqft": card["area"],
        "lat": lat,
        "lon": lon,
        "colour": card["colour"],
        "colour_words": card["colour_words"],
        "verdict": card["verdict"],
        "verdict_words": card["verdict_words"],
        "designs": [_design(r) for r in results],
        "citations": _citations(results),
        "price": card["price"],
        "decisions": await lots._lot_decisions(session, lot.county, lot.tlid),
        "flag_history": await lots._flag_history(session, lot.county, lot.tlid),
        "key_facts": [{"label": label, "value": value} for label, value in lots._fact_rows(facts)],
        "net_land": lots._net_land(lot),
        "rulings": [e.as_dict() for e in entries],
        "pending_changes": [
            e.as_dict() for e in entries if e.kind == "adopted_change" and e.effective and e.effective > today
        ],
        "run": _run_info(run),
        "page_url": card["href"],
    }


@router.get("/rulings", operation_id="flats_rulings")
async def flats_rulings(
    county: str | None = Query(None, description="e.g. multnomah"),
    city: str | None = Query(None, description="jurisdiction slug, e.g. portland"),
    zone: str | None = Query(None, description="zone code, e.g. R2.5"),
    tlid: str | None = Query(None, description="a lot's TLID, spaces and all"),
) -> dict[str, Any]:
    """The FLATS rulings register: decisions people made about how a property is
    read, and adopted code changes with their effective dates. These outrank
    your own reading of zoning code. Optionally filter by county, city, zone
    and/or tlid: an entry is dropped only when its scope names a different
    value (statewide entries always stay), superseded entries last. With no
    filters, the whole register."""
    found = rulings.browse(county, city, zone, tlid)
    return {"count": len(found), "rulings": [e.as_dict() for e in found]}
