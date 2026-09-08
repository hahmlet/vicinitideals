"""What a sentence has to do before this ledger will call it a number.

The whole value of this check is in what it refuses. A ledger that reports
every digit in every unread line reports a thousand rows and gets read once;
one that reports only figures wearing the right unit, of a plausible size, that
the jurisdiction holds nowhere, is a few dozen and gets worked. So most of
these tests are about the refusals, and they are written on sentences copied
out of the corpus rather than invented, because the ways a zoning code puts a
number in a sentence are not guessable.

No corpus count is pinned. This ledger shrinks as the reading gets done, and a
pinned number would go red on a good day.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from pathlib import Path

from flats.encode.missed import (
    Missed,
    _figures,
    _held,
    audit,
    by_figure,
    chapter_list,
    orphans,
    render,
    report,
    score,
    score_chapters,
    work_list,
)
from flats.encode.uncited import Uncited

pytestmark = pytest.mark.unit


class _Variant:
    def __init__(self, value=None, reduce_pct=None) -> None:
        self.value = value
        self.reduce_pct = reduce_pct


class _Value:
    def __init__(self, value=None, variants=(), **printed) -> None:
        self.value = value
        self.per_dwelling = printed.get("per_dwelling")
        self.sqft_per_unit = printed.get("sqft_per_unit")
        self.variants = tuple(variants)


class _Zone:
    def __init__(self, **values: _Value) -> None:
        self.values = dict(values)


class _Layer:
    def __init__(self, defaults: dict | None = None, **zones: _Zone) -> None:
        self.zones = dict(zones)
        self.defaults = dict(defaults or {})


def _row(text: str, field: str = "max_height_ft", **kw) -> Uncited:
    return Uncited(
        layer="or/x/y",
        path="or/x/y/doc.txt",
        line=kw.get("line", 1),
        section=kw.get("section", "19.301"),
        field=field,
        text=text,
        repeats=kw.get("repeats", 1),
    )


def _run(
    text: str,
    held: _Layer | None = None,
    field: str = "max_height_ft",
    read: dict | None = None,
) -> Missed:
    layer = held if held is not None else _Layer()
    return audit([_row(text, field)], {"or/x/y": layer}, read=read or {})[0]


# --- a number has to be wearing the right unit ------------------------------


def test_a_bare_number_in_a_sentence_about_heights_is_not_a_height() -> None:
    """Milwaukie 19.303.4, and the reason this gate exists.

    "up to 2 of the development incentive bonuses" is a count of bonuses. Two
    feet is a perfectly plausible height, so no window catches this and only
    the missing unit does.
    """
    assert _figures("can utilize up to 2 of the development incentive bonuses", "length_ft") == ()


def test_the_same_number_wearing_feet_is_read() -> None:
    assert _figures("an additional 12 ft of building height", "length_ft") == (Decimal("12"),)


def test_a_bracketed_restatement_is_still_one_figure() -> None:
    """Oregon ordinances write "forty-five (45) feet" constantly."""
    assert _figures("at least forty-five (45) feet from the property line", "length_ft") == (
        Decimal("45"),
    )


def test_a_percentage_is_not_a_length() -> None:
    text = "buildings that devote 25% of the gross floor area to residential uses"
    assert _figures(text, "length_ft") == ()
    assert _figures(text, "percent") == (Decimal("25"),)


def test_an_area_is_read_in_either_unit_the_code_prints() -> None:
    assert _figures("a minimum lot area of 5,000 square feet", "area_sqft") == (Decimal("5000"),)
    assert _figures("no parcel smaller than 80 acres", "area_sqft") == (Decimal("80"),)


def test_a_field_with_no_figure_to_compare_reads_nothing() -> None:
    """A bool has no number and an enum has no order."""
    assert _figures("quadplexes are permitted outright in this district", "bool") == ()
    assert _figures("the entrance shall face the street within 45 degrees", "enum") == ()


# --- the numbers that are not standards -------------------------------------


def test_a_section_number_is_not_a_measurement() -> None:
    assert _figures("as provided in Subsection 19.301.4.C.4", "length_ft") == ()
    assert _figures("Table 4.0131 note 7 applies", "length_ft") == ()


def test_a_dotted_citation_standing_alone_is_masked() -> None:
    assert _figures("19.301.4 does not apply to accessory structures", "length_ft") == ()


def test_a_hyphenated_state_rule_number_is_masked() -> None:
    assert _figures("OAR 660-046-0220 caps the count", "count") == ()


def test_a_range_survives_the_hyphen_mask() -> None:
    """"3-5 feet" is a measurement and "660-046-0220" is not, and the rule
    that tells them apart is how many digits are on each side."""
    assert Decimal("5") in _figures("a strip 3-5 feet wide", "length_ft")


def test_an_amendment_trail_contributes_nothing() -> None:
    assert _figures("Amended by Ord. 2134, effective January 1 2019", "length_ft") == ()


def test_a_figure_outside_its_kinds_window_is_something_else() -> None:
    """A four-figure number of feet in a height sentence is a floor area."""
    assert _figures("40,000 ft", "length_ft") == ()
    assert _figures("40,000 sq ft", "area_sqft") == (Decimal("40000"),)


# --- against what the layer holds -------------------------------------------


def test_a_figure_the_layer_carries_somewhere_is_bookkeeping() -> None:
    layer = _Layer(R7=_Zone(max_height_ft=_Value(35)))
    row = _run("the maximum height is 35 ft", layer)
    assert row.verdict == "held"
    assert row.novel == ()


def test_a_figure_no_zone_carries_is_the_one_to_read() -> None:
    layer = _Layer(R7=_Zone(max_height_ft=_Value(35)))
    row = _run("an additional 12 ft of building height may be permitted", layer)
    assert row.verdict == "unheld"
    assert row.novel == (Decimal("12"),)


def test_zones_are_pooled_because_the_line_rarely_says_which_one() -> None:
    layer = _Layer(R7=_Zone(max_height_ft=_Value(35)), R10=_Zone(max_height_ft=_Value(45)))
    assert _run("45 ft", layer).verdict == "held"


def test_an_exception_counts_as_held() -> None:
    """A variant is a number in the corpus. Ignoring them would report every
    encoded exception as a standard nobody took."""
    layer = _Layer(R7=_Zone(max_height_ft=_Value(35, variants=[_Variant(45)])))
    assert _run("45 ft", layer).verdict == "held"


def test_the_figure_compared_is_the_one_printed_not_the_one_derived() -> None:
    """MCC 39.4862(C) prints 5,000 per unit and prints 20,000 nowhere.

    Comparing against the product would report the city's own sentence as a
    figure it does not hold, which is exactly backwards.
    """
    layer = _Layer(LR7=_Zone(min_lot_sqft=_Value(20000, per_dwelling=5000)))
    assert _run("5,000 square feet for each dwelling unit", layer, "min_lot_sqft").verdict == (
        "held"
    )


def test_a_line_with_no_comparable_figure_is_its_own_answer() -> None:
    row = _run("the height limit of the underlying district applies")
    assert row.verdict == "unnumbered"
    assert row.stated == ()


def test_only_the_unread_bucket_is_asked() -> None:
    """An unfielded line names no field, so there is nothing to compare to."""
    rows = audit([_row("a 20 ft height plane", field="")], {"or/x/y": _Layer()}, read={})
    assert rows == []


# --- the ranking ------------------------------------------------------------


def test_the_same_unheld_figure_stated_twice_outranks_one_stated_once() -> None:
    layer = {"or/x/y": _Layer()}
    rows = audit(
        [
            _row("an additional 12 ft of height", line=1),
            _row("an additional 12 ft of height", line=2),
            _row("a 16 ft mechanical extension", line=3),
        ],
        layer,
        read={},
    )
    ranked = by_figure(rows)
    assert ranked[0][2] == Decimal("12") and ranked[0][3] == 2


def test_repeats_are_weighted_because_a_table_reprints_its_caption() -> None:
    rows = audit(
        [_row("an additional 12 ft of height", repeats=9)], {"or/x/y": _Layer()}, read={}
    )
    assert by_figure(rows)[0][3] == 9


def test_the_report_says_it_is_a_sort_and_not_a_finding() -> None:
    text = render(audit([_row("an additional 12 ft of height")], {"or/x/y": _Layer()}, read={}))
    assert "a sort, not a finding" in text
    assert "max_height_ft = 12" in text


# --- against the real corpus, without pinning a number ----------------------


def test_every_novel_figure_really_is_absent_from_its_layer() -> None:
    from flats.rules.loader import load_rules

    layers = load_rules(strict=False)
    rows = audit(layers=layers)
    held = {lid: _held(layer) for lid, layer in layers.items()}
    for row in rows:
        for figure in row.novel:
            assert figure not in held[row.layer].get(row.field, ())


def test_every_row_carries_a_field_the_registry_knows() -> None:
    from flats.rules.fields import FIELDS

    for row in audit():
        assert row.field in FIELDS
        assert row.verdict in {"unheld", "held", "unnumbered"}


# --- how near the line sits to reading somebody already did ------------------


_SECTION = {"or/x/y/doc.txt": {"19.301": {"setback_front_ft", "max_height_ft"}}}


def test_a_row_left_in_a_table_we_took_this_standard_from_leads() -> None:
    """The shape of every missed standard this project has found by hand."""
    row = _run("an additional 12 ft of height", read=_SECTION)
    assert row.nearness == "same_field"


def test_a_section_read_for_something_else_is_the_second_tier() -> None:
    read = {"or/x/y/doc.txt": {"19.301": {"setback_front_ft"}}}
    assert _run("an additional 12 ft of height", read=read).nearness == "read_section"


def test_a_section_nothing_was_ever_quoted_from_is_a_different_job() -> None:
    assert _run("an additional 12 ft of height").nearness == "unread_section"


def test_the_ranking_puts_nearness_before_volume() -> None:
    """Ten lines in an unopened chapter do not outrank one skipped table row.

    Sorting by count alone put fences, parapets and cistern heights at the top
    of the first corpus run, because prose about heights is everywhere and a
    missed table row is one line.
    """

    def _made(figure: str, line: int, read_here: tuple[str, ...]) -> Missed:
        return Missed(
            layer="or/x/y",
            field="max_height_ft",
            path="or/x/y/doc.txt",
            line=line,
            section="19.301",
            text=f"{figure} ft",
            stated=(Decimal(figure),),
            held=(),
            matched=(),
            read_here=read_here,
        )

    rows = [_made("12", n, ()) for n in range(2, 12)]
    rows.append(_made("16", 1, ("max_height_ft",)))
    ranked = by_figure(rows)
    assert ranked[0][2] == Decimal("16")
    assert ranked[0][4] == "same_field"
    assert ranked[1][4] == "unread_section"


def test_the_report_names_its_three_tiers() -> None:
    text = render(audit([_row("an additional 12 ft of height")], {"or/x/y": _Layer()}, read={}))
    assert "in a section we took THIS standard from" in text
    assert "unread_section" in text


# --- the reading queue ------------------------------------------------------


class _Store:
    """Just enough of the provenance store to hand back a document."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def text_path(self, path: str):
        import tempfile

        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        )
        handle.write("\n".join(self._lines))
        handle.close()
        return Path(handle.name)


def _made(**kw) -> Missed:
    base = dict(
        layer="or/x/y",
        field="max_height_ft",
        path="or/x/y/doc.txt",
        line=3,
        section="19.301",
        text="the maximum height is 24 ft",
        stated=(Decimal("24"),),
        held=(Decimal("35"),),
        matched=(),
        repeats=1,
        read_here=("max_height_ft",),
    )
    base.update(kw)
    return Missed(**base)


_DOC = ["Table 19.301.4", "Standard", "the maximum height is 24 ft", "next row", "and another"]


def test_the_card_never_carries_the_number_we_hold() -> None:
    """The one property that makes the answer worth having.

    A reader shown "we hold 35" agrees with 35. The card carries the page and
    nothing this corpus concluded from it -- not the figure, and not even which
    standard we guessed the line was about.
    """
    cards, key, _ = work_list([_made()], _Store(_DOC))
    assert set(cards[0]) == {
        "id",
        "jurisdiction",
        "document",
        "cited_lines",
        "section",
        "headings",
        "passage",
    }
    assert "held" in key[0] and "field" in key[0] and "stated" in key[0]


def test_the_marked_line_is_the_one_being_asked_about() -> None:
    cards, _, _ = work_list([_made()], _Store(_DOC))
    marked = [line for line in cards[0]["passage"] if line.startswith(">>")]
    assert len(marked) == 1
    assert "maximum height is 24 ft" in marked[0]


def test_a_held_or_unnumbered_line_is_not_asked() -> None:
    cards, _, skipped = work_list(
        [_made(matched=(Decimal("35"),), stated=(Decimal("35"),))], _Store(_DOC)
    )
    assert cards == [] and skipped["held_or_unnumbered"] == 1


def test_an_unopened_chapter_is_a_different_question() -> None:
    cards, _, skipped = work_list([_made(read_here=())], _Store(_DOC))
    assert cards == [] and skipped["far_tier"] == 1


def test_the_far_tier_can_be_asked_for_deliberately() -> None:
    cards, _, _ = work_list([_made(read_here=())], _Store(_DOC), tiers=("unread_section",))
    assert len(cards) == 1


def test_a_city_nobody_screens_is_not_reading_work() -> None:
    """The first run of this queue spent a seventh of itself on excluded land.

    26 of 185 cards, and 8 of the 29 findings, were Lake Oswego and Rivergrove
    -- one shut off by an owner decision about the Mountain Park PUD, three
    too small to be under the state's fourplex mandate. A finding there is a
    true statement about a code nobody is screening.
    """
    cards, _, skipped = work_list([_made()], _Store(_DOC), off={"or/x/y"})
    assert cards == [] and skipped["switched_off"] == 1


def test_an_excluded_city_comes_back_when_it_is_asked_for() -> None:
    cards, _, skipped = work_list(
        [_made()], _Store(_DOC), off={"or/x/y"}, include_off=True
    )
    assert len(cards) == 1 and skipped["switched_off"] == 0


# --- a standard everybody else regulates ------------------------------------


def _peers(n: int, field: str = "setback_garage_entrance_ft") -> dict:
    return {
        f"or/x/peer{i}": _Layer(**{"Z": _Zone(**{field: _Value(20)})}) for i in range(n)
    }


def test_a_field_every_neighbour_holds_and_this_city_does_not_is_asked() -> None:
    """West Linn, and the accident this check was written from.

    Nine zones, all complete, and no garage-entrance setback in any of them --
    while ten of fourteen screened cities hold one and West Linn's own access
    chapter states 20 feet. No coverage ledger sees that, because the field is
    not required.
    """
    layers = {**_peers(9), "or/x/y": _Layer(Z=_Zone(max_height_ft=_Value(35)))}
    row = _made(field="setback_garage_entrance_ft")
    # `declared=()` asks the question the way it was asked on 2026-09-08, before
    # the answer -- the pod has no garage -- was written into `paper.py`. The
    # shape being pinned here is the check, not the corpus's live state.
    found = orphans([row], layers, declared=())
    assert [(o.layer, o.field, o.peers, o.total) for o in found] == [
        ("or/x/y", "setback_garage_entrance_ft", 9, 10)
    ]


def test_a_city_that_holds_the_field_somewhere_is_not_a_gap() -> None:
    layers = {
        **_peers(9),
        "or/x/y": _Layer(Z=_Zone(setback_garage_entrance_ft=_Value(20))),
    }
    assert orphans([_made(field="setback_garage_entrance_ft")], layers) == []


def test_a_recorded_no_standard_counts_as_holding_it() -> None:
    """A value written down as None is an answer somebody gave, not a gap."""
    layers = {
        **_peers(9),
        "or/x/y": _Layer(Z=_Zone(setback_garage_entrance_ft=_Value(None))),
    }
    assert orphans([_made(field="setback_garage_entrance_ft")], layers) == []


def test_a_field_only_a_few_cities_regulate_is_ordinary_variation() -> None:
    """Gresham has no residential lot coverage standard and that is correct."""
    others = {
        f"or/x/other{i}": _Layer(Z=_Zone(max_height_ft=_Value(35))) for i in range(8)
    }
    layers = {
        **_peers(2),
        **others,
        "or/x/y": _Layer(Z=_Zone(max_height_ft=_Value(35))),
    }
    assert orphans([_made(field="setback_garage_entrance_ft")], layers) == []


def test_a_city_the_screen_does_not_cover_is_neither_gap_nor_peer() -> None:
    layers = {**_peers(9), "or/x/y": _Layer(Z=_Zone(max_height_ft=_Value(35)))}
    assert orphans([_made(field="setback_garage_entrance_ft")], layers, off={"or/x/y"}) == []


def test_a_held_line_does_not_raise_a_gap() -> None:
    """The city's own code has to have said something we never took."""
    layers = {**_peers(9), "or/x/y": _Layer(Z=_Zone(max_height_ft=_Value(35)))}
    row = _made(
        field="setback_garage_entrance_ft",
        matched=(Decimal("24"),),
        stated=(Decimal("24"),),
    )
    assert orphans([row], layers) == []


def test_a_section_card_asks_about_every_unread_line_at_once() -> None:
    """89 of 144 unopened sections hold one line; the largest holds 34.

    A per-line card would ask the largest of them thirty-four times and buy
    thirty-four copies of one answer.
    """
    rows = [
        _made(line=3, read_here=(), text="the maximum height is 24 ft"),
        _made(line=4, read_here=(), text="next row"),
    ]
    cards, key, _ = chapter_list(rows, _Store(_DOC))
    assert len(cards) == 1
    marked = [line for line in cards[0]["passage"] if line.startswith(">>")]
    assert len(marked) == 2
    assert cards[0]["marked_lines"] == "L3, L4"
    assert key[0]["lines"] == [3, 4]


def test_a_section_card_carries_no_guess_of_ours_either() -> None:
    cards, key, _ = chapter_list([_made(read_here=())], _Store(_DOC))
    assert set(cards[0]) == {
        "id",
        "jurisdiction",
        "document",
        "section",
        "headings",
        "marked_lines",
        "passage",
    }
    assert key[0]["fields"] == ["max_height_ft"]


def test_only_the_unopened_tier_becomes_a_section_card() -> None:
    cards, _, skipped = chapter_list([_made()], _Store(_DOC))
    assert cards == [] and skipped["not_the_far_tier"] == 1


def test_a_section_in_a_city_nobody_screens_is_not_asked() -> None:
    cards, _, skipped = chapter_list([_made(read_here=())], _Store(_DOC), off={"or/x/y"})
    assert cards == [] and skipped["switched_off"] == 1


def test_the_biggest_section_is_the_first_card() -> None:
    rows = [
        _made(line=3, section="small", read_here=()),
        _made(line=3, section="big", read_here=()),
        _made(line=4, section="big", read_here=()),
    ]
    cards, _, _ = chapter_list(rows, _Store(_DOC))
    assert [c["section"] for c in cards] == ["big", "small"]


def _chapter_key() -> list[dict]:
    return [
        {
            "id": "00000",
            "layer": "or/x/y",
            "path": "or/x/y/doc.txt",
            "section": "19.301",
            "lines": [3],
            "fields": ["max_height_ft"],
            "texts": ["the maximum height is 24 ft"],
        }
    ]


def test_an_unopened_section_with_nothing_in_it_closes() -> None:
    rows = score_chapters(_chapter_key(), {"00000": {"binds": "no"}}, layers={})
    assert rows[0]["verdict"] == "agree"


def test_a_figure_printed_nowhere_in_that_city_is_worth_reading() -> None:
    rows = score_chapters(
        _chapter_key(), {"00000": {"binds": "yes", "number": "24"}}, layers={}
    )
    assert rows[0]["verdict"] == "worth_reading"


def test_a_figure_the_city_prints_somewhere_is_the_weaker_answer() -> None:
    layer = _Layer(A=_Zone(max_height_ft=_Value(35)))
    rows = score_chapters(
        _chapter_key(),
        {"00000": {"binds": "yes", "number": "35"}},
        layers={"or/x/y": layer},
    )
    assert rows[0]["verdict"] == "seen_elsewhere"


def test_the_ledger_still_counts_what_the_reading_queue_drops() -> None:
    """A ledger that hides excluded land cannot be told from a finished one.

    Same split as the crossref and triage queues: the count keeps everything
    and says so, and only the queue somebody has to *work* is narrowed.
    """
    out = render([_made()], off={"or/x/y"})
    assert "unread statements naming a field we screen on: 1" in out
    assert "in cities the screen does not cover: 1" in out
    assert "[SWITCHED OFF -- not screened]" in out


# --- scoring the readings ---------------------------------------------------


def _key(**kw) -> list[dict]:
    row = {
        "id": "00000",
        "layer": "or/x/y",
        "field": "max_height_ft",
        "path": "or/x/y/doc.txt",
        "line": 3,
        "section": "19.301",
        "nearness": "same_field",
        "repeats": 1,
        "text": "the maximum height is 24 ft",
        "stated": ["24"],
        "held": ["35"],
    }
    row.update(kw)
    return [row]


def _verdict(**answer) -> str:
    return score(_key(), {"00000": answer})[0]["verdict"]


def test_a_reader_who_says_it_does_not_bind_agrees_with_us() -> None:
    assert _verdict(binds="no", about="fences") == "agree"


def test_a_figure_we_carry_elsewhere_means_our_reader_took_it_off_another_row() -> None:
    assert _verdict(binds="yes", number="35") == "already_held"


def test_a_figure_we_carry_nowhere_is_the_finding() -> None:
    assert _verdict(binds="yes", number="24") == "missed"


def test_an_unanswered_card_is_not_an_agreement() -> None:
    assert score(_key(), {})[0]["verdict"] == "missing"


def test_a_reader_who_cannot_tell_says_so() -> None:
    assert _verdict(binds="unclear", note="the column head did not extract") == "unclear"


def test_a_number_is_read_out_of_whatever_the_reader_typed() -> None:
    assert _verdict(binds="yes", number="35 ft") == "already_held"
    assert _verdict(binds="yes", number="5,000") == "missed"
    assert _verdict(binds="yes", number="") == "missed"


def test_the_report_leads_with_the_findings() -> None:
    rows = score(_key(), {"00000": {"binds": "yes", "number": "24", "standard": "height"}})
    text = report(rows)
    assert "A STANDARD THIS CORPUS HOLDS NOWHERE: 1" in text
    assert "in a section we took that very standard from: 1" in text


def test_a_standard_the_screen_says_it_leaves_out_is_not_asked_again() -> None:
    """The 2026-09-08 ruling, made durable.

    Both real rows of this check's first run were garage-entrance setbacks,
    and the answer turned out to be one sentence about our own building rather
    than anything about Oregon. `paper.py` now names the field in
    `PaperFit.excluded`, and a question whose answer is already written down is
    not a question -- so the live default reads those declarations and drops it.
    """
    layers = {**_peers(9), "or/x/y": _Layer(Z=_Zone(max_height_ft=_Value(35)))}
    row = _made(field="setback_garage_entrance_ft")

    assert orphans([row], layers) == []
    assert orphans([row], layers, declared=()) != []


def test_a_field_nothing_happens_to_read_is_still_asked() -> None:
    """Only a *declared* exclusion closes the question. A field no screen reads
    is a different state: the asymmetry may be the very reason it should be
    read, and silently dropping it would hide the case this check exists for.
    """
    layers = {
        **_peers(9, field="min_lot_depth_ft"),
        "or/x/y": _Layer(Z=_Zone(max_height_ft=_Value(35))),
    }
    row = _made(field="min_lot_depth_ft")

    found = orphans([row], layers)
    assert [(o.layer, o.field) for o in found] == [("or/x/y", "min_lot_depth_ft")]
