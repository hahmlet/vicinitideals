"""FD5 pass 2 for the foundation research (report only; FOLLOWUPS 199).

Adds columns to the FD2 pass 1 lot file (``fd2_lots.csv``, 9,517 live GREEN
lots of run 128) without changing any column it already has. Nothing here
changes a lot's colour, reasons, flags, drawing, page or database row.

Subcommands:

* ``extract`` (LXC 137; pyarrow only, one process, streamed in batches): the
  greens' rows of the live assign file (drawing, fit angle, orientation) and
  of quadfit's s4 / s5o stage files, written small so the rest runs on a PC.
* ``measure`` (PC): per lot, against the extract, the RLIS building
  footprints, the DOGAMI O-12-02 fill polygons and the lot's street lines,
  writes ``fd5_cols.csv`` (TLID + the new columns). Where the lot file
  carries stage B's ``flat_ring`` the same building and fill measures are
  taken for that position too (``flat_*``).
* ``join``: folds ``fd5_cols.csv`` into a lot file (replacing any earlier
  fd5 columns, keeping every other column and its order) -- run again after
  stage B lands.
* ``summary``: the hand-off's count tables, as Markdown.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

ASSIGN_COLS = ["TLID", "layer_id", "colour", "drawing", "fit_angle_deg", "fit_orientation", "front_deg"]
FOOTPRINT_SOURCE = "Metro RLIS Building Footprint Database (FeatureServer/8)"
FILL_SOURCE = "DOGAMI O-12-02 (Ma, Madin, Duplantis, Williams 2012), unit Aaf"
BASEMENT_NOT_HELD = "not held"
#: Why the assessor basement field is not held, per county (scout 2026-11-18).
BASEMENT_WHY = {
    "multnomah": "not published in bulk: RLIS/PortlandMaps taxlots carry YEARBUILT, BLDGSQFT, FLOORS only; "
                 "the assessor's Improvements Characteristics report is fee-for-service, layout unseen",
    "clackamas": "not published: CMap shows sq ft, bedrooms, baths, year built only; the bulk tax lot "
                 "download sits behind a licence click-through (not accepted)",
    "washington": "not published: GIS taxlots carry map numbers and value only; the A&T account page "
                  "lists improvement sections with no basement row; a paid extract ($187 prepay) is unread",
}

FD5_COLS = (
    "bldg_fp_held", "bldg_on_lot_n", "bldg_on_lot_sqft", "bldg_overlap_sqft", "bldg_overlap_share",
    "bldg_overlap_band", "bldg_gap_ft", "bldg_gap_any_ft", "bldg_fp_subarea", "bldg_fp_source_ref",
    "bldg_fp_created", "year_built_band", "basement_source",
    "fill_map_cover", "fill_touches", "fill_share", "fill_dist_ft",
    "front_face_street_ft", "back_face_street_ft", "front_face_turn_deg", "front_known_fd5",
    "flat_bldg_overlap_share", "flat_bldg_overlap_band", "flat_bldg_gap_ft", "flat_fill_touches",
    "flat_fill_share",
)


# --- extract (LXC 137) ----------------------------------------------------------


def extract(assign: Path, quadfit: Path, out: Path, batch: int = 20000) -> dict[str, Any]:
    """The greens' rows of the assign file and of quadfit s4 / s5o, streamed."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    out.mkdir(parents=True, exist_ok=True)
    greens: set[str] = set()
    parts = []
    for b in pq.ParquetFile(assign).iter_batches(batch_size=batch, columns=ASSIGN_COLS):
        t = pa.Table.from_batches([b])
        keep = [i for i, c in enumerate(t.column("colour").to_pylist()) if c == "green"]
        if keep:
            t = t.take(keep)
            greens.update(t.column("TLID").to_pylist())
            parts.append(t)
    pq.write_table(pa.concat_tables(parts), out / "greens_assign.parquet")
    counts = {"greens": len(greens)}
    for name in ("s4_lots.parquet", "s5o_lots.parquet"):
        pf = pq.ParquetFile(quadfit / name)
        got = []
        for b in pf.iter_batches(batch_size=batch):
            t = pa.Table.from_batches([b])
            keep = [i for i, k in enumerate(t.column("TLID").to_pylist()) if k in greens]
            if keep:
                got.append(t.take(keep))
        tab = pa.concat_tables(got) if got else pf.schema_arrow.empty_table()
        pq.write_table(tab, out / name)
        counts[name] = tab.num_rows
    (out / "extract_meta.json").write_text(json.dumps({
        "assign": str(assign), "quadfit": str(quadfit), "counts": counts,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=2), encoding="utf-8")
    return counts


# --- measure (PC) ---------------------------------------------------------------


def _footprints(path: Path) -> tuple[list[Any], list[dict[str, Any]]]:
    import shapely
    from shapely.geometry import shape

    geoms, props = [], []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            d = json.loads(line)
            if not d.get("g"):
                continue
            g = shape(d["g"])
            if not g.is_valid:
                g = shapely.make_valid(g)
            geoms.append(g)
            props.append(d.get("p") or {})
    return geoms, props


def _fill_layer(gdb: Path) -> tuple[list[Any], list[bool]]:
    import numpy as np
    import pyogrio
    import shapely
    from pyproj import Transformer

    meta, _fids, wkb, fields = pyogrio.raw.read(gdb, layer="MapUnitPolys", columns=["MAP_UNIT_L"])
    crs = meta.get("crs") or "EPSG:2994"
    tf = Transformer.from_crs(crs, 2913, always_xy=True)
    geoms = shapely.from_wkb(wkb)
    geoms = shapely.transform(geoms, lambda xy: np.column_stack(tf.transform(xy[:, 0], xy[:, 1])))
    geoms = [shapely.make_valid(g) if not g.is_valid else g for g in geoms]
    from flats.ingest import fd5

    is_fill = [str(u).strip() in fd5.FILL_UNITS for u in fields[0]]
    return geoms, is_fill


def _ms_date(v: Any) -> str | None:
    try:
        return time.strftime("%Y-%m-%d", time.gmtime(int(v) / 1000)) if v else None
    except (TypeError, ValueError, OverflowError):
        return None


def _ring_poly(ring: Any) -> Any | None:
    from shapely.geometry import Polygon

    if isinstance(ring, str):
        try:
            ring = json.loads(ring)
        except ValueError:
            return None
    if not ring or len(ring) < 4:
        return None
    return Polygon(ring)


def measure(args: argparse.Namespace) -> dict[str, Any]:
    import pyarrow.parquet as pq
    import shapely
    from shapely.strtree import STRtree

    from flats.ingest import fd2, fd5, quadfit
    from flats.rules.loader import load_rules

    t0 = time.time()
    ex = Path(args.extract)
    with open(args.csv, newline="", encoding="utf-8") as fh:
        lots = list(csv.DictReader(fh))
    assign = {r["TLID"]: r for r in pq.read_table(ex / "greens_assign.parquet").to_pylist()}
    rows = {r["TLID"]: r for r in quadfit.iter_rows(ex / "s4_lots.parquet", ex / "s5o_lots.parquet",
                                                     tlids=[r["TLID"] for r in lots])}
    layers = load_rules()
    print(f"lots {len(lots)} assign {len(assign)} rows {len(rows)} {time.time() - t0:.0f}s", flush=True)
    fgeoms, fprops = _footprints(Path(args.footprints) / "footprints.geojsonl.gz")
    ftree = STRtree(fgeoms)
    print(f"footprints {len(fgeoms)} {time.time() - t0:.0f}s", flush=True)
    ugeoms, ufill = _fill_layer(Path(args.fill))
    utree = STRtree(ugeoms)
    print(f"fill units {len(ugeoms)} (fill {sum(ufill)}) {time.time() - t0:.0f}s", flush=True)

    def bldg(fp: Any, lot: Any) -> dict[str, Any]:
        near_lot = [fgeoms[i] for i in ftree.query(lot, predicate="intersects")]
        near_any = [fgeoms[i] for i in ftree.query(shapely.buffer(fp, fd5.NEAR_ANY_FT), predicate="intersects")]
        held = len(near_lot) + len(ftree.query(shapely.buffer(lot, fd5.COVERAGE_FT))) > 0
        got = fd5.stand_on(fp, lot, near_lot, near_any)
        if not held:
            got.update({k: None for k in got})
            got["bldg_overlap_band"] = fd5.overlap_band(None)
        got["bldg_fp_held"] = held
        return got

    def fill(fp: Any) -> dict[str, Any]:
        idx = utree.query(shapely.buffer(fp, 500.0), predicate="intersects")
        return fd5.fill_measure(fp, [ugeoms[i] for i in idx if ufill[i]],
                                [ugeoms[i] for i in utree.query(fp, predicate="intersects")])

    out_rows = []
    n = Counter()
    for k, r in enumerate(lots):
        tlid = r["TLID"]
        rec: dict[str, Any] = {"TLID": tlid, "county": r["county"]}
        a, row = assign.get(tlid), rows.get(tlid)
        ring = (json.loads(a["drawing"]) if a and a.get("drawing") else {}).get("building")
        fp = _ring_poly(ring)
        lot = shapely.from_wkb(row["lot_wkb"]) if row and row.get("lot_wkb") else None
        rec["year_built_band"] = fd5.year_band(r.get("year_built"))
        rec["basement_source"] = BASEMENT_WHY.get(r["county"], "not held")
        if fp is None or lot is None:
            n["no ring or lot"] += 1
            rec["bldg_overlap_band"] = "not held"
            out_rows.append(rec)
            continue
        if not lot.is_valid:
            lot = shapely.make_valid(lot)
        rec.update(bldg(fp, lot))
        if rec.get("bldg_fp_held"):
            touch = [i for i in ftree.query(fp, predicate="intersects")]
            pick = max(touch, key=lambda i: shapely.area(shapely.intersection(fp, fgeoms[i])), default=None)
            if pick is None:
                cand = list(ftree.query(lot, predicate="intersects"))
                pick = min(cand, key=lambda i: shapely.distance(fp, fgeoms[i]), default=None)
            if pick is not None:
                p = fprops[pick]
                rec["bldg_fp_subarea"] = p.get("SUBAREA")
                rec["bldg_fp_source_ref"] = (str(p.get("SOURCE_REF") or "").strip() or None)
                rec["bldg_fp_created"] = _ms_date(p.get("CREATEDATE"))
        rec.update(fill(fp))
        try:
            ql = quadfit.lot_from_row(row, layers)
            streets = tuple(dict.fromkeys(quadfit._street_lines(ql) + quadfit._side_street_lines(ql)))
            fr = fd2.frame(ring, streets)
            rec["front_known_fd5"] = fr.front_known
            rec.update(fd5.front_face(fr.fl, fr.fr, fr.bl, fr.br, streets))
        except Exception as exc:  # noqa: BLE001 -- recorded, the lot goes on
            n["front face error"] += 1
            rec["front_known_fd5"] = None
            print(f"{tlid}: front face {exc!r}"[:200], flush=True)
        fflat = _ring_poly(r.get("flat_ring")) if r.get("flat_status") == "searched" else None
        if fflat is not None:
            b2 = fd5.stand_on(fflat, lot, [fgeoms[i] for i in ftree.query(lot, predicate="intersects")])
            f2 = fill(fflat)
            rec.update({"flat_bldg_overlap_share": b2["bldg_overlap_share"],
                        "flat_bldg_overlap_band": b2["bldg_overlap_band"] if rec.get("bldg_fp_held") else "not held",
                        "flat_bldg_gap_ft": b2["bldg_gap_ft"],
                        "flat_fill_touches": f2["fill_touches"], "flat_fill_share": f2["fill_share"]})
        out_rows.append(rec)
        if (k + 1) % 1000 == 0:
            print(f"{k + 1}/{len(lots)} {time.time() - t0:.0f}s", flush=True)
    outp = Path(args.out)
    outp.mkdir(parents=True, exist_ok=True)
    with open(outp / "fd5_cols.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["TLID", "county", *FD5_COLS])
        w.writeheader()
        for rec in out_rows:
            w.writerow({k: rec.get(k) for k in ["TLID", "county", *FD5_COLS]})
    fmeta = json.loads((Path(args.footprints) / "meta.json").read_text(encoding="utf-8"))
    meta = {"csv": str(args.csv), "extract": str(ex), "footprints": {k: fmeta.get(k) for k in (
                "label", "layer", "fetched_at", "data_last_edit", "server_count", "written")},
            "fill": {"source": FILL_SOURCE, "path": str(args.fill), "units": len(ugeoms), "fill_polys": sum(ufill)},
            "counts": dict(n), "rows": len(out_rows), "seconds": round(time.time() - t0, 1),
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (outp / "fd5_meta.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return meta


# --- join -----------------------------------------------------------------------


def join_rows(base: list[dict[str, Any]], base_keys: list[str], cols: dict[str, dict[str, Any]],
              basement: dict[str, str] | None = None) -> tuple[list[str], list[dict[str, Any]]]:
    """``base`` with every fd5 column replaced from ``cols`` (by TLID), the
    base columns kept in their order and the fd5 columns after them. The
    ``basement`` column keeps its name and reads "not held" where the
    assessor's field is not held (it read blank in pass 1)."""
    keys = [k for k in base_keys if k not in FD5_COLS] + list(FD5_COLS)
    out = []
    for r in base:
        got = cols.get(r["TLID"], {})
        new = {k: r.get(k) for k in keys if k not in FD5_COLS}
        new.update({k: got.get(k) for k in FD5_COLS})
        if not new.get("basement"):
            new["basement"] = BASEMENT_NOT_HELD
        out.append(new)
    return keys, out


def join(lot_csv: Path, cols_csv: Path, out_csv: Path) -> dict[str, Any]:
    with open(lot_csv, newline="", encoding="utf-8") as fh:
        rd = csv.DictReader(fh)
        base_keys = list(rd.fieldnames or [])
        base = list(rd)
    with open(cols_csv, newline="", encoding="utf-8") as fh:
        cols = {r["TLID"]: r for r in csv.DictReader(fh)}
    keys, out = join_rows(base, base_keys, cols)
    missing = sum(1 for r in base if r["TLID"] not in cols)
    tmp = out_csv.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(out)
    tmp.replace(out_csv)
    return {"rows": len(out), "columns": len(keys), "without_fd5": missing}


# --- refresh-frost --------------------------------------------------------------

#: Places the register now reads silent on Steph's whole-code word search, with
#: the ruling that says so (flats/config/rulings.yaml): their figure is the
#: county/state one, and the note says how it was reached.
SILENT_BY_SEARCH = {
    "or/clackamas/oregon-city": "2026-11-18-frost-silent-oregon-city",
    "or/washington/sherwood": "2026-11-18-frost-silent-sherwood",
}
SILENT_WORDS = "city code silent on a whole-code word search; county/state figure"
FROST_COLS = ("frost_register_in", "frost_register_level", "frost_register_note", "frost_hub_in",
              "frost_state_in", "frost_state_basis", "frost_register_outcome", "frost_register_kind",
              "frost_register_below_ft", "frost_register_reference_in", "frost_register_cite",
              "frost_disagree", "frost_above_stated_band")


def _cellstr(v: Any) -> str:
    return "" if v is None else str(v)


def frost_row(r: dict[str, Any], note: dict[str, Any] | None) -> dict[str, str]:
    """The frost columns of one lot from the register's ``note`` for its
    place (:func:`flats.frost.describe`), as the lot file holds them."""
    from flats.ingest import fd2

    got = fd2.frost(note, r.get("county"), fd2._num(r.get("ground_mean_ft")), fd2._num(r.get("frost_hub_in")))
    ruling = SILENT_BY_SEARCH.get(str(r.get("layer_id") or ""))
    if ruling and (note or {}).get("outcome") == "silent":
        lead = f"{SILENT_WORDS} (ruling {ruling})"
        got["frost_register_note"] = " | ".join(x for x in (lead, got.get("frost_register_note")) if x)
    return {k: _cellstr(got.get(k)) for k in FROST_COLS}


def refresh_frost(lot_csv: Path, out_csv: Path) -> dict[str, Any]:
    """Re-read every lot's frost columns from the live register (flats/frost.py);
    every other column is kept as it is. Returns the changed lots by place."""
    from flats import frost as register

    with open(lot_csv, newline="", encoding="utf-8") as fh:
        rd = csv.DictReader(fh)
        keys = list(rd.fieldnames or [])
        recs = list(rd)
    notes: dict[tuple[str, str], Any] = {}
    changed: Counter = Counter()
    for r in recs:
        key = (r.get("layer_id") or "", (r.get("county") or "").lower())
        if key not in notes:
            notes[key] = register.describe(key[0] or None, key[1] or None)
        new = frost_row(r, notes[key])
        if any(new[k] != (r.get(k) or "") for k in FROST_COLS):
            changed[r.get("layer_id")] += 1
        r.update(new)
    tmp = out_csv.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(recs)
    tmp.replace(out_csv)
    return {"rows": len(recs), "changed": dict(changed)}


# --- dwellings reasons from the static SSURGO tabular file ----------------------

#: The column order of SSURGO's ``cointerp.csv`` (the CONUS tabular package),
#: for rows read without their header line.
COINTERP_COLS = ("cokey", "mrulekey", "mrulename", "seqnum", "rulekey", "rulename", "ruledepth",
                 "interphr", "interphrc", "nullpropdatabool", "defpropdatabool", "incpropdatabool",
                 "cointerpkey")
DWELLINGS = "ENG - Dwellings W/O Basements"


def static_reasons(rows: Any, cokeys: set[str]) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    """From ``cointerp`` rows (dicts keyed by :data:`COINTERP_COLS`) return,
    for the wanted components, the reasons text -- the ruledepth-1 rules of
    "dwellings without basements" with a value above 0, highest first, as
    pass 1 wrote them ("name (0.xx)") -- and the overall (ruledepth 0) rating
    and value, for checking against the lot file's ``dwellings_rating``."""
    found: dict[str, list[tuple[float, str]]] = defaultdict(list)
    overall: dict[str, tuple[str, str]] = {}
    for row in rows:
        k = str(row.get("cokey") or "").strip()
        if k not in cokeys or row.get("mrulename") != DWELLINGS:
            continue
        depth = str(row.get("ruledepth") or "").strip()
        if depth == "0":
            overall[k] = (str(row.get("interphrc") or "").strip(), str(row.get("interphr") or "").strip())
        elif depth == "1":
            try:
                v = float(row.get("interphr") or "")
            except ValueError:
                continue
            name = str(row.get("rulename") or "").strip()
            if v > 0 and name:
                found[k].append((v, name))
    words = {k: "; ".join(f"{n} ({v:.2f})" for v, n in sorted(vn, key=lambda x: (-x[0], x[1])))
             for k, vn in found.items()}
    return words, overall


def fill_reasons_static(lot_csv: Path, rows_csv: Path, out_csv: Path) -> dict[str, Any]:
    """Fill ``dwellings_reasons`` by each lot's ``cokey`` from ``rows_csv``
    (``cointerp.csv`` lines, header or not); every other column is kept.
    Returns the counts and every component's file rating beside the lot file's."""
    with open(lot_csv, newline="", encoding="utf-8") as fh:
        rd = csv.DictReader(fh)
        keys = list(rd.fieldnames or [])
        recs = list(rd)
    cokeys = {r["cokey"].strip() for r in recs if (r.get("cokey") or "").strip()}
    with open(rows_csv, newline="", encoding="utf-8-sig") as fh:
        # The CONUS package is comma-separated; a Web Soil Survey area zip's
        # tabular/cointerp.txt is pipe-separated. Both keep this column order.
        delim = "|" if "|" in fh.readline() else ","
        fh.seek(0)
        rows = (dict(zip(COINTERP_COLS, line, strict=False)) for line in csv.reader(fh, delimiter=delim))
        words, overall = static_reasons(rows, cokeys)
    filled = 0
    agree: Counter = Counter()
    pairs: dict[str, tuple[str, str]] = {}
    for r in recs:
        k = (r.get("cokey") or "").strip()
        if not k:
            continue
        r["dwellings_reasons"] = words.get(k, "")
        filled += bool(words.get(k))
        file_rating = overall.get(k, ("", ""))[0]
        pairs[k] = (file_rating, r.get("dwellings_rating") or "")
        agree["same" if file_rating == (r.get("dwellings_rating") or "") else "differ"] += 1
    tmp = out_csv.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(recs)
    tmp.replace(out_csv)
    return {"rows": len(recs), "components": len(cokeys), "components_with_reasons": len(words),
            "components_rated": len(overall), "lots_filled": filled, "rating_vs_lot_file": dict(agree),
            "pairs": pairs}


# --- summary --------------------------------------------------------------------

COUNTIES = ("clackamas", "multnomah", "washington")


def _cross(recs: list[dict[str, Any]], rk: Any, ck: Any, rorder: tuple[str, ...],
           corder: tuple[str, ...], title: str) -> str:
    c: dict[str, Counter] = defaultdict(Counter)
    for r in recs:
        c[rk(r)][ck(r)] += 1
    head = f"| {title} | " + " | ".join(corder) + " | total |\n|---|" + "---:|" * (len(corder) + 1) + "\n"
    body = ""
    for rv in rorder:
        if sum(c[rv].values()) == 0:
            continue
        body += f"| {rv} | " + " | ".join(str(c[rv][cv]) for cv in corder) + f" | {sum(c[rv].values())} |\n"
    tot = Counter()
    for rv in c:
        tot.update(c[rv])
    body += "| **total** | " + " | ".join(str(tot[cv]) for cv in corder) + f" | {sum(tot.values())} |\n"
    return head + body


def _basement(r: dict[str, Any]) -> str:
    v = str(r.get("basement") or "").strip().lower()
    return v if v in ("yes", "no") else "not held"


def _fill_word(r: dict[str, Any]) -> str:
    t = r.get("fill_touches")
    if t in (None, "", "None"):
        return "not mapped"
    return "touches fill" if str(t) == "True" else "no fill"


def summary(lot_csv: Path) -> str:
    from flats.ingest import fd5

    with open(lot_csv, newline="", encoding="utf-8") as fh:
        recs = list(csv.DictReader(fh))
    built = [r for r in recs if r.get("occupied") == "built"]
    parts = [f"Lots: {len(recs)}; built (occupancy label): {len(built)}.\n"]
    band = lambda r: r.get("bldg_overlap_band") or "not held"  # noqa: E731
    for name, rs in (("all green lots", recs), ("built lots", built)):
        parts.append(f"\n#### Overlap with an existing building, {name}\n\n")
        parts.append(_cross(rs, lambda r: r["county"], band, COUNTIES, fd5.OVERLAP_BANDS, "county"))
    for county in (*COUNTIES, None):
        rs = [r for r in recs if county is None or r["county"] == county]
        lab = county or "all counties"
        parts.append(f"\n#### {lab}: overlap x basement\n\n")
        parts.append(_cross(rs, band, _basement, fd5.OVERLAP_BANDS, ("yes", "no", "not held"), "overlap"))
        parts.append(f"\n#### {lab}: overlap x year built\n\n")
        parts.append(_cross(rs, band, lambda r: r.get("year_built_band") or "not held", fd5.OVERLAP_BANDS,
                            fd5.YEAR_BANDS, "overlap"))
    parts.append("\n#### Overlap x occupancy label\n\n")
    labels = ("vacant", "teardown", "house", "larger", "unclear", "")
    parts.append(_cross(recs, band, lambda r: r.get("occupancy_label") or "", fd5.OVERLAP_BANDS, labels, "overlap"))
    gaps = ("0-5", "5-10", "10-20", "20-40", "40+", "no building on lot")

    def gap_bin(r: dict[str, Any]) -> str:
        v = r.get("bldg_gap_ft")
        if v in (None, "", "None"):
            return "no building on lot"
        x = float(v)
        return "0-5" if x < 5 else "5-10" if x < 10 else "10-20" if x < 20 else "20-40" if x < 40 else "40+"
    clear = [r for r in recs if band(r) == "none"]
    parts.append("\n#### Distance from the footprint to the nearest building on the lot (ft), lots with no overlap\n\n")
    parts.append(_cross(clear, lambda r: r["county"], gap_bin, COUNTIES, gaps, "county"))
    parts.append("\n#### Mapped artificial fill (DOGAMI O-12-02 unit Aaf) under the footprint\n\n")
    fw = ("touches fill", "no fill", "not mapped")
    parts.append(_cross(recs, lambda r: r["county"], _fill_word, COUNTIES, fw, "county"))
    flat = [r for r in recs if r.get("flat_bldg_overlap_band")]
    if flat:
        parts.append("\n#### Stage B flattest position: overlap with an existing building, live band x flat band\n\n")
        parts.append(_cross(flat, band, lambda r: r["flat_bldg_overlap_band"], fd5.OVERLAP_BANDS,
                            fd5.OVERLAP_BANDS, "live \\ flat"))
        parts.append("\n#### Stage B flattest position: mapped fill\n\n")
        parts.append(_cross(flat, lambda r: r["county"], lambda r: _fill_word({"fill_touches": r.get("flat_fill_touches")}),
                            COUNTIES, fw, "county"))

    def fill_bin(r: dict[str, Any]) -> str:
        s = float(r.get("fill_share") or 0)
        return "under 25%" if s < 0.25 else "25-50%" if s < 0.5 else "50-99%" if s < 0.999 else "whole footprint"
    touched = [r for r in recs if _fill_word(r) == "touches fill"]
    parts.append("\n#### Share of the footprint on mapped fill, lots touching it\n\n")
    parts.append(_cross(touched, lambda r: r["county"], fill_bin, COUNTIES,
                        ("under 25%", "25-50%", "50-99%", "whole footprint"), "county"))
    liq = sorted({r.get("liq_majority") or "not mapped" for r in recs},
                 key=lambda s: (s == "not mapped", s))
    parts.append("\n#### Liquefaction, majority (largest-share) class under the footprint (O-19-09)\n\n")
    parts.append(_cross(recs, lambda r: r.get("liq_majority") or "not mapped", lambda r: r["county"],
                        tuple(liq), COUNTIES, "liq_majority"))
    parts.append("\n#### Liquefaction, majority class x worst class touching\n\n")
    worst = sorted({r.get("liq_class") or "not mapped" for r in recs}, key=lambda s: (s == "not mapped", s))
    parts.append(_cross(recs, lambda r: r.get("liq_majority") or "not mapped",
                        lambda r: r.get("liq_class") or "not mapped", tuple(liq), tuple(worst), "majority \\ worst"))
    turn = ("0-10", "10-45", "45-80", "80-90", "not known")

    def turn_bin(r: dict[str, Any]) -> str:
        v = r.get("front_face_turn_deg")
        if v in (None, "", "None"):
            return "not known"
        x = float(v)
        return "0-10" if x <= 10 else "10-45" if x <= 45 else "45-80" if x <= 80 else "80-90"
    parts.append("\n#### Street-side 80 ft face: turn from the nearest street line (degrees) x fit orientation\n\n")
    parts.append(_cross(recs, lambda r: r.get("fit_orientation") or "", turn_bin,
                        ("width_facing", "depth_facing", ""), turn, "orientation"))
    return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--assign", required=True)
    e.add_argument("--quadfit", required=True)
    e.add_argument("--out", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--csv", required=True)
    m.add_argument("--extract", required=True)
    m.add_argument("--footprints", required=True)
    m.add_argument("--fill", required=True)
    m.add_argument("--out", required=True)
    j = sub.add_parser("join")
    j.add_argument("--csv", required=True)
    j.add_argument("--cols", required=True)
    j.add_argument("--out", required=True)
    rf = sub.add_parser("refresh-frost")
    rf.add_argument("--csv", required=True)
    rf.add_argument("--out", required=True)
    fr = sub.add_parser("fill-reasons-static")
    fr.add_argument("--csv", required=True)
    fr.add_argument("--rows", required=True, help="cointerp.csv lines (the dwellings rule's rows)")
    fr.add_argument("--out", required=True)
    s = sub.add_parser("summary")
    s.add_argument("--csv", required=True)
    s.add_argument("--out", required=True)
    a = p.parse_args(argv)
    if a.cmd == "extract":
        print(json.dumps(extract(Path(a.assign), Path(a.quadfit), Path(a.out))))
    elif a.cmd == "measure":
        print(json.dumps(measure(a), default=str)[:2000])
    elif a.cmd == "join":
        print(json.dumps(join(Path(a.csv), Path(a.cols), Path(a.out))))
    elif a.cmd == "refresh-frost":
        print(json.dumps(refresh_frost(Path(a.csv), Path(a.out))))
    elif a.cmd == "fill-reasons-static":
        got = fill_reasons_static(Path(a.csv), Path(a.rows), Path(a.out))
        got.pop("pairs")
        print(json.dumps(got))
    else:
        Path(a.out).write_text(summary(Path(a.csv)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
