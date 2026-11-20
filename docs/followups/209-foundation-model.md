# 209 -- Foundation model per lot (how the foundation sits, what it takes, what it costs)

**Asked by Steph 2026-11-19:** "I want to build out as part of our scan an understanding of how the
lot's foundation will work and therefore what we can expect on cost." This lifts the 2026-11-12
"no build cost work" rule for foundations only.

## What

For every lot with a drawn building: floor level, wall height at every foot of every wall line,
steps at each of the eight doors, concrete / bars / form face / rock fill, cost low and high for
slab-on-fill (A) and raised floor on a wall (B, and B on screw piles), flags, and the cost exposure
if an old building under the pod had a basement. **It never changes a lot's colour** (Steph: steps
are counted, never capped; a flag never removes a lot).

## Where the design lives

The foundation agent's research, in the sibling repo, read in place, never modified:
`../Factory-Sim/docs/research/` (branch `claude/factory-housing-sim-research-xga5t5`, latest FD6/FD7
committed there but not pushed).

- `FD6-foundation-model-spec.md` -- the build report. Start here. Section 8 has the test tables.
- `FD6_foundation_model.py` -- the answer key (needs `FD3_flat_lot_takeoff.py`, `FD4_lot_reading.py`).
- `FD1`, `FD3`, `FD4`, `FD7` -- research behind the settings; `FD7` = building over filled basements.

Lot file the research ran on: `../vicinitideals-worktrees/fd2-pass1-data/fd2_lots.csv` (9,517 lots,
195 columns; from branch `flats/fd2-pass1` 56806fe1, not merged; hand-offs `fd2-pass1-summary.md`,
`fd5-pass2.handoff.md`, `fd5-pass2-summary.md` in the same folder).

## Plan

1. **Calculation (FD6 build steps 1-7)** -- `flats/foundation/`, settings in
   `flats/config/foundation.yaml` (every value with its source label), tests that reproduce the FD6
   section 8 tables and the eight any-ground checks; a script that runs the lot file in place and
   reproduces the section 8 shares. Worktree branch `flats/foundation-model`. No screen wiring.
2. **Real ground (step 8)** -- on 137, read the ground grid under each drawn building (the code that
   made the six readings is on `flats/fd2-pass1`); compare with the six-reading result.
3. **Ground support and old buildings (step 9)** -- sorting into ordinary / piles / own look; wall
   stretches over old building outlines; basement likelihood by year built.
4. **Into the scan and onto the page (step 10)** -- per-lot results stored with the run, a foundation
   section on the lot report, and export. Needs a design note first: which lots, which table.

## Decisions taken by the coordinator (tell Steph, change if they say so)

- Built in FLATS, not Factory-Sim (Steph: "as part of our scan").
- Every lot with a drawn building gets a result (green and yellow).
- Cost basis as the foundation agent set it: materials plus unavoidable hired services; low and high
  never averaged.
- Not part of rel11.

## Steph 2026-11-19, second message: go, and keep it cheap to re-analyse

"We will want to tweak costs and such later, so get what data you can about foundation style, challenges, and easy parts so we can run cheap analysis."

So: two layers. MEASURE stores every physical fact per lot once (no prices; per-lot row plus per-door and per-wall-line tables, richer than FD6 section 2). PRICE is a pure step over the stored record plus the settings file, and gives cost lines, style, a list of challenges and a list of easy parts. A price or threshold change re-prices every lot without touching the ground or the scan.

## Open

- Framed low wall on top of a shorter concrete wall as a variant (FD6 section 11): engineer's call.
- Code rules marked "recalled" in FD6 section 4 (R312 guard height, R311.7.8 handrail, R401.3,
  R311.7.3): re-read against the ORSC before the numbers go on a page.
- Step-free entry requirement in any jurisdiction (the foundation agent's FOLLOWUPS 237).

## Status

2026-11-19: step 1 lane started (builder agent, branch `flats/foundation-model`).

2026-11-19 evening: step 1 DONE on `flats/foundation-model` a02a75eb (not merged). Every FD6 section 8 value matched; lot-file shares match; 144 foundation tests; measure and price layers split, re-price test passes. Nine spec-vs-reference disagreements listed in `../vicinitideals-worktrees/foundation-model.handoff.md` (to pass to the foundation agent). Ties follow the rule as written. Slice 2 started: real ground on 137 for the 9,517 lots (light work only), old buildings (spec 5.8, FD7), own frost depth.

2026-11-19 night: SHIPPED. main a29a596c, deploy smoke passed, migration 0153, 9,514 lot records loaded
(9,441 match the current county copy), production E2E `tests/e2e/test_flats_foundation.py` passed, colours
unchanged on eight compared lots. Slices: 1 calculation (answer key matched), 2 real ground on 137 + old
buildings, 3 table `flats` lot foundation + API `foundation` block + lot-page panel + `reprice` command.
Data and the grid-vs-six-readings report: `../vicinitideals-worktrees/foundation-model-data/`. Hand-off with the
nine spec-vs-answer-key differences: `../vicinitideals-worktrees/foundation-model.handoff.md`.

## Left to do

1. **Re-measure after every release** that moves a drawn building (about 2 minutes on 137: measure, bundle,
   copy `records.jsonl.gz` to 114, run `scripts/flats_foundation.py load`). The stored record does not notice a
   changed drawing by itself. Add it to the release runner's routine.
2. **Widen from the 9,514 research lots to every lot with a drawn building** (green and yellow). Needs the
   pass-1 inputs (six readings are not needed; the grid reader is) for lots outside the research file.
3. Four lots with blank ground cells (1S2E15AB  -00100, 1S2E03CD  -02900, 1S2E10DB  -11900, 1S2E10DC  -16100) and
   2,128 coarse-ground Portland lots: reported apart; no fix planned.
4. Screw-pile version (B+P): not priced over old basements; no per-lot answer key exists.
5. Pass the nine differences and the grid findings (lump allowance about 20% small) back to the foundation agent.
6. Code rules marked "recalled": re-read when the residential code chapters arrive (FOLLOWUPS 210).
