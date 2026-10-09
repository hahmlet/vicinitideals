"""Read which lots are institutional land, once per snapshot.

Steph RULED 2026-10-06 (FOLLOWUPS 47): schools, hospitals, municipal sites,
parks, utilities, airports, marinas, transit hubs, rail, public pools and
plazas, malls -- "flagged red and flagged out of scans for any reason".
Churches and charities stay screened. The reading itself is
:mod:`flats.geom.institutional`; this step runs it over every lot of the
normalized lot table against an acquire snapshot and writes
``institutional.parquet`` -- one row per institutional lot -- beside
``institutional.json`` (counts by category, the snapshot read).

Two stages read the file:

* the bridge (``python -m flats.ingest.quadfit --institutional ...``) leaves
  those lots out of the scan -- the hours a campus costs are the point;
* assign answers every one of them RED with the reason
  ``INSTITUTIONAL_USE``, whatever else it would have said -- measured or not,
  gated or not. assign is where the answer is made, so a bridge run that
  forgot the file costs time, never the colour.

    uv run python -m flats.ingest.institutional \\
        --lots data/flats/normalized/2026-10-01/lots.parquet \\
        --sources data/flats/sources/2026-10-01 --out data/flats/institutional/2026-10-01
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from flats.geom.institutional import Land, classify, load, load_rules, missing

INSTITUTIONAL = "institutional.parquet"
META = "institutional.json"
#: The reason a lot answered this way carries (``checks.reasons``).
INSTITUTIONAL_USE = "INSTITUTIONAL_USE"
#: The reason on a lot the county tax roll rules out (FOLLOWUPS 59).
ROLL_RED = "COUNTY_ROLL_RED"
COLUMNS = ("county", "TLID", "category", "share", "source", "name", "whole_tlid")


def measure(lots: Any, land: Land) -> Any:
    """The institutional rows for ``lots`` (columns county, tlid, wkb).

    ``whole_tlid`` is True when every lot under that TLID is institutional:
    a few TLIDs name a lot in two counties, and the bridge, which keys on
    TLID alone, may leave a TLID out of the scan only then.
    """
    import pandas as pd
    import shapely

    geoms = [shapely.from_wkb(w) if w is not None else None for w in lots["wkb"]]
    got = classify(geoms, land)
    tlids = lots["tlid"].astype(str).str.rstrip().to_numpy()
    counties = lots["county"].astype(str).to_numpy()
    rows = [
        {
            "county": counties[i],
            "TLID": tlids[i],
            "category": r.category,
            "share": round(r.share, 4),
            "source": r.source,
            "name": r.name,
        }
        for i, r in enumerate(got)
        if r is not None
    ]
    return mark_whole(pd.DataFrame(rows, columns=list(COLUMNS[:-1])), tlids)


ROLL_COLUMNS = ("county", "tlid", "PROP_CODE", "LANDVAL", "BLDGVAL", "TOTALVAL", "ASSESSVAL", "site_address", "YEARBUILT")


def measure_roll(lots: Any, taken: set[tuple[str, str]] | None = None) -> Any:
    """The rows the county tax roll rules out (FOLLOWUPS 59), same columns as
    :func:`measure`. ``lots`` carries :data:`ROLL_COLUMNS`; a lot the map
    reading already holds (``taken``: ``(county, TLID)``) keeps that reading.
    """
    import pandas as pd

    from flats.geom.roll import built_counts
    from flats.geom.roll import load_rules as roll_rules
    from flats.geom.roll import read as roll_read

    rules = roll_rules()
    taken = taken or set()
    rows = []
    records = lots.astype(object).where(lots.notna(), None).to_dict("records")
    built = built_counts(records, rules)
    for rec in records:
        key = (str(rec["county"]), str(rec["tlid"]).rstrip())
        if key in taken:
            continue
        got = roll_read(rec, rules, built)
        if got is not None:
            rows.append({"county": key[0], "TLID": key[1], **got})
    return pd.DataFrame(rows, columns=list(COLUMNS[:-1]))


def mark_whole(frame: Any, tlids: Any) -> Any:
    """Set ``whole_tlid``: True when every lot under that TLID is in ``frame``."""
    every = Counter(str(t).rstrip() for t in tlids)
    taken = Counter(frame["TLID"].tolist())
    frame["whole_tlid"] = [taken[t] == every[t] for t in frame["TLID"]]
    return frame


def read(path: Path | None) -> Any:
    """The institutional frame, or None when there is no file."""
    import pandas as pd

    if path is None:
        return None
    file = path / INSTITUTIONAL if path.is_dir() else path
    if not file.is_file():
        raise FileNotFoundError(f"no institutional reading at {file}")
    frame = pd.read_parquet(file)
    lacking = set(COLUMNS) - set(frame.columns)
    if lacking:
        raise SystemExit(f"{file} lacks {sorted(lacking)}")
    frame["TLID"] = frame["TLID"].astype(str).str.rstrip()
    return frame


def skip_tlids(path: Path | None) -> set[str]:
    """The TLIDs the bridge leaves out of the scan."""
    frame = read(path)
    if frame is None:
        return set()
    return set(frame.loc[frame["whole_tlid"].astype(bool), "TLID"])


def by_lot(path: Path | None) -> dict[tuple[str, str], dict[str, Any]]:
    """``(county, TLID)`` -> the row, for assign."""
    frame = read(path)
    if frame is None:
        return {}
    frame = frame.astype(object).where(frame.notna(), None)
    return {(str(r["county"]), str(r["TLID"])): r for r in frame.to_dict("records")}


def run(lots_path: Path, sources: Path, out: Path, *, log: Callable[[str], None] = print) -> dict[str, Any]:
    import pandas as pd

    from flats.ingest.transit import read_lots

    started = time.monotonic()
    if lacking := missing(sources):
        raise SystemExit(f"{sources} lacks {', '.join(lacking)}: run acquire --keys {' '.join(lacking)}")
    rules = load_rules()
    land = load(sources, rules)
    assert land is not None
    log(f"land: {', '.join(f'{k} {n:,}' for k, n in land.counts().items())}")
    lots = read_lots(lots_path)
    if "county" not in lots.columns:
        lots["county"] = pd.read_parquet(lots_path, columns=["county"])["county"].to_numpy()
    lots = lots.rename(columns={"TLID": "tlid"})
    frame = measure(lots, land)
    import pyarrow.parquet as pq

    names = set(pq.read_schema(lots_path).names)
    roll_lots = pd.read_parquet(lots_path, columns=[c for c in ROLL_COLUMNS if c in names])
    roll = measure_roll(roll_lots, set(zip(frame["county"], frame["TLID"])))
    frame = pd.concat([frame.drop(columns="whole_tlid"), roll], ignore_index=True)
    frame = mark_whole(frame, lots["tlid"])
    out.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out / INSTITUTIONAL, index=False)
    manifest = sources / "manifest.json"
    datasets = (json.loads(manifest.read_text(encoding="utf-8")).get("datasets") or {}) if manifest.is_file() else {}
    meta = {
        "lots": int(len(lots)),
        "institutional": int(len(frame)),
        "roll": int(frame["category"].astype(str).str.startswith("roll_").sum()),
        "by_category": {k: int(v) for k, v in sorted(Counter(frame["category"]).items())},
        "by_county": {k: int(v) for k, v in sorted(Counter(frame["county"]).items())},
        "tlids_not_whole": int((~frame["whole_tlid"].astype(bool)).sum()),
        "min_share": rules.min_share,
        "lots_file": str(lots_path),
        "sources": str(sources),
        "sha256": {k: (datasets.get(k) or {}).get("sha256") for k in ("osm_land_use", "rlis_orca")},
        "seconds": round(time.monotonic() - started, 1),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out / META).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    log(f"institutional: {meta['institutional']:,} of {meta['lots']:,} lots -- "
        + ", ".join(f"{k} {v:,}" for k, v in meta["by_category"].items()))
    return meta


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lots", type=Path, required=True, help="the normalize stage's lots.parquet")
    ap.add_argument("--sources", type=Path, required=True, help="acquire snapshot holding osm_land_use and rlis_orca")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    run(args.lots, args.sources, args.out, log=lambda m: print(m, flush=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
