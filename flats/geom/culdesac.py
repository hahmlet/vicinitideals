"""Whether the lot fronts a cul-de-sac, read off quadfit's bulb test.

Happy Valley's district tables print two street-frontage rows above the
townhome one -- "Lots fronting on cul-de-sac" and "All other lots" -- and
the first asks 35 ft where the second asks 50 (R-5 to R-10), 50 to 70 where
it asks 60 to 100 (R-15 to R-40). Wilsonville's Table 2 note F and Table 8A
note J do the same for PDR-3, PDR-4 and RN, at 24. The corpus held only the
interior row on every one of those zones from the day it was read until
2026-09-15, and said why in a comment on each: nothing measured whether a
lot fronts a cul-de-sac, and reading the looser row across would pass lots
the code holds to the larger number.

quadfit's s4 measures it now (`Lot Analysis/quadfit/s4_edges.py`,
``fronts_cul_de_sac``): the lot's street-facing chords, in ring order, turn
toward the street on one circle of a turnaround's radius -- 30 to 80 ft,
which is what 16.12's "front lot line contiguous with the outer radius of a
curve" comes to on the ground -- and a street centreline ends inside that
circle, which is the "permanently terminated" half of the same section's
definition of the street. Both halves are required because a knuckle in a
winding street is surveyed on the same radius and turns the same way; only
the dead end tells them apart. This module turns that one column into the
site fact the rule layer knows.

What it does not see: a bulb whose centreline was drawn short of the throat
(the dead end then lies outside the circle), and the cul-de-sac row of a
city whose corpus does not hold one. Both answer False, and False is the
conservative answer here: the row this fact switches is looser than the
row it replaces, so a lot not proven on a bulb owes the interior frontage.
"""

from __future__ import annotations

from pathlib import Path

#: quadfit's per-lot stage record, where s4 leaves it. The same file
#: :mod:`flats.geom.alley` reads; the flag rides beside the edge classes.
S4_LOTS = Path(__file__).resolve().parents[2] / "data" / "quadfit" / "s4_lots.parquet"

#: The one fact, named the way the registry names it.
CUL_DE_SAC_FACTS: tuple[str, ...] = ("fronts_cul_de_sac",)


def observed_cul_de_sac(flag: object) -> dict[str, bool]:
    """The cul-de-sac fact for one lot, as ``configure`` takes it.

    ``flag`` is s4's column value. Anything but a plain True -- a missing
    column, a null from a merge, a lot s4 never reached -- reads False,
    because False keeps the interior number and True loosens it. The key is
    always present: a False here is an answer, not silence.
    """
    return {"fronts_cul_de_sac": isinstance(flag, bool) and flag}


def cul_de_sac_facts_from_quadfit(path: Path = S4_LOTS) -> dict[str, dict[str, bool]]:
    """Every lot's cul-de-sac fact, keyed by TLID, from s4's parquet.

    One read of the stage file. The returned mapping is what a county-scale
    caller hands to ``configure(observed=...)`` lot by lot; the column is
    refreshed by an s4 run, so a caller that wants today's bulbs runs s4
    first. A parquet written before the column existed answers False on
    every lot, which is what the corpus assumed of every lot until then.
    """
    import pandas as pd  # the only place flats.geom touches a frame

    import pyarrow.parquet as pq

    columns = ["TLID"]
    if "fronts_cul_de_sac" in pq.read_schema(path).names:
        columns.append("fronts_cul_de_sac")
    frame = pd.read_parquet(path, columns=columns)
    if "fronts_cul_de_sac" not in frame:
        frame["fronts_cul_de_sac"] = False
    flags = frame["fronts_cul_de_sac"].fillna(False).astype(bool)
    return {
        str(tlid): observed_cul_de_sac(bool(flag))
        for tlid, flag in zip(frame["TLID"], flags)
    }


__all__ = [
    "CUL_DE_SAC_FACTS",
    "S4_LOTS",
    "cul_de_sac_facts_from_quadfit",
    "observed_cul_de_sac",
]
