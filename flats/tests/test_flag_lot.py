"""Portland's flag lots are held out of GREEN (FOLLOWUPS 205).

PCC 33.110.255 gives a flag lot the same setback along every lot line (15 ft
in RF, R20 and R10; 10 ft in R7, R5 and R2.5), a landscaped buffer round the
flag and coverage on the flag alone; 33.120.284 gives RM1 to RM4 flag lots
10 ft and a buffer. Nothing measured the fact and no zone held the standards,
so a flag lot was certified on the ordinary five-foot side and rear yards. The lot's shape is
now read as far as "plainly not a flag lot" (:mod:`flats.geom.flag_lot`);
any other lot of those zones is held on the fact by name.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("shapely")

import shapely  # noqa: E402
from shapely.geometry import Polygon, box  # noqa: E402

from flats.designs.model import load_catalog  # noqa: E402
from flats.encode.load import load_trusted  # noqa: E402
from flats.geom import flag_lot  # noqa: E402
from flats.geom.flag_lot import FACT, load_rules, observed_flag_lot  # noqa: E402
from flats.ingest import quadfit  # noqa: E402
from flats.ingest.quadfit import lot_from_row, observed_facts, screen_lot  # noqa: E402
from flats.provenance.store import ProvenanceStore  # noqa: E402
from flats.score import flags as flag_plan  # noqa: E402
from flats.score import relief, slack  # noqa: E402
from flats.score.flags import Colour  # noqa: E402

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
COUNTY = "or/multnomah/_unincorporated"
SINGLE = ("RF", "R20", "R10", "R7", "R5", "R2.5")
MULTI = ("RM1", "RM2", "RM3", "RM4")
POCKETS = ("RF", "R20", "R10", "R7", "R5")
POD = load_catalog().latest("pod80x30")
FLAG = "FACT-PDX-FLAG-LOT"


def ring(points: list[tuple[float, float]], street: set[int]) -> list[list[object]]:
    """A lot's edges from its corners in order; ``street`` names the edges on a street."""
    out: list[list[object]] = []
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        out.append([x1, y1, x2, y2, "F" if i in street else "S"])
    return out


def rectangle(wide: float, deep: float) -> list[list[object]]:
    return ring([(0, 0), (wide, 0), (wide, deep), (0, deep)], {0})


def flag_shape(pole: float, pole_len: float, wide: float, deep: float) -> list[tuple[float, float]]:
    """A flag ``wide`` by ``deep`` behind a pole down its left side."""
    return [
        (0, 0), (pole, 0), (pole, pole_len), (wide, pole_len),
        (wide, pole_len + deep), (0, pole_len + deep),
    ]


def _lines(quote: str) -> str:
    doc, _, spans = quote.partition("#")
    lines = ProvenanceStore().load(doc).text.splitlines()
    out: list[str] = []
    for span in spans.split(","):
        a, _, b = span.lstrip("L").partition("-L")
        out += lines[int(a) - 1 : int(b or a)]
    return " ".join(" ".join(out).split())


# --- the shape ----------------------------------------------------------------------


def test_an_ordinary_lot_is_plainly_not_a_flag_lot() -> None:
    assert observed_flag_lot(rectangle(50, 100), PORTLAND, "R5") == {FACT: False}
    assert observed_flag_lot(rectangle(97, 110), COUNTY, "R5") == {FACT: False}


def test_a_flag_lot_is_left_unanswered_never_answered_true() -> None:
    """A 15 ft pole 100 ft long to a 60 by 80 flag: no part 36 ft wide comes
    near the street, and the front lot's ground is missing from the outline."""
    edges = ring(flag_shape(15, 100, 60, 80), {0})
    assert observed_flag_lot(edges, PORTLAND, "R5") == {}
    # A 30 ft neck is still under R5's 36 ft, and under R10's 50.
    wide_pole = ring(flag_shape(30, 60, 100, 110), {0})
    assert observed_flag_lot(wide_pole, PORTLAND, "R5") == {}
    assert observed_flag_lot(wide_pole, PORTLAND, "R10") == {}
    # ... but it is a lot at least 25 ft wide at the street, R2.5's width.
    assert observed_flag_lot(wide_pole, PORTLAND, "R2.5") == {FACT: False}


def test_the_wide_part_must_reach_the_street() -> None:
    rules = load_rules()[PORTLAND]
    lot = Polygon(flag_shape(30, 60, 100, 110))
    street = flag_lot.street_lines(ring(flag_shape(30, 60, 100, 110), {0}))
    assert not flag_lot.wide_at_street(lot, street, 35.5, rules.reach_ft)
    # Within 10 ft of the street the neck is no pole: nothing stands in front.
    short = Polygon(flag_shape(30, 9, 100, 110))
    assert flag_lot.wide_at_street(short, street, 35.5, rules.reach_ft)
    assert flag_lot.wide_at_street(Polygon(flag_shape(36, 60, 100, 110)), street, 35.5, rules.reach_ft)


def test_a_wedge_on_a_cul_de_sac_is_an_ordinary_lot() -> None:
    """30 ft at the street widening to 90: under R7's 40 ft at the street, but
    convex -- there is no ground in front of it for another lot."""
    wedge = ring([(30, 0), (60, 0), (90, 110), (0, 110)], {0})
    assert flag_lot.notch_sqft(flag_lot.outline(wedge)) == pytest.approx(0.0)
    assert observed_flag_lot(wedge, PORTLAND, "R7") == {FACT: False}
    # A narrow lot of one width has no pole either.
    assert observed_flag_lot(rectangle(30, 100), PORTLAND, "R5") == {FACT: False}


def test_what_the_shape_cannot_settle_is_unanswered() -> None:
    # No street line, a ring that does not close, a zone or a city not listed.
    assert observed_flag_lot(ring([(0, 0), (50, 0), (50, 100), (0, 100)], set()), PORTLAND, "R5") == {}
    assert observed_flag_lot(rectangle(50, 100)[:3], PORTLAND, "R5") == {}
    assert observed_flag_lot(rectangle(50, 100), PORTLAND, "CM2") == {}
    assert observed_flag_lot(rectangle(50, 100), "or/multnomah/gresham", "R5") == {}
    assert observed_flag_lot(rectangle(50, 100), COUNTY, "LR7") == {}


# --- the code's figures -------------------------------------------------------------


def test_the_pole_widths_are_the_code_s_minimum_lot_widths() -> None:
    import yaml

    raw = yaml.safe_load(flag_lot.CONFIG_PATH.read_text(encoding="utf-8"))["jurisdictions"]
    city = raw[PORTLAND]
    assert "at any point is less than the minimum lot width for the zone" in _lines(city["definition"]["quote"])
    single, multi, campus = city["min_lot_width_ft"]
    assert campus["zones"] == {"CI1": 33}
    assert "CI1 zone are subject to the development standards that apply in the RM1 zone" in _lines(campus["via"])
    assert single["zones"] == {"RF": 60, "R20": 60, "R10": 50, "R7": 40, "R5": 36, "R2.5": 25}
    table = _lines(single["quote"])
    assert table.startswith("RF R20 R10 R7 R5 R2.5 Minimum Lot Width [3] Attached house lots [1] All other lots")
    assert table.endswith("NA 60 ft. 15 ft. 60 ft. 15 ft. 50 ft. 15 ft. 40 ft. 15 ft. 36 ft. 15 ft. 25 ft.")
    assert multi["zones"] == dict.fromkeys(MULTI, 33)
    assert "RM1 through RM4 Zones Lot 33 feet wide" in _lines(multi["quote"])
    pockets = raw[COUNTY]["min_lot_width_ft"]
    assert [b["zones"] for b in pockets] == [{z: single["zones"][z] for z in POCKETS}]
    assert load_rules()[PORTLAND].widths["R5"] == 36.0


@pytest.fixture(scope="module")
def trusted():
    return load_trusted(strict=False)


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


@pytest.mark.parametrize(
    ("layer", "zones", "says"),
    [
        (PORTLAND, SINGLE, ("RF, R20, R10 15 feet", "R7, R5, R2.5 10 feet", "at least 5 feet deep", "20 feet")),
        (PORTLAND, MULTI, ("RM1, RM2, RM3, RM4 10 feet", "at least 3 feet deep", "before July 1, 2002")),
        (COUNTY, POCKETS, ("RF, R20, R10 15 feet", "R7, R5, R2.5 10 feet", "at least 5 feet deep", "20 feet")),
    ],
)
def test_every_zone_with_flag_lot_standards_is_held_on_the_fact(trusted, layer, zones, says) -> None:
    for zone in zones:
        held = trusted.rules.layers[layer].zones[zone].values["setback_side_ft"]
        assert held.qualified_by == FACT, zone
        text = _lines(held.qualified_quote)
        for phrase in says:
            assert phrase in text, (zone, phrase)
        got = trusted.rules.resolve(layer, zone)
        assert FACT in got.unencoded, zone
        assert FACT in got.levers, zone


def test_the_shape_is_read_in_every_zone_the_hold_reaches_and_no_other(trusted) -> None:
    """A zone held on the fact with no reading of the shape would hold every
    lot in it. CI1 is held through RM1, whose standards its housing takes
    (33.150.200)."""
    for layer_id, layer in trusted.rules.layers.items():
        leaning = {z for z in layer.zones if FACT in trusted.rules.resolve(layer_id, z).levers}
        read = set(load_rules()[layer_id].widths) if layer_id in load_rules() else set()
        assert leaning == read, layer_id
    assert set(load_rules()[PORTLAND].widths) == set(SINGLE + MULTI) | {"CI1"}
    assert set(load_rules()[COUNTY].widths) == set(POCKETS)
    assert trusted.rules.resolve(PORTLAND, "CI1").borrowed_from == ("RM1",)


# --- the bridge ---------------------------------------------------------------------


def _row(jurisdiction: str, zone: str, points: list[tuple[float, float]], buildable) -> dict[str, object]:
    from flats.tests.test_fire import X0, Y0, bridge_row

    moved = [(X0 + x, Y0 + y) for x, y in points]
    lot = Polygon(moved)
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return bridge_row(
        TLID="1S2E20AA  -99205",
        jurisdiction=jurisdiction,
        zone=zone,
        has_z_overlay=False,
        area_sqft=lot.area,
        lot_depth_ft=max(ys) - min(ys),
        frontage_ft=moved[1][0] - moved[0][0],
        lot_width_ft=max(xs) - min(xs),
        edges_json=json.dumps(ring(moved, {0})),
        wkb=shapely.to_wkb(shapely.affinity.translate(buildable, X0, Y0)),
        lot_wkb=shapely.to_wkb(lot),
    )


def _screen(trusted, policies, row):
    (s,) = screen_lot(
        lot_from_row(row, trusted.rules.layers),
        [POD],
        rules=trusted.rules,
        policy=policies[0],
        relief=policies[1],
        step_deg=30.0,
    )
    return s


def _flag(s):
    return next((f for f in s.signed.flags if f.code == FLAG), None)


RECT = [(0.0, 0.0), (97.0, 0.0), (97.0, 110.0), (0.0, 110.0)]


@pytest.mark.parametrize("jurisdiction", ["portland", "multnomah_unincorporated"])
def test_an_ordinary_lot_keeps_its_green(trusted, policies, jurisdiction: str) -> None:
    row = _row(jurisdiction, "R5", RECT, box(5, 10, 92, 105))
    assert observed_facts(row, trusted.rules.layers)[FACT] is False
    s = _screen(trusted, policies, row)
    assert s.signed.colour is Colour.green
    assert _flag(s) is None


@pytest.mark.parametrize("jurisdiction", ["portland", "multnomah_unincorporated"])
def test_a_lot_not_shown_to_be_ordinary_is_held_by_name(
    trusted, policies, monkeypatch, jurisdiction: str
) -> None:
    """The same lot with the shape unread: the side yard turns on a fact
    nobody answered, and no worst reading is tried for it -- the buffer and
    the flag-only coverage are not numbers the screen holds."""
    monkeypatch.setattr(quadfit, "observed_flag_lot", lambda *a, **k: {})
    row = _row(jurisdiction, "R5", RECT, box(5, 10, 92, 105))
    assert FACT not in observed_facts(row, trusted.rules.layers)
    s = _screen(trusted, policies, row)
    assert s.signed.colour is Colour.yellow
    held = _flag(s)
    assert held is not None
    reg = flag_plan.registry()
    assert flag_plan.severity_of(held, reg) >= flag_plan.colour_rules().yellow_at_severity


def test_a_flag_lot_is_not_green(trusted, policies) -> None:
    """A 30 ft pole 60 ft long to a 100 by 110 flag in R5: the pod and its
    court stand on the flag with the ordinary yards to spare."""
    points = flag_shape(30, 60, 100, 110)
    row = _row("portland", "R5", points, box(5, 70, 95, 165))
    assert FACT not in observed_facts(row, trusted.rules.layers)
    s = _screen(trusted, policies, row)
    assert s.signed.colour is not Colour.green
    assert _flag(s) is not None
