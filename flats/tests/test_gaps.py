"""Why a value carries no citation, which is six answers wearing one name.

The readiness ladder collapses every uncited value into ``unquoted`` and sends
the whole pile to ``attach``. Most of the pile is not attachable, and the two
largest causes — the document never says it, and nothing can read a boolean —
need a chapter and a person respectively, not a citation tool.

These tests are about telling those apart, and one of them is load-bearing in a
way the others are not: a value nothing could check must never be reported as a
value nothing supports. That mistake sends somebody hunting for a chapter that
is already in the store.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from flats.encode.corroborate import Finding, Verdict
from flats.encode.gaps import CAUSES, by_cause, classify, gaps
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit

DOC = "or/multnomah/portland/33.110.txt"
OVERLAY = "or/multnomah/portland/33.440.txt"
LAYER = "or/multnomah/portland"

CITE = {
    "cite": "PCC 33.110.220, Table 110-4",
    "url": "https://www.portland.gov/code/33/100s/110",
    "retrieved": "2026-08-12",
}

#: One zone holding one of each: a plain number, a boolean, and a number that
#: already carries its citation and so is nobody's gap.
FILE = {
    "label": "Portland",
    "kind": "city",
    "eligible": True,
    #: Declared, so a value citing it is one the fetcher knows about — which is
    #: what separates "no document says this" from "nobody fetched the chapter".
    "code": [{"id": "33.110", "url": CITE["url"], "title": "Chapter 33.110"}],
    "zones": {
        "R5": {
            "cite_default": CITE,
            "setback_front_ft": 10,
            "setback_rear_ft": 5,
            "min_lot_sqft": 3000,
            "quadplex_allowed": True,
            "max_height_ft": {"value": 30, "quote": f"{DOC}#L7"},
        },
    },
}


@pytest.fixture()
def layer(tmp_path: Path):
    root = tmp_path / "jurisdictions" / "or" / "multnomah"
    root.mkdir(parents=True)
    (root.parent / "_state.yaml").write_text(
        yaml.safe_dump({"label": "Oregon", "kind": "state", "zones": {}}), encoding="utf-8"
    )
    (root / "portland.yaml").write_text(yaml.safe_dump(FILE), encoding="utf-8")
    return load_rules(tmp_path / "jurisdictions", strict=False)[LAYER]


def finding(field: str, verdict: Verdict, encoded, *found, notes=(), path=DOC) -> Finding:
    return Finding(
        layer=LAYER,
        zone="R5",
        field=field,
        verdict=verdict,
        encoded=encoded,
        found=tuple(found),
        quote=f"{path}#L4",
        notes=notes,
    )


def cause_of(items, field: str) -> str:
    return next(g.cause for g in items if g.field == field)


# --- the causes -------------------------------------------------------


def test_a_clean_agreement_is_quotable_and_names_the_line(layer) -> None:
    found = gaps(layer, [finding("setback_front_ft", Verdict.agrees, 10, 10)])

    gap = next(g for g in found if g.field == "setback_front_ft")
    assert gap.cause == "quotable"
    assert gap.detail == f"{DOC}#L4"
    assert "attach" in gap.action


def test_a_footnoted_number_is_conditional_even_though_it_agrees(layer) -> None:
    # The number matches, so attach would be tempted. It is a base case with an
    # exit, and quoting the base as the whole rule is how the exit disappears.
    found = gaps(layer, [finding("setback_front_ft", Verdict.agrees, 10, 10, notes=("[3] see 33.110.265",))])

    assert cause_of(found, "setback_front_ft") == "conditional"


def test_conditional_only_numbers_are_conditional_not_missing(layer) -> None:
    # `unsupported` carrying numbers means the document does state figures,
    # all of them scoped. That is a reading to make, not a chapter to find.
    found = gaps(layer, [finding("setback_rear_ft", Verdict.unsupported, 5, 8, 12)])

    assert cause_of(found, "setback_rear_ft") == "conditional"


def test_two_numbers_for_one_field_is_multi(layer) -> None:
    found = gaps(layer, [finding("setback_rear_ft", Verdict.agrees, 5, 5, 10)])

    gap = next(g for g in found if g.field == "setback_rear_ft")
    assert gap.cause == "multi"
    assert gap.detail == "5, 10"


def test_a_field_no_document_mentions_is_unsourced(layer) -> None:
    found = gaps(layer, [finding("setback_front_ft", Verdict.agrees, 10, 10)])

    gap = next(g for g in found if g.field == "min_lot_sqft")
    assert gap.cause == "unsourced"
    assert "declare it" in gap.action


def test_a_boolean_is_uncheckable_never_unsourced(layer) -> None:
    # Corroboration emits no finding for a boolean at all, so its silence says
    # nothing about the store. Reporting it as unsourced would send a person
    # looking for a chapter that is very likely already fetched.
    found = gaps(layer, [])

    gap = next(g for g in found if g.field == "quadplex_allowed")
    assert gap.cause == "uncheckable"
    assert gap.detail == "bool"


def test_an_uncheckable_field_is_not_reported_as_missing_evidence(layer) -> None:
    assert by_cause(gaps(layer, []))["unsourced"] == 3  # the three numbers, not the boolean


# --- reading documents together ---------------------------------------


def test_a_disagreement_in_one_document_outranks_agreement_in_another(layer) -> None:
    # Attaching the agreeing chapter's line would bury the finding somebody has
    # to resolve, and it would read afterwards as a cited, settled value.
    found = gaps(
        layer,
        [
            finding("setback_front_ft", Verdict.agrees, 10, 10),
            finding("setback_front_ft", Verdict.differs, 10, 15, path=OVERLAY),
        ],
    )

    gap = next(g for g in found if g.field == "setback_front_ft")
    assert gap.cause == "contested"
    assert gap.detail == "file 10, document 15"


def test_silence_in_one_document_does_not_outvote_evidence_in_another(layer) -> None:
    # Most documents in a jurisdiction mention most fields not at all, so a
    # document with nothing to say has to abstain rather than vote unsourced.
    assert classify(
        [
            finding("setback_front_ft", Verdict.unsupported, 10),
            finding("setback_front_ft", Verdict.agrees, 10, 10, path=OVERLAY),
        ]
    ) == ("quotable", f"{OVERLAY}#L4")


# --- what is not a gap ------------------------------------------------


def test_a_value_that_already_cites_something_is_not_a_gap(layer) -> None:
    assert not [g for g in gaps(layer, []) if g.field == "max_height_ft"]


def test_worst_cause_first(layer) -> None:
    found = gaps(
        layer,
        [
            finding("setback_front_ft", Verdict.differs, 10, 15),
            finding("setback_rear_ft", Verdict.agrees, 5, 5),
        ],
    )

    assert [g.cause for g in found] == sorted(
        (g.cause for g in found), key=CAUSES.index
    )
    assert found[0].cause == "contested"


# --- the citation itself -----------------------------------------------


AGGREGATOR = {
    "label": "West Linn",
    "kind": "city",
    "eligible": True,
    "zones": {
        "R-5": {
            "cite_default": {
                "cite": "West Linn CDC 13.070",
                "url": "https://www.zoneomics.com/code/west-linn-OR/chapter_9",
                "retrieved": "2026-08-12",
            },
            "min_lot_sqft": 5000,
        },
    },
}


def test_an_aggregator_citation_outranks_a_document_that_agrees(tmp_path: Path) -> None:
    # It corroborates. It would attach cleanly. Signing it would put a name on
    # a third party's transcription, so the citation is the finding, not the
    # number — and it has to outrank the agreement rather than hide behind it.
    root = tmp_path / "jurisdictions" / "or" / "clackamas"
    root.mkdir(parents=True)
    (root / "west-linn.yaml").write_text(yaml.safe_dump(AGGREGATOR), encoding="utf-8")
    layer = load_rules(tmp_path / "jurisdictions", strict=False)["or/clackamas/west-linn"]

    found = gaps(
        layer,
        [
            Finding(
                layer="or/clackamas/west-linn",
                zone="R-5",
                field="min_lot_sqft",
                verdict=Verdict.agrees,
                encoded=5000,
                found=(5000,),
                quote="or/clackamas/west-linn/13.txt#L4",
            )
        ],
    )

    assert [(g.cause, g.detail) for g in found] == [("unofficial", "zoneomics.com")]


OTHER_CHAPTER = "https://www.portland.gov/code/33/200s/266"


def test_a_value_naming_an_undeclared_chapter_is_not_a_hunt(tmp_path: Path) -> None:
    # The zone cites a real chapter of the real code, and `code:` does not list
    # it, so nothing has ever fetched it. That is one line of YAML away from
    # readable; calling it unsourced sends somebody hunting for a URL that is
    # already written on the value.
    file = dict(FILE)
    file["zones"] = {
        "R2.5": {
            "cite_default": {**CITE, "url": OTHER_CHAPTER},
            "min_lot_sqft": 1600,
        }
    }
    root = tmp_path / "jurisdictions" / "or" / "multnomah"
    root.mkdir(parents=True)
    (root / "portland.yaml").write_text(yaml.safe_dump(file), encoding="utf-8")
    layer = load_rules(tmp_path / "jurisdictions", strict=False)[LAYER]

    found = gaps(layer, [])

    assert [(g.cause, g.detail) for g in found] == [("undeclared", OTHER_CHAPTER)]
