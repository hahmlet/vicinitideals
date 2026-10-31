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
- Smaller tier-1 districts still open: Oregon City Park Place/South End concept plans + historic
  districts (boundaries), Sunnyside Village, Wood Village TC, Sandy Bornstedt, Wilsonville Old Town;
  Portland plan districts (33.5xx) boundaries.
- Splice base now 137 /root/bridge_spliced_nb_maps, quadfit data/quadfit_2026-10-30_dd_c6.
