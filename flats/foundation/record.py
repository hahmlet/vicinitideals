"""One lot's measured record as a single JSON document (FD6 build step 10).

The MEASURE layer's tables (:mod:`flats.foundation.rows`: the lot row, its wall
lines and doors, the old buildings under the pod and their stretches) folded
into one document per lot, so the app can keep a lot's whole record in one
JSONB column and the record can grow without a migration. Nothing priced is
ever stored: the lot report prices the document at read time with the current
settings (:mod:`flats.foundation.report`).

* :func:`document` / :func:`measured_of` -- record <-> document;
* :func:`staleness` -- why a stored record can no longer be priced under the
  current settings (its geometric settings or its record layout changed), or
  None when it can;
* :func:`settings_version` -- the hash stamped on every priced output;
* :func:`ring_hash` / :func:`drawing_changed` -- the drawn building a record was
  measured under, against the lot's drawing now (slice 4).

Pure: no database, no web.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from flats.foundation import rows
from flats.foundation import settings as settings_mod
from flats.foundation.measure import Measured, geometry_of
from flats.foundation.settings import Settings

#: The layout of the stored document; bump it when :func:`document` changes shape.
RECORD_VERSION = 2
#: The model that measured the record (FD6 build steps 1-9, slice 2 of FOLLOWUPS
#: 209; FD8 sections 2b and 2d, FOLLOWUPS 213: the real doors on the face the
#: door-face rule names, their out-lines and guard boxes, the steep ground).
MODEL_VERSION = "fd8"

#: What a record's lot row says it was measured on.
MEASURED_ON = ("drawing", "ground_source", "cell_m", "measured_at")
#: ... and the footprint it was measured on, in words (from its geometry; slice 4).
MEASURED_ON_FOOTPRINT = "footprint"
#: Added by the slice-4 routine (absent on the slice-3 records): the run whose
#: drawing was measured, a hash of the drawn building ring, and the ring itself
#: (EPSG:2913 ft, to 0.01 ft) so the read side can tell a moved drawing.
MEASURED_ON_DRAWING = ("run", "drawing_hash", "drawn_ring")
#: A vertex of the drawing now may sit this far (ft) from the measured one and
#: still be the same drawing (stored rings are rounded on the way to the app).
SAME_RING_FT = 0.15
#: The geometric settings that ARE the building footprint: a record measured
#: under others was measured on a different footprint (``measured_on.footprint``
#: names the one it was).
FOOTPRINT_KEYS = frozenset({"finished_length_ft", "finished_width_ft", "length_ft", "width_ft", "party_x_ft",
                            "door_x_ft", "door_x_front_ft", "door_x_back_ft"})


def _plain(geometry: Mapping[str, Any]) -> dict[str, Any]:
    return {k: list(v) if isinstance(v, tuple) else v for k, v in geometry.items()}


def footprint_words(geometry: Mapping[str, Any]) -> str:
    """The footprint a record was measured on, in words, from its geometric
    settings: the framing inches inside the finished box, or (a record from
    before the framing size, slice 3) the finished size alone."""
    length, width = float(geometry["length_ft"]), float(geometry["width_ft"])
    box = (geometry.get("finished_length_ft"), geometry.get("finished_width_ft"))
    if None in box:
        return f"{length:g} x {width:g} ft (the finished faces)"
    return (f"framing {_inches(length)} x {_inches(width)} in, centred in the "
            f"{float(box[0]):g} x {float(box[1]):g} ft finished faces")


def _inches(ft: float) -> str:
    return f"{ft * 12:.4f}".rstrip("0").rstrip(".")


def geometry_hash(geometry: Mapping[str, Any]) -> str:
    """A short stable hash of a set of geometric settings."""
    text = json.dumps(_plain(geometry), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def settings_hash(s: Settings) -> str:
    """The hash of the geometric settings a record must have been measured under."""
    return geometry_hash(dict(geometry_of(s)))


def settings_version(path: Path = settings_mod.PATH) -> str:
    """The first 12 hex of the settings file's sha256: stamped on every priced output."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def plain_ring(ring: Sequence[Sequence[float]]) -> list[list[float]]:
    """A drawn ring as stored: [x, y] pairs to 0.01 ft."""
    return [[round(float(p[0]), 2), round(float(p[1]), 2)] for p in ring]


def ring_hash(ring: Sequence[Sequence[float]]) -> str:
    """A short hash of a drawn building ring, to 0.1 ft (stable across the
    rounding a ring meets on its way into the app)."""
    text = json.dumps([[round(float(p[0]), 1), round(float(p[1]), 1)] for p in ring], separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def drawing_changed(doc: Mapping[str, Any], ring: Sequence[Sequence[float]] | None) -> bool | None:
    """Whether the lot's drawn building now (``ring``) is not the one the record
    was measured under: None when either side does not hold a ring (a slice-3
    record, or a report without the drawing), else True / False. Same ring =
    the same number of vertices, each within :data:`SAME_RING_FT`."""
    on = doc.get("measured_on") or {}
    have = on.get("drawn_ring")
    if not have or not ring:
        return None
    if on.get("drawing_hash") and on["drawing_hash"] == ring_hash(ring):
        return False
    if len(have) != len(ring):
        return True
    return any(math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1])) > SAME_RING_FT
               for a, b in zip(have, ring, strict=True))


def _child(r: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in r.items() if k != "tlid"}


def document(
    m: Measured,
    *,
    drawing: str,
    measured_at: str,
    run: str | None = None,
    ring: Sequence[Sequence[float]] | None = None,
) -> dict[str, Any]:
    """The whole measured record of one lot, as JSON-ready plain data. ``run``
    and ``ring`` (the drawn building measured) stamp the drawing it was
    measured on, for :func:`drawing_changed`."""
    lot, lines, doors = rows.measured_rows(m)
    bldgs, stretches = rows.old_building_rows(m)
    on: dict[str, Any] = {
        "drawing": drawing,
        "ground_source": m.ground_source,
        "cell_m": m.cell_m,
        "measured_at": measured_at,
        "footprint": footprint_words(dict(m.geometry)),
    }
    if run is not None:
        on["run"] = run
    if ring:
        on["drawing_hash"] = ring_hash(ring)
        on["drawn_ring"] = plain_ring(ring)
    return {
        "record_version": RECORD_VERSION,
        "model_version": MODEL_VERSION,
        "measured_on": on,
        "geometry_hash": geometry_hash(dict(m.geometry)),
        "lot": lot,
        "lines": [_child(r) for r in lines],
        "doors": [_child(r) for r in doors],
        "buildings": [_child(r) for r in bldgs],
        "stretches": [_child(r) for r in stretches],
    }


def measured_of(doc: Mapping[str, Any]) -> Measured:
    """The record back from its document (the inverse of :func:`document`)."""
    if doc.get("record_version") != RECORD_VERSION:
        raise ValueError(f"record layout {doc.get('record_version')!r}, this code reads {RECORD_VERSION}: re-measure")
    return rows.from_measured_rows(
        dict(doc["lot"]),
        [dict(r) for r in doc["lines"]],
        [dict(r) for r in doc["doors"]],
        [dict(r) for r in doc.get("buildings") or []],
        [dict(r) for r in doc.get("stretches") or []],
    )


def staleness(doc: Mapping[str, Any], s: Settings) -> tuple[str, ...] | None:
    """Why the stored record cannot be priced under ``s``: the names of the
    geometric settings that changed (or ``record_version``), or None when it can."""
    if doc.get("record_version") != RECORD_VERSION:
        return ("record_version",)
    try:
        have = json.loads(doc["lot"]["geometry"])
    except (KeyError, TypeError, ValueError):
        return ("geometry",)
    want = _plain(dict(geometry_of(s)))
    changed = tuple(sorted(k for k in have.keys() | want.keys() if have.get(k) != want.get(k)))
    return changed or None


# ---------------------------------------------------------------- flat tables


#: The measured tables, as Parquet (one directory or one file per table).
TABLES = ("lots", "lines", "doors", "buildings", "stretches")
#: Columns a bundle's lot row carries beside the measured lot row.
LOT_EXTRA = ("drawing", "measured_at", "model_version", "record_version")
#: ... and, on a slice-4 bundle, the drawing it was measured on (``drawn_ring`` as JSON text).
LOT_EXTRA_DRAWING = ("run", "drawing_hash", "drawn_ring")


def table_rows(doc: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """One document as rows of the five flat tables (children keyed county + tlid)."""
    lot = dict(doc["lot"])
    key = {"county": lot["county"], "tlid": lot["tlid"]}
    on = doc.get("measured_on") or {}
    lot.update(drawing=on.get("drawing"), measured_at=on.get("measured_at"),
               model_version=doc.get("model_version"), record_version=doc.get("record_version"))
    for k in LOT_EXTRA_DRAWING:
        if on.get(k) is not None:
            lot[k] = json.dumps(on[k]) if k == "drawn_ring" else on[k]
    out: dict[str, list[dict[str, Any]]] = {"lots": [lot]}
    for name in TABLES[1:]:
        out[name] = [{**key, **r} for r in doc.get(name) or []]
    return out


def documents_from_tables(tables: Mapping[str, Iterable[Mapping[str, Any]]]) -> Iterator[dict[str, Any]]:
    """The documents back from the five flat tables, in the lot table's order."""
    kids: dict[str, dict[tuple[Any, str], list[dict[str, Any]]]] = {}
    for name in TABLES[1:]:
        by: dict[tuple[Any, str], list[dict[str, Any]]] = defaultdict(list)
        for r in tables.get(name) or ():
            row = dict(r)
            k = (row.pop("county", None), row.pop("tlid"))
            by[k].append(row)
        kids[name] = by
    for r in tables["lots"]:
        lot = dict(r)
        extra = {k: lot.pop(k, None) for k in LOT_EXTRA}
        drawn = {k: lot.pop(k, None) for k in LOT_EXTRA_DRAWING}
        k = (lot.get("county"), lot["tlid"])
        geometry = json.loads(lot["geometry"])
        on = {
            "drawing": extra["drawing"],
            "ground_source": lot.get("ground_source"),
            "cell_m": lot.get("cell_m"),
            "measured_at": extra["measured_at"],
            "footprint": footprint_words(geometry),
        }
        for name, v in drawn.items():
            if v is not None:
                on[name] = json.loads(v) if name == "drawn_ring" else v
        yield {
            "record_version": extra["record_version"],
            "model_version": extra["model_version"],
            "measured_on": on,
            "geometry_hash": geometry_hash(geometry),
            "lot": lot,
            **{name: kids[name].get(k) or kids[name].get((None, lot["tlid"])) or [] for name in TABLES[1:]},
        }


def _parts(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("*.parquet"))
    return [path] if path.exists() else []


def read_tables(path: Path) -> dict[str, list[dict[str, Any]]]:
    """The five measured tables from a directory holding ``lots/``, ``lines/`` ...
    (Parquet parts) or ``lots.parquet``, ``lines.parquet`` ... (needs pyarrow)."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = Path(path)
    out: dict[str, list[dict[str, Any]]] = {}
    for name in TABLES:
        parts = _parts(path / name) or _parts(path / f"{name}.parquet")
        if not parts and name == "lots":
            raise FileNotFoundError(f"no lots table under {path}")
        out[name] = (
            pa.concat_tables([pq.read_table(p) for p in parts], promote_options="default").to_pylist() if parts else []
        )
    return out


def write_jsonl(path: Path, docs: Iterable[Mapping[str, Any]]) -> int:
    """One document per line, gzipped: what the app loader reads (no pyarrow there)."""
    n = 0
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as fh:
        for doc in docs:
            fh.write(json.dumps(doc, separators=(",", ":"), allow_nan=False))
            fh.write("\n")
            n += 1
    return n


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)
