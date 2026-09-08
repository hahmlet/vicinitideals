"""One document in the corpus lost cells on the way in. Only one.

:mod:`flats.encode.ragged` counts, per stored document, how many of its
use-table rows are shorter than that document's own widest row. A dropped cell
does not merely lose a prohibition -- it shifts every cell after it, so a
permission read off such a table can silently be the neighbouring zone's.

The corpus separates cleanly: Lake Oswego's ``LOC 50.03.002`` at 64 percent,
and every other document at zero. That is not a threshold anybody tuned, it is
what the numbers do, and it is the reason this can be a test rather than a
report. It fails in both directions on purpose. A second ragged document means
something was fetched that nothing may be encoded from until it is re-fetched.
Lake Oswego falling to zero means the re-fetch worked and ten ``column``
rulings in :mod:`flats.tests.test_districts` are owed a re-read.
"""

from __future__ import annotations

from flats.encode.ragged import scan

#: The one document known to have lost cells, and roughly how badly. Lake
#: Oswego's own preamble says "a blank cell in a use table indicates that the
#: land use is prohibited", and the blanks are gone: ``Cemetery`` arrives as
#: one cell and ``Residential use at R-5 density or greater`` as eleven,
#: against sixteen column heads. 93 observed lots carry a Lake Oswego zone this
#: table is the only permission for.
KNOWN_RAGGED = "or/clackamas/lake-oswego/50.03.002.use-table.txt"


def test_exactly_one_document_lost_cells() -> None:
    ragged = [d.name for d in scan() if d.ragged > 0]
    assert ragged == [KNOWN_RAGGED], (
        "a use table whose rows are not all the same width is a table nothing "
        "may be encoded from -- a dropped cell shifts every cell after it. "
        f"Ragged now: {ragged}"
    )


def test_the_known_one_is_still_badly_ragged() -> None:
    """If this falls, the re-fetch landed and the `column` rulings are owed a look."""
    worst = next(d for d in scan() if d.name == KNOWN_RAGGED)
    assert worst.ragged > 0.5, (
        f"{KNOWN_RAGGED} is now only {worst.ragged:.0%} ragged; if it has been "
        "re-fetched, re-read the ten Lake Oswego 'column' rulings in "
        "test_districts.py, which exist only because this table is unreadable."
    )


def test_the_tables_we_do_encode_from_are_whole() -> None:
    """The one that would actually have cost us a wrong number.

    ``quadplex_allowed`` for the nine Clackamas County districts is read off
    Table 315-1 in ZDO 315, whose Quadplexes row is eleven cells wide against
    eleven column heads. Every row in that document is eleven or seven -- the
    widths of Tables 315-1 and 315-4 -- and none is short.
    """
    zdo = next(
        d for d in scan() if d.name.endswith("_unincorporated/zdo.315.txt")
    )
    assert zdo.short == 0, sorted(set(zdo.runs))
    assert set(zdo.runs) <= {7, 11}, sorted(set(zdo.runs))
