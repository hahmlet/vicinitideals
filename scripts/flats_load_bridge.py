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
  ``(snapshot_id, county, tlid)`` -- every lot row names the county copy it
  came from (``flats.snapshots``, migration 0132), so ``--snapshot`` names the
  registered snapshot the bundle was read from and a second copy lands beside
  the first, never on top of it -- results on ``(lot_id, design_key,
  run_id)``. Geometry is
  built in PostGIS (``ST_GeomFromWKB`` at SRID 2913, the centroid transformed
  to 4326), so nothing geospatial is needed on the Python side. Run twice, the
  second load changes nothing but ``updated_run_id``. ``--dry-run`` does the
  whole load in a transaction and rolls it back -- and leaves dead tuples the
  size of the load behind (the county: 2.4 GB), so after a dry run on a full
  county follow the real load with ``VACUUM (FULL, ANALYZE)`` on
  ``flats.lot_results`` and ``flats.lots`` (14 s on 2026-09-18, 3.0 -> 1.8 GB),
  one statement per ``psql -c``. The county load itself is about a minute.
* ``load-changes`` (also the api container) carries a delta's
  ``changes.csv.gz`` (``flats.ingest.delta``: what every lot did between two
  copies) into ``flats.lot_changes`` for one ``--from`` / ``--to`` pair of
  registered snapshots, replacing that pair's rows if they were loaded before.

A run directory written by ``flats.ingest.assign`` (every lot in the county:
the bridge's rows plus an ``unknown`` row per design for each lot quadfit did
not measure) names its normalized lot table in ``meta.json``; ``export`` then
takes the lot record for an unmeasured lot from that table (polygon, address,
jurisdiction, zone, the assessor's roll values, the condo verdict) and for a
measured lot adds the same roll values and verdict beside s4's facts. Such a
run is loaded with ``status: candidate`` -- reachable with ``?run=``, never
the default until promoted -- and the load ends by writing the snapshot's
``checks``: the promotion-blocking thresholds (a layer not whole, a feature
count that moved, a zone code the rules lack, a city whose zones moved, a
county change list that disagrees with ours), each ``{tripped, detail}``.

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
        --bundle /app/data/flats/bridge/county2 --snapshot <flats.snapshots id> [--dry-run]

The snapshot row comes first (``scripts/flats_snapshot.py register``); the
loader refuses a snapshot id it cannot find and a snapshot already retired.
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
from flats.ingest.checks import snapshot_checks, tripped  # noqa: E402
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
    "condo_verdict",
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


#: The screen's own files: what a verdict depends on besides the rules and
#: the ground. Everything under ``flats/`` but the tests, the jurisdictions
#: (``rules_version``) and the provenance store (the corpus, not the
#: screen), plus quadfit's stages and its ``rules.yaml``.
SCREEN_ROOTS = ("flats", "Lot Analysis/quadfit")
SCREEN_SKIP_PARTS = frozenset({"tests", "__pycache__"})
SCREEN_SKIP_UNDER = ("flats/config/jurisdictions", "flats/provenance/docs", "Lot Analysis/quadfit/provenance")
SCREEN_SUFFIXES = frozenset({".py", ".yaml", ".yml", ".json", ".csv"})


def screen_version(root: Path = REPO_ROOT) -> str:
    """Content hash of the screen's files, the run's ``screen_version``.

    Path and bytes of every screen file under :data:`SCREEN_ROOTS`, in sorted
    order, so two checkouts that differ only outside the screen (docs, the
    app, a test) carry the same version and the drift report does not put a
    move to "code" that no screen change explains. Full sha256 hex.
    """
    h = hashlib.sha256()
    files: list[tuple[str, Path]] = []
    for top in SCREEN_ROOTS:
        base = root / top
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in SCREEN_SUFFIXES:
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            if SCREEN_SKIP_PARTS & set(rel.split("/")[:-1]) or rel.startswith(SCREEN_SKIP_UNDER):
                continue
            files.append((rel, path))
    for rel, path in sorted(files):
        h.update(rel.encode())
        h.update(b"\0")
        h.update(path.read_bytes().replace(b"\r\n", b"\n"))  # one version across a Windows and a Linux checkout
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


#: RLIS roll columns the normalize stage carries, and the fact each becomes.
ASSESSOR = (
    ("LANDVAL", "land_value", "num"),
    ("BLDGVAL", "building_value", "num"),
    ("TOTALVAL", "total_value", "num"),
    ("ASSESSVAL", "assessed_value", "num"),
    ("YEARBUILT", "year_built", "int"),
    ("BLDGSQFT", "building_sqft", "num"),
    ("SALEDATE", "sale_date", "str"),
    ("SALEPRICE", "sale_price", "num"),
    ("PROP_CODE", "prop_code", "str"),
    ("STATECLASS", "state_class", "str"),
    ("LANDUSE", "land_use", "str"),
)


def assessor_facts(nr: dict[str, Any]) -> dict[str, Any]:
    """The roll values from a normalized lot row, adopted as they are."""
    out: dict[str, Any] = {}
    for column, name, kind in ASSESSOR:
        value = _clean(nr.get(column))
        if value is None:
            out[name] = None
        elif kind == "int":
            out[name] = _int(value)
        elif kind == "num":
            out[name] = _num(value)
        else:
            out[name] = str(value).strip() or None
    return out


#: ``lots.jurisdiction`` for a lot in a city the rules do not hold (Canby,
#: Sandy, Molalla, Estacada, Barlow -- outside Metro's boundary but on the
#: county roll). The column is NOT NULL and the first September load stopped
#: on a blank; the map's own city name is kept behind this prefix the way a
#: measured lot outside ``layer_id_for`` keeps ``quadfit:<name>``.
UNMAPPED_LAYER_PREFIX = "juris_city:"


def unmapped_layer(juris_city: Any) -> str:
    name = str(juris_city or "").strip().lower() or "none"
    return f"{UNMAPPED_LAYER_PREFIX}{name}"


def snapshot_facts(nr: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    """The design-independent record for a lot the snapshot holds and quadfit never measured."""
    reasons = _split(row.get("reasons"))
    step = next((r.split(":", 1)[1] for r in reasons if r.startswith("quadfit:")), None)
    return _clean(
        {
            "source": "snapshot",
            "unmeasured": {
                "reason": next((r for r in reasons if not r.startswith("quadfit:")), None),
                "quadfit_step": step,
            },
            "juris_city": nr.get("juris_city"),
            "split_zone": nr.get("split_zone"),
            "zone_frac": _num(nr.get("zone_frac")),
            "inside_ugb": nr.get("inside_ugb"),
            "stack_count": _int(nr.get("stack_count")),
            "part_count": _int(nr.get("part_count")),
            "observed": {},
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
            # The screen wrote this row (a synthetic ``unknown`` from the
            # assign stage carries no rule verdict and no measurement).
            "screened": _clean(row.get("rule_verdict")) is not None,
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
    normalized: Path | None = None,
    rules_ver: str | None = None,
    source_id: str | None = None,
    screen_ver: str | None = None,
) -> dict[str, Any]:
    """Write the bundle for one run; returns ``run.json``'s content.

    ``normalized`` (or ``meta.json``'s ``normalized``) is the normalize stage's
    directory; with it, a lot the run carries that s4 lacks takes its record
    from there, and every lot gains the roll values and the condo verdict.

    ``code_version`` and ``rules_ver`` name the checkout the SCREEN ran on;
    they default to this checkout's HEAD and rules hash, which is right when
    the bundle is exported on the commit that screened it. A re-export that
    only refreshes quadfit's columns (``lots_results.csv``) from a bridge run
    screened earlier passes the earlier run's two versions, so the drift
    report reads the FLATS results as what they are -- unchanged.

    ``screen_ver`` is the hash of the screen's own files (:func:`screen_version`),
    the third version beside the two above; it defaults to this checkout's.

    ``source_id`` is the run row the bundle lands on. The loader finds a run
    by it, so a bundle stamped with an existing CANDIDATE run's id upserts
    that run's lots and results in place instead of making a second
    candidate on the same copy -- the path for a re-screen of the SAME lots
    from a fresh assign directory while the run is still a candidate. The
    loader refuses to land on a run the Lots pages show (``complete``): a
    re-screen of the copy in use is a NEW run (the default source id), loaded
    as a candidate on the current copy and promoted with
    ``flats_promote.py promote --run``, so it goes through the gate and can
    be rolled back. The default names this assign directory and its finish
    time, a new run.
    """
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
    if quadfit_results is None and meta.get("quadfit_dir"):
        quadfit_results = Path(meta["quadfit_dir"]) / "lots_results.csv"
    quadfit_results = quadfit_results or LOTS_RESULTS
    normalized = normalized or (Path(meta["normalized"]) if meta.get("normalized") else None)

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
    n_rows: dict[str, dict[str, Any]] = {}
    if normalized is not None:
        n = pd.read_parquet(normalized / "lots.parquet")
        n["tlid"] = n["tlid"].astype(str).str.rstrip()
        n = n[n["tlid"].isin(tlids)].astype(object)
        n = n.where(n.notna(), None).set_index("tlid")
        if n.index.has_duplicates:
            twice = sorted(set(n.index[n.index.duplicated()]))
            raise SystemExit(f"{normalized}: a TLID names lots in two counties: {twice[:5]}")
        n_rows = n.to_dict("index")

    missing = [t for t in tlids if t not in s4_rows and t not in n_rows]
    if missing:
        where = f"{s4}" if normalized is None else f"{s4} or {normalized}"
        raise SystemExit(f"{len(missing)} lots in the run are not in {where}: {missing[:5]}")

    out.mkdir(parents=True, exist_ok=True)
    counties: Counter[str] = Counter()
    # One facts record per lot: the observed dict is the lot's, identical on
    # every design row, so the first row seen carries it.
    first_row: dict[str, dict[str, Any]] = {}
    for row in frame.to_dict("records"):
        first_row.setdefault(row["TLID"], row)
    county_of: dict[str, str] = {}
    sources: Counter[str] = Counter()
    with gzip.open(out / LOTS_FILE, "wt", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(LOT_COLUMNS)
        for tlid in tlids:
            nr = n_rows.get(tlid, {})
            observed_raw = first_row[tlid].get("observed")
            try:
                observed = json.loads(observed_raw) if observed_raw else {}
            except (TypeError, ValueError):
                observed = {}
            if tlid in s4_rows:
                # Measured: s4's record, as the bridge always exported it.
                s4r = s4_rows[tlid]
                juris = str(s4r.get("jurisdiction"))
                county = lot_county(s4r)
                try:
                    layer = layer_id_for(juris)
                except KeyError:
                    layer = f"quadfit:{juris}"
                facts = lot_facts(s4r, s5o_rows.get(tlid, {}), observed, q_rows.get(tlid, {}))
                zone_raw, zone, address = s4r.get("zone_raw"), s4r.get("zone"), s4r.get("SITEADDR")
                wkb = s4r.get("wkb")
                area = _num(s4r.get("area_sqft"))
                sources["quadfit"] += 1
            else:
                # Unmeasured: the snapshot's record, and the reason it was not measured.
                county = str(nr.get("county"))
                layer = str(nr.get("jurisdiction") or "") or unmapped_layer(nr.get("juris_city"))
                facts = snapshot_facts(nr, first_row[tlid])
                zone_raw, zone, address = nr.get("zone_raw"), nr.get("zone"), nr.get("site_address")
                wkb = nr.get("wkb")
                area = _num(nr.get("area_sqft"))
                sources["snapshot"] += 1
            if nr:
                facts["assessor"] = assessor_facts(nr)
                facts["condo"] = {
                    "verdict": _clean(nr.get("condo_verdict")) or "land",
                    "reason": _clean(nr.get("condo_reason")),
                }
                facts["snapshot_zone"] = {
                    "raw": _clean(nr.get("zone_raw")),
                    "zone": _clean(nr.get("zone")),
                    "gate": _clean(nr.get("gate")),
                }
            county_of[tlid] = county
            counties[county] += 1
            w.writerow(
                [
                    tlid,
                    county,
                    layer,
                    _clean(zone_raw) or "",
                    _clean(zone) or "",
                    _clean(address) or "",
                    "" if area is None else repr(area),
                    wkb.hex() if isinstance(wkb, (bytes, bytearray)) else "",
                    _clean(nr.get("condo_verdict")) or "land",
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
            county = county_of[tlid]
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
    from_snapshot = normalized is not None
    source_id = source_id or f"{host}:{run_dir.resolve()}:{finished.isoformat()}"
    run = {
        "source_id": source_id,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        # A run read from a dated snapshot is a candidate until promoted; the
        # bridge's July run was loaded complete because it WAS the copy in use.
        "status": "candidate" if from_snapshot else "complete",
        "code_version": code_version or _git_head(REPO_ROOT),
        "rules_version": rules_ver or rules_version(),
        "screen_version": screen_ver or screen_version(),
        "design_keys": designs,
        "counties": sorted(counties),
        "snapshot_date": meta.get("snapshot_date"),
        "new_zones": meta.get("new_zones") or {},
        "ruled_zones": meta.get("ruled_zones") or {},
        "params": {
            **{k: v for k, v in meta.items() if k not in {"lots", "rows", "funnel"}},
            "source_id": source_id,
            "host": host,
            "run_dir": str(run_dir.resolve()),
            "caller": meta.get("caller") or "flats.ingest.quadfit",
        },
        "notes": (
            f"every lot of the {meta.get('snapshot_date')} county map ({host}:{run_dir}): the screen's "
            f"verdict where quadfit measured, unknown with a reason where it did not; if_signed sits in "
            f"checks beside it"
            if from_snapshot
            else f"bridge run from quadfit's county map ({host}:{run_dir}); the verdict is the "
            f"screen's, if_signed sits in checks beside it"
        ),
        "counts": {
            "lots": len(tlids),
            "results": n_results,
            "tiers": dict(sorted(tiers.items())),
            "if_signed": dict(sorted(signed.items())),
            "by_county": dict(sorted(counties.items())),
            "by_source": dict(sorted(sources.items())),
            "unmeasured": (meta.get("assign") or {}).get("by_reason", {}),
        },
    }
    (out / RUN_FILE).write_text(json.dumps(run, indent=2), encoding="utf-8")
    return run


# --- load (114) ---------------------------------------------------------------


def _dsn(url: str) -> str:
    """SQLAlchemy's URL to asyncpg's: drop the driver suffix."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _rows(path: Path) -> Iterator[list[str]]:
    # A lot's WKB is one CSV field. The county's largest parcels (unincorporated
    # timber and farm tracts, present since every lot rides the bundle) run past
    # the reader's 128 KB default; the first September load stopped on one.
    csv.field_size_limit(sys.maxsize)
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


async def load(
    bundle: Path, db_url: str, *, snapshot_id: int, dry_run: bool = False, batch_size: int = 20_000
) -> dict[str, Any]:
    """Load one bundle into the named snapshot; returns the counts written and verified."""
    import asyncpg

    run = json.loads((bundle / RUN_FILE).read_text(encoding="utf-8"))
    expected = run["counts"]
    catalog = load_catalog(strict=False)
    for key in run["design_keys"]:
        catalog.get(key)  # loud if a result names a design the catalog cannot produce

    conn = await asyncpg.connect(_dsn(db_url))
    report: dict[str, Any] = {"dry_run": dry_run, "snapshot_id": snapshot_id}
    try:
        try:
            async with conn.transaction():
                snapshot = await conn.fetchrow(
                    "SELECT id, snapshot_date, status, counts::text AS counts, report::text AS report "
                    "FROM flats.snapshots WHERE id = $1",
                    snapshot_id,
                )
                if snapshot is None:
                    raise SystemExit(f"no flats.snapshots row {snapshot_id}; register the snapshot first")
                if snapshot["status"] in ("retired", "failed"):
                    raise SystemExit(f"snapshot {snapshot_id} is {snapshot['status']}; a load goes into a candidate or the current copy")
                report["snapshot_date"] = snapshot["snapshot_date"].isoformat()
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
                             design_keys, counties, params, notes, snapshot_id, screen_version)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10, $11)
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
                        snapshot_id,
                        run.get("screen_version"),
                    )
                    report["run_created"] = True
                else:
                    was = await conn.fetchrow("SELECT snapshot_id, status FROM flats.runs WHERE id = $1", run_id)
                    if was["snapshot_id"] is not None and was["snapshot_id"] != snapshot_id:
                        raise SystemExit(
                            f"run {run_id} was loaded into snapshot {was['snapshot_id']}; a run reads one copy, not two"
                        )
                    if was["status"] != "candidate":
                        # The run the Lots pages show is never overwritten in
                        # place: that would change what the site says with no
                        # gate and no way back. A re-screen is a new run.
                        raise SystemExit(
                            f"run {run_id} is {was['status']}; a re-screen of the copy in use is loaded as a NEW run "
                            f"(export without --source-id), read with flats_promote.py drift, and promoted with "
                            f"flats_promote.py promote --run"
                        )
                    # The row keeps its identity and takes the bundle's versions:
                    # a re-load from a fresh assign directory was screened on
                    # THIS checkout, and the drift report reads the versions.
                    await conn.execute(
                        """
                        UPDATE flats.runs
                           SET snapshot_id = $2,
                               code_version = COALESCE($3, code_version),
                               rules_version = COALESCE($4, rules_version),
                               finished_at = $5,
                               notes = COALESCE(notes, '') || $6,
                               screen_version = COALESCE($7, screen_version)
                         WHERE id = $1
                        """,
                        run_id,
                        snapshot_id,
                        run.get("code_version"),
                        run.get("rules_version"),
                        datetime.fromisoformat(run["finished_at"]),
                        f"\nre-loaded from {run['params'].get('run_dir')} "
                        f"(finished {run['finished_at']}, code {run.get('code_version')}, "
                        f"rules {run.get('rules_version')}, screen {run.get('screen_version')})",
                        run.get("screen_version"),
                    )
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
                before = await conn.fetchval("SELECT count(*) FROM flats.lots WHERE snapshot_id = $1", snapshot_id)
                await conn.execute(
                    """
                    INSERT INTO flats.lots
                        (snapshot_id, tlid, county, jurisdiction, zone_raw, zone, site_address, area_sqft,
                         geom, centroid, condo_verdict, facts, first_seen_run_id, updated_run_id)
                    SELECT $2, tlid, county, jurisdiction, NULLIF(zone_raw, ''), NULLIF(zone, ''),
                           NULLIF(site_address, ''), NULLIF(area_sqft, '')::numeric,
                           CASE WHEN wkb_hex IS NULL THEN NULL ELSE
                             ST_Multi(ST_CollectionExtract(
                               ST_SetSRID(ST_GeomFromWKB(decode(wkb_hex, 'hex')), 2913), 3)) END,
                           CASE WHEN wkb_hex IS NULL THEN NULL ELSE
                             ST_Transform(ST_Centroid(
                               ST_SetSRID(ST_GeomFromWKB(decode(wkb_hex, 'hex')), 2913)), 4326) END,
                           COALESCE(NULLIF(condo_verdict, ''), 'land'), facts::jsonb, $1, $1
                    FROM tmp_lots
                    ON CONFLICT (snapshot_id, county, tlid) DO UPDATE SET
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
                    snapshot_id,
                )
                after = await conn.fetchval("SELECT count(*) FROM flats.lots WHERE snapshot_id = $1", snapshot_id)
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
                    LEFT JOIN flats.lots l
                      ON l.snapshot_id = $1 AND l.county = r.county AND l.tlid = r.tlid
                    WHERE l.id IS NULL
                    """,
                    snapshot_id,
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
                    JOIN flats.lots l ON l.snapshot_id = $2 AND l.county = r.county AND l.tlid = r.tlid
                    ON CONFLICT (lot_id, design_key, run_id) DO UPDATE SET
                        tier = EXCLUDED.tier,
                        slack_ft = EXCLUDED.slack_ft,
                        binding = EXCLUDED.binding,
                        checks = EXCLUDED.checks
                    """,
                    run_id,
                    snapshot_id,
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

                # The promotion gate, written on the snapshot in the same
                # transaction: a candidate is never in the database without
                # its checks beside it.
                checks = await _snapshot_checks(conn, snapshot, snapshot_id, run, n_lots)
                report["checks"] = checks
                report["blocks"] = tripped(checks)
                if dry_run:
                    raise _RolledBack()
        except _RolledBack:
            report["rolled_back"] = True
    finally:
        await conn.close()
    return report


async def _snapshot_checks(conn: Any, snapshot: Any, snapshot_id: int, run: dict[str, Any], n_lots: int) -> dict[str, Any]:
    """Gather the gate's inputs from the rows just written and store the result.

    The baseline is the copy the newest complete run reads -- the one the
    page shows by default -- when it is a different copy from this one.
    """
    counts = json.loads(snapshot["counts"] or "{}")
    stored_report = json.loads(snapshot["report"] or "{}")
    baseline = await conn.fetchrow(
        """
        SELECT s.id, s.counts::text AS counts
        FROM flats.runs r JOIN flats.snapshots s ON s.id = r.snapshot_id
        WHERE r.status = 'complete' AND r.snapshot_id <> $1
        ORDER BY r.finished_at DESC LIMIT 1
        """,
        snapshot_id,
    )
    baseline_counts = json.loads(baseline["counts"] or "{}") if baseline else {}
    zone_changes: dict[str, tuple[int, int]] = {}
    if baseline:
        rows = await conn.fetch(
            """
            SELECT n.jurisdiction, count(*)::int AS total,
                   count(*) FILTER (WHERE n.zone IS DISTINCT FROM o.zone)::int AS changed
            FROM flats.lots n
            JOIN flats.lots o ON o.snapshot_id = $2 AND o.county = n.county AND o.tlid = n.tlid
            WHERE n.snapshot_id = $1
            GROUP BY n.jurisdiction
            """,
            snapshot_id,
            baseline["id"],
        )
        zone_changes = {r["jurisdiction"]: (r["changed"], r["total"]) for r in rows}
    by_source = (run["counts"].get("by_source") or {})
    measured = int(by_source.get("quadfit", n_lots))
    baseline_measured = baseline_counts.get("measured") or baseline_counts.get("lots")
    checks = snapshot_checks(
        datasets=counts.get("datasets") or {},
        baseline_datasets=baseline_counts.get("datasets") or None,
        new_zones=run.get("new_zones") or {},
        baseline_new_zones=baseline_counts.get("new_zones") or None,
        measured=measured,
        baseline_measured=int(baseline_measured) if baseline_measured else None,
        zone_changes=zone_changes,
        crosscheck=(stored_report.get("delta") or {}).get("crosscheck"),
    )
    written = {
        "lots": n_lots,
        "measured": measured,
        "results": run["counts"]["results"],
        "tiers": run["counts"].get("tiers", {}),
        "by_reason": run["counts"].get("unmeasured", {}),
        "new_zones": run.get("new_zones") or {},
        "ruled_zones": run.get("ruled_zones") or {},
        "prohibited_by_zone": ((run.get("params") or {}).get("assign") or {}).get("prohibited_by_zone") or {},
        "baseline_snapshot_id": baseline["id"] if baseline else None,
    }
    await conn.execute(
        "UPDATE flats.snapshots SET checks = $2::jsonb, counts = COALESCE(counts, '{}'::jsonb) || $3::jsonb WHERE id = $1",
        snapshot_id,
        json.dumps(checks),
        json.dumps(written),
    )
    return checks


async def load_changes(
    changes: Path, db_url: str, *, snapshot_from: int, snapshot_to: int, dry_run: bool = False, batch_size: int = 20_000
) -> dict[str, Any]:
    """Load a delta's ``changes.csv.gz`` into ``flats.lot_changes`` for one pair of snapshots.

    Loading the same pair again replaces its rows, so a re-run delta never
    doubles up. Both snapshots must be registered; the pair is refused when
    it names one copy twice.
    """
    import asyncpg

    from flats.ingest.delta import read_changes

    if snapshot_from == snapshot_to:
        raise SystemExit("a delta is between two copies; --from and --to name the same snapshot")
    report: dict[str, Any] = {"changes": str(changes), "snapshot_from": snapshot_from, "snapshot_to": snapshot_to}
    conn = await asyncpg.connect(_dsn(db_url))
    try:
        try:
            async with conn.transaction():
                for label, sid in (("from", snapshot_from), ("to", snapshot_to)):
                    row = await conn.fetchrow("SELECT id, snapshot_date, status FROM flats.snapshots WHERE id = $1", sid)
                    if row is None:
                        raise SystemExit(f"no flats.snapshots row {sid} for --{label}; register the snapshot first")
                    report[f"snapshot_{label}_date"] = row["snapshot_date"].isoformat()
                replaced = await conn.fetchval(
                    "WITH gone AS (DELETE FROM flats.lot_changes WHERE snapshot_from = $1 AND snapshot_to = $2 RETURNING 1) "
                    "SELECT count(*) FROM gone",
                    snapshot_from,
                    snapshot_to,
                )
                report["replaced"] = replaced
                sql = (
                    "INSERT INTO flats.lot_changes (snapshot_from, snapshot_to, county, tlid, kind, role, related_tlids, "
                    "area_before, area_after, iou, attr_diff, rlis_change, note) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, $13)"
                )
                written = 0
                batch: list[tuple[Any, ...]] = []
                for row in read_changes(changes):
                    batch.append(
                        (
                            snapshot_from, snapshot_to, row["county"], row["tlid"], row["kind"], row["role"],
                            row["related_tlids"], row["area_before"], row["area_after"], row["iou"],
                            json.dumps(row["attr_diff"], sort_keys=True, default=str), row["rlis_change"], row["note"],
                        )
                    )
                    if len(batch) >= batch_size:
                        await conn.executemany(sql, batch)
                        written += len(batch)
                        batch = []
                if batch:
                    await conn.executemany(sql, batch)
                    written += len(batch)
                report["written"] = written
                report["by_kind"] = dict(
                    (r["kind"], r["n"])
                    for r in await conn.fetch(
                        "SELECT kind, count(*) AS n FROM flats.lot_changes WHERE snapshot_from = $1 AND snapshot_to = $2 "
                        "GROUP BY 1 ORDER BY 1",
                        snapshot_from,
                        snapshot_to,
                    )
                )
                if sum(report["by_kind"].values()) != written:
                    raise SystemExit(f"VERIFY FAILED: {sum(report['by_kind'].values())} rows in the table, {written} written")
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
    ex.add_argument("--rules-version", default=None, help="rules hash the run was screened under (default: this checkout's)")
    ex.add_argument("--screen-version", default=None, help="hash of the screen's files the run was screened with (default: this checkout's)")
    ex.add_argument("--normalized", type=Path, default=None, help="the normalize stage's directory (default: meta.json's)")
    ex.add_argument(
        "--source-id",
        default=None,
        help="land on the run row with this params->>'source_id' (a re-screen of the same lots); default: a new run",
    )

    ld = sub.add_parser("load", help="load a bundle into flats.* (needs asyncpg)")
    ld.add_argument("--bundle", type=Path, required=True)
    ld.add_argument("--snapshot", type=int, required=True, help="flats.snapshots id the bundle's lots were read from")
    ld.add_argument("--db-url", default=None, help="default: app settings' database_url")
    ld.add_argument("--dry-run", action="store_true", help="do the whole load in a transaction and roll it back")
    ld.add_argument("--batch-size", type=int, default=20_000)

    lc = sub.add_parser("load-changes", help="load a delta's changes.csv.gz into flats.lot_changes (needs asyncpg)")
    lc.add_argument("--changes", type=Path, required=True, help="changes.csv.gz written by flats.ingest.delta")
    lc.add_argument("--from", dest="snapshot_from", type=int, required=True, help="flats.snapshots id of the older copy")
    lc.add_argument("--to", dest="snapshot_to", type=int, required=True, help="flats.snapshots id of the newer copy")
    lc.add_argument("--db-url", default=None, help="default: app settings' database_url")
    lc.add_argument("--dry-run", action="store_true", help="do the whole load in a transaction and roll it back")
    lc.add_argument("--batch-size", type=int, default=20_000)

    args = parser.parse_args(argv)
    if args.command == "export":
        run = export(
            args.run_dir,
            args.out,
            s4=args.s4,
            s5o=args.s5o,
            quadfit_results=args.quadfit_results,
            code_version=args.code_version,
            normalized=args.normalized,
            rules_ver=args.rules_version,
            source_id=args.source_id,
            screen_ver=args.screen_version,
        )
        keys = ("source_id", "status", "snapshot_date", "code_version", "rules_version", "screen_version", "design_keys", "counties", "counts")
        print(json.dumps({k: run.get(k) for k in keys}, indent=2))
        return 0

    db_url = args.db_url
    if db_url is None:
        from app.config import settings

        db_url = settings.database_url
    if args.command == "load-changes":
        report = asyncio.run(
            load_changes(
                args.changes, db_url,
                snapshot_from=args.snapshot_from, snapshot_to=args.snapshot_to,
                dry_run=args.dry_run, batch_size=args.batch_size,
            )
        )
    else:
        report = asyncio.run(
            load(args.bundle, db_url, snapshot_id=args.snapshot, dry_run=args.dry_run, batch_size=args.batch_size)
        )
    print(json.dumps(report, indent=2, default=str))
    if report.get("verified") and "checks" in report:
        blocks = report["blocks"]
        print(
            f"promotion gate: {'WARNED -- ' + ', '.join(blocks) + '; Steph reads the report' if blocks else 'clean'}",
            file=sys.stderr,
        )
    return 0 if report.get("verified") else 1


if __name__ == "__main__":
    sys.exit(main())
