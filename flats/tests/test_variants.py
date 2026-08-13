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
from flats.rules.model import Layer, Provenance, Status, Value, Variant, Zone
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
