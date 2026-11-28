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
    # FOLLOWUPS 215 F2: the definition's own first sentence takes in a slip
    # road of the street grid.
    assert r.connectors_street is True and r.connectors_quote and r.connectors_says
    doc, _, line = r.connectors_quote.partition("#L")
    held = (store / doc).read_text(encoding="utf-8").split("\n")[int(line) - 1]
    assert " ".join(r.connectors_says.split()) in " ".join(held.split())
    assert "A right-of-way that is intended for motor vehicle" in r.connectors_says


def test_the_loader_refuses_a_freeway_ruling_without_its_quote() -> None:
    base = {"street": False, "quote": "or/x/y.txt#L1", "says": "words", "note": "n" * 60}
    problems: list[str] = []
    assert _parse_freeways(base, where="t", problems=problems) is not None and not problems
    for bad in ({"street": "no"}, {"quote": "or/x/y.txt"}, {"says": ""}, {"note": "short"}, {"extra": 1}):
        problems = []
        assert _parse_freeways({**base, **bad}, where="t", problems=problems) is None
        assert problems
    assert _parse_freeways(None, where="t", problems=[]) is None
    assert _parse_freeways(base, where="t", problems=[]).connectors_street is False
    linked = {**base, "connectors_street": True, "connectors_quote": "or/x/y.txt#L2", "connectors_says": "w"}
    got = _parse_freeways(linked, where="t", problems=[])
    assert got is not None and got.connectors_street and got.connectors_quote == "or/x/y.txt#L2"
    for bad in ({"connectors_street": "yes"}, {"connectors_quote": "or/x/y.txt"}, {"connectors_says": " "}):
        problems = []
        assert _parse_freeways({**linked, **bad}, where="t", problems=problems) is None
        assert problems


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


def test_a_slip_road_is_a_street_in_portland_and_held_elsewhere(corpus) -> None:
    """FOLLOWUPS 215 F2: s4's ``connector`` (RLIS 1321/1421/1471/1521) is a
    street in Portland -- 33.910.030's "right-of-way that is intended for
    motor vehicle ... travel", which leaves out only the interstates' and
    the Sunset's ramps -- so the lot is read as s4 read it. Outside
    Portland it is screened both ways like any ramp."""
    layers = corpus.layers
    assert limited_reading(beside("connector"), layers) == (None, "")
    assert limited_reading(beside("connector", jurisdiction="hillsboro", zone="MR-2"), layers) == (
        "worse", "the east line (100 ft) faces a ramp or limited-access road",
    )
    assert limited_reading(beside("connector"), None)[0] == "worse"
    # With a private drive's line: the slip road's is no reason to hold it.
    drive = beside(street_kind_json=json.dumps(["drive", "connector", None, None]))
    assert limited_reading(drive, layers) == (None, "")
    # Beside a freeway line: s4's reading without the marked lines drops the
    # slip road's too, so it is not the code's reading -- both ways, held,
    # and only the freeway's line is named.
    both = beside(street_kind_json=json.dumps(["connector", "freeway", None, None]))
    how, side = limited_reading(both, layers)
    assert how == "worse" and side == "the east line (100 ft) faces a freeway or its ramp"
    assert limited_reading(beside("freeway"), layers)[0] == "replace"


def test_a_portland_lot_on_a_slip_road_is_the_lot_s4_read(corpus, policies) -> None:
    """One reading, s4's: the slip road's line a street line (a corner),
    no second reading, no ACCESS-LIMITED-WAY -- the answer the lot gets
    with the line read as any street."""
    lot = lot_from_row(beside("connector"), corpus.layers)
    assert lot.second is None and not lot.limited_replaced and not lot.facts.limited_way
    assert lot.facts.corner
    kw = dict(rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    (got,) = screen_lot(lot, [pod()], **kw)
    street = lot_from_row(beside(street_kind_json=json.dumps(["street", "street", None, None])), corpus.layers)
    (want,) = screen_lot(street, [pod()], **kw)
    assert _shown(got) == _shown(want)
    assert got.signed.reasons == want.signed.reasons
    assert STREET_LINE_LIMITED_WAY not in got.signed.reasons


def test_the_side_is_named_even_where_the_kinds_do_not_match_the_lines() -> None:
    odd = beside(street_kind_json=json.dumps(["street", "rail"]))
    assert limited_way_side(odd) == "a street line faces a street on the far side of a railroad"
    assert limited_reading(odd, None)[0] == "worse"
    assert set(LIMITED_STREET_KINDS) == {"connector", "freeway", "limited", "rail"}


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
        # A reading RED on one side of the line only says so after the side
        # (rulings.yaml 2026-11-27-freeway-line-red-only-yellow).
        assert flag.source.startswith(side)
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


def _read(colour_of: str, *, side: str = "", flags: tuple[str, ...] = ()) -> object:
    """One reading of a limited-way lot, as :func:`_worse` reads it: RED on
    a ``fit_ft`` bind, YELLOW on a held flag, else GREEN. ``side`` is the
    line the reading without the freeway-side line names (its
    ``facts.limited_way``); empty on the reading s4 wrote."""
    from types import SimpleNamespace

    from flats.score import flags as flag_plan
    from flats.score.screen import Screening

    @dataclasses.dataclass(frozen=True)
    class Read:
        screening: Screening
        signed: Screening
        lot: object
        envelope: object = None

    binds = (flag_plan.Bind("fit_ft", 70.0, 80.0, 10.0),) if colour_of == "red" else ()
    codes = flags + (("MEASURE-FRONT-MAX-STREET",) if colour_of == "yellow" else ())
    got = tuple(
        flag_plan.Flag(c, flag_plan.LOT, STREET_LINE_LIMITED_WAY if c == "ACCESS-LIMITED-WAY" else "X")
        for c in codes
    )
    s = Screening(triage=Triage.unknown, flags=got, binds=binds)
    return Read(screening=s, signed=s, lot=SimpleNamespace(facts=SimpleNamespace(limited_way=side)))


SIDE = "the north line (111 ft) faces a ramp or limited-access road"


def test_a_lot_red_only_on_one_reading_of_its_freeway_side_line_is_held_yellow() -> None:
    """Steph 2026-11-27 (rulings.yaml 2026-11-27-freeway-line-red-only-yellow,
    "Yellow for a look"): the map cannot tell the line, so a RED on one
    reading alone is shown on the other reading, YELLOW, naming the miss."""
    from flats.ingest.quadfit import LINE_RED_ONLY_RULING, _worse

    # The reading without the line misses; the reading s4 wrote does not.
    as_s4 = _read("yellow")
    without = _read("red", side=SIDE, flags=("ACCESS-LIMITED-WAY",))
    got = _worse(as_s4, without)
    assert got.signed.colour is got.screening.colour is Colour.yellow
    (held,) = [f for f in got.signed.flags if f.code == "ACCESS-LIMITED-WAY"]
    assert SIDE in held.source and "fit_ft" in held.source and LINE_RED_ONLY_RULING in held.source
    assert STREET_LINE_LIMITED_WAY in got.signed.reasons
    # The other way round: the reading s4 wrote misses, the one without the
    # line holds YELLOW on its own flag, which now names the miss.
    got = _worse(_read("red"), _read("yellow", side=SIDE, flags=("ACCESS-LIMITED-WAY",)))
    assert got.signed.colour is Colour.yellow
    assert [f.code for f in got.signed.flags].count("ACCESS-LIMITED-WAY") == 1
    assert "fit_ft" in next(f.source for f in got.signed.flags if f.code == "ACCESS-LIMITED-WAY")


def test_a_lot_red_on_both_readings_stays_red() -> None:
    """RED on another check that holds either way the line is read: RED."""
    from flats.ingest.quadfit import _worse

    as_s4 = _read("red")
    without = _read("red", side=SIDE, flags=("ACCESS-LIMITED-WAY",))
    assert _worse(as_s4, without).signed.colour is Colour.red


def test_a_green_other_reading_is_held_yellow_never_green() -> None:
    from flats.ingest.quadfit import _worse

    clear = _read("green")
    assert clear.signed.colour is Colour.green
    got = _worse(clear, _read("red", side=SIDE, flags=("ACCESS-LIMITED-WAY",)))
    assert got.signed.colour is got.screening.colour is Colour.yellow
    assert any(f.code == "ACCESS-LIMITED-WAY" for f in got.signed.flags)


def test_a_private_drive_lot_red_on_one_reading_stays_red() -> None:
    """The hold is the freeway-side line's alone: a lot read with and
    without a private drive (no ``limited_way``) keeps its worse answer."""
    from flats.ingest.quadfit import _worse

    red = _read("red")
    assert _worse(_read("green"), red) is red
