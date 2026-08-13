"""Coverage and clause ledgers.

The coverage ledger is the control for silent omission — the failure that left
40,500 Portland multi-dwelling lots invisible. Its contract: an unencoded zone
is a ranked top row, never an absence.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from flats.rules.ledger import (
    Clause,
    Coverage,
    ObservedZone,
    Rase,
    build_coverage,
    clause_gaps,
    coverage_summary,
    sections_complete,
    write_coverage,
)
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.tests.signing import sign_encoded

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
#: Marks a value as ready for review. The helper signs exactly these — a
#: file cannot declare itself verified, which is what the log is for.
REVIEWED = "status: encoded"
CITE = (
    "cite_default:\n"
    '  cite: "PCC 33.110.220, Table 110-4"\n'
    '  url: "https://www.portland.gov/code/33/100s/110"\n'
    "  retrieved: 2026-08-12\n"
)
REQUIRED = [
    ("quadplex_allowed", "true"),
    ("setback_front_ft", 10),
    ("setback_side_ft", 5),
    ("setback_rear_ft", 5),
    ("min_lot_sqft", 3000),
    ("max_height_ft", 30),
    ("parking_min_per_unit", 0),
]


def rules_with(root: Path, zones_yaml: str) -> RuleSet:
    p = root / f"{PORTLAND}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("label: Portland\n" + CITE + "zones:\n" + zones_yaml, encoding="utf-8")
    # Stands in for a reviewer working the queue: everything marked `encoded`
    # gets signed, everything left shorthand stays draft.
    return RuleSet(sign_encoded(load_rules(root)))


def verified_zone(name: str) -> str:
    body = "".join(f"    {f}: {{value: {v}, {REVIEWED}}}\n" for f, v in REQUIRED)
    return f"  {name}:\n{body}"


def draft_zone(name: str) -> str:
    return f"  {name}:\n" + "".join(f"    {f}: {v}\n" for f, v in REQUIRED)


# --- coverage ---------------------------------------------------------


def test_unencoded_zone_is_a_ranked_row_not_an_absence(tmp_path: Path) -> None:
    rules = rules_with(tmp_path, verified_zone("R5"))
    obs = [
        ObservedZone(PORTLAND, "R5", lots=73_690),
        ObservedZone(PORTLAND, "RM1", lots=14_426),
    ]

    rows = build_coverage(obs, rules)

    # RM1 outranks the fully-encoded R5 despite having a fifth the lots, because
    # ranking is by lots *blocked*, not lots present.
    assert rows[0].zone == "RM1"
    assert rows[0].status == Coverage.zone_missing.value
    assert rows[0].blocking == 14_426
    assert rows[1].blocking == 0, "a verified zone blocks nothing"


def test_unencoded_jurisdiction_is_reported(tmp_path: Path) -> None:
    rules = rules_with(tmp_path, verified_zone("R5"))

    rows = build_coverage([ObservedZone("or/multnomah/gresham", "LDR-5", 12_854)], rules)

    assert rows[0].status == Coverage.jurisdiction_missing.value
    assert rows[0].blocking == 12_854


def test_draft_values_make_a_zone_partial_and_blocking(tmp_path: Path) -> None:
    rules = rules_with(tmp_path, draft_zone("R5"))

    row = build_coverage([ObservedZone(PORTLAND, "R5", 73_690)], rules)[0]

    assert row.status == Coverage.partial.value
    assert row.blocking == 73_690, "encoded but unverified still cannot produce GREEN"
    assert row.verified_fields == 0
    assert row.total_fields >= len(REQUIRED)


def test_partial_zone_names_its_untrusted_fields(tmp_path: Path) -> None:
    zone = verified_zone("R5").replace(
        "    setback_rear_ft: {value: 5, " + REVIEWED + "}\n", "    setback_rear_ft: 5\n"
    )
    rules = rules_with(tmp_path, zone)

    row = build_coverage([ObservedZone(PORTLAND, "R5", 100)], rules)[0]

    assert row.status == Coverage.partial.value
    assert row.untrusted_fields == "setback_rear_ft"


def test_missing_required_field_is_named(tmp_path: Path) -> None:
    zone = verified_zone("R5")
    zone = zone.replace("    max_height_ft: {value: 30, " + REVIEWED + "}\n", "")
    rules = rules_with(tmp_path, zone)

    row = build_coverage([ObservedZone(PORTLAND, "R5", 100)], rules)[0]

    assert "max_height_ft" in row.missing_required
    assert row.blocking == 100


def test_verified_zone_clears(tmp_path: Path) -> None:
    rules = rules_with(tmp_path, verified_zone("R5"))

    row = build_coverage([ObservedZone(PORTLAND, "R5", 73_690)], rules)[0]

    assert row.status == Coverage.verified.value
    assert row.blocking == 0
    assert row.missing_required == ""


def test_ineligible_jurisdictions_are_kept_by_default(tmp_path: Path) -> None:
    p = tmp_path / f"{PORTLAND}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("label: Portland\neligible: false\n" + CITE + "zones:\n" + draft_zone("R5"), encoding="utf-8")
    rules = RuleSet(load_rules(tmp_path))
    obs = [ObservedZone(PORTLAND, "R5", 100)]

    # A toggle is report-time policy, so the backlog is still worth seeing —
    # re-enabling is seconds, re-encoding is not.
    assert len(build_coverage(obs, rules)) == 1
    assert build_coverage(obs, rules, eligible_only=True) == []


def test_summary_counts(tmp_path: Path) -> None:
    rules = rules_with(tmp_path, verified_zone("R5"))
    obs = [ObservedZone(PORTLAND, "R5", 100), ObservedZone(PORTLAND, "RM1", 40)]

    s = coverage_summary(build_coverage(obs, rules))

    assert s["lots_total"] == 140
    assert s["lots_blocked"] == 40
    assert s["zones_verified"] == 1
    assert s["zones_zone_missing"] == 1


def test_csv_round_trips(tmp_path: Path) -> None:
    rules = rules_with(tmp_path, verified_zone("R5"))
    rows = build_coverage([ObservedZone(PORTLAND, "RM1", 14_426)], rules)

    out = write_coverage(rows, tmp_path / "out" / "coverage.csv")
    read = list(csv.DictReader(out.open(encoding="utf-8")))

    assert read[0]["zone"] == "RM1"
    assert read[0]["blocking"] == "14426"


# --- clause ledger ----------------------------------------------------


def clause(cid: str, **kw) -> Clause:
    base = dict(
        jurisdiction="portland", section="PCC 33.110.220", quote="x.txt#L1-L2", text="..."
    )
    return Clause(id=cid, **{**base, **kw})


def test_untagged_clause_is_a_gap() -> None:
    gaps = clause_gaps([clause("c1", tag=None)])

    assert [g.problem for g in gaps] == ["untagged"]


def test_unresolved_requirement_is_a_gap() -> None:
    gaps = clause_gaps([clause("c1", tag=Rase.requirement, resolved=False)])

    assert [g.problem for g in gaps] == ["unresolved_requirement"]


def test_unresolved_exception_is_a_gap() -> None:
    # The case the clause ledger exists for: a rule we know about but ignore.
    gaps = clause_gaps([clause("c1", tag=Rase.exception, resolved=False)])

    assert [g.problem for g in gaps] == ["unresolved_exception"]


def test_non_normative_clause_needs_no_resolution() -> None:
    assert clause_gaps([clause("c1", tag=Rase.non_normative)]) == []


@pytest.mark.parametrize("tag", [Rase.applicability, Rase.selection])
def test_scoping_tags_need_no_resolution(tag: Rase) -> None:
    assert clause_gaps([clause("c1", tag=tag)]) == []


def test_section_is_complete_only_when_every_clause_is() -> None:
    done = clause("a", tag=Rase.requirement, resolved=True)
    loose = clause("b", tag=None)

    assert sections_complete([done]) == {("portland", "PCC 33.110.220"): True}
    assert sections_complete([done, loose]) == {("portland", "PCC 33.110.220"): False}
