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
    SNIPPET,
    Card,
    Mention,
    Neighbour,
    _below_a_section,
    _key,
    _splice,
    _title_in,
    _window,
    _wrap,
    cards,
    feed,
    fields_in,
    layer_path,
    rule,
)
from flats.rules.fields import FIELDS
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


def test_the_sort_leads_with_lots_that_can_still_move() -> None:
    """Not mentions, and not raw lots either.

    Mentions first was the first mistake: Gladstone's loudest reference was ten
    mentions of one settled sentence about mobile home parks, and a queue that
    leads with volume teaches the person working it to skip rows.

    Raw lots was the second, and it is the subtler one. A reference sitting in a
    citywide use table stands beside ``quadplex_allowed`` for every zone in the
    city, so it counts the whole city -- but ``quadplex_allowed`` is a yes/no
    that is already decided, and no chapter we go and read can make it more or
    less true. The lots that matter are the ones behind a standard with *room*
    in it: a setback, a coverage ratio, a height. Those can move.
    """
    rows = feed(layer=GRESHAM)
    live = [c.live_lots for c in rows]

    assert live == sorted(live, reverse=True)


def test_a_settled_yes_no_does_not_put_a_chapter_at_the_top() -> None:
    """The finding that forced the sort change, pinned.

    Portland 33.236 is the Floating Structures chapter -- houseboats. It led the
    whole corpus at 178,237 lots because it is named once in the citywide use
    table, on a line that also carries ``quadplex_allowed``. Reading it cannot
    change a single number this screen uses.
    """
    rows = feed(layer="or/multnomah/portland")
    by_ref = {c.ref: c for c in rows}
    if "33.236" not in by_ref:
        pytest.skip("33.236 not in the current Portland feed")

    houseboats = by_ref["33.236"]
    assert houseboats.lots > 100_000, "still cited beside the whole city"
    assert houseboats.live_lots == 0, "but beside nothing that has slack"
    assert rows[0].ref != "33.236"
    assert rows[0].live_lots > 0, "something with room in it leads instead"


def test_live_lots_counts_a_zone_once_however_many_standards_it_carries() -> None:
    """A zone standing beside four loose standards is still one zone of lots.

    ``zone_lots`` is held flat on the card for exactly this: summing the
    neighbours' own lot counts would multiply a zone by the number of standards
    it happens to carry, and the top of the queue would be whichever reference
    sits in the widest table rather than whichever covers the most ground.
    """
    card = Card(
        layer="or/x",
        ref="1.1",
        mentions=(),
        neighbours=(
            Neighbour("setback_rear_ft", "20 ft", ("R5",), 0, 100),
            Neighbour("setback_front_ft", "10 ft", ("R5",), 0, 100),
            Neighbour("max_height_ft", "35 ft", ("R5", "R7"), 1, 160),
        ),
        zone_lots=(("R5", 100), ("R7", 60)),
    )

    assert card.live_lots == 160


def test_a_standard_with_no_slack_contributes_no_lots() -> None:
    """A bool is not a thing another chapter can nudge."""
    settled = Card(
        layer="or/x",
        ref="1.1",
        mentions=(),
        neighbours=(Neighbour("quadplex_allowed", "yes", ("R5",), 0, 900),),
        zone_lots=(("R5", 900),),
    )
    loose = Card(
        layer="or/x",
        ref="1.2",
        mentions=(),
        neighbours=(Neighbour("setback_rear_ft", "20 ft", ("R5",), 0, 900),),
        zone_lots=(("R5", 900),),
    )

    assert settled.lots == loose.lots == 900
    assert settled.live_lots == 0
    assert loose.live_lots == 900
    assert loose.rank > settled.rank


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

    open_card = Card(
        layer="or/x", ref="1.1", mentions=(), neighbours=(),
        ruling=Ruling("x" * 60, "fetch"),
    )
    shut_card = Card(
        layer="or/x", ref="1.2", mentions=(), neighbours=(),
        ruling=Ruling("x" * 60, "other_building"),
    )
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

# --- what the card says, as opposed to what it counts ------------------------


def test_a_chapter_number_alone_does_not_say_what_the_chapter_is() -> None:
    """"Section 33.236" is a filing reference, not a question.

    The person working this queue has to decide whether a chapter can move a
    number, and the chapter number carries no information about that at all.
    The title does: "Floating Structures" answers it in two words. It is only
    ever read out of a citing sentence, never guessed.
    """
    assert _title_in("33.236", "See Chapter 33.236, Floating Structures.") == (
        "Floating Structures"
    )
    assert _title_in("7.0420", "subject to Section 7.0420, Parking Standards") == (
        "Parking Standards"
    )


def test_a_title_may_be_broken_across_two_extracted_lines() -> None:
    """The extractor wraps at the page's column width, not at the sentence.

    Gresham 10.1520 read as "Reduction" until the next line was consulted, and
    "Reduction" is not a subject -- it is the first word of one.
    """
    got = _title_in(
        "10.1520",
        "as provided in Section 10.1520, Reduction in Minimum",
        "Lot Frontage, the Director may",
    )
    assert got == "Reduction in Minimum Lot Frontage"


def test_a_title_stops_where_the_sentence_resumes() -> None:
    """Capitalised words keep coming after the title ends. A rule that reads
    to the end of the line swallows the sentence and prints a paragraph in a
    heading slot."""
    assert _title_in("7.0420", "Section 7.0420, Parking Standards shall apply") == (
        "Parking Standards"
    )
    assert _title_in(
        "1.2", "Chapter 1.2, Definitions of the Community Development Code"
    ) == "Definitions"


def test_a_title_does_not_end_on_a_dangling_preposition() -> None:
    """"Reduction in Minimum Lot Frontage" needs the "in"; "Reduction in" does
    not need anything -- it needs trimming."""
    got = _title_in("10.1520", "under Section 10.1520, Reduction in")
    assert got in ("Reduction", "")
    assert not got.endswith(" in")


def test_a_number_below_a_section_is_not_a_section() -> None:
    """Portland's floor-area-ratio table prints "0.7 to 1". The reference
    scanner sees a dotted number and files a chapter that does not exist -- and
    because the cell sits inside the citywide table, the phantom sorts to the
    top of the queue on lots.

    No Oregon code numbers a chapter zero.
    """
    assert _below_a_section("0.7")
    assert _below_a_section("0.35")
    assert not _below_a_section("33.236")
    assert not _below_a_section("10.1520")
    assert not _below_a_section("7.0420")


def test_a_quote_from_a_table_row_is_cut_down_to_the_reference() -> None:
    """A table row in an extracted PDF is one very long line of cells separated
    by runs of spaces. Printed from the beginning it is a column of Y and N and
    the reference never appears; printed whole it is unreadable either way.

    Centre on the reference, and collapse the runs to a visible marker so what
    is left does not pretend to be a sentence.
    """
    cells = "     ".join(["Y", "N"] * 60)
    line = f"Household Living     {cells}     See Chapter 33.236     {cells}"
    at = line.index("33.236")
    got = _window(line, at, at + len("33.236"))

    assert "33.236" in got
    assert len(got) < len(line)
    assert len(got) <= SNIPPET + 20
    assert "     " not in got, "runs of cells collapse to a marker"
    assert "·" in got
    assert got.startswith("…") and got.endswith("…"), "both ends were cut"


def test_a_short_line_is_left_alone() -> None:
    """Windowing a sentence that already fits only loses its beginning."""
    line = "Accessory dwellings are subject to Section 7.0420."
    at = line.index("7.0420")

    assert _window(line, at, at + len("7.0420")) == line



# --- the inbox, and getting past a card you cannot answer --------------------


def test_a_recorded_decision_closes_a_row_before_it_reaches_a_rule_file() -> None:
    """Rules load from the repository, and the container rebuilds them from git
    on every deploy, so a ruling made in a browser cannot be written where the
    rules live -- it would be gone by the next release.

    It goes to a table, and the queue reads that table on top of the files. The
    row has to leave the queue at the moment it is decided, or the next person
    is handed a question somebody already answered.
    """
    rows = feed(layer=GRESHAM)
    assert rows
    target = rows[0]

    decided = {
        (target.layer, target.ref): Ruling(
            "Read it. Design review procedure, no dimensional standard in it.",
            "procedure",
        )
    }
    after = feed(layer=GRESHAM, overrides=decided)

    assert target.key not in {c.key for c in after}
    assert len(after) == len(rows) - 1

    back = feed(layer=GRESHAM, ruled=True, overrides=decided)
    ruled = {c.key: c for c in back}[target.key]
    assert ruled.outcome == "procedure"
    assert not ruled.open


def test_a_recorded_fetch_leaves_the_row_where_it_is() -> None:
    """Saying "yes, go get this" is not the same as having got it. The row
    closes when the document is in the store, and until then it is the only
    list of what to go and fetch."""
    rows = feed(layer=GRESHAM)
    target = rows[0]
    decided = {
        (target.layer, target.ref): Ruling("x" * 60, "fetch")
    }

    after = {c.key: c for c in feed(layer=GRESHAM, overrides=decided)}

    assert target.key in after
    assert after[target.key].outcome == "fetch"


def test_an_override_only_speaks_for_its_own_reference() -> None:
    """Two cities number their chapters however they like, and 1.2 in one is
    not 1.2 in another. The key is the pair."""
    rows = feed(layer=GRESHAM)
    target = rows[0]
    wrong_layer = {
        ("or/multnomah/portland", target.ref): Ruling("x" * 60, "procedure")
    }

    assert target.key in {c.key for c in feed(layer=GRESHAM, overrides=wrong_layer)}


# --- what a standard is called, once a person has to read it -----------------


def test_every_standard_has_a_name_a_person_would_say_out_loud() -> None:
    """``setback_rear_ft`` is what the code calls it. "rear setback" is what a
    reviewer calls it, and the card is asking that reviewer a question.

    Derivation from the identifier is not enough on its own -- it produces
    "quadplex allowed" for a fourplex and "max far" for a floor area ratio --
    so every field carries a written label and this is what checks none went
    missing.
    """
    for name, spec in FIELDS.items():
        assert spec.shown, name
        assert "_" not in spec.shown, name
        assert not spec.shown.endswith((" ft", " sqft", " pct", " du")), name


def test_the_labels_that_derivation_gets_wrong_are_written_out() -> None:
    """Each of these is a case where splitting the identifier on underscores
    produces something a reader has to translate back."""
    assert FIELDS["quadplex_allowed"].shown == "fourplex allowed"
    assert FIELDS["max_far"].shown == "max. floor area ratio"
    assert FIELDS["min_lot_sqft"].shown == "min. lot area"
    assert FIELDS["setback_rear_ft"].shown == "rear setback"


def test_slack_is_a_property_of_the_standard_not_of_the_lot() -> None:
    """A setback of twenty feet has room in it -- twenty-two would still be a
    number, and a chapter we have not read might say so. "Fourplexes allowed:
    yes" has no room in it at all; nothing another chapter says makes it more
    or less true.

    This is the whole basis of the sort, so it is checked against the registry
    rather than against a list written here.
    """
    assert FIELDS["setback_rear_ft"].has_slack
    assert FIELDS["max_height_ft"].has_slack
    assert not FIELDS["quadplex_allowed"].has_slack

    for name, spec in FIELDS.items():
        assert spec.has_slack == (spec.kind not in ("bool", "enum")), name
