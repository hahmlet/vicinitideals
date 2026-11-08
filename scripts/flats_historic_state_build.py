"""Build the state's historic lists from their two public layers (FOLLOWUPS 87).

    python -I scripts/flats_historic_state_build.py --raw <empty folder> --lots <s1_lots.parquet>

Pages the State Historic Preservation Office's Historic Sites layer (the three
counties) and the National Park Service's National Register points (Oregon) into
``--raw``, keeps the fields and rows the screen uses, and writes each to
``flats/config/historic/state/<source>-<date>/`` with a ``SOURCE.json``. Left out,
and counted there: an entry surveyed and found not eligible, one marked demolished
or delisted, a National Register district's single point, the city rows FLATS does
not screen, and Multnomah rows whose point lands in Portland, whose map answers
there. ``scripts/flats_match_historic.py`` then places the rest on the lots.

What the layers send is data. Run this with ``python -I``.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from flats.geom import historic_lists as hl

SHPO = "https://maps.prd.state.or.us/arcgis/rest/services/Cultural/HistSites_GIS_FeaturesOnly/FeatureServer/0"
SHPO_WHERE = "county IN ('Clackamas','Multnomah','Washington')"
SHPO_FIELDS = "OBJECTID,RESOURCE_ID,propName,address,city,county,origUse,elig,nrStat,HistDist"
NPS = "https://mapservices.nps.gov/arcgis/rest/services/cultural_resources/nrhp_locations/MapServer/0"
NPS_WHERE = "State='OR' OR State='OREGON' OR State='Oregon'"
NPS_FIELDS = "OBJECTID,NRIS_Refnum,RESNAME,ResType,Address,City,County"
COUNTIES = ("Clackamas", "Multnomah", "Washington")
#: Cities in the three counties FLATS holds no jurisdiction for.
NOT_SCREENED = frozenset(
    {"AURORA", "BANKS", "BARLOW", "BONNEVILLE", "CASCADE LOCKS", "FOREST GROVE", "GASTON", "MOLALLA", "NORTH PLAINS"}
)


def _get(url: str, params: dict[str, object]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{url}/query?{urllib.parse.urlencode(params)}", headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def fetch(url: str, where: str, fields: str, sink: Path) -> None:
    start = 0
    with sink.open("w", encoding="utf-8") as out:
        while True:
            got = _get(
                url,
                {
                    "where": where,
                    "outFields": fields,
                    "returnGeometry": "true",
                    "outSR": 4326,
                    "resultOffset": start,
                    "resultRecordCount": 1000,
                    "orderByFields": "OBJECTID",
                    "f": "json",
                },
            )
            features = got.get("features", [])
            for feature in features:
                out.write(json.dumps(feature) + "\n")
            start += len(features)
            if not features or not got.get("exceededTransferLimit"):
                return


def _row(
    tag: str,
    identity: object,
    name: object,
    address: object,
    city: str,
    county: object,
    kind: str,
    geometry: dict[str, float] | None,
) -> dict[str, str]:
    return {
        "tlid": "",
        "address_listed": " ".join(str(address or "").split()),
        "name": " ".join(str(name or "").split()),
        "listing_id_or_row": f"{tag}-{identity}",
        "source": tag,
        "match_method": "none",
        "match_note": "Not yet matched.",
        "place": hl.place_of(city, county),
        "class": kind,
        "county": str(county or "").strip(),
        "city": city,
        "lon": f"{geometry['x']:.6f}" if geometry else "",
        "lat": f"{geometry['y']:.6f}" if geometry else "",
    }


def build(
    tag: str,
    rows: list[dict[str, str]],
    dropped: Counter[str],
    table: hl.LotTable,
    out: Path,
    about: dict[str, object],
) -> None:
    located = [r for r in rows if r["lon"]]
    under = table.under_points([float(r["lon"]) for r in located], [float(r["lat"]) for r in located])
    in_portland = {
        r["listing_id_or_row"]
        for r, lots in zip(located, under, strict=True)
        if r["county"] == "Multnomah" and any(table.places[lot] == "portland" for lot in lots)
    }
    kept = [r for r in rows if r["listing_id_or_row"] not in in_portland]
    dropped["multnomah point in Portland (its map answers)"] = len(rows) - len(kept)
    out.mkdir(parents=True, exist_ok=True)
    hl.write_state_rows(out / "listings.csv", kept)
    (out / "SOURCE.json").write_text(
        json.dumps(
            {
                **about,
                "retrieved": date.today().isoformat(),
                "kept_rows": len(kept),
                "kept_by_class": dict(Counter(r["class"] for r in kept).most_common()),
                "left_out": dict(dropped),
                "bytes_kept": (out / "listings.csv").stat().st_size,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{tag}: kept {len(kept)}, left out {dict(dropped)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True, help="where the layers' pages go; never committed")
    parser.add_argument("--lots", type=Path, required=True, help="a lot table parquet")
    args = parser.parse_args(argv)
    args.raw.mkdir(parents=True, exist_ok=True)
    shpo_raw, nps_raw = args.raw / "shpo.jsonl", args.raw / "nps.jsonl"
    if not shpo_raw.exists():
        fetch(SHPO, SHPO_WHERE, SHPO_FIELDS, shpo_raw)
    if not nps_raw.exists():
        fetch(NPS, NPS_WHERE, NPS_FIELDS, nps_raw)
    today = date.today().isoformat()

    frame = pd.read_parquet(args.lots, columns=["TLID", "SITEADDR", "SITECITY", "JURIS_CITY", "COUNTY", "wkb"])
    table = hl.LotTable(frame, ())

    rows: list[dict[str, str]] = []
    dropped: Counter[str] = Counter()
    raw_rows = 0
    with shpo_raw.open(encoding="utf-8") as lines:
        for line in lines:
            feature = json.loads(line)
            a = feature["attributes"]
            raw_rows += 1
            kind = hl.shpo_class(a)
            city = (a.get("city") or "").strip()
            if kind in hl.LEFT_OUT:
                dropped[kind] += 1
            elif city.upper() in NOT_SCREENED:
                dropped["city FLATS does not screen"] += 1
            else:
                rows.append(
                    _row(
                        "shpo",
                        int(a["RESOURCE_ID"]),
                        a.get("propName"),
                        a.get("address"),
                        city,
                        a.get("county"),
                        kind,
                        feature.get("geometry"),
                    )
                )
    build(
        "shpo",
        rows,
        dropped,
        table,
        hl.STATE_DIR / f"shpo-{today}",
        {
            "source": SHPO,
            "holds": "Oregon State Historic Preservation Office Historic Sites: an inventory, not a designation list",
            "where": SHPO_WHERE,
            "fields": SHPO_FIELDS,
            "raw_rows": raw_rows,
            "raw_bytes": shpo_raw.stat().st_size,
        },
    )

    rows, dropped, raw_rows = [], Counter(), 0
    with nps_raw.open(encoding="utf-8") as lines:
        for line in lines:
            feature = json.loads(line)
            a = feature["attributes"]
            raw_rows += 1
            if (a.get("County") or "").strip() not in COUNTIES:
                dropped["outside the three counties"] += 1
                continue
            nps_kind = hl.nps_class(a)
            city = (a.get("City") or "").strip()
            if nps_kind is None:
                dropped["a National Register district's single point"] += 1
            elif city.upper() in NOT_SCREENED:
                dropped["city FLATS does not screen"] += 1
            else:
                rows.append(
                    _row(
                        "nps",
                        a.get("NRIS_Refnum"),
                        a.get("RESNAME"),
                        a.get("Address"),
                        city,
                        a.get("County"),
                        nps_kind,
                        feature.get("geometry"),
                    )
                )
    build(
        "nps",
        rows,
        dropped,
        table,
        hl.STATE_DIR / f"nps-{today}",
        {
            "source": NPS,
            "holds": "National Park Service National Register of Historic Places points",
            "where": NPS_WHERE,
            "fields": NPS_FIELDS,
            "raw_rows": raw_rows,
            "raw_bytes": nps_raw.stat().st_size,
        },
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
