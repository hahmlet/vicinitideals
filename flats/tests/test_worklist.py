"""Four queues, and the rules that decide which one a section lands in.

The reading ledger is right and unworkable: 4,693 rows, one per statement,
grouped by city. Every city says the same word, so the grouping carries no
information, and the unit it prints is not the unit anybody decides in. The
same lines are 649 sections, and a section is one decision.

What these tests hold down is the routing, because routing by guesswork is how
this queue would quietly become furniture. Two facts decide it and both are
already known: does the line name a field the screen holds, and has anything
in that chapter ever been quoted. A keyword classifier was tried on the same
corpus and left 43% of it unsorted; nothing here classifies by keyword except
the one thing keywords can honestly find, which is whether a sentence hangs
its number on a condition.

The other half is the ranking. A card where the code prints a figure we hold a
different one for is a finding; a card where the figures match is bookkeeping,
and there are far more of the second. If the second sorts first, nobody ever
reaches the first.
"""

from __future__ import annotations

import pytest
import yaml

from flats.encode.uncited import Uncited
from flats.encode.worklist import (
    KINDS,
    QUEUES,
    Card,
    Line,
    _kind,
    _numbers,
    _rank,
    _splice,
    audit,
    cards,
    counts,
    feed,
    render,
    rule,
)
from flats.rules.loader import load_rules
from flats.rules.model import READING_CLOSED, READING_OUTCOMES, Layer, Reading

pytestmark = pytest.mark.unit

MILWAUKIE = "or/clackamas/milwaukie"
LAKE_OSWEGO = "or/clackamas/lake-oswego"


@pytest.fixture(scope="module")
def layers() -> dict[str, Layer]:
    return load_rules()


def _line(text: str, *, field: str = "max_height_ft", held: tuple[float, ...] = ()) -> Line:
    return Line(
        line=1,
        field=field,
        text=text,
        repeats=1,
        numbers=_numbers(text),
        held=held,
    )


def _card(**kw: object) -> Card:
    base: dict[str, object] = {
        "layer": MILWAUKIE,
        "path": f"{MILWAUKIE}/19.300.base-zones.txt",
        "section": "19.301",
        "kind": "missed",
        "lines": (_line("Maximum height: 35 ft", held=(35.0,)),),
    }
    base.update(kw)
    return Card(**base)  # type: ignore[arg-type]


def _uncited(text: str, *, field: str = "", line: int = 1, section: str = "19.301") -> Uncited:
    return Uncited(
        layer=MILWAUKIE,
        path=f"{MILWAUKIE}/19.300.base-zones.txt",
        line=line,
        section=section,
        field=field,
        text=text,
    )


# --- reading the figures out of a sentence ---------------------------------


def test_a_section_number_is_not_a_measurement() -> None:
    """The comparison is worthless if every citation reads as a figure.

    "MMC 19.301.4" carries 19.301 and 4 under any plain numeral pattern, and a
    line that cites its own section would then disagree with everything we
    hold. Two dots or more is the test: codes number by containment and no
    standard is ever written 35.0.0.
    """
    assert _numbers("See 19.301.4 for the standard") == ()
    assert _numbers("Per 33.120.205.C, height is 35 ft") == (35.0,)


def test_a_number_written_twice_is_counted_once() -> None:
    """Drafters write "twelve (12) feet". One figure, not two."""
    assert _numbers("a minimum width of twelve (12) feet") == (12.0,)


def test_a_thousands_comma_does_not_make_two_numbers() -> None:
    """A table printing 5,000 and prose printing 5000 state the same standard."""
    assert _numbers("5,000 square feet") == _numbers("5000 square feet") == (5000.0,)


# --- what the comparison can and cannot say --------------------------------


def test_holding_nothing_is_not_agreement() -> None:
    """Three-valued on purpose.

    "We hold nothing to compare against" and "we hold something and it
    differs" are opposite findings. A boolean would file the first as
    agreement, which is the shape of every silent miss this project has had.
    """
    assert _line("Maximum height: 35 ft", held=()).agrees is None
    assert _line("Maximum height: 35 ft", held=(35.0,)).agrees is True
    assert _line("Maximum height: 40 ft", held=(35.0,)).agrees is False


def test_a_line_with_no_field_is_never_compared() -> None:
    """There is nothing to compare a fieldless measure against."""
    assert _line("The plane rises at 45 degrees", field="", held=(35.0,)).agrees is None


# --- routing ----------------------------------------------------------------


def test_an_unquoted_chapter_never_routes_as_a_missed_standard() -> None:
    """Nobody read it, so nobody skipped a line in it.

    A section in a chapter our encoding has never quoted is a door, not a
    line: the decision is whether to open it at all. Routing one of those into
    the missed-standards queue would put a reviewer to work comparing figures
    inside a chapter nobody has established is about this building.
    """
    rows = [_uncited("Maximum height: 40 ft", field="max_height_ft")]
    assert _kind(rows, quoted=False) == "chapter"
    assert _kind(rows, quoted=True) == "missed"


def test_a_measure_with_no_field_behind_it_is_bulk() -> None:
    rows = [_uncited("The plane rises at 45 degrees")]
    assert _kind(rows, quoted=True) == "nofield"


def test_a_condition_outranks_a_flat_standard_in_the_same_section() -> None:
    """Precedence, not a score.

    A section carries lines of more than one shape and splitting it would put
    the same page in two queues on the same day. The strongest signal in it
    decides where the whole card goes, and a conditional number is the
    stronger one: reading it flat is how an exception gets encoded as a rule.
    """
    flat = _uncited("Maximum height: 35 ft", field="max_height_ft", line=1)
    conditional = _uncited(
        "except on a corner lot, where the maximum is 40 ft",
        field="max_height_ft",
        line=2,
    )
    assert _kind([flat], quoted=True) == "missed"
    assert _kind([flat, conditional], quoted=True) == "condition"


def test_a_fieldless_condition_does_not_promote_the_card() -> None:
    """Only a line naming a field we hold can make the card about a number.

    Otherwise every ``nofield`` section containing the word "except" — which
    is most of them — arrives in the queue for judging conditions on standards
    we do not have.
    """
    rows = [_uncited("Fences may be 8 ft except where the alley abuts")]
    assert _kind(rows, quoted=True) == "nofield"


# --- ranking ----------------------------------------------------------------


def test_a_disagreement_sorts_above_everything_that_agrees() -> None:
    """The single biggest lever on this queue.

    Most cards confirm a figure we already hold; a handful print a different
    one. Ranked by consequence alone, Portland's bulk would bury every finding
    in the corpus, and the queue would be worked from the top for a week
    without reaching one.
    """
    agrees = _card(lines=(_line("35 ft", held=(35.0,)),), lots=999_999)
    disagrees = _card(lines=(_line("40 ft", held=(35.0,)),), lots=1)

    assert sorted([agrees, disagrees], key=_rank)[0] is disagrees


def test_lots_break_the_tie_and_never_the_rule() -> None:
    """Consequence is the sort, not a filter — the 2026-08-22 design, kept."""
    small = _card(lines=(_line("40 ft", held=(35.0,)),), lots=10, section="a")
    large = _card(lines=(_line("40 ft", held=(35.0,)),), lots=10_000, section="b")

    assert sorted([small, large], key=_rank)[0] is large


def test_a_card_we_hold_nothing_for_outranks_one_that_matches() -> None:
    """Between bookkeeping and an unmeasured standard, the unknown wins."""
    matches = _card(lines=(_line("35 ft", held=(35.0,)),))
    unknown = _card(lines=(_line("35 ft", held=()),))

    assert sorted([matches, unknown], key=_rank)[0] is unknown


# --- the fingerprint --------------------------------------------------------


def test_the_fingerprint_moves_when_the_section_does() -> None:
    """A ruling remembers what it was about.

    When a document is re-fetched and the section moves, a ruling stored
    against the old text must not silently keep the card closed. The
    fingerprint is what makes that visible, and it is the same bargain a
    signature strikes over a number and its citation.
    """
    before = _card(lines=(_line("35 ft", held=(35.0,)),))
    after = _card(lines=(_line("40 ft", held=(35.0,)),))

    assert before.fingerprint != after.fingerprint
    assert before.fingerprint == _card(lines=(_line("35 ft", held=(35.0,)),)).fingerprint


# --- against the real corpus ------------------------------------------------


def test_every_card_lands_in_exactly_one_queue(layers: dict[str, Layer]) -> None:
    made = cards(layers[MILWAUKIE])
    assert made, "Milwaukie has uncited statements; if it does not, the ledger broke"
    assert {c.kind for c in made} <= set(KINDS)
    assert len({c.key for c in made}) == len(made), "one card per section, no duplicates"


def test_the_queues_partition_the_ledger(layers: dict[str, Layer]) -> None:
    """Every line in the ledger is behind exactly one card.

    The queue is a regrouping, not a filter. A line that falls out of it is a
    line nobody will ever be asked about again, which is the failure this
    whole subsystem exists to prevent.
    """
    from flats.encode.uncited import survey

    rows = survey([layers[MILWAUKIE]])
    made = cards(layers[MILWAUKIE], rows=rows)
    assert sum(len(c.lines) for c in made) == len(rows)


def test_a_switched_off_jurisdiction_is_out_of_the_feed(layers: dict[str, Layer]) -> None:
    """Lake Oswego's dimensional chapter is the largest block of
    disagreements in the corpus, and none of its lots is ever scored.

    Left in, it takes the top of the missed-standards queue and the first
    morning of reading goes to a city the screen does not cover. It is a
    filter and not a ruling — the lines are real and unread — so the feed
    hides them by default and hands them back on request.
    """
    assert not layers[LAKE_OSWEGO].eligible

    shown = feed("missed", layers, rows=[], layer=None)
    assert LAKE_OSWEGO not in {c.layer for c in shown}

    asked = feed("missed", layers, layer=LAKE_OSWEGO)
    assert asked, "naming it explicitly still works"


def test_an_unknown_queue_is_refused(layers: dict[str, Layer]) -> None:
    with pytest.raises(ValueError, match="unknown queue"):
        feed("everything", layers)


def test_every_queue_has_a_question_for_a_person() -> None:
    """A queue nobody can state the question of is a queue nobody works."""
    assert set(QUEUES) == set(KINDS)
    for title, question in QUEUES.values():
        assert title and question.endswith("?")


def test_the_counts_add_up(layers: dict[str, Layer]) -> None:
    from flats.encode.uncited import survey

    one = {MILWAUKIE: layers[MILWAUKIE]}
    rows = survey([layers[MILWAUKIE]])
    tally = counts(one, rows=rows)

    assert set(tally) == set(KINDS)
    assert sum(lines for _, lines in tally.values()) == len(rows)


def test_an_empty_queue_says_so() -> None:
    assert "nothing in this queue" in render([])


# --- writing a decision into the rule files ---------------------------------


class TestSplice:
    """A ruling goes into a file full of hand-written prose, so it has to land
    where a person would have put it and read like the rest.
    """

    def test_a_file_with_no_readings_block_gets_one(self) -> None:
        lines = ["layer: or/x", "zones:", "  R5: {}"]
        out = _splice(lines, "a.txt#1.1", "nofield", "design", "a reason " * 10, "ff")

        assert "readings:" in out
        assert out.index("readings:") < out.index("zones:"), (
            "beside the layer-wide bookkeeping, not after two thousand lines of zones"
        )

    def test_a_ruling_survives_a_round_trip_through_the_splice(self) -> None:
        lines = ["readings:", "layer: or/x"]
        out = _splice(lines, "a.txt#1.1", "missed", "duplicate", "a reason " * 10, "ff")
        parsed = yaml.safe_load("\n".join(out))

        entry = parsed["readings"]["a.txt#1.1"]
        assert entry["queue"] == "missed"
        assert entry["outcome"] == "duplicate"
        assert entry["fingerprint"] == "ff"
        assert entry["note"].startswith("a reason")

    def test_ruling_the_same_card_twice_replaces_rather_than_appends(self) -> None:
        """Otherwise the file grows a second answer to the same question and
        the loader takes whichever YAML happens to keep.
        """
        lines = ["readings:", "layer: or/x"]
        once = _splice(lines, "a.txt#1.1", "missed", "duplicate", "first " * 12, "ff")
        twice = _splice(once, "a.txt#1.1", "missed", "encode", "second " * 12, "gg")
        parsed = yaml.safe_load("\n".join(twice))

        assert list(parsed["readings"]) == ["a.txt#1.1"]
        assert parsed["readings"]["a.txt#1.1"]["outcome"] == "encode"

    def test_a_fingerprintless_ruling_writes_no_fingerprint_line(self) -> None:
        """A hand-written ruling has nothing to compare, and an empty string
        in the file would look like a fingerprint that failed to match.
        """
        out = _splice(["readings:"], "a.txt#1.1", "nofield", "design", "why " * 20, "")
        assert not any("fingerprint" in ln for ln in out)


class TestRule:
    """The gates, checked before anything is written.

    A rule file that does not load takes every jurisdiction down with it -- the
    loader accumulates problems across the corpus and refuses the set -- so
    these raise rather than write.
    """

    def test_an_outcome_from_another_queue_is_refused(self) -> None:
        """The keying is the design, not decoration.

        "Different building" is a real answer to a section we have no field
        for and a meaningless one to a chapter nobody has opened. A ruling that
        answers a question it was not asked reads fine and means nothing.
        """
        with pytest.raises(ValueError, match="is not an answer the chapter queue"):
            rule(MILWAUKIE, "a.txt#1.1", "chapter", "other_building", "x" * 80)

    def test_an_unknown_queue_is_refused_by_the_writer(self) -> None:
        with pytest.raises(ValueError, match="unknown queue"):
            rule(MILWAUKIE, "a.txt#1.1", "everything", "design", "x" * 80)

    def test_a_ruling_with_no_reasoning_is_refused(self) -> None:
        """A card closed with a word nobody can check is worse than an open
        one: the open one still shows the sentence.
        """
        with pytest.raises(ValueError, match="characters of reasoning"):
            rule(MILWAUKIE, "a.txt#1.1", "nofield", "design", "no")

    def test_a_layer_we_do_not_hold_is_refused(self) -> None:
        """The id arrives from a browser form and everything past it writes."""
        with pytest.raises(ValueError, match="not a layer we hold"):
            rule("../../../../etc/passwd", "a.txt#1.1", "nofield", "design", "x" * 80)


# --- a ruling that has outlived what it was about ---------------------------


class TestDrift:
    """The queue must not outlive its reasons.

    Two ways it would. A ruling can be written about text that later moves,
    and a card can stop existing because somebody encoded the value -- the
    first has to reopen and the second has to disappear on its own.
    """

    def test_a_ruling_whose_section_moved_reopens(self) -> None:
        ruled = _card(
            lines=(_line("35 ft", held=(35.0,)),),
            ruling=Reading(
                queue="missed", outcome="duplicate", note="x" * 80, fingerprint="stale"
            ),
        )

        assert ruled.moved
        assert ruled.open, "a decision about words nobody has seen since is not one"

    def test_a_ruling_that_still_matches_stays_closed(self) -> None:
        card = _card(lines=(_line("35 ft", held=(35.0,)),))
        ruled = _card(
            lines=card.lines,
            ruling=Reading(
                queue="missed",
                outcome="duplicate",
                note="x" * 80,
                fingerprint=card.fingerprint,
            ),
        )

        assert not ruled.moved
        assert not ruled.open

    def test_a_hand_written_ruling_with_no_fingerprint_is_not_drift(self) -> None:
        """Nothing to compare is not a mismatch. Treating it as one would
        reopen every ruling written before the queues existed.
        """
        ruled = _card(ruling=Reading(queue="missed", outcome="duplicate", note="x" * 80))

        assert not ruled.moved
        assert not ruled.open

    def test_an_outcome_that_orders_work_keeps_the_card_open(self) -> None:
        """``encode`` is work ordered, not work finished. A queue that hid it
        would report a decision as a disposal.
        """
        ordered = _card(ruling=Reading(queue="missed", outcome="encode", note="x" * 80))
        closed = _card(ruling=Reading(queue="missed", outcome="not_here", note="x" * 80))

        assert ordered.open and not closed.open

    def test_the_audit_reports_a_clean_corpus_as_clean(
        self, layers: dict[str, Layer]
    ) -> None:
        from flats.encode.uncited import survey

        one = {MILWAUKIE: layers[MILWAUKIE]}
        report = audit(one, rows=survey([layers[MILWAUKIE]]))

        assert report.clean, "no rulings written yet, so nothing can have gone stale"
        assert dict(report.open_by_queue).keys() == set(KINDS)


# --- the vocabulary ---------------------------------------------------------


def test_every_queue_offers_a_way_to_close_and_a_way_to_act() -> None:
    """A queue with no closing answer never empties; a queue with no opening
    answer cannot record a find, which is the only reason to read at all.
    """
    for kind, outcomes in READING_OUTCOMES.items():
        closing = [o for o in outcomes if o in READING_CLOSED]
        acting = [o for o in outcomes if o not in READING_CLOSED]
        assert closing, f"{kind} can never be finished"
        assert acting, f"{kind} can never record a find"


def test_an_outcome_named_by_two_queues_means_one_thing() -> None:
    """Two screens showing the same word for different things is how a
    vocabulary stops being countable.
    """
    seen: dict[str, str] = {}
    for outcomes in READING_OUTCOMES.values():
        for key, why in outcomes.items():
            assert seen.setdefault(key, why) == why
