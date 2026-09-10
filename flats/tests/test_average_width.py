"""Two rows on one axis, and why one field could not hold them.

West Linn prints "Minimum lot width at front lot line" and, three rows under
it, "Average minimum lot width". For six of its nine residential chapters the
two figures are the same and nothing turns on the distinction. For R-15 they
are 45 and 80, and for R-10 35 and 50, and there the distinction is the whole
standard: CDC 02.030 says "Lot width. The horizontal distance between side lot
lines, measured at right angles to the lot depth. Average lot width is measured
at the midpoints of opposite lot lines." Two sentences, two lines on the
ground, two numbers a lot has to clear at once.

So a single ``min_lot_width_ft`` is wrong in both directions and there is no
safe number to put in it. Raise it to 80 and a lot forty-five feet wide at the
street and ninety feet wide across the middle is refused, and it satisfies both
rows the city wrote. Leave it at 45 and a lot forty-five feet wide the whole
way down passes, and it fails the average row. The rows want two measurements.

Two conventions from ``test_min_height.py``, for the same reasons:

* the mechanism is tested on rules written in this file, never on the corpus,
  so a test cannot go red because West Linn reworded a sentence;
* the corpus tests assert only that what is on file is internally true --
  every encoded average is quoted from a line that states it, and a zone
  holding one width and not the other is not thereby incomplete. Those hold at
  any corpus size.

The measurement rules BOTH ways or it is an amnesty. A lot measured narrow
across the middle is refused here; a lot nothing measured is left unchecked,
never refused. Both halves are pinned below, because a second width standard
that could only ever rescue a lot would not be a measurement.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("shapely")

from flats.designs.model import load_catalog  # noqa: E402
from flats.encode.extract import _subject  # noqa: E402
from flats.fit.rectangle import Fit  # noqa: E402
from flats.provenance.store import ProvenanceError, ProvenanceStore  # noqa: E402
from flats.rules.fields import FIELDS, OPTIONAL_FIELDS, REQUIRED_FIELDS  # noqa: E402
from flats.rules.loader import load_rules  # noqa: E402
from flats.rules.model import Provenance, Status  # noqa: E402
from flats.rules.resolver import Resolved, RuleSet  # noqa: E402
from flats.rules.resolver import Verdict as RuleVerdict, ZoneResolution  # noqa: E402
from flats.score.paper import paper_fit  # noqa: E402
from flats.score.screen import CHECK_FIELD, LotFacts, Triage, screen  # noqa: E402
from flats.score.slack import SlackPolicy, Verdict  # noqa: E402

pytestmark = pytest.mark.unit

FIELD = "min_average_lot_width_ft"

WHERE = "or/clackamas/west-linn"
PROV = Provenance(
    cite="West Linn CDC 10.070",
    url="https://www.codepublishing.com/OR/WestLinn/html/WestLinnCDC/WestLinnCDC10.html",
    retrieved=date(2026, 8, 19),
)
POLICY = SlackPolicy(tolerance={"fit_ft": 0.5})

DESIGN = load_catalog().latest("pod56x36")

#: Generous on everything else, so a test can break exactly one standard.
CLEAR = {
    "quadplex_allowed": True,
    "min_lot_sqft": 3000,
    "setback_front_ft": 10,
    "setback_rear_ft": 10,
    "setback_side_ft": 5,
    "min_frontage_ft": 25,
    "min_lot_width_ft": 25,
    "max_coverage_pct": 60,
    "max_far": 2.0,
    "max_height_ft": 60,
    "max_units": 4,
    "parking_min_per_unit": 1.0,
}


def rules(**overrides) -> ZoneResolution:
    values = {**CLEAR, **overrides}
    return ZoneResolution(
        jurisdiction=WHERE,
        zone="R-15",
        verdict=RuleVerdict.trusted,
        values={
            name: Resolved(
                name=name,
                value=value,
                status=Status.verified,
                prov=PROV,
                layer=WHERE,
                origin="zone",
            )
            for name, value in values.items()
            if value is not None
        },
    )


def fit() -> Fit:
    """Room to spare on everything geometric, so width is the only question."""
    depth_ft = 36.0
    best = depth_ft + DESIGN.parking.court_depth_ft + 4.0
    return Fit(
        fits=True,
        width_ft=56.0,
        depth_ft=depth_ft,
        best_depth_ft=best,
        slack_ft=best - depth_ft,
    )


def lot(*, at_front: float | None = 60.0, across: float | None = 60.0) -> LotFacts:
    """One parcel, measured on both of the lines the code names."""
    return LotFacts(
        lot_sqft=12000,
        frontage_ft=at_front or 0.0,
        lot_width_ft=at_front,
        avg_lot_width_ft=across,
    )


def run(rule_set=None, parcel: LotFacts | None = None, design=DESIGN):
    return screen(rule_set or rules(), parcel or lot(), design, fit(), policy=POLICY)


def check(result, name: str):
    """One named check off a screening result, or None if it never ran."""
    return next((c for c in result.checks if c.check == name), None)


# --- the average row is a standard, and it is tested ------------------


def test_a_lot_wide_enough_across_the_middle_clears_the_average_row() -> None:
    result = run(rules(**{FIELD: 80}), lot(at_front=60, across=90))

    assert check(result, FIELD).verdict is Verdict.passes
    assert result.triage is Triage.green


def test_a_lot_narrow_across_the_middle_does_not_clear_it() -> None:
    """No amnesty. A second measurement that could only ever rescue a lot
    would not be a measurement, and this is the half that costs."""
    result = run(rules(**{FIELD: 80}), lot(at_front=60, across=60))

    assert check(result, FIELD).verdict is not Verdict.passes
    assert result.triage is not Triage.green


# --- and it is a different standard, not a stricter reading of the other ---


def test_the_lot_the_two_fields_exist_for_clears_both_rows() -> None:
    """R-15's own numbers, on the lot the ruling was written about: forty-five
    feet wide at the street and ninety feet across the middle. It satisfies
    both rows the city wrote, and one field set to either figure gets it
    wrong -- at 80 by refusing it, at 45 by never asking the second
    question."""
    tapered = lot(at_front=45, across=90)
    both = run(rules(min_lot_width_ft=45, **{FIELD: 80}), tapered)

    assert check(both, "min_lot_width_ft").verdict is Verdict.passes
    assert check(both, FIELD).verdict is Verdict.passes
    assert both.triage is Triage.green

    one_field_raised = run(rules(min_lot_width_ft=80), tapered)
    assert check(one_field_raised, "min_lot_width_ft").verdict is not Verdict.passes


def test_a_lot_can_clear_the_average_and_fail_at_the_front_line() -> None:
    """The other direction, which is why neither field may stand in for the
    other: a flag-shaped lot pinched at the street and generous behind."""
    pinched = lot(at_front=30, across=90)
    result = run(rules(min_lot_width_ft=45, **{FIELD: 80}), pinched)

    assert check(result, "min_lot_width_ft").verdict is not Verdict.passes
    assert check(result, FIELD).verdict is Verdict.passes


def test_a_lot_can_clear_the_front_line_and_fail_the_average() -> None:
    """The shape the average row exists for: a wedge on a cul-de-sac, wide
    where it meets the street and converging behind it."""
    wedge = lot(at_front=50, across=40)
    result = run(rules(min_lot_width_ft=45, **{FIELD: 80}), wedge)

    assert check(result, "min_lot_width_ft").verdict is Verdict.passes
    assert check(result, FIELD).verdict is not Verdict.passes


# --- an unmeasured width is unchecked, never failed -------------------


def test_a_lot_nobody_measured_across_the_middle_is_not_refused() -> None:
    """The other half of ruling both ways, and the more important half. The
    measurement declines on irregular shapes and on lots with one side lot
    line; failing those on a number nobody took is the false RED this project
    exists to avoid."""
    result = run(rules(**{FIELD: 80}), lot(at_front=60, across=None))

    assert check(result, FIELD) is None
    assert FIELD in result.unchecked


def test_a_zone_that_states_no_average_width_is_still_green() -> None:
    """West Linn R-3 prints a front-line row and no average row, which is why
    the field is optional: a required field left unchecked blocks GREEN corpus
    wide, and almost every zone in Oregon states no average width at all."""
    result = run(rules(), lot(at_front=60, across=None))

    assert check(result, FIELD) is None
    assert result.triage is Triage.green


# --- the registry ------------------------------------------------------


def test_the_field_is_optional_and_reachable_from_a_check() -> None:
    assert FIELD in FIELDS
    assert FIELD in OPTIONAL_FIELDS
    assert FIELD not in REQUIRED_FIELDS
    assert FIELD in CHECK_FIELD.values()


# --- the paper lot is a rectangle, where the two lines are one line ----


def test_the_paper_lot_satisfies_the_larger_of_the_two_width_rows() -> None:
    """``paper_fit`` asks for the smallest lot the pod could legally sit on,
    and that lot is a rectangle -- so the front-line width and the average
    width are measured on the same line and the larger of them governs."""
    narrow = paper_fit(DESIGN, rules(min_lot_width_ft=45))
    both = paper_fit(DESIGN, rules(min_lot_width_ft=45, **{FIELD: 80}))

    assert both.min_width_ft >= 80
    assert both.min_width_ft >= narrow.min_width_ft


def test_the_paper_lot_is_unchanged_where_the_two_rows_agree() -> None:
    """Six of West Linn's eight restate the front-line figure. Encoding the
    second row there must cost nothing, or this field would have moved lots
    in zones where the city said the same thing twice."""
    alone = paper_fit(DESIGN, rules(min_lot_width_ft=35))
    twice = paper_fit(DESIGN, rules(min_lot_width_ft=35, **{FIELD: 35}))

    assert twice.min_width_ft == alone.min_width_ft
    assert twice.min_area_sqft == alone.min_area_sqft


# --- the reader files the two rows apart ------------------------------


def test_the_extractor_reads_an_average_row_as_the_average_field() -> None:
    """A reader that filed "Average minimum lot width 80 ft" under
    ``min_lot_width_ft`` would state 80 feet at a street edge the city asks 45
    of -- the misread this field was registered to stop."""
    assert _subject("Minimum lot width at front lot line") == "min_lot_width_ft"
    assert _subject("Average minimum lot width") == FIELD
    assert _subject("Average lot width") == FIELD


def test_an_average_lot_size_is_still_not_a_standard() -> None:
    """Springwater's VLDR preamble describes character at "an average lot size
    of 12,000 square feet". Widening the reader for one average must not have
    widened it for that one."""
    assert _subject("an average lot size of 12,000 square feet") is None


# --- what is on file, checked against the pages it came from ----------


def encoded() -> list[tuple[str, str, float, str]]:
    """Every average lot width in the corpus: layer, zone, value, quote."""
    out = []
    for name, layer in sorted(load_rules(strict=False).items()):
        for code, zone in sorted(layer.zones.items()):
            held = zone.values.get(FIELD)
            if held is None:
                continue
            prov = held.prov or layer.cite_default
            out.append((name, code, float(held.value), (prov.quote if prov else "") or ""))
    return out


def test_the_corpus_states_at_least_one_average_lot_width() -> None:
    """Not a pinned count -- a floor under one. A corpus with none would mean
    the field had been registered and never used."""
    assert encoded()


def test_every_encoded_average_width_is_quoted_from_a_line_that_states_it() -> None:
    store = ProvenanceStore()
    for layer, zone, value, quote in encoded():
        assert quote, f"{layer} {zone} states an average lot width with no quote"
        try:
            text = store.quote(quote)
        except ProvenanceError as exc:  # pragma: no cover
            pytest.fail(f"{layer} {zone} cites {quote}, which the store cannot serve: {exc}")
        digits = f"{value:g}"
        assert digits in text.replace(",", ""), (
            f"{layer} {zone} states {digits} ft but {quote} reads {text!r}"
        )


def test_a_zone_holding_one_width_and_not_the_other_is_not_incomplete() -> None:
    """The invariant ``OPTIONAL_FIELDS`` exists for, asserted where it bites.
    A code can state a width at the front lot line and no average, or an
    average and no front-line figure, and neither zone is half-read."""
    layers = load_rules(strict=False)
    rule_set = RuleSet(layers)
    seen = False
    for name, layer in sorted(layers.items()):
        for code, zone in sorted(layer.zones.items()):
            has_front = zone.values.get("min_lot_width_ft") is not None
            has_avg = zone.values.get(FIELD) is not None
            if has_front == has_avg:
                continue
            seen = True
            resolved = rule_set.resolve(name, code)
            assert FIELD not in resolved.missing_required, (
                f"{name} {code} is reported incomplete for a width row its code "
                f"does not state"
            )
    assert seen, "no zone in the corpus states one width row and not the other"
