"""The six-step cap at the doors, inside the screen pass (FD8; FOLLOWUPS 213).

Steph 2026-11-20 (rulings.yaml):

* ``2026-11-20-foundation-six-step-cap-red`` -- a foundation method with any
  door over six precast unit risers is not used on the lot; the lot is RED
  only when every method open to it fails
  (:data:`FOUNDATION_STEPS_CAP`, a bind on :data:`CHECK`).
* ``2026-11-20-foundation-near-cap-yellow`` -- the best method's worst door
  over the cap by 2 in or less: YELLOW with :data:`NEAR_FLAG` naming the door;
  never GREEN, not RED.
* ``2026-11-20-front-doors-face-parking`` -- which long face takes the front
  doors (:mod:`flats.foundation.doors`).

The cap is worked where the screen stands the building: the drawing the lot
page shows (``Screened.drawing``), framed against the lot's street lines, read
off the same elevation models the slope check reads (the bridge's ``--dem``),
by the foundation package's own measure (:func:`flats.foundation.place.place`)
-- so the record the lot page prices and the colour agree.

Conservative where unread, never a pass:

* a drawn lot with no ground under the whole grid: YELLOW
  (:data:`UNMEASURED_FLAG`);
* a lot whose ground class is not read or not sorted, with A under the cap
  and B over it: YELLOW (:data:`CLASS_UNREAD_FLAG`) -- piles ground would
  leave only B on piles.

Notes, no colour (below the yellow line): within 2 in under the cap
(:data:`CLOSE_FLAG`); a stair that would run off the lot or onto the drawn
court or lane (:data:`STAIR_REACH_FLAG`).

Only a drawn lot (a fit and a building ring) is read, and only a colour that
is not RED already moves; nothing here makes a lot GREEN. Like
:func:`flats.geom.sewer.checked`, it is the last step of a lot's screen,
applied to ``screening`` and ``signed`` alike, and adds nothing twice.

The check is on wherever the run has elevation models (``terrain``); a run
without them (the unit tests' screens) is unchanged.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from flats.foundation import cap as caps
from flats.foundation import doors as door_face
from flats.foundation import measure, model, place, support
from flats.foundation import settings as foundation_settings
from flats.score import flags as flag_plan

CHECK = "foundation_steps_cap"
#: RED: every method open to the lot needs more than six steps at a door.
FOUNDATION_STEPS_CAP = "FOUNDATION_STEPS_CAP"
NEAR_REASON = "FOUNDATION_NEAR_CAP"
NEAR_FLAG = "FOUNDATION-NEAR-CAP"
CLASS_UNREAD_REASON = "FOUNDATION_CLASS_UNREAD"
CLASS_UNREAD_FLAG = "FOUNDATION-CLASS-UNREAD"
UNMEASURED_REASON = "FOUNDATION_UNMEASURED"
UNMEASURED_FLAG = "FOUNDATION-UNMEASURED"
CLOSE_REASON = "FOUNDATION_CAP_CLOSE"
CLOSE_FLAG = "FOUNDATION-CAP-CLOSE"
STAIR_REACH_REASON = "FOUNDATION_STAIR_REACH"
STAIR_REACH_FLAG = "FOUNDATION-STAIR-REACH"
REASONS: tuple[str, ...] = (
    FOUNDATION_STEPS_CAP, NEAR_REASON, CLASS_UNREAD_REASON, UNMEASURED_REASON, CLOSE_REASON, STAIR_REACH_REASON,
)
#: The flags that hold a GREEN lot YELLOW, and the notes that do not.
YELLOW_FLAGS = (NEAR_FLAG, CLASS_UNREAD_FLAG, UNMEASURED_FLAG)
NOTE_FLAGS = (CLOSE_FLAG, STAIR_REACH_FLAG)

RULING = "Steph 2026-11-20, rulings.yaml 2026-11-20-foundation-six-step-cap-red"
NEAR_RULING = "Steph 2026-11-20, rulings.yaml 2026-11-20-foundation-near-cap-yellow"

#: The bridge row's column: this lot x design's cap facts, JSON.
ROW_COLUMN = "foundation_cap"
#: The ground classes the bridge pre-pass sets on a lot row (:func:`with_classes`).
ROW_CLASS = "foundation_ground_class"
ROW_ALT_CLASS = "foundation_alt_ground_class"
UNMEASURED = "unmeasured"

_CACHE: dict[Any, dict[str, Any]] = {}
_CACHE_MAX = 512
_DEMS: dict[int, Any] = {}


# --- the ground classes -------------------------------------------------------


def with_classes(rows: Iterable[dict[str, Any]], path: Path | None) -> int:
    """Set each row's ground classes from ``path`` (parquet or CSV: ``tlid`` or
    ``TLID``, ``ground_class``, ``alt_ground_class``; the foundation measure
    run's ``status.parquet`` serves). TLIDs are matched whole, spaces kept. A
    row the file does not hold keeps no class: unread, the conservative case.
    Returns how many rows were classed."""
    if path is None:
        return 0
    import pandas as pd

    p = Path(path)
    frame = pd.read_csv(p, dtype=str) if p.suffix.lower() == ".csv" else pd.read_parquet(p)
    tl = "tlid" if "tlid" in frame.columns else "TLID"
    alt = frame["alt_ground_class"] if "alt_ground_class" in frame.columns else [None] * len(frame)
    got = {str(t): (g, a) for t, g, a in zip(frame[tl], frame["ground_class"], alt, strict=True)}
    n = 0
    for row in rows:
        hit = got.get(str(row.get("TLID")))
        if hit is None:
            continue
        row[ROW_CLASS], row[ROW_ALT_CLASS] = (_clean(v) for v in hit)
        n += 1
    return n


def _clean(v: Any) -> str | None:
    if v is None:
        return None
    text = str(v).strip()
    return None if not text or text.lower() in ("nan", "none") else text


def classes_of(row: Mapping[str, Any]) -> tuple[str | None, str | None] | None:
    """A lot row's ground classes, or None where the pre-pass gave none."""
    if row.get(ROW_CLASS) is None and row.get(ROW_ALT_CLASS) is None:
        return None
    return _clean(row.get(ROW_CLASS)), _clean(row.get(ROW_ALT_CLASS))


# --- the measure ----------------------------------------------------------------


def dem_of(terrain: Any) -> Any:
    """A foundation :class:`~flats.foundation.terrain.Dem` sharing the slope
    check's open elevation models (one set of file handles a process)."""
    from flats.foundation.terrain import Dem

    if terrain is None:
        return None
    got = _DEMS.get(id(terrain))
    if got is None:
        got = _DEMS[id(terrain)] = Dem.sharing(terrain)
    return got


def _ring_of(drawing: Mapping[str, Any] | None) -> list[list[float]] | None:
    ring = (drawing or {}).get("building")
    return ring if ring and len(ring) >= 4 else None


def _stair_reach(fr: Any, r: model.MethodResult, lot: Any, court: Any, lane: Any, s: Any) -> list[str]:
    """The doors whose unit would run off the lot or onto the drawn court or lane."""
    import shapely

    shapes = [shapely.Polygon(x) for x in (court, lane) if x and len(x) >= 4]
    out = []
    for d in r.doors:
        if not d.units:
            continue
        run_ft = model.unit_run_in(d.units, s) / 12.0
        y0, y1 = (0.0, -run_ft) if d.face == "front" else (s.width_ft, s.width_ft + run_ft)
        a, b = fr.world([d.x_ft, d.x_ft], [y0, y1], s.length_ft, s.width_ft, s.box_ft)
        seg = shapely.LineString([tuple(a), tuple(b)])
        foot = shapely.Point(tuple(b))
        if (lot is not None and not lot.is_empty and not lot.covers(foot)) or any(seg.intersects(g) for g in shapes):
            out.append(model.door_name(d, r.doors))
    return out


def facts_for(
    drawing: Mapping[str, Any] | None,
    *,
    terrain: Any,
    streets: Sequence[tuple[float, float, float, float]],
    lot: Any,
    required: bool,
    classes: tuple[str | None, str | None] | None,
    tlid: str | None = None,
    county: str | None = None,
) -> dict[str, Any] | None:
    """The cap on one drawn building, as plain facts; None where nothing is drawn."""
    ring = _ring_of(drawing)
    if ring is None or terrain is None:
        return None
    court, lane = (drawing or {}).get("court"), (drawing or {}).get("lane")
    key = (tlid, json.dumps(ring), required, json.dumps(court), json.dumps(lane), classes, tuple(streets))
    if key in _CACHE:
        return _CACHE[key]
    s = foundation_settings.load()
    placed = place.place(ring, streets, dem_of(terrain), s, required=required, court=court, lane=lane, lot=lot,
                         tlid=tlid, county=county)
    gc, alt = classes if classes is not None else (None, None)
    rule = placed.rule
    base = {"door_face": door_face.AWAY if placed.turned else door_face.STREET, "door_face_rule": rule,
            "ground_class": gc, "alt_ground_class": alt, "steps_rule": s.steps_rule}
    if placed.measured is None:
        facts = {**base, "state": UNMEASURED, "words": f"foundation: not measured ({placed.error})"}
    else:
        m = measure.with_inputs(placed.measured, {"ground_class": gc, "alt_ground_class": alt})
        group = support.group_of_class(support.effective_class_of(gc, alt), s)
        methods: dict[str, model.MethodResult] = {}
        for name in caps.CAP_OPEN[group]:
            methods[name] = model.slab(m, s) if name.startswith("A") else model.raised(m, s, piles=name == "B+P")
        c = caps.cap_of(methods, group, s)
        reach = _stair_reach(placed.frame, methods[c.best], lot, court, lane, s)
        facts = {**base, **c.facts(), "stair_reach": reach}
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[key] = facts
    return facts


# --- the colour -------------------------------------------------------------------


def _flag(code: str, by: str, source: str) -> flag_plan.Flag:
    return flag_plan.Flag(code, flag_plan.LOT, by, source=source)


def _apply(x: Any, facts: Mapping[str, Any]) -> Any:
    from flats.score.screen import Triage

    if x.triage is Triage.red:
        return x  # already red: nothing to add, nothing to attribute
    state = facts.get("state")
    if state == caps.RED:
        if any(b.check == CHECK for b in x.binds):
            return x
        bind = flag_plan.Bind(
            CHECK, facts["height_in"], facts["cap_in"], facts["over_by_in"],
            source=f"{facts['words']} -- {RULING}",
        )
        reasons = x.reasons if FOUNDATION_STEPS_CAP in x.reasons else (*x.reasons, FOUNDATION_STEPS_CAP)
        return dataclasses.replace(x, triage=Triage.red, binds=(*x.binds, bind), reasons=tuple(reasons))
    held = {
        caps.NEAR: (NEAR_FLAG, NEAR_REASON, f"{facts.get('words')} -- {NEAR_RULING}"),
        caps.CLASS_UNREAD: (CLASS_UNREAD_FLAG, CLASS_UNREAD_REASON, f"{facts.get('words')} -- {RULING}"),
        UNMEASURED: (UNMEASURED_FLAG, UNMEASURED_REASON, str(facts.get("words"))),
    }.get(state)
    out = x
    if held is not None:
        code, reason, source = held
        if not any(f.code == code for f in out.flags):
            reasons = out.reasons if reason in out.reasons else (*out.reasons, reason)
            triage = Triage.yellow if out.triage is Triage.green else out.triage
            out = dataclasses.replace(out, triage=triage, flags=(*out.flags, _flag(code, reason, source)),
                                      reasons=tuple(reasons))
    notes = []
    if state == caps.CLOSE:
        notes.append((CLOSE_FLAG, CLOSE_REASON, str(facts.get("words"))))
    if facts.get("stair_reach"):
        notes.append((STAIR_REACH_FLAG, STAIR_REACH_REASON,
                      "foundation: the precast steps at " + ", ".join(facts["stair_reach"])
                      + " would run off the lot or onto the drawn court or lane"))
    for code, reason, source in notes:
        if not any(f.code == code for f in out.flags):
            out = dataclasses.replace(out, flags=(*out.flags, _flag(code, reason, source)))
    return out


def checked(
    s: Any,
    *,
    terrain: Any,
    streets: Callable[[], Sequence[tuple[float, float, float, float]]],
    lot_geom: Any,
    classes: tuple[str | None, str | None] | None,
    tlid: str | None = None,
    county: str | None = None,
) -> Any:
    """``s`` with the six-step cap applied (see the module docstring)."""
    if terrain is None or not s.drawing or not getattr(s.fit, "fits", False) or _ring_of(s.drawing) is None:
        return s
    side = getattr(s.facts, "entrance_side_fit", None) if s.facts is not None else None
    facts = facts_for(
        s.drawing, terrain=terrain, streets=tuple(dict.fromkeys(streets())), lot=lot_geom,
        required=door_face.entrance_required(s.rules, side), classes=classes, tlid=tlid, county=county,
    )
    if facts is None:
        return s
    return dataclasses.replace(s, foundation=facts, screening=_apply(s.screening, facts), signed=_apply(s.signed, facts))


__all__ = [
    "CHECK",
    "CLASS_UNREAD_FLAG",
    "CLOSE_FLAG",
    "FOUNDATION_STEPS_CAP",
    "NEAR_FLAG",
    "REASONS",
    "ROW_COLUMN",
    "STAIR_REACH_FLAG",
    "UNMEASURED_FLAG",
    "checked",
    "classes_of",
    "dem_of",
    "facts_for",
    "with_classes",
]
