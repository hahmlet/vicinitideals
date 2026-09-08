"""The reach ledger: which encoded standards can move a verdict.

The load-bearing test here is :func:`test_the_silently_unread_set_is_the_one_
we_signed_up_for`. Everything else checks the reading is honest.
"""

from __future__ import annotations

import textwrap

import pytest

from flats.encode.consumed import Reach, reach, readers_by_field, render
from flats.rules.fields import FIELDS

#: Every field the corpus encodes that no scoring module names, as of
#: 2026-09-08. This is not a wish list -- it is the record of what a reviewer's
#: care currently buys nothing, and it exists so that *adding* to it is a
#: deliberate act rather than a side effect. Two ways to make this test pass
#: when it fails, and they are not equivalent: teach a screen to read the
#: field, or write the field down here having decided it can wait.
#:
#: Four fields left this set on 2026-09-08, two by each route. `paper.court_depth`
#: now reads `parking_stall_depth_ft` and `parking_aisle_two_way_ft` to size the
#: rear court, so the "stalls are laid out by a stage that does not exist yet"
#: excuse no longer covers the two that set the court's *depth*. The other two --
#: `setback_garage_entrance_ft` and `parking_aisle_one_way_ft` -- are now
#: *declared* in `PaperFit.excluded` on a ruling: the pod has no garage and its
#: court is two-way. Declared is not the same as read, and that is the point --
#: a reason on the record can be argued with, and a silence cannot.
#:
#: What is left of the parking-geometry block (widths, driveways, maneuvering)
#: is still the honest kind: those numbers size the court *across*, and nothing
#: measures a lot that way yet. `open_space_min_sqft` is the other kind -- it
#: already holds numbers the 2026-09-07 blind reading found misquoted, and
#: nobody noticed because nothing reads it.
SILENTLY_UNREAD = frozenset(
    {
        "min_lot_depth_ft",
        "parking_street_setback_ft",
        "setback_front_max_ft",
        "parking_max_per_unit",
        "open_space_min_sqft",
        "parking_stall_width_ft",
        "driveway_approach_max_width_ft",
        "min_building_separation_ft",
        "parking_front_prohibited",
        "driveway_approach_min_width_ft",
        "driveway_min_width_two_way_ft",
        "parking_maneuvering_max_width_ft",
        "driveway_min_width_one_way_ft",
        "parking_area_max_frontage_pct",
        "max_lot_depth_ratio",
        "max_building_width_ft",
        "parking_front_yard_max_pct",
        "parking_area_max_width_ft",
        "parking_building_buffer_ft",
    }
)


@pytest.fixture(scope="module")
def rows() -> list[Reach]:
    return reach()


def test_the_silently_unread_set_is_the_one_we_signed_up_for(rows):
    got = {r.field for r in rows if r.silent and r.stated}
    assert got == SILENTLY_UNREAD, (
        "the set of encoded-but-unread standards moved. Newly unread: "
        f"{sorted(got - SILENTLY_UNREAD)}; newly read: "
        f"{sorted(SILENTLY_UNREAD - got)}"
    )


def test_every_field_is_read_declared_or_silent_and_only_one(rows):
    for r in rows:
        assert sum((r.reached, bool(r.declared) and not r.reached, r.silent)) == 1


def test_the_registry_and_the_report_hold_the_same_fields(rows):
    assert {r.field for r in rows} == set(FIELDS)


def test_street_side_setback_is_excluded_on_the_record_not_forgotten(rows):
    """95 values across 15 jurisdictions, and `paper.py` says why in the fit."""
    row = next(r for r in rows if r.field == "setback_street_side_ft")
    assert not row.reached
    assert not row.silent
    assert "flats/score/paper.py" in row.declared


def test_the_parking_minimum_is_read_and_the_maximum_is_not(rows):
    """The asymmetry the footnote re-read turned up, pinned.

    Milwaukie caps middle housing at 0.5 spaces per unit on an arterial. That
    is tighter than the 1.0 we hold, and it cannot produce a wrong answer
    today for the single reason that nothing asks for the ceiling.
    """
    by = {r.field: r for r in rows}
    assert by["parking_min_per_unit"].reached
    assert not by["parking_max_per_unit"].reached


def test_a_field_stated_nowhere_carries_no_weight(rows):
    for r in rows:
        assert r.values == len(r.stated)
        assert r.layers <= r.values


def test_reading_finds_a_literal_wherever_it_is_written(tmp_path):
    root = tmp_path
    (root / "flats" / "score").mkdir(parents=True)
    (root / "flats" / "score" / "fake.py").write_text(
        textwrap.dedent(
            '''
            """A docstring naming max_far counts, on purpose."""
            USED = "max_height_ft"
            EXCLUDED = ("min_lot_depth_ft (not costed)",)
            '''
        ),
        encoding="utf-8",
    )
    read, declared = readers_by_field(root)
    assert "flats/score/fake.py" in read["max_height_ft"]
    assert "flats/score/fake.py" in declared["min_lot_depth_ft"]
    # A bare mention inside prose is a read, not a declaration: crude, and
    # crude towards over-reporting reach, which never invents a gap.
    assert "max_far" not in read


def test_no_consumer_tree_means_nothing_is_reached(tmp_path):
    read, declared = readers_by_field(tmp_path)
    assert read == {}
    assert declared == {}


def test_render_names_both_kinds_of_unread(rows):
    text = render(rows)
    assert "SILENTLY UNREAD" in text
    assert "UNREAD BUT DECLARED" in text
    assert "setback_street_side_ft" in text
    dark_only = render(rows, unreached_only=True)
    assert "REACHED\n" not in dark_only
