"""The main entrance within 4 feet of grade (FOLLOWUPS 64 round 5, fg5 F3).

PCC 33.110.230.D and 33.120.231.D: "The main entrance that meets
Subsection C must be within 4 feet of grade. For the purposes of this
Subsection, grade is the average grade measured at the outer most corners of
the street facing façade." Measured in the foundation pass on the floor the
six-step cap stands the building at (:mod:`flats.ingest.entrance_grade`,
:func:`flats.ingest.foundation_cap.entrance_of`): RED over the limit by more
than the ground model's error with every exemption ruled out, YELLOW within
the error or where an exemption is not read, never GREEN over the limit.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from flats.ingest import entrance_grade as eg
from flats.ingest import foundation_cap as fc

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "flats/provenance/docs"
RULES = eg.load()
R110, MULT, R120 = RULES.rules
STREET = ((0.0, 0.0, 300.0, 0.0),)


def _lines(ref: str) -> list[str]:
    path, _, span = ref.partition("#")
    text = (DOCS / path).read_text(encoding="utf-8").splitlines()
    out = []
    for part in span.split(","):
        a, _, b = part.lstrip("L").partition("-L")
        out += [" ".join(t.split()) for t in text[int(a) - 1:int(b or a)]]
    return out


# --- the rules hold the code's own words ----------------------------------------------


@pytest.mark.parametrize("rule", RULES.rules, ids=lambda r: r.section)
def test_each_rule_quotes_the_four_feet_and_its_exemptions(rule: eg.Rule) -> None:
    said = " ".join(_lines(rule.quote))
    assert "within 4 feet of" in said and rule.max_in == 48.0
    assert rule.says.split(" must ")[0] in said
    held = " ".join(_lines(rule.exemptions))
    assert "flag lots" in held and "20 percent" in held and "flood hazard area" in held


def test_grade_is_the_average_at_the_street_facing_corners() -> None:
    for ref in ("or/multnomah/portland/33.110/33.110.230.txt#L34",
                "or/multnomah/portland/33.120/33.120.231.txt#L45"):
        assert "average grade measured at the outer most corners of the street facing" in _lines(ref)[0]


# --- which zones carry the limit ---------------------------------------------------


def _resolution(value: str, quote: str) -> SimpleNamespace:
    v = SimpleNamespace(value=value, prov=SimpleNamespace(quote=quote))
    return SimpleNamespace(get=lambda name: value if name == "entrance_faces_street" else None,
                           values={"entrance_faces_street": v})


def test_rule_for_follows_the_entrance_rules_own_section() -> None:
    assert eg.rule_for(_resolution("required", "or/multnomah/portland/33.110/33.110.230.txt#L8-L17,L20-L34")) is R110
    assert eg.rule_for(_resolution("required", "or/multnomah/portland/33.120/33.120.231.txt#L8-L14,L18-L42")) is R120
    assert eg.rule_for(_resolution("required", "or/multnomah/_unincorporated/33.110.txt#L768-L769,L781-L812")) is MULT
    # Portland's commercial zones' entrance section holds no grade limit.
    assert eg.rule_for(_resolution("required", "or/multnomah/portland/33.130/33.130.250.txt#L11-L14")) is None
    # Not required (R20): no limit.
    assert eg.rule_for(_resolution("not_required", "or/multnomah/portland/33.110/33.110.230.txt#L8")) is None
    assert eg.rule_for(_resolution("required", "or/multnomah/gresham/7/7.0420.txt#L1-L15")) is None


# --- the exemptions are read conservatively -----------------------------------------


def test_exemptions_rule_out_only_what_is_read() -> None:
    clear = {"pdx_flag_lot": False, "in_floodplain": False}
    assert eg.exemption(clear, ()) is None
    assert eg.exemption(clear, ("pdx_flood_1996",)) == "exempt"
    assert eg.exemption({**clear, "in_floodplain": True}, ()) == "exempt"
    assert eg.exemption({"in_floodplain": False}, ()) == "unread"  # flag lot unread
    assert eg.exemption({"pdx_flag_lot": False}, ()) == "unread"  # flood unread


@pytest.mark.parametrize(("pct", "want"), [(None, "unread"), (10.0, None), (18.0, None), (19.0, "unread"),
                                           (21.9, "unread"), (22.0, "exempt"), (35.0, "exempt")])
def test_the_slope_exemption_holds_its_error_band(pct, want) -> None:
    assert eg.slope_state(pct) == want


class _Plane:
    """A fake elevation model: ground rising ``rise`` ft per ft north."""

    def __init__(self, rise: float) -> None:
        self.rise = rise

    def z_reader(self, ring, *, coarse: bool = False):
        return (lambda pts: 100.0 + self.rise * np.asarray(pts, dtype=float).reshape(-1, 2)[:, 1]), "dem_1m", 1.0


def test_lot_slope_reads_the_plane_from_the_street() -> None:
    import shapely

    lot = shapely.box(0, 0, 100, 150)
    assert eg.lot_slope_pct(_Plane(0.12), lot, (0.0, 1.0)) == pytest.approx(12.0, abs=0.01)
    # Read along the street it is flat.
    assert eg.lot_slope_pct(_Plane(0.12), lot, (1.0, 0.0)) == pytest.approx(0.0, abs=0.01)
    assert eg.lot_slope_pct(None, lot, (0.0, 1.0)) is None


# --- the measure -------------------------------------------------------------------


def _facts(ground, *, floor=4.5, per_home=True, exempt=None, slope=10.0, floors=None):
    return eg.entrance_facts(
        ground, length_ft=80.0, homes=4, per_home=per_home, facade_y=0.0,
        floors=floors or [("A", floor)], rule=R110, near_in=2.0, exempt=exempt, slope_of=lambda: slope,
    )


def test_within_four_feet_fits() -> None:
    got = _facts(lambda x, y: 0.0, floor=3.9)
    assert got["state"] == eg.FITS and got["height_in"] == pytest.approx(46.8)


def test_over_by_more_than_the_error_with_nothing_exempt_is_over() -> None:
    got = _facts(lambda x, y: 0.0, floor=4.5)
    assert got["state"] == eg.OVER and got["over_by_in"] == pytest.approx(6.0)
    assert "PCC 33.110.230.D" in got["words"] and "10.0 percent" in got["words"]


def test_within_the_error_is_held() -> None:
    assert _facts(lambda x, y: 0.0, floor=4.15)["state"] == eg.HELD


@pytest.mark.parametrize(("exempt", "slope", "want"), [
    ("exempt", 10.0, eg.EXEMPT), (None, 25.0, eg.EXEMPT), ("unread", 10.0, eg.HELD), (None, 20.0, eg.HELD),
    (None, None, eg.HELD),
])
def test_an_exemption_exempts_and_an_unread_one_holds(exempt, slope, want) -> None:
    assert _facts(lambda x, y: 0.0, floor=5.0, exempt=exempt, slope=slope)["state"] == want


def test_each_home_is_measured_on_its_own_corners() -> None:
    # The street-facing wall falls 4 ft along its 80 ft: the end home's
    # corners average 3.5 ft below the building's high end, the building's
    # two ends 2 ft.
    ground = lambda x, y: -4.0 * x / 80.0  # noqa: E731
    home = _facts(ground, floor=1.0, per_home=True)
    whole = _facts(ground, floor=1.0, per_home=False)
    assert home["home"] == 4 and home["height_in"] == pytest.approx(54.0) and home["state"] == eg.OVER
    assert whole["home"] is None and whole["height_in"] == pytest.approx(36.0) and whole["state"] == eg.FITS


def test_an_unread_ground_class_holds_what_only_the_higher_floor_passes() -> None:
    got = _facts(lambda x, y: 0.0, floors=[("A", 3.8), ("B", 4.6)])
    assert got["state"] == eg.HELD and got["method"] == "B" and got["screened_in"] == pytest.approx(45.6)
    assert "ground class is not read" in got["words"]


def test_the_slope_is_read_only_past_the_limit() -> None:
    def boom():
        raise AssertionError("slope read on a lot within the limit")

    got = eg.entrance_facts(lambda x, y: 0.0, length_ft=80.0, homes=4, per_home=True, facade_y=0.0,
                            floors=[("A", 3.0)], rule=R110, near_in=2.0, exempt=None, slope_of=boom)
    assert got["state"] == eg.FITS


# --- in the screen ---------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    fc._CACHE.clear()
    monkeypatch.setattr(fc, "dem_of", lambda terrain: terrain)
    yield
    fc._CACHE.clear()


def _green(tlid: str, zone: str, jurisdiction: str, observed: dict | None = None):
    from flats.score.screen import Triage
    from flats.tests.test_historic_lists import _screened

    s = _screened(tlid, zone=zone, jurisdiction=jurisdiction)
    clean = dataclasses.replace(s.signed, triage=Triage.green, binds=(), flags=(), reasons=())
    lot = dataclasses.replace(s.lot, observed={**s.lot.observed, **(observed or {})})
    return dataclasses.replace(s, signed=clean, screening=clean, lot=lot)


@pytest.fixture(scope="module")
def portland():
    return _green("1N1E22CC  -99999", "R5", "portland", {"pdx_flag_lot": False, "in_floodplain": False})


def _checked(s, rise: float, classes=("FIRM", None)):
    import shapely

    return fc.checked(s, terrain=_Plane(rise), streets=lambda: STREET, lot_geom=shapely.box(0, 0, 300, 300),
                      classes=classes, tlid=s.lot.tlid)



def test_portland_flat_ground_carries_the_measure_and_stays_green(portland) -> None:
    from flats.score.flags import Colour

    assert fc.entrance_for(portland)[0] is R110
    out = _checked(portland, 0.0)
    ent = out.foundation["entrance"]
    assert ent["state"] == eg.FITS and ent["section"] == "PCC 33.110.230.D"
    assert out.signed.colour is Colour.green


def test_ground_rising_from_the_street_stays_under_four_feet_before_the_cap(portland) -> None:
    """On ordinary ground rising from the street the six-step cap, tested at
    the foot of the steps out from the wall, binds before the entrance does
    at the wall's corners: the measure rises with the ground and stays
    within 4 ft while the cap still passes."""
    last = -1.0
    for rise in (0.02, 0.04, 0.05):
        fc._CACHE.clear()
        out = _checked(portland, rise)
        ent = out.foundation["entrance"]
        assert out.foundation["state"] in ("fits", "close_under_cap")
        assert ent["state"] == eg.FITS and ent["height_in"] > last
        last = ent["height_in"]


def _lower(monkeypatch, max_in: float) -> None:
    """The 4 ft limit set to ``max_in`` on the real measure, so the drawn
    building on a gentle plane reaches it before the cap."""
    real = fc.entrance_for

    def lowered(s):
        got = real(s)
        return None if got is None else (dataclasses.replace(got[0], max_in=max_in), got[1], got[2])

    monkeypatch.setattr(fc, "entrance_for", lowered)


@pytest.mark.parametrize(("rise", "want"), [(0.04, eg.FITS), (0.043, eg.HELD), (0.05, eg.OVER)])
def test_over_the_limit_is_red_and_within_the_error_yellow(portland, monkeypatch, rise, want) -> None:
    from flats.score.flags import Colour

    _lower(monkeypatch, 30.0)
    out = _checked(portland, rise)
    ent = out.foundation["entrance"]
    assert ent["state"] == want, ent
    colour = {eg.FITS: Colour.green, eg.HELD: Colour.yellow, eg.OVER: Colour.red}[want]
    assert out.signed.colour is colour and out.screening.colour is colour
    if want == eg.OVER:
        assert fc.ENTRANCE_GRADE in out.signed.reasons
        bind = next(b for b in out.signed.binds if b.check == fc.ENTRANCE_CHECK)
        assert bind.threshold == 30.0 and "33.110.230.txt#L33-L34" in bind.source
        assert ent["slope_pct"] is not None and ent["slope_pct"] < 18
        again = fc._apply(out.signed, out.foundation)
        assert again.binds == out.signed.binds and again.reasons == out.signed.reasons
    if want == eg.HELD:
        assert [f.code for f in out.signed.flags] == [fc.ENTRANCE_HELD_FLAG]
        assert fc.ENTRANCE_HELD in out.signed.reasons


def test_an_unread_flag_lot_holds_yellow_never_red(monkeypatch) -> None:
    from flats.score.flags import Colour

    s = _green("1N1E22CC  -99998", "R5", "portland", {"in_floodplain": False})
    s = dataclasses.replace(s, lot=dataclasses.replace(s.lot, observed={
        k: v for k, v in s.lot.observed.items() if k != "pdx_flag_lot"}))
    _lower(monkeypatch, 30.0)
    out = _checked(s, 0.05)
    assert out.foundation["entrance"]["state"] == eg.HELD
    assert out.signed.colour is Colour.yellow and fc.ENTRANCE_GRADE not in out.signed.reasons


def test_a_zone_with_no_grade_limit_is_not_measured() -> None:
    s = _green("1S3E10BC  -99999", "R-5", "gresham")
    assert fc.entrance_for(s) is None
    assert "entrance" not in _checked(s, 0.1).foundation


def test_the_held_flag_and_reasons_are_registered() -> None:
    from flats.score import flags as flag_plan

    reg = flag_plan.registry()
    assert fc.ENTRANCE_HELD_FLAG in reg
    assert flag_plan.severity_of(flag_plan.Flag(fc.ENTRANCE_HELD_FLAG, flag_plan.LOT, fc.ENTRANCE_HELD), reg) \
        >= flag_plan.colour_rules().yellow_at_severity
    assert {fc.ENTRANCE_GRADE, fc.ENTRANCE_HELD} <= set(fc.REASONS)
