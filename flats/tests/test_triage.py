"""Fetch triage — the first review vertical to get a worklist of its own.

The cross-reference ledger has been right and unusable since it was written.
It knows a reference is *binding* -- that it stands within a few lines of text
an encoded value was read from -- and then discards which value, which is the
entire decision. A reference beside Gresham's rear setback across 22,000 lots
and a reference beside a definition of "story" print as the same row.

So these tests are mostly about what a card carries rather than what it counts.
The one that matters most is :func:`test_a_card_names_the_standards_it_stands_beside`:
if that ever goes back to a bare count, the queue is a ledger again.
"""

from __future__ import annotations

import pytest

from flats.encode.triage import (
    CONFIG,
    Card,
    Mention,
    Neighbour,
    _key,
    _splice,
    _wrap,
    cards,
    feed,
    fields_in,
    layer_path,
    rule,
)
from flats.rules.loader import load_rules
from flats.rules.model import CROSSREF_CLOSED, CROSSREF_OUTCOMES, Ruling

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"


def test_a_card_names_the_standards_it_stands_beside() -> None:
    """The whole reason this module exists.

    Gresham 7.0221 is "See Section 7.0221 - 7.0223 for additional
    requirements", printed seven lines from the rear setback in the
    middle-housing design chapter. That is the exact shape of the miss this
    ledger was built after -- a design chapter nothing cited, holding the
    sentence that moves a 26 ft building five feet back -- and the ledger's own
    row for it says only "1 mention, 1 binding".
    """
    card = next(c for c in cards(load_rules()[GRESHAM]) if c.ref == "7.0221")

    assert card.fields == ("setback_rear_ft",)
    assert card.lots > 20_000
    assert card.binding == 1
    assert any("additional requirements" in m.text for m in card.mentions)


def test_neighbours_group_by_figure_rather_than_repeating_per_zone() -> None:
    """Four zones sharing one coverage curve is one row, not four.

    Portland's curve is an eleven-cell array printed identically in R5, R7,
    R2.5 and R10. Listed per zone it fills the card with the same number four
    times; what actually differs is the zone names and the lots, and both
    survive the grouping.
    """
    card = next(
        c for c in cards(load_rules()["or/multnomah/portland"]) if c.ref == "11.50"
    )
    curves = [n for n in card.neighbours if n.field == "coverage_curve"]

    assert len(curves) == 1
    assert len(curves[0].zones) > 1
    assert curves[0].lots == sum(
        dict(card.zone_lots)[z] for z in curves[0].zones
    )


def test_lots_count_a_zone_once_however_many_standards_it_shares() -> None:
    """A reference beside four of R-5's numbers is one R-5.

    Summing neighbours would multiply the largest zone in the corpus by the
    number of standards that happen to sit near the same line, and the sort is
    by lots -- so the error would not be cosmetic, it would decide the order of
    work.
    """
    card = Card(
        layer="or/x",
        ref="1.1",
        mentions=(Mention("d.txt", 1, "t", True),),
        neighbours=(
            Neighbour("setback_front_ft", "10", ("R5",), 1, 100),
            Neighbour("setback_rear_ft", "20", ("R5",), 1, 100),
        ),
        zone_lots=(("R5", 100),),
    )

    assert card.lots == 100


def test_the_sort_is_lots_first() -> None:
    """Not mentions. Gladstone's loudest reference was ten mentions of one
    settled sentence about mobile home parks, and a queue that leads with
    volume teaches the person working it to skip rows."""
    rows = feed(layer=GRESHAM)
    lots = [c.lots for c in rows]

    assert lots == sorted(lots, reverse=True)


def test_ruled_rows_leave_the_queue_but_fetch_and_later_do_not() -> None:
    """Closing a row and ordering work are different things.

    ``fetch`` is a decision that the chapter matters; the row closes when the
    document is in the store and the reference resolves, not when somebody says
    so. Hiding it at the moment of the decision would lose the only list of
    documents anybody asked for.
    """
    assert "fetch" not in CROSSREF_CLOSED
    assert "later" not in CROSSREF_CLOSED
    assert CROSSREF_CLOSED >= {"other_building", "other_path", "misread", "procedure"}

    open_card = Card("or/x", "1.1", (), (), (), Ruling("x" * 60, "fetch"))
    shut_card = Card("or/x", "1.2", (), (), (), Ruling("x" * 60, "other_building"))
    assert open_card.open
    assert not shut_card.open


def test_the_filters_compose() -> None:
    """"Gresham today" and "setbacks everywhere" are the two shapes of session
    this queue is for, and they have to be able to be the same session."""
    everywhere = feed(field="setback_rear_ft")
    here = feed(layer=GRESHAM, field="setback_rear_ft")

    assert here
    assert {c.layer for c in here} == {GRESHAM}
    assert {c.key for c in here} <= {c.key for c in everywhere}
    assert all("setback_rear_ft" in c.fields for c in everywhere)


def test_the_field_menu_is_built_from_the_feed_it_filters() -> None:
    """A filter offering a field no row carries is a dead end, and one that
    omits a field rows do carry hides them."""
    rows = feed(layer=GRESHAM)
    menu = dict(fields_in(rows))

    assert menu
    for field, count in menu.items():
        assert count == sum(1 for c in rows if field in c.fields)


def test_state_law_is_not_in_this_queue() -> None:
    """ORS and OAR are a different fetch problem -- one document answers for
    all seventeen layers rather than one. Mixed in they bury a city's own
    missing chapter, which is the complaint this module was built from."""
    refs = {c.ref for c in feed()}

    assert not [r for r in refs if r.upper().startswith(("ORS", "OAR"))]


class TestRecordingADecision:
    """Rulings are spliced into hand-written YAML and never dumped over it."""

    def test_the_two_authoring_forms_both_load(self) -> None:
        """The seventeen rulings written before the vocabulary are prose and
        stay valid; they load as ``read``, which is deliberately a visible
        state rather than a silent one -- an unclassified ruling is a fact
        about the queue worth being able to see."""
        gladstone = load_rules()["or/clackamas/gladstone"].crossrefs

        assert gladstone["17.62.070"].outcome == "read"
        assert "mobile home park" in gladstone["17.62.070"]
        assert len(gladstone["17.62.070"]) > 100

    def test_a_ruling_survives_a_round_trip_through_the_splice(self) -> None:
        lines = [
            "layer: or/x",
            "crossrefs:",
            '  "1.1":',
            "    outcome: procedure",
            "    note: >-",
            "      the old one",
            "zones:",
            "  R5: {}",
        ]
        out = _splice(lines, "1.1", "other_building", "the new one " * 6)

        assert "    outcome: other_building" in out
        assert "      the old one" not in out
        assert out[-2:] == ["zones:", "  R5: {}"]

    def test_a_new_ref_appends_rather_than_replacing(self) -> None:
        lines = ["crossrefs:", '  "1.1":', "    outcome: procedure", "zones:"]
        out = _splice(lines, "2.2", "misread", "a table cell, not a section " * 3)

        assert '  "1.1":' in out
        assert '  "2.2":' in out
        assert out[-1] == "zones:"

    def test_a_file_with_no_crossrefs_block_gets_one_before_the_zones(self) -> None:
        """Appended at the end it would land after two thousand lines of zones,
        which is where nobody looks and where a hand edit will collide."""
        lines = ["layer: or/x", "label: X", "zones:", "  R5: {}"]
        out = _splice(lines, "1.1", "fetch", "go and get it " * 5)

        assert out.index("crossrefs:") < out.index("zones:")

    def test_an_entry_key_is_read_at_one_indent_only(self) -> None:
        assert _key('  "17.62.070":') == "17.62.070"
        assert _key("  17.62.070:") == "17.62.070"
        assert _key("    outcome: fetch") == ""
        assert _key("zones:") == ""

    def test_prose_is_wrapped_and_never_run_together(self) -> None:
        wrapped = _wrap("word " * 60)

        assert all(line.startswith("      ") for line in wrapped)
        assert all(len(line) <= 98 for line in wrapped)
        assert " ".join(w.strip() for w in wrapped).split() == ["word"] * 60

    def test_an_unknown_outcome_is_refused_before_anything_is_written(self) -> None:
        with pytest.raises(ValueError, match="unknown outcome"):
            rule(GRESHAM, "7.0221", "sounds_fine", "x" * 60)

    def test_a_tag_with_no_reasoning_is_refused(self) -> None:
        """A row closed with a word nobody can check is worse than an open row:
        the open row still shows the sentence."""
        with pytest.raises(ValueError, match="at least"):
            rule(GRESHAM, "7.0221", "procedure", "no")

    @pytest.mark.parametrize(
        "layer_id",
        [
            "../../../../etc/passwd",
            "or/multnomah/../../../../Windows/system",
            "/etc/hosts",
            "or/multnomah/gresham/../../../pyproject",
            "",
        ],
    )
    def test_a_layer_id_that_is_not_a_layer_never_becomes_a_path(
        self, layer_id: str
    ) -> None:
        """The id comes from a browser form and everything past it writes.

        Checked against the loaded keyset rather than a pattern: the
        authoritative list of seventeen strings is already in memory, and a
        pattern is a guess about what a path can look like.
        """
        with pytest.raises(ValueError, match="not a layer we hold"):
            layer_path(layer_id)

    def test_a_real_layer_id_resolves_inside_the_rule_tree(self) -> None:
        path = layer_path(GRESHAM)

        assert path.is_relative_to(CONFIG.resolve())
        assert path.name == "gresham.yaml"
        assert path.exists()

    def test_the_write_path_refuses_before_it_touches_disk(self) -> None:
        with pytest.raises(ValueError, match="not a layer we hold"):
            rule("../../../../etc/passwd", "1.1", "procedure", "x" * 60)

    def test_every_offered_outcome_is_a_real_one(self) -> None:
        from app.api.routers.ui_flats import _TRIAGE_ORDER

        assert set(_TRIAGE_ORDER) <= set(CROSSREF_OUTCOMES)
        assert "read" not in _TRIAGE_ORDER, "legacy tag, not something to file under"
        assert set(CROSSREF_OUTCOMES) - set(_TRIAGE_ORDER) == {"read"}
