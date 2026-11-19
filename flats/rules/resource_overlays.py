"""Mapped stream, wetland, habitat and flood areas the code builds in only
with a permit -- each one a closer look, never a pass (FOLLOWUPS 42(b)/(c)).

quadfit's s5o lays every overlay in ``Lot Analysis/quadfit/config/overlays.yaml``
over the lots and records, per lot, whether it touches each one
(``ovl_<key>``). It gives each overlay one of three actions, read from the
city's code on 2026-07-27 and after:

* ``carve`` -- the code forbids building there. s5o takes the ground off the
  envelope (``carve_wkb``), and FLATS places the building on what is left.
* ``kill`` -- the code makes everything there a hearing. Portland's
  environmental zones are the z overlay's triggers (``constrained_sites_overlay``,
  33.418.030) and Milwaukie's Willamette Greenway is ``willamette_greenway_zone``;
  both are use rules in the corpus.
* ``flag`` -- the code lets a house go up there, with a permit, a report,
  mitigation planting or a raised floor. Nothing is taken off the lot.

Until 2026-10-05 FLATS read the third kind only as square feet a city's net
area may deduct, so a lot touching one passed GREEN with nothing said: 5,482
Washington County greens on mapped habitat, 1,756 in a Clean Water Services
corridor, 2,917 on Clackamas habitat, 1,099 in the FEMA flood fringe. Each
of those is a permit a builder has to get and price, so it is a closer look
(YELLOW), exactly as the planted strip and the 5-15% slope are. The flag
itself never takes ground. Phase 2 (2026-10-05) read each one's sentences
and, where the code forbids the pod inside the area -- a Clean Water Services
corridor, Milwaukie's and Gladstone's water quality areas, the Clackamas,
Milwaukie and Gladstone habitat caps, Wilsonville's SROZ, West Linn's
riparian corridors -- quadfit carves the same map under a ``*_core`` (or
``west_linn_rci_resource`` / ``west_linn_wra_riparian``) key as well. The
flag stays on the lot whose pod clears the area: the letter, the planting
and the plan are still owed.

Portland's three environmental zones sit here too. A lot the z covers is RED
on the use rule already; the few the city's z map leaves out while its
environmental-zone map touches them are a map disagreement, and a person
reads the lot rather than the screen picking a side. Since 2026-10-06 quadfit
also carves what 33.430 and 33.465 leave no building on (``pdx_ezone_*_core``:
the p resource area plus 5 ft, the c resource area, all of v), so the pod is
placed off it first. Portland's River Environmental overlay ("e", 33.475)
is carved whole the same way since 2026-11-18 (``pdx_river_e``): its one
by-right path for a house caps disturbance inside it at Table 475-4 less the
site outside it, and anything more goes to River Review. It is no z trigger,
so it carries no flag (CLEARED). Wood Village's WQR and HCA (WVDC 430.170) carve under the
Metro keys and are flagged under ``wood_village_*`` for the plan 430.190 asks.

The carves quadfit held before 2026-10-05 had no flag of their own, so a lot
whose pod cleared one passed GREEN with nothing said: 47 lots in the
2026-10-07 weekly, on Gresham's, Tualatin's and West Linn's no-build maps and
Troutdale's (FOLLOWUPS 50). Each city's sentence was read for what it asks of
a site that holds the area while the building stays out of it. Where it asks
for something -- a construction management plan or an exemption form, a
surveyed boundary, a delineation, the boundary on the application -- the same
map is flagged under a ``*_site`` key. Where it asks for nothing, the carve is
in CLEARED below with the sentence that says so.

Touch-only: quadfit's ``ovl_<key>`` is True when any part of the lot is in
the area. Several codes reach 25 to 100 ft past it (Wilsonville 4.139.05,
Milwaukie 19.402.3.A, Happy Valley 16.34.060, Gladstone 17.25.020(A)); a lot
inside that reach but outside the polygon is not flagged. That is the
under-reach overlays.yaml records for each of them.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Permit:
    """One mapped area a house goes up in only with a permit."""

    #: quadfit's overlay key; s5o's column is ``ovl_<key>``.
    key: str
    #: What the area is, said to somebody reading a lot page.
    words: str
    #: Where the code says so, as quadfit's overlays.yaml read it.
    cite: str

    @property
    def column(self) -> str:
        return f"ovl_{self.key}"


#: The state's own permit, which binds whatever a city's wetland map says
#: (FOLLOWUPS 42(d)): both DSL maps are laid over every jurisdiction.
_STATE_FILL = (
    "ORS 196.810(1)(a): removing material from or filling a wetland needs a Department of "
    "State Lands permit (wetlands are waters of this state, ORS 196.800(16)-(17); fill is "
    "50 cubic yards or more at one location, ORS 196.800(3))"
)

#: What a site holding the area owes while the building stays out of it
#: (FOLLOWUPS 50): Gresham asks for a plan within 50 ft and a form beyond it.
_GRESHAM_NRO = (
    "GDC 5.0703(A)(1) and 5.0706(A) (a construction management plan within 50 ft of the "
    "resource area, Type I); 5.0705(A)(3) (an NRO exemption form beyond 50 ft)"
)
_WEST_LINN_WRA = (
    "WLCDC 32.060 (an application for development on property containing a WRA meets the "
    "approval criteria); 32.020(B) (the owner's burden; a survey or delineation on request)"
)

#: Every quadfit overlay whose action is ``flag``, and Portland's three
#: environmental zones. ``flats/tests/test_resource_overlays.py`` holds this
#: list against overlays.yaml, so an overlay added there cannot go unread here.
PERMITS: tuple[Permit, ...] = (
    Permit(
        "pdx_ezone_p",
        "Portland environmental protection zone (p) the city's z map leaves out",
        "PCC 33.430; 33.418.030.A puts a z on every R20-R2.5 lot it touches",
    ),
    Permit(
        "pdx_ezone_c",
        "Portland environmental conservation zone (c) the city's z map leaves out",
        "PCC 33.430; 33.418.030.A puts a z on every R20-R2.5 lot it touches",
    ),
    Permit(
        "pdx_ezone_v",
        "Portland Pleasant Valley natural resource overlay (v) the city's z map leaves out",
        "PCC 33.418.030.A (z trigger)",
    ),
    Permit(
        "metro_wetlands",
        "a wetland on Metro's regional inventory",
        "DSL removal-fill applies to the wetland footprint itself (overlays.yaml metro_wetlands)",
    ),
    Permit(
        "wood_village_wqr",
        "a Wood Village water quality resource area (stream or wetland corridor)",
        "WVDC 430.190 (a Construction Management Plan before any permit in a WQRA); "
        "430.170.A forbids new structures inside it",
    ),
    Permit(
        "wood_village_hca",
        "a Wood Village habitat conservation area",
        "WVDC 430.140.A and 430.210.A(7) (the HCA marked and kept undisturbed through "
        "construction); 430.170.A forbids new structures inside it",
    ),
    Permit(
        "dsl_lwi_wetlands",
        "a wetland on the state's approved local wetland inventory",
        _STATE_FILL,
    ),
    Permit(
        "dsl_nwi_wetlands",
        "a wetland or pond on the National Wetlands Inventory",
        _STATE_FILL,
    ),
    Permit(
        "washington_cws_corridor",
        "a Clean Water Services vegetated corridor beside a stream or wetland",
        "Clean Water Services Design and Construction Standards, Chapter 3: a Service Provider "
        "Letter, an alternatives analysis and mitigation (Metro Title 3 map as proxy)",
    ),
    Permit(
        "washington_habitat",
        "mapped Goal 5 habitat",
        "Metro Title 13 as each Washington County jurisdiction applies it through its own Goal 5 "
        "overlay (Metro's map as proxy)",
    ),
    Permit(
        "hillsboro_snro",
        "a Hillsboro significant natural resource site or its impact area",
        "Hillsboro CDC 12.27.220.A.9.b (a written verification of exemption, boundaries "
        "verified and fenced) or 12.27.220.B (a Significant Natural Resource Permit)",
    ),
    Permit(
        "clackamas_hca",
        "a Clackamas County habitat conservation area",
        "ZDO 706.05 prohibits no dwelling; 706.06/706.10 require an HCA development permit",
    ),
    Permit(
        "clackamas_wqra",
        "a Clackamas County water quality resource area",
        "ZDO 709.05 prohibits no dwelling; 709.06/709.10 require a construction management plan "
        "and a WQRA development permit",
    ),
    Permit(
        "west_linn_rci",
        "a riparian corridor on West Linn's water resource map",
        "WLCDC 32.120(A); Table 32-2 row D",
    ),
    Permit(
        "west_linn_flood",
        "West Linn's flood management area",
        "WLCDC 27.020 (a flood management area permit) and 27.070/27.080 (floor elevation)",
    ),
    Permit(
        "wilsonville_sroz",
        "Wilsonville's Significant Resource Overlay Zone or its 25 ft impact area",
        "WDC 4.139.02 (a Significant Resource Impact Report); 4.139.03(.04)",
    ),
    Permit(
        "happy_valley_nroz",
        "Happy Valley's Natural Resources Overlay Zone",
        "HV LDC 16.34.060 (further environmental review; map verification)",
    ),
    Permit(
        "happy_valley_slope",
        "Happy Valley's Steep Slopes Development Overlay Zone",
        "HV LDC 16.32.020 and 16.34.060 (a review trigger)",
    ),
    Permit(
        "milwaukie_hca",
        "a Milwaukie habitat conservation area",
        "MMC 19.402.5.A; Table 19.402.3.K (Type I review, 19.402.11.D mitigation planting)",
    ),
    Permit(
        "milwaukie_wqr",
        "a Milwaukie water quality resource (vegetated corridor)",
        "MMC 19.402.5.A; Table 19.402.3.K and 19.402.6.B (limited disturbance, Type I review)",
    ),
    Permit(
        "milwaukie_wetlands",
        "a wetland on Milwaukie's inventory",
        "MMC 19.402.3.A and 19.402.3.D.2",
    ),
    Permit(
        "gladstone_hca",
        "a Gladstone habitat conservation area",
        "GMC 17.25.060 (an HCA development permit); 17.25.100 Table 3 caps the disturbance area",
    ),
    Permit(
        "gladstone_wq",
        "a Gladstone water quality resource area",
        "GMC 17.27.040(3)(a) (subject to review) and 17.27.045(1)(a) (no practicable alternative)",
    ),
    Permit(
        "tualatin_wfa",
        "Tualatin's Wetlands Fringe Area",
        "TDC 71.030 and 71.040(1) (an Oregon-licensed engineer's certification)",
    ),
    Permit(
        "tualatin_stream_piped",
        "a piped stream on Tualatin's map",
        "TDC 72.040(3)(a)-(b) measure the buffer from a top of bank a pipe does not have",
    ),
    Permit(
        "gresham_hcra_site",
        "a Gresham natural resource area on the site (the building is kept out of it)",
        _GRESHAM_NRO,
    ),
    Permit(
        "gresham_wetlands_site",
        "a Gresham wetland or its 50 ft buffer on the site (the building is kept out of it)",
        _GRESHAM_NRO,
    ),
    Permit(
        "troutdale_veco_site",
        "Troutdale's vegetation corridor or steep slope district on the site (the building is kept out of it)",
        "TDC 4.311(A) (the boundary set at the development proposal by a licensed surveyor's "
        "topographic and slope analysis, and a wetland delineation if applicable)",
    ),
    Permit(
        "fairview_nrl_site",
        "a Fairview creek or wetland protection area on the site (the building is kept out of it)",
        "FMC 19.106.070(A) (a Type I boundary verification unless the site plan shows the building "
        "more than 40 ft from the mapped area)",
    ),
    Permit(
        "west_linn_wra_stream_site",
        "a West Linn stream water resource area on the property (the building is kept out of it)",
        _WEST_LINN_WRA,
    ),
    Permit(
        "west_linn_wra_ephemeral_site",
        "a West Linn ephemeral stream water resource area on the property (the building is kept out of it)",
        _WEST_LINN_WRA,
    ),
    Permit(
        "west_linn_wra_riparian_site",
        "a West Linn riparian corridor stream area on the property (the building is kept out of it)",
        _WEST_LINN_WRA,
    ),
    Permit(
        "west_linn_wetlands_site",
        "a West Linn wetland water resource area on the property (the building is kept out of it)",
        _WEST_LINN_WRA,
    ),
    Permit(
        "tualatin_nrpo_site",
        "a Tualatin greenway or natural area on the site (the building is kept out of it)",
        "TDC 72.040(3)(c) (the boundary, a wetland delineation, top of bank, topography and a "
        "vegetation inventory on the application); 72.060(3) (building setback as a condition)",
    ),
    Permit(
        "tualatin_stream_buffer_site",
        "a Tualatin 50 ft stream buffer on the site (the building is kept out of it)",
        "TDC 72.040(3)(c) (the boundary, a wetland delineation, top of bank, topography and a "
        "vegetation inventory on the application)",
    ),
    Permit(
        "fema_sfha",
        "the FEMA 100-year flood area outside the floodway",
        "fringe building stays by right with elevation and fill standards (Gresham GDC 5.0120, "
        "Troutdale TDC Ch 14, MCC 39.5030, PCC 24.50; West Linn 27.070)",
    ),
    # Portland's own flood map beside FEMA's (FOLLOWUPS 202, 2026-11-18): the
    # same conditions, so the same closer look, under its own key so a lot
    # says which map put it there.
    Permit(
        "pdx_flood_1996",
        "Portland's 1996 flood area (the City's Composite February 1996 Flood Inundation Area)",
        "PCC 24.50.040 E adopts the map; 24.50.050 J sets the flood protection elevation 2 ft "
        "above the 1996 flood (1 ft by the Columbia); 24.50.060 F.2.a lowest floor at or above it, "
        "G.2.c 1:1 compensating excavation for fill",
    ),
    # Portland's Scenic Resource overlay "s" (FOLLOWUPS 204 item 1,
    # 2026-11-18). The scenic corridor setback is drawn per street line
    # (setback_scenic_corridor_ft); the chapter's other standards are not
    # measured, so the lot is a closer look whether or not the pod clears it.
    Permit(
        "pdx_scenic",
        "Portland's Scenic Resource overlay zone (s)",
        "PCC 33.480.035 (any development within the zone); 33.480.040.B.2 (the scenic corridor "
        "setback, structure length, landscaped setback and the trees in it); 33.480.040.A.2.a "
        "(view corridor height limits); 33.480.050 (tree review)",
    ),
    # Oregon City's Geologic Hazards Overlay (FOLLOWUPS 204 item 2,
    # 2026-11-18): the review reaches the whole property, so a pod standing
    # clear of the carved landslide and slope ground still owes it. A
    # measurable review that may add conditions (Steph 2026-10-14), held as
    # happy_valley_slope is.
    Permit(
        "oregon_city_geohazard",
        "Oregon City's Geologic Hazards Overlay Zone",
        "OCMC 17.44.025 (a property that contains a mapped area needs the chapter's approval); "
        "17.44.050 (geotechnical report); 17.44.060.I.2 (graded and covered ground capped at half "
        "the lot or 4,000 sq ft); 17.44.060.L (the review authority may impose conditions)",
    ),
    # Clackamas County's mass movement hazard areas (FOLLOWUPS 204,
    # 2026-11-18), held as Oregon City's geologic hazards are: the mapped
    # landslide ground is carved, and a lot holding any of it whose pod stands
    # clear still owes a permit the county may attach conditions to (Steph
    # 2026-10-14). Steph ruled both halves 2026-11-18 (rulings.yaml
    # 2026-11-18-clackamas-landslide-under-building-red): RED when the
    # building cannot be fitted clear of the mapped ground, YELLOW when the
    # lot holds some and the building fits clear. Two of DOGAMI's layers, so
    # two areas.
    Permit(
        "clackamas_landslide",
        "a landslide deposit on the state's landslide map (Clackamas County mass movement hazard area)",
        "ZDO 1003.02(A) (a mass movement hazard area development permit for development in areas "
        "of land movement, slump or earth flow, or mud or debris flow); 1003.02(B)(2)-(3) (an "
        "engineering geologic study that establishes the site is stable; the county may attach "
        "conditions); 1003.02(B)(5) (DOGAMI's maps the principal source)",
    ),
    Permit(
        "clackamas_landslide_scarp",
        "a landslide scarp on the state's landslide map (Clackamas County mass movement hazard area)",
        "ZDO 1003.02(A) (a mass movement hazard area development permit for development in areas "
        "of land movement, slump or earth flow, or mud or debris flow); 1003.02(B)(2)-(3) (an "
        "engineering geologic study that establishes the site is stable; the county may attach "
        "conditions); 1003.02(B)(5) (DOGAMI's maps the principal source)",
    ),
)

BY_KEY: Mapping[str, Permit] = {p.key: p for p in PERMITS}


@dataclass(frozen=True, slots=True)
class Traced:
    """A permit area nobody publishes as data, traced here off the adopted
    map and read against the lot's own shape by the bridge
    (:func:`flats.geom.drawn.touches_area`) -- quadfit measures nothing for
    it, so it has no ``ovl_`` column and is not one of :data:`PERMITS`."""

    key: str
    words: str
    cite: str
    #: quadfit's jurisdiction key whose lots it reaches.
    jurisdiction: str
    #: The tracing, under ``flats/config/areas``; the file states how it was
    #: made and how far off its edge can be (``EDGE_FT`` per feature).
    file: str
    #: The standing ruling (its id in ``flats/config/rulings.yaml``) under
    #: which a lot that touches the traced area is RED outright, whatever
    #: would fit beside it; '' where touching is only a closer look. A lot
    #: within the tracing's ``EDGE_FT`` of the traced line, on either side of
    #: it, is the closer look either way: the tracing cannot say whether it
    #: touches.
    red_ruling: str = ""


#: Clackamas County's open space (FOLLOWUPS 204, ZDO 1011 and 1103 read whole
#: 2026-11-18). 1103.01: Open Space Review "applies to development that
#: affects an open space resource described in Section 1011 ... and shown
#: generally on Comprehensive Plan Map IV-6 ... as Resource Protection, Major
#: Hazards, or Public and Community Use Open Space" -- a Type II review that
#: weighs "the probable impact of the proposed development" and identifies
#: "alternative development proposals" (1103.02). The county publishes no
#: layer of it, so Map 4-06 is traced (the file says how, and that its edge
#: is good to 14 ft).
#:
#: The text leaves two things open. 1011.02(B) preserves "outright" only the
#: high-priority open space, which turns on the resource present (wetland,
#: land movement, slope over 35 percent) and not on the map's class; and
#: Table 1001-1 does not apply Section 1011 to a quadplex or townhouse in the
#: R and VR districts at all (zdo.1001, the two middle-housing rows), where
#: 1103.01 still states its own reach. Steph ruled both 2026-11-18
#: (rulings.yaml 2026-11-18-clackamas-open-space-red): "if its free of mapped
#: open space, it's available to be green. If it's touching open space, it's
#: a red. We aren't fighting on developing open space." So in every zone, the
#: standard residential zones included:
#:
#: * a lot the traced open space plainly reaches is RED outright, whatever
#:   would fit beside it (``red_ruling``;
#:   :data:`flats.score.screen.MAPPED_OPEN_SPACE`);
#: * a lot clear of it carries nothing from this rule.
#:
#: Whether a lot touches is a question of fact, and the tracing answers it
#: only to the 14 ft its drawn line is wide (coordinator 2026-11-18, for
#: Steph to overrule). So "plainly" is an overlap deeper than 14 ft, into
#: the lot or into the open space (:func:`flats.geom.drawn.reaches_past_edge`);
#: and a lot within 14 ft of the traced line on either side -- a strip of
#: overlap along a lot line no deeper than that, or a gap no wider -- is the
#: closer look (YELLOW): the map only just reaches the lot line, or only
#: just misses it, and a person must look. The county's own Public and
#: Community Use polygons are held to the same 14 ft on the inside (three
#: neighbouring lots overlap one by the same 2.1 ft strip, so that layer and
#: the tax lots do not agree to the foot); they carry no band outside.
#: Before any of it the lot loses a 0.5 ft rim
#: (:data:`flats.geom.drawn.TOUCH_SHRINK_FT`), as for every overlay flag.
TRACED: tuple[Traced, ...] = (
    Traced(
        "clackamas_open_space",
        "the open space on Clackamas County's Comprehensive Plan Map 4-06 only just reaches "
        "this lot's line, or stops just short of it -- by less than the 14 ft width of the line "
        "the map draws it with, so the map cannot say whether the lot touches it and a person "
        "must look; a lot it plainly reaches into is red (Steph 2026-11-18)",
        "ZDO 1103.01 (Open Space Review for development that affects an open space resource "
        "shown on Map IV-6 as Resource Protection, Major Hazards, or Public and Community Use "
        "Open Space); 1103.02 (Type II; impact evaluated, alternatives identified); 1011.02(A)-(C) "
        "(development shall avoid disturbance of identified open space resources; high-priority "
        "open space preserved outright, second-priority to the maximum extent possible)",
        jurisdiction="clackamas_unincorporated",
        file="or/clackamas/_unincorporated/zdo-map-4-06-open-space.geojson",
        red_ruling="2026-11-18-clackamas-open-space-red",
    ),
)

#: Every area a RESOURCE-PERMIT flag can name, measured or traced.
AREAS: Mapping[str, Permit | Traced] = {**BY_KEY, **{t.key: t for t in TRACED}}

#: quadfit flag overlays measured for something else and read as nothing here,
#: each with the sentence that releases it. West Linn's piped streams stay on
#: the WRA Map and in its net-area deduction, but the chapter exempts them.
EXEMPT: Mapping[str, str] = {
    "west_linn_wra_piped": (
        "WLCDC 32.040(F) Exempt areas: '2. Existing enclosed or piped sections of streams, "
        "including any development at right angles to the enclosed or piped sections.'"
    ),
}

#: quadfit carves whose code asks nothing of a site while the building stays
#: out of the area, each with the sentence that confines it (FOLLOWUPS 50).
#: The carve still takes the ground; nothing else is owed, so no flag.
CLEARED: Mapping[str, str] = {
    "gresham_hillside": (
        "GDC 5.0203(A): the regulations apply 'when the following regulated activities are "
        "proposed within the boundaries of the Hillside and Geologic Risk Overlay (HGRO)'"
    ),
    "oregon_city_nrod": (
        "OCMC 17.49.030(1): 'This chapter applies to all development within the natural "
        "resources overlay district'; 17.49.060(B)(2): 'The requirements of this chapter apply only "
        "to areas within the NROD'"
    ),
    "tualatin_wpd_nobuild": (
        "TDC 71.040(1): the engineer's certification is for buildings 'upon lands lying within "
        "the Wetlands Protection District'; the fringe half is flagged as tualatin_wfa"
    ),
    "fema_floodway": (
        "the floodplain chapters regulate development within the flood area (GDC 5.0110: "
        "'any proposal for development within the Floodplain Overlay District'); the fringe "
        "around a floodway is flagged as fema_sfha"
    ),
    # Portland's River Environmental overlay (FOLLOWUPS 202, 2026-11-18). Not
    # a z trigger (33.418.030.A names c, p and Pleasant Valley only), so no use
    # rule and no map-disagreement flag reach it; the one standard a house
    # meets by right (440.O) caps disturbance inside "e" only.
    "pdx_river_e": (
        "PCC 33.475.440: 'the standards in this Section apply to development, exterior "
        "alterations, and land divisions in the River Environmental overlay zone'; 440.O.1: "
        "'The maximum disturbance area allowed within the River Environmental overlay zone on "
        "the site'; 33.475.050.A: supplemental site plans 'when a permit for development or "
        "exterior alteration within the River Overlay zones is reviewed'"
    ),
}

#: s5o's columns the bridge reads for these.
COLUMNS: tuple[str, ...] = tuple(p.column for p in PERMITS)


def permits_on(row: Mapping[str, Any]) -> tuple[str, ...]:
    """The keys of every permit area this stage-file row touches.

    A column the s5o file lacks, or a null, says nothing, as everywhere in
    the bridge; s5o writes these as plain booleans for every lot (False
    outside the overlay's jurisdictions), so a run on a current s5o never
    meets one.
    """
    out = []
    for p in PERMITS:
        value = row.get(p.column)
        if value is None or isinstance(value, float) and math.isnan(value):
            continue
        if bool(value):
            out.append(p.key)
    return tuple(out)


__all__ = [
    "AREAS", "BY_KEY", "CLEARED", "COLUMNS", "EXEMPT", "PERMITS", "Permit", "TRACED", "Traced", "permits_on",
]
