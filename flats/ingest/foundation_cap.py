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
(:data:`CLOSE_FLAG`).

Room for the steps (Steph 2026-11-20, rulings.yaml
``2026-11-20-stair-room-reserved`` and ``2026-11-20-stair-no-room-red-flag``):
each door's precast unit, 4 ft wide and as deep as its risers need, is laid
straight out from the wall where the building is drawn, and read against the
drawn court's stalls (past the standoff off the wall), the drawn lane and the
lot line (:func:`stair_room_of`). Where one lands on any of them,
:func:`flats.ingest.quadfit.foundation_checked` stands the plan again with that much
room kept (:class:`flats.designs.model.StairRoom`) and the whole screen runs
on the new placement; where it still has no room after
:data:`STAIR_PASSES` placements, or the plan with room kept is red, the lot
is RED with :data:`STAIR_ROOM_FLAG` naming the door, what it lands on and by
how much (:func:`no_room`), the facts kept in the row's ``foundation_cap``.

Only a drawn lot (a fit and a building ring) is read, and only a colour that
is not RED already moves; nothing here makes a lot GREEN. It is the last step
of a lot's screen, worked once on the answer every search between readings
kept (:func:`flats.ingest.quadfit.screen_lot`), never inside one, applied to
``screening`` and ``signed`` alike, and adds nothing twice.

The check is on wherever the run has elevation models (``terrain``); a run
without them (the unit tests' screens) is unchanged.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from flats.designs.model import StairRoom
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
#: RED: no placement found leaves the steps at a door room (a bind on
#: :data:`STAIR_CHECK`, with :data:`STAIR_ROOM_FLAG` to find the lot again).
STAIR_CHECK = "foundation_stair_room"
STAIR_ROOM = "FOUNDATION_STAIR_ROOM"
STAIR_ROOM_FLAG = "FOUNDATION-STAIR-ROOM"
#: The plan stood again with room for the steps reads another colour than the
#: first placement did: better, held at the first one's colour (YELLOW); worse,
#: the new colour with this flag naming why.
STAIR_MOVED = "FOUNDATION_STAIR_MOVED"
STAIR_MOVED_FLAG = "FOUNDATION-STAIR-MOVED"
REASONS: tuple[str, ...] = (
    FOUNDATION_STEPS_CAP, NEAR_REASON, CLASS_UNREAD_REASON, UNMEASURED_REASON, CLOSE_REASON, STAIR_ROOM,
    STAIR_MOVED,
)
#: The flags that hold a GREEN lot YELLOW, and the notes that do not.
YELLOW_FLAGS = (NEAR_FLAG, CLASS_UNREAD_FLAG, UNMEASURED_FLAG, STAIR_MOVED_FLAG)
NOTE_FLAGS = (CLOSE_FLAG,)
#: Rides with the stair-room bind on a red lot.
RED_FLAGS = (STAIR_ROOM_FLAG,)

RULING = "Steph 2026-11-20, rulings.yaml 2026-11-20-foundation-six-step-cap-red"
NEAR_RULING = "Steph 2026-11-20, rulings.yaml 2026-11-20-foundation-near-cap-yellow"
ROOM_RULING = ("Steph 2026-11-20, rulings.yaml 2026-11-20-stair-room-reserved and "
               "2026-11-20-stair-no-room-red-flag")

#: Placements tried with room kept for the steps, after the first.
STAIR_PASSES = 3
#: Feet a stair may touch the paving or cross the lot line by and still count
#: as clear: the drawing's coordinates are stored to a tenth of a foot.
STAIR_TOL_FT = 0.05
#: Every precast unit on the price list is 4 ft wide (flats/config/
#: foundation.yaml#L465, "a precast unit of 1 riser, 4 ft wide, 42 in
#: platform", and every row after it).
UNIT_WIDTH_FT = 4.0
#: What a stair lands on, as the flag says it, and the room kept for it.
COURT, LANE, LOT_LINE = "court", "lane", "lot line"
_KEEP = {COURT: "court_ft", LANE: "flank_ft", LOT_LINE: "lot_ft"}

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


def _poly(ring: Any) -> Any:
    import shapely

    if not ring or len(ring) < 4:
        return None
    got = shapely.Polygon(ring)
    return got if got.is_valid and not got.is_empty else got.buffer(0)


def stair_room_of(
    fr: Any, r: model.MethodResult, s: Any, *, lot: Any, court: Any, lane: Any, standoff_ft: float, beside: bool,
) -> dict[str, Any]:
    """Where each door's precast unit lands on the drawing (FOLLOWUPS 213).

    The unit is a box :data:`UNIT_WIDTH_FT` wide centred on the door, run
    straight out from the wall as far as its risers need
    (:func:`flats.foundation.model.unit_run_in`). It has no room where it
    runs further into the drawn court than the standoff off the wall
    (``standoff_ft``; a court beside the building has none, its stalls are
    against the flank), onto the drawn lane, or past the lot line. ``need``
    is the room to keep on the next placement, the worst unit's run for
    each kind it lands on."""
    import shapely

    paving = [(COURT, _poly(court), 0.0 if beside else standoff_ft), (LANE, _poly(lane), 0.0)]
    grown = lot.buffer(STAIR_TOL_FT) if lot is not None and not lot.is_empty else None
    hits: list[dict[str, Any]] = []
    need = {k: 0.0 for k in _KEEP.values()}
    half = UNIT_WIDTH_FT / 2
    for d in r.doors:
        if not d.units:
            continue
        run_ft = model.unit_run_in(d.units, s) / 12.0
        y0, y1 = (0.0, -run_ft) if d.face == "front" else (s.width_ft, s.width_ft + run_ft)
        xs = [d.x_ft - half, d.x_ft + half, d.x_ft]
        pts = fr.world(xs + xs, [y0] * 3 + [y1] * 3, s.length_ft, s.width_ft, s.box_ft)
        wall, foot = pts[:3], pts[3:]
        # The frame stretches the pod's plan onto the drawn ring; the unit
        # runs its own length out of the wall, in feet on the ground.
        foot = [w + (f - w) * (run_ft / max(float(((f - w) ** 2).sum()) ** 0.5, 1e-9)) for w, f in zip(wall, foot)]
        box = shapely.Polygon([tuple(wall[0]), tuple(wall[1]), tuple(foot[1]), tuple(foot[0])])
        lines = [shapely.LineString([tuple(wall[i]), tuple(foot[i])]) for i in range(3)]
        name = model.door_name(d, r.doors)
        got: list[tuple[str, float]] = []
        for kind, shape, allowed in paving:
            if shape is None or not box.intersects(shape):
                continue
            into = max(float(line.intersection(shape).length) for line in lines)
            if into - allowed > STAIR_TOL_FT:
                got.append((kind, into - allowed))
                # A court beside the building is kept off it as the lane is.
                kept = _KEEP[LANE] if beside else _KEEP[kind]
                need[kept] = max(need[kept], run_ft)
        if grown is not None and not grown.covers(box):
            off = max(float(shapely.Point(tuple(p)).distance(lot)) for p in foot)
            got.append((LOT_LINE, max(off, STAIR_TOL_FT)))
            need["lot_ft"] = max(need["lot_ft"], run_ft)
        for kind, by in got:
            hits.append({"door": name, "risers": int(d.units), "run_ft": round(run_ft, 2), "hits": kind,
                         "by_ft": round(by, 2)})
    return {"hits": hits, "need": {k: round(v, 2) for k, v in need.items()}, "standoff_ft": standoff_ft}


def _terrain_key(terrain: Any) -> Any:
    """Which elevation models ``terrain`` reads, for the cache key: the same
    lot and drawing on other ground is another answer."""
    tiles = tuple(getattr(x, "name", str(x)) for x in (getattr(terrain, "tiles", None) or ()))
    coarse = getattr(getattr(terrain, "coarse", None), "name", None)
    return (tiles, coarse) if tiles or coarse is not None else id(terrain)


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
    standoff_ft: float = 0.0,
    beside: bool = False,
) -> dict[str, Any] | None:
    """The cap on one drawn building, as plain facts; None where nothing is drawn.
    ``standoff_ft`` is the clear ground the drawn court keeps off the rear
    wall and ``beside`` a court drawn beside the building
    (:func:`stair_room_of`)."""
    ring = _ring_of(drawing)
    if ring is None or terrain is None:
        return None
    court, lane = (drawing or {}).get("court"), (drawing or {}).get("lane")
    key = (tlid, json.dumps(ring), required, json.dumps(court), json.dumps(lane), classes, tuple(streets),
           round(standoff_ft, 3), beside, None if lot is None else lot.wkb, _terrain_key(terrain))
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
        room = stair_room_of(placed.frame, methods[c.best], s, lot=lot, court=court, lane=lane,
                             standoff_ft=standoff_ft, beside=beside)
        facts = {**base, **c.facts(), "stair_room": room}
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
    for code, reason, source in notes:
        if not any(f.code == code for f in out.flags):
            out = dataclasses.replace(out, flags=(*out.flags, _flag(code, reason, source)))
    return out


def standoff_of(s: Any) -> float:
    """The clear ground the drawing keeps between the rear wall and the
    court's stalls: the design's (raised by any room kept for the steps)
    or the city's stated buffer, the wider, as :func:`flats.ingest.quadfit`
    draws it."""
    gap = float(s.design.parking.building_gap_ft)
    stated = s.rules.get("parking_building_buffer_ft") if s.rules is not None else None
    if isinstance(stated, (int, float)) and not isinstance(stated, bool):
        gap = max(gap, float(stated))
    return gap


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
    """``s`` with the six-step cap applied and its steps' room read (see the
    module docstring); the room is acted on by
    :func:`flats.ingest.quadfit.foundation_checked`."""
    if terrain is None or not s.drawing or not getattr(s.fit, "fits", False) or _ring_of(s.drawing) is None:
        return s
    side = getattr(s.facts, "entrance_side_fit", None) if s.facts is not None else None
    facts = facts_for(
        s.drawing, terrain=terrain, streets=tuple(dict.fromkeys(streets())), lot=lot_geom,
        required=door_face.entrance_required(s.rules, side), classes=classes, tlid=tlid, county=county,
        standoff_ft=standoff_of(s), beside=bool(getattr(s.fit, "beside", False)),
    )
    if facts is None:
        return s
    return dataclasses.replace(s, foundation=facts, screening=_apply(s.screening, facts), signed=_apply(s.signed, facts))


# --- room for the steps -------------------------------------------------------------


def stair_hits(s: Any) -> list[dict[str, Any]]:
    """Where ``s``'s drawn steps have no room (:func:`stair_room_of`)."""
    return list(((getattr(s, "foundation", None) or {}).get("stair_room") or {}).get("hits") or ())


def _red(x: Any) -> bool:
    """Whether a view reads RED: on its triage, or on its colour -- a bind
    with a discretionary path round it (a ``fit_ft`` miss open to a variance)
    leaves the triage yellow and the colour red (fd8 bound: 47 NEAR-CAP and 2
    CLASS-UNREAD lots went red on a kept-room plan's variance miss, the triage
    read yellow, and :func:`reconciled` passed the red with no flag)."""
    from flats.score.screen import Triage

    return x.triage is Triage.red or x.colour is flag_plan.Colour.red


def next_room(s: Any) -> StairRoom | None:
    """The room to keep for the steps on ``s``'s next placement: what is
    kept now, widened to the worst unit's run on each kind its steps land on.
    None where it keeps no more than now, or :data:`STAIR_PASSES` placements
    have been tried: another would not find more."""
    hits = stair_hits(s)
    if not hits:
        return None
    cur = s.design.stairs or StairRoom()
    if cur.passes >= STAIR_PASSES:
        return None
    need = s.foundation["stair_room"]["need"]
    widened = {k: max(getattr(cur, k), float(need.get(k) or 0.0)) for k in _KEEP.values()}
    if all(widened[k] <= getattr(cur, k) + STAIR_TOL_FT for k in widened):
        return None
    return StairRoom(**widened, passes=cur.passes + 1)


def _hit_words(hits: Sequence[Mapping[str, Any]]) -> str:
    said = []
    for h in hits:
        where = {COURT: "onto the drawn parking court's stalls", LANE: "onto the drawn drive lane",
                 LOT_LINE: "past the lot line"}[h["hits"]]
        said.append(f"{h['door']}'s {h['risers']}-riser unit runs {h['run_ft']:.1f} ft out and lands "
                    f"{h['by_ft']:.1f} ft {where}")
    return "; ".join(said)


def no_room(s: Any, *, tried: str | None = None) -> Any:
    """``s`` RED on its steps' room: a bind on :data:`STAIR_CHECK` and
    :data:`STAIR_ROOM_FLAG` naming each door, what it lands on and by how
    much (Steph 2026-11-20, rulings.yaml 2026-11-20-stair-no-room-red-flag).
    A colour already red is left alone, so it is not attributed."""
    hits = stair_hits(s)
    if not hits:
        return s
    kept = s.design.stairs
    words = "foundation: no room for the steps -- " + _hit_words(hits)
    if kept is not None:
        words += (f" (placed {kept.passes + 1} times keeping up to {kept.court_ft:.1f} ft behind, "
                  f"{kept.flank_ft:.1f} ft beside and {kept.lot_ft:.1f} ft inside the lot)")
    if tried:
        words += f"; {tried}"
    worst = max(float(h["by_ft"]) for h in hits)

    def one(x: Any) -> Any:
        from flats.score.screen import Triage

        if _red(x) or any(b.check == STAIR_CHECK for b in x.binds):
            return x
        bind = flag_plan.Bind(STAIR_CHECK, worst, 0.0, worst, source=f"{words} -- {ROOM_RULING}")
        reasons = x.reasons if STAIR_ROOM in x.reasons else (*x.reasons, STAIR_ROOM)
        flags = x.flags if any(f.code == STAIR_ROOM_FLAG for f in x.flags) else (
            *x.flags, _flag(STAIR_ROOM_FLAG, STAIR_ROOM, words))
        return dataclasses.replace(x, triage=Triage.red, binds=(*x.binds, bind), flags=flags, reasons=tuple(reasons))

    room = {**s.foundation["stair_room"], "state": "no_room", "words": words}
    return dataclasses.replace(s, foundation={**s.foundation, "stair_room": room},
                               screening=one(s.screening), signed=one(s.signed))


_RANK = {"green": 0, "yellow": 1, "red": 2}


def _rank(x: Any) -> int:
    return _RANK[x.colour.value]


def reconciled(first: Any, alt: Any) -> Any:
    """The answer once ``alt`` -- ``first``'s plan stood again with room kept
    for the steps, through the whole screen -- is back.

    * ``alt`` red on its own steps' room: it, with its own flag.
    * ``alt`` red for anything else: ``first`` RED on its steps' room (the plan
      that leaves them room does not pass), the other reasons named.
    * Otherwise ``alt`` (its steps have room, or it would be red), and every
      view whose colour differs from ``first``'s carries
      :data:`STAIR_MOVED_FLAG` so the move is attributable: a better colour
      is held at ``first``'s, so nothing becomes GREEN that was not; a worse
      one reads as it is, the flag naming why (fd8 bound: 1,326 green ->
      yellow re-placements named nothing). A view red on the first placement
      stays as it read.

    ``first`` is the answer every search kept, capped once
    (:func:`flats.ingest.quadfit.foundation_checked`); ``alt`` is the whole
    screen again with room kept, capped once -- never an answer some outer
    search chose between after the cap had moved it (fd8 bound: a re-placed
    reading red on the steps sent 11E25AA02800 to the narrow-lane search,
    whose GREEN then stood).
    """
    if _red(alt.signed) or _red(alt.screening):
        if STAIR_ROOM in alt.signed.reasons or STAIR_ROOM in alt.screening.reasons:
            return alt
        why = ", ".join(dict.fromkeys(b.check for b in (*alt.signed.binds, *alt.screening.binds))) or "red"
        return no_room(first, tried=f"with room kept for them the plan is red ({why})")

    def held(x: Any, before: Any) -> Any:
        from flats.score.screen import Triage

        # A view already red on the first placement stays as it read: a
        # second placement never takes a red lot out of red.
        if _red(before):
            return before
        if _rank(x) == _rank(before) or any(f.code == STAIR_MOVED_FLAG for f in x.flags):
            return x
        better = _rank(x) < _rank(before)
        words = (f"foundation: the plan was stood again to leave the steps room and reads {x.colour.value} "
                 f"there; the first placement read {before.colour.value}"
                 + (", so it is held" if better else ", so the new placement's colour stands"))
        triage = Triage.yellow if better and x.triage is Triage.green else x.triage
        reasons = x.reasons if STAIR_MOVED in x.reasons else (*x.reasons, STAIR_MOVED)
        return dataclasses.replace(x, triage=triage, flags=(*x.flags, _flag(STAIR_MOVED_FLAG, STAIR_MOVED, words)),
                                   reasons=tuple(reasons))

    facts = dict(alt.foundation or {})
    if facts.get("stair_room") is not None:
        kept = alt.design.stairs
        facts["stair_room"] = {**facts["stair_room"], "state": "moved",
                               "kept": None if kept is None else kept.model_dump(),
                               "first_hits": stair_hits(first)}
    return dataclasses.replace(alt, foundation=facts, screening=held(alt.screening, first.screening),
                               signed=held(alt.signed, first.signed))


__all__ = [
    "CHECK",
    "CLASS_UNREAD_FLAG",
    "CLOSE_FLAG",
    "FOUNDATION_STEPS_CAP",
    "NEAR_FLAG",
    "REASONS",
    "ROW_COLUMN",
    "STAIR_CHECK",
    "STAIR_MOVED_FLAG",
    "STAIR_ROOM",
    "STAIR_ROOM_FLAG",
    "UNMEASURED_FLAG",
    "checked",
    "classes_of",
    "dem_of",
    "facts_for",
    "next_room",
    "no_room",
    "reconciled",
    "stair_hits",
    "stair_room_of",
    "standoff_of",
    "with_classes",
]
