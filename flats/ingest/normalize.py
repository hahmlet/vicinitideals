"""Every lot in a county-map snapshot, with what the screen knows before measuring.

The bridge (:mod:`flats.ingest.quadfit`) screens the lots quadfit measured --
the 289,845 that survived its structural filter -- and nothing else. The county
holds 453,000. The ones that never reached a measurement are not nothing: a
lot whose zone the rules do not hold, a lot in a city that is switched off, a
lot outside the growth boundary, a lot too small to measure. Each of those is
an answer the page owes ("we do not know, and here is why"), and a refresh that
brings a new zone code into the county has to be able to say so instead of
dropping the lot on the floor the way quadfit's s3 does (C4 in the refresh plan).

This stage builds the lot table from the snapshot's taxlot file, one row per
``(county, tlid)``:

* **jurisdiction** -- the FLATS layer id, from RLIS ``JURIS_CITY`` through each
  layer's ``ingest.juris_city_codes``; the two unincorporated layers share the
  blank code and the county letter decides. A city with no layer is
  ``None`` (Canby, Sandy, Molalla, Estacada, Barlow -- outside the encoded map).
* **zone** -- the majority-area join against the layer's zoning dataset from
  the same snapshot (:meth:`flats.ingest.sources.Pipeline.for_layer`), the
  code normalised the way the layer's ingest hints say (whitespace; Portland's
  lowercase suffix), and then kept only when the layer's rules hold it.
  ``zone_raw`` always keeps what the map said; a code the rules lack is counted
  in ``new_zones.json`` by layer -- the list the refresh report prints.
* **gate** -- why the screen cannot answer for this lot without a measurement
  it does not have, or ``None`` when nothing here stands in the way:
  ``JURISDICTION_NOT_ENCODED``, ``JURISDICTION_OFF`` (a layer with
  ``eligible: false`` or switched off in the registry -- Lake Oswego, HUMAN_TODO
  16), ``OUTSIDE_UGB`` (unincorporated county land beyond the Metro boundary,
  the same rule quadfit's rules apply), ``NO_ZONE`` (no zoning polygon covers
  the lot), ``ZONE_NOT_ENCODED``. The assign stage turns a gate into an
  ``unknown`` result with that reason.
* **assessor** -- the RLIS roll values (land, building, total, assessed, year
  built, building sqft, last sale, property code, state class, land use) as
  columns, adopted on every refresh -- Steph's "updated information we need to
  adopt as well".
* **condo** -- :func:`flats.normalize.condo.check_condo`; ``excluded`` rows
  (air parcels) are dropped and counted, ``suspect`` kept and marked.

What is dropped, and counted in ``funnel.json``: features with no usable
polygon; the right-of-way and water pseudo-lots (``NOT_A_TAXLOT_RE``); a
``(county, tlid)`` the file carries twice (the larger polygon stays); condo
air parcels; and condo stacks -- units platted on one identical footprint
collapse to one representative with ``stack_count``, the way quadfit's s1
does, so the two lot universes agree on what a lot is. Every dropped record
that has a ``(county, tlid)`` is also named in ``excluded.csv.gz`` with its
step and reason, so a later stage that meets the TLID again (quadfit's s1
measured 2,001 condominium unit records the September table lacked -- its
own condo test looks for stacked geometry, not the roll's property code)
can tell "not land" from "missing".

Outputs under ``--out``: ``lots.parquet`` (a ``wkb`` column carries the full
valid geometry, every part), ``excluded.csv.gz``, ``funnel.json``,
``new_zones.json``, ``summary.json``, ``summary.md``.

Runs on the analysis host (shapely, pyarrow, pandas)::

    python -m flats.ingest.normalize --snapshot 2026-09-18
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from flats.ingest.acquire import SNAPSHOTS, read_manifest, snapshot_dir
from flats.ingest.delta import COUNTY_NAMES, DEFAULT_COUNTIES, iter_features
from flats.ingest.sources import Pipeline, Provides, load_pipeline
from flats.normalize.condo import CondoVerdict, check_condo
from flats.rules.loader import load_rules
from flats.rules.model import Layer

#: The right-of-way and the water, which RLIS holds as polygons of their own
#: (Multnomah ``-STR`` / ``-RIV`` / ``-RR``, Clackamas ``ROADS`` / ``WATER``).
#: quadfit's ``common.NOT_A_TAXLOT_RE``, verbatim; a divergence here would
#: make the two lot universes disagree on what a lot is.
NOT_A_TAXLOT_RE = re.compile(r"(?:-STR|-RIV|-RR|ROADS|WATER)$")

#: ``excluded.csv.gz``: one row per record the lot table dropped by name.
EXCLUDED_COLUMNS = ("county", "tlid", "step", "reason", "area_sqft", "prop_code")

#: RLIS roll attributes carried as columns and adopted on every refresh.
ASSESSOR_FIELDS = (
    "LANDVAL",
    "BLDGVAL",
    "TOTALVAL",
    "ASSESSVAL",
    "YEARBUILT",
    "BLDGSQFT",
    "SALEDATE",
    "SALEPRICE",
    "PROP_CODE",
    "STATECLASS",
    "LANDUSE",
)

#: Below this share of the lot's area under its majority zone, the lot is
#: split-zoned (quadfit's ``s2_assign.SPLIT_ZONE_THRESHOLD``).
SPLIT_ZONE_THRESHOLD = 0.9

#: Why a lot cannot be screened without a measurement it does not have.
GATES = ("JURISDICTION_NOT_ENCODED", "JURISDICTION_OFF", "OUTSIDE_UGB", "NO_ZONE", "ZONE_NOT_ENCODED")

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "data" / "flats" / "normalized"

LOT_COLUMNS = (
    "county",
    "tlid",
    "juris_city",
    "jurisdiction",
    "site_address",
    "site_city",
    "site_zip",
    "area_sqft",
    "part_count",
    "stack_count",
    "condo_verdict",
    "condo_reason",
    "zone_raw",
    "zone",
    "zone_frac",
    "split_zone",
    "inside_ugb",
    "gate",
    *ASSESSOR_FIELDS,
    "wkb",
)


# --- jurisdiction ------------------------------------------------------------


@dataclass(frozen=True)
class Jurisdictions:
    """RLIS ``JURIS_CITY`` (+ county letter) -> FLATS layer id, from the layers' ingest hints."""

    by_code: dict[str, tuple[str, ...]]

    @classmethod
    def from_layers(cls, layers: dict[str, Layer]) -> Jurisdictions:
        by_code: dict[str, list[str]] = defaultdict(list)
        for layer_id, layer in sorted(layers.items()):
            if layer.kind in ("state", "county"):
                continue
            for code in layer.ingest.get("juris_city_codes") or ():
                by_code[str(code).strip().upper()].append(layer_id)
        return cls({k: tuple(v) for k, v in by_code.items()})

    def layer_for(self, juris_city: Any, county: str | None) -> str | None:
        """The layer whose codes hold ``juris_city``; the county picks between two that share one."""
        code = str(juris_city or "").strip().upper()
        found = self.by_code.get(code, ())
        if len(found) == 1:
            return found[0]
        if not found:
            return None
        for layer_id in found:
            if county and layer_id.startswith(f"or/{county}/"):
                return layer_id
        return None


# --- zone ---------------------------------------------------------------------


def normalize_zone(raw: Any, *, strip_lowercase_suffix: bool = False) -> str | None:
    """The zone code as the rules spell it: whitespace off, Portland's lowercase suffix off."""
    if raw is None:
        return None
    code = str(raw).strip()
    if not code:
        return None
    if strip_lowercase_suffix:
        stripped = code.rstrip("abcdefghijklmnopqrstuvwxyz")
        if stripped:
            code = stripped
    return code


def zone_for(layer: Layer | None, zone_raw: Any) -> tuple[str | None, str | None]:
    """``(normalised code, zone)`` -- ``zone`` is the code only when the layer's rules hold it."""
    if layer is None:
        return normalize_zone(zone_raw), None
    code = normalize_zone(zone_raw, strip_lowercase_suffix=bool(layer.ingest.get("strip_lowercase_suffix")))
    if code is None:
        return None, None
    return code, code if code in layer.zones else None


def assign_majority_zone(lot_geoms: list, zone_geoms: list, zone_codes: list) -> tuple[list, list]:
    """Vectorised majority-area zone join; ``(zone_raw, zone_frac)`` aligned with ``lot_geoms``.

    quadfit's ``s2_assign.assign_majority_zone``, verbatim in effect: the zone
    whose polygons cover the most of the lot wins, ``zone_frac`` is that
    share of the lot's area.
    """
    import numpy as np
    import shapely
    from shapely.strtree import STRtree

    zone_out: list[str | None] = [None] * len(lot_geoms)
    frac_out: list[float | None] = [None] * len(lot_geoms)
    if not lot_geoms or not zone_geoms:
        return zone_out, frac_out
    lots = np.array(lot_geoms, dtype=object)
    zones = np.array(zone_geoms, dtype=object)
    tree = STRtree(zones)
    li, zi = tree.query(lots, predicate="intersects")
    inter_area = shapely.area(shapely.intersection(lots[li], zones[zi]))
    best: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for lot_idx, zone_idx, a in zip(li, zi, inter_area):
        if a > 0:
            best[int(lot_idx)][zone_codes[int(zone_idx)]] += float(a)
    lot_areas = shapely.area(lots)
    for lot_idx, zmap in best.items():
        code, area = max(zmap.items(), key=lambda kv: kv[1])
        zone_out[lot_idx] = code
        frac_out[lot_idx] = min(1.0, area / lot_areas[lot_idx]) if lot_areas[lot_idx] else None
    return zone_out, frac_out


def load_zoning(path: Path, zone_field: str) -> tuple[list, list[str]]:
    """A zoning dataset's polygons and codes, valid and in the working CRS."""
    import shapely
    from shapely.geometry import shape

    geoms: list = []
    codes: list[str] = []
    for feature in iter_features(path):
        raw = feature.get("geometry")
        if not raw:
            continue
        try:
            geom = shape(raw)
        except Exception:
            continue
        if geom.is_empty:
            continue
        if not geom.is_valid:
            geom = shapely.make_valid(geom)
        props = feature.get("properties") or {}
        geoms.append(geom)
        codes.append(str(props.get(zone_field) if props.get(zone_field) is not None else ""))
    return geoms, codes


def gate_for(layer: Layer | None, *, on: bool, inside_ugb: bool, zone_raw: str | None, zone: str | None) -> str | None:
    """Why the screen cannot answer for this lot, or None."""
    if layer is None:
        return "JURISDICTION_NOT_ENCODED"
    if not layer.eligible or not on:
        return "JURISDICTION_OFF"
    if layer.kind == "unincorporated" and not inside_ugb:
        return "OUTSIDE_UGB"
    if zone_raw is None:
        return "NO_ZONE"
    if zone is None:
        return "ZONE_NOT_ENCODED"
    return None


# --- the stage ------------------------------------------------------------------


def _clean_polygon(raw: dict[str, Any] | None) -> tuple[Any | None, float, int]:
    """(valid multi/polygon of every part, area, part count); None when degenerate."""
    import shapely
    from shapely import get_parts
    from shapely.geometry import MultiPolygon, shape

    if not raw:
        return None, 0.0, 0
    try:
        geom = shape(raw)
    except Exception:
        return None, 0.0, 0
    if geom.is_empty:
        return None, 0.0, 0
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    parts = [p for p in get_parts(geom) if p.geom_type == "Polygon" and p.area > 0]
    if not parts:
        return None, 0.0, 0
    whole = parts[0] if len(parts) == 1 else MultiPolygon(parts)
    return whole, float(sum(p.area for p in parts)), len(parts)


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize(
    snapshot: Path,
    out: Path,
    *,
    layers: dict[str, Layer] | None = None,
    pipeline: Pipeline | None = None,
    counties: Iterable[str] = DEFAULT_COUNTIES,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Build the lot table for one snapshot; returns the summary written beside it."""
    import numpy as np
    import pandas as pd
    import shapely
    from shapely.strtree import STRtree

    say = log or (lambda _msg: None)
    started = time.monotonic()
    layers = layers or load_rules()
    pipeline = pipeline or load_pipeline()
    manifest = read_manifest(snapshot)
    jurisdictions = Jurisdictions.from_layers(layers)
    wanted = set(counties)

    def dataset_file(key: str) -> Path:
        entry = (manifest.get("datasets") or {}).get(key) or {}
        return snapshot / str(entry.get("file") or f"{key}.geojson")

    taxlots = next((d for d in pipeline.datasets.values() if d.provides is Provides.lots), None)
    if taxlots is None:
        raise SystemExit("the registry has no dataset that provides lots")
    path = dataset_file(taxlots.key)
    if not path.is_file():
        raise SystemExit(f"{path} is not in the snapshot")

    # 1. Every feature, cleaned; pseudo-lots and duplicates out.
    funnel: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    ledger: list[dict[str, Any]] = []

    def drop(county: str, tlid: str, step: str, reason: str | None, area: float | None, prop_code: Any) -> None:
        ledger.append(
            {
                "county": county,
                "tlid": tlid,
                "step": step,
                "reason": reason or "",
                "area_sqft": round(area, 1) if area is not None else "",
                "prop_code": _text(prop_code) or "",
            }
        )

    for feature in iter_features(path):
        counts["features"] += 1
        props = feature.get("properties") or {}
        letter = str(props.get("COUNTY") or "").strip().upper()
        county = COUNTY_NAMES.get(letter, letter.lower())
        if county not in wanted:
            counts["other_county"] += 1
            continue
        tlid = str(props.get("TLID") or "").rstrip()
        if not tlid:
            counts["no_tlid"] += 1
            continue
        if NOT_A_TAXLOT_RE.search(tlid):
            counts["not_a_taxlot"] += 1
            drop(county, tlid, "not_a_taxlot", None, None, props.get("PROP_CODE"))
            continue
        geom, area, parts = _clean_polygon(feature.get("geometry"))
        if geom is None:
            counts["no_geometry"] += 1
            drop(county, tlid, "no_geometry", None, None, props.get("PROP_CODE"))
            continue
        key = (county, tlid)
        if key in rows:
            counts["duplicate_tlid"] += 1
            if rows[key]["area_sqft"] >= area:
                drop(county, tlid, "duplicate_tlid", "smaller copy", area, props.get("PROP_CODE"))
                continue
            drop(county, tlid, "duplicate_tlid", "smaller copy", rows[key]["area_sqft"], rows[key].get("PROP_CODE"))
        row: dict[str, Any] = {
            "county": county,
            "tlid": tlid,
            "juris_city": _text(props.get("JURIS_CITY")),
            "site_address": _text(props.get("SITEADDR")),
            "site_city": _text(props.get("SITECITY")),
            "site_zip": _text(props.get("SITEZIP")),
            "area_sqft": area,
            "part_count": parts,
            "geom": geom,
            "COUNTY": letter,
        }
        for f in ASSESSOR_FIELDS:
            row[f] = props.get(f)
        rows[key] = row
    say(f"{counts['features']:,} features read in {time.monotonic() - started:.0f}s; {len(rows):,} lots kept")
    funnel.append({"step": "features", "count": counts["features"]})
    for step in ("other_county", "no_tlid", "not_a_taxlot", "no_geometry", "duplicate_tlid"):
        funnel.append({"step": step, "dropped": counts[step]})

    # 2. Condo: air parcels out, suspects marked; stacks collapsed to one.
    lots = list(rows.values())
    kept: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    for row in lots:
        verdict = check_condo({"area_sqft": row["area_sqft"], "BLDGSQFT": row["BLDGSQFT"], "PROP_CODE": row["PROP_CODE"], "COUNTY": row["COUNTY"]})
        row["condo_verdict"] = verdict.verdict.value
        row["condo_reason"] = verdict.reason or None
        if verdict.verdict is CondoVerdict.excluded:
            excluded[verdict.reason] += 1
            drop(row["county"], row["tlid"], "condo_excluded", verdict.reason, row["area_sqft"], row["PROP_CODE"])
            continue
        kept.append(row)
    funnel.append({"step": "condo_excluded", "dropped": len(lots) - len(kept), "reasons": dict(sorted(excluded.items()))})
    lots = kept
    stacks: dict[tuple[str, float, float, int], list[dict[str, Any]]] = defaultdict(list)
    for row in lots:
        c = row["geom"].centroid
        stacks[(row["county"], round(c.x, 1), round(c.y, 1), round(row["area_sqft"]))].append(row)
    kept = []
    for members in stacks.values():
        members.sort(key=lambda r: r["tlid"])
        members[0]["stack_count"] = len(members)
        kept.append(members[0])
        for other in members[1:]:
            drop(other["county"], other["tlid"], "condo_stack", f"stacked on {members[0]['tlid']}", other["area_sqft"], other["PROP_CODE"])
    funnel.append({"step": "condo_stack", "dropped": len(lots) - len(kept)})
    lots = sorted(kept, key=lambda r: (r["county"], r["tlid"]))
    say(f"{len(lots):,} lots after condo ({len(rows) - len(lots):,} out)")

    # 3. Jurisdiction.
    for row in lots:
        row["jurisdiction"] = jurisdictions.layer_for(row["juris_city"], row["county"])
    unmapped: Counter[str] = Counter(str(r["juris_city"] or "<blank>") for r in lots if r["jurisdiction"] is None)
    funnel.append({"step": "jurisdiction_unmapped", "count": sum(unmapped.values()), "juris_city": dict(unmapped.most_common())})

    # 4. Zone, one zoning dataset at a time, for every layer that has one.
    for row in lots:
        row["zone_raw"] = None
        row["zone_frac"] = None
    by_layer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in lots:
        if row["jurisdiction"] is not None:
            by_layer[row["jurisdiction"]].append(row)
    zoning_used: dict[str, str] = {}
    for layer_id, members in sorted(by_layer.items()):
        datasets = pipeline.for_layer(layer_id, Provides.zoning)
        if not datasets:
            say(f"{layer_id}: no zoning dataset in the registry; {len(members):,} lots stay unzoned")
            continue
        ds = datasets[0]
        zpath = dataset_file(ds.key)
        if not zpath.is_file():
            raise SystemExit(f"{layer_id}: zoning dataset {ds.key} is not in the snapshot ({zpath})")
        if not ds.zone_field:
            raise SystemExit(f"{ds.key}: a zoning dataset needs a zone_field")
        zgeoms, zcodes = load_zoning(zpath, ds.zone_field)
        zone_raw, zone_frac = assign_majority_zone([r["geom"] for r in members], zgeoms, zcodes)
        for row, zr, zf in zip(members, zone_raw, zone_frac):
            row["zone_raw"] = _text(zr)
            row["zone_frac"] = zf
        zoning_used[layer_id] = ds.key
        say(f"{layer_id}: {len(members):,} lots against {len(zgeoms):,} {ds.key} polygons")

    # 5. Inside the growth boundary.
    boundary = next((d for d in pipeline.datasets.values() if d.provides is Provides.boundary), None)
    inside = np.zeros(len(lots), dtype=bool)
    if boundary is not None and lots:
        ugb_geoms, _ = load_zoning(dataset_file(boundary.key), "OBJECTID")
        if ugb_geoms:
            tree = STRtree(np.array(ugb_geoms, dtype=object))
            reps = shapely.point_on_surface(np.array([r["geom"] for r in lots], dtype=object))
            li, _ = tree.query(reps, predicate="within")
            inside[li] = True
    for row, flag in zip(lots, inside):
        row["inside_ugb"] = bool(flag)

    # 6. The zone the rules hold, the gate, the new codes.
    new_zones: dict[str, Counter[str]] = defaultdict(Counter)
    gates: Counter[str] = Counter()
    for row in lots:
        layer = layers.get(row["jurisdiction"]) if row["jurisdiction"] else None
        code, zone = zone_for(layer, row["zone_raw"])
        row["zone"] = zone
        row["split_zone"] = bool(row["zone_frac"] is not None and row["zone_frac"] < SPLIT_ZONE_THRESHOLD)
        row["gate"] = gate_for(
            layer,
            on=bool(row["jurisdiction"] and pipeline.enabled(row["jurisdiction"])),
            inside_ugb=row["inside_ugb"],
            zone_raw=row["zone_raw"],
            zone=zone,
        )
        if row["gate"] == "ZONE_NOT_ENCODED" and code is not None:
            new_zones[row["jurisdiction"]][code] += 1
        gates[row["gate"] or "screenable"] += 1
        row.setdefault("stack_count", 1)

    # 7. Write.
    out.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [{**{c: r.get(c) for c in LOT_COLUMNS if c != "wkb"}, "wkb": shapely.to_wkb(r["geom"])} for r in lots],
        columns=list(LOT_COLUMNS),
    )
    for f in ("area_sqft", "zone_frac"):
        frame[f] = frame[f].astype("float64")
    frame.to_parquet(out / "lots.parquet", index=False)
    with gzip.open(out / "excluded.csv.gz", "wt", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(EXCLUDED_COLUMNS))
        w.writeheader()
        w.writerows(sorted(ledger, key=lambda r: (r["county"], r["tlid"], r["step"])))
    by_county = Counter(r["county"] for r in lots)
    by_layer_counts = Counter(str(r["jurisdiction"]) for r in lots)
    summary = {
        "snapshot": snapshot.name,
        "taxlots": taxlots.key,
        "taxlots_sha256": ((manifest.get("datasets") or {}).get(taxlots.key) or {}).get("sha256"),
        "lots": len(lots),
        "by_county": dict(sorted(by_county.items())),
        "by_jurisdiction": dict(sorted(by_layer_counts.items())),
        "by_gate": dict(sorted(gates.items())),
        "condo": {"suspect": sum(1 for r in lots if r["condo_verdict"] == "suspect"), "excluded": dict(sorted(excluded.items()))},
        "split_zone": sum(1 for r in lots if r["split_zone"]),
        "zoning": zoning_used,
        "new_zones": {k: dict(sorted(v.items())) for k, v in sorted(new_zones.items())},
        "funnel": funnel,
        "seconds": round(time.monotonic() - started, 1),
    }
    (out / "funnel.json").write_text(json.dumps(funnel, indent=2), encoding="utf-8")
    (out / "new_zones.json").write_text(json.dumps(summary["new_zones"], indent=2, sort_keys=True), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (out / "summary.md").write_text("\n".join(describe(summary)) + "\n", encoding="utf-8")
    say(f"wrote {len(lots):,} lots to {out} in {summary['seconds']}s")
    return summary


def describe(summary: dict[str, Any]) -> list[str]:
    """The summary in plain English, one line per fact."""
    out = [f"# County map {summary['snapshot']}: {summary['lots']:,} lots", ""]
    out.append("Of the taxlot file's features:")
    for step in summary["funnel"]:
        if "count" in step and step["step"] == "features":
            out.append(f"- {step['count']:,} features")
        elif "dropped" in step and step["dropped"]:
            extra = ""
            if step.get("reasons"):
                extra = " (" + ", ".join(f"{k} {v:,}" for k, v in step["reasons"].items()) + ")"
            out.append(f"- {step['dropped']:,} out: {step['step'].replace('_', ' ')}{extra}")
    out.append("")
    out.append("By county: " + ", ".join(f"{k} {v:,}" for k, v in summary["by_county"].items()))
    out.append("")
    out.append("Can the screen answer?")
    for gate, n in summary["by_gate"].items():
        out.append(f"- {gate}: {n:,}")
    unmapped = next((s for s in summary["funnel"] if s["step"] == "jurisdiction_unmapped"), None)
    if unmapped and unmapped.get("juris_city"):
        out.append("")
        out.append("Cities with no encoded layer: " + ", ".join(f"{k} {v:,}" for k, v in unmapped["juris_city"].items()))
    if summary["new_zones"]:
        out.append("")
        out.append("Zone codes on the map that the rules do not hold:")
        for layer_id, codes in summary["new_zones"].items():
            out.append(f"- {layer_id}: " + ", ".join(f"{c} ({n:,})" for c, n in codes.items()))
    else:
        out.append("")
        out.append("Every zone code on the map is one the rules hold.")
    out.append("")
    out.append(f"Split-zoned lots: {summary['split_zone']:,}; condo suspects kept: {summary['condo']['suspect']:,}.")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--snapshot", required=True, help="YYYY-MM-DD under data/flats/sources")
    ap.add_argument("--root", type=Path, default=SNAPSHOTS, help="where snapshots live")
    ap.add_argument("--out", type=Path, default=None, help="output directory (default: data/flats/normalized/<snapshot>)")
    ap.add_argument("--county", action="append", default=None, help="limit to a county (repeatable)")
    args = ap.parse_args(argv)
    snapshot = snapshot_dir(args.snapshot, args.root)
    if not snapshot.is_dir():
        raise SystemExit(f"no snapshot at {snapshot}")
    out = args.out or DEFAULT_OUT / args.snapshot
    summary = normalize(snapshot, out, counties=args.county or DEFAULT_COUNTIES, log=lambda m: print(m, flush=True))
    print()
    for line in describe(summary):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
