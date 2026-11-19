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

from flats.ingest.sources import load_pipeline
from flats.ingest.quadfit import (
    GREENWAY_ANSWERS,
    GREENWAY_COLUMN,
    GREENWAY_COLUMNS,
    S5O_COLUMNS,
    lot_from_row,
    observed_facts,
)
from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import CONDITIONS
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.rules.resource_overlays import AREAS, BY_KEY, CLEARED, COLUMNS, EXEMPT, PERMITS, TRACED, permits_on
from flats.score import flags as flag_plan
from flats.score.screen import CLOSER_LOOK_RESOURCE, Triage
from flats.tests.test_quadfit_bridge import row
from flats.tests.test_screen import LOT, run

OVERLAYS = Path(__file__).resolve().parents[2] / "Lot Analysis" / "quadfit" / "config" / "overlays.yaml"

#: quadfit's kills FLATS reads as use rules rather than as a permit flag.
#: Portland's three environmental zones are both: a lot the z covers is RED
#: on 33.418 (``constrained_sites_overlay``), and one the z map leaves out
#: is a permit flag.
KILLS_AS_FACTS = {
    "milwaukie_greenway": "willamette_greenway_zone",
    # OCMC 17.48 (FOLLOWUPS 204 item 3, 2026-11-18), held as Milwaukie's is.
    "oregon_city_greenway": "willamette_greenway_zone",
}

MILWAUKIE = "or/clackamas/milwaukie"
OREGON_CITY = "or/clackamas/oregon-city"
#: Every Oregon City zone that opens the fourplex, each closed in the WRG.
OREGON_CITY_OPEN = ("R-10", "R-8", "R-6", "R-5", "R-3.5", "R-2", "MUC-1", "MUC-2", "MUD", "C", "WFDD")
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
        "clackamas_landslide_core": "clackamas_landslide",
        "clackamas_landslide_scarp_core": "clackamas_landslide_scarp",
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


def test_the_river_environmental_overlay_is_carved_and_asks_nothing_else(quadfit_specs) -> None:
    """PCC 33.475 (FOLLOWUPS 202, 2026-11-18): "e" takes the ground and no flag.

    Its only by-right path for a house caps disturbance inside it (440.O); a
    pod clear of it owes nothing under the chapter, and it is no z trigger
    (33.418.030.A names c, p and Pleasant Valley only).
    """
    spec = quadfit_specs["pdx_river_e"]
    assert spec["action"] == "carve" and spec["jurisdictions"] == ["portland"]
    assert spec.get("buffer_ft", 0) == 0 and "within" not in spec
    assert "pdx_river_e" in CLEARED and "pdx_river_e" not in BY_KEY
    assert "in the River Environmental overlay zone" in CLEARED["pdx_river_e"]
    assert permits_on({"ovl_pdx_river_e": True}) == ()
    held = load_pipeline().datasets["overlay_pdx_river_e"]
    assert held.url.endswith("/BPS_Zoning_Code_Layers/MapServer/110")


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
    assert set(GREENWAY_COLUMNS.values()) <= set(S5O_COLUMNS)
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


def test_portland_s_1996_flood_area_is_the_same_closer_look_as_fema_s_fringe() -> None:
    """PCC 24.50.040 E adopts the City's Composite February 1996 Flood
    Inundation Area beside the FIRMs, under the same chapter's conditions
    (FOLLOWUPS 202): a lot on it is YELLOW, as in the FEMA fringe (ruling
    2026-10-06-fema-fringe-stays-yellow), and says which map put it there."""
    area = BY_KEY["pdx_flood_1996"]
    assert "24.50.040 E" in area.cite and "1996" in area.words
    assert area.column in S5O_COLUMNS

    inside = lot_from_row(row(ovl_pdx_flood_1996=True)).facts
    assert inside.resource_permits == ("pdx_flood_1996",)
    got = run(lot=replace(LOT, resource_permits=inside.resource_permits))
    assert got.triage is Triage.yellow and got.colour is flag_plan.Colour.yellow
    assert got.reasons == (CLOSER_LOOK_RESOURCE,)
    [held] = [f for f in got.flags if f.code == "RESOURCE-PERMIT"]
    assert held.key.split(flag_plan.SEP)[-1] == "pdx_flood_1996"
    fema_only = run(lot=replace(LOT, resource_permits=("fema_sfha",)))
    assert (fema_only.triage, fema_only.colour) == (got.triage, got.colour)

    # outside the area, and a row s5o wrote before the layer existed: nothing said
    assert lot_from_row(row(ovl_pdx_flood_1996=False)).facts.resource_permits == ()
    assert lot_from_row(row()).facts.resource_permits == ()


def test_fema_and_the_1996_area_stay_two_answers() -> None:
    both = lot_from_row(row(ovl_fema_sfha=True, ovl_pdx_flood_1996=True)).facts
    assert set(both.resource_permits) == {"fema_sfha", "pdx_flood_1996"}
    got = run(lot=replace(LOT, resource_permits=both.resource_permits))
    keys = {f.key.split(flag_plan.SEP)[-1] for f in got.flags if f.code == "RESOURCE-PERMIT"}
    assert keys == {"fema_sfha", "pdx_flood_1996"}
    assert got.triage is Triage.yellow


def test_the_1996_area_is_measured_on_portland_only(quadfit_specs) -> None:
    spec = quadfit_specs["pdx_flood_1996"]
    assert spec["action"] == "flag" and spec["jurisdictions"] == ["portland"]
    # the FEMA fringe the flag mirrors reaches everywhere; this map is the City's alone
    assert quadfit_specs["fema_sfha"]["jurisdictions"] == "all"


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
        # DMU and GMU (encoded 2026-10-08) carry a Greenway variant on the
        # same field, but pointed the other way: `value: false` on the
        # unit-lots townhouse path (DMU also inside_mapped_use_area), because
        # 19.401.3 / 19.401.5.D make all development in the Greenway Zone a
        # conditional use and by-right only means no hearing variant. It can
        # only refuse the zone's one open path, never open anything.
        and not (name == MILWAUKIE and zone in {"DMU", "GMU"} and field == "quadplex_allowed")
        # Oregon City's WRG (OCMC 17.48, FOLLOWUPS 204 item 3): `value: false`
        # on every zone that opens the fourplex, and no way in.
        and not (name == OREGON_CITY and zone in OREGON_CITY_OPEN and field == "quadplex_allowed")
    ]
    assert stray == []


@pytest.mark.parametrize(
    ("juris", "value", "expected"),
    [
        ("milwaukie", True, True),
        ("milwaukie", False, False),
        ("milwaukie", None, None),
        ("gladstone", True, None),
        # Another city's map is not this one: Milwaukie's column says nothing
        # about an Oregon City lot.
        ("oregon_city", True, None),
    ],
)
def test_the_bridge_answers_the_greenway_in_milwaukie_only(juris, value, expected) -> None:
    got = observed_facts(row(jurisdiction=juris, ovl_milwaukie_greenway=value))
    assert got.get(GREENWAY) is expected
    assert GREENWAY_ANSWERS == {"milwaukie", "oregon_city"}


# --- Oregon City's Willamette River Greenway (FOLLOWUPS 204 item 3) --------


@pytest.mark.parametrize(
    ("juris", "value", "expected"),
    [
        ("oregon_city", True, True),
        ("oregon_city", False, False),
        ("oregon_city", None, None),
        ("milwaukie", True, None),
        ("west_linn", True, None),
    ],
)
def test_the_bridge_answers_oregon_city_s_greenway_off_its_own_map(juris, value, expected) -> None:
    got = observed_facts(row(jurisdiction=juris, ovl_oregon_city_greenway=value))
    assert got.get(GREENWAY) is expected


@pytest.mark.parametrize("zone", OREGON_CITY_OPEN)
def test_oregon_city_s_greenway_closes_the_fourplex_with_no_way_in(rules, zone) -> None:
    """OCMC 17.48.050: a Greenway permit for all developments, decided on
    judgement (17.48.080). Held as Milwaukie's is, and no relief is encoded."""
    assert rules.resolve(OREGON_CITY, zone).get("quadplex_allowed") is True
    got = rules.resolve(OREGON_CITY, zone, conditions=[GREENWAY]).values["quadplex_allowed"]
    assert got.value is False
    assert not any(GREENWAY in when for when, _, _ in got.relief)
    again = rules.resolve(OREGON_CITY, zone, conditions=[GREENWAY, "state_middle_housing"])
    assert again.get("quadplex_allowed") is False


def test_oregon_city_s_greenway_quotes_its_sentences(layers) -> None:
    held = layers[OREGON_CITY].zones["R-6"].values["quadplex_allowed"]
    [variant] = [v for v in held.variants if v.when == (GREENWAY,)]
    text = " ".join(ProvenanceStore().quote(variant.prov.quote).split())
    assert "A Willamette River Greenway permit shall be required for all developments" in text
    assert "considerations shall be applicable to all Willamette River Greenway permits" in text
    assert "approved only if the following findings are made by the planning commission" in text


def test_oregon_city_s_greenway_is_a_kill_on_oregon_city_only(quadfit_specs) -> None:
    spec = quadfit_specs["oregon_city_greenway"]
    assert spec["action"] == "kill" and spec["jurisdictions"] == ["oregon_city"]
    assert "17.48.050" in spec["citation"]
    held = load_pipeline().datasets["overlay_oregon_city_greenway"]
    assert held.url.endswith("/WaterAndNaturalResources/MapServer/10")
    assert list(held.serves) == [OREGON_CITY]


# --- Oregon City's Geologic Hazards Overlay (FOLLOWUPS 204 item 2) ----------


def test_oregon_city_s_geologic_hazards_carve_the_core_and_flag_the_site(quadfit_specs) -> None:
    """OCMC 17.44.060.H: no pod, court or drive on a mapped landslide, its
    buffer or a 25 percent slope (two dwellings an acre; none over 35
    percent) -- carved. 17.44.025: the review reaches any property that
    contains a mapped area -- flagged, whole overlay, slope buffer included."""
    site, core = quadfit_specs["oregon_city_geohazard"], quadfit_specs["oregon_city_geohazard_core"]
    assert site["action"] == "flag" and core["action"] == "carve"
    assert site["jurisdictions"] == core["jurisdictions"] == ["oregon_city"]
    assert core["source"] == "oregon_city_geohazard" and core.get("buffer_ft", 0) == 0
    assert core["keep_where"] == {"IN_LANDSLIDE": ["Y"], "IN_LANDSLIDE_BUFFER": ["Y"], "IN_SLOPE": ["Y"]}
    assert "keep_where" not in site and "IN_SLOPE_BUFFER" not in core["keep_where"]
    assert "17.44.025" in site["citation"] and "H.2.a" in core["citation"]
    # the carve takes the ground and says nothing; the flag is the site's
    assert "oregon_city_geohazard" in BY_KEY and "oregon_city_geohazard_core" not in BY_KEY
    assert "oregon_city_geohazard_core" not in CLEARED
    assert permits_on({"ovl_oregon_city_geohazard_core": True}) == ()
    held = load_pipeline().datasets["overlay_oregon_city_geohazard"]
    assert held.url.endswith("/HazardsAndFloodInfo_PUBLIC/MapServer/11")
    assert {"IN_SLOPE", "IN_LANDSLIDE", "IN_LANDSLIDE_BUFFER"} <= set(held.fields)


def test_a_lot_holding_any_of_the_geologic_hazards_overlay_is_a_closer_look() -> None:
    """The pod clear of the carved ground still owes the 17.44 review, whose
    authority "may impose any conditions": YELLOW, as Happy Valley's steep
    slopes overlay is (ruling 2026-10-14-review-tiers)."""
    area = BY_KEY["oregon_city_geohazard"]
    assert "17.44.025" in area.cite and area.column in S5O_COLUMNS
    inside = lot_from_row(row(jurisdiction="oregon_city", ovl_oregon_city_geohazard=True)).facts
    assert inside.resource_permits == ("oregon_city_geohazard",)
    got = run(lot=replace(LOT, resource_permits=inside.resource_permits))
    assert got.triage is Triage.yellow and got.colour is flag_plan.Colour.yellow
    assert got.reasons == (CLOSER_LOOK_RESOURCE,)
    slope = run(lot=replace(LOT, resource_permits=("happy_valley_slope",)))
    assert (slope.triage, slope.colour) == (got.triage, got.colour)
    # clear of the overlay, and a row s5o wrote before the layer existed: nothing said
    clear = lot_from_row(row(jurisdiction="oregon_city", ovl_oregon_city_geohazard=False)).facts
    assert clear.resource_permits == ()
    assert lot_from_row(row(jurisdiction="oregon_city")).facts.resource_permits == ()


def test_the_geologic_hazards_review_quotes_its_sentences() -> None:
    store = ProvenanceStore()
    doc = "or/clackamas/oregon-city/17.zoning.txt"
    trigger = " ".join(store.quote(f"{doc}#L10778-L10786").split())
    assert "on a property that contains an area mapped within the adopted Oregon City Geologic Hazards Overlay Zone" in trigger
    density = " ".join(store.quote(f"{doc}#L11121-L11142").split())
    assert "the density shall not exceed two dwelling units per acre" in density
    assert "within any portion of the mapped landslide or buffer zone" in density
    assert "development shall be prohibited" in density


# --- Portland's Scenic Resource overlay (FOLLOWUPS 204 item 1) --------------


def test_portland_s_scenic_overlay_is_flagged_not_carved(quadfit_specs) -> None:
    """PCC 33.480: the setback is a street line's (test_scenic_corridor.py);
    the overlay itself only makes the lot a closer look."""
    spec = quadfit_specs["pdx_scenic"]
    assert spec["action"] == "flag" and spec["jurisdictions"] == ["portland"]
    assert "33.480.035" in spec["citation"]
    assert "pdx_scenic" in BY_KEY and "pdx_scenic" not in CLEARED
    held = load_pipeline().datasets["overlay_pdx_scenic"]
    assert held.url.endswith("/BPS_Zoning_Code_Layers/MapServer/137")


# --- Unincorporated Clackamas: landslides, the floodplain district and the
# --- open space of Map 4-06 (FOLLOWUPS 204) --------------------------------

COUNTY = "clackamas_unincorporated"
ZDO = "or/clackamas/_unincorporated"
OPEN_SPACE = "or/clackamas/_unincorporated/zdo-map-4-06-open-space.geojson"


@pytest.mark.parametrize(
    ("key", "layer"),
    [
        ("clackamas_landslide", "/SLIDO_Inventory/MapServer/11"),
        ("clackamas_landslide_scarp", "/SLIDO_Inventory/MapServer/3"),
    ],
)
def test_clackamas_s_mapped_landslides_carve_the_ground_and_flag_the_lot(quadfit_specs, key, layer) -> None:
    """ZDO 1003.02(A): no development in an area of land movement short of a
    Type II permit -- carved, as Oregon City's landslides are. A lot holding
    any of it whose pod stands clear still owes that permit -- flagged."""
    site, core = quadfit_specs[key], quadfit_specs[f"{key}_core"]
    assert site["action"] == "flag" and core["action"] == "carve"
    assert site["jurisdictions"] == core["jurisdictions"] == [COUNTY]
    assert core["source"] == key and core.get("buffer_ft", 0) == 0
    assert "keep_where" not in site and "keep_where" not in core
    assert "1003.02(A)" in site["citation"] and "1003.02(B)(5)" in site["citation"]
    assert "No development or grading shall be allowed" in core["citation"]
    assert key in BY_KEY and f"{key}_core" not in BY_KEY and f"{key}_core" not in CLEARED
    assert permits_on({f"ovl_{key}_core": True}) == ()
    held = load_pipeline().datasets[f"overlay_{key}"]
    assert held.url.endswith(layer) and held.bbox_4326 is not None
    assert list(held.serves) == ["or/clackamas/_unincorporated"]


def test_a_clackamas_lot_holding_a_mapped_landslide_is_a_closer_look() -> None:
    """22E08CA03200's case: a debris-flow fan across one end, the pod clear of
    it. The permit's conditions "may be attached by the County": YELLOW, the
    colour Oregon City's geologic hazards and Happy Valley's slopes give."""
    for key in ("clackamas_landslide", "clackamas_landslide_scarp"):
        area = BY_KEY[key]
        assert "1003.02(A)" in area.cite and area.column in S5O_COLUMNS
        inside = lot_from_row(row(jurisdiction=COUNTY, **{area.column: True})).facts
        assert inside.resource_permits == (key,)
        got = run(lot=replace(LOT, resource_permits=inside.resource_permits))
        assert got.triage is Triage.yellow and got.colour is flag_plan.Colour.yellow
        assert got.reasons == (CLOSER_LOOK_RESOURCE,)
        other = run(lot=replace(LOT, resource_permits=("oregon_city_geohazard",)))
        assert (other.triage, other.colour) == (got.triage, got.colour)
        assert lot_from_row(row(jurisdiction=COUNTY, **{area.column: False})).facts.resource_permits == ()
    assert lot_from_row(row(jurisdiction=COUNTY)).facts.resource_permits == ()


def test_the_mass_movement_rule_quotes_its_sentences() -> None:
    store = ProvenanceStore()
    doc = f"{ZDO}/zdo.1003.txt"
    bar = " ".join(store.quote(f"{doc}#L13").split())
    assert (
        "No development or grading shall be allowed in areas of land movement, slump or earth flow, "
        "or mud or debris flow, unless approved in a Type II application"
    ) in bar
    assert "a mass movement hazard area development permit is required" in bar
    assert (
        "Appropriate conditions of approval of development approved under this subsection may be "
        "attached by the County"
    ) in store.quote(f"{doc}#L19")
    assert "shall establish that the site is stable for the proposed use and development" in store.quote(f"{doc}#L21")
    source = " ".join(store.quote(f"{doc}#L47").split())
    assert (
        "The principal source of information for determining mass movement hazards is the State "
        "Department of Geology and Mineral Industries (DOGAMI) Bulletin 99 and accompanying maps"
    ) in source
    assert "to update the mass movement hazards data base" in source


def test_clackamas_s_floodplain_district_is_carved_and_the_fringe_flag_stays(quadfit_specs) -> None:
    """ZDO 845.01(3) prohibits the quadplex and the townhouse in the
    Floodplain Management District; 703.04 applies that district to FEMA's
    special flood hazard areas, and 703.05(J) makes paving and grading
    development. So the fringe is carved in the unincorporated county and
    nowhere else, and a lot it touches is still fema_sfha's closer look."""
    fmd, fringe = quadfit_specs["clackamas_fmd"], quadfit_specs["fema_sfha"]
    assert fmd["action"] == "carve" and fmd["source"] == "fema_sfha"
    assert fmd["jurisdictions"] == [COUNTY] and fmd.get("buffer_ft", 0) == 0
    assert fringe["action"] == "flag" and fringe["jurisdictions"] == "all"
    assert "fema_sfha" in BY_KEY and "clackamas_fmd" not in BY_KEY and "clackamas_fmd" not in CLEARED
    assert permits_on({"ovl_clackamas_fmd": True}) == ()
    others = [k for k, o in quadfit_specs.items() if o.get("source") == "fema_sfha" and o["action"] == "carve"]
    assert others == ["clackamas_fmd"]
    text = fmd["citation"]
    assert "845.01(3)" in text and "703.04" in text and "703.05(J)" in text
    store = ProvenanceStore()
    ban = " ".join(store.quote(f"{ZDO}/zdo.845.txt#L17").split())
    assert "quadplexes, townhouses, and cottage clusters" in ban
    assert "is prohibited in the Floodplain Management District" in ban
    reach = " ".join(store.quote(f"{ZDO}/zdo.703.txt#L47").split())
    assert (
        "Section 703 applies to the FMD, which is applied to the special flood hazard areas (SFHAs) "
        "identified by the Federal Insurance Administration"
    ) in reach
    development = " ".join(store.quote(f"{ZDO}/zdo.703.txt#L81").split())
    assert "buildings or other structures, mining, dredging, filling, grading, paving, excavation" in development


def _open_space():
    import json

    from shapely.geometry import shape

    from flats.rules.loader import AREAS_ROOT

    doc = json.loads((AREAS_ROOT / OPEN_SPACE).read_text(encoding="utf-8"))
    return doc, [(f["properties"], shape(f["geometry"])) for f in doc["features"]]


def test_clackamas_s_open_space_is_traced_off_map_4_06_and_says_how() -> None:
    """ZDO 1103.01 names three kinds of open space on Map IV-6; the county
    publishes no layer of it, so the file is the tracing and states how it
    was placed and how far off its edge can be."""
    [area] = [t for t in TRACED if t.key == "clackamas_open_space"]
    assert area.jurisdiction == COUNTY and area.file == OPEN_SPACE
    assert "1103.01" in area.cite and "1011.02" in area.cite
    assert area.unbuildable is True
    assert AREAS[area.key] is area and area.key not in BY_KEY
    assert set(AREAS) == set(BY_KEY) | {t.key for t in TRACED}
    doc, feats = _open_space()
    assert doc["drawn"] is True and "EPSG::2913" in doc["crs"]["properties"]["name"]
    assert {"map", "quote", "says", "traced", "placed", "edge", "not_held"} <= set(doc["source"])
    kinds: dict[str, list] = {}
    for props, geom in feats:
        assert geom.is_valid and not geom.is_empty
        kinds.setdefault(props["OS_CLASS"], []).append(props)
    assert {k: len(v) for k, v in kinds.items()} == {
        "major_hazard": 25,
        "resource_protection": 54,
        "public_community_use": 38,
    }
    # a traced line is 14 ft wide on the ground; the county's own polygons are not
    assert {p["EDGE_FT"] for k in ("major_hazard", "resource_protection") for p in kinds[k]} == {14}
    assert {p["EDGE_FT"] for p in kinds["public_community_use"]} == {0}
    store = ProvenanceStore()
    said = " ".join(store.quote(doc["source"]["quote"]).split())
    assert doc["source"]["says"] in said
    assert "applies to development that affects an open space resource described in Section 1011" in said
    plan = f"{ZDO}/zdo.1011.txt"
    assert "areas generally indicated as Open Space on Comprehensive Plan Map IV-6" in store.quote(f"{plan}#L3")
    assert "shall avoid disturbance of identified open space resources" in store.quote(f"{plan}#L65")
    assert "High-priority open space shall be preserved outright" in store.quote(f"{plan}#L67")
    assert "preserved to the maximum extent possible" in store.quote(f"{plan}#L73")


def test_a_clackamas_lot_touching_the_traced_open_space_is_a_closer_look() -> None:
    """Inside it, or within the 14 ft the drawn line is wide: Open Space
    Review, never GREEN. Clear of it, or another jurisdiction's lot: nothing."""
    import shapely
    from shapely.geometry import box

    from flats.ingest.quadfit import traced_permits_on

    _, feats = _open_space()
    traced = [g for p, g in feats if p["EDGE_FT"] == 14]
    everything = shapely.union_all([g for _, g in feats])
    east = max(traced, key=lambda g: g.bounds[2])
    x = east.bounds[2]
    y = next(c[1] for part in getattr(east, "geoms", [east]) for c in part.exterior.coords if c[0] == x)
    spot = east.representative_point()

    def lot(x0: float, y0: float, **over: object) -> dict[str, object]:
        over.setdefault("jurisdiction", COUNTY)
        return row(lot_wkb=shapely.to_wkb(box(x0, y0, x0 + 100, y0 + 50)), **over)

    inside = lot(spot.x - 50, spot.y - 25)
    beside = lot(x + 8, y - 25)  # 8 ft off the traced edge: inside the line's width
    clear = lot(x + 20, y - 25)  # 20 ft off: outside it
    assert everything.distance(shapely.from_wkb(beside["lot_wkb"])) == pytest.approx(8, abs=0.2)
    assert traced_permits_on(inside) == ("clackamas_open_space",)
    assert traced_permits_on(beside) == ("clackamas_open_space",)
    assert traced_permits_on(clear) == ()
    assert traced_permits_on(lot(spot.x - 50, spot.y - 25, jurisdiction="happy_valley")) == ()
    # a city lot the county's rules screen (a pocket) is reached through its home
    pocket = lot(spot.x - 50, spot.y - 25, jurisdiction="happy_valley", home_jurisdiction=COUNTY)
    assert traced_permits_on(pocket) == ("clackamas_open_space",)
    assert traced_permits_on(row(jurisdiction=COUNTY)) == ()  # no shape, nothing measured

    facts = lot_from_row(beside).facts
    assert facts.resource_permits == ("clackamas_open_space",)
    got = run(lot=replace(LOT, resource_permits=facts.resource_permits))
    assert got.triage is Triage.yellow and got.colour is flag_plan.Colour.yellow
    assert got.reasons == (CLOSER_LOOK_RESOURCE,)
    assert lot_from_row(clear).facts.resource_permits == ()
    # both together: a landslide column and the traced area
    both = lot_from_row({**inside, "ovl_clackamas_landslide": True}).facts
    assert both.resource_permits == ("clackamas_landslide", "clackamas_open_space")

    # Steph 2026-11-18 (rulings.yaml 2026-11-18-clackamas-open-space-red): the
    # traced ground, the 14 ft of its line included, comes off the lot the way
    # one of s5o's carves does -- nothing built or parked on it.
    from flats.geom.drawn import load_edged_area
    from flats.ingest.quadfit import traced_off

    [area] = [t for t in TRACED if t.key == "clackamas_open_space"]
    assert area.unbuildable is True
    edged = load_edged_area(OPEN_SPACE)
    strip = shapely.from_wkb(beside["lot_wkb"]).intersection(edged)
    assert 0 < strip.area < 100 * 50
    assert strip.bounds[2] == pytest.approx(x + 14, abs=0.3)  # 8 ft off, 14 ft wide: 6 ft of the lot
    held = lot_from_row(beside)
    assert held.traced is not None and held.traced.equals(strip)
    assert held.carve is not None and held.carve.equals(strip)  # s5o carved nothing on this row
    assert lot_from_row(inside).traced.area > strip.area
    nothing = lot_from_row(clear)
    assert nothing.traced is None and nothing.carve is None
    assert traced_off(lot(spot.x - 50, spot.y - 25, jurisdiction="happy_valley")) is None
    assert traced_off(pocket) is not None
    assert traced_off(row(jurisdiction=COUNTY)) is None
    # beside one of s5o's carves, the lot loses both
    far = box(x + 98, y + 15, x + 108, y + 25)
    two = lot_from_row({**beside, "carve_wkb": shapely.to_wkb(far)})
    assert two.traced.equals(strip) and two.carve.equals(far.union(strip))


def test_steph_s_rulings_of_2026_11_18_stand_behind_the_clackamas_carves(quadfit_specs) -> None:
    """Asked whether the county's flood ban, its landslide permit and its
    open space review made a lot RED or a closer look, Steph ruled all three
    RED where the building cannot stand clear, and YELLOW where the lot only
    holds the ground. The carves are what make the RED and the flags what
    keep the YELLOW; each names its ruling where it is declared, so none is
    read as a worker's judgement."""
    text = OVERLAYS.read_text(encoding="utf-8")
    slide, flood = "2026-11-18-clackamas-landslide-under-building-red", "2026-11-18-clackamas-flood-ban-red"
    space = "2026-11-18-clackamas-open-space-red"
    assert slide in text and flood in text
    for key in ("clackamas_landslide", "clackamas_landslide_scarp"):
        assert quadfit_specs[key]["action"] == "flag"  # holds some, building clear: YELLOW
        assert quadfit_specs[f"{key}_core"]["action"] == "carve"  # under the building: RED
        assert quadfit_specs[f"{key}_core"]["jurisdictions"] == [COUNTY]
    assert quadfit_specs["clackamas_fmd"]["action"] == "carve"
    assert quadfit_specs["clackamas_fmd"]["jurisdictions"] == [COUNTY]
    # the flood ruling is the county's use ban; the fringe is a flag everywhere
    assert quadfit_specs["fema_sfha"]["action"] == "flag"
    import flats.rules.resource_overlays as declared

    said = Path(declared.__file__).read_text(encoding="utf-8")
    assert slide in said and space in said
    # the open space is no quadfit overlay: the bridge takes its ground off
    assert not any("open_space" in key for key in quadfit_specs if key.startswith("clackamas"))
    assert [t.key for t in TRACED if t.unbuildable] == ["clackamas_open_space"]
    notes = (
        Path(__file__).resolve().parents[1] / "config" / "jurisdictions" / "or" / "clackamas" / "_unincorporated.yaml"
    ).read_text(encoding="utf-8")
    assert slide in notes and flood in notes and space in notes
