"""One standard, more than one number.

"5 ft., or 10 ft. where the development is affordable" is the ordinary shape of
a zoning table, not an edge case: a row of numbers with footnote markers hanging
off them. Encoding only the base silently applies the wrong setback to every
project that took an incentive. Encoding only the exception does the same in
reverse. Refusing to encode either — which is what this system used to do —
leaves the most common shape in real code unrepresentable.

What the tests below pin down is that a variant is a first-class number: it is
authored, resolved, signed, withdrawn and queued on its own terms, and never
inherits somebody's confidence in the sentence next to it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from flats.encode.verify import (
    VerificationError,
    VerificationLog,
    apply_verifications,
    fingerprint,
    sign,
    variant_for,
)
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Band, Layer, Provenance, Status, Value, Variant, Zone
from flats.rules.resolver import RuleSet, Verdict

pytestmark = pytest.mark.unit

LAYER = "or/41051-multnomah/4159000-portland"
REVIEWED = date(2026, 8, 12)

PROV = Provenance(
    cite="PCC 33.110.220, Table 110-4",
    url="https://www.portland.gov/code/33/100s/110",
    retrieved=REVIEWED,
    quote="pdx/33.110.txt#L42-L48",
)

CITE = (
    "cite_default:\n"
    '  cite: "PCC 33.110.220, Table 110-4"\n'
    '  url: "https://www.portland.gov/code/33/100s/110"\n'
    "  retrieved: 2026-08-12\n"
    "  quote: \"pdx/33.110.txt#L42-L48\"\n"
)


def value(*variants: Variant, base: object = 5, name: str = "setback_front_ft") -> Value:
    return Value(name=name, value=base, prov=PROV, variants=variants)


def variant(val: object, *when: str, prov: Provenance = PROV, **over) -> Variant:
    return Variant(value=val, when=when, prov=prov, **over)


def portland(root: Path, zones: str) -> None:
    p = root / f"{LAYER}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("label: Portland\n" + CITE + "zones:\n" + zones, encoding="utf-8")


def layers(**values: Value) -> dict[str, Layer]:
    return {
        LAYER: Layer(
            layer=LAYER,
            kind="city",
            label="Portland",
            zones={"R5": Zone(zone="R5", values=values)},
        )
    }


# --- what applies to this lot -----------------------------------------


def test_the_base_applies_when_nothing_is_elected() -> None:
    assert value(variant(10, "affordable")).under().value == 5


def test_the_exception_applies_when_its_condition_holds() -> None:
    assert value(variant(10, "affordable")).under({"affordable"}).value == 10


def test_an_unrelated_condition_changes_nothing() -> None:
    # Every condition is not a lever on every standard. A lot in a flood
    # overlay does not thereby get the affordable-housing setback.
    assert value(variant(10, "affordable")).under({"corner_lot"}).value == 5


def test_the_more_specific_exception_wins() -> None:
    # A code that writes both "affordable" and "affordable and corner" meant
    # the pair to differ from either alone; taking the shorter match would
    # quietly discard the sentence that was harder to read.
    v = value(variant(10, "affordable"), variant(12, "affordable", "corner_lot"))

    assert v.under({"affordable", "corner_lot"}).value == 12
    assert v.under({"affordable"}).value == 10


def test_a_partial_match_does_not_apply() -> None:
    v = value(variant(12, "affordable", "corner_lot"))

    assert v.under({"corner_lot"}).value == 5


def test_two_equally_specific_exceptions_are_not_guessed() -> None:
    # Picking one would mean choosing between two encoded rules on no basis at
    # all, and the choice would be invisible in the output. Saying so is the
    # only honest move: the screen routes this lot to UNKNOWN.
    v = value(variant(10, "affordable"), variant(8, "mixed_use"))

    eff = v.under({"affordable", "mixed_use"})

    assert eff.ambiguous == ("affordable", "mixed_use")
    assert not eff.trusted
    assert eff.value == 5, "the base is carried, but nothing may read it as an answer"


def test_the_effective_value_names_what_selected_it() -> None:
    eff = value(variant(10, "affordable")).under({"affordable"})

    assert eff.when == ("affordable",)
    assert eff.conditional


def test_provenance_follows_the_number_that_applied() -> None:
    # The usual case for an exception is that it lives in a different chapter
    # from the table it modifies. A lot detail page that cited the table would
    # send a reviewer to a page the number is not on.
    bonus = Provenance(
        cite="PCC 33.120.205",
        url="https://www.portland.gov/code/33/100s/120",
        retrieved=REVIEWED,
        quote="pdx/33.120.txt#L12",
    )

    eff = value(variant(10, "affordable", prov=bonus)).under({"affordable"})

    assert eff.prov.cite == "PCC 33.120.205"


def test_the_levers_are_the_conditions_that_move_a_number() -> None:
    # What makes the batch view possible: offering a toggle is worth doing only
    # when flipping it changes a standard some lot in the selection is bound by.
    v = value(variant(10, "affordable"), variant(12, "affordable", "corner_lot"))

    assert v.levers == frozenset({"affordable", "corner_lot"})
    assert value().levers == frozenset()


# --- what a file may say ----------------------------------------------


def test_an_exception_with_no_condition_is_refused() -> None:
    with pytest.raises(ValueError, match="condition"):
        value(Variant(value=10, when=(), prov=PROV))


def test_an_unregistered_condition_is_refused() -> None:
    # Same refusal as the field registry. A typo would otherwise become a
    # second lever nobody can satisfy, on a number that never applies.
    with pytest.raises(ValueError, match="rainy_tuesday"):
        value(variant(10, "rainy_tuesday"))


def test_two_exceptions_under_the_same_conditions_are_refused() -> None:
    with pytest.raises(ValueError, match="same conditions"):
        value(variant(10, "affordable"), variant(11, "affordable"))


def test_an_exception_is_checked_against_the_field_kind() -> None:
    with pytest.raises(ValueError, match="boolean"):
        value(variant(10, "affordable"), base=True, name="quadplex_allowed")


# --- authoring them ---------------------------------------------------


def test_a_variant_loads_from_yaml(root: Path) -> None:
    portland(
        root,
        "  R5:\n"
        "    setback_front_ft:\n"
        "      value: 5\n"
        "      variants:\n"
        "        - value: 10\n"
        "          when: [affordable]\n",
    )

    v = load_rules(root)[LAYER].zones["R5"].values["setback_front_ft"]

    assert v.under({"affordable"}).value == 10
    assert v.variants[0].status is Status.draft


def test_a_variant_inherits_the_citation_it_hangs_off(root: Path) -> None:
    # The common case is one table cell with a footnote marker on it, and
    # retyping the citation for every footnote is how citations drift.
    portland(
        root,
        "  R5:\n"
        "    setback_front_ft:\n"
        "      value: 5\n"
        "      variants:\n"
        "        - value: 10\n"
        "          when: [affordable]\n",
    )

    v = load_rules(root)[LAYER].zones["R5"].values["setback_front_ft"]

    assert v.variants[0].prov.cite == "PCC 33.110.220, Table 110-4"


def test_a_variant_may_cite_the_chapter_it_actually_lives_in(root: Path) -> None:
    portland(
        root,
        "  R5:\n"
        "    setback_front_ft:\n"
        "      value: 5\n"
        "      variants:\n"
        "        - value: 10\n"
        "          when: [affordable]\n"
        '          cite: "PCC 33.120.205"\n'
        '          quote: "pdx/33.120.txt#L12"\n',
    )

    v = load_rules(root)[LAYER].zones["R5"].values["setback_front_ft"]

    assert v.variants[0].prov.cite == "PCC 33.120.205"
    assert v.variants[0].prov.url.endswith("/110"), "unstated fields still inherit"


def test_a_single_condition_may_be_written_as_a_string(root: Path) -> None:
    portland(
        root,
        "  R5:\n"
        "    setback_front_ft:\n"
        "      value: 5\n"
        "      variants:\n"
        "        - value: 10\n"
        "          when: affordable\n",
    )

    assert load_rules(root)[LAYER].zones["R5"].values["setback_front_ft"].levers == {"affordable"}


def test_a_variant_with_no_when_is_reported_not_raised(root: Path) -> None:
    # Loading accumulates problems so that porting a jurisdiction surfaces all
    # of them in one pass rather than one per run.
    portland(
        root,
        "  R5:\n    setback_front_ft:\n      value: 5\n      variants:\n        - value: 10\n",
    )

    with pytest.raises(RuleLoadError, match="'when' must list"):
        load_rules(root)


def test_a_file_may_not_declare_a_variant_verified(root: Path) -> None:
    # The same rule as a base value, and worth stating twice: a variant is
    # easier to wave through, because it reads as a detail of a number somebody
    # already checked.
    portland(
        root,
        "  R5:\n"
        "    setback_front_ft:\n"
        "      value: 5\n"
        "      variants:\n"
        "        - value: 10\n"
        "          when: [affordable]\n"
        "          status: verified\n"
        "          reviewer: sjk\n"
        "          reviewed: 2026-08-14\n",
    )

    with pytest.raises(RuleLoadError, match="may not declare status"):
        load_rules(root)


# --- signing them -----------------------------------------------------


def test_a_variant_hashes_apart_from_its_base() -> None:
    # If they hashed alike, signing "5 ft." would certify "10 ft. where
    # affordable" — a number in a different sentence, often a different chapter.
    base = fingerprint(LAYER, "R5", "setback_front_ft", 10, cite="PCC 33.110.220")
    under = fingerprint(LAYER, "R5", "setback_front_ft", 10, cite="PCC 33.110.220", when=["affordable"])

    assert base != under


def test_the_order_conditions_were_typed_in_is_not_part_of_the_signature() -> None:
    a = fingerprint(LAYER, "R5", "setback_front_ft", 12, when=["affordable", "corner_lot"])
    b = fingerprint(LAYER, "R5", "setback_front_ft", 12, when=["corner_lot", "affordable"])

    assert a == b


def test_signing_the_base_leaves_the_exception_in_draft() -> None:
    v = value(variant(10, "affordable"))
    log = VerificationLog([sign(LAYER, "R5", "setback_front_ft", v, reviewer="sjk", reviewed=REVIEWED)])

    out, orphans = apply_verifications(layers(setback_front_ft=v), log)
    signed = out[LAYER].zones["R5"].values["setback_front_ft"]

    assert signed.status is Status.verified
    assert signed.variants[0].status is Status.draft, "nobody has read the exception yet"
    assert orphans == []


def test_signing_the_exception_leaves_the_base_in_draft() -> None:
    v = value(variant(10, "affordable"))
    log = VerificationLog(
        [
            sign(
                LAYER, "R5", "setback_front_ft", v, reviewer="sjk", reviewed=REVIEWED,
                when=["affordable"],
            )
        ]
    )

    out, _ = apply_verifications(layers(setback_front_ft=v), log)
    signed = out[LAYER].zones["R5"].values["setback_front_ft"]

    assert signed.status is Status.draft
    assert signed.variants[0].status is Status.verified
    assert signed.variants[0].reviewer == "sjk"


def test_the_effective_value_carries_the_variant_review_state() -> None:
    # What the screen reads. A verified base with a draft exception must not
    # look trusted to a lot that elected the exception.
    v = value(variant(10, "affordable"))
    log = VerificationLog([sign(LAYER, "R5", "setback_front_ft", v, reviewer="sjk", reviewed=REVIEWED)])

    out, _ = apply_verifications(layers(setback_front_ft=v), log)
    signed = out[LAYER].zones["R5"].values["setback_front_ft"]

    assert signed.under().trusted
    assert not signed.under({"affordable"}).trusted


def test_editing_the_exception_withdraws_only_its_own_signature() -> None:
    v = value(variant(10, "affordable"))
    log = VerificationLog(
        [
            sign(LAYER, "R5", "setback_front_ft", v, reviewer="sjk", reviewed=REVIEWED),
            sign(
                LAYER, "R5", "setback_front_ft", v, reviewer="sjk", reviewed=REVIEWED,
                when=["affordable"],
            ),
        ]
    )
    amended = value(variant(15, "affordable"))

    out, orphans = apply_verifications(layers(setback_front_ft=amended), log)
    after = out[LAYER].zones["R5"].values["setback_front_ft"]

    assert after.status is Status.verified, "the base was not touched"
    assert after.variants[0].status is Status.draft
    assert [(o.field, o.when) for o in orphans] == [("setback_front_ft", ("affordable",))]


def test_an_orphan_names_the_exception_it_was_signed_over() -> None:
    v = value(variant(10, "affordable"))
    log = VerificationLog(
        [
            sign(
                LAYER, "R5", "setback_front_ft", v, reviewer="sjk", reviewed=REVIEWED,
                when=["affordable"],
            )
        ]
    )

    _, orphans = apply_verifications(layers(setback_front_ft=value()), log)

    assert orphans[0].label == "setback_front_ft [affordable]"


def test_signing_an_exception_that_is_not_encoded_is_refused() -> None:
    # Exact match, not most-specific: `under()` answers "what applies to this
    # lot", which is a different question from "which sentence am I signing".
    with pytest.raises(VerificationError, match="no variant"):
        sign(
            LAYER, "R5", "setback_front_ft", value(variant(10, "affordable")),
            reviewer="sjk", reviewed=REVIEWED, when=["corner_lot"],
        )


def test_the_exception_is_found_by_its_exact_conditions() -> None:
    v = value(variant(10, "affordable"), variant(12, "affordable", "corner_lot"))

    assert variant_for(v, ["corner_lot", "affordable"]).value == 12
    assert variant_for(v, ["affordable"]).value == 10


def test_a_verification_survives_the_log_round_trip(tmp_path: Path) -> None:
    v = value(variant(10, "affordable"))
    entry = sign(
        LAYER, "R5", "setback_front_ft", v, reviewer="sjk", reviewed=REVIEWED, when=["affordable"]
    )
    log = VerificationLog()
    log.append(entry, tmp_path / "verifications.jsonl")

    reloaded = VerificationLog.load(tmp_path / "verifications.jsonl")

    assert reloaded.active()[entry.key].when == ("affordable",)



# --- resolving them ---------------------------------------------------


def ruleset(*variants: Variant, base: object = 5) -> RuleSet:
    return RuleSet(layers(setback_front_ft=value(*variants, base=base)))


def test_resolution_answers_for_the_conditions_it_was_asked_about() -> None:
    rs = ruleset(variant(10, "affordable"))

    assert rs.resolve(LAYER, "R5").get("setback_front_ft") == 5
    assert rs.resolve(LAYER, "R5", {"affordable"}).get("setback_front_ft") == 10


def test_a_resolved_value_says_which_condition_selected_it() -> None:
    r = ruleset(variant(10, "affordable")).resolve(LAYER, "R5", {"affordable"})

    assert r.values["setback_front_ft"].when == ("affordable",)
    assert r.values["setback_front_ft"].conditional


def test_a_resolution_reports_the_levers_it_could_be_asked_about() -> None:
    # The batch view reads this to decide which toggles to offer. Offering
    # every registered condition on every selection would bury the two or three
    # that actually move a number here.
    r = ruleset(variant(10, "affordable"), variant(12, "affordable", "corner_lot")).resolve(
        LAYER, "R5"
    )

    assert r.levers == frozenset({"affordable", "corner_lot"})


def test_an_unasked_condition_leaves_the_resolution_alone() -> None:
    r = ruleset(variant(10, "affordable")).resolve(LAYER, "R5", {"corner_lot"})

    assert r.get("setback_front_ft") == 5
    assert r.values["setback_front_ft"].when == ()


def test_a_tie_makes_the_whole_resolution_ambiguous() -> None:
    r = ruleset(variant(10, "affordable"), variant(8, "mixed_use")).resolve(
        LAYER, "R5", {"affordable", "mixed_use"}
    )

    assert r.verdict is Verdict.ambiguous
    assert r.reason == "RULE_AMBIGUOUS"
    assert r.ambiguous == ("setback_front_ft",)
    assert not r.trusted


def test_ambiguity_outranks_unverified() -> None:
    # Different problems with different fixes. Signing more numbers will never
    # resolve a tie — somebody has to say which exception governs — so a queue
    # that reported this as "awaiting review" would send the work to the wrong
    # person and it would come back unchanged.
    r = ruleset(variant(10, "affordable"), variant(8, "mixed_use")).resolve(
        LAYER, "R5", {"affordable", "mixed_use"}
    )

    assert r.verdict is Verdict.ambiguous
    assert "setback_front_ft" in r.untrusted


def test_conditions_are_recorded_on_the_resolution() -> None:
    # A cached or exported result has to say what configuration produced it.
    r = ruleset(variant(10, "affordable")).resolve(LAYER, "R5", {"affordable", "corner_lot"})

    assert r.conditions == ("affordable", "corner_lot")


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return tmp_path / "jurisdictions"


# --- a standard banded by lot size ------------------------------------
#
# Milwaukie consolidated its single-family zones into one R-MD and then wrote
# Table 19.301.4 as four columns of that same zone, split by how big the lot
# already is: 1,500–2,999 sq ft, 3,000–4,999, 5,000–6,999, and 7,000 and up.
# The street side setback runs 5, 15, 15, 20. None of those four numbers is
# "the R-MD street side setback", and the encoding has to be able to say so.


def band(low: object = None, high: object = None, measure: str = "lot_sqft") -> Band:
    return Band(measure=measure, at_least=low, at_most=high)


def banded(val: object, low: object = None, high: object = None, **over) -> Variant:
    return Variant(value=val, prov=PROV, band=band(low, high), **over)


def test_a_band_selects_the_column_the_lot_falls_in() -> None:
    v = value(banded(5, 1500, 2999), banded(15, 3000, 6999), base=20)

    assert v.under(lot={"lot_sqft": 2400}).value == 5
    assert v.under(lot={"lot_sqft": 4000}).value == 15


def test_the_base_is_the_residual_column() -> None:
    # "7,000 and up" is open-ended, so it is the base and the narrower columns
    # are the exceptions — which is also why a lot larger than every band is
    # not a miss.
    v = value(banded(5, 1500, 2999), banded(15, 3000, 6999), base=20)

    assert v.under(lot={"lot_sqft": 12000}).value == 20


def test_a_band_is_inclusive_at_both_ends() -> None:
    # Codes write "3,000–4,999" and start the next column at 5,000. Reading
    # either bound as exclusive puts a hole between the columns, and a lot in
    # the hole silently takes the residual.
    v = value(banded(15, 3000, 4999), base=20)

    assert v.under(lot={"lot_sqft": 3000}).value == 15
    assert v.under(lot={"lot_sqft": 4999}).value == 15
    assert v.under(lot={"lot_sqft": 5000}).value == 20


def test_an_unmeasured_lot_does_not_fall_through_to_the_base() -> None:
    # The base of a banded standard is the last column, not a safe default.
    # A lot whose area we do not have is not a 7,000 sq ft lot.
    v = value(banded(5, 1500, 2999), base=20)

    got = v.under()

    assert got.ambiguous == ("lot_sqft:1500-2999",)
    assert not got.trusted


def test_a_lot_measured_on_a_different_axis_is_still_unmeasured() -> None:
    v = value(banded(5, 1500, 2999), base=20)

    assert v.under(lot={"lot_width_ft": 40}).ambiguous == ("lot_sqft:1500-2999",)


def test_a_band_and_a_condition_narrow_together() -> None:
    # The affordable exception to one column is one sentence, and it beats
    # both the column and the plain affordable exception.
    v = value(
        variant(10, "affordable"),
        banded(15, 3000, 4999),
        banded(8, 3000, 4999, when=("affordable",)),
        base=20,
    )

    assert v.under({"affordable"}, lot={"lot_sqft": 4000}).value == 8
    assert v.under(lot={"lot_sqft": 4000}).value == 15
    assert v.under({"affordable"}, lot={"lot_sqft": 9000}).value == 10


def test_overlapping_bands_are_refused() -> None:
    # A transcription that types 5,999 where the code says 4,999 leaves two
    # columns claiming the same lot, and whichever sorted first would win —
    # silently, and differently per field.
    with pytest.raises(ValueError, match="overlap"):
        value(banded(5, 1500, 3999), banded(15, 3000, 6999))


def test_bands_on_different_measures_may_overlap() -> None:
    # A width band and an area band are different axes; both applying to one
    # lot is a code that stated both, not a transcription error.
    v = value(banded(5, 1500, 2999), banded(8, 20, 30, measure="lot_width_ft"))

    assert len(v.variants) == 2


def test_a_band_needs_a_bound() -> None:
    with pytest.raises(ValueError, match="at least one bound"):
        Band(measure="lot_sqft")


def test_a_band_names_a_registered_measure() -> None:
    # Same refusal as the field and condition registries: "lot_size" beside
    # "lot_sqft" would be two axes nobody can reconcile.
    with pytest.raises(ValueError, match="unknown lot measure"):
        Band(measure="lot_size", at_least=1500)


def test_a_banded_variant_is_addressed_by_its_band() -> None:
    # Signing is over one sentence, and for a banded table the sentence is one
    # column. Without the band in the key it would address as the base.
    v = banded(5, 1500, 2999)

    assert v.key == ("lot_sqft:1500-2999",)
    assert banded(20, 7000).key == ("lot_sqft:7000+",)
    assert variant_for(value(v), ["lot_sqft:1500-2999"]) is v


# --- a band split on one figure ---------------------------------------
#
# Wilsonville 4.113(.02) states its setbacks twice: "for lots over 10,000
# square feet" and "for lots not exceeding 10,000 square feet". Both columns
# name the same figure, and only one of them can include a lot that measures
# it exactly. Written with two inclusive bounds the encoding is wrong either
# way — 10,000 sq ft lands in both columns, or, moved a foot apart, in neither.


def test_an_exclusive_lower_bound_excludes_the_figure_it_names() -> None:
    over = Band(measure="lot_sqft", more_than=10000)

    assert over.holds({"lot_sqft": 10000.5}) is True
    assert over.holds({"lot_sqft": 10000}) is False
    assert Band(measure="lot_sqft", at_least=10000).holds({"lot_sqft": 10000}) is True


def test_the_two_columns_of_a_split_meet_without_overlapping() -> None:
    # The point of the exclusive bound: no lot is in both columns, and no lot
    # between them falls through to the base unseen.
    v = value(
        Variant(value=20, prov=PROV, band=Band(measure="lot_sqft", more_than=10000)),
        Variant(value=15, prov=PROV, band=Band(measure="lot_sqft", at_most=10000)),
        base=15,
    )

    assert v.under(lot={"lot_sqft": 10000}).value == 15
    assert v.under(lot={"lot_sqft": 10000.5}).value == 20


def test_an_inclusive_bound_still_collides_at_the_shared_figure() -> None:
    with pytest.raises(ValueError, match="overlap"):
        value(
            Variant(value=20, prov=PROV, band=Band(measure="lot_sqft", at_least=10000)),
            Variant(value=15, prov=PROV, band=Band(measure="lot_sqft", at_most=10000)),
        )


def test_a_band_has_one_lower_bound() -> None:
    with pytest.raises(ValueError, match="one lower bound"):
        Band(measure="lot_sqft", at_least=10000, more_than=10000)


def test_an_empty_exclusive_band_is_refused() -> None:
    with pytest.raises(ValueError, match="empty"):
        Band(measure="lot_sqft", more_than=10000, at_most=10000)


def test_a_band_token_says_which_side_the_figure_is_on() -> None:
    # The token is what a reviewer types to sign that column, so the two halves
    # of a split may not address the same way.
    assert Band(measure="lot_sqft", more_than=10000).token == "lot_sqft:>10000+"
    assert Band(measure="lot_sqft", at_most=10000).token == "lot_sqft:<=10000"


def test_a_storey_split_inside_a_band_resolves_to_one_number(root: Path) -> None:
    # Wilsonville's small-lot column splits again on the building: five feet at
    # one storey, seven at two. The pod is two storeys, so the number that
    # applies to it is not the one printed first.
    portland(
        root,
        "  R5:\n"
        "    setback_side_ft:\n"
        "      value: 5\n"
        "      variants:\n"
        "        - value: 7\n"
        "          when: [multi_story]\n"
        "          band: {measure: lot_sqft, at_most: 10000}\n"
        "        - value: 10\n"
        "          band: {measure: lot_sqft, more_than: 10000}\n",
    )
    v = load_rules(root)[LAYER].zones["R5"].values["setback_side_ft"]

    assert v.under(("multi_story",), {"lot_sqft": 6000}).value == 7
    assert v.under((), {"lot_sqft": 6000}).value == 5
    # Over 10,000 sq ft the code stops asking about storeys, so the storey
    # variant must not reach across the split.
    assert v.under(("multi_story",), {"lot_sqft": 12000}).value == 10


def test_a_band_is_authored_as_a_range_on_a_measure(root: Path) -> None:
    portland(
        root,
        "  R5:\n"
        "    setback_street_side_ft:\n"
        "      value: 20\n"
        "      variants:\n"
        "        - value: 5\n"
        "          band: {measure: lot_sqft, at_least: 1500, at_most: 2999}\n",
    )

    v = load_rules(root)[LAYER].zones["R5"].values["setback_street_side_ft"]

    assert v.banded
    assert v.under(lot={"lot_sqft": 2000}).value == 5
    assert v.variants[0].prov.cite == "PCC 33.110.220, Table 110-4"


def test_a_variant_selected_by_nothing_is_still_refused(root: Path) -> None:
    # Dropping the `when` requirement to let bands through must not let a
    # second base in behind it.
    portland(
        root,
        "  R5:\n"
        "    setback_front_ft:\n"
        "      value: 5\n"
        "      variants:\n"
        "        - value: 10\n",
    )

    with pytest.raises(RuleLoadError, match="band"):
        load_rules(root)


def test_resolution_selects_the_band_the_lot_falls_in(root: Path) -> None:
    portland(
        root,
        "  R5:\n"
        "    setback_street_side_ft:\n"
        "      value: 20\n"
        "      variants:\n"
        "        - value: 5\n"
        "          band: {measure: lot_sqft, at_least: 1500, at_most: 2999}\n",
    )
    rules = RuleSet(load_rules(root))

    got = rules.resolve(LAYER, "R5", lot={"lot_sqft": 2400})

    assert got.values["setback_street_side_ft"].value == 5
    assert got.values["setback_street_side_ft"].when == ("lot_sqft:1500-2999",)


def test_resolution_without_the_lot_reports_the_bands_it_could_not_choose(root: Path) -> None:
    # A batch run that forgot to pass the area must not read as an answer.
    portland(
        root,
        "  R5:\n"
        "    setback_street_side_ft:\n"
        "      value: 20\n"
        "      variants:\n"
        "        - value: 5\n"
        "          band: {measure: lot_sqft, at_least: 1500, at_most: 2999}\n",
    )
    rules = RuleSet(load_rules(root))

    got = rules.resolve(LAYER, "R5")

    assert got.values["setback_street_side_ft"].ambiguous == ("lot_sqft:1500-2999",)


# --- a standard that stops applying, rather than changing its number -------


def test_an_exemption_is_not_a_number() -> None:
    """Fairview caps lot depth at three times the width, then writes
    "Townhomes and cottage clusters none" in the same cell. That is not a
    larger cap. Encoding it as one would screen correctly and read as a lie."""
    held = value(
        Variant(exempt=True, when=("unit_lots",), prov=PROV),
        base=3,
        name="max_lot_depth_ratio",
    )

    on_one_lot = held.under()
    assert on_one_lot.value == 3 and not on_one_lot.exempt

    as_townhouses = held.under({"unit_lots"})
    assert as_townhouses.exempt is True
    assert as_townhouses.value is None, "there is no number to compare a lot against"


def test_an_exempt_variant_may_not_also_state_a_number() -> None:
    """Both would leave every reader guessing which half the engine honours."""
    with pytest.raises(Exception):
        Variant(value=3, exempt=True, when=("unit_lots",), prov=PROV)


def test_a_variant_states_a_number_or_states_that_it_is_exempt() -> None:
    with pytest.raises(Exception):
        Variant(when=("unit_lots",), prov=PROV)


def test_an_exemption_survives_the_file(tmp_path: Path) -> None:
    """The loader is where this has to work — it is written in YAML, by hand."""
    root = tmp_path / "or" / "multnomah"
    root.mkdir(parents=True)
    (tmp_path / "or" / "multnomah" / "somewhere.yaml").write_text(
        "layer: or/multnomah/somewhere\n"
        "kind: city\n"
        "label: Somewhere\n"
        "zones:\n"
        "  R-6:\n"
        "    cite_default:\n"
        "      cite: FMC 19.30.030\n"
        "      url: https://example.invalid/19.30\n"
        "      retrieved: '2026-08-15'\n"
        "    max_lot_depth_ratio:\n"
        "      value: 3\n"
        "      quote: 'or/multnomah/somewhere/19.30.txt#L353'\n"
        "      variants:\n"
        "        - exempt: true\n"
        "          when: [unit_lots]\n"
        "          quote: 'or/multnomah/somewhere/19.30.txt#L354'\n",
        encoding="utf-8",
    )
    (tmp_path / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )

    loaded = load_rules(tmp_path, strict=True)
    held = loaded["or/multnomah/somewhere"].zones["R-6"].values["max_lot_depth_ratio"]

    assert held.under().value == 3
    assert held.under({"unit_lots"}).exempt is True


def test_an_exempted_standard_leaves_the_resolution_entirely() -> None:
    """A None sitting in `values` is a number-shaped hole. Something downstream
    would eventually subtract from it and fail the lot on a standard the code
    says does not apply to it, which is the worse of the two ways to be wrong."""
    held = value(
        Variant(exempt=True, when=("unit_lots",), prov=PROV),
        base=3,
        name="max_lot_depth_ratio",
    )
    rules = RuleSet(layers(max_lot_depth_ratio=held))

    on_one_lot = rules.resolve(LAYER, "R5")
    assert on_one_lot.values["max_lot_depth_ratio"].value == 3
    assert on_one_lot.exempted == ()

    as_townhouses = rules.resolve(LAYER, "R5", conditions=["unit_lots"])
    assert "max_lot_depth_ratio" not in as_townhouses.values
    assert as_townhouses.exempted == ("max_lot_depth_ratio",)
