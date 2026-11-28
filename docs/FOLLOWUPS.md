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
2. [Claude] [scan: YES] **Neighbour zoning per lot line -- (a) LIVE (run 124); (c) RE-COUNTED 11-18: 3,666 lots lean on an unknown neighbour fact, 53 green and all 53 pass under both answers -- closed; (d) guard done, CI2 on hold; (e) parked. [file](followups/2-neighbour-zoning.md)
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
217. [Claude] [scan: NO] **Spend the monthly API credit ($200) in tiers, never over** -- DEADLINE ~11-30; key in, LIVE 11-27: t1 security patches running, t1b code-change read DONE (-> 218), t2 completeness DONE 9 places $31 (-> 222); t3 dev jobs from 222 next, last ~$20 green checks. [file](followups/217-api-credit-tiers.md)
218. [Claude] [scan: maybe] **Code changes from the 11-27 sweep: Wilsonville amended (lines shift, Village path looser), Gladstone moved to eCode360, OAR/ORS footer-only** -- refresh/repoint + re-point Gladstone URLs. [file](followups/218-code-changes-2026-11.md)
222. [Claude] [Steph: 6 questions] [scan: YES] **"Do we have everything?" 9-place check (11-27)** -- 7 likely false-GREEN gaps in held text (Milwaukie vegetation, Clackamas 1009 landscaping, Gresham FAR, Oregon City Thimble Creek, Hillsboro stub ends, West Linn 38.030, Beaverton Cooper Mtn) -> t3 build jobs; questions + fetch list in file. Green check 30 lots: 23 right / 0 wrong / 7 can't tell. [file](followups/222-completeness-2026-11.md)
223. [Claude] [scan: YES] **Portland corner lots: parking court not kept behind the side-street building line (33.266.120.C.1.a)** -- left over from item 5; count on 137 first, then build the clip. [file](followups/223-corner-court-side-street-line.md)
224. [Claude] [scan: maybe] **pypdf held at 6.19 (18 security alerts open; all others cleared 11-28)** -- the extraction hold breaks from 6.20.1; re-extract the corpus and compare, then lift the `<6.20` cap. [file](followups/224-pypdf-past-6-19.md)

213. [Claude] [Steph: entrance-side red?] [scan: done] **Foundation reply FD8: six-step cap, stair room, real doors** -- LIVE run 134 (2026-11-28, 677621dc); only Steph's entrance-side red-vs-yellow question open. [file](followups/213-foundation-fd8-six-step-cap.md)
214. [Claude] [scan: YES -- toward red] **Precast steps in a front or side setback: read and encode each city's projection allowances** -- opened 11-21; Steph 11-27: steps allowed where the code is silent, porch/deck allowances count; building on flats/step-setbacks. [file](followups/214-step-setback-projections.md)
215. [Claude] [scan: YES -- toward green] **Portland short connector roads read as limited roads; re-placement can land worse** -- BUILT 181fc5ef on flats/pdx-connectors; Steph 11-27: bridge ramps stay limited, freeway-line-only reds go yellow (building); bound after 213 ships. [file](followups/215-portland-connector-roads.md)
216. [Claude] [scan: YES -- toward green] **Court turns for the deeper stair-room courts (fd8 F3)** -- bound + read 11-28: 1,504 Y->G all right, no false GREEN; RELEASING.
225. [Claude] [scan: YES -- toward yellow/green] **Stair-room red: try the court's other turn fixes before red (136 of 151 dcourt reds)** -- opened 11-28 from the dcourt read; after 216 ships. [file](followups/225-stair-room-try-other-fixes.md)
221. [Claude] [scan: YES -- toward green] **Stair-room stand-back slides along the street on corner lots (~34 wrong reds) + 4 held yellows** -- opened 11-27 from the fd8c read; after the 213 release. [file](followups/221-stair-standback-corner.md)
219. [Claude] [scan: YES -- toward green] **Lot-by-lot parking layout builder: trial on the ~4,200 near-miss reds first** -- opened 11-27 from Steph's question; PARKED 11-27 (Steph: continue current lanes first). [file](followups/219-parking-layout-trial.md)
220. [Claude] [scan: YES -- toward green] **Short slip roads outside Portland: read each city's definition of a street** -- READ 11-27: Clackamas uninc, Milwaukie, Multnomah uninc cover it; Tigard/Beaverton/WashCo unclear (stay limited); encode on top of 215. [file](followups/220-slip-roads-outside-portland.md)
212. [Claude] [scan: no move expected] **Fire access rules still cite the 2022 fire code and the 2022 local guide; the 2025 code and 2025 guides are now held** -- found 11-19; 150 ft, 20 ft and dead-end figures re-read and unchanged; compare the rest, store the 2025 guide, re-point the citations; after rel11. [file](followups/212-fire-citations-2025.md)
211. [Claude] [Steph: Q52, Q56, none blocking] [scan: YES -- toward green/yellow] **Freeway, ramp and railroad sides: fix LIVE in rel11 (run 131)** -- open: Q52 freeway side outside Portland, Q56 unmeasurable widening strip, state access-control layer, choose front after fire. [file](followups/211-open-way-fix.md)
208. [Claude] [scan: YES -- toward green if curb-cut-only reading] **Beaverton 3 ft driveway rule: fix LIVE in rel11 (run 131)** -- open: is 3/6 ft measured at the curb cut only or along the whole lane (built stricter); Q51 optional. [file](followups/208-bvt-drive-side.md)
209. [Claude] [scan: no colour change] **Foundation model per lot: how it sits, what it takes, what it costs** -- Steph 11-19, from the foundation agent's FD6 spec (../Factory-Sim/docs/research); SHIPPED 11-19 a29a596c (lot-page panel, API block, reprice command); 11-20 2342792a now covers all 44,211 drawn lots on the framing footprint; left: re-measure after each release; findings SENT to the foundation agent 11-20, waiting on its recommended changes. [file](followups/209-foundation-model.md)
207. [Claude] [scan: NO for geology; YES toward yellow for streams] **Two public data candidates from Steph links (11-18): surface geology for the foundation agent; federal stream map (NHDPlus HR) as a yellow flag where a city has no stream layer** -- scouted, not started; geology after the FD5 report goes back, streams after rel11. [file](followups/207-public-data-candidates.md)
206. [Claude] [scan: YES -- toward yellow/red, FALSE GREEN] **Lane/court in a side yard vs carves: fix LIVE in rel11 (run 131)** -- open: front-yard drive is not drawn so unchecked against carves; size it. [file](followups/206-carve-overlap.md)
205. [Claude] [scan: YES -- toward yellow/red] **Seven noted gaps: fixes LIVE in rel11 (run 131)** -- open: RM1/RM2 20 ft max front setback not sized, no city street-class maps / Hillsboro standards, 26 ft pod config notes unchecked. [file](followups/205-noted-gaps-sized.md)
204. [Claude] [Steph: scenic / OC hazard / greenway / 2 Beaverton lots, none blocking] [scan: YES -- toward yellow/red] **Overlay inventory: fixes LIVE in rel11 (run 131)** -- open: Steph's yellow-or-green answers, overlays with no public map (Canby, Cornelius, Estacada, Sandy, Durham, Sherwood, Happy Valley, Clackamas historic), texts not in the library. [file](followups/204-overlay-inventory.md)
203. [Claude] [Steph: Estacada D, Gresham shop-front yellow or red, non-blocking] [scan: YES] **Commercial-zone greens: fixes LIVE in rel11 (run 131)** -- built yellow pending Steph; open: 8 Gresham DTM lots unchecked, OC MUD two-storey reading. [file](followups/203-commercial-zone-greens.md)
202. [Claude] [scan: YES -- toward yellow] **Portland FEMA gap: fix LIVE in rel11 (run 131)** -- open: 8 greens in the 50 ft edge band, PCC 24.70 / Title 3 map not fetched, carry the 1996 layer, reload flood notes, 73 Metro-flagged greens partly unread. [file](followups/202-portland-fema-gap.md)
201. [Claude] [scan: YES -- toward green/red, hunts] **Round 4 class hunt: fixes LIVE in rel11 (run 131)** -- open: untested next hunts (15 narrow-frontage flag lots, footnote-scope errors), 3,405 landlocked lots on open right-of-way, Beaverton corner clearance maybe too strict, RLIS tax-code banner check. [file](followups/201-fg4-class-hunt-fixes.md)
199. [Claude] [scan: NO] **Ground levels and soil per lot for the foundation agent (FD2/FD5)** -- FULL report issued 11-19 (fd5-pass2-summary.md + fd2_lots.csv, 195 columns; stage B flattest position and soil rating reasons in; flats/fd2-pass1 56806fe1, not merged). Only left: re-run the file after rel10 ships; basements not held by decision. [file](followups/199-ground-levels-under-building.md)
152. [Claude] [Steph] **ci-runner: optional OOM protection for its Postgres** -- run cap + Postgres check shipped (70c1cb75); only the optional OOMScoreAdjust=-900 unit setting on 138 is left, Steph's call (only if Postgres is OOM-killed again). [file](followups/152-ci-runner-overload.md)


185. [Claude] [scan: YES -- every lot] **Screen the 80 x 25 pod, 20 ft tall, 9'2" storeys** -- RULED 11-12 (three rulings); BUILT c6f46146, LIVE run 126 (2026-11-15). Open later: trace Kenton 33.538.230 Map 538-4 (held YELLOW whole now). [file](followups/185-pod-depth-30.md)

188. [Claude] [scan: YES -- first pass live since rel9 (9046c755: 10-90% cut lots screened both ways); last case BUILT flats/cut-district b3a730d3 (from rel10d; lot 90%+ one side with the plan on the piece across the line -> YELLOW + DISTRICT-EDGE flag); 11 cut greens read, none false; moves no colour on run 128; scope 232 lots; rides the release after rel10 (hand-off cut-district.handoff.md). [file](followups/188-cut-district-untested.md)
189. [Claude] [scan: YES -- toward green only] **rel7 move-read fix-forwards: pdx-9ft cases not moved, Thorville bulb unmeasured, Clackamas R10 51.2% share red** -- none a false GREEN. F5/F6 (ingest cert, recipe root) done 766dd02d. [file](followups/189-rel7-fix-forwards.md)
191. [Claude] [scan: YES -- toward green only] **Middle townhouse lots asked for the corner lot's 25 ft frontage (false RED); drop 3 untied Hillsboro UC entries** -- BUILT flats/corner-th-191 3652cfa6 (rides rel10 with pagecheck-34); ~40 Gresham RED->YELLOW, 0 GREEN; Hillsboro UC entries deleted. [file](followups/191-corner-townhouse-false-red.md)
192. [Claude] [Steph: Q1 Q2 Q7 Q9-Q11 Q19 info asked] [scan: YES -- mostly moot today] **Steph's 11-14 answers: encode Fairview all corners, OC/Hillsboro engineer sight GREEN+flag, Gresham MDR-24 alley 16 ft, King City per-side buffer** -- rulings recorded 4cb7d85a; lane BUILT flats/rulings-1114 98fe014b (rides rel10). New Steph Q: Hillsboro driveway engineer-set sight area same as corners? [file](followups/192-rulings-1114-lane.md)

### 1a. The weekly re-screen: traps to honour before it, moves to read after it

- Weekly re-screen state -- run 128 PROMOTED 2026-11-18 (rel9, 623 moves, main 6b1665c5; 137 snapshot scan-run128-2026-11-18); NEXT rel10 pack. [file](followups/weekly-rescreen.md)
77. [Claude] **Road land to the centre line in the cities** -- all built and live (7cbc3346, d3b6db52, 19ee2d97, e67b7193); only the no-centre-line case (34 lots) left conservative, needs a new centreline source. [file](followups/77-city-road-dedication.md)
78. [Claude] [Steph: confirm 2029 transit-street RED vs YELLOW] **Portland false GREENs: main street minimum floor area and protected historic buildings are RED** -- all built and live (4ed70036, 8d1597ef, bc380601); only Steph's confirm that a 2029 mapped-transit-street lot is RED (built under no-variances) left. [file](followups/78-portland-false-greens.md)
80. [Claude] [Steph: (c) human copy of Wood Village 235.400/490] **Readings for Steph from item 64 round 2** -- (a)(b)(d) ruled/built and live; 1S113BA07700 ruled 11-03 (show green), build not recorded; (c) waits on a copy; (e) flag_instances staleness unchecked. [file](followups/80-item64-round2-readings.md)
76. [Claude] [Steph: (c) assessor lookup] **Tigard pod80x25 red at exactly -43 ft, and split-zoned lots** -- (a)(b) merged and read at run 78; only (c) open: human lookup of Estacada tax lot 34E20AC00201 owner. [file](followups/76-tigard-minus-43.md)
42. [Claude] **Water, wetland and flood ground at slope's fidelity** -- DONE and live; three accepted known gaps left (washington_habitat flag, Portland transition-area under-carve, unread Clackamas WQRA/HV/Tualatin). [file](followups/42-wetland-flood-fidelity.md)
29. [Claude] [Steph: (C) county widths, deferred] **Fire reach: measure where the truck really stands** -- (A) d8880db1 and (B) 57313463 live; (C) asking WashCo/Clackamas/West Linn for pavement widths deferred by Steph. [file](followups/29-fire-reach-truck.md)
30. [Claude] **Net land area review** -- SHIPPED and live (d8d4a439, 995f0007, 183 values); remaining floodplain/resource-overlay areas stay unmeasured (`may_less`). [file](followups/30-net-land-area.md)
36. [Claude] [Steph: the OAR strip question] [scan: YES] **Parking tool queue** -- mostly LIVE (f7ba7038, 1723db45, 1d3c89cb); OAR 660-046-0220 strip question still open for Steph; some cities' strips and chapters still unencoded. [file](followups/36-parking-tool-queue.md)
8. [Claude] [scan: YES if (b) is taken up] **Pockets + corridors -- leftovers** -- all code live, both checks DONE 2026-11-09; only (b) open: 66 ZONE_POCKET lots (Troutdale NSA, Oregon City County, Beaverton WAcnty). [file](followups/8-pockets-corridors.md)
21. [Claude] [Steph: worktree go; HUMAN_TODO 26] [scan: YES for (a)-(c); NO for (d)-(e)] **Post-2027 world** -- (b) built and live (runs 46, 49); (a) state layer to adopted Div 46 and (c) Oregon Homes path wait on Steph's worktree go. [file](followups/21-post-2027-world.md)
64. [Claude] [scan: NO] **Measure the false-GREEN rate** -- ROUND 4 DONE on run 128: pooled 1 wrong + 2 doubtful of 100 (1%, was ~4%); class hunt 1 class / 4 lots of 9,517; fixes in item 201 (rel10); after rel10 propose the stopping signal to Steph. [file](followups/64-false-green-rate.md)

### 1b. Built lanes not merged yet (merge so they ride a weekly)

(rel10 PACKED flats/rel10 04bd6129 11-18, full bound RUNNING on 137 -> rel10-bound.result.md; then move read, then release. Left out: wide-road corner (own lane, sizing), 194(1)(3)(4). RLIS November copy needed right after release.)

### 1c. The rest, most urgent first (dated items first)
194. [Claude] [scan: YES -- (1)(4) + 158's envelope lot BUILT flats/false-reds-194 1e25ffa6 (from rel10d), rides the release after rel10, gains to be read one by one; (3) stays RED; open: 40 street-class losses in Milwaukie/OC/West Linn/Sherwood, Steph's downtown Gresham driveway question. [file](followups/194-rel8-false-reds.md)

100. [Claude] [scan: YES (yellows only go green)] **Driveway street: measure it instead of asking** -- MERGED e63617b8, LIVE (run 124). Open: (a) measure the street line the drawn drive crosses; (b) a Happy Valley street-class map -- until then MEASURE-DRIVE-STREET / ACCESS-STREET-RANK-UNKNOWN yellows stay. [file](followups/100-driveway-street.md)
86. [Claude] [Steph: (B) unattributed rulings] [scan: NO] **Agents could not recall a property ruling** -- A, B, C1, C2 merged and live (CI1 live in run 124); (B) leftovers (Tigard MUR, Portland total-turn, Hillsboro SCR, Milwaukie aisle) wait on Steph; RICAP MP5/MP4/TA9 not encoded; DLCD watch weekly. [file](followups/86-ruling-recall.md)
2. [Claude] [scan: YES] **Neighbour zoning per lot line -- (a) LIVE (run 124); (c) RE-COUNTED 11-18: 3,666 lots lean on an unknown neighbour fact, 53 green and all 53 pass under both answers -- closed; (d) guard done, CI2 on hold; (e) parked. [file](followups/2-neighbour-zoning.md)
13. [Claude] [scan: NO -- lands with the November county refresh] **Tax code area in the RLIS ingest** -- TAXCODE still not declared on main; lands as first step of the RLIS 2026_11 refresh (released 2026-11-05; plan ~11-19, after rel6 which has shipped) (status unverified 11-13). [file](followups/13-taxcode-rlis.md)
53. [Claude] [Steph: (b) Molalla PDFs; (c)-(d) HUMAN_TODO 30; (f) Downtown yes/no] [scan: see file] **Canby, Sandy, Estacada, Molalla** -- Estacada, Canby, Sandy LIVE (item 85 merged c20ea3a1). Waits on Steph: Molalla PDFs (HUMAN_TODO 29), Estacada q1-5 (HUMAN_TODO 30), Downtown zone. Owed, Claude: re-read Canby/Sandy doubts now 85 landed. [file](followups/53-canby-sandy-estacada-molalla.md)
87. [Claude] [Oak Hills RULED RED 11-07] [scan: YES -- BUILT and LIVE (run 124). 11-18: Giese House + Ely Building placed (Gresham, Y->R, in flats/commercial-fixes); Joy Theater and Doriot/Rider Log House lots already red; 84 unmatched state listings mostly forest/dam/bridge entries, 18 addressed ones have no lot. Open: Lake Oswego (switched off). [file](followups/87-historic-outside-portland.md)
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
113. [Claude] [Steph: design before build] [scan: NO] **Two-source check: a second review queue** -- HOLD -- Steph 2026-10-29; after 73; major feature, check in. [file](followups/113-two-source-check.md)
112. [Claude] [Steph: S8 storage, flag 372, eight re-asked flags] **Page check: show the passage that sends a number to another table** -- (a)(b) DONE and live; Gresham 4.1152 S9-S13 READ 11-18: no false green (S11/S12/S14 held, rest garage-only); open: 34 numbers with no stored tie, Steph's three questions. [file](followups/112-page-check-via.md)
109. [Claude] **Design districts** -- all chunks and Portland plan districts parts 1-2 LIVE (last: batch C in rel2; min floor area is item 148); left: Gladstone Portland Ave C-2 strip waits on a better map (20 lots yellow). [file](followups/109-design-districts.md)
105. [Claude] [scan: YES (new standards bind)] **Follow every cross-reference one layer down** -- rounds 1-4 DONE and live (9a229b24, b78a4495, 3f1e7f0e); open: Beaverton Type A frontage map trace (download OK), West Linn Ch 28 (resolver gap done fdcbada3); round 5 (top unfetched refs) read on flats/crossref-5 672d164b, rides rel10, 0 moves expected; vision triangles are item 161. [file](followups/105-follow-cross-references.md)
119. [Claude] [scan: NO for (b); YES for (c)] **Portland page-check notes, reviewed 2026-10-28** -- HOLD (Steph 2026-10-29); (a) DONE a54faf2a; (b), (c) left. [file](followups/119-portland-page-check.md)
142. [Claude] [Steph: through-lot court yellow or red, non-blocking] [scan: YES -- false reds only] **Placement ignores fire reach; stall width; parking down a long lot** -- (a) rounds 1-6, (b) city stall width, court-front-yard all DONE and live; (c) later with 92; open: through lot parking facing the back street (built YELLOW). [file](followups/142-placement-and-stall-width.md)
145. [Claude] [Steph: load charts + parameter answers] [scan: YES when built (colour policy TBD by Steph)] **Set access: truck route, crane setup and lifts solved per lot** -- slice 1 (calculator, not wired) BUILT 6e6669fb on flats/set-access, not yet in a release; crane guide (28 t + 45 t charts) delivered 11-14; slice 2 direction 11-14: report only (no colour), 28 t then 45 t, trailer spot = 45 t landing, street set-up by road width, power lines later. Slice 2 BUILT 9c8f9ff0; 11-14 plan change (IC-80 primary, 45 t fallback, 28 t dropped): slice 3 BUILT flats/set-access-3 04616184; slice 3b BUILT 8f1fc121; slice 3c f59c08f3; FIRST SAMPLE 11-15 (598 greens): IC-80 3, 45 t 46, not viable 56, unmeasured 493; gear changes 3 lots; 11-14 Steph: IC-80 picks from street trailer + carries; ignore curb; trees matter; slice 4 BUILT 2263ffc5; 4b BUILT ec10aab7, sample: IC-80 5 (25 without trees), 45 t 47, undecided 489 (pavement width missing 469); street-width scout DONE: real data ~1/5 of lots; street width A+B BUILT 0f159ea9 (unmeasured 489->272, not viable 57->269); city street standards BUILT 1b94fdaa (17 places), sample s4f: unmeasured 269, not viable 271, 45 t street 9; offered widest strip vs local-street strip for unmatched ROW; sample run on 137 after rel8 bound. [file](followups/145-set-access-crane-truck.md)
146. [Claude] [scan: YES -- BUILT and LIVE; side-yard greens READ 11-18 (705 tested by geometry, 50 read: none wrong; two tight at the rear line kept: 22E17CD05007 Gladstone 4.7 of 5 ft, 22E21DC02300 Oregon City 4.56 of 5 ft); open: King City 16.124.110 C buffer unencoded. [file](followups/146-parking-in-side-yards.md)
156. [Claude] [scan: YES (envelopes only)] **Gladstone quadfit rules follow Ordinance 1545** -- quadfit mirror DONE cd5ba695 (main/live); citation pass 33a2a406 LIVE run 126; optional R5/MR/C2/C3 provenance tidy left. [file](followups/156-gladstone-ordinance-1545.md)
158. [Claude] [scan: YES] **17 fire-reach / front-max reds left after rel4-fixes** -- 14 resolved or read (Hillsboro 45 deg fixed 89aa02bd, live); OPEN: 3 lots whose envelope shrank in rel4, cause untraced (RED = safe side). [file](followups/158-fire-front-max-17-reds.md)
161. [Claude] [scan: YES -- toward yellow] **Sight triangles at corners and driveways** -- open parts BUILT flats/sight-leftovers 2fe743d5 (King City read; alley corners + parking-in-triangle YELLOW+flag; 0 run-124 greens reached), LIVE run 128 (rel9); held YELLOW (moot today): OC/Hillsboro engineer-set size, 450 vs 500 ft at 45 mph. [file](followups/161-sight-triangles.md)
170. [Claude] [Steph] [scan: YES if read the other way] **Hillsboro SCR 5 ft maximum side setback: one wall or both?** -- RULED 11-09 both walls, BUILT + LIVE (84b08a72, 6d5b84d0, rel7); OPEN: city email parked by Steph (offer again). [file](followups/170-hillsboro-side-max.md)

## 2. Waiting on Steph

179. [Claude] [Steph] [scan: YES if adopted] **End-door variant: windows needed** -- 80x25 recount 11-12: 15% rule = 7 windows + door (5 at ~20 ft); ~10,500 lots back; state rule checked, does not reach a single pod; Steph 11-14: perfecting doors on the LONG walls first; end-wall door assessed later (parked). [file](followups/179-end-door-variant.md)
178. [Claude] [scan: YES -- toward yellow] **False-green round 4: driveway spacing tables** -- BUILT flats/drive-spacing e122ec48 (Gresham, OC, West Linn, Milwaukie, Fairview, Sherwood, Wilsonville; 787 greens in reach), LIVE run 128 (rel9); judgement 150 ft queue reach (no code figure) -- read Sherwood greens near busier cross streets. [file](followups/178-fg-round4-questions.md)
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

210. [Claude] [Steph] [scan: no] **State building code books as an agent reference library (fire, residential, electrical, plumbing; plus state interpretations and alternate methods); NOT encoded** -- Steph 11-19; two UpCodes chapter prints extract cleanly with Oregon amendments already merged; internal use only (Steph 11-19); state rulings collected; Steph printing chapters into data/flats/books/building-codes/<book>/ -- check each on arrival. Status log docs/flats/building_code_books.md. [file](followups/210-building-code-books.md)

## 3. Copilot queue -- low priority, not time-sensitive

23. [Copilot] [scan: NO] **Page check** -- SHIPPED 2026-09-30 (a203e9f1). [file](followups/23-page-check.md)
16. [Copilot] [PARKED] [scan: NO] **Partial re-screen** -- SHIPPED 50a0ecc2 2026-09-25; PARKED -- ask before firing. [file](followups/16-partial-rescreen.md)
