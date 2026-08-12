"""Rule loading, validation, and hierarchy resolution.

These tests are the contract for the encoding standard: no unsourced numbers,
no silent defaults, no trust without a reviewer, and state preemption that a
city cannot override.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Status
from flats.rules.resolver import RuleSet, Verdict

pytestmark = pytest.mark.unit

PORTLAND = "or/41051-multnomah/4159000-portland"
GRESHAM = "or/41051-multnomah/4131250-gresham"

CITE = (
    "cite_default:\n"
    '  cite: "PCC 33.110.220, Table 110-4"\n'
    '  url: "https://www.portland.gov/code/33/100s/110"\n'
    "  retrieved: 2026-08-12\n"
)
REVIEWED = "status: verified, reviewer: sjk, reviewed: 2026-08-14"


def write(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def portland(root: Path, zones: str, extra: str = "", cite: str = CITE) -> None:
    """Write a Portland layer. ``zones`` is YAML indented two spaces at column 0."""
    write(root, f"{PORTLAND}.yaml", "label: Portland\n" + extra + cite + "zones:\n" + zones)


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return tmp_path / "jurisdictions"


# --- authoring forms -------------------------------------------------


def test_shorthand_inherits_cite_default(root: Path) -> None:
    portland(root, "  R5:\n    quadplex_allowed: true\n    setback_front_ft: 10\n")
    zone = load_rules(root)[PORTLAND].zones["R5"]

    assert zone.values["setback_front_ft"].value == 10
    assert zone.values["setback_front_ft"].prov.cite.startswith("PCC 33.110.220")
    # Shorthand is convenience, not trust — it must not arrive pre-verified.
    assert zone.values["setback_front_ft"].status is Status.draft
    assert not zone.trusted


def test_full_form_overrides_cite_default(root: Path) -> None:
    portland(
        root,
        "  R5:\n"
        "    quadplex_allowed: true\n"
        "    setback_front_ft:\n"
        "      value: 10\n"
        '      cite: "PCC 33.110.240"\n'
        '      url: "https://example.gov/240"\n'
        "      retrieved: 2026-08-01\n"
        "      status: verified\n"
        "      reviewer: sjk\n"
        "      reviewed: 2026-08-14\n",
    )
    v = load_rules(root)[PORTLAND].zones["R5"].values["setback_front_ft"]

    assert v.prov.cite == "PCC 33.110.240"
    assert v.trusted


# --- the "no unsourced numbers" contract -----------------------------


def test_value_without_provenance_is_rejected(root: Path) -> None:
    portland(root, "  R5:\n    setback_front_ft: 10\n", cite="")
    with pytest.raises(RuleLoadError, match="missing provenance"):
        load_rules(root)


def test_unknown_field_is_rejected(root: Path) -> None:
    portland(root, "  R5:\n    setback_diagonal_ft: 10\n")
    with pytest.raises(RuleLoadError, match="unknown rule field"):
        load_rules(root)


def test_verified_without_reviewer_is_rejected(root: Path) -> None:
    portland(root, "  R5:\n    setback_front_ft: {value: 10, status: verified}\n")
    with pytest.raises(RuleLoadError, match="requires both 'reviewer' and 'reviewed'"):
        load_rules(root)


@pytest.mark.parametrize(
    "body,fragment",
    [
        ("quadplex_allowed: 1", "expected a boolean"),
        ("setback_front_ft: -5", "non-negative"),
        ("max_coverage_pct: 140", "exceeds 100"),
        ("max_units: 2.5", "non-negative integer"),
        ("orientation_constraint: sideways", "not one of"),
        ("coverage_curve: [[5000, 2250, 15], [3000, 1500, 37.5]]", "must exceed the previous"),
        ("setback_front_ft: {value: 10, retrieved: 2026-08-12, colour: blue}", "unknown key"),
    ],
)
def test_kind_validation(root: Path, body: str, fragment: str) -> None:
    portland(root, f"  R5:\n    {body}\n")
    with pytest.raises(RuleLoadError, match=fragment):
        load_rules(root)


def test_every_problem_reported_in_one_pass(root: Path) -> None:
    portland(
        root,
        "  R5:\n    setback_front_ft: -5\n    max_coverage_pct: 140\n    bogus_field: 3\n",
    )
    with pytest.raises(RuleLoadError) as exc:
        load_rules(root)
    # A 96-row port should not need 96 runs to find 96 problems.
    assert len(exc.value.problems) == 3


# --- hierarchy resolution --------------------------------------------


def hierarchy(root: Path) -> RuleSet:
    write(
        root,
        "or/_state.yaml",
        "label: Oregon\n"
        "kind: state\n"
        "cite_default:\n"
        '  cite: "OAR 660-046-0220"\n'
        '  url: "https://oregon.public.law/rules/oar_660-046-0220"\n'
        "  retrieved: 2026-08-12\n"
        "defaults:\n"
        "  parking_min_per_unit: {value: 1.0, preempts: true}\n"
        "  max_height_ft: 35\n",
    )
    portland(
        root,
        "  R5:\n"
        "    quadplex_allowed: true\n"
        "    setback_front_ft: 10\n"
        "    setback_side_ft: 5\n"
        "    setback_rear_ft: 5\n"
        "    min_lot_sqft: 3000\n"
        "    max_height_ft: 30\n"
        "    parking_min_per_unit: 2.0\n",
    )
    return RuleSet(load_rules(root))


def test_city_overrides_state(root: Path) -> None:
    height = hierarchy(root).resolve(PORTLAND, "R5").values["max_height_ft"]

    assert height.value == 30
    assert height.layer == PORTLAND
    assert height.origin == "zone"


def test_state_preemption_beats_the_city(root: Path) -> None:
    parking = hierarchy(root).resolve(PORTLAND, "R5").values["parking_min_per_unit"]

    assert parking.value == 1.0, "OAR 660-046 caps parking; Portland's 2.0 must lose"
    assert parking.layer == "or"
    assert parking.preempted
    assert parking.shadowed == 2.0, "the displaced local value is kept so the UI can explain it"


def test_resolution_records_the_chain(root: Path) -> None:
    assert hierarchy(root).resolve(PORTLAND, "R5").chain == (PORTLAND, "or")


# --- verdicts: absence is explicit, never inferred --------------------


def test_missing_zone_is_not_encoded_not_prohibited(root: Path) -> None:
    r = hierarchy(root).resolve(PORTLAND, "RM1")

    assert r.verdict is Verdict.zone_not_encoded
    assert r.reason == "ZONE_NOT_ENCODED"
    assert not r.trusted
    # The failure that cost this project 40,500 lots: RM1 must surface as
    # unencoded, never as "quadplex not allowed".
    assert r.get("quadplex_allowed") is None


def test_missing_jurisdiction_is_reported(root: Path) -> None:
    r = hierarchy(root).resolve(GRESHAM, "LDR-5")

    assert r.verdict is Verdict.jurisdiction_not_encoded
    assert r.reason == "JURISDICTION_NOT_ENCODED"


def test_draft_values_make_the_zone_unverified(root: Path) -> None:
    r = hierarchy(root).resolve(PORTLAND, "R5")

    assert r.verdict is Verdict.unverified
    assert r.reason == "RULE_UNVERIFIED"
    assert "setback_front_ft" in r.untrusted


def test_missing_required_field_blocks_trust(root: Path) -> None:
    portland(root, "  R5:\n    quadplex_allowed: {value: true, " + REVIEWED + "}\n")
    r = RuleSet(load_rules(root)).resolve(PORTLAND, "R5")

    assert r.verdict is Verdict.unverified
    assert "setback_front_ft" in r.missing_required
    assert "min_lot_sqft" in r.missing_required


def test_fully_verified_zone_is_trusted(root: Path) -> None:
    zones = "  R5:\n" + "".join(
        f"    {name}: {{value: {val}, {REVIEWED}}}\n"
        for name, val in [
            ("quadplex_allowed", "true"),
            ("setback_front_ft", 10),
            ("setback_side_ft", 5),
            ("setback_rear_ft", 5),
            ("min_lot_sqft", 3000),
            ("max_height_ft", 30),
            ("parking_min_per_unit", 0),
        ]
    )
    portland(root, zones)
    r = RuleSet(load_rules(root)).resolve(PORTLAND, "R5")

    assert r.verdict is Verdict.trusted, f"untrusted={r.untrusted} missing={r.missing_required}"


# --- jurisdiction toggle ---------------------------------------------


def test_jurisdiction_toggle_is_policy_not_a_drop(root: Path) -> None:
    portland(root, "  R5:\n    setback_front_ft: 10\n", extra="eligible: false\n")
    rs = RuleSet(load_rules(root))

    assert not rs.eligible(PORTLAND)
    # Toggling a jurisdiction off must not erase its rules — turning it back on
    # is a report-time re-run, not a re-encode.
    assert rs.resolve(PORTLAND, "R5").get("setback_front_ft") == 10
