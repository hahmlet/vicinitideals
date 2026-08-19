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
from flats.rules.model import Layer, Provenance, Value, Zone

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


def test_a_line_the_readers_refuse_is_unread_not_unsourced(layer) -> None:
    """Two different afternoons, and the ledger has to say which.

    "Unsourced" means find the chapter, fetch it, declare it. Eighty-eight of
    the eighty-nine values under that heading were printed in a document
    already in the store, in a shape no reader will claim: a cell reading
    "15/04 feet", a row written for five housing types at once, a column headed
    "R-5 – R-30". Those are two minutes of reading, not an afternoon of
    hunting, and calling them the same thing buries them.
    """
    found = gaps(
        layer,
        [finding("setback_front_ft", Verdict.agrees, 10, 10)],
        {("R5", "min_lot_sqft"): f"{DOC}#L42"},
    )

    gap = next(g for g in found if g.field == "min_lot_sqft")
    assert gap.cause == "unread"
    assert gap.detail == f"{DOC}#L42"
    assert "read the line" in gap.action


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


def test_a_zone_that_adopts_another_by_inference_is_unmapped(tmp_path: Path) -> None:
    """Happy Valley's R20CC is a code in the zoning layer and not in the
    ordinance: LDC 16.22 names R-40, R-20 and R-15 and nothing with a CC on
    it. The file adopts R-20's standards, which is a claim about a map legend
    rather than a sentence anybody can quote — so it never reached the values
    queue, and the ladder sent a reviewer to a command that printed nothing."""
    file = {**FILE, "zones": {**FILE["zones"], "R5CC": {"cite_default": CITE, "like": "R5"}}}
    root = tmp_path / "jurisdictions" / "or" / "multnomah"
    root.mkdir(parents=True)
    (root.parent / "_state.yaml").write_text(
        yaml.safe_dump({"label": "Oregon", "kind": "state", "zones": {}}), encoding="utf-8"
    )
    (root / "portland.yaml").write_text(yaml.safe_dump(file), encoding="utf-8")
    layer = load_rules(tmp_path / "jurisdictions", strict=False)[LAYER]

    found = gaps(layer, [])
    unmapped = [g for g in found if g.cause == "unmapped"]

    assert [(g.zone, g.field, g.detail) for g in unmapped] == [("R5CC", "like", "R5")]
    assert "ask the city" in unmapped[0].action


def test_an_incorporation_somebody_quoted_is_nobody_s_gap(tmp_path: Path) -> None:
    """A code that states its own incorporation — "the R-6 use list applies in
    the VSF zone" — is a rule that was read, and it is not this queue's."""
    file = {
        **FILE,
        "zones": {
            **FILE["zones"],
            "R5A": {"cite_default": CITE, "like": {"zone": "R5", "quote": f"{DOC}#L9"}},
        },
    }
    root = tmp_path / "jurisdictions" / "or" / "multnomah"
    root.mkdir(parents=True)
    (root.parent / "_state.yaml").write_text(
        yaml.safe_dump({"label": "Oregon", "kind": "state", "zones": {}}), encoding="utf-8"
    )
    (root / "portland.yaml").write_text(yaml.safe_dump(file), encoding="utf-8")
    layer = load_rules(tmp_path / "jurisdictions", strict=False)[LAYER]

    assert not [g for g in gaps(layer, []) if g.cause == "unmapped"]


def test_the_three_unmapped_zones_in_the_corpus_are_named() -> None:
    """All three are the same thing: a zoning-layer label whose base zone was
    inferred. None of them can be closed by reading a code."""
    from flats.encode.gaps import gaps as gaps_for

    held = {
        (lid, g.zone)
        for lid, layer in load_rules(strict=False).items()
        for g in gaps_for(layer, [])
        if g.cause == "unmapped"
    }

    assert held == {
        ("or/clackamas/happy-valley", "R20CC"),
        ("or/multnomah/fairview", "RM/TOZ"),
        ("or/multnomah/fairview", "R/SFLD"),
    }


def _layer(setbacks: dict[str, int]) -> Layer:
    """A layer of one standard per zone, built without touching the YAML."""
    return Layer(
        layer="or/x",
        kind="city",
        label="X",
        zones={
            code: Zone(
                zone=code,
                values={
                    "setback_front_ft": Value(
                        name="setback_front_ft", value=number, prov=Provenance(**CITE)
                    )
                },
            )
            for code, number in setbacks.items()
        },
    )


def test_the_digest_ignores_a_file_being_tidied():
    """It hashes answers, not bytes.

    A digest over the YAML files would move for a comment, a re-indent or a
    reordering, and a staleness warning that fires every time somebody tidies
    is a staleness warning nobody reads.
    """
    from flats.encode.gaps import digest

    def build(order):
        return {"or/x": _layer({code: 10 for code in order})}

    assert digest(build(["R1", "R2"])) == digest(build(["R2", "R1"]))


def test_the_digest_moves_when_an_answer_does():
    from flats.encode.gaps import digest

    assert digest({"or/x": _layer({"R1": 10})}) != digest({"or/x": _layer({"R1": 15})})


def test_a_ledger_nobody_has_written_is_absent_not_empty(tmp_path):
    """None and "no gaps" are opposite answers; a missing file must not read as
    a clean corpus."""
    from flats.encode.gaps import read_ledger

    assert read_ledger(tmp_path / "nothing.json") is None
