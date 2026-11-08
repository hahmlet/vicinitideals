"""Fill ``flats.lot_best``: one row per lot, with its best verdict/colour.

The Lots page used to group a run's full ``flats.lot_results`` set on every
request to find each lot's best result across designs. This table stores that
answer once per run, plus the list's filter/sort fields, so the page reads a
small per-lot table instead.

The loader calls :func:`refresh` after loading results, and
``scripts/flats_backfill_lot_best.py`` fills runs loaded earlier.
"""

from __future__ import annotations

from typing import Any

from app.models.flats import FLATS_COLOUR_ORDER

_ELSE_RANK = len(FLATS_COLOUR_ORDER)


def _rank_sql(value_sql: str) -> str:
    parts = [f"WHEN {value_sql} = '{colour}' THEN {rank}" for rank, colour in enumerate(FLATS_COLOUR_ORDER)]
    return "CASE " + " ".join(parts) + f" ELSE {_ELSE_RANK} END"


#: Replaces a run's rows. Parameter: $1 the run id.
DELETE_SQL = "DELETE FROM flats.lot_best WHERE run_id = $1"

_BEST_VERDICT_SQL = _rank_sql("r.tier")
_BEST_COLOUR_SQL = _rank_sql("COALESCE(r.checks->>'colour', r.checks->>'if_signed')")

#: One set-based statement for a run. Parameter: $1 the run id.
FILL_SQL = f"""
    INSERT INTO flats.lot_best (
        run_id, lot_id, jurisdiction, zone, tlid, site_address, best_verdict, best_colour
    )
    SELECT
        r.run_id,
        r.lot_id,
        l.jurisdiction,
        l.zone,
        l.tlid,
        l.site_address,
        MIN({_BEST_VERDICT_SQL}) AS best_verdict,
        MIN({_BEST_COLOUR_SQL}) AS best_colour
    FROM flats.lot_results r
    JOIN flats.lots l ON l.id = r.lot_id
    WHERE r.run_id = $1
    GROUP BY r.run_id, r.lot_id, l.jurisdiction, l.zone, l.tlid, l.site_address
"""


async def refresh(conn: Any, run_id: int) -> int:
    """Replace the run's rows. ``conn`` is an asyncpg connection inside a
    transaction. Returns the number of rows written."""
    await conn.execute(DELETE_SQL, run_id)
    status = await conn.execute(FILL_SQL, run_id)
    return int(status.rsplit(" ", 1)[-1])
