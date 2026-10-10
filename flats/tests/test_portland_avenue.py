"""Gladstone C-2 along Portland Avenue (FOLLOWUPS 52, Steph 2026-10-09).

GMC 17.18.050(3) asks a building "along Portland Avenue" for a primary
entrance facing the avenue and ground-floor windows over a quarter of the
residential ground-floor wall; 17.18.040(4) makes an outright use that
misses them a conditional use. The catalog does not say whether the pod has
them, and Steph ruled: yellow until known, no assumption about the pod.

What must hold: the fact is measured only on Gladstone's lots, to Portland
Avenue's centreline, by a reach that takes a corner lot on a side street and
leaves the lot behind; C-2's permission is qualified on it, so a lot off the
avenue keeps its answer, a lot along it is held open under a named flag, and
a lot red for another reason stays red.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import shapely
from shapely.geometry import LineString, box

from flats.designs.model import load_catalog
from flats.encode.load import load_trusted
from flats.geom.named_street import (
    AVENUE_FACT,
    AVENUE_JURISDICTIONS,
    AVENUE_REACH_FT,
    AVENUE_STREETS,
    avenue_column,
    observed_avenue,
)
from flats.ingest.quadfit import OBSERVABLE, S4_COLUMNS, iter_rows, lot_from_row, observed_facts, screen_lot
from flats.rules.conditions import CONDITIONS
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score import flags as flag_plan
from flats.score import relief, slack
from flats.score.flags import fact_code
from flats.tests.test_utility_easement import X0, Y0
from flats.tests.test_utility_easement import lot_row as _beaverton_row

pytestmark = pytest.mark.unit

GLADSTONE = "or/clackamas/gladstone"
POD = ("multi_story", "attached_wall")
FLAG = fact_code(AVENUE_FACT)
# Portland Avenue 40 ft south of a lot's street line, the way the C-2 lots
# along it measure (34-45 ft); a side street the same distance west.
AVENUE = LineString([(X0 - 1000, Y0 - 40), (X0 + 1000, Y0 - 40)])
SIDE = LineString([(X0 - 40, Y0 - 1000), (X0 - 40, Y0 + 1000)])


# --- the measurement ----------------------------------------------------------


def test_the_avenue_is_gladstones_portland_avenue_and_nothing_else() -> None:
    assert AVENUE_STREETS == (("PORTLAND", "AVE"),)
    assert AVENUE_JURISDICTIONS == frozenset({"gladstone"})
    assert AVENUE_FACT in CONDITIONS and CONDITIONS[AVENUE_FACT].kind == "site_fact"
    assert CONDITIONS[AVENUE_FACT].assume is None
    assert AVENUE_FACT in OBSERVABLE


def test_the_reach_takes_a_lot_touching_the_avenue_and_leaves_the_lot_behind() -> None:
    # Read on the 2026-10-07 file: lots with a line on the avenue 34-45 ft,
    # 1050 Portland Ave's junction corner 55 ft, the nearest lot behind 84 ft.
    assert 55.0 <= AVENUE_REACH_FT < 84.0
    assert observed_avenue(34.1) == {AVENUE_FACT: True}
    assert observed_avenue(54.8) == {AVENUE_FACT: True}
    assert observed_avenue(84.3) == {AVENUE_FACT: False}
    assert observed_avenue(None) == {}
    assert observed_avenue(float("nan")) == {}


def _streets(tmp_path: Path) -> Path:
    path = tmp_path / "s1_streets.parquet"
    pd.DataFrame(
        {
            "name": ["PORTLAND", "JERSEY", "PORTLAND"],
            "ftype": ["AVE", "ST", "ST"],
            "type": [1400, 1500, 1500],
            "alley": [False, False, False],
            "wkb": [
                shapely.to_wkb(AVENUE),
                shapely.to_wkb(SIDE),
                # A Portland STREET is a different street.
                shapely.to_wkb(LineString([(X0 - 1000, Y0 + 300), (X0 + 1000, Y0 + 300)])),
            ],
        }
    ).to_parquet(path, index=False)
    return path


def test_only_gladstone_lots_are_measured(tmp_path: Path) -> None:
    lot = shapely.to_wkb(box(X0, Y0, X0 + 50, Y0 + 100))
    frame = pd.DataFrame(
        {"jurisdiction": ["gladstone", "milwaukie", "gladstone"], "lot_wkb": [lot, lot, None]}
    )
    assert avenue_column(frame, _streets(tmp_path)) == [40.0, None, None]
    bare = tmp_path / "bare.parquet"
    pd.DataFrame({"wkb": [shapely.to_wkb(AVENUE)]}).to_parquet(bare, index=False)
    assert avenue_column(frame, bare) == [None, None, None]


def test_the_rows_carry_the_distance_and_the_fact(tmp_path: Path) -> None:
    lots = pd.DataFrame(
        [
            # On the avenue, a corner on the side street, one lot behind.
            {"TLID": "on", "jurisdiction": "gladstone", "zone": "C2", "wkb": shapely.to_wkb(box(X0 + 100, Y0, X0 + 150, Y0 + 100))},
            {"TLID": "corner", "jurisdiction": "gladstone", "zone": "C2", "wkb": shapely.to_wkb(box(X0, Y0, X0 + 100, Y0 + 50))},
            {"TLID": "behind", "jurisdiction": "gladstone", "zone": "C2", "wkb": shapely.to_wkb(box(X0, Y0 + 50, X0 + 100, Y0 + 150))},
            {"TLID": "elsewhere", "jurisdiction": "milwaukie", "zone": "GMU", "wkb": shapely.to_wkb(box(X0 + 200, Y0, X0 + 250, Y0 + 100))},
        ]
    )
    s4 = tmp_path / "s4_lots.parquet"
    s5o = tmp_path / "s5o_lots.parquet"
    lots[[c for c in S4_COLUMNS if c in lots] + ["wkb"]].to_parquet(s4, index=False)
    lots[["TLID"]].to_parquet(s5o, index=False)
    got = {r["TLID"]: r for r in iter_rows(s4, s5o, streets=_streets(tmp_path))}
    assert got["on"]["avenue_ft"] == 40.0
    assert got["behind"]["avenue_ft"] == 90.0
    assert got["elsewhere"]["avenue_ft"] is None
    assert observed_facts(got["on"])[AVENUE_FACT] is True
    assert observed_facts(got["corner"])[AVENUE_FACT] is True
    assert observed_facts(got["behind"])[AVENUE_FACT] is False
    assert AVENUE_FACT not in observed_facts(got["elsewhere"])


# --- the rule -----------------------------------------------------------------


def test_c2s_permission_is_qualified_on_the_avenue_with_the_codes_own_words() -> None:
    held = load_rules()[GLADSTONE].zones["C2"].values["quadplex_allowed"]
    assert held.value is True
    assert held.qualified_by == AVENUE_FACT
    assert "17.18.050(3)" in held.qualified_cite and "17.18.040(4)" in held.qualified_cite
    assert held.qualified_quote == "or/clackamas/gladstone/17.18.c-2.txt#L115-L121"
    res = RuleSet(load_rules()).resolve(GLADSTONE, "C2", POD)
    assert AVENUE_FACT in res.unencoded
    assert AVENUE_FACT in res.values["quadplex_allowed"].levers


def test_the_quoted_lines_are_the_avenue_limitations() -> None:
    from flats.provenance.store import ProvenanceStore

    text = ProvenanceStore().quote("or/clackamas/gladstone/17.18.c-2.txt#L115-L121")
    assert "along Portland Avenue" in text
    assert "25 percent" in text
    assert "primary entrance facing Portland Avenue" in text


def test_the_flag_names_the_building_and_is_yellow() -> None:
    reg = flag_plan.registry()
    t = reg.types[FLAG]
    assert "entrance" in t.description and "25%" in t.description
    assert t.severity >= flag_plan.colour_rules().yellow_at_severity


# --- through the bridge -------------------------------------------------------


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def _gladstone_row(w: float = 100.0, d: float = 200.0, **over: object) -> dict[str, object]:
    return _beaverton_row(w, d, TLID="22E20CA00000", jurisdiction="gladstone", zone="C2", **over)


def _screened(corpus, policies, row):
    (s,) = screen_lot(
        lot_from_row(row, corpus.layers),
        [load_catalog().latest("pod56x36")],
        rules=corpus,
        policy=policies[0],
        relief=policies[1],
        step_deg=30.0,
    )
    return s


def test_off_the_avenue_the_answer_stands(corpus, policies) -> None:
    s = _screened(corpus, policies, _gladstone_row(avenue_ft=90.0))
    assert s.lot.observed.get(AVENUE_FACT) is False
    assert FLAG not in {f.code for f in s.signed.flags}


def test_along_the_avenue_the_lot_is_held_open_by_name(corpus, policies) -> None:
    off = _screened(corpus, policies, _gladstone_row(avenue_ft=90.0))
    on = _screened(corpus, policies, _gladstone_row(avenue_ft=40.0))
    assert on.lot.observed.get(AVENUE_FACT) is True
    got = {f.code: f for f in on.signed.flags}
    assert FLAG in got
    assert on.signed.colour is not flag_plan.Colour.green
    # Nothing but the avenue moved: the checks are the same checks.
    assert [(c.check, c.verdict) for c in on.screening.checks] == [
        (c.check, c.verdict) for c in off.screening.checks
    ]
    assert off.signed.colour is flag_plan.Colour.green
    assert on.signed.colour is flag_plan.Colour.yellow


def test_red_for_another_reason_stays_red(corpus, policies) -> None:
    # Too narrow for the pod: red whether or not it is on the avenue.
    s = _screened(corpus, policies, _gladstone_row(w=30.0, d=200.0, avenue_ft=40.0))
    assert s.signed.colour is flag_plan.Colour.red
    assert FLAG in {f.code for f in s.signed.flags}
