"""What stands on each lot: fetch the footprint map, build the labels, load them.

FOLLOWUPS 125 (:mod:`flats.ingest.occupancy`). A LABEL, never a colour -- the
standing ruling ``2026-10-14-existing-buildings-stay-green``. Three steps, on
whichever box has what each needs:

* ``fetch`` (httpx; anywhere with the internet) pages Metro RLIS's Building
  Footprint Database into ``footprints.geojsonl.gz`` (one footprint per line,
  Oregon North feet, EPSG:2913) and ``meta.json`` (the layer, the server's own
  edit dates, the count it reported and the count written). The download is
  data, never code: it is parsed as JSON and nothing else.
* ``build`` (shapely + pyarrow; LXC 137, or a laptop with a lot table) cuts
  every footprint against every lot of a lot table -- the normalize stage's
  ``lots.parquet`` (every lot of the county copy) or quadfit's ``s1_lots.parquet``
  -- and writes ``occupancy.csv.gz`` (one row per lot), ``disagreements.csv.gz``
  (the lots where the footprint map and the roll disagree, both ways) and
  ``summary.json`` (labels and disagreements per county and per city).
* ``load`` (asyncpg; the api container) replaces one snapshot's rows of
  ``flats.lot_occupancy`` from a build directory, matching on
  ``(snapshot_id, county, tlid)``. No lot, result or run is touched.

Usage::

    python scripts/flats_lot_occupancy.py fetch --out data/flats/footprints/2026-11-07
    python scripts/flats_lot_occupancy.py build --footprints data/flats/footprints/2026-11-07 \\
        --lots /root/flats_normalized/<snapshot>/lots.parquet --out data/flats/occupancy/<snapshot>
    # copy the build directory to VM 114's /root/stacks/vicinitideals/data/flats/occupancy/<snapshot>, then
    docker compose run --rm api python scripts/flats_lot_occupancy.py load \\
        --build /app/data/flats/occupancy/<snapshot> --snapshot <flats.snapshots id> [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from flats.ingest.occupancy import OCCUPANCY_COLUMNS, measure_lots  # noqa: E402

#: Metro RLIS Building Footprint Database (ArcGIS Online, owner OregonMetro.RLIS).
#: Chosen over the statewide GEOHub layer (``building_footprints_or``) on
#: 2026-11-07: that layer is Metro's own footprints compiled in 2018-2022 and
#: last edited 2024-01-05, mostly 2007-2009 digitising; this one was edited
#: 2026-11-04, and its City of Portland footprints were all re-created 2025+.
FOOTPRINT_LAYER = (
    "https://services2.arcgis.com/McQ0OlIABe29rJJy/arcgis/rest/services/"
    "Building_Footprint_Database/FeatureServer/8"
)
FOOTPRINT_LABEL = "Metro RLIS Building Footprint Database"
FOOTPRINT_FIELDS = ("FID", "BLDG_ID", "STATE_ID", "SUBAREA", "SOURCE_REF", "CREATEDATE", "MOD_DATE", "YEAR_BUILT")
FOOTPRINTS_FILE = "footprints.geojsonl.gz"
META_FILE = "meta.json"
OCCUPANCY_FILE = "occupancy.csv.gz"
DISAGREEMENTS_FILE = "disagreements.csv.gz"
SUMMARY_FILE = "summary.json"
PAGE = 2000
#: Oregon North, international feet -- the lot table's projection.
OUT_SR = 2913

#: quadfit's county letters.
COUNTY_LETTERS = {"M": "multnomah", "C": "clackamas", "W": "washington"}
ROLL = ("LANDVAL", "BLDGVAL", "TOTALVAL", "YEARBUILT", "BLDGSQFT")


# --- fetch ----------------------------------------------------------------------


def _get(client: Any, url: str, params: dict[str, Any], tries: int = 5) -> dict[str, Any]:
    for attempt in range(tries):
        try:
            resp = client.get(url, params=params, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(str(data["error"])[:300])
            return data
        except Exception:  # noqa: BLE001 -- retried, then raised
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def fetch(out: Path, layer: str = FOOTPRINT_LAYER, page: int = PAGE) -> dict[str, Any]:
    """Page the footprint layer to ``out``; returns the meta record."""
    import httpx

    out.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"User-Agent": "vicinitideals-flats/occupancy"}) as client:
        info = _get(client, layer, {"f": "json"})
        total = _get(client, f"{layer}/query", {"where": "1=1", "returnCountOnly": "true", "f": "json"})["count"]
        written = 0
        offset = 0
        tmp = out / (FOOTPRINTS_FILE + ".part")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            while True:
                data = _get(
                    client,
                    f"{layer}/query",
                    {
                        "where": "1=1",
                        "outFields": ",".join(FOOTPRINT_FIELDS),
                        "orderByFields": "FID",
                        "resultOffset": offset,
                        "resultRecordCount": page,
                        "outSR": OUT_SR,
                        "geometryPrecision": 2,
                        "f": "geojson",
                    },
                )
                features = data.get("features") or []
                for feat in features:
                    geom = feat.get("geometry")
                    if not isinstance(geom, dict) or geom.get("type") not in ("Polygon", "MultiPolygon"):
                        continue
                    props = {k: feat.get("properties", {}).get(k) for k in FOOTPRINT_FIELDS}
                    fh.write(json.dumps({"p": props, "g": geom}, separators=(",", ":")) + "\n")
                    written += 1
                offset += len(features)
                if not features or (not data.get("exceededTransferLimit") and len(features) < page):
                    break
        tmp.replace(out / FOOTPRINTS_FILE)
    editing = info.get("editingInfo") or {}
    meta = {
        "layer": layer,
        "label": FOOTPRINT_LABEL,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "server_count": total,
        "written": written,
        "out_sr": OUT_SR,
        "data_last_edit": _ms_date(editing.get("dataLastEditDate")),
        "description": (info.get("description") or "")[:1000],
    }
    (out / META_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def _ms_date(ms: Any) -> str | None:
    if not isinstance(ms, (int, float)):
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


def iter_footprints(path: Path) -> Iterator[Any]:
    """The footprints of a fetch as shapely polygons (JSON in, nothing executed)."""
    from shapely.geometry import shape

    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield shape(json.loads(line)["g"])
            except Exception:  # noqa: BLE001 -- a broken ring is skipped, and counted by the caller
                yield None


# --- build ----------------------------------------------------------------------


def read_lots(path: Path) -> list[dict[str, Any]]:
    """The lot table: normalize's ``lots.parquet`` or quadfit's ``s1_lots.parquet``."""
    import pyarrow.parquet as pq
    import shapely

    names = set(pq.ParquetFile(path).schema_arrow.names)
    county_col = "county" if "county" in names else "COUNTY"
    tlid_col = "tlid" if "tlid" in names else "TLID"
    extra = [c for c in ("juris_city", "JURIS_CITY", "jurisdiction", "site_address", "SITEADDR") if c in names]
    cols = [county_col, tlid_col, "wkb", *[c for c in ROLL if c in names], *extra]
    if "area_sqft" in names:
        cols.append("area_sqft")
    table = pq.read_table(path, columns=cols)
    geoms = shapely.from_wkb(table.column("wkb").to_numpy(zero_copy_only=False))
    rows = table.drop(["wkb"]).to_pylist()
    lots = []
    for row, geom in zip(rows, geoms):
        county = str(row[county_col] or "")
        lots.append(
            {
                **{c: row.get(c) for c in ROLL},
                "county": COUNTY_LETTERS.get(county, county.lower()),
                "tlid": row[tlid_col],
                "geom": geom,
                "area_sqft": row.get("area_sqft"),
                "juris_city": row.get("juris_city") or row.get("JURIS_CITY"),
                "jurisdiction": row.get("jurisdiction"),
                "site_address": row.get("site_address") or row.get("SITEADDR"),
            }
        )
    return lots


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    with gzip.open(path, "wt", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(["" if row.get(c) is None else row[c] for c in columns])


def build(footprints_dir: Path, lots_path: Path, out: Path) -> dict[str, Any]:
    """Label every lot of ``lots_path``; returns the summary."""
    meta = json.loads((footprints_dir / META_FILE).read_text(encoding="utf-8"))
    started = time.time()
    lots = read_lots(lots_path)
    footprints = [g for g in iter_footprints(footprints_dir / FOOTPRINTS_FILE)]
    broken = sum(1 for g in footprints if g is None)
    rows = list(measure_lots(lots, (g for g in footprints if g is not None)))
    out.mkdir(parents=True, exist_ok=True)
    _write_csv(out / OCCUPANCY_FILE, OCCUPANCY_COLUMNS, rows)
    extra = ("juris_city", "jurisdiction", "site_address")
    disagreeing = [
        {**row, **{k: lot.get(k) for k in extra}} for row, lot in zip(rows, lots) if row["disagreement"]
    ]
    _write_csv(out / DISAGREEMENTS_FILE, (*OCCUPANCY_COLUMNS, *extra), disagreeing)
    labels: dict[str, Counter] = defaultdict(Counter)
    disagree: dict[str, Counter] = defaultdict(Counter)
    by_city: dict[str, Counter] = defaultdict(Counter)
    for row, lot in zip(rows, lots):
        labels[row["county"]][row["label"]] += 1
        if row["disagreement"]:
            disagree[row["county"]][row["disagreement"]] += 1
            by_city[f"{row['county']}/{(lot.get('juris_city') or 'unincorporated').strip().lower()}"][row["disagreement"]] += 1
    summary = {
        "footprints": {**{k: meta.get(k) for k in ("label", "layer", "fetched_at", "data_last_edit", "server_count", "written")}, "unreadable": broken},
        "source": f"{meta.get('label')}, fetched {str(meta.get('fetched_at') or '')[:10]}",
        "lots_file": str(lots_path),
        "lots": len(rows),
        "labels": {k: dict(v) for k, v in sorted(labels.items())},
        "disagreements": {k: dict(v) for k, v in sorted(disagree.items())},
        "disagreements_by_city": {k: dict(v) for k, v in sorted(by_city.items(), key=lambda kv: -sum(kv[1].values()))},
        "seconds": round(time.time() - started, 1),
    }
    (out / SUMMARY_FILE).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


# --- load -----------------------------------------------------------------------


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _csv_rows(path: Path) -> Iterator[list[str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        if tuple(header) != OCCUPANCY_COLUMNS:
            raise SystemExit(f"{path}: columns {header} are not {list(OCCUPANCY_COLUMNS)}")
        yield from reader


_TYPES = {
    "building_count": int,
    "main_count": int,
    "year_built": int,
    "footprint_sqft": float,
    "largest_sqft": float,
    "coverage": float,
    "building_value": float,
    "total_value": float,
    "roll_building_sqft": float,
}


def _typed(row: list[str]) -> tuple[Any, ...]:
    out: list[Any] = []
    for col, cell in zip(OCCUPANCY_COLUMNS, row):
        if cell == "":
            out.append(None)
        elif col in _TYPES:
            out.append(_TYPES[col](float(cell)) if _TYPES[col] is int else float(cell))
        else:
            out.append(cell)
    return tuple(out)


async def load(build_dir: Path, db_url: str, *, snapshot_id: int, dry_run: bool = False, batch_size: int = 20_000) -> dict[str, Any]:
    """Replace ``flats.lot_occupancy`` for one snapshot from a build directory."""
    import asyncpg

    summary = json.loads((build_dir / SUMMARY_FILE).read_text(encoding="utf-8"))
    source = str(summary.get("source") or "")[:160]
    report: dict[str, Any] = {"snapshot_id": snapshot_id, "dry_run": dry_run, "source": source}
    conn = await asyncpg.connect(_dsn(db_url))
    try:
        tx = conn.transaction()
        await tx.start()
        try:
            snap = await conn.fetchrow("SELECT id FROM flats.snapshots WHERE id = $1", snapshot_id)
            if snap is None:
                raise SystemExit(f"no flats.snapshots row {snapshot_id}")
            await conn.execute(
                "CREATE TEMP TABLE tmp_occupancy ("
                "county text, tlid text, label text, disagreement text, building_count int, main_count int, "
                "footprint_sqft double precision, largest_sqft double precision, coverage double precision, "
                "building_value double precision, total_value double precision, year_built int, "
                "roll_building_sqft double precision) ON COMMIT DROP"
            )
            rows = 0
            batch: list[tuple[Any, ...]] = []
            for raw in _csv_rows(build_dir / OCCUPANCY_FILE):
                batch.append(_typed(raw))
                if len(batch) >= batch_size:
                    await conn.copy_records_to_table("tmp_occupancy", records=batch, columns=list(OCCUPANCY_COLUMNS))
                    rows += len(batch)
                    batch = []
            if batch:
                await conn.copy_records_to_table("tmp_occupancy", records=batch, columns=list(OCCUPANCY_COLUMNS))
                rows += len(batch)
            report["file_rows"] = rows
            report["removed"] = int(
                (await conn.execute("DELETE FROM flats.lot_occupancy WHERE snapshot_id = $1", snapshot_id)).split()[-1]
            )
            status = await conn.execute(
                """
                INSERT INTO flats.lot_occupancy
                    (lot_id, snapshot_id, label, disagreement, building_count, main_count, footprint_sqft,
                     largest_sqft, coverage, building_value, total_value, year_built, roll_building_sqft, source)
                SELECT l.id, l.snapshot_id, t.label, t.disagreement, t.building_count, t.main_count, t.footprint_sqft,
                       t.largest_sqft, t.coverage, t.building_value, t.total_value, t.year_built, t.roll_building_sqft, $2
                FROM tmp_occupancy t
                JOIN flats.lots l ON l.snapshot_id = $1 AND l.county = t.county AND l.tlid = t.tlid
                ON CONFLICT (lot_id) DO NOTHING
                """,
                snapshot_id,
                source,
            )
            report["written"] = int(status.split()[-1])
            report["lots_in_snapshot"] = await conn.fetchval("SELECT count(*) FROM flats.lots WHERE snapshot_id = $1", snapshot_id)
            report["file_rows_without_a_lot"] = rows - report["written"]
            labels = await conn.fetch(
                "SELECT label, count(*)::int AS n FROM flats.lot_occupancy WHERE snapshot_id = $1 GROUP BY label ORDER BY label",
                snapshot_id,
            )
            report["labels"] = {r["label"]: r["n"] for r in labels}
        except BaseException:
            await tx.rollback()
            raise
        if dry_run:
            await tx.rollback()
        else:
            await tx.commit()
    finally:
        await conn.close()
    return report


# --- cli ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    fe = sub.add_parser("fetch", help="download the footprint layer (needs httpx)")
    fe.add_argument("--out", type=Path, required=True, help="a new, empty directory for the download")
    fe.add_argument("--layer", default=FOOTPRINT_LAYER)
    bu = sub.add_parser("build", help="label every lot of a lot table (needs shapely + pyarrow)")
    bu.add_argument("--footprints", type=Path, required=True, help="a fetch directory")
    bu.add_argument("--lots", type=Path, required=True, help="normalize's lots.parquet or quadfit's s1_lots.parquet")
    bu.add_argument("--out", type=Path, required=True)
    ld = sub.add_parser("load", help="replace one snapshot's flats.lot_occupancy rows (needs asyncpg)")
    ld.add_argument("--build", type=Path, required=True, help="a build directory")
    ld.add_argument("--snapshot", type=int, required=True, help="flats.snapshots id the lots belong to")
    ld.add_argument("--db-url", default=None, help="default: app settings' database_url")
    ld.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "fetch":
        if args.out.exists() and any(args.out.iterdir()):
            raise SystemExit(f"{args.out} is not empty; a download goes in a new directory")
        print(json.dumps(fetch(args.out, args.layer), indent=2))
        return 0
    if args.command == "build":
        print(json.dumps(build(args.footprints, args.lots, args.out), indent=2))
        return 0
    db_url = args.db_url
    if db_url is None:
        from app.config import settings

        db_url = settings.database_url
    report = asyncio.run(load(args.build, db_url, snapshot_id=args.snapshot, dry_run=args.dry_run))
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("written") else 1


if __name__ == "__main__":
    sys.exit(main())
