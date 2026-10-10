"""Fill ``flats.lot_prices``: each lot's price inputs as plain numbers.

The Lots page filters and sorts on price per home across the whole county
copy. Reading the price out of each lot's JSON and matching its zone against
a few hundred rules on every request hung production (2026-10-10), so the
slow inputs are worked out once, here, and stored one narrow row per lot:

* the price (the first positive source in :data:`flats.score.price.PRICE_SOURCES`),
  with the name of the source and its as-of date;
* the lot's area, copied beside it so the page never has to read the wide lot row;
* the zone's two density limits (homes per acre, smallest townhouse lot).

Pods, homes and price per home then stay plain arithmetic on these numbers, so
the pod size and the road share remain adjustable per request.

The loader calls :func:`refresh` after it writes a bundle's lots, and
``scripts/flats_backfill_lot_prices.py`` fills a copy that was loaded earlier.
A paid price feed slots in by adding a :class:`~flats.score.price.PriceSource`
ahead of the county roll; nothing here changes.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from flats.encode.load import load_trusted
from flats.rules.resolver import RuleSet
from flats.score.price import PRICE_SOURCES, PriceSource, ZoneCap, zone_caps

#: A number as the facts spell it: digits with an optional fraction.
_NUMBER = r"^[0-9]+(\.[0-9]+)?$"


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _path(path: Sequence[str]) -> str:
    return _quote("{" + ",".join(path) + "}")


def current_caps() -> dict[tuple[str, str], ZoneCap]:
    """Every (layer, zone) that states a density ceiling, read the way the Lots
    page reads it (trusted rules, the screen's own resolver)."""
    layers = load_trusted(strict=False).layers
    return zone_caps(RuleSet(layers), layers)


def county_as_of(rlis_release: str | None, snapshot_date: Any) -> str:
    """The as-of a county-roll price carries: the RLIS release and the copy's date."""
    release = f"RLIS {rlis_release} release, " if rlis_release else ""
    return f"{release}county copy of {snapshot_date.isoformat()}"


def fill_sql(sources: Sequence[PriceSource] = PRICE_SOURCES, *, only_run: bool = False) -> str:
    """The upsert for one snapshot's lots. Parameters: $1 snapshot id, $2 the
    county copy's as-of text, and (with ``only_run``) $3 the run whose lots to
    refresh. Reads the zone limits from ``tmp_zone_caps``."""
    lateral = ", ".join(
        f"CASE WHEN (l.facts #>> {_path(s.amount_path)}) ~ {_quote(_NUMBER)} "
        f"THEN (l.facts #>> {_path(s.amount_path)})::numeric END AS a{i}"
        for i, s in enumerate(sources)
    )
    amount = "CASE " + " ".join(f"WHEN a.a{i} > 0 THEN a.a{i}" for i in range(len(sources))) + " END"
    source = "CASE " + " ".join(f"WHEN a.a{i} > 0 THEN {_quote(s.name)}" for i, s in enumerate(sources)) + " END"
    as_of = "CASE " + " ".join(
        f"WHEN a.a{i} > 0 THEN "
        + (f"COALESCE(l.facts #>> {_path(s.as_of_path)}, $2::text)" if s.as_of_path else "$2::text")
        for i, s in enumerate(sources)
    ) + " END"
    scope = "AND l.updated_run_id = $3::bigint" if only_run else ""
    return f"""
        INSERT INTO flats.lot_prices
            (lot_id, snapshot_id, amount, source, as_of, area_sqft, cap_du_per_acre, cap_unit_lot_sqft)
        SELECT l.id, l.snapshot_id, {amount}, {source}, {as_of}, l.area_sqft, c.du_per_acre, c.unit_lot_sqft
        FROM flats.lots l
        CROSS JOIN LATERAL (SELECT {lateral}) a
        LEFT JOIN tmp_zone_caps c
          ON c.layer = COALESCE(
                 CASE WHEN jsonb_typeof(l.facts -> 'snapshot_zone') = 'object'
                      THEN l.facts -> 'snapshot_zone' ->> 'of' END,
                 l.jurisdiction)
         AND c.zone = l.zone
        WHERE l.snapshot_id = $1 {scope}
        ON CONFLICT (lot_id) DO UPDATE SET
            snapshot_id = EXCLUDED.snapshot_id,
            amount = EXCLUDED.amount,
            source = EXCLUDED.source,
            as_of = EXCLUDED.as_of,
            area_sqft = EXCLUDED.area_sqft,
            cap_du_per_acre = EXCLUDED.cap_du_per_acre,
            cap_unit_lot_sqft = EXCLUDED.cap_unit_lot_sqft
    """


async def refresh(
    conn: Any,
    snapshot_id: int,
    caps: Mapping[tuple[str, str], ZoneCap],
    *,
    run_id: int | None = None,
    sources: Sequence[PriceSource] = PRICE_SOURCES,
) -> int:
    """Write the price row of every lot in the snapshot (or, with ``run_id``,
    only the lots that run just wrote). ``conn`` is an asyncpg connection inside
    a transaction. Returns the number of rows written."""
    snap = await conn.fetchrow(
        "SELECT snapshot_date, rlis_release FROM flats.snapshots WHERE id = $1", snapshot_id
    )
    if snap is None:
        raise SystemExit(f"no flats.snapshots row {snapshot_id}")
    as_of = county_as_of(snap["rlis_release"], snap["snapshot_date"])
    await conn.execute("DROP TABLE IF EXISTS pg_temp.tmp_zone_caps")
    await conn.execute(
        "CREATE TEMP TABLE tmp_zone_caps (layer text, zone text, du_per_acre numeric, unit_lot_sqft numeric) "
        "ON COMMIT DROP"
    )
    await conn.executemany(
        "INSERT INTO tmp_zone_caps VALUES ($1, $2, $3, $4)",
        [(layer, zone, cap.du_per_acre, cap.unit_lot_sqft) for (layer, zone), cap in caps.items()],
    )
    sql = fill_sql(sources, only_run=run_id is not None)
    args: list[Any] = [snapshot_id, as_of] + ([run_id] if run_id is not None else [])
    status = await conn.execute(sql, *args)
    return int(status.rsplit(" ", 1)[-1])
