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

## Steph 2026-11-20 (chat), in rulings.yaml on the branch (8c4ecdd0)

- Ship it ALL AT ONCE: costs and the colour change in one release, the one after rel11.
- Near the cap (misses by 2 in or less): YELLOW.
- Front doors: toward the parking; with no parking, the face with more open lot. Where the city
  requires a street-facing entrance, toward the street as placed.
- Step prices: "Step prices are just estimates for a local provider" -- the Hampton list stands in
  for a local supplier; no delivery line, none asked of the foundation agent.
- Steph also asked whether end-on lots in places that require a street-facing entrance should be
  red "for now with a note". They are already YELLOW with ENTRANCE-SIDE-DOOR by Steph's 2026-11-10
  ruling; asked whether to switch (not changed).

## Status

- BUILT 2026-11-20: branch `flats/foundation-fd8` head 3d4a2a8a (rulings 8c4ecdd0), pushed, not merged.
  Hand-off `../vicinitideals-worktrees/foundation-fd8.handoff.md`. The cap runs inside the screen pass
  (last step, needs `--dem` and `--foundation-classes /root/foundation/run128_fd8/status.parquet`).
  FD8 key matches to the dollar; full FLATS suite green after one test fix (test_flatter, cap held off).
- Re-measure on 137 (`/root/foundation/run128_fd8`, run 128 drawings): RED 7,438 (570 now green),
  near-cap YELLOW 1,208 (224 green), class-unread YELLOW 319 (101 green). FD8 said 5,991; the stair-foot
  ground adds about 1,820, the real door positions and faces about 830. At the wall it would be 6,824.
  Told Steph; measuring where the stair lands is the physical answer, kept.
- Next: bound on the rel-next drawings after rel11 ships (BOUND SCOPE in the hand-off), move read
  (every GREEN-to-RED read for a true over-cap), release, then report counts to the foundation agent.
- Later (coordinator build call, not Steph): the flatter-placement search (FOLLOWUPS 57) does not try the
  cap, so a plan it moves can still be over the cap. Letting it try placements that clear the cap could
  rescue some of the 570.
- Answer to FD8 for the foundation agent: `../vicinitideals-worktrees/TO-FOUNDATION-AGENT-2026-11-20-v2.md`
 (asks key issue 3, railing as guard, side-entry units; delivery question dropped on Steph's word).
- Stair reach: Steph asked whether the 8 ft steps actually hit anything. The screen checks each door
  (off the lot, onto the court or lane) as a note only. COUNTED 2026-11-20 on run 128 drawings
  (`/root/stair_reach/` on 137, matches the cap counts exactly), 44,211 drawn lots:
  - off the lot: 5,968 lots (824 green), 4,680 by 1 ft or more, 2,043 by 4 ft or more; mostly front doors;
  - onto the court: 25,708 (7,887 green); onto the lane: 15,898 (712 green); any: 41,859 (8,655 green);
  - the court and lane are drawn flush to the wall (about 0.13 ft off), so ANY step on that face hits
    them -- the placement leaves no room for steps at all. At 6+ risers: court 4,294, lane 3,321.
  - Risers by worst door (lots not red): 1: 2,499; 2: 10,836; 3: 9,053; 4: 6,063; 5: 4,026; 6: 3,088; 7: 1,208.
  - ASKED STEPH 2026-11-20: (1) reserve the steps' room in placement (wall-to-parking strip and inside the
    lot), rides this release, re-bound -- recommended; or allow steps onto the paving; or note only.
    (2) where room can't be found: yellow (recommended) / red / note.
  - RULED 2026-11-20 (rulings.yaml 68e546fe on the branch): leave room; no room = RED with a flag
    (door, what it hits, by how much) so lots come back if parking, steps or door orientation change.
    Worker stair-room-builder building it on the branch.
- FD9 (foundation agent's reply to v2, `../Factory-Sim/docs/research/FD9-reply-to-flats-fd8-answer.md`,
  read 2026-11-21): key issue 3 built into FD6_foundation_model.py (11 test lots); one correction --
  platform measured from the larger of the wall and stair-foot drops (railing sides/cost only, cap
  unchanged); no stock side-entry units; railing stays the guard [est]; 2026 ORSC not yet read; our
  counts confirmed. Passed to stair-room-builder to fold in and match the key.
- STAIR ROOM + FD9 BUILT 2026-11-21: branch head a78c1ade (pushed). All 11 FD9 test lots match door
  by door; full FLATS suite 8,588 passed (3 local-only errors in test_foundation_lot_file.py, which
  still calls the old reference's as_flats_built -- move it to the FD9 reference before release).
  Estimated on run 128 drawings (sample): about 1,800 RED for no step room (626 green, 1,176 yellow;
  lot line 1,111 mostly Portland CM/CE drawn at the line; fire access after re-placement about 500;
  court 319; lane 373); about 15,200 re-placed with colour held; none improved.
  Move read must check the front-lot-line reds for a drawing window limit (e.g. `1N1E23BB  -19300`).
- Steps standing in setbacks: not modelled; FOLLOWUPS 214.
