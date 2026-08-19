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
from flats.tests.signing import sign_encoded

pytestmark = pytest.mark.unit

PORTLAND = "or/41051-multnomah/4159000-portland"
GRESHAM = "or/41051-multnomah/4131250-gresham"

CITE = (
    "cite_default:\n"
    '  cite: "PCC 33.110.220, Table 110-4"\n'
    '  url: "https://www.portland.gov/code/33/100s/110"\n'
    "  retrieved: 2026-08-12\n"
    "  quote: \"or/multnomah/portland/33.110.txt#L2\"\n"
)
#: Ready for review. The signing helper promotes exactly these.
REVIEWED = "status: encoded"


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
        "      status: encoded\n",
    )
    v = load_rules(root)[PORTLAND].zones["R5"].values["setback_front_ft"]

    assert v.prov.cite == "PCC 33.110.240"
    assert v.prov.url == "https://example.gov/240"
    assert not v.trusted, "written down is not read — only a signature promotes"


# --- the "no unsourced numbers" contract -----------------------------


def test_value_without_provenance_is_rejected(root: Path) -> None:
    portland(root, "  R5:\n    setback_front_ft: 10\n", cite="")
    with pytest.raises(RuleLoadError, match="missing provenance"):
        load_rules(root)


def test_unknown_field_is_rejected(root: Path) -> None:
    portland(root, "  R5:\n    setback_diagonal_ft: 10\n")
    with pytest.raises(RuleLoadError, match="unknown rule field"):
        load_rules(root)


def test_a_file_may_not_declare_itself_verified(root: Path) -> None:
    # The forgery this design exists to stop: an edit to a YAML file that
    # certifies a number nobody read. Trust is a signature over the value, its
    # citation and its quote — never the word typed beside it.
    portland(root, "  R5:\n    setback_front_ft: {value: 10, status: verified}\n")
    with pytest.raises(RuleLoadError, match="may not declare status"):
        load_rules(root)


def test_stale_is_derived_and_may_not_be_typed_either(root: Path) -> None:
    portland(root, "  R5:\n    setback_front_ft: {value: 10, status: stale}\n")
    with pytest.raises(RuleLoadError, match="stale to be derived"):
        load_rules(root)


def test_a_verified_value_still_needs_a_reviewer_on_it(root: Path) -> None:
    # The model invariant behind the signature: reaching `verified` without a
    # named reviewer and a date is not a state this system has.
    from pydantic import ValidationError

    from flats.rules.model import Provenance, Value

    with pytest.raises(ValidationError, match="requires both 'reviewer' and 'reviewed'"):
        Value(
            name="setback_front_ft",
            value=10,
            prov=Provenance(cite="PCC 33.110", url="https://example.gov/1", retrieved="2026-08-01"),
            status=Status.verified,
        )


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
        '  quote: "or/oar.660-046-0220.txt#L79"\n'
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
    # One signed field does not carry a zone. An absent standard is unknown,
    # and unknown routes to REVIEW rather than being assumed away.
    portland(root, "  R5:\n    quadplex_allowed: {value: true, " + REVIEWED + "}\n")
    r = RuleSet(sign_encoded(load_rules(root))).resolve(PORTLAND, "R5")

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
    r = RuleSet(sign_encoded(load_rules(root))).resolve(PORTLAND, "R5")

    assert r.verdict is Verdict.trusted, f"untrusted={r.untrusted} missing={r.missing_required}"


# --- jurisdiction toggle ---------------------------------------------


def test_jurisdiction_toggle_is_policy_not_a_drop(root: Path) -> None:
    portland(root, "  R5:\n    setback_front_ft: 10\n", extra="eligible: false\n")
    rs = RuleSet(load_rules(root))

    assert not rs.eligible(PORTLAND)
    # Toggling a jurisdiction off must not erase its rules — turning it back on
    # is a report-time re-run, not a re-encode.
    assert rs.resolve(PORTLAND, "R5").get("setback_front_ft") == 10


# --- preemption has a direction ---------------------------------------


def capped(root: Path, city_parking: str, city_height: str = "30") -> RuleSet:
    """The same hierarchy, with the state rule declared as a ceiling.

    OAR 660-046-0220 bars a city from requiring MORE parking than this. It does
    not oblige one to require any. `preempts: cap` is that distinction, and the
    three tests below are the three cases it has to get right.
    """
    write(
        root,
        "or/_state.yaml",
        "label: Oregon\n"
        "kind: state\n"
        "cite_default:\n"
        '  cite: "OAR 660-046-0220"\n'
        '  url: "https://oregon.public.law/rules/oar_660-046-0220"\n'
        '  quote: "or/oar.660-046-0220.txt#L79"\n'
        "  retrieved: 2026-08-12\n"
        "defaults:\n"
        "  parking_min_per_unit: {value: 1.0, preempts: cap}\n"
        "  max_coverage_pct: {value: 50, preempts: cap}\n",
    )
    portland(
        root,
        "  R5:\n"
        "    quadplex_allowed: true\n"
        "    setback_front_ft: 10\n"
        "    setback_side_ft: 5\n"
        "    setback_rear_ft: 5\n"
        "    min_lot_sqft: 3000\n"
        f"    max_height_ft: {city_height}\n"
        f"    parking_min_per_unit: {city_parking}\n",
    )
    return RuleSet(load_rules(root))


def test_a_cap_clips_a_city_that_asks_for_more(root: Path) -> None:
    """The case a lock also got right, and the reason preemption exists."""
    parking = capped(root, "2.0").resolve(PORTLAND, "R5").values["parking_min_per_unit"]

    assert parking.value == 1.0
    assert parking.preempted
    assert parking.shadowed == 2.0


def test_a_cap_lets_a_city_that_asks_for_less_through(root: Path) -> None:
    """The case a lock got wrong. Portland repealed its parking minimum; a cap
    read as a substitute hands every lot in the city four stalls nobody
    requires, which on a narrow lot is the difference between fitting and
    not."""
    parking = capped(root, "0").resolve(PORTLAND, "R5").values["parking_min_per_unit"]

    assert parking.value == 0
    assert parking.layer == PORTLAND
    assert not parking.preempted, "nothing was displaced — the city is inside the ceiling"


def test_which_way_looser_runs_is_read_off_the_field(root: Path) -> None:
    """A minimum gets looser as it falls; a maximum gets looser as it rises.
    Same `cap`, opposite direction, and the direction is a property of the
    standard rather than of the preemption — so it comes from the field
    registry and not from anything written in a rule file."""
    capped(root, "0")  # writes the state layer; the zone is replaced below
    portland(
        root,
        "  R5:\n"
        "    quadplex_allowed: true\n"
        "    setback_front_ft: 10\n"
        "    setback_side_ft: 5\n"
        "    setback_rear_ft: 5\n"
        "    min_lot_sqft: 3000\n"
        "    max_coverage_pct: 70\n",
    )
    rules = RuleSet(load_rules(root))
    coverage = rules.resolve(PORTLAND, "R5").values["max_coverage_pct"]

    assert coverage.value == 70, "70% is looser than a 50% floor-on-a-ceiling"
    assert not coverage.preempted


def test_a_cap_on_a_boolean_still_wins_outright(root: Path) -> None:
    """A boolean has no ordering, so "looser" is undefined and there is nothing
    to clip. The conservative reading is that the ancestor wins, and the
    alternative — inventing an order for true and false — is how a state
    mandate silently becomes optional."""
    write(
        root,
        "or/_state.yaml",
        "label: Oregon\n"
        "kind: state\n"
        "cite_default:\n"
        '  cite: "ORS 92.031"\n'
        '  url: "https://www.oregonlegislature.gov/bills_laws/ors/ors092.html"\n'
        '  quote: "or/ors.92.031.txt#L7"\n'
        "  retrieved: 2026-08-14\n"
        "defaults:\n"
        "  land_division_parent_standards: {value: true, preempts: cap}\n",
    )
    portland(
        root,
        "  R5:\n"
        "    quadplex_allowed: true\n"
        "    setback_front_ft: 10\n"
        "    setback_side_ft: 5\n"
        "    setback_rear_ft: 5\n"
        "    min_lot_sqft: 3000\n"
        "    land_division_parent_standards: false\n",
    )
    res = RuleSet(load_rules(root)).resolve(PORTLAND, "R5")

    split = res.values["land_division_parent_standards"]
    assert split.value is True
    assert split.preempted


def test_an_unreadable_preemption_is_refused_not_ignored(root: Path) -> None:
    """A typo that quietly resolved to "no preemption" would drop a statute
    without a word — the failure mode this whole rule set is built against."""
    write(
        root,
        "or/_state.yaml",
        "label: Oregon\n"
        "kind: state\n"
        "cite_default:\n"
        '  cite: "OAR 660-046-0220"\n'
        '  url: "https://oregon.public.law/rules/oar_660-046-0220"\n'
        '  quote: "or/oar.660-046-0220.txt#L79"\n'
        "  retrieved: 2026-08-12\n"
        "defaults:\n"
        "  parking_min_per_unit: {value: 1.0, preempts: sometimes}\n",
    )
    portland(root, "  R5:\n    quadplex_allowed: true\n")

    with pytest.raises(RuleLoadError, match="preempts"):
        load_rules(root)


def test_a_third_layer_is_measured_against_the_state_not_the_city(root: Path) -> None:
    """Once a cap lets a looser city number through, the resolved value is the
    city's — but an overlay after it is still bounded by the STATE's ceiling,
    not by whatever the city happened to choose. Comparing against the last
    winner would turn a city's permissiveness into a cap it never declared and
    silently void an overlay that was inside the state rule all along."""
    write(
        root,
        "or/_state.yaml",
        "label: Oregon\n"
        "kind: state\n"
        "cite_default:\n"
        '  cite: "OAR 660-046-0220"\n'
        '  url: "https://oregon.public.law/rules/oar_660-046-0220"\n'
        '  quote: "or/oar.660-046-0220.txt#L79"\n'
        "  retrieved: 2026-08-12\n"
        "defaults:\n"
        "  parking_min_per_unit: {value: 1.0, preempts: cap}\n",
    )
    county = PORTLAND.rsplit("/", 1)[0]
    write(
        root,
        f"{county}/_county.yaml",
        "label: Multnomah\nkind: county\n"
        "cite_default:\n"
        '  cite: "MCC"\n'
        '  url: "https://example.invalid/mcc"\n'
        '  quote: "or/multnomah/mcc.txt#L1"\n'
        "  retrieved: 2026-08-12\n"
        "defaults:\n"
        "  parking_min_per_unit: 0\n",
    )
    portland(
        root,
        "  R5:\n"
        "    quadplex_allowed: true\n"
        "    setback_front_ft: 10\n"
        "    setback_side_ft: 5\n"
        "    setback_rear_ft: 5\n"
        "    min_lot_sqft: 3000\n"
        "    parking_min_per_unit: 0.5\n",
    )

    res = RuleSet(load_rules(root)).resolve(PORTLAND, "R5")

    # Without this the test is vacuous: if the county layer never loaded, the
    # city would be compared against the state's 1.0 either way and pass.
    assert res.chain == (PORTLAND, county, "or")

    parking = res.values["parking_min_per_unit"]
    assert parking.value == 0.5, "0.5 is inside the state's 1.0 ceiling"
    assert parking.layer == PORTLAND
    assert not parking.preempted



# --- an ancestor removing a standard outright --------------------------


def unexempted(root: Path, city_density: str) -> RuleSet:
    """The state removing a standard, and a city printing one anyway.

    OAR 660-046-0220(2)(b): "If a Large City applies density maximums in a
    zone, it may not apply those maximums to the development of Quadplex and
    Triplexes." That is not a ceiling on a number — there is no number. It says
    the standard is not there for this building, and a city may not put it
    back.
    """
    write(
        root,
        "or/_state.yaml",
        "label: Oregon\n"
        "kind: state\n"
        "cite_default:\n"
        '  cite: "OAR 660-046-0220(2)(b)"\n'
        '  url: "https://oregon.public.law/rules/oar_660-046-0220"\n'
        '  quote: "or/oar.660-046-0220.txt#L55"\n'
        "  retrieved: 2026-08-19\n"
        "defaults:\n"
        "  max_density_du_per_acre: {exempt: true, preempts: always}\n",
    )
    portland(
        root,
        "  R5:\n"
        "    quadplex_allowed: true\n"
        "    setback_front_ft: 10\n"
        "    setback_side_ft: 5\n"
        "    setback_rear_ft: 5\n"
        "    min_lot_sqft: 3000\n"
        f"    max_density_du_per_acre: {city_density}\n",
    )
    return RuleSet(load_rules(root))


def test_a_city_may_not_reinstate_a_standard_the_state_removed(root: Path) -> None:
    """Before the lock the state wrote the exemption and the first city to
    print a density row overwrote it — which is precisely the standard the
    rule exists to remove."""
    got = unexempted(root, "8.7").resolve(PORTLAND, "R5")

    assert "max_density_du_per_acre" in got.exempted
    assert "max_density_du_per_acre" not in got.values


def test_an_exemption_states_no_number_so_it_caps_nothing(root: Path) -> None:
    """`cap` clips a local value back to a ceiling. There is no ceiling here,
    and asking the resolver to clip a number back to an absence is a file that
    means two things at once."""
    write(
        root,
        "or/_state.yaml",
        "label: Oregon\n"
        "kind: state\n"
        "cite_default:\n"
        '  cite: "OAR 660-046-0220(2)(b)"\n'
        '  url: "https://oregon.public.law/rules/oar_660-046-0220"\n'
        '  quote: "or/oar.660-046-0220.txt#L55"\n'
        "  retrieved: 2026-08-19\n"
        "defaults:\n"
        "  max_density_du_per_acre: {exempt: true, preempts: cap}\n",
    )
    portland(root, "  R5:\n    quadplex_allowed: true\n")

    with pytest.raises(RuleLoadError, match="caps nothing"):
        load_rules(root, strict=True)


# --- a layer standing down, which is not the same as an exemption ------


def test_a_layer_says_nothing_under_a_condition_it_did_not_address(
    root: Path,
) -> None:
    """OAR 660-046-0220 removes a density maximum for quadplexes at (2)(b) and
    leaves a Large City a townhouse ceiling at (3)(c). Split onto four lots the
    pod is townhouses, the state's exemption was written about a different
    building, and the city's own row is the answer. Silence, not relief: an
    exemption here would cancel a standard the rule never spoke to.
    """
    write(
        root,
        "or/_state.yaml",
        "label: Oregon\n"
        "kind: state\n"
        "cite_default:\n"
        '  cite: "OAR 660-046-0220(2)(b)"\n'
        '  url: "https://oregon.public.law/rules/oar_660-046-0220"\n'
        '  quote: "or/oar.660-046-0220.txt#L55"\n'
        "  retrieved: 2026-08-19\n"
        "defaults:\n"
        "  max_density_du_per_acre:\n"
        "    exempt: true\n"
        "    preempts: always\n"
        "    unless: [unit_lots]\n",
    )
    portland(
        root,
        "  R5:\n"
        "    quadplex_allowed: true\n"
        "    max_density_du_per_acre: 8.7\n",
    )
    rules = RuleSet(load_rules(root))

    whole = rules.resolve(PORTLAND, "R5")
    assert "max_density_du_per_acre" in whole.exempted

    split = rules.resolve(PORTLAND, "R5", ("unit_lots",))
    assert "max_density_du_per_acre" not in split.exempted
    assert split.get("max_density_du_per_acre") == 8.7


def test_standing_down_leaves_nothing_behind_when_no_city_answers(
    root: Path,
) -> None:
    """The point of silence is that a lower layer may still speak. When none
    does, the field is simply absent — not exempt, which would read as "the
    state removed it", and not a number nobody wrote.
    """
    write(
        root,
        "or/_state.yaml",
        "label: Oregon\n"
        "kind: state\n"
        "cite_default:\n"
        '  cite: "OAR 660-046-0220(2)(b)"\n'
        '  url: "https://oregon.public.law/rules/oar_660-046-0220"\n'
        '  quote: "or/oar.660-046-0220.txt#L55"\n'
        "  retrieved: 2026-08-19\n"
        "defaults:\n"
        "  max_density_du_per_acre:\n"
        "    exempt: true\n"
        "    preempts: always\n"
        "    unless: [unit_lots]\n",
    )
    portland(root, "  R5:\n    quadplex_allowed: true\n")
    rules = RuleSet(load_rules(root))

    split = rules.resolve(PORTLAND, "R5", ("unit_lots",))
    assert "max_density_du_per_acre" not in split.exempted
    assert split.get("max_density_du_per_acre") is None


def test_a_value_may_not_both_stand_down_and_answer(root: Path) -> None:
    """A value that states a variant for `unit_lots` and also stands down
    under it means two things at once, and which one wins is an accident of
    the order the resolver reads them in."""
    write(
        root,
        "or/_state.yaml",
        "label: Oregon\n"
        "kind: state\n"
        "cite_default:\n"
        '  cite: "OAR 660-046-0220(2)(b)"\n'
        '  url: "https://oregon.public.law/rules/oar_660-046-0220"\n'
        '  quote: "or/oar.660-046-0220.txt#L55"\n'
        "  retrieved: 2026-08-19\n"
        "defaults:\n"
        "  max_density_du_per_acre:\n"
        "    value: 25\n"
        "    unless: [unit_lots]\n"
        "    variants:\n"
        "      - value: 20\n"
        "        when: [unit_lots]\n",
    )
    portland(root, "  R5:\n    quadplex_allowed: true\n")

    with pytest.raises(RuleLoadError, match="stands down under"):
        load_rules(root, strict=True)


def test_standing_down_names_a_registered_condition(root: Path) -> None:
    """The same guard every other condition name gets. A typo here silently
    turns the exemption on everywhere, because a condition nobody ever holds
    is a condition that never fires."""
    write(
        root,
        "or/_state.yaml",
        "label: Oregon\n"
        "kind: state\n"
        "cite_default:\n"
        '  cite: "OAR 660-046-0220(2)(b)"\n'
        '  url: "https://oregon.public.law/rules/oar_660-046-0220"\n'
        '  quote: "or/oar.660-046-0220.txt#L55"\n'
        "  retrieved: 2026-08-19\n"
        "defaults:\n"
        "  max_density_du_per_acre:\n"
        "    exempt: true\n"
        "    preempts: always\n"
        "    unless: [unit_lotz]\n",
    )
    portland(root, "  R5:\n    quadplex_allowed: true\n")

    with pytest.raises(RuleLoadError, match="unit_lotz"):
        load_rules(root, strict=True)
