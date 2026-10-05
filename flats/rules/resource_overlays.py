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
(YELLOW), exactly as the planted strip and the 5-15% slope are. The lot keeps
its envelope: these never take ground, which is the next reading's job --
FOLLOWUPS 42(b) reads each one's sentences to say which belong in ``carve``.

Portland's three environmental zones sit here too. A lot the z covers is RED
on the use rule already; the few the city's z map leaves out while its
environmental-zone map touches them are a map disagreement, and a person
reads the lot rather than the screen picking a side.

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
        "west_linn_wra_piped",
        "a piped stream on West Linn's water resource map",
        "WLCDC 32.120(A); Table 32-2 states no width for a channel still piped",
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
        "fema_sfha",
        "the FEMA 100-year flood area outside the floodway",
        "fringe building stays by right with elevation and fill standards (Gresham GDC 5.0120, "
        "Troutdale TDC Ch 14, MCC 39.5030, PCC 24.50; West Linn 27.070)",
    ),
)

BY_KEY: Mapping[str, Permit] = {p.key: p for p in PERMITS}

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


__all__ = ["BY_KEY", "COLUMNS", "PERMITS", "Permit", "permits_on"]
