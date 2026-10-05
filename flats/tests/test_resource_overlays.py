"""Mapped stream, wetland, habitat and flood areas before placement
(FOLLOWUPS 42(b)/(c)).

quadfit reads every overlay's code and gives it an action: ``carve`` takes the
ground off the envelope, ``kill`` makes the lot a hearing, ``flag`` lets a
house go up with a permit. Until 2026-10-05 FLATS read the carves only, so a
lot touching a ``flag`` area passed GREEN with nothing said, and Milwaukie's
Willamette Greenway -- a hearing for every building -- did not stop a lot at
all. These hold each overlay to one reading in FLATS and keep any overlay
added to quadfit from going unread here.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from flats.ingest.quadfit import (
    GREENWAY_ANSWERS,
    GREENWAY_COLUMN,
    S5O_COLUMNS,
    lot_from_row,
    observed_facts,
)
from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import CONDITIONS
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.rules.resource_overlays import BY_KEY, COLUMNS, PERMITS, permits_on
from flats.score import flags as flag_plan
from flats.score.screen import CLOSER_LOOK_RESOURCE, Triage
from flats.tests.test_quadfit_bridge import row
from flats.tests.test_screen import LOT, run

OVERLAYS = Path(__file__).resolve().parents[2] / "Lot Analysis" / "quadfit" / "config" / "overlays.yaml"

#: quadfit's kills FLATS reads as use rules rather than as a permit flag.
#: Portland's three environmental zones are both: a lot the z covers is RED
#: on 33.418 (``constrained_sites_overlay``), and one the z map leaves out
#: is a permit flag.
KILLS_AS_FACTS = {"milwaukie_greenway": "willamette_greenway_zone"}

MILWAUKIE = "or/clackamas/milwaukie"
GREENWAY = "willamette_greenway_zone"


@pytest.fixture(scope="module")
def quadfit_overlays() -> dict[str, str]:
    held = yaml.safe_load(OVERLAYS.read_text(encoding="utf-8"))
    return {o["key"]: o["action"] for o in held["overlays"]}


@pytest.fixture(scope="module")
def layers():
    return load_rules()


@pytest.fixture(scope="module")
def rules(layers):
    return RuleSet(layers)


# --- every overlay quadfit reads has one reading here ---------------------


def test_every_quadfit_flag_overlay_is_a_permit_here(quadfit_overlays) -> None:
    flags = {k for k, action in quadfit_overlays.items() if action == "flag"}
    assert flags <= set(BY_KEY), sorted(flags - set(BY_KEY))


def test_every_quadfit_kill_is_read_here(quadfit_overlays) -> None:
    kills = {k for k, action in quadfit_overlays.items() if action == "kill"}
    unread = kills - set(BY_KEY) - set(KILLS_AS_FACTS)
    assert unread == set(), sorted(unread)
    for fact in KILLS_AS_FACTS.values():
        assert CONDITIONS[fact].kind == "site_fact"


def test_no_permit_names_an_overlay_quadfit_does_not_measure(quadfit_overlays) -> None:
    assert set(BY_KEY) <= set(quadfit_overlays)
    # A carve is already off the envelope; flagging it as well would say the
    # ground is buildable with a permit when the code says it is not.
    carves = {k for k, action in quadfit_overlays.items() if action == "carve"}
    assert not carves & set(BY_KEY)


def test_the_bridge_reads_every_permit_column_and_the_greenway() -> None:
    assert set(COLUMNS) <= set(S5O_COLUMNS)
    assert GREENWAY_COLUMN in S5O_COLUMNS
    assert len(COLUMNS) == len(PERMITS) == len(BY_KEY)


# --- reading the columns ---------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, ("washington_habitat",)), (False, ()), (None, ()), (float("nan"), ())],
)
def test_a_permit_area_is_read_off_its_column(value, expected) -> None:
    assert permits_on({"ovl_washington_habitat": value}) == expected


def test_a_row_with_no_overlay_columns_says_nothing() -> None:
    assert permits_on({}) == ()


def test_the_bridge_carries_the_areas_onto_the_lot() -> None:
    got = lot_from_row(row(ovl_fema_sfha=True, ovl_washington_cws_corridor=True))
    assert set(got.facts.resource_permits) == {"fema_sfha", "washington_cws_corridor"}
    assert lot_from_row(row()).facts.resource_permits == ()


# --- the screen ------------------------------------------------------------


def test_a_clean_lot_on_a_permit_area_is_a_closer_look_not_green() -> None:
    clean = run()
    assert clean.triage is Triage.green

    got = run(lot=replace(LOT, resource_permits=("washington_habitat",)))
    assert got.triage is Triage.yellow
    assert got.reasons == (CLOSER_LOOK_RESOURCE,)
    assert got.colour is flag_plan.Colour.yellow
    [held] = [f for f in got.flags if f.code == "RESOURCE-PERMIT"]
    assert held.key.split(flag_plan.SEP)[-1] == "washington_habitat"


def test_each_area_is_its_own_question() -> None:
    got = run(lot=replace(LOT, resource_permits=("fema_sfha", "clackamas_hca")))
    keys = {f.key.split(flag_plan.SEP)[-1] for f in got.flags if f.code == "RESOURCE-PERMIT"}
    assert keys == {"fema_sfha", "clackamas_hca"}


def test_the_flag_holds_the_lot_at_yellow() -> None:
    kind = flag_plan.registry()["RESOURCE-PERMIT"]
    assert kind.severity >= flag_plan.colour_rules().yellow_at_severity


# --- Milwaukie's Willamette Greenway ---------------------------------------


def test_the_greenway_is_a_measured_site_fact_never_assumed() -> None:
    held = CONDITIONS[GREENWAY]
    assert held.kind == "site_fact" and held.assume is None


@pytest.mark.parametrize("zone", ["R-MD", "R-HD"])
def test_the_greenway_makes_the_fourplex_a_hearing(rules, zone) -> None:
    assert rules.resolve(MILWAUKIE, zone).get("quadplex_allowed") is True
    got = rules.resolve(MILWAUKIE, zone, conditions=[GREENWAY]).values["quadplex_allowed"]
    assert got.value is False
    assert [(set(w), v) for w, v, _ in got.relief] == [({GREENWAY, "conditional_use"}, True)]
    again = rules.resolve(MILWAUKIE, zone, conditions=[GREENWAY, "state_middle_housing"])
    assert again.get("quadplex_allowed") is False


@pytest.mark.parametrize("zone", ["R-MD", "R-HD"])
def test_the_greenway_quotes_its_sentence(layers, zone) -> None:
    held = layers[MILWAUKIE].zones[zone].values["quadplex_allowed"]
    [variant] = [v for v in held.variants if v.when == (GREENWAY,)]
    text = ProvenanceStore().quote(variant.prov.quote)
    assert "development permitted in the underlying zone, are conditional uses" in text
    assert "A greenway conditional use is required for all" in text


def test_no_other_zone_turns_on_the_greenway(layers) -> None:
    stray = [
        (name, zone, field)
        for name, layer in layers.items()
        for zone, z in layer.zones.items()
        for field, value in z.values.items()
        if any(GREENWAY in v.when for v in getattr(value, "variants", ()) or ())
        and not (name == MILWAUKIE and zone in {"R-MD", "R-HD"} and field == "quadplex_allowed")
    ]
    assert stray == []


@pytest.mark.parametrize(
    ("juris", "value", "expected"),
    [
        ("milwaukie", True, True),
        ("milwaukie", False, False),
        ("milwaukie", None, None),
        ("gladstone", True, None),
    ],
)
def test_the_bridge_answers_the_greenway_in_milwaukie_only(juris, value, expected) -> None:
    got = observed_facts(row(jurisdiction=juris, ovl_milwaukie_greenway=value))
    assert got.get(GREENWAY) is expected
    assert GREENWAY_ANSWERS == {"milwaukie"}
