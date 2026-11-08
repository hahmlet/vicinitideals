"""Read how each Washington County lot was made, once per tax-roll pull.

Washington County's denser zones open the quick (Type I) review of Middle
Housing only on "an existing lot or parcel that was approved for the
construction of a Single Detached Dwelling Unit through a Standard
Subdivision or Standard Partition" (CDC 304-2.14, 305-2.14, 306-2.14,
307-2.13; 375-7 30.c), and "Standard" is set against the Middle Housing Land
Division alone (CDC 106-107, Ord. 890A). Reading of 2026-11-03, Steph GO
2026-11-07 (FOLLOWUPS 83): a lot a recorded subdivision or partition plat
made -- any age, a PUD's included -- passes the gate; one a Middle Housing
Land Division made (CDC 606) is flagged as today; a lot no plat made
(described by acres or metes and bounds, or only part of a platted lot)
misses the Type I path and takes the Type II review, as today.

The county's tax lots carry the assessor's legal description, which names
the plat where a plat made the lot ("VIEW CREST, LOT 3", "2016-037 PARTITION
PLAT, LOT 1") and reads acres otherwise ("ACRES 10.05"). This step pulls
that one field (with the TLID) from the county's free Taxlots layer and
writes ``plats.parquet`` -- one row per TLID, its :data:`ORIGINS` class --
beside ``plats.json`` naming the URL, the pull date and the counts. The
download is untrusted data: it is only ever parsed as JSON and matched
against the patterns below, never run.

A plat's title need not say it was a middle housing land division, and
those began in 2022 (:data:`FIRST_MHLD_YEAR`). So a plat passes only where
it is known to be older: a partition plat by the year in its name, a named
subdivision by houses on its lots built in several different years before
then (:func:`pre_mhld_plats`). A newer plat, or one whose age the roll does
not show, is unread -- the flag stays, never a false GREEN.

The bridge joins the file on TLID for Washington County lots only
(``python -m flats.ingest.quadfit --plats plats.parquet``); a lot the file
does not hold, or whose description no pattern reads, keeps the gate
unmeasured and the flag it carries today. Re-pull when the tax roll turns
over (yearly) -- a plat recorded since only changes an unmeasured lot.

    uv run python -m flats.ingest.plats --out data/flats/plats/2026-11-07
    uv run python -m flats.ingest.plats --raw data/flats/plats/2026-11-07/raw.parquet \\
        --out data/flats/plats/2026-11-07       # re-parse a pull, no download
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

#: The county's free Taxlots layer (Urban Services Framework, layer 151).
LAYER_URL = (
    "https://gispub.co.washington.or.us/server/rest/services/"
    "Urban_Services_Plan_Framework/Urban_Services_Framework/FeatureServer/151"
)
#: The fields pulled: the lot's id, its legal description, and the point the
#: county places it at (kept in the raw pull only, to check a count by zone).
FIELDS = ("OBJECTID", "TLID", "LEGAL_DESCRIPTION", "YEARBUILT", "X_COORD", "Y_COORD")
PAGE = 2000
PLATS = "plats.parquet"
#: The pull the bridge reads when it is given none (committed: ~0.4 MB).
CURRENT = Path(__file__).resolve().parents[2] / "data" / "flats" / "plats" / "2026-11-07" / PLATS
RAW = "raw.parquet"
META = "plats.json"

#: How a lot was made, read off its legal description.
PLATTED = "platted"  # a recorded subdivision or partition plat: gate passed
MHLD = "mhld"  # a Middle Housing Land Division plat (CDC 606): flagged
UNPLATTED = "unplatted"  # acres, metes and bounds, or part of a lot: gate missed
UNREAD = "unread"  # nothing below reads it: unmeasured
ORIGINS = (PLATTED, MHLD, UNPLATTED, UNREAD)

#: A Middle Housing Land Division named in the description.
_MHLD = re.compile(r"\bMIDDLE\s+HOUSING\b|\bMHLD\b")
#: A condominium: its "lots" are units of a condominium plat, not lots a
#: subdivision or partition approved for a Single Detached Dwelling Unit.
_CONDO = re.compile(r"\bCONDO")
#: Land by acres alone: no plat is named, so none made the lot.
_ACRES_ONLY = re.compile(r"^ACRES?\s+[\d.]+$")
#: A partition plat's name carries its recording year ("2016-037 PARTITION PLAT").
_PARTITION = re.compile(r"^(\d{4})-\d+\s+PARTITION\s+PLAT$")
#: The lot clause, whole: one block (optional) and ONE lot or parcel, named
#: by a number or a letter -- "LOT 3", "BLOCK 2, LOT 3", "LOT A".
_BLOCK = re.compile(r"^BLOCK\s+(?:\d+|[A-Z]{1,2})$")
_ONE_LOT = re.compile(r"^(?:LOT|PARCEL)\s+(?:\d+|[A-Z]{1,2})$")
#: Notes the assessor appends that say nothing about how the lot was made.
_NOTES = (
    re.compile(r"^ACRES?\s+[\d.]+$"),
    re.compile(r"^POTENTIAL ADD'?L TAX LIABILITY$"),
    re.compile(r"^CODE SPLIT$"),
)
#: Only part of a platted lot, block or tract ("LOT PT 10", "LOT 94 & PT 93",
#: "PLUS PT VACATED RD"): a deed, not the plat, made the lot as it stands.
_PART = re.compile(r"\bPTS?\b|\bPORTION\b|\bPART\b")
#: Washington County's Middle Housing Land Division came in with Ord. No.
#: 885A, eff. 7-28-22 (CDC 106-126,
#: or/washington/_unincorporated/cdc.106.definitions.txt#L698-L704; the state
#: law it carries out, ORS 92.031, is not held here and dates from the same
#: year). A plat recorded in 2022 or since may be one whose title does not
#: say so, so it is not read as a standard plat -- the whole year, since a
#: partition plat's name gives no month.
FIRST_MHLD_YEAR = 2022
#: A named subdivision carries no year, so its age is read off the lots it
#: holds: houses built in at least this many different years before
#: :data:`FIRST_MHLD_YEAR` say the plat is older than middle housing land
#: divisions. One division's child lots share the building(s) of one parent
#: lot, so they do not show three separate building years.
PRE_MHLD_BUILD_YEARS = 3


def parse(legal: str | None) -> tuple[str, str | None, int | None]:
    """``(origin, plat, partition_year)`` of one legal description.

    ``origin`` is :data:`PLATTED` only where the description is exactly a
    plat's name, an optional block, ONE whole lot or parcel, and the
    assessor's notes (acres, a tax-code split) -- and that is a candidate
    still: :func:`classify` keeps it only where the plat is known to predate
    middle housing land divisions. Part of a lot is :data:`UNPLATTED`, as
    is land by acres alone; a unit, a tract, several lots run together or
    anything else is :data:`UNREAD`.
    """
    if legal is None:
        return UNREAD, None, None
    text = " ".join(str(legal).split()).upper()
    if not text:
        return UNREAD, None, None
    if _MHLD.search(text):
        return MHLD, None, None
    if _CONDO.search(text):
        return UNREAD, None, None
    items = [i.strip() for i in re.split(r"[,;]", text) if i.strip()]
    if not items:
        return UNREAD, None, None
    head, rest = items[0], items[1:]
    if _ACRES_ONLY.match(head):
        return (UNPLATTED if all(any(n.match(i) for n in _NOTES) for i in rest) else UNREAD), None, None
    if not re.search(r"[A-Z]{3,}", head):
        return UNREAD, None, None
    if any(_PART.search(i) for i in rest):
        return UNPLATTED, head, None
    if rest and _BLOCK.match(rest[0]):
        rest = rest[1:]
    if not rest or not _ONE_LOT.match(rest[0]):
        return UNREAD, head, None
    if not all(any(n.match(i) for n in _NOTES) for i in rest[1:]):
        return UNREAD, head, None
    year = _PARTITION.match(head)
    return PLATTED, head, int(year.group(1)) if year else None


def origin(legal: str | None) -> str:
    """The :data:`ORIGINS` class :func:`parse` reads, before the plat-age
    check of :func:`classify`."""
    return parse(legal)[0]


def pre_mhld_plats(heads: Any, built: Any) -> set[str]:
    """The named plats whose lots show houses built in at least
    :data:`PRE_MHLD_BUILD_YEARS` different years before :data:`FIRST_MHLD_YEAR`."""
    import pandas as pd

    frame = pd.DataFrame({"plat": heads, "built": pd.to_numeric(built, errors="coerce")})
    old = frame[frame["plat"].notna() & frame["built"].between(1800, FIRST_MHLD_YEAR - 1)]
    years = old.groupby("plat")["built"].nunique()
    return set(years[years >= PRE_MHLD_BUILD_YEARS].index)


def _pages(
    get: Callable[[str, dict[str, Any]], dict[str, Any]],
    *,
    page: int = PAGE,
    log: Callable[[str], None] = print,
) -> Iterator[dict[str, Any]]:
    """Every feature's attributes, OBJECTID order, ``page`` at a time --
    one request after another, never in parallel."""
    offset = 0
    while True:
        body = get(
            f"{LAYER_URL}/query",
            {
                "where": "1=1",
                "outFields": ",".join(FIELDS),
                "returnGeometry": "false",
                "orderByFields": "OBJECTID",
                "resultOffset": offset,
                "resultRecordCount": page,
                "f": "json",
            },
        )
        if "error" in body:
            raise SystemExit(f"{LAYER_URL}: {body['error']}")
        feats = body.get("features") or []
        for f in feats:
            attrs = f.get("attributes") or {}
            yield {k: attrs.get(k) for k in FIELDS}
        offset += len(feats)
        if offset % 20000 < len(feats):
            log(f"  {offset:,} lots")
        if not feats or not body.get("exceededTransferLimit"):
            return


def fetch(log: Callable[[str], None] = print) -> Any:
    """The raw pull: one row per tax lot, :data:`FIELDS` only."""
    import httpx
    import pandas as pd

    with httpx.Client(timeout=120, headers={"User-Agent": "FLATS plat reader (viciniti.deals)"}) as client:

        def get(url: str, params: dict[str, Any]) -> dict[str, Any]:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            got = resp.json()
            if not isinstance(got, dict):
                raise SystemExit(f"{url}: not a JSON object")
            return got

        rows = list(_pages(get, log=log))
    frame = pd.DataFrame(rows, columns=list(FIELDS))
    for c in ("TLID", "LEGAL_DESCRIPTION"):
        frame[c] = frame[c].astype("string")
    return frame


def classify(raw: Any) -> tuple[Any, dict[str, int]]:
    """``plats.parquet`` from a raw pull: TLID, origin and the plat named,
    one row per TLID.

    A :func:`parse` candidate stays :data:`PLATTED` only where the plat is
    known to predate middle housing land divisions: a partition plat
    recorded before :data:`FIRST_MHLD_YEAR`, or a named subdivision among
    :func:`pre_mhld_plats`. Any other is :data:`UNREAD`. A TLID the pull
    holds twice keeps one class only where both read the same; otherwise it
    is :data:`UNREAD`.
    """
    import pandas as pd

    parsed = [parse(None if pd.isna(v) else str(v)) for v in raw["LEGAL_DESCRIPTION"]]
    heads = [p[1] for p in parsed]
    built = raw["YEARBUILT"] if "YEARBUILT" in raw else pd.Series([None] * len(raw))
    old = pre_mhld_plats(heads, built.to_numpy())

    def dated(got: tuple[str, str | None, int | None]) -> str:
        how, head, year = got
        if how != PLATTED:
            return how
        if year is not None:
            return PLATTED if year < FIRST_MHLD_YEAR else UNREAD
        return PLATTED if head in old else UNREAD

    frame = pd.DataFrame(
        {
            "TLID": raw["TLID"].astype("string").str.strip(),
            "origin": [dated(p) for p in parsed],
            "plat": pd.Series(heads, dtype="string"),
        }
    )
    frame = frame[frame["TLID"].notna() & (frame["TLID"] != "")]
    agree = frame.groupby("TLID")["origin"].nunique()
    frame = frame.drop_duplicates("TLID").set_index("TLID")
    frame.loc[agree[agree > 1].index, "origin"] = UNREAD
    frame = frame.reset_index()
    frame["origin"] = frame["origin"].astype("category")
    counts = Counter(frame["origin"].astype(str))
    return frame, {k: int(counts.get(k, 0)) for k in ORIGINS}


def tlid_key(tlid: Any) -> str | None:
    """One spelling of a Washington County TLID, to join on.

    The county writes the map and lot run together ("2S124A003100": map
    2S124A0, lot 03100); the regional (RLIS) fabric pads the map with spaces
    and a dash ("2S124A  -03100"). Both come out as the county's twelve
    characters: the map's quarter-sections filled with ``0``, the lot to
    five digits. Anything else is None -- not joined, so unread.
    """
    if tlid is None:
        return None
    text = str(tlid).upper()
    if "-" in text:
        left, _, right = text.partition("-")
        map_no, lot = re.sub(r"\s+", "", left), re.sub(r"\s+", "", right)
        if not re.fullmatch(r"[0-9][NS][0-9][0-9]{2}[A-D0-9]{0,2}", map_no) or not re.fullmatch(r"\d{1,5}", lot):
            return None
        return map_no.ljust(7, "0") + lot.zfill(5)
    text = re.sub(r"\s+", "", text)
    return text if re.fullmatch(r"[0-9][NS][0-9][0-9]{2}[A-D0-9]{2}\d{5}", text) else None


def read(path: Path) -> Any:
    """``plat_key``, ``plat_origin`` from a ``plats.parquet``, one row per
    TLID (:func:`tlid_key`), for the bridge to join."""
    import pandas as pd

    frame = pd.read_parquet(path, columns=["TLID", "origin"])
    frame["plat_key"] = [tlid_key(t) for t in frame["TLID"]]
    frame["plat_origin"] = frame["origin"].astype(str)
    frame = frame[frame["plat_key"].notna()]
    return frame.drop_duplicates("plat_key")[["plat_key", "plat_origin"]]


def run(out: Path, *, raw: Path | None = None, log: Callable[[str], None] = print) -> Path:
    """Pull (or re-read ``raw``), classify, and write under ``out``."""
    import pandas as pd

    out.mkdir(parents=True, exist_ok=True)
    meta_path = out / META
    old = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    if raw is None:
        log(f"pulling {LAYER_URL}")
        frame = fetch(log)
        frame.to_parquet(out / RAW, index=False)
        fetched = datetime.now(timezone.utc).isoformat(timespec="seconds")
        raw_path = out / RAW
    else:
        frame = pd.read_parquet(raw)
        fetched = old.get("fetched_at")
        raw_path = raw
    plats, counts = classify(frame)
    # Only the lots something was read for: a TLID the table does not hold
    # is unread, the conservative answer, so the unread rows are not kept.
    keep = plats[plats["origin"].astype(str) != UNREAD].sort_values("TLID")
    keep.to_parquet(out / PLATS, index=False, compression="zstd")
    meta = {
        "source": LAYER_URL,
        "fields": list(FIELDS),
        "fetched_at": fetched,
        "raw": raw_path.as_posix(),
        "lots": int(len(frame)),
        "with_description": int(frame["LEGAL_DESCRIPTION"].notna().sum()),
        "tlids": int(len(plats)),
        "kept": int(len(keep)),
        "origins": counts,
        "classified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    log(json.dumps(meta["origins"]))
    return out / PLATS


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True, help="data/flats/plats/<date>")
    ap.add_argument("--raw", type=Path, help="re-classify an earlier raw.parquet, no download")
    args = ap.parse_args(argv)
    run(args.out, raw=args.raw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
