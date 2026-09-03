"""A number that is drawn on a sheet rather than written in a sentence.

Clackamas County is the case this exists for and, as of 2026-09-03, the only
one. ZDO 1015.02(A)(4) hands stall and aisle dimensions to the Roadway
Standards, 320.3(a) hands them on to Standard Drawings P100 and P200, and both
sheets carry three lines of title block with every dimension as CAD geometry.
The chain of authority is complete and it terminates in a picture. It cost the
county 17,486 lots -- more than any other open question in the project -- for
the month nobody could reach the aisle.

`drawn: true` is the way out, and the thing it is NOT is a way around the
evidence rule. It says the figure was read off the sheet, by a named person, on
a named date, and it forfeits the one thing every other value here has: a later
reader cannot open the quote and check, because there is no quote. So the
bargain is enforced at both ends -- a drawn figure must carry a reader and a
date, and it must not carry a quote -- and the readiness ledger reports these
rows for the life of the value instead of clearing them.

What is guarded hardest is the *exemption*. `drawn` lets a value past the
quarantine that holds every unquoted number out of the screen, so a flag set by
accident, or set on a number nobody actually read, is the one mistake in this
module that reaches a verdict.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Provenance, Value

pytestmark = pytest.mark.unit

COUNTY = "or/clackamas/_unincorporated"

#: The sheet, as the corpus cites it.
SHEET = "https://dochub.clackamas.us/documents/drupal/6dab9eb0-a4d6-44bc-8246-bc4465676fbd"


def _prov(**over: object) -> dict:
    base = dict(
        cite="Clackamas County Roadway Standard Drawing P100, 90 degrees",
        url=SHEET,
        retrieved="2026-08-27",
        drawn=True,
        read_by="sjk",
        read_on="2026-09-03",
    )
    base.update(over)
    return base


def _value(**over: object) -> Value:
    return Value(name="parking_aisle_two_way_ft", value=24, prov=Provenance(**_prov(**over)))


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
        "      cite: Standard Drawing P100\n"
        "      url: https://example.invalid/p100\n"
        "      retrieved: '2026-08-27'\n" + body,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )
    return root


def test_the_county_aisle_is_twenty_four_feet_and_reaches_the_screen() -> None:
    """The number itself, and the fact that it is not in the holding queue.

    `wanted` is where the loader parks every value with no quote, on the
    reasoning that a number nobody has sourced is encoding debt rather than an
    answer. A drawn figure would sit there forever -- it will never acquire a
    quote, however long it waits -- so the exemption is what makes the value
    usable at all, and this asserts both halves at once.
    """
    county = load_rules()[COUNTY]
    for name in ("parking_aisle_two_way_ft", "parking_aisle_one_way_ft"):
        aisle = county.defaults[name]
        assert aisle.value == 24
        assert aisle.prov.drawn
        assert aisle.prov.read_by == "sjk"
        assert aisle.prov.quote is None
    assert [(w.zone, w.field) for w in county.wanted] == []


def test_the_ledger_keeps_reporting_a_drawn_figure_rather_than_clearing_it() -> None:
    """It is not `unquoted` -- that rung means nobody has sourced the number,
    and this one is sourced to a sheet and a person. It gets its own row, and
    that row never goes away, because the weakness it records never does."""
    county = load_rules()[COUNTY]
    ready = readiness_for(county, store=ProvenanceStore())
    assert set(ready.drawn) == {
        ("defaults", "parking_aisle_two_way_ft"),
        ("defaults", "parking_aisle_one_way_ft"),
    }
    assert ready.unquoted == ()
    assert ready.stage != "unquoted"


def test_a_drawn_figure_nobody_signed_their_name_to_is_refused() -> None:
    """Without a reader and a date it is an unsourced number wearing a flag
    that tells the ledger to stop asking about it -- strictly worse than an
    unsourced number, which at least stays in the queue."""
    with pytest.raises(ValueError, match="read_by"):
        _value(read_by=None)
    with pytest.raises(ValueError, match="read_on"):
        _value(read_on=None)


def test_a_drawn_figure_may_not_also_carry_a_quote() -> None:
    """The two are a contradiction. If the number turns out to be written in
    words somewhere, that sentence is the evidence and the flag comes off; the
    corpus must not hold a row claiming both kinds of proof, because the ledger
    would check the text and report the value clean while the flag quietly
    exempts it from everything else."""
    with pytest.raises(ValueError, match="no text to quote"):
        _value(quote=f"{COUNTY}/roadway.p100.txt#L2")


def test_an_unquoted_number_without_the_flag_is_still_held_out(tmp_path: Path) -> None:
    """The guard the exemption is cut into, tested from the other side.

    Drop `drawn` and the same value goes to the holding queue and never reaches
    a zone. If this stopped being true the flag would be decoration and any
    unsourced number in the corpus would screen lots.
    """
    rules = load_rules(
        _somewhere(tmp_path, "    parking_aisle_two_way_ft:\n      value: 24\n"),
        strict=True,
    )
    layer = rules["or/multnomah/somewhere"]
    assert "parking_aisle_two_way_ft" not in layer.zones["R-6"].values
    assert [(w.zone, w.field) for w in layer.wanted] == [("R-6", "parking_aisle_two_way_ft")]


def test_the_flag_carries_a_number_into_a_zone_from_yaml(tmp_path: Path) -> None:
    """The path the county takes, exercised on a layer of its own so the test
    fails on the mechanism rather than on the corpus."""
    rules = load_rules(
        _somewhere(
            tmp_path,
            "    parking_aisle_two_way_ft:\n"
            "      value: 24\n"
            "      drawn: true\n"
            "      read_by: sjk\n"
            "      read_on: '2026-09-03'\n",
        ),
        strict=True,
    )
    aisle = rules["or/multnomah/somewhere"].zones["R-6"].values["parking_aisle_two_way_ft"]
    assert aisle.value == 24
    assert aisle.prov.drawn and aisle.prov.read_by == "sjk"


def test_a_drawn_flag_with_nothing_behind_it_fails_the_whole_file(tmp_path: Path) -> None:
    """A bad flag has to stop the load, not degrade quietly to a draft value.

    This is the accident the module is most exposed to: `drawn: true` typed on
    a number nobody read. It must be an error in the file, collected with every
    other problem, rather than a value that screens lots.
    """
    with pytest.raises(RuleLoadError, match="read_by"):
        load_rules(
            _somewhere(
                tmp_path,
                "    parking_aisle_two_way_ft:\n      value: 24\n      drawn: true\n",
            ),
            strict=True,
        )
