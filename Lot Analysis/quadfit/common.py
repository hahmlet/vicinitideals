"""
Quadfit — shared plumbing for the quadplex-buildability pipeline.

Standalone statistical analysis: for every Multnomah County tax lot whose zone
allows a quadplex by-right (HB 2001 / OAR 660-046), test whether candidate
footprint rectangles fit inside the lot's setback envelope. No app imports, no
DB — file-based stages under data/quadfit/. See README.md for the stage graph.

This module holds paths, CRS constants, config schemas/loaders, and Parquet+WKB
IO helpers shared by the s* stage scripts. Config-only consumers (tests, the
rules compiler) must be able to import it without the `gis` extra installed, so
shapely/pyproj/pyarrow imports are deferred into the functions that need them.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

TOOL_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOL_DIR.parents[1]
CONFIG_DIR = TOOL_DIR / "config"
if str(REPO_ROOT) not in sys.path:  # the pipeline runs these as scripts
    sys.path.insert(0, str(REPO_ROOT))

#: How tall the thing we are trying to place is. Lives in the FLATS field
#: registry, which documents it as the tallest design in the catalog rather
#: than an average, and guards it with `flats/tests/test_height_ratio.py`.
#: Imported instead of copied because a step-back setback is DERIVED from it,
#: and the whole point of deriving is that the number moves when the product
#: does. `flats.rules.fields` imports nothing but dataclasses and typing, so
#: this costs the rules compiler nothing and needs no extra installed.
from flats.rules.fields import DESIGN_HEIGHT_FT  # noqa: E402

GIS_CACHE_DIR = REPO_ROOT / "data" / "gis_cache" / "oregon"
DATA_DIR = REPO_ROOT / "data" / "quadfit"

# RLIS native CRS: NAD83(HARN) / Oregon North, international feet. All pipeline
# geometry works in this CRS so setbacks/footprints are in feet with no
# reprojection of the 400K+ taxlot polygons. Only WGS84 zoning layers from
# cache_layers.py get reprojected on load.
CRS_WORKING = "EPSG:2913"
CRS_WGS84 = "EPSG:4326"


# ---------------------------------------------------------------------------
# Config schemas
# ---------------------------------------------------------------------------

Confidence = Literal["verified", "needs_verification"]

OrientationConstraint = Literal["none", "entrance_only", "axis_required"]


class StepBack(BaseModel):
    """A yard that grows with the building, because the roof is capped at the line.

    Gresham 7.0420(G)(1): "The maximum roof height at the rear setback line is
    21 feet and increases at a rate of one foot in height for every one foot of
    distance further from the rear property line." Milwaukie prints the same
    rule as geometry rather than as a rate -- Table 19.302.4 allows 25 ft at the
    minimum side yard and slopes the plane up at 45 degrees -- and MMC 19.200
    fixes where the plane starts: "horizontally offset from the side lot line by
    the required side yard depth", not at the lot line, which is the difference
    between 11 ft and 6.

    Both spellings are kept because both are what a reader finds on the page.
    `rise_per_ft` is computed from `slope_degrees` when only the angle is
    printed, so no rule file ever types a figure the code does not state.

    The setback this produces is DERIVED from the pod's height, and that is the
    reason this is a model and not five edited numbers: rules.yaml keeps the
    figure the district table prints, the envelope gets the figure a 26 ft
    building actually owes, and if the product ever gets taller every one of
    these moves on its own.
    """

    #: Roof height allowed AT the setback line the district prints.
    height_ft: float
    #: Feet of height bought per foot of additional setback. 1.0 is a 45-degree
    #: plane; a 1:2 plane and a 1:1 plane are different rules and both are
    #: written, so this is stated rather than assumed.
    rise_per_ft: float | None = None
    #: The angle, where the code prints one instead of a rate.
    slope_degrees: float | None = None
    cite: str = ""

    @model_validator(mode="after")
    def _validate(self) -> StepBack:
        if (self.rise_per_ft is None) == (self.slope_degrees is None):
            raise ValueError("step-back needs exactly one of rise_per_ft, slope_degrees")
        if self.rise_per_ft is not None and self.rise_per_ft <= 0:
            raise ValueError("step-back rise_per_ft must be positive")
        if self.slope_degrees is not None and not 0 < self.slope_degrees < 90:
            raise ValueError("step-back slope_degrees must be between 0 and 90")
        return self

    @property
    def rise(self) -> float:
        """Feet of height per foot of distance, however the code spelled it."""
        if self.rise_per_ft is not None:
            return self.rise_per_ft
        return math.tan(math.radians(float(self.slope_degrees)))

    def extra_ft(self, height_ft: float = DESIGN_HEIGHT_FT) -> float:
        """Feet of setback a building of this height owes beyond the printed one."""
        over = height_ft - self.height_ft
        return 0.0 if over <= 0 else over / self.rise


class ZoneRule(BaseModel):
    zone: str
    quadplex_allowed: bool
    setback_front_ft: float | None = None
    setback_side_ft: float | None = None
    setback_rear_ft: float | None = None
    # Corner-lot street-side setback when it exceeds the interior side setback
    # (e.g. Gresham MDR 20 ft vs 10 ft interior). Applied to ALL street edges of
    # tier-B lots via max(front, street_side) — conservative, since the true
    # front edge legally takes only the front setback.
    setback_street_side_ft: float | None = None
    # Rear/side roof-height planes. See StepBack: the printed setback above
    # stays what the district table prints, and the ENVELOPE uses the effective
    # figure these produce for a DESIGN_HEIGHT_FT building. Every one of them
    # pushes the building further from the line, so leaving them out is the
    # direction that manufactures a green.
    step_back_rear: StepBack | None = None
    step_back_side: StepBack | None = None
    # Minimum lot area for a quadplex where the code sets one (e.g. Portland
    # Table 110-7). Lots below this drop in the s3 funnel.
    min_lot_sqft: float | None = None
    # Minimum street frontage for residential use where the code sets one
    # (e.g. Gresham CMF 100 ft). Gates fits in s6 (frontage known after s4).
    min_frontage_ft: float | None = None
    max_coverage_pct: float | None = None  # building coverage cap, % of lot area
    # Piecewise coverage formula rows [lot_area_break_sqft, base_sqft,
    # marginal_pct_over_break] — e.g. Portland Table 110-5. Overrides
    # max_coverage_pct when present.
    coverage_curve: list[list[float]] | None = None
    accessory_allowance_sqft: float = 0  # reserved coverage for garage/shed assumption
    # Per-zone override of the jurisdiction orientation_constraint (e.g.
    # Gresham design districts force the long axis parallel to the street).
    orientation_constraint: OrientationConstraint | None = None
    source: str = ""
    source_url: str = ""
    confidence: Confidence = "needs_verification"
    notes: str = ""

    @model_validator(mode="after")
    def _validate(self) -> ZoneRule:
        if self.quadplex_allowed:
            missing = [
                n
                for n in ("setback_front_ft", "setback_side_ft", "setback_rear_ft")
                if getattr(self, n) is None
            ]
            if missing:
                raise ValueError(
                    f"zone {self.zone}: quadplex_allowed=true requires {missing}"
                )
        if self.coverage_curve:
            breaks = [row[0] for row in self.coverage_curve]
            if any(len(row) != 3 for row in self.coverage_curve):
                raise ValueError(f"zone {self.zone}: coverage_curve rows need 3 values")
            if breaks != sorted(breaks):
                raise ValueError(f"zone {self.zone}: coverage_curve breaks must ascend")
        return self

    def effective_setback_rear_ft(
        self, height_ft: float = DESIGN_HEIGHT_FT
    ) -> float | None:
        """The rear setback a building of this height actually stands at."""
        if self.setback_rear_ft is None or self.step_back_rear is None:
            return self.setback_rear_ft
        return self.setback_rear_ft + self.step_back_rear.extra_ft(height_ft)

    def effective_setback_side_ft(
        self, height_ft: float = DESIGN_HEIGHT_FT
    ) -> float | None:
        """The side setback a building of this height actually stands at."""
        if self.setback_side_ft is None or self.step_back_side is None:
            return self.setback_side_ft
        return self.setback_side_ft + self.step_back_side.extra_ft(height_ft)

    def coverage_cap_sqft(self, lot_area_sqft: float) -> float | None:
        """Max combined building coverage for a lot, or None if uncapped."""
        if self.coverage_curve:
            cap: float | None = None
            for brk, base, marginal in self.coverage_curve:
                if lot_area_sqft >= brk:
                    cap = base + marginal / 100.0 * (lot_area_sqft - brk)
            return cap
        if self.max_coverage_pct is not None:
            return self.max_coverage_pct / 100.0 * lot_area_sqft
        return None


class JurisdictionRules(BaseModel):
    eligible: bool
    reason: str = ""
    # Literal values of the RLIS JURIS_CITY field that map to this jurisdiction.
    juris_city_codes: list[str] = Field(default_factory=list)
    # RLIS COUNTY codes (M=Multnomah, C=Clackamas) this block applies to. Empty
    # = any county (incorporated city names are unique). Set it to disambiguate
    # the unincorporated blocks that share a blank JURIS_CITY across counties.
    county_codes: list[str] = Field(default_factory=list)
    # Slug of the cached zoning layer (data/gis_cache/oregon/<slug>.geojson).
    zoning_layer: str | None = None
    zone_field: str | None = None
    zone_aliases: dict[str, str] = Field(default_factory=dict)
    # Portland writes overlay letters into the zone code (R5a, R2.5h...):
    # strip trailing lowercase letters before rule lookup.
    strip_lowercase_suffix: bool = False
    require_inside_ugb: bool = False
    # Middle-housing orientation rules bind the entrance/facade, not the long
    # axis, everywhere verified so far; axis_required restricts fit testing to
    # width-facing placements only.
    orientation_constraint: OrientationConstraint = "entrance_only"
    # This city's dimensional table states a LOT WIDTH and defines it as
    # measured across the MIDDLE of the lot -- Oregon City 17.04.700 "between
    # the midpoints of the two principal opposite side lot lines", Tualatin TDC
    # 31.060 "at the center of the lot". `min_frontage_ft` carries that number
    # because there is nowhere else to put it, but s4 measures the run of
    # boundary that TOUCHES A STREET, which is a different line on the same
    # parcel: identical on a rectangle, nothing alike on a wedge, a flag lot or
    # anything that tapers toward the road.
    #
    # Where this is set, falling short sends the lot to REVIEW instead of
    # dropping it in the funnel. The pipeline cannot take the measurement the
    # code asks for, and a lot the screen is unable to judge belongs in front of
    # a person, not in the red pile. It cannot turn anything green.
    #
    # Leave it false where the table pins the measurement to the street edge --
    # West Linn heads the row "Minimum lot width AT FRONT LOT LINE", so its
    # number is the one s4 measures and its exclusions are sound.
    frontage_is_lot_width: bool = False
    zones: list[ZoneRule] = Field(default_factory=list)

    def normalize_zone(self, raw: str | None) -> str | None:
        if raw is None:
            return None
        code = str(raw).strip()
        if not code:
            return None
        if code in self.zone_aliases:
            return self.zone_aliases[code]
        if self.strip_lowercase_suffix:
            stripped = code.rstrip("abcdefghijklmnopqrstuvwxyz")
            if stripped and stripped in {z.zone for z in self.zones}:
                return stripped
            if stripped in self.zone_aliases:
                return self.zone_aliases[stripped]
            if stripped:
                return stripped
        return code

    def rule_for(self, raw_zone: str | None) -> ZoneRule | None:
        code = self.normalize_zone(raw_zone)
        if code is None:
            return None
        for rule in self.zones:
            if rule.zone == code:
                return rule
        return None


class Defaults(BaseModel):
    # Max distance from a lot edge midpoint to a street centerline for the edge
    # to count as frontage (~ROW half-width + margin).
    street_threshold_ft: float = 50.0
    sliver_min_lot_sqft: float = 1000.0
    grid_resolution_ft: float = 0.5
    simplify_tolerance_ft: float = 1.5


class RulesConfig(BaseModel):
    meta: dict[str, Any] = Field(default_factory=dict)
    defaults: Defaults = Field(default_factory=Defaults)
    jurisdictions: dict[str, JurisdictionRules]

    def jurisdiction_for_juris_city(
        self, juris_city: str | None, county: str | None = None
    ) -> str | None:
        """Map an RLIS JURIS_CITY literal (+ optional COUNTY code) to a
        jurisdiction key. `county` disambiguates the unincorporated blocks that
        share a blank JURIS_CITY across counties (COUNTY field: M=Multnomah,
        C=Clackamas); it is ignored for blocks with no county_codes."""
        code = (juris_city or "").strip().upper()
        cc = (county or "").strip().upper()
        for key, j in self.jurisdictions.items():
            if code not in {c.upper() for c in j.juris_city_codes}:
                continue
            if j.county_codes and cc and cc not in {c.upper() for c in j.county_codes}:
                continue
            return key
        return None


class Footprint(BaseModel):
    name: str
    width_ft: float  # dimension parallel to the front lot line (before flip)
    depth_ft: float

    @model_validator(mode="after")
    def _positive(self) -> Footprint:
        if self.width_ft <= 0 or self.depth_ft <= 0:
            raise ValueError(f"footprint {self.name}: dimensions must be positive")
        return self


class ConstantAreaSweep(BaseModel):
    """Sweep aspect ratios at fixed footprint area (identical floor plates)."""

    area_sqft: float
    width_min_ft: float
    width_max_ft: float
    step_ft: float = 0.5

    def widths(self) -> list[float]:
        out: list[float] = []
        w = self.width_min_ft
        # Float-safe inclusive range in step_ft increments.
        n = 0
        while True:
            w = self.width_min_ft + n * self.step_ft
            if w > self.width_max_ft + 1e-9:
                break
            out.append(round(w, 4))
            n += 1
        return out


class FrontierSpec(BaseModel):
    """Width grid for the per-lot max-depth frontier."""

    width_min_ft: float = 12.0
    width_max_ft: float = 60.0
    step_ft: float = 0.5

    def widths(self) -> list[float]:
        out: list[float] = []
        n = 0
        while True:
            w = self.width_min_ft + n * self.step_ft
            if w > self.width_max_ft + 1e-9:
                break
            out.append(round(w, 4))
            n += 1
        return out


class SplitSpec(BaseModel):
    """Large-lot subdivision screen — pure attribute math applied in s7, so
    every knob here is adjustable with a report-only re-run."""

    quad_ground_sqft: float = 2000.0
    parking_slots_per_unit: float = 1.5
    parking_sqft_per_slot: float = 162.0  # 9x18 stall, no travel lanes
    units_per_quad: int = 4
    min_quads: int = 2

    def per_quad_lot_sqft(self) -> float:
        """Buildable sqft one carved quadplex lot must supply."""
        return (
            self.quad_ground_sqft
            + self.units_per_quad * self.parking_slots_per_unit * self.parking_sqft_per_slot
        )


class ScreenSpec(BaseModel):
    """Current-use + value + acquisition-economics screen (s7-only knobs).

    Current use is tagged from the assessor property class (STATECLASS first
    digit; RLIS LANDUSE as fallback): lots whose category is listed in
    exclude_current_use become a counted policy-funnel step — the team won't
    replace existing multifamily or valuable commercial. TOTALVAL is the county
    Real Market Value (RMV = LANDVAL + BLDGVAL, the assessor's annual market
    estimate — NOT the Measure-50 capped ASSESSVAL, which is ~45% of it and is
    unused here). RMV is reasonable in aggregate but wrong on any single lot, so
    the value side is a reported slice, never a silent kill:
      vacant             — improvement value <= vacant_max_improvement_value
                           (a ~$5k shed is virtually vacant)
      teardown_candidate — building <= teardown_max_improvement_share of
                           total value (mostly-land lots)
      improved           — building dominates value; costly to replace

    Acquisition economics turns that into a land-cost-per-door slice. The
    acquisition estimate is a post-cutoff arm's-length sale where recorded
    (SALEPRICE >= recent_sale_min_price AND sale year >= recent_sale_min_year —
    post-COVID prices are trusted; anything older or nominal falls back to RMV).
    land_cost_per_unit = acquisition / doors, where doors = units_per_quad for a
    1-lot conversion and units_per_quad x carved pods for a split. Tiers:
    preferred (<= preferred_land_cost_per_unit) / viable (<= max) / over_budget.
    """

    exclude_current_use: list[str] = Field(
        default_factory=lambda: ["multifamily", "commercial"])
    teardown_max_improvement_share: float = 0.5
    vacant_max_improvement_value: float = 5000.0
    # Acquisition economics (land cost per door). See docstring.
    recent_sale_min_year: int = 2020       # sales this year+ trusted; older -> RMV
    recent_sale_min_price: float = 10000.0  # below = nominal/family transfer, ignore
    preferred_land_cost_per_unit: float = 30000.0
    max_land_cost_per_unit: float = 45000.0


class StallGeometry(BaseModel):
    """One jurisdiction's parking dimensions, as that jurisdiction states them.

    Per jurisdiction rather than one constant because the numbers differ and the
    difference decides lots: Gresham's townhouse stall is 8.5 ft wide
    (§7.0431(B)(5)(b)), Portland's fourplex stall is 9 (PCC 33.266.120.D.1).
    Half a foot is one stall in every eighteen across a court, and a court that
    seats a stall it could not really hold is a GREEN nobody can build.

    The aisle widths are optional, and None is a fact rather than a missing
    value: it means the code states a stall and no aisle. Portland's 33.266.120
    does exactly that — the aisle table one section over belongs to 33.266.130,
    whose own applicability sentence hands residential vehicle areas back to
    .120. A cell with no aisle standard is a cell s6s declines to lay out, not
    one that quietly borrows a neighbour's number.
    """

    stall_width_ft: float
    stall_depth_ft: float
    aisle_one_way_ft: float | None = None
    aisle_two_way_ft: float | None = None
    parallel_stall_ft: list[float] | None = None

    #: Spaces per unit the city will not let this building exceed, or None
    #: where it states no ceiling. Mirrors the corpus `parking_max_per_unit`,
    #: and None is what an `exempt: true` there means: read, and no maximum.
    #:
    #: A ceiling is not a detail. Milwaukie caps a quadplex at one space per
    #: unit, which is four for this pod — the same number as the marketability
    #: floor, so every Milwaukie plan is a minimum-tier plan by law and the
    #: 1.5 and 2.0 tiers are not offers that city will accept. A generator
    #: that seats eight stalls there is drawing an illegal site plan and
    #: calling it preferred.
    max_per_unit: float | None = None

    #: Plat paths on which these dimensions stand down entirely, mirroring the
    #: corpus `unless:`. Oregon City is the case: OCMC 17.52.010 excludes
    #: townhouses from the whole parking chapter and leaves quadplexes in it,
    #: so 9 x 19 off a 24 ft aisle is what governs four units on ONE lot and
    #: nothing governs the same building on four. Which is a fact about how
    #: the product is brought to market, not about the parcel.
    stands_down_on: list[str] = Field(default_factory=list)

    cite: str = ""

    #: True where the aisle above is ASSUMED rather than published by this
    #: city. It is the one dimension in this file that is not a reading, and
    #: it exists because two cities in the corpus state a stall, regulate the
    #: parking completely, and never once say how wide the lane between two
    #: rows of it has to be -- Milwaukie and Wilsonville, 6,091 lots between
    #: them that could not be drawn at all.
    #:
    #: OAR 660-046-0220(2)(e)(E) is the reason an assumption is legitimate here
    #: rather than a shrug: state law tells a Large City to apply to middle
    #: housing "the same off-street parking ... dimensional ... standards that
    #: apply to single-family detached dwellings in the same zone". Both cities
    #: were read down that path and both come back empty -- Milwaukie's
    #: 19.607.1 names single detached dwellings and quadplexes in ONE sentence,
    #: so the redirect lands back on the section already read, and Wilsonville
    #: files its residential standards by structure type with no aisle in any
    #: of them. The number does not exist to be found, in either direction.
    #:
    #: An assumed dimension DOES reach GREEN, decided 2026-08-31 on the statute
    #: the screen already rests on. ORS 197A.400 (renumbered from ORS
    #: 197.307(4)) lets a local government apply only CLEAR AND OBJECTIVE
    #: standards to housing, and a standard that does not exist cannot be clear
    #: and objective -- so a city that never wrote an aisle width down has no
    #: lawful basis to refuse a court drawn to the national minimum. Silence is
    #: a better position than a published number, not a worse one: Troutdale's
    #: 25 ft binds and nothing binds here.
    #:
    #: `geometry_assumed` still rides onto every lot drawn this way and into
    #: lots_results.csv, so a reviewer can filter for the rows whose aisle came
    #: from ULI/NPA rather than from a code. It is a provenance column, not a
    #: verdict.
    aisle_assumed: bool = False

    #: Where an assumed aisle comes from. Required when `aisle_assumed` is set,
    #: because an assumption with no source is indistinguishable from a guess
    #: and this file's whole discipline is that every number names its origin.
    aisle_cite: str = ""

    @model_validator(mode="after")
    def _an_assumption_names_its_source(self) -> "StallGeometry":
        if self.aisle_assumed and not self.aisle_cite.strip():
            raise ValueError(
                "aisle_assumed is set with no aisle_cite; an assumed dimension "
                "must say where it came from"
            )
        if self.aisle_cite.strip() and not self.aisle_assumed:
            raise ValueError(
                "aisle_cite is set without aisle_assumed; a published aisle "
                "cites itself through `cite`"
            )
        return self

    def lays_out(self) -> bool:
        """Whether a rear court can be dimensioned from what this code states."""
        return self.aisle_one_way_ft is not None and self.aisle_two_way_ft is not None

    def stall_ceiling(self, units: int) -> int | None:
        """Most stalls this city permits the pod, or None where it caps none."""
        if self.max_per_unit is None:
            return None
        return int(math.floor(self.max_per_unit * units))


# Gresham, the pilot cell. The one-way aisle is 23 ft, not 20: Table 9.0825A
# gives 23 at 90° with a standard stall, and the 20 that used to sit here is
# note 1's emergency-vehicle access figure — a different standard answering a
# different question. Table 9.0861's 8'6" is the parking STRUCTURE matrix and
# does not reach a surface rear court either. Both readings err the same way,
# seating stalls the court cannot hold.
_GRESHAM_GEOMETRY = {
    "stall_width_ft": 8.5,
    "stall_depth_ft": 18.5,
    "aisle_one_way_ft": 23.0,
    "aisle_two_way_ft": 24.0,
    "parallel_stall_ft": [8.0, 24.0],
    "cite": "GDC Table 9.0825A, 90 degrees standard, reached via 9.0802(F)",
}


class DrivewayRules(BaseModel):
    """One jurisdiction's driveway, parking-placement and open-space rules.

    The sibling of StallGeometry, and it exists for the same reason. Until this
    block landed, s6s drew every city's driveway to five numbers lifted from
    Gresham GDC 7.0431 and applied nationwide -- an 18 ft approach, a 12 ft
    side lane, a 5 ft gap, and a 15 percent open-space reserve taken off every
    lot in every city. Two of those were wrong even in Gresham (7.0431 is the
    TOWNHOUSE chapter; on the one-lot plat this stage actually draws, 7.0420
    caps the approach at TEN feet) and the other three were nobody's law
    outside it.

    Every value here mirrors a FLATS corpus field, which is where it carries a
    citation. `None` is a fact, not a blank: the drift test reads an omitted
    field as "this city was read and its code states no such rule" and a city
    missing from the map entirely as "nobody has read this city". Where the
    corpus holds `exempt: true` -- read, and no such standard -- the mirror
    holds None, because for a rule about where pavement may sit an exemption
    and a silence constrain the drawing identically.

    THESE ARE THE ONE-LOT VALUES. Four units on one lot is a quadplex and four
    units on four lots is townhouses, and every city in this corpus states a
    different approach width, a different maneuvering cap and sometimes a
    different open-space rule for the two. SiteplanSpec refuses to load the
    unit-lot plat while this map is populated, rather than draw a townhouse to
    a quadplex's numbers.
    """

    #: `driveway_approach_min_width_ft` -- the narrowest curb cut the city will
    #: accept. Oregon City and Fairview both say ten feet; most say nothing.
    approach_min_ft: float | None = None
    #: `driveway_approach_max_width_ft` -- the widest curb cut, measured at the
    #: property line. This is the number the old global had backwards: it is a
    #: CEILING, and Gresham's is 10 ft on this plat, not the 18 that was
    #: shipped. A lane wider than the cut is legal (the drive may widen behind
    #: the property line) so this narrows the opening, it does not fail a lot.
    approach_max_ft: float | None = None
    #: `driveway_min_width_one_way_ft` / `driveway_min_width_two_way_ft`. The
    #: side lane carries cars in and out, so the two-way figure is the one that
    #: binds. Happy Valley's 20 ft is the hardest number in this family and the
    #: only one that takes lots away: a minimum cannot be traded down.
    drive_min_one_way_ft: float | None = None
    drive_min_two_way_ft: float | None = None
    #: `parking_maneuvering_max_width_ft` -- a CEILING on the same lane. It is
    #: None on every one-lot row here because the model code states it of
    #: townhouse lots only; it is carried so the unit-lot branch has somewhere
    #: to land, and because a 10 ft cap under a 12 ft lane is a city that
    #: cannot be drawn rather than a city drawn narrow.
    maneuvering_max_ft: float | None = None
    #: `parking_area_max_frontage_pct` / `parking_area_max_width_ft` -- how much
    #: of the street frontage garages and parking may occupy. Satisfied by
    #: construction in this typology (every stall is behind the building) and
    #: mirrored so the day a front-court typology is added it is already here.
    parking_max_frontage_pct: float | None = None
    parking_max_width_ft: float | None = None
    #: `parking_front_yard_max_pct` -- Portland's and Milwaukie's shape, a share
    #: of the front yard AREA rather than of the frontage. The side lane
    #: crossing the front setback is the only pavement this typology puts
    #: there.
    parking_front_yard_max_pct: float | None = None
    #: `parking_front_prohibited` -- True where the city bans parking between
    #: the building and the street outright. It is the reason the rear court is
    #: the only typology in this stage, and every city that states it is
    #: satisfied by that arrangement. Both Portland and Milwaukie carve the
    #: driveway out of the ban in the same sentence.
    parking_front_prohibited: bool | None = None
    #: `parking_street_setback_ft` -- how far a stall must stand off a street
    #: lot line. A rear court clears it everywhere it is stated.
    parking_street_setback_ft: float | None = None
    #: Per-zone override of the same, for the city that states the standard by
    #: reference rather than by number. Happy Valley LDC 16.43.030.E.4 sets it
    #: to "the same distance as the required building setbacks" with a ten-foot
    #: floor, which is 22 ft in six districts, 20 in two and 10 in three -- one
    #: sentence, three answers, and no citywide number to mirror. The corpus
    #: resolves it per zone through `same_as`; this carries what it resolved to.
    parking_street_setback_by_zone: dict[str, float | None] = Field(default_factory=dict)
    #: `parking_building_buffer_ft` -- the city's own minimum between the
    #: building and the parking area. Raises the design gap where it exceeds
    #: it; Fairview's 4 ft does not.
    building_buffer_ft: float | None = None

    #: `open_space_min_pct` -- private open space as a share of the gross lot.
    #: Gresham states 15 percent and is now the only city that gets it, where
    #: it used to be charged to all seven.
    open_space_pct: float | None = None
    #: `open_space_min_sqft` -- the same claim as a flat area for the whole pod.
    #: Milwaukie's 384 is four ground-floor units at 96 sq ft each; the corpus
    #: resolves the per-dwelling carrier against the four-unit design, so this
    #: mirror holds the POD total and not the per-unit figure.
    open_space_sqft: float | None = None
    #: Per-zone override of `open_space_sqft`, for the one city that states it
    #: by zone rather than citywide: Portland's Table 110-4 asks 250 sq ft of
    #: outdoor area in most residential zones and 200 in R2.5. A zone present
    #: with a null reserves nothing (the corpus says exempt); a zone absent
    #: falls through to the citywide figures above.
    open_space_sqft_by_zone: dict[str, float | None] = Field(default_factory=dict)

    cite: str = ""


class SiteplanSpec(BaseModel):
    """Procedural site-plan generator knobs (s6s stage).

    Unlike SplitSpec (parking as a flat area allowance), this drives an actual
    per-lot geometric layout: building placed at the front, a driveway to a
    parking court, 90° stalls counted by real geometry, and a mandatory private
    open-space reservation. All lengths in feet (CRS EPSG:2913). Every knob is
    an s6s+s7 re-run; drawings alone are an s7 re-run.

    The three parking counts are Steph's marketability target and not a legal
    floor — Gresham requires ZERO parking (CFEC citywide elimination,
    §9.0802(A)) and Fairview and Portland require none either. What the law
    contributes is the other end: a city may state a MAXIMUM, and where it does
    the higher tiers are not on offer there however much room a lot has. That
    ceiling lives on StallGeometry beside the stall it belongs to, because it
    is the same reading of the same table.

    The ARRANGEMENT travels: off-street parking in the REAR yard, reached by a
    single consolidated driveway down one SIDE, cars entering and leaving
    forward so nothing backs onto the street. Every city in this corpus asks
    for it in its own words — Gresham §7.0431(B)(3)(b)(iii), Milwaukie
    19.607.1.E.2, Happy Valley 16.43.030.F.5 — which is why there is one
    typology: `townhome_rear_court`.

    What does NOT travel is any DIMENSION. The stall is StallGeometry; the
    driveway, the curb cut, the building-to-parking gap and the open-space
    reserve are DrivewayRules. Both are per-city and neither has a default,
    because the alternative is what this stage used to do: draw Gresham's
    townhouse chapter in seven cities, including the two figures that were not
    even Gresham's on the plat being drawn.
    """

    enabled: bool = True

    # WHICH LOTS GET LAID OUT.
    #
    # This began as one cell — Gresham LDR-5 — because Gresham was the only
    # city whose stall and aisle had been read. That is no longer the reason
    # it is one cell; it is now just the shape the code was left in, and a
    # stage scoped to a city nobody chose is a stage answering a question
    # nobody asked. `every_city_it_can_dimension` lays out every lot in every
    # city whose own code states a stall AND an aisle. A city that states a
    # stall and no aisle is still declined — the point of per-city geometry is
    # that a borrowed dimension is a made-up one — and a city nobody has read
    # is still passed through as `not_evaluated`.
    #
    # `pilot_cell` is kept because it is the cheap way to re-run one city
    # after a layout change, and because the drawings in siteplans.geojson
    # were sampled from it.
    scope: Literal["every_city_it_can_dimension", "pilot_cell"] = (
        "every_city_it_can_dimension"
    )
    pilot_jurisdiction: str = "gresham"
    pilot_zone: str = "LDR-5"

    # WHICH BUILDING IS BEING LAID OUT, on paper.
    #
    # Four units on one lot is a quadplex; four units on four lots is
    # townhouses, and cities state different standards for the two. The
    # pipeline's verdict is the ONE-LOT conversion (s7 `conversion_*`), and
    # the FLATS design catalog defaults to the same path, so that is what this
    # stage draws. It is stated here rather than assumed because it decides
    # whether a city's parking chapter reaches this building at all: Oregon
    # City's does on one lot and does not on four.
    plat: Literal["one_lot", "unit_lots"] = "one_lot"

    # Marketability tiers — spaces per townhome unit.
    parking_per_unit_min: float = 1.0        # 4 / pod (tight-lot floor)
    parking_per_unit_target: float = 1.5     # 6 / pod (design target)
    parking_per_unit_preferred: float = 2.0  # 8 / pod (where the city caps none)
    units_per_pod: int = 4

    # Single honest typology (see class docstring). Kept as a list so a future
    # cell can add typologies without a schema change.
    layout_methods: list[Literal["townhome_rear_court"]] = Field(
        default_factory=lambda: ["townhome_rear_court"]
    )

    # Stall + drive geometry, per jurisdiction — never one global number. See
    # StallGeometry. A city with no entry here is a city s6s passes through.
    geometry: dict[str, StallGeometry] = Field(
        default_factory=lambda: {"gresham": StallGeometry(**_GRESHAM_GEOMETRY)}
    )

    # Driveway, parking placement and open space, per jurisdiction — never one
    # global number. See DrivewayRules. A city with no entry here is a city
    # whose access chapter nobody has read; it is laid out to the design
    # constants below and constrained by nothing, which the report says out
    # loud rather than passing off as compliance.
    driveway: dict[str, DrivewayRules] = Field(default_factory=dict)

    # THE THREE ENGINEERING CONSTANTS. What is left after the law was taken
    # out of this block: not one of them is a citation, and none may grow one.
    #
    # A car needs about twelve feet of lane and a wall needs about five feet of
    # standoff whatever the code says, so these are the floor the drawing works
    # to when a city asks for less or asks for nothing. Where a city asks for
    # MORE — Happy Valley's twenty-foot two-way drive — the city's number wins,
    # because a minimum is not a preference. The old 12 and 5 sat here wearing
    # Gresham's section numbers; they are the same figures, saying what they
    # actually are.
    driveway_lane_design_ft: float = 12.0
    driveway_cut_min_design_ft: float = 9.0   # one car through the curb cut
    building_parking_gap_ft: float = 5.0

    @model_validator(mode="after")
    def _the_mirror_is_the_one_lot_branch(self) -> SiteplanSpec:
        if self.plat != "one_lot" and self.driveway:
            raise ValueError(
                "siteplan.driveway mirrors the ONE-LOT branch of each city's "
                "code; every city here states a different approach width and "
                "maneuvering cap for townhouses on their own lots. Mirror the "
                "unit-lot branch before flipping `plat`, rather than drawing "
                "a townhouse to a quadplex's numbers."
            )
        return self

    def driveway_for(self, jurisdiction: str) -> DrivewayRules | None:
        """The driveway rules a jurisdiction publishes, or None if unread."""
        return self.driveway.get(jurisdiction)

    def lane_ft_for(self, jurisdiction: str) -> float | None:
        """Width of the side lane in this city, or None if it cannot be drawn.

        The design lane, widened to any minimum the city states. None where the
        city caps a maneuvering area BELOW what a car needs — Milwaukie's ten
        feet on the townhouse path is the live case — because a lane drawn
        narrower than a car is a site plan nobody can build, and a lane drawn
        wider than the cap is one nobody can permit.
        """
        lane = self.driveway_lane_design_ft
        dw = self.driveway_for(jurisdiction)
        if dw is None:
            return lane
        if dw.drive_min_two_way_ft is not None:
            lane = max(lane, dw.drive_min_two_way_ft)
        if dw.maneuvering_max_ft is not None and dw.maneuvering_max_ft < lane:
            return None
        return lane

    def curb_cut_ft_for(self, jurisdiction: str) -> float | None:
        """Width of the opening at the property line, or None if it cannot be.

        The lane, narrowed to the city's approach ceiling. Gresham is the case
        the old constants got backwards: a 12 ft lane meets the street through
        a 10 ft cut and widens behind the property line, which GDC 7.0420
        permits and 7.0431's 18 ft never described. None where the ceiling
        falls below the city's own floor or below one car's width.
        """
        lane = self.lane_ft_for(jurisdiction)
        if lane is None:
            return None
        dw = self.driveway_for(jurisdiction)
        cut = lane if dw is None or dw.approach_max_ft is None else min(
            lane, dw.approach_max_ft
        )
        floor = self.driveway_cut_min_design_ft
        if dw is not None and dw.approach_min_ft is not None:
            floor = max(floor, dw.approach_min_ft)
        return None if cut < floor else cut

    def gap_ft_for(self, jurisdiction: str) -> float:
        """Clear distance between the building and the parking court."""
        dw = self.driveway_for(jurisdiction)
        if dw is None or dw.building_buffer_ft is None:
            return self.building_parking_gap_ft
        return max(self.building_parking_gap_ft, dw.building_buffer_ft)

    def open_space_required_sqft(
        self, jurisdiction: str, zone: str, lot_area_sqft: float
    ) -> float:
        """Private open space this lot must reserve, in square feet.

        Zero for four of the seven cities that can be dimensioned. Fairview,
        Wilsonville, Oregon City and Happy Valley state no private open space
        standard for this building at all — read, and absent, each for its own
        reason recorded in its layer — so the 15 percent they were being
        charged was Gresham's rule collected in cities that never wrote it.

        Where a city states more than one form, the largest binds: they are
        concurrent claims on the same lot, not alternatives.
        """
        dw = self.driveway_for(jurisdiction)
        if dw is None:
            return 0.0
        need = 0.0
        if dw.open_space_pct is not None:
            need = max(need, dw.open_space_pct / 100.0 * lot_area_sqft)
        by_zone = dw.open_space_sqft_by_zone
        if zone and zone in by_zone:
            flat = by_zone[zone]
        else:
            flat = dw.open_space_sqft
        if flat is not None:
            need = max(need, float(flat))
        return need

    def parking_street_setback_for(self, jurisdiction: str, zone: str) -> float | None:
        """How far this cell's code makes a stall stand off a street lot line.

        None where the city states no such standard — which is most of them,
        and is not the same as zero. A zone named in the per-zone map wins over
        the citywide figure; a zone absent from it falls through.
        """
        dw = self.driveway_for(jurisdiction)
        if dw is None:
            return None
        if zone and zone in dw.parking_street_setback_by_zone:
            return dw.parking_street_setback_by_zone[zone]
        return dw.parking_street_setback_ft

    def geometry_for(self, jurisdiction: str) -> StallGeometry | None:
        """The stall geometry a jurisdiction publishes, or None if it has none.

        None is the answer for a jurisdiction nobody has read yet. It is not an
        invitation to substitute the pilot's numbers: a court laid out to
        Gresham's stall in a city that writes a wider one is a stall count that
        no reviewer could defend.

        It is also the answer where a city states dimensions that do not reach
        the building on the plat path being drawn — Oregon City on unit lots —
        which is the same refusal for the same reason.
        """
        geom = self.geometry.get(jurisdiction)
        if geom is None or self.plat in geom.stands_down_on:
            return None
        return geom

    def cities_it_can_dimension(self) -> list[str]:
        """Every jurisdiction this stage will lay out, in scope order.

        Sorted so a run's console output and the report read the same way twice
        running; `pilot_cell` scope narrows to the pilot city alone, and even
        then only if that city can actually be dimensioned.
        """
        if self.scope == "pilot_cell":
            names = [self.pilot_jurisdiction]
        else:
            names = sorted(self.geometry)
        return [n for n in names
                if (g := self.geometry_for(n)) is not None and g.lays_out()
                and self.curb_cut_ft_for(n) is not None]

    def cities_on_an_assumed_aisle(self) -> list[str]:
        """Those of them whose aisle is assumed rather than published.

        Always a subset of `cities_it_can_dimension`, and the reason s7 can
        keep an assumption out of GREEN without re-reading this file per lot.
        """
        return [n for n in self.cities_it_can_dimension()
                if (g := self.geometry_for(n)) is not None and g.aisle_assumed]

    def stall_cap_for(self, jurisdiction: str) -> int:
        """Most stalls s6s will seat here: the marketability ceiling or the law.

        A four-plex has no use for more than 2/unit, so the preferred tier is
        the standing cap. Where a city states a maximum below that, the city's
        number is the one that binds, and the pod simply cannot reach the
        higher tiers there — which is a fact about the market in that city and
        belongs in the output rather than in a footnote.
        """
        cap = self.preferred_stalls()
        geom = self.geometry_for(jurisdiction)
        legal = geom.stall_ceiling(self.units_per_pod) if geom else None
        return cap if legal is None else min(cap, legal)

    def min_stalls(self) -> int:
        return math.ceil(self.units_per_pod * self.parking_per_unit_min)

    def target_stalls(self) -> int:
        return math.ceil(self.units_per_pod * self.parking_per_unit_target)

    def preferred_stalls(self) -> int:
        return math.ceil(self.units_per_pod * self.parking_per_unit_preferred)

    def tier_for(self, stalls: int) -> str:
        """Best marketability tier a stall count achieves."""
        if stalls >= self.preferred_stalls():
            return "preferred"
        if stalls >= self.target_stalls():
            return "target"
        if stalls >= self.min_stalls():
            return "minimum"
        return "fail"


class FootprintsConfig(BaseModel):
    orientations: list[Literal["width_facing", "depth_facing"]] = Field(
        default_factory=lambda: ["width_facing", "depth_facing"]
    )
    footprints: list[Footprint]
    constant_area_sweeps: list[ConstantAreaSweep] = Field(default_factory=list)
    frontier: FrontierSpec = Field(default_factory=FrontierSpec)
    split: SplitSpec | None = None
    screen: ScreenSpec = Field(default_factory=ScreenSpec)
    siteplan: SiteplanSpec | None = None


# --- Phase 2: overlay policy (environmental/hazard/slope/utility) -----------
#
# Each overlay layer gets exactly one legal action for by-right middle housing:
#   kill  — any overlap voids the by-right allowance (or forces discretionary
#           review, same thing for this analysis): lot excluded, like the
#           Portland z overlay
#   carve — development stays by-right but overlay area + buffer_ft is
#           unbuildable: subtracted from the setback envelope, pod re-fit on
#           the remainder
#   flag  — no by-right or geometry effect, adds cost/process (e.g. flood
#           elevation): reported as a per-lot column, never blocks
#
# `coverage` records per-jurisdiction DATA quality so the report can caveat
# what each number is standing on:
#   A — city-maintained, parcel-grade    B — regional/federal fallback, adequate
#   C — coarse or partial                X — nothing usable (theme unmodeled)

OverlayAction = Literal["kill", "carve", "flag"]
CoverageGrade = Literal["A", "B", "C", "X"]


class OverlayCoverage(BaseModel):
    grade: CoverageGrade
    note: str = ""


class OverlaySpec(BaseModel):
    key: str  # matches data/quadfit/raw/overlay_<key>.geojson
    name: str
    # Read a layer fetched under a DIFFERENT key. One regional map is often
    # adopted by several jurisdictions that give it different legal weight:
    # Metro's Title 13 habitat inventory is a carve in Wood Village, which
    # takes it by reference in WVDC 430, and a flag in unincorporated
    # Clackamas, whose ZDO 706.05 prohibits exactly two things in an HCA and a
    # house is neither. Same geometry, two actions, and no reason to download
    # it twice.
    source: str | None = None
    action: OverlayAction
    buffer_ft: float = 0.0  # carve only: unbuildable halo around the feature
    # Some cities publish only the *buffer ring* around a resource, not the
    # resource. Wilsonville's SROZ_ImpactArea is the worked example: 22 donut
    # polygons, each an exterior boundary with exactly one hole, the hole being
    # the Significant Resource Overlay Zone itself. Screening the ring alone
    # would flag lots BESIDE a wetland and miss a lot sitting INSIDE it, which
    # is backwards. Discarding interior rings recovers resource + buffer, which
    # is precisely the extent WDC 4.139.02 applies its regulations to ("the
    # portion of any lot ... within a Significant Resource Overlay Zone and its
    # associated Impact Areas").
    #
    # Only set this where the hole is known to BE the resource. A genuine
    # doughnut -- a lake with an island, a floodplain around high ground -- gets
    # bigger and wronger. The published geometry has to be checked, not guessed.
    fill_holes: bool = False
    jurisdictions: list[str] | Literal["all"] = "all"  # where the RULE applies
    citation: str = ""
    confidence: Literal["verified", "needs_verification"] = "needs_verification"
    coverage: dict[str, OverlayCoverage] = Field(default_factory=dict)

    @property
    def layer(self) -> str:
        """The raw layer this overlay reads — its own key unless it borrows."""
        return self.source or self.key

    def applies_to(self, jurisdiction: str) -> bool:
        return self.jurisdictions == "all" or jurisdiction in self.jurisdictions


class SlopeTiers(BaseModel):
    """Cutlines applied to a per-lot slope statistic at REPORT time (s7).

    `fallback_10m_*` govern the coarse DEM that stands in where 3DEP has no
    1 m lidar at all. USGS's metro lidar projects stop at roughly easting
    540,000 (UTM 10N, about longitude -122.48), which puts every lot in
    Gresham, Troutdale, Fairview and Wood Village -- and Portland's eastern
    third -- outside 1 m coverage. The 1/3 arc-second (~10 m) national DEM is
    seamless and does cover them; it is a different instrument and is labelled
    as one in `slope_source`.
    """

    stat: Literal["mean", "p85", "max"] = "p85"
    ideal_max_pct: float = 10.0
    tolerable_max_pct: float = 20.0  # above this: cost_prohibitive

    # --- coarse fallback -----------------------------------------------
    fallback_10m: bool = True
    # Statistic taken over a window of 10 m cells centred on the lot. `max`
    # over 5 cells (a 50 m box) is the calibrated choice: measured against the
    # 1 m answer on the 184,101 lots where both DEMs exist, `max5 <= 10%`
    # wrongly clears 1.50% of genuinely steep lots while keeping 91.8% of the
    # genuinely flat ones. Smaller windows keep more flat lots and clear more
    # steep ones; larger windows the reverse.
    fallback_10m_stat: Literal["max", "p95", "p85", "mean"] = "max"
    fallback_10m_window: int = 5
    # Whether a lot whose slope came from the coarse DEM may grade GREEN.
    # False = it is reported with a number and a source but still goes to the
    # human queue. This is a business call, not a technical one: see
    # docs/HUMAN_TODO.md.
    fallback_10m_may_green: bool = False

    def tier(self, slope_pct: float) -> str:
        if slope_pct <= self.ideal_max_pct:
            return "ideal"
        if slope_pct <= self.tolerable_max_pct:
            return "tolerable"
        return "cost_prohibitive"


class OverlaysConfig(BaseModel):
    slope: SlopeTiers = Field(default_factory=SlopeTiers)
    overlays: list[OverlaySpec] = Field(default_factory=list)
    # Per-jurisdiction DATA grades for the two non-overlay themes, so the
    # report's coverage matrix covers every phase 2 input.
    slope_coverage: dict[str, OverlayCoverage] = Field(default_factory=dict)
    sewer_coverage: dict[str, OverlayCoverage] = Field(default_factory=dict)

    def by_key(self, key: str) -> OverlaySpec | None:
        return next((o for o in self.overlays if o.key == key), None)


def load_overlays(path: Path | None = None) -> OverlaysConfig:
    import yaml

    p = path or CONFIG_DIR / "overlays.yaml"
    if not p.exists():
        return OverlaysConfig()
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return OverlaysConfig.model_validate(raw)


def load_rules(path: Path | None = None) -> RulesConfig:
    import yaml

    raw = yaml.safe_load((path or CONFIG_DIR / "rules.yaml").read_text(encoding="utf-8"))
    return RulesConfig.model_validate(raw)


def load_footprints(path: Path | None = None) -> FootprintsConfig:
    import yaml

    raw = yaml.safe_load(
        (path or CONFIG_DIR / "footprints.yaml").read_text(encoding="utf-8")
    )
    return FootprintsConfig.model_validate(raw)


# ---------------------------------------------------------------------------
# Geometry + IO helpers (require the `gis` extra)
# ---------------------------------------------------------------------------


def load_geojson_features(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if doc.get("type") == "FeatureCollection":
        return doc.get("features", [])
    raise ValueError(f"{path}: not a FeatureCollection")


def features_to_geoms(features: list[dict[str, Any]]) -> list[Any]:
    """GeoJSON features → shapely geometries (None-safe)."""
    from shapely.geometry import shape

    geoms: list[Any] = []
    for feat in features:
        geom = feat.get("geometry")
        geoms.append(shape(geom) if geom else None)
    return geoms


def reproject_4326_to_2913(geoms: list[Any]) -> list[Any]:
    import shapely
    from pyproj import Transformer

    tr = Transformer.from_crs(CRS_WGS84, CRS_WORKING, always_xy=True)

    def _fn(coords):
        x, y = tr.transform(coords[:, 0], coords[:, 1])
        import numpy as np

        return np.column_stack([x, y])

    return [None if g is None else shapely.transform(g, _fn) for g in geoms]


def stage_path(name: str) -> Path:
    return DATA_DIR / f"{name}.parquet"


def write_stage(df: Any, name: str) -> Path:
    """Write a stage DataFrame (with optional shapely 'geom' column) to Parquet.

    A 'geom' column of shapely geometries is serialized to WKB bytes as 'wkb';
    all other columns pass through.
    """
    import shapely

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    if "geom" in out.columns:
        out["wkb"] = [None if g is None else shapely.to_wkb(g) for g in out["geom"]]
        out = out.drop(columns=["geom"])
    path = stage_path(name)
    out.to_parquet(path, index=False)
    return path


def read_stage(name: str) -> Any:
    """Read a stage Parquet; a 'wkb' column is rehydrated to shapely 'geom'."""
    import pandas as pd
    import shapely

    df = pd.read_parquet(stage_path(name))
    if "wkb" in df.columns:
        df["geom"] = [None if b is None else shapely.from_wkb(b) for b in df["wkb"]]
        df = df.drop(columns=["wkb"])
    return df
