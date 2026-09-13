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
]
