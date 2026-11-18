"""FD2 pass 1: measure and summarise every GREEN lot of a live run (FOLLOWUPS 199).

A report only (module docstring of :mod:`flats.ingest.fd2`): nothing here
changes a lot's colour, reasons, flags, drawing, the pages or any database.
Runs on LXC 137 against the run's files, lock-free (it reads; it never takes
the bridge machinery).

    soil-prep  the survey's horizons, restrictive layers, corrosion and the
               "dwellings without basements" reasons (Soil Data Access) per
               map unit -> soil_attrs.json
    run        every GREEN lot -> fd2_lots.parquet / .csv
    summary    the hand-off's tables -> summary_tables.md

Example (137)::

    PYTHONPATH=<worktree>:/root/fd2_pass1/pylib python scripts/flats_fd2_pass1.py soil-prep \\
        --gpkg .../SQLite_SSURGO_OR.gpkg --extract .../extract_2026-10-01 --out /root/fd2_pass1/soil_attrs.json
    ... run --assign /root/assign_rel9_fr/lots.parquet --quadfit data/quadfit_rel8 \\
        --soil-extract ... --soil-attrs ... --hazards /root/fd2_pass1/hazards_extract \\
        --occupancy .../occupancy.csv.gz --overlay gresham_hillside=... --out /root/fd2_pass1
    ... summary --out /root/fd2_pass1
"""

from __future__ import annotations

import argparse
import csv
import gzip
import importlib.util
import json
import math
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from flats.ingest import fd2  # noqa: E402

HUB_FROST = (
    "https://services1.arcgis.com/CD5mKowwN6nIaqd8/arcgis/rest/services/"
    "project_designcriteria_or_county_wind_weathering_frost_decay_freezing_ORSC_2026/FeatureServer/21/query"
)
SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/tabular/post.rest"
DWELLINGS = "ENG - Dwellings W/O Basements"
COUNTY_OF = {"multnomah": "Multnomah", "clackamas": "Clackamas", "washington": "Washington"}
ELEV_SOURCES = {"dem_1m": "1 m lidar DEM (s0 raw/dem, UTM 10N)", "dem_10m": "~10 m USGS 1/3 arc-second DEM (raw/dem10_utm)"}


def _hazards_module() -> Any:
    spec = importlib.util.spec_from_file_location("flats_lot_hazards", REPO / "scripts" / "flats_lot_hazards.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    sys.modules["flats_lot_hazards"] = mod
    spec.loader.exec_module(mod)
    return mod


# --- soil-prep -------------------------------------------------------------------


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


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


def soil_prep(gpkg: Path, extract: Path, out: Path, *, sda: bool = True) -> dict[str, Any]:
    """Per map unit of the soil extract: its components, each with the
    horizons, restrictive layers, corrosion, monthly water rows and the
    dwellings rating with its reasons."""
    units = {r["mukey"]: r for r in csv.DictReader(gzip.open(extract / "mapunits.csv.gz", "rt", encoding="utf-8"))}
    comps = list(csv.DictReader(gzip.open(extract / "components.csv.gz", "rt", encoding="utf-8")))
    cokeys = [c["cokey"] for c in comps]
    conn = sqlite3.connect(f"file:{gpkg.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    ccols = _cols(conn, "component")
    extra = [c for c in ("corsteel", "corcon", "hydricrating", "drainagecl") if c in ccols]
    marks = ",".join("?" for _ in cokeys)
    comp_extra = {str(r["cokey"]): dict(r) for r in conn.execute(
        f"SELECT cokey, {', '.join(extra)} FROM component WHERE cokey IN ({marks})", cokeys)}
    horizons: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in conn.execute(
        f"""SELECT h.cokey, h.chkey, h.hzname, h.hzdept_r, h.hzdepb_r, h.lep_r, h.frag3to10_r, h.fraggt10_r,
                   (SELECT u.unifiedcl FROM chunified u WHERE u.chkey = h.chkey
                      ORDER BY CASE WHEN u.rvindicator = 'Yes' THEN 0 ELSE 1 END, u.unifiedcl LIMIT 1) AS unified
            FROM chorizon h WHERE h.cokey IN ({marks}) ORDER BY h.cokey, h.hzdept_r""", cokeys):
        horizons[str(r["cokey"])].append(dict(r))
    restr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in conn.execute(
        f"SELECT cokey, reskind, reshard, resdept_r, resdepb_r FROM corestrictions WHERE cokey IN ({marks})", cokeys
    ):
        restr[str(r["cokey"])].append(dict(r))
    conn.close()
    reasons: dict[str, list[tuple[float, str]]] = defaultdict(list)
    sda_rows = 0
    sda_error = None
    if sda:
        import httpx

        try:
            with httpx.Client(headers={"User-Agent": "flats-fd2-report"}) as client:
                for i in range(0, len(cokeys), 400):
                    chunk = ",".join(f"'{int(k)}'" for k in cokeys[i:i + 400])
                    for row in _sda(client, (
                        "SELECT cokey, ruledepth, rulename, interphr, interphrc FROM cointerp "
                        f"WHERE cokey IN ({chunk}) AND ruledepth = 1 AND mrulename = '{DWELLINGS}'"
                    )):
                        sda_rows += 1
                        v = fd2._num(row.get("interphr"))
                        name = str(row.get("rulename") or row.get("interphrc") or "").strip()
                        if v is not None and v > 0 and name:
                            reasons[str(row["cokey"])].append((v, name))
        except Exception as exc:  # noqa: BLE001 -- the reasons stay missing; ``fill-reasons`` adds them later
            reasons.clear()
            sda_error = repr(exc)[:300]
    by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in comps:
        k = c["cokey"]
        months = json.loads(c["months"]) if c.get("months") else []
        found = sorted(reasons.get(k, []), key=lambda vn: (-vn[0], vn[1]))
        by_unit[c["mukey"]].append({
            "cokey": k, "compname": c["compname"], "comppct_r": fd2._num(c["comppct_r"]),
            "majcompflag": c["majcompflag"], "compkind": c.get("compkind"),
            "drainagecl": c.get("drainagecl") or comp_extra.get(k, {}).get("drainagecl"),
            "hydricrating": c.get("hydricrating") or comp_extra.get(k, {}).get("hydricrating"),
            "corsteel": comp_extra.get(k, {}).get("corsteel"),
            "corcon": comp_extra.get(k, {}).get("corcon"),
            "dwellings_rating": c.get("dwellings_rating") or None,
            "dwellings_reasons": "; ".join(f"{n} ({v:.2f})" for v, n in found) if found else None,
            "months": months,
            "horizons": horizons.get(k, []),
            "restrictions": restr.get(k, []),
        })
    out_units = {
        mk: {"musym": u.get("musym"), "muname": u.get("muname"), "areasymbol": u.get("areasymbol"),
             "components": by_unit.get(mk, [])}
        for mk, u in units.items()
    }
    meta = {"gpkg": str(gpkg), "extract": str(extract), "units": len(out_units), "components": len(comps),
            "sda_reason_rows": sda_rows, "sda_url": SDA_URL if sda else None, "sda_error": sda_error,
            "made_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    out.write_text(json.dumps({"meta": meta, "units": out_units}), encoding="utf-8")
    return meta


def fill_reasons(out: Path) -> dict[str, Any]:
    """Fetch the "dwellings without basements" reasons from Soil Data Access
    for the components the lots stand on, and write them into the outputs
    (for a run made while Soil Data Access was down)."""
    import httpx
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pq.read_table(out / "fd2_lots.parquet")
    recs = table.to_pylist()
    cokeys = sorted({str(r["cokey"]) for r in recs if r.get("cokey")})
    reasons: dict[str, list[tuple[float, str]]] = defaultdict(list)
    rows = 0
    with httpx.Client(headers={"User-Agent": "flats-fd2-report"}) as client:
        for i in range(0, len(cokeys), 200):
            chunk = ",".join(f"'{int(k)}'" for k in cokeys[i:i + 200])
            for row in _sda(client, (
                "SELECT cokey, ruledepth, rulename, interphr, interphrc FROM cointerp "
                f"WHERE cokey IN ({chunk}) AND ruledepth = 1 AND mrulename = '{DWELLINGS}'"
            )):
                rows += 1
                v = fd2._num(row.get("interphr"))
                name = str(row.get("rulename") or row.get("interphrc") or "").strip()
                if v is not None and v > 0 and name:
                    reasons[str(row["cokey"])].append((v, name))
    words = {k: "; ".join(f"{n} ({v:.2f})" for v, n in sorted(found, key=lambda vn: (-vn[0], vn[1])))
             for k, found in reasons.items()}
    filled = 0
    for r in recs:
        k = str(r.get("cokey") or "")
        if k in words:
            r["dwellings_reasons"] = words[k]
            filled += 1
    keys = table.column_names
    pq.write_table(pa.table({k: [r.get(k) for r in recs] for k in keys}), out / "fd2_lots.parquet")
    with open(out / "fd2_lots.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in recs:
            w.writerow({k: r.get(k) for k in keys})
    meta = json.loads((out / "fd2_meta.json").read_text(encoding="utf-8"))
    meta["fill_reasons"] = {"components": len(cokeys), "sda_rows": rows, "lots_filled": filled,
                            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (out / "fd2_meta.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return meta["fill_reasons"]


# --- run -------------------------------------------------------------------------

_W: dict[str, Any] = {}


def _init(cfg: dict[str, Any]) -> None:
    import numpy as np
    import pyarrow.parquet as pq
    import shapely

    from flats.ingest import quadfit
    from flats.ingest.hazards import load_registry
    from flats.rules.loader import load_rules

    _W["cfg"] = cfg
    _W["layers"] = load_rules()
    _W["terrain"] = quadfit.terrain_at(Path(cfg["quadfit"]) / "raw")
    haz = _hazards_module()
    _W["haz_layers"], _W["haz_cov"] = haz.open_layers(Path(cfg["hazards"]), load_registry())
    t = pq.read_table(Path(cfg["soil_extract"]) / "polygons.parquet")
    geoms = shapely.from_wkb(t.column("wkb").to_numpy(zero_copy_only=False))
    _W["soil_keys"] = np.array([str(k) for k in t.column("mukey").to_pylist()], dtype=object)
    _W["soil_geoms"] = geoms
    _W["soil_tree"] = shapely.STRtree(geoms)
    _W["soil"] = json.loads(Path(cfg["soil_attrs"]).read_text(encoding="utf-8"))["units"]
    _W["overlays"] = {name: _read_overlay(Path(p)) for name, p in (cfg.get("overlays") or {}).items()}


def _read_overlay(path: Path) -> Any:
    import numpy as np
    import shapely
    from pyproj import Transformer
    from shapely.geometry import shape

    data = json.loads(path.read_text(encoding="utf-8"))
    geoms = [shape(f["geometry"]) for f in data.get("features", []) if f.get("geometry")]
    if not geoms:
        return None
    g = shapely.union_all(geoms)
    x0 = g.bounds[0]
    if -180 <= x0 <= 180:  # lon/lat
        tf = Transformer.from_crs(4326, 2913, always_xy=True)
        g = shapely.transform(g, lambda xy: np.column_stack(tf.transform(xy[:, 0], xy[:, 1])))
    return shapely.make_valid(g)


def _z_reader(terrain: Any, fp: Any) -> tuple[Any, str | None, float | None]:
    """A function from (N, 2) EPSG:2913 points to ground in feet over the
    footprint's neighbourhood, the model used, and its cell size (m)."""
    import numpy as np

    pad_ft = 120.0
    b = fp.buffer(pad_ft).bounds
    fx, fy = terrain._fwd.transform([b[0], b[2], b[0], b[2]], [b[1], b[1], b[3], b[3]])
    bounds = (min(fx), min(fy), max(fx), max(fy))
    got = terrain._fine(bounds, strict=False) if terrain.tiles else None
    source = "dem_1m"
    if got is None or np.isnan(got[0]).mean() > 0.5:
        got = terrain._read(terrain.coarse, bounds) if terrain.coarse is not None else None
        source = "dem_10m"
        if got is not None and np.isnan(got[0]).all():
            got = None
    if got is None:
        return None, None, None
    raw, tf = got
    cell = abs(tf.a)

    def z_of(pts: Any) -> Any:
        pts = np.asarray(pts, dtype=float).reshape(-1, 2)
        if not len(pts):
            return np.zeros(0)
        x, y = terrain._fwd.transform(pts[:, 0], pts[:, 1])
        col = (np.asarray(x) - tf.c) / tf.a - 0.5
        row = (np.asarray(y) - tf.f) / tf.e - 0.5
        c0 = np.floor(col).astype(int)
        r0 = np.floor(row).astype(int)
        dc = col - c0
        dr = row - r0
        h, w = raw.shape
        ok = (c0 >= 0) & (r0 >= 0) & (c0 + 1 < w) & (r0 + 1 < h)
        out = np.full(len(pts), np.nan)
        if ok.any():
            cc, rr, a, bb = c0[ok], r0[ok], dc[ok], dr[ok]
            z = (raw[rr, cc] * (1 - a) * (1 - bb) + raw[rr, cc + 1] * a * (1 - bb)
                 + raw[rr + 1, cc] * (1 - a) * bb + raw[rr + 1, cc + 1] * a * bb)
            out[ok] = z * fd2.FT_PER_M
        return out

    return z_of, source, cell


def _steepest(terrain: Any, fp: Any, reach_ft: float) -> tuple[float | None, str | None]:
    import numpy as np

    from flats.fit.slope import _cells

    geom_m = terrain._to(fp.buffer(reach_ft), terrain._fwd)
    got = terrain._slope_pct(geom_m)
    if got is None:
        return None, None
    pct, tf, source, _raw, _ = got
    inside = _cells(geom_m, pct.shape, tf) & np.isfinite(pct)
    if not inside.any():
        return None, source
    return round(float(pct[inside].max()), 1), source


def _soil(fp: Any) -> dict[str, Any]:
    import shapely

    idx = _W["soil_tree"].query(fp, predicate="intersects")
    area: dict[str, float] = defaultdict(float)
    for i in idx:
        a = float(shapely.area(shapely.intersection(fp, _W["soil_geoms"][i])))
        if a > 0:
            area[str(_W["soil_keys"][i])] += a
    out: dict[str, Any] = {"soil_units_sqft": None, "mukey": None}
    if not area:
        out["soil_no_data"] = None
        out["soil_missing"] = "no survey polygon under the footprint"
        return out
    ranked = sorted(area.items(), key=lambda kv: (-kv[1], kv[0]))
    mk = ranked[0][0]
    unit = _W["soil"].get(mk) or {}
    out.update({
        "mukey": mk, "musym": unit.get("musym"), "muname": unit.get("muname"),
        "mu_share": round(ranked[0][1] / fp.area, 3),
        "soil_units_sqft": "; ".join(f"{(_W['soil'].get(k) or {}).get('musym')} {round(v)}" for k, v in ranked),
        "mu_urban_land": "urban land" in str(unit.get("muname") or "").lower(),
    })
    comps = sorted(unit.get("components") or [], key=lambda c: (-(c.get("comppct_r") or 0.0),
                   0 if str(c.get("majcompflag") or "").lower().startswith("y") else 1, str(c.get("cokey"))))
    if not comps:
        out["soil_no_data"] = True
        out["soil_missing"] = "map unit has no components"
        return out
    dom = comps[0]
    has = _has_data(dom)
    out.update({"comp_name": dom.get("compname"), "comp_pct": dom.get("comppct_r"),
                "comp_is_urban_land": str(dom.get("compname") or "").strip().lower() == "urban land",
                "comp_has_data": has})
    out["soil_no_data"] = bool(out["comp_is_urban_land"] or not has)
    out.update(_component_facts(dom))
    if out["soil_no_data"]:
        # Not part of the brief's class: the largest named soil series in the
        # unit (its horizons held), so a reader can see what sits under the
        # "Urban land" label. Reported in alt_* columns only.
        alt = next((c for c in comps if _has_data(c)
                    and str(c.get("compname") or "").strip().lower() != "urban land"), None)
        if alt is not None:
            out["alt_comp"] = alt.get("compname")
            out["alt_comp_pct"] = alt.get("comppct_r")
            out["_alt"] = _component_facts(alt)
    return out


def _has_data(c: dict[str, Any]) -> bool:
    """A component carries soil data when its horizon rows are held."""
    return bool(c.get("horizons"))


ALT_FIELDS = ("unified_1_5ft", "lep_1_5ft_pct", "frag_gt3in_pct", "restriction_cm", "restriction_kind",
              "bedrock_cm", "pan_cm", "pan_kind", "drainage", "hydric", "water_cm", "water_months",
              "dwellings_rating", "corrosion_steel", "corrosion_concrete")


def _component_facts(c: dict[str, Any]) -> dict[str, Any]:
    layer = fd2.soil_layer(c.get("horizons") or [])
    res = fd2.restrictions(c.get("restrictions") or [])
    water_cm, water_months = fd2.high_water(c.get("months"))
    return {
        "cokey": c.get("cokey"),
        **{k: v for k, v in layer.items() if k != "layer_horizons"},
        **res,
        "restrictions_known": bool(c.get("horizons")),
        "drainage": c.get("drainagecl"), "hydric": c.get("hydricrating"),
        "water_cm": water_cm, "water_months": water_months, "water_months_held": bool(c.get("months")),
        "dwellings_rating": c.get("dwellings_rating"), "dwellings_reasons": c.get("dwellings_reasons"),
        "corrosion_steel": c.get("corsteel"), "corrosion_concrete": c.get("corcon"),
    }


_SHALLOW = {"1": 1, "2": 2, "3": 3}
_DEEP = {"Low": 1, "Moderate": 2, "High": 3}
_OVER = {"1": 1, "2": 2, "3": 3, "4": 4}


def _hazards(fp: Any, layer_id: str | None) -> dict[str, Any]:
    from flats.ingest.hazards import measure_shape

    rows = list(measure_shape(fp, _W["haz_layers"], _W["haz_cov"], jurisdiction=layer_id))
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by[r["layer"]].append(r)
    have = {lay.spec.key for lay in _W["haz_layers"]}
    out: dict[str, Any] = {}

    def worst(key: str, order: dict[str, int]) -> tuple[str | None, float]:
        cls = [r for r in by.get(key, []) if r["state"] == "class" and str(r["class_code"]) in order]
        if not cls:
            return None, 0.0
        top = max(cls, key=lambda r: order[str(r["class_code"])])
        return str(top["class_label"] or top["class_code"]), round(sum(
            r["share"] for r in cls if order[str(r["class_code"])] == order[str(top["class_code"])]), 3)

    def share(key: str, state: str) -> float:
        return round(sum(r["share"] for r in by.get(key, []) if r["state"] == state), 3)

    # Landslide susceptibility: detailed where the detailed maps cover, else the overview.
    out["susc_shallow"], out["susc_shallow_share"] = worst("landslide_shallow", _SHALLOW)
    out["susc_deep"], out["susc_deep_share"] = worst("landslide_deep", _DEEP)
    out["susc_overview"], out["susc_overview_share"] = worst("landslide_overview", _OVER)
    out["susc_detailed_cover"] = round(1.0 - share("landslide_shallow", "outside"), 3) if "landslide_shallow" in have else None
    out["susc_source"] = (
        None if not ({"landslide_shallow", "landslide_overview"} & have)
        else "detailed" if (out["susc_detailed_cover"] or 0) >= 0.999
        else "overview" if (out["susc_detailed_cover"] or 0) <= 0.001
        else "detailed+overview"
    )
    top = []
    if out["susc_shallow"] == "High":
        top.append("detailed shallow High")
    if out["susc_deep"] == "High":
        top.append("detailed deep High")
    if out["susc_overview"] == "Very high":
        top.append("overview Very high")
    out["slide_top"] = None if out["susc_source"] is None else bool(top)
    out["slide_top_why"] = "; ".join(top) or None

    # Landslide inventory: inside, or within 100 ft.
    near: dict[str, float | None] = {}
    for key in ("landslide_inventory", "landslide_historic"):
        for r in by.get(key, []):
            if r["state"] == "nearest":
                near[str(r["class_code"])] = (r["detail"] or {}).get("distance_ft")
    inside_inv = [str(r["class_label"]) for r in by.get("landslide_inventory", []) if r["state"] == "class"]
    out["slide_inside"] = ", ".join(sorted(set(inside_inv))) or None
    out["slide_deposit_ft"] = near.get("Deposit")
    out["slide_scarp_flank_ft"] = near.get("Scarp flank")
    out["slide_historic_ft"] = near.get("Historic landslide point")
    scarp_near = None
    lay = next((x for x in _W["haz_layers"] if x.spec.key == "landslide_scarps"), None)
    if lay is not None:
        ring = fp.buffer(100.0)
        scarp_near = any(f.geom.intersects(ring) for f in lay.features(ring))
    out["slide_scarp_within_100ft"] = scarp_near
    if "landslide_inventory" in have:
        hits = [bool(inside_inv)]
        hits += [d is not None and d <= 100.0 for d in (near.get("Deposit"), near.get("Scarp flank"), near.get("Historic landslide point"))]
        hits.append(bool(scarp_near))
        out["slide_mapped"] = any(hits)
    else:
        out["slide_mapped"] = None

    # Liquefaction (O-19-09).
    liq = [r for r in by.get("liquefaction", []) if r["state"] == "class"]
    if "liquefaction" not in have:
        out["liq_class"], out["liq_top2"], out["liq_share"] = None, None, None
    elif not liq:
        out["liq_class"], out["liq_top2"], out["liq_share"] = None, None, 0.0
    else:
        topr = max(liq, key=lambda r: int(r["class_code"]))
        out["liq_class"] = str(topr["class_label"])
        out["liq_class_code"] = int(topr["class_code"])
        out["liq_share"] = round(sum(r["share"] for r in liq), 3)
        out["liq_top2"] = int(topr["class_code"]) >= 4
        major = max(liq, key=lambda r: r["share"])
        out["liq_majority"] = str(major["class_label"])

    # Flood.
    fema = [r for r in by.get("flood_fema", []) if r["state"] == "class"]
    if "flood_fema" not in have:
        out["fema_zone"], out["flood_100"] = None, None
    else:
        out["fema_zone"] = ", ".join(sorted({str(r["class_code"]) + (f" ({r['class_label']})" if r["class_label"] else "")
                                             for r in fema})) or "not mapped"
        out["flood_100"] = any((r["detail"] or {}).get("in_100_year") for r in fema)
    out["flood_title3"] = any(r["state"] == "class" for r in by.get("flood_title3", [])) if "flood_title3" in have else None
    out["flood_west_linn"] = any(r["state"] == "class" for r in by.get("flood_west_linn", [])) if "flood_west_linn" in have else None
    return out


def _one(item: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    import shapely
    from pyproj import Transformer
    from shapely.geometry import MultiLineString, Polygon

    from flats.geom.edges import EdgeClass
    from flats.ingest import quadfit

    a = item["assign"]
    row = item["row"]
    rec: dict[str, Any] = {
        "county": item["county"], "TLID": a["TLID"], "jurisdiction": a.get("jurisdiction"),
        "layer_id": a.get("layer_id"), "zone": a.get("zone"), "ask": a.get("ask"), "tier": a.get("tier"),
        "fit_angle_deg": a.get("fit_angle_deg"), "fit_orientation": a.get("fit_orientation"),
        "lot_sqft": a.get("lot_sqft"), "site_grade_pct": a.get("site_grade_pct"),
        "site_grade_source": a.get("site_grade_source"),
        "lot_slope_pct": item.get("slope_mean_pct"), "lot_slope_source": item.get("slope_source"),
        "errors": None,
    }
    errs: list[str] = []
    drawing = json.loads(a["drawing"]) if a.get("drawing") else {}
    ring = drawing.get("building")
    if not ring or row is None:
        rec["errors"] = "no drawn building" if not ring else "lot row not in s4"
        return rec
    lot = quadfit.lot_from_row(row, _W["layers"])
    streets = tuple(dict.fromkeys(quadfit._street_lines(lot) + quadfit._side_street_lines(lot)))
    fr = fd2.frame(ring, streets)
    fp = Polygon(ring)
    rec.update({"fp_long_ft": round(fr.long_ft, 2), "fp_short_ft": round(fr.short_ft, 2),
                "fp_area_sqft": round(fp.area, 1), "front_known": fr.front_known})
    c = fp.centroid
    lon, lat = Transformer.from_crs(2913, 4326, always_xy=True).transform(c.x, c.y)
    rec["lon"], rec["lat"] = round(lon, 6), round(lat, 6)

    # 1. Ground shape.
    terrain = _W["terrain"]
    z_of, src, cell = _z_reader(terrain, fp)
    rec["elev_source"], rec["elev_cell_m"] = src, cell
    if z_of is not None:
        rec.update(fd2.ground_shape(fr, z_of))
        fronts = tuple((e.x1, e.y1, e.x2, e.y2) for e in lot.edges.of_class(EdgeClass.front)) if lot.edges else ()
        env_rings = drawing.get("envelope") or []
        if fronts and env_rings and lot.lot_geom is not None:
            env = shapely.union_all([Polygon(r) for r in env_rings if len(r) >= 4])
            lines = MultiLineString([[(x1, y1), (x2, y2)] for x1, y1, x2, y2 in fronts])
            setback = float(env.distance(lines))
            rec["front_setback_ft"] = round(setback, 1)
            sb = fd2.setback_line(lot.lot_geom, fronts, max(setback, 0.01))
            rise = fd2.street_rise(z_of(fd2.line_points(fronts)), z_of(fd2.geom_points(sb)))
            rec["street_rise_ft"] = None if rise is None else round(rise, 2)
        else:
            rec["street_rise_ft"] = None
            errs.append("street rise: " + ("no front lot line" if not fronts else "no envelope"))
    else:
        errs.append("no elevation model covers the footprint")
    for reach in (10, 25):
        try:
            v, s2 = _steepest(terrain, fp, float(reach))
        except Exception as exc:  # noqa: BLE001 -- recorded, the lot goes on
            v, s2 = None, None
            errs.append(f"steepest {reach}: {exc!r}"[:120])
        rec[f"steepest_{reach}ft_pct"], rec[f"steepest_{reach}ft_source"] = v, s2

    # 2. Soil.
    rec.update(_soil(fp))
    # 3. Hazards and the held city overlays.
    rec.update(_hazards(fp, a.get("layer_id")))
    for name, geom in _W["overlays"].items():
        rec[f"overlay_{name}"] = None if geom is None else bool(geom.intersects(fp))
    # 4-6. Place, occupancy, route.
    occ = item.get("occ") or {}
    lab = occ.get("label")
    rec["occupancy_label"] = lab
    rec["occupied"] = None if not lab or lab == "unclear" else ("vacant" if lab == "vacant" else "built")
    yb = fd2._num(occ.get("year_built"))
    rec["year_built"] = int(yb) if yb and yb > 0 else None
    rec["basement"] = None  # the assessor's basement field is not held
    rec.update(fd2.visitability(a.get("layer_id"), a.get("zone"), rec["lot_slope_pct"], rec.get("street_rise_ft")))
    rec.update(fd2.frost(a.get("jurisdiction"), rec.get("ground_mean_ft"), item.get("hub_frost_in")))
    rec["hub_sdc"] = None
    g, unread, pan = fd2.ground_class(rec)
    rec["ground_class"], rec["ground_class_unread"], rec["pan"] = g, ",".join(unread) or None, pan
    alt = rec.pop("_alt", None)
    if alt is not None:
        for k in ALT_FIELDS:
            rec[f"alt_{k}"] = alt.get(k)
        # What the named series would sort as with this lot's hazards (the
        # brief's class stays NO-DATA; this column is for "what the classes hide").
        g2, _u2, pan2 = fd2.ground_class({**rec, **alt, "soil_no_data": False})
        rec["alt_ground_class"], rec["alt_pan"] = g2, pan2
    rec["relief_class"] = fd2.relief_class(rec.get("relief_ft"))
    rec["errors"] = "; ".join(errs) or None
    _ = np  # numpy is imported for the readers above
    return rec


def _chunk(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for it in items:
        try:
            out.append(_one(it))
        except Exception as exc:  # noqa: BLE001 -- a lot that breaks is reported, not dropped
            a = it["assign"]
            out.append({"county": it["county"], "TLID": a["TLID"], "jurisdiction": a.get("jurisdiction"),
                        "layer_id": a.get("layer_id"), "zone": a.get("zone"), "errors": f"failed: {exc!r}"[:300]})
    return out


def _hub_frost(points: dict[str, tuple[float, float]]) -> dict[str, dict[str, Any]]:
    import httpx

    out: dict[str, dict[str, Any]] = {}
    with httpx.Client(headers={"User-Agent": "flats-fd2-report"}, timeout=60) as client:
        for county, (lon, lat) in points.items():
            try:
                r = client.get(HUB_FROST, params={
                    "f": "json", "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": "4326",
                    "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "returnGeometry": "false"})
                feats = r.json().get("features") or []
                attrs = feats[0]["attributes"] if feats else {}
                raw = attrs.get("Frost_line_depth")
                m = re.search(r"[\d.]+", str(raw)) if raw is not None else None
                out[county] = {"frost_in": float(m.group()) if m else None, "raw": raw, "attributes": attrs,
                               "point": [lon, lat]}
            except Exception as exc:  # noqa: BLE001 -- a hub that does not answer leaves the column blank
                out[county] = {"frost_in": None, "error": repr(exc)[:200], "point": [lon, lat]}
    return out


def run(args: argparse.Namespace) -> dict[str, Any]:
    import pyarrow as pa
    import pyarrow.parquet as pq
    import shapely
    from pyproj import Transformer

    from flats.ingest import quadfit

    t0 = time.time()
    out = Path(args.out)
    cols = ["TLID", "jurisdiction", "zone", "layer_id", "ask", "tier", "colour", "drawing", "fit_angle_deg",
            "fit_orientation", "lot_sqft", "site_grade_pct", "site_grade_source"]
    greens = [r for r in pq.read_table(args.assign, columns=cols).to_pylist() if r["colour"] == "green"]
    if args.limit:
        greens = greens[: args.limit]
    tlids = [g["TLID"] for g in greens]
    qf = Path(args.quadfit)
    rows = {r["TLID"]: r for r in quadfit.iter_rows(qf / "s4_lots.parquet", qf / "s5o_lots.parquet", tlids=tlids)}
    s5 = pq.read_table(qf / "s5o_lots.parquet", columns=["TLID", "slope_mean_pct", "slope_source"]).to_pylist()
    slope = {r["TLID"]: r for r in s5 if r["TLID"] in rows}
    occ: dict[tuple[str, str], dict[str, Any]] = {}
    with gzip.open(args.occupancy, "rt", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            occ[(r["county"].lower(), r["tlid"])] = r
    # One Design Criteria Hub reading per county, at its first green lot.
    to_ll = Transformer.from_crs(2913, 4326, always_xy=True)
    points: dict[str, tuple[float, float]] = {}
    for g in greens:
        county = (g.get("layer_id") or "").split("/")[1] if g.get("layer_id") else None
        ring = (json.loads(g["drawing"]) if g.get("drawing") else {}).get("building")
        if county and county not in points and ring:
            c = shapely.Polygon(ring).centroid
            points[county] = to_ll.transform(c.x, c.y)
    hub = _hub_frost(points) if not args.no_hub else {}
    items = []
    for g in greens:
        county = (g.get("layer_id") or "").split("/")[1] if g.get("layer_id") else None
        s = slope.get(g["TLID"]) or {}
        items.append({"county": county, "assign": g, "row": rows.get(g["TLID"]),
                      "slope_mean_pct": fd2._num(s.get("slope_mean_pct")), "slope_source": s.get("slope_source"),
                      "occ": occ.get((county or "", g["TLID"])),
                      "hub_frost_in": (hub.get(county) or {}).get("frost_in")})
    cfg = {"quadfit": str(qf), "hazards": args.hazards, "soil_extract": args.soil_extract,
           "soil_attrs": args.soil_attrs,
           "overlays": dict(o.split("=", 1) for o in (args.overlay or []))}
    size = max(1, math.ceil(len(items) / (args.processes * 8)))
    chunks = [items[i:i + size] for i in range(0, len(items), size)]
    recs: list[dict[str, Any]] = []
    if args.processes <= 1:
        _init(cfg)
        for ch in chunks:
            recs += _chunk(ch)
    else:
        with ProcessPoolExecutor(args.processes, initializer=_init, initargs=(cfg,)) as ex:
            for got in ex.map(_chunk, chunks):
                recs += got
                print(f"{len(recs)}/{len(items)} {time.time() - t0:.0f}s", flush=True)
    keys: list[str] = []
    for r in recs:
        for k in r:
            if k not in keys:
                keys.append(k)
    table = pa.table({k: [_cell(r.get(k)) for r in recs] for k in keys})
    out.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out / "fd2_lots.parquet")
    with open(out / "fd2_lots.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in recs:
            w.writerow({k: r.get(k) for k in keys})
    meta = {"assign": args.assign, "quadfit": str(qf), "greens": len(greens), "rows": len(recs),
            "hub": hub, "seconds": round(time.time() - t0, 1), "cfg": cfg,
            "made_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (out / "fd2_meta.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return meta


def _cell(v: Any) -> Any:
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, (list, dict)):
        return json.dumps(v, default=str)
    return v


# --- summary ---------------------------------------------------------------------


def _table(head: list[str], rows: list[list[Any]]) -> str:
    def f(v: Any) -> str:
        return "" if v is None else str(v)
    lines = ["| " + " | ".join(f(h) for h in head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(f(v) for v in r) + " |" for r in rows]
    return "\n".join(lines)


def _cross(recs: list[dict[str, Any]], rk: str, ck: str, rorder: tuple[str, ...], corder: tuple[str, ...]) -> str:
    n = Counter((r.get(rk), r.get(ck)) for r in recs)
    rows = []
    for a in rorder:
        line = [a] + [n.get((a, b), 0) for b in corder]
        rows.append(line + [sum(line[1:])])
    tot = ["total"] + [sum(n.get((a, b), 0) for a in rorder) for b in corder]
    rows.append(tot + [sum(tot[1:])])
    return _table([rk, *corder, "total"], rows)


def summary(out: Path, *, seed: int = 199) -> str:
    import random

    import pyarrow.parquet as pq

    recs = pq.read_table(out / "fd2_lots.parquet").to_pylist()
    meta = json.loads((out / "fd2_meta.json").read_text(encoding="utf-8"))
    total = len(recs)
    parts: list[str] = [f"Lots: {total}"]
    counties = sorted({str(r.get("county")) for r in recs})
    g_order = (*fd2.GROUND_ORDER, None)
    g_names = tuple(str(x) for x in g_order)
    for r in recs:
        r["_g"] = str(r.get("ground_class"))
        r["_occ"] = str(r.get("occupied") or "unknown")
    # 1. ground x relief by county; and by vacant/built.
    parts.append("## 1. Ground class x relief class, by county")
    for cty in counties:
        sub = [r for r in recs if str(r.get("county")) == cty]
        parts.append(f"### {cty} ({len(sub)})\n" + _cross(sub, "_g", "relief_class", g_names, fd2.RELIEF_ORDER))
    parts.append("### all counties\n" + _cross(recs, "_g", "relief_class", g_names, fd2.RELIEF_ORDER))
    for occ in ("vacant", "built", "unknown"):
        for cty in counties:
            sub = [r for r in recs if str(r.get("county")) == cty and r["_occ"] == occ]
            parts.append(f"### {cty}, {occ} ({len(sub)})\n" + _cross(sub, "_g", "relief_class", g_names, fd2.RELIEF_ORDER))
    parts.append("### By county and occupancy\n" + _table(
        ["county", "vacant", "built", "unknown", "total"],
        [[c] + [sum(1 for r in recs if str(r.get("county")) == c and r["_occ"] == o) for o in ("vacant", "built", "unknown")]
         + [sum(1 for r in recs if str(r.get("county")) == c)] for c in counties]))
    parts.append("### PAN (hardpan, not bedrock, within 3.5 ft) by ground class\n" + _cross(
        recs, "_g", "pan", g_names, (True, False, None)))  # type: ignore[arg-type]

    # 2. Top 25 map units.
    mu = Counter((r.get("musym"), r.get("muname"), r.get("mukey")) for r in recs if r.get("mukey"))
    rows = []
    for (sym, name, mk), n in mu.most_common(25):
        one = next(r for r in recs if r.get("mukey") == mk)
        rows.append([sym, name, n, one.get("comp_name"), one.get("comp_pct"), one.get("unified_1_5ft_all"),
                     one.get("drainage"), one.get("water_cm"), one.get("water_months"),
                     one.get("restrictions_all"), one.get("lep_1_5ft_pct"), one.get("frag_gt3in_pct"),
                     one.get("dwellings_rating"), one.get("dwellings_reasons"), one.get("corrosion_steel"),
                     one.get("corrosion_concrete"), one.get("hydric"), "yes" if one.get("soil_no_data") else "no",
                     one.get("ground_class")])
    parts.append("## 2. The 25 most common map units\n" + _table(
        ["musym", "map unit", "lots", "dominant component", "%", "Unified 1-5 ft", "drainage", "high water cm",
         "months", "restrictive layers", "LEP 1-5 ft", "frag >3in %", "dwellings w/o basements", "reasons",
         "corr. steel", "corr. concrete", "hydric", "Urban land / no data", "ground class"], rows))
    parts.append(f"Lots with no map unit under the footprint: {sum(1 for r in recs if not r.get('mukey'))}")

    # 3. Distributions.
    for key in ("fall_along_ft", "fall_across_ft", "relief_ft"):
        n = Counter(fd2.ft_bin(r.get(key)) for r in recs)
        order = sorted((b for b in n if b != "missing"), key=lambda b: int(b.split("-")[0])) + (["missing"] if "missing" in n else [])
        parts.append(f"## 3. {key} (size, 1 ft bins)\n" + _table(["bin_ft", "lots"], [[b, n[b]] for b in order]
                                                                   + [["total", sum(n.values())]]))
    parts.append("### High side across\n" + _table(["high side", "lots"], [[k, v] for k, v in Counter(
        str(r.get("high_side")) for r in recs).most_common()]))
    parts.append("### High end along\n" + _table(["high end", "lots"], [[k, v] for k, v in Counter(
        str(r.get("high_end")) for r in recs).most_common()]))

    # 4. Jurisdiction x SDC x frost.
    n = Counter((r.get("jurisdiction"), r.get("hub_sdc"), r.get("frost_hub_in"), r.get("frost_register_in"),
                 r.get("frost_register_level"), r.get("frost_disagree")) for r in recs)
    parts.append("## 4. Jurisdiction, seismic design category, frost depth\n" + _table(
        ["jurisdiction", "SDC (hub)", "frost hub in", "frost register in", "register level", "disagree", "lots"],
        [[*k, v] for k, v in sorted(n.items(), key=lambda kv: -kv[1])] + [["total", "", "", "", "", "", total]]))
    above = Counter(r.get("jurisdiction") for r in recs if r.get("frost_above_stated_band"))
    parts.append("Lots above the elevation their place's frost figure is stated for: " + json.dumps(above))
    parts.append("Hub readings: " + json.dumps({k: {"frost_in": v.get("frost_in"), "raw": v.get("raw")}
                                                  for k, v in (meta.get("hub") or {}).items()}))

    # 5. Visitability.
    n = Counter((r.get("visit_status"), r.get("visit_exempt"), r.get("visit_exempt_why")) for r in recs)
    parts.append("## 5. Step-free entry rule\n" + _table(
        ["status", "exempt", "why", "lots"], [[*k, v] for k, v in sorted(n.items(), key=lambda kv: -kv[1])]
        + [["total", "", "", total]]))

    # 6. Missing shares.
    fields = ["elev_source", "relief_ft", "fall_along_ft", "fall_across_ft", "street_rise_ft", "lot_slope_pct",
              "steepest_10ft_pct", "steepest_25ft_pct", "mukey", "comp_name", "unified_1_5ft", "drainage",
              "water_cm", "restriction_cm", "lep_1_5ft_pct", "frag_gt3in_pct", "dwellings_rating",
              "dwellings_reasons", "corrosion_steel", "corrosion_concrete", "hydric", "susc_source", "slide_mapped",
              "liq_class", "fema_zone", "occupied", "year_built", "basement", "frost_hub_in", "frost_register_in",
              "hub_sdc", "visit_status"]
    rows = [[f, sum(1 for r in recs if r.get(f) in (None, "")), round(100 * sum(1 for r in recs if r.get(f) in (None, "")) / total, 1)]
            for f in fields]
    parts.append("## 6. Missing per input\n" + _table(["input", "lots missing", "% missing"], rows))
    parts.append("Elevation source: " + json.dumps(Counter(f"{r.get('elev_source')} cell {r.get('elev_cell_m')} m" for r in recs)))
    parts.append("Errors: " + json.dumps(Counter(str(r.get("errors"))[:80] for r in recs).most_common(12)))

    # 7. Twenty random lots.
    rnd = random.Random(seed)
    pick = rnd.sample(recs, min(20, total))
    keys = [k for k in recs[0] if not k.startswith("_")]
    parts.append("## 7. Twenty random lots (seed %d)\n" % seed + "\n".join(
        "- " + json.dumps({k: p.get(k) for k in keys}, default=str) for p in pick))

    # 8. What the classes hide (inputs for the write-up).
    nod = [r for r in recs if r.get("ground_class") == "NO-DATA"]
    parts.append("## 8a. NO-DATA lots: what the largest named series would sort as (not the brief's class)\n"
                 + _table(["alt ground class", "alt PAN", "lots"], [[*k, v] for k, v in sorted(Counter(
                     (r.get("alt_ground_class"), r.get("alt_pan")) for r in nod).items(), key=lambda kv: -kv[1])]
                     + [["total", "", len(nod)]]))
    alts = Counter((r.get("musym"), r.get("alt_comp"), r.get("alt_comp_pct"), r.get("alt_unified_1_5ft"),
                    r.get("alt_drainage"), r.get("alt_water_cm"), r.get("alt_pan_kind"), r.get("alt_pan_cm"),
                    r.get("alt_lep_1_5ft_pct"), r.get("alt_ground_class")) for r in nod)
    parts.append("### NO-DATA map units and their named series\n" + _table(
        ["musym", "series", "%", "Unified 1-5 ft", "drainage", "high water cm", "pan", "pan cm", "LEP", "alt class",
         "lots"], [[*k, v] for k, v in alts.most_common(25)]))
    parts.append("### Checks a lot's class could not make (input missing), by class\n" + _table(
        ["ground class", "unread checks", "lots"], [[*k, v] for k, v in sorted(Counter(
            (r.get("ground_class"), r.get("ground_class_unread")) for r in recs
            if r.get("ground_class_unread")).items(), key=lambda kv: -kv[1])]))
    steep = Counter((r.get("relief_class"), fd2.ft_bin((r.get("steepest_25ft_pct") or 0) / 10)
                     if r.get("steepest_25ft_pct") is not None else "missing") for r in recs)
    parts.append("### Relief class x steepest ground within 25 ft (bins of 10 %)\n" + _table(
        ["relief class", "steepest 25 ft, 10% bin", "lots"],
        [[*k, v] for k, v in sorted(steep.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1])))]))
    parts.append("### Street rise (ft, 1 ft bins, signed: + = setback above street)\n" + _table(
        ["bin", "lots"], [[k, v] for k, v in sorted(Counter(
            "missing" if r.get("street_rise_ft") is None else str(math.floor(r["street_rise_ft"]))
            for r in recs).items(), key=lambda kv: (kv[0] == "missing", float(kv[0]) if kv[0] != "missing" else 0))]))
    parts.append("### Liquefaction (worst class touching the footprint) and FEMA zone\n" + _table(
        ["liquefaction", "lots"], [[k, v] for k, v in Counter(str(r.get("liq_class")) for r in recs).most_common()])
        + "\n\n" + _table(["FEMA zone", "lots"], [[k, v] for k, v in Counter(
            str(r.get("fema_zone")) for r in recs).most_common()]))
    parts.append("### Landslide susceptibility (source, top class)\n" + _table(
        ["source", "shallow", "deep", "overview", "lots"], [[*k, v] for k, v in Counter(
            (r.get("susc_source"), r.get("susc_shallow"), r.get("susc_deep"), r.get("susc_overview"))
            for r in recs).most_common()]))

    # Gates.
    bad =[r["TLID"] for r in recs if r.get("relief_ft") is not None and (
        (r.get("fall_along_ft") is not None and r["relief_ft"] + 1e-6 < abs(r["fall_along_ft"]))
        or (r.get("fall_across_ft") is not None and r["relief_ft"] + 1e-6 < abs(r["fall_across_ft"])))]
    parts.append(f"## Gates\nrelief >= |falls| failures: {len(bad)} {bad[:10]}\nrows {total} vs greens {meta.get('greens')}")
    text = "\n\n".join(parts)
    (out / "summary_tables.md").write_text(text, encoding="utf-8")
    return text


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("soil-prep")
    s.add_argument("--gpkg", required=True)
    s.add_argument("--extract", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--no-sda", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--assign", required=True)
    r.add_argument("--quadfit", required=True)
    r.add_argument("--soil-extract", required=True)
    r.add_argument("--soil-attrs", required=True)
    r.add_argument("--hazards", required=True)
    r.add_argument("--occupancy", required=True)
    r.add_argument("--overlay", action="append", help="name=path.geojson")
    r.add_argument("--out", required=True)
    r.add_argument("--processes", type=int, default=8)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--no-hub", action="store_true")
    m = sub.add_parser("summary")
    m.add_argument("--out", required=True)
    m.add_argument("--seed", type=int, default=199)
    f = sub.add_parser("fill-reasons")
    f.add_argument("--out", required=True)
    args = p.parse_args(argv)
    if args.cmd == "fill-reasons":
        print(json.dumps(fill_reasons(Path(args.out)), indent=2))
    elif args.cmd == "soil-prep":
        print(json.dumps(soil_prep(Path(args.gpkg), Path(args.extract), Path(args.out), sda=not args.no_sda), indent=2))
    elif args.cmd == "run":
        meta = run(args)
        print(json.dumps({k: v for k, v in meta.items() if k != "hub"}, indent=2, default=str))
    else:
        print(summary(Path(args.out), seed=args.seed)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
