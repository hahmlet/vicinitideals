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
    render,
    report,
    score,
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
    def __init__(self, **zones: _Zone) -> None:
        self.zones = dict(zones)


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
