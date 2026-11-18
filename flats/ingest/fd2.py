"""Foundation screen, pass 1: measure and summarise (FOLLOWUPS 199, FD2).

A report only. For every GREEN lot of a live run it measures, on the
building exactly where the live fit drew it (80 ft x 25 ft finished outside
dimension, owner 2026-11-18), the ground under it, the soil survey and the
mapped hazards there, and a few facts by place; then sorts each lot into the
FD2 hand-off's provisional relief class and ground class. Nothing here feeds
the screen: it changes no colour, reason, flag, drawing or page.

The pure measures live here (unit-tested in ``flats/tests/test_fd2.py``); the
run that reads the elevation model, the soil survey and the hazard extract
is ``scripts/flats_fd2_pass1.py``.

Every missing input stays missing (None), never zero.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

#: Feet per metre (international foot), for elevations read in metres.
FT_PER_M = 3.280839895013123
#: Centimetres per foot.
CM_PER_FT = 30.48
#: The soil layer the hand-off asks about: 1 to 5 ft below the surface.
LAYER_TOP_CM = 1 * CM_PER_FT
LAYER_BOT_CM = 5 * CM_PER_FT
#: Ground class cut-offs, as the hand-off prints them (sorting only).
BEDROCK_CM = 5 * CM_PER_FT
COBBLE_PCT = 15.0
SWELL_LEP = 6.0
WET_CM = 2 * CM_PER_FT
PAN_CM = 3.5 * CM_PER_FT
#: Spacing of the ground samples, feet.
SAMPLE_FT = 1.0
#: A side whose mean differs from the opposite side by no more than this is "level".
LEVEL_FT = 0.1
#: A side's mean is read only when at least this share of its samples has ground.
MIN_SIDE_SHARE = 0.8

RELIEF_BINS: tuple[tuple[float, str], ...] = (
    (1.0, "0-1"), (2.0, "1-2"), (3.0, "2-3"), (4.0, "3-4"), (6.0, "4-6"), (8.0, "6-8"),
)
RELIEF_OVER = "over 8"
RELIEF_ORDER = (*(label for _, label in RELIEF_BINS), RELIEF_OVER, "missing")

GROUND_ORDER = ("HAZ-SLIDE", "HAZ-LIQ", "FLOOD", "NO-DATA", "ROCK", "COBBLE", "SWELL", "SOFT", "WET-FINE", "FIRM")

#: Drainage classes that sort a lot WET-FINE. The hand-off names "poorly or
#: somewhat poorly drained"; "very poorly drained" is wetter still and is
#: taken with them (choices made).
WET_DRAINAGE = frozenset({"Very poorly drained", "Poorly drained", "Somewhat poorly drained"})
#: Unified classes the hand-off calls organic.
ORGANIC_UNIFIED = frozenset({"OL", "OH", "PT"})
#: Restrictive-layer kinds that are bedrock.
BEDROCK_KINDS = frozenset({"Lithic bedrock", "Paralithic bedrock", "Densic bedrock"})
#: Restrictive-layer kinds read as a "hardpan (fragipan or similar, not
#: bedrock)" for the PAN yes/no. A textural change or salt layer is not a pan.
PAN_KINDS = frozenset({
    "Fragipan", "Duripan", "Densic material", "Cemented horizon", "Ortstein",
    "Petrocalcic", "Petroferric", "Petrogypsic", "Placic",
})


# --- the footprint ---------------------------------------------------------------


Seg = tuple[float, float, float, float]


@dataclass(frozen=True)
class Frame:
    """The drawn building as four named corners.

    ``front`` is the long side nearer the street lot lines (where the front
    doors face); left and right are as seen from the street, looking at the
    building. ``front_known`` is False when no street line was traced (the
    first long side is then called front).
    """

    fl: tuple[float, float]
    fr: tuple[float, float]
    bl: tuple[float, float]
    br: tuple[float, float]
    long_ft: float
    short_ft: float
    front_known: bool

    def at(self, u: Any, v: Any) -> np.ndarray:
        """Points at ``u`` (0 left .. 1 right) and ``v`` (0 front .. 1 back)."""
        u = np.asarray(u, dtype=float)
        v = np.asarray(v, dtype=float)
        fl, fr, bl = (np.array(p, dtype=float) for p in (self.fl, self.fr, self.bl))
        along = fr - fl
        across = bl - fl
        return fl + u[..., None] * along + v[..., None] * across


def _dist_to_lines(x: float, y: float, lines: Sequence[Seg]) -> float:
    best = math.inf
    for x1, y1, x2, y2 in lines:
        dx, dy = x2 - x1, y2 - y1
        n = dx * dx + dy * dy
        t = 0.0 if n == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / n))
        best = min(best, math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)))
    return best


def frame(ring: Sequence[Sequence[float]], streets: Sequence[Seg]) -> Frame:
    """Name the corners of a drawn rectangle (closed or open ring)."""
    pts = [(float(p[0]), float(p[1])) for p in ring]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) != 4:
        raise ValueError(f"the building ring has {len(pts)} corners, not 4")
    sides = [(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    lengths = [math.dist(a, b) for a, b in sides]
    # The two long sides: 0/2 or 1/3.
    first = 0 if lengths[0] + lengths[2] >= lengths[1] + lengths[3] else 1
    long_sides = [sides[first], sides[first + 2]]
    long_ft = (lengths[first] + lengths[first + 2]) / 2
    short_ft = (lengths[first + 1] + lengths[(first + 3) % 4]) / 2
    front_known = bool(streets)
    if front_known:
        mids = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in long_sides]
        d = [_dist_to_lines(mx, my, streets) for mx, my in mids]
        front, back = (long_sides[0], long_sides[1]) if d[0] <= d[1] else (long_sides[1], long_sides[0])
    else:
        front, back = long_sides
    fa, fb = np.array(front[0]), np.array(front[1])
    fmid = (fa + fb) / 2
    bmid = (np.array(back[0]) + np.array(back[1])) / 2
    inward = bmid - fmid
    # Facing the building from the street is facing ``inward``; left of that
    # is ``inward`` turned a quarter anticlockwise.
    left = np.array([-inward[1], inward[0]])
    if float(np.dot(fa - fmid, left)) >= 0:
        fl, fr = fa, fb
    else:
        fl, fr = fb, fa
    ba, bb = np.array(back[0]), np.array(back[1])
    bl, br = (ba, bb) if float(np.dot(ba - fl, fr - fl)) < float(np.dot(bb - fl, fr - fl)) else (bb, ba)
    return Frame(
        fl=(float(fl[0]), float(fl[1])), fr=(float(fr[0]), float(fr[1])),
        bl=(float(bl[0]), float(bl[1])), br=(float(br[0]), float(br[1])),
        long_ft=float(long_ft), short_ft=float(short_ft), front_known=front_known,
    )


def _steps(length_ft: float, spacing: float = SAMPLE_FT) -> np.ndarray:
    n = max(2, int(math.ceil(length_ft / spacing)) + 1)
    return np.linspace(0.0, 1.0, n)


def samples(fr: Frame, spacing: float = SAMPLE_FT) -> dict[str, np.ndarray]:
    """The points the ground is read at: the six levels the hand-off names,
    each side at ``spacing``, and a grid over the whole footprint."""
    us = _steps(fr.long_ft, spacing)
    vs = _steps(fr.short_ft, spacing)
    uu, vv = np.meshgrid(us, vs)
    return {
        "six": fr.at([0.0, 1.0, 0.0, 1.0, 0.5, 0.5], [0.0, 0.0, 1.0, 1.0, 0.0, 1.0]),
        "front": fr.at(us, np.zeros_like(us)),
        "back": fr.at(us, np.ones_like(us)),
        "left": fr.at(np.zeros_like(vs), vs),
        "right": fr.at(np.ones_like(vs), vs),
        "grid": fr.at(uu.ravel(), vv.ravel()),
    }


SIX = ("z_front_left", "z_front_right", "z_back_left", "z_back_right", "z_front_mid", "z_back_mid")


def _side_mean(z: np.ndarray) -> float | None:
    z = np.asarray(z, dtype=float)
    if z.size == 0:
        return None
    good = np.isfinite(z)
    if good.mean() < MIN_SIDE_SHARE:
        return None
    return float(z[good].mean())


def _r(x: float | None, nd: int = 2) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), nd)


def ground_shape(fr: Frame, z_of: Callable[[np.ndarray], np.ndarray]) -> dict[str, Any]:
    """The hand-off's ground shape on the footprint, in feet.

    ``z_of`` turns an (N, 2) array of points into ground levels in feet (NaN
    where the model has none). ``fall_along`` is the left end's mean less the
    right end's; ``fall_across`` the front (street) side's mean less the
    back's: positive means that end or side is higher. ``relief`` is the
    highest less the lowest of every sample, sides and grid together, so it
    is never below either fall's size.
    """
    pts = samples(fr)
    z = {k: np.asarray(z_of(v), dtype=float) for k, v in pts.items()}
    out: dict[str, Any] = {k: _r(float(v)) if np.isfinite(v) else None for k, v in zip(SIX, z["six"])}
    means = {k: _side_mean(z[k]) for k in ("front", "back", "left", "right")}
    along = None if means["left"] is None or means["right"] is None else means["left"] - means["right"]
    across = None if means["front"] is None or means["back"] is None else means["front"] - means["back"]
    every = np.concatenate([z[k] for k in ("six", "front", "back", "left", "right", "grid")])
    good = every[np.isfinite(every)]
    covered = good.size / every.size if every.size else 0.0
    relief = float(good.max() - good.min()) if good.size and covered >= MIN_SIDE_SHARE else None
    out.update({
        "fall_along_ft": _r(along),
        "fall_across_ft": _r(across),
        "relief_ft": _r(relief),
        "high_side": _high(across, "street", "back"),
        "high_end": _high(along, "left", "right"),
        "ground_mean_ft": _r(float(good.mean())) if good.size else None,
        "ground_samples": int(every.size),
        "ground_covered": round(covered, 4),
    })
    return out


def _high(diff: float | None, pos: str, neg: str) -> str | None:
    if diff is None:
        return None
    if diff > LEVEL_FT:
        return pos
    if diff < -LEVEL_FT:
        return neg
    return "level"


def relief_class(relief_ft: float | None) -> str:
    """The hand-off's relief class (upper bounds inclusive: 1.0 ft is "0-1")."""
    if relief_ft is None or not math.isfinite(relief_ft):
        return "missing"
    for top, label in RELIEF_BINS:
        if relief_ft <= top:
            return label
    return RELIEF_OVER


def ft_bin(x: float | None) -> str:
    """A 1 ft bin of a size: "0-1", "1-2", ... (upper bound inclusive)."""
    if x is None or not math.isfinite(x):
        return "missing"
    a = abs(float(x))
    top = max(1, int(math.ceil(a - 1e-9)))
    return f"{top - 1}-{top}"


# --- the street-to-setback rise --------------------------------------------------


def line_points(segs: Iterable[Seg], spacing: float = SAMPLE_FT) -> np.ndarray:
    """Points along segments at ``spacing``, ends included."""
    out = []
    for x1, y1, x2, y2 in segs:
        t = _steps(math.hypot(x2 - x1, y2 - y1), spacing)
        out.append(np.column_stack([x1 + t * (x2 - x1), y1 + t * (y2 - y1)]))
    return np.concatenate(out) if out else np.zeros((0, 2))


def setback_line(lot: Any, fronts: Sequence[Seg], setback_ft: float) -> Any:
    """The front setback line: each front lot line moved ``setback_ft`` into
    the lot, clipped to it (shapely geometry; empty when nothing is left)."""
    import shapely
    from shapely.geometry import LineString

    parts = []
    for x1, y1, x2, y2 in fronts:
        line = LineString([(x1, y1), (x2, y2)])
        if line.length <= 0:
            continue
        best = None
        for side in (setback_ft, -setback_ft):
            moved = line.offset_curve(side)
            inside = moved.intersection(lot)
            if best is None or inside.length > best.length:
                best = inside
        if best is not None and not best.is_empty:
            parts.append(best)
    return shapely.union_all(parts) if parts else shapely.LineString()


def geom_points(geom: Any, spacing: float = SAMPLE_FT) -> np.ndarray:
    """Points along every line of ``geom`` at ``spacing``."""
    import shapely

    segs: list[Seg] = []
    for part in shapely.get_parts(geom):
        if part.is_empty or part.geom_type not in ("LineString", "LinearRing"):
            continue
        c = list(part.coords)
        segs += [(a[0], a[1], b[0], b[1]) for a, b in zip(c, c[1:])]
    return line_points(segs, spacing)


def street_rise(street_z: np.ndarray, setback_z: np.ndarray) -> float | None:
    """The lowest ground on the front setback line less the highest ground on
    the street lot line, feet (positive: the lot rises from the street)."""
    s = np.asarray(street_z, dtype=float)
    b = np.asarray(setback_z, dtype=float)
    s, b = s[np.isfinite(s)], b[np.isfinite(b)]
    if not s.size or not b.size:
        return None
    return float(b.min() - s.max())


# --- the soil --------------------------------------------------------------------


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def overlap_cm(top: Any, bot: Any, lo: float, hi: float) -> float:
    t, b = _num(top), _num(bot)
    if t is None or b is None:
        return 0.0
    return max(0.0, min(b, hi) - max(t, lo))


def soil_layer(horizons: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The 1-5 ft layer of one component's horizons (``hzdept_r``,
    ``hzdepb_r``, ``unified`` (the RV class), ``lep_r``, ``frag3to10_r``,
    ``fraggt10_r``).

    The Unified class is the one over the most of the layer (all classes met
    are listed); shrink-swell (LEP) is the highest in the layer; fragments
    over 3 in are the highest sum of the two fragment columns of any horizon
    from the surface to 5 ft (a footing is dug through the top foot too).
    """
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
    """The shallowest restrictive layer (depth cm as printed, kind), and the
    shallowest bedrock and pan of their own."""
    def shallowest(keep: Callable[[str], bool]) -> tuple[float | None, str | None]:
        found = [(_num(r.get("resdept_r")), str(r.get("reskind") or "")) for r in rows]
        found = [(d, k) for d, k in found if d is not None and keep(k)]
        if not found:
            return None, None
        return min(found)

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
    """The shallowest seasonal high water (the shallowest wet layer of any
    month, cm as printed) and the months it occurs, from the survey's monthly
    rows (``wet_top_cm``, ``month``). None when no month records one."""
    wet = [m for m in (months or ()) if _num(m.get("wet_top_cm")) is not None]
    if not wet:
        return None, None
    low = min(_num(m["wet_top_cm"]) for m in wet)  # type: ignore[type-var]
    when = [str(m.get("month")) for m in sorted(wet, key=lambda m: m.get("monthseq") or 0)
            if _num(m["wet_top_cm"]) == low]
    return low, ",".join(when)


# --- the ground class ------------------------------------------------------------


def ground_class(r: Mapping[str, Any]) -> tuple[str, list[str], bool | None]:
    """The hand-off's ground class (first match wins), the checks above it
    that could not be made for a missing input, and PAN (a hardpan, not
    bedrock, within 3.5 ft; None when the restrictive layers are unknown).

    ``r`` holds: ``slide_mapped`` (inside or within 100 ft of a mapped slide),
    ``slide_top`` (susceptibility in the top class), ``liq_top2``,
    ``flood_100``, ``soil_no_data``, ``bedrock_cm``, ``frag_gt3in_pct``,
    ``lep_1_5ft_pct``, ``hydric``, ``organic_1_5ft``, ``water_cm``,
    ``drainage``, ``restrictions_known``, ``pan_cm``. A missing input never
    matches; it is named in the list instead.
    """
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
    # "Unranked" (or blank) is not read: only a printed Yes or No answers.
    hyd = str(r.get("hydric") or "").strip().lower()
    hydric = True if hyd == "yes" else False if hyd == "no" else None
    if test("SOFT", either(hydric, r.get("organic_1_5ft"))):
        return "SOFT", unread, pan
    drain = None if not r.get("drainage") else str(r["drainage"]) in WET_DRAINAGE
    water = at_most(r.get("water_cm"), WET_CM)
    if r.get("water_cm") is None and r.get("water_months_held"):
        water = False  # monthly rows held, no wet layer recorded in any month
    if test("WET-FINE", either(water, drain)):
        return "WET-FINE", unread, pan
    return "FIRM", unread, pan


# --- rules by place ---------------------------------------------------------------

PORTLAND_DOC = "flats/provenance/docs/or/multnomah/portland/33.110/33.110.265.txt"
MULTCO_DOC = "flats/provenance/docs/or/multnomah/_unincorporated/33.110.txt"
#: Zones where 33.110.265.E (triplexes and fourplexes) applies: "R20 through R2.5".
SINGLE_DWELLING = frozenset({"R20", "R10", "R7", "R5", "R2.5"})
VISIT_SLOPE_PCT = 20.0
VISIT_RISE_FT = 3.0
#: Stored text that only offers visitability as an option or incentive.
OPTION_ONLY = {
    "or/washington/beaverton": "flats/provenance/docs/or/washington/beaverton/20.22/20.22.40.txt#L34",
    "or/washington/hillsboro": "flats/provenance/docs/or/washington/hillsboro/12.68/12.68.710.txt#L5",
}


def visitability(layer_id: str | None, zone: str | None, slope_pct: float | None,
                 rise_ft: float | None) -> dict[str, Any]:
    """Whether a step-free ("visitable") entry rule applies on the fourplex
    route, and whether the lot meets an exemption.

    ``status``: ``applies`` (Portland's 33.110.265.E.3 in R20-R2.5, and the
    same text held for unincorporated Multnomah); ``none_in_zone_chapter``
    (Portland's other zones: the stored chapters hold only an optional bonus,
    33.120.211, and the cottage-cluster rule, 33.120.270); ``not_read``
    everywhere else -- never "no rule". An exemption is met only on a measure
    that clears it; a missing measure leaves the rule applying.
    """
    zone_s = (zone or "").strip()
    if layer_id in ("or/multnomah/portland", "or/multnomah/_unincorporated") and zone_s in SINGLE_DWELLING:
        cite = (f"{PORTLAND_DOC}#L72" if layer_id == "or/multnomah/portland" else f"{MULTCO_DOC}#L1468")
        ex_cite = (f"{PORTLAND_DOC}#L88-L90" if layer_id == "or/multnomah/portland" else f"{MULTCO_DOC}#L1488-L1491")
        reasons = []
        if slope_pct is not None and slope_pct >= VISIT_SLOPE_PCT:
            reasons.append("E.3.c(1) average slope 20% or more")
        if rise_ft is not None and rise_ft > VISIT_RISE_FT:
            reasons.append("E.3.c(2) more than 3 ft rise street to front setback")
        unknown = not reasons and (slope_pct is None or rise_ft is None)
        return {
            "visit_status": "applies",
            "visit_exempt": bool(reasons),
            "visit_exempt_why": "; ".join(reasons) or ("measure missing, taken as not exempt" if unknown else None),
            "visit_cite": cite,
            "visit_exempt_cite": ex_cite,
        }
    if layer_id == "or/multnomah/portland":
        return {"visit_status": "none_in_zone_chapter", "visit_exempt": None, "visit_exempt_why": None,
                "visit_cite": "flats/provenance/docs/or/multnomah/portland/33.120/33.120.211.txt#L68 (bonus only)",
                "visit_exempt_cite": None}
    return {"visit_status": "not_read", "visit_exempt": None, "visit_exempt_why": None,
            "visit_cite": OPTION_ONLY.get(layer_id or ""), "visit_exempt_cite": None}


#: The frost register (../vicinitideals-worktrees/frost-scout.md, 2026-11-18)
#: with the owner's rulings of the same day: inches, level, note. None where
#: unresolved.
FROST_REGISTER: dict[str, tuple[int | None, str, str]] = {
    "portland": (12, "state", "residential silent; city page 12 in for commercial/engineered"),
    "gresham": (18, "city", "practice: 2008 inspection checklist, 18 in below finished grade (owner)"),
    "troutdale": (12, "state", "silent"),
    "fairview": (12, "state", "silent: MC 15.05 adopts state code (owner 2026-11-18); issues its own "
                 "permits (Multnomah County service-providers page, Aug 2026), so Gresham's 18 in does not reach it"),
    "wood_village": (12, "state", "silent: MC 15.04 adopts state code (owner 2026-11-18)"),
    "multnomah_unincorporated": (12, "state", "county silent; permits by contracted city (Gresham-area may be 18)"),
    "happy_valley": (12, "state", "silent"),
    "milwaukie": (12, "state", "silent"),
    "oregon_city": (12, "state", "silent"),
    "gladstone": (12, "county", "Clackamas County criteria page"),
    "canby": (12, "county", "Clackamas County criteria page"),
    "sandy": (12, "city", "design-criteria sheet 2024"),
    "estacada": (None, "unresolved", "image-only PDF not read"),
    "west_linn": (12, "state", "silent"),
    "tualatin": (12, "city", "sheet: 12 in below 400 ft elevation"),
    "wilsonville": (12, "state", "silent"),
    "lake_oswego": (12, "state", "silent"),
    "clackamas_unincorporated": (12, "county", "below 2,500 ft"),
    "washington_unincorporated": (12, "county", "below 400 ft (2024 copy); older sheet 18 in at 500 ft+"),
    "hillsboro": (12, "state", "silent: owner's search of the municipal code 2026-11-18"),
    "beaverton": (12, "city", "design-criteria sheet"),
    "sherwood": (12, "state", "silent"),
    "king_city": (12, "state", "silent"),
    "durham": (12, "city", "Tualatin's sheet by contract"),
    "cornelius": (12, "state", "silent"),
    "tigard": (12, "state", "silent: owner's search of the municipal code 2026-11-18"),
}
#: Places whose stated figure holds only below an elevation (feet).
FROST_BELOW_FT = {"tualatin": 400.0, "washington_unincorporated": 400.0, "durham": 400.0}


#: The state frost line depth by county: the figure each table prints, and its
#: elevation note. Both ORSC editions may be used until 2027-04-01.
#: * 2023 ORSC Table R301.2 (BCD "2023 ORSC Summary of Amendments" p.29, errata
#:   April 2024; stored data/flats/books/frost/state-baseline/orsc/
#:   23orsc-summaryofamendments.pdf): Clackamas 12, Multnomah 18 note e,
#:   Washington 12. Note e: "The frost line depth for site elevations below
#:   2,500 feet in Jackson, Josephine and Multnomah Counties is 12 inches."
#: * 2026 ORSC: table text not published; the Design Criteria Hub's 2026 ORSC
#:   layer (FeatureServer/21, edited 2026-09-22) prints Clackamas 18, Multnomah
#:   18, Washington 12. The 2025 OSSC Table 1809.5 adds Clackamas to the
#:   12-below-2,500-ft note (BCD 2025 OSSC matrix p.19, item 18-8); the 2026
#:   ORSC "aligns with OSSC" (BCD 2026 ORSC matrix p.1).
#: Read with the owner's instruction of 2026-11-18: 12 in below 2,500 ft in all
#: three counties, the printed figure (the larger edition's) at or above.
FROST_STATE: dict[str, dict[str, Any]] = {
    "multnomah": {"orsc_2023": 18, "orsc_2026": 18, "below_ft": 2500.0, "below_in": 12,
                  "basis_below": "2023 ORSC Table R301.2 note e (and 2026 ORSC/2025 OSSC note)"},
    "clackamas": {"orsc_2023": 12, "orsc_2026": 18, "below_ft": 2500.0, "below_in": 12,
                  "basis_below": "2023 ORSC Table R301.2 prints 12; 2026 ORSC/2025 OSSC print 18, 12 below 2,500 ft"},
    "washington": {"orsc_2023": 12, "orsc_2026": 12, "below_ft": None, "below_in": None,
                   "basis_below": "2023 and 2026 ORSC Table R301.2 print 12, no elevation note"},
}


def frost_state(county: str | None, elevation_ft: float | None) -> dict[str, Any]:
    """The footnote-adjusted state frost depth for a lot's ground elevation.
    Unread elevation takes the printed figure (the deeper reading)."""
    row = FROST_STATE.get((county or "").lower())
    if row is None:
        return {"frost_state_in": None, "frost_state_basis": "county not in the state table read"}
    printed = max(row["orsc_2023"], row["orsc_2026"])
    if row["below_ft"] is None:
        return {"frost_state_in": printed, "frost_state_basis": row["basis_below"]}
    if elevation_ft is None:
        return {"frost_state_in": printed, "frost_state_basis": "elevation unread: printed figure"}
    if elevation_ft < row["below_ft"]:
        return {"frost_state_in": row["below_in"], "frost_state_basis": row["basis_below"]}
    return {"frost_state_in": printed, "frost_state_basis": "at or above 2,500 ft: printed figure"}


def frost(jurisdiction: str | None, elevation_ft: float | None, hub_in: float | None,
          county: str | None = None) -> dict[str, Any]:
    """The register's frost depth beside the hub's printed county figure and the
    footnote-adjusted state figure, and the flags: the register and the state
    figure disagree; or the lot stands above the elevation band the place's
    figure is stated for."""
    reg = FROST_REGISTER.get(jurisdiction or "")
    inches, level, note = reg if reg else (None, "not in register", "")
    above = None
    cap = FROST_BELOW_FT.get(jurisdiction or "")
    if cap is not None and elevation_ft is not None:
        above = elevation_ft >= cap
    state = frost_state(county, elevation_ft)
    st = state["frost_state_in"]
    disagree = None if inches is None or st is None else float(inches) != float(st)
    return {
        "frost_register_in": inches, "frost_register_level": level, "frost_register_note": note,
        "frost_hub_in": hub_in, **state, "frost_disagree": disagree, "frost_above_stated_band": above,
    }
