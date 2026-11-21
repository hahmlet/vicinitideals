"""Redraw the list of Multnomah lots whose owner of record is a public body.

Multnomah's tax roll marks exempt land only by an assessed value of 0, which
cannot tell a city park from a church (flats/config/roll_red.yaml). The
region's public taxlot layer carries the assessor's owner of record; this
script reads it, keeps the names the ``public_owner`` tier's patterns call a
public body or a housing authority, and writes
``flats/config/public_owners_multnomah.csv`` (``tlid,group,owner``).

Run at each county refresh, then set the ``retrieved`` date in the tier's
comment:

    uv run python scripts/flats_public_owners.py            # write the list
    uv run python scripts/flats_public_owners.py --dry-run  # count only

The list holds public bodies' names only: a private owner's name is read to
be discarded and is never written, and a name is cut at its first bracket,
where the assessor notes a bureau or a lessee. Parcel numbers hold spaces;
they are written and read whole.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flats.geom import roll  # noqa: E402

SERVICE = "https://www.portlandmaps.com/arcgis/rest/services/Public/Taxlots/MapServer/0/query"
COUNTY = "M"
PAGE = 2000
#: Words that narrow the request to names worth reading; the tier's own
#: patterns do the deciding. A pattern no word here reaches finds nothing,
#: which :func:`unreached` reports.
WORDS = (
    "CITY OF", "COUNTY", "STATE", "UNITED STATES", "U S ", "FEDERAL", "BONNEVILLE", "METRO", "PORT OF",
    "SCHOOL", "COLLEGE", "UNIVERSITY", "DIST", "UTILITY D", "CONSERV", "FIRE", "WATER", "PDC", "PROSPER",
    "DEVELOPMENT COMM", "DEPT OF", "HOUSING AUTH", "HOME FORWARD",
)


def _post(params: dict[str, Any]) -> dict[str, Any]:
    data = urllib.parse.urlencode({**params, "f": "json"}).encode()
    request = urllib.request.Request(SERVICE, data=data, headers={"User-Agent": "taxlot-list-client"})
    with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310 (fixed https URL)
        got = json.load(response)
    if "error" in got:
        raise SystemExit(f"the taxlot service refused the request: {got['error']}")
    return got


def owners() -> Iterator[tuple[str, str]]:
    """``(tlid, owner of record)`` for every lot whose owner's name holds one
    of :data:`WORDS`."""
    where = f"COUNTY='{COUNTY}' AND (" + " OR ".join(f"OWNER1 LIKE '%{w}%'" for w in WORDS) + ")"
    offset = 0
    while True:
        got = _post(
            {
                "where": where,
                "outFields": "TLID,OWNER1",
                "orderByFields": "OBJECTID",
                "resultOffset": offset,
                "resultRecordCount": PAGE,
                "returnGeometry": "false",
            }
        )
        features = got.get("features") or []
        for feature in features:
            attrs = feature["attributes"]
            if attrs.get("TLID") and attrs.get("OWNER1"):
                yield str(attrs["TLID"]).rstrip(), str(attrs["OWNER1"])
        offset += len(features)
        if not features or not got.get("exceededTransferLimit"):
            return


def unreached(tier: roll.Tier) -> list[str]:
    """The tier's patterns that none of :data:`WORDS` could bring a name to:
    a pattern added to the config and not to the request."""
    out = []
    for patterns in tier.owner_patterns.values():
        for p in patterns:
            if not any(w.strip() in p.pattern for w in WORDS):
                out.append(p.pattern)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="count, write nothing")
    args = parser.parse_args()

    tier = roll.load_rules().tier("public_owner")
    if missed := unreached(tier):
        raise SystemExit(f"no request word reaches these patterns: {missed}")
    rows: dict[str, tuple[str, str]] = {}
    read = 0
    for tlid, owner in owners():
        read += 1
        group = roll.owner_group(owner, tier)
        if group is not None:
            rows[tlid] = (group, " ".join(owner.split("(")[0].split()))
    counts = Counter(group for group, _owner in rows.values())
    print(f"{read:,} names read; {len(rows):,} lots kept: {dict(sorted(counts.items()))}")
    if args.dry_run:
        return 0
    out = roll.CONFIG.parent / "public_owners_multnomah.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["tlid", "group", "owner"])
        for tlid in sorted(rows):
            writer.writerow([tlid, *rows[tlid]])
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
