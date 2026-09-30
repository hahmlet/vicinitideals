"""Measure every lot's distance to transit, once per transit release.

Steph, 2026-09-30: "we don't need to re-run transit distance every single
time. Once we've defined which lots are near transit, the only way that
changes is if bus stops change." So this is a step of its own, not a stage of
the screen: it reads the lot fabric and an acquire snapshot holding the three
transit layers, and writes ``distances.parquet`` -- one row per lot, the four
distances of :mod:`flats.geom.transit` -- beside ``distances.json`` naming
the transit version it was measured against. The bridge joins the file on
TLID (``python -m flats.ingest.quadfit --transit distances.parquet``).

When is it re-run? When the monthly probe reports a transit layer's data was
edited (``new_release`` on ``transit_*``), take a new snapshot of those three
keys and run this with ``--reuse`` pointing at the last file. If the stops,
stations and frequent lines hash the same as before (a republish, not a
change) nothing is measured and the old file is copied forward; if they
changed, every lot is measured again -- it is seconds. A lot fabric refresh
alone re-measures only the lots whose shape changed (each row carries the
lot's geometry hash, :func:`flats.ingest.delta._geom_hash`).

    uv run python -m flats.ingest.transit --s4 s4_lots.parquet \\
        --sources data/flats/sources/2026-09-30 --out data/flats/transit/2026-09-30 \\
        [--reuse data/flats/transit/2026-06-01/distances.parquet]
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from flats.geom.transit import MEASURES, TransitSet, distances, load

DISTANCES = "distances.parquet"
META = "distances.json"


def _meta_for(parquet: Path) -> dict[str, Any]:
    path = parquet.with_name(META)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def read_lots(path: Path) -> Any:
    """TLID and lot polygon from quadfit's s4 file (``TLID``) or the
    normalize stage's table (``tlid``, every lot of the copy, measured or
    not -- the lot page shows the distance on both)."""
    import pandas as pd
    import pyarrow.parquet as pq

    names = set(pq.read_schema(path).names)
    key = "TLID" if "TLID" in names else "tlid"
    lots = pd.read_parquet(path, columns=[key, "wkb"]).rename(columns={key: "TLID"})
    lots["TLID"] = lots["TLID"].astype(str).str.rstrip()
    return lots


def measure(
    lots: Any,
    transit: TransitSet,
    *,
    reuse: Any = None,
    reuse_version: str | None = None,
) -> tuple[Any, dict[str, int]]:
    """The distance frame for ``lots`` (columns TLID, wkb) and what was reused.

    ``reuse`` is an earlier distance frame; its rows are kept for every lot
    whose TLID and shape are unchanged, but only when it was measured against
    this same transit version -- new stops move everybody's distance.
    """
    import pandas as pd
    import shapely

    from flats.ingest.delta import _geom_hash

    geoms = [shapely.from_wkb(w) if w is not None else None for w in lots["wkb"]]
    frame = pd.DataFrame(
        {
            "TLID": lots["TLID"].astype(str).to_numpy(),
            "geom_hash": [_geom_hash(g) if g is not None else None for g in geoms],
        }
    )
    todo = pd.Series(True, index=frame.index)
    for m in MEASURES:
        frame[m] = None
    kept = 0
    if reuse is not None and reuse_version == transit.version and len(reuse):
        old = reuse.drop_duplicates("TLID").set_index("TLID")
        joined = frame[["TLID", "geom_hash"]].join(old, on="TLID", rsuffix="_old")
        same = joined["geom_hash_old"].eq(frame["geom_hash"]) & frame["geom_hash"].notna()
        for m in MEASURES:
            frame.loc[same, m] = joined.loc[same, m]
        todo = ~same
        kept = int(same.sum())
    idx = [i for i, t in enumerate(todo.to_numpy()) if t]
    if idx:
        got = distances([geoms[i] for i in idx], transit)
        for m in MEASURES:
            frame.loc[frame.index[idx], m] = got[m]
    for m in MEASURES:
        frame[m] = pd.to_numeric(frame[m], errors="coerce")
    return frame, {"lots": len(frame), "reused": kept, "measured": len(idx)}


def run(
    s4: Path,
    sources: Path,
    out: Path,
    *,
    reuse: Path | None = None,
    log: Callable[[str], None] = print,
) -> Path:
    """Measure and write ``distances.parquet`` + ``distances.json`` under ``out``."""
    import pandas as pd

    transit = load(sources)
    if transit is None:
        raise SystemExit(
            f"{sources}: the snapshot does not hold all three transit layers -- "
            f"acquire transit_rail_stations, transit_stops and transit_routes together"
        )
    lots = read_lots(s4)
    old = old_version = None
    if reuse is not None and reuse.is_file():
        old = pd.read_parquet(reuse)
        old_version = _meta_for(reuse).get("transit_version")
    frame, stats = measure(lots, transit, reuse=old, reuse_version=old_version)
    out.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out / DISTANCES, index=False)
    meta = {
        "transit_version": transit.version,
        "sources": str(sources),
        "s4": str(s4),
        "reused_from": str(reuse) if reuse is not None else None,
        "unchanged_transit": old_version == transit.version if old is not None else None,
        "targets": {k: len(v) for k, v in transit.targets().items()},
        **stats,
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out / META).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    log(
        f"transit: {stats['lots']:,} lots, {stats['measured']:,} measured, "
        f"{stats['reused']:,} reused (version {transit.version}) -> {out / DISTANCES}"
    )
    return out / DISTANCES


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--s4", "--lots", dest="s4", type=Path, required=True,
        help="the lot fabric: quadfit's s4_lots.parquet or data/flats/normalized/<date>/lots.parquet",
    )
    ap.add_argument("--sources", type=Path, required=True, help="snapshot holding the transit layers")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reuse", type=Path, help="the last distances.parquet")
    args = ap.parse_args(argv)
    run(args.s4, args.sources, args.out, reuse=args.reuse)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
