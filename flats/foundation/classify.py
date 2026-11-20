"""PRICE layer, part 3: each lot in plain words -- foundation style, challenges, easy parts.

Derived from the stored record and the priced methods, with every threshold in the
``classify`` section of ``flats/config/foundation.yaml`` (mine are [est]). Codes
are few on purpose; each item carries the measured value that raised it, so a
list can be re-cut at another threshold without re-reading anything.

Never a colour: a challenge is a cost or a look, not a limit.
"""

from __future__ import annotations

from dataclasses import dataclass

from flats.foundation import model, support
from flats.foundation.measure import Measured
from flats.foundation.settings import Settings

# challenge codes
TALL_WALL = "tall_wall"
WALL_OVER_STANDARD = "wall_over_standard"
DEEP_FILL = "deep_fill"
RETAINED_EDGE = "retained_edge"
GUARDS = "guards_at_doors"
LONG_STAIR = "long_stair"
PILES = "soft_ground_piles"
OWN_LOOK = "own_look_ground"
NOT_SORTED = "ground_not_sorted"
COARSE = "coarse_ground_model"
FRONT_GUESS = "front_face_guess"
OLD_BUILDING = "old_building_later"
CHALLENGES = (TALL_WALL, WALL_OVER_STANDARD, DEEP_FILL, RETAINED_EDGE, GUARDS, LONG_STAIR, PILES, OWN_LOOK, NOT_SORTED, COARSE, FRONT_GUESS, OLD_BUILDING)

# easy-part codes
NEAR_FLAT = "near_flat"
LOW_WALLS = "walls_under_4ft"
NO_GUARDS = "no_guards"
ORDINARY = "ordinary_footing"
SHALLOW_FILL = "shallow_fill"
EASY = (NEAR_FLAT, LOW_WALLS, NO_GUARDS, ORDINARY, SHALLOW_FILL)


@dataclass(frozen=True, slots=True)
class Item:
    code: str
    #: The method it is about ("B", "B+P", "A"), or "" for the lot.
    method: str
    value: float | str | None
    unit: str
    words: str


@dataclass(frozen=True, slots=True)
class Style:
    #: The methods that are standard on this ground ("A", "B", "B+P").
    standard: tuple[str, ...]
    #: Cheaper of A (dry season) and B at low and at high prices, or None when
    #: only one method is standard here.
    cheaper_low: str | None
    cheaper_high: str | None
    words: str


def _a(method: str) -> str:
    return "A" if method.startswith("A") else method


def style(group: str, methods: dict[str, model.MethodResult], applicable: tuple[str, ...]) -> Style:
    standard = tuple(dict.fromkeys(_a(m) for m in applicable))
    lo = hi = None
    if "B" in applicable and "A dry" in applicable:
        a, b = methods["A dry"].cost, methods["B"].cost
        lo = "B" if b.low < a.low else "A"
        hi = "B" if b.high < a.high else "A"
    if group == support.ORDINARY:
        if lo == hi:
            cheap = f"{'B' if lo == 'B' else 'A (dry season)'} is cheaper at low and high prices"
        else:
            cheap = f"{lo} is cheaper at low prices, {hi} at high"
        words = f"Ordinary footing: slab on fill (A) or raised floor on a wall (B); {cheap}."
    elif group == support.PILES:
        words = "Soft or swelling ground: raised floor on a wall carried on screw piles (B+P); no slab."
    elif group == support.OWN_LOOK:
        words = "Ground that needs its own look (slide, liquefaction or flood): B shown for the record only."
    else:
        words = "Ground not sorted: B shown for the record only."
    return Style(standard, lo, hi, words)


def challenges(m: Measured, group: str, methods: dict[str, model.MethodResult], applicable: tuple[str, ...], s: Settings) -> tuple[Item, ...]:
    out: list[Item] = []
    on = [x for x in applicable if x != "A wet"]
    for name in on:
        r = methods[name]
        tag = _a(name)
        if tag in ("B", "B+P"):
            if r.tallest_wall_in > s.tall_wall_over_ft * 12 + s.tolerance_in:
                out.append(Item(TALL_WALL, tag, r.tallest_wall_in / 12, "ft", f"tallest wall {r.tallest_wall_in / 12:.1f} ft"))
            if model.WALL_OVER in r.flags:
                out.append(Item(WALL_OVER_STANDARD, tag, r.tallest_wall_in / 12, "ft", "a wall over the standard 8 ft: reinforced or engineered"))
        else:
            if model.FILL_OVER in r.flags:
                out.append(Item(DEEP_FILL, tag, r.fill_max_in, "in", f"fill up to {r.fill_max_in:.0f} in under the slab: approved fill design"))
            if model.EDGE_OVER in r.flags:
                held = r.tallest_wall_in - s.edge_d_in
                out.append(Item(RETAINED_EDGE, tag, held, "in", f"edge holds back {held / 12:.1f} ft of fill: engineered edge"))
        if r.guards >= s.guard_doors_min:
            out.append(Item(GUARDS, tag, r.guards, "doors", f"guard at {r.guards} of 8 doors"))
        if r.longest_stair_in > s.long_stair_over_ft * 12 + s.tolerance_in:
            out.append(Item(LONG_STAIR, tag, r.longest_stair_in / 12, "ft", f"a stair runs {r.longest_stair_in / 12:.1f} ft out from the wall"))
    cls = support.effective_class_of(m.ground_class, m.alt_ground_class)
    if group == support.PILES:
        out.append(Item(PILES, "", cls, "class", f"soft or swelling ground ({cls}): screw piles under the wall"))
    elif group == support.OWN_LOOK:
        out.append(Item(OWN_LOOK, "", cls, "class", f"ground class {cls}: needs its own look"))
    elif group == support.NOT_SORTED:
        out.append(Item(NOT_SORTED, "", cls, "class", "ground not sorted"))
    if m.cell_m is not None and m.cell_m > s.coarse_cell_over_m:
        out.append(Item(COARSE, "", m.cell_m, "m", f"ground read from {m.cell_m:g} m cells: relief understated"))
    if m.front_face_turn_deg is not None and m.front_face_turn_deg > s.front_face_guess_over_deg:
        out.append(Item(FRONT_GUESS, "", m.front_face_turn_deg, "deg", "which face carries the front doors is a guess"))
    if m.bldg_overlap_share is not None and m.bldg_overlap_share >= s.old_building_share_min:
        out.append(
            Item(OLD_BUILDING, "", m.bldg_overlap_share, "share", f"{m.bldg_overlap_share:.0%} of the pod over a building standing today (basement exposure sized later)")
        )
    return tuple(out)


def easy_parts(m: Measured, group: str, methods: dict[str, model.MethodResult], applicable: tuple[str, ...], s: Settings) -> tuple[Item, ...]:
    out: list[Item] = []
    relief = m.low_drop_in / 12
    if relief <= s.near_flat_relief_ft + s.tolerance_in / 12:
        out.append(Item(NEAR_FLAT, "", relief, "ft", f"near flat under the building ({relief:.1f} ft of fall)"))
    if group == support.ORDINARY:
        out.append(Item(ORDINARY, "", support.effective_class_of(m.ground_class, m.alt_ground_class), "class", "ordinary footing ground"))
    for name in (x for x in applicable if x != "A wet"):
        r = methods[name]
        tag = _a(name)
        if tag in ("B", "B+P") and r.tallest_wall_in <= s.low_wall_max_ft * 12 + s.tolerance_in:
            out.append(Item(LOW_WALLS, tag, r.tallest_wall_in / 12, "ft", f"every wall {s.low_wall_max_ft:g} ft or under"))
        if tag == "A" and r.fill_max_in <= s.shallow_fill_max_in + s.tolerance_in:
            out.append(Item(SHALLOW_FILL, tag, r.fill_max_in, "in", f"fill {r.fill_max_in:.0f} in or less under the slab"))
        if r.guards == 0:
            out.append(Item(NO_GUARDS, tag, 0, "doors", "no guard at any door"))
    return tuple(out)
