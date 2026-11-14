"""Portland's 9 ft drive (rulings.yaml ``2026-11-10-portland-driveway-9ft``).

Steph 2026-11-10, "9ft in Portland": the lane down the building's flank to
the rear court may be as narrow as Portland's printed minimum,
33.266.120.D.2's "The minimum driveway width on private property is 9 feet",
wherever the code allows it for this building; elsewhere the plan's 12 ft
stands. 33.266.120.B is a test on the structure (houses through fourplexes,
"all parking areas"), so it reaches the pod in every Portland zone, and the
Portland-administered pockets that take Portland's parking rulings (R5, R7,
R10, R20) carry it too.

Held as ``driveway_lane_narrow_ft`` 9: the narrowest lane the screen may
TRY. The pod's 12 ft lane is screened first; a lot it misses is screened
again with the drive at 9, or at the narrowest whole foot above 9 from
which the screen's car can use every stall (the turning ledger), and the
better colour kept (:func:`flats.ingest.quadfit.narrow_lane_checked`). A
narrow drive costs the court a deeper aisle (9 ft: the 20 ft aisle 12 ft
deeper), so it never replaces a lane that already works.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("shapely")

import shapely  # noqa: E402
from shapely.geometry import box  # noqa: E402

from flats.designs.model import load_catalog  # noqa: E402
from flats.encode.load import load_trusted  # noqa: E402
from flats.ingest import quadfit  # noqa: E402
from flats.ingest.quadfit import lot_from_row, screen_lot, townhouse  # noqa: E402
from flats.provenance.store import ProvenanceStore  # noqa: E402
from flats.score import relief, slack  # noqa: E402
from flats.score.flags import Colour  # noqa: E402
from flats.score.paper import court_across, narrow_lane_rules  # noqa: E402
from flats.score.turns import fixes  # noqa: E402

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
COUNTY = "or/multnomah/_unincorporated"
POCKETS = ("R5", "R7", "R10", "R20")
SENTENCE = "The minimum driveway width on private property is 9 feet."
DESIGNS = load_catalog().active()
POD = load_catalog().latest("pod80x30")
SIDE_DOOR = "ENTRANCE-SIDE-DOOR"


@pytest.fixture(autouse=True)
def _courts_from_the_ledger(monkeypatch) -> None:
    """The real turning ledger, not conftest's as-drawn court: the ladder
    and the 9 ft fits turn on the room a car needs on the real corpus."""
    from flats.score import paper, turns

    monkeypatch.setattr(paper, "fixes", turns.fixes)


@pytest.fixture(scope="module")
def trusted():
    return load_trusted(strict=False)


@pytest.fixture(scope="module")
def corpus(trusted):
    return trusted.rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def _quoted(quote: str) -> str:
    doc, _, spans = quote.partition("#")
    lines = ProvenanceStore().load(doc).text.splitlines()
    out: list[str] = []
    for span in spans.split(","):
        a, _, b = span.lstrip("L").partition("-L")
        out += lines[int(a) - 1 : int(b or a)]
    return " ".join(" ".join(out).split())


# --- the encoding -------------------------------------------------------------------


def test_every_portland_zone_may_try_the_nine_foot_drive(corpus) -> None:
    layer = corpus.layers[PORTLAND]
    held = layer.defaults["driveway_lane_narrow_ft"]
    assert held.value == 9
    assert "2026-11-10" in held.prov.cite
    assert SENTENCE in _quoted(held.prov.quote)
    for zone in layer.zones:
        got = corpus.resolve(PORTLAND, zone)
        assert got.get("driveway_lane_narrow_ft") == 9, zone
        # Not the lane: the first reading still draws the pod's own.
        assert got.get("driveway_one_lane_ft") is None, zone
        for design in DESIGNS:
            assert court_across(design, got, turning=False).lane_ft in (0.0, 12.0), zone


@pytest.mark.parametrize("zone", POCKETS)
def test_the_portland_administered_pockets_take_it(corpus, zone: str) -> None:
    held = corpus.layers[COUNTY].zones[zone].values["driveway_lane_narrow_ft"]
    assert held.value == 9
    assert "2026-11-10" in held.prov.cite
    assert SENTENCE in _quoted(held.prov.quote)
    narrow = narrow_lane_rules(POD, corpus.resolve(COUNTY, zone))
    assert narrow is not None
    assert court_across(POD, narrow).lane_ft == 9


def test_nowhere_else_holds_a_narrow_drive(corpus) -> None:
    """Elsewhere the plan's 12 ft stands -- RF included, which takes Title
    33's card but not Steph's Portland parking rulings (2026-11-09 scoped
    them to R5-R20)."""
    for layer_id, layer in corpus.layers.items():
        here = "driveway_lane_narrow_ft" in layer.defaults
        assert here == (layer_id == PORTLAND), layer_id
        for name, zone in layer.zones.items():
            if "driveway_lane_narrow_ft" in zone.values:
                assert layer_id == COUNTY and name in POCKETS, (layer_id, name)
    assert narrow_lane_rules(POD, corpus.resolve(COUNTY, "RF")) is None


# --- the narrow reading -------------------------------------------------------------


def test_the_nine_foot_court_is_driven_with_a_deeper_aisle(corpus) -> None:
    narrow = narrow_lane_rules(POD, corpus.resolve(PORTLAND, "R5"))
    assert narrow is not None and narrow.get("driveway_one_lane_ft") == 9
    across = court_across(POD, narrow)
    shape = across.turn_shape
    assert shape is not None and (shape.lane_ft, shape.aisle_ft) == (9, 20)
    # The court's own aisle is not the drive: it is never narrowed, and the
    # car needs it deeper to use every stall from a 9 ft lane.
    assert across.turns is True
    assert all(f.aisle_ft >= 12 for f in fixes(shape))
    assert "driveway_one_lane_ft" in across.from_code


def test_a_court_the_car_cannot_use_from_nine_feet_steps_the_drive_up(corpus) -> None:
    """EX's two-stall court cannot be used from a 9 ft lane at any fix the
    ledger asks: the drive is tried a whole foot wider, never left
    unusable and never wider than the pod's own lane."""
    got = corpus.resolve(PORTLAND, "EX")
    narrow = narrow_lane_rules(POD, got)
    if narrow is not None:
        lane = narrow.get("driveway_one_lane_ft")
        assert 9 < lane < 12
        assert court_across(POD, narrow).turns is not False


def test_the_unit_lot_form_keeps_the_pod_s_lane(corpus) -> None:
    """A parking tract goes to 33.266.130 (120.B.1), which prints no
    driveway width: the 9 is not this form's."""
    assert narrow_lane_rules(townhouse(POD), corpus.resolve(PORTLAND, "R5")) is None
    got = corpus.resolve(PORTLAND, "R5", ("unit_lots",))
    assert narrow_lane_rules(POD, got) is None


# --- the bridge ---------------------------------------------------------------------


def _screen(trusted, policies, jurisdiction: str, zone: str, wide: float, deep: float, *, narrow=True):
    from flats.tests.test_fire import X0, Y0, bridge_row

    edges = [
        [X0, Y0, X0 + wide, Y0, "F"],
        [X0 + wide, Y0, X0 + wide, Y0 + deep, "S"],
        [X0 + wide, Y0 + deep, X0, Y0 + deep, "R"],
        [X0, Y0 + deep, X0, Y0, "S"],
    ]
    row = bridge_row(
        TLID="1S2E20AA  -99154",
        jurisdiction=jurisdiction,
        zone=zone,
        has_z_overlay=False,
        area_sqft=wide * deep,
        lot_depth_ft=deep,
        frontage_ft=wide,
        lot_width_ft=wide,
        edges_json=json.dumps(edges),
        wkb=shapely.to_wkb(box(X0 + 5, Y0 + 10, X0 + wide - 5, Y0 + deep - 5)),
        lot_wkb=shapely.to_wkb(box(X0, Y0, X0 + wide, Y0 + deep)),
    )
    lot = lot_from_row(row, trusted.rules.layers)
    real = quadfit.narrow_lane_checked
    if not narrow:
        quadfit.narrow_lane_checked = lambda lot, designs, got, **kw: got
    try:
        (s,) = screen_lot(
            lot, [POD], rules=trusted.rules, policy=policies[0], relief=policies[1], step_deg=30.0
        )
    finally:
        quadfit.narrow_lane_checked = real
    return s


def _codes(s) -> set[str]:
    return {f.code for f in s.signed.flags}


@pytest.mark.parametrize("jurisdiction", ["portland", "multnomah_unincorporated"])
def test_a_lot_that_faces_the_street_only_on_the_nine_foot_drive_is_green(
    trusted, policies, jurisdiction: str
) -> None:
    """95 x 110 in R5, 2 ft short of facing the street on the 12 ft lane --
    the kind false-green round 4 found (1N2E21BA  -12200, 1S2E15AD  -08900):
    the 12 ft lane fits the pod only turned sideways, YELLOW for its doors;
    the 9 ft drive fits it facing the street, and nothing else fails."""
    wide = _screen(trusted, policies, jurisdiction, "R5", 95.0, 110.0, narrow=False)
    assert wide.signed.colour is Colour.yellow
    assert SIDE_DOOR in _codes(wide)
    s = _screen(trusted, policies, jurisdiction, "R5", 95.0, 110.0)
    assert s.signed.colour is Colour.green
    assert SIDE_DOOR not in _codes(s)
    assert s.rules.get("driveway_one_lane_ft") == 9


def test_a_lot_the_pod_s_lane_already_fits_keeps_it(trusted, policies) -> None:
    s = _screen(trusted, policies, "portland", "R5", 97.0, 110.0)
    assert s.signed.colour is Colour.green
    assert s.rules.get("driveway_one_lane_ft") is None


def test_outside_portland_the_twelve_foot_lane_stands(trusted, policies) -> None:
    for narrow in (True, False):
        s = _screen(trusted, policies, "gresham", "LDR-5", 95.0, 110.0, narrow=narrow)
        assert s.rules.get("driveway_one_lane_ft") is None
        assert s.rules.get("driveway_lane_narrow_ft") is None
    a = _screen(trusted, policies, "gresham", "LDR-5", 95.0, 110.0)
    b = _screen(trusted, policies, "gresham", "LDR-5", 95.0, 110.0, narrow=False)
    assert a.signed.colour is b.signed.colour
    assert a.screening.fit_slack_ft == b.screening.fit_slack_ft
