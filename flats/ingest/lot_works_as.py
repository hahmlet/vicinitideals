"""Fill ``flats.lot_works_as``: whether each result is green as an apartment / as townhomes.

The Lots page's "Works as" filter used to group every result of a run and read
two colours out of each ``checks`` JSON per request (10-14 s on production, past
the page's clock; FOLLOWUPS 121). The answer is worked out once per run here:
one row per result the screen recorded a ``forms`` entry on. A colour the screen
left out is stored NULL, which the old JSON grouping also treated as matching no choice. A result without a
``forms`` entry gets no row, so a lot nothing measured matches no choice.

The loader calls :func:`refresh` right after ``lot_prices`` and
``scripts/flats_backfill_works_as.py`` fills runs loaded earlier.
"""

from __future__ import annotations

from typing import Any

#: Replaces a run's rows. Parameter: $1 the run id.
DELETE_SQL = "DELETE FROM flats.lot_works_as WHERE run_id = $1"

#: One set-based statement for a run. Parameter: $1 the run id.
FILL_SQL = """
    INSERT INTO flats.lot_works_as (run_id, lot_id, design_key, apartment_green, townhomes_green)
    SELECT r.run_id, r.lot_id, r.design_key,
           (r.checks #>> '{forms,apartment,colour}') = 'green',
           (r.checks #>> '{forms,townhomes,colour}') = 'green'
    FROM flats.lot_results r
    WHERE r.run_id = $1 AND r.checks ? 'forms'
"""


async def refresh(conn: Any, run_id: int) -> int:
    """Replace the run's rows. ``conn`` is an asyncpg connection inside a
    transaction. Returns the number of rows written."""
    await conn.execute(DELETE_SQL, run_id)
    status = await conn.execute(FILL_SQL, run_id)
    return int(status.rsplit(" ", 1)[-1])
