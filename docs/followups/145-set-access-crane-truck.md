# 145. Set access: can the delivery truck and the crane actually reach, park and lift on this site? (Steph 2026-11-03)

145. [Claude] [Steph: parameters + design review before build -- moderate feature] [scan: YES when built (colour policy TBD by Steph)]
   **Set access -- solve for the truck route, crane position and lifts on each lot.**

Steph 2026-11-03: "we need a followup for a moderate level feature: check site geometry for actually landing
the crane, the truck, access for both. Much like we do for driveways and it will need to be iterative/generative
since standard layouts won't really work. We'll just have parameters and something will have to solve for it
digitally."

## What it answers
For a lot that otherwise fits: can the panel truck get to a place within the crane's reach, can the crane set
up (outriggers on firm, near-level ground, clear of overhead lines and buildings), and can it lift every panel
from the truck to its final place in the building -- with the building, court and parking where the screen put
them? Output in the screen's usual form: pass / fail / unmeasured, the binding constraint, and slack.

This is FLATS_PLAN.md Phase 4 "Stage 8 prefab set access (truck route, crane footprint, overhead lines,
staging, grade)" -- planned, never started. The pod files say "module dimensions and crane needs are
unspecified until the set-access stage" (flats/config/pods/*.yaml).

## Parameters (Steph / the product supplies; none exist yet -- do NOT invent them)
- Truck: length, width, turning radius / swept path, axle loads; can it reverse in; trailer type.
- Crane: type (mobile truck crane / knuckle-boom on the delivery truck), outrigger spread and pad size,
  load chart (capacity vs radius), boom length, setup on the street (needs a street-use permit) or on site.
- Panels: largest/heaviest panel size and weight, number of lifts, set order.
- Staging / laydown area, if panels are not lifted straight off the truck.

## Site facts the solver uses (most already measured by the screen)
- Building footprint and placement, parking court, driveway (flats/fit, placement in flats/ingest/quadfit.py).
- Truck swept paths: the turning search already used for parking courts (flats/score/turns.py,
  flats/config/court_turns.json) -- reuse for the truck.
- Street width / right of way / street class per lot line (FOLLOWUPS 41), alleys, cul-de-sacs.
- Ground slope (FOLLOWUPS slope work, 502f67b3), water/wetland/flood ground (42).
- Neighbouring buildings (footprints), trees only as teammate-entered marks (rulings 2026-11-01).
- Overhead power: PGE + Pacific Power pole and line layers (FOLLOWUPS 144). OSHA 29 CFR 1926.1408 keeps a
  crane 20 ft from lines up to 350 kV unless the utility de-energises or a lower clearance is set up -- read
  the rule before encoding. Mapped lines are incomplete (Steph's spot check), so poles drive it.

## How (generative, not a menu of layouts)
Like the driveway/court search: generate candidate crane positions (street frontage within the right of way,
the court, the yard) and truck positions, keep those where the outriggers fit on near-level clear ground and
power clearance holds, then check every panel's lift radius against the load chart. Pass if any combination
works; report the best one (draw it on the lot page like the court). Same solver family as the parked parking
layout generator (FOLLOWUPS 92) -- design them together if 92 is revived.

## Open for Steph before any build
- The parameters above (or a first guess Steph signs off).
- Colour policy: a failed set-access check -> YELLOW flag first (likely), or RED?
- Street setup allowed by default (permit assumed obtainable) or on-site only?

## Steph 2026-11-11: parameters given, BUILD STARTED (absorbs former item 184)
- Crane: 100 in (8.33 ft) wide, 40 ft long, 28 x 40 ft setup pad (raw dirt OK) near the home;
  may enter/leave temporarily from any side with room, setbacks ignored; must be able to leave
  once the pod is up. Load charts (capacity vs radius) to come from Steph -- solver reports
  "unmeasured" until a chart is loaded.
- Pod as built: 30 x 80 ft, 4 homes 20 x 30; long walls front/back, short walls between homes.
  (pod80x25.yaml says depth 25 -- Steph to confirm 30.)
- Whole-stack lifts (6): ground walls 40 x 8'1" x 6'1" 12,074 lb; floor cassettes homes 1-2
  30 x 4'4" x 7'9" 4,414 lb (+ site container ~4,100 lb lifted separately); floor cassettes
  homes 3-4 4,414 lb (+ 4 stair kits 508 lb each + loose trusses); upper walls 11,625 lb; roof
  cassettes x2 30 x 6'4" x 7'9" 5,895 lb. +6 in blocking. Rigging per lift: lifting frame
  1,000-1,500 lb, long beam 800-1,100 lb, plus hook. Totals ~14,500-15,000 (walls), 7,000-8,500
  (cassettes).
- Single picks (50-65 + 6 stack lifts): front/back ground wall x8 20 ft x 8'1" 774 lb; upper x8
  711-724 lb; wall between homes x16 29'1" x 8'1" 725 lb; floor cassettes x12 30 x 4'-4'3.5" x
  15.5" 648-786 lb; roof cassettes x12 30 x 4-6' 864-1,194 lb (stair-side 6'3.5" wide); site
  container 10 x 8 x 8.5 ft ~4,100 lb. Heaviest single piece 1,194 lb.
- Lift governed by weight x radius: the solver finds every reachable radius from the site
  geometry and checks the farthest lift of each load against the chart.
- Assessment 11-11 (court proxy): a single-row court is ~36-54 x 42 ft, bigger than the pad;
  gaps: double-loaded courts, drive bends, far-end reach, overhead lines/trees, no-court lots.

## 11-11 slice 1 BUILT: flats/set-access 6e6669fb (not wired to screen)
Calculator only: pads around the placed pod, straight drive-out check, farthest radius per
load (truck->landing->set), chart check at next-longer radius, 75% flag (OSHA). Prior art:
nothing adoptable (4 unlicensed hobby repos). Turning paths + power lines (144) unmeasured.
Hand-off ../vicinitideals-worktrees/set-access.handoff.md.
Waiting on Steph (with the charts): loose-truss weight; stair kits ride with stack 3?;
frame+beam on single picks too?; truck load offset past lot line; upper-wall stack size;
straight-off-truck picks allowed?; pad max slope; street setup allowed; any cap below chart.
Chart needs: model, outrigger setup, counterweight, hook-block weight, deductions, capacity by
radius per boom length. Factory list to be redrawn for 20 x 25.

## Steph 2026-11-14: crane guide delivered
Guide: Factory-Sim repo docs/research/S3f-crane-28t-vs-45t.md (28 t Manitex 2892C = current plan, pick panels off the parked trailer; 45 t National NBT45-2 = whole trailer loads lifted off, then set from the ground). Load charts, outrigger spreads, pad sizes (~26x42 / ~28x42), piece weights for the 20x25 pod (heaviest panel 863 lb, container ~4,100-4,600 lb), truck turning (est) all in it. Supersedes the 11-11 piece list (30x80 pod).
Steph asked the cost of evaluating BOTH cranes. Answer given: the solver is the main cost either way; a second crane adds roughly a fifth to a quarter more build (charts as data + 360 vs rear-only swing) PLUS ground landing spots for the 4 whole loads (the real extra); scan time grows only on lots where the 28 t fails if run "28 t first, 45 t only on a miss". Offered: build both that way. Still open: colour of a failed check (YELLOW proposed), street setup allowed by default?

## Steph 2026-11-14: direction for slice 2
- **No colour.** "Don't flag any lots by color yet, we're just starting something from scratch." Output is a report only; nothing touches the screen colour, reasons or flags.
- **Two cranes:** 28 t first, 45 t only where the 28 t misses (offer accepted by going ahead).
- **45 t landing spot:** "consider the location of the truck that backs up as a valid landing spot. It'll be fairly level, and the size of the load." The whole load is set down where the trailer stood.
- **Street:** evaluate the site in front of the lot where we can: road width, and whether the crane's set-up fits there. Overhead power lines are NOT calculated now ("another job depending on the results of the on-site load"); Portland is mostly overhead lines, and craning over them plus utility buffers (up ~30 ft, across up to ~100 ft, down) is not seen as reliable. Report street set-ups as "power lines not checked".

## 11-14 slice 2 BUILT: flats/set-access-2 9c8f9ff0 (report only, not wired)
Order 28 t site, 45 t site, 28 t street, 45 t street; street only where recorded road width >= pad width, always "power lines not checked". 45 t lands whole loads on the truck spot. Finding: 28 t rarely works on site -- the site container (~6,150 lb rigged) must be within ~40 ft, rear-only swing puts it ~41 ft+. Sample-run command in ../vicinitideals-worktrees/set-access-2.handoff.md (run on 137 after the rel8 bound). Unmeasured: power lines, pad slope, boom height, turning paths, ground bearing. Steph questions on the sheet (Q21-25): container on the truck or separate, 28 t turntable position, load at the trailer back, stair kits/truss bundles reach, 75% of chart fail or mark.

## Steph 2026-11-14 (later): crane plan changed -- IC-80 primary, 45 t secondary, 28 t dropped
Spec: Factory-Sim docs/research/S3e-crane-20x25.md (fc9ead7). Primary owned Broderson IC-80-3H (9 t carry-deck, works from one long face); fallback hired 45 t NBT45-2; viability rule section 5 (IC-80 one face -> both faces -> 45 t -> not viable). Slice 3 being built on flats/set-access-3 (report only; power lines still not checked). Slice-2 questions on the 28 t (container reach, turntable) are moot.

## 11-14 slice 3 BUILT: flats/set-access-3 04616184 (report only)
IC-80 one face -> both faces -> 45 t site -> 45 t street -> not viable/unmeasured. Hand-off ../vicinitideals-worktrees/set-access-3.handoff.md (137 sample command). Judgements: one trailer spot serves the pod (both-faces carry fails at 800 lb rigging); roof-cassette stack 45 ft (stowed jib); 12 ft swing room. Steph questions on the sheet: container lift from the street or arrive another way; one parking spot per truck load; stair kit/truss/cassette hook height; 45 t jib stowed?

Steph 2026-11-14 answers: (1) container -- IC-80 may lift it from the street, yes; (2) one trailer on site at a time ("the empty trailer leaves before the new full trailer arrives") so each load parks where it suits; (3) per-piece hook height table now in the spec; (4) 45 t jib optional, assume on (cautious); 45 t hook ball 250 lb. Slice 3b building on flats/set-access-3.

## 11-14 slice 3b BUILT: flats/set-access-3 8f1fc121
Steph answers built. Both-faces still fails on the test lot at 800 lb rigging: loads 1 and 3 each carry front AND back walls, one park spot per load, so the far-face wall is carried round. Container street lift rarely helps (trailer between crane and lot). 45 t keeps one truck spot per lot. Offered Steph (sheet Q25): may the truck move part way through unloading, or can each wall load hold one face only (Factory-Sim repack item 223)?

Steph 11-14: "Packing is done to optimize for lifting, so whatever we want." Asked: per-site smart packing software, or one pack order? Answer given: ONE fixed pack order is enough (one-face lots do not care; both-face lots only need each wall load split by face). Catch: the set order (ground walls -> floor cassettes -> upper walls -> roof) puts both faces in the same load, so by-face packing means either 6 deliveries instead of 4, or one load packed in two halves (one face on top) with the truck moving once to the other side. Offered: build "two halves, truck moves once" in the report (needs a park spot on each face); waits on Steph picking halves+move vs 6 deliveries.

Steph 11-14: crane agent (Factory-Sim) agrees, picks A, and notes A needs no new packing (existing one-face stack order: far-face walls top, end/party middle, near-face bottom; truck parks back first, moves once to front; per-lot flip where crane only works from the back). Steph concern: does this restrict lots? Answer: no -- both faces is a fallback after one face, before the 45 t; it only adds lots, and only matters if the wall gear is heavy (~800 lb, engineer open). Slice 3c building A + sample at both gear weights so Steph sees the cost of heavy gear.

## 2026-11-15 first real sample (set-access-3 f59c08f3 on /root/bridge_rel8, 598 rel8 GREENs, 21 min)
Output 137 /root/set_access_sample_rel8 (summary.md, set_access.csv).
- Light gear (400 lb) / heavy (800 lb): IC-80 one face 2/0, both faces 1/1, 45 t on site 43/44, 45 t street 3/3, not viable 56/57, unmeasured 493/493. Gear weight changes 3 lots -- Steph's restriction worry is not where the limit is.
- IC-80 fails ~99% of lots, usually on several checks at once (light gear, per face front/back): trailer has no place clear of the working strip 491/529 (curb in front unmeasured on most); strip not level within 1% 462/414 (median lot grade 2.1%, quarter over 3.6%); back-face lifts (front walls at 32 ft over 75%) 148/477; swing room 278/221; strip off lot or into building 262/245; carry route unchecked ~250.
- Not viable concentrated in Portland (35 of 40 sampled), Wilsonville 11, Troutdale 8.
- Unmeasured mostly from missing data: curb position in front (1,642 mentions) and street pavement width (473).
Offered Steph: (a) a data job to get curb lines and pavement widths in front of each lot (turns most "unmeasured" into answers); (b) ask the crane side whether the 1% level applies to the whole strip or only under the outriggers/mats, and whether the trailer may stand at the curb in the street while the IC-80 unloads from the lot.

## Steph 2026-11-14 (after the sample): the small crane's real job, level, curb, trees
Steph: the IC-80 is meant to drive to a trailer parked in the street, pick under the wires, carry to the lot and lift; trailer on site is preferred (faster) but not needed. Crane spec 5dcd917: level applies only at each set-up spot's pads (~3% across the pads plus cribbing [est]; FOLLOWUPS 215(b) asks the leg range); between spots ground only needs to be firm to drive empty. Curb: Steph says ignore it (drive over, replace cheaply); trees matter more.
CONFLICT to settle with Steph's crane agent before carry is trusted: the spec still says "Cassettes cannot be carried" (S3e L619), the carry path must be "smooth, level and paved" (L386), and carrying a load under a line needs 20 ft from it (L418, 1926.1408). A front yard is usually not paved.
Offered slice 4 (report only, flats/set-access-3): pad-only level at ~3%; IC-80 street-trailer pick-and-carry with the carry rules as switches (cassettes carryable yes/no, carry path must be paved yes/no) so the sample shows both; trailer placed in the street along the frontage from the street lines we have (no curb data job); pavement width kept only for the 45 t street set-up; trees from the 2026-11-01 canopy layer on 137 (data/flats/canopy/2026-11-01) in the swing room and carry path; re-run the 598-green sample.

## 11-15 slice 4 BUILT: flats/set-access-3 2263ffc5 (report only; full flats suite green)
Pad-only level (~3% [est]); IC-80 street trailer placed from the street centreline, curb ignored; carry switches (cassettes_carryable default false, carry_path_must_be_paved default true; 20 ft line clearance noted, never checked); pavement width only for the 45 t street pad; canopy (2026-11-01) in working ground / carry path blocks, with a "without trees" answer per lot. Finding: even with cassettes carryable, the on-rubber chart refuses every cassette but the stair cassette (77-96% vs the 75% line), so carrying helps walls and bundles only. Sample queued on 137 behind the Hillsboro re-bound -> /root/set_access_sample_rel8_s4/summary.md (+ python3 /root/sa_analyse.py). Hand-off ../vicinitideals-worktrees/set-access-4.handoff.md.
Questions for Steph (to put with the sample numbers): (1) no paving data on lots, so every carry is "not measured" under the paved default -- use the regional hard-surface (impervious) layer as a paving stand-in? (2) canopy gives tree height, not branch height, so any tree blocks (cautious) -- right?

## 11-15 slice 4b BUILDING (spec moved to Factory-Sim 9985b64)
Steph's crane agent: cassettes carried flat CROSSWISE (hook 10.8-12.1 ft, 27-47% stowed, path ~27 ft; cross slope >3% -> 360 on-rubber column); walls unchanged (upright, 64-78%, flat-crosswise waits on 215a); carry route "paved" replaced by firm/even (not checked, no data) + downhill derate chart x (1 - 0.03 x downhill %); 3% pad level is NOT a carry rule; power lines: loaded carry = lifting, 20 ft (10 ft with <=50 kV), no loaded carry or trailer pick under a ~18 ft street line; street trailer works if truck on lot, line far side/rear easement, phone/cable only, or de-energised+grounded -- note on every street-trailer plan. The paving and impervious-layer question is moot. Steph 11-15: yes, any tree blocks for now (canopy gives height only).

## 11-15 slice 4b BUILT: flats/set-access-3 ec10aab7; sample on 598 rel8 greens (light gear)
Spec / trees left out: IC-80 5 / 25; 45 t 47 / 42; not viable 57 / 55; undecided 489 / 476. Walls flat-crosswise adds 1 lot. Trees cost ~20 IC-80 lots. Commonest IC-80 failures: trees, then street-trailer wall carry (no 6.5 ft path, or > ~1% off level). Most undecided stall at the 45 t street set-up: pavement width missing on 469 lots. Agent's cautious call: the 27 ft cassette path must stay clear right up to the hang point (~12 ft off a set-up spot), so a back face needs ~32 ft of open yard -- for Steph's crane agent to confirm.
Offered Steph: a quick search for street pavement-width data (scout first, then a lane only if a usable source exists).

Steph 11-15: yes, look for street width. Scout running -> ../vicinitideals-worktrees/street-width-scout.md; build lane only if a usable source exists.

## 11-15 street-width scout result (../vicinitideals-worktrees/street-width-scout.md)
Real pavement-width data covers only ~17-23% of the undecided sample lots: Hillsboro "Roadway" polygons (38), Washington County Paved Roads Width_Rd (35, county roads only), Oregon City edge of pavement (40, patchy), Tualatin (0 in sample). Portland/Wilsonville/Multnomah are already in the registry, but 4+7 lots still miss (a lookup bug). Nothing for Gresham, Clackamas County and its cities, Beaverton, Sherwood, Troutdale, Cornelius or Durham (~75%). Clackamas's licensed shapefile is a named centreline only (no width), so it is not worth accepting. OSM width tags are too sparse. ROW from taxlots is an upper bound only; the 1 m impervious raster merges sidewalks.
Offered Steph: (A) build the real-data lane (Hillsboro, Washington County, Oregon City, plus the Portland/Wilsonville lookup fix), ~1/5 of lots; (B) for the rest, an ESTIMATE from each street's ROW width less a standard sidewalk/planter allowance (or the city's narrowest street standard), always labelled estimated; (C) measure curbs from Metro's lidar (bigger job, covers everything). Recommend A + B now, C only if the 45 t street set-up proves to matter.

Steph 11-15: A and B. Building on flats/set-access-3 (real data Hillsboro/WashCo/Oregon City/Tualatin + lookup fix; ROW-minus-allowance estimate labelled estimated); sample -> /root/set_access_sample_rel8_s4c; hand-off set-access-5.handoff.md. C (lidar curbs) parked.

## 11-15 street width A+B BUILT: flats/set-access-3 0f159ea9 (report only)
Sources added 2026-11-15 (open, no licence): Washington County Paved Roads, Tualatin, Hillsboro Roadway, Oregon City edge of pavement. Estimate = ROW gap at frontage less a sidewalk+planter allowance each side (12 ft [est]; Oregon City standard read: 11 ft), labelled "width estimated". Portland lookup miss fixed. Sample (598 greens, spec): unmeasured 489 -> 272, not viable 57 -> 269, 45 t street measured 3 -> 6, estimated 0 -> 2; no decided lot changed. Of 469 width-missing lots: 104 measured, 290 estimated, 67 still none (no facing lot / curve). Newly decided 205, all not viable (~85 lift limits, 89 narrow on estimate, 35 narrow on measured). Hand-off ../vicinitideals-worktrees/set-access-5.handoff.md.
Offered Steph: sidewalk allowance -- keep 12 ft, use 11 ft, or read each city's street standard (43 sample lots fail at exactly 26 ft). Recommend reading the standards, 12 ft meanwhile.
