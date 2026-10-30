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
- Tualatin CO: quadfit has no CO entry, so its 33 lots are yellow "not measured" -- add the entry.
- Gladstone Portland Ave C-2 strip: rear edge of the Town Center line unconfirmed; 20 cut lots stay
  yellow until a better map turns up.
- Chunks 6-8: WashCo's eleven community plans (68,777 lots), unread.
- Smaller tier-1 districts still open: Oregon City Park Place/South End concept plans + historic
  districts (boundaries), Sunnyside Village, Wood Village TC, Sandy Bornstedt, Wilsonville Old Town;
  Portland plan districts (33.5xx) boundaries.
- Splice base now 137 /root/bridge_spliced_1029_c5, quadfit data/quadfit_2026-10-29_c5.
