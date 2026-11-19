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

2026-11-18 Steph (before going away ~9 h): do NOT wait for the 80 ft 4 in re-screen; measure now on run 128 greens; for the 4 in "just flag a column counting the number where the 4 in is known or is too close to call without a rescan" -- first draft, getting the foundation research going matters most. RUNNING: flats/fd2-pass1 (report-only job on 137, /root/fd2_pass1/); outputs fd2-pass1-summary.md + fd2-pass1.handoff.md in ../vicinitideals-worktrees/. Re-run after rel10.

2026-11-18 Steph, change of plan: "I'm actually going to have the design agent design the buildings to absorb the 4 in. So 80x25 is your finished-surface dimensions." The live 80 x 25 screen is correct; item 200 withdrawn; the fd2-pass1 job told to drop the lengthening and the 4 in column.

Soil notes (was item 196) LIVE 2026-11-18, main b5834c0d: every lot, all map units with sq ft, identifiers, winter water (main soil first). Greens: 9,517 with soil, 1,808 on more than one soil; ~4,030 "not rated" = Urban land complexes. Owed (federal soil web service was erroring 11-18; fill step ready, see ../vicinitideals-worktrees/soil-notes.handoff.md): the reasons behind each building rating and the national map-unit code -- FD2 pass 1 wants the reasons. Soil lot rows must be reloaded with each new county copy (runbook step S4).

2026-11-18 FD2 pass 1 FIRST DRAFT DONE for 9,517 greens: ../vicinitideals-worktrees/fd2-pass1-summary.md, fd2-pass1.handoff.md, fd2-pass1-data/fd2_lots.csv; branch flats/fd2-pass1 ee750a13 (carries hazard-notes). Still to come: flattest-position search (stage B, queued on 137 behind/with the rel10 bound, ~1 h, then re-copy csv + update summary); soil rating reasons (federal soil service down); seismic category (hub layer not public -> scout frost-seismic-scout.md); basement (not held). Missing: soil attributes 43.1% (Urban land top component), year built 3.7%, occupancy 4.4%; 22% of lots on 10 m ground (understates relief). Findings: (1) 11 Portland greens in FEMA 100-year zone near Johnson Creek, held FEMA layer has no Portland panels -> possible false GREEN, investigation fema-portland.findings.md RUNNING; (2) Urban land hides the soil on 3,992 lots; (3) frost: state hub layer says Multnomah 18, Clackamas 18, Washington 12 vs our register 12 on 7,138 lots -> scout settling it (197).

2026-11-18 SECOND DRAFT issued (flats/fd2-pass1 90fd7962; frost from the live register, USGS seismic stand-in, 80 x 25 finished surface; stage B pending banner). PASS 2 REQUESTS received from the foundation research (C:/Users/Steph/Repos/Factory-Sim/docs/research/FD5-lot-screen-pass2-handoff.md; their reading FD4-lot-summary-reading.md): (1) overlap of the placed footprint with existing buildings + assessor basement field + is the old building assumed removed; (2) stage B with flat_* beside the originals; (3) mapped artificial fill; (4) liq_majority; (5) soil rating reasons; (6) Oregon City + Sherwood frost; (7) door positions. No verdicts wanted; keep column names. Lane RUNNING on flats/fd2-pass1 -> ../vicinitideals-worktrees/fd5-pass2-summary.md. Stage B on 137 finishes when /root/fd2_pass1/stageB.log ends 'all done' (after the rel10 bound frees the lock).
