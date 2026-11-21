"""A freeway, a ramp or a railroad is not a street a lot fronts.

Release 10's move read (2026-11-19) found three false GREENs: s4's
wide-road test counted a freeway or ramp centreline as a street's
(``1S1E31BB  -16100``, ``1S2E04AC  -09600``, Portland) and looked across a
railroad to the highway beyond it (``1S205CD03601``, Hillsboro). s4 now says
what the way across each street line is (``street_kind_json``: ``freeway``,
``limited``, ``rail``) and writes the lot without those lines
(``sans_drive_json["limited"]``); the bridge chooses the reading by the
lot's code (:func:`flats.ingest.quadfit.limited_reading`):

* Portland 33.910.030 says a street "does not include ... the interstate
  freeways and the Sunset Highway including their ramps": the lot is read
  without the line, and nothing is given back.
* Everywhere else -- and for a ramp of another road or a railroad anywhere
  -- the lot is screened both ways, the worse kept, and held YELLOW
  (``STREET_LINE_LIMITED_WAY``, flag ``ACCESS-LIMITED-WAY``). The stricter
  reading is the coordinator's default pending Steph.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
import shapely

from flats.encode.load import load_trusted
from flats.geom.edges import EdgeClass
from flats.ingest.quadfit import (
    LIMITED_KEY,
    LIMITED_STREET_KINDS,
    _limited_replaced,
    _shown,
    limited_reading,
    limited_way_side,
    lot_from_row,
    screen_lot,
)
from flats.rules.loader import _parse_freeways, load_rules
from flats.rules.resolver import RuleSet, Verdict
from flats.score import relief, slack
from flats.score.configure import configure
from flats.score.flags import Colour, colour_rules, load_registry
from flats.score.screen import STREET_LINE_LIMITED_WAY, Triage, screen
from flats.tests.test_center_cores import CORE, FAR, HILLSBORO, PLAIN
from flats.tests.test_quadfit_bridge import EDGES, X0, Y0, pod, row
from flats.tests.test_round2_rulings import DESIGN, facts, fit

pytestmark = pytest.mark.unit

FLAG = "ACCESS-LIMITED-WAY"
PORTLAND = "or/multnomah/portland"
REAL = json.loads((Path(__file__).parent / "fixtures" / "limited_way_lots.json").read_text())
FREEWAY_LOT = "1S2E04AC  -09600"
RAIL_LOT = "1S205CD03601"


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def real_row(tlid: str, **over: object) -> dict[str, object]:
    """The stage-file row of one real lot as s4 writes it on this branch."""
    fx = REAL[tlid]
    lot = shapely.from_wkt(fx["lot"])
    base = dict(
        TLID=tlid, jurisdiction=fx["jurisdiction"], zone=fx["zone"], tier=fx["tier"],
        area_sqft=fx["area_sqft"], frontage_ft=fx["frontage_ft"], lot_width_ft=None, lot_depth_ft=None,
        edges_json=json.dumps(fx["edges"]), front_bearings_json=json.dumps(fx["front_bearings"]),
        street_kind_json=json.dumps(fx["street_kinds"]), sans_drive_json=json.dumps(fx["sans"]),
        lot_wkb=shapely.to_wkb(lot), wkb=shapely.to_wkb(lot.buffer(-20)),
    )
    return row(**{**base, **over})


# The 50 x 100 lot of the bridge tests with its east side line read as a
# street line across to a freeway, and s4's reading of it without that line.
ON_FREEWAY = [[*e[:4], "F" if i == 1 else e[4]] for i, e in enumerate(EDGES)]


def _sans(tier: str = "A", edges: list | None = None) -> str:
    alt = {
        "tier": tier, "edges": EDGES if edges is None else edges, "front_bearings": [0.0],
        "frontage_ft": 50.0, "alley_cover": [None] * 4, "alley_width_ft": None,
        "lot_width_ft": 50.0, "lot_depth_ft": 100.0, "fronts_cul_de_sac": False,
        "neighbour_zones": None, "park_across": None,
    }
    return json.dumps({LIMITED_KEY: alt})


def beside(kind: str = "freeway", **over: object) -> dict[str, object]:
    base = dict(
        tier="B", frontage_ft=150.0, edges_json=json.dumps(ON_FREEWAY),
        front_bearings_json="[0.0, 90.0]",
        street_kind_json=json.dumps(["street", kind, None, None]),
        sans_drive_json=_sans(),
        lot_wkb=shapely.to_wkb(shapely.box(X0, Y0, X0 + 50, Y0 + 100)),
    )
    return row(**{**base, **over})


# --- what the code says ----------------------------------------------------------


def test_portland_says_a_freeway_is_not_a_street_and_no_other_layer_is_ruled(corpus) -> None:
    """``freeways.says`` is held verbatim by the line ``quote`` points at."""
    store = Path(__file__).resolve().parents[1] / "provenance" / "docs"
    ruled = {k: v.freeways for k, v in corpus.layers.items() if v.freeways is not None}
    assert set(ruled) == {PORTLAND}
    r = ruled[PORTLAND]
    assert r.street is False
    doc, _, line = r.quote.partition("#L")
    held = (store / doc).read_text(encoding="utf-8").split("\n")[int(line) - 1]
    assert " ".join(r.says.split()) in " ".join(held.split())
    assert "interstate freeways and the Sunset Highway including their ramps" in r.says


def test_the_loader_refuses_a_freeway_ruling_without_its_quote() -> None:
    base = {"street": False, "quote": "or/x/y.txt#L1", "says": "words", "note": "n" * 60}
    problems: list[str] = []
    assert _parse_freeways(base, where="t", problems=problems) is not None and not problems
    for bad in ({"street": "no"}, {"quote": "or/x/y.txt"}, {"says": ""}, {"note": "short"}, {"extra": 1}):
        problems = []
        assert _parse_freeways({**base, **bad}, where="t", problems=problems) is None
        assert problems
    assert _parse_freeways(None, where="t", problems=[]) is None


# --- which reading ---------------------------------------------------------------


def test_the_reading_follows_the_code_and_the_kind_of_way(corpus) -> None:
    layers = corpus.layers
    assert limited_reading(row(), layers) == (None, "")
    assert limited_reading(row(street_kind_json=json.dumps(["street", None, None, None])), layers) == (None, "")
    # Portland, its own freeways: the code's reading alone.
    how, side = limited_reading(beside("freeway"), layers)
    assert how == "replace" and side == "the east line (100 ft) faces a freeway or its ramp"
    # A ramp of another road, a railroad: Title 33's sentence names neither.
    assert limited_reading(beside("limited"), layers)[0] == "worse"
    assert limited_reading(beside("rail"), layers)[0] == "worse"
    # A silent code, or none loaded: both ways.
    assert limited_reading(beside("freeway", jurisdiction="hillsboro", zone="MR-2"), layers)[0] == "worse"
    assert limited_reading(beside("freeway"), None)[0] == "worse"
    # A private drive's line as well: no reading without both.
    both = beside(street_kind_json=json.dumps(["drive", "freeway", None, None]))
    assert limited_reading(both, layers)[0] == "mixed"


def test_the_side_is_named_even_where_the_kinds_do_not_match_the_lines() -> None:
    odd = beside(street_kind_json=json.dumps(["street", "rail"]))
    assert limited_way_side(odd) == "a street line faces a street on the far side of a railroad"
    assert limited_reading(odd, None)[0] == "worse"
    assert set(LIMITED_STREET_KINDS) == {"freeway", "limited", "rail"}


def test_in_portland_the_lot_is_read_without_its_freeway_line(corpus, policies) -> None:
    """One reading, the code's: an interior lot on its one street, with no
    corner, no second front and no way in off the freeway -- and the same
    answer the lot gets with no freeway beside it at all."""
    lot = lot_from_row(beside("freeway"), corpus.layers)
    assert lot.second is None and lot.limited_replaced and not lot.facts.limited_way
    assert not lot.facts.corner and lot.access == () and lot.front_bearings == (0.0,)
    assert [e.cls for e in lot.edges.edges].count(EdgeClass.front) == 1
    kw = dict(rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    (got,) = screen_lot(lot, [pod()], **kw)
    plain = lot_from_row(row(lot_wkb=beside()["lot_wkb"]), corpus.layers)
    (want,) = screen_lot(plain, [pod()], **kw)
    assert _shown(got) == _shown(want)
    assert got.signed.reasons == want.signed.reasons
    assert STREET_LINE_LIMITED_WAY not in got.signed.reasons


def test_a_replaced_reading_on_s5s_envelope_was_never_computed(corpus, policies) -> None:
    """s5 cut its envelope with the freeway line as a street line: a design
    fitted on it was not screened on the code's reading, and is held."""
    lot = lot_from_row(beside("freeway"), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    green = dataclasses.replace(
        s,
        signed=dataclasses.replace(s.signed, triage=Triage.green, reasons=()),
        envelope=dataclasses.replace(s.envelope, source="quadfit"),
    )
    (held,) = _limited_replaced(lot, [green])
    assert held.signed.triage is Triage.unknown and STREET_LINE_LIMITED_WAY in held.signed.reasons
    assert [f.source for f in held.signed.flags if f.code == FLAG] == [lot.limited_replaced]
    own = dataclasses.replace(green, envelope=dataclasses.replace(s.envelope, source="flats"))
    assert _limited_replaced(lot, [own]) == [own]
    assert _limited_replaced(dataclasses.replace(lot, limited_replaced=""), [green]) == [green]


def test_where_the_code_is_silent_both_readings_are_screened_and_the_lot_is_held(
    corpus, policies
) -> None:
    """Outside Portland (and for a ramp or a railroad in it): the lot as s4
    read it and the lot without the line, the worse kept, never GREEN."""
    for r in (beside("freeway", jurisdiction="hillsboro", zone="MR-2"), beside("rail"), beside("limited")):
        lot = lot_from_row(r, corpus.layers)
        assert lot.second is not None and lot.second.second is None
        assert lot.facts.limited_way and lot.second.facts.limited_way == lot.facts.limited_way
        assert not lot.limited_replaced and not lot.facts.street_unconfirmed
        assert lot.facts.corner and not lot.second.facts.corner
        kw = dict(rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
        (both,) = screen_lot(lot, [pod()], **kw)
        (first,) = screen_lot(dataclasses.replace(lot, second=None), [pod()], **kw)
        (second,) = screen_lot(lot.second, [pod()], **kw)
        assert _shown(both) == max(_shown(first), _shown(second))
        for s in (both, first, second):
            assert STREET_LINE_LIMITED_WAY in s.signed.reasons
            assert s.signed.colour is not Colour.green
            assert FLAG in {f.code for f in s.signed.flags}


def test_with_no_street_left_the_lot_is_held_as_s4_read_it(corpus, policies) -> None:
    """The lot's only street line is the freeway's, s4 wrote no reading
    without it, or a private drive makes another: held, in Portland too."""
    cases = (
        beside("freeway", sans_drive_json=_sans(tier="D", edges=[])),
        beside("freeway", sans_drive_json=None),
        beside(street_kind_json=json.dumps(["drive", "freeway", None, None])),
    )
    for r in cases:
        lot = lot_from_row(r, corpus.layers)
        assert lot.second is None and not lot.limited_replaced and lot.facts.limited_way
        (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
        assert STREET_LINE_LIMITED_WAY in s.signed.reasons and s.signed.colour is not Colour.green
    assert lot.facts.street_unconfirmed  # the last: the private drive's line as well


# --- the real lots ---------------------------------------------------------------


def test_the_portland_lot_on_the_i205_ramp_is_an_interior_lot_on_taylor_st(corpus) -> None:
    """1S2E04AC -09600 (R2.5), a false GREEN of release 10 as a corner lot
    on the Washington St ramp of I-205: read without the ramp line, as it
    was before the wide-road test, with nothing held."""
    r = real_row(FREEWAY_LOT)
    assert limited_reading(r, corpus.layers) == ("replace", "the east line (138 ft) faces a freeway or its ramp")
    lot = lot_from_row(r, corpus.layers)
    assert lot.second is None and lot.limited_replaced and not lot.facts.limited_way
    fronts = [e for e in lot.edges.edges if e.cls in (EdgeClass.front, EdgeClass.street_side)]
    assert len(fronts) == 1 and fronts[0].length_ft == pytest.approx(90.0, abs=0.5)
    assert not lot.facts.corner and lot.access == ()
    assert lot.facts.frontage_ft == pytest.approx(90.0, abs=0.5)
    # As release 10 read it: a corner lot on the ramp, 228 ft of frontage.
    before = lot_from_row({**r, "street_kind_json": None, "sans_drive_json": None}, corpus.layers)
    assert before.facts.corner and before.facts.frontage_ft == pytest.approx(228.3, abs=0.5)


def test_the_hillsboro_lot_behind_the_railroad_is_never_green(corpus, policies) -> None:
    """1S205CD03601 (MR-2), a false GREEN of release 10: its 303 ft line
    reaches Tualatin Valley Hwy only across the railroad. s4 also reads a
    line of it as a street only by a drive on other land, so no reading
    without both exists: the lot is held, the rail side named."""
    r = real_row(RAIL_LOT)
    how, side = limited_reading(r, corpus.layers)
    assert how == "mixed"
    assert side == "the north-east line (303 ft) faces a street on the far side of a railroad"
    kw = dict(rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    for row_ in (r, {**r, "street_kind_json": json.dumps([None, "street", "rail", "street"])}):
        lot = lot_from_row(row_, corpus.layers)
        (s,) = screen_lot(lot, [pod()], **kw)
        assert s.signed.colour is not Colour.green
        assert STREET_LINE_LIMITED_WAY in s.signed.reasons
        (flag,) = [f for f in s.signed.flags if f.code == FLAG]
        assert flag.source == side
    assert lot.second is not None  # without the drive's line: both readings screened


# --- the screen ------------------------------------------------------------------


def _screen(**lot_facts: object):
    """A Hillsboro MU-VTC lot that is GREEN with every fact answered
    (``test_center_cores``), with ``lot_facts`` on top."""
    rules = RuleSet(load_rules(strict=True))
    lot = facts(street_lines_ft=(80.0,), lot_sqft=9000, inside_ugb=True, driveway_spacing="clear", **lot_facts)
    cfg = configure(lot, DESIGN, observed={**PLAIN, CORE: False, FAR: False})
    got = rules.resolve(HILLSBORO, "MU-VTC", cfg.conditions)
    got = dataclasses.replace(got, verdict=Verdict.trusted, untrusted=())
    return screen(
        got, lot, DESIGN, fit(), policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}),
        relief=relief.load_policy(), config=cfg,
    )


def test_a_lot_that_would_be_green_is_yellow_with_the_side_named() -> None:
    plain = _screen()
    assert plain.colour is Colour.green
    side = "the north line (263 ft) faces a street on the far side of a railroad"
    held = _screen(limited_way=side)
    assert held.colour is Colour.yellow
    assert STREET_LINE_LIMITED_WAY in held.reasons
    (flag,) = [f for f in held.flags if f.code == FLAG]
    assert flag.source == side


def test_the_flag_alone_holds_a_lot_yellow() -> None:
    entry = load_registry()[FLAG]
    assert entry.severity >= colour_rules().yellow_at_severity
    assert list(entry.raised_from) == [STREET_LINE_LIMITED_WAY]
