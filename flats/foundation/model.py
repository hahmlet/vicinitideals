"""PRICE layer, part 1: the two foundations from a measured record (FD6 sections 5.2-5.6).

* **B, raised floor on a wall** (:func:`raised`): one concrete wall on a strip
  footing under the outside and the party lines, level on top; the floor of
  twelve factory cassettes sits on it. With ``piles=True`` it is **B+P**
  (section 5.7): the footing concrete is dropped and screw piles carry the wall.
* **A, slab on fill** (:func:`slab`): a 4 in slab with a turned-down edge,
  set 8 in above the highest ground; the low side is built up in rock behind a
  deeper edge. ``wet=True`` is the wet-season switch: only the flat-lot rock
  and haul lines change.

Both take a :class:`~flats.foundation.measure.Measured` record (or a ground,
which is measured first). Everything here is the record's drops plus settings:
B wall = drop + clear + footing depth - footing thickness; B door = drop +
clear + floor depth; A edge = drop + edge depth; A door = drop + slab top. So a
price, size or threshold change re-prices stored records without the ground.

Footing depth is per lot (:func:`embed_of`): with ``use_frost_register`` the
lot's own frost-register depth (stored in the record) replaces ``embed_in`` for
B's wall and dig and A's edge depth and edge dig (:func:`lot_settings`); the FD6
section 8 reference is ``use_frost_register: false``.

Quantities are kept before and after their factors (over-order, laps) so the
factors can be re-tuned. Two simplifications, both slightly generous, are
stated on every B result (:data:`B_SIMPLIFICATIONS`).
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass

from flats.foundation import cost as costing
from flats.foundation.ground import Ground
from flats.foundation.measure import (
    DoorMeasure,
    LineMeasure,
    Measured,
    WallLine,
    geometry_of,
    measure,
    stations,
    wall_lines,
)
from flats.foundation.settings import Settings

__all__ = ["WallLine", "wall_lines", "stations", "raised", "slab", "risers_at", "door_results"]

FT3_PER_YD3 = 27.0

B_SIMPLIFICATIONS = (
    "The crawlspace ground is left as it is, so the wall holds nothing back; if it is ever levelled the wall is a retaining wall and this model no longer applies.",
)
#: Said where ``stepped_footing`` is off (the answer keys): the FD6 slope.
SLOPED_FOOTING = "The footing is modelled on a slope, not in steps: the real wall is taller by up to half a step."

# flag codes (FD6 section 7)
WALL_OVER = "wall_over_standard"
FILL_OVER = "fill_over_limit"
EDGE_OVER = "edge_holds_back_over_limit"
GUARD = "guard_at_door"
#: FD8 2a: a door needs more than ``cap_risers`` unit risers: the method is not used here.
OVER_CAP = "over_six_step_cap"
#: FD8 2b: engineered, not priced by this model (a stop, not a colour).
ENGINEERED = "engineered_not_priced"
#: FD8 2d: B on piles is designed (R403.1.2): priced, flagged.
PILES_ENGINEERED = "piles_engineered"


def _yd3(ft3: float) -> float:
    return ft3 / FT3_PER_YD3


def _sqft(width_in: float, depth_in: float) -> float:
    return width_in * depth_in / 144.0


def _over(value: float, limit: float, s: Settings) -> bool:
    """value > limit, by more than the numerical tolerance."""
    return value > limit + s.tolerance_in


def _record(src: Measured | Ground, s: Settings) -> Measured:
    if isinstance(src, Measured):
        have, want = dict(src.geometry), dict(geometry_of(s))
        if have != want:
            changed = sorted(k for k in have.keys() | want.keys() if have.get(k) != want.get(k))
            raise ValueError(f"record measured under other geometric settings ({', '.join(changed)}): re-measure")
        return src
    return measure(src, s)


def embed_of(m: Measured, s: Settings) -> float:
    """The lot's footing depth (in): its frost-register depth when
    ``use_frost_register`` and the record holds one, else ``embed_in``."""
    if s.use_frost_register and m.frost_register_in is not None and m.frost_register_in > 0:
        return float(m.frost_register_in)
    return s.embed_in


def _with_embed(s: Settings, embed_in: float) -> Settings:
    # A's edge is footing depth + slab top (edge_d_in's source): it moves with the footing.
    # Not cached: Settings compare without their prices, so a cache keyed on them
    # would hand back another file's prices.
    return s.replace(embed_in=embed_in, edge_d_in=s.edge_d_in + embed_in - s.embed_in)


def lot_settings(m: Measured, s: Settings) -> Settings:
    """The settings as they apply on this lot (its own footing depth)."""
    e = embed_of(m, s)
    return s if e == s.embed_in else _with_embed(s, e)


# ---------------------------------------------------------------- results


@dataclass(frozen=True, slots=True)
class LineResult:
    """One wall line for one method. B: wall = footing top to wall top; A (outside
    lines only): edge = footing bottom to slab top."""

    name: str
    kind: str
    length_ft: float
    #: Wall (B) or edge (A) height at every station, inches.
    walls_in: tuple[float, ...]
    tallest_in: float
    shortest_in: float
    average_in: float
    showing_max_in: float
    showing_avg_in: float
    #: Length (ft) of wall whose height falls in each band of ``wall_bands_ft``
    #: (up to the first edge, ..., over the last).
    band_length_ft: tuple[float, ...]
    #: B: wall thickness used on this line (thicker over the standard wall);
    #: A: the edge width.
    thickness_in: float
    level_bars: int
    #: B: tallest point over the standard wall: not the standard wall.
    over_standard: bool
    #: Steepest fall of the ground between neighbouring stations (rise/run).
    steepest_slope: float
    #: Over ``footing_max_slope`` the real footing must step [code R403.1.5].
    #: Info only: the model keeps the footing on a slope (FD6 section 5.3).
    footing_steps: bool


@dataclass(frozen=True, slots=True)
class DoorResult:
    face: str  # "front" or "back" door
    x_ft: float
    #: Floor level minus the ground at the door (the wall), inches.
    height_in: float
    #: Includes the step from the landing up through the door: the unit's
    #: risers plus that one step (FD8 2a), 1 at a step pad.
    risers: int
    #: How far the stair runs out from the wall, inches.
    stair_run_in: float
    guard: bool
    handrail: bool
    #: Feet of rail (the per-riser rule only; 0 under the precast rule).
    rail_ft: float
    #: The precast unit's risers k (0 = no unit, a step pad); None under the
    #: per-riser rule. Over ``cap_risers`` the door is over the cap.
    units: int | None = None
    #: Floor level above the ground the cap is tested on: the highest of the
    #: wall and the foot of every unit tried (FD8 2d), inches.
    cap_height_in: float | None = None
    #: Railing sides on the unit (FD8 2a): 1 at four risers, 2 with a guard.
    rail_sides: int = 0
    over_cap: bool = False
    #: The platform's height above the lowest ground in the guard box (in).
    platform_in: float | None = None

    def over_by_in(self, cap_in: float) -> float:
        """How far the floor is over (+) or under (-) the cap at this door."""
        h = self.cap_height_in if self.cap_height_in is not None else self.height_in
        return h - cap_in


@dataclass(frozen=True)
class MethodResult:
    """One foundation on one lot: everything FD6 section 2 items 1-7 lists."""

    method: str  # "B", "B+P", "A dry", "A wet"
    floor_above_high_in: float
    floor_above_low_in: float
    lines: tuple[LineResult, ...]
    tallest_wall_in: float
    average_wall_in: float
    showing_max_in: float
    # quantities before their factors, the factors, and after
    concrete_net_yd3: float
    concrete_waste: float
    concrete_yd3: float
    level_bar_ft_net: float
    lap: float
    upright_bar_ft: float
    bar_lb_per_ft: float
    bars_lb: float
    form_sf: float
    fill_ton: float
    fill_max_in: float
    doors: tuple[DoorResult, ...]
    piles: int
    cost: costing.Cost
    flags: tuple[str, ...]
    flag_words: tuple[str, ...]
    simplifications: tuple[str, ...]
    #: A door needs more than ``cap_risers`` unit risers (FD8 2a): the method
    #: is not used on this lot and its cost is not shown.
    over_cap: bool = False
    #: Engineered, not priced by this model (FD8 2b), in words; None = priced.
    stop: str | None = None

    @property
    def usable(self) -> bool:
        """Under the cap and not stopped: the method is open, its cost shown."""
        return not self.over_cap and self.stop is None

    def worst_door(self) -> DoorResult:
        """The door whose floor stands highest over the ground the cap is tested on."""
        return max(self.doors, key=lambda d: d.cap_height_in if d.cap_height_in is not None else d.height_in)

    @property
    def risers_total(self) -> int:
        return sum(d.risers for d in self.doors)

    @property
    def risers_least(self) -> int:
        return min(d.risers for d in self.doors)

    @property
    def risers_most(self) -> int:
        return max(d.risers for d in self.doors)

    @property
    def longest_stair_in(self) -> float:
        return max(d.stair_run_in for d in self.doors)

    @property
    def highest_door_in(self) -> float:
        return max(d.height_in for d in self.doors)

    @property
    def guards(self) -> int:
        return sum(1 for d in self.doors if d.guard)

    @property
    def rail_ft(self) -> float:
        return sum(d.rail_ft for d in self.doors)


# ---------------------------------------------------------------- doors (5.5)


def risers_at(height_in: float, s: Settings) -> int:
    """risers = the larger of 1 and roundup((H - landing drop) / riser) + 1."""
    n = (height_in - s.landing_drop_in) / s.riser_in
    tol = s.tolerance_in / s.riser_in
    return max(1, math.ceil(n - tol) + 1)


def units_at(height_in: float, s: Settings) -> int:
    """FD8 2a: k = (H - 8) / 7.25 rounded up, at least 1 (H over the step in)."""
    tol = s.tolerance_in / s.riser_in
    return max(1, math.ceil((height_in - s.landing_drop_in) / s.riser_in - tol))


def unit_run_in(k: int, s: Settings) -> float:
    """How far a k-riser unit runs out from the wall: the 42 in platform and
    11 in a riser after the first (FD8 2a, 2d)."""
    return s.landing_depth_in + max(0, k - 1) * s.tread_in


def _unit_door(door: DoorMeasure, floor_above_high_in: float, s: Settings) -> DoorResult:
    """One door under the precast rule (FD8 2a), with the ground where the
    stair lands and the guard box (FD8 2d) where those are switched on."""
    h = floor_above_high_in + door.drop_in
    if h <= s.landing_drop_in + s.tolerance_in:
        return DoorResult(door.face, door.x_ft, h, 1, s.landing_depth_in, False, False, 0.0,
                          units=0, cap_height_in=h, rail_sides=0, over_cap=False, platform_in=None)
    test = h
    k = units_at(h, s)
    foot_drop = door.drop_in
    if s.stair_ground and door.out_drops_in:
        while k <= s.cap_risers:
            foot_drop = door.drop_at(unit_run_in(k, s), s.station_ft)
            at_foot = floor_above_high_in + foot_drop
            test = max(test, at_foot)
            need = units_at(at_foot, s)
            if need <= k:
                break
            k = need
    over = k > s.cap_risers
    platform = k * s.riser_in
    if s.guard_box and door.box_drop_in is not None:
        # the unit stands on the lower of the ground at the wall and at its foot (the
        # larger drop, the ground its height was tested on), so its platform is never
        # above the threshold it serves where the ground rises away from the door (FD9 2)
        base = test - floor_above_high_in
        platform = max(platform, platform + door.box_drop_in - base)
    guard = (not over) and _over(platform, s.guard_over_in, s)
    handrail = k >= s.handrail_risers
    sides = 0 if over else 2 if guard else 1 if handrail else 0
    return DoorResult(door.face, door.x_ft, h, k + 1, unit_run_in(k, s), guard, handrail, 0.0,
                      units=k, cap_height_in=test, rail_sides=sides, over_cap=over, platform_in=platform)


def door_results(m: Measured, floor_above_high_in: float, s: Settings) -> tuple[DoorResult, ...]:
    """Every one of the eight doors, front then back, left to right.

    ``steps_rule: precast`` (FD8 2a): one precast unit a door, :func:`_unit_door`.
    ``per_riser`` (the rule before FD8, the ``--as-flats-built`` override): rail
    both sides of the stair plus the landing where the landing needs a guard,
    one side where it has a handrail only, else none; never capped.
    """
    if s.steps_rule == "precast":
        return tuple(_unit_door(door, floor_above_high_in, s) for door in m.doors)
    out = []
    for door in m.doors:
        h = floor_above_high_in + door.drop_in
        n = risers_at(h, s)
        run = s.landing_depth_in + max(0, n - 2) * s.tread_in
        guard = _over(h - s.landing_drop_in, s.guard_over_in, s)
        handrail = n >= s.handrail_risers
        if guard:
            rail = (2 * run + s.landing_depth_in) / 12
        elif handrail:
            rail = run / 12
        else:
            rail = 0.0
        out.append(DoorResult(door.face, door.x_ft, h, n, run, guard, handrail, rail, cap_height_in=h))
    return tuple(out)


def door_name(d: DoorResult, doors) -> str:
    """'front door 2': the second front door from the left, as the plan reads."""
    same = [x for x in doors if x.face == d.face]
    return f"{d.face} door {same.index(d) + 1}"


def _cap(door_res, flags: list[str], words: list[str], s: Settings) -> bool:
    """FD8 2a: the method is over the cap where any door needs more than six
    unit risers. Names the worst door and by how much."""
    over = [d for d in door_res if d.over_cap]
    if not over:
        return False
    worst = max(over, key=lambda d: d.cap_height_in)
    flags.append(OVER_CAP)
    words.append(
        f"door needs more than {s.cap_risers} steps: {door_name(worst, door_res)} is "
        f"{worst.cap_height_in:.1f} in above the ground, {worst.over_by_in(s.cap_in):.1f} in over the "
        f"{s.cap_in:g} in cap (not used on this lot)"
    )
    return True


def level_bars(tallest_in: float, s: Settings) -> int:
    """Footing bar and top bar [code R403.1.3.1]; a third over 4 ft and a fourth
    over 8 ft [est; Table R404.1.2(1) not opened]."""
    n = s.level_bars_base
    n += 1 if _over(tallest_in, s.level_bar_third_over_in, s) else 0
    n += 1 if _over(tallest_in, s.level_bar_fourth_over_in, s) else 0
    return n


def _bands(walls: tuple[float, ...], seg: float, s: Settings) -> tuple[float, ...]:
    edges = [e * 12 for e in s.wall_bands_ft]
    out = [0.0] * (len(edges) + 1)
    for w in walls:
        k = next((i for i, e in enumerate(edges) if w <= e + s.tolerance_in), len(edges))
        out[k] += seg
    return tuple(out)


def _steepest(ln: LineMeasure) -> float:
    seg = ln.length_ft / len(ln.drops_in)
    return max((abs(b - a) / 12 / seg for a, b in zip(ln.drops_in, ln.drops_in[1:])), default=0.0)


def stepped(ln: LineMeasure, s: Settings) -> LineMeasure:
    """The line as the stepped footing sees it (FD8 2d, [code R403.1.5]): where
    the line's fall is one step or less every station takes the line's tallest
    wall; where it is more, every station takes half a step more wall. The
    line as measured where ``stepped_footing`` is off (the FD6 slope)."""
    if not s.stepped_footing:
        return ln
    n = len(ln.drops_in)
    if ln.drop_max_in - ln.drop_min_in <= s.footing_step_in + s.tolerance_in:
        drops = (ln.drop_max_in,) * n
    else:
        drops = tuple(d + s.footing_step_in / 2 for d in ln.drops_in)
    seg = ln.length_ft / n
    return dataclasses.replace(
        ln,
        drops_in=drops,
        drop_max_in=max(drops),
        drop_min_in=min(drops),
        drop_mean_in=sum(drops) / n,
        drop_area_ftin=sum(drops) * seg,
    )


def _line(ln: LineMeasure, offset: float, show_offset: float, thickness: float, bars: int, over: bool, s: Settings,
          raw: LineMeasure | None = None) -> LineResult:
    raw = raw or ln
    walls = tuple(d + offset for d in ln.drops_in)
    steep = _steepest(raw)
    return LineResult(
        name=ln.name,
        kind=ln.kind,
        length_ft=ln.length_ft,
        walls_in=walls,
        tallest_in=ln.drop_max_in + offset,
        shortest_in=ln.drop_min_in + offset,
        average_in=ln.drop_mean_in + offset,
        showing_max_in=raw.drop_max_in + show_offset,
        showing_avg_in=raw.drop_mean_in + show_offset,
        band_length_ft=_bands(walls, ln.length_ft / len(walls), s),
        thickness_in=thickness,
        level_bars=bars,
        over_standard=over,
        steepest_slope=steep,
        footing_steps=steep > s.footing_max_slope,
    )


def _guard_flag(door_res, flags: list[str], words: list[str], s: Settings) -> None:
    n = sum(1 for d in door_res if d.guard)
    if n:
        flags.append(GUARD)
        words.append(f"guard at {n} door{'s' if n != 1 else ''}: landing over {s.guard_over_in:g} in up (cost and look, not a limit)")


# ---------------------------------------------------------------- B (5.2-5.4)


def raised(src: Measured | Ground, s: Settings, *, piles: bool = False) -> MethodResult:
    """B (or B+P with ``piles``): one concrete wall, top level, raised cassette floor."""
    m = _record(src, s)
    s = lot_settings(m, s)
    offset = s.clear_in + s.embed_in - s.footing_t_in  # wall = drop + offset
    floor_above_high = s.clear_in + s.floor_depth_in
    conc_ft3 = level_ft = upright_ft = form = 0.0
    run = wall_len_h = 0.0
    wall_max = showing_max = 0.0
    results = []
    storey_ft = outside_ft = 0.0
    storey_any = False
    for raw in m.lines:
        ln = stepped(raw, s)
        line_max = ln.drop_max_in + offset
        over = _over(line_max, s.plain_wall_max_in, s)
        stem = s.stem_party_in if ln.kind == "party" else s.stem_outside_in
        if over:
            stem = max(stem, s.engineered_stem_in)
        if piles:
            stem = max(stem, s.piles_stem_in)
        if raw.outside:  # FD8 2b storey rule: the floor above the ground along the outside walls
            seg = raw.length_ft / len(raw.drops_in)
            outside_ft += raw.length_ft
            for d in raw.drops_in:
                above = floor_above_high + d
                if _over(above, s.storey_floor_over_in, s):
                    storey_ft += seg
                if _over(above, s.storey_floor_any_over_in, s):
                    storey_any = True
        foot_w = {"long": s.footing_w_long_in, "end": s.footing_w_end_in, "party": s.footing_w_party_in}[ln.kind]
        footing = 0.0 if piles else _sqft(foot_w, s.footing_t_in)
        wall_area = ln.drop_area_ftin + offset * ln.length_ft  # sum of h x seg, ft x in
        conc_ft3 += footing * ln.length_ft + stem * wall_area / 144.0
        form += 2 * (wall_area + s.footing_t_in * ln.length_ft) / 12
        wall_len_h += wall_area
        bars = level_bars(line_max, s)
        if piles:
            bars = max(bars, s.piles_level_bars_min)
        level_ft += bars * ln.length_ft
        verts = ln.length_ft / s.vert_bar_spacing_ft + s.vert_bars_extra_per_line
        upright_ft += verts * (ln.drop_mean_in + offset + s.vert_bar_extra_in) / 12
        run += ln.length_ft
        wall_max = max(wall_max, line_max)
        if ln.outside:
            showing_max = max(showing_max, raw.drop_max_in + s.clear_in)
        results.append(_line(ln, offset, s.clear_in, stem, bars, over, s, raw))
    door_res = door_results(m, floor_above_high, s)
    concrete_net = _yd3(conc_ft3)
    concrete = concrete_net * s.concrete_waste
    bars_lb = (level_ft * s.lap + upright_ft) * s.bar_lb_per_ft
    spoil = _yd3(_sqft(s.trench_w_in, s.embed_in) * run)
    flags, words = [], []
    if _over(wall_max, s.plain_wall_max_in, s):
        flags.append(WALL_OVER)
        words.append(f"wall over {s.plain_wall_max_in / 12:g} ft: not the standard wall")
    _guard_flag(door_res, flags, words, s)
    if piles:
        flags.append(PILES_ENGINEERED)
        words.append("engineered: a wall on piles is designed by an engineer [code R403.1.2] (priced here as a working figure)")
    stop = None
    if _over(wall_max, s.engineered_wall_over_in, s):
        stop = f"engineered, not priced by this model: wall over {s.engineered_wall_over_in / 12:g} ft"
    elif storey_any or (outside_ft and storey_ft > s.storey_share * outside_ft + s.tolerance_in / 12):
        stop = (f"engineered, not priced by this model: the floor is a storey above the ground (over "
                f"{s.storey_floor_over_in / 12:g} ft on more than half the outside wall, or over "
                f"{s.storey_floor_any_over_in / 12:g} ft anywhere)")
    if stop is not None:
        flags.append(ENGINEERED)
        words.append(stop)
    over_cap = _cap(door_res, flags, words, s)
    n_piles = s.piles_per_pod if piles else 0
    cost = costing.raised_cost(
        s,
        concrete_yd3=concrete,
        bars_lb=bars_lb,
        form_sf=form,
        haul_yd3=spoil * s.haul_share,
        door_res=door_res,
        piles=n_piles,
    )
    return MethodResult(
        method="B+P" if piles else "B",
        floor_above_high_in=floor_above_high,
        floor_above_low_in=floor_above_high + m.low_drop_in,
        lines=tuple(results),
        tallest_wall_in=wall_max,
        average_wall_in=wall_len_h / run,
        showing_max_in=showing_max,
        concrete_net_yd3=concrete_net,
        concrete_waste=s.concrete_waste,
        concrete_yd3=concrete,
        level_bar_ft_net=level_ft,
        lap=s.lap,
        upright_bar_ft=upright_ft,
        bar_lb_per_ft=s.bar_lb_per_ft,
        bars_lb=bars_lb,
        form_sf=form,
        fill_ton=0.0,
        fill_max_in=0.0,
        doors=door_res,
        piles=n_piles,
        cost=cost,
        flags=tuple(flags),
        flag_words=tuple(words),
        simplifications=B_SIMPLIFICATIONS if s.stepped_footing else (SLOPED_FOOTING, *B_SIMPLIFICATIONS),
        over_cap=over_cap,
        stop=stop,
    )


# ---------------------------------------------------------------- A (5.6)


def slab(src: Measured | Ground, s: Settings, *, wet: bool = False) -> MethodResult:
    """A: slab set above the highest ground, low side built up in rock behind a deeper edge."""
    m = _record(src, s)
    s = lot_settings(m, s)
    edge_ft3 = form = level_ft = upright_ft = 0.0
    unbalanced_max = 0.0
    edge_len_h = edge_run = 0.0
    results = []
    for raw in m.lines:
        if not raw.outside:  # party lines are not deepened
            continue
        ln = stepped(raw, s)
        edge_ft3 += s.edge_extra_t_in * ln.drop_area_ftin / 144.0
        form += 2 * (ln.drop_area_ftin + s.edge_d_in * ln.length_ft) / 12
        edge_len_h += ln.drop_area_ftin + s.edge_d_in * ln.length_ft
        edge_run += ln.length_ft
        unbalanced_max = max(unbalanced_max, raw.drop_max_in)
        bars = level_bars(ln.drop_max_in + s.edge_d_in, s)
        level_ft += (bars - s.level_bars_base) * ln.length_ft
        if _over(raw.drop_max_in, s.uprights_fill_over_in, s):
            verts = ln.length_ft / s.vert_bar_spacing_ft + s.vert_bars_extra_per_line
            upright_ft += verts * (ln.drop_mean_in + s.edge_d_in + s.vert_bar_extra_in) / 12
        results.append(_line(ln, s.edge_d_in, s.slab_top_in, s.edge_w_in, bars, False, s, raw))
    flags, words = [], []
    # fill to the slab's underside: fill + slab top - slab thickness (reference
    # model); with the strip soil, all the rock placed on the stripped ground (FD8 2d)
    strip = s.strip_soil_in if s.fill_flag_with_strip else 0.0
    if _over(m.fill_max_in + strip + s.slab_top_in - s.slab_t_in, s.fill_limit_in, s):
        flags.append(FILL_OVER)
        words.append(f"fill under the slab over {s.fill_limit_in:g} in: approved design")
    stop = None
    if _over(unbalanced_max, s.unbalanced_limit_in, s):
        flags.append(EDGE_OVER)
        words.append(f"edge holds back over {s.unbalanced_limit_in / 12:g} ft of fill: engineered wall")
        # FD8 2b [code R404.1.1 item 2, R404.1.3.2.2 item 2]: a stop, never red
        stop = f"engineered, not priced by this model: the slab edge holds back over {s.unbalanced_limit_in / 12:g} ft of fill"
        flags.append(ENGINEERED)
    door_res = door_results(m, s.slab_top_in, s)
    _guard_flag(door_res, flags, words, s)
    over_cap = _cap(door_res, flags, words, s)
    fill_ton = _yd3(m.fill_volume_ft3) * s.rock_ton_per_yd3
    flat = costing.flat_lot(s)
    conc_extra_net = _yd3(edge_ft3)
    conc_extra = conc_extra_net * s.concrete_waste
    extra_bars_lb = (level_ft * s.lap + upright_ft) * s.bar_lb_per_ft
    cost = costing.slab_cost(
        s,
        wet=wet,
        fill_ton=fill_ton,
        conc_extra_yd3=conc_extra,
        extra_bars_lb=extra_bars_lb,
        form_sf=form,
        door_res=door_res,
    )
    return MethodResult(
        method="A wet" if wet else "A dry",
        floor_above_high_in=s.slab_top_in,
        floor_above_low_in=s.slab_top_in + m.low_drop_in,
        lines=tuple(results),
        tallest_wall_in=unbalanced_max + s.edge_d_in,
        average_wall_in=edge_len_h / edge_run,
        showing_max_in=unbalanced_max + s.slab_top_in,
        concrete_net_yd3=flat.slab_concrete_net_yd3 + conc_extra_net,
        concrete_waste=s.concrete_waste,
        concrete_yd3=flat.slab_concrete_yd3 + conc_extra,
        level_bar_ft_net=flat.slab_level_bar_ft_net + level_ft,
        lap=s.lap,
        upright_bar_ft=upright_ft,
        bar_lb_per_ft=s.bar_lb_per_ft,
        bars_lb=flat.slab_bars_lb + extra_bars_lb,
        form_sf=form,
        fill_ton=fill_ton,
        fill_max_in=m.fill_max_in,
        doors=door_res,
        piles=0,
        cost=cost,
        flags=tuple(flags),
        flag_words=tuple(words),
        simplifications=() if s.stepped_footing else (SLOPED_FOOTING,),
        over_cap=over_cap,
        stop=stop,
    )
