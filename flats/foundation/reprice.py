"""Bulk what-if pricing from the measured tables (FD6 build step 10).

    uv run python -m flats.foundation reprice --measured <dir or records.jsonl.gz>
        [--settings other.yaml] [--out priced.parquet | priced.csv]

Reads the measured records where they lie (the Parquet tables a bundle writes,
or its ``records.jsonl.gz``), prices every one under the settings given, and
writes ONE flat table, one row per lot: what it was measured on, the settings
version, whether it could be priced, and every assessed column
(:func:`flats.foundation.rows.assessed_rows`: style, cheaper method and by how
much, each method's costs, challenges, easy parts, flags, and the old-building
conditional and weighted figures, which are never part of a method's cost).
A record measured under other geometric settings gets a row saying
``needs_remeasuring`` and no prices. Never touches a database or LXC 137.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from flats.foundation import lot as lots_mod
from flats.foundation import record, report, rows
from flats.foundation import settings as settings_mod
from flats.foundation.settings import Settings


def documents(path: Path) -> Iterator[dict[str, Any]]:
    """Measured documents from a bundle directory (Parquet tables) or a ``.jsonl.gz``."""
    path = Path(path)
    if path.is_file() and path.name.endswith(".jsonl.gz"):
        yield from record.read_jsonl(path)
        return
    yield from record.documents_from_tables(record.read_tables(path))


def priced_row(doc: Mapping[str, Any], s: Settings, version: str) -> dict[str, Any]:
    """One flat row for one lot under ``s``."""
    on = doc.get("measured_on") or {}
    lot = doc.get("lot") or {}
    row: dict[str, Any] = {
        "county": lot.get("county"),
        "tlid": lot.get("tlid"),
        "settings_version": version,
        "drawing": on.get("drawing"),
        "ground_source": on.get("ground_source"),
        "cell_m": on.get("cell_m"),
        "measured_at": on.get("measured_at"),
        "model_version": doc.get("model_version"),
    }
    stale = record.staleness(doc, s)
    if stale:
        row.update(status=report.NEEDS_REMEASURING, remeasure_because=";".join(stale))
        return row
    res = lots_mod.assess(record.measured_of(doc), s)
    row.update(status=report.PRICED, remeasure_because="")
    assessed, _, _ = rows.assessed_rows(res)
    assessed.pop("tlid", None)
    row.update(assessed)
    return row


def reprice(docs: Iterable[Mapping[str, Any]], s: Settings, version: str) -> list[dict[str, Any]]:
    return [priced_row(d, s, version) for d in docs]


def write(out: Path, table: list[dict[str, Any]]) -> None:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix == ".csv":
        cols = list(dict.fromkeys(k for r in table for k in r))
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(table)
        return
    import pyarrow as pa
    import pyarrow.parquet as pq

    cols = list(dict.fromkeys(k for r in table for k in r))
    pq.write_table(pa.Table.from_pylist([{c: r.get(c) for c in cols} for r in table]), out, compression="zstd")


def main(measured: Path, settings_path: Path | None, out: Path | None) -> dict[str, Any]:
    path = Path(settings_path) if settings_path else settings_mod.PATH
    s = settings_mod.load(path)
    version = record.settings_version(path)
    table = reprice(documents(measured), s, version)
    out = Path(out) if out else Path("foundation_priced.parquet")
    write(out, table)
    counts: dict[str, int] = {}
    for r in table:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"lots": len(table), "status": counts, "settings": str(path), "settings_version": version, "out": str(out)}
