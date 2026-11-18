"""The USDA soil survey under each lot: extract the survey, cut it against the lots, load it.

FOLLOWUPS 196 (:mod:`flats.ingest.soil`). A NOTE, never a colour: nothing that
screens reads these tables. Four steps, on whichever box has what each needs:

* ``extract`` (sqlite3 + shapely + pyproj; LXC 137) reads the NRCS state
  GeoPackage ("SQLite SSURGO", Oregon, from NRCS's public soils share
  https://nrcs.app.box.com/v/soils -> SSURGO -> SQLite SSURGO (Geopackages) ->
  States) for the survey areas that overlap the named counties, and writes
  ``mapunits.csv.gz``, ``components.csv.gz`` (the values the note reads,
  folded per ``cokey``, with each component's months as JSON),
  ``polygons.parquet`` (one map-unit polygon part per row, EPSG:2913 WKB)
  and ``meta.json`` (the file, its publication date, every survey area with
  its ``saverest``). The GeoPackage is data, never code: it is opened
  read-only and queried.
* ``sda`` (httpx; anywhere with the internet) fills what the state download
  leaves out from Soil Data Access (the public SDA tabular service): the
  limiting reasons of the two building ratings (``cointerp`` ruledepth 1) and
  ``mapunit.nationalmusym``. It rewrites the two tables in place and notes
  the fetch in ``meta.json``. Optional: without it the reasons and the
  national symbol say "not in this download".
* ``build`` (shapely + pyarrow; LXC 137) cuts every polygon part against every
  lot of a lot table (the normalize stage's ``lots.parquet``) and writes
  ``lot_soil.csv.gz`` (one row per lot per map unit, plus the uncovered part)
  and ``summary.json``; it copies the extract's tables beside them.
* ``load`` (asyncpg; the api container) upserts ``flats.soil_map_units`` and
  ``flats.soil_components`` and replaces one snapshot's ``flats.lot_soil``
  rows -- every lot, or with ``--colour green`` only the lots the run shown
  (or ``--run``) has GREEN, so the green lots can go first. No lot, result or
  run is touched. ``--tables-only`` refreshes the two survey tables alone
  (after an ``sda`` fill).

Usage::

    python scripts/flats_lot_soil.py extract --gpkg data/flats/soil/ssurgo_or/SQLite_SSURGO_OR/SQLite_SSURGO_OR.gpkg \\
        --published 2026-10-01 --out data/flats/soil/extract_2026-10-01
    python scripts/flats_lot_soil.py sda --extract data/flats/soil/extract_2026-10-01        # optional
    python scripts/flats_lot_soil.py build --extract data/flats/soil/extract_2026-10-01 \\
        --lots data/flats/normalized/<snapshot>/lots.parquet --out data/flats/soil/build_<snapshot> --processes 12
    # copy the build directory to VM 114's /root/stacks/vicinitideals/data/flats/soil/<name>, then
    docker compose run --rm api python scripts/flats_lot_soil.py load \\
        --build /app/data/flats/soil/<name> --snapshot <flats.snapshots id> [--colour green] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import json
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from flats.ingest.soil import (  # noqa: E402
    COMPONENT_COLUMNS,
    DWELLINGS,
    INTERPRETATIONS,
    LOT_COLUMNS,
    MAP_UNIT_COLUMNS,
    SMALL_COMMERCIAL,
    SOURCE_NAME,
    dominant_condition,
    fold_interpretations,
    fold_months,
    measure_lots,
    unit_wet_season,
    wet_season,
)

MAPUNITS_FILE = "mapunits.csv.gz"
COMPONENTS_FILE = "components.csv.gz"
POLYGONS_FILE = "polygons.parquet"
META_FILE = "meta.json"
LOT_FILE = "lot_soil.csv.gz"
SUMMARY_FILE = "summary.json"

#: Oregon North, international feet -- the lot table's projection.
OUT_SRID = 2913
COUNTIES = ("Multnomah", "Clackamas", "Washington")
COUNTY_LETTERS = {"M": "multnomah", "C": "clackamas", "W": "washington"}
SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/tabular/post.rest"
SOURCE_PAGE = "https://nrcs.app.box.com/v/soils"


# --- shared ----------------------------------------------------------------------


def _write_csv(path: Path, columns: Iterable[str], rows: Iterable[dict[str, Any]]) -> int:
    columns = tuple(columns)
    n = 0
    with gzip.open(path, "wt", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        for row in rows:
            cells = []
            for c in columns:
                value = row.get(c)
                if value is None:
                    cells.append("")
                elif isinstance(value, (list, dict)):
                    cells.append(json.dumps(value, separators=(",", ":")))
                else:
                    cells.append(value)
            writer.writerow(cells)
            n += 1
    return n


def read_csv(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as fh:
        return [{k: (v if v != "" else None) for k, v in row.items()} for row in csv.DictReader(fh)]


# --- extract -----------------------------------------------------------------------


def _gpkg_wkb(blob: bytes) -> bytes:
    """The WKB inside a GeoPackage geometry blob (header + optional envelope)."""
    if blob[:2] != b"GP":
        raise ValueError("not a GeoPackage geometry")
    flags = blob[3]
    envelope = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(flags >> 1) & 0b111]
    return bytes(blob[8 + envelope:])


def _areas(conn: sqlite3.Connection, counties: Iterable[str]) -> list[dict[str, Any]]:
    names = tuple(counties)
    marks = ",".join("?" for _ in names)
    rows = conn.execute(
        f"""SELECT DISTINCT l.areasymbol, l.areaname, s.saverest, s.saversion, s.tabularverest
            FROM laoverlap lo JOIN legend l ON l.lkey = lo.lkey
            JOIN sacatalog s ON s.areasymbol = l.areasymbol
            WHERE lo.areatypename = 'County or Parish' AND lo.areaname IN ({marks})
            ORDER BY l.areasymbol""",
        names,
    ).fetchall()
    return [dict(zip(("areasymbol", "areaname", "saverest", "saversion", "tabularverest"), r)) for r in rows]


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info('{table}')")}


def extract(gpkg: Path, out: Path, *, counties: Iterable[str] = COUNTIES, published: str | None = None) -> dict[str, Any]:
    """Read the survey tables and polygons for the counties' survey areas into ``out``."""
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    import shapely
    from pyproj import Transformer

    started = time.time()
    conn = sqlite3.connect(f"file:{gpkg.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    areas = _areas(conn, counties)
    if not areas:
        raise SystemExit(f"{gpkg}: no survey area overlaps {list(counties)}")
    symbols = tuple(a["areasymbol"] for a in areas)
    marks = ",".join("?" for _ in symbols)
    national = "m.nationalmusym" if "nationalmusym" in _columns(conn, "mapunit") else "NULL"

    units = [dict(r) for r in conn.execute(
        f"""SELECT m.mukey, l.areasymbol, l.areaname, s.saverest, m.musym, {national} AS nationalmusym,
                   m.muname, m.mukind, a.drclassdcd, a.hydgrpdcd, a.hydclprs, a.wtdepannmin, a.brockdepmin,
                   a.engdwobdcd
            FROM mapunit m JOIN legend l ON l.lkey = m.lkey JOIN sacatalog s ON s.areasymbol = l.areasymbol
            LEFT JOIN muaggatt a ON a.mukey = m.mukey
            WHERE l.areasymbol IN ({marks})""",
        symbols,
    )]
    mukeys = {str(u["mukey"]) for u in units}
    comp_sql = f"""
        SELECT c.cokey, c.mukey, c.compname, c.comppct_r, c.majcompflag, c.compkind,
               c.taxclname, c.taxorder, c.taxsuborder, c.taxgrtgroup, c.taxsubgrp, c.taxpartsize,
               c.drainagecl, c.hydricrating, c.hydgrp,
               (SELECT MAX(h.lep_r) FROM chorizon h WHERE h.cokey = c.cokey) AS lep_max,
               (SELECT MIN(r.resdept_r) FROM corestrictions r WHERE r.cokey = c.cokey) AS restriction_cm,
               (SELECT r.reskind FROM corestrictions r WHERE r.cokey = c.cokey AND r.resdept_r IS NOT NULL
                  ORDER BY r.resdept_r, r.reskind LIMIT 1) AS restriction_kind
        FROM component c JOIN mapunit m ON m.mukey = c.mukey JOIN legend l ON l.lkey = m.lkey
        WHERE l.areasymbol IN ({marks})"""
    components = [dict(r) for r in conn.execute(comp_sql, symbols)]
    interps = [dict(r) for r in conn.execute(
        f"""SELECT i.cokey, i.mrulename, i.ruledepth, i.rulename, i.interphr, i.interphrc
            FROM cointerp i JOIN component c ON c.cokey = i.cokey JOIN mapunit m ON m.mukey = c.mukey
            JOIN legend l ON l.lkey = m.lkey
            WHERE l.areasymbol IN ({marks}) AND i.mrulename IN (?, ?) AND i.ruledepth IN (0, 1)""",
        (*symbols, DWELLINGS, SMALL_COMMERCIAL),
    )]
    month_rows = [dict(r) for r in conn.execute(
        f"""SELECT cm.cokey, cm.monthseq, cm.month, cm.flodfreqcl, cm.pondfreqcl,
                   sm.soimoiststat, sm.soimoistdept_r
            FROM comonth cm JOIN component c ON c.cokey = cm.cokey JOIN mapunit m ON m.mukey = c.mukey
            JOIN legend l ON l.lkey = m.lkey
            LEFT JOIN cosoilmoist sm ON sm.comonthkey = cm.comonthkey
            WHERE l.areasymbol IN ({marks})""",
        symbols,
    )]
    reasons_rows = sum(1 for r in interps if int(r.get("ruledepth") or 0) == 1)
    folded = fold_interpretations(interps)
    months = fold_months(month_rows)
    by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for comp in components:
        cokey = str(comp["cokey"])
        comp.update(folded.get(cokey, {}))
        comp_months = months.get(cokey, [])
        comp["months"] = comp_months
        status, cm, when = wet_season(comp_months)
        comp["wet_season_status"], comp["wet_season_cm"], comp["wet_season_months"] = status, cm, ",".join(when)
        wet = [m for m in comp_months if m.get("wet_top_cm") is not None]
        if wet:
            low = min(m["wet_top_cm"] for m in wet)
            comp["water_table_cm"] = low
            comp["water_table_month"] = next(m["month"] for m in wet if m["wet_top_cm"] == low)
        by_unit[str(comp["mukey"])].append(comp)
    for unit in units:
        comps = by_unit.get(str(unit["mukey"]), [])
        unit["dwellings_dcd"] = dominant_condition(comps, "dwellings_rating")
        unit["small_commercial_dcd"] = dominant_condition(comps, "small_commercial_rating")
        status, cm, when, cokey = unit_wet_season(comps)
        unit["wet_season_status"], unit["wet_season_cm"] = status, cm
        unit["wet_season_months"], unit["wet_season_cokey"] = ",".join(when), cokey

    # Polygons: one part per row, reprojected to the lot table's CRS.
    to_ft = Transformer.from_crs(4326, OUT_SRID, always_xy=True)
    keys: list[str] = []
    parts: list[Any] = []
    broken = 0
    for mukey, blob in conn.execute(f"SELECT mukey, shape FROM mupolygon WHERE areasymbol IN ({marks})", symbols):
        try:
            geom = shapely.from_wkb(_gpkg_wkb(blob))
        except Exception:  # noqa: BLE001 -- a broken ring is counted, not fatal
            broken += 1
            continue
        for part in shapely.get_parts(geom):
            keys.append(str(mukey))
            parts.append(part)
    conn.close()
    arr = np.array(parts, dtype=object)
    arr = shapely.transform(arr, lambda xy: np.column_stack(to_ft.transform(xy[:, 0], xy[:, 1])))
    invalid = ~shapely.is_valid(arr)
    if invalid.any():
        arr[invalid] = shapely.make_valid(arr[invalid])
    out.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table({"mukey": keys, "wkb": shapely.to_wkb(arr)}), out / POLYGONS_FILE
    )
    _write_csv(out / MAPUNITS_FILE, MAP_UNIT_COLUMNS, units)
    _write_csv(out / COMPONENTS_FILE, COMPONENT_COLUMNS, components)
    meta = {
        "source": SOURCE_NAME,
        "file": gpkg.name,
        "published": published,
        "source_page": SOURCE_PAGE,
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counties": list(counties),
        "survey_areas": areas,
        "map_units": len(units),
        "map_units_with_polygons": len(set(keys)),
        "components": len(components),
        "polygon_parts": len(parts),
        "unreadable_polygons": broken,
        "invalid_repaired": int(invalid.sum()),
        "reasons_rows": reasons_rows,
        "reasons_in_source": reasons_rows > 0,
        "nationalmusym_in_source": national != "NULL",
        "map_units_without_polygons": sorted(mukeys - set(keys))[:50],
        "seconds": round(time.time() - started, 1),
    }
    (out / META_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def source_label(meta: dict[str, Any]) -> str:
    """One line naming the agency, the product, each survey area and its date."""
    areas = "; ".join(
        f"{a.get('areasymbol')} {a.get('areaname')} ({a.get('saverest')})" for a in meta.get("survey_areas") or []
    )
    published = f", state download of {meta['published']}" if meta.get("published") else ""
    return f"{SOURCE_NAME}{published}: {areas}"


# --- sda (optional fill) -----------------------------------------------------------


def _sda(client: Any, query: str, tries: int = 4) -> list[dict[str, Any]]:
    for attempt in range(tries):
        try:
            resp = client.post(SDA_URL, json={"format": "JSON+COLUMNNAME", "query": query}, timeout=180)
            resp.raise_for_status()
            table = resp.json().get("Table") or []
            if not table:
                return []
            head, *body = table
            return [dict(zip(head, row)) for row in body]
        except Exception:  # noqa: BLE001 -- retried, then raised
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError("unreachable")


def sda_fill(extract_dir: Path, *, batch: int = 400) -> dict[str, Any]:
    """Fill the limiting reasons and ``nationalmusym`` from Soil Data Access."""
    import httpx

    units = read_csv(extract_dir / MAPUNITS_FILE)
    comps = read_csv(extract_dir / COMPONENTS_FILE)
    cokeys = [str(c["cokey"]) for c in comps]
    mukeys = [str(u["mukey"]) for u in units]
    interps: list[dict[str, Any]] = []
    national: dict[str, str] = {}
    with httpx.Client(headers={"User-Agent": "vicinitideals-flats/soil"}) as client:
        for i in range(0, len(cokeys), batch):
            chunk = ",".join(f"'{int(k)}'" for k in cokeys[i:i + batch])
            interps += _sda(client, (
                "SELECT cokey, mrulename, ruledepth, rulename, interphr, interphrc FROM cointerp "
                f"WHERE cokey IN ({chunk}) AND ruledepth IN (0, 1) AND mrulename IN "
                f"('{DWELLINGS}', '{SMALL_COMMERCIAL}')"
            ))
        for i in range(0, len(mukeys), batch):
            chunk = ",".join(f"'{int(k)}'" for k in mukeys[i:i + batch])
            for row in _sda(client, f"SELECT mukey, nationalmusym FROM mapunit WHERE mukey IN ({chunk})"):
                national[str(row["mukey"])] = row.get("nationalmusym")
    folded = fold_interpretations(interps)
    filled = 0
    for comp in comps:
        found = folded.get(str(comp["cokey"]), {})
        for key in INTERPRETATIONS.values():
            if found.get(f"{key}_reasons"):
                comp[f"{key}_reasons"] = found[f"{key}_reasons"]
                filled += 1
    for unit in units:
        unit["nationalmusym"] = national.get(str(unit["mukey"])) or unit.get("nationalmusym")
    _write_csv(extract_dir / MAPUNITS_FILE, MAP_UNIT_COLUMNS, units)
    _write_csv(extract_dir / COMPONENTS_FILE, COMPONENT_COLUMNS, comps)
    meta = json.loads((extract_dir / META_FILE).read_text(encoding="utf-8"))
    meta["sda_fill"] = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "url": SDA_URL,
        "interp_rows": len(interps),
        "reasons_filled": filled,
        "nationalmusym_filled": sum(1 for v in national.values() if v),
    }
    (extract_dir / META_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta["sda_fill"]


# --- build -----------------------------------------------------------------------


def read_lots(path: Path) -> list[dict[str, Any]]:
    """``county``, ``tlid`` and ``geom`` of every lot of normalize's ``lots.parquet``."""
    import pyarrow.parquet as pq
    import shapely

    names = set(pq.ParquetFile(path).schema_arrow.names)
    county_col = "county" if "county" in names else "COUNTY"
    tlid_col = "tlid" if "tlid" in names else "TLID"
    table = pq.read_table(path, columns=[county_col, tlid_col, "wkb"])
    geoms = shapely.from_wkb(table.column("wkb").to_numpy(zero_copy_only=False))
    lots = []
    for county, tlid, geom in zip(table.column(county_col).to_pylist(), table.column(tlid_col).to_pylist(), geoms):
        county = str(county or "")
        lots.append({"county": COUNTY_LETTERS.get(county, county.lower()), "tlid": tlid, "geom": geom})
    return lots


def read_polygons(path: Path) -> list[tuple[str, Any]]:
    import pyarrow.parquet as pq
    import shapely

    table = pq.read_table(path)
    geoms = shapely.from_wkb(table.column("wkb").to_numpy(zero_copy_only=False))
    return list(zip((str(k) for k in table.column("mukey").to_pylist()), geoms))


_SOILS: list[tuple[str, Any]] = []


def _measure_chunk(lots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list(measure_lots(lots, _SOILS))


def build(extract_dir: Path, lots_path: Path, out: Path, *, processes: int = 1, chunk: int = 5000) -> dict[str, Any]:
    """Cut the extract's polygons against every lot of ``lots_path``; returns the summary."""
    import shutil

    global _SOILS
    started = time.time()
    meta = json.loads((extract_dir / META_FILE).read_text(encoding="utf-8"))
    lots = read_lots(lots_path)
    _SOILS = read_polygons(extract_dir / POLYGONS_FILE)
    batches = [lots[i:i + chunk] for i in range(0, len(lots), chunk)]
    rows: list[dict[str, Any]] = []
    if processes > 1:
        import multiprocessing as mp

        with mp.get_context("fork").Pool(processes) as pool:
            for part in pool.imap(_measure_chunk, batches):
                rows.extend(part)
    else:
        for batch in batches:
            rows.extend(_measure_chunk(batch))
    out.mkdir(parents=True, exist_ok=True)
    _write_csv(out / LOT_FILE, LOT_COLUMNS, rows)
    for name in (MAPUNITS_FILE, COMPONENTS_FILE, META_FILE):
        shutil.copyfile(extract_dir / name, out / name)
    units = {str(u["mukey"]): u for u in read_csv(extract_dir / MAPUNITS_FILE)}
    per_lot: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        per_lot[(row["county"], row["tlid"])].append(row)
    spans: Counter = Counter()
    uncovered_lots: Counter = Counter()
    worst_gap = 0.0
    for (county, _tlid), lot_rows in per_lot.items():
        covered = [r for r in lot_rows if r["mukey"]]
        spans[min(len(covered), 5)] += 1
        if not covered:
            uncovered_lots[county] += 1
        total = sum(float(r["area_sqft"]) for r in lot_rows)
        lot_area = float(lot_rows[0]["lot_area_sqft"])
        worst_gap = max(worst_gap, abs(total - lot_area) / lot_area if lot_area else 0.0)
    summary = {
        "source": source_label(meta),
        "lots_file": str(lots_path),
        "lots_read": len(lots),
        "lots_measured": len(per_lot),
        "rows": len(rows),
        "map_units_per_lot": {("5+" if k == 5 else str(k)): v for k, v in sorted(spans.items())},
        "lots_with_no_coverage": dict(uncovered_lots),
        "lots_partly_uncovered": sum(1 for lr in per_lot.values() if any(not r["mukey"] for r in lr) and any(r["mukey"] for r in lr)),
        "largest_sum_gap_share": round(worst_gap, 6),
        "map_units_used": len({r["mukey"] for r in rows if r["mukey"]}),
        "map_units_unknown": sorted({r["mukey"] for r in rows if r["mukey"] and r["mukey"] not in units})[:20],
        "processes": processes,
        "seconds": round(time.time() - started, 1),
    }
    (out / SUMMARY_FILE).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


# --- load -----------------------------------------------------------------------


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


_UNIT_NUM = {"hydclprs", "wtdepannmin", "brockdepmin", "wet_season_cm"}
_COMP_NUM = {"comppct_r", "lep_max", "restriction_cm", "water_table_cm", "wet_season_cm"}


def _typed(row: dict[str, Any], columns: tuple[str, ...], numeric: set[str]) -> tuple[Any, ...]:
    out: list[Any] = []
    for col in columns:
        value = row.get(col)
        if value is None or value == "":
            out.append(None)
        elif col in numeric:
            out.append(float(value))
        elif col == "months":
            out.append(value if isinstance(value, str) else json.dumps(value))
        else:
            out.append(str(value))
    return tuple(out)


def _lot_rows(path: Path) -> Iterator[tuple[Any, ...]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        if tuple(header) != LOT_COLUMNS:
            raise SystemExit(f"{path}: columns {header} are not {list(LOT_COLUMNS)}")
        for county, tlid, mukey, area, share, lot_area in reader:
            yield county, tlid, mukey or None, float(area), float(share), float(lot_area)


async def load(
    build_dir: Path,
    db_url: str,
    *,
    snapshot_id: int,
    colour: str | None = None,
    run_id: int | None = None,
    tables_only: bool = False,
    dry_run: bool = False,
    batch_size: int = 20_000,
) -> dict[str, Any]:
    """Upsert the survey tables and replace one snapshot's ``flats.lot_soil`` rows
    (every lot, or only the lots the run has in ``colour``)."""
    import asyncpg

    meta = json.loads((build_dir / META_FILE).read_text(encoding="utf-8"))
    source = source_label(meta)[:400]
    report: dict[str, Any] = {"snapshot_id": snapshot_id, "dry_run": dry_run, "source": source, "colour": colour}
    units = read_csv(build_dir / MAPUNITS_FILE)
    comps = read_csv(build_dir / COMPONENTS_FILE)
    conn = await asyncpg.connect(_dsn(db_url))
    try:
        tx = conn.transaction()
        await tx.start()
        try:
            if await conn.fetchrow("SELECT id FROM flats.snapshots WHERE id = $1", snapshot_id) is None:
                raise SystemExit(f"no flats.snapshots row {snapshot_id}")
            ucols = ", ".join(MAP_UNIT_COLUMNS)
            await conn.executemany(
                f"INSERT INTO flats.soil_map_units ({ucols}, source) VALUES "
                f"({', '.join(f'${i + 1}' for i in range(len(MAP_UNIT_COLUMNS) + 1))}) "
                f"ON CONFLICT (mukey) DO UPDATE SET "
                + ", ".join(f"{c} = EXCLUDED.{c}" for c in (*MAP_UNIT_COLUMNS[1:], "source")),
                [(*_typed(u, MAP_UNIT_COLUMNS, _UNIT_NUM), source) for u in units],
            )
            ccols = ", ".join(COMPONENT_COLUMNS)
            places = ", ".join(
                f"${i + 1}::jsonb" if c == "months" else f"${i + 1}" for i, c in enumerate(COMPONENT_COLUMNS)
            )
            await conn.executemany(
                f"INSERT INTO flats.soil_components ({ccols}) VALUES ({places}) "
                f"ON CONFLICT (cokey) DO UPDATE SET "
                + ", ".join(f"{c} = EXCLUDED.{c}" for c in COMPONENT_COLUMNS[1:]),
                [_typed(c, COMPONENT_COLUMNS, _COMP_NUM) for c in comps],
            )
            report["map_units"] = len(units)
            report["components"] = len(comps)
            if not tables_only:
                await _load_lots(conn, build_dir, snapshot_id, colour, run_id, report, batch_size)
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


async def _load_lots(
    conn: Any, build_dir: Path, snapshot_id: int, colour: str | None, run_id: int | None,
    report: dict[str, Any], batch_size: int,
) -> None:
    from app.models.flats import FLATS_COLOUR_ORDER

    await conn.execute(
        "CREATE TEMP TABLE tmp_lot_soil (county text, tlid text, mukey text, area_sqft double precision, "
        "share double precision, lot_area_sqft double precision) ON COMMIT DROP"
    )
    rows = 0
    batch: list[tuple[Any, ...]] = []
    for row in _lot_rows(build_dir / LOT_FILE):
        batch.append(row)
        if len(batch) >= batch_size:
            await conn.copy_records_to_table("tmp_lot_soil", records=batch, columns=list(LOT_COLUMNS))
            rows += len(batch)
            batch = []
    if batch:
        await conn.copy_records_to_table("tmp_lot_soil", records=batch, columns=list(LOT_COLUMNS))
        rows += len(batch)
    report["file_rows"] = rows
    await conn.execute(
        "CREATE TEMP TABLE tmp_soil_lots ON COMMIT DROP AS "
        "SELECT DISTINCT l.id AS lot_id FROM tmp_lot_soil t "
        "JOIN flats.lots l ON l.snapshot_id = $1 AND l.county = t.county AND l.tlid = t.tlid",
        snapshot_id,
    )
    if colour is not None:
        if colour not in FLATS_COLOUR_ORDER:
            raise SystemExit(f"--colour {colour!r} is not one of {FLATS_COLOUR_ORDER}")
        if run_id is None:
            run_id = await conn.fetchval(
                "SELECT id FROM flats.runs WHERE status = 'complete' ORDER BY id DESC LIMIT 1"
            )
        snap = await conn.fetchval("SELECT snapshot_id FROM flats.runs WHERE id = $1", run_id)
        if snap != snapshot_id:
            raise SystemExit(f"run {run_id} screens snapshot {snap}, not {snapshot_id}")
        await conn.execute(
            "DELETE FROM tmp_soil_lots s WHERE NOT EXISTS (SELECT 1 FROM flats.lot_best b "
            "WHERE b.run_id = $1 AND b.lot_id = s.lot_id AND b.best_colour = $2)",
            run_id,
            FLATS_COLOUR_ORDER.index(colour),
        )
        report["run_id"] = run_id
        report["lots_in_colour"] = await conn.fetchval(
            "SELECT count(*) FROM flats.lot_best WHERE run_id = $1 AND best_colour = $2",
            run_id, FLATS_COLOUR_ORDER.index(colour),
        )
        removed = await conn.execute(
            "DELETE FROM flats.lot_soil WHERE lot_id IN (SELECT lot_id FROM tmp_soil_lots)"
        )
    else:
        removed = await conn.execute("DELETE FROM flats.lot_soil WHERE snapshot_id = $1", snapshot_id)
    report["removed"] = int(removed.split()[-1])
    status = await conn.execute(
        """
        INSERT INTO flats.lot_soil (lot_id, snapshot_id, mukey, area_sqft, share)
        SELECT l.id, l.snapshot_id, t.mukey, t.area_sqft, t.share
        FROM tmp_lot_soil t
        JOIN flats.lots l ON l.snapshot_id = $1 AND l.county = t.county AND l.tlid = t.tlid
        JOIN tmp_soil_lots s ON s.lot_id = l.id
        """,
        snapshot_id,
    )
    report["written"] = int(status.split()[-1])
    report["lots_written"] = await conn.fetchval("SELECT count(*) FROM tmp_soil_lots")
    report["lots_in_snapshot"] = await conn.fetchval("SELECT count(*) FROM flats.lots WHERE snapshot_id = $1", snapshot_id)
    report["lots_with_soil_in_snapshot"] = await conn.fetchval(
        "SELECT count(DISTINCT lot_id) FROM flats.lot_soil WHERE snapshot_id = $1", snapshot_id
    )


# --- cli ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("extract", help="read the survey for the counties out of the NRCS state GeoPackage")
    ex.add_argument("--gpkg", type=Path, required=True)
    ex.add_argument("--out", type=Path, required=True, help="a new, empty directory")
    ex.add_argument("--published", default=None, help="the download's publication date (its _ReadMe.txt)")
    ex.add_argument("--counties", default=",".join(COUNTIES))
    sd = sub.add_parser("sda", help="fill limiting reasons and nationalmusym from Soil Data Access (needs httpx)")
    sd.add_argument("--extract", type=Path, required=True)
    bu = sub.add_parser("build", help="cut the survey against every lot of a lot table (needs shapely + pyarrow)")
    bu.add_argument("--extract", type=Path, required=True)
    bu.add_argument("--lots", type=Path, required=True, help="normalize's lots.parquet")
    bu.add_argument("--out", type=Path, required=True)
    bu.add_argument("--processes", type=int, default=1)
    ld = sub.add_parser("load", help="upsert the survey tables and replace a snapshot's lot rows (needs asyncpg)")
    ld.add_argument("--build", type=Path, required=True)
    ld.add_argument("--snapshot", type=int, required=True, help="flats.snapshots id the lots belong to")
    ld.add_argument("--colour", default=None, help="only the lots the run has in this colour (e.g. green)")
    ld.add_argument("--run", type=int, default=None, help="the run --colour reads (default: newest complete)")
    ld.add_argument("--tables-only", action="store_true", help="refresh the map-unit and component tables only")
    ld.add_argument("--db-url", default=None, help="default: app settings' database_url")
    ld.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "extract":
        if args.out.exists() and any(args.out.iterdir()):
            raise SystemExit(f"{args.out} is not empty; an extract goes in a new directory")
        counties = tuple(c.strip() for c in args.counties.split(",") if c.strip())
        print(json.dumps(extract(args.gpkg, args.out, counties=counties, published=args.published), indent=2))
        return 0
    if args.command == "sda":
        print(json.dumps(sda_fill(args.extract), indent=2))
        return 0
    if args.command == "build":
        print(json.dumps(build(args.extract, args.lots, args.out, processes=args.processes), indent=2))
        return 0
    db_url = args.db_url
    if db_url is None:
        from app.config import settings

        db_url = settings.database_url
    report = asyncio.run(
        load(args.build, db_url, snapshot_id=args.snapshot, colour=args.colour, run_id=args.run,
             tables_only=args.tables_only, dry_run=args.dry_run)
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if (args.tables_only or report.get("written")) else 1


if __name__ == "__main__":
    sys.exit(main())
