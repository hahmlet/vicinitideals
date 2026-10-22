"""Two Portland map overlays the zoning letters on a lot do not carry
(FOLLOWUPS 78, found by the 2026-10-14 sample).

**The Centers Main Street overlay ("m", PCC 33.415).** 33.415.310 sets a
minimum floor area ratio on "all new development": 0.5 to 1 in the Inner
Pattern Area, 0.25 to 1 in the Eastern and Western Pattern Areas (Map 415-1).
The pod's floor area is fixed (4,032 sf for the 56 x 36 pod, two storeys), so
past 8,064 sf of lot in the Inner area, or 16,128 sf in the Eastern and
Western, the pod is too little building and the lot is RED. The code names no
minimum for the River and Central City pattern areas, and states none: silence
is none. A lot no pattern area answers takes the Inner 0.5, the worst case.
A lot only partly in the overlay is measured on that part: PCC 33.700.070.F,
"When a site is in more than one zone, the development standards of each zone
apply to the portion of the site in that zone" (``CITES["split_site"]``), and
the minimum FAR is one of 33.415's development regulations. Only the floor
area standing on that part counts toward it: the pod's floor area times the
share of the drawn building's footprint inside the overlay, in the placement
the screen chose. A pod drawn wholly off the overlay leaves the part at an FAR
of 0, and a plan with no drawing credits nothing -- never the whole pod
against a part it may not stand on. A part over ``1 - MAIN_STREET_SHARE`` of
the lot is the whole lot (map noise).

**Protected historic resources (PCC 33.445).** Steph ruled 2026-10-14: a lot
carrying a protected historic building is RED -- a Historic, Conservation or
National Register Landmark, or a contributing resource in a Historic or
Conservation District. Demolishing any of them needs demolition review
(33.445.100.E, 110.E, 120.E, 200.E, 210.E), a hearing nobody can count on.
Every other existing building stays green (a separate ruling). A contributing
resource in a National Register District (Eastmoreland) is protected the same
way: 33.445.220.E.1 puts its demolition under demolition review, and E.3 lets
the permit issue only "if the review body approves" -- a discretionary
review, not a delay or a notice period, so it is RED under the standing
ruling (coordinator 2026-10-15, ``NR_DISTRICT_RED``). The voluntary historic
resource review of 220.D/E.2.d exempts alterations only, never a total
demolition. It stays on its own row field, ``pdx_nr_district_resource``.

What is read per lot, off the acquire snapshot (``flats/config/pipeline.yaml``):

* :data:`MAIN_STREET_KEY` -- the zoning polygons whose ``OVRLY`` letters hold
  an ``m`` token. The lot is in the overlay where at least
  :data:`MAIN_STREET_SHARE` of it is: a thinner edge is the city's zoning
  polygons and the county's taxlots disagreeing, the same 10 % the split-zone
  reading takes as map noise.
* :data:`PATTERN_KEY` -- Map 415-1's pattern areas, every one holding at least
  :data:`PATTERN_SHARE` of the lot; the strictest minimum among them governs.
* :data:`RESOURCE_KEY` -- the city's district status layer, one polygon per
  resource drawn on the city's taxlots, and :data:`LANDMARK_KEY` -- the
  landmark building footprints. A resource is on the lot where their overlap
  is at least :data:`RESOURCE_SHARE` of the smaller of the two: a footprint
  standing on the lot, or a resource polygon that is the lot, but never a
  neighbour's edge.

**The rest of the Centers Main Street overlay (FOLLOWUPS 109).** Three more
of 33.415's development regulations reach the pod, and each turns on a
*transit street* -- a street the Transportation System Plan classes as a
Major Transit Priority, Transit Access or Community Transit Street (33.910).
No snapshot holds that classification, so every street of the lot is taken as
one, the worst case, and a miss is YELLOW (the street may not be one), never
RED:

* 33.415.300.B bars "Houses, attached houses, and duplexes" within 100 ft of
  a transit street. The apartment form is a fourplex, which the list leaves
  out. The townhouse form is four homes each on its own lot -- attached
  houses, unless the lots come from a middle housing land division (33.910's
  definition carves those out), and which way the plat goes is not known, so
  the townhouse form on an "m" lot carries :data:`MAIN_STREET_TRANSIT_FLAG`.
* 33.415.330.B caps the frontage "used for vehicle areas" (33.910: "All the
  area on a site where vehicles may circulate or park including parking
  areas, driveways") on any transit street: 30 % in the Inner pattern area,
  50 % in the Eastern and Western. The lane and the court of the drawn plan
  are laid against every street the way :func:`flats.fit.frontage.street_runs`
  reads parking; a share over the cap, or no drawing, raises
  :data:`MAIN_STREET_VEHICLE_FLAG`. River and Central City state no cap.
* 33.415.320 (Inner pattern area only): at least 70 % of the length of the
  ground level street-facing facade (33.910: the wall planes "at an angle of
  45 degrees or less from a street lot line") must meet the base zone's
  maximum building setback. Read on the drawn building against the zone's
  ``setback_front_max_ft`` on every street; a miss, no drawing, or a zone
  whose maximum is not read raises :data:`MAIN_STREET_SETBACK_FLAG` -- the
  pod could be stood forward, so not RED.

**Historic and Conservation Districts (33.445, the 2026-10-14 review
tiers).** Building a new structure in a Historic District or a Conservation
District needs historic resource review (33.445.200.D.1.b, 210.D.1.b), on
criteria such as "will be compatible with the massing, size, scale, and
architectural features of ... the district as a whole" (33.846.060.G.8):
essentially judgement, so a lot in a Historic District is RED
(:data:`HISTORIC_REVIEW_CHECK`), whatever stands on it. A Conservation
District offers a clear and objective alternative, the Community Design
Standards (33.445.500, 33.218), except in the Central City plan district
(33.445.510.A, RED there). Those standards place the building and its
parking -- the front setback matched to the neighbours' and never more than
25 ft back, the car in off an alley where there is one -- and the screen
measures none of it, so the lot is YELLOW with
:data:`COMMUNITY_DESIGN_FLAG`. A National Register District needs no review
for new development (33.445.220.D). ORS 197A.400's clear and objective rule
excepts historic areas, so the review is never lifted to GREEN here (the
2026-10-15 ruling's exception). District membership is read off the same
district status polygons, every status, non-contributing included.

**The Design overlay ("d", 33.420).** New development needs the design
standards or design review (33.420.041), but four homes of Household Living
no taller than 35 ft are exempt outside RX, EX and CX (33.420.045.A.2), and
the chapter does not reach a Historic or Conservation District (33.420.025).
RX and CX carry the overlay everywhere (33.120.030.E, 33.130.030.F); EX is
taken as carrying it (no map of the letter is read beside the base zone; all
EX lots are red today on other grounds). In the Central City plan district the
design standards may not be used (33.420.050.B.1), and design review is
approval on "the design guidelines for the area" (33.825.055): judgement, so
RED (:data:`DESIGN_REVIEW_CHECK`). Elsewhere the design standards are the
clear and objective track (residential floor area has no size limit, Table
420-1 note [1]) and the lot keeps its colour with
:data:`DESIGN_STANDARDS_FLAG` below the yellow line (Steph 2026-10-14: an
unchecked measurable design detail does not block green). The Central City
plan district is read as Map 415-1's Central City pattern area: on the
city's own maps that area is the plan district plus one 0.5-million-sf
neighbour (CCSA), to within 4 sf -- a little wider, never narrower.

The reading rides on the bridge row as :data:`ROW_KEY` (JSON) and on the lot
as ``QuadfitLot.pdx_overlays``; :func:`checked` turns it into binds and
flags.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flats.score import flags as flag_plan

MAIN_STREET_KEY = "overlay_pdx_main_street"
PATTERN_KEY = "pdx_pattern_areas"
RESOURCE_KEY = "pdx_historic_resources"
LANDMARK_KEY = "pdx_landmark_footprints"
KEYS: tuple[str, ...] = (MAIN_STREET_KEY, PATTERN_KEY, RESOURCE_KEY, LANDMARK_KEY)

#: The bridge jurisdictions Portland's zoning map answers: the city and the
#: unincorporated pockets it administers under Title 33 (as ``Z_ANSWERS``).
ANSWERS: frozenset[str] = frozenset({"portland", "multnomah_unincorporated"})

#: The row key the reading rides on.
ROW_KEY = "pdx_overlays_json"

MAIN_STREET_SHARE = 0.10
PATTERN_SHARE = 0.01
RESOURCE_SHARE = 0.5

#: 33.415.310, by Map 415-1's label. River and Central City are absent: the
#: section names no minimum there.
MIN_FAR: Mapping[str, float] = {"Inner": 0.5, "Eastern": 0.25, "Western": 0.25}
#: Where no pattern area answers the lot: the strictest stated.
MIN_FAR_UNMEASURED = 0.5

#: Status values (``Status``, the overriding one) of a protected resource.
PROTECTED_STATUS: frozenset[str] = frozenset(
    {"contributing", "historic landmark", "conservation landmark", "national register landmark"}
)
_LANDMARKS = frozenset({"historic landmark", "conservation landmark", "national register landmark"})

#: Whether a contributing resource in a National Register District reds the
#: lot: yes. 33.445.220.E.1 puts its demolition under demolition review and
#: E.3 issues the permit only if the review body approves -- discretionary, so
#: protected under Steph's 2026-10-14 rule (``CITES["nr_district_approval"]``).
NR_DISTRICT_RED = True

#: 33.415.330.B's cap on the share of any transit street frontage used for
#: vehicle areas, percent, by Map 415-1's label. River and Central City are
#: absent: the section states none there.
VEHICLE_AREA_CAP_PCT: Mapping[str, float] = {"Inner": 30.0, "Eastern": 50.0, "Western": 50.0}
#: Where no pattern area answers the lot: the strictest stated.
VEHICLE_AREA_CAP_UNMEASURED = 30.0
#: 33.415.320: the share of the street-facing facade that must meet the base
#: zone's maximum building setback, in the Inner pattern area.
SETBACK_FACADE_PCT = 70.0
#: 33.910 "Street-facing Facade": wall planes at 45 degrees or less from a
#: street lot line.
FACADE_ANGLE_DEG = 45.0
#: Drawn rings are rounded to a tenth of a foot.
DRAWN_TOL_FT = 0.5

#: Map 415-1's label for the Central City, read as the plan district.
CENTRAL_CITY = "Central City"
#: 33.420.045.A.2.d: the zones the Household Living exemption leaves out.
DESIGN_ZONES: frozenset[str] = frozenset({"RX", "EX", "CX"})
#: 33.420.045.A.2.b and c.
DESIGN_EXEMPT_UNITS = 4
DESIGN_EXEMPT_HEIGHT_FT = 35.0
#: 33.420.050.B.2.a (Gateway) and B.3 (everywhere): the design standards may
#: not be used past these heights.
GATEWAY_STANDARDS_HEIGHT_FT = 35.0
STANDARDS_HEIGHT_FT = 75.0

#: District kinds, from the district's name.
HISTORIC = "historic"
CONSERVATION = "conservation"
NATIONAL_REGISTER = "nr"

#: Screen reasons (said in words in ``app/api/routers/ui_flats.py``).
MIN_FAR_REASON = "PDX_MAIN_STREET_MIN_FAR"
PROTECTED_RESOURCE_REASON = "PDX_PROTECTED_RESOURCE"
HISTORIC_REVIEW_REASON = "PDX_HISTORIC_REVIEW"
DESIGN_REVIEW_REASON = "PDX_DESIGN_REVIEW"
MAIN_STREET_TRANSIT_REASON = "PDX_MAIN_STREET_TRANSIT"
MAIN_STREET_VEHICLE_REASON = "PDX_MAIN_STREET_VEHICLE_AREA"
MAIN_STREET_SETBACK_REASON = "PDX_MAIN_STREET_SETBACK"
COMMUNITY_DESIGN_REASON = "PDX_COMMUNITY_DESIGN_STANDARDS"
DESIGN_STANDARDS_REASON = "PDX_DESIGN_STANDARDS"
REASONS: tuple[str, ...] = (
    MIN_FAR_REASON,
    PROTECTED_RESOURCE_REASON,
    HISTORIC_REVIEW_REASON,
    DESIGN_REVIEW_REASON,
    MAIN_STREET_TRANSIT_REASON,
    MAIN_STREET_VEHICLE_REASON,
    MAIN_STREET_SETBACK_REASON,
    COMMUNITY_DESIGN_REASON,
    DESIGN_STANDARDS_REASON,
)
#: The binds' check names.
MIN_FAR_CHECK = "pdx_min_far"
PROTECTED_RESOURCE_CHECK = "pdx_protected_resource"
HISTORIC_REVIEW_CHECK = "pdx_historic_review"
DESIGN_REVIEW_CHECK = "pdx_design_review"
CHECKS: tuple[str, ...] = (
    MIN_FAR_CHECK, PROTECTED_RESOURCE_CHECK, HISTORIC_REVIEW_CHECK, DESIGN_REVIEW_CHECK
)
_BIND_REASON: Mapping[str, str] = {
    MIN_FAR_CHECK: MIN_FAR_REASON,
    PROTECTED_RESOURCE_CHECK: PROTECTED_RESOURCE_REASON,
    HISTORIC_REVIEW_CHECK: HISTORIC_REVIEW_REASON,
    DESIGN_REVIEW_CHECK: DESIGN_REVIEW_REASON,
}
#: The flag types (``flats/config/flags.yaml``), each with its reason.
MAIN_STREET_TRANSIT_FLAG = "PDX-MAIN-STREET-TRANSIT"
MAIN_STREET_VEHICLE_FLAG = "PDX-MAIN-STREET-VEHICLE-AREA"
MAIN_STREET_SETBACK_FLAG = "PDX-MAIN-STREET-SETBACK"
COMMUNITY_DESIGN_FLAG = "PDX-COMMUNITY-DESIGN-STANDARDS"
DESIGN_STANDARDS_FLAG = "PDX-DESIGN-STANDARDS"
FLAGS: Mapping[str, str] = {
    MAIN_STREET_TRANSIT_FLAG: MAIN_STREET_TRANSIT_REASON,
    MAIN_STREET_VEHICLE_FLAG: MAIN_STREET_VEHICLE_REASON,
    MAIN_STREET_SETBACK_FLAG: MAIN_STREET_SETBACK_REASON,
    COMMUNITY_DESIGN_FLAG: COMMUNITY_DESIGN_REASON,
    DESIGN_STANDARDS_FLAG: DESIGN_STANDARDS_REASON,
}

#: Where the code says so, each with the stored lines that say it
#: (``flats/provenance/docs``; ``flats/tests/test_pdx_overlays.py`` holds the
#: quotes to them).
CITES: Mapping[str, tuple[str, str, str]] = {
    "min_far_inner": (
        "PCC 33.415.310.A",
        "or/multnomah/portland/33.415.txt#L79-L81",
        "In the Inner Pattern Area the minimum floor area ratio (FAR) for all new development is 0.5",
    ),
    "min_far_outer": (
        "PCC 33.415.310.B",
        "or/multnomah/portland/33.415.txt#L82-L83",
        "In the Eastern and Western Pattern Area the minimum floor area ratio (FAR) for all new",
    ),
    "historic_district": (
        "PCC 33.445.200.E.1",
        "or/multnomah/portland/33.445.txt#L1184-L1185",
        "of a contributing resource in a Historic District is subject to demolition review",
    ),
    "conservation_district": (
        "PCC 33.445.210.E.1",
        "or/multnomah/portland/33.445.txt#L1593-L1594",
        "of a contributing resource in a Conservation District is subject to demolition review",
    ),
    "nr_district": (
        "PCC 33.445.220.E.1",
        "or/multnomah/portland/33.445.txt#L1697-L1699",
        "of a contributing resource in a National Register District is subject to demolition",
    ),
    "nr_district_approval": (
        "PCC 33.445.220.E.3",
        "or/multnomah/portland/33.445.txt#L1743-L1744",
        "If the review body approves demolition of the resource",
    ),
    "split_site": (
        "PCC 33.700.070.F",
        "or/multnomah/portland/33.700.txt#L385-L386",
        "When a site is in more than one zone, the development standards of each zone apply to "
        "the portion of the site in that zone",
    ),
    "historic landmark": (
        "PCC 33.445.100.E.1",
        "or/multnomah/portland/33.445.txt#L360-L362",
        "of a Historic Landmark and demolition of a contributing resource is subject to",
    ),
    "conservation landmark": (
        "PCC 33.445.110.E.1",
        "or/multnomah/portland/33.445.txt#L654-L656",
        "of a Conservation Landmark and demolition of a contributing resource is subject to",
    ),
    "national register landmark": (
        "PCC 33.445.120.E.1",
        "or/multnomah/portland/33.445.txt#L754-L756",
        "of a National Register Landmark and demolition of a contributing resource is subject",
    ),
    # --- the rest of the Centers Main Street overlay (FOLLOWUPS 109) -------
    "transit_ban": (
        "PCC 33.415.300.B",
        "or/multnomah/portland/33.415.txt#L73-L77",
        "The following development is prohibited within 100 feet of a transit street : "
        "A. Drive-through facilities; and B. Houses, attached houses, and duplexes.",
    ),
    "attached_house": (
        "PCC 33.910 (Residential Structure Types)",
        "or/multnomah/portland/33.910.definitions.txt#L1072-L1073",
        "Attached House. Except for individual dwelling units on lots created through a middle "
        "housing land division, a dwelling unit, located on its own lot",
    ),
    "transit_street": (
        "PCC 33.910 (Street Types)",
        "or/multnomah/portland/33.910.definitions.txt#L1378-L1379",
        "Transit Street. A street that is classified in the Transportation System Plan as:",
    ),
    "vehicle_area_inner": (
        "PCC 33.415.330.B.1",
        "or/multnomah/portland/33.415.txt#L105-L106",
        "In the Inner Pattern area, no more than 30 percent of any transit street frontage may "
        "be used for vehicle areas",
    ),
    "vehicle_area_outer": (
        "PCC 33.415.330.B.2",
        "or/multnomah/portland/33.415.txt#L107-L108",
        "In the Eastern and Western Pattern areas, no more than 50 percent of any transit "
        "street frontage may be used for vehicle areas",
    ),
    "vehicle_areas": (
        "PCC 33.910 (Vehicle Areas)",
        "or/multnomah/portland/33.910.definitions.txt#L1490-L1491",
        "Vehicle Areas. All the area on a site where vehicles may circulate or park including "
        "parking areas, driveways",
    ),
    "max_setback": (
        "PCC 33.415.320",
        "or/multnomah/portland/33.415.txt#L86-L87",
        "of the building must meet the maximum building setback standard of the base zone.",
    ),
    "street_facing_facade": (
        "PCC 33.910 (Street-facing Facade)",
        "or/multnomah/portland/33.910.definitions.txt#L1324-L1325",
        "All the wall planes of a structure as seen from one side or view that are at an "
        "angle of 45 degrees or less from a street lot line.",
    ),
    # --- Historic and Conservation Districts --------------------------------
    "historic_district_review": (
        "PCC 33.445.200.D.1.b",
        "or/multnomah/portland/33.445.txt#L868-L872",
        "following proposals in a Historic District are subject to historic resource review: "
        "a. Exterior alterations; b. Building a new structure;",
    ),
    "conservation_district_review": (
        "PCC 33.445.210.D",
        "or/multnomah/portland/33.445.txt#L1282-L1290",
        "When historic resource review is required, the Community Design Standards may be used "
        "as an alternative for some proposals.",
    ),
    "historic_compatibility": (
        "PCC 33.846.060.G.8",
        "or/multnomah/portland/33.846.txt#L887-L888",
        "Architectural compatibility. New additions, exterior alterations, or new construction "
        "will be compatible with the massing, size, scale, and",
    ),
    "community_design_standards": (
        "PCC 33.445.500",
        "or/multnomah/portland/33.445.txt#L2000-L2001",
        "The Community Design Standards provide a clear and objective alternative to historic "
        "resource review",
    ),
    "community_design_central_city": (
        "PCC 33.445.510.A",
        "or/multnomah/portland/33.445.txt#L2019-L2021",
        "Proposals affecting a Conservation Landmark or Conservation District in the Central City "
        "plan district are not eligible to use the Community Design Standards",
    ),
    "community_design_setback": (
        "PCC 33.218.100.B",
        "or/multnomah/portland/33.218.txt#L102-L109",
        "In any case, the structure may not be set back from the front lot line more than 25 feet.",
    ),
    "community_design_alley": (
        "PCC 33.218.100.F.1",
        "or/multnomah/portland/33.218.txt#L165-L165",
        "If the site is served by an alley, access for motor vehicles must be from the",
    ),
    "nr_district_no_review": (
        "PCC 33.445.220.D",
        "or/multnomah/portland/33.445.txt#L1682-L1683",
        "Historic resource review is not required for development within the boundary of a "
        "National Register District",
    ),
    # --- the Design overlay -------------------------------------------------
    "design_required": (
        "PCC 33.420.041.A",
        "or/multnomah/portland/33.420.txt#L57-L60",
        "the following must meet the design standards or be approved through design review: "
        "A. New development;",
    ),
    "design_exempt": (
        "PCC 33.420.045.A.2",
        "or/multnomah/portland/33.420.txt#L80-L82",
        "a. The only use on the site will be Household Living; b. There will be no more than four "
        "dwelling units total on the site;",
    ),
    "design_exempt_zones": (
        "PCC 33.420.045.A.2.d",
        "or/multnomah/portland/33.420.txt#L85-L85",
        "d. The site is not zoned RX, EX, or CX;",
    ),
    "design_not_in_districts": (
        "PCC 33.420.025",
        "or/multnomah/portland/33.420.txt#L53-L54",
        "This chapter does not apply to sites located within the boundary of a Historic Landmark, "
        "Conservation Landmark, Historic District, or Conservation District.",
    ),
    "design_standards_central_city": (
        "PCC 33.420.050.B.1",
        "or/multnomah/portland/33.420.txt#L255-L256",
        "1. In the Central City plan district.",
    ),
    "design_standards_residential": (
        "PCC 33.420 Table 420-1 note [1]",
        "or/multnomah/portland/33.420.txt#L253-L253",
        "There are no maximum limits for proposals where any of the floor area is in residential use.",
    ),
    "design_standards_gateway": (
        "PCC 33.420.050.B.2.a",
        "or/multnomah/portland/33.420.txt#L258-L259",
        "any portion of the new development or alteration exceeds 35 feet in height",
    ),
    "design_standards_height": (
        "PCC 33.420.050.B.3",
        "or/multnomah/portland/33.420.txt#L267-L268",
        "New buildings or additions when any portion of the new building or addition exceeds "
        "75 feet in height",
    ),
    "design_review_guidelines": (
        "PCC 33.825.055",
        "or/multnomah/portland/33.825.txt#L177-L178",
        "A design review application will be approved if the review body finds the applicant to "
        "have shown that the proposal complies with the design guidelines for the area.",
    ),
    "rx_design": (
        "PCC 33.120.030.E",
        "or/multnomah/portland/33.120.txt#L136-L137",
        "The Design overlay zone is applied to this zone.",
    ),
    "cx_design": (
        "PCC 33.130.030.F",
        "or/multnomah/portland/33.130.txt#L163-L164",
        "The Design overlay zone is applied to this zone.",
    ),
    "gateway_open_area": (
        "PCC 33.526.240.C",
        "or/multnomah/portland/33.526.txt#L362-L363",
        "The requirements of this section apply to sites 5 acres or more in area.",
    ),
}


@dataclass(frozen=True, slots=True)
class Reading:
    """What the Portland overlays say about one lot."""

    #: At least :data:`MAIN_STREET_SHARE` of the lot is in the "m" overlay.
    main_street: bool = False
    #: Map 415-1's labels holding the lot, largest share first.
    pattern_areas: tuple[str, ...] = ()
    #: Protected resources on the lot, each said in a line.
    protected: tuple[str, ...] = ()
    #: Contributing resources in a National Register District.
    nr_district: tuple[str, ...] = ()
    #: The share of the lot in the "m" overlay (33.700.070.F measures the
    #: minimum FAR on that part).
    main_street_share: float = 1.0
    #: The part of the lot in the overlay (hex WKB, EPSG:2913), kept only
    #: where the lot is partly in it: the drawn building is measured on it.
    main_street_part_wkb: str | None = None
    #: The Historic, Conservation and National Register Districts the lot is
    #: in, by the district status polygons of every status (a
    #: non-contributing house, a removed one, a lot with no status), as the
    #: city names them.
    districts: tuple[str, ...] = ()

    @property
    def central_city(self) -> bool:
        """The lot is in Map 415-1's Central City pattern area, read as the
        Central City plan district."""
        return CENTRAL_CITY in self.pattern_areas

    def districts_of(self, kind: str) -> tuple[str, ...]:
        return tuple(d for d in self.districts if district_kind(d) == kind)

    @property
    def main_street_part(self) -> float:
        """The share of the lot the minimum FAR is measured on: the part in
        the overlay, or the whole lot past ``1 - MAIN_STREET_SHARE``."""
        share = max(0.0, min(1.0, self.main_street_share))
        return 1.0 if share >= 1.0 - MAIN_STREET_SHARE else share

    @property
    def min_far(self) -> float | None:
        """33.415.310's minimum FAR for the lot, or None where none applies."""
        if not self.main_street:
            return None
        if not self.pattern_areas:
            return MIN_FAR_UNMEASURED
        stated = [MIN_FAR[p] for p in self.pattern_areas if p in MIN_FAR]
        return max(stated) if stated else None

    @property
    def red_resources(self) -> tuple[str, ...]:
        return self.protected + (self.nr_district if NR_DISTRICT_RED else ())


def encode(r: Reading) -> str:
    return json.dumps(
        {
            "pdx_main_street_overlay": r.main_street,
            "pdx_pattern_area": list(r.pattern_areas),
            "pdx_protected_resource": list(r.protected),
            "pdx_nr_district_resource": list(r.nr_district),
            "pdx_main_street_share": r.main_street_share,
            "pdx_main_street_part": r.main_street_part_wkb,
            "pdx_district": list(r.districts),
        },
        separators=(",", ":"),
    )


def decode(raw: str | None) -> Reading | None:
    """The reading a row carries; None where nothing read the lot."""
    if not raw:
        return None
    doc = json.loads(raw)
    return Reading(
        main_street=bool(doc.get("pdx_main_street_overlay")),
        pattern_areas=tuple(doc.get("pdx_pattern_area") or ()),
        protected=tuple(doc.get("pdx_protected_resource") or ()),
        nr_district=tuple(doc.get("pdx_nr_district_resource") or ()),
        main_street_share=float(doc.get("pdx_main_street_share", 1.0)),
        main_street_part_wkb=doc.get("pdx_main_street_part"),
        districts=tuple(doc.get("pdx_district") or ()),
    )


# --- the maps ----------------------------------------------------------------


@dataclass(frozen=True)
class Maps:
    """The four layers, each with its spatial index."""

    main_street: tuple[Any, ...]
    patterns: tuple[tuple[Any, str], ...]
    #: (geometry, words, kind) -- kind ``protected``, ``nr`` or ``none``.
    resources: tuple[tuple[Any, str, str], ...]
    #: (geometry, district name) -- every district status polygon.
    districts: tuple[tuple[Any, str], ...] = ()
    trees: dict[str, Any] = dataclasses.field(default_factory=dict)

    @classmethod
    def build(
        cls,
        main_street: Sequence[Any],
        patterns: Sequence[tuple[Any, str]],
        resources: Sequence[tuple[Any, str, str]],
        districts: Sequence[tuple[Any, str]] = (),
    ) -> Maps:
        from shapely.strtree import STRtree

        out = cls(tuple(main_street), tuple(patterns), tuple(resources), tuple(districts))
        out.trees["m"] = STRtree(list(out.main_street))
        out.trees["p"] = STRtree([g for g, _ in out.patterns])
        out.trees["r"] = STRtree([g for g, _, _ in out.resources])
        out.trees["d"] = STRtree([g for g, _ in out.districts])
        return out


def _manifest(sources: Path) -> dict[str, Any]:
    path = sources / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _dataset_path(sources: Path, manifest: Mapping[str, Any], key: str) -> Path:
    entry = (manifest.get("datasets") or {}).get(key) or {}
    return sources / str(entry.get("file") or f"{key}.geojson")


def missing(sources: Path | None) -> tuple[str, ...]:
    """The layers an acquire snapshot lacks -- every one where there is no
    snapshot. Without them a lot in the overlay or holding a landmark would
    pass GREEN unread, so the bridge refuses a snapshot missing one."""
    if sources is None:
        return KEYS
    manifest = _manifest(sources)
    return tuple(k for k in KEYS if not _dataset_path(sources, manifest, k).is_file())


def has_m(ovrly: object) -> bool:
    """Whether a zoning polygon's overlay letters (``"d,m"``) hold ``m``."""
    return "m" in {t.strip() for t in str(ovrly or "").split(",")}


def _district_kind(name: str) -> str:
    """A district's kind from its name: ``nr``, else ``protected``. The
    layer spells some names short ("...HISTORI*", "...DISTRICTC"); any name
    that is not a National Register District is read as protected."""
    return "nr" if "NATIONAL REGISTER" in name.upper() else "protected"


def district_name(props: Mapping[str, Any]) -> str:
    """A district status record's district, as the city spells it, without
    the layer's truncation star."""
    return str(props.get("DistName") or "").strip().rstrip("*").strip()


def district_kind(name: str) -> str:
    """:data:`NATIONAL_REGISTER`, :data:`CONSERVATION` or :data:`HISTORIC`,
    from the name. The layer spells some short ("...HISTORI*",
    "...DISTRICTC"); a name that says neither National Register nor
    Conservation is a Historic District, the strictest of the three."""
    up = name.upper()
    if "NATIONAL REGISTER" in up:
        return NATIONAL_REGISTER
    if "CONSERVATION" in up:
        return CONSERVATION
    return HISTORIC


def resource_words(props: Mapping[str, Any]) -> tuple[str, str]:
    """A district status record said in a line, and its kind: ``protected``,
    ``nr`` (a contributing resource in a National Register District) or
    ``none`` (non-contributing, removed, or no status)."""
    status = str(props.get("Status") or "").strip()
    low = status.lower()
    district = str(props.get("DistName") or "").strip().rstrip("*")
    where = f" in {district.title()}" if district else ""
    built = f", built {props['YearBuilt']}" if props.get("YearBuilt") else ""
    address = str(props.get("Address") or "").strip()
    said = "contributing resource" if low == "contributing" else low
    words = f"{said}{where} ({address}{built})" if address else f"{said}{where}"
    if low not in PROTECTED_STATUS:
        return words, "none"
    if low in _LANDMARKS:
        return words, "protected"
    return words, _district_kind(district)


def landmark_words(props: Mapping[str, Any]) -> str:
    kind = str(props.get("designation_new") or props.get("TYPE") or "landmark").strip().lower()
    name = str(props.get("HISTNAME") or "").strip()
    address = str(props.get("ADDRESS") or "").strip()
    bits = ", ".join(b for b in (name, address) if b)
    return f"{kind} ({bits})" if bits else kind


def load(sources: Path) -> Maps | None:
    """The four layers an acquire snapshot holds; None where it lacks any."""
    from shapely.geometry import shape

    from flats.ingest.delta import iter_features

    if missing(sources):
        return None
    manifest = _manifest(sources)

    def feats(key: str) -> Iterable[tuple[Any, Mapping[str, Any]]]:
        for f in iter_features(_dataset_path(sources, manifest, key)):
            if not f.get("geometry"):
                continue
            g = shape(f["geometry"])
            yield (g if g.is_valid else g.buffer(0)), (f.get("properties") or {})

    main = [g for g, p in feats(MAIN_STREET_KEY) if has_m(p.get("OVRLY"))]
    patterns = [(g, str(p.get("MapLabel") or "").strip()) for g, p in feats(PATTERN_KEY)]
    resources: list[tuple[Any, str, str]] = []
    districts: list[tuple[Any, str]] = []
    for g, p in feats(RESOURCE_KEY):
        words, kind = resource_words(p)
        if kind != "none":
            resources.append((g, words, kind))
        if district_name(p):
            districts.append((g, district_name(p)))
    resources.extend((g, landmark_words(p), "protected") for g, p in feats(LANDMARK_KEY))
    return Maps.build(main, patterns, resources, districts)


def read(lot: Any, maps: Maps) -> Reading | None:
    """The reading for one taxlot polygon (EPSG:2913); None without a shape."""
    if lot is None or lot.is_empty or lot.area <= 0:
        return None
    lot = lot if lot.is_valid else lot.buffer(0)
    area = lot.area

    pieces = [lot.intersection(maps.main_street[i]) for i in maps.trees["m"].query(lot)]
    inside = sum(g.area for g in pieces)
    shares: dict[str, float] = {}
    for i in maps.trees["p"].query(lot):
        g, label = maps.patterns[int(i)]
        shares[label] = shares.get(label, 0.0) + lot.intersection(g).area / area
    patterns = tuple(k for k, v in sorted(shares.items(), key=lambda kv: -kv[1]) if v >= PATTERN_SHARE)

    protected: list[str] = []
    nr: list[str] = []
    for i in maps.trees["r"].query(lot):
        g, words, kind = maps.resources[int(i)]
        if g.area <= 0:
            continue
        if lot.intersection(g).area < RESOURCE_SHARE * min(area, g.area):
            continue
        target = protected if kind == "protected" else nr
        if words not in target:
            target.append(words)
    districts: list[str] = []
    for i in maps.trees["d"].query(lot) if "d" in maps.trees else ():
        g, name = maps.districts[int(i)]
        if g.area <= 0 or name in districts:
            continue
        if lot.intersection(g).area >= RESOURCE_SHARE * min(area, g.area):
            districts.append(name)
    share = min(1.0, inside / area)
    part_wkb = None
    if MAIN_STREET_SHARE <= share < 1.0 - MAIN_STREET_SHARE:
        import shapely

        part_wkb = shapely.to_wkb(shapely.union_all(pieces), hex=True)
    return Reading(
        main_street_share=round(share, 4),
        main_street_part_wkb=part_wkb,
        main_street=inside / area >= MAIN_STREET_SHARE,
        pattern_areas=patterns,
        protected=tuple(protected),
        nr_district=tuple(nr),
        districts=tuple(sorted(districts)),
    )


def with_overlays(rows: Iterable[dict[str, Any]], sources: Path | None) -> int:
    """Join :data:`ROW_KEY` onto every Portland row (:data:`ANSWERS`) with a
    shape, in place; say how many carry something (the overlay or a
    resource). Nothing without a snapshot holding the layers."""
    import shapely

    if sources is None:
        return 0
    maps = load(sources)
    if maps is None:
        return 0
    marked = 0
    for row in rows:
        if row.get("jurisdiction") not in ANSWERS or not row.get("lot_wkb"):
            continue
        got = read(shapely.from_wkb(row["lot_wkb"]), maps)
        if got is None:
            continue
        row[ROW_KEY] = encode(got)
        marked += bool(got.main_street or got.protected or got.nr_district or got.districts)
    return marked


# --- the check ---------------------------------------------------------------


def credited(reading: Reading, floor_sqft: float, building: Any | None) -> float:
    """The floor area that counts toward the overlay's minimum: all of it on a
    lot wholly in the overlay; on a lot partly in it, the share of the drawn
    building's footprint standing on the part in the overlay, and nothing
    without a drawing or the part's shape (33.700.070.F)."""
    if reading.main_street_part >= 1.0:
        return floor_sqft
    if building is None or building.is_empty or building.area <= 0 or not reading.main_street_part_wkb:
        return 0.0
    import shapely

    part = shapely.from_wkb(reading.main_street_part_wkb)
    return floor_sqft * min(1.0, building.intersection(part).area / building.area)


def building_of(drawing: Mapping[str, Any] | None) -> Any | None:
    """The building a stored drawing stands (EPSG:2913), or None."""
    ring = (drawing or {}).get("building")
    if not ring or len(ring) < 4:
        return None
    from shapely.geometry import Polygon

    g = Polygon(ring)
    return g if g.is_valid else g.buffer(0)


def _plain(name: str) -> str:
    return name.title().replace("'S ", "'s ")


def binds_for(
    reading: Reading | None,
    floor_sqft: float,
    lot_sqft: float,
    building: Any | None = None,
    *,
    zone: str | None = None,
    height_ft: float | None = None,
) -> tuple[flag_plan.Bind, ...]:
    """The binds the reading puts on one design: a protected resource, a
    floor area under the overlay's minimum, a Historic District's (or a
    Central City Conservation District's) historic resource review, and the
    Central City's design review. ``building`` is the drawn building, read
    only on a lot partly in the overlay (:func:`credited`); ``zone`` the base
    zone and ``height_ft`` the design's height, read by the design overlay
    (None where the caller has neither: no design-overlay bind)."""
    if reading is None:
        return ()
    out: list[flag_plan.Bind] = []
    for words in reading.red_resources:
        kind = next((k for k in _LANDMARKS if words.startswith(k)), None)
        if kind is not None:
            cite = CITES[kind][0]
        elif "conservation district" in words.lower():
            cite = CITES["conservation_district"][0]
        elif "national register district" in words.lower():
            cite = CITES["nr_district"][0]
        else:
            cite = CITES["historic_district"][0]
        out.append(
            flag_plan.Bind(
                PROTECTED_RESOURCE_CHECK,
                None,
                None,
                None,
                source=f"{cite}: demolition review -- {words} (Steph 2026-10-14: a protected building is red)",
            )
        )
    need = reading.min_far
    part = reading.main_street_part
    measured = lot_sqft * part
    if need is not None and measured > 0:
        counted = credited(reading, floor_sqft, building)
        far = counted / measured
        if far < need - 1e-9:
            inner = need >= MIN_FAR["Inner"]
            cite = CITES["min_far_inner" if inner else "min_far_outer"][0]
            area = ", ".join(reading.pattern_areas) or "no pattern area mapped, taken as Inner"
            on = (
                f"{floor_sqft:,.0f} sf of floor on {lot_sqft:,.0f} sf of lot"
                if part >= 1.0
                else f"{counted:,.0f} of the pod's {floor_sqft:,.0f} sf of floor standing on the "
                f"{measured:,.0f} sf of the {lot_sqft:,.0f} sf lot in the overlay "
                f"({CITES['split_site'][0]}: each zone's standards on its portion of the site)"
            )
            out.append(
                flag_plan.Bind(
                    MIN_FAR_CHECK,
                    round(far, 4),
                    need,
                    round(need - far, 4),
                    source=f"{cite}: Centers Main Street overlay ({area} pattern area), {on}",
                )
            )
    tiers = "Steph 2026-10-14: a review that is essentially judgement is red"
    for name in reading.districts_of(HISTORIC):
        out.append(
            flag_plan.Bind(
                HISTORIC_REVIEW_CHECK,
                None,
                None,
                None,
                source=(
                    f"{CITES['historic_district_review'][0]}: building a new structure in "
                    f"{_plain(name)} needs historic resource review, judged on compatibility with "
                    f"the district ({CITES['historic_compatibility'][0]}); historic areas are "
                    f"outside ORS 197A.400 ({tiers})"
                ),
            )
        )
    if reading.central_city:
        for name in reading.districts_of(CONSERVATION):
            out.append(
                flag_plan.Bind(
                    HISTORIC_REVIEW_CHECK,
                    None,
                    None,
                    None,
                    source=(
                        f"{CITES['community_design_central_city'][0]}: in the Central City plan "
                        f"district a new structure in {_plain(name)} may not use the Community "
                        f"Design Standards, so it needs historic resource review "
                        f"({CITES['conservation_district_review'][0]}; {tiers})"
                    ),
                )
            )
    design = _design_track(reading, zone, height_ft)
    if design is not None and design[0] == "review":
        out.append(flag_plan.Bind(DESIGN_REVIEW_CHECK, None, None, None, source=design[1]))
    return tuple(out)


def _design_track(
    reading: Reading, zone: str | None, height_ft: float | None
) -> tuple[str, str, int | None] | None:
    """Where the design overlay sends the pod: ``("review", why, None)``
    (design review, RED), ``("standards", why, severity)`` (the design
    standards track, a flag at ``severity`` -- None for the type's own), or
    None where the chapter does not reach it (exempt, or in a district)."""
    if zone is None or height_ft is None:
        return None
    if reading.districts_of(HISTORIC) or reading.districts_of(CONSERVATION):
        return None  # 33.420.025: historic resource review governs instead
    z = zone.strip().upper()
    if z not in DESIGN_ZONES:
        return None  # 33.420.045.A.2: four homes, 35 ft or less (checked by the caller)
    carried = (
        CITES["rx_design"][0] if z == "RX" else CITES["cx_design"][0] if z == "CX"
        else "EX taken as carrying it (the map's letter is not read)"
    )
    lead = (
        f"{CITES['design_exempt_zones'][0]}: the Household Living exemption leaves out {z}, "
        f"and the Design overlay is on it ({carried})"
    )
    tiers = "Steph 2026-10-14: a review that is essentially judgement is red"
    if reading.central_city:
        return (
            "review",
            f"{lead}; {CITES['design_standards_central_city'][0]}: no design standards track in "
            f"the Central City plan district, so design review, approved on "
            f"\"the design guidelines for the area\" ({CITES['design_review_guidelines'][0]}); "
            f"the Central City is outside ORS 197A.400 ({tiers})",
            None,
        )
    if height_ft > STANDARDS_HEIGHT_FT:
        return (
            "review",
            f"{lead}; {CITES['design_standards_height'][0]}: over 75 ft only design review "
            f"({CITES['design_review_guidelines'][0]}; {tiers})",
            None,
        )
    if height_ft > GATEWAY_STANDARDS_HEIGHT_FT:
        return (
            "standards",
            f"{lead}; {CITES['design_standards_gateway'][0]}: over 35 ft in the Gateway plan "
            f"district only design review, and no Gateway map is read",
            5,
        )
    return (
        "standards",
        f"{lead}; the design standards are the clear and objective track "
        f"({CITES['design_standards_residential'][0]}: no size limit with residential floor "
        f"area; the Gateway open area rule reaches only sites of 5 acres or more, "
        f"{CITES['gateway_open_area'][0]}); unchecked design details do not block green "
        f"(Steph 2026-10-14)",
        None,
    )


# --- the main street measurements --------------------------------------------


def _ring_of(drawing: Mapping[str, Any] | None, name: str) -> Any | None:
    ring = (drawing or {}).get(name)
    if not ring or len(ring) < 4:
        return None
    from shapely.geometry import Polygon

    g = Polygon(ring)
    return g if g.is_valid else g.buffer(0)


def vehicle_share(lot: Any, edges: Any, drawing: Mapping[str, Any] | None) -> tuple[float, float] | None:
    """``(percent, feet)`` of the worst street frontage the drawn plan's
    vehicle areas -- its lane and its court (33.910: "parking areas,
    driveways") -- face, read as :func:`flats.fit.frontage.street_runs`
    reads parking. ``(0, 0)`` for a plan with no vehicle area; None where
    there is no lot, no street, or no drawn building."""
    from flats.fit.frontage import street_chains, street_runs

    building = building_of(drawing)
    if lot is None or edges is None or building is None or not street_chains(edges):
        return None
    import shapely

    areas = [g for g in (_ring_of(drawing, "lane"), _ring_of(drawing, "court")) if g is not None]
    if not areas:
        return 0.0, 0.0
    rows = shapely.union_all(areas).intersection(lot)
    if rows.is_empty:
        return 0.0, 0.0
    runs = street_runs(lot, edges, rows, building)
    if not runs:
        return None
    return max(p for p, _ in runs), max(f for _, f in runs)


def facade_share(lot: Any, edges: Any, building: Any | None, max_ft: float) -> float | None:
    """The smallest share, percent, over the lot's streets, of the drawn
    building's street-facing facade (33.910: the wall planes "at an angle of
    45 degrees or less from a street lot line", on the side that faces it)
    that stands within ``max_ft`` of that street's lot line. 0 for a street
    the building turns no wall to; None where there is no building or street.
    Every street is read (33.415.320 lets a site of three frontages leave one
    out, chosen by transit class, which nothing here holds)."""
    import math

    from flats.fit.frontage import street_chains
    from flats.geom.edges import bearing_deg, bearing_delta

    if lot is None or edges is None or building is None or building.is_empty:
        return None
    chains = street_chains(edges)
    if not chains:
        return None
    import shapely
    from shapely.ops import nearest_points

    ring = list(building.exterior.coords)
    worst: float | None = None
    for chain in chains:
        street = shapely.multilinestrings([[(e.x1, e.y1), (e.x2, e.y2)] for e in chain])
        total = within = 0.0
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            dx, dy = x2 - x1, y2 - y1
            length = math.hypot(dx, dy)
            if length <= 0:
                continue
            bearing = bearing_deg(x1, y1, x2, y2)
            if min(bearing_delta(bearing, e.bearing_deg) for e in chain) > FACADE_ANGLE_DEG:
                continue
            nx, ny = dy / length, -dx / length
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            if building.contains(shapely.Point(mx + nx * 0.5, my + ny * 0.5)):
                nx, ny = -nx, -ny
            near = nearest_points(shapely.Point(mx, my), street)[1]
            if (near.x - mx) * nx + (near.y - my) * ny <= 0:
                continue  # the wall's back is to this street
            steps = max(1, math.ceil(length))
            for j in range(steps):
                t = (j + 0.5) / steps
                pt = shapely.Point(x1 + dx * t, y1 + dy * t)
                total += length / steps
                if pt.distance(street) <= max_ft + DRAWN_TOL_FT:
                    within += length / steps
        share = 100.0 * within / total if total > 0 else 0.0
        worst = share if worst is None else min(worst, share)
    return worst


def flags_for(
    reading: Reading | None,
    *,
    zone: str | None,
    plat: str,
    units: int,
    height_ft: float,
    max_setback_ft: float | None,
    lot: Any,
    edges: Any,
    drawing: Mapping[str, Any] | None,
) -> tuple[flag_plan.Flag, ...]:
    """The open questions the reading leaves on one design: the main
    street's transit-street rules, a Conservation District's Community
    Design Standards, and the design overlay's standards track. ``plat`` is
    the design's plat (``unit_lots`` for the townhouse form)."""
    if reading is None:
        return ()
    out: list[flag_plan.Flag] = []

    def flag(code: str, source: str, severity: int | None = None) -> None:
        out.append(flag_plan.Flag(code, flag_plan.LOT, FLAGS[code], source=source, severity=severity))

    unheld = f"no map of transit streets is held, so every street is taken as one ({CITES['transit_street'][0]})"
    if reading.main_street:
        if plat == "unit_lots":
            flag(
                MAIN_STREET_TRANSIT_FLAG,
                f"{CITES['transit_ban'][0]}: houses, attached houses and duplexes are barred within "
                f"100 ft of a transit street; four homes each on its own lot are attached houses "
                f"unless the lots come from a middle housing land division "
                f"({CITES['attached_house'][0]}); {unheld}",
            )
        stated = [VEHICLE_AREA_CAP_PCT[p] for p in reading.pattern_areas if p in VEHICLE_AREA_CAP_PCT]
        cap = min(stated) if stated else (None if reading.pattern_areas else VEHICLE_AREA_CAP_UNMEASURED)
        if cap is not None:
            cite = CITES["vehicle_area_inner" if cap <= 30.0 else "vehicle_area_outer"][0]
            got = vehicle_share(lot, edges, drawing)
            if got is None:
                flag(
                    MAIN_STREET_VEHICLE_FLAG,
                    f"{cite}: vehicle areas may use at most {cap:.0f}% of any transit street "
                    f"frontage; no drawn plan to measure; {unheld}",
                )
            elif got[0] > cap + 1e-9:
                flag(
                    MAIN_STREET_VEHICLE_FLAG,
                    f"{cite}: vehicle areas may use at most {cap:.0f}% of any transit street "
                    f"frontage; the plan's lane and court face {got[0]:.0f}% ({got[1]:.0f} ft) of "
                    f"one street; {unheld}",
                )
        inner = "Inner" in reading.pattern_areas or not reading.pattern_areas
        if inner:
            cite = CITES["max_setback"][0]
            if max_setback_ft is None:
                flag(
                    MAIN_STREET_SETBACK_FLAG,
                    f"{cite}: 70% of the street-facing facade must meet the base zone's maximum "
                    f"building setback, and no maximum is read for {zone or 'the zone'}",
                )
            else:
                share = facade_share(lot, edges, building_of(drawing), max_setback_ft)
                if share is None:
                    flag(
                        MAIN_STREET_SETBACK_FLAG,
                        f"{cite}: 70% of the street-facing facade must stand within "
                        f"{max_setback_ft:.0f} ft of the street; no drawn plan to measure",
                    )
                elif share < SETBACK_FACADE_PCT - 1e-9:
                    flag(
                        MAIN_STREET_SETBACK_FLAG,
                        f"{cite}: 70% of the street-facing facade must stand within "
                        f"{max_setback_ft:.0f} ft of the street; the drawn building has "
                        f"{share:.0f}% there on its worst street",
                    )
    if not reading.central_city and not reading.districts_of(HISTORIC):
        for name in reading.districts_of(CONSERVATION):
            flag(
                COMMUNITY_DESIGN_FLAG,
                f"{CITES['conservation_district_review'][0]}: a new structure in {_plain(name)} "
                f"may meet the Community Design Standards instead of historic resource review "
                f"({CITES['community_design_standards'][0]}); they set the front setback by the "
                f"neighbours', never over 25 ft ({CITES['community_design_setback'][0]}), and "
                f"the car in off an alley where there is one ({CITES['community_design_alley'][0]}), "
                f"none of it measured",
            )
    design = _design_track(reading, zone, height_ft)
    if design is not None and design[0] == "standards":
        flag(DESIGN_STANDARDS_FLAG, design[1], design[2])
    elif design is None and (units > DESIGN_EXEMPT_UNITS or height_ft > DESIGN_EXEMPT_HEIGHT_FT):
        if not (reading.districts_of(HISTORIC) or reading.districts_of(CONSERVATION)):
            flag(
                DESIGN_STANDARDS_FLAG,
                f"{CITES['design_exempt'][0]}: past four homes or 35 ft the design overlay's "
                f"exemption ends, and the zoning map's \"d\" is not read beside the base zone",
                5,
            )
    return tuple(out)


def checked(s: Any, reading: Reading | None) -> Any:
    """``s`` (a bridge ``Screened``) RED where the reading binds its design
    and YELLOW (from GREEN) where it leaves a question at the yellow line: a
    bind or a flag each, the reason beside it, as screened and as signed.
    Adds nothing twice, so a screen that runs again over its own answer is
    unchanged."""
    if reading is None:
        return s
    design = s.design
    zone = getattr(s.lot, "zone", None)
    binds = binds_for(
        reading,
        design.ground_sqft * design.stories,
        s.lot.facts.lot_sqft,
        building_of(s.drawing),
        zone=zone,
        height_ft=design.height_ft,
    )
    rules = getattr(s, "rules", None)
    flags = flags_for(
        reading,
        zone=zone,
        plat=getattr(getattr(design, "plat", None), "value", str(getattr(design, "plat", ""))),
        units=design.units,
        height_ft=design.height_ft,
        max_setback_ft=rules.get("setback_front_max_ft") if rules is not None else None,
        lot=getattr(s.lot, "lot_geom", None),
        edges=getattr(s.lot, "edges", None),
        drawing=s.drawing,
    )
    if not binds and not flags:
        return s
    from flats.score.screen import Triage

    reg = flag_plan.registry()
    line = flag_plan.colour_rules().yellow_at_severity

    def apply(x: Any) -> Any:
        have = {(b.check, b.source) for b in x.binds}
        new = tuple(b for b in binds if (b.check, b.source) not in have)
        held = {(f.code, f.source) for f in x.flags}
        raised = tuple(f for f in flags if (f.code, f.source) not in held)
        if not new and not raised:
            return x
        reasons = list(x.reasons)
        for b in new:
            why = _BIND_REASON.get(b.check, PROTECTED_RESOURCE_REASON)
            if why not in reasons:
                reasons.append(why)
        triage = x.triage
        for f in raised:
            if flag_plan.severity_of(f, reg) >= line:
                if f.by not in reasons:
                    reasons.append(f.by)
                if triage is Triage.green:
                    triage = Triage.yellow
        if new:
            triage = Triage.red
        return dataclasses.replace(
            x, triage=triage, binds=(*x.binds, *new), flags=(*x.flags, *raised), reasons=tuple(reasons)
        )

    return dataclasses.replace(s, screening=apply(s.screening), signed=apply(s.signed))


__all__ = [
    "ANSWERS",
    "CHECKS",
    "CITES",
    "COMMUNITY_DESIGN_FLAG",
    "DESIGN_REVIEW_CHECK",
    "DESIGN_STANDARDS_FLAG",
    "FLAGS",
    "HISTORIC_REVIEW_CHECK",
    "KEYS",
    "MAIN_STREET_SETBACK_FLAG",
    "MAIN_STREET_TRANSIT_FLAG",
    "MAIN_STREET_VEHICLE_FLAG",
    "MIN_FAR_CHECK",
    "MIN_FAR_REASON",
    "PROTECTED_RESOURCE_CHECK",
    "PROTECTED_RESOURCE_REASON",
    "REASONS",
    "ROW_KEY",
    "Maps",
    "Reading",
    "binds_for",
    "building_of",
    "checked",
    "credited",
    "decode",
    "district_kind",
    "encode",
    "facade_share",
    "flags_for",
    "has_m",
    "load",
    "missing",
    "read",
    "vehicle_share",
    "with_overlays",
]
