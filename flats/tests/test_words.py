"""What the words in our numbers mean here — the queue underneath signing.

Signing asks whether a number matches the sentence it was taken from. That is
the right question and it is not the first one: a number read perfectly out of
its sentence is still wrong if this city measures the sentence's words its own
way. Four codes in the corpus give four incompatible tests for *corner lot* and
seven subtract seven different lists from a *net acre*.

Three things have to hold, and each of them is a way this queue would quietly
become furniture:

**A card must cost something.** Only a word that sets the meaning of a field
this jurisdiction actually holds a value on, and that this jurisdiction's own
code actually writes. Portland writes *setback* 582 times and *yard* 43; a
queue that asked about words the code never uses teaches reviewers to skip
rows, and a reviewer who skips rows skips the row that mattered.

**The three standings are three different instructions.** "The code is quiet"
and "we never opened the book" are opposite pieces of news, and a screen that
merged them would ask somebody to reason about a silence that is ours.

**A ruling remembers what it was about.** Glossaries are re-extracted whenever
a document is re-fetched, and this corpus has watched entries appear, split and
triple on a re-read. A decision made against wording nobody has seen since must
reopen rather than stay silently shut.
"""

from __future__ import annotations

import re

import pytest
import yaml

from flats.encode import words as W
from flats.encode.words import (
    GOVERNS,
    QUEUES,
    STANDINGS,
    Card,
    Definition,
    cards,
    counts,
    feed,
    orders,
    rule,
    tally,
    uses,
)
from flats.encode.worklist import _splice
from flats.rules.fields import FIELDS
from flats.rules.loader import load_rules
from flats.rules.model import (
    WORD_ALL,
    WORD_CLOSED,
    WORD_OUTCOMES,
    WORD_WORK,
    Layer,
    Provenance,
    Reading,
    Value,
    Zone,
)

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
GRESHAM = "or/multnomah/gresham"


def _stems(text: str) -> tuple[str, ...]:
    return tuple(W._stem(w) for w in W._norm(text).split() if w)


def _card(**kw: object) -> Card:
    base: dict[str, object] = {
        "layer": GRESHAM,
        "label": "Gresham",
        "term": "lot width",
        "standing": "defined",
        "says": (
            Definition(
                term="Lot, Width",
                text="The mean horizontal distance between the side lot lines.",
                cite=f"{GRESHAM}/dc.txt#L100-L101",
                doc="dc.txt",
                line=100,
            ),
        ),
        "exact": True,
        "fields": ("min_lot_width_ft",),
        "values": 9,
        "uses": 12,
        "lots": 40_000,
    }
    base.update(kw)
    return Card(**base)  # type: ignore[arg-type]


# --- the registry -----------------------------------------------------------


class TestRegistry:
    """What a word is allowed to govern, and what it costs to be wrong."""

    def test_every_governed_field_is_a_field_the_screen_knows(self) -> None:
        """A word governing a field nobody has named is a question about
        nothing: the card would show a cost of zero and never sort into view.
        """
        named = {f for fields in GOVERNS.values() for f in fields}
        assert not named - set(FIELDS)

    def test_every_standing_has_its_own_answers_and_shares_none(self) -> None:
        """The keying is the design. "Means what we assumed" is not an answer
        anybody can give about a glossary nobody has opened, and a screen that
        accepted it would record a decision nobody made.
        """
        seen: set[str] = set()
        for standing in STANDINGS:
            here = set(WORD_OUTCOMES[standing])
            assert here, standing
            assert not here & seen, f"{standing} shares an answer with another"
            seen |= here
        assert seen == set(WORD_ALL)

    def test_every_standing_is_named_in_front_of_a_person(self) -> None:
        for standing in STANDINGS:
            title, question = QUEUES[standing]
            assert title and question.endswith("?")

    def test_the_answers_that_order_work_are_the_ones_that_stay_open(self) -> None:
        """A ruling is not a disposal. "This city measures it differently" is a
        job, and a job that closed its own card would leave the encoding
        untouched and nothing to show for the reading.
        """
        assert set(WORD_WORK) == set(WORD_ALL) - WORD_CLOSED


# --- matching a city's own spelling -----------------------------------------


class TestMatching:
    """A glossary files its entries the way an index does.

    One code writes "Lot, Width" and another "lot width"; comparing whole words
    rather than characters reads both without a rule per code. Comparing
    characters would read "Streetcar Line" as an entry for *street*.
    """

    def test_a_comma_filed_entry_is_the_same_word(self) -> None:
        assert W._bag("Lot, Width") in W.forms("lot width")

    def test_a_plural_is_the_same_word(self) -> None:
        assert W._bag("Lot Widths") in W.forms("lot width")

    def test_a_qualified_entry_contains_the_word(self) -> None:
        assert W._contains(_stems("Site Frontage"), _stems("frontage"))
        assert W._contains(_stems("Street Tree"), ("street",))

    def test_a_word_glued_into_another_is_not_the_word(self) -> None:
        """The whole reason matching is on stems rather than substrings: a
        streetcar line is not a street, and a card built on it would send a
        reviewer to read the wrong entry.
        """
        assert not W._contains(_stems("Streetcar Line"), ("street",))

    def test_a_codes_own_wording_is_reached_through_spellings(self) -> None:
        """Ours is "lot area"; three codes in the corpus say "site area"."""
        assert W._bag("Site Area") in W.forms("lot area")


# --- which questions get asked ----------------------------------------------


class TestUsageGate:
    """A card exists only where the question is real.

    Two gates, and they are different. The field gate asks whether we hold a
    number the word could move; the usage gate asks whether this city's own
    text writes the word at all. Portland writes *setback* and rarely *yard*,
    and asking about a word a code does not use is how a queue teaches people
    to skim.
    """

    def test_a_word_the_code_never_writes_is_never_asked_about(self) -> None:
        layer = load_rules()[PORTLAND]
        spoken = uses(PORTLAND, list(GOVERNS))
        asked = {c.term for c in cards(layer)}
        for term, count in spoken.items():
            if count == 0:
                assert term not in asked, f"{term} asked about, never written"

    def test_every_card_names_a_field_this_jurisdiction_holds(self) -> None:
        layer = load_rules()[GRESHAM]
        held = W._held(layer)
        for card in cards(layer):
            assert card.fields
            assert not set(card.fields) - held

    def test_a_card_carries_the_cost_of_being_wrong(self) -> None:
        for card in cards(load_rules()[GRESHAM]):
            assert card.values > 0, f"{card.term} would sort last forever"

    def test_a_word_buried_inside_a_longer_word_is_not_a_use_of_it(self) -> None:
        """The gate is worth only as much as the match underneath it.

        Unbounded, *alley* matched inside "Pleasant Valley" and "Happy Valley",
        so two cities passed a gate about vehicle access on the strength of
        their own place names -- Happy Valley on 105 uses of which 14 were
        real -- and the lines the card offered as evidence were about solar
        energy systems and tree removal plans.
        """
        alley = re.compile(W._flex("alley"), re.I)
        assert not alley.search("within the Happy Valley Town Center Plan area")
        assert alley.search("Access shall be taken from the alley where one exists")
        assert alley.search("Alleys shall be paved to the property line")

        story = re.compile(W._flex("story"), re.I)
        assert not story.search("the history of the district")
        assert story.search("No building shall exceed two stories")

        yard = re.compile(W._flex("yard"), re.I)
        assert not yard.search("a courtyard or plaza open to the sky")
        assert yard.search("The required rear yard is 20 feet")



# --- the lines the code writes the word on ----------------------------------


class TestMentions:
    """What a card shows of the code itself, and why it shows the hand-offs.

    A ``silent`` card that says only "the glossary has no entry" leaves the
    reviewer to go and find out where else the word might be settled. The
    corpus usually already knows, because the code says so out loud: Portland
    defines neither *lot width* nor *building height* and points at Chapter
    33.930, Measurements, for both. Surfacing that is the difference between a
    hunt and a one-click ``elsewhere`` ruling that names the chapter.
    """

    def test_a_reference_with_no_deferring_verb_is_not_a_hand_off(self) -> None:
        assert W._sends("Maximum height 35 ft. and 33.110.215 applies to lots") == ()

    def test_a_deferring_verb_with_no_reference_is_not_a_hand_off(self) -> None:
        assert W._sends("Lot width is measured as described in this section.") == ()

    def test_a_section_does_not_send_the_reader_to_itself(self) -> None:
        """A heading prints its own number, and "33.130.200 Lot Size" sends
        nobody anywhere. Counting it would put every heading in the corpus at
        the top of a queue about where a word is defined."""
        assert W._sends("33.130.200 Lot Size. As described in 33.130.200.") == ()

    def test_the_chapter_it_does_send_to_comes_back_with_where_it_was_raised(
        self,
    ) -> None:
        line = "measured as lot width is measured. See 33.930.100."
        sent = W._sends(line)
        assert [ref for ref, _ in sent] == ["33.930.100"]
        assert sent[0][1] == line.index("33.930.100")

    def test_a_pointer_inside_the_open_chapter_is_not_leaving_the_book(self) -> None:
        """Portland's height table writes "Base Height (see 33.130.210.B.1)",
        which tells a reader of 33.130 nothing they did not have. Four lines
        away the same chapter says height is stated in Chapter 33.930, and that
        is the sentence a word card exists to surface."""
        assert not W._away("33.130", (("33.130.210", 12),))
        assert W._away("33.130", (("33.930", 12),))

    def test_a_document_whose_name_does_not_say_its_chapter_keeps_every_pointer(
        self,
    ) -> None:
        """Refusing to guess. Where the filename does not name a chapter there
        is nothing to compare against, and dropping the pointer would be us
        deciding it was local."""
        assert W._away("", (("16.42.030", 3),))

    def _corpus(self, tmp_path, monkeypatch) -> str:
        home = tmp_path / "or" / "test" / "town"
        home.mkdir(parents=True)
        (home / "19.300.txt").write_text(
            "\n".join(
                [
                    "19.300 Residential Zones",
                    "Maximum lot coverage is 40 percent of the lot area.",
                    "The lot area of a corner lot excludes the flag pole.",
                    "Lot area is measured as described in Chapter 19.100.",
                    "Minimum Lot Area (see 19.300.4) 5,000 sq ft",
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(W, "DOCS", tmp_path)
        return "or/test/town"

    def test_the_hand_off_leads_however_late_in_the_document_it_sits(
        self, tmp_path, monkeypatch
    ) -> None:
        layer_id = self._corpus(tmp_path, monkeypatch)
        counted, shown = W._scan(layer_id, ["lot area"])

        assert counted["lot area"] == 4
        first = shown["lot area"][0]
        assert first.sends == ("19.100",)
        assert "Chapter 19.100" in first.text
        assert [m.sends for m in shown["lot area"][1:]] == [("19.300.4",), (), ()]

    def test_the_ordinary_uses_stay_in_the_order_the_code_prints_them(
        self, tmp_path, monkeypatch
    ) -> None:
        """The first lines of a chapter are the code being read from the top,
        which is the right way to meet a word. Only the hand-offs are ranked."""
        layer_id = self._corpus(tmp_path, monkeypatch)
        plain = [m for m in W._scan(layer_id, ["lot area"])[1]["lot area"] if not m.sends]
        assert [m.line for m in plain] == [2, 3]

    def test_counting_alone_finds_no_lines_to_show(self, tmp_path, monkeypatch) -> None:
        """The usage gate wants a number and nothing else, and should not pay
        for the sampling. ``uses`` and a full scan must still agree."""
        layer_id = self._corpus(tmp_path, monkeypatch)
        counted, shown = W._scan(layer_id, ["lot area"], keep=0)
        assert shown == {"lot area": ()}
        assert counted == uses(layer_id, ["lot area"])

    def test_a_card_names_every_chapter_its_lines_point_at_once_each(self) -> None:
        card = _card(
            shown=(
                W.Mention(doc="a.txt", line=1, text="see 33.930", sends=("33.930",)),
                W.Mention(doc="b.txt", line=2, text="see 33.930", sends=("33.930",)),
                W.Mention(doc="b.txt", line=9, text="plain use"),
            )
        )
        assert card.sends == ("33.930",)

    def test_the_lines_shown_are_not_part_of_the_fingerprint(self) -> None:
        """Context, not testimony. These are the lines that *use* the word, not
        what the city says it means, and a fingerprint over them would reopen
        every card in the corpus every time a document was re-extracted."""
        bare = _card()
        with_lines = _card(
            shown=(W.Mention(doc="a.txt", line=1, text="see 33.930", sends=("33.930",)),)
        )
        assert bare.fingerprint == with_lines.fingerprint

    def test_portland_is_shown_the_measurements_chapter_it_defers_to(self) -> None:
        """The finding this was built for. Portland's definitions chapter runs
        to 296 entries and defines neither of these words; its own text sends
        the reader to Chapter 33.930, Measurements, for both."""
        found = {c.term: c for c in cards(load_rules()[PORTLAND])}
        for term in ("lot width", "building height"):
            card = found[term]
            assert card.standing == "silent"
            assert any(ref.startswith("33.930") for ref in card.sends), (
                f"{term} is silent and the card does not say where to look"
            )

# --- read it, or go and get it ----------------------------------------------


class TestWhatWeCanOpen:
    """A shortlist of chapters is two instructions wearing one set of clothes.

    "Go and read 33.930" and "go and fetch 33.930" are not the same morning,
    and a section number does not say which it is. Portland's silent words
    pointed at 33.930 for weeks while it was not in the store, and nothing on
    the card said so.
    """

    def test_the_shortlist_splits_into_what_we_hold_and_what_we_do_not(
        self,
    ) -> None:
        for layer_id in (PORTLAND, GRESHAM):
            for card in cards(load_rules()[layer_id]):
                assert set(card.held) | set(card.unheld) == set(card.sends)
                assert not set(card.held) & set(card.unheld)

    def test_a_chapter_we_say_we_hold_is_not_one_the_fetch_queue_wants(
        self,
    ) -> None:
        """Two ledgers, one document, one answer.

        Both sides use ``crossrefs._resolves``, and this is the reason: a card
        telling a reviewer to go and read a chapter that the fetch queue is
        still asking somebody to buy would be the corpus disagreeing with
        itself in front of the person it is asking.
        """
        from flats.encode.triage import feed

        for layer_id in (PORTLAND, GRESHAM):
            waiting = {c.ref for c in feed(layer=layer_id)}
            for card in cards(load_rules()[layer_id]):
                assert not set(card.held) & waiting, card.term

    def test_nothing_is_held_where_the_code_hands_the_word_nowhere(self) -> None:
        assert W._holds(lambda ref: True, ()) == ()

    def test_a_chapter_named_twice_is_asked_about_once(self) -> None:
        """The store test reads every document this jurisdiction owns. Asking
        it once per mention rather than once per chapter would read them all
        again for every line a card shows."""
        asked: list[str] = []

        def opens(ref: str) -> bool:
            asked.append(ref)
            return True

        shown = (
            W.Mention(doc="a.txt", line=1, text="see 33.930", sends=("33.930",)),
            W.Mention(doc="b.txt", line=9, text="see 33.930", sends=("33.930",)),
        )

        assert W._holds(opens, shown) == ("33.930",)
        assert asked == ["33.930"]


# --- what this queue owes the fetch queue -----------------------------------


class TestUndefinedHere:
    """The chapter behind a silence, handed to the queue that fetches things.

    A chapter reaches our numbers two ways and the fetch ledger could only ever
    see one of them: standing beside a standard, in the margin of a table. The
    other is being handed a *word* every one of those standards is measured in,
    which a code says once, in prose, nowhere near a value. Portland's Chapter
    33.930, Measurements, settles how height is measured on 95% of the city and
    ranked (0, 0, 0, 0) at position 69 of 75 because nothing we encode quotes a
    line near it.
    """

    LOTS = {("zz/county/town", "R5"): 700, ("zz/county/town", "R10"): 300}

    def _town(self, tmp_path, monkeypatch, *lines: str) -> Layer:
        home = tmp_path / "zz" / "county" / "town"
        home.mkdir(parents=True)
        (home / "19.300.txt").write_text("\n".join(lines), encoding="utf-8")
        monkeypatch.setattr(W, "DOCS", tmp_path)
        width = Value(
            name="min_lot_width_ft",
            value=50,
            prov=Provenance(
                cite="TMC 19.300",
                url="https://example.test/19.300",
                retrieved="2026-09-06",
            ),
        )
        return Layer(
            layer="zz/county/town",
            kind="city",
            label="Town",
            zones={"R5": Zone(zone="R5", values={"min_lot_width_ft": width})},
        )

    def test_the_chapter_a_silence_points_at_is_named_with_its_word(
        self, tmp_path, monkeypatch
    ) -> None:
        town = self._town(
            tmp_path,
            monkeypatch,
            "19.300 Residential Zones",
            "Minimum lot width is 50 feet in the R5 zone.",
            "Lot width is measured as described in Chapter 19.100, Measurements.",
        )
        found = W.undefined_here(town, self.LOTS)

        assert found["19.100"][0] == ("lot width",)
        assert found["19.100"][1] == 700

    def test_a_reference_that_settles_nothing_is_not_where_a_word_is_defined(
        self, tmp_path, monkeypatch
    ) -> None:
        """The narrowing that kept a plan-procedure chapter out of first place.

        Portland writes "shown as open space. See Chapter 33.810, Comprehensive
        Plan Amendments". That is a hand-off, and on the broad pattern it put a
        chapter about amending the comprehensive plan second in the whole city's
        fetch queue on 185,397 lots. A hand-off only says where a *word* is
        settled if it carries a verb of determining.
        """
        town = self._town(
            tmp_path,
            monkeypatch,
            "19.300 Residential Zones",
            "Minimum lot width is 50 feet in the R5 zone.",
            "Lot width is shown as open space. See Chapter 19.800, Plan Amendments.",
        )

        assert W.undefined_here(town, self.LOTS) == {}

    def test_a_pointer_that_stays_inside_its_own_chapter_hands_nothing_over(
        self, tmp_path, monkeypatch
    ) -> None:
        """"Minimum Lot Width (see 19.300.4)" tells a reader of 19.300 nothing
        they did not already have, and fetching it is not a fetch."""
        town = self._town(
            tmp_path,
            monkeypatch,
            "19.300 Residential Zones",
            "Minimum Lot Width (see 19.300.4), as defined in 19.300.4",
        )

        assert W.undefined_here(town, self.LOTS) == {}

    def test_a_word_that_moves_no_number_here_lifts_no_chapter(
        self, tmp_path, monkeypatch
    ) -> None:
        """The field gate, again. This town holds a lot width and nothing else,
        so its code's care over *building height* costs it nothing."""
        town = self._town(
            tmp_path,
            monkeypatch,
            "19.300 Residential Zones",
            "Building height is measured as described in Chapter 19.100.",
        )

        assert W.undefined_here(town, self.LOTS) == {}

    def test_the_lots_are_the_ones_behind_the_numbers_that_word_measures(
        self, tmp_path, monkeypatch
    ) -> None:
        """A layer default applies to every zone, so a word measuring a
        defaulted number reaches the whole jurisdiction rather than the one
        zone that happens to restate it."""
        town = self._town(
            tmp_path,
            monkeypatch,
            "19.300 Residential Zones",
            "Lot width is measured as described in Chapter 19.100, Measurements.",
        )
        everywhere = town.model_copy(
            update={
                "defaults": {
                    "min_lot_width_ft": Value(
                        name="min_lot_width_ft",
                        value=50,
                        prov=Provenance(
                cite="TMC 19.300",
                url="https://example.test/19.300",
                retrieved="2026-09-06",
            ),
                    )
                }
            }
        )

        assert W.undefined_here(town, self.LOTS)["19.100"][1] == 700
        assert W.undefined_here(everywhere, self.LOTS)["19.100"][1] == 1_000

    def test_only_a_word_this_glossary_leaves_alone_lifts_a_chapter(self) -> None:
        """The two callers must mean the same thing by *defined*.

        This function ranks a chapter in the fetch queue; :func:`cards` asks a
        reviewer about the same word here. If they disagreed, a chapter would
        climb to the top of one queue for a word the other shows as answered.
        """
        for layer_id in (PORTLAND, GRESHAM):
            layer = load_rules()[layer_id]
            silent = {c.term for c in cards(layer) if c.standing == "silent"}
            for chapter, (terms, _) in W.undefined_here(layer).items():
                assert not set(terms) - silent, f"{layer_id} {chapter}"


# --- the three standings ----------------------------------------------------


class TestStandings:
    """Three findings, and they are not interchangeable.

    ``defined`` is about the code and answerable now. ``silent`` is a finding
    about the code: we have read its definitions and the word is not there.
    ``unread`` is a finding about *us*, and the only one answerable without
    reading a word of code.
    """

    def test_a_word_the_glossary_carries_is_defined(self) -> None:
        found = [c for c in cards(load_rules()[GRESHAM]) if c.standing == "defined"]
        assert found
        assert all(c.says for c in found)

    def test_a_silent_word_shows_nothing_rather_than_something_close(self) -> None:
        quiet = [c for c in cards(load_rules()[PORTLAND]) if c.standing == "silent"]
        for card in quiet:
            assert not card.says
            assert not card.exact

    def test_an_entry_for_a_flavour_of_the_word_is_marked_as_such(self) -> None:
        """A code defining "Design Street" and "Street Tree" and never "street"
        has not defined the word. Said out loud on the card, because a list
        that looks like an answer is worse than no list -- the reviewer would
        read the special case as the rule.
        """
        near = [
            c
            for c in cards(load_rules()[PORTLAND])
            if c.standing == "defined" and not c.exact
        ]
        assert near, "the corpus has qualified-only entries; the flag must find them"
        for card in near:
            assert card.says

    def test_exact_entries_are_shown_first(self) -> None:
        """Leading with the qualified flavour makes a reviewer read the special
        case as the rule.
        """
        for card in cards(load_rules()[PORTLAND]):
            if not card.exact:
                continue
            first = card.says[0]
            assert W._bag(first.term) in W.forms(card.term)

    def test_the_standings_that_exist_are_the_standings_offered(self) -> None:
        rows = feed()
        assert set(counts(rows)) == set(STANDINGS)


# --- a ruling, and what it does to a card -----------------------------------


class TestRulings:
    """A card is derived, never stored. Only the ruling persists."""

    def test_an_answer_that_settles_the_word_closes_the_card(self) -> None:
        ruled = _card(
            ruling=Reading(
                queue="defined", outcome="matches", note="x" * 80, fingerprint=""
            )
        )
        assert ruled.closed

    def test_an_answer_that_orders_work_leaves_the_card_open(self) -> None:
        """"The city measures it differently" is the loudest thing this queue
        can find: numbers already in production were read against the wrong
        edge. Closing on it would file the finding and lose it.
        """
        ruled = _card(
            ruling=Reading(
                queue="defined", outcome="differs", note="x" * 80, fingerprint=""
            )
        )
        assert not ruled.closed
        assert ruled.open

    def test_a_ruling_made_against_wording_that_has_since_moved_reopens(self) -> None:
        ruled = _card(
            ruling=Reading(
                queue="defined", outcome="matches", note="x" * 80, fingerprint="stale"
            )
        )
        assert ruled.moved
        assert ruled.open

    def test_a_hand_written_ruling_carrying_no_fingerprint_is_not_drift(self) -> None:
        """It was written before the queue existed. There is nothing to
        compare, and reopening it would report a re-fetch that never happened.
        """
        ruled = _card(
            ruling=Reading(
                queue="defined", outcome="matches", note="x" * 80, fingerprint=""
            )
        )
        assert not ruled.moved
        assert not ruled.open

    def test_the_fingerprint_covers_the_standing_as_well_as_the_words(self) -> None:
        """A word going from silent to defined is the most important change
        that can happen to one of these cards, and a fingerprint over the
        entries alone would be blind to it -- there were no entries to hash.
        """
        silent = _card(standing="silent", says=(), exact=False)
        assert silent.fingerprint != _card(standing="unread", says=()).fingerprint

    def test_two_cities_answering_the_same_word_do_not_answer_for_each_other(
        self,
    ) -> None:
        """The whole finding is that the same word means different things in
        different books.
        """
        ruled = Reading(
            queue="defined", outcome="matches", note="x" * 80, fingerprint=""
        )
        rows = feed(overrides={GRESHAM: {"lot width": ruled}})
        assert not any(c.layer == GRESHAM and c.term == "lot width" for c in rows)
        assert any(c.layer != GRESHAM and c.term == "lot width" for c in rows)


# --- the queue --------------------------------------------------------------


class TestFeed:
    def test_the_heaviest_word_in_a_standing_comes_first(self) -> None:
        rows = feed("defined")
        assert rows == sorted(
            rows, key=lambda c: (-c.values, -c.lots, c.layer, c.term)
        )

    def test_lots_break_the_tie_and_never_the_rule(self) -> None:
        """Consequence is the sort, never a filter. A small city's word is
        still wrong if it is wrong.
        """
        rows = feed()
        assert any(c.lots == 0 for c in rows) or all(c.lots for c in rows)
        assert len({c.layer for c in rows}) > 1

    def test_a_standing_serves_only_its_own_cards(self) -> None:
        for standing in STANDINGS:
            assert all(c.standing == standing for c in feed(standing))

    def test_filtering_by_jurisdiction_leaves_only_that_jurisdiction(self) -> None:
        assert {c.layer for c in feed(layer=GRESHAM)} <= {GRESHAM}

    def test_filtering_by_standard_leaves_only_words_that_move_it(self) -> None:
        rows = feed(field="max_height_ft")
        assert rows
        assert all("max_height_ft" in c.fields for c in rows)

    def test_the_landing_counts_agree_with_the_queues_behind_them(self) -> None:
        got = tally()
        for standing in STANDINGS:
            rows = feed(standing)
            assert got[standing][0] == len(rows)
            assert got[standing][1] == sum(c.values for c in rows)

    def test_only_rulings_that_asked_for_something_reach_the_hand_off(self) -> None:
        closed = Reading(
            queue="defined", outcome="matches", note="x" * 80, fingerprint=""
        )
        work = Reading(
            queue="defined", outcome="differs", note="y" * 80, fingerprint=""
        )
        jobs = orders(
            overrides={GRESHAM: {"lot width": work, "lot depth": closed}}
        )
        got = {(c.layer, c.term) for c in jobs}
        assert (GRESHAM, "lot width") in got
        assert (GRESHAM, "lot depth") not in got



# --- keeping the queue honest -----------------------------------------------


class TestAudit:
    """Whether the queue would still ask what it is asking.

    Cards are derived, so a card retires itself the moment its reason goes.
    What cannot retire itself is a *ruling*, and this is the check that finds
    the two ways one goes stale: standing over a question nobody would ask
    now, and made against wording that has moved since. Run before working the
    queue, not after -- the alternative is a morning spent on a word somebody
    settled last week.
    """

    def _with(self, layer_id: str, words: dict[str, Reading]) -> dict[str, object]:
        layers = dict(load_rules())
        layers[layer_id] = layers[layer_id].model_copy(update={"words": words})
        return layers

    def test_the_corpus_asks_nothing_it_has_already_answered(self) -> None:
        assert W.audit().clean

    def test_the_audit_counts_the_queue_it_audits(self) -> None:
        """An audit that disagrees with the queue behind it is worse than
        none: it would send a reviewer looking for work that is not there."""
        found = dict(W.audit().open_by_standing)
        rows = feed()
        for standing in STANDINGS:
            assert found[standing] == sum(1 for c in rows if c.standing == standing)

    def test_a_ruling_on_a_word_nothing_rests_on_any_more_is_reported(self) -> None:
        """The word is still a word. What has gone is the reason to ask: this
        jurisdiction holds no number it governs, or its code stopped writing
        it, and either way the card is not there to carry the ruling."""
        ruling = Reading(
            queue="defined", outcome="matches", note="z" * 80, fingerprint=""
        )
        found = W.audit(self._with(GRESHAM, {"nothing rests on this": ruling}))
        assert not found.clean
        assert any("nothing rests on this" in row for row in found.settled)

    def test_a_ruling_made_against_wording_that_moved_is_reported(self) -> None:
        term = next(c.term for c in feed(layer=GRESHAM))
        stale = Reading(
            queue="defined", outcome="matches", note="q" * 80, fingerprint="0" * 16
        )
        found = W.audit(self._with(GRESHAM, {term: stale}))
        assert any(row.endswith(term) for row in found.moved)
        assert not found.settled

    def test_a_jurisdiction_the_screen_is_switched_off_for_is_not_work(self) -> None:
        """Counting a switched-off city's cards would report a morning that
        does not exist."""
        layers = dict(load_rules())
        off = [k for k, v in layers.items() if not v.eligible]
        if not off:
            pytest.skip("every jurisdiction in the corpus is switched on")
        rows = feed()
        assert sum(n for _, n in W.audit().open_by_standing) == len(rows)
        assert all(c.layer not in off for c in rows)

# --- writing a decision into the rule files ---------------------------------


class TestSplice:
    """The ruling goes into a file full of hand-written prose, in its own block
    beside the reading rulings rather than mixed in with them.
    """

    def test_a_file_with_no_words_block_gets_one(self) -> None:
        lines = ["layer: or/x", "zones:", "  R5: {}"]
        out = _splice(
            lines, "lot width", "defined", "matches", "a reason " * 10, "ff", "words"
        )
        assert "words:" in out
        assert out.index("words:") < out.index("zones:")

    def test_a_ruling_survives_a_round_trip_through_the_splice(self) -> None:
        out = _splice(
            ["words:", "layer: or/x"],
            "lot width",
            "defined",
            "differs",
            "a reason " * 10,
            "ff",
            "words",
        )
        entry = yaml.safe_load("\n".join(out))["words"]["lot width"]
        assert entry["queue"] == "defined"
        assert entry["outcome"] == "differs"
        assert entry["fingerprint"] == "ff"

    def test_ruling_the_same_word_twice_replaces_rather_than_appends(self) -> None:
        once = _splice(
            ["words:"], "lot width", "defined", "matches", "first " * 12, "ff", "words"
        )
        twice = _splice(
            once, "lot width", "defined", "differs", "second " * 12, "gg", "words"
        )
        parsed = yaml.safe_load("\n".join(twice))
        assert list(parsed["words"]) == ["lot width"]
        assert parsed["words"]["lot width"]["outcome"] == "differs"

    def test_the_reading_block_is_untouched_by_a_word_ruling(self) -> None:
        """Two ledgers in one file. A splice that wrote into the wrong block
        would answer a question nobody asked and lose the one that was."""
        lines = ["readings:", '  "a.txt#1.1":', "    queue: missed", "layer: or/x"]
        out = _splice(
            lines, "lot width", "defined", "matches", "why " * 20, "", "words"
        )
        parsed = yaml.safe_load("\n".join(out))
        assert "a.txt#1.1" in parsed["readings"]
        assert "lot width" in parsed["words"]


class TestRule:
    """The gates, checked before anything is written.

    A rule file that does not load takes every jurisdiction down with it — the
    loader accumulates problems across the corpus and refuses the set — so
    these raise rather than write.
    """

    def test_an_answer_from_another_standing_is_refused(self) -> None:
        with pytest.raises(ValueError, match="is not an answer the defined queue"):
            rule(GRESHAM, "lot width", "defined", "find_glossary", "x" * 80)

    def test_an_unknown_standing_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown standing"):
            rule(GRESHAM, "lot width", "everything", "matches", "x" * 80)

    def test_a_word_this_queue_never_asks_about_is_refused(self) -> None:
        """The term arrives from a browser form and is the key of the ledger.
        A word outside the registry would file a ruling nothing ever reads
        back.
        """
        with pytest.raises(ValueError, match="not a word this queue asks about"):
            rule(GRESHAM, "vibes", "defined", "matches", "x" * 80)

    def test_a_ruling_with_no_reasoning_is_refused(self) -> None:
        with pytest.raises(ValueError, match="characters of reasoning"):
            rule(GRESHAM, "lot width", "defined", "matches", "no")

    def test_a_layer_we_do_not_hold_is_refused(self) -> None:
        with pytest.raises(ValueError, match="not a layer we hold"):
            rule("../../../../etc/passwd", "lot width", "defined", "matches", "x" * 80)
