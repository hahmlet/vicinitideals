# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **The county map copy: loose ends after the first promotion (HUMAN_TODO
   20).** The September copy (snapshot 3, run 10: 400,032 lots = 288,031
   measured + 112,001 unmeasured with a reason) was PROMOTED 2026-09-20
   11:29 UTC by the agent on the standing word -- gate clean on all nine
   rows after the 100 zone codes were ruled (637c6dca); drift 2 -> 10
   unchanged at 178 / 0 unexplained (the 18,681 use-gate REDs sit on lots
   run 2 never held); prune had nothing to do (snapshot 1 is the one kept
   whole); Lots default run 10, footer 2026-09-18, probe row 3 ok. Loose
   ends the September map found, queued not fixed: Happy Valley's layer
   carries both `MURM2` and `MURm2` (one lot; the source's casing, kept,
   both aliased to MURM);
   quadfit's s1 condo test reads only stacked geometry, so it measures
   ~2,000 Multnomah condo unit records (PROP_CODE 102/132/202/122,
   1,000-2,000 sq ft) every run -- normalize's `excluded.csv.gz` ledger
   names them and assign drops them (8e596f8b), but s1 itself could read
   the roll's property code the way `flats/normalize/condo.py` does;
   Terrain (DEM tiles) stays `deferred` until the slope stage exists; no
   writer for lot decisions in `app/` yet (they are inserted by hand or by
   a future review page); a decision on a lot whose verdict moved in a
   re-screen of the same copy (`promote --run`) is not marked "look again"
   -- only ground and zone changes are flagged, so a re-screen's moves are
   read in its drift report and nowhere on the lot page; the 142 lots
   quadfit refused as `zone_quadplex_not_allowed` (all Multnomah
   `_unincorporated` RR) are NOT two rule sets disagreeing -- read
   2026-09-20, the FLATS block also says `quadplex_allowed: false`, behind
   a `planned_development` lever the use gate skips by design (a levered
   value is a relief path, not a permission), so they sit NOT_MEASURED
   rather than USE_PROHIBITED; what they want is a relief-policy line (is a
   planned development on 20-acre rural land a path, yellow, or not, red),
   not a re-read.
2. **Neighbour zoning per lot line -- loose ends after the measurement
   (4b25df09 + the carve fix cfc8c033; re-screened as run 12 and PROMOTED
   2026-09-22 10:30 UTC on the standing word -- the first §4b run: gate
   clean on eight rows, drift 10 -> 12 = 289 of 576,062 answers moved,
   0 unexplained, every one the carve fix read both ways: +10/+15 ft of
   fit on tier-C lots cut uniformly at the front number (Portland
   R5/R7/R10/R20/RM1/R2.5, Multnomah R10/R20, Wilsonville V: 283
   yellow->unknown -- the pod fits now and the lot's unreadable width
   shows instead of the relief it no longer needs) and -5 ft on Wood
   Village LR 7.5 / LR 12 where quadfit cut 15 against a resolved 20 (3
   green->yellow, 1 green->unknown, 2 unknown->yellow); the neighbour
   fact itself moved no verdict, as the bound said; county if_signed
   green 64,565 / yellow 475,357 / unknown 34,754 / red 1,386 rows).**
   s4 reads the zone across every non-street line; FLATS answers
   `abuts_nonresidential_zone` in Portland / Troutdale / Fairview and
   `abuts_residential_zone` in Oregon City (ANY line tightens, EVERY line
   relaxes; anything unresolved stays UNKNOWN). Still owed, most lots
   first: (a) `abuts_lower_density_zone` is declared in Clackamas
   `_unincorporated` only (2026-09-22: ZDO Table 315-4 note 14 became the
   10-ft variant on MR1/MR2 `setback_side_ft`, the cap lifted, the ten
   315.01 districts are the true side; read on the MR1/MR2 lots since run
   14, see (b)). An observed fact lifts a
   caps.json cap and the base number would certify with the footnote's
   other number never encoded
   (`test_no_declared_condition_caps_a_value_on_that_layer`), so the two
   cities still capped stay undeclared: Oregon City R-2 (twelve fields;
   the note narrowed to `zones: [R-2]` 2026-09-22 -- R-3.5/R-5
   `min_density` had been caught by region scope only) is a dead end until
   `utility_easement` is read, because every OC R zone is capped on THAT
   fact on every field too (no easement layer in RLIS -- a measurement
   question, not an encoding one). Wood Village TC (167 lots, seven fields
   incl. `like`): Table 235-2 note (3) is a plain 15-ft side/rear variant
   on `abuts_residential_zone` (the disposition names the lower-density
   fact; re-point it) with a list from sections 210/220 (LR 7.5, LR 12,
   MR 2, MR 4 true) vs 230/235/240/250/260 (NC, TC, LM, GM, C/I, O false);
   note (2) is a HEIGHT PLANE FROM THE LOT LINE -- 25 ft within 25 ft of a
   light-residential line, +1 ft per 2 ft beyond (the 26-ft pod clears it
   ~27 ft in) -- which `step_back` cannot express (it charges the whole
   standard from the setback line), so it needs a variant-level form, and
   it also fires ACROSS A STREET ("right-of-way adjacent to a light
   residential zone"), which the per-line measurement does not read yet
   (same across-the-street question as Portland 33.910 in (d)). (b) DONE 2026-09-23 -- the nine `AHEAD_OF_QUADFIT`
   zones ported (0504ef84, larger neighbour limb, `needs_verification`),
   re-screened as run 14 and PROMOTED 18:43 UTC on the standing word
   (gate clean on eight rows; 0 of 576,062 earlier answers moved; the
   1,557 new lots answer for the first time: MR1/MR2 338 green-if-signed
   rows, the note-14 fact read; Oregon City commercial 0 green -- see 12).
   (c) 1,938 lots in the turning zones still
   lean on the fact: 813 a blank point across a line (park / ROW /
   fabric gap), 802 no non-street line at all (ringed by streets and
   alleys; the relaxing fact needs EVERY line), 272 a split-zone
   neighbour, 46 both, 5 a neighbour in another city. The
   blank-point class wants `abuts_park` from RLIS orca (Troutdale MU-3
   owes 10 ft "abutting a park regardless of zoning" -- the row that kept
   OS off both lists, troutdale.yaml L1866). (d) Portland CI1/CI2: 33.150
   gives a CI lot 10 ft against OS, so the shared Portland list is wrong
   for CI home lots -- safe only while CI stays capped on
   `site_specific_limitation` (guard test); a per-zone list and the
   across-the-street reading (33.910) when that cap lifts. (e) Troutdale's
   5 ft side against HDR is unread.
3. **The court search takes the biggest rectangle, not the deepest one that
   holds a row.** `s6s_siteplan.py` `_largest_rect(ok[court_r0:, :])` returns
   the maximum-AREA all-clear rectangle behind the building and then asks
   whether it is deep enough for a row of stalls (stall + two-way aisle). A
   wide, shallow rectangle can win that contest on an irregular lot while a
   narrower rectangle one cell over is deep enough for a row -- a lot refused
   `court_too_shallow` that has a court. Conservative direction (a lost
   GREEN, never a false one), so it has waited; the 2026-09-17 aisle run
   turned 113 plans into `court_too_shallow` / `no_side_lane` and some may be
   of this kind. Measure first: re-search the failed lots for the deepest
   rectangle at least `cap x stall_w` wide and count how many would hold a
   row, before changing the search. Offered 2026-09-17.
4. **Four places the screen and the county map disagree, found by the
   bridge's sample run (2026-09-17) and left alone on purpose.** Named so
   the comparison stays readable, each its own change: (a) the court's
   shape -- `court_across` draws one row of stalls across the lot behind
   the building (six at 9 ft = 54 ft), quadfit's s6s lays the stalls in the
   largest rectangle behind the building whichever way round fits, so a
   63-ft-wide Portland R5 lot seats eight along its depth where the 54-ft
   row does not fit across it -- 18 of the 63 quadfit greens the screen
   calls yellow (all on `fit_ft`) seat six-plus that way; (b) the alley is
   the aisle (Steph 2026-09-13) on the county map and nowhere in
   `flats/score/` -- 33 of the 63 park on the alley in quadfit; (c)
   quadfit's policy gates are not site facts: `z_overlay_constrained_site`
   (PCC 33.418), the overlay kill layers, `existing_*` current use and the
   sewer gate (`no_public_sewer` is a hard gate there; here `public_sewer`
   is observed but no Clackamas standard turns on it) -- 84 of the 178
   screen-GREEN / quadfit-red lots in the sample; (d) the sweep -- the
   screen tries 180 angles, s6 fits at the front bearings only, and 94 of
   those 178 are quadfit `siteplan_no_layout` lots the sweep found a fit on;
   (e) which street is the front on a corner lot, and the lane in from the
   side street (FOLLOWUPS 5 at the time, now 6: slice B, 9522942d + fcea6d57) -- on the county
   map only; `flats/score/paper.py` still faces s4's first bearing and
   brings the lane down the side of the building, so the screen's stall
   count and `fit_ft` on ~60,000 corner lots read the old drawing.
   Also owed: FLATS's own envelope from the corpus setbacks
   (`geom/envelope.buildable`) instead of quadfit's carved one, and
   `steep_slope` from s5o's DEM percentile / Gresham's hillside overlay
   (assumed False today, named on every lot it leans on). County-scale
   sizes from the four-stall county run (2026-09-18, `/root/bridge_county2`),
   on the 4,024 quadfit-green / FLATS-yellow lots (all `fit_ft`): (b) 3,507
   on the alley (2,976 seating four there), (a) 517 off their own lane, 268
   of them seating eight with the row along the lot; (c) + (d) are 21,660
   GREEN-where-red. Also under (a), the other direction: on the 13,196 lots
   both call green FLATS seats FEWER than quadfit on 3,881 (one row across
   where s6s found two) and MORE on 160 (`target` where quadfit's tier is
   `minimum` 100, `preferred` where `target` 58) -- find what the screen's
   row counts that s6s's rectangle does not before changing either. The
   stall count was decided 2026-09-18 (HUMAN_TODO 18) and is out of this
   item.
5. **Draw what the screen fitted on the lot page.** `/flats/lots/{county}/
   {tlid}` (`app/api/routers/ui_flats.py`, the "lots" section) draws the
   outline only. Two things are missing before the building can be
   drawn on it: quadfit's carved envelope (s5o `wkb`) is not carried by
   `scripts/flats_load_bridge.py` -- a geometry column on `flats.lots`
   (migration) and one more `export` column; and the screen's `fit_for`
   reports depth / across / angle / orientation but no *position*, so a
   placement (the rectangle's origin on the lot, in 2913 feet) has to be
   returned by the fit and stored in `checks.fit` before anything can be
   drawn. Offered 2026-09-18 with the pages.
6. **Where parking may SIT, and which street is "the front".** Offered
   2026-09-19 when Steph asked why the court is always behind. **Steph's
   ruling 2026-09-19:** trying each street as the front applies ONLY where
   the lot has more than one street AND the code leaves the choice to us;
   HUMAN_TODO 21 DECIDED: (1) the orientation that turns the lot green,
   (2) if both, the one that reaches the `preferred` band, (3) if both
   preferred or both only `minimum`, the orientation whose COURT has the
   least exposure to a street (its frontage on street edges; a court on no
   street beats one along the shorter street beats one along the longer);
   a higher band wins before exposure decides. **More parking is not a
   goal** ("sufficient, but minimal parking so we can fit a 2nd pod"), so
   s6s's "keep the orientation with the MOST stalls" rule goes. And read
   every city for multi-street rules even where the front is clear.
   **Slice A DONE (this commit):** three per-line fields encoded in all 14
   layers from the corpus and mirrored into `footprints.yaml` /
   `DrivewayRules` -- `front_lot_line_corner` (shortest: Portland 33.910,
   Oregon City 17.04.490, Wilsonville 4.001, West Linn 02, Multnomah 39.2000,
   Wood Village 720.030; owner: Gladstone, Happy Valley, Milwaukie, Gresham
   3.0100 (deeper-street condition), Troutdale; entrance: Tualatin,
   Fairview; both: Clackamas ZDO 202), `corner_access_street` (side for a
   unit-lot townhouse in Gresham / OC / Milwaukie / Wilsonville / Fairview /
   Troutdale; lowest_class: Clackamas 845.02, Milwaukie 12.16, OC 16.12.035,
   West Linn 48.025, Wilsonville PWS, Fairview 19.162; any elsewhere) and
   `parking_side_prohibited` (true only on the unit-lot branch of Gresham /
   OC / Milwaukie / Wilsonville / Troutdale; exempt on the one-lot fourplex
   everywhere; Fairview 19.30(D)(2)(a) is a setback, not a ban, since its
   side yard is the setback strip). Read by no screen yet (`SILENTLY_UNREAD`).
   **Measured 2026-09-19 on the September tree** (`measure_corner_front.py`,
   each street tried as the front, `/root/corner_front_measure.parquet`
   on 137): 59,620 corner lots of 222,955 evaluated; both fronts park
   7,491 / today's only 2,224 / the OTHER only 4,149 / neither 45,756.
   Today's front is the LONGER street on 58,019 (97 %) -- so in the six
   `shortest` cities (44,275 corner lots: Portland 38,455, West Linn 2,052,
   OC 2,004, Wilsonville 867, Multnomah 759, Wood Village 138) the drawing
   faces the wrong street by the code; Portland alone parks 3,189 lots
   only from the shorter street and 1,260 only from the longer. In the
   owner/entrance/both cities 705 lots park only with the other front
   (Clackamas 336, Gresham 164, HV 86, Milwaukie 59, Troutdale 25, Fairview
   21, Gladstone 12, Tualatin 2). Where both park, 7,294 of 7,491 seat 8
   and 8; same band 7,387; the court is less exposed with today's front on
   4,161, with the other on 1,360, tie 1,866; the court touches no street
   on 852 today / 406 other. What stops the other front: court_too_shallow
   2,300, no_side_lane 1,426, too_few_stalls 395. **Slice B BUILT (this
   commit, `s6s_siteplan.py`)**: `_candidate_fronts` faces the shortest
   street where the code fixes it (both when equal), each street where the
   owner/entrance chooses, the longest where unread; the flip reads one
   street; `townhome_rear_court_side_street` brings the lane in from the
   side street across its strip (`_alley_mouths` + `_lane_to_alley` on the
   side-street edges, `_street_setback_for` = s5's F cut) where
   `corner_access_street` is any / lowest_class / side; `_plan_rank`
   chooses green > band > least court exposure (`court_street_ft`) > own
   aisle > least pavement -- never most stalls, so within a band a lot may
   show fewer stalls and the same colour; new columns front_bearing_deg /
   fronts_tried / court_street_ft; 56 siteplan tests. **BOUND on 137
   2026-09-19** (s6s -> s7 on the September tree; three runs, two fixes
   found by reading the LOST lots one by one): run 1 (9522942d) faced
   738 lots the wrong way because "shortest street" was read as the
   shorter SUM of a street's front edges -- streets at both ends summed
   past the side, a jogged frontage's 30 ft step "won" -- fixed fcea6d57
   (`_extent_along`: the lot LINE, corner to corner); run 2 still lost
   200, 117 of them lots whose two "streets" are 20-45 degrees apart --
   one street that bends, which s4's 20-degree clustering splits (15,530
   of 86,775 two-bearing lots) -- fixed 364c360e (`CORNER_MIN_DEG` 45:
   one street, every front edge, drawn as before; an acute corner such as
   Sandy Blvd forgoes its second front until s4 holds the street's name
   per edge, (c) below). **Run 3 (364c360e), the bound:** only corner
   lots moved, no interior lot changed colour (22 interior lots show
   fewer stalls in the same band -- `_plan_rank`, by design);
   site_plan_ok +7,984 / -83; verdicts green 20,119 -> 23,477 (red->green
   3,368, green->red 10), review 13,495 -> 15,798 (red->review 2,338,
   review->red 35), red 256,418 -> 250,757; 12,203 lots drawn to two
   fronts, 12,986 face the street s4 did not list first, 14,778 take the
   lane in from the side street (Portland 11,416); greens gained by city:
   Portland 2,801, Gresham 211, Troutdale 98, Oregon City 91, Milwaukie
   66, West Linn 53, Clackamas 28, Wood Village 14, Wilsonville 5,
   Multnomah 1. The 83 losses (Portland 65, Multnomah 6, OC 5, WL 5,
   Clackamas 1, Wilsonville 1; court_too_shallow 48, no_side_lane 31) are
   the code's front -- a real corner whose shorter street is too shallow
   to park behind -- or a flip the old drawing had wrong (12E29AB00200
   parked in its FRONT yard). Diff `/root/corner_diff.py`, moves
   `corner_moves.csv`, parquets `s6s_lots.{before_corner,corner_v1,
   corner_v2}.parquet` on 137. **LOADED 2026-09-19 as the county copy's
   candidate, run 10 replacing run 8** (run 8 retired in one transaction,
   its bundle kept as `bridge/2026-09-18.run8`; re-export from the same
   assign dir with `--code-version`/`--rules-version` of run 8, 6044713f,
   so the 288,031 FLATS verdicts read as unchanged -- only quadfit's
   badge, stalls and method on the lot page moved). Still awaits Steph's
   read (HUMAN_TODO 20: trips `new_zones` by design).
   Then (iii) a named side-court arrangement and (iv) through lots,
   which turn out to be one slice. **Measured 2026-09-19 evening**
   (`data/quadfit_2026-09-18/through_lots.csv` on 137): 6,118 lots have
   ONE bearing and front edges at both ends more than 40 ft apart; 1,327
   draw ok today (green 487 / review 479 / red 361), 4,791 fail
   (court_too_shallow 2,602 -- both ends carry the front setback, which
   the codes require: Portland 33.910 "a through lot has two front lot
   lines", Wood Village 720.030, Gresham "each street frontage shall be
   considered a front yard"; no_side_lane 871; no_court 176; 1,136 never
   evaluated). Two halves. (iv-a) **Portland and Milwaukie ban the
   drawing we make today**: the rear court sits between the building and
   the SECOND street, and 33.266.120.C.1.a prohibits vehicle area "between
   the primary structure and the street" unless "entirely behind the
   front and side street building lines" (both ends are fronts), Milwaukie
   19.505.3.D.4.a "not directly between the facade of a primary building
   and an abutting street right-of-way" -- 826 through lots draw ok there
   today (green 325 / review 201 / red 300), a false-GREEN direction; a
   lane from the second street cannot cure it, only a court BESIDE the
   building (iii) or a refusal, so (iii) comes first and is bound on
   these 826 (expect greens lost, then some recovered by the side court
   where the lot is wide: today's ok through lots are 90 ft wide at the
   median). (iv-b) the other twelve cities state no ban, so the court
   behind the building is lawful in the second front yard and the lane
   may come in straight from the second street across its setback strip
   (`townhome_rear_court_side_street`'s construction on the far end's F
   edges; access rule Tualatin 36.400(b), West Linn 48.030(B)(5),
   Fairview 19.162.020(5), Clackamas 845.03(A)(3) = lowest class, drawn
   as `any` per (c); alley-fed cities keep the alley): at most the 380
   no_side_lane lots outside Portland/Milwaukie (Gresham 85, Clackamas
   83, WL 51, Multnomah 38, HV 31, OC 25, Wilsonville 24, Troutdale 13)
   plus a few no_court. **(iii)+(iv) BUILT (this commit, `s6s_siteplan.py`,
   65 siteplan tests):** `_through_ends` splits one street cluster's
   edges into two ends where the widest gap across the bearing is >= 40
   ft (and half the lot's extent, with the corners), and each end is
   tried as the front under every corner word; `front_ban` (Portland,
   Milwaukie) refuses EVERY rear court on a through lot, alley-fed
   included, and offers `townhome_side_court` (`_side_court`: the largest
   rectangle beside the building, stalls against the side lot line, aisle
   along the wall -- `max(aisle_two, lane)` wide, West Linn's 24 ft lane
   into its 23 ft aisle -- no farther back than the rear wall, the front
   lane straight into the aisle) or `townhome_side_court_alley`; in a ban
   city the side court is never drawn on a side whose strip holds another
   street's cells (33.266.120.C.1.a "behind the front AND side street
   building lines"); elsewhere `townhome_rear_court_rear_street` brings
   the lane in from the far end where the access word is any /
   lowest_class (the `any` cites are silence about WHICH street, read as
   silence about the far end too -- say so if a city's through-lot rule
   turns up). `_plan_rank` bins exposure to 5 ft (raster corner cells) and
   ranks own-aisle rear court > side court > alley-aisle on a tie. **And
   the rear court is TRIMMED to the rows it parks** (`_court_places`): it
   was the whole free rectangle behind the pod -- second row at the back
   of the lot, aisle paved across the lot's width, side along the side
   street for the room's depth -- which is the opposite of "sufficient
   but minimal" and made the side court win any lot wide enough to hold
   one; now one or two rows (both tried) at any corner of the room, a
   court that can slide off a street's strip offered at zero exposure
   with a lane to that street; the one-row court turns its aisle toward
   the lane. On a synthetic grid of 312 lots: no colour moved, 194
   drawings did (68 interior lots pave less and open more, 36 corner side
   courts / whole-room courts became hidden rear courts, 11 Gresham
   through lots took the far-street lane, 44 alley courts shrank); s6s
   ~3 % slower. `parking_area_sqft` / `open_space_sqft` move on every
   rear-court lot. **BOUND 2026-09-20 on the September parquet in FOUR
   runs (~14 min each, every one read lot by lot against run 10) and
   LOADED 2026-09-20 into run 10 in place (same 400,032 lots from the
   same assign dir, so the loader's upsert refreshed the candidate rather
   than retiring it; drift 2 -> 10 unchanged at 178 / 0 unexplained; the
   gate still `new_zones` only, Steph reads).** v1 (net +3,149 site
   plans) hid two lane bugs in
   its losses: the trimmed court at the room's four corners missed a
   mouth that meets a 3-acre room mid-side (`_court_places` takes the
   whole room's lane), and the front lane had to be free from the
   BUILDING's front row, which no column beside the pod is on a lot whose
   front bends (`_front_runs`: from each column's own edge on the strip).
   v2 (net +7,141) hid a bug in that fix -- the strip was sought at the
   FRONT setback's reach where a corner lot's edge is cut to the
   street-side one (161 lots; now `street_reach`) -- plus two honest
   classes the OLD drawing had paved without looking: flag-lot poles and
   partial frontages. v3 took the pole as the lane where it is at least
   the lane's width (resumed at the body's top); v4 keyed that on the
   strip's WIDTH, since a 16-ft pole between 5-ft side setbacks keeps a
   6-ft sliver that is no more a lane than no sliver (127 v3 losses
   cured, 104 Portland; 0 new). **Final (v4 vs run 10):** site plans
   gained 7,880 / lost 1,860; green 23,477 -> 25,127, review 15,798 ->
   18,571, red 250,757 -> 246,334 (6,357 moved: red->green 2,084,
   red->review 3,306, green->red 434, review->red 533 -- Portland's 414 +
   444 are the through-lot ban); through lots ok 4,243 -> 4,028 (Portland
   2,994 -> 1,939: 1,780 side courts, 1,502 refused by the ban; Milwaukie
   66 -> 55; every other city UP on the far-street lane, e.g. Clackamas
   373 -> 586, Gresham 267 -> 451); corner lots ok 14,512 -> 16,229;
   one-street 35,358 -> 39,876; on lots ok both ways the pavement median
   fell 3456 / 3156 / 2802 -> 2160 sq ft (through / corner / one-street)
   and the court's street exposure fell on 12,145 corner + 2,437 through
   lots. Methods after: rear court 36,468, side court 6,579 (+18 off an
   alley), rear court from the side street 10,627, from the far street
   1,474, alley 1,622, alley-aisle 5,126. Lost by reason: `no_court` on
   1,252 through lots (the ban, by design), `no_side_lane` 429 (330
   one-front, 99 through), `court_too_shallow` 160 (through lots whose
   trimmed court no longer reaches), `too_few_stalls` 15, `no_alley_lane`
   4. The 429 `no_side_lane`, read via `/root/lane_diag3.py` on 137: 151
   have no envelope cell on the street strip at all (about 120 poles and
   stubs narrower than the lane -- the old drawing took a 5-ft pole --
   and about 30 wide fronts whose envelope stands off the street reach:
   tier-C round buffer, overlay carve-outs, (m)); 278 have a strip at
   least the lane wide but no clear column that meets a court (stubs,
   notches, bent fronts, (k)). All were ground the old drawing paved
   without checking. Read on the gained side: the 123 pole lots v3/v4
   restored are 106 true poles (the lot's ground at the street is the
   street piece) and 17 lots whose street piece is shorter than the neck;
   on 92 of them the drawn lane stands off the pole's span (median 23 ft,
   six wide tracts 240-400 ft) -- the same lots with the same undrawn jog
   run 10 had, queued as (n). **Divergence noted, not changed:**
   `_front_setback` in s6s main falls back to 10 ft when the effective
   front setback is None OR ZERO (Portland CM2/CM3 lots run with a 10-ft
   pod setback and a 0-ft street strip, `fsb=10.0 ... ssb=0.0` in the
   trace) -- report/queue as (o). Queued from this slice: (f) the rear
   court keeps a tie with the side court; Steph's "room for a 2nd pod"
   could read the other way (prefer the side court so the rear yard is
   free) -- the ties are NOT counted: only the winning offer is in the
   output, so counting needs both offers written out; (g) the two-row
   court's lane lands on its near row's end where a stall is drawn
   (one-row courts turn the aisle to the lane; two-row need the landing
   carved out of the row or the lane run to the aisle band); (h) the
   alley-aisle court (`townhome_rear_court_alley_aisle`) still scores the
   whole room's exposure -- trim it to its stall row + back-out depth;
   (i) which end of a through lot is "the front" is read as the
   applicant's choice under every corner word (Portland 33.910 makes both
   ends front lot lines) -- read the other 13 cities' through-lot lines;
   (j) in a ban city the side court is drawn on ONE side of a through-lot
   pod -- a court on both sides where one side is short of the band;
   (k) the partial frontage / stub lane: a street piece that lines up
   with no column beside the pod (278 lots above, e.g. Gresham
   `1N3E30CB  -12300`) -- slide the pod onto the stub's columns, or run
   the lane through the setback strip with a jog and charge it; needs the
   lot polygon minus overlays, which `layout_lot` does not receive
   (`lot_xy` is the bare corners); the test to flip is
   `test_a_stub_front_that_misses_the_columns_beside_the_pod_is_refused`;
   (l) `_alley_mouths` uses square caps, so at the street reach a lane may
   start up to `street_sb` past the frontage's END (21.5 ft in Gresham;
   the two v2-vs-v3 differences were this) -- clip the strip to the edge's
   own extent and count the moves; (m) the ~30 wide fronts with no
   envelope cell within the street reach: s5's tier-C envelope is
   `buffer(-max(setbacks))`, round and uniform, not per edge, and an
   overlay carve-out can eat the strip -- refused today, count which is
   which; (n) the pole's lane jog: in the pole case the lane is taken at
   any column of the body's top while `_placement` puts the pod first-fit
   at the top-left, so a pole at the left leaves the lane to the pod's
   right with an undrawn, uncharged run along the body's top (92 of 123
   restored pole lots; six wide tracts with a short street piece where
   the envelope's strip, not the lot's ground, called it a pole) -- key
   the pole rule on the lot's ground at the street (`lot_xy` suffices)
   and place the pod beside the pole's lane (block the lane's corridor
   before placement), then bound: some 77-100 ft Portland bodies lose the
   56-wide pod to the 36-wide; (o) `_front_setback`'s 10-ft fallback on a
   ZERO front setback (above): a pod 10 ft back where the code asks
   nothing -- decide whether 0 is the drawing or a placeholder, then fix
   and bound.
   Queued behind it, each to bound first: (a) s4 measures lot
   width/depth along the LONGEST street (`cluster_bearings` orders by
   length) -- in the shortest cities width and depth are swapped on most
   corner lots, which moves `lot_width_ft` facts and every width gate; (b)
   Portland 33.266.120.C.1.b: on a corner lot the court must sit behind the
   side-street building line and pave at most 20 % of the side-street
   setback -- the drawn lane is consistent by construction (court inside
   the envelope, a 12-ft lane is ~12 % of the strip), so only "behind the
   building line" is unread; (c) `lowest_class` needs a street classification per edge (s4
   holds none; drawn as `any` and said so at runtime); (d) Fairview
   19.30.050(D)(2)(a) side-yard parking setback -> redirect ledger; (e)
   Gresham 3.0100: the front is fixed where the minimum lot depth is met
   in one direction only (needs depth both ways = (a)).

7. **Green and outdoor space: charge the SHAPE, not just the amount.**
   Offered 2026-09-19 when Steph asked whether we consider outdoor-space
   rules for townhomes. What exists: the county map (s6s) subtracts
   building + court + driveway from the lot and tests the leftover against
   the city's stated AMOUNT (Gresham 15 %, Portland 250/200 per lot and 192
   in RM, Milwaukie 384 = 96 x 4, Multnomah county by zone; 0 of 46,212
   drawn plans on the September map fall short, Portland's tightest has 848
   sq ft to spare, median leftover 49-77 % of the lot -- as an amount it
   never decides a colour); the app screen reads `open_space_min_pct` and
   `min_landscaped_pct` as lot MINUS BUILDING only (parking never
   subtracted though every code excludes pavement -- `OPTIMISTIC_CHECKS`)
   and never reads `open_space_min_sqft` at all (encoded in Portland x18,
   Milwaukie, Multnomah LR7; the reach ledger should already list it).
   What no layer holds: Portland 33.110.240 -- a contiguous 250 sq ft in
   which a 12 x 12 square fits, outside the front setback, not vehicle
   area; Milwaukie Table 19.505.3.D.1 -- a 96 sq ft patio per GROUND-FLOOR
   UNIT, 5 ft minimum dimension, opening from inside the unit, fenced from
   the neighbour (not on unit lots) -- on a rear-court plan those four
   patios sit between the back wall and the court, i.e. inside the depth
   `court_too_shallow` (140,472 lots) already fights over; Happy Valley
   16.42.030(B)(1) 20 % landscaping named for fourplexes, Portland RM
   15-30 %, Oregon City R-2 15 %, Fairview 20-25 %, Wilsonville 15 % -- no
   landscaping reserve on the county map at all. Ruled and NOT owed:
   Troutdale 8.120.B.1.b voids open space for quadplexes (its 60 sq ft/unit
   is a balcony); Oregon City 17.62.057 is multi-family, the quadplex
   chapter states none; Wilsonville's 25 % is Villebois, delivered
   communally; Gladstone / Tualatin / West Linn / Clackamas county state
   none for this building. Options: (a) honest leftover in the screen --
   subtract court + lane (the fit knows both), read the sqft field, drop
   the optimistic label; cheap, few or no moves expected; (b) the shape on
   the drawing -- Milwaukie: `gap` behind the wall becomes max(gap, patio
   depth = 96 / unit width) on 916 ok plans; Portland: place a 12 x 12
   square in the leftover outside the front setback and off the pavement
   (`no_open_space` then means something); (c) landscaping share on the
   county map; (d) what the leftover is FOR -- sheds, garages, ADUs, a
   second pod -- is product direction, not a rule; the leftover medians
   above say a second pod is plausible on many lots and belongs with
   the parking item's (now 6) "least ground under pavement". Measure the affected
   population (Milwaukie ok plans with court depth within 7 ft of the
   floor; Portland ok plans with no 12 x 12 square outside the pavement)
   before any county run.

8. **Screen the ~210 pocket lots under the layer their ruling names.** A
   `pocket` ruling (16 of them, 2026-09-20) says "this code is the other
   layer's zone carried on this map" and today gates the lot ZONE_POCKET,
   unscreened, because `like:` cannot cross into `_unincorporated` (there is
   no `or/clackamas.yaml` parent) and `ZoneRuling` has no field naming the
   zone under the `of` layer -- the note names it in prose. Happy Valley
   RRFF5 95 / FF10 5 / RA1 1 / RA2 8 / RC 1 / VR57 1 (111), Troutdale NSA
   64 (county Gorge zoning; Chapter 38 is in the corpus now and would
   answer RED for GGR/GSR), Oregon City `County` 14 (Clackamas zoning
   inside the city, per OCMC 17.68.025), Multnomah UPAGI 8 / UPAR-10 4
   (Troutdale's GI and LDR-1), Clackamas IPU/MG/R-10/R-15/R-MD/RC-ME 9
   (city codes in county pockets). Give `ZoneRuling` a `zone:` (the code
   under the `of` layer; default the same spelling), let `assign` resolve a
   pocket lot through `RuleSet.resolve(of, zone)`, and screen it with the
   `of` layer's measurements. Mostly RED at the use gate (RRFF5/FF10/RA/RC
   are farm-forest and rural zones, NSA is Gorge); the R-10/R-15/R-MD/
   UPAR-10 lots would get a real answer.
9. **Corpus drift found while ruling the September codes -- a
   `--refresh --repoint` pass per layer.** (a) Clackamas ZDO: zdo.315/316/
   510/845/903/1005/1015 and every roadway.* doc report CHANGED (the county
   re-published the ZDO; the stored text is the old cut) and the zdo.202
   end marker no longer matches; every quote into those docs must be
   re-pointed (`flats/provenance` `--repoint` follows the quoted text).
   (b) Portland Title 33 PDFs held in the Multnomah `_unincorporated` layer
   (33.100/33.110/33.140/33.266) CHANGED at the same length -- likely a
   re-issued PDF with the same page count; re-fetch, diff the text, repoint.
   (c) Fairview: every codepublishing.com URL now returns a 1.3 KB
   "hosted on eCode360" stub -- the city moved to eCode360 (FA4439; Title
   19 TOC guid 50509052; print view `https://ecode360.com/print/FA4439?guid=
   <n>`; chapter numbering unchanged, 19.25 = 50509402, 19.30 = 50509420,
   19.65 = 50509772, 19.135 = 51011016). Re-point every `code:` entry in
   fairview.yaml, re-fetch, repoint quotes; the 19.25.ah doc already points
   at eCode360. Until (c) is done a `--refresh` of Fairview would replace
   every stored chapter with the stub -- do not run it layer-wide first.
10. **Two loose ends from the ruling pass.** (a) Fairview FLX is the map's
   name for the "VC flex" area (19.135.txt L62) and is aliased to VC, whose
   `inside_mapped_use_area` variant names that same area -- the map code
   could FEED the variant (a lot zoned FLX is inside the area by
   definition) instead of leaving it unmeasured; one lot today. (b) THR is
   one lot (1N2E36DA-02200, the Gresham IGA-162nd pocket) whose code no
   published document defines -- not Gresham 4.0100, not MCC 39; ruled
   `to_read` and worth one question to Gresham planning if it ever
   matters; nothing else owed.
11. **Measure `civic_corridor` (Portland Map 130-1).** The neighbour bound
   found the fact alone frees almost no Portland lot: nearly every unknown
   CR/CM1/CM2/CM3 lot ALSO leans on `civic_corridor` (front setback 0 ->
   10 ft "adjacent to a Civic Corridor shown on Map 130-1", 33.130.215.B.1.a;
   RM2 coverage 60 -> 70), or already fails fit_ft / min_density /
   parking_cap. ~2,900 unknown Portland commercial lots have the corridor
   as their last lever. It is a line on an adopted map, not a fact in the
   parcel record: acquire the Civic / Neighborhood Corridor layer (Portland
   open data; a registry entry with a count tolerance), measure "street
   lot line adjacent to a corridor street" in s4 as a per-LINE fact the way
   the alley was (the front on the corridor takes 10, another front 0),
   read it in FLATS as an observed site fact. Read what "adjacent to"
   means in 33.910 first, and bound both ways on the subset.
12. **The envelope is cut with quadfit's table, not the corpus's
   resolution -- the rear is reconciled, the sides are not.** The carve
   fix (2026-09-22: s5 `env_setbacks_json`, bridge `carved_rear_ft`,
   `LotFacts.envelope_rear_ft`, `_court_beyond_rear`) charges the court
   against the strip s5 really cut at the REAR. The SIDES and FRONT still
   stand at quadfit's number: Portland CE side 10 -> 0 against a
   non-residential neighbour resolves in FLATS while the envelope is
   already 10 ft narrower each side, so `fit_across_ft` and the seat count
   are conservative by up to 20 ft of width on every True lot, and the same
   for any variant that relaxes a side or front (alley side, corner
   street side). Two ways: (i) carry "S"/"F" from `env_setbacks_json` and
   widen the search -- arithmetic on a shape already cut; (ii) build the
   envelope in FLATS from the lot polygon, the edges and the RESOLVED
   setbacks (`flats/geom/envelope.py buildable` exists for it; the bridge
   would call it instead of reading s5o's wkb) -- the real fix, and the
   point where quadfit's s5 stops mattering to the screen. Bound (ii) on
   the subset first: every lot whose FLATS envelope differs from s5's must
   be explained by a variant that fired, and the diff read both ways.
   SIZED 2026-09-23 on run 14: Oregon City C/MUC-1/MUC-2/MUD are carved at
   20 ft side/rear everywhere (the port's larger limb); on lots FLATS reads
   as NOT abutting a residential zone -- where the code says "None" -- 456
   lot-and-design answers are yellow on `fit` alone, and no Oregon City
   commercial lot is green. That is the biggest single pool this item
   would unlock.
13. **Tax code area in the RLIS ingest.** The Gresham tax-impact snapshot
   (`scripts/flats_tax_snapshot.py`, migration 0136) needs each lot's tax
   code area (RLIS `TAXCODE`), which acquire drops because it is not a
   declared field; the script's `taxcodes` step pulls it separately out of
   the quarterly ZIP. Declare `TAXCODE` in the RLIS fields and carry it into
   `facts["assessor"]` so the next snapshot joins on the lot row and the
   county copy and the code areas are guaranteed the same release.
14. **Tax impact beyond Gresham.** `flats/config/tax/or/multnomah/2025-26.yaml`
   holds Gresham's eleven code areas only. Another city needs its code
   areas' rates (Multnomah's levy-code-rates PDF, split local option /
   bond / urban renewal as the Gresham file does) and its CPR row; Clackamas
   needs its own rate file and CPR table (a different county publication).
   Pending decision: which city next (the pitch is per-city).
