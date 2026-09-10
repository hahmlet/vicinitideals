"""A height standard that is a floor, and the one direction that costs a GREEN.

Every other bulk standard in this registry is a ceiling, and a ceiling nobody
encoded is safe in a boring way: the screen simply does not test it, and the
building is no more likely to pass than it deserves. A *floor* inverts that. A
minimum building height nobody encoded lets a design that is too short walk
through as GREEN, and it is the only shape in the corpus where an unheld
standard buys a verdict rather than costing one.

Which is why the field exists even though it binds on nothing today. Both
catalogued pods stand about twenty-six feet over two storeys and clear all five
encoded instances, so this whole module is currently a test of machinery with
no live consequence -- and that is the argument for building it now rather than
the argument against. The design the accessible-stall reading points at is a
SINGLE-STOREY flat, and a single-storey flat is exactly what these four
mixed-use districts were written to keep off a main street.

Two conventions from ``test_stale.py`` are kept, for the same reasons:

* the mechanism is tested on rules written in this file, never on the corpus,
  so a test cannot go red because Oregon City reworded a sentence;
* the corpus tests assert only that what is on file is internally true -- that
  every encoded floor is quoted from a line that states one, and that no floor
  sits above its own zone's ceiling. Those hold at any corpus size.

The one thing asserted about a *count* is asserted at zero: no zone may state a
minimum height this screen would silently skip.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("shapely")

from flats.designs.model import load_catalog  # noqa: E402
from flats.fit.rectangle import Fit  # noqa: E402
from flats.provenance.store import ProvenanceStore  # noqa: E402
from flats.rules.fields import OPTIONAL_FIELDS, REQUIRED_FIELDS, FIELDS  # noqa: E402
from flats.rules.loader import load_rules  # noqa: E402
from flats.rules.model import Provenance, Status  # noqa: E402
from flats.rules.resolver import Resolved, Verdict as RuleVerdict, ZoneResolution  # noqa: E402
from flats.score.paper import _height_ok  # noqa: E402
from flats.score.screen import CHECK_FIELD, LotFacts, Triage, screen  # noqa: E402
from flats.score.slack import SlackPolicy, Verdict  # noqa: E402

pytestmark = pytest.mark.unit

WHERE = "or/multnomah/portland"
PROV = Provenance(
    cite="PCC 33.110.220",
    url="https://www.portland.gov/code/33/100s/110",
    retrieved=date(2026, 8, 12),
)
POLICY = SlackPolicy(tolerance={"fit_ft": 0.5})

DESIGN = load_catalog().latest("pod56x36")

#: Generous on everything else, so a test can break exactly one standard.
CLEAR = {
    "quadplex_allowed": True,
    "min_lot_sqft": 3000,
    "min_frontage_ft": 25,
    "min_lot_width_ft": 25,
    "max_coverage_pct": 60,
    "max_far": 2.0,
    "max_height_ft": 60,
    "max_units": 4,
    "parking_min_per_unit": 1.0,
}

LOT = LotFacts(lot_sqft=6000, frontage_ft=60, lot_width_ft=60)

#: The two fields this module is about, and the check name each is read under.
FLOORS = ("min_building_height_ft", "min_building_height_stories")


def rules(**overrides) -> ZoneResolution:
    values = {**CLEAR, **overrides}
    return ZoneResolution(
        jurisdiction=WHERE,
        zone="R5",
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
    """Room to spare on everything geometric, so height is the only question."""
    depth_ft = 36.0
    best = depth_ft + DESIGN.parking.court_depth_ft + 4.0
    return Fit(
        fits=True,
        width_ft=56.0,
        depth_ft=depth_ft,
        best_depth_ft=best,
        slack_ft=best - depth_ft,
    )


def run(rule_set=None, design=DESIGN):
    return screen(rule_set or rules(), LOT, design, fit(), policy=POLICY)


def check(result, name: str):
    """One named check off a screening result, or None if it never ran."""
    return next((c for c in result.checks if c.check == name), None)


# --- the floor is a standard, and it is tested ------------------------


def test_a_design_that_clears_the_floor_passes_it() -> None:
    result = run(rules(min_building_height_ft=25))

    assert check(result, "min_height_ft").verdict is Verdict.passes
    assert result.triage is Triage.green


def test_a_design_shorter_than_the_floor_does_not_pass() -> None:
    """The whole reason the field exists: too SHORT has to be a miss."""
    result = run(rules(min_building_height_ft=40))

    assert check(result, "min_height_ft").verdict is not Verdict.passes
    assert result.triage is not Triage.green


def test_the_storey_floor_is_counted_in_storeys_and_not_converted() -> None:
    """Oregon City's WFDD writes both limbs, so both have to be testable."""
    passes = run(rules(min_building_height_stories=2))
    misses = run(rules(min_building_height_stories=3))

    assert check(passes, "min_stories").verdict is Verdict.passes
    assert check(misses, "min_stories").verdict is not Verdict.passes


def test_a_zone_stating_both_limbs_runs_both_checks() -> None:
    """A conjunction is two standards. Neither may stand in for the other."""
    result = run(rules(min_building_height_ft=25, min_building_height_stories=2))

    assert check(result, "min_height_ft") is not None
    assert check(result, "min_stories") is not None


def test_the_floor_and_the_ceiling_are_tested_separately() -> None:
    """A building can be legal on one and illegal on the other at once."""
    result = run(rules(min_building_height_ft=40, max_height_ft=60))

    assert check(result, "height_ft").verdict is Verdict.passes
    assert check(result, "min_height_ft").verdict is not Verdict.passes


# --- silence is not a gap ---------------------------------------------


def test_a_zone_that_states_no_floor_is_still_green() -> None:
    """The invariant this field broke on its first run, and the reason for
    ``OPTIONAL_FIELDS``: a required field left unchecked blocks GREEN corpus
    wide, and most Oregon zones state no minimum height at all."""
    result = run(rules())

    assert check(result, "min_height_ft") is None
    assert result.triage is Triage.green


def test_both_floors_are_optional_fields() -> None:
    for name in FLOORS:
        assert name in OPTIONAL_FIELDS
        assert name not in REQUIRED_FIELDS


def test_both_floors_are_registered_and_reachable_from_a_check() -> None:
    names = set(FIELDS)
    for name in FLOORS:
        assert name in names
        assert name in CHECK_FIELD.values()


# --- the paper calculation folds three bounds into one answer ---------


def test_a_zone_with_no_height_standard_at_all_is_unasked_not_passed() -> None:
    assert _height_ok(DESIGN, None, None, None) is None


def test_the_paper_answer_is_false_when_any_one_bound_is_missed() -> None:
    assert _height_ok(DESIGN, 60.0, None, None) is True
    assert _height_ok(DESIGN, 20.0, None, None) is False
    assert _height_ok(DESIGN, None, 40.0, None) is False
    assert _height_ok(DESIGN, None, None, 3.0) is False
    assert _height_ok(DESIGN, 60.0, 25.0, 2.0) is True


# --- what is on file, checked against the pages it came from ----------


def encoded() -> list[tuple[str, str, str, float, str]]:
    """Every minimum height in the corpus: layer, zone, field, value, quote."""
    out = []
    for name, layer in sorted(load_rules(strict=False).items()):
        for code, zone in sorted(layer.zones.items()):
            for field in FLOORS:
                held = zone.values.get(field)
                if held is None:
                    continue
                prov = held.prov or layer.cite_default
                out.append((name, code, field, float(held.value), prov.quote or ""))
    return out


def test_the_corpus_states_at_least_one_minimum_height() -> None:
    """Not a pinned count -- a floor under one. A corpus with none of these
    would mean the field had been registered and never used, which is a
    different bug from the one this module is about and worth failing on."""
    assert encoded()


def test_every_encoded_floor_is_quoted_from_a_line_that_states_a_floor() -> None:
    """The misquote guard, made specific: the cited lines must contain the
    words 'minimum' and 'height'. Every one of the five is a prose sentence or
    a table row that says so in as many words, so this is a real constraint
    and not a tautology."""
    store = ProvenanceStore()
    for name, code, field, _value, quote in encoded():
        assert quote, f"{name} {code} {field} has no quote"
        text = store.quote(quote).lower()
        assert "minimum" in text, f"{name} {code} {field}: {text[:120]!r}"
        assert "height" in text, f"{name} {code} {field}: {text[:120]!r}"


def test_no_floor_sits_above_its_own_zones_ceiling() -> None:
    """Internally true at any corpus size, and it catches the transcription
    error this field is most exposed to: reading a maximum row as a minimum."""
    for name, layer in sorted(load_rules(strict=False).items()):
        for code, zone in sorted(layer.zones.items()):
            floor = zone.values.get("min_building_height_ft")
            ceiling = zone.values.get("max_height_ft")
            if floor is None or ceiling is None:
                continue
            assert float(floor.value) <= float(ceiling.value), f"{name} {code}"


def test_both_catalogued_pods_clear_every_floor_on_file() -> None:
    """True today, and the sentence that makes this field worth having: it
    stops being true the moment a single-storey design enters the catalog, and
    THAT is when the screen needs to already know how to say so."""
    for design in load_catalog().active():
        for name, code, field, value, _quote in encoded():
            observed = (
                design.height_ft if field.endswith("_ft") else float(design.stories)
            )
            assert observed >= value, f"{design.id} misses {name} {code} {field}"


def test_a_zone_holding_a_floor_has_it_screened_rather_than_skipped() -> None:
    """The count asserted at zero. A field can be registered, encoded, and
    still read by nothing -- that is the silent set the reach ledger exists
    for, and it is exactly how a floor would come to buy a false GREEN."""
    skipped = [
        (name, code, field)
        for name, code, field, _value, _quote in encoded()
        if field not in CHECK_FIELD.values()
    ]
    assert skipped == []
