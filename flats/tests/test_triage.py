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
    _HEADING,
    Card,
    Mention,
    Neighbour,
    _below_a_section,
    _curve,
    _deferred_to,
    _key,
    _named_in,
    _nesting,
    _num,
    _passage,
    _same,
    _splice,
    _title_in,
    _window,
    _wrap,
    _zone_key,
    cards,
    feed,
    fields_in,
    layer_path,
    render,
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
    """Seventeen zones sharing two answers is two rows, not seventeen.

    Portland's use tables print the same permission over and over. A four-plex
    is allowed in ten zones and barred in seven, and every one of those cells
    cites Chapter 33.236, Floating Structures -- houseboat moorages, which is
    why the chapter is unfetched and will stay that way. Listed per zone the
    card is seventeen lines of "yes" and "no"; grouped by figure it is two,
    and the zone names and the lot counts both survive the grouping.

    This used to be pinned on 11.50, whose coverage curve prints identically in
    R5, R7, R2.5 and R10. That chapter was fetched and read on 2026-09-01, so
    it stopped dangling and its card went away with it. A test pinned to a
    corpus GAP goes red when the gap is closed, and this suite has been through
    that before: it is the right kind of red, and the fix is to re-point it at
    something the corpus has not answered yet rather than to leave the gap open.
    """
    card = next(
        c for c in cards(load_rules()["or/multnomah/portland"]) if c.ref == "33.236"
    )
    allowed = [n for n in card.neighbours if n.field == "quadplex_allowed"]

    # One row per distinct figure -- not one per zone, and not one overall.
    assert len(allowed) == 2
    assert {n.shown for n in allowed} == {"yes", "no"}
    for row in allowed:
        assert len(row.zones) > 1
        assert row.lots == sum(dict(card.zone_lots)[z] for z in row.zones)


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


# --- the second route in ----------------------------------------------------
#
# Everything above counts a chapter by what it is written *beside*. That is one
# of the two ways a chapter reaches our numbers and it was, until now, the only
# one this queue could see. The other is being handed a *word* every one of
# those numbers is measured in, said once, in prose, nowhere near a value.


def test_a_chapter_reached_only_through_a_word_is_still_at_stake() -> None:
    """Portland's Chapter 33.930, Measurements, pinned as a shape.

    It stands beside nothing -- no table, no figure, no standard -- so every
    number this card has ever counted is zero, and it ranked (0, 0, 0, 0) at
    position 69 of 75. It also settles how height is measured on 95% of the
    city. A queue that cannot see that is sorting on the wrong thing, not
    sorting badly.
    """
    silent = Card(
        layer="or/x",
        ref="33.930",
        mentions=(),
        neighbours=(),
        zone_lots=(),
        undefined=("building height", "lot width"),
        undefined_lots=186_888,
    )
    ordinary = Card(
        layer="or/x",
        ref="33.613",
        mentions=(),
        neighbours=(Neighbour("min_lot_sqft", "5,000 sq ft", ("R5",), 0, 13_710),),
        zone_lots=(("R5", 13_710),),
    )

    assert silent.live_lots == 0
    assert silent.reach == 186_888
    assert silent.rank > ordinary.rank


def test_the_two_routes_are_the_same_lots_reached_twice_not_twice_the_lots() -> None:
    """A chapter cited beside a city's setback table *and* handed the word that
    setback is measured in is one chapter over one city. Adding the counts
    would report a jurisdiction larger than it is."""
    both = Card(
        layer="or/x",
        ref="1.1",
        mentions=(),
        neighbours=(Neighbour("setback_rear_ft", "20 ft", ("R5",), 0, 900),),
        zone_lots=(("R5", 900),),
        undefined=("yard",),
        undefined_lots=900,
    )

    assert both.reach == 900


def test_a_subsection_is_credited_to_the_chapter_that_contains_it() -> None:
    """"See 33.930.100" and "See Chapter 33.930, Measurements" are one fetch,
    and both are cards in this queue. Crediting only the exact string would
    rank the parent below the child inside it and split one decision in two."""
    deferred = {
        "33.930": (("building height",), 186_888),
        "33.930.100": (("lot width",), 24_689),
    }

    words, lots = _deferred_to(deferred, "33.930")
    assert words == ("building height", "lot width")
    assert lots == 186_888, "the larger of two overlapping counts, not their sum"

    assert _deferred_to(deferred, "33.930.100") == (("lot width",), 24_689)


def test_a_chapter_that_merely_starts_the_same_way_is_a_different_chapter() -> None:
    """33.9301 is not inside 33.930. Matching on the string alone would hand a
    chapter its neighbour's lots."""
    deferred = {"33.9301": (("yard",), 900)}

    assert _deferred_to(deferred, "33.930") == ((), 0)


def test_a_card_at_the_top_of_the_queue_says_what_put_it_there() -> None:
    """The rank moved and the row did not, so the queue's own first card read
    "0 lots · binds 0× · 8 mentions" with nothing to explain itself. A chapter
    that jumps to the top for a reason nobody can see is worse than one sitting
    at the bottom."""
    card = Card(
        layer="or/x",
        ref="33.930",
        mentions=(),
        neighbours=(),
        zone_lots=(),
        undefined=("building height",),
        undefined_lots=186_888,
    )

    shown = render([card])
    assert "building height" in shown
    assert "186,888" in shown


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
    """"This city today" and "setbacks everywhere" are the two shapes of
    session this queue is for, and they have to be able to be the same session.

    The pair is taken from the feed rather than typed in. This test used to
    name Gresham and `setback_rear_ft`, and it went red the day that card was
    closed -- Section 10.1100 was fetched, and its mention sits inside Table
    4.0130, so it was the row carrying every dimensional standard in the city.
    A queue is meant to empty; a test that hard-codes one of its rows fails on
    success. What is worth asserting is the composition, not the example."""
    layer, field = next(
        (c.layer, f) for c in feed() for f in sorted(c.fields)
    )
    everywhere = feed(field=field)
    here = feed(layer=layer, field=field)

    assert here
    assert {c.layer for c in here} == {layer}
    assert {c.key for c in here} <= {c.key for c in everywhere}
    assert all(field in c.fields for c in everywhere)


def test_the_field_menu_is_built_from_the_feed_it_filters() -> None:
    """A filter offering a field no row carries is a dead end, and one that
    omits a field rows do carry hides them.

    The layer is chosen from the feed for the same reason the composition test
    above chooses its pair there. This named Gresham, and Gresham's menu went
    empty the day 10.1100 was fetched: that one card sat inside Table 4.0130
    and was the only Gresham row standing beside a field at all. Sixty
    references remain open in the city and not one of them is beside a number
    this screen measures with, which is a good state for a queue to be in and a
    bad one to hard-code."""
    layer = next(c.layer for c in feed() if c.fields)
    rows = feed(layer=layer)
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


def test_the_state_does_not_scan_a_city_s_code() -> None:
    """A layer owns the documents in its own directory and no others.

    The ownership test read ``path.startswith(layer + "/")``, which is true of
    every document in the corpus when the layer is ``or`` -- all 177 of them
    are filed under ``or/``. So Oregon was scanned against every city code we
    hold and the queue grew 691 cards numbered like municipal code (1.04.070,
    02.16.6) filed under the state's name, none of which Oregon writes. The
    reading ledger had the identical fault and it was found there first; this
    is its twin, and the reason the queue was four fifths phantom.
    """
    from flats.provenance.store import ProvenanceStore

    store = ProvenanceStore()
    held = {
        p.rsplit("/", 1)[-1]
        for p in store.documents()
        if p.rsplit("/", 1)[0] == "or"
    }
    docs = {m.doc for c in cards(load_rules()["or"]) for m in c.mentions}

    assert held, "the state layer does hold documents of its own"
    assert docs <= held


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


# --- saying what the reference is, and what stands beside it ----------------


def test_a_title_is_not_a_section() -> None:
    """Portland's tree rules are Title 11. The card said "Section 11", which
    describes a paragraph rather than a whole body of code -- and a reviewer
    deciding whether something can reach their lot is being told the wrong
    scale of thing.

    The noun is read from the citing sentence, exactly like the title.
    """
    assert _named_in("11", "requirements of Title 11, Trees. See Chapter") == (
        "Title",
        "Trees",
    )
    assert _named_in("33.236", "See Chapter 33.236, Floating Structures.") == (
        "Chapter",
        "Floating Structures",
    )
    assert _named_in("7.0420", "under Section 7.0420, Parking Standards apply")[0] == (
        "Section"
    )


def test_the_noun_defaults_to_the_commonest_rather_than_the_truest() -> None:
    """Most of these are sections, and a card with no citing sentence to read
    has to call it something."""
    bare = Card(layer="or/x", ref="1.1", mentions=(), neighbours=())
    assert bare.kind == "Section"
    assert bare.title == ""


def test_portland_title_11_is_read_off_the_corpus_as_a_title() -> None:
    rows = {c.ref: c for c in feed(layer="or/multnomah/portland")}
    if "11" not in rows:
        pytest.skip("Title 11 not in the current Portland feed")

    assert rows["11"].kind == "Title"
    assert rows["11"].title == "Trees"


def test_a_tiered_coverage_table_is_said_out_loud() -> None:
    """It was printed as ``[[0, 0, 50], [3000, 1500, 37.5], [5000, 2...`` --
    nested brackets, truncated mid-number, and the only standard on the card.

    The tiers mean: on a lot at or above the floor, the footprint may be the
    base plus that percentage of everything above the floor. That is what
    ``flats.score.screen._coverage_allowed_sqft`` computes, and a reviewer
    cannot judge whether a tree chapter eats into it while reading a list.
    """
    got = _curve([[0, 0, 50], [3000, 1500, 37.5], [20000, 4500, 7.5]])

    assert got.startswith("any lot: 0 sqft + 50% of the excess")
    assert "from 3,000 sqft: 1,500 sqft + 37.5% of the excess" in got
    assert "from 20,000 sqft: 4,500 sqft + 7.5% of the excess" in got
    assert "[" not in got and "]" not in got


def test_a_curve_of_an_unexpected_shape_is_not_dressed_up() -> None:
    """Better a raw list than a confident sentence about a table we did not
    understand."""
    assert _curve([[0, 50]]) == "[[0, 50]]"


def test_figures_carry_thousands_separators() -> None:
    """"12000" and "12,000" are the same number and not the same reading."""
    assert _num(12000) == "12,000"
    assert _num(37.5) == "37.5"
    assert _num(35.0) == "35", "a whole number does not need its .0"


def test_no_standard_reaches_the_card_as_a_python_repr() -> None:
    """The guard for the whole class of bug the coverage curve was one of."""
    for card in feed():
        for n in card.neighbours:
            assert "[" not in n.shown, f"{card.layer} {card.ref} {n.field}: {n.shown}"
            assert not n.shown.endswith("..."), f"{card.layer} {card.ref}: {n.shown}"


# --- which of fourteen mentions is worth reading ----------------------------


def test_the_card_shows_what_the_reference_says_not_how_often_it_says_it() -> None:
    """Portland's tree reference is written fourteen times and says eight
    different things. The card showed the first four in document order, which
    were four copies of the same boilerplate sentence -- and put the two that
    carried anything ("a Title 11 tree permit must be obtained", "Large canopy
    trees are defined in") behind "and 10 more mentions".
    """
    rows = {c.ref: c for c in feed(layer="or/multnomah/portland")}
    if "11" not in rows:
        pytest.skip("Title 11 not in the current Portland feed")
    card = rows["11"]

    assert len(card.mentions) > len(card.distinct), "boilerplate was repeated"
    texts = [" ".join(m.text.split()) for m, _ in card.distinct]
    assert len(texts) == len(set(texts)), "and it is not repeated on the card"
    assert sum(n for _, n in card.distinct) == len(card.mentions), "none dropped"


def test_the_mention_beside_a_number_leads() -> None:
    """The card asks whether this chapter can change a number we screen on.
    The mention standing next to that number is the evidence for the question
    being asked, and it was third on the list."""
    card = Card(
        layer="or/x",
        ref="1.1",
        mentions=(
            Mention(doc="a.txt", line=1, text="somewhere else entirely", binding=False),
            Mention(doc="a.txt", line=2, text="also elsewhere", binding=False),
            Mention(doc="b.txt", line=9, text="right by the setback", binding=True),
        ),
        neighbours=(),
    )

    assert card.distinct[0][0].binding
    assert card.distinct[0][0].line == 9


def test_a_repeated_sentence_is_counted_at_the_binding_copy() -> None:
    """Same sentence in two places, one of them next to a number. The card
    should cite the copy that is next to the number and say the other exists,
    not cite the first one it happened to read."""
    card = Card(
        layer="or/x",
        ref="1.1",
        mentions=(
            Mention(doc="a.txt", line=3, text="see Section 1.1", binding=False),
            Mention(doc="b.txt", line=7, text="see  Section 1.1", binding=True),
        ),
        neighbours=(),
    )

    assert len(card.distinct) == 1
    shown, repeats = card.distinct[0]
    assert repeats == 2
    assert shown.line == 7 and shown.binding


def test_every_mention_is_accounted_for_on_every_card() -> None:
    """Deduplication that loses one is a card quietly showing less evidence
    than the corpus holds."""
    for card in feed():
        assert sum(n for _, n in card.distinct) == len(card.mentions), card.key


def test_a_reference_says_when_a_bigger_one_in_the_queue_already_covers_it() -> None:
    """Portland's Title 11 and its Chapter 11.50 came up back to back with the
    same lots and the same sentences, and nothing said they were one fetch.

    Not merged -- fetching a title and fetching one chapter of it are
    different fetches and a code can publish a chapter on its own. Named, so
    the decision is made once knowingly instead of twice unknowingly.
    """
    rows = {c.ref: c for c in feed(layer="or/multnomah/portland")}
    if "11" not in rows or "11.50" not in rows:
        pytest.skip("Title 11 and Chapter 11.50 not both in the current feed")

    assert rows["11"].inside == ""
    assert "11.50" in rows["11"].contains
    assert rows["11.50"].inside == "11"


def test_nesting_names_the_nearest_container_not_the_largest() -> None:
    """A section inside a chapter inside a title has two ancestors, and the
    useful one is the smallest thing that already covers it."""
    got = _nesting(("11", "11.50", "11.50.030", "33.100"))

    assert got["11.50.030"][0] == "11.50"
    assert got["11.50"][0] == "11"
    assert got["33.100"][0] == ""
    assert got["11"][1] == ("11.50", "11.50.030")


def test_a_sibling_is_not_a_parent() -> None:
    """33.100 and 33.110 are two chapters of one title, not one inside the
    other, and a prefix test that ignored the dot would call them nested."""
    got = _nesting(("33.100", "33.110", "33.1"))

    assert got["33.110"][0] == ""
    assert got["33.100"][0] == ""


# --- a quote that reads as a sentence ---------------------------------------


def test_a_wrapped_sentence_is_rejoined_across_the_extractor_s_line_break() -> None:
    """An extractor breaks at the page width, not at the full stop, so the line
    a reference lands on routinely starts and ends mid-clause. Shown that way a
    card reads as broken English and the reviewer cannot tell whether the
    sentence was cut by us or by the code."""
    body = [
        "The trees must be determined to be dead, dying, or",
        "dangerous by an arborist, and a Title 11 tree permit must be",
        "obtained. If a tree is removed, two must be planted.",
    ]
    at = body[1].index("11")
    got = _passage(body, 2, at, at + 2, "11")

    assert got == (
        "The trees must be determined to be dead, dying, or dangerous by an "
        "arborist, and a Title 11 tree permit must be obtained."
    )


def test_a_table_row_is_never_rejoined_with_its_neighbours() -> None:
    """A row's horizontal spacing is the only record of which column a number
    belonged to. Three rows glued together look like one row and read like
    nonsense, so grid lines keep the window treatment."""
    body = [
        "R5      5,000      20      See Chapter 33.236",
        "R7      7,000      25      See Chapter 33.236",
    ]
    at = body[0].index("33.236")
    got = _passage(body, 1, at, at + 6, "33.236")

    assert "R7" not in got, "the row below was not dragged in"
    assert "·" in got, "and the cut columns are still marked as columns"


def test_the_ellipsis_means_fragment_not_neighbourhood() -> None:
    """Marking on position put an ellipsis in front of a sentence that began
    exactly where it should, and left one off a fragment that began mid-word
    because the line above it was a table."""
    whole = [
        "Some earlier sentence entirely about something else.",
        "The permit is issued under Section 7.0420 and expires.",
    ]
    at = whole[1].index("7.0420")
    got = _passage(whole, 2, at, at + 6, "7.0420")
    assert not got.startswith("…"), "it starts where a sentence starts"
    assert not got.endswith("…"), "and ends where one ends"

    cut = [
        "R5      5,000      20",
        "preservation requirements of Section 7.0420, Trees.",
    ]
    at = cut[1].index("7.0420")
    got = _passage(cut, 2, at, at + 6, "7.0420")
    assert got.startswith("…"), "this one really does begin mid-sentence"


def test_a_section_number_starts_a_new_sentence() -> None:
    """"...Signs and Related Regulations. 33.100.230 Trees Requirements for..."
    is two sentences and a heading. Splitting only on a capital letter pulled
    an unrelated sentence about signs onto a card about trees."""
    body = [
        "The sign regulations are stated in Title 32, Signs and Related "
        "Regulations. 33.100.230 Trees Requirements are in Title 11, Trees."
    ]
    at = body[0].rindex("11")
    got = _passage(body, 1, at, at + 2, "11")

    assert "sign regulations" not in got
    assert got.startswith("33.100.230")


def test_zones_sort_the_way_a_planner_reads_them() -> None:
    """Portland's residential zones printed "R10, R2.5, R20, R5, R7" -- which
    looks like a list nobody checked, and hides that they run smallest lot to
    largest."""
    got = sorted(["R10", "R2.5", "R20", "R5", "R7"], key=_zone_key)

    assert got == ["R2.5", "R5", "R7", "R10", "R20"]
    assert sorted(["RM2", "RM1", "C", "EX"], key=_zone_key) == ["C", "EX", "RM1", "RM2"]


def test_no_quote_on_any_card_ends_mid_word() -> None:
    """The guard for the class of bug this was one of."""
    for card in feed():
        for m, _ in card.distinct:
            text = m.text.rstrip("…").rstrip()
            assert text, card.key
            # A quote may end on a cut, but the cut is marked; what it may not
            # do is stop with no sign that it stopped.
            if not text.endswith((".", ";", ":", "!", "?", "·")):
                assert m.text.endswith("…"), f"{card.key} {m.doc}L{m.line}: {m.text!r}"


def test_a_section_heading_is_not_the_first_two_words_of_a_sentence() -> None:
    """Codes print "33.110.227 Trees" on a line above the paragraph it names.
    Joined to the sentence under it that reads "Trees Requirements for street
    trees", which is a heading being read as prose -- and it made three
    chapters saying one thing look like three different things, because each
    carried its own section number into the quote."""
    body = [
        "33.110.227 Trees",
        "Requirements for street trees and for on-site tree preservation",
        "are specified in Title 11, Trees.",
    ]
    at = body[2].index("11")
    got = _passage(body, 3, at, at + 2, "11")

    assert got.startswith("Requirements for street trees")
    assert "33.110.227" not in got


def test_a_heading_boundary_does_not_swallow_ordinary_numbered_prose() -> None:
    """A paragraph that opens with a figure is not a heading. The test is a
    section-shaped number and a short unpunctuated title, not any digit."""
    assert _HEADING.match("33.110.227 Trees")
    assert _HEADING.match("10.1520 Reduction in Minimum Street Frontage")
    assert not _HEADING.match("20,000 sq. ft. or more")
    assert not _HEADING.match("5 feet is required where the lot abuts an alley.")
    assert not _HEADING.match("A. Purpose. These standards apply to all lots.")


def test_one_sentence_written_twice_is_counted_once() -> None:
    """Portland states its tree requirement identically in several chapters and
    the extractor wrote "on -site" in one of them. That is not a difference in
    what the code says, and a card reporting nine statements where there are
    six is inflating its own evidence."""
    assert _same("on-site trees") == _same("on -site  trees")
    assert _same("Title 11, Trees.") == _same("title 11 trees")
    assert _same("are specified in Title 11") != _same("are in Title 11")


def test_the_same_sentence_under_different_section_numbers_collapses() -> None:
    rows = {c.ref: c for c in feed(layer="or/multnomah/portland")}
    if "11" not in rows:
        pytest.skip("Title 11 not in the current Portland feed")
    card = rows["11"]

    texts = [m.text for m, _ in card.distinct]
    assert len(texts) == len(set(texts))
    for text in texts:
        assert not _HEADING.match(text.lstrip("…")), text


def test_a_quote_that_is_the_opening_of_another_is_the_same_quote() -> None:
    """One column is narrower than another and the sentence stops earlier.
    "...are specified in Title 11." and "...are specified in Title 11, Trees."
    are one statement, and the longer one contains the shorter whole, so
    folding them loses nothing."""
    card = Card(
        layer="or/x",
        ref="11",
        mentions=(
            Mention(doc="a.txt", line=1, text="Trees are specified in Title 11.", binding=False),
            Mention(doc="b.txt", line=2, text="Trees are specified in Title 11, Trees.", binding=False),
        ),
        neighbours=(),
    )

    assert len(card.distinct) == 1
    shown, repeats = card.distinct[0]
    assert repeats == 2
    assert shown.text.endswith("Title 11, Trees."), "the one that says more"


def test_two_quotes_that_merely_resemble_each_other_are_left_alone() -> None:
    """Measured against the corpus, a 0.92 similarity merge collapses "P P P
    Accessory dwelling units complying with Section 16.44.050" into "X X X
    Accessory dwelling units complying with Section 16.44.050" -- permitted
    and prohibited, told apart by one letter -- and "the minimum lot size
    standards apply" into "the minimum and maximum lot size standards apply".

    A queue that shows one sentence twice wastes a reader's time. One that
    silently merges two rules is wrong. Only containment folds.
    """
    card = Card(
        layer="or/x",
        ref="16.44.050",
        mentions=(
            Mention(doc="a.txt", line=1, binding=False,
                    text="P P P Accessory dwelling units complying with Section 16.44.050"),
            Mention(doc="a.txt", line=2, binding=False,
                    text="X X X Accessory dwelling units complying with Section 16.44.050"),
            Mention(doc="a.txt", line=3, binding=False,
                    text="The minimum lot size standards apply as established here."),
            Mention(doc="a.txt", line=4, binding=False,
                    text="The minimum and maximum lot size standards apply as established here."),
        ),
        neighbours=(),
    )

    assert len(card.distinct) == 4


def test_a_fold_never_shows_one_document_s_words_under_another_s_line() -> None:
    """The longer text wins only when nothing else distinguishes them. Where
    one is beside a number we use, that one is the citation -- showing its
    line number over the other document's sentence would be a fabricated
    quote."""
    card = Card(
        layer="or/x",
        ref="11",
        mentions=(
            Mention(doc="long.txt", line=1, text="Trees are in Title 11, Trees.", binding=False),
            Mention(doc="short.txt", line=9, text="Trees are in Title 11.", binding=True),
        ),
        neighbours=(),
    )

    shown, repeats = card.distinct[0]
    assert repeats == 2
    assert shown.doc == "short.txt" and shown.line == 9
    assert shown.text == "Trees are in Title 11.", "its own words, not the other's"


def test_a_card_in_a_city_nobody_screens_says_so_on_its_own_line() -> None:
    """This feed is ranked by lots at stake, which is what makes it worth
    marking.

    Lake Oswego is switched off — an owner decision about the Mountain Park PUD
    — and 50.06.001.5 arrives third in the binding feed on 350 lots, above Wood
    Village's 60. Those 350 are real lots in a real city; none of them is ever
    scored, so the number is true and the ranking it produces is not useful.

    The rank is deliberately left alone. Sorting by a second criterion nobody
    can see is how a queue stops being explainable, and the person reading it
    can weigh a marked row perfectly well. What they cannot do is guess.
    """
    card = Card(
        layer="or/clackamas/lake-oswego",
        ref="50.06.001.5",
        mentions=(Mention(doc="50.04.txt", line=1, text="see LOC 50.06.001.5", binding=True),),
        neighbours=(),
    )

    marked = render([card], off={"or/clackamas/lake-oswego"})
    plain = render([card])

    assert "SWITCHED OFF" in marked
    assert "the screen does not cover" in marked
    assert "SWITCHED OFF" not in plain, "the caller decides, not this renderer"
