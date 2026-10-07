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
from flats.rules.resource_overlays import BY_KEY, CLEARED, COLUMNS, EXEMPT, PERMITS, permits_on
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
def quadfit_specs() -> dict[str, dict]:
    held = yaml.safe_load(OVERLAYS.read_text(encoding="utf-8"))
    return {o["key"]: o for o in held["overlays"]}


@pytest.fixture(scope="module")
def quadfit_overlays(quadfit_specs) -> dict[str, str]:
    return {k: o["action"] for k, o in quadfit_specs.items()}


@pytest.fixture(scope="module")
def layers():
    return load_rules()


@pytest.fixture(scope="module")
def rules(layers):
    return RuleSet(layers)


# --- every overlay quadfit reads has one reading here ---------------------


def test_every_quadfit_flag_overlay_is_a_permit_here(quadfit_overlays) -> None:
    flags = {k for k, action in quadfit_overlays.items() if action == "flag"}
    assert flags <= set(BY_KEY) | set(EXEMPT), sorted(flags - set(BY_KEY) - set(EXEMPT))


def test_an_exempt_overlay_is_measured_and_never_a_permit(quadfit_overlays) -> None:
    """West Linn's piped streams: on the map, in the net area, and released.

    WLCDC 32.040(F)(2) exempts "existing enclosed or piped sections of
    streams" from the chapter, so a lot touching one is not a closer look.
    quadfit still measures it, for the net-area deduction.
    """
    assert set(EXEMPT) <= {k for k, action in quadfit_overlays.items() if action == "flag"}
    assert not set(EXEMPT) & set(BY_KEY)
    assert "32.040(F)" in EXEMPT["west_linn_wra_piped"]
    assert permits_on({"ovl_west_linn_wra_piped": True}) == ()


def test_each_no_build_carve_keeps_its_permit_flag(quadfit_overlays) -> None:
    """Phase 2: the carve takes the ground; the flag keeps the paperwork.

    A lot whose pod clears a Clean Water Services corridor still owes the
    Service Provider Letter and the corridor planting, so the flag on the same
    map stays a closer look while the ``*_core`` twin takes the ground off.
    """
    twins = {
        "washington_cws_corridor_core": "washington_cws_corridor",
        "clackamas_hca_core": "clackamas_hca",
        "wilsonville_sroz_core": "wilsonville_sroz",
        "milwaukie_hca_core": "milwaukie_hca",
        "milwaukie_wqr_core": "milwaukie_wqr",
        "gladstone_hca_core": "gladstone_hca",
        "gladstone_wq_core": "gladstone_wq",
        "west_linn_rci_resource": "west_linn_rci",
        "metro_title3": "wood_village_wqr",
        "metro_title13": "wood_village_hca",
        "hillsboro_snro_core": "hillsboro_snro",
    }
    for carve, flag in twins.items():
        assert quadfit_overlays[carve] == "carve", carve
        assert quadfit_overlays[flag] == "flag", flag
        assert flag in BY_KEY and carve not in BY_KEY
    # Portland's zones are quadfit kills read here as permits (a lot the z map
    # leaves out); the resource areas inside them carve under their own keys.
    for zone in ("p", "c", "v"):
        carve, permit = f"pdx_ezone_{zone}_core", f"pdx_ezone_{zone}"
        assert quadfit_overlays[carve] == "carve" and quadfit_overlays[permit] == "kill"
        assert permit in BY_KEY and carve not in BY_KEY


#: The carves quadfit held before 2026-10-05, each with the flag on the same
#: map that keeps the lot a closer look once the pod clears it (FOLLOWUPS 50).
SITE_TWINS = {
    "gresham_hcra": "gresham_hcra_site",
    "gresham_wetlands": "gresham_wetlands_site",
    "troutdale_veco": "troutdale_veco_site",
    "fairview_nrl": "fairview_nrl_site",
    "west_linn_wra_stream": "west_linn_wra_stream_site",
    "west_linn_wra_ephemeral": "west_linn_wra_ephemeral_site",
    "west_linn_wra_riparian": "west_linn_wra_riparian_site",
    "west_linn_wetlands": "west_linn_wetlands_site",
    "tualatin_nrpo": "tualatin_nrpo_site",
    "tualatin_stream_buffer": "tualatin_stream_buffer_site",
}

#: What decides whether two specs touch the same lots, with OverlaySpec's defaults.
_GEOMETRY = {
    "buffer_ft": 0,
    "keep_where": {},
    "within": None,
    "within_inset_ft": 0,
    "fill_holes": False,
    "holes_only": False,
    "jurisdictions": "all",
}


def _layer(spec: dict) -> str:
    return spec.get("source") or spec["key"]


def test_a_site_twin_draws_exactly_its_carve(quadfit_specs) -> None:
    """The flag must touch the lots the carve touches -- no more, no fewer.

    47 greens in the 2026-10-07 weekly sat on one of these carves with no
    flag, because nothing but the carve read the map. A twin that read a
    narrower buffer than its carve would let some of them through again.
    """
    for carve, twin in SITE_TWINS.items():
        c, t = quadfit_specs[carve], quadfit_specs[twin]
        assert c["action"] == "carve" and t["action"] == "flag", carve
        assert _layer(c) == _layer(t), carve
        for field, default in _GEOMETRY.items():
            assert c.get(field, default) == t.get(field, default), (carve, field)
        assert twin in BY_KEY and carve not in BY_KEY


def test_every_carve_is_either_flagged_on_the_site_or_cleared(quadfit_specs) -> None:
    """Each no-build map is read for what it asks of a site the pod clears.

    Either a flag reads the same layer (the paperwork is still owed: a
    Service Provider Letter, an NRO exemption form, a surveyed boundary), or
    CLEARED quotes the sentence confining the chapter to the area itself.
    """
    flagged_layers = {_layer(o) for o in quadfit_specs.values() if o["action"] in ("flag", "kill")}
    unread = [
        k for k, o in quadfit_specs.items()
        if o["action"] == "carve"
        and _layer(o) not in flagged_layers
        and not {w for w in ([o["within"]] if isinstance(o.get("within"), str) else o.get("within") or [])}
        & flagged_layers
        and k not in CLEARED
    ]
    assert unread == []
    assert all(quadfit_specs[k]["action"] == "carve" for k in CLEARED)
    assert not set(CLEARED) & set(BY_KEY)
    # a cleared carve with a flag on its own layer would be read twice, two ways
    assert not {_layer(quadfit_specs[k]) for k in CLEARED} & flagged_layers


@pytest.mark.parametrize("carve", sorted(SITE_TWINS))
def test_a_lot_beside_an_older_carve_is_a_closer_look(carve) -> None:
    twin = SITE_TWINS[carve]
    assert permits_on({f"ovl_{twin}": True}) == (twin,)
    # the carve's own column says nothing: the ground is off, the permit is the twin's
    assert permits_on({f"ovl_{carve}": True}) == ()
    got = run(lot=replace(LOT, resource_permits=(twin,)))
    assert got.triage is Triage.yellow and got.colour is flag_plan.Colour.yellow


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
