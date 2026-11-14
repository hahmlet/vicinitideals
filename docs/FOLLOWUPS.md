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
1. [Claude] [Steph: HUMAN_TODO 23] [scan: NO] **The county map copy: loose ends after the first promotion** -- September copy PROMOTED 2026-09-20; loose ends in file. [file](followups/1-county-map-copy.md)
   traps and its moves to read, (1b) built lanes waiting to merge, (1c) the
   rest, (1d) the finance items (kept word for word).
2. [Claude] [scan: YES] **Neighbour zoning per lot line -- loose ends after the measurement** -- (a) Oregon City R-2 note 1 + Beaverton lists LIVE (run 124); (c) ~5,100 lots (11-09 count) still lean on an unknown neighbour fact -- re-count; (d) guard done, CI2 on hold; (e) parked. [file](followups/2-neighbour-zoning.md)
   says go; Claude does the work after.
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

152. [Claude] [Steph] **ci-runner: optional OOM protection for its Postgres** -- run cap + Postgres check shipped (70c1cb75); only the optional OOMScoreAdjust=-900 unit setting on 138 is left, Steph's call (only if Postgres is OOM-killed again). [file](followups/152-ci-runner-overload.md)
147. [Claude] **Maximum front setback never checked on its own** -- DONE and live; last open lot 1S2E17BA -14300 re-checked 11-13: true RED (corner, 18 ft off SE 71st; small-fixes-9 hand-off). Remove at rel9 merge. [file](followups/147-max-front-setback-unchecked.md)

148. [Claude] [scan: YES -- toward yellow] **Minimum floor area: red only when more pods clearly cannot fit** -- LIVE since run 118; fix-forward BUILT flats/small-fixes-9 6ed32c51 (4 Portland part-overlay lots R->Y), rides rel9. [file](followups/148-min-floor-area-more-pods.md)

182. [Claude] [scan: YES -- false greens only] **No-sewer rule: city pipe in the street outside every district** -- RULED 11-11 YELLOW; BUILT 4592039a, rides rel8 (bound running 11-13; ~398 G->R, ~148 G->Y). [file](followups/182-no-sewer-street-pipe.md)
181. [Claude] [scan: YES -- false greens only] **Roof sweep: Clackamas pitched roof + four re-reads** -- (a) BUILT 4245abd9, (b) BUILT 0151a6c5, both ride rel8 (bound running 11-13). Steph 11-14: no city contact (ruling 2026-11-14-no-city-contact) -- text governs, Tualatin flat roof RED, Villebois YELLOW; nothing left open. [file](followups/181-roof-sweep-clackamas.md)

186. [Claude] [scan: YES -- toward red, FALSE GREEN] **Gresham end walls need 5% glass but 40 greens sit < 3 ft from a lot line** -- RULED 11-12 each wall; BUILT 1b0d6299 (+187 places), rides rel8 (bound running 11-13; est. 5-20 of 40 go RED). [file](followups/186-gresham-end-wall-glass.md)

187. [Claude] [scan: YES -- end-wall glass places] **Glazing rules: read, report published** -- report https://claude.ai/artifact/PvTVXncwqnjMT4br3Krhdj; Portland CM fourplex exemption RULED 11-12; end-wall hold (1b0d6299) and Tigard TMU (c6f46146) ride rel8 (bound running 11-13). [file](followups/187-glazing-gaps.md)

185. [Claude] [scan: YES -- every lot] **Screen the 80 x 25 pod, 20 ft tall, 9'2" storeys** -- RULED 11-12 (three rulings); BUILT c6f46146, rides rel8 (full bound running 11-13). Open later: trace Kenton 33.538.230 Map 538-4 (held YELLOW whole now). [file](followups/185-pod-depth-30.md)

188. [Claude] [scan: YES -- toward yellow] **Lots cut by a district boundary pass untested** (S/E Hillsboro, Portland map areas) -- found 11-12; count + sample, then split-zone-yellow rule. [file](followups/188-cut-district-untested.md)
189. [Claude] [scan: YES -- toward green only] **rel7 move-read fix-forwards: pdx-9ft cases not moved, Thorville bulb unmeasured, Clackamas R10 51.2% share red** -- none a false GREEN. F5/F6 (ingest cert, recipe root) done 766dd02d. [file](followups/189-rel7-fix-forwards.md)
191. [Claude] [scan: YES -- toward green only] **Middle townhouse lots asked for the corner lot's 25 ft frontage (false RED); drop 3 untied Hillsboro UC entries** -- BUILT flats/corner-th-191 3652cfa6 (rides rel10 with pagecheck-34); ~40 Gresham RED->YELLOW, 0 GREEN; Hillsboro UC entries deleted. [file](followups/191-corner-townhouse-false-red.md)
192. [Claude] [Steph: Q1 Q2 Q7 Q9-Q11 Q19 info asked] [scan: YES -- mostly moot today] **Steph's 11-14 answers: encode Fairview all corners, OC/Hillsboro engineer sight GREEN+flag, Gresham MDR-24 alley 16 ft, King City per-side buffer** -- rulings recorded; lane not built (rel10). [file](followups/192-rulings-1114-lane.md)

### 1a. The weekly re-screen: traps to honour before it, moves to read after it

- Weekly re-screen state -- run 124 PROMOTED 2026-11-12 (rel7, pod80x30); NEXT rel8 full bound (pod80x25@3). [file](followups/weekly-rescreen.md)
77. [Claude] **Road land to the centre line in the cities** -- all built and live (7cbc3346, d3b6db52, 19ee2d97, e67b7193); only the no-centre-line case (34 lots) left conservative, needs a new centreline source. [file](followups/77-city-road-dedication.md)
78. [Claude] [Steph: confirm 2029 transit-street RED vs YELLOW] **Portland false GREENs: main street minimum floor area and protected historic buildings are RED** -- all built and live (4ed70036, 8d1597ef, bc380601); only Steph's confirm that a 2029 mapped-transit-street lot is RED (built under no-variances) left. [file](followups/78-portland-false-greens.md)
80. [Claude] [Steph: (c) human copy of Wood Village 235.400/490] **Readings for Steph from item 64 round 2** -- (a)(b)(d) ruled/built and live; 1S113BA07700 ruled 11-03 (show green), build not recorded; (c) waits on a copy; (e) flag_instances staleness unchecked. [file](followups/80-item64-round2-readings.md)
76. [Claude] [Steph: (c) assessor lookup] **Tigard pod80x25 red at exactly -43 ft, and split-zoned lots** -- (a)(b) merged and read at run 78; only (c) open: human lookup of Estacada tax lot 34E20AC00201 owner. [file](followups/76-tigard-minus-43.md)
42. [Claude] **Water, wetland and flood ground at slope's fidelity** -- DONE and live; three accepted known gaps left (washington_habitat flag, Portland transition-area under-carve, unread Clackamas WQRA/HV/Tualatin). [file](followups/42-wetland-flood-fidelity.md)
29. [Claude] [Steph: (C) county widths, deferred] **Fire reach: measure where the truck really stands** -- (A) d8880db1 and (B) 57313463 live; (C) asking WashCo/Clackamas/West Linn for pavement widths deferred by Steph. [file](followups/29-fire-reach-truck.md)
30. [Claude] **Net land area review** -- SHIPPED and live (d8d4a439, 995f0007, 183 values); remaining floodplain/resource-overlay areas stay unmeasured (`may_less`). [file](followups/30-net-land-area.md)
36. [Claude] [Steph: the OAR strip question] [scan: YES] **Parking tool queue** -- mostly LIVE (f7ba7038, 1723db45, 1d3c89cb); OAR 660-046-0220 strip question still open for Steph; some cities' strips and chapters still unencoded. [file](followups/36-parking-tool-queue.md)
44. [Claude] [scan: NO new code, check after the weekly run] **Readings ranked on the map's colour, and 43's hose edge** -- SHIPPED 51577bb8 (on main, live); the spot-check of the 34 lots is not recorded (status unverified 11-13). [file](followups/44-reading-rank.md)
8. [Claude] [scan: YES if (b) is taken up] **Pockets + corridors -- leftovers** -- all code live, both checks DONE 2026-11-09; only (b) open: 66 ZONE_POCKET lots (Troutdale NSA, Oregon City County, Beaverton WAcnty). [file](followups/8-pockets-corridors.md)
21. [Claude] [Steph: worktree go; HUMAN_TODO 26] [scan: YES for (a)-(c); NO for (d)-(e)] **Post-2027 world** -- (b) built and live (runs 46, 49); (a) state layer to adopted Div 46 and (c) Oregon Homes path wait on Steph's worktree go. [file](followups/21-post-2027-world.md)
64. [Claude] [scan: NO] **Measure the false-GREEN rate** -- rounds 1-3 done (pooled ~4%, stopping signal not met); round 4 next on a post-rel6 live run. [file](followups/64-false-green-rate.md)

### 1b. Built lanes not merged yet (merge so they ride a weekly)

(none -- rel8 is packed and bounding; lanes built for rel9 carry BUILT in their line below)

### 1c. The rest, most urgent first (dated items first)

100. [Claude] [scan: YES (yellows only go green)] **Driveway street: measure it instead of asking** -- MERGED e63617b8, LIVE (run 124). Open: (a) measure the street line the drawn drive crosses; (b) a Happy Valley street-class map -- until then MEASURE-DRIVE-STREET / ACCESS-STREET-RANK-UNKNOWN yellows stay. [file](followups/100-driveway-street.md)
86. [Claude] [Steph: (B) unattributed rulings] [scan: NO] **Agents could not recall a property ruling** -- A, B, C1, C2 merged and live (CI1 live in run 124); (B) leftovers (Tigard MUR, Portland total-turn, Hillsboro SCR, Milwaukie aisle) wait on Steph; RICAP MP5/MP4/TA9 not encoded; DLCD watch weekly. [file](followups/86-ruling-recall.md)
2. [Claude] [scan: YES] **Neighbour zoning per lot line -- loose ends after the measurement** -- (a) Oregon City R-2 note 1 + Beaverton lists LIVE (run 124); (c) ~5,100 lots (11-09 count) still lean on an unknown neighbour fact -- re-count; (d) guard done, CI2 on hold; (e) parked. [file](followups/2-neighbour-zoning.md)
13. [Claude] [scan: NO -- lands with the November county refresh] **Tax code area in the RLIS ingest** -- TAXCODE still not declared on main; lands as first step of the RLIS 2026_11 refresh (released 2026-11-05; plan ~11-19, after rel6 which has shipped) (status unverified 11-13). [file](followups/13-taxcode-rlis.md)
53. [Claude] [Steph: (b) Molalla PDFs; (c)-(d) HUMAN_TODO 30; (f) Downtown yes/no] [scan: see file] **Canby, Sandy, Estacada, Molalla** -- Estacada, Canby, Sandy LIVE (item 85 merged c20ea3a1). Waits on Steph: Molalla PDFs (HUMAN_TODO 29), Estacada q1-5 (HUMAN_TODO 30), Downtown zone. Owed, Claude: re-read Canby/Sandy doubts now 85 landed. [file](followups/53-canby-sandy-estacada-molalla.md)
87. [Claude] [Oak Hills RULED RED 11-07] [scan: YES -- greens only lose] **Protected historic buildings outside Portland** -- BUILT and LIVE (run 124): SHPO/NPS lists + city lists, Oak Hills RED. Open: a few listings unplaced (Giese House, Ely Building, Doriet/Rider Log House, Joy Theater; SHPO 84 unmatched); Lake Oswego 50.06.009 not stored (city off). [file](followups/87-historic-outside-portland.md)
68. [Claude] [scan: YES] **Portland Maps 120-2 and 120-3 are not held** -- BUILT and LIVE (a34c7b01 via rel6, run 124); Steph's questions ruled. Open: three possibly wrong reds (1S2E20DB-04000, 1S2E10DA-03400, 1S2E11CB-06900; corner exemption lost on an alternate reading, fire-reach placement); status unverified 11-13. [file](followups/68-portland-maps-120.md)
90. [Claude] [scan: NO (citations move, answers must not)] **Cites that name a section the cited lines do not sit in** -- checker fixed 726bb7e1, live (367 -> 84 disagreements); NOT TO BUILD further: item 73's section tree replaces it; the leftover list is 73's conversion checklist. [file](followups/90-cite-section-mismatch.md)
66. [Claude] [Steph: (a), (d)] [scan: NO] **A price check beside the fit** -- (A) and (b) LIVE (d1d8c03f, 77d466a0). Waits on Steph: (a) filter default ON?, (d) a "value looks too low" mark. Claude owes the production backfill re-run after migration 0145 (not recorded as done). [file](followups/66-price-check.md)
71. [Claude] [scan: NO unless it finds a siting rule] **Building-code editions** -- checked 2026-10-16/11-03 (1686bbd3): no change to what the screen checks. Open: (a) re-cite fire_access_max_ft from 2022 to 2025 OFC 503.1.1 once its text is read; (b) read Oregon's R302.2 townhouse text when the book is out. [file](followups/71-building-code-editions.md)
17. [Claude] [Steph: (c) HUMAN_TODO 28; HUMAN_TODO 25C] [scan: YES] **Washington County: drafts reviewed; publish, then the county map** -- (a)(b)(b2)(d)(e)(f) DONE and live. Open: (c) Forest Grove waits on Steph's six PDFs; 25C city questions; Tualatin Ch.58 path, Hillsboro flag_lot, Tigard sub-area maps, Jan 2027 drift check (leftovers not re-verified 11-13). [file](followups/17-washington-county-drafts.md)
52. [Claude] [scan: NO for the parked rest] **Lots dropped before a fit** -- SHIPPED and live (2cfd13d6; SCMU 2f8f4836, Fairview TCC 2fe9d37d). Parked with triggers (0 greens each): Milwaukie DMU/GMU, Tualatin leftovers; SCMU min building depth/ground-floor height unread. [file](followups/52-lots-dropped-before-fit.md)
46. [Claude] [Steph: (d) after the measuring, (f) after the re-measure] [scan: YES (a proof run: every answer must come out identical)] **Scans (bounds) on 137 are the lanes' bottleneck** -- (a)-(c) SHIPPED 24a61695; rented compute UNPARKED 11-08, research DONE (compute-research.md); Steph to pick service, budget, box count; (f) skip big private lots to re-measure. [file](followups/46-scan-bottleneck.md)
41. [Claude] [scan: NO for the parked rest] **Street class per lot line** -- (a)(b)(i)-(iii) SHIPPED 2026-10-05/06 (6b924963, 972caa17) and live. Parked: Tualatin through lots (351, ~30 green if signed; needs a class map), Wilsonville note P. Every full re-screen needs all 7 street_class_* keys. [file](followups/41-street-class.md)
6. [Claude] [Steph: (f)] [scan: YES] **Where parking may SIT, and which street is "the front"** -- ruled 2026-09-19; built and live (run 124); (f) side vs rear court waits on Steph; (g)-(n) are quadfit drawing leftovers. [file](followups/6-parking-sit-front.md)
4. [Claude] [scan: YES] **Four places the screen and the county map disagree** -- most done/struck; open: (a) court shape L/T search + row-count gap vs quadfit, (e)(ii)/(iii) corner alley. [file](followups/4-screen-vs-county-map.md)
7. [Claude] [Steph: HUMAN_TODO 27] [scan: YES] **Green and outdoor space: charge the SHAPE, not just the amount** -- (a)(b) and Fairview fix live; open: Steph's call on Portland near misses (HUMAN_TODO 27), side-strip court unmeasured (3 lots). [file](followups/7-green-space-shape.md)
37. [Claude] [scan: NO] **Flag system plan** -- slices 1-(e) and (iii) built and live (run 124); open: (e) 29 unmeasured notes need data nobody holds; plan gaps (flag history, bulk writes) to scope with Steph first. [file](followups/37-flag-system.md)
58. [Claude] [scan: YES] **Yellows held by one measurable question** -- passes 1 and 3 live (runs 69, 124); open: 12 Springwater-abutting lots need a per-line setback build; four unmeasurable holds need a new source. [file](followups/58-yellows-one-question.md)
27. [Claude] [Steph: (a)] [scan: YES for (a); NO for (b)] **Steph's Oregon City page check** -- card/reader fixes shipped; (a) waits on Steph (was the OC front-parking "differs" the 17.16.060.E escape?); (b) other cities' prose refusals into `set_aside:` still open (only oregon-city.yaml has it). [file](followups/27-oc-page-check.md)
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
103. [Claude] [scan: YES for (d) only] **Page check: notes the cards still cannot ask** -- (a)(b)(c)(e)(f) DONE and live (0387fc8a, a40e4be8, cb070ec2, 3783bfb5, 67a8d0b5); open: lot-by-lot read of the dc79bd29 Gresham corner-frontage gains (no record it was done). [file](followups/103-page-check-notes.md)
104. [Claude] [LIVE run 81; Gresham green 1,834 -> 2,039] **Gresham Table 4.0430 notes, read note by note** -- everything built is live; (g) folded into 142(a); open: confirm 1S3E14AA  -08900 (still RED run 124, fire access + min density) is right, then close. [file](followups/104-gresham-table-4-0430.md)
113. [Claude] [Steph: design before build] [scan: NO] **Two-source check: a second review queue** -- HOLD -- Steph 2026-10-29; after 73; major feature, check in. [file](followups/113-two-source-check.md)
112. [Claude] [Opus reading; Steph sees the result on the page check] **Page check: show the passage that sends a number to another table** -- (a) sweep e4e2f941 + (b) 34c44acd DONE and live; open: 34 numbers with no stored tie, 29 Gresham flags to triage, Gresham 4.1152 S9-S13 possible false GREEN. [file](followups/112-page-check-via.md)
108. [Claude] [scan: YES (reds/yellows only go toward green)] **Every taxlot is a legal lot of record** -- BUILT 0a7d9e60 + ef98ae43, LIVE since run 122 (84 zones); Estacada stays yellow (ruled 11-06); open: read of the gained greens not recorded (status unverified 11-13). [file](followups/108-legal-lots.md)
109. [Claude] **Design districts** -- all chunks and Portland plan districts parts 1-2 LIVE (last: batch C in rel2; min floor area is item 148); left: Gladstone Portland Ave C-2 strip waits on a better map (20 lots yellow). [file](followups/109-design-districts.md)
105. [Claude] [scan: YES (new standards bind)] **Follow every cross-reference one layer down** -- rounds 1-4 DONE and live (9a229b24, b78a4495, 3f1e7f0e); open: Beaverton Type A frontage map trace (download OK), West Linn Ch 28 (resolver gap done fdcbada3); round 5 (top unfetched refs) read on flats/crossref-5 672d164b, rides rel10, 0 moves expected; vision triangles are item 161. [file](followups/105-follow-cross-references.md)
119. [Claude] [scan: NO for (b); YES for (c)] **Portland page-check notes, reviewed 2026-10-28** -- HOLD (Steph 2026-10-29); (a) DONE a54faf2a; (b), (c) left. [file](followups/119-portland-page-check.md)
142. [Claude] [Steph: through-lot court yellow or red, non-blocking] [scan: YES -- false reds only] **Placement ignores fire reach; stall width; parking down a long lot** -- (a) rounds 1-6, (b) city stall width, court-front-yard all DONE and live; (c) later with 92; open: through lot parking facing the back street (built YELLOW). [file](followups/142-placement-and-stall-width.md)
145. [Claude] [Steph: load charts + parameter answers] [scan: YES when built (colour policy TBD by Steph)] **Set access: truck route, crane setup and lifts solved per lot** -- slice 1 (calculator, not wired) BUILT 6e6669fb on flats/set-access, not yet in a release; waits on Steph's load charts and parameter answers (Steph checking, 11-14). [file](followups/145-set-access-crane-truck.md)
146. [Claude] [scan: YES -- reds/yellows only go green] **Let the drive lane (and court) use the side setback where the code allows it** -- BUILT and LIVE (e92ca641..add83c5f, rescreen-1110); open: read of the side-yard moves not recorded, King City 16.124.110 C buffer unencoded. [file](followups/146-parking-in-side-yards.md)
156. [Claude] [scan: YES (envelopes only)] **Gladstone quadfit rules follow Ordinance 1545** -- quadfit mirror DONE cd5ba695 (main/live); citation pass 33a2a406 rides rel8 (bound running 11-13); optional R5/MR/C2/C3 provenance tidy left. [file](followups/156-gladstone-ordinance-1545.md)
158. [Claude] [scan: YES] **17 fire-reach / front-max reds left after rel4-fixes** -- 14 resolved or read (Hillsboro 45 deg fixed 89aa02bd, live); OPEN: 3 lots whose envelope shrank in rel4, cause untraced (RED = safe side). [file](followups/158-fire-front-max-17-reds.md)
161. [Claude] [scan: YES -- toward yellow] **Sight triangles at corners and driveways** -- open parts BUILT flats/sight-leftovers 2fe743d5 (King City read; alley corners + parking-in-triangle YELLOW+flag; 0 run-124 greens reached), rides rel9; held YELLOW (moot today): OC/Hillsboro engineer-set size, 450 vs 500 ft at 45 mph. [file](followups/161-sight-triangles.md)
162. [Claude] [scan: YES -- toward red, false-GREEN risk] **Tigard entrance rules outside TMU** -- BUILT d35ef11a on flats/tigard-entrances, 0 moves; NOT in main or rel8 (earlier 'rides rel7' was wrong) -- needs a release slot (rel9). [file](followups/162-tigard-entrances.md)
163. [Claude] [scan: YES -- toward green] **Fire retry at the drawing's angle** -- BUILT 7ae34393 on flats/retry-drawing-angle; NOT in main or rel8 (earlier 'rides rel7' was wrong) -- needs a release slot (rel9) and a gain read. [file](followups/163-retry-drawing-angle.md)
164. [Claude] [scan: YES -- toward red, possible false GREEN] **Turned pod not held back where no street direction was measured** -- BUILT 32a510bf (+9f8f71dd), rides rel8 (bound running 11-13). [file](followups/164-no-bearing-parallel.md)
170. [Claude] [Steph] [scan: YES if read the other way] **Hillsboro SCR 5 ft maximum side setback: one wall or both?** -- RULED 11-09 both walls, BUILT + LIVE (84b08a72, 6d5b84d0, rel7); OPEN: city email parked by Steph (offer again). [file](followups/170-hillsboro-side-max.md)

## 2. Waiting on Steph

179. [Claude] [Steph] [scan: YES if adopted] **End-door variant: windows needed** -- 80x25 recount 11-12: 15% rule = 7 windows + door (5 at ~20 ft); ~10,500 lots back; state rule checked, does not reach a single pod; Steph 11-14: perfecting doors on the LONG walls first; end-wall door assessed later (parked). [file](followups/179-end-door-variant.md)
178. [Claude] [scan: YES -- toward yellow] **False-green round 4: driveway spacing tables** -- BUILT flats/drive-spacing e122ec48 (Gresham, OC, West Linn, Milwaukie, Fairview, Sherwood, Wilsonville; 787 greens in reach), rides rel9; judgement 150 ft queue reach (no code figure) -- read Sherwood greens near busier cross streets. [file](followups/178-fg-round4-questions.md)
176. [Claude] [Steph] [scan: YES if (f) answered the loose way] **Questions the rel7 lanes raised** -- (a)(b)(c)(g)(h) answered and live in rel7; open: Steph to drop Sandy Title 17 + Hillsboro Ord 6514/6516 documents (d), Sandy walkway entrance question (f) unanswered (built held), Rivergrove retry (e). [file](followups/176-lane-questions-1110.md)
128. [Claude] [scan: NO] **CI takes an hour or more per push** -- BUILT 2026-10-30: pushes tested on LXC 138 ci-runner (~16 min), GitHub daily; open (optional): quadfit 7 min long pole. [file](followups/128-ci-speed.md)
127. [Claude] [scan: NO] **Cut token spend** -- (a)(b)(e)(f) DONE (7 profiles d387fd7c, 2849fa9a, 90f56c9f); open: Copilot after reset (c), reading pilot, local pre-sort (d). [file](followups/127-token-spend.md)
126. [Claude] [Steph] [scan: NO -- display only] **A fast map of every lot, and a live 3D lot view** -- IDEA 2026-10-29; major feature, check in before any design. [file](followups/126-lot-map-3d.md)
115. [Claude] [Steph] **Tables, superscripts and footnotes in the readable text, Tualatin pilot** -- tables + superscripts/footnotes BUILT + LIVE (8bc86bdc, df9346d5, 6c599e3f); Steph's table review workbook (sent 10-24) not yet imported; open: page-check cards, other cities, footnote-to-cell links. [file](followups/115-readable-tables-footnotes.md)
114. [Claude] **Batch-fix the logged text corrections** -- 'Suggest a correction' box BUILT 145c1f46 (no checker, Steph 10-24); batch-fix when notes accumulate (queue not checked 11-13). [file](followups/114-text-corrections.md)
73. [Claude] [Steph] [scan: NO] **The code library as a public, structured repository** -- STRUCTURING ROLLOUT DONE 2026-10-31 (batch 8 WashCo 07fa1e17, tables 67b9aaa4); hard leftovers kept as known gaps (see file). Hosting PARKED (Steph 2026-11-01: 'Not ready to publicize'). [file](followups/73-code-library.md)
54. [Steph] [scan: NO] **Code-change reader on the Claude API credit ($100/month)** -- Steph picked it 2026-10-07 and declined the other two offered. [file](followups/54-code-change-reader.md)
55. [Steph] [scan: NO] **Expansion scouting on the credit item 54 leaves** -- background scouting; waits until we choose a place to encode. [file](followups/55-expansion-scouting.md)
22. [Steph] [scan: YES if Milwaukie 22 ft aisle adopted] **Portland aisle 20 ft** -- Portland DONE (bacea669, run 44); open: Milwaukie 22 ft aisle, waits on Steph (no ruling on file 11-13). [file](followups/22-portland-aisle.md)
32. [Steph] [(B) Copilot-able after a yes] [scan: NO] **Windows CPU spikes** -- measured: bursts come from test runs and hooks; waits on Steph. [file](followups/32-windows-cpu.md)
65. [Steph] [scan: YES (proof run)] **The Windows PC as an idle-time scan helper** -- Steph GO in principle 11-08 (1 AM-10 AM idle window); research DONE (WSL2), Steph to approve PC setup. [file](followups/65-windows-scan-helper.md)
62. [Steph] [scan: YES] **Roof shape: teach the screen gable vs flat** -- offered 2026-10-09; nothing signed. [file](followups/62-roof-shape.md)
40. [Steph] [scan: YES if started] **Easements from maps** -- odds answered 2026-10-04; not started. [file](followups/40-easements-from-maps.md)
72. [Steph] [scan: NO] **Oregon Explorer statewide map** -- PARKED. [file](followups/72-oregon-explorer.md)
92. [Steph] [scan: YES (parked)] **Parking layout generator (was the second item 27)** -- PARKED by Steph 2026-10-04; scoping only, nothing built. [file](followups/92-parking-layout-generator.md)

## 3. Copilot queue -- low priority, not time-sensitive

23. [Copilot] [scan: NO] **Page check** -- SHIPPED 2026-09-30 (a203e9f1). [file](followups/23-page-check.md)
16. [Copilot] [PARKED] [scan: NO] **Partial re-screen** -- SHIPPED 50a0ecc2 2026-09-25; PARKED -- ask before firing. [file](followups/16-partial-rescreen.md)
