# 199. Ground levels under the placed building, and per-lot foundation-method check

**Status:** offered 2026-11-18; waits on Steph's go and on the foundation agent's method table.

Foundation agent feedback (via Steph 11-18): a slope % alone is not enough -- on a 10% slope the ground falls 2.5 ft under the building along the hill but 8 ft down it; needs slope direction relative to the street or ground levels at the building corners. Steph's idea: the foundation agent supplies what each foundation method demands of the site (e.g. helical pile = stoop 16 in above ground, slab = 8 in), and FLATS computes each per lot.

Proposed split:
1. FLATS measures (no new data: the 1 m elevation model and the placed building outline from the drawn fit are both held): ground level at each building corner and along each wall, fall along the long side and across the short side, highest and lowest ground under the building, level of the street edge / driveway start vs the building, direction of fall relative to the street. Stored per lot and per placement, shown as a note and in the lot report.
2. Foundation agent supplies a method table: per method the limits it puts on those numbers (max fall under the building, floor height above highest ground, max exposed height at the low end, stoop/step height, any soil / groundwater / frost / hazard conditions from 196-198).
3. FLATS evaluates each method per lot: works / works with conditions / does not, with the governing number. NOTE ONLY unless Steph rules otherwise.
Caveats to state on the note: levels are existing ground from the elevation model (inches-level accuracy, not a survey); the building position is the screen's chosen spot and others may exist; floor height above ground feeds the zoning height limit, which is measured from grade -- that part may later belong in the screen proper.
No build-cost work (Steph 11-12).

Steph 2026-11-18 (later): placement needs an optimizer for roomy lots that fit one building in several spots. Existing: flats/ingest/flatter.py (FOLLOWUPS 57, 34b42b4f) already searches other legal spots, but ONLY when the ground grade is the sole block to green, top 4 candidates, 1 m ground, lane-from-street plans, ranks by grade band. Generalising = run it for every lot with more than one legal spot, rank by fall under the building (corner levels), keep the "nothing else worse" rule. Offered in two stages: (a) report-only "flattest legal spot" beside the chosen spot; (b) let it move the drawn placement (needs a bound + move read).

Foundation agent's return list (pasted by Steph 11-18) -- what it wants back, as aggregates:
1. Lot counts by county for ground class x relief class; same split by vacant/built.
2. The 25 most common soil map units by lot count, each with the measured soil attributes.
3. Distributions (count per 1 ft bin) of fall_along, fall_across, relief.
4. Counts by jurisdiction, seismic design category and frost depth.
5. Count of lots where a step-free entry rule applies and is not exempt.
6. Share of lots where each input was missing; elevation source and cell size used.
7. Twenty random lots with all raw values.
8. Anything noticed that these classes hide.
NEEDED from Steph: the part of that spec ABOVE this list (definitions of ground class, relief class, the soil attributes, step-free entry rule). Seismic design category is NOT held -- new per-jurisdiction fact to collect (same sources as frost, 197).

2026-11-18 Steph: GO, report only, GREEN lots only ("I'm only interested in green lots at this time"). Spec = C:\Users\Steph\Repos\Factory-Sim\docs\research\FD2-lot-screen-handoff.md (FD2 pass 1: measure and summarise; NO foundation verdicts in pass 1). This item is now "FD2 pass 1":
- ground shape at the placed footprint (4 corners + long-side midpoints, fall_along, fall_across, relief, high side, lot slope, street-to-front-setback rise, steepest ground within 10/25 ft); where more than one workable position, report the one with the smallest relief and say so (report only -- does not move the drawn building);
- soil AT THE FOOTPRINT with the extra attributes FD2 lists (Unified class 1-5 ft, drainage, seasonal high water + months, restrictive layer, linear extensibility, fragments > 3 in, dwellings-without-basements rating + reasons, steel/concrete corrosion, hydric; flag Urban land / no component data) -- extends 196;
- hazards at the footprint (reuses 198 layers); frost + seismic design category from the Oregon Design Criteria Hub (also check it against 197); vacant/built, year built, assessor basement; zone, permit route, step-free entry rule + exemptions (Portland 33.110.265.E.3);
- provisional ground class + relief class; then the 8-part summary back to the foundation research.
Start when the soil lane (196) lands; hazard lane (198) told to make its measuring take any polygon.
