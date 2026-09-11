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
    UNZONED_LABEL,
    Clause,
    Coverage,
    ObservedZone,
    Rase,
    ZoneMiss,
    build_coverage,
    clause_gaps,
    coverage_summary,
    near_label,
    sections_complete,
    unweighed,
    unweighed_zones,
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
    "  quote: \"or/multnomah/portland/33.110.txt#L2\"\n"
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


def test_a_coverage_file_nobody_generated_is_absent_not_empty(tmp_path) -> None:
    """None and "nothing is blocked" are opposite answers.

    A page that reads a missing ledger as an empty one reports every zone as
    fully encoded, which is the failure the coverage ledger exists to prevent
    wearing a different hat.
    """
    from flats.rules.ledger import read_coverage

    assert read_coverage(tmp_path / "nothing.csv") is None


def test_a_written_ledger_reads_back_as_what_was_written(tmp_path) -> None:
    from flats.rules.ledger import CoverageRow, read_coverage, write_coverage

    row = CoverageRow(
        jurisdiction="or/multnomah/portland",
        zone="RM1",
        lots=14426,
        acres=1234.5,
        status="zone_missing",
        verified_fields=0,
        total_fields=0,
        missing_required="",
        untrusted_fields="",
        blocking=14426,
    )
    path = write_coverage([row], tmp_path / "coverage.csv")

    assert read_coverage(path) == [row]


def _row(jurisdiction: str, zone: str = "R5", lots: int = 10):
    from flats.rules.ledger import CoverageRow

    return CoverageRow(
        jurisdiction=jurisdiction,
        zone=zone,
        lots=lots,
        acres=1.0,
        status="partial",
        verified_fields=0,
        total_fields=1,
        missing_required="",
        untrusted_fields="",
        blocking=lots,
    )


def test_a_narrower_corpus_is_named_before_it_can_overwrite_a_wider_one() -> None:
    """The regression this ledger actually suffered, made loud.

    It held Multnomah County alone for five weeks while the pipeline it serves
    screened two, and nothing anywhere said so. A rebuild is not automatically
    an improvement: the corpus is an argument with a default, the default is
    whatever file is on the machine, and the output is committed. So a run
    against the smaller of two parcel files replaces a wider count with a
    narrower one and every ranking downstream goes quiet about land that has
    not gone anywhere.
    """
    from flats.encode.backlog import shrinkage

    wide = [_row("or/multnomah/portland"), _row("or/clackamas/oregon-city")]
    narrow = [_row("or/multnomah/portland")]

    assert shrinkage(narrow, wide) == ["or/clackamas/oregon-city"]


def test_a_wider_corpus_is_not_shrinkage() -> None:
    """The check has to be silent in the direction we want, or it is noise
    that gets passed --shrink by habit."""
    from flats.encode.backlog import shrinkage

    wide = [_row("or/multnomah/portland"), _row("or/clackamas/oregon-city")]
    narrow = [_row("or/multnomah/portland")]

    assert shrinkage(wide, narrow) == []
    assert shrinkage(wide, wide) == []


def test_a_first_run_has_nothing_to_shrink_from() -> None:
    """No committed ledger is not a loss. `read_coverage` answers None there,
    and None must not read as an empty ledger that everything shrinks from --
    that is the same confusion this file already pins one test against."""
    from flats.encode.backlog import shrinkage

    assert shrinkage([_row("or/multnomah/portland")], None) == []
    assert shrinkage([], None) == []


def test_a_zone_that_forbids_the_building_asks_for_no_dimensions() -> None:
    """The queue's job is work that can move a verdict, and a setback in a
    zone where a fourplex is prohibited cannot: the screen returns RED at the
    use gate without reading one.

    Seven zones reported missing dimensional standards for exactly this
    reason, which is how an encoding queue quietly fills with lookups nobody
    should do. Portland's RF is the plain case -- 33.110.265.E allows
    triplexes and fourplexes "in the R20 through R2.5 zones" and Table 110-7
    prints no RF row at all.
    """
    rules = RuleSet(load_rules())
    resolved = rules.resolve(PORTLAND, "RF")

    assert resolved.values["quadplex_allowed"].value is False
    assert resolved.missing_required == ()


def test_a_prohibition_a_hearing_can_lift_still_needs_its_numbers() -> None:
    """LR-7 is the other half of the rule. A multiplex there is a conditional
    use rather than a prohibited one, so the path to the dimensional standards
    exists and they are still owed."""
    rules = RuleSet(load_rules())
    lr7 = rules.resolve("or/multnomah/_unincorporated", "LR7")

    assert lr7.values["quadplex_allowed"].value is False
    assert "conditional_use" in lr7.values["quadplex_allowed"].levers
    assert rules.resolve(
        "or/multnomah/_unincorporated", "LR7", ("conditional_use",)
    ).values["quadplex_allowed"].value is True


# --- the mirror, one level down --------------------------------------


def test_a_zone_nobody_weighed_hides_behind_a_city_that_was(tmp_path: Path) -> None:
    """The claim the zone-granularity check exists to make.

    ``unweighed`` asks "which encoded jurisdiction has no lot?" and, since the
    two-county ledger was built, correctly answers none. That empty answer is
    exactly what conceals a city whose *zones* were never counted: a layer is
    weighed the moment one zone in it is.
    """
    rules = rules_with(tmp_path, verified_zone("R5") + verified_zone("R10"))

    rows = build_coverage([ObservedZone(PORTLAND, "R5", lots=100)], rules)

    assert unweighed(rows, rules) == [], "the city is in the ledger, so it is weighed"
    blind = unweighed_zones(rows, rules)
    assert [(z.jurisdiction, z.zone) for z in blind] == [(PORTLAND, "R10")]


def test_the_map_printing_a_suffix_is_a_join_failure_not_encoding_work(
    tmp_path: Path,
) -> None:
    """Happy Valley, reduced to its bones.

    We encode the stem the code book prints. The map prints the members, and
    every one lands in the ``zone_missing`` queue asking to be encoded. It
    already is. The rows carry their evidence so the match is checkable.
    """
    rules = rules_with(tmp_path, verified_zone("MURM") + verified_zone("R5"))
    obs = [
        ObservedZone(PORTLAND, "R5", lots=100),
        ObservedZone(PORTLAND, "MURM1", lots=172),
        ObservedZone(PORTLAND, "MURM2", lots=300),
    ]

    rows = build_coverage(obs, rules)
    blind = unweighed_zones(rows, rules)

    assert len(blind) == 1
    hit = blind[0]
    assert hit.zone == "MURM"
    assert hit.cause is ZoneMiss.near_miss
    # Biggest first: the evidence is ordered so a reader meets the real one.
    assert hit.candidates == (("MURM2", 300), ("MURM1", 172))
    assert hit.lots == 472
    # And those lots are, wrongly, ranked as encoding work in the same ledger.
    assert {r.zone for r in rows if r.status == Coverage.zone_missing.value} == {
        "MURM1",
        "MURM2",
    }


def test_one_district_spelled_three_ways_is_one_finding(tmp_path: Path) -> None:
    """A leading space and a lowercase letter are not two more districts.

    All three spellings are live in the committed ledger for Happy Valley's
    MURM2 and all three sit in the queue separately.
    """
    rules = rules_with(tmp_path, verified_zone("MURM") + verified_zone("R5"))
    obs = [
        ObservedZone(PORTLAND, "R5", lots=100),
        ObservedZone(PORTLAND, "MURM2", lots=300),
        ObservedZone(PORTLAND, " MURM2", lots=5),
        ObservedZone(PORTLAND, "MURm2", lots=1),
    ]

    blind = unweighed_zones(build_coverage(obs, rules), rules)

    assert len(blind) == 1
    assert blind[0].lots == 306
    assert [label for label, _ in blind[0].candidates] == ["MURM2", " MURM2", "MURm2"]


def test_a_city_with_no_zoning_join_is_not_encoding_debt(tmp_path: Path) -> None:
    """Every lot arriving under the sentinel means the join never ran.

    Reported, because absence is not a zero -- but named as its own cause, so
    it cannot be mistaken for zones anybody has to go and encode.
    """
    rules = rules_with(tmp_path, verified_zone("R5") + verified_zone("R10"))

    rows = build_coverage([ObservedZone(PORTLAND, UNZONED_LABEL, lots=14_256)], rules)
    blind = unweighed_zones(rows, rules)

    assert {z.zone for z in blind} == {"R5", "R10"}
    assert {z.cause for z in blind} == {ZoneMiss.unzoned}
    assert all(z.lots == 0 for z in blind), "the sentinel is not evidence of a match"


def test_a_district_the_map_does_not_carry_is_its_own_answer(tmp_path: Path) -> None:
    """Tualatin RML: mapped districts exist, none is this one, none is close."""
    rules = rules_with(tmp_path, verified_zone("RL") + verified_zone("RML"))
    obs = [
        ObservedZone(PORTLAND, "RL", lots=956),
        ObservedZone(PORTLAND, "RMH", lots=5),
    ]

    blind = unweighed_zones(build_coverage(obs, rules), rules)

    assert [z.zone for z in blind] == ["RML"]
    assert blind[0].cause is ZoneMiss.unmapped
    assert blind[0].candidates == (), "an unmapped zone must not invent evidence"


def test_the_blank_join_sentinel_is_never_matched_as_a_label(tmp_path: Path) -> None:
    """It is not a zone code and nothing may read it as one."""
    assert not near_label("R5", UNZONED_LABEL)
    assert not near_label(UNZONED_LABEL, "R5")


@pytest.mark.parametrize(
    "encoded,observed",
    [
        ("MURM", "MURM1"),  # the map prints the family members
        ("MURM2", " MURM2"),  # leading whitespace
        ("MURM2", "MURm2"),  # case
        ("R-10", "R10"),  # punctuation, both directions
        ("R10", "R-10"),
    ],
)
def test_a_label_that_could_be_the_same_district_is_flagged(
    encoded: str, observed: str
) -> None:
    assert near_label(encoded, observed)


@pytest.mark.parametrize(
    "encoded,observed",
    [
        ("RML", "RMH"),  # Tualatin: two real districts, one character apart
        ("R5", "R20"),
        ("MURM", "MURS"),
        ("R5", "R5000"),  # a tail this long is a different standard, not a typo
    ],
)
def test_a_substitution_is_not_a_join_failure(encoded: str, observed: str) -> None:
    """The refusal that makes the flag worth reading.

    An edit-distance rule flags RML/RMH and sends a reader to alias two
    districts the city defines separately. A false flag here does not cost a
    minute; it costs a wrong rule.
    """
    assert not near_label(encoded, observed)


def test_every_unweighed_zone_carries_exactly_one_cause() -> None:
    """Over the committed ledger, not a fixture. The causes must partition, and
    only a near miss may carry evidence -- otherwise the report's three
    sections would double-count or argue with each other."""
    from flats.rules.ledger import read_coverage

    rules = RuleSet(load_rules())
    rows = read_coverage()
    assert rows is not None, "no committed ledger to check against"

    blind = unweighed_zones(rows, rules)

    assert blind, "the check is only worth keeping while it is still asked"
    for z in blind:
        if z.cause is ZoneMiss.near_miss:
            assert z.candidates and z.lots > 0
        else:
            assert z.candidates == () and z.lots == 0
