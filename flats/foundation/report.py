"""One lot's foundation, priced at read time, for the lot report (FD6 build step 10).

:func:`describe` takes a stored measured document (:mod:`flats.foundation.record`)
and the current settings and returns the lot report's ``foundation`` block:
plain data for the JSON report and plain sentences for the lot page panel.
Prices are never stored: every call prices the record afresh, so a price or
threshold change is an edit to ``flats/config/foundation.yaml``. A record
measured under other geometric settings is never priced: it reads "needs
re-measuring", with the settings that changed, and no figure.

Money is a string of dollars and cents (``"12345.67"``), never a float.

**Never a colour.** Nothing here is read by the screen, the colour, its reasons
or its flags; the block says so (``never_a_colour``).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from flats.foundation import classify, record, support
from flats.foundation import cost as costing
from flats.foundation import lot as lots
from flats.foundation import model
from flats.foundation.measure import geometry_of
from flats.foundation.settings import Settings

PRICED = "priced"
NEEDS_REMEASURING = "needs_remeasuring"

#: Plain names for the methods (FD6: A = slab on fill, B = raised floor on a wall).
PLAIN = {
    "B": "raised floor on a wall",
    "B+P": "raised floor on screw piles",
    "A dry": "slab on fill (dry season)",
    "A wet": "slab on fill (wet season)",
    "A": "slab on fill",
    "": "",
}

NOTE = (
    "Sizes are code minimums and the costs are estimates; an engineer's design will replace both. "
    "Prices are guide-level, for comparing one lot with another, not a budget."
)
NOT_A_CHECK = "Not a screen check: this never changes the lot's colour, its reasons or its flags."

_CENT = Decimal("0.01")


def money(value: Decimal) -> str:
    """Dollars and cents as a string (half to even)."""
    return str(value.quantize(_CENT, rounding=ROUND_HALF_EVEN))


def dollars(value: Decimal) -> str:
    return f"${costing.dollars(value):,}"


def span(low: Decimal, high: Decimal) -> str:
    return f"{dollars(low)} to {dollars(high)}"


def ft_in(inches: float) -> str:
    """4 ft 2 in; under a foot, 8 in."""
    total = int(round(inches))
    if total < 0:
        return "-" + ft_in(-inches)
    ft, inch = divmod(total, 12)
    if not ft:
        return f"{inch} in"
    return f"{ft} ft" if not inch else f"{ft} ft {inch} in"


def _measured_on_words(on: Mapping[str, Any]) -> str:
    ground = str(on.get("ground_source") or "")
    cell = on.get("cell_m")
    if "grid" in ground:
        what = "a 1 ft grid of the ground"
    elif ground == "six readings":
        what = "six ground readings"
    else:
        what = ground or "the ground"
    model_name = f"the {cell:g} m elevation model" if isinstance(cell, int | float) else "the elevation model"
    when = str(on.get("measured_at") or "")[:10]
    drawing = on.get("drawing") or "the drawn building"
    return f"Measured on {what} from {model_name} under {drawing}" + (f", {when}." if when else ".")


def _base(doc: Mapping[str, Any], version: str) -> dict[str, Any]:
    # The measured ring stays in the record; the block names it by its hash.
    on = {k: v for k, v in (doc.get("measured_on") or {}).items() if k != "drawn_ring"}
    return {
        "never_a_colour": True,
        "not_a_check_words": NOT_A_CHECK,
        "note": NOTE,
        "settings_version": version,
        "settings_file": "flats/config/foundation.yaml",
        "model_version": doc.get("model_version"),
        "record_version": doc.get("record_version"),
        "geometry_hash": doc.get("geometry_hash"),
        "measured_on": on,
        "measured_on_words": _measured_on_words(on),
    }


def _cost_lines(c: costing.Cost) -> list[dict[str, Any]]:
    return [
        {"name": ln.name, "quantity": round(ln.quantity, 3), "unit": ln.unit, "low": money(ln.low), "high": money(ln.high)}
        for ln in c.lines
    ]


def _method(name: str, r: model.MethodResult) -> dict[str, Any]:
    plain = PLAIN[name]
    slab = name.startswith("A")
    floor_words = (
        f"The floor sits {ft_in(r.floor_above_high_in)} above the highest ground under the building "
        f"and {ft_in(r.floor_above_low_in)} above the lowest."
    )
    if slab:
        wall_words = f"Deepest fill under the slab {ft_in(r.fill_max_in)}; the slab edge is up to {ft_in(r.tallest_wall_in)} tall."
    else:
        wall_words = (
            f"Tallest wall {ft_in(r.tallest_wall_in)} (footing top to floor), "
            f"{ft_in(r.average_wall_in)} on average."
        )
    guards = "no guard at any door" if not r.guards else f"a guard at {r.guards} of the 8 doors"
    steps_words = (
        f"Steps at the 8 doors: {r.risers_least} to {r.risers_most} (fewest to most), "
        f"{r.risers_total} in all; {guards}."
    )
    return {
        "method": name,
        "name": plain,
        "floor_above_high_in": round(r.floor_above_high_in, 2),
        "floor_above_low_in": round(r.floor_above_low_in, 2),
        "tallest_wall_in": round(r.tallest_wall_in, 2),
        "average_wall_in": round(r.average_wall_in, 2),
        "fill_max_in": round(r.fill_max_in, 2),
        "piles": r.piles,
        "risers_total": r.risers_total,
        "risers_least": r.risers_least,
        "risers_most": r.risers_most,
        "guards": r.guards,
        "longest_stair_in": round(r.longest_stair_in, 2),
        "floor_words": floor_words,
        "wall_words": wall_words,
        "steps_words": steps_words,
        "cost_low": money(r.cost.low),
        "cost_high": money(r.cost.high),
        "cost_words": span(r.cost.low, r.cost.high),
        "cost_lines": _cost_lines(r.cost),
        "doors": [
            {
                "face": d.face,
                "x_ft": d.x_ft,
                "height_in": round(d.height_in, 2),
                "height_words": ft_in(d.height_in),
                "steps": d.risers,
                "stair_run_in": round(d.stair_run_in, 2),
                "guard": d.guard,
                "handrail": d.handrail,
                "rail_ft": round(d.rail_ft, 2),
            }
            for d in r.doors
        ],
        "flags": [{"code": c, "words": w} for c, w in zip(r.flags, r.flag_words, strict=True)],
    }


def _style_words(res: lots.LotResult) -> str:
    group = res.group
    if group == support.ORDINARY:
        lo, hi = res.style.cheaper_low, res.style.cheaper_high
        name = {"A": "slab on fill", "B": "raised floor"}
        if lo == hi and lo:
            cheap = f"the {name[lo]} is cheaper at low and at high prices"
        elif lo and hi:
            cheap = f"the {name[lo]} is cheaper at low prices, the {name[hi]} at high prices"
        else:
            cheap = ""
        return "Ordinary ground: a slab on fill or a raised floor on a wall both work here" + (f"; {cheap}." if cheap else ".")
    if group == support.PILES:
        return "Soft or swelling ground: a raised floor carried on screw piles; no slab."
    if group == support.OWN_LOOK:
        return "The ground needs its own look (mapped slide, liquefaction or flood): the raised floor is shown for the record only."
    return "The ground under this lot is not sorted: the raised floor is shown for the record only."


def _cheaper(res: lots.LotResult) -> tuple[list[dict[str, Any]], str]:
    rows = [
        {"prices": c.prices, "against": c.against, "cheaper": c.cheaper, "by": money(c.by)}
        for c in res.cheaper
    ]
    dry = {c.prices: c for c in res.cheaper if c.against == "A dry"}
    if not dry:
        return rows, ""
    name = {"A": "slab on fill", "B": "raised floor", "same": "neither"}
    lo, hi = dry.get("low"), dry.get("high")
    if lo and hi and lo.cheaper == hi.cheaper and lo.cheaper != "same":
        words = f"Cheaper: the {name[lo.cheaper]}, by {span(lo.by, hi.by)} (against the dry-season slab)."
    else:
        parts = [f"at {c.prices} prices the {name[c.cheaper]} (by {dollars(c.by)})" for c in (lo, hi) if c]
        words = "Cheaper: " + "; ".join(parts) + " (against the dry-season slab)."
    return rows, words


def _item(i: classify.Item) -> dict[str, Any]:
    value: Any = i.value
    if isinstance(value, float):
        value = round(value, 2)
    return {"code": i.code, "method": i.method, "method_name": PLAIN.get(i.method, i.method), "value": value,
            "unit": i.unit, "words": i.words}


def _old(res: lots.LotResult) -> dict[str, Any]:
    old = res.infill
    methods = [m for m, on in (("B", "B" in res.applicable), ("A", "A dry" in res.applicable)) if on]
    if_basement = {m: {"low": money(old.total(m, "low")), "high": money(old.total(m, "high"))} for m in methods}
    weighted = {m: {"low": money(old.weighted(m, "low")), "high": money(old.weighted(m, "high"))} for m in methods}
    out: dict[str, Any] = {
        "in_total": False,
        "held": old.held,
        "count": len(old.buildings),
        "wall_crossed": old.wall_crossed,
        "wall_ft": round(old.wall_ft, 2),
        "longest_ft": round(old.longest_ft, 2),
        "floor_sf": round(old.floor_sf, 1),
        "year_built": old.year_built,
        "year_band": old.year_band,
        "basement_share": old.basement_share,
        "backfill_ft": round(old.backfill_ft, 2),
        "if_basement": if_basement,
        "weighted": weighted,
        "buildings": [
            {
                "bldg_id": bc.bldg_id,
                "wall_ft": round(bc.exposure.wall_ft, 2),
                "longest_ft": round(bc.exposure.longest_ft, 2),
                "floor_sf": round(bc.exposure.floor_sf, 1),
                "reaches_a_corner": bc.exposure.corner,
                "raised_floor_remedy": bc.b_remedy,
                "if_basement_b": {"low": money(bc.b.low), "high": money(bc.b.high)},
                "if_basement_a": {"low": money(bc.a.low), "high": money(bc.a.high)},
            }
            for bc in old.buildings
        ],
    }
    name = {"B": "raised floor", "A": "slab"}
    if not old.held:
        out["words"] = "Building footprints are not held for this lot."
    elif not old.buildings:
        out["words"] = "No mapped building stands under the pod."
    else:
        n = len(old.buildings)
        out["words"] = (
            f"{'A mapped building stands' if n == 1 else f'{n} mapped buildings stand'} under the pod "
            f"(a house, garage or shed on the footprint map); the walls cross {old.wall_ft:.0f} ft of "
            f"{'its' if n == 1 else 'their'} outline, longest stretch {old.longest_ft:.0f} ft."
        )
        if methods:
            parts = ", ".join(f"{name[m]} {span(old.total(m, 'low'), old.total(m, 'high'))} more" for m in methods)
            out["if_basement_words"] = f"If a mapped building here had a basement: {parts}. Not in the cost ranges above."
            year = f"built {old.year_built}" if old.year_built else "whose year built is not held"
            parts = ", ".join(f"{name[m]} {span(old.weighted(m, 'low'), old.weighted(m, 'high'))}" for m in methods)
            out["weighted_words"] = (
                f"Weighted by how often a house {year} had a basement ({old.basement_share:.0%}): {parts}. "
                f"Also not in the cost ranges above."
            )
        else:
            out["if_basement_words"] = "The basement figure is not priced for screw piles."
    return out


#: The words for a record measured on a drawing the lot no longer has.
EARLIER_DRAWING = (
    "Measured on an earlier drawing -- needs re-measuring: the building has been drawn in another place "
    "on this lot since it was measured, so no figure is shown until it is measured again."
)


def describe(
    doc: Mapping[str, Any],
    s: Settings,
    *,
    version: str,
    drawing: Sequence[Sequence[float]] | None = None,
) -> dict[str, Any]:
    """The ``foundation`` block for one lot from its stored document, priced now
    under ``s`` (``version`` = :func:`flats.foundation.record.settings_version`).
    ``drawing`` is the lot's drawn building ring now, when the caller has it: a
    record measured on another drawing reads "needs re-measuring" and carries
    no figure (:func:`flats.foundation.record.drawing_changed`)."""
    out = _base(doc, version)
    changed = record.drawing_changed(doc, drawing)
    out["drawing_checked"] = changed is not None
    if changed:
        out.update(status=NEEDS_REMEASURING, remeasure_because=["drawing"], status_words=EARLIER_DRAWING)
        return out
    stale = record.staleness(doc, s)
    if stale and record.FOOTPRINT_KEYS & set(stale):
        on = doc.get("measured_on") or {}
        try:
            was = on.get("footprint") or record.footprint_words(json.loads(doc["lot"]["geometry"]))
        except (KeyError, TypeError, ValueError):
            was = "another footprint"
        out.update(
            status=NEEDS_REMEASURING,
            remeasure_because=["footprint", *stale],
            status_words=(
                f"Measured on a different building footprint -- needs re-measuring: this lot was measured on {was}, "
                f"and the model now uses {record.footprint_words(dict(geometry_of(s)))}, so no figure is shown "
                "until it is measured again."
            ),
        )
        return out
    if stale:
        out.update(
            status=NEEDS_REMEASURING,
            remeasure_because=list(stale),
            status_words=(
                "Needs re-measuring: this lot was measured under other building dimensions or another record "
                f"layout ({', '.join(stale)}), so no figure is shown until it is measured again."
            ),
        )
        return out
    try:
        res = lots.assess(record.measured_of(doc), s)
    except (KeyError, TypeError, ValueError) as exc:
        out.update(
            status=NEEDS_REMEASURING,
            remeasure_because=["record"],
            status_words=f"Needs re-measuring: the stored record could not be read ({type(exc).__name__}).",
        )
        return out
    cheaper, cheaper_words = _cheaper(res)
    methods = [_method(name, res.methods[name]) for name in res.applicable]
    # Slab first, then the raised floor, as the panel reads.
    methods.sort(key=lambda m: (not m["method"].startswith("A"), m["method"]))
    out.update(
        status=PRICED,
        status_words="",
        group=res.group,
        embed_in_used=res.embed_in_used,
        style={
            "standard": list(res.style.standard),
            "cheaper_low": res.style.cheaper_low,
            "cheaper_high": res.style.cheaper_high,
            "words": _style_words(res),
        },
        cheaper=cheaper,
        cheaper_words=cheaper_words,
        methods=methods,
        challenges=[_item(i) for i in res.challenges],
        easy=[_item(i) for i in res.easy],
        flags=[{"code": c, "words": w} for c, w in zip(res.flags, res.flag_words, strict=True)],
        old_buildings=_old(res),
    )
    return out
