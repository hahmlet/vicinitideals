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
placed off it first. Wood Village's WQR and HCA (WVDC 430.170) carve under the
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
)

BY_KEY: Mapping[str, Permit] = {p.key: p for p in PERMITS}

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


__all__ = ["BY_KEY", "CLEARED", "COLUMNS", "EXEMPT", "PERMITS", "Permit", "permits_on"]
