"""A setback stated as a share of the lot's own width.

WDC 4.113(.02)A.2: on a corner lot over 10,000 sq ft and less than 100 ft
wide, "the side yard on the street or private drive side of such lot shall be
not less than 20 percent of the width of the lot, but not less than ten feet."
The page prints 20 and prints ten and prints 15.6 -- what a 78 ft lot owes --
nowhere. For a week the reading queue's one open Wilsonville card was this
sentence: every gate it turns on was measured, and the registry had no form
for the number, so every zone charged the ten-foot floor and a wide corner lot
read as clear. That is the false-GREEN shape, and it is the one this file is
about.

The form is `pct_of_lot_width` with a `floor_ft`, on a VARIANT and never on a
base value: a share of a width is a number only once a lot is in hand, and a
base standard is read with none. `Value.under` turns it into feet from the
lot's measured width, and refuses -- ambiguous, so the lot screens UNKNOWN --
where the width is unmeasured, exactly as it refuses an unmeasured lot against
a band. The sentence also bands the lot on two measures at once, area and
width, so a variant now carries `bands`, all of which must hold.

Every test here rules both ways: the lot the share tightens and the lot it
leaves alone, the width that is measured and the width that is not.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from flats.encode.applied import _numbers_of
from flats.encode.readiness import _printed_variant
from flats.encode.verify import fingerprint
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Band, LotWidthShare, Provenance, Value, Variant
from flats.rules.resolver import RuleSet, Verdict

pytestmark = pytest.mark.unit

WV = "or/clackamas/wilsonville"
LAYER = "or/41051-multnomah/4159000-portland"

PROV = Provenance(
    cite="WDC 4.113(.02)A.2",
    url="https://library.municode.com/or/wilsonville",
    retrieved=date(2026, 9, 16),
    quote="or/clackamas/wilsonville/4.planning.txt#L3013-L3016",
)

CITE = (
    "cite_default:\n"
    '  cite: "PCC 33.110.220, Table 110-4"\n'
    '  url: "https://www.portland.gov/code/33/100s/110"\n'
    "  retrieved: 2026-08-12\n"
    '  quote: "pdx/33.110.txt#L42-L48"\n'
)

#: The eight zones that take their setbacks from 4.113(.02). RN is Table 8A,
#: V is Table V-1 and TC is its own chapter; none of the three cites the
#: sentence and none holds the share.
TAKES_4113 = ("R", "OTR", "PDR1", "PDR2", "PDR3", "PDR4", "PDR5", "PDR6")

OVER_10K = Band(measure="lot_sqft", more_than=10000)
UNDER_100_WIDE = Band(measure="lot_width_ft", less_than=100)


def share(pct: float = 20, floor: float | None = 10) -> LotWidthShare:
    return LotWidthShare(pct=pct, floor_ft=floor)


def corner_share(**over) -> Variant:
    kw = dict(value=share(), when=("corner_lot",), bands=(OVER_10K, UNDER_100_WIDE), prov=PROV)
    kw.update(over)
    return Variant(**kw)


def street_side(*variants: Variant, base: float = 10) -> Value:
    return Value(name="setback_street_side_ft", value=base, prov=PROV, variants=variants)


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return tmp_path / "jurisdictions"


def portland(root: Path, zones: str) -> None:
    p = root / f"{LAYER}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("label: Portland\n" + CITE + "zones:\n" + zones, encoding="utf-8")


# --- the arithmetic, on the lot ---------------------------------------


def test_a_wide_enough_corner_lot_owes_the_share_of_its_width() -> None:
    """The lot the old encoding read as clear: 78 ft wide owes 15.6, not 10."""
    got = street_side(corner_share()).under(["corner_lot"], {"lot_sqft": 12000, "lot_width_ft": 78})

    assert got.value == 15.6
    assert got.when == ("corner_lot", "lot_sqft:>10000+", "lot_width_ft:<=<100")
    assert got.lot_width_share == share()
    assert not got.ambiguous


def test_a_narrow_corner_lot_owes_the_floor() -> None:
    """Twenty percent of 40 ft is 8, and the sentence says never under ten."""
    got = street_side(corner_share()).under(["corner_lot"], {"lot_sqft": 12000, "lot_width_ft": 40})

    assert got.value == 10
    assert got.lot_width_share == share()


def test_at_a_hundred_feet_and_wider_the_code_states_no_share() -> None:
    """"Less than 100 feet in width" -- a 100 ft lot is outside the band and
    takes the base, and so is a 120 ft one. The share would have asked 20 and
    24; the code does not."""
    value = street_side(corner_share())

    assert value.under(["corner_lot"], {"lot_sqft": 12000, "lot_width_ft": 100}).value == 10
    assert value.under(["corner_lot"], {"lot_sqft": 12000, "lot_width_ft": 120}).value == 10
    assert value.under(["corner_lot"], {"lot_sqft": 12000, "lot_width_ft": 99.5}).value == 19.9


def test_a_small_lot_is_outside_the_band_whatever_its_width() -> None:
    """The other gate: A.2 is written for lots over 10,000 sq ft. A 9,000 sq
    ft corner lot 78 ft wide takes B.2's ten -- and so does one whose width
    nobody measured, because it is not in the column that would need it."""
    value = street_side(corner_share())

    assert value.under(["corner_lot"], {"lot_sqft": 9000, "lot_width_ft": 78}).value == 10
    unmeasured = value.under(["corner_lot"], {"lot_sqft": 9000})
    assert unmeasured.value == 10
    assert not unmeasured.ambiguous


def test_an_interior_lot_takes_the_base() -> None:
    """The sentence is about corner lots; a 78 ft interior lot in the band is
    not the lot it describes."""
    got = street_side(corner_share()).under([], {"lot_sqft": 12000, "lot_width_ft": 78})

    assert got.value == 10
    assert got.when == ()


def test_a_corner_lot_in_the_band_with_no_measured_width_is_refused() -> None:
    """The refusal that keeps this from being an amnesty.

    Over 10,000 sq ft, a corner, width unknown: the share cannot be worked
    out and the floor is the wrong column. Ambiguous, as an unmeasured lot
    against a band is ambiguous, and the screen routes the lot to UNKNOWN
    rather than certifying it on ten feet.
    """
    got = street_side(corner_share()).under(["corner_lot"], {"lot_sqft": 12000})

    assert got.value == 10
    assert got.ambiguous == ("lot_width_ft:<=<100",)
    assert not got.trusted


def test_a_share_with_no_width_band_still_refuses_an_unmeasured_width() -> None:
    """A code that states the share for every corner lot, without the width
    gate, selects the variant on the condition alone -- and the number still
    cannot be produced without the width."""
    value = street_side(corner_share(bands=(OVER_10K,)))

    assert value.under(["corner_lot"], {"lot_sqft": 12000, "lot_width_ft": 78}).value == 15.6
    got = value.under(["corner_lot"], {"lot_sqft": 12000})
    assert got.ambiguous == ("lot_width_ft:unmeasured",)


def test_the_share_alone_with_no_floor_is_the_share() -> None:
    v = Variant(value=share(floor=None), when=("corner_lot",), prov=PROV)

    assert street_side(v).under(["corner_lot"], {"lot_width_ft": 40}).value == 8


def test_the_feet_are_rounded_like_a_reduced_base() -> None:
    """20 percent of 78 is 15.6, not 15.600000000000001; the figure has to
    survive being printed beside the sentence it came from."""
    assert share().feet(78) == 15.6
    assert share().feet(40) == 10
    assert share().feet(99.5) == 19.9


# --- what the form refuses ---------------------------------------------


def test_a_share_is_a_percentage() -> None:
    with pytest.raises(ValueError, match="not a percentage"):
        share(pct=120)
    with pytest.raises(ValueError, match="not a percentage"):
        share(pct=0)


def test_a_floor_is_a_length() -> None:
    with pytest.raises(ValueError, match="not a length"):
        share(floor=-1)


def test_a_share_of_the_width_is_a_length_and_nothing_else() -> None:
    """Twenty percent of the lot width is feet. A lot area or a count of
    stalls stated that way is a sentence no code writes, and a file that
    wrote one has the wrong field."""
    with pytest.raises(ValueError, match="is a length"):
        Value(
            name="min_lot_sqft",
            value=7000,
            prov=PROV,
            variants=(Variant(value=share(), when=("corner_lot",), prov=PROV),),
        )


def test_a_variant_states_one_band_per_measure() -> None:
    with pytest.raises(ValueError, match="one band per lot measure"):
        Variant(value=15, bands=(OVER_10K, Band(measure="lot_sqft", at_most=20000)), prov=PROV)


def test_the_singular_band_is_the_plural_with_one_entry() -> None:
    """Every file and most tests write `band:`; the two spellings are one
    field, so nothing can read the singular and miss the plural."""
    one = Variant(value=15, band=OVER_10K, prov=PROV)
    two = corner_share()

    assert one.bands == (OVER_10K,)
    assert one.band == OVER_10K
    assert two.band is None, "a two-band variant answers None to the singular"
    assert two.bands == (OVER_10K, UNDER_100_WIDE)
    with pytest.raises(ValueError, match="'band' or 'bands'"):
        Variant(value=15, band=OVER_10K, bands=(UNDER_100_WIDE,), prov=PROV)


def test_two_bands_count_twice_toward_specificity() -> None:
    """"Over 10,000 sq ft" against "over 10,000 sq ft and under 100 ft wide"
    is the pair A.2 writes beside the plain side yard: the deeper one governs
    the lot both describe, and the shallower one the lot only it does."""
    plain = Variant(value=12, when=("corner_lot",), bands=(OVER_10K,), prov=PROV)
    value = street_side(plain, corner_share())

    assert value.under(["corner_lot"], {"lot_sqft": 12000, "lot_width_ft": 78}).value == 15.6
    assert value.under(["corner_lot"], {"lot_sqft": 12000, "lot_width_ft": 120}).value == 12


def test_two_variants_on_the_same_measures_may_not_overlap_on_all_of_them() -> None:
    """The overlap check, generalised: two columns of one table sharing a lot
    is the silent error, and with two measures a lot is shared only when it
    is inside both ranges of both variants."""
    with pytest.raises(ValueError, match="overlap"):
        street_side(
            corner_share(value=15),
            Variant(
                value=18,
                when=("corner_lot",),
                bands=(Band(measure="lot_sqft", at_least=8000), Band(measure="lot_width_ft", at_most=60)),
                prov=PROV,
            ),
        )
    # Overlapping on area alone is not an overlap: no lot is both under 60
    # ft wide and 100 ft or wider.
    street_side(
        corner_share(value=15),
        Variant(
            value=18,
            when=("corner_lot",),
            bands=(Band(measure="lot_sqft", at_least=8000), Band(measure="lot_width_ft", at_least=100)),
            prov=PROV,
        ),
    )


def test_a_variant_still_needs_something_selecting_it() -> None:
    with pytest.raises(ValueError, match="must state the condition"):
        street_side(Variant(value=share(), prov=PROV))


# --- the file -----------------------------------------------------------


def test_the_file_writes_the_share_the_way_the_sentence_does(root: Path) -> None:
    portland(
        root,
        "  R5:\n"
        "    setback_street_side_ft:\n"
        "      value: 10\n"
        "      variants:\n"
        "        - pct_of_lot_width: 20\n"
        "          floor_ft: 10\n"
        "          when: [corner_lot]\n"
        "          band:\n"
        "            - {measure: lot_sqft, more_than: 10000}\n"
        "            - {measure: lot_width_ft, less_than: 100}\n",
    )
    rules = RuleSet(load_rules(root))

    wide = rules.resolve(LAYER, "R5", ["corner_lot"], lot={"lot_sqft": 12000, "lot_width_ft": 78})
    narrow = rules.resolve(LAYER, "R5", ["corner_lot"], lot={"lot_sqft": 12000, "lot_width_ft": 40})
    unmeasured = rules.resolve(LAYER, "R5", ["corner_lot"], lot={"lot_sqft": 12000})

    assert wide.values["setback_street_side_ft"].value == 15.6
    assert narrow.values["setback_street_side_ft"].value == 10
    assert unmeasured.verdict is Verdict.ambiguous
    assert "setback_street_side_ft" in unmeasured.ambiguous


def test_the_file_may_not_state_a_number_and_a_share_together(root: Path) -> None:
    portland(
        root,
        "  R5:\n"
        "    setback_street_side_ft:\n"
        "      value: 10\n"
        "      variants:\n"
        "        - value: 15\n"
        "          pct_of_lot_width: 20\n"
        "          when: [corner_lot]\n",
    )
    with pytest.raises(RuleLoadError, match="a number or a share of the lot width, not both"):
        load_rules(root)


def test_the_file_may_not_state_a_floor_with_nothing_over_it(root: Path) -> None:
    portland(
        root,
        "  R5:\n"
        "    setback_street_side_ft:\n"
        "      value: 10\n"
        "      variants:\n"
        "        - floor_ft: 10\n"
        "          value: 12\n"
        "          when: [corner_lot]\n",
    )
    with pytest.raises(RuleLoadError, match="states nothing on its own"):
        load_rules(root)


def test_the_file_may_not_state_a_share_over_a_hundred(root: Path) -> None:
    portland(
        root,
        "  R5:\n"
        "    setback_street_side_ft:\n"
        "      value: 10\n"
        "      variants:\n"
        "        - pct_of_lot_width: 120\n"
        "          when: [corner_lot]\n",
    )
    with pytest.raises(RuleLoadError, match="not a percentage"):
        load_rules(root)


def test_the_file_may_not_state_a_share_as_a_base_value(root: Path) -> None:
    """A base standard is read with no lot -- the rules table and the paper
    lot both print it -- so a share of the width there is a number nothing
    could produce."""
    portland(
        root,
        "  R5:\n"
        "    setback_street_side_ft:\n"
        "      pct_of_lot_width: 20\n"
        "      floor_ft: 10\n",
    )
    with pytest.raises(RuleLoadError, match="a number only on a lot"):
        load_rules(root)


def test_a_share_still_needs_a_condition_or_a_band(root: Path) -> None:
    portland(
        root,
        "  R5:\n"
        "    setback_street_side_ft:\n"
        "      value: 10\n"
        "      variants:\n"
        "        - pct_of_lot_width: 20\n",
    )
    with pytest.raises(RuleLoadError, match="'when' must list"):
        load_rules(root)


def test_a_bad_band_in_a_list_is_named_by_its_place(root: Path) -> None:
    portland(
        root,
        "  R5:\n"
        "    setback_street_side_ft:\n"
        "      value: 10\n"
        "      variants:\n"
        "        - value: 15\n"
        "          band:\n"
        "            - {measure: lot_sqft, more_than: 10000}\n"
        "            - {measure: lot_width_ft, at_most: 100, less_than: 100}\n",
    )
    with pytest.raises(RuleLoadError, match=r"band\[1\]"):
        load_rules(root)


# --- the ledgers see the figures the page prints ----------------------


def test_the_citation_check_looks_for_the_share_not_the_result() -> None:
    """Lines 3013 to 3016 print 20 and ten. A check that looked for 15.6
    would flag the one encoding that did not invent it."""
    assert _printed_variant(corner_share()) == 20


def test_the_footnote_ledger_counts_the_share_the_floor_and_both_bounds() -> None:
    assert set(_numbers_of(corner_share())) == {20.0, 10.0, 10000.0, 100.0}


def test_the_signature_is_over_the_share_and_changes_when_it_does() -> None:
    """A reviewer signs the sentence. Change the 20 to 25 and what they
    signed is no longer what is there."""
    twenty = fingerprint(WV, "R", "setback_street_side_ft", share(), cite="WDC", when=corner_share().key)
    twenty_five = fingerprint(
        WV, "R", "setback_street_side_ft", share(pct=25), cite="WDC", when=corner_share().key
    )
    floorless = fingerprint(
        WV, "R", "setback_street_side_ft", share(floor=None), cite="WDC", when=corner_share().key
    )

    assert twenty != twenty_five
    assert twenty != floorless
    assert twenty == fingerprint(
        WV, "R", "setback_street_side_ft", share(), cite="WDC", when=corner_share().key
    )
    assert str(share()) == "20% of lot width, not less than 10 ft"


# --- Wilsonville, as encoded -------------------------------------------


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.mark.parametrize("zone", TAKES_4113)
def test_every_zone_that_takes_its_setbacks_from_4113_charges_the_share(rules: RuleSet, zone: str) -> None:
    wide = rules.resolve(WV, zone, ["corner_lot"], lot={"lot_sqft": 12000, "lot_width_ft": 78})
    narrow = rules.resolve(WV, zone, ["corner_lot"], lot={"lot_sqft": 12000, "lot_width_ft": 40})
    over = rules.resolve(WV, zone, ["corner_lot"], lot={"lot_sqft": 12000, "lot_width_ft": 120})
    small = rules.resolve(WV, zone, ["corner_lot"], lot={"lot_sqft": 9000, "lot_width_ft": 78})
    interior = rules.resolve(WV, zone, [], lot={"lot_sqft": 12000, "lot_width_ft": 78})

    assert wide.values["setback_street_side_ft"].value == 15.6
    assert narrow.values["setback_street_side_ft"].value == 10
    assert over.values["setback_street_side_ft"].value == 10
    assert small.values["setback_street_side_ft"].value == 10
    assert interior.values["setback_street_side_ft"].value == 10


@pytest.mark.parametrize("zone", TAKES_4113)
def test_and_refuses_a_corner_lot_in_the_band_whose_width_is_unmeasured(rules: RuleSet, zone: str) -> None:
    got = rules.resolve(WV, zone, ["corner_lot"], lot={"lot_sqft": 12000})

    assert got.verdict is Verdict.ambiguous
    assert "setback_street_side_ft" in got.ambiguous


def test_the_share_leans_on_corner_status_so_an_unknown_corner_cannot_go_green(rules: RuleSet) -> None:
    """`corner_lot` is a site fact the registry refuses to assume. The
    variant names it, so wherever it is unobserved the screen's FACT_UNOBSERVED
    fires on this field -- the conservative reading, not the floor."""
    got = rules.resolve(WV, "R", [], lot={"lot_sqft": 12000, "lot_width_ft": 78})

    assert "corner_lot" in got.values["setback_street_side_ft"].levers


def test_the_zones_on_their_own_tables_do_not_hold_it(rules: RuleSet) -> None:
    """RN reads Table 8A, V reads Table V-1: 4.113(.02) applies "unless
    otherwise provided", and both tables provide otherwise."""
    layer = load_rules()[WV]
    for zone in ("RN", "V"):
        value = layer.zones[zone].values["setback_street_side_ft"]
        assert not any(isinstance(v.value, LotWidthShare) for v in value.variants), zone


def test_the_variant_cites_the_sentence_and_the_sentence_prints_the_share() -> None:
    from flats.provenance.store import ProvenanceStore, parse_quote

    layer = load_rules()[WV]
    store = ProvenanceStore()
    for zone in TAKES_4113:
        (variant,) = layer.zones[zone].values["setback_street_side_ft"].variants
        assert variant.prov.quote == "or/clackamas/wilsonville/4.planning.txt#L3013-L3016"
        ref = parse_quote(variant.prov.quote)
        text = " ".join(store.load(ref.path).lines(ref).splitlines())
        assert "20 percent of the width of" in text and "not less than ten feet" in text
