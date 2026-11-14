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
