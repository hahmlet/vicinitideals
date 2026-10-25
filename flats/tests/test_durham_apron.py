"""Durham 3.7.1.7: no driveway apron within 100 ft of a street intersection
(FOLLOWUPS 118, owner 2026-10-24).

Nothing measures how far a frontage sits from an intersection's curb return,
so the sentence is held as a qualifier on the apron standard, on a fact
nothing answers. What must hold: a Durham lot the rest of the screen would
certify -- a corner lot above all -- comes back out of GREEN under a flag
whose words say why in plain English; the flag is the only thing holding it
(answered False, the same lot is GREEN); and no other city carries the fact.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
import shapely
from shapely.geometry import box

from flats.designs.model import load_catalog
from flats.encode.load import load_trusted
from flats.ingest.quadfit import lot_from_row, screen_lot
from flats.rules.conditions import CONDITIONS
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score import flags as flag_plan
from flats.score import relief, slack
from flats.score.flags import fact_code
from flats.tests.test_utility_easement import X0, Y0
from flats.tests.test_utility_easement import lot_row as _beaverton_row

pytestmark = pytest.mark.unit

DURHAM = "or/washington/durham"
FACT = "driveway_near_intersection_100ft"
FLAG = fact_code(FACT)
POD = ("multi_story", "attached_wall")


def test_the_fact_is_registered_and_never_answered() -> None:
    defn = CONDITIONS[FACT]
    assert defn.kind == "site_fact"
    assert defn.assume is None
    assert "3.7.1.7" in defn.describe and "100 feet" in defn.describe


def test_the_apron_is_qualified_with_the_codes_own_words() -> None:
    held = load_rules()[DURHAM].defaults["driveway_approach_max_width_ft"]
    assert held.value == 40
    assert held.qualified_by == FACT
    assert "3.7.1.7" in held.qualified_cite and "100 feet" in held.qualified_cite
    assert held.qualified_quote == "or/washington/durham/3/3.7.txt#L27"
    for zone in ("SDR", "MDR"):
        res = RuleSet(load_rules()).resolve(DURHAM, zone, POD)
        assert FACT in res.unencoded


def test_the_quoted_line_is_the_100_feet() -> None:
    from flats.provenance.store import ProvenanceStore

    text = ProvenanceStore().quote("or/washington/durham/3/3.7.txt#L27")
    assert text.startswith("3.7.1.7")
    assert "100 feet from any street intersection" in text
    assert "curb return" in text


def test_no_other_city_carries_the_fact() -> None:
    for jid, layer in load_rules().items():
        if jid == DURHAM:
            continue
        held = list(layer.defaults.values()) + [
            v for z in layer.zones.values() for v in z.values.values()
        ]
        assert all(v.qualified_by != FACT for v in held), jid


def test_the_flag_reads_in_plain_english() -> None:
    t = flag_plan.registry().types[FLAG]
    assert t.description == (
        "Durham forbids a driveway within 100 ft of a street intersection "
        "(3.7.1.7); not yet checked on this lot"
    )
    assert t.severity >= flag_plan.colour_rules().yellow_at_severity


# --- through the bridge -------------------------------------------------------


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def _durham_corner(w: float = 120.0, d: float = 200.0) -> dict[str, object]:
    """A Durham SDR corner lot: streets along its south and west edges."""
    edges = [
        [X0, Y0, X0 + w, Y0, "F"],
        [X0 + w, Y0, X0 + w, Y0 + d, "S"],
        [X0 + w, Y0 + d, X0, Y0 + d, "R"],
        [X0, Y0 + d, X0, Y0, "F"],
    ]
    return _beaverton_row(
        w,
        d,
        TLID="2S113BC00100",
        jurisdiction="durham",
        zone="SDR",
        edges_json=json.dumps(edges),
        front_bearings_json="[0.0, 90.0]",
        frontage_ft=w + d,
        area_sqft=w * d,
        lot_wkb=shapely.to_wkb(box(X0, Y0, X0 + w, Y0 + d)),
    )


def _screen(corpus, policies, lot):
    (s,) = screen_lot(
        lot,
        [load_catalog().latest("pod56x36")],
        rules=corpus,
        policy=policies[0],
        relief=policies[1],
        step_deg=30.0,
    )
    return s


def test_a_durham_corner_lot_cannot_be_green_and_says_why(corpus, policies) -> None:
    lot = lot_from_row(_durham_corner(), corpus.layers)
    assert FACT not in lot.observed
    held = _screen(corpus, policies, lot)
    flags = {f.code: f for f in held.signed.flags}
    assert FLAG in flags
    assert held.signed.colour is not flag_plan.Colour.green
    assert held.signed.colour is flag_plan.Colour.yellow
    # The flag is the only thing holding it: answered False, the lot is GREEN.
    cleared = _screen(
        corpus, policies, dataclasses.replace(lot, observed={**lot.observed, FACT: False})
    )
    assert FLAG not in {f.code for f in cleared.signed.flags}
    assert cleared.signed.colour is flag_plan.Colour.green
