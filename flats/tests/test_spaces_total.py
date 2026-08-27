"""Parking counted for the whole building, and the rate nobody printed.

OAR 660-046-0220(2)(e)(B) caps what a Large City may require of a quadplex, and
it counts spaces rather than stating a rate: "one space in total" under 3,000
square feet, two to 5,000, three to 7,000, four above it. Said per unit those
are 0.25, 0.5, 0.75 and 1.0, and not one of them appears in the rule. The
denominator is not a digit either -- it is the word "Quadplexes" in the stem of
the sentence, which is `DWELLINGS` under another name.

`spaces_total` carries the printed count and divides by `DWELLINGS` at load,
where the arithmetic can be read. The inverse of `per_units`, and it exists
because the state rule and every city that copied its model code state parking
this way round.

What it bought: the cap had been encoded flat at 1.0 per unit off band (iv)
alone, so a quadplex on a 4,000 sq ft lot was screened against four stalls when
no Oregon city is allowed to ask for more than two. The bands reach a hundred
zones.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.encode.readiness import _quoted_parts, readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.fields import DWELLINGS
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Provenance, Value
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

STATE = "or"
RULE = "or/oar.660-046-0220.txt#L79,L90-L91"
PROV = Provenance(
    cite="OAR 660-046-0220(2)(e)(B)(iv)",
    url="https://oregon.public.law/rules/oar_660-046-0220",
    retrieved="2026-08-12",
    quote=RULE,
)


def _somewhere(root: Path, body: str) -> Path:
    d = root / "or" / "multnomah"
    d.mkdir(parents=True)
    (d / "somewhere.yaml").write_text(
        "layer: or/multnomah/somewhere\n"
        "kind: city\n"
        "label: Somewhere\n"
        "zones:\n"
        "  R-6:\n"
        "    cite_default:\n"
        "      cite: OAR 660-046-0220\n"
        "      url: https://example.invalid/220\n"
        "      retrieved: '2026-08-12'\n" + body,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )
    return root


def test_the_four_bands_are_read_as_the_rule_bands_them() -> None:
    """One space per band, in total, and each boundary where the rule puts it.
    The bounds are the rule's own: "less than 3,000", then "greater than or
    equal to" each of 3,000, 5,000 and 7,000 -- so 4,999 is two spaces and
    5,000 is three."""
    state = load_rules()[STATE].defaults["parking_min_per_unit"]
    printed = {state.spaces_total} | {v.spaces_total for v in state.variants}

    assert printed == {1.0, 2.0, 3.0, 4.0}
    assert state.value == 4 / DWELLINGS


def test_the_cap_a_lot_carries_moves_with_the_lot() -> None:
    """A hundred zones inherit this cap and nothing else states one. Before the
    bands they all carried band (iv) whatever the lot measured."""
    rules = RuleSet(load_rules())
    at = {
        sqft: rules.resolve(
            "or/clackamas/_unincorporated", "R7", lot={"lot_sqft": sqft}
        ).values["parking_min_per_unit"]
        for sqft in (2500, 3000, 4999, 5000, 6999, 7000, 12000)
    }

    assert [at[s].value * DWELLINGS for s in (2500, 3000, 4999)] == [1, 2, 2]
    assert [at[s].value * DWELLINGS for s in (5000, 6999, 7000, 12000)] == [3, 3, 4, 4]
    # Each band cites its own clause, so attribution sends a reader to the
    # sentence that produced the number rather than to the subsection.
    assert at[2500].prov.cite.endswith("(B)(i)")
    assert at[7000].prov.cite.endswith("(B)(iv)")


def test_a_lot_nobody_measured_is_assumed_into_the_widest_band() -> None:
    """The base fires only where the area is unknown, and it has to be the
    loosest cap: this is a ceiling on what a city may DEMAND, so assuming a
    small lot would quietly forgive a requirement that really applies."""
    rules = RuleSet(load_rules())
    unmeasured = rules.resolve("or/clackamas/_unincorporated", "R7")

    assert unmeasured.values["parking_min_per_unit"].value == 4 / DWELLINGS


def test_the_citation_is_checked_against_the_count_and_not_the_rate() -> None:
    """The rule prints one, two, three and four and prints 0.25 nowhere.
    Sending the rate to the quote would report the one encoding that invented
    nothing as the misquote -- and the words are spelled, so the check has to
    find "two spaces" rather than a digit."""
    r = readiness_for(load_rules()[STATE], store=ProvenanceStore())

    assert not [row for row in r.misquoted if row[1].startswith("parking_min")]
    assert not [row for row in r.unquoted if row[1].startswith("parking_min")]


def test_a_layer_default_is_read_like_any_other_value() -> None:
    """The state cap lives in `defaults:`, and defaults used to be checked as a
    bare `value` with their exceptions not checked at all. A derived default
    was therefore compared against arithmetic instead of against the page, and
    three of these four bands were never looked for by anything."""
    rows = [row for row in _quoted_parts(load_rules()[STATE]) if row[0] == "defaults"]
    banded = [row for row in rows if row[1].startswith("parking_min_per_unit")]

    # The base and its three exceptions, each with a quote of its own.
    assert len(banded) == 4
    assert sorted(row[3] for row in banded) == [1.0, 2.0, 3.0, 4.0]


def test_a_value_states_a_rate_or_a_count_of_spaces(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="a rate or a count of spaces"):
        load_rules(
            _somewhere(
                tmp_path,
                "    parking_min_per_unit:\n"
                "      spaces_total: 4\n"
                "      value: 1.0\n"
                "      quote: 'or/multnomah/somewhere/220.txt#L1'\n",
            ),
            strict=True,
        )


def test_a_table_states_parking_per_unit_or_in_total(tmp_path: Path) -> None:
    """Both carriers name the same arithmetic from opposite ends. A file that
    set both would be stating a rate twice and could not be read either way."""
    with pytest.raises(RuleLoadError, match="per unit or in total"):
        load_rules(
            _somewhere(
                tmp_path,
                "    parking_min_per_unit:\n"
                "      spaces_total: 4\n"
                "      per_units: 2\n"
                "      quote: 'or/multnomah/somewhere/220.txt#L1'\n",
            ),
            strict=True,
        )


def test_only_parking_may_be_stated_as_a_count_for_the_building() -> None:
    """A total is only a total where the standard counts things the building
    has. A lot width stated as four dwellings' worth is not a rule any code
    writes, and dividing one by four would produce a number in feet that means
    nothing."""
    with pytest.raises(ValueError, match="count for the whole building"):
        Value(name="min_lot_width_ft", value=1.0, spaces_total=4, prov=PROV)


def test_a_code_that_asks_for_none_says_so_rather_than_counting_zero() -> None:
    """Fairview requires no parking at all, and `exempt: true` is how that is
    said. Zero spaces in total would divide to zero and read as a requirement
    that happens to be satisfiable, which is a different sentence."""
    with pytest.raises(ValueError, match="not a count of spaces"):
        Value(name="parking_min_per_unit", value=0.0, spaces_total=0, prov=PROV)


def test_the_printed_count_is_kept_for_the_reader() -> None:
    """Attribution has to be able to say where 0.25 came from."""
    state = load_rules()[STATE].defaults["parking_min_per_unit"]
    smallest = min(state.variants, key=lambda v: v.spaces_total)

    assert smallest.spaces_total == 1
    assert smallest.value == 1 / DWELLINGS
