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
- **Code numbers re-read against the printed 2023 ORSC, 2026-11-19** (chapters 1 to 4 arrived from
  Steph; reader's full findings: `../vicinitideals-worktrees/orsc-foundation-read.findings.md`).
  Of 20 code-sourced settings: 9 confirmed, 2 differ, 5 right number but a condition ignored,
  4 not found in the cited section. NOT changed in FLATS: the settings are the foundation agent's,
  so the findings go back to it (through Steph) and FLATS follows its answer. The ones that matter:
  - Stair riser: the model uses 7.75 in; Oregon's maximum is 8 in (R311.7.5.1). Counts more steps
    than the code needs.
  - Mid-height bar: added over 48 in in the model; the printed table adds it over 60 in. Overprices.
  - Guard: the 30 in is measured to the ground anywhere within 36 in out from the edge, not just
    under the landing. On ground falling away the model can miss a guard (the one unsafe-side gap).
  - Landing: 8 in drop only where the door does not swing over it; no top landing needed at a
    door other than the main exit when the outside stair has 3 risers or fewer.
  - Not found where cited: "plus 2 bars per wall line", 26 in edge depth, 24 in fill limit (cites
    chapter 5, not held), 16 in party strip (the table gives 15 in). End and party footing widths
    of 12 and 14 in are under the table's 15 in for two storeys on 1,500 psf soil.
  - Not held at all: slope setbacks for footings (R403.1.9, slopes steeper than 1 in 3), fill
    under footings must be designed and tested (R401.2), a tall crawl space counts as a storey
    (over 6 ft above grade round half the building, or 12 ft anywhere), 6 in fall in 10 ft away
    from the building (R401.3), continuous footings under interior bracing walls for a building
    over 50 ft long in the higher earthquake categories, crawl access.
  - **The 2026 ORSC has been mandatory since 2026-10-01.** Only its Chapter 1 is held. Its
    chapter 3 is renumbered (guards become R321), so every R311/R312 citation here is a 2023
    number, and none of the above is checked against the 2026 chapters 3 and 4.
  - The slope setback (R403.1.9) could also be a screen matter on steep lots: not looked at.
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

2026-11-20: slice 4 SHIPPED. main 2342792a, deploy smoke passed, 44,211 records loaded (every drawn green and
yellow lot of run 128), measured on the framing footprint 79 ft 8-3/4 in x 24 ft 8-15/16 in; production E2E passed.

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
7. Tell the foundation agent: the FLATS model now measures and prices the FRAMING footprint (79 ft 8-3/4 in x
   24 ft 8-15/16 in centred in the 80 x 25 ft finished faces; DECISIONS N-finished, FOLLOWUPS 238(i)); its FD6
   answer key (`FD6_foundation_model.py`) and the FD3 takeoff are still on the old sizes (80 x 25 ft walls,
   80 ft 3-3/4 in fixed lines), and our answer-key tests run on those as explicit overrides.
