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

import dataclasses
from datetime import date

import pytest
import yaml
from shapely import Polygon, box

from flats.designs.model import Design
from flats.encode.load import load_trusted
from flats.fit.draw import Drawing
from flats.fit.rectangle import Fit
from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier
from flats.geom.neighbour import Line as NeighbourLine
from flats.ingest.quadfit import (
    QuadfitLot,
    Screened,
    _fit_stands,
    _imaginary_rear_line,
    _opposite_line,
    _parking_doubt_drawn_fails,
    _rear_court_short,
    _sandy_strip_drawn_fails,
    rear_court_checked,
)
from flats.provenance.store import ProvenanceStore
from flats.rules.fields import OPTIONAL_FIELDS, field
from flats.rules.model import Provenance, Status
from flats.rules.resolver import Resolved, Verdict as RuleVerdict, ZoneResolution
from flats.score.paper import behind_wall_ft, paper_fit
from flats.score.screen import (
    PARKING_SETBACK_DOUBT,
    PARKING_SETBACK_DOUBT_RULING,
    REAR_COURT_SHORT,
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


# --- Round 5 (2026-11-06): a slanted line opposite the front is still the rear ---


def slanted_lot(layer: str, *, zone: str = "LDR-1", neighbour: str = "LDR-1") -> QuadfitLot:
    """A 100 ft front along y=0, a square side, and a far line 33 degrees off the
    front, as 1N3E36AC  -06300 lies: no line is classed rear."""
    deep_left, deep_right = 150.0, 150.0 - 100.0 * 0.6494
    edges = LotEdges(
        tier=Tier.clean,
        edges=(
            Edge(0, 0, 100, 0, 100, 0, EdgeClass.front),
            Edge(100, 0, 100, deep_right, deep_right, 90, EdgeClass.side),
            Edge(100, deep_right, 0, deep_left, 119.2, 147, EdgeClass.side),
            Edge(0, deep_left, 0, 0, deep_left, 90, EdgeClass.side),
        ),
        front_bearings=(0,),
        frontage_ft=100,
        convexity=1,
    )
    bare = layer.rsplit("/", 1)[-1]
    across = NeighbourLine(((bare, neighbour),), 0)
    return QuadfitLot(
        tlid="1N3E36AC  -06300",
        jurisdiction=bare,
        zone=zone,
        layer_id=layer,
        facts=LotFacts(lot_sqft=20_000),
        observed={},
        front_bearings=(0,),
        envelope=None,
        edges=edges,
        lot_geom=Polygon([(0, 0), (100, 0), (100, deep_right), (0, deep_left)]),
        neighbour_lines=(None, across, across, across),
    )


def far_line_court(lot: QuadfitLot, off_ft: float) -> object:
    """A 10 by 10 court ``off_ft`` from the slanted line, one side along it."""
    far = _opposite_line(lot)
    assert far is not None
    # The slanted line's inward normal, walked from its midpoint.
    mx, my = (far.x1 + far.x2) / 2, (far.y1 + far.y2) / 2
    dx, dy = (far.x2 - far.x1) / far.length_ft, (far.y2 - far.y1) / far.length_ft
    nx, ny = -dy, dx
    if ny > 0:
        nx, ny = -nx, -ny
    cx, cy = mx + nx * off_ft, my + ny * off_ft
    return Polygon(
        [
            (cx - dx * 5, cy - dy * 5),
            (cx + dx * 5, cy + dy * 5),
            (cx + dx * 5 + nx * 10, cy + dy * 5 + ny * 10),
            (cx - dx * 5 + nx * 10, cy - dy * 5 + ny * 10),
        ]
    )


def test_the_slanted_far_line_is_the_opposite_line() -> None:
    lot = slanted_lot(TROUTDALE)
    far = _opposite_line(lot)
    assert far is lot.edges.edges[2]
    assert far.cls is EdgeClass.side


def test_a_square_line_across_a_through_lot_is_not_opposite() -> None:
    # The far non-street line runs 90 degrees off the front: a side, never a rear.
    edges = LotEdges(
        tier=Tier.clean,
        edges=(
            Edge(0, 0, 100, 0, 100, 0, EdgeClass.front),
            Edge(0, 100, 100, 100, 100, 0, EdgeClass.front),
            Edge(100, 0, 100, 100, 100, 90, EdgeClass.side),
            Edge(0, 0, 0, 100, 100, 90, EdgeClass.side),
        ),
        front_bearings=(0,),
        frontage_ft=200,
        convexity=1,
    )
    across = NeighbourLine((("troutdale", "LDR-1"),), 0)
    lot = QuadfitLot(
        tlid="through",
        jurisdiction="troutdale",
        zone="LDR-1",
        layer_id=TROUTDALE,
        facts=LotFacts(lot_sqft=10_000),
        observed={},
        front_bearings=(0,),
        envelope=None,
        edges=edges,
        neighbour_lines=(None, None, across, across),
    )
    assert _opposite_line(lot) is None


def test_troutdale_slanted_far_line_owes_the_rear_figure_not_the_side() -> None:
    """1N3E36AC  -06300: 17.2 ft off a line classed side, under the 20 of 3.130.A."""
    rules = screen_rules()
    lot = slanted_lot(TROUTDALE)
    drawn = Drawing(
        room=box(0, 0, 100, 100),
        building=None,
        lane=None,
        court=far_line_court(lot, 17.2),
        fits=True,
    )
    assert _parking_doubt_drawn_fails(lot, rules, drawn)
    drawn = Drawing(
        room=box(0, 0, 100, 100),
        building=None,
        lane=None,
        court=far_line_court(lot, 21.0),
        fits=True,
    )
    assert not _parking_doubt_drawn_fails(lot, rules, drawn)


def test_the_line_opposite_changes_no_setback_class() -> None:
    lot = slanted_lot(TROUTDALE)
    _opposite_line(lot)
    assert [e.cls for e in lot.edges.edges] == [
        EdgeClass.front,
        EdgeClass.side,
        EdgeClass.side,
        EdgeClass.side,
    ]


def test_gresham_imaginary_rear_line_is_ten_feet_at_the_deepest_point() -> None:
    lot = slanted_lot(GRESHAM, zone="LDR-7", neighbour="LDR-7")
    line = _imaginary_rear_line(lot, 0.0)
    assert line.length == pytest.approx(10.0, abs=0.1)
    # Parallel to the front, at the deep corner: 10 ft across at the 0.6494 slope.
    y = {round(c[1], 3) for c in line.coords}
    assert len(y) == 1
    assert y.pop() == pytest.approx(150.0 - 6.494, abs=0.1)


def test_gresham_rear_line_of_a_rectangle_is_the_rear_line() -> None:
    edges = LotEdges(
        tier=Tier.clean,
        edges=(
            Edge(0, 0, 100, 0, 100, 0, EdgeClass.front),
            Edge(100, 0, 100, 150, 150, 90, EdgeClass.side),
            Edge(100, 150, 0, 150, 100, 0, EdgeClass.rear),
            Edge(0, 150, 0, 0, 150, 90, EdgeClass.side),
        ),
        front_bearings=(0,),
        frontage_ft=100,
        convexity=1,
    )
    lot = QuadfitLot(
        tlid="square",
        jurisdiction="gresham",
        zone="LDR-5",
        layer_id=GRESHAM,
        facts=LotFacts(lot_sqft=15_000),
        observed={},
        front_bearings=(0,),
        envelope=None,
        edges=edges,
        lot_geom=box(0, 0, 100, 150),
    )
    line = _imaginary_rear_line(lot, 0.0)
    assert line.length == pytest.approx(100.0, abs=0.1)
    assert line.coords[0][1] == pytest.approx(150.0, abs=0.01)


def test_gresham_court_is_measured_from_the_imaginary_rear_line(corpus) -> None:
    """1S3E04BB  -07500 misses it (8.7 ft); 1S3E03BA  -00500 clears it though the
    slanted line itself stands 5.8 ft off (3.0100 L1316, L1345-L1347)."""
    rules = corpus.resolve(GRESHAM, "LDR-7", ())
    lot = slanted_lot(GRESHAM, zone="LDR-7", neighbour="LDR-7")
    y = 150.0 - 6.494
    near_the_deep_corner = box(0, y - 8.7 - 10, 10, y - 8.7)
    assert _rear_court_short(lot, rules, near_the_deep_corner, 0.0)
    # Clear of the imaginary line by 15 ft, though only ~6 ft off the slanted one.
    beside_the_slant = box(70, 50, 95, y - 15.5)
    assert not _rear_court_short(lot, rules, beside_the_slant, 0.0)


def test_gresham_court_inside_the_yard_off_a_tilted_rear_line_is_held(corpus) -> None:
    """1S3E10DA  -10200: 14.5 ft off a rear line a shade off the front, clear of
    the 10 ft line at its far corner. The real line is still opposite the front."""
    rules = corpus.resolve(GRESHAM, "LDR-5", ())
    edges = LotEdges(
        tier=Tier.clean,
        edges=(
            Edge(0, 0, 100, 0, 100, 0, EdgeClass.front),
            Edge(100, 0, 100, 150, 150, 90, EdgeClass.side),
            Edge(100, 150, 0, 148, 100, 1, EdgeClass.rear),
            Edge(0, 148, 0, 0, 148, 90, EdgeClass.side),
        ),
        front_bearings=(0,),
        frontage_ft=100,
        convexity=1,
    )
    across = NeighbourLine((("gresham", "LDR-5"),), 0)
    lot = QuadfitLot(
        tlid="1S3E10DA  -10200",
        jurisdiction="gresham",
        zone="LDR-5",
        layer_id=GRESHAM,
        facts=LotFacts(lot_sqft=15_000),
        observed={},
        front_bearings=(0,),
        envelope=None,
        edges=edges,
        lot_geom=Polygon([(0, 0), (100, 0), (100, 150), (0, 148)]),
        neighbour_lines=(None, across, across, across),
    )
    # The low corner of the rear line stands 14.5 off; the 10 ft line, up in the
    # far corner, 15 and more.
    court = box(0, 100, 20, 133.5)
    line = _imaginary_rear_line(lot, 0.0)
    assert court.distance(line) >= 15
    assert _rear_court_short(lot, rules, court, 0.0)
    assert not _rear_court_short(lot, rules, box(0, 100, 20, 132.0), 0.0)


def test_gresham_unread_court_is_held(corpus) -> None:
    rules = corpus.resolve(GRESHAM, "LDR-7", ())
    assert _rear_court_short(slanted_lot(GRESHAM), rules, None, 0.0)


def test_a_gresham_townhouse_or_alley_lot_is_not_measured(corpus) -> None:
    lot = slanted_lot(GRESHAM, zone="LDR-7", neighbour="LDR-7")
    y = 150.0 - 6.494
    court = box(0, y - 18, 10, y - 8)
    for conds in (("unit_lots",), ("alley_at_rear", "abuts_alley")):
        rules = corpus.resolve(GRESHAM, "LDR-7", conds)
        assert not _rear_court_short(lot, rules, court, 0.0), conds


def test_another_city_with_the_field_is_not_measured(corpus) -> None:
    # Cornelius holds the same field; its rear-line definition is unread here.
    rules = corpus.resolve("or/washington/cornelius", "R-7", ())
    assert rules.get(FIELD) is True
    lot = slanted_lot("or/washington/cornelius", zone="R-7", neighbour="R-7")
    assert not _rear_court_short(lot, rules, None, 0.0)


def test_rear_court_short_is_held_never_green() -> None:
    rules = screen_rules()
    design = pod()
    fit = Fit(
        fits=True,
        width_ft=56,
        depth_ft=36,
        best_depth_ft=120,
        slack_ft=84,
        across_ft=100,
        stalls=6,
    )
    held = screen(
        rules,
        LotFacts(
            lot_sqft=20_000,
            frontage_ft=100,
            lot_width_ft=100,
            lot_depth_ft=200,
            rear_court_short=True,
        ),
        design,
        fit,
        policy=SlackPolicy(tolerance={"fit_ft": 0.5}),
    )
    # Held: the colour rules show an unsettled lot as yellow.
    assert held.triage is Triage.unknown
    assert REAR_COURT_SHORT in held.reasons
    assert any(f.code == "PARKING-REAR-COURT-SHORT" for f in held.flags)


# --- The court the lot page shows has the last word ---


def _screened_for(lot: QuadfitLot, rules, *, court, facts: LotFacts):
    design = pod()
    fit = Fit(
        fits=True,
        width_ft=56,
        depth_ft=36,
        best_depth_ft=120,
        slack_ft=84,
        across_ft=100,
        stalls=6,
    )
    policy = SlackPolicy(tolerance={"fit_ft": 0.5})
    first = screen(rules, facts, design, fit, policy=policy)
    return Screened(
        lot=lot,
        design=design,
        rules=rules,
        config=None,
        fit=fit,
        screening=first,
        signed=first,
        angles=1,
        step_deg=5.0,
        envelope=None,
        front_deg=0.0,
        drawing=None if court is None else {"court": [list(c) for c in court.exterior.coords]},
        facts=facts,
    ), policy


GOOD_FACTS = dict(lot_sqft=20_000, frontage_ft=100, lot_width_ft=100, lot_depth_ft=200)


def test_the_final_drawing_takes_a_short_troutdale_court_out_of_green() -> None:
    rules = screen_rules()
    lot = slanted_lot(TROUTDALE)
    facts = LotFacts(**GOOD_FACTS, parking_setback_doubt_checked=True)
    s, policy = _screened_for(lot, rules, court=far_line_court(lot, 17.2), facts=facts)
    assert s.screening.triage is Triage.green
    out = rear_court_checked(s, policy=policy, relief=None)
    assert out.screening.triage is Triage.yellow
    assert PARKING_SETBACK_DOUBT in out.screening.reasons


def test_the_final_drawing_lifts_a_troutdale_hold_set_on_the_earlier_drawing() -> None:
    """1N3E25CC  -02500 80x25: the search's drawing stood 11.4 ft off the rear, the
    court the lot page shows clears every line. Finding 3."""
    rules = screen_rules()
    lot = drawn_lot(TROUTDALE, "LDR-1", "LDR-2")
    facts = LotFacts(
        **GOOD_FACTS,
        parking_setback_doubt_checked=True,
        parking_setback_doubt_failed=True,
    )
    s, policy = _screened_for(lot, rules, court=drawn_court(side=7.5, rear=20).court, facts=facts)
    assert s.screening.triage is Triage.yellow
    out = rear_court_checked(s, policy=policy, relief=None)
    assert out.screening.triage is Triage.green
    assert PARKING_SETBACK_DOUBT not in out.screening.reasons


def test_a_hold_stays_where_the_final_drawing_is_short_too() -> None:
    rules = screen_rules()
    lot = drawn_lot(TROUTDALE, "LDR-1", "LDR-2")
    facts = LotFacts(
        **GOOD_FACTS,
        parking_setback_doubt_checked=True,
        parking_setback_doubt_failed=True,
    )
    s, policy = _screened_for(lot, rules, court=drawn_court(side=7.5, rear=16).court, facts=facts)
    assert rear_court_checked(s, policy=policy, relief=None) is s


def test_no_drawing_keeps_the_hold() -> None:
    rules = screen_rules()
    lot = drawn_lot(TROUTDALE, "LDR-1", "LDR-2")
    facts = LotFacts(
        **GOOD_FACTS,
        parking_setback_doubt_checked=True,
        parking_setback_doubt_failed=True,
    )
    s, policy = _screened_for(lot, rules, court=None, facts=facts)
    out = rear_court_checked(s, policy=policy, relief=None)
    assert out.screening.triage is not Triage.green
    assert out.facts.parking_setback_doubt_failed


def test_a_strip_the_second_reading_waived_is_not_lifted(corpus) -> None:
    rules = corpus.resolve(SANDY, "R-2", ("abuts_lower_density_zone",))
    lot = dataclasses.replace(
        drawn_lot(SANDY, "R-2", "R-2"),
        facts=LotFacts(lot_sqft=20_000, strip_waived=True),
    )
    facts = LotFacts(**GOOD_FACTS, strip_waived=True)
    s, policy = _screened_for(lot, rules, court=drawn_court(side=30, rear=30).court, facts=facts)
    out = rear_court_checked(s, policy=policy, relief=None)
    assert out.facts.strip_waived


def test_a_strip_set_on_the_earlier_drawing_lifts_where_the_court_clears(corpus) -> None:
    rules = corpus.resolve(SANDY, "R-2", ("abuts_lower_density_zone",))
    lot = drawn_lot(SANDY, "R-2", "R-2")
    facts = LotFacts(**GOOD_FACTS, strip_waived=True)
    s, policy = _screened_for(lot, rules, court=drawn_court(side=30, rear=30).court, facts=facts)
    assert not rear_court_checked(s, policy=policy, relief=None).facts.strip_waived


# --- Fix 2: the court stays out of the printed yard, not the wall's distance ---


@pytest.mark.parametrize(
    ("zone", "wall", "printed"),
    [
        ("LDR-5", 20, 15),
        ("LDR-7", 20, 15),
        ("TR", 20, 15),
        ("LDR-SW", 20, 15),
        ("LDR-PV", 15, 10),
        ("VLDR-SW", 25, 20),
    ],
)
def test_gresham_court_stays_out_of_the_printed_yard(corpus, zone, wall, printed) -> None:
    """7.0420(G)(1) moves the 26 ft wall; the yard (B)(5)(c) keeps parking out of
    is what the table prints. 1S3E05CC  -00400 read 1.0 ft short at 20, fits at 15."""
    rules = corpus.resolve(GRESHAM, zone, ())
    assert rules.get("setback_rear_ft") == wall
    assert rules.values["setback_rear_ft"].before_step_back == printed
    court = _court_beyond_rear(pod(), Sharing(rules), carved_rear_ft=0.0)
    assert behind_wall_ft(court, wall, rules) == court + printed


def test_a_zone_outside_the_plane_keeps_its_printed_yard(corpus) -> None:
    # TLDR is the one LDR-family zone 7.0420(G)(1) leaves off the list: 15 is its wall too.
    rules = corpus.resolve(GRESHAM, "TLDR", ())
    assert rules.get("setback_rear_ft") == 15
    assert behind_wall_ft(47.5, 15, rules) == 62.5


def test_the_wall_still_stands_the_whole_setback(corpus) -> None:
    # A court shallower than the plane's extra depth does not bring the wall forward.
    rules = corpus.resolve(GRESHAM, "LDR-5", ())
    assert behind_wall_ft(0.0, 20, rules) == 20


def test_an_alley_lot_shares_as_before(corpus) -> None:
    rules = corpus.resolve(GRESHAM, "LDR-5", ("alley_at_rear", "abuts_alley"))
    rear = float(rules.get("setback_rear_ft"))
    assert rules.values["setback_rear_ft"].before_step_back == 8
    assert behind_wall_ft(47.5, rear, rules) == 47.5


def test_every_reason_here_is_said_in_words() -> None:
    from app.api.routers.ui_flats import _REASON_WORDS

    assert PARKING_SETBACK_DOUBT in _REASON_WORDS
    assert REAR_COURT_SHORT in _REASON_WORDS
