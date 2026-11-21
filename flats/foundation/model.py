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

import math
from dataclasses import dataclass

from flats.foundation import cost as costing
from flats.foundation.ground import Ground
from flats.foundation.measure import (
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
    "The footing is modelled on a slope, not in steps: the real wall is taller by up to half a step.",
    "The crawlspace ground is left as it is, so the wall holds nothing back; if it is ever levelled the wall is a retaining wall and this model no longer applies.",
)

# flag codes (FD6 section 7)
WALL_OVER = "wall_over_standard"
FILL_OVER = "fill_over_limit"
EDGE_OVER = "edge_holds_back_over_limit"
GUARD = "guard_at_door"


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
    face: str  # "front" or "back"
    x_ft: float
    #: Floor level minus the ground at the door, inches.
    height_in: float
    #: Includes the step from the landing up through the door. Never capped [Steph].
    risers: int
    #: How far the stair runs out from the wall, inches.
    stair_run_in: float
    guard: bool
    handrail: bool
    rail_ft: float


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


def door_results(m: Measured, floor_above_high_in: float, s: Settings) -> tuple[DoorResult, ...]:
    """Every one of the eight doors, front then back, left to right.

    Rail: both sides of the stair plus the landing where the landing needs a
    guard; one side of the stair where it has a handrail only; else none.
    """
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
        out.append(DoorResult(door.face, door.x_ft, h, n, run, guard, handrail, rail))
    return tuple(out)


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


def _line(ln: LineMeasure, offset: float, show_offset: float, thickness: float, bars: int, over: bool, s: Settings) -> LineResult:
    walls = tuple(d + offset for d in ln.drops_in)
    steep = _steepest(ln)
    return LineResult(
        name=ln.name,
        kind=ln.kind,
        length_ft=ln.length_ft,
        walls_in=walls,
        tallest_in=ln.drop_max_in + offset,
        shortest_in=ln.drop_min_in + offset,
        average_in=ln.drop_mean_in + offset,
        showing_max_in=ln.drop_max_in + show_offset,
        showing_avg_in=ln.drop_mean_in + show_offset,
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
    for ln in m.lines:
        line_max = ln.drop_max_in + offset
        over = _over(line_max, s.plain_wall_max_in, s)
        stem = s.stem_party_in if ln.kind == "party" else s.stem_outside_in
        if over:
            stem = max(stem, s.engineered_stem_in)
        foot_w = {"long": s.footing_w_long_in, "end": s.footing_w_end_in, "party": s.footing_w_party_in}[ln.kind]
        footing = 0.0 if piles else _sqft(foot_w, s.footing_t_in)
        wall_area = ln.drop_area_ftin + offset * ln.length_ft  # sum of h x seg, ft x in
        conc_ft3 += footing * ln.length_ft + stem * wall_area / 144.0
        form += 2 * (wall_area + s.footing_t_in * ln.length_ft) / 12
        wall_len_h += wall_area
        bars = level_bars(line_max, s)
        level_ft += bars * ln.length_ft
        verts = ln.length_ft / s.vert_bar_spacing_ft + s.vert_bars_extra_per_line
        upright_ft += verts * (ln.drop_mean_in + offset + s.vert_bar_extra_in) / 12
        run += ln.length_ft
        wall_max = max(wall_max, line_max)
        if ln.outside:
            showing_max = max(showing_max, ln.drop_max_in + s.clear_in)
        results.append(_line(ln, offset, s.clear_in, stem, bars, over, s))
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
        simplifications=B_SIMPLIFICATIONS,
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
    for ln in m.lines:
        if not ln.outside:  # party lines are not deepened
            continue
        edge_ft3 += s.edge_extra_t_in * ln.drop_area_ftin / 144.0
        form += 2 * (ln.drop_area_ftin + s.edge_d_in * ln.length_ft) / 12
        edge_len_h += ln.drop_area_ftin + s.edge_d_in * ln.length_ft
        edge_run += ln.length_ft
        unbalanced_max = max(unbalanced_max, ln.drop_max_in)
        bars = level_bars(ln.drop_max_in + s.edge_d_in, s)
        level_ft += (bars - s.level_bars_base) * ln.length_ft
        if _over(ln.drop_max_in, s.uprights_fill_over_in, s):
            verts = ln.length_ft / s.vert_bar_spacing_ft + s.vert_bars_extra_per_line
            upright_ft += verts * (ln.drop_mean_in + s.edge_d_in + s.vert_bar_extra_in) / 12
        results.append(_line(ln, s.edge_d_in, s.slab_top_in, s.edge_w_in, bars, False, s))
    flags, words = [], []
    # fill measured to the slab's underside: fill + slab top - slab thickness (reference model)
    if _over(m.fill_max_in + s.slab_top_in - s.slab_t_in, s.fill_limit_in, s):
        flags.append(FILL_OVER)
        words.append(f"fill under the slab over {s.fill_limit_in:g} in: approved design")
    if _over(unbalanced_max, s.unbalanced_limit_in, s):
        flags.append(EDGE_OVER)
        words.append(f"edge holds back over {s.unbalanced_limit_in / 12:g} ft of fill: engineered wall")
    door_res = door_results(m, s.slab_top_in, s)
    _guard_flag(door_res, flags, words, s)
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
        simplifications=(),
    )
