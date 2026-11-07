# Follow-ups offered but not yet done

Agent-maintained queue, kept as an INDEX: one line per item here, the item's
full text in its own file under [followups/](followups/). A worker given one
item reads only that file. Human-action items live in
[HUMAN_TODO.md](HUMAN_TODO.md), not here. "Do the next thing" means the first
item of section 1.

How to keep it:
- Numbers are stable IDs, never reused or changed; items sit out of number
  order across the sections. A new item takes the next unused number (128
  onward), gets a file `followups/N-short-slug.md` (`# N. Title`, then the full
  text) and one index line in its section. A moved item leaves a one-line
  pointer (27b).
- Index line: `N. [lead tags] **Title** -- one-line current status. [file](...)`.
  Whenever an item's file changes status, update its index line in the same
  commit.
- When an item is DONE, delete its file and its index line (git keeps the
  history). Whoever next works an item first trims its finished history down to
  one line with the commit SHAs (lazy slimming).

Sections, by WHO does the next action:
1. **Claude -- priority**: most urgent first -- (1a) the weekly re-screen's
   traps and its moves to read, (1b) built lanes waiting to merge, (1c) the
   rest, (1d) the finance items (kept word for word).
2. **Waiting on Steph**: nothing moves until Steph answers, sends something or
   says go; Claude does the work after.
3. **Copilot queue -- low priority, not time-sensitive**: each item is a
   cold-start brief. On the 1st of each month the queue is fired (batches of
   4) until Copilot's quota is gone (item 91 has the rule).

Tags: `[Claude]` reading or encoding code text, rulings, reading bound or
weekly moves, anything that changes lot answers or must land before the
weekly, anything with a deadline. `[Copilot]` only when ALL hold: build work
a test can prove (tests, tooling, show-only UI, plumbing, identical-output
refactors, docs; or a small rule tweak whose ruling is made and whose exact
values the brief names); no decision from Steph and no judgement reading of
code text; nothing waits on it; it can be run cold. `[Steph: ...]` names a
sub-part that waits on Steph inside an item that can otherwise move.
"(x) Copilot-able" marks a sub-part that could go to Copilot on its own.

`[scan: ...]`: YES = the work changes lot answers, so a before/after scan on
137 must be read before it ships; NO = tests are enough; "NO new code, check
after the weekly run" = already deployed, its moves are read when the weekly
full re-screen lands. (Index lines carry a shortened tag; the item file has
the full one.)

## 1. Claude -- priority

150. [Claude] [scan: YES -- toward red] **Rear-court sharing may be wrong in Gresham (QP, no alley), Sandy, Troutdale -- FALSE GREEN RISK** -- found 11-05 by the 146 reading; BUILT e2badec3 (flats/rear-court-150, pushed); RULED Troutdale 10 ft + doubt flag 11-05, round 2 73ac9be7; bound rear_court150 READ 11-05: HOLD (Troutdale doubt never drawn, 20 ft on every side, Sandy 24E14DA00700 false gain) -> round 3 c89c1057 (pushed) -> re-bound rear_court3 READ 11-06: HOLD (drawn check gated off on unsigned rules -> 132 Troutdale false greens; Sandy strip quit at 5 ft; Gresham five -> item 151) -> FIXED 10cc88b4 -> 133-lot mini check: 45 Troutdale false greens still stood (tolerated fits never drawn-checked; screen gate on signed rules) + Sandy check matched no real lot -> FIXED 553af386 (pushed), mini check clean (16 more to yellow, no new greens) -> re-bound rear_court4 QUEUED on 137 (vs rel2). [file](followups/150-rear-court-sharing-check.md)
151. [Claude] [scan: YES -- toward red only] **A fit with no window wide enough reads as a 0.5 ft near miss (depth never scored)** -- BUILT 11-06 a68b2ec7 on flats/width-short-depth, full suite not yet run on it; moves colours toward red, needs a bound or rides the ~11-10 re-screen. (followups/151-width-short-hides-depth-miss.md)
147. [Claude] [scan: YES -- toward red] **Maximum front setback never checked on its own -- FALSE GREEN RISK** -- found 11-04 (Tigard 2S103AA00300 green 60 ft back, max 20); BUILT 20fbf9ed (flats/max-front-setback, pushed): ~2,500 live greens exposed (166 beyond on every street -> RED, ~1,600 some streets, ~740 turned wall -> YELLOW); readings DONE, round 2 586a7b9b pushed, bound max_front DONE 11-05 (1,824 moves: 1,257 greens lost, 2 gained) READ: HOLD -- ~13 live greens still pass (separate frontages merged; through-lot plan drops a street) + 1 wrong gain, ~175 wrong reds (max-front-setback.moveread.md) -> Copilot r3 RUNNING, re-bound max_front + hb_active (done on old code, re-run after); South Hillsboro active streets RULED 11-04 (trace, green+flag) -> BUILT e2f5546d (flats/hillsboro-active-streets, stacked on max-front, ~103 lots, none green today); bound hb_active queued after min_far [file](followups/147-max-front-setback-unchecked.md)

148. [Claude] [scan: YES -- both ways] **Minimum floor area: red only when more pods clearly cannot fit** -- RULED Steph 11-04; replaces always-yellow min_far and always-red Portland main street (~1,600 red); BUILT 27934967; bound min_far READ 11-05: 746 red->yellow all right -> LIVE run 118 2026-11-06 (with 118, rel1, f71cf172); fix-forward: 3 part-overlay lots stay RED that should be YELLOW (moveread F1). [file](followups/148-min-floor-area-more-pods.md)

### 1a. The weekly re-screen: traps to honour before it, moves to read after it

- Weekly re-screen state -- run 87 PROMOTED 2026-10-28; NEXT full re-screen ~2026-11-10, splices in between. [file](followups/weekly-rescreen.md)
67. [Claude] **Washington County makes the owner hand over road land first (CDC 302-2.14 C(1) ...)** -- MERGED; moves READ at run 78; only (b) open (tax lot includes the roadway). [file](followups/67-wash-co-road-dedication.md)
77. [Claude] **Road land to the centre line in the cities, not just unincorporated Washington County** -- MERGED; READ at run 78; OPEN: Tigard not encoded, segment qualifiers, lot area. [file](followups/77-city-road-dedication.md)
78. [Claude] **Portland false GREENs: main street minimum floor area and protected historic buildings are RED** -- MERGED 2026-10-15; READ at run 78, exactly the bound; "Still open" list in file. [file](followups/78-portland-false-greens.md)
80. [Claude] [Steph: (a), (c)] [scan: (a)(b) built] **Readings for Steph from item 64 round 2** -- (a)(b) RULED + BUILT, r3 merged; (d) LIVE run 113 (main afb7ad39; Estacada, Canby, Sandy stall counts; 90 moves); (c)(e) open; 1S113BA07700 question waits on Steph. [file](followups/80-item64-round2-readings.md)
76. [Claude] [Steph: (c) assessor lookup] **Tigard pod80x25 red at exactly -43 ft, and split-zoned lots** -- (a)(b) READ at run 78; only (c) open. [file](followups/76-tigard-minus-43.md)
84. [Claude] **Frontage caps read as caps on every street** -- MERGED, READ at run 78; only Fairview VC open. [file](followups/84-frontage-caps.md)
42. [Claude] [scan: NO new code, check after the weekly] **Water, wetland and flood ground at slope's fidelity** -- DONE and live; check after the weekly run. [file](followups/42-wetland-flood-fidelity.md)
29. [Claude] [Steph: (C) county widths, deferred] [scan: YES for (C)] **Fire reach: measure where the truck really stands** -- RULED 2026-10-05 ("stricter"); (A)/(B) checked after the weekly; (C) deferred. [file](followups/29-fire-reach-truck.md)
30. [Claude] [scan: NO new code, check after the weekly] **Net land area review** -- SHIPPED (run 61, 183 values, slopes 995f0007); check after the weekly run. [file](followups/30-net-land-area.md)
36. [Claude] [Steph: the OAR strip question] [scan: YES] **Parking tool queue** -- mostly LIVE (f7ba7038, 1723db45); OAR strip question open. [file](followups/36-parking-tool-queue.md)
44. [Claude] [scan: NO new code, check after the weekly] **Readings ranked on the map's colour, and 43's hose edge** -- SHIPPED 51577bb8; wait for the next weekly run. [file](followups/44-reading-rank.md)
51. [Claude] **Tigard and Cornelius switched on** -- DONE 2026-10-14, run 73 LIVE; one check after the weekly. [file](followups/51-tigard-cornelius.md)
8. [Claude] [scan: NO new code; YES if (b)] **Pockets + corridors -- leftovers** -- on main since run 65; two checks not recorded as done. [file](followups/8-pockets-corridors.md)
33. [Claude] [scan: YES for (c) and speed-ups] **Parking court leftovers** -- ca26e048 LIVE (run 63); (b), (c) still open. [file](followups/33-parking-court-leftovers.md)
21. [Claude] [Steph: worktree go; HUMAN_TODO 26] [scan: YES (a)-(c)] **Post-2027 world** -- sources STORED 2026-09-30; waits on Steph's worktree go. [file](followups/21-post-2027-world.md)
64. [Claude] [scan: NO] **Measure the false-GREEN rate** -- reading exercise: ~100 GREEN lots read blind, repeated each weekly. [file](followups/64-false-green-rate.md)
95. [Claude] **Weekly 2026-10-19 DONE 2026-10-20** -- DONE; gains and losses read; remove at the next weekly. [file](followups/95-weekly-2026-10-19.md)

### 1b. Built lanes not merged yet (merge so they ride a weekly)

24. [Claude] [scan: YES] **Oregon City 16.12.035.F -- one driveway approach per two townhouses** -- RULED 2026-09-30; lane branch deleted 2026-10-24 on Steph's go. [file](followups/24-oc-two-approaches.md)

### 1c. The rest, most urgent first (dated items first)

100. [Claude] [scan: YES (yellows only go green)] **Driveway street: measure it instead of asking** -- merged e63617b8 2026-10-20; moves expected at the next weekly. [file](followups/100-driveway-street.md)
94. [Claude] [scan: YES -- false reds only] **Townhouse row held to the street's angle** -- ~105 false reds; BUILT by Copilot (merged with main b8ba280b), first bound timed out 11-03; th_row3 used the wrong base and moved 0; Copilot r2 1dc9159f (1 deg tolerance, pushed); re-bound th_row4 QUEUED (chain6); read every gain next. [file](followups/94-townhouse-row-angle.md)
86. [Claude] [Steph: (B) unattributed rulings] [scan: YES for (C1)] **Agents could not recall a property ruling** -- A, B, C1, C2 MERGED; DLCD backlog READ; (B) waits on Steph. [file](followups/86-ruling-recall.md)
2. [Claude] [scan: YES] **Neighbour zoning per lot line -- loose ends after the measurement** -- run 12 PROMOTED 2026-09-22; loose ends still owed. [file](followups/2-neighbour-zoning.md)
13. [Claude] [scan: NO -- lands with the November county refresh] **Tax code area in the RLIS ingest** -- lands with the November county data refresh. [file](followups/13-taxcode-rlis.md)
53. [Claude] [Steph: (b) Molalla PDFs; (c)-(d) HUMAN_TODO 30; (f)] [scan: see file] **Canby, Sandy, Estacada, Molalla** -- Estacada + Canby/Sandy DONE in run 73; Sandy reversed by r3; Steph parts open. [file](followups/53-canby-sandy-estacada-molalla.md)
87. [Claude] [Steph: OK to fetch public lists] [scan: YES -- greens only lose] **Protected historic buildings outside Portland** -- BUILT 11-06 flats/historic-outside-portland, rides the re-screen; 5 lists wired; 11 cities still have no list; needs Steph's OK to fetch the statewide list. [file](followups/87-historic-outside-portland.md)
68. [Claude] [scan: YES] **Portland Maps 120-2 and 120-3 are not held** -- found 2026-10-10; re-bound READ 11-04: no false green, 60+ false reds + 17 needless holds; round 3 (fixes + half-area parking ruling) BUILT by Copilot b0cdece7 (pushed) -> re-bound after th_row3, read; 90 ft RULED one street 11-04. 11-05 pdx_map_120c HOLD: ~252 wrong REDs (overlap charged twice), FIXED a34c7b01 (pushed) -> re-bound pdx_map_120d queued (chain8); 3 other branch reds open (1S2E20DB-04000 = 142a; 1S2E10DA-03400, 1S2E11CB-06900 lose corner status); shared-outdoor-space option -> 31 (Steph). [file](followups/68-portland-maps-120.md)
90. [Claude] [scan: NO] **Cites that name a section the cited lines do not sit in** -- CHECKER FIXED 726bb7e1, LIVE 2026-10-22: 367 -> 84 disagreements. [file](followups/90-cite-section-mismatch.md)
83. [Claude] [scan: YES (yellows only go green)] **Measure Washington County's "standard plat" gate instead of flagging it** -- offered 2026-10-14; 731 lots yellow on it. [file](followups/83-standard-plat-gate.md)
66. [Claude] [Steph: (a), (d)] [scan: NO for (A); YES for (B)] **A price check beside the fit** -- (A) LIVE 2026-10-10 (d1d8c03f); (B) and Steph parts open. [file](followups/66-price-check.md)
71. [Claude] [scan: NO unless it finds a siting rule] **Building-code editions** -- editions CHECKED 2026-10-16 (1686bbd3, notes only). [file](followups/71-building-code-editions.md)
17. [Claude] [Steph: (c) HUMAN_TODO 28; 25C] [scan: YES] **Washington County: drafts reviewed; publish, then the county map** -- Steph answered HUMAN_TODO 25 on 2026-09-29; (c) open. [file](followups/17-washington-county-drafts.md)
52. [Claude] [scan: NO for the leftovers] **Lots dropped before a fit (run 65)** -- SHIPPED 2cfd13d6, LIVE runs 69/70; leftovers listed in file. [file](followups/52-lots-dropped-before-fit.md)
46. [Claude] [Steph: (d), (f)] [scan: YES (proof run)] **Scans (bounds) on 137 are the lanes' bottleneck** -- (a)-(c) SHIPPED 24a61695 2026-10-08; (d), (f) wait on Steph. [file](followups/46-scan-bottleneck.md)
41. [Claude] [scan: YES] **Street class per lot line** -- (a)(b) SHIPPED 2026-10-05, (i)-(iii) SHIPPED 2026-10-06, deployed. [file](followups/41-street-class.md)
6. [Claude] [scan: YES] **Where parking may SIT, and which street is "the front"** -- offered 2026-09-19; Steph ruled the same day (orientation choice order). [file](followups/6-parking-sit-front.md)
4. [Claude] [scan: YES] **Four places the screen and the county map disagree** -- left alone on purpose; some parts done and dropped. [file](followups/4-screen-vs-county-map.md)
3. [Claude] [scan: YES court placement; NO lot-page note] **Alley leftovers** -- alley fixes live (runs 24-42); leftovers open. [file](followups/3-alley-leftovers.md)
7. [Claude] [Steph: HUMAN_TODO 27] [scan: YES] **Green and outdoor space: charge the SHAPE, not just the amount** -- (a)(b) done and live (run 42); remaining parts in file. [file](followups/7-green-space-shape.md)
10. [Claude] [scan: YES for (a), one lot; NO for (b)] **Two loose ends from the ruling pass** -- (a) DONE 4b725b6a; (b) open. [file](followups/10-ruling-pass-loose-ends.md)
5. [Claude] [scan: YES, small sample] **Draw what the screen fitted** -- DONE 666c6837 (run 31 PROMOTED); drawing-angle leftovers. [file](followups/5-draw-the-fit.md)
37. [Claude] [scan: YES for (iii); NO for (f)] **Flag system plan** -- slices 1-(e) BUILT and LIVE; (iii), (e), (f) open. [file](followups/37-flag-system.md)
58. [Claude] [scan: YES] **Yellows held by one measurable question** -- first pass DONE c98be01d 2026-10-09; LIVE in run 69. [file](followups/58-yellows-one-question.md)
27. [Claude] [Steph: (a)] [scan: YES for (a); NO for (b)] **Steph's Oregon City page check: what is left** -- answers triaged, card and reader fixes shipped; (a) waits on Steph. [file](followups/27-oc-page-check.md)
27b. Moved to 92 (Parking layout generator, the second item numbered 27).
25. [Claude] [scan: YES when built (on hold)] **Driveway approach geometry, ahead of a second approach** -- flag only -- ON HOLD, do not build yet. [file](followups/25-driveway-approach-geometry.md)
20. [Claude] [Steph: before a worktree] [scan: NO] **Design-standards catalog** -- catalog of rules about how the building looks; Steph before a worktree. [file](followups/20-design-standards-catalog.md)
31. [Claude] [scan: YES (not started)] **Split a big lot to meet a minimum density** -- not started; "maybe never done". [file](followups/31-split-big-lot.md)
1. [Claude] [Steph: HUMAN_TODO 23] [scan: NO] **The county map copy: loose ends after the first promotion** -- September copy PROMOTED 2026-09-20; loose ends in file. [file](followups/1-county-map-copy.md)
96. [Claude] [Steph: mark the 13 handed on] [scan: LIVE run 80] **Hand-off: 13 open Gresham questions from 2026-08-17** -- ANSWERED 2026-10-21; Steph to mark the 13 handed on. [file](followups/96-gresham-13-questions.md)
143. [Claude] [Steph: design before build] [FLATS 2.0 -- after 1.0, not midstream] **Every word in the code bound to the definition that governs it** -- major feature, Steph 2026-11-03; proving case: Large City (80(d), run 113). [file](followups/143-word-definitions-flats-2.md)
144. [Claude] [Steph: whether to use it] [scan: YES if built] **Overhead power lines near the building** -- Steph asked 2026-11-03; PGE + Pacific Power both publish lines (Pacific Power also every pole); clearance rule + accuracy check open. [file](followups/144-overhead-power-lines.md)
99. [Claude] [scan: NO until a 2-unit design exists] **State middle-housing parking is held as a per-unit ratio** -- matters only once a 2-unit design exists. [file](followups/99-middle-housing-parking.md)

### 1d. Finance (underwriting) -- [Claude]; kept word for word (15 waits on Steph's answers)

14. [scan: NO] **Tax impact beyond Gresham** -- needs another city's code-area rates and CPR row. [file](followups/14-tax-impact-beyond-gresham.md)
15. [scan: NO] **Edgemont (P7) bond-model update** -- waiting on Steph's answers. [file](followups/15-edgemont-bond-model.md)
18. [scan: NO] **`GET /api/projects` is not scoped to the caller's organisation** -- scope to the user's org + two-org integration test. [file](followups/18-projects-org-scope.md)
19. [scan: NO] **Excel export vs the engine -- four disagreements** -- none fixed (PR #21/#22); each needs a ruling. [file](followups/19-excel-vs-engine.md)
102. [Claude] [Steph: Durham 273/282] [scan: LIVE run 80] **Gresham front lot line on corner and through lots** -- LIVE run 80 2026-10-21 (main 67611b26); Durham 273/282 wait on Steph. [file](followups/102-gresham-corner-through.md)
103. [Claude] [scan: YES for (d) only] **Page check: notes the cards still cannot ask** -- (a)(b) DONE (0387fc8a, a40e4be8); rest in file. [file](followups/103-page-check-notes.md)
104. [Claude] [left: (f), (g)] [scan: (a) LIVE run 80] **Gresham Table 4.0430 notes, read note by note** -- LIVE run 81 (main 0060aad3); left (f), (g). [file](followups/104-gresham-table-4-0430.md)
113. [Claude] [Steph: design before build] [scan: NO] **Two-source check: a second review queue** -- HOLD -- Steph 2026-10-29; after 73; major feature, check in. [file](followups/113-two-source-check.md)
112. [Claude] **Page check: show the passage that sends a number to another table** -- 81457395 added `via`; 958 cards say the zone is not on the cited page. [file](followups/112-page-check-via.md)
108. [Claude] [Steph: Estacada per-home figure] [scan: YES (toward green)] **Every taxlot is a legal lot of record** -- BUILT 11-06 flats/legal-lots 0a7d9e60, 84 zones; rides the re-screen, read every gain; Estacada held yellow pending Steph. [file](followups/108-legal-lots.md)
109. [Claude] **Design districts** -- chunk 5 LIVE run 91; chunk 6 LIVE run 94 2026-10-30; North Bethany LIVE run 97; Bethany ASC LIVE run 99; chunk 7 (Raleigh Hills-Garden Home, Bull Mountain) LIVE run 101 2026-10-31 (16 green->yellow); chunk 6b re-read (connectivity, plan rules, Bethany ASC 3, Raleigh Hills ASC U; was 134/135/136) LIVE run 103 2026-10-31 (280 green->yellow); chunk 8 (Metzger-Progress, West Tigard, East Hillsboro, Sherwood; West Union has no pod lots) + 137 flags LIVE run 105 2026-10-31 -- ALL ELEVEN WashCo community plans read; chunk 9 (Sandy, Wilsonville OTR) + Portland plan districts part 1 (Johnson Creek, Laurelhurst-Eastmoreland) LIVE run 111 2026-11-01 (441 green leave). Portland 33.5xx part 2 batch A 105c1d37 + batch B 5e2a8551 batches A+B LIVE run 115 2026-11-04 (1,466 moves, fingerprint exact; main 6f2d8c35); batch C BUILT 9e8f708a (flats/districts-pdx-pd2c, pushed; Gateway/East Corridor min floor area off the map sheets, ~173 yellow->green expected; Map 530-1 shows only the outline, Glendoveer unchanged) -> bound pd2c HELD 11-05 (Gateway through lots let out), FIXED 4ed4f5b8 (pushed) -> re-bound pd2d READ 11-05: 172 yellow->green all right; stacked on live as rel2 (bundle /root/bundle_rel2, EQUAL 6498aeae) -> RELEASING via flats/release-1106 ebe61e9d; min floor area RULED 11-04 -> item 148 -- LAST overlay work. [file](followups/109-design-districts.md)
140. [Claude] **Trees ignored, entered per lot** -- Steph 2026-11-01: canopy build cancelled; per-lot tree mark LIVE 2026-11-01 (3c7accea); left: drop the Johnson Creek tree hold, NEXT WEEK. [file](followups/140-johnson-creek-trees.md)
105. [Claude] [scan: YES (new standards bind)] **Follow every cross-reference one layer down** -- after 73's restructure; Portland batch 6 adds new references. [file](followups/105-follow-cross-references.md)
116. [Claude] **Mend the misread words the squiggles show, worst city first** -- Canby + first King City batch 3046b980; this branch mended 68 more King City joins (89 -> 12); 12 leftovers and Tualatin remain; Claude to close. [file](followups/116-misread-words.md)
118. [Claude] **Durham 3.7.1.7: no driveway apron within 100 ft of an intersection -- FALSE GREEN RISK** -- measurement BUILT 23e839d2 (flats/durham-apron-100ft); bound READ 11-04: 10 gains right, 1 wrong RED (2S124AB01200, phantom junction on a jog) + missed-junction weakness; round 2 91c8ebc1 bound READ 11-05: 13/14 right (10 greens right), 2S124AB01200 still false RED (backtracking jog sets the extension) -> round 3 ba736e61 (pushed); re-bound durham_apron3 READ 11-05: 13/13 right -> LIVE run 118 2026-11-06 (with 148); fix-forward: junction search skips same-name cross street (no colour effect). [file](followups/118-durham-apron-100ft.md)
119. [Claude] [scan: NO for (b); YES for (c)] **Portland page-check notes, reviewed 2026-10-28** -- HOLD (Steph 2026-10-29); (a) DONE a54faf2a; (b), (c) left. [file](followups/119-portland-page-check.md)
142. [Claude] [scan: YES -- false reds only] **Placement ignores fire reach; stall width; parking down a long lot** -- (a) BUILT bf18785e, bound /root/fire_rp3 READ 11-04: 4 wrong greens (max front setback ignored) + 2 unconfirmed -> round 2 a531417f bound fire_rp4 FAILED 11-05 (retry draws every placement: workers killed for memory on big lots) -> r3 BUILT 58f177ab (pushed; retry ranks without drawing, max 24, none over 3 acres) -> re-bound fire_rp5 (6a5f8b6d) queued in chain8 before the study; (b) RULED city's own stall width, BUILT by Copilot 7c342592 (pushed; widths checked, Tigard TMU 7.5 is printed) -> bound after th_row3, read gains; (c) RULED later with 92. [file](followups/142-placement-and-stall-width.md)
145. [Claude] [Steph: parameters + design review] [scan: YES when built] **Set access: truck route, crane setup and lifts solved per lot** -- moderate feature, Steph 2026-11-03; generative like the court search; parameters not yet given. [file](followups/145-set-access-crane-truck.md)
120. [Claude] [scan: YES -- false red only] **Happy Valley 16.44 driveway cap measured on a short line** -- BUILT by Copilot 56891775 (flats/happy-valley-driveway-cap), also reaches Beaverton + Sherwood; bound READ 11-04: target untouched (private-drive frontage) + tiny lenient drift; round 2 BUILT by Copilot e6efdcb1 (pushed) -> re-bound after th_row3, read. 11-05 hv_cap2 HOLD: private-drive fix never ran on real data, FIXED 86254150 (pushed; 22E01DD03100 red->yellow, hand-measured ~50 ft tract frontage NOT adopted) -> re-bound hv_cap3 READ 11-06 (Claude): 4 moves -- 22E01DD03100 + Beaverton CS 1S115AD01100 red->yellow right (driveway share cleared); 2 Beaverton green->yellow are base drift (SLOPE-GRADE), not this branch -> SHIP, stack on live after rel2. [file](followups/120-happy-valley-driveway-cap.md)
146. [Claude] [scan: YES -- toward green] **Let the drive lane (and court) use the side setback where the code allows it** -- STARTED 11-05 for the Monday sizing study (149): mechanism e92ca641; city values read (side-yard-parking.readings.md); all cities encoded 605de374 except 6 chapters being fetched; checked BY THE ~11-10 RE-SCREEN (Steph), no separate bound; today the lane never sits in a side yard; Portland allows it (33.266.120). ROUND 4 11-06 add83c5f + 7d07ec92 (West Linn, Clackamas, WashCo, King City; suite 6552 passed); not merged, rides the re-screen. [file](followups/146-parking-in-side-yards.md)

## 2. Waiting on Steph

149. [Claude] [Steph] **Pod unit width** -- 14 ft homes (pod56x36) too narrow for 2 bedrooms side by side; COUNTED: 20,032 of 44,641 greens need it; Steph: one-time sizing study 14-20 ft by 1 ft at 500 sq ft/floor ~Mon 11-09; prep built 958ebe29 (flats/sizing-study, pushed: 5 study pods, scope + report scripts; curve dropped, no stored frontier); trial DONE 11-05 (works; ~0.5 s/lot); Steph: run every lot with a chance -> FULL RUN 267,544 lots x 7 sizes queued on 137 (chain8, after held re-bounds), results ~Sun 11-08; report r3 BUILT 7927e176 (pushed) [file](followups/149-pod-unit-width.md)
128. [Claude] [Steph] [scan: NO] **CI takes an hour or more per push** -- BUILT 2026-10-30: pushes tested on LXC 138 ci-runner (~16 min), GitHub daily; open: quadfit 7 min, watch daily runs. [file](followups/128-ci-speed.md)
127. [Claude] [Steph] [scan: NO] **Cut token spend** -- (a)(b)(e)(f) done (7 profiles d387fd7c, 2849fa9a; first real use next session); open: Copilot 11-01, reading pilot, local pre-sort. [file](followups/127-token-spend.md)
126. [Claude] [Steph] [scan: NO -- display only] **A fast map of every lot, and a live 3D lot view** -- IDEA 2026-10-29; major feature, check in before any design. [file](followups/126-lot-map-3d.md)
125. [Claude] [Steph] [scan: NO -- a label] **What stands on the lot now: vacant / small house / bigger building** -- OFFERED 2026-10-29; waits on Steph's go. [file](followups/125-lot-occupancy.md)
115. [Claude] **Tables, superscripts and footnotes in the readable text (readable/3), Tualatin pilot** -- GO 2026-10-24; tables BUILT + LIVE (8bc86bdc). [file](followups/115-readable-tables-footnotes.md)
114. [Claude] **Batch-fix the logged text corrections** -- no checker; "Suggest a correction" box BUILT 145c1f46; batch when notes accumulate. [file](followups/114-text-corrections.md)
73. [Claude] [Steph] [scan: NO] **The code library as a public, structured repository** -- STRUCTURING ROLLOUT DONE 2026-10-31 (batch 8 WashCo 07fa1e17, tables 67b9aaa4); hard leftovers kept as known gaps (see file). Hosting PARKED (Steph 2026-11-01: "Not ready to publicize"). [file](followups/73-code-library.md)
54. [Steph] [scan: NO] **Code-change reader on the Claude API credit ($100/month)** -- Steph picked it 2026-10-07 and declined the other two offered. [file](followups/54-code-change-reader.md)
55. [Steph] [scan: NO] **Expansion scouting on the credit item 54 leaves** -- background scouting; waits until we choose a place to encode. [file](followups/55-expansion-scouting.md)
22. [Steph] [scan: YES if Milwaukie 22 ft aisle adopted] **Portland aisle 20 ft** -- DONE bacea669, run 44 PROMOTED 2026-09-30; Milwaukie 22 ft question. [file](followups/22-portland-aisle.md)
32. [Steph] [(B) Copilot-able after a yes] [scan: NO] **Windows CPU spikes** -- measured: bursts come from test runs and hooks; waits on Steph. [file](followups/32-windows-cpu.md)
65. [Steph] [scan: YES (proof run)] **The Windows PC as an idle-time scan helper** -- offered 2026-10-09, not started. [file](followups/65-windows-scan-helper.md)
62. [Steph] [scan: YES] **Roof shape: teach the screen gable vs flat** -- offered 2026-10-09; nothing signed. [file](followups/62-roof-shape.md)
40. [Steph] [scan: YES if started] **Easements from maps** -- odds answered 2026-10-04; not started. [file](followups/40-easements-from-maps.md)
72. [Steph] [scan: NO] **Oregon Explorer statewide map** -- PARKED. [file](followups/72-oregon-explorer.md)
92. [Steph] [scan: YES (parked)] **Parking layout generator (was the second item 27)** -- PARKED by Steph 2026-10-04; scoping only, nothing built. [file](followups/92-parking-layout-generator.md)

## 3. Copilot queue -- low priority, not time-sensitive

23. [Copilot] [scan: NO] **Page check** -- SHIPPED 2026-09-30 (a203e9f1). [file](followups/23-page-check.md)
16. [Copilot] [PARKED] [scan: NO] **Partial re-screen** -- SHIPPED 50a0ecc2 2026-09-25; PARKED -- ask before firing. [file](followups/16-partial-rescreen.md)
