# 109. Design districts (Steph 2026-10-21: "we do need to incorporate Rockwood (and other) design districts").

[Claude] Plan: docs/flats/design_districts_plan.md. Inventory: docs/flats/design_districts_2026-10-21.md
(84 districts, 62 reach the pod). Steph 2026-10-21: all go, ingest first, flat roof = RED, read the
WashCo plans, max 2 chunks a week. Rulings made along the way are in flats/config/rulings.yaml
(2026-10-21 frontage share as coded / wide lot more pods / King City all four doors; 2026-10-22
Gresham corner main street, Oregon City residence per unit, Sandy row houses not multi-family,
WashCo open space off site; 2026-10-28 King City average width per lot, Springwater no-alley yellow).

## Done (history in git)
- Chunk 1 LIVE run 84 (pdx-overlays-2 01a5d05d + frontage-share 45d8f5a7).
- Chunk 2 ingest 75afe352 (docs/flats/ingest_c2_2026-10-22.md).
- Chunk 3 LIVE run 85 (69382e2f), frontage-c3 eacc698b, 4bdfeb29 and the cr_bound rode run 87.
- Chunk 4 LIVE run 89 (6dbc54fd): Gresham CN*/Downtown/RTC/THR-SW, Troutdale TC, King City
  townhouses.
- Chunk 5 LIVE run 91 2026-10-30 (merge b9c87776, words fix 964cc28b). Tigard Washington Square
  (WSRC outline from city GIS, MUR traced from CDC Map 18.670.A), Estacada Downtown, Canby C-1
  floor-area minimum (short -> YELLOW + flag, never GREEN unchecked), Tualatin CO Block 1, Gladstone
  Town Center (traced from Ordinance 1539's adopted map, 2025-06-10 packet p149), Gresham DCC/DTM
  townhouse rows, Troutdale quarter-mile ring, King City corner fronts. Lot moves = the bound
  exactly (292): 152 to green (Gresham DCC 50 / DTM 53, Estacada D 16, Gladstone R5 14, Tigard
  MUC 9 / MUR 10 outside WSRC), 74 red->yellow (Tualatin CO 33, Gresham 22, Canby C-1 14, others),
  10 green->yellow (Gladstone C2 building-frontage rule), 56 yellow->red (Tigard MUC 50 / MUR 6
  inside WSRC). Drift 89->91 439 answers / 0 unexplained. Every GREEN checked against the traced
  lines: Tigard greens >= 297 ft outside, Gladstone R5 greens 88-100% inside.

## Left
- 2026-11-01 Steph (80%, OK to 90% this week): "do some overlays, see if we can wrap that up". Chunk 9 (zone-keyed, no maps needed): Clackamas Sunnyside Village 1005.11, Wood Village Town Center street types (Table 235-5), Wilsonville Old Town OTR 4.123 + overlay 4.138 re-ruling, Sandy Bornstedt 17.54 text. In parallel a source scout for the map-keyed ones (chunk 10): Oregon City Park Place 17.21 / South End 17.22 / historic 17.40 boundaries, Sandy 'S' overlay, Wilsonville Old Town overlay outline, Portland plan districts 33.5xx layer + text.
- 2026-11-01 scout: boundaries for Oregon City (17.21/17.22/17.40) and Portland (plan districts, historic, conservation) already in flats/config/areas from the 10-22 ingest; Sandy 'S' and Wilsonville Old Town are map-only (traced in chunk 9). Chunk 10a CHECKED 2026-11-01, nothing to change: Oregon City Park Place (13 RED, roof pitch) / South End (21 GREEN, per-unit residence ruling) / 17.40 historic (942 RED, hearing) were done in chunk 3, Portland 33.445 (historic 4,749 RED, conservation 3,004 red / 102 yellow) in chunk 1; status layer covers vacant lots. Historic RED (not yellow) is the standing 2026-10-14 tier + 10-15 statute exception ruling. LEFT AFTER: Portland plan districts 33.5xx -- 24 chapter texts in flats/provenance/pending/or/multnomah/portland, 25 districts with residential land (Johnson Creek 4,647 ac, Northwest Hills 2,283, East Corridor, Glendoveer, Albina, ...); Laurelhurst/Eastmoreland special setback maps not online. Likely 2 chunks; next week.
- Gladstone Portland Ave C-2 strip: rear edge of the Town Center line unconfirmed; 20 cut lots stay
  yellow until a better map turns up.
- Chunk 6 LIVE run 94 2026-10-30 (main af509800; 32cf3a0e encoding, 550899fa + 12a3b298 Tualatin CO quadfit row):
  the 4 largest WashCo plans read; only North Bethany binds (special setbacks, Park Blocks, Kaiser Main
  Street on R-15 NB / R-24 NB, held behind unmeasured facts). 34 moves, all read right: 33 Tualatin CO
  yellow->red (use not allowed outside Block 1), 1 R-15 NB green->yellow. Follow-ups 129 (trace the
  maps) and 131 (CO overlay minimums) LIVE run 97 2026-10-30 (4b80f4ef, 729daaa1; 0 colour moves,
  683 lots' flags/reasons; splice base now /root/bridge_spliced_nb_maps); 130 (Bethany ASC 1) ruled
  green with a flag, ASC 1 trace owed.
- Chunks 7-8: WashCo's seven smaller community plans, unread (Raleigh Hills - Garden Home 6,022 lots and
  Bull Mountain 3,847 next).
- Smaller tier-1 districts still open (Oregon City concept plans + historic DONE, see 2026-11-01): Sunnyside Village, Wood Village TC, Sandy Bornstedt, Wilsonville Old Town;
  Portland plan districts (33.5xx) boundaries.
- Splice base now 137 /root/bridge_spliced_nb_maps, quadfit data/quadfit_2026-10-30_dd_c6.

- 2026-10-31: chunk 7 LIVE run 101 (16ab319d; 16 green->yellow). Chunk 6b (was FOLLOWUPS 134/135/136: WashCo local street connectivity on R-5..R-25+, plan rules / pedestrian areas / ASCs held, Bethany ASC 3 flag, Raleigh Hills ASC U flag) LIVE run 103 (8077332e; 280 green->yellow, fingerprint a7f0be94). Splice base on 137: /root/bridge_spliced_districts_c6b. Optional, offered, not asked for: narrow the connectivity hold to lots big enough to need a street (~5 lots).
- 2026-10-31: chunk 8 + FOLLOWUPS 137 LIVE run 105 (3d0d9787; 16 green->yellow, md5 569b1902), East Hillsboro overlay LIVE run 107 (FOLLOWUPS 138). All eleven WashCo community plans now read. Splice base on 137: /root/bridge_spliced_east_hillsboro. Steph 2026-10-31: Metzger unnamed outlines stay yellow (ruling).
- 2026-11-01: chunk 9 (e8861fcf) + Portland part 1 (ff8525ab) LIVE run 111 (stacked bound, fingerprint b7aca5fc over 450 lots: green->red 34, green->yellow 407, yellow->red 9). Splice base now /root/bridge_spliced_districts_pdx_pd1, assign /root/assign_districts_pdx_pd1. NEXT: Portland 33.5xx part 2.
- 2026-11-01: part 2 inventory (21 chapters, maps held / not held) in [109-pd2-inventory.md](109-pd2-inventory.md). Gaps: Maps 510-12..23, 521-4, 532-3, 562-7, 595-2, NH Hillside subarea.
- 2026-11-04: part 2 BATCH A built (flats/districts-pdx-pd2a 105c1d37, pushed; hand-off ../vicinitideals-worktrees/districts-pdx-pd2a.handoff.md).
  Glendoveer R7 setbacks 30/10/15 (every R7 lot in GL read as old LR7.5); one review hold (FACT-PDX-PLAN-DISTRICT-UNMEASURED) for
  EC, HW, KN, LB, MA, NI, NH-Linnton, WP (~224 green->yellow) incl. EC Map 521-3 min building size areas whole (~167; figures on the
  map only, not in stored text); 7 chapters read and dismissed. 0 gains expected. Bound queued on 137 (tag pd2a). QUESTIONS for
  Steph 2026-11-04: (1) ask the City for the list of former LR7.5 lots in Glendoveer? (2) fetch the Map 521-3 sheet so small East
  Corridor lots can go back to green? Batch B (510/562/532/565/580) next.
- 2026-11-04: BATCH B built (flats/districts-pdx-pd2b 5e2a8551, STACKS on pd2a; hand-off districts-pdx-pd2b.handoff.md): Gateway 377,
  Northwest 58, Sandy Blvd 30, Hayden Island 11, Powell 11, Columbia South Shore 10, Central City 7, South Auditorium 3 green->yellow
  into the shared hold; RM4/RX/CX/EX join the hold. Coordinator rulings (standing rules): NW 33.562.100.B CM3 on Map 562-2 = RED
  (flat prohibition, >20% residential); NW main streets traced by eye accepted (54 greens to check in the move read). Bound pd2a+pd2b
  TOGETHER (replace the queued pd2a tag). QUESTION for Steph: download the City's map sheets (Gateway min building size, East Corridor
  Map 521-3) so the figures can be read off them (drawn:true form) and small lots reopened?

