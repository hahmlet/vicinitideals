"""Reading an encoded rule file back against its source.

The value this catches is the one nobody would question: a number that is
plausible, consistent with its neighbours, and absent from the code. Every test
below is about keeping that finding visible and keeping the ones that do not
matter quiet, because a check that cries about coverage curves it cannot read
is a check people learn to skip.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from flats.encode.corroborate import (
    Verdict,
    check_layer,
    check_zone,
    main,
    tally,
)
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Provenance, Value

pytestmark = pytest.mark.unit

DOC = "or/multnomah/portland/33.110.txt"

TEXT = """33.110.220 Setbacks
The required setbacks are stated in Table 110-4.
Table 110-4
Standard                      RF          R5          R2.5
- Front building              20 ft.      10 ft.      10 ft.
 setback
- Side building               10 ft.      5 ft.       5 ft.
 setback
Maximum Height                30 ft.      30 ft.      35 ft.
"""

CITE = {
    "cite": "PCC 33.110.220, Table 110-4",
    "url": "https://www.portland.gov/code/33/100s/110",
    "retrieved": "2026-08-12",
}


def value(number: float | int, name: str = "setback_front_ft") -> Value:
    return Value(name=name, value=number, prov=Provenance(**CITE))


def findings_for(values: dict[str, Value], zone: str = "R5"):
    return check_zone(TEXT, layer="or/multnomah/portland", zone=zone, values=values, path=DOC)


def verdicts(values: dict[str, Value], zone: str = "R5") -> dict[str, Verdict]:
    return {f.field: f.verdict for f in findings_for(values, zone)}


# --- the four verdicts -------------------------------------------------


def test_a_value_the_document_states_agrees() -> None:
    assert verdicts({"setback_front_ft": value(10)})["setback_front_ft"] is Verdict.agrees


def test_a_value_the_document_contradicts_differs() -> None:
    assert verdicts({"setback_front_ft": value(12)})["setback_front_ft"] is Verdict.differs


def test_a_value_the_document_says_nothing_about_is_unsupported() -> None:
    # Not a failure. Most standards are stated somewhere these readers cannot
    # reach, and calling that a defect would bury the ones that are.
    assert verdicts({"min_lot_sqft": value(3000)})["min_lot_sqft"] is Verdict.unsupported


def test_a_standard_the_file_is_missing_is_reported() -> None:
    # The opposite of the usual worry: the code states a rule and the screen
    # does not apply it, so every lot passes a test it never took.
    found = {f.field: f for f in findings_for({"setback_front_ft": value(10)})}

    assert found["max_height_ft"].verdict is Verdict.unencoded
    assert found["max_height_ft"].found == (30,)


def test_only_a_disagreement_blocks() -> None:
    assert Verdict.differs.blocking
    assert not Verdict.agrees.blocking
    assert not Verdict.unsupported.blocking
    assert not Verdict.unencoded.blocking


# --- reading the right column ------------------------------------------


def test_each_zone_is_checked_against_its_own_column() -> None:
    # The whole point. R5's 30 ft. height is not R2.5's, and a check that
    # reads the wrong column certifies the error it was built to catch.
    assert verdicts({"max_height_ft": value(35)}, "R2.5")["max_height_ft"] is Verdict.agrees
    assert verdicts({"max_height_ft": value(35)}, "R5")["max_height_ft"] is Verdict.differs


def test_a_finding_carries_the_line_a_reviewer_opens() -> None:
    found = findings_for({"setback_side_ft": value(5)})[0]

    assert found.quote.startswith(f"{DOC}#L")
    line = int(found.quote.rsplit("#L", 1)[1])
    assert "5 ft." in TEXT.splitlines()[line - 1]


def test_a_disagreement_shows_what_the_document_said() -> None:
    found = findings_for({"setback_front_ft": value(12)})[0]

    assert found.encoded == 12
    assert found.found == (10,)


# --- what it declines to check -----------------------------------------


def test_a_field_no_reader_can_state_as_one_number_is_skipped() -> None:
    # A coverage curve is four (lot size, area, percent) rows. Reporting it
    # unsupported every run teaches a reviewer to skim past the report.
    values = {
        "coverage_curve": Value(
            name="coverage_curve", value=[[0, 0, 50]], prov=Provenance(**CITE)
        )
    }

    assert findings_for(values) == [f for f in findings_for(values) if f.field != "coverage_curve"]


def test_a_permission_flag_is_not_a_measurement() -> None:
    values = {
        "quadplex_allowed": Value(name="quadplex_allowed", value=True, prov=Provenance(**CITE))
    }

    assert not any(f.field == "quadplex_allowed" for f in findings_for(values))


# --- a whole layer -----------------------------------------------------


LAYER = {
    "label": "Portland",
    "kind": "city",
    "eligible": True,
    "zones": {
        "R5": {"cite_default": CITE, "setback_front_ft": 10, "setback_side_ft": 5},
        "R2.5": {"cite_default": CITE, "setback_front_ft": 10, "max_height_ft": 30},
    },
}


@pytest.fixture()
def rules(tmp_path: Path) -> Path:
    root = tmp_path / "jurisdictions" / "or" / "multnomah"
    root.mkdir(parents=True)
    (root.parent / "_state.yaml").write_text(
        yaml.safe_dump({"label": "Oregon", "kind": "state", "zones": {}}), encoding="utf-8"
    )
    (root / "portland.yaml").write_text(yaml.safe_dump(LAYER), encoding="utf-8")
    return tmp_path / "jurisdictions"


def test_every_zone_in_the_layer_is_checked(rules: Path) -> None:
    layer = load_rules(rules, strict=False)["or/multnomah/portland"]

    zones = {f.zone for f in check_layer(TEXT, layer, path=DOC)}

    assert zones == {"R5", "R2.5"}


def test_one_zone_can_be_singled_out(rules: Path) -> None:
    layer = load_rules(rules, strict=False)["or/multnomah/portland"]

    found = check_layer(TEXT, layer, path=DOC, zones=["R2.5"])

    assert {f.zone for f in found} == {"R2.5"}


def test_the_summary_counts_every_verdict(rules: Path) -> None:
    layer = load_rules(rules, strict=False)["or/multnomah/portland"]

    counts = tally(check_layer(TEXT, layer, path=DOC))

    assert counts["agrees"] == 3, "R5 front, R5 side, R2.5 front"
    assert counts["differs"] == 1, "the file says R2.5 is 30 ft.; the table says 35"


# --- the command -------------------------------------------------------


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    ProvenanceStore(root).save(DOC, url=CITE["url"], text=TEXT, retrieved=date(2026, 8, 12))
    return root


def test_the_command_fails_when_a_value_disagrees(rules: Path, store: Path, capsys) -> None:
    code = main(["or/multnomah/portland", "--doc", DOC, "--rules", str(rules), "--docs", str(store)])

    assert code == 1
    assert "differs" in capsys.readouterr().out


def test_the_command_passes_when_nothing_disagrees(rules: Path, store: Path, capsys) -> None:
    code = main(
        ["or/multnomah/portland", "--doc", DOC, "--zone", "R5",
         "--rules", str(rules), "--docs", str(store)]
    )

    assert code == 0


def test_quiet_prints_only_what_blocks(rules: Path, store: Path, capsys) -> None:
    main(
        ["or/multnomah/portland", "--doc", DOC, "--quiet",
         "--rules", str(rules), "--docs", str(store)]
    )
    out = capsys.readouterr().out

    assert "differs" in out
    assert "agrees" not in out.split("against")[0]


def test_an_unknown_layer_is_an_error_not_an_empty_pass(rules: Path, store: Path) -> None:
    code = main(["or/multnomah/nowhere", "--doc", DOC, "--rules", str(rules), "--docs", str(store)])

    assert code == 2


def test_a_missing_document_is_an_error_not_an_empty_pass(rules: Path, store: Path) -> None:
    code = main(
        ["or/multnomah/portland", "--doc", "or/nope.txt",
         "--rules", str(rules), "--docs", str(store)]
    )

    assert code == 2


def test_corroboration_never_promotes_anything(rules: Path, store: Path) -> None:
    # Two machines agreeing is still nobody having read the sentence.
    before = (rules / "or" / "multnomah" / "portland.yaml").read_text(encoding="utf-8")
    main(["or/multnomah/portland", "--doc", DOC, "--rules", str(rules), "--docs", str(store)])

    assert (rules / "or" / "multnomah" / "portland.yaml").read_text(encoding="utf-8") == before
    assert "status" not in before


# --- section scope: how a prose code says whose standard this is -------


PROSE = """Section  4.122.  Residential Zone.
The minimum front yard setback shall be 20 feet.

Section  4.123.  Old Town Residential Zone.
The minimum front yard setback shall be 10 feet.
"""


def _zone(**values):
    from flats.rules.model import Provenance, Value

    prov = Provenance(
        cite="Wilsonville Development Code 4.122",
        url="https://api.municode.com/PublicationPdfDownload/1951",
        retrieved=date(2026, 8, 13),
    )
    return {
        name: Value(name=name, value=value, prov=prov) for name, value in values.items()
    }


def test_a_prose_standard_under_a_declared_section_is_zone_keyed() -> None:
    # Most of Oregon writes standards this way: a heading names the zone and
    # the paragraphs under it state the numbers. Without section scope none of
    # it counts as evidence, because a sentence in a 22,000-line chapter does
    # not say whose setback it is.
    found = check_zone(
        PROSE,
        layer="or/clackamas/wilsonville",
        zone="R",
        values=_zone(setback_front_ft=20),
        path="doc.txt",
        sections=("4.122",),
    )

    assert [f.verdict for f in found] == [Verdict.agrees]


def test_the_neighbouring_section_does_not_speak_for_this_zone() -> None:
    # 4.123 states 10 feet for a different zone. Counting it would report a
    # disagreement that is the reader's fault, and a page of those gets skimmed
    # past the one real disagreement in it.
    found = check_zone(
        PROSE,
        layer="or/clackamas/wilsonville",
        zone="R",
        values=_zone(setback_front_ft=20),
        path="doc.txt",
        sections=("4.122",),
    )

    assert found[0].found == (20,)


def test_without_a_declared_section_prose_states_nothing() -> None:
    # The default stays deliberately deaf. An encoder declaring `section:` is
    # making a checkable claim; inferring it from heading text would attribute
    # one zone's setback to another silently.
    found = check_zone(
        PROSE,
        layer="or/clackamas/wilsonville",
        zone="R",
        values=_zone(setback_front_ft=20),
        path="doc.txt",
    )

    assert [f.verdict for f in found] == [Verdict.unsupported]


def test_a_section_prefix_matches_its_subsections() -> None:
    # A code numbering paragraphs 4.113.02 states the same standard as 4.113.
    # Requiring an exact match would need every subsection listed by hand.
    text = "Section 4.113.02 Setbacks.\nThe minimum front yard setback shall be 20 feet.\n"
    found = check_zone(
        text,
        layer="l",
        zone="R",
        values=_zone(setback_front_ft=20),
        path="doc.txt",
        sections=("4.113",),
    )

    assert [f.verdict for f in found] == [Verdict.agrees]


def test_a_heading_printed_with_the_word_section_is_still_a_heading() -> None:
    # Portland prints "33.110.220 Development Standards"; Wilsonville prints
    # "Section  4.122.  Residential Zone". Reading only the first shape leaves
    # every paragraph of the second attributed to whatever came before it.
    from flats.encode.extract import extract

    read = extract(PROSE, path="doc.txt", jurisdiction="l", zone="R")

    assert {c.section for c in read.candidates} == {"4.122", "4.123"}


def test_a_heading_prefixed_with_the_code_s_own_initials_is_still_a_heading() -> None:
    # Tualatin prints "TDC 40.100. Purpose." — the code's initials in front of
    # every heading. A third shape, same failure as the other two if unread.
    from flats.encode.extract import extract

    text = (
        "TDC 40.300. DevelopmentStandards.\n"
        "The minimum front yard setback shall be 20 feet.\n"
    )
    read = extract(text, path="doc.txt", jurisdiction="l", zone="RL")

    assert {c.section for c in read.candidates} == {"40.300"}


def test_a_sentence_starting_with_a_short_word_is_not_a_heading() -> None:
    # The initials form is case-sensitive inside an otherwise case-insensitive
    # pattern: "The 10.25 acre site" and "and 40.100" must not read as
    # headings, or every number after them lands in a section that does not
    # exist.
    from flats.encode.extract import _SECTION

    assert _SECTION.match("The 10.25 acre site") is None
    assert _SECTION.match("and 40.100 is referenced") is None
