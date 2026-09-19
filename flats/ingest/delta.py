"""The delta: what every lot did between two copies of the county map.

Steph's third condition on keeping the screen's copy of the county map in
the database (HUMAN_TODO 20, 2026-09-19) was a method for delta correction:
lots combine, lots split, and updated information (assessments) has to be
adopted. This module reads two snapshots' taxlot files and says, lot by lot,
which of eight things happened:

* ``attr_change`` -- same ground, attributes differ. Adopted as-is; nothing
  is re-measured.
* ``reshape``     -- same TLID, boundary adjusted (or moved without a clean
  lineage). Re-measured.
* ``split``       -- one old lot's ground is now under two or more lots. The
  parent sometimes keeps its TLID and shrinks, sometimes is renumbered.
* ``merge``       -- one new lot's ground was under two or more old lots,
  or an old lot lies almost wholly inside a neighbour that grew over it.
* ``renumbered``  -- the same ground, one lot, a new TLID.
* ``added``       -- in the new copy with no ground in the old one (a plat
  on former right-of-way, or a unit stacked on an unchanged lot).
* ``deleted``     -- in the old copy only, its ground now under lots that
  did not change enough to be its heir (a street pseudo-lot, a neighbour
  that grew by a sliver) or scattered under several.
* ``vacated``     -- in the old copy only, its ground under no lot at all.

Lineage is read from **geometry overlap**, not from the TLID. Metro's
2026_08 change list showed why: of the 654 lots added that quarter in our
two counties, only 340 shared a section-quarter with any deleted lot -- in
the other 314 the parent kept its number and shrank. The TLID naming
(``-02500`` -> ``-02501``) and Metro's own ADDED / DELETED / CHANGE list
are corroboration, and :func:`crosscheck` grades our diff against the list
so the report can say how far the two accounts agree.

Nothing here touches the database. :mod:`scripts.flats_load_bridge`
``load-changes`` reads the CSV this writes into ``flats.lot_changes``.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

import numpy as np
import shapely
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

#: RLIS ``COUNTY`` letters, as ``flats.lots.county`` spells them.
COUNTY_NAMES = {"M": "multnomah", "C": "clackamas", "W": "washington"}
#: The first two digits of ``ORTAXLOT`` in Metro's change list.
ORTAXLOT_COUNTIES = {"03": "clackamas", "26": "multnomah", "34": "washington"}
DEFAULT_COUNTIES = ("multnomah", "clackamas")

#: Coordinates are compared at a hundredth of a foot: the county's exports
#: wobble in the eighth decimal, which is not a boundary moving.
PRECISION_FT = 0.01
#: The same ground, allowing for that wobble and a re-ordered ring.
SAME_GROUND_IOU = 0.999
#: A boundary adjustment rather than a lineage event: overlap this high and
#: area moved less than the tolerance.
RESHAPE_IOU = 0.95
RESHAPE_AREA_TOLERANCE = 0.02
#: An overlap counts once it is this big AND this share of the smaller lot;
#: below that it is a survey sliver.
OVERLAP_MIN_SQFT = 50.0
OVERLAP_MIN_SHARE = 0.05
#: One old lot covering this share of a new lot is its parent.
PARENT_SHARE = 0.80
#: Two or more old lots each covering this share of a new lot make it a merge.
MERGE_SHARE = 0.20
#: An old lot lying this far inside one new lot was absorbed by it -- a merge
#: however small the old lot was next to the survivor.
ABSORBED_SHARE = 0.95

KINDS = ("attr_change", "reshape", "split", "merge", "renumbered", "added", "deleted", "vacated")
#: Kinds after which a review decision on the lot was made about different ground.
REREVIEW_KINDS = frozenset({"split", "merge", "renumbered", "deleted", "vacated"})

Key = tuple[str, str]


# --- lots ------------------------------------------------------------------


@dataclass
class Lot:
    county: str
    tlid: str
    geom: BaseGeometry | None
    props: dict[str, Any]
    area: float
    geom_hash: str | None
    attr_hash: str

    @property
    def key(self) -> Key:
        return (self.county, self.tlid)


def _norm(value: Any) -> Any:
    """One spelling for a value whichever export it came from."""
    if value is None:
        return None
    if isinstance(value, float):
        if value != value:  # NaN
            return None
        return int(value) if value.is_integer() else value
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return value


def _geom_hash(geom: BaseGeometry) -> str:
    rounded = shapely.transform(shapely.normalize(geom), lambda c: np.round(c, 2))
    return hashlib.sha1(shapely.to_wkb(rounded)).hexdigest()


def _attr_hash(props: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(props, sort_keys=True, default=str).encode()).hexdigest()


def iter_features(path: Path) -> Iterator[dict[str, Any]]:
    """Every feature of a GeoJSON FeatureCollection, one at a time.

    The files are half a gigabyte each; parsing them whole would hold every
    coordinate as a Python float twice over. This walks the ``features``
    array with the decoder's ``raw_decode`` so only one feature is a dict at
    a time (the text itself is still read into memory).
    """
    text = path.read_text(encoding="utf-8")
    start = text.find('"features"')
    if start < 0:
        raise ValueError(f"{path}: not a FeatureCollection")
    idx = text.index("[", start) + 1
    decoder = json.JSONDecoder()
    n = len(text)
    while True:
        while idx < n and text[idx] in " \t\r\n,":
            idx += 1
        if idx >= n or text[idx] == "]":
            return
        feature, idx = decoder.raw_decode(text, idx)
        yield feature


def load_lots(
    path: Path,
    *,
    counties: Iterable[str] = DEFAULT_COUNTIES,
    fields: Iterable[str] | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[Key, Lot]:
    """The lots of one snapshot's taxlot file, keyed ``(county, tlid)``.

    Duplicate keys (the file carries a lot twice) keep the first and are
    logged; ``fields`` limits the attributes compared, otherwise every
    property is.
    """
    wanted = set(counties)
    keep = set(fields) if fields is not None else None
    lots: dict[Key, Lot] = {}
    dupes = 0
    started = time.monotonic()
    for i, feature in enumerate(iter_features(path)):
        props = feature.get("properties") or {}
        county = COUNTY_NAMES.get(str(props.get("COUNTY") or "").strip().upper(), str(props.get("COUNTY") or "").strip().lower())
        if county not in wanted:
            continue
        tlid = str(props.get("TLID") or "").rstrip()
        if not tlid:
            continue
        key = (county, tlid)
        if key in lots:
            dupes += 1
            continue
        raw = feature.get("geometry")
        geom: BaseGeometry | None = None
        if raw:
            try:
                geom = shape(raw)
                if not geom.is_valid:
                    geom = shapely.make_valid(geom)
            except Exception:  # degenerate county shapes are attribute-only lots
                geom = None
        attrs = {k: _norm(v) for k, v in props.items() if (keep is None or k in keep) and k not in ("TLID", "COUNTY")}
        lots[key] = Lot(
            county=county,
            tlid=tlid,
            geom=geom,
            props=attrs,
            area=float(geom.area) if geom is not None else 0.0,
            geom_hash=_geom_hash(geom) if geom is not None else None,
            attr_hash=_attr_hash(attrs),
        )
        if log and i and i % 100_000 == 0:
            log(f"  {path.name}: {i:,} features read, {len(lots):,} kept, {time.monotonic() - started:.0f}s")
    if log:
        log(f"{path.name}: {len(lots):,} lots in {sorted(wanted)}; {dupes:,} duplicate keys dropped; {time.monotonic() - started:.0f}s")
    return lots


# --- the classification ----------------------------------------------------


@dataclass
class Change:
    county: str
    tlid: str
    kind: str
    role: str | None = None
    related_tlids: list[str] = field(default_factory=list)
    area_before: float | None = None
    area_after: float | None = None
    iou: float | None = None
    attr_diff: dict[str, list[Any]] = field(default_factory=dict)
    rlis_change: str | None = None
    note: str = ""

    @property
    def key(self) -> Key:
        return (self.county, self.tlid)

    def as_row(self) -> dict[str, Any]:
        return {
            "county": self.county,
            "tlid": self.tlid,
            "kind": self.kind,
            "role": self.role or "",
            "related_tlids": "|".join(self.related_tlids),
            "area_before": "" if self.area_before is None else f"{self.area_before:.2f}",
            "area_after": "" if self.area_after is None else f"{self.area_after:.2f}",
            "iou": "" if self.iou is None else f"{self.iou:.4f}",
            "attr_diff": json.dumps(self.attr_diff, sort_keys=True, default=str) if self.attr_diff else "",
            "rlis_change": self.rlis_change or "",
            "note": self.note,
        }


@dataclass
class Delta:
    """Every change between two copies, plus the sets the cross-check needs."""

    changes: list[Change]
    prev_count: int
    new_count: int
    unchanged: int
    only_prev: set[Key]
    only_new: set[Key]
    seconds: float = 0.0

    def by_kind(self) -> dict[str, int]:
        return dict(sorted(Counter(c.kind for c in self.changes).items()))

    def by_kind_and_county(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = defaultdict(dict)
        for (county, kind), n in sorted(Counter((c.county, c.kind) for c in self.changes).items()):
            out[county][kind] = n
        return dict(out)


def _attr_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[Any]]:
    keys = set(before) | set(after)
    return {k: [before.get(k), after.get(k)] for k in sorted(keys) if before.get(k) != after.get(k)}


def _pair_iou(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """IoU and relative area move for aligned geometry arrays (vectorised)."""
    inter = shapely.area(shapely.intersection(a, b))
    area_a = shapely.area(a)
    area_b = shapely.area(b)
    union = area_a + area_b - inter
    with np.errstate(divide="ignore", invalid="ignore"):
        iou = np.where(union > 0, inter / union, 1.0)
        moved = np.where(area_a > 0, np.abs(area_b - area_a) / area_a, np.where(area_b > 0, 1.0, 0.0))
    return iou, moved


def _overlaps(
    geom: BaseGeometry, tree: STRtree, pool: list[Lot], *, exclude: Key | None = None
) -> list[tuple[Lot, float]]:
    """Lots in ``pool`` sharing ground with ``geom``: (lot, overlap area)."""
    if geom is None or geom.is_empty:
        return []
    found: list[tuple[Lot, float]] = []
    for i in tree.query(geom, predicate="intersects"):
        other = pool[int(i)]
        if other.key == exclude or other.geom is None:
            continue
        inter = float(geom.intersection(other.geom).area)
        smaller = min(geom.area, other.area) or 1.0
        if inter >= OVERLAP_MIN_SQFT and inter / smaller >= OVERLAP_MIN_SHARE:
            found.append((other, inter))
    found.sort(key=lambda t: -t[1])
    return found


def classify(prev: dict[Key, Lot], new: dict[Key, Lot], *, log: Callable[[str], None] | None = None) -> Delta:
    """Every lot's change between ``prev`` and ``new``; unchanged lots are counted, not listed."""
    started = time.monotonic()
    say = log or (lambda _s: None)
    both = sorted(set(prev) & set(new))
    only_prev = set(prev) - set(new)
    only_new = set(new) - set(prev)
    say(f"keys: {len(both):,} in both, {len(only_prev):,} only before, {len(only_new):,} only after")

    changes: list[Change] = []
    unchanged = 0
    #: Lots keyed in both copies whose ground moved beyond a reshape.
    moved: set[Key] = set()
    iou_of: dict[Key, float] = {}

    # 1. Same key: same ground, a reshape, or moved. The hash settles most;
    #    the vectorised IoU settles the rest (ring order, precision wobble).
    same_hash = [k for k in both if prev[k].geom_hash == new[k].geom_hash]
    to_measure = [k for k in both if prev[k].geom_hash != new[k].geom_hash and prev[k].geom is not None and new[k].geom is not None]
    lost_shape = [k for k in both if prev[k].geom_hash != new[k].geom_hash and (prev[k].geom is None or new[k].geom is None)]
    say(f"same ground by hash: {len(same_hash):,}; measuring {len(to_measure):,}; {len(lost_shape):,} with a shape on one side only")
    same_ground: set[Key] = set(same_hash)
    reshaped: set[Key] = set()
    if to_measure:
        a = np.array([prev[k].geom for k in to_measure], dtype=object)
        b = np.array([new[k].geom for k in to_measure], dtype=object)
        iou, area_moved = _pair_iou(a, b)
        for k, i, m in zip(to_measure, iou, area_moved, strict=True):
            iou_of[k] = float(i)
            if i >= SAME_GROUND_IOU:
                same_ground.add(k)
            elif i >= RESHAPE_IOU and m < RESHAPE_AREA_TOLERANCE:
                reshaped.add(k)
            else:
                moved.add(k)
    for k in lost_shape:
        reshaped.add(k)
        iou_of[k] = 0.0
    say(f"same ground: {len(same_ground):,}; reshaped: {len(reshaped):,}; moved: {len(moved):,}")

    for k in both:
        p, n = prev[k], new[k]
        diff = _attr_diff(p.props, n.props) if p.attr_hash != n.attr_hash else {}
        if k in same_ground:
            if diff:
                changes.append(Change(k[0], k[1], "attr_change", area_before=p.area, area_after=n.area, iou=iou_of.get(k, 1.0), attr_diff=diff))
            else:
                unchanged += 1
        elif k in reshaped:
            note = "shape on one side only" if k in lost_shape else ""
            changes.append(Change(k[0], k[1], "reshape", area_before=p.area, area_after=n.area, iou=iou_of[k], attr_diff=diff, note=note))
        # moved lots are settled by lineage below

    # 2. Lineage, from the new side: which old lots' ground is each new or
    #    moved lot standing on? Unchanged old lots are not candidates -- a
    #    unit stacked on an unchanged footprint (condos) is not its child.
    pool_prev = [prev[k] for k in sorted(only_prev | moved) if prev[k].geom is not None]
    tree_prev = STRtree([lot.geom for lot in pool_prev]) if pool_prev else None
    parent_of: dict[Key, Key] = {}
    merge_parents: dict[Key, list[Key]] = {}
    overlaps_new: dict[Key, list[tuple[Key, float]]] = {}
    for k in sorted(only_new | moved):
        n = new[k]
        found = _overlaps(n.geom, tree_prev, pool_prev) if tree_prev is not None else []
        shares = [
            (lot, inter / n.area if n.area else 0.0, inter / lot.area if lot.area else 0.0) for lot, inter in found
        ]
        overlaps_new[k] = [(lot.key, s) for lot, s, _ in shares]
        dominant = shares[0][0].key if shares and shares[0][1] >= PARENT_SHARE else None
        # Old lots lying almost wholly inside this one were absorbed by it: a
        # merge, even when the survivor dwarfs them (a 1,800 sq ft remnant
        # folded into a 26,000 sq ft neighbour is what Metro lists as one
        # DELETED and one CHANGE).
        absorbed = [lot.key for lot, _, of_lot in shares if of_lot >= ABSORBED_SHARE and lot.key != dominant]
        if dominant is not None and not absorbed:
            parent_of[k] = dominant
        elif dominant is not None:
            merge_parents[k] = [dominant] + absorbed
        else:
            big = [lot.key for lot, s, _ in shares if s >= MERGE_SHARE]
            parents = big + [a for a in absorbed if a not in big]
            if len(parents) >= 2:
                merge_parents[k] = parents

    # 3. From the old side: what became of each old or moved lot.
    children: dict[Key, list[Key]] = defaultdict(list)
    for child, parent in parent_of.items():
        children[parent].append(child)
    merged_into: dict[Key, list[Key]] = defaultdict(list)
    for survivor, parents in merge_parents.items():
        for parent in parents:
            merged_into[parent].append(survivor)

    pool_new = [new[k] for k in sorted(new) if new[k].geom is not None]
    tree_new = STRtree([lot.geom for lot in pool_new]) if pool_new else None
    settled_new: set[Key] = set()

    def diff_for(k: Key) -> dict[str, list[Any]]:
        if k in prev and k in new and prev[k].attr_hash != new[k].attr_hash:
            return _attr_diff(prev[k].props, new[k].props)
        return {}

    for k in sorted(only_prev | moved):
        p = prev[k]
        kids = sorted(children.get(k, []))
        survivors = sorted(merged_into.get(k, []))
        heirs = kids + [s for s in survivors if s not in kids]
        if len(heirs) >= 2:
            # A split: the parent's ground is under two or more lots now. If
            # one of them carries the parent's TLID, the parent kept its
            # number and shrank -- one row, role parent.
            kept = k in new and k in heirs
            related = [h[1] for h in heirs if h != k]
            changes.append(
                Change(
                    k[0], k[1], "split", role="parent", related_tlids=related,
                    area_before=p.area, area_after=new[k].area if kept else None,
                    iou=iou_of.get(k) if kept else None, attr_diff=diff_for(k) if kept else {},
                    note="kept its TLID" if kept else "",
                )
            )
            if kept:
                settled_new.add(k)
            for h in kids:
                if h == k:
                    continue
                changes.append(Change(h[0], h[1], "split", role="child", related_tlids=[k[1]], area_after=new[h].area, attr_diff=diff_for(h)))
                settled_new.add(h)
            continue
        if len(kids) == 1:
            h = kids[0]
            if h == k:
                # The same lot, its boundary moved more than a reshape allows,
                # and nothing else stands on its old ground: a big reshape.
                changes.append(Change(k[0], k[1], "reshape", area_before=p.area, area_after=new[k].area, iou=iou_of.get(k), attr_diff=diff_for(k), note="boundary moved"))
            else:
                changes.append(Change(k[0], k[1], "renumbered", role="parent", related_tlids=[h[1]], area_before=p.area, note="" if k not in new else "TLID reused elsewhere"))
                changes.append(Change(h[0], h[1], "renumbered", role="child", related_tlids=[k[1]], area_after=new[h].area, attr_diff=_attr_diff(p.props, new[h].props)))
            settled_new.add(h)
            continue
        if survivors:
            s = survivors[0]
            if s == k:
                continue  # the survivor kept this TLID; its row is written below
            changes.append(Change(k[0], k[1], "merge", role="parent", related_tlids=[s[1]], area_before=p.area))
            continue
        # No heir at all.
        if k in new:
            changes.append(
                Change(
                    k[0], k[1], "reshape", area_before=p.area, area_after=new[k].area, iou=iou_of.get(k),
                    attr_diff=diff_for(k), note="boundary moved; " + _overlap_note(overlaps_new.get(k, []), exclude=k),
                )
            )
            settled_new.add(k)
            continue
        under = _overlaps(p.geom, tree_new, pool_new) if tree_new is not None else []
        if under:
            changes.append(
                Change(
                    k[0], k[1], "deleted", related_tlids=[lot.tlid for lot, _ in under[:10]], area_before=p.area,
                    note=_overlap_note([(lot.key, inter / p.area if p.area else 0.0) for lot, inter in under]),
                )
            )
        else:
            changes.append(Change(k[0], k[1], "vacated", area_before=p.area))

    # 4. The new side: merge survivors, and lots with no lineage at all.
    for k in sorted(only_new | moved):
        if k in settled_new:
            continue
        n = new[k]
        if k in merge_parents:
            parents = [pk[1] for pk in merge_parents[k] if pk != k]
            changes.append(
                Change(
                    k[0], k[1], "merge", role="survivor", related_tlids=parents,
                    area_before=prev[k].area if k in prev else None, area_after=n.area,
                    iou=iou_of.get(k), attr_diff=diff_for(k), note="kept its TLID" if k in prev else "",
                )
            )
        elif k in parent_of:
            continue  # written from the old side
        elif k in prev:
            continue  # a moved lot already written as reshape from the old side
        else:
            note = _overlap_note(overlaps_new.get(k, []))
            changes.append(Change(k[0], k[1], "added", area_after=n.area, note=note))

    changes.sort(key=lambda c: (c.county, c.tlid, c.kind, c.role or ""))
    return Delta(
        changes=changes,
        prev_count=len(prev),
        new_count=len(new),
        unchanged=unchanged,
        only_prev=only_prev,
        only_new=only_new,
        seconds=round(time.monotonic() - started, 1),
    )


def _overlap_note(shares: list[tuple[Key, float]], *, exclude: Key | None = None) -> str:
    parts = [f"{k[1]} ({s:.0%})" for k, s in shares[:5] if k != exclude]
    return "partial overlap with " + ", ".join(parts) if parts else ""


# --- the cross-check against Metro's list ----------------------------------


def read_change_log(path: Path) -> list[dict[str, Any]]:
    """Metro's ``taxlot_change`` rows as the acquire stage wrote them (no shapes)."""
    return [f.get("properties") or {} for f in iter_features(path)]


def crosscheck(delta: Delta, log_rows: Iterable[dict[str, Any]], *, counties: Iterable[str] = DEFAULT_COUNTIES) -> dict[str, Any]:
    """Our added / gone lots against Metro's ADDED / DELETED, per county.

    Recall is the share of Metro's list we also found; precision the share
    of ours that Metro lists. Neither is expected at 100 % -- the two
    accounts cover different windows -- but a recall under 80 % on either
    side is the warning the plan names.
    """
    wanted = set(counties)
    theirs: dict[str, dict[str, set[str]]] = {c: {"ADDED": set(), "DELETED": set(), "CHANGE": set()} for c in wanted}
    unknown = 0
    for row in log_rows:
        county = ORTAXLOT_COUNTIES.get(str(row.get("ORTAXLOT") or "")[:2])
        change = str(row.get("ADDCHANGE") or "").strip().upper()
        tlid = str(row.get("TLID") or "").rstrip()
        if county not in wanted or not tlid:
            continue
        if change not in theirs[county]:
            unknown += 1
            continue
        theirs[county][change].add(tlid)
    listed = {(c, t): ch for c, buckets in theirs.items() for ch, tlids in buckets.items() for t in tlids}
    for change in delta.changes:
        change.rlis_change = listed.get(change.key)

    ours_added: dict[str, set[str]] = defaultdict(set)
    ours_gone: dict[str, set[str]] = defaultdict(set)
    for county, tlid in delta.only_new:
        ours_added[county].add(tlid)
    for county, tlid in delta.only_prev:
        ours_gone[county].add(tlid)

    def grade(ours: set[str], metro: set[str]) -> dict[str, Any]:
        both = ours & metro
        return {
            "ours": len(ours),
            "metro": len(metro),
            "both": len(both),
            "recall": round(len(both) / len(metro), 3) if metro else None,
            "precision": round(len(both) / len(ours), 3) if ours else None,
            "metro_only": sorted(metro - ours)[:20],
            "ours_only": sorted(ours - metro)[:20],
        }

    out: dict[str, Any] = {"counties": {}, "unknown_rows": unknown}
    for county in sorted(wanted):
        out["counties"][county] = {
            "added": grade(ours_added[county], theirs[county]["ADDED"]),
            "deleted": grade(ours_gone[county], theirs[county]["DELETED"]),
            "changed_listed": len(theirs[county]["CHANGE"]),
        }
    recalls = [
        g[side]["recall"]
        for g in out["counties"].values()
        for side in ("added", "deleted")
        if g[side]["recall"] is not None
    ]
    out["min_recall"] = min(recalls) if recalls else None
    out["agrees"] = bool(recalls) and min(recalls) >= 0.8
    return out


# --- the summary and the report --------------------------------------------


def summarize(delta: Delta, check: dict[str, Any] | None, *, prev_label: str, new_label: str) -> dict[str, Any]:
    fields = Counter(f for c in delta.changes for f in c.attr_diff)
    return {
        "from": prev_label,
        "to": new_label,
        "lots_before": delta.prev_count,
        "lots_after": delta.new_count,
        "unchanged": delta.unchanged,
        "by_kind": delta.by_kind(),
        "by_county": delta.by_kind_and_county(),
        "rows": len(delta.changes),
        "rereview": sum(1 for c in delta.changes if c.kind in REREVIEW_KINDS),
        "fields_changed": dict(fields.most_common(20)),
        "crosscheck": check,
        "seconds": delta.seconds,
    }


def _address(lot: Lot | None) -> str:
    if lot is None:
        return ""
    return str(lot.props.get("SITEADDR") or "").strip()


def report(
    delta: Delta,
    check: dict[str, Any] | None,
    *,
    prev_label: str,
    new_label: str,
    prev: dict[Key, Lot] | None = None,
    new: dict[Key, Lot] | None = None,
    examples: int = 10,
) -> str:
    """The one page Steph reads: counts, the cross-check, ten examples per kind."""
    kinds = delta.by_kind()
    by_county = delta.by_kind_and_county()
    lines = [
        f"# County map delta: {prev_label} -> {new_label}",
        "",
        f"{delta.prev_count:,} lots before, {delta.new_count:,} after; {delta.unchanged:,} unchanged "
        f"in ground and attributes; {len(delta.changes):,} change rows.",
        "",
        "## What happened, by kind",
        "",
        "| kind | " + " | ".join(sorted(by_county)) + " | total |",
        "|---|" + "---|" * (len(by_county) + 1),
    ]
    for kind in KINDS:
        if kind not in kinds:
            continue
        cells = [str(by_county[c].get(kind, 0)) for c in sorted(by_county)]
        lines.append(f"| {kind} | " + " | ".join(cells) + f" | {kinds[kind]} |")
    lines += [
        "",
        f"Rows that put a review decision in doubt (split, merge, renumbered, deleted, vacated): "
        f"{sum(1 for c in delta.changes if c.kind in REREVIEW_KINDS):,}.",
        "",
    ]
    fields = Counter(f for c in delta.changes for f in c.attr_diff)
    if fields:
        lines += ["## Attributes that changed most", ""]
        lines += [f"- {name}: {n:,} lots" for name, n in fields.most_common(12)]
        lines.append("")
    if check:
        lines += [
            "## Against Metro's own change list",
            "",
            "Recall = the share of Metro's list our diff also found; precision = the share of ours Metro lists. "
            "The two accounts cover different windows, so neither is expected at 100 %; under 80 % recall is the warning.",
            "",
            "| county | side | ours | Metro | both | recall | precision |",
            "|---|---|---|---|---|---|---|",
        ]
        for county, g in check["counties"].items():
            for side in ("added", "deleted"):
                s = g[side]
                rec = "-" if s["recall"] is None else f"{s['recall']:.0%}"
                pre = "-" if s["precision"] is None else f"{s['precision']:.0%}"
                lines.append(f"| {county} | {side} | {s['ours']:,} | {s['metro']:,} | {s['both']:,} | {rec} | {pre} |")
        verdict = "agree" if check["agrees"] else "DISAGREE -- a human reads this before anything is promoted"
        lines += ["", f"Verdict: the two accounts {verdict}.", ""]
    lines += ["## Examples", ""]
    for kind in KINDS:
        rows = [c for c in delta.changes if c.kind == kind]
        if not rows:
            continue
        lines.append(f"### {kind} ({len(rows):,})")
        lines.append("")
        for c in rows[:examples]:
            lot = (new or {}).get(c.key) or (prev or {}).get(c.key)
            bits = [f"{c.county} {c.tlid}"]
            if c.role:
                bits.append(c.role)
            if c.related_tlids:
                bits.append("with " + ", ".join(c.related_tlids[:6]))
            if c.area_before is not None and c.area_after is not None and round(c.area_before) != round(c.area_after):
                bits.append(f"{c.area_before:,.0f} -> {c.area_after:,.0f} sq ft")
            elif c.area_after is not None and c.area_before is not None:
                bits.append(f"{c.area_after:,.0f} sq ft")
            elif c.area_before is not None:
                bits.append(f"{c.area_before:,.0f} sq ft")
            elif c.area_after is not None:
                bits.append(f"{c.area_after:,.0f} sq ft")
            if c.attr_diff:
                shown = list(c.attr_diff.items())[:4]
                bits.append("; ".join(f"{k}: {a} -> {b}" for k, (a, b) in shown))
            if c.rlis_change:
                bits.append(f"Metro says {c.rlis_change}")
            if c.note:
                bits.append(c.note)
            addr = _address(lot)
            lines.append(f"- {' -- '.join(bits)}" + (f" ({addr})" if addr else ""))
        lines.append("")
    return "\n".join(lines)


# --- files -----------------------------------------------------------------

CSV_FIELDS = ["county", "tlid", "kind", "role", "related_tlids", "area_before", "area_after", "iou", "attr_diff", "rlis_change", "note"]


def write_changes(changes: Iterable[Change], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for change in changes:
            writer.writerow(change.as_row())
            n += 1
    return n


def read_changes(path: Path) -> Iterator[dict[str, Any]]:
    """Rows of a ``changes.csv.gz`` with the typed columns restored."""
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            yield {
                "county": row["county"],
                "tlid": row["tlid"],
                "kind": row["kind"],
                "role": row["role"] or None,
                "related_tlids": [t for t in row["related_tlids"].split("|") if t],
                "area_before": float(row["area_before"]) if row["area_before"] else None,
                "area_after": float(row["area_after"]) if row["area_after"] else None,
                "iou": float(row["iou"]) if row["iou"] else None,
                "attr_diff": json.loads(row["attr_diff"]) if row["attr_diff"] else {},
                "rlis_change": row["rlis_change"] or None,
                "note": row["note"],
            }


def run(
    prev_path: Path,
    new_path: Path,
    out_dir: Path,
    *,
    change_log: Path | None = None,
    counties: Iterable[str] = DEFAULT_COUNTIES,
    prev_label: str | None = None,
    new_label: str | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Load, classify, cross-check, write ``changes.csv.gz`` / ``summary.json`` / ``report.md``."""
    counties = tuple(counties)
    prev_label = prev_label or prev_path.parent.name
    new_label = new_label or new_path.parent.name
    prev = load_lots(prev_path, counties=counties, log=log)
    new = load_lots(new_path, counties=counties, log=log)
    delta = classify(prev, new, log=log)
    log(f"classified in {delta.seconds}s: {delta.by_kind()}")
    check = None
    if change_log is not None:
        check = crosscheck(delta, read_change_log(change_log), counties=counties)
        log(f"cross-check: min recall {check['min_recall']}, {'agree' if check['agrees'] else 'DISAGREE'}")
    out_dir.mkdir(parents=True, exist_ok=True)
    n = write_changes(delta.changes, out_dir / "changes.csv.gz")
    summary = summarize(delta, check, prev_label=prev_label, new_label=new_label)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "report.md").write_text(
        report(delta, check, prev_label=prev_label, new_label=new_label, prev=prev, new=new), encoding="utf-8"
    )
    log(f"wrote {n:,} rows to {out_dir}")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m flats.ingest.delta",
        description="What every lot did between two copies of the county map.",
    )
    ap.add_argument("--prev", type=Path, required=True, help="the copy in use: its taxlot GeoJSON")
    ap.add_argument("--new", type=Path, required=True, help="the refreshed copy: its taxlot GeoJSON")
    ap.add_argument("--change-log", type=Path, help="the snapshot's rlis_taxlot_change.geojson, to cross-check")
    ap.add_argument("--out", type=Path, required=True, help="directory for changes.csv.gz, summary.json, report.md")
    ap.add_argument("--counties", nargs="+", default=list(DEFAULT_COUNTIES))
    ap.add_argument("--from-label", help="how the report names the old copy (default: its directory)")
    ap.add_argument("--to-label", help="how the report names the new copy (default: its directory)")
    args = ap.parse_args(argv)
    summary = run(
        args.prev, args.new, args.out,
        change_log=args.change_log, counties=args.counties,
        prev_label=args.from_label, new_label=args.to_label,
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "crosscheck"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
