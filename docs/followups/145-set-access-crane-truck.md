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
