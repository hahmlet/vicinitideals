"""Flags, binds and the colour they make (Steph's flag plan, 2026-10-02).

The plan's own invariants, each defended here:

* the colour is derived, never stored: binds and flags in, colour out;
* no colour without a reason -- a lot that is not green names a bind or a
  flag at or above the line;
* every reason the old screen gave is accounted for by a flag or a bind, so
  the backfill can be reconciled one reason at a time;
* a flag is written whole or not at all (the write gate).

And Steph's four answers:

1. no variances: a miss is RED even where the code offers a path, and the
   path is logged on the bind;
2. a flag below the line keeps the lot green;
3. a minimum density missed is a low-severity flag, not a bind;
4. the colour is the "as if signed" one (the bridge's ``colour`` column is
   computed on the signed screening -- see test_quadfit_bridge).
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("shapely")

from flats.ingest import assign as az  # noqa: E402
from flats.ingest.normalize import GATES  # noqa: E402
from flats.rules.conditions import CONDITIONS  # noqa: E402
from flats.rules.resolver import Verdict as RuleVerdict  # noqa: E402
from flats.score import flags as fp  # noqa: E402
from flats.score.flags import SEP, Bind, Colour, ColourRules, Flag  # noqa: E402
from flats.score.screen import (  # noqa: E402
    _MEASURED_FLAG,
    _VERDICT_FLAG,
    CLOSER_LOOK_MIN_DENSITY,
    RELIEF_UNCONFIRMED,
    UNFLAGGED_REASONS,
    USE_PROHIBITED,
    LotFacts,
    Triage,
    screen,
)
from flats.score.configure import configure  # noqa: E402
from flats.score.relief import USE, ReliefPath, ReliefPolicy  # noqa: E402
from flats.rules.conditions import Tier  # noqa: E402
from flats.tests.test_screen import (  # noqa: E402
    DESIGN,
    LOT,
    NO_RELIEF,
    POLICY,
    READ,
    TWO_ACRES,
    WHERE,
    fit,
    levered,
    rules,
    run,
)

pytestmark = pytest.mark.unit


# --- the files a person owns ------------------------------------------------


def test_the_registry_and_the_rule_set_load() -> None:
    reg = fp.load_registry()
    rules_ = fp.load_rules()
    assert len(reg.types) >= 60
    assert rules_.yellow_at_severity == 3
    # Steph Q1: no approval is accepted yet.
    assert rules_.accept_approvals == ()


def test_every_type_waits_for_a_person() -> None:
    """An agent proposes types; it does not approve them."""
    reg = fp.load_registry()
    assert {t.status for t in reg.types.values()} == {fp.TypeStatus.pending}
    assert fp.load_rules().status is fp.TypeStatus.pending


def test_every_site_fact_has_a_flag_type() -> None:
    reg = fp.load_registry()
    facts = [n for n, c in CONDITIONS.items() if c.kind == "site_fact"]
    assert facts
    assert [n for n in facts if fp.fact_code(n) not in reg.types] == []


def test_every_code_the_screen_and_the_assign_stage_raise_is_registered() -> None:
    reg = fp.load_registry()
    raised = {*_VERDICT_FLAG.values(), *_MEASURED_FLAG.values(), *az.GATE_FLAG.values()}
    assert sorted(raised - set(reg.types)) == []
    # Every gate the lot table can set has its flag.
    assert set(GATES) <= set(az.GATE_FLAG)


def test_a_per_lot_type_is_keyed_by_the_lot_and_a_shared_one_is_not() -> None:
    with pytest.raises(ValueError):
        fp.FlagType(
            code="X-ONE", description="x", kind="categorical", risk="possible", severity=4,
            resolution="per_lot_review", scope="per_lot", key=["jurisdiction"], priority="next",
        )
    with pytest.raises(ValueError):
        fp.FlagType(
            code="X-TWO", description="x", kind="categorical", risk="possible", severity=4,
            resolution="measurement", scope="shared", key=["jurisdiction", "lot"], priority="next",
        )


def test_an_approved_type_names_who_approved_it() -> None:
    with pytest.raises(ValueError):
        fp.FlagType(
            code="X-THREE", description="x", kind="categorical", risk="possible", severity=4,
            resolution="measurement", scope="shared", key=["jurisdiction"], priority="next",
            status="approved",
        )


def test_an_unregistered_code_is_refused_with_the_way_forward() -> None:
    with pytest.raises(KeyError, match="pending"):
        fp.registry()["NO-SUCH-TYPE"]


# --- the write gate ----------------------------------------------------------


def _ok() -> Flag:
    return fp.make("RULE-UNSIGNED", "RULE_UNVERIFIED", {"jurisdiction": WHERE, "zone": "R5"})


def test_a_whole_flag_passes_the_gate() -> None:
    f = _ok()
    assert f.key == f"{WHERE}{SEP}R5"
    fp.validate([f])


@pytest.mark.parametrize(
    "bad",
    [
        Flag("RULE-UNSIGNED", WHERE, "RULE_UNVERIFIED"),  # a key part missing
        Flag("RULE-UNSIGNED", f"{WHERE}{SEP}R5", ""),  # no reason it was raised
        Flag("RULE-UNSIGNED", f"{WHERE}{SEP}R5", "x", bounds=(1.0, 2.0)),  # bounds on a categorical
        Flag("FIT-TIGHT", f"@{SEP}d", "TIGHT_FIT"),  # parametric without bounds
        Flag("FIT-TIGHT", f"@{SEP}d", "TIGHT_FIT", bounds=(2.0, 1.0)),  # low > high
        Flag("RULE-UNSIGNED", f"{WHERE}{SEP}R5", "x", severity=9),  # raised above its type
        Flag("NO-SUCH-TYPE", "x", "x"),
    ],
)
def test_an_incomplete_flag_is_refused(bad: Flag) -> None:
    if bad.code == "FIT-TIGHT":
        # The key is whole; only the bounds are wrong.
        fp.validate([Flag(bad.code, bad.key, bad.by, bounds=(1.0, 2.0))])
    with pytest.raises((ValueError, KeyError)):
        fp.validate([bad])


def test_a_key_part_may_not_hold_the_separator() -> None:
    with pytest.raises(ValueError):
        fp.make("RULE-UNSIGNED", "x", {"jurisdiction": WHERE, "zone": f"R5{SEP}X"})


def test_the_lot_is_filled_in_when_the_row_is_written() -> None:
    f = fp.make("ACCESS-STREET-UNCONFIRMED", "STREET_UNCONFIRMED", {"jurisdiction": WHERE, "zone": "R5", "lot": fp.LOT})
    (row,) = json.loads(fp.dumps([f], lot="1N1E01AA  100"))
    assert "1N1E01AA  100" in row["key"].split(SEP) and fp.LOT not in row["key"].split(SEP)
    assert fp.flags_from(fp.dumps([f])) == [f]


# --- the colour ---------------------------------------------------------------


def _rules(**over) -> ColourRules:
    """The shipped rule set with some settings moved (a person's edit)."""
    return fp.load_rules().model_copy(update=over)


RULES = _rules(yellow_at_severity=3, accept_approvals=())


def test_no_binds_and_no_flags_is_green() -> None:
    assert fp.colour([], [], rules=RULES) is Colour.green


def test_any_bind_is_red_while_no_approval_is_accepted() -> None:
    """Q1: a variance path does not save the lot; it is logged."""
    b = Bind("min_lot_area_sqft", 6000, 8000, 2000, relief="variance", relief_tier="discretionary")
    assert fp.colour([b], [], rules=RULES) is Colour.red


def test_an_accepted_path_makes_a_bind_yellow_and_a_wall_stays_red() -> None:
    later = _rules(yellow_at_severity=3, accept_approvals=("adjustment",), approval_severity=5)
    eased = Bind("fit_ft", 10, 11, 1, relief="adjustment", relief_tier="administrative")
    wall = Bind("fit_ft", 10, 11, 1, relief=None)
    assert fp.colour([eased], [], rules=later) is Colour.yellow
    assert fp.colour([eased, wall], [], rules=later) is Colour.red


def test_a_flag_below_the_line_stays_green_and_one_at_it_is_yellow() -> None:
    """Q2: "items with risk < 3 ... are still green"."""
    low = fp.make("SOLAR-SHADE", "SOLAR_SHADE_LIMIT", {"jurisdiction": WHERE, "zone": "R5", "lot": fp.LOT, "design": "d"})
    assert fp.severity_of(low) < 3
    assert fp.colour([], [low], rules=RULES) is Colour.green
    assert fp.colour([], [_ok()], rules=RULES) is Colour.yellow


def test_a_flag_cleared_at_its_worst_reading_counts_as_zero() -> None:
    """Q2: still a flag, and still on the lot, but at severity 0."""
    cleared = Flag(_ok().code, _ok().key, _ok().by, severity=0)
    fp.validate([cleared])
    assert fp.colour([], [cleared], rules=RULES) is Colour.green


def test_moving_the_line_recolours_without_a_rescreen() -> None:
    f = _ok()
    assert fp.colour([], [f], rules=_rules(yellow_at_severity=6)) is Colour.green
    assert fp.colour([], [f], rules=_rules(yellow_at_severity=5)) is Colour.yellow



def test_a_fit_short_by_under_a_foot_is_yellow_and_a_foot_or_more_is_red() -> None:
    """Steph 2026-10-02: "everything 1-20' goes to red ... except short by
    under 1'". The line is a setting, so moving it recolours without a
    re-screen."""
    shipped = fp.load_rules()
    assert shipped.near_miss == {"fit_ft": 1.0}
    assert shipped.near_miss_severity >= shipped.yellow_at_severity

    def fit_bind(short: float) -> Bind:
        return Bind("fit_ft", 50.0 - short, 50.0, short, relief="variance", relief_tier="discretionary")

    for short in (0.6, 0.99):
        assert fp.colour([fit_bind(short)], [], rules=shipped) is Colour.yellow, short
    for short in (1.0, 5.0, 20.0, 40.0):
        assert fp.colour([fit_bind(short)], [], rules=shipped) is Colour.red, short
    # Only the fit has a near miss: a lot 0.5 sq ft short of its minimum area is red.
    area = Bind("min_lot_area_sqft", 4999.5, 5000.0, 0.5, relief="variance")
    assert fp.colour([area], [], rules=shipped) is Colour.red
    # A near miss beside a real miss is still red.
    assert fp.colour([fit_bind(0.7), area], [], rules=shipped) is Colour.red
    # Moved, it recolours.
    assert fp.colour([fit_bind(3.0)], [], rules=_rules(near_miss={"fit_ft": 5.0})) is Colour.yellow
    assert fp.colour([fit_bind(0.7)], [], rules=_rules(near_miss={})) is Colour.red


def test_the_screen_makes_a_near_miss_yellow() -> None:
    s = run(f=fit(over_ft=-0.8), relief=READ)
    (b,) = s.binds
    assert b.check == "fit_ft" and b.shortfall == pytest.approx(0.8)
    assert s.colour is Colour.yellow
    assert run(f=fit(over_ft=-1.5), relief=READ).colour is Colour.red


# --- the screen writes them -------------------------------------------------


def test_a_clean_lot_has_nothing_and_is_green() -> None:
    s = run()
    assert (s.flags, s.binds, s.colour) == ((), (), Colour.green)


def test_a_miss_the_code_can_waive_is_red_with_its_path_logged() -> None:
    """Q1. The old screen said yellow; the plan says red, and keeps the path."""
    s = run(rules(min_lot_sqft=8000), relief=READ)
    assert s.triage is Triage.yellow
    assert s.colour is Colour.red
    (b,) = s.binds
    assert (b.check, b.relief, b.relief_tier, b.relief_confirmed) == (
        "min_lot_area_sqft", "variance", "discretionary", True,
    )
    assert b.shortfall == pytest.approx(2000)
    assert b.source == "PCC 33.110.220"


def test_an_unread_chapter_is_logged_unconfirmed_on_the_bind() -> None:
    s = run(rules(min_lot_sqft=8000))
    assert RELIEF_UNCONFIRMED in s.reasons
    (b,) = s.binds
    assert b.relief_confirmed is False and s.colour is Colour.red


def test_a_prohibited_use_is_a_bind_even_with_a_conditional_use_path() -> None:
    cup = ReliefPolicy({WHERE: {USE: [ReliefPath("conditional_use", Tier.discretionary, cite="PCC 33.815", confirmed=True)]}})
    s = run(rules(quadplex_allowed=False), relief=cup)
    assert s.triage is Triage.yellow
    assert s.colour is Colour.red
    assert [(b.check, b.relief) for b in s.binds] == [("use", "conditional_use")]


def test_a_rule_set_nobody_signed_binds_nothing() -> None:
    """A draft number never deletes a lot, here as in the triage."""
    s = run(rules(RuleVerdict.unverified, min_lot_sqft=99_000), relief=NO_RELIEF)
    assert s.binds == ()
    assert [f.code for f in s.flags] == ["RULE-UNSIGNED"]
    assert s.colour is Colour.yellow


def test_minimum_density_alone_is_a_low_flag_and_the_lot_is_green() -> None:
    """Q3: "It would just be a low risk flag. Maybe a 2"."""
    s = run(rules(min_density_du_per_acre=17.424), lot=TWO_ACRES, relief=NO_RELIEF)
    assert CLOSER_LOOK_MIN_DENSITY in s.reasons
    assert s.binds == ()
    (f,) = s.flags
    assert f.code == "DENSITY-MIN" and f.bounds is not None and f.bounds[0] <= f.bounds[1]
    assert fp.severity_of(f) == 2
    assert s.colour is Colour.green


def test_minimum_density_beside_a_wall_is_red() -> None:
    s = run(rules(min_density_du_per_acre=17.424, max_height_ft=20), lot=TWO_ACRES, relief=NO_RELIEF)
    assert s.colour is Colour.red


def test_a_tight_fit_is_green_with_its_flag() -> None:
    s = run(f=fit(over_ft=-0.3))
    (f,) = s.flags
    assert f.code == "FIT-TIGHT" and f.bounds is not None
    assert f.bounds[0] <= -0.3 <= f.bounds[1]
    assert s.colour is Colour.green


def test_a_warning_is_a_flag_below_the_line() -> None:
    s = run(rules(solar_shade_limit=True))
    assert [f.code for f in s.flags] == ["SOLAR-SHADE"]
    assert s.colour is Colour.green


def test_an_unknown_fact_a_standard_turns_on_is_a_flag_keyed_by_the_fact() -> None:
    config = configure(LOT, DESIGN)
    s = screen(levered("public_sewer"), LOT, DESIGN, fit(), policy=POLICY, config=config)
    (f,) = s.flags
    assert f.code == "FACT-PUBLIC-SEWER"
    assert f.key.split(SEP)[-1] == "public_sewer"
    assert s.colour is Colour.yellow


def test_a_lot_with_no_area_is_flagged_not_silent() -> None:
    s = run(lot=LotFacts(lot_sqft=0, frontage_ft=60, lot_width_ft=60))
    assert s.triage is Triage.unknown
    assert "GEOM-UNREADABLE" in {f.code for f in s.flags}
    assert s.colour is Colour.yellow


# --- the invariants, over every shape of lot the screen tests build -----------


def _cases():
    yield run()
    yield run(rules(min_lot_sqft=8000))
    yield run(rules(min_lot_sqft=8000), relief=READ)
    yield run(rules(min_lot_sqft=8000), relief=NO_RELIEF)
    yield run(rules(min_lot_sqft=9000, min_frontage_ft=62), relief=READ)
    yield run(rules(quadplex_allowed=False))
    yield run(rules(quadplex_allowed=None))
    yield run(rules(parking_min_per_unit=None))
    yield run(rules(RuleVerdict.unverified, min_lot_sqft=99_000))
    yield run(rules(RuleVerdict.zone_not_encoded))
    yield run(rules(RuleVerdict.jurisdiction_not_encoded))
    yield run(rules(solar_shade_limit=True, min_lot_sqft=8000), relief=READ)
    yield run(rules(min_density_du_per_acre=17.424), lot=TWO_ACRES, relief=NO_RELIEF)
    yield run(rules(min_density_du_per_acre=17.424, min_lot_sqft=100_000), lot=TWO_ACRES)
    yield run(rules(max_coverage_pct=33.0))
    for over in (-0.6, -0.3, 0.5, 4.0):
        yield run(f=fit(over_ft=over))
    yield run(f=fit(over_ft=-0.8), relief=NO_RELIEF)
    yield run(f=fit(over_ft=-3.0), relief=NO_RELIEF)
    yield run(lot=LotFacts(lot_sqft=0, frontage_ft=60, lot_width_ft=60))
    yield screen(levered("corner_lot"), LOT, DESIGN, fit(), policy=POLICY, config=configure(LOT, DESIGN))
    yield screen(levered("public_sewer"), LOT, DESIGN, fit(), policy=POLICY, config=configure(LOT, DESIGN))


CASES = list(_cases())


@pytest.mark.parametrize("s", CASES, ids=[f"case{i}" for i in range(len(CASES))])
def test_no_colour_without_a_reason(s) -> None:
    if s.colour is Colour.red:
        assert s.binds
    elif s.colour is Colour.yellow:
        assert any(fp.severity_of(f) >= fp.colour_rules().yellow_at_severity for f in s.flags) or s.binds


@pytest.mark.parametrize("s", CASES, ids=[f"case{i}" for i in range(len(CASES))])
def test_every_old_reason_is_accounted_for(s) -> None:
    """The backfill's reconciliation, one screening at a time."""
    fp.validate(s.flags)
    by = {f.by for f in s.flags}
    assert set(s.reasons) - UNFLAGGED_REASONS <= by
    signed = not any(f.code in _VERDICT_FLAG.values() for f in s.flags)
    if USE_PROHIBITED in s.reasons and signed:
        assert any(b.check == "use" for b in s.binds)
    if RELIEF_UNCONFIRMED in s.reasons:
        assert any(not b.relief_confirmed for b in s.binds)


@pytest.mark.parametrize("s", CASES, ids=[f"case{i}" for i in range(len(CASES))])
def test_the_new_colour_is_never_kinder_than_the_old_except_where_steph_said(s) -> None:
    """Old red stays red, unless its only miss is a fit short by under a
    foot (Steph's near-miss line). Old yellow from a waivable miss goes red
    (Q1). Only a lot whose every reason is a minimum density (Q3) moves
    toward green."""
    if s.triage is Triage.red:
        near = s.binds and all(fp.near_miss(b, fp.colour_rules()) for b in s.binds)
        assert s.colour is (Colour.yellow if near else Colour.red)
    if s.triage is not Triage.green and s.colour is Colour.green:
        assert set(s.reasons) == {CLOSER_LOOK_MIN_DENSITY}
    if s.triage is Triage.green:
        assert s.colour is Colour.green


# --- the assign stage's rows ---------------------------------------------------


def _lot(**over):
    return {"tlid": "1N1E01AA  100", "jurisdiction": WHERE, "zone": "R5", "area_sqft": 5000.0, **over}


@pytest.mark.parametrize("gate", [*GATES, az.NOT_MEASURED])
def test_an_unmeasured_lot_carries_its_gate_as_a_flag(gate: str) -> None:
    row = az.synthetic_row(_lot(zone=None if gate == "NO_ZONE" else "R5"), "pod56x36", gate)
    (f,) = json.loads(row["flags"])
    assert f["code"] == az.GATE_FLAG[gate] and f["by"] == gate
    assert row["binds"] == ""
    assert row["colour"] == "yellow"


def test_a_per_lot_gate_names_the_lot() -> None:
    row = az.synthetic_row(_lot(zone=None), "pod56x36", "NO_ZONE")
    (f,) = json.loads(row["flags"])
    assert f["key"].split(SEP)[-1] == "1N1E01AA  100"


def test_a_pocket_lot_is_keyed_by_the_layer_whose_zoning_it_carries() -> None:
    row = az.synthetic_row(_lot(rules_layer="or/clackamas"), "pod56x36", "ZONE_POCKET")
    (f,) = json.loads(row["flags"])
    assert f["key"].split(SEP)[0] == "or/clackamas"


class _Res:
    def __init__(self, trusted: bool):
        self.verdict = RuleVerdict.trusted if trusted else RuleVerdict.unverified
        self.reason = None if trusted else "RULE_UNVERIFIED"
        self.values = {"quadplex_allowed": type("V", (), {"value": False, "levers": frozenset()})()}


class _Rules:
    def resolve(self, layer_id, zone):
        return _Res(trusted=layer_id != "or/draft")


@pytest.mark.parametrize(
    ("policy", "relief"),
    [
        (ReliefPolicy({}), None),
        (ReliefPolicy({WHERE: {USE: [ReliefPath("conditional_use", Tier.discretionary, cite="X", confirmed=True)]}}), "conditional_use"),
    ],
)
def test_a_forbidden_zone_is_red_with_its_use_path_logged(policy, relief) -> None:
    gate = az.use_gate_for(_Rules(), policy)
    answer = gate(WHERE, "C3")
    row = az.prohibited_row(_lot(zone="C3"), "pod56x36", answer)
    assert row["colour"] == "red" and row["flags"] == ""
    (b,) = json.loads(row["binds"])
    assert b["check"] == "use" and b.get("relief") == relief
