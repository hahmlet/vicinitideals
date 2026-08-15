"""Writing the citation a person read, and the check that survives them reading it.

Every other path into a rule file is a machine agreeing with itself: a reader
finds a number in a column, the encoding says the same number, and the citation
is written because the two matched. This path has no such agreement behind it —
somebody looked at the page and said *that line*. So the checks that remain are
the ones a person cannot accidentally satisfy: the value must actually be held
out (re-citing a signed value silently replaces evidence somebody chose), and
the line must actually print the number (the commonest way to mis-cite a
flattened table is to pick the row above the one you meant, and the row above
states a different number by definition).

What is deliberately unchecked is the column. That is the thing the readers
could not resolve and the person could, and re-imposing it would refuse every
citation this command exists to accept.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from flats.encode.cite import main
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit

DOC = "or/clackamas/happy-valley/16.22.residential.txt"
LAYER = "or/clackamas/happy-valley"

CITE = {
    "cite": "HV LDC 16.22.020 Table 16.22.020-2",
    "url": "https://ecode360.com/print/HA4934?guid=43529907",
    "retrieved": "2026-08-15",
}

#: The shape no reader will claim: three districts across, and a cell that
#: states two numbers because a townhome may build to the line.
TEXT = """Table 16.22.020-2 Development Standards for R-40, R-20, R-15
Standard                 R-40          R-20          R-15
Interior side            15/04 feet    10/04 feet    7/04 feet
Building height          45 feet5      45 feet5      45 feet5
Quadplexes
P
P
"""

FILE = {
    "label": "Happy Valley",
    "kind": "city",
    "eligible": True,
    "zones": {
        "R40": {"cite_default": CITE, "setback_side_ft": 15, "quadplex_allowed": True},
        "R20": {
            "cite_default": CITE,
            "setback_side_ft": {"value": 10, "quote": f"{DOC}#L3"},
        },
    },
}


@pytest.fixture()
def rules(tmp_path: Path) -> Path:
    root = tmp_path / "jurisdictions" / "or" / "clackamas"
    root.mkdir(parents=True)
    (root.parent / "_state.yaml").write_text(
        yaml.safe_dump({"label": "Oregon", "kind": "state", "zones": {}}), encoding="utf-8"
    )
    (root / "happy-valley.yaml").write_text(yaml.safe_dump(FILE), encoding="utf-8")
    return tmp_path / "jurisdictions"


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    ProvenanceStore(root).save(DOC, url=CITE["url"], text=TEXT, retrieved=date(2026, 8, 15))
    return root


def run(rules: Path, store: Path, zone: str, field: str, quote: str, *extra: str) -> int:
    return main([LAYER, zone, field, quote, "--rules", str(rules), "--docs", str(store), *extra])


def loaded(rules: Path) -> dict:
    path = rules / "or" / "clackamas" / "happy-valley.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_a_line_stating_the_number_is_written(rules: Path, store: Path) -> None:
    """The cell reads "15/04 feet", which no reader will call a 15.

    A person reading the page settles it in a second, and this is where that
    answer goes.
    """
    assert run(rules, store, "R40", "setback_side_ft", f"{DOC}#L3", "--apply") == 0

    assert loaded(rules)["zones"]["R40"]["setback_side_ft"]["quote"] == f"{DOC}#L3"


def test_the_value_reaches_the_zone_once_it_is_cited(rules: Path, store: Path) -> None:
    """Which is the whole point: held out is not screened, cited is."""
    run(rules, store, "R40", "setback_side_ft", f"{DOC}#L3", "--apply")

    layer = load_rules(rules, strict=False)[LAYER]

    assert layer.zones["R40"].values["setback_side_ft"].value == 15
    assert not [w for w in layer.wanted if w.field == "setback_side_ft" and w.zone == "R40"]


def test_a_line_that_does_not_state_the_number_is_refused(rules: Path, store: Path) -> None:
    """Off by one row is the mistake this catches.

    In a flattened grid the row above is a different standard printing a
    different number, and a citation to it reads exactly as correct as a right
    one — the reviewer checks the number against the sentence and nothing else.
    """
    assert run(rules, store, "R40", "setback_side_ft", f"{DOC}#L4", "--apply") == 1

    assert loaded(rules)["zones"]["R40"]["setback_side_ft"] == 15


def test_a_permission_is_checked_by_its_housing_type(rules: Path, store: Path) -> None:
    """A boolean has no number, so what is checked is that the line names it."""
    assert run(rules, store, "R40", "quadplex_allowed", f"{DOC}#L5", "--apply") == 0
    assert loaded(rules)["zones"]["R40"]["quadplex_allowed"]["quote"] == f"{DOC}#L5"


def test_a_permission_cited_against_a_line_naming_no_type_is_refused(
    rules: Path, store: Path
) -> None:
    assert run(rules, store, "R40", "quadplex_allowed", f"{DOC}#L4") == 1


def test_a_value_that_already_carries_a_citation_is_refused(rules: Path, store: Path) -> None:
    """Re-citing replaces evidence somebody chose with evidence somebody typed.

    R20 is already quoted, and the fact that the new citation would point at
    the same line is not the point — the next one would not.
    """
    assert run(rules, store, "R20", "setback_side_ft", f"{DOC}#L3", "--apply") == 2


def test_nothing_is_written_without_apply(rules: Path, store: Path) -> None:
    assert run(rules, store, "R40", "setback_side_ft", f"{DOC}#L3") == 0

    assert loaded(rules)["zones"]["R40"]["setback_side_ft"] == 15


def test_a_citation_past_the_end_of_the_document_is_refused(rules: Path, store: Path) -> None:
    assert run(rules, store, "R40", "setback_side_ft", f"{DOC}#L900", "--apply") == 2
