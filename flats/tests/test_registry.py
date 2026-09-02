"""A jurisdiction declares where its code is.

Which URL serves the ordinance text — rather than a landing page, a table of
contents, or a JavaScript shell that renders one — is knowledge somebody worked
out once by trying four of them. Left in a shell history it is lost, and nothing
can re-fetch the corpus to watch it for amendments; the encoding quietly becomes
a snapshot of whatever the web looked like the week it was done.

These tests pin down that the declaration is the interface: fetching a
jurisdiction takes no arguments beyond naming it, a sweep survives the documents
that fail, and the three sets that ought to agree — declared, stored, cited —
are reconciled rather than assumed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.provenance.fetch import declared, evidence, main
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import RuleLoadError, load_rules

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
FAIRVIEW = "or/multnomah/fairview"

#: Long enough to clear the plausibility guard — a page of furniture is not a
#: document, and the fetch layer refuses one whatever declared it.
CHAPTER = "\n".join(
    ["<html><body>"]
    + [f"<p>33.110.{200 + i} Standard {i}: the minimum setback is {i} feet.</p>" for i in range(30)]
    + ["</body></html>"]
)
OTHER = CHAPTER.replace("33.110", "19.115")

CITE = (
    "cite_default:\n"
    '  cite: "PCC 33.110.220"\n'
    '  url: "https://www.portland.gov/code/33/100s/110"\n'
    "  retrieved: 2026-08-12\n"
)


def write(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def declaring(root: Path, layer: str, docs: str, zones: str = "") -> None:
    write(
        root,
        f"{layer}.yaml",
        f"label: {layer.rsplit('/', 1)[-1]}\n" + CITE + docs + ("zones:\n" + zones if zones else ""),
    )


ONE_DOC = (
    "code:\n"
    '  - id: "33.110"\n'
    "    url: https://www.portland.gov/code/33.110.pdf\n"
    "    title: Single-Dwelling Zones\n"
)


@pytest.fixture()
def bench(tmp_path: Path) -> dict:
    return {
        "root": tmp_path / "jurisdictions",
        "docs": tmp_path / "docs",
        "log": tmp_path / "verifications.jsonl",
    }


def run(bench: dict, *argv: str, get=lambda _u: CHAPTER) -> int:
    return main(
        ["--docs", str(bench["docs"]), "--rules", str(bench["root"]), "--log", str(bench["log"]),
         *argv],
        get=get,
    )


# --- the declaration --------------------------------------------------


def test_a_layer_lists_the_documents_its_rules_come_from(bench: dict) -> None:
    declaring(bench["root"], PORTLAND, ONE_DOC)

    layer = load_rules(bench["root"])[PORTLAND]

    assert [d.id for d in layer.code] == ["33.110"]
    assert layer.code[0].title == "Single-Dwelling Zones"


def test_the_store_path_is_derived_from_the_layer_and_the_id(bench: dict) -> None:
    # So a quote written by hand and a document fetched by the registry land in
    # the same place without anybody coordinating.
    declaring(bench["root"], PORTLAND, ONE_DOC)

    layer = load_rules(bench["root"])[PORTLAND]

    assert layer.document_path("33.110") == f"{PORTLAND}/33.110.txt"
    assert list(layer.documents()) == [f"{PORTLAND}/33.110.txt"]


def test_a_geoid_prefix_is_dropped_from_the_document_path(bench: dict) -> None:
    # Directory names carry a GEOID so two Springfields can sit side by side.
    # A quote is read by a person in a review queue, and the GEOID form is not.
    geoid = "or/41051-multnomah/4159000-portland"
    declaring(bench["root"], geoid, ONE_DOC)

    layer = load_rules(bench["root"])[geoid]

    assert layer.document_path("33.110") == "or/multnomah/portland/33.110.txt"


def test_a_document_declared_twice_is_refused(bench: dict) -> None:
    # Both would fetch to the same file and the second would overwrite the first
    # on every run, with nothing to show for it.
    declaring(bench["root"], PORTLAND, ONE_DOC + '  - id: "33.110"\n    url: http://x.gov/other\n')

    with pytest.raises(RuleLoadError, match="declared twice"):
        load_rules(bench["root"])


def test_a_document_id_may_not_be_a_path(bench: dict) -> None:
    declaring(bench["root"], PORTLAND, 'code:\n  - id: "../secrets"\n    url: http://x.gov/a\n')

    with pytest.raises(RuleLoadError, match="path separator"):
        load_rules(bench["root"])


def test_declaring_nothing_is_a_legitimate_state(bench: dict) -> None:
    # Most layers are unencoded, and an empty registry is the honest way to say
    # so — not an error to be worked around.
    declaring(bench["root"], PORTLAND, "")

    assert load_rules(bench["root"])[PORTLAND].code == ()


# --- fetching from it -------------------------------------------------


def test_a_jurisdiction_is_fetched_by_name(bench: dict, capsys) -> None:
    declaring(bench["root"], PORTLAND, ONE_DOC)

    assert run(bench, "--layer", PORTLAND) == 0

    assert ProvenanceStore(bench["docs"]).exists(f"{PORTLAND}/33.110.txt")
    assert "1/1 document(s) current" in capsys.readouterr().out


def test_the_layer_filter_is_a_prefix(bench: dict, capsys) -> None:
    # A county and its cities come back together, which is how encoding work is
    # actually scoped.
    declaring(bench["root"], PORTLAND, ONE_DOC)
    declaring(bench["root"], FAIRVIEW, ONE_DOC.replace("33.110", "19.115"))

    assert run(bench, "--layer", "or/multnomah") == 0
    assert "2/2 document(s) current" in capsys.readouterr().out


def test_everything_declared_can_be_swept_at_once(bench: dict, capsys) -> None:
    declaring(bench["root"], PORTLAND, ONE_DOC)
    declaring(bench["root"], FAIRVIEW, ONE_DOC.replace("33.110", "19.115"))

    assert run(bench, "--all") == 0
    assert "2/2" in capsys.readouterr().out


def test_a_second_sweep_reports_no_change(bench: dict, capsys) -> None:
    # What makes this a drift watch rather than a download: running it weekly
    # has to be quiet until something is actually amended.
    declaring(bench["root"], PORTLAND, ONE_DOC)
    run(bench, "--all")
    capsys.readouterr()

    assert run(bench, "--all") == 0
    assert "unchanged" in capsys.readouterr().out


def test_a_sweep_reports_an_amended_document_and_stores_nothing(bench: dict, capsys) -> None:
    declaring(bench["root"], PORTLAND, ONE_DOC)
    run(bench, "--all")
    capsys.readouterr()
    amended = CHAPTER.replace("minimum setback is 5 feet", "minimum setback is 15 feet")

    assert run(bench, "--all", get=lambda _u: amended) == 1

    out = capsys.readouterr()
    assert "CHANGED" in out.err
    assert "needs attention" in out.out


def test_one_bad_document_does_not_stop_the_sweep(bench: dict, capsys) -> None:
    # The point of a corpus watch is the report at the end. A run that halts on
    # the first 403 tells you about one city instead of eighty.
    declaring(bench["root"], PORTLAND, ONE_DOC)
    declaring(bench["root"], FAIRVIEW, ONE_DOC.replace("33.110", "19.115"))
    served = {}

    def get(url: str) -> str:
        served[url] = served.get(url, 0) + 1
        return "" if "19.115" in url else CHAPTER

    assert run(bench, "--all", get=get) == 1

    out = capsys.readouterr().out
    assert "1/2 document(s) current" in out
    assert ProvenanceStore(bench["docs"]).exists(f"{PORTLAND}/33.110.txt")


def test_check_reports_a_missing_document_without_storing_it(bench: dict, capsys) -> None:
    declaring(bench["root"], PORTLAND, ONE_DOC)

    assert run(bench, "--all", "--check") == 1

    assert "MISSING" in capsys.readouterr().err
    assert not ProvenanceStore(bench["docs"]).exists(f"{PORTLAND}/33.110.txt")


def test_a_scope_that_declares_nothing_says_so(bench: dict, capsys) -> None:
    declaring(bench["root"], PORTLAND, ONE_DOC)

    assert run(bench, "--layer", "or/clackamas") == 1
    assert "no documents declared" in capsys.readouterr().err


def test_a_path_and_a_layer_together_are_refused(bench: dict) -> None:
    declaring(bench["root"], PORTLAND, ONE_DOC)

    with pytest.raises(SystemExit):
        run(bench, "a/b.txt", "http://x.gov", "--layer", PORTLAND)


def test_the_one_off_form_still_works(bench: dict) -> None:
    # Declaring is for a jurisdiction being maintained; a one-off is for finding
    # out whether a URL is worth declaring.
    declaring(bench["root"], PORTLAND, "")

    assert run(bench, f"{PORTLAND}/33.110.txt", "https://portland.gov/x") == 0


def test_declared_lists_every_document_with_its_layer(bench: dict) -> None:
    declaring(bench["root"], PORTLAND, ONE_DOC)
    declaring(bench["root"], FAIRVIEW, ONE_DOC.replace("33.110", "19.115"))

    found = declared(load_rules(bench["root"]))

    assert [(layer.layer, path) for layer, path, _ in found] == [
        (FAIRVIEW, f"{FAIRVIEW}/19.115.txt"),
        (PORTLAND, f"{PORTLAND}/33.110.txt"),
    ]


# --- reconciling what we have -----------------------------------------


def test_a_document_cited_but_never_declared_is_the_loud_one(bench: dict) -> None:
    # Nothing will re-fetch it, so an amendment to it passes unnoticed while
    # every value on it goes on reading as verified. The worst of the three
    # because everything looks fine.
    declaring(
        bench["root"],
        PORTLAND,
        "",
        f'  R5:\n    setback_front_ft:\n      value: 10\n      quote: "{PORTLAND}/33.110.txt#L2"\n',
    )

    report = evidence(load_rules(bench["root"]), ProvenanceStore(bench["docs"]))

    assert report.undeclared == (f"{PORTLAND}/33.110.txt",)
    assert not report.clean


def test_a_declared_document_nobody_fetched_is_ordinary_work(bench: dict) -> None:
    declaring(bench["root"], PORTLAND, ONE_DOC)

    report = evidence(load_rules(bench["root"]), ProvenanceStore(bench["docs"]))

    assert report.unfetched == (f"{PORTLAND}/33.110.txt",)


def test_a_stored_document_nothing_cites_is_not_a_problem(bench: dict) -> None:
    # A chapter fetched ahead of the encoding is the normal order of work, so
    # this is reported and does not fail the audit.
    declaring(bench["root"], PORTLAND, ONE_DOC)
    run(bench, "--all")

    report = evidence(load_rules(bench["root"]), ProvenanceStore(bench["docs"]))

    assert report.uncited == (f"{PORTLAND}/33.110.txt",)
    assert report.clean


def test_an_incorporation_counts_as_a_citation(bench: dict) -> None:
    # It is a rule read from a document like any other, and if it were left out
    # the document backing it would look orphaned and get cleaned up.
    declaring(
        bench["root"],
        PORTLAND,
        ONE_DOC,
        f'  R-6:\n    setback_front_ft: 20\n  VSF:\n    like:\n      zone: R-6\n'
        f'      quote: "{PORTLAND}/33.110.txt#L4"\n',
    )
    run(bench, "--all")

    report = evidence(load_rules(bench["root"]), ProvenanceStore(bench["docs"]))

    assert report.uncited == ()


def test_a_definition_counts_as_a_citation(bench: dict) -> None:
    """A definitions chapter is evidence, and the audit could not see it.

    ``corner_lot`` is not decoration -- it decides which limb of a setback a
    lot takes, four codes define it four incompatible ways, and each one is
    quoted out of a definitions chapter fetched for no other purpose. The
    reconciliation walked value quotes only, so on 2026-09-02 it reported
    eleven of those chapters as "stored, no value points at it": the store
    failing to recognise its own evidence, which is the same blindness the
    cross-reference ledger had.

    The direction of the error is what makes it worth a test. An orphaned
    document is a candidate for deletion, and deleting the page a definition
    was read from would strand the definition.
    """
    declaring(
        bench["root"],
        PORTLAND,
        ONE_DOC
        + "definitions:\n"
        "  corner_lot:\n"
        "    test: intersecting_frontages\n"
        f'    quote: "{PORTLAND}/33.110.txt#L4"\n'
        '    cite: "PCC 33.910, Corner Lot"\n',
    )
    run(bench, "--all")

    report = evidence(load_rules(bench["root"]), ProvenanceStore(bench["docs"]))

    assert report.uncited == ()


def test_the_denominator_a_standard_is_measured_on_counts_as_a_citation(
    bench: dict,
) -> None:
    """Seven cities mean seven different things by "net acres".

    Which one a density figure divides by is a reading in its own right, taken
    from its own passage -- usually a definitions chapter rather than the table
    the number is printed in. `measured_on_quote` is where that passage goes,
    and it is a citation exactly like the number's own.
    """
    declaring(
        bench["root"],
        PORTLAND,
        ONE_DOC,
        "  R5:\n"
        "    min_density_du_per_acre:\n"
        "      value: 8\n"
        f'      quote: "{PORTLAND}/33.110.txt#L2"\n'
        "      measured_on:\n"
        "        fact: net_developable_area\n"
        '        cite: PCC 33.910 "Net Site Area"\n'
        f'        quote: "{PORTLAND}/33.910.txt#L7"\n',
    )

    report = evidence(load_rules(bench["root"]), ProvenanceStore(bench["docs"]))

    assert f"{PORTLAND}/33.910.txt" in report.undeclared


def test_a_variant_citing_another_chapter_counts_as_a_citation(bench: dict) -> None:
    declaring(
        bench["root"],
        PORTLAND,
        "",
        "  R5:\n"
        "    setback_front_ft:\n"
        "      value: 10\n"
        f'      quote: "{PORTLAND}/33.110.txt#L2"\n'
        "      variants:\n"
        "        - value: 5\n"
        "          when: [affordable]\n"
        f'          quote: "{PORTLAND}/33.120.txt#L9"\n',
    )

    report = evidence(load_rules(bench["root"]), ProvenanceStore(bench["docs"]))

    assert f"{PORTLAND}/33.120.txt" in report.undeclared


def test_the_audit_reports_all_three_sets(bench: dict, capsys) -> None:
    declaring(bench["root"], PORTLAND, ONE_DOC)

    assert run(bench, "--audit") == 1

    out = capsys.readouterr().out
    assert "1 declared, 0 stored, 0 cited" in out
    assert "UNFETCHED" in out
