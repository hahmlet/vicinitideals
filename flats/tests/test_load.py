"""The one load path the screen may use: parse, promote, demote.

The invariant under test is that trust cannot be typed. A rule file may say
what the code says; only a signature says somebody read it, and only intact
evidence keeps that signature standing.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from flats.encode.load import load_trusted, tally
from flats.encode.verify import VerificationLog, sign
from flats.provenance.staleness import EVIDENCE_MISSING, SOURCE_CHANGED
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Status
from flats.rules.resolver import Verdict

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
REVIEWED = date(2026, 8, 14)
DOC = "or/multnomah/portland/33.110.txt"
TEXT = "33.110.220 Development Standards\nFront setback: 10 feet.\nSide setback: 5 feet.\n"

CITE = (
    "cite_default:\n"
    '  cite: "PCC 33.110.220, Table 110-4"\n'
    '  url: "https://www.portland.gov/code/33/100s/110"\n'
    "  retrieved: 2026-08-12\n"
    f'  quote: "{DOC}#L2"\n'
)


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    p = tmp_path / "jurisdictions" / f"{PORTLAND}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "label: Portland\n" + CITE + "zones:\n  R5:\n    setback_front_ft: 10\n",
        encoding="utf-8",
    )
    return tmp_path / "jurisdictions"


@pytest.fixture()
def store(tmp_path: Path) -> ProvenanceStore:
    s = ProvenanceStore(tmp_path / "docs")
    s.save(DOC, url="https://www.portland.gov/code/33/100s/110", text=TEXT, retrieved=REVIEWED)
    return s


def signed(root: Path, *, value: int = 10) -> VerificationLog:
    v = load_rules(root)[PORTLAND].zones["R5"].values["setback_front_ft"]
    assert v.value == value
    return VerificationLog(
        [sign(PORTLAND, "R5", "setback_front_ft", v, reviewer="sjk", reviewed=REVIEWED)]
    )


def front(t) -> object:
    return t.layers[PORTLAND].zones["R5"].values["setback_front_ft"]


# --- the three passes -------------------------------------------------


def test_an_unsigned_rule_file_yields_nothing_trusted(root: Path, store: ProvenanceStore) -> None:
    t = load_trusted(root, log=VerificationLog(), store=store)

    assert front(t).status is Status.draft
    assert t.rules.resolve(PORTLAND, "R5").verdict is Verdict.unverified


def test_a_signed_value_loads_verified(root: Path, store: ProvenanceStore) -> None:
    t = load_trusted(root, log=signed(root), store=store)

    assert front(t).status is Status.verified
    assert front(t).reviewer == "sjk"
    assert t.orphans == ()
    assert t.stale == ()


def test_editing_the_number_after_signing_drops_it_back_to_draft(
    root: Path, store: ProvenanceStore
) -> None:
    log = signed(root)
    p = root / f"{PORTLAND}.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("setback_front_ft: 10", "setback_front_ft: 15"), encoding="utf-8")

    t = load_trusted(root, log=log, store=store)

    assert front(t).status is Status.draft
    assert [o.field for o in t.orphans] == ["setback_front_ft"]


def test_editing_the_evidence_demotes_a_signed_value(root: Path, store: ProvenanceStore) -> None:
    # Local tampering, caught without a network: the stored text no longer
    # hashes to what was recorded, so everything citing it stops being trusted.
    store.text_path(DOC).write_text(TEXT.replace("10 feet", "20 feet"), encoding="utf-8", newline="")

    t = load_trusted(root, log=signed(root), store=store)

    assert front(t).status is Status.stale
    assert t.tampered == (DOC,)
    assert t.stale[0].reason == SOURCE_CHANGED


def test_an_upstream_change_demotes_a_signed_value(root: Path, store: ProvenanceStore) -> None:
    t = load_trusted(root, log=signed(root), store=store, invalidated=[DOC])

    assert front(t).status is Status.stale
    assert t.stale[0].reason == SOURCE_CHANGED


def test_a_quote_pointing_at_nothing_is_not_trusted(root: Path, store: ProvenanceStore) -> None:
    p = root / f"{PORTLAND}.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace(DOC, "or/multnomah/portland/99.txt"), encoding="utf-8")

    t = load_trusted(root, log=signed(root), store=store)

    assert front(t).status is Status.stale
    assert t.stale[0].reason == EVIDENCE_MISSING


def test_promotion_runs_before_demotion(root: Path, store: ProvenanceStore) -> None:
    # Order matters: demote-then-promote would re-trust a value whose evidence
    # had just been found missing. The report has to show both facts at once.
    store.text_path(DOC).write_text("something else entirely\n", encoding="utf-8", newline="")

    t = load_trusted(root, log=signed(root), store=store)

    assert front(t).status is Status.stale, "it was promoted, then demoted — not skipped"
    assert t.orphans == (), "the signature still matched; the evidence is what moved"


# --- the report -------------------------------------------------------


def test_the_report_counts_what_can_be_trusted(root: Path, store: ProvenanceStore) -> None:
    t = load_trusted(root, log=signed(root), store=store)

    assert t.counts == {Status.verified.value: 1}
    assert any("verified: 100.0%" in line for line in t.summary())


def test_a_clean_load_is_not_the_same_as_a_verified_one(
    root: Path, store: ProvenanceStore
) -> None:
    t = load_trusted(root, log=VerificationLog(), store=store)

    assert t.clean, "nothing is wrong; nothing is trusted either"
    assert t.counts == {Status.draft.value: 1}


def test_tampering_shows_up_in_the_summary(root: Path, store: ProvenanceStore) -> None:
    store.text_path(DOC).write_text("edited\n", encoding="utf-8", newline="")

    t = load_trusted(root, log=signed(root), store=store)

    assert not t.clean
    assert any("TAMPERED" in line for line in t.summary())


def test_tally_counts_layer_defaults_too(root: Path, store: ProvenanceStore) -> None:
    p = root / f"{PORTLAND}.yaml"
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "zones:\n", "defaults:\n  parking_min_per_unit: 1.0\nzones:\n"
        ),
        encoding="utf-8",
    )

    assert tally(load_trusted(root, log=VerificationLog(), store=store).layers) == {"draft": 2}


def test_a_broken_rule_file_is_reported_when_asked_not_to_raise(
    root: Path, store: ProvenanceStore
) -> None:
    # Tooling that means to *show* the problems, not act on the rules. The
    # pipeline itself always loads strict.
    (root / f"{PORTLAND}.yaml").write_text(
        "label: Portland\n" + CITE + "zones:\n  R5:\n    setback_diagonal_ft: 10\n",
        encoding="utf-8",
    )

    t = load_trusted(root, log=VerificationLog(), store=store, strict=False)

    assert any("unknown rule field" in p for p in t.problems)
    assert not t.clean
