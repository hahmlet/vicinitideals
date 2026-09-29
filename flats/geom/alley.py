"""Which lot line abuts the alley, read off quadfit's edge classes.

The condition registry has carried ``abuts_alley`` since the Portland waiver
was encoded, and until 2026-09-13 nothing filled it: the registry assumed
False on every lot, so the garage-entrance exemption was never reached and
the corpus was right about alleys on paper only. quadfit's s4 now measures
every alley (`Lot Analysis/quadfit/s4_edges.py`: RLIS alley centreline within
reach of the edge, an alley of 8 to 40 ft measured across the taxlot fabric
on at least three of five rays) and records the edge as class ``A``. This
module turns that record into the three site facts the rule layer knows.

**The line is named, not just the lot.** Portland 33.110.220.D.9 waives the
"side, rear, or garage entrance setback ... from a lot line abutting an
alley" -- a statement about one line. ``abuts_alley`` alone cannot carry it:
an exemption on ``setback_rear_ft`` switched by a lot-level fact would open
the rear yard of a lot whose alley runs down its side, and that is the
false-GREEN direction. So the alley edge is compared to the frontage
bearings with the same rule s4 and :mod:`flats.geom.edges` use to tell rear
from side (within :data:`~flats.geom.edges.PARALLEL_TOL_DEG` of a frontage
bearing is the opposite line, else a side line), and the bridge answers
``alley_at_rear`` and ``alley_at_side`` as well as ``abuts_alley``.

What it does not see: a lot whose ONLY public way is the alley. s4 promotes
that alley to the frontage (class ``F``) so the lot is not called landlocked,
and from here it looks like a lot on a street. That lot owes its front
setback to the alley and the waiver does not reach it, so False is the
conservative answer; the count is small (the alley-only lots of a city are
its landlocked-but-for-the-alley remainder) and named here so nobody reads
``abuts_alley: False`` on one as a measurement.

**A line on the alley is not a line the alley runs the length of.** s4
classes an edge ``A`` where three of five rays across it find the alley, so
an alley that runs along half a side line and dead-ends there -- or turns
away behind the neighbour -- makes the whole line an alley line. That is the
right reading for "a lot line abutting an alley", and the wrong one for the
court that parks along a side alley and backs out into it (FOLLOWUPS 3(c)):
the court stands behind the building, wherever the fit put it, and a stub
along the front half of the line leaves it backing into a fence. So s4 also
measures how much of each alley edge the alley runs along (``alley_cover_json``,
one ray every five feet) and :func:`side_alley_along` hands the court a side
alley only where one side line is on the alley end to end. Where s4 predates
that column nothing measured the stretch, and the answer is False: the court
keeps its street lane, which is the answer it had before side alleys were read.

The rear line is read the same way twice over (FOLLOWUPS 3(d)/(e)). The
court whose row of stalls backs out into a rear alley gets that plan where
:func:`rear_alley_along` says the alley runs the whole rear line, or --
Steph's ruling of 2026-09-28 -- where the stretch it does run, with the
envelope behind it (:func:`usable_run_ft`), is at least as long as the row
of stalls; a shorter stub still reaches the court, which keeps its own
aisle. And the rules'
``alley_at_rear`` -- the switch on the rear setback's alley variant, one
number for the line -- is :func:`registry_alley`'s: on only where the alley
runs the whole rear line, so the stretch across from the neighbour behind
is never cut at the alley's number. The side line's alley setback is cut
stretch by stretch instead (:func:`cover_stretches`,
:func:`flats.geom.envelope.buildable`), since both its numbers are in hand;
and so, since 2026-09-29, is a rear line the alley runs part of, the bridge
resolving the lot a second time for the alley's rear
(:func:`flats.ingest.quadfit.part_rear_alley`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from flats.geom.edges import PARALLEL_TOL_DEG, bearing_deg, bearing_delta

#: s4's class letter for an edge on an alley.
ALLEY_CLASS = "A"

#: quadfit's per-lot edge record, where s4 leaves it. The bridge reads the
#: parquet rather than lots_results.csv because the csv carries the width
#: and not the edges, and the width alone cannot say which line.
S4_LOTS = Path(__file__).resolve().parents[2] / "data" / "quadfit" / "s4_lots.parquet"

#: The three facts, in the order they are reported.
ALLEY_FACTS: tuple[str, ...] = ("abuts_alley", "alley_at_rear", "alley_at_side")


def alley_lines(
    edges: Iterable[Sequence[object]], front_bearings: Sequence[float]
) -> tuple[str, ...]:
    """Name each class-``A`` edge ``rear`` or ``side``, in edge order.

    ``edges`` is s4's ``edges_json`` decoded: ``[x1, y1, x2, y2, cls]`` per
    boundary segment. ``front_bearings`` is its ``front_bearings_json``, the
    clustered street directions of the frontage (s4 records at most two; an
    alley parallel to an unrecorded third direction is called ``side``,
    which resolves nothing and so errs the safe way).
    """
    names: list[str] = []
    for edge in edges:
        if edge[4] != ALLEY_CLASS:
            continue
        b = bearing_deg(float(edge[0]), float(edge[1]), float(edge[2]), float(edge[3]))
        rear = any(bearing_delta(b, float(fb)) <= PARALLEL_TOL_DEG for fb in front_bearings)
        names.append("rear" if rear else "side")
    return tuple(names)


def observed_alley(
    edges: Iterable[Sequence[object]], front_bearings: Sequence[float]
) -> dict[str, bool]:
    """The three alley facts for one lot, as ``configure`` takes them.

    A lot with an alley edge behind it and another beside it holds both
    per-line facts; the parent holds whenever either does. Every key is
    always present: the bridge answers the question on every lot it has
    edges for, and a False here is a measurement, not silence.
    """
    lines = alley_lines(edges, front_bearings)
    rear = "rear" in lines
    side = "side" in lines
    return {"abuts_alley": rear or side, "alley_at_rear": rear, "alley_at_side": side}


#: Where s4's first and last cover rays stand, in from each end of an alley
#: edge (``ALLEY_COVER_INSET_FT`` in `Lot Analysis/quadfit/s4_edges.py`). The
#: rays between are evenly spaced, so a cover string's length alone places
#: every one of them (:func:`cover_stretches`).
COVER_INSET_FT = 2.5


def whole(cover: object) -> bool:
    """Whether one edge's cover string found the alley on every ray."""
    return isinstance(cover, str) and bool(cover) and set(cover) == {"1"}


def decode_cover(raw: object, n_edges: int) -> list[str | None] | None:
    """s4's ``alley_cover_json`` for one lot, parallel to its ``n_edges``
    edges, or None where nothing usable is on record: s4 before the column
    (null / empty), JSON that does not parse, or a list of the wrong length.
    Every caller reads None as "nothing measured the stretch", which is never
    the alley running the whole line."""
    if raw is None or (isinstance(raw, str) and not raw):
        return None
    try:
        got = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return None
    if not isinstance(got, list) or len(got) != n_edges:
        return None
    return [c if isinstance(c, str) else None for c in got]


def _lines(
    edges: Sequence[Sequence[object]],
    front_bearings: Sequence[float],
    name: str,
) -> list[list[int]]:
    """The lot's ``name`` lines (``side`` or ``rear``), each a list of edge
    indices in ring order.

    A line is a run of consecutive edges of that name -- s4's ``S`` or
    ``R``, and the ``A`` edges :func:`alley_lines` names the same -- that
    keep one direction: a bend of more than
    :data:`~flats.geom.edges.PARALLEL_TOL_DEG` starts another line (the two
    legs of a triangular lot are two lines), and any edge of another name
    ends it. A ring of nothing but that name (no frontage) has no line.
    """
    letter = {"side": "S", "rear": "R"}[name]
    named = iter(alley_lines(edges, front_bearings))
    member: list[bool] = []
    for edge in edges:
        if edge[4] == ALLEY_CLASS:
            member.append(next(named) == name)
        else:
            member.append(edge[4] == letter)
    if not member or all(member):
        return []

    def bearing(i: int) -> float:
        e = edges[i]
        return bearing_deg(float(e[0]), float(e[1]), float(e[2]), float(e[3]))  # type: ignore[arg-type]

    # Walk the ring from just after a non-member edge so no line wraps round.
    start = member.index(False) + 1
    n = len(edges)
    lines: list[list[int]] = []
    line: list[int] = []
    for k in range(n + 1):
        i = (start + k) % n
        same = (
            k < n
            and member[i]
            and (not line or bearing_delta(bearing(line[-1]), bearing(i)) <= PARALLEL_TOL_DEG)
        )
        if same:
            line.append(i)
            continue
        if line:
            lines.append(line)
        line = [i] if k < n and member[i] else []
    return lines


def side_alley_along(
    edges: Sequence[Sequence[object]],
    front_bearings: Sequence[float],
    cover: Sequence[str | None] | None,
) -> bool:
    """Whether one side lot line is on the alley from end to end.

    ``edges`` and ``front_bearings`` as :func:`alley_lines` takes them;
    ``cover`` is s4's ``alley_cover_json`` decoded, parallel to ``edges``: per
    alley edge a string of ``1`` and ``0``, one per ray along it (the alley
    found or not), ``None`` on every other edge.

    A side line is a run of consecutive side edges (:func:`_lines`): s4's
    ``S``, and the ``A`` edges :func:`alley_lines` names ``side``; a jog
    across the lot is parallel to the frontage, so s4 calls it a rear edge
    and it ends the run. A line qualifies only where every edge of it is an
    alley edge and every ray along every one found the alley: a line whose
    front half is a neighbour's fence and rear half the alley is not on the
    alley, because which half the court would stand in the fit does not say.

    ``cover`` of None, or not one entry per edge, is a record that predates
    the measurement: False, the court's street-fed answer.
    """
    if cover is None or len(cover) != len(edges):
        return False
    return any(
        all(edges[j][4] == ALLEY_CLASS and whole(cover[j]) for j in line)
        for line in _lines(edges, front_bearings, "side")
    )


def rear_alley_along(
    edges: Sequence[Sequence[object]],
    front_bearings: Sequence[float],
    cover: Sequence[str | None] | None,
) -> bool:
    """Whether the rear lot line on the alley is on it from end to end.

    FOLLOWUPS 3(d)/(e), the rear twin of :func:`side_alley_along`. s4 names
    a rear line an alley line on three rays of five, so an alley stub along
    40 % of it makes the whole line ``A``. Two things read that line as if
    the alley ran all of it: the court whose row of stalls backs out into
    the alley (:func:`flats.score.paper.court_depth`), and the rear setback
    a code waives or relaxes on "a lot line abutting an alley"
    (``alley_at_rear``). The court stands behind the building, and neither
    the fit (placed at any angle, anywhere in the envelope) nor the rules
    say where along the rear line; the rear setback is one number the rules
    resolve for the line. So the honest test is the whole line, the same
    as the side's.

    True only where the lot has a rear line holding an alley edge, and
    EVERY rear line holding one (:func:`_lines`) is alley edges end to end,
    each with every ray on the alley: a rear line half ``R`` (the neighbour
    behind) and half ``A`` is not on the alley, however well the ``A`` half
    is covered. A rear line with no alley edge is not asked -- on a corner
    lot the line along the second street's far side is a rear line too, and
    it says nothing about the alley behind.

    ``cover`` of None, or not one entry per edge, predates the measurement:
    False.
    """
    if cover is None or len(cover) != len(edges):
        return False
    on = [line for line in _lines(edges, front_bearings, "rear")
          if any(edges[j][4] == ALLEY_CLASS for j in line)]
    return bool(on) and all(
        all(edges[j][4] == ALLEY_CLASS and whole(cover[j]) for j in line) for line in on
    )


def cover_stretches(length_ft: float, cover: str) -> tuple[tuple[float, float], ...]:
    """Where along an alley edge the alley runs, as ``(from, to)`` in feet
    from the edge's first point -- the stretches the cover's rays vouch for.

    s4 casts the rays :data:`COVER_INSET_FT` in from each end and evenly
    between (one, at the middle, on an edge too short for two), so a string
    of ``n`` places them all. A run of ``1`` rays covers from its first ray
    to its last, and reaches the end of the edge where the run does; the
    ground between a ``1`` and the next ``0`` is where the alley stopped,
    somewhere nobody measured, and is left uncovered. An isolated ``1``
    between two ``0`` rays covers nothing (a point). The empty string --
    nothing measured -- covers nothing.
    """
    n = len(cover)
    if n == 0 or length_ft <= 0:
        return ()
    if n == 1:
        return ((0.0, length_ft),) if cover == "1" else ()
    span = max(0.0, length_ft - 2 * COVER_INSET_FT)
    at = [COVER_INSET_FT + span * i / (n - 1) for i in range(n)]
    out: list[tuple[float, float]] = []
    i = 0
    while i < n:
        if cover[i] != "1":
            i += 1
            continue
        j = i
        while j + 1 < n and cover[j + 1] == "1":
            j += 1
        a = 0.0 if i == 0 else at[i]
        b = length_ft if j == n - 1 else at[j]
        if b > a:
            out.append((a, b))
        i = j + 1
    return tuple(out)


#: One covered stretch of a rear alley line, ``(x1, y1, x2, y2)`` in the
#: lot's own coordinates, in the edge's ring direction.
Stretch = tuple[float, float, float, float]

#: How finely :func:`usable_run_ft` walks a covered stretch, in feet.
RUN_STEP_FT = 0.5
#: How far past the envelope's rear edge :func:`usable_run_ft` looks for
#: the envelope: a foot in, twice the fit's half-foot cell.
RUN_PROBE_FT = 1.0


def rear_cover_runs(
    edges: Sequence[Sequence[object]],
    front_bearings: Sequence[float],
    cover: Sequence[str | None] | None,
) -> tuple[tuple[Stretch, ...], ...]:
    """Where the alley runs along each rear alley line, in the lot's
    coordinates: per rear line holding an alley edge (:func:`_lines`), the
    stretches its cover vouches for (:func:`cover_stretches`), in ring
    order. A stretch that ends where the next begins is one run carried
    across the bend; an ``R`` piece of the line is a gap. Empty where
    nothing measured the cover -- no stretch, no aisle.
    """
    if cover is None or len(cover) != len(edges):
        return ()
    out: list[tuple[Stretch, ...]] = []
    for line in _lines(edges, front_bearings, "rear"):
        if not any(edges[j][4] == ALLEY_CLASS for j in line):
            continue
        got: list[Stretch] = []
        for j in line:
            c = cover[j]
            if edges[j][4] != ALLEY_CLASS or not isinstance(c, str):
                continue
            x1, y1, x2, y2 = (float(v) for v in edges[j][:4])  # type: ignore[arg-type]
            length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            for a, b in cover_stretches(length, c):
                ta, tb = a / length, b / length
                got.append((
                    x1 + (x2 - x1) * ta, y1 + (y2 - y1) * ta,
                    x1 + (x2 - x1) * tb, y1 + (y2 - y1) * tb,
                ))
        out.append(tuple(got))
    return tuple(out)


def usable_run_ft(
    runs: Sequence[Sequence[Stretch]],
    lot: object,
    envelope: object,
    rear_cut_ft: float | None,
) -> float:
    """The longest stretch of rear alley a court could stand behind, in feet.

    Steph's ruling of 2026-09-28: a rear alley that runs only part of the
    rear line is the court's travel lane *"only if the lane is actually long
    enough to accommodate"*, and the court has to be able to sit behind that
    stretch within the envelope. So each covered stretch (``runs``, from
    :func:`rear_cover_runs`) is walked every :data:`RUN_STEP_FT`, and a point
    counts only where the envelope stands straight in from it -- probed
    ``rear_cut_ft`` (the strip the envelope lost at the rear) plus
    :data:`RUN_PROBE_FT` in, perpendicular to the line. The side yards cut
    the stretch at each end where they reach it, and a notch in the envelope
    breaks it. The answer is the longest unbroken run, measured along the
    line. 0.0 where there is no lot, no envelope or no stretch.

    Only the length is compared (:meth:`flats.score.paper.Alley.rear_aisle_for`):
    the fit finds the deepest rectangle anywhere in the envelope and does
    not say where along the rear line its court stands.
    """
    import shapely

    if lot is None or envelope is None or getattr(envelope, "is_empty", True) or not runs:
        return 0.0
    probe = max(0.0, rear_cut_ft or 0.0) + RUN_PROBE_FT
    best = 0.0
    for line in runs:
        start: float | None = None
        at = 0.0  # distance walked along this line's stretches
        last_ok: float | None = None
        prev_end: tuple[float, float] | None = None
        for x1, y1, x2, y2 in line:
            length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            if length <= 0:
                continue
            if prev_end is not None and (
                (x1 - prev_end[0]) ** 2 + (y1 - prev_end[1]) ** 2
            ) ** 0.5 > RUN_STEP_FT:
                start = last_ok = None  # a gap along the line: a new run
            ux, uy = (x2 - x1) / length, (y2 - y1) / length
            nx, ny = -uy, ux
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            if not shapely.contains_xy(lot, mx + nx * RUN_PROBE_FT, my + ny * RUN_PROBE_FT):
                nx, ny = -nx, -ny  # point the probe into the lot
            k = max(1, int(length // RUN_STEP_FT))
            t = [length * i / k for i in range(k + 1)]
            px = [x1 + ux * d + nx * probe for d in t]
            py = [y1 + uy * d + ny * probe for d in t]
            inside = shapely.contains_xy(envelope, px, py)
            for d, ok in zip(t, inside):
                here = at + d
                if ok:
                    if start is None:
                        start = here
                    last_ok = here
                    best = max(best, last_ok - start)
                else:
                    start = last_ok = None
            at += length
            prev_end = (x2, y2)
    return best


def registry_alley(
    edges: Sequence[Sequence[object]],
    front_bearings: Sequence[float],
    cover: Sequence[str | None] | None,
) -> dict[str, bool]:
    """The three alley facts as the rules resolve on them.

    :func:`observed_alley`, but ``alley_at_rear`` -- the fact the rear
    setback's alley variants are switched by (Portland's and Multnomah's
    exemption, Gresham's and Troutdale's rear-with-alley numbers) -- holds
    only where :func:`rear_alley_along` says the alley runs the rear line
    end to end (FOLLOWUPS 3(e)). The variant is one number for the whole
    line, and on a line the alley runs part of, the stretch across from the
    neighbour's yard owes the ordinary rear setback: the ordinary number
    for the line is the conservative one. ``abuts_alley`` stays s4's -- the
    lot does abut the alley -- and so does ``alley_at_side``, whose one
    standard (``setback_alley_side_ft``) the envelope cuts stretch by
    stretch (:func:`flats.geom.envelope.buildable`). No cover on record is
    no rear alley line.
    """
    got = observed_alley(edges, front_bearings)
    if got["alley_at_rear"]:
        got["alley_at_rear"] = rear_alley_along(edges, front_bearings, cover)
    return got


def alley_facts_from_quadfit(path: Path = S4_LOTS) -> dict[str, dict[str, bool]]:
    """Every lot's alley facts, keyed by TLID, from s4's parquet, as the
    rules resolve on them (:func:`registry_alley`).

    One read of the stage file. The returned mapping is what a county-scale
    caller hands to ``configure(observed=...)`` lot by lot; the parquet is
    the s4 stage output and is refreshed by an s4 run, so a caller that
    wants today's alleys runs s4 first.
    """
    import pandas as pd  # the only place flats.geom touches a frame

    import pyarrow.parquet as pq

    columns = ["TLID", "edges_json", "front_bearings_json"]
    has_cover = "alley_cover_json" in pq.read_schema(path).names
    frame = pd.read_parquet(path, columns=columns + (["alley_cover_json"] if has_cover else []))
    covers = frame["alley_cover_json"] if has_cover else [None] * len(frame)
    out: dict[str, dict[str, bool]] = {}
    for tlid, ej, fj, cj in zip(frame["TLID"], frame["edges_json"], frame["front_bearings_json"], covers):
        edges = json.loads(ej)
        out[str(tlid)] = registry_alley(edges, json.loads(fj), decode_cover(cj, len(edges)))
    return out


def entailed(observed: Mapping[str, bool]) -> dict[str, bool]:
    """Close a set of alley observations under the parent/child relation.

    A per-line fact True carries ``abuts_alley`` True; ``abuts_alley`` False
    carries both per-line facts False where they were not stated. Raises on
    a contradiction (a rear alley on a lot said to abut none), because a
    caller holding both has two sources disagreeing and the bridge cannot
    pick. This is the same closure ``configure`` applies from the registry's
    ``ENTAILS`` table, offered here so a caller can see the closed set
    before handing it over.
    """
    from flats.rules.conditions import close_entailed

    return close_entailed(observed)


__all__ = [
    "ALLEY_CLASS",
    "ALLEY_FACTS",
    "COVER_INSET_FT",
    "S4_LOTS",
    "alley_facts_from_quadfit",
    "alley_lines",
    "cover_stretches",
    "decode_cover",
    "entailed",
    "observed_alley",
    "rear_alley_along",
    "rear_cover_runs",
    "registry_alley",
    "side_alley_along",
    "usable_run_ft",
    "whole",
]
