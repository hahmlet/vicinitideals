# 204. Overlay inventory: mapped areas the screen does not hold

**Status:** hunted 2026-11-18 on run 128 (report ../vicinitideals-worktrees/overlay-inventory.findings.md; lists overlay-inventory-lists/; layers data/flats/books/overlays/). Every jurisdiction's published overlays compared with what the screen holds. Fix lanes: flats/overlay-fixes-a (1, 2, 7) and flats/overlay-fixes-b (3-6, 8), both from rel10d, ride the release after rel10. Second scout: overlay-inventory-2.findings.md (the places not checked).

FALSE GREEN classes (greens touching):
1. Portland scenic overlay "s" -- 25 greens; PCC 33.480.040.B.2 20 ft building setback from the scenic street; building as drawn inside it on 8, 4 more on N Willamette Blvd likely. Not held at all.
2. Oregon City Geologic Hazards overlay -- 21 greens; OCMC 17.44.060.H caps density at 2 homes/acre where the building stands in a mapped landslide or buffer (8 lots, + 1 on steep slope; all under an acre -> fail). Other 12 need the review but building is clear.
3. Beaverton historic inventory -- 8 greens (BDC 40.35.15.3; 2 ranked, 6 "unrankable"; designation unconfirmed).
4. Beaverton Significant Groves -- 8 greens, building in grove on 6 (BDC 40.90.15; judgement review -> flag).
5. Washington County historic list -- 5 greens (should be yellow by the screen's own reading).
6. Milwaukie historic list -- 2 greens (MMC 19.403).
7. Oregon City Willamette Greenway -- 1 green (OCMC 17.48), not held.
8. Milwaukie Willamette Greenway -- 12080 SE 19th Ave green with a flag while the rule file says the greenway is not lifted: needs a look.
Counts only: Gladstone greenway 1, West Linn greenway 1.

NOT CHECKED (no public map found): Clackamas County unincorporated (459 greens: floodplain, stream conservation, greenway, historic, airport); Canby, Cornelius, Estacada, Sandy, Durham, Sherwood, Happy Valley (126 greens); Hillsboro cultural resource sites + PD boundaries; Beaverton planning map folder (login) + 3 layers; failed downloads: West Linn steep slope, 2 layers each Oregon City and Gresham, regional 1996 flood. Also from loose-reads: Sandy flood and slope hazard overlay 17.60.30 not held (10 Sandy greens); Canby hazard/wetland/riparian chapters not in the library (403; 40 greens).

Clean: every other published overlay for Portland, Washington County, Hillsboro, Gresham, Milwaukie, West Linn, Wilsonville, Troutdale, Gladstone, unincorporated Multnomah.

2026-11-18 BUILT flats/overlay-fixes-b ed878b81 (from rel10d; hand-off ../vicinitideals-worktrees/overlay-fixes-b.handoff.md): 12 greens -> YELLOW 'historic listing unsettled' (Beaverton 8: only Council-designated landmarks are protected and the held list is the 1984-86 survey; Milwaukie 2: demolition delay up to 120 days only; Washington County 2). Beaverton groves: ~650 lots gain a flag, no colour change (2026-10-15 judgement-only ruling + 2026-11-01 ignore-trees ruling). Milwaukie 12080 SE 19th Ave and the West Linn greenway lot: GREEN is right. Gladstone greenway lot right but unflagged (no map). STEPH (non-blocking): 2 Beaverton lots also in the city's register of historic sites -- yellow or red; 6050 SW Old Scholls Ferry Rd removed from the county list in 1991 -- drop or keep yellow. Second scout done: overlay-inventory-2.findings.md (data layers got; Clackamas RSCA/greenway/hazard and Sandy maps PDF-only; WQRA map, county historic inventory, Canby wetland inventory office-only). Check of the 585 unverified greens RUNNING -> clackamas-overlay-check.findings.md.
