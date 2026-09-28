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

    A side line is a run of consecutive side edges -- s4's ``S``, and the
    ``A`` edges :func:`alley_lines` names ``side`` -- that keep one
    direction: a bend of more than :data:`~flats.geom.edges.PARALLEL_TOL_DEG`
    starts another line (the two legs of a triangular lot are two lines),
    and a jog across the lot is parallel to the frontage, so s4 calls it a
    rear edge and it ends the run. A line qualifies only where every edge of
    it is an alley edge and every ray along every one found the alley: a
    line whose front half is a neighbour's fence and rear half the alley is
    not on the alley, because which half the court would stand in the fit
    does not say.

    ``cover`` of None, or not one entry per edge, is a record that predates
    the measurement: False, the court's street-fed answer.
    """
    if cover is None or len(cover) != len(edges):
        return False
    named = iter(alley_lines(edges, front_bearings))
    side: list[bool] = []
    for edge in edges:
        if edge[4] == ALLEY_CLASS:
            side.append(next(named) == "side")
        else:
            side.append(edge[4] == "S")
    if all(side):
        return False  # no frontage and no rear: nothing to call a side line

    def bearing(i: int) -> float:
        e = edges[i]
        return bearing_deg(float(e[0]), float(e[1]), float(e[2]), float(e[3]))  # type: ignore[arg-type]

    def on_alley(i: int) -> bool:
        c = cover[i]
        return edges[i][4] == ALLEY_CLASS and isinstance(c, str) and bool(c) and set(c) == {"1"}

    # Walk the ring from just after a non-side edge so no line wraps round.
    start = side.index(False) + 1
    n = len(edges)
    line: list[int] = []
    for k in range(n + 1):
        i = (start + k) % n
        same = (
            k < n
            and side[i]
            and (not line or bearing_delta(bearing(line[-1]), bearing(i)) <= PARALLEL_TOL_DEG)
        )
        if same:
            line.append(i)
            continue
        if line and all(on_alley(j) for j in line):
            return True
        line = [i] if k < n and side[i] else []
    return False


def alley_facts_from_quadfit(path: Path = S4_LOTS) -> dict[str, dict[str, bool]]:
    """Every lot's alley facts, keyed by TLID, from s4's parquet.

    One read of the stage file. The returned mapping is what a county-scale
    caller hands to ``configure(observed=...)`` lot by lot; the parquet is
    the s4 stage output and is refreshed by an s4 run, so a caller that
    wants today's alleys runs s4 first.
    """
    import pandas as pd  # the only place flats.geom touches a frame

    frame = pd.read_parquet(path, columns=["TLID", "edges_json", "front_bearings_json"])
    out: dict[str, dict[str, bool]] = {}
    for tlid, ej, fj in zip(frame["TLID"], frame["edges_json"], frame["front_bearings_json"]):
        out[str(tlid)] = observed_alley(json.loads(ej), json.loads(fj))
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
    "S4_LOTS",
    "alley_facts_from_quadfit",
    "alley_lines",
    "entailed",
    "observed_alley",
    "side_alley_along",
]
