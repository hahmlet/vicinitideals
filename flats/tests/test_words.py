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
    Reading,
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
