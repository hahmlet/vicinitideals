"""Carry a bridge run (``flats.ingest.quadfit``) into ``flats.runs`` / ``flats.lots`` /
``flats.lot_results`` in production.

Two halves, because the files and the database live on different boxes and
neither has the other's libraries:

* ``export`` runs where the stage files are (LXC 137, the repo's venv with
  pandas / pyarrow / shapely). It joins the run's ``lots.parquet`` to quadfit's
  s4 (the taxlot polygon, address, zone) and s5o (envelope, slope, sewer,
  flood) and to quadfit's own verdict, and writes a **bundle**: ``lots.csv.gz``
  (one row per lot, WKB as hex, design-independent facts as JSON),
  ``results.csv.gz`` (one row per lot x design) and ``run.json`` (what the
  run was, and the counts the load must reproduce).
* ``load`` runs inside the api container (asyncpg, no pandas) against the
  bundle at ``/app/data/...``. It writes the catalog's designs once, finds or
  creates the run row, COPYs the bundle into temp tables and upserts: lots on
  ``(county, tlid)``, results on ``(lot_id, design_key, run_id)``. Geometry is
  built in PostGIS (``ST_GeomFromWKB`` at SRID 2913, the centroid transformed
  to 4326), so nothing geospatial is needed on the Python side. Run twice, the
  second load changes nothing but ``updated_run_id``. ``--dry-run`` does the
  whole load in a transaction and rolls it back -- and leaves dead tuples the
  size of the load behind (the county: 2.4 GB), so after a dry run on a full
  county follow the real load with ``VACUUM (FULL, ANALYZE)`` on
  ``flats.lot_results`` and ``flats.lots`` (14 s on 2026-09-18, 3.0 -> 1.8 GB),
  one statement per ``psql -c``. The county load itself is about a minute.

What lands where:

* ``lot_results.tier`` carries the screen's OWN word -- ``green`` / ``yellow``
  / ``unknown`` / ``red`` (:class:`flats.score.screen.Triage`), not quadfit's
  ``review``. Today that is ``unknown`` on every lot (every corpus value is a
  draft), and the colour the lot takes once the corpus is signed sits in
  ``checks->>'if_signed'`` beside it -- named, never in the verdict's place
  (Steph, 2026-09-17). ``slack_ft`` is the fit's slack; ``binding`` is the head
  check first and the other failing checks after it.
* ``lots.facts`` holds what is true of the lot whatever gets built: the
  geometry tier, frontage, width, depth, alley width, cul-de-sac, the observed
  site facts as the screen saw them, s5o's envelope areas / slope / sewer /
  flood, and quadfit's own verdict under ``quadfit`` (the county map's answer,
  which the comparison reads). The lot polygon is s4's; quadfit's carved
  envelope is not carried (no column for it yet -- FOLLOWUPS).
* ``lots.jurisdiction`` is the rule-layer id (``or/multnomah/portland``), as
  the model asks; quadfit's short name stays in ``facts.quadfit_jurisdiction``.

Usage, on 137::

    PYTHONIOENCODING=utf-8 .venv/bin/python scripts/flats_load_bridge.py export \\
        --run-dir /root/bridge_county2 --out /root/bridge_county2/bundle
    scp -r /root/bridge_county2/bundle root@<vm114>:/root/stacks/vicinitideals/data/flats/bridge/county2

and on 114::

    docker compose run --rm api python scripts/flats_load_bridge.py load \\
        --bundle /app/data/flats/bridge/county2 [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import hashlib
import json
import math
import socket
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from flats.designs.model import Design, load_catalog  # noqa: E402
from flats.encode.port_quadfit import COUNTY, layer_id_for  # noqa: E402
from flats.rules.loader import CONFIG_ROOT as RULES_ROOT  # noqa: E402

#: The files a bundle is made of.
LOTS_FILE = "lots.csv.gz"
RESULTS_FILE = "results.csv.gz"
RUN_FILE = "run.json"

LOT_COLUMNS = (
    "tlid",
    "county",
    "jurisdiction",
    "zone_raw",
    "zone",
    "site_address",
    "area_sqft",
    "wkb_hex",
    "facts",
)
RESULT_COLUMNS = ("tlid", "county", "design_key", "tier", "slack_ft", "binding", "checks")

#: s4 columns the export reads, besides TLID. Any the file lacks are read as
#: absent -- the same rule the bridge follows.
S4_WANTED = (
    "COUNTY",
    "SITEADDR",
    "jurisdiction",
    "zone_raw",
    "zone",
    "area_sqft",
    "tier",
    "frontage_ft",
    "lot_width_ft",
    "lot_depth_ft",
    "front_bearings_json",
    "alley_width_ft",
    "fronts_cul_de_sac",
    "split_zone",
    "inside_ugb",
    "has_z_overlay",
    "zone_frac",
    "stack_count",
    "wkb",
)
S5O_WANTED = (
    "envelope_sqft",
    "envelope_setback_sqft",
    "envelope_carved_sqft",
    "slope_mean_pct",
    "slope_p85_pct",
    "slope_max_pct",
    "slope_source",
    "sewer_main_dist_ft",
    "in_sewer_district",
    "ovl_fema_sfha",
    "ovl_fema_floodway",
)
QUADFIT_WANTED = (
    "triage",
    "binding_constraint",
    "policy_exclusion",
    "parking_tier",
    "stalls_provided",
    "layout_method",
)

#: The screen's four words, the only values ``lot_results.tier`` takes here.
TIERS = ("green", "yellow", "unknown", "red")


# --- shared -----------------------------------------------------------------


def rules_version(root: Path = RULES_ROOT) -> str:
    """Content hash of the encoded rules, the run's ``rules_version``.

    Every file under the jurisdictions directory, path and bytes, in sorted
    order; a rule edit changes results with no code change, so it gets its own
    version. Full sha256 hex (64 chars, the column's width).
    """
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(str(path.relative_to(root)).replace("\\", "/").encode())
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _clean(value: Any) -> Any:
    """A JSON-safe Python value: NaN / NaT / numpy scalars leave as None / plain."""
    if value is None:
        return None
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, (str, bool, int)):
        return value
    if hasattr(value, "item"):  # numpy scalar
        return _clean(value.item())
    if type(value).__name__ == "NAType":  # pandas.NA, whose truth value is an error
        return None
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    try:
        if value != value:  # pandas NA / NaT
            return None
    except Exception:  # pragma: no cover - exotic types
        pass
    return str(value)


def _split(value: Any) -> list[str]:
    """A comma-joined bridge column back to its list; '' and None are empty."""
    text = _clean(value)
    if not text or not isinstance(text, str):
        return []
    return [part for part in text.split(",") if part]


def _num(value: Any) -> float | None:
    v = _clean(value)
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    v = _num(value)
    return None if v is None else int(round(v))


#: RLIS's county letter on the taxlot record.
COUNTY_LETTER = {"M": "multnomah", "C": "clackamas", "W": "washington"}


def lot_county(s4: dict[str, Any]) -> str:
    """The taxlot's county -- the assessor's, from s4's ``COUNTY`` letter.

    Not the jurisdiction's: Portland reaches into Clackamas County and Happy
    Valley into Multnomah, and ``(county, tlid)`` is the lot's natural key, so
    it takes the county whose roll the TLID is on. The jurisdiction's county
    is the fallback for a stage file without the letter.
    """
    letter = _clean(s4.get("COUNTY"))
    if isinstance(letter, str) and letter.strip().upper()[:1] in COUNTY_LETTER:
        return COUNTY_LETTER[letter.strip().upper()[:1]]
    return COUNTY.get(str(s4.get("jurisdiction")), "unknown")


def lot_facts(s4: dict[str, Any], s5o: dict[str, Any], observed: dict[str, Any], quadfit: dict[str, Any]) -> dict[str, Any]:
    """The design-independent record for one lot, from the four sources."""
    bearings_raw = _clean(s4.get("front_bearings_json"))
    try:
        bearings = [float(b) for b in json.loads(bearings_raw)] if bearings_raw else []
    except (TypeError, ValueError):
        bearings = []
    return _clean(
        {
            "source": "quadfit",
            "quadfit_jurisdiction": s4.get("jurisdiction"),
            "geometry_tier": s4.get("tier"),
            "frontage_ft": _num(s4.get("frontage_ft")),
            "lot_width_ft": _num(s4.get("lot_width_ft")),
            "lot_depth_ft": _num(s4.get("lot_depth_ft")),
            "front_bearings_deg": bearings,
            "alley_width_ft": _num(s4.get("alley_width_ft")),
            "fronts_cul_de_sac": s4.get("fronts_cul_de_sac"),
            "split_zone": s4.get("split_zone"),
            "zone_frac": _num(s4.get("zone_frac")),
            "inside_ugb": s4.get("inside_ugb"),
            "has_z_overlay": s4.get("has_z_overlay"),
            "stack_count": _int(s4.get("stack_count")),
            "observed": observed,
            "envelope": {
                "sqft": _num(s5o.get("envelope_sqft")),
                "setback_sqft": _num(s5o.get("envelope_setback_sqft")),
                "carved_sqft": _num(s5o.get("envelope_carved_sqft")),
            },
            "slope": {
                "mean_pct": _num(s5o.get("slope_mean_pct")),
                "p85_pct": _num(s5o.get("slope_p85_pct")),
                "max_pct": _num(s5o.get("slope_max_pct")),
                "source": s5o.get("slope_source"),
            },
            "sewer": {
                "main_dist_ft": _num(s5o.get("sewer_main_dist_ft")),
                "in_district": s5o.get("in_sewer_district"),
            },
            "flood": {"sfha": s5o.get("ovl_fema_sfha"), "floodway": s5o.get("ovl_fema_floodway")},
            "quadfit": {
                "triage": quadfit.get("triage"),
                "binding_constraint": quadfit.get("binding_constraint"),
                "policy_exclusion": quadfit.get("policy_exclusion"),
                "parking_tier": quadfit.get("parking_tier"),
                "stalls_provided": _int(quadfit.get("stalls_provided")),
                "layout_method": quadfit.get("layout_method"),
            },
        }
    )


def result_checks(row: dict[str, Any]) -> dict[str, Any]:
    """What one lot x design row becomes in ``lot_results.checks``."""
    return _clean(
        {
            "verdict": row.get("triage"),
            "if_signed": row.get("if_signed"),
            "reasons": _split(row.get("reasons")),
            "if_signed_reasons": _split(row.get("if_signed_reasons")),
            "head": row.get("head") or None,
            "dominant": row.get("dominant") or None,
            "failing": _split(row.get("failing")),
            "unchecked": _split(row.get("unchecked")),
            "ask": row.get("ask"),
            "rule_verdict": row.get("rule_verdict"),
            "fits": row.get("fits"),
            "fit": {
                "slack_ft": _num(row.get("fit_slack_ft")),
                "best_depth_ft": _num(row.get("fit_best_depth_ft")),
                "required_ft": _num(row.get("fit_required_ft")),
                "across_ft": _num(row.get("fit_across_ft")),
                "angle_deg": _num(row.get("fit_angle_deg")),
                "orientation": row.get("fit_orientation") or None,
            },
            "stalls": {
                "charged": _int(row.get("stalls_charged")),
                "seated": _int(row.get("stalls_seated")),
                "band": row.get("parking_band") or None,
            },
            "leaning": {"assumed": _split(row.get("assumed_leaning")), "unknown": _split(row.get("unknown_leaning"))},
            "search": {"angles": _int(row.get("angles")), "step_deg": _num(row.get("step_deg"))},
        }
    )


def result_binding(row: dict[str, Any]) -> list[str]:
    """Head first, then every other failing check, each once."""
    head = _clean(row.get("head"))
    out: list[str] = [head] if isinstance(head, str) and head else []
    for name in _split(row.get("failing")):
        if name not in out:
            out.append(name)
    return out


# --- export (137) -------------------------------------------------------------


def _git_head(cwd: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def export(
    run_dir: Path,
    out: Path,
    *,
    s4: Path | None = None,
    s5o: Path | None = None,
    quadfit_results: Path | None = None,
    code_version: str | None = None,
) -> dict[str, Any]:
    """Write the bundle for one bridge run; returns ``run.json``'s content."""
    import pandas as pd
    import pyarrow.parquet as pq

    from flats.ingest.quadfit import LOTS_RESULTS, S5O_LOTS
    from flats.geom.alley import S4_LOTS

    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    frame = pd.read_parquet(run_dir / "lots.parquet")
    frame = frame.astype(object).where(frame.notna(), None)
    tlids = sorted(set(frame["TLID"]))
    designs = sorted(set(frame["design"]))

    s4 = s4 or Path(meta.get("s4") or S4_LOTS)
    s5o = s5o or Path(meta.get("s5o") or S5O_LOTS)
    quadfit_results = quadfit_results or LOTS_RESULTS

    have4 = set(pq.read_schema(s4).names)
    left = pd.read_parquet(s4, columns=["TLID", *[c for c in S4_WANTED if c in have4]])
    left = left[left["TLID"].isin(tlids)].astype(object)
    left = left.where(left.notna(), None).set_index("TLID")
    have5 = set(pq.read_schema(s5o).names)
    right = pd.read_parquet(s5o, columns=["TLID", *[c for c in S5O_WANTED if c in have5]])
    right = right[right["TLID"].isin(tlids)].astype(object)
    right = right.where(right.notna(), None).set_index("TLID")
    if quadfit_results.exists():
        header = pd.read_csv(quadfit_results, nrows=0).columns
        q = pd.read_csv(quadfit_results, usecols=["TLID", *[c for c in QUADFIT_WANTED if c in header]], dtype=str)
        q = q[q["TLID"].isin(tlids)].astype(object)
        q = q.where(q.notna(), None).set_index("TLID")
    else:
        q = pd.DataFrame(index=pd.Index([], name="TLID"))
    s4_rows = left.to_dict("index")
    s5o_rows = right.to_dict("index")
    q_rows = q.to_dict("index")

    missing = [t for t in tlids if t not in s4_rows]
    if missing:
        raise SystemExit(f"{len(missing)} lots in the run are not in {s4}: {missing[:5]}")

    out.mkdir(parents=True, exist_ok=True)
    counties: Counter[str] = Counter()
    # One facts record per lot: the observed dict is the lot's, identical on
    # every design row, so the first row seen carries it.
    first_row: dict[str, dict[str, Any]] = {}
    for row in frame.to_dict("records"):
        first_row.setdefault(row["TLID"], row)
    with gzip.open(out / LOTS_FILE, "wt", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(LOT_COLUMNS)
        for tlid in tlids:
            s4r = s4_rows[tlid]
            juris = str(s4r.get("jurisdiction"))
            county = lot_county(s4r)
            try:
                layer = layer_id_for(juris)
            except KeyError:
                layer = f"quadfit:{juris}"
            observed_raw = first_row[tlid].get("observed")
            try:
                observed = json.loads(observed_raw) if observed_raw else {}
            except (TypeError, ValueError):
                observed = {}
            facts = lot_facts(s4r, s5o_rows.get(tlid, {}), observed, q_rows.get(tlid, {}))
            wkb = s4r.get("wkb")
            area = _num(s4r.get("area_sqft"))
            counties[county] += 1
            w.writerow(
                [
                    tlid,
                    county,
                    layer,
                    _clean(s4r.get("zone_raw")) or "",
                    _clean(s4r.get("zone")) or "",
                    _clean(s4r.get("SITEADDR")) or "",
                    "" if area is None else repr(area),
                    wkb.hex() if isinstance(wkb, (bytes, bytearray)) else "",
                    json.dumps(facts, separators=(",", ":")),
                ]
            )

    tiers: Counter[str] = Counter()
    signed: Counter[str] = Counter()
    n_results = 0
    with gzip.open(out / RESULTS_FILE, "wt", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(RESULT_COLUMNS)
        for row in frame.to_dict("records"):
            tlid = row["TLID"]
            county = lot_county(s4_rows[tlid])
            tier = str(row.get("triage"))
            if tier not in TIERS:
                raise SystemExit(f"unexpected triage {tier!r} on {tlid} {row.get('design')}")
            slack = _num(row.get("fit_slack_ft"))
            tiers[tier] += 1
            signed[str(row.get("if_signed"))] += 1
            n_results += 1
            w.writerow(
                [
                    tlid,
                    county,
                    row["design"],
                    tier,
                    "" if slack is None else repr(slack),
                    json.dumps(result_binding(row)),
                    json.dumps(result_checks(row), separators=(",", ":")),
                ]
            )

    finished = datetime.fromtimestamp((run_dir / "lots.parquet").stat().st_mtime, tz=timezone.utc)
    seconds = float(meta.get("seconds") or 0.0)
    started = finished - timedelta(seconds=seconds)
    host = socket.gethostname()
    run = {
        "source_id": f"{host}:{run_dir.resolve()}:{finished.isoformat()}",
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "status": "complete",
        "code_version": code_version or _git_head(REPO_ROOT),
        "rules_version": rules_version(),
        "design_keys": designs,
        "counties": sorted(counties),
        "params": {
            **{k: v for k, v in meta.items() if k not in {"lots", "rows"}},
            "source_id": f"{host}:{run_dir.resolve()}:{finished.isoformat()}",
            "host": host,
            "run_dir": str(run_dir.resolve()),
            "caller": "flats.ingest.quadfit",
        },
        "notes": (
            f"bridge run from quadfit's county map ({host}:{run_dir}); the verdict is the "
            f"screen's, if_signed sits in checks beside it"
        ),
        "counts": {
            "lots": len(tlids),
            "results": n_results,
            "tiers": dict(sorted(tiers.items())),
            "if_signed": dict(sorted(signed.items())),
            "by_county": dict(sorted(counties.items())),
        },
    }
    (out / RUN_FILE).write_text(json.dumps(run, indent=2), encoding="utf-8")
    return run


# --- load (114) ---------------------------------------------------------------


def _dsn(url: str) -> str:
    """SQLAlchemy's URL to asyncpg's: drop the driver suffix."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _rows(path: Path) -> Iterator[list[str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        yield header
        yield from reader


def _batches(rows: Iterable[list[str]], size: int) -> Iterator[list[tuple[str | None, ...]]]:
    batch: list[tuple[str | None, ...]] = []
    for row in rows:
        batch.append(tuple(cell if cell != "" else None for cell in row))
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _design_row(design: Design) -> tuple[Any, ...]:
    return (
        design.key,
        design.id,
        design.version,
        design.label,
        design.typology.value,
        design.footprint.width_ft,
        design.footprint.depth_ft,
        design.units,
        design.stories,
        design.height_ft,
        design.status.value,
        json.dumps(design.model_dump(mode="json")),
    )


class _RolledBack(Exception):
    """Raised inside the transaction on a dry run so it never commits."""


async def load(bundle: Path, db_url: str, *, dry_run: bool = False, batch_size: int = 20_000) -> dict[str, Any]:
    """Load one bundle; returns the counts written and verified."""
    import asyncpg

    run = json.loads((bundle / RUN_FILE).read_text(encoding="utf-8"))
    expected = run["counts"]
    catalog = load_catalog(strict=False)
    for key in run["design_keys"]:
        catalog.get(key)  # loud if a result names a design the catalog cannot produce

    conn = await asyncpg.connect(_dsn(db_url))
    report: dict[str, Any] = {"dry_run": dry_run}
    try:
        try:
            async with conn.transaction():
                # Designs: written once per id@version, never updated.
                for key in run["design_keys"]:
                    await conn.execute(
                        """
                        INSERT INTO flats.designs
                            (key, design_id, version, label, typology, width_ft, depth_ft,
                             units, stories, height_ft, status, spec)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb)
                        ON CONFLICT (key) DO NOTHING
                        """,
                        *_design_row(catalog.get(key)),
                    )

                # The run: found by its source, so a re-load lands on the same row.
                run_id = await conn.fetchval(
                    "SELECT id FROM flats.runs WHERE params->>'source_id' = $1", run["source_id"]
                )
                if run_id is None:
                    run_id = await conn.fetchval(
                        """
                        INSERT INTO flats.runs
                            (started_at, finished_at, status, code_version, rules_version,
                             design_keys, counties, params, notes)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
                        RETURNING id
                        """,
                        datetime.fromisoformat(run["started_at"]),
                        datetime.fromisoformat(run["finished_at"]),
                        run["status"],
                        run.get("code_version"),
                        run.get("rules_version"),
                        list(run["design_keys"]),
                        list(run["counties"]),
                        json.dumps(run["params"]),
                        run.get("notes", ""),
                    )
                    report["run_created"] = True
                else:
                    report["run_created"] = False
                report["run_id"] = run_id

                # Lots, through a temp table: text in, PostGIS builds the geometry.
                await conn.execute(
                    "CREATE TEMP TABLE tmp_lots ("
                    + ", ".join(f"{c} text" for c in LOT_COLUMNS)
                    + ") ON COMMIT DROP"
                )
                rows = _rows(bundle / LOTS_FILE)
                header = next(rows)
                if tuple(header) != LOT_COLUMNS:
                    raise SystemExit(f"{LOTS_FILE} header {header} != {LOT_COLUMNS}")
                n_lots = 0
                for batch in _batches(rows, batch_size):
                    await conn.copy_records_to_table("tmp_lots", records=batch, columns=list(LOT_COLUMNS))
                    n_lots += len(batch)
                if n_lots != expected["lots"]:
                    raise SystemExit(f"{LOTS_FILE} has {n_lots} rows, run.json says {expected['lots']}")
                before = await conn.fetchval("SELECT count(*) FROM flats.lots")
                await conn.execute(
                    """
                    INSERT INTO flats.lots
                        (tlid, county, jurisdiction, zone_raw, zone, site_address, area_sqft,
                         geom, centroid, condo_verdict, facts, first_seen_run_id, updated_run_id)
                    SELECT tlid, county, jurisdiction, NULLIF(zone_raw, ''), NULLIF(zone, ''),
                           NULLIF(site_address, ''), NULLIF(area_sqft, '')::numeric,
                           CASE WHEN wkb_hex IS NULL THEN NULL ELSE
                             ST_Multi(ST_CollectionExtract(
                               ST_SetSRID(ST_GeomFromWKB(decode(wkb_hex, 'hex')), 2913), 3)) END,
                           CASE WHEN wkb_hex IS NULL THEN NULL ELSE
                             ST_Transform(ST_Centroid(
                               ST_SetSRID(ST_GeomFromWKB(decode(wkb_hex, 'hex')), 2913)), 4326) END,
                           'land', facts::jsonb, $1, $1
                    FROM tmp_lots
                    ON CONFLICT (county, tlid) DO UPDATE SET
                        jurisdiction = EXCLUDED.jurisdiction,
                        zone_raw = EXCLUDED.zone_raw,
                        zone = EXCLUDED.zone,
                        site_address = EXCLUDED.site_address,
                        area_sqft = EXCLUDED.area_sqft,
                        geom = EXCLUDED.geom,
                        centroid = EXCLUDED.centroid,
                        condo_verdict = EXCLUDED.condo_verdict,
                        facts = EXCLUDED.facts,
                        first_seen_run_id = COALESCE(flats.lots.first_seen_run_id, EXCLUDED.first_seen_run_id),
                        updated_run_id = EXCLUDED.updated_run_id
                    """,
                    run_id,
                )
                after = await conn.fetchval("SELECT count(*) FROM flats.lots")
                report["lots_inserted"] = after - before
                report["lots_updated"] = n_lots - (after - before)

                # Results, the same way, joined to the lot ids just written.
                await conn.execute(
                    "CREATE TEMP TABLE tmp_results ("
                    + ", ".join(f"{c} text" for c in RESULT_COLUMNS)
                    + ") ON COMMIT DROP"
                )
                rows = _rows(bundle / RESULTS_FILE)
                header = next(rows)
                if tuple(header) != RESULT_COLUMNS:
                    raise SystemExit(f"{RESULTS_FILE} header {header} != {RESULT_COLUMNS}")
                n_results = 0
                for batch in _batches(rows, batch_size):
                    await conn.copy_records_to_table("tmp_results", records=batch, columns=list(RESULT_COLUMNS))
                    n_results += len(batch)
                if n_results != expected["results"]:
                    raise SystemExit(f"{RESULTS_FILE} has {n_results} rows, run.json says {expected['results']}")
                orphans = await conn.fetchval(
                    """
                    SELECT count(*) FROM tmp_results r
                    LEFT JOIN flats.lots l ON l.county = r.county AND l.tlid = r.tlid
                    WHERE l.id IS NULL
                    """
                )
                if orphans:
                    raise SystemExit(f"{orphans} result rows name a lot the bundle did not carry")
                before = await conn.fetchval("SELECT count(*) FROM flats.lot_results WHERE run_id = $1", run_id)
                await conn.execute(
                    """
                    INSERT INTO flats.lot_results
                        (lot_id, design_key, run_id, tier, slack_ft, binding, checks)
                    SELECT l.id, r.design_key, $1, r.tier, NULLIF(r.slack_ft, '')::numeric,
                           ARRAY(SELECT jsonb_array_elements_text(r.binding::jsonb)),
                           r.checks::jsonb
                    FROM tmp_results r
                    JOIN flats.lots l ON l.county = r.county AND l.tlid = r.tlid
                    ON CONFLICT (lot_id, design_key, run_id) DO UPDATE SET
                        tier = EXCLUDED.tier,
                        slack_ft = EXCLUDED.slack_ft,
                        binding = EXCLUDED.binding,
                        checks = EXCLUDED.checks
                    """,
                    run_id,
                )
                after = await conn.fetchval("SELECT count(*) FROM flats.lot_results WHERE run_id = $1", run_id)
                report["results_inserted"] = after - before
                report["results_updated"] = n_results - (after - before)

                # Verify against what the export counted, before anything commits.
                tiers = dict(
                    await conn.fetch(
                        "SELECT tier, count(*)::int FROM flats.lot_results WHERE run_id = $1 GROUP BY tier ORDER BY tier",
                        run_id,
                    )
                )
                signed = dict(
                    await conn.fetch(
                        "SELECT checks->>'if_signed', count(*)::int FROM flats.lot_results "
                        "WHERE run_id = $1 GROUP BY 1 ORDER BY 1",
                        run_id,
                    )
                )
                bad_geom = await conn.fetchval(
                    "SELECT count(*) FROM flats.lots WHERE updated_run_id = $1 AND geom IS NOT NULL "
                    "AND (ST_SRID(geom) <> 2913 OR ST_IsEmpty(geom) OR ST_SRID(centroid) <> 4326)",
                    run_id,
                )
                report["tiers"] = tiers
                report["if_signed"] = signed
                problems = []
                if after != expected["results"]:
                    problems.append(f"results {after} != {expected['results']}")
                if tiers != expected["tiers"]:
                    problems.append(f"tiers {tiers} != {expected['tiers']}")
                if signed != expected["if_signed"]:
                    problems.append(f"if_signed {signed} != {expected['if_signed']}")
                if bad_geom:
                    problems.append(f"{bad_geom} lots with a geometry in the wrong SRID or empty")
                if problems:
                    raise SystemExit("VERIFY FAILED: " + "; ".join(problems))
                report["verified"] = True
                if dry_run:
                    raise _RolledBack()
        except _RolledBack:
            report["rolled_back"] = True
    finally:
        await conn.close()
    return report


# --- cli ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    ex = sub.add_parser("export", help="write a bundle from a bridge run directory (needs pandas/pyarrow)")
    ex.add_argument("--run-dir", type=Path, required=True, help="directory with lots.parquet + meta.json")
    ex.add_argument("--out", type=Path, required=True, help="bundle directory to write")
    ex.add_argument("--s4", type=Path, default=None, help="override quadfit's s4_lots.parquet")
    ex.add_argument("--s5o", type=Path, default=None, help="override quadfit's s5o_lots.parquet")
    ex.add_argument("--quadfit-results", type=Path, default=None, help="override quadfit's lots_results.csv")
    ex.add_argument("--code-version", default=None, help="git SHA the run was made with (default: this checkout's HEAD)")

    ld = sub.add_parser("load", help="load a bundle into flats.* (needs asyncpg)")
    ld.add_argument("--bundle", type=Path, required=True)
    ld.add_argument("--db-url", default=None, help="default: app settings' database_url")
    ld.add_argument("--dry-run", action="store_true", help="do the whole load in a transaction and roll it back")
    ld.add_argument("--batch-size", type=int, default=20_000)

    args = parser.parse_args(argv)
    if args.command == "export":
        run = export(
            args.run_dir,
            args.out,
            s4=args.s4,
            s5o=args.s5o,
            quadfit_results=args.quadfit_results,
            code_version=args.code_version,
        )
        print(json.dumps({k: run[k] for k in ("source_id", "code_version", "rules_version", "design_keys", "counties", "counts")}, indent=2))
        return 0

    db_url = args.db_url
    if db_url is None:
        from app.config import settings

        db_url = settings.database_url
    report = asyncio.run(load(args.bundle, db_url, dry_run=args.dry_run, batch_size=args.batch_size))
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("verified") else 1


if __name__ == "__main__":
    sys.exit(main())
