"""The rear court kept out of the rear setback in Gresham, Sandy and Troutdale
(FOLLOWUPS 150, read 2026-11-05).

Until this reading the court SHARED the rear yard in all three: the ground
behind the building's rear wall was the deeper of the court and the yard.
Each code keeps parking out of it in its own words, and the encoding is the
one Cornelius already uses (``parking_required_yard_prohibited``): the court
stands in front of the yard and the two stack.

- Gresham GDC 7.0420(B)(5)(c), the quadplex on its parent lot: parking spaces
  "in the rear yard setback when there is an alley", a closed list. The alley
  lot and the townhouse path (7.0431(B)(3)(b)(i), "located in the rear yard")
  keep the old sharing.
- Sandy SDC 17.98.50 A and Troutdale TDC 9.095 A: "Parking areas, which abut
  a residential zoning district, shall meet the setback of the most
  restrictive adjoining residential zoning district" -- read literally, with
  the stricter neighbour's yard where one adjoins.

Each test resolves the real zone from the corpus.
"""

from __future__ import annotations

from datetime import date

import pytest
import yaml
from shapely import box

from flats.designs.model import Design
from flats.encode.load import load_trusted
from flats.fit.draw import Drawing
from flats.fit.rectangle import Fit
from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier
from flats.geom.neighbour import Line as NeighbourLine
from flats.ingest.quadfit import (
    QuadfitLot,
    _fit_stands,
    _parking_doubt_drawn_fails,
    _sandy_strip_drawn_fails,
)
from flats.provenance.store import ProvenanceStore
from flats.rules.fields import OPTIONAL_FIELDS, field
from flats.rules.model import Provenance, Status
from flats.rules.resolver import Resolved, Verdict as RuleVerdict, ZoneResolution
from flats.score.paper import paper_fit
from flats.score.screen import (
    PARKING_SETBACK_DOUBT,
    PARKING_SETBACK_DOUBT_RULING,
    LotFacts,
    Triage,
    _court_beyond_rear,
    screen,
)
from flats.score.slack import SlackPolicy

pytestmark = pytest.mark.unit

FIELD = "parking_required_yard_prohibited"
STRIP = "parking_lot_line_buffer_ft"
DOUBT = "parking_lot_line_buffer_doubt_ft"
GRESHAM = "or/multnomah/gresham"
SANDY = "or/clackamas/sandy"
TROUTDALE = "or/multnomah/troutdale"

POD = """
version: 1
label: Four-plex pod
typology: townhome_rear_court
footprint: {width_ft: 56, depth_ft: 36}
units: 4
stories: 2
height_ft: 26
parking: {stalls_per_unit: 1.5, config: rear_court}
delivery: {method: modular, crane_required: true, crane_reach_ft: 60}
"""


def pod() -> Design:
    return Design(**{**yaml.safe_load(POD), "id": "pod"})


class Sharing:
    """A real resolution with the rule taken out: the screen before."""

    def __init__(self, rules) -> None:
        self._rules = rules

    def get(self, name: str) -> object:
        return None if name in (FIELD, STRIP) else self._rules.get(name)

    def __getattr__(self, name: str) -> object:
        return getattr(self._rules, name)


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


def quoted(value) -> str:
    return " ".join(ProvenanceStore().quote(value.prov.quote).split())


def deeper(rules) -> float:
    """How much deeper the paper lot is than when the court shared the yard."""
    return paper_fit(pod(), rules).min_depth_ft - paper_fit(pod(), Sharing(rules)).min_depth_ft


def screen_rules(
    *,
    doubt: float | None = 20,
    yard_prohibited: bool = True,
    strip: float = 0,
    jurisdiction: str = TROUTDALE,
) -> ZoneResolution:
    values = {
        "quadplex_allowed": True,
        "min_lot_sqft": 3000,
        "min_frontage_ft": 20,
        "min_lot_width_ft": 20,
        "max_coverage_pct": 100,
        "max_far": 10,
        "max_height_ft": 35,
        "max_units": 4,
        "parking_min_per_unit": 1.5,
        "setback_front_ft": 10,
        "setback_side_ft": 5,
        "setback_rear_ft": 10,
        FIELD: yard_prohibited,
        STRIP: strip,
        DOUBT: doubt,
    }
    provenance = Provenance(
        cite="TDC 3.130.A",
        url="https://api.municode.com/PublicationPdfDownload/1813",
        retrieved=date(2026, 8, 29),
    )
    return ZoneResolution(
        jurisdiction=jurisdiction,
        zone="LDR-2",
        verdict=RuleVerdict.trusted,
        values={
            name: Resolved(
                name=name,
                value=value,
                status=Status.verified,
                prov=provenance,
                layer=TROUTDALE,
                origin="zone",
            )
            for name, value in values.items()
            if value is not None
        },
    )


def screen_lot(
    *,
    depth: float,
    rules: ZoneResolution,
    doubt_fit_failed: bool = False,
    doubt_checked: bool = False,
    strip_waived: bool = False,
):
    design = pod()
    fit = Fit(
        fits=True,
        width_ft=56,
        depth_ft=36,
        best_depth_ft=depth,
        slack_ft=depth - 36,
        across_ft=100,
        stalls=6,
    )
    return screen(
        rules,
        LotFacts(
            lot_sqft=20_000,
            frontage_ft=100,
            lot_width_ft=100,
            lot_depth_ft=200,
            parking_setback_doubt_failed=doubt_fit_failed,
            parking_setback_doubt_checked=doubt_checked,
            strip_waived=strip_waived,
        ),
        design,
        fit,
        policy=SlackPolicy(tolerance={"fit_ft": 0.5}),
    )


def drawn_lot(
    jurisdiction: str,
    rear_zone: str,
    side_zone: str,
    *,
    rear_unresolved: int = 0,
) -> QuadfitLot:
    edges = LotEdges(
        tier=Tier.clean,
        edges=(
            Edge(0, 0, 100, 0, 100, 0, EdgeClass.rear),
            Edge(0, 0, 0, 100, 100, 90, EdgeClass.side),
        ),
        front_bearings=(0,),
        frontage_ft=100,
        convexity=1,
    )
    # As the bridge builds it: ``jurisdiction`` and the neighbours' in
    # quadfit's bare spelling ("sandy"), the layer the corpus path. Round 3's
    # fixture used the path for both and hid a check that matched no real lot.
    bare = jurisdiction.rsplit("/", 1)[-1]
    return QuadfitLot(
        tlid="test",
        jurisdiction=bare,
        zone=rear_zone,
        layer_id=jurisdiction,
        facts=LotFacts(lot_sqft=20_000),
        observed={},
        front_bearings=(0,),
        envelope=None,
        edges=edges,
        neighbour_lines=(
            NeighbourLine(((bare, rear_zone),), rear_unresolved),
            NeighbourLine(((bare, side_zone),), 0),
        ),
    )


def drawn_court(*, side: float, rear: float) -> Drawing:
    return Drawing(
        room=box(0, 0, 100, 100),
        building=None,
        lane=None,
        court=box(side, rear, side + 10, rear + 10),
        fits=True,
    )


def test_setback_doubt_is_an_optional_numeric_field() -> None:
    assert DOUBT in OPTIONAL_FIELDS
    assert field(DOUBT).kind == "length_ft"


# --- Gresham --------------------------------------------------------------------


def test_gresham_cites_the_closed_list() -> None:
    from flats.rules.loader import load_rules

    held = load_rules()[GRESHAM].defaults[FIELD]
    assert held.value is True
    assert "in the rear yard setback when there is an alley" in quoted(held)


def test_a_gresham_quadplex_court_no_longer_parks_in_the_rear_setback(corpus) -> None:
    rules = corpus.resolve(GRESHAM, "LDR-7", ())
    assert rules.get(FIELD) is True
    # 2026-11-06, round 5: LDR-7 carries 20 for the wall (the roof plane) and
    # prints 15; the court stays out of the 15, so that is what it adds.
    rear = float(rules.values["setback_rear_ft"].before_step_back)
    assert rear == 15
    assert float(rules.get("setback_rear_ft")) == 20
    assert rear > 0
    assert deeper(rules) == pytest.approx(rear)
    assert _court_beyond_rear(pod(), rules) > _court_beyond_rear(pod(), Sharing(rules))


def test_a_gresham_alley_lot_keeps_todays_sharing(corpus) -> None:
    rules = corpus.resolve(GRESHAM, "LDR-7", ("alley_at_rear", "abuts_alley"))
    assert rules.get(FIELD) is False
    assert deeper(rules) == pytest.approx(0)
    assert _court_beyond_rear(pod(), rules) == _court_beyond_rear(pod(), Sharing(rules))


def test_a_side_alley_does_not_open_the_gresham_rear_setback(corpus) -> None:
    rules = corpus.resolve(GRESHAM, "LDR-7", ("alley_at_side", "abuts_alley"))
    assert rules.get(FIELD) is True


@pytest.mark.parametrize("conds", [("unit_lots",), ("unit_lots", "alley_at_rear", "abuts_alley")])
def test_the_gresham_townhouse_path_keeps_the_rear_yard(corpus, conds) -> None:
    rules = corpus.resolve(GRESHAM, "LDR-7", conds)
    assert rules.get(FIELD) is False
    assert not rules.ambiguous


# --- Sandy ----------------------------------------------------------------------


@pytest.mark.parametrize("zone", ["R-2", "R-3"])
def test_a_sandy_court_meets_the_rear_setback(corpus, zone: str) -> None:
    rules = corpus.resolve(SANDY, zone, ())
    assert rules.get(FIELD) is True
    assert "abut a residential zoning district" in quoted(rules.values[FIELD])
    # No stricter neighbour: the strip is the zone's own side yard, which
    # the building already keeps, and the court stacks on the 15 ft rear.
    assert rules.get(STRIP) == rules.get("setback_side_ft") == 5
    assert deeper(rules) == pytest.approx(15)


def test_a_sandy_court_beside_sfr_takes_the_sfr_rear_yard(corpus) -> None:
    rules = corpus.resolve(SANDY, "R-2", ("abuts_lower_density_zone",))
    assert rules.get(STRIP) == 20
    # The 15 ft rear stands, and the court stands 20 off the line instead.
    assert deeper(rules) == pytest.approx(20)


def test_sandy_row_houses_are_held_too(corpus) -> None:
    rules = corpus.resolve(SANDY, "R-1", ("unit_lots",))
    assert rules.get(FIELD) is True


# --- Troutdale ------------------------------------------------------------------


@pytest.mark.parametrize("zone", ["LDR-1", "LDR-2", "MDR"])
def test_a_troutdale_court_meets_the_rear_setback(corpus, zone: str) -> None:
    rules = corpus.resolve(TROUTDALE, zone, (), lot={"lot_sqft": 9000.0})
    assert rules.get(FIELD) is True
    assert "abut a residential zoning district" in quoted(rules.values[FIELD])
    assert rules.get("setback_rear_ft") == 10
    assert deeper(rules) == pytest.approx(10)


def test_a_troutdale_lot_with_no_residential_neighbour_shares(corpus) -> None:
    rules = corpus.resolve(TROUTDALE, "MU-2", ("abuts_nonresidential_zone",), lot={"lot_sqft": 9000.0})
    assert rules.get(FIELD) is False


@pytest.mark.parametrize("zone", ["LDR-1", "LDR-2", "MDR", "HDR", "MU-1", "MU-2", "MU-3"])
def test_troutdale_residential_and_mixed_zones_hold_the_doubt_figure(corpus, zone: str) -> None:
    rules = corpus.resolve(TROUTDALE, zone, (), lot={"lot_sqft": 9000.0})

    assert rules.get(FIELD) is True
    assert rules.get(DOUBT) == 20


def test_troutdale_fitting_only_the_encoded_setback_is_yellow() -> None:
    result = screen_lot(depth=90, rules=screen_rules())

    assert result.triage is Triage.yellow
    assert PARKING_SETBACK_DOUBT in result.reasons
    (flag,) = [item for item in result.flags if item.code == "PARKING-SETBACK-DOUBT"]
    assert flag.by == PARKING_SETBACK_DOUBT
    assert flag.source == PARKING_SETBACK_DOUBT_RULING


def test_troutdale_fitting_both_setbacks_keeps_today_green() -> None:
    result = screen_lot(depth=120, rules=screen_rules())

    assert result.triage is Triage.green
    assert PARKING_SETBACK_DOUBT not in result.reasons
    assert not any(item.code == "PARKING-SETBACK-DOUBT" for item in result.flags)


def test_troutdale_drawn_court_under_rear_doubt_is_yellow() -> None:
    rules = screen_rules()
    lot = drawn_lot(TROUTDALE, "LDR-1", "MU-2")
    failed = _parking_doubt_drawn_fails(lot, rules, drawn_court(side=25, rear=16.5))
    result = screen_lot(
        depth=120, rules=rules, doubt_checked=True, doubt_fit_failed=failed
    )

    assert failed
    assert result.triage is Triage.yellow
    assert PARKING_SETBACK_DOUBT in result.reasons


def test_troutdale_drawn_court_clearing_rear_and_side_doubt_can_be_green() -> None:
    rules = screen_rules()
    lot = drawn_lot(TROUTDALE, "LDR-1", "LDR-2")
    failed = _parking_doubt_drawn_fails(lot, rules, drawn_court(side=7.5, rear=20))
    result = screen_lot(
        depth=120, rules=rules, doubt_checked=True, doubt_fit_failed=failed
    )

    assert not failed
    assert result.triage is Triage.green
    assert PARKING_SETBACK_DOUBT not in result.reasons


def test_troutdale_side_line_uses_its_side_figure_not_the_rear_figure() -> None:
    rules = screen_rules()
    lot = drawn_lot(TROUTDALE, "MU-2", "LDR-2")
    failed = _parking_doubt_drawn_fails(lot, rules, drawn_court(side=8, rear=30))

    assert not failed


def test_troutdale_failing_the_stricter_side_fit_is_yellow() -> None:
    result = screen_lot(depth=120, rules=screen_rules(), doubt_fit_failed=True)

    assert result.triage is Triage.yellow
    assert PARKING_SETBACK_DOUBT in result.reasons
    assert any(item.code == "PARKING-SETBACK-DOUBT" for item in result.flags)


def test_troutdale_failing_the_encoded_setback_is_not_a_doubt_move() -> None:
    result = screen_lot(depth=80, rules=screen_rules())

    assert PARKING_SETBACK_DOUBT not in result.reasons
    assert not any(item.code == "PARKING-SETBACK-DOUBT" for item in result.flags)
    assert result.triage is not Triage.green


def test_troutdale_nonresidential_neighbour_has_no_setback_doubt() -> None:
    result = screen_lot(depth=90, rules=screen_rules(yard_prohibited=False))

    assert result.triage is Triage.green
    assert PARKING_SETBACK_DOUBT not in result.reasons
    assert not any(item.code == "PARKING-SETBACK-DOUBT" for item in result.flags)


def test_city_without_setback_doubt_field_is_unchanged() -> None:
    result = screen_lot(depth=90, rules=screen_rules(doubt=None))

    assert result.triage is Triage.green
    assert PARKING_SETBACK_DOUBT not in result.reasons
    assert not any(item.code == "PARKING-SETBACK-DOUBT" for item in result.flags)


def test_sandy_partly_unread_house_line_checks_the_drawn_court_strip() -> None:
    rules = screen_rules(doubt=None, strip=20, jurisdiction=SANDY)
    lot = drawn_lot(SANDY, "R-2", "R-2", rear_unresolved=1)
    failed = _sandy_strip_drawn_fails(lot, rules, drawn_court(side=18.4, rear=30))
    result = screen_lot(depth=120, rules=rules, strip_waived=failed)

    assert failed
    assert result.triage is not Triage.green


@pytest.mark.parametrize(("zone", "strip"), [("MDR", 10), ("LDR-2", 10)])
def test_a_troutdale_quadplex_beside_ldr_takes_its_side_yard(corpus, zone: str, strip: float) -> None:
    rules = corpus.resolve(TROUTDALE, zone, ("abuts_lower_density_zone",), lot={"lot_sqft": 9000.0})
    assert rules.get(STRIP) == strip
    townhouses = corpus.resolve(
        TROUTDALE, zone, ("abuts_lower_density_zone", "unit_lots"), lot={"lot_sqft": 9000.0}
    )
    # The townhouse row prints 5 in every district: the strip is the side
    # yard already charged, so it adds nothing.
    assert townhouses.get(STRIP) == 5
    # With no stricter neighbour the strip is the zone's own quadplex side,
    # likewise already charged.
    alone = corpus.resolve(TROUTDALE, zone, (), lot={"lot_sqft": 9000.0})
    assert alone.get(STRIP) == alone.get("setback_side_ft")


def test_troutdale_drawn_court_is_checked_on_unsigned_rules() -> None:
    """Every Troutdale lot is RULE_UNVERIFIED; the check ran on none of them
    in round 3 (FOLLOWUPS 150 round-3 read, finding 1)."""
    import dataclasses

    rules = dataclasses.replace(screen_rules(), verdict=RuleVerdict.unverified)
    lot = drawn_lot(TROUTDALE, "LDR-1", "MU-2")

    assert not rules.trusted
    assert _parking_doubt_drawn_fails(lot, rules, drawn_court(side=25, rear=16.5))


def test_sandy_unread_line_owes_sfr_strip_even_where_the_resolved_strip_is_the_side_yard() -> None:
    """24E14DA00700: the strip resolved to the zone's own 5 ft side, the
    neighbour line partly unread, the drawn court 18.4 ft off it -- not GREEN."""
    rules = screen_rules(doubt=None, strip=5, jurisdiction=SANDY)
    lot = drawn_lot(SANDY, "R-2", "R-2", rear_unresolved=1)
    failed = _sandy_strip_drawn_fails(lot, rules, drawn_court(side=30, rear=18.4))
    result = screen_lot(depth=120, rules=rules, strip_waived=failed)

    assert failed
    assert result.triage is not Triage.green


def test_sandy_fully_read_neighbours_no_stricter_keep_the_resolved_strip() -> None:
    rules = screen_rules(doubt=None, strip=5, jurisdiction=SANDY)
    lot = drawn_lot(SANDY, "R-2", "R-1")

    assert not _sandy_strip_drawn_fails(lot, rules, drawn_court(side=6, rear=6))


def test_sandy_sfr_across_a_line_owes_twenty_feet() -> None:
    rules = screen_rules(doubt=None, strip=5, jurisdiction=SANDY)
    lot = drawn_lot(SANDY, "R-2", "SFR")

    assert _sandy_strip_drawn_fails(lot, rules, drawn_court(side=12, rear=30))
    assert not _sandy_strip_drawn_fails(lot, rules, drawn_court(side=20, rear=30))


def test_troutdale_drawn_doubt_holds_an_unsigned_lot_out_of_green() -> None:
    """The screen kept a gate on ``rules.trusted`` that threw away the
    bridge's drawn-court doubt on every Troutdale lot (FOLLOWUPS 150 round-4
    mini check): the doubt must reach the colour on unsigned rules."""
    import dataclasses

    rules = dataclasses.replace(screen_rules(), verdict=RuleVerdict.unverified)
    result = screen_lot(depth=120, rules=rules, doubt_checked=True, doubt_fit_failed=True)

    assert not rules.trusted
    assert result.triage is not Triage.green
    assert any(item.code == "PARKING-SETBACK-DOUBT" for item in result.flags)


def test_a_tolerated_fit_has_its_drawn_court_checked() -> None:
    """A fit short by less than the tolerance still reads GREEN, so the
    drawn-court doubt must run on it (FOLLOWUPS 150 round-4 mini check:
    45 Troutdale GREENs stood on tolerated fits never drawn-checked)."""
    tolerated = screen_lot(depth=82.8, rules=screen_rules(doubt=None))
    passed = screen_lot(depth=120, rules=screen_rules(doubt=None))
    failed = screen_lot(depth=60, rules=screen_rules(doubt=None))
    verdicts = {
        name: next(c.verdict.value for c in r.checks if c.check == "fit_ft")
        for name, r in (("tolerated", tolerated), ("passed", passed), ("failed", failed))
    }

    assert verdicts == {"tolerated": "tolerated", "passed": "pass", "failed": "fail"}
    assert _fit_stands(tolerated) and _fit_stands(passed)
    assert not _fit_stands(failed)
