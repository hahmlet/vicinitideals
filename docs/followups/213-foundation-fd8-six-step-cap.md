# 213 -- Foundation agent's reply (FD8 v3): adopt it, and RED where no foundation method fits the six-step cap

Opened 2026-11-20. Source: `../Factory-Sim/docs/research/FD8-reply-to-flats-foundation-run.md`
(version 3, Factory-Sim commit b134fd9; read in place, never modified). It answers
`../vicinitideals-worktrees/TO-FOUNDATION-AGENT-2026-11-20.md` (FOLLOWUPS 209 item 5).

## Steph's decisions carried in FD8 (2026-11-20, given to the foundation agent)

- Outside steps are precast units with stock aluminium railing, priced door by door from the
  Hampton Concrete Products public list plus 10% (the 10% for steps only).
- **Six-step cap at any door.** A method that needs more is not used on the lot. **A lot where no
  method fits is RED** (no retaining walls modelled). FD8 reads it per method (5,991 red of 44,211
  drawn lots on today's door positions: 330 green, 5,661 yellow); "red if either fails" would be
  20,977. The per-method reading was told to Steph.
- Doors swing inward; raised floor stays 18 in up; crawl access is a floor hatch under each stair.
- Old basements: two scenarios (has / no basement) with the likelihood by year built, not one
  weighted figure.

## What FD8 recommends (full tables in FD8 sections 2a to 2e)

- Price/threshold only (re-price, no re-measure): riser 7.25 in, tread 11, landing 42 in, third
  level bar over 60 in, end and party footings 15 in, precast unit price table and railing sides,
  the cap per method, engineered stops (A edge over 48 in; B wall over 10 ft or the storey rule),
  shares over open methods, basement scenarios, outlines under 400 sq ft left out, fill-flag
  formula (+ strip soil), label changes.
- Geometry (re-measure on 137, ~20 min): real door positions, separate front and back lists
  (Factory-Sim `config/product.yaml`); ground read along a line out from each door where the
  stair lands; guard tested to the lowest ground in a box 6 ft out x 5 ft either side; stepped
  footing; steep-ground (over 1 in 3 within 10 ft) flag.
- B on piles: 10 in wall, four level bars a line, "engineered" flag; 34 piles confirmed.
- Front face a guess (21,939 lots): test the cap both ways round, use the worse.
- Seismic category: D0 or D1 everywhere in the three counties; every "D0 to D2" rule applies.
- Re-issued FD6 key (issue 2, framing size, real doors) and FD3 takeoff; `--as-flats-built`
  reproduces our test-lot figures to the dollar. Key issue 3 (precast + section 2d) still to come.

## Plan (coordinator, pending Steph on the open points)

1. Slice A, worktree `flats/foundation-fd8`: everything above inside the foundation panel. No
   colour change. Ship, re-measure, reload. The panel shows "no method fits: would be red".
2. Slice B: the colour change, as a screen reason with a bound and a move read. Rides the release
   after rel11 so rel11 is not delayed.

## Open (Steph)

- Lots that fail the cap only because the front face is a guess: red (FD8) or yellow?
- Lots within about 2 in of the cap: red as measured, or yellow?
