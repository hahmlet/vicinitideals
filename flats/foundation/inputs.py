"""The per-lot inputs the foundation model keeps but does not measure, worked out
from the sources themselves for any drawn lot (FOLLOWUPS 209 slice 4).

Slices 1-3 read these from the FD2 pass-1 lot file, which exists only for the
9,517 research lots. To measure every lot a run draws a building on, the same
facts are worked out here from the same sources, by the same rules:

* the ground class (``ground_class``, ``alt_ground_class``): the soil survey
  under the drawn footprint and the mapped landslide, liquefaction and flood
  hazards there (:func:`soil_facts`, :func:`hazard_facts`, :func:`ground_class`);
* the street-side face's turn (``front_face_turn_deg``, :func:`front_face`);
* whether building footprints are held round the lot (:func:`held_box`).

Copied, unchanged in behaviour, from branch ``flats/fd2-pass1`` at 90fd7962
(not on main), so the foundation package needs neither that branch nor the
ingest package's FD2 module: ``flats/ingest/fd2.py`` (``overlap_cm``,
``soil_layer``, ``restrictions``, ``high_water``, ``ground_class`` and their
constants), ``scripts/flats_fd2_pass1.py`` (``_soil``, ``_component_facts``,
``_hazards``, ``_liq_label`` and the ``fix-flood`` NFHL step), and
``flats/ingest/fd5.py`` (``front_face``, ``COVERAGE_FT``) with
``scripts/flats_fd5_pass2.py``'s "held" rule. Only the facts the ground class
reads are kept from ``_hazards``.

Every missing input stays missing (None), never a guess: a lot whose soil
cannot be read sorts NO-DATA, and with no named series under it the
foundation model calls its ground "not sorted" (:mod:`flats.foundation.support`).
A hazard check whose layer holds no answer for the footprint does not match
(FD2's rule) and is named in ``ground_class_unread``; the foundation model
does not take FD2's class for such a lot (it could be the unread one), but
:data:`UNREAD`, which sorts "not sorted" (slice 4: "never guess ordinary").

Never a colour: nothing here is read by the screen.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

#: Centimetres per foot.
CM_PER_FT = 30.48
#: The soil layer FD2 asks about: 1 to 5 ft below the surface.
LAYER_TOP_CM = 1 * CM_PER_FT
LAYER_BOT_CM = 5 * CM_PER_FT
#: Ground class cut-offs, as the FD2 hand-off prints them.
BEDROCK_CM = 5 * CM_PER_FT
COBBLE_PCT = 15.0
SWELL_LEP = 6.0
WET_CM = 2 * CM_PER_FT
PAN_CM = 3.5 * CM_PER_FT

GROUND_ORDER = ("HAZ-SLIDE", "HAZ-LIQ", "FLOOD", "NO-DATA", "ROCK", "COBBLE", "SWELL", "SOFT", "WET-FINE", "FIRM")
#: The model's class for a lot with a check above FD2's class that could not be
#: made: in no group's list, so :func:`flats.foundation.support.group_of_class`
#: sorts it "not sorted".
UNREAD = "UNREAD"
WET_DRAINAGE = frozenset({"Very poorly drained", "Poorly drained", "Somewhat poorly drained"})
ORGANIC_UNIFIED = frozenset({"OL", "OH", "PT"})
BEDROCK_KINDS = frozenset({"Lithic bedrock", "Paralithic bedrock", "Densic bedrock"})
PAN_KINDS = frozenset({
    "Fragipan", "Duripan", "Densic material", "Cemented horizon", "Ortstein",
    "Petrocalcic", "Petroferric", "Petrogypsic", "Placic",
})

#: The hazard layers the ground class reads (FD2 pass 1's extract keys).
HAZARD_KEYS = (
    "landslide_shallow", "landslide_deep", "landslide_overview", "landslide_inventory",
    "landslide_historic", "landslide_scarps", "liquefaction", "flood_fema",
)
#: The scarp ring FD2 reads round a footprint (``slide_scarp_within_100ft``).
SCARP_RING_FT = 100.0
#: FD5 pass 2: footprints are "held" round a lot when any footprint's box
#: meets the box of the lot grown by this much (RLIS covers the Metro area only).
COVERAGE_FT = 1500.0

ALT_FIELDS = ("unified_1_5ft", "lep_1_5ft_pct", "frag_gt3in_pct", "restriction_cm", "restriction_kind",
              "bedrock_cm", "pan_cm", "pan_kind", "drainage", "hydric", "water_cm", "water_months",
              "dwellings_rating", "corrosion_steel", "corrosion_concrete")


def hazard_reach_ft(nearest_ft: Iterable[float | None]) -> float:
    """How far from a footprint any hazard answer reads: the largest
    ``nearest_ft`` of the vector layers loaded (pipeline.yaml: 1000 ft) or the
    scarp ring, whichever is larger, plus a foot. A feature farther than this
    from every drawn footprint can be dropped before a run without changing
    any answer."""
    return max([SCARP_RING_FT, *(float(d) for d in nearest_ft if d is not None)]) + 1.0


def held_box(bounds: Sequence[float]) -> tuple[float, float, float, float]:
    """FD5 pass 2's "held" test box: the lot's box grown by :data:`COVERAGE_FT`
    (the box of ``lot.buffer(COVERAGE_FT)``). Footprints are held round a lot
    when any footprint's box meets it."""
    x0, y0, x1, y1 = (float(v) for v in bounds)
    return (x0 - COVERAGE_FT, y0 - COVERAGE_FT, x1 + COVERAGE_FT, y1 + COVERAGE_FT)


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# --- the soil survey ---------------------------------------------------------------


def overlap_cm(top: Any, bot: Any, lo: float, hi: float) -> float:
    t, b = _num(top), _num(bot)
    if t is None or b is None:
        return 0.0
    return max(0.0, min(b, hi) - max(t, lo))


def soil_layer(horizons: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The 1-5 ft layer of one component's horizons (FD2 ``soil_layer``)."""
    thick: dict[str, float] = {}
    classes: list[str] = []
    lep = None
    frag = None
    seen_layer = False
    for h in horizons:
        o = overlap_cm(h.get("hzdept_r"), h.get("hzdepb_r"), LAYER_TOP_CM, LAYER_BOT_CM)
        o_all = overlap_cm(h.get("hzdept_r"), h.get("hzdepb_r"), 0.0, LAYER_BOT_CM)
        if o > 0:
            seen_layer = True
            u = h.get("unified")
            if u:
                thick[str(u)] = thick.get(str(u), 0.0) + o
                if str(u) not in classes:
                    classes.append(str(u))
            v = _num(h.get("lep_r"))
            if v is not None:
                lep = v if lep is None else max(lep, v)
        if o_all > 0:
            parts = [_num(h.get("frag3to10_r")), _num(h.get("fraggt10_r"))]
            if any(p is not None for p in parts):
                f = sum(p for p in parts if p is not None)
                frag = f if frag is None else max(frag, f)
    unified = max(thick, key=lambda k: (thick[k], k)) if thick else None
    return {
        "unified_1_5ft": unified,
        "unified_1_5ft_all": ",".join(classes) or None,
        "organic_1_5ft": (bool(set(classes) & ORGANIC_UNIFIED) if classes else None),
        "lep_1_5ft_pct": lep,
        "frag_gt3in_pct": frag,
        "layer_horizons": seen_layer,
    }


def restrictions(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The shallowest restrictive layer, bedrock and pan (FD2 ``restrictions``)."""

    def shallowest(keep: Callable[[str], bool]) -> tuple[float | None, str | None]:
        found = [(_num(r.get("resdept_r")), str(r.get("reskind") or "")) for r in rows]
        found = [(d, k) for d, k in found if d is not None and keep(k)]
        if not found:
            return None, None
        return min(found)  # type: ignore[type-var]

    d, k = shallowest(lambda k: bool(k))
    bd, bk = shallowest(lambda k: k in BEDROCK_KINDS)
    pd, pk = shallowest(lambda k: k in PAN_KINDS)
    return {
        "restriction_cm": d, "restriction_kind": k,
        "bedrock_cm": bd, "bedrock_kind": bk,
        "pan_cm": pd, "pan_kind": pk,
        "restrictions_all": "; ".join(
            f"{r.get('reskind')} {r.get('resdept_r')} cm" for r in sorted(
                rows, key=lambda r: (_num(r.get("resdept_r")) or 1e9, str(r.get("reskind"))))
        ) or None,
    }


def high_water(months: Sequence[Mapping[str, Any]] | None) -> tuple[float | None, str | None]:
    """The shallowest seasonal high water and its months (FD2 ``high_water``)."""
    wet = [m for m in (months or ()) if _num(m.get("wet_top_cm")) is not None]
    if not wet:
        return None, None
    low = min(_num(m["wet_top_cm"]) for m in wet)  # type: ignore[type-var]
    when = [str(m.get("month")) for m in sorted(wet, key=lambda m: m.get("monthseq") or 0)
            if _num(m["wet_top_cm"]) == low]
    return low, ",".join(when)


def _has_data(c: Mapping[str, Any]) -> bool:
    return bool(c.get("horizons"))


def _component_facts(c: Mapping[str, Any]) -> dict[str, Any]:
    layer = soil_layer(c.get("horizons") or [])
    res = restrictions(c.get("restrictions") or [])
    water_cm, water_months = high_water(c.get("months"))
    return {
        "cokey": c.get("cokey"),
        **{k: v for k, v in layer.items() if k != "layer_horizons"},
        **res,
        "restrictions_known": bool(c.get("horizons")),
        "drainage": c.get("drainagecl"), "hydric": c.get("hydricrating"),
        "water_cm": water_cm, "water_months": water_months, "water_months_held": bool(c.get("months")),
        "dwellings_rating": c.get("dwellings_rating"), "dwellings_reasons": c.get("dwellings_reasons"),
        "corrosion_steel": c.get("corsteel"), "corrosion_concrete": c.get("corcon"),
    }


def soil_facts(area_by_mukey: Mapping[str, float], fp_area: float, units: Mapping[str, Any]) -> dict[str, Any]:
    """FD2 pass 1 ``_soil``: the dominant map unit under the footprint (by area),
    its dominant component's facts, and for an Urban-land / no-data unit the
    largest named series with data (``_alt``). ``area_by_mukey`` is the
    footprint's area (sq ft) in each map unit; ``units`` the soil attributes."""
    area = {k: v for k, v in area_by_mukey.items() if v > 0}
    out: dict[str, Any] = {"soil_units_sqft": None, "mukey": None}
    if not area:
        out["soil_no_data"] = None
        out["soil_missing"] = "no survey polygon under the footprint"
        return out
    ranked = sorted(area.items(), key=lambda kv: (-kv[1], kv[0]))
    mk = ranked[0][0]
    unit = units.get(mk) or {}
    out.update({
        "mukey": mk, "musym": unit.get("musym"), "muname": unit.get("muname"),
        "mu_share": round(ranked[0][1] / fp_area, 3),
        "soil_units_sqft": "; ".join(f"{(units.get(k) or {}).get('musym')} {round(v)}" for k, v in ranked),
        "mu_urban_land": "urban land" in str(unit.get("muname") or "").lower(),
    })
    comps = sorted(unit.get("components") or [], key=lambda c: (-(c.get("comppct_r") or 0.0),
                   0 if str(c.get("majcompflag") or "").lower().startswith("y") else 1, str(c.get("cokey"))))
    if not comps:
        out["soil_no_data"] = True
        out["soil_missing"] = "map unit has no components"
        return out
    dom = comps[0]
    has = _has_data(dom)
    out.update({"comp_name": dom.get("compname"), "comp_pct": dom.get("comppct_r"),
                "comp_is_urban_land": str(dom.get("compname") or "").strip().lower() == "urban land",
                "comp_has_data": has})
    out["soil_no_data"] = bool(out["comp_is_urban_land"] or not has)
    out.update(_component_facts(dom))
    if out["soil_no_data"]:
        alt = next((c for c in comps if _has_data(c)
                    and str(c.get("compname") or "").strip().lower() != "urban land"), None)
        if alt is not None:
            out["alt_comp"] = alt.get("compname")
            out["alt_comp_pct"] = alt.get("comppct_r")
            out["_alt"] = _component_facts(alt)
    return out


# --- the mapped hazards --------------------------------------------------------------

_SHALLOW = {"1": 1, "2": 2, "3": 3}
_DEEP = {"Low": 1, "Moderate": 2, "High": 3}
_OVER = {"1": 1, "2": 2, "3": 3, "4": 4}


def hazard_facts(rows: Iterable[Mapping[str, Any]], have: set[str], *, scarp_within_100ft: bool | None) -> dict[str, Any]:
    """FD2 pass 1 ``_hazards``, the facts the ground class reads: ``slide_top``,
    ``slide_mapped``, ``liq_top2`` and ``flood_100`` (with the FEMA zone).

    ``rows`` are :func:`flats.ingest.hazards.measure_shape` rows for the
    footprint; ``have`` the layer keys loaded; ``scarp_within_100ft`` whether a
    mapped scarp line meets the footprint grown by 100 ft (None when the scarp
    layer is not loaded)."""
    by: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        by[r["layer"]].append(r)
    out: dict[str, Any] = {}

    def worst(key: str, order: dict[str, int]) -> tuple[str | None, float]:
        cls = [r for r in by.get(key, []) if r["state"] == "class" and str(r["class_code"]) in order]
        if not cls:
            return None, 0.0
        top = max(cls, key=lambda r: order[str(r["class_code"])])
        return str(top["class_label"] or top["class_code"]), round(sum(
            r["share"] for r in cls if order[str(r["class_code"])] == order[str(top["class_code"])]), 3)

    def share(key: str, state: str) -> float:
        return round(sum(r["share"] for r in by.get(key, []) if r["state"] == state), 3)

    out["susc_shallow"], out["susc_shallow_share"] = worst("landslide_shallow", _SHALLOW)
    out["susc_deep"], out["susc_deep_share"] = worst("landslide_deep", _DEEP)
    out["susc_overview"], out["susc_overview_share"] = worst("landslide_overview", _OVER)
    out["susc_detailed_cover"] = round(1.0 - share("landslide_shallow", "outside"), 3) if "landslide_shallow" in have else None
    out["susc_source"] = (
        None if not ({"landslide_shallow", "landslide_overview"} & have)
        else "detailed" if (out["susc_detailed_cover"] or 0) >= 0.999
        else "overview" if (out["susc_detailed_cover"] or 0) <= 0.001
        else "detailed+overview"
    )
    top = []
    if out["susc_shallow"] == "High":
        top.append("detailed shallow High")
    if out["susc_deep"] == "High":
        top.append("detailed deep High")
    if out["susc_overview"] == "Very high":
        top.append("overview Very high")
    out["slide_top"] = None if out["susc_source"] is None else bool(top)
    out["slide_top_why"] = "; ".join(top) or None

    near: dict[str, float | None] = {}
    for key in ("landslide_inventory", "landslide_historic"):
        for r in by.get(key, []):
            if r["state"] == "nearest":
                near[str(r["class_code"])] = (r["detail"] or {}).get("distance_ft")
    inside_inv = [str(r["class_label"]) for r in by.get("landslide_inventory", []) if r["state"] == "class"]
    out["slide_inside"] = ", ".join(sorted(set(inside_inv))) or None
    out["slide_scarp_within_100ft"] = scarp_within_100ft
    if "landslide_inventory" in have:
        hits = [bool(inside_inv)]
        hits += [d is not None and d <= 100.0 for d in (near.get("Deposit"), near.get("Scarp flank"), near.get("Historic landslide point"))]
        hits.append(bool(scarp_within_100ft))
        out["slide_mapped"] = any(hits)
    else:
        out["slide_mapped"] = None

    liq = [r for r in by.get("liquefaction", []) if r["state"] == "class"]
    if "liquefaction" not in have:
        out["liq_top2"] = None
    elif not liq:
        out["liq_top2"] = None
    else:
        topr = max(liq, key=lambda r: int(r["class_code"]))
        out["liq_class_code"] = int(topr["class_code"])
        out["liq_top2"] = int(topr["class_code"]) >= 4

    fema = [r for r in by.get("flood_fema", []) if r["state"] == "class"]
    if "flood_fema" not in have:
        out["fema_zone"], out["flood_100"] = None, None
    else:
        out["fema_zone"] = ", ".join(sorted({str(r["class_code"]) + (f" ({r['class_label']})" if r["class_label"] else "")
                                             for r in fema})) or "not mapped"
        out["flood_100"] = any((r["detail"] or {}).get("in_100_year") for r in fema) if fema else None
        out["fema_source"] = "held overlay_fema_flood" if fema else None
    return out


def with_nfhl(hazards: Mapping[str, Any], hits: Sequence[Mapping[str, Any]] | None) -> dict[str, Any]:
    """FD2 ``fix-flood`` on one lot: where the held FEMA layer reads "not
    mapped", flood is unread (None) unless the NFHL zones under the footprint
    (``hits``) answer it."""
    out = dict(hazards)
    if out.get("fema_zone") == "not mapped":
        out["flood_100"], out["fema_source"] = None, None
        out.update(nfhl_flood(hits or ()))
    return out


def nfhl_flood(hits: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """FD2 ``fix-flood``: where the held FEMA layer has no polygon under the
    footprint, the FEMA NFHL zones it meets (``hits``: their properties)."""
    if not hits:
        return {}
    zones = sorted({str(p.get("FLD_ZONE")) + (f" ({p.get('ZONE_SUBTY')})" if p.get("ZONE_SUBTY") else "") for p in hits})
    return {
        "fema_zone": ", ".join(zones),
        "flood_100": any(str(p.get("SFHA_TF")).upper() == "T" for p in hits),
        "fema_source": "FEMA NFHL service (layer 28)",
    }


# --- the ground class ----------------------------------------------------------------


def ground_class(r: Mapping[str, Any]) -> tuple[str, list[str], bool | None]:
    """FD2 ``ground_class``: the class (first match wins), the checks above it
    that could not be made, and PAN. A missing input never matches; it is
    named in the list instead."""
    unread: list[str] = []

    def test(name: str, value: bool | None) -> bool:
        if value is None:
            unread.append(name)
            return False
        return bool(value)

    def either(*vals: bool | None) -> bool | None:
        if any(v is True for v in vals):
            return True
        if any(v is None for v in vals):
            return None
        return False

    def at_most(v: Any, cut: float) -> bool | None:
        x = _num(v)
        return None if x is None else x <= cut

    def at_least(v: Any, cut: float) -> bool | None:
        x = _num(v)
        return None if x is None else x >= cut

    known = r.get("restrictions_known")
    pan = None if not known else (r.get("pan_cm") is not None and float(r["pan_cm"]) <= PAN_CM)

    if test("HAZ-SLIDE", either(r.get("slide_mapped"), r.get("slide_top"))):
        return "HAZ-SLIDE", unread, pan
    if test("HAZ-LIQ", r.get("liq_top2")):
        return "HAZ-LIQ", unread, pan
    if test("FLOOD", r.get("flood_100")):
        return "FLOOD", unread, pan
    if r.get("soil_no_data") is not False:
        return "NO-DATA", unread, pan
    bedrock = (r.get("bedrock_cm") is not None and float(r["bedrock_cm"]) <= BEDROCK_CM) if known else None
    if test("ROCK", bedrock):
        return "ROCK", unread, pan
    if test("COBBLE", at_least(r.get("frag_gt3in_pct"), COBBLE_PCT)):
        return "COBBLE", unread, pan
    if test("SWELL", at_least(r.get("lep_1_5ft_pct"), SWELL_LEP)):
        return "SWELL", unread, pan
    hyd = str(r.get("hydric") or "").strip().lower()
    hydric = True if hyd == "yes" else False if hyd == "no" else None
    if test("SOFT", either(hydric, r.get("organic_1_5ft"))):
        return "SOFT", unread, pan
    drain = None if not r.get("drainage") else str(r["drainage"]) in WET_DRAINAGE
    water = at_most(r.get("water_cm"), WET_CM)
    if r.get("water_cm") is None and r.get("water_months_held"):
        water = False
    if test("WET-FINE", either(water, drain)):
        return "WET-FINE", unread, pan
    return "FIRM", unread, pan


def classes(soil: Mapping[str, Any], hazards: Mapping[str, Any]) -> dict[str, Any]:
    """The lot's ``ground_class`` and ``alt_ground_class`` (FD2 pass 1 ``_one``
    plus ``fix-flood``), from :func:`soil_facts` and :func:`hazard_facts`
    (with any NFHL answer merged in)."""
    rec = {**soil, **hazards}
    alt = rec.pop("_alt", None)
    g, unread, pan = ground_class(rec)
    out: dict[str, Any] = {"ground_class": g, "ground_class_unread": ",".join(unread) or None, "pan": pan,
                           "alt_ground_class": None}
    if alt is not None:
        g2, _u2, _pan2 = ground_class({**rec, **alt, "soil_no_data": False})
        out["alt_ground_class"] = g2
        if g2 and rec.get("flood_100") and g2 not in ("HAZ-SLIDE", "HAZ-LIQ"):
            out["alt_ground_class"] = "FLOOD"
    return out


# --- the drawn building against the street ------------------------------------------

Seg = tuple[float, float, float, float]


def _bearing(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0


def _turn(a: float, b: float) -> float:
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def _seg_dist(x: float, y: float, s: Seg) -> float:
    x1, y1, x2, y2 = s
    dx, dy = x2 - x1, y2 - y1
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / ll))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def front_face(fl: tuple[float, float], fr: tuple[float, float], bl: tuple[float, float],
               br: tuple[float, float], streets: Iterable[Seg]) -> dict[str, Any]:
    """FD5 ``front_face``: how far the street-side face is turned from the
    nearest street lot line (0 = parallel, 90 = end-on), and how far each
    face's middle stands from the streets."""
    segs = list(streets)
    if not segs:
        return {"front_face_street_ft": None, "back_face_street_ft": None, "front_face_turn_deg": None}
    fm = ((fl[0] + fr[0]) / 2, (fl[1] + fr[1]) / 2)
    bm = ((bl[0] + br[0]) / 2, (bl[1] + br[1]) / 2)
    near = min(segs, key=lambda s: _seg_dist(fm[0], fm[1], s))
    return {
        "front_face_street_ft": round(_seg_dist(fm[0], fm[1], near), 1),
        "back_face_street_ft": round(min(_seg_dist(bm[0], bm[1], s) for s in segs), 1),
        "front_face_turn_deg": round(_turn(_bearing(*fl, *fr), _bearing(*near)), 1),
    }


def year_built(value: Any) -> int | None:
    """FD2 pass 1: the occupancy build's assessor year, or None (0 is not a year)."""
    yb = _num(value)
    return int(yb) if yb and yb > 0 else None


def model_inputs(
    soil: Mapping[str, Any],
    hazards: Mapping[str, Any],
    *,
    frost_in: Any,
    year: Any,
    turn_deg: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The fields :func:`flats.foundation.measure.with_inputs` takes, and the
    facts behind the ground class (for the run's lot-status table). The two
    lot-file fields no price reads (``relief_input_ft``, ``bldg_overlap_share``)
    are not worked out: None. A lot with a check above its class that could not
    be made gets :data:`UNREAD` ("not sorted"), never FD2's class; FD2's class
    stays in the facts (``fd2_ground_class``)."""
    cls = classes(soil, hazards)
    yb = year_built(year)
    inputs = {
        "relief_input_ft": None,
        "ground_class": UNREAD if cls["ground_class_unread"] else cls["ground_class"],
        "alt_ground_class": cls["alt_ground_class"],
        "frost_register_in": _num(frost_in),
        "bldg_overlap_share": None,
        "front_face_turn_deg": _num(turn_deg),
        "year_built": None if yb is None else float(yb),
    }
    facts = {
        "fd2_ground_class": cls["ground_class"],
        "ground_class_unread": cls["ground_class_unread"],
        "soil_no_data": soil.get("soil_no_data"),
        "soil_missing": soil.get("soil_missing"),
        "mukey": soil.get("mukey"),
        "comp_name": soil.get("comp_name"),
        "alt_comp": soil.get("alt_comp"),
        "slide_mapped": hazards.get("slide_mapped"),
        "slide_top": hazards.get("slide_top"),
        "liq_top2": hazards.get("liq_top2"),
        "fema_zone": hazards.get("fema_zone"),
        "fema_source": hazards.get("fema_source"),
        "flood_100": hazards.get("flood_100"),
    }
    return inputs, facts
