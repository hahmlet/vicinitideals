"""The refusal ledger, and why a count is the assertion worth making.

A refusal is a reading -- somebody opened the code, understood a standard and
decided it does not reach this building. Nothing can check that automatically
and nothing here tries. What can be checked is that the set is *known*: that
adding a refusal is a deliberate act with a number attached, rather than a
sentence of prose in a notes field that no ledger will ever revisit.

The motivating case is pinned at the bottom. A test docstring declared Table
4.0430's setback rows unreadable and therefore unencodable; four of the seven
columns were encoded from those exact lines afterwards, by somebody who had
never seen the refusal, and it sat there reading like a live constraint. That
is what an uncounted decision looks like weeks later.
"""

from __future__ import annotations

import pytest

from flats.encode.refusals import FLOOR, Refusal, _spans, refusals
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit

#: Per source, as of 2026-08-21. These numbers are meant to move -- what they
#: are not meant to do is move quietly. A refusal added without a line here is
#: a reading nobody signed off on; a refusal removed without one is a reading
#: somebody overturned without saying so.
EXPECTED = {"notes": 90, "comments": 24, "tests": 16}
#: Two of the sixteen are this file, which quotes the marker while
#: explaining it, and one is a back-reference in test_gresham_rockwood --
#: prose saying a zone *was* not encoded until it was. Left in rather than
#: special-cased, both of them: a ledger that skips one file because the file
#: is inconvenient is a ledger with an exception nobody remembers, and a
#: ledger that tries to tell a refusal from a reference to one is parsing
#: prose, which this module states plainly that it does not do.
#:
#: The two added on 2026-08-22 are test_lake_oswego_commercial_notes, and they
#: are the shape this ledger exists for: the NC zone is readable, it carries
#: 88 of the 93 lots that jurisdiction reports as zone_missing, and it is
#: deliberately not encoded until LOC 50.03.003.2 is fetched. A decision that
#: size should cost a line here.


def test_the_corpus_declares_more_refusals_than_any_ledger_counts() -> None:
    rows = refusals()
    counts = {kind: sum(1 for r in rows if r.kind == kind) for kind in EXPECTED}

    assert counts == EXPECTED
    assert len(rows) == sum(EXPECTED.values())


def test_every_layer_that_refuses_is_named() -> None:
    """Fifteen of the seventeen layers carry at least one, which is the real
    finding: this is not a corner case, it is how the corpus records judgement.
    The two that carry none are the state layer, which holds no zones, and the
    one jurisdiction encoded from a single table."""
    where = {r.where for r in refusals() if r.kind in ("notes", "comments")}
    layers = set(load_rules())

    assert where <= layers | {"or/_state"}
    assert len(where) >= 14


def test_a_refusal_folded_across_a_yaml_line_ending_is_still_found() -> None:
    """Read from the model, not the file. A folded block scalar breaks long
    prose at whatever column it likes, so "not\\nencoded" appears in the file
    and "not encoded" appears in the loaded string. Scanning the file would
    silently under-report, and under-reporting is the one direction this
    subsystem never takes."""
    assert list(_spans("something is not\n   encoded here for a reason")) == [
        "not encoded here for a reason"
    ]


def test_the_window_does_not_stop_at_a_header() -> None:
    """Half the corpus writes "NOT ENCODED, on purpose. (1) ..." and cutting at
    the nearest full stop would report the header and drop the refusal, which
    is a ledger that costs a file-open per row."""
    text = "NOT ENCODED, on purpose. (1) " + "the actual reason goes here. " * 6
    span = next(iter(_spans(text)))

    assert span.startswith("NOT ENCODED, on purpose. (1) the actual reason")
    assert len(span) > FLOOR


def test_a_refusal_carries_where_it_was_found() -> None:
    row = next(r for r in refusals() if r.zone)

    assert row.label == f"{row.where}:{row.zone}"
    assert Refusal("notes", "or/x", None, "t").label == "or/x"


def test_one_layer_can_be_asked_on_its_own() -> None:
    """Test docstrings are dropped when a layer is named, because they belong
    to no layer. Worth stating: the per-layer view is deliberately narrower
    than a filter of the whole."""
    rows = refusals("or/multnomah/gresham")

    assert {r.where for r in rows} == {"or/multnomah/gresham"}
    assert not [r for r in rows if r.kind == "tests"]


def test_the_refusal_that_prompted_this_module_is_gone() -> None:
    """Table 4.0430 was declared unreadable and then read.

    The refusal said its cells "wrap across a dozen lines each and the
    extraction shifts fragments between columns; the setback rows in particular
    cannot be assigned to a district by reading the text." That was true of the
    commercial half of those cells and never true of the Residential sub-cell,
    which RTC, SC and SC-RJ share and which reads identically in all three.

    Nothing detected the contradiction. Four columns were encoded from those
    lines while the sentence still stood."""
    stale = [r for r in refusals() if "guess wearing a citation" in r.text]

    assert stale == []
    gresham = load_rules()["or/multnomah/gresham"]
    for zone in ("RTC", "SC", "SC-RJ", "CMF", "CMU", "CC", "MC"):
        assert "setback_front_ft" in gresham.zones[zone].values, zone
