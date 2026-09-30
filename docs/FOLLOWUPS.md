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
   condo records: DONE e7217598, live in run 42 (assign 2026-09-30:
   0 measured lots excluded, was ~2,001);
   Terrain (DEM tiles) stays `deferred` until the slope stage exists; no
   writer for lot decisions in `app/` yet (they are inserted by hand or by
   a future review page); a decision on a lot whose verdict moved in a
   re-screen of the same copy (`promote --run`) is not marked "look again"
   -- only ground and zone changes are flagged, so a re-screen's moves are
   read in its drift report and nowhere on the lot page; the 142 Multnomah `_unincorporated` RR lots behind a
   `planned_development` lever are a relief-policy question -- HUMAN_TODO 23
   (2026-09-25). No lot decisions exist yet (0 rows 2026-09-25), so the
   "look again" flag has nothing to mark until a review page writes some.
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
   question, not an encoding one). Wood Village TC ENCODED 2026-09-23 (28850154): note (3) = side 15
   on `abuts_residential_zone`, note (2) = a VARIANT-level `step_back`
   (27 ft side+rear for the 26-ft pod on `abuts_lower_density_zone`; the
   across-the-street half is inert -- the ROW counts toward the distance),
   both facts declared, TC cap gone, quadfit TC side 27 (larger limb);
   Re-screened with 86b06340 below as run 16 and PROMOTED 2026-09-24 on
   the standing word (gate clean, no warnings; drift 14 -> 16: 22 of
   579,176 answers moved, all rules, 0 unexplained -- every one a Wood
   Village TC lot whose neighbour fact is now read: 21 unknown->green,
   1 unknown->yellow; the rest of TC moved slack inside yellow).
   (b) DONE 2026-09-23 -- the nine `AHEAD_OF_QUADFIT`
   zones ported (0504ef84, larger neighbour limb, `needs_verification`),
   re-screened as run 14 and PROMOTED 18:43 UTC on the standing word
   (gate clean on eight rows; 0 of 576,062 earlier answers moved; the
   1,557 new lots answer for the first time: MR1/MR2 338 green-if-signed
   rows, the note-14 fact read; Oregon City commercial 0 green -- see 12).
   (c) 1,938 lots in the turning zones still
   lean on the fact: 813 a blank point across a line (park / ROW /
   fabric gap), 802 no non-street line at all -- ANSWERED 86b06340 where s4 traced
   the lot and it is not irregular (a whole block: EVERY-line True,
   ANY-line False; 1,565 lots county-wide, ~370 of them Portland
   commercial; the tier-C and untraced ones stay unanswered), 272 a split-zone
   neighbour, 46 both, 5 a neighbour in another city. The
   blank-point class: `abuts_park` BUILT a89a3b9b from RLIS ORCA (per-city
   `parks:` block; Troutdale MU-3's 10 ft park row encoded, OS now
   non-residential; only Troutdale conditions on a park in the corpus).
   Live in run 42 (s4 2026-09-30 carries `park_across_json`; ORCA sits
   in quadfit raw/ but was never acquired into snapshot 2026-09-18 -- do
   that at the next county refresh). (d) Portland CI1/CI2: 33.150
   gives a CI lot 10 ft against OS, so the shared Portland list is wrong
   for CI home lots -- safe only while CI stays capped on
   `site_specific_limitation` (guard test); a per-zone list and the
   across-the-street reading (33.910) when that cap lifts. (e) Troutdale's
   5 ft side against HDR is unread -- SIZED 2026-09-23: at most 13 MU
   lots see an HDR neighbour, the unread half only relaxes (7.5/15 ->
   5), and reading it needs a fourth neighbour fact ("every line
   non-residential OR HDR"); recommend leaving it unless those lots
   come up.
3. **Alley leftovers (rear alley caad6f3f run 24; side alleys + the
   6-inch tight-fit rule 82d4c7de, run 26 PROMOTED 2026-09-26 on the
   standing word: 730 answers moved, 0 unexplained -- 669 unknown->green
   and 52 yellow->green if signed, 9 yellow->unknown where the fit was the
   only miss and an unmeasured fact is left; 3,848 lots carry the "tight
   fit" flag, 744 park in a column along a side alley).** Left: (a) 36 of
   run 24's 4,803 quadfit cannot draw (knife-edge or a slanted alley),
   read and accepted. (b) Of the 55 side-alley lots gained, quadfit draws
   no pod on 23 -- 15 because quadfit keeps the pod across the front while
   FLATS turns it (a wide shallow lot, court at the alley end), 3 an
   irregular block, the rest overlays; read, accepted; if Steph wants the
   drawing to agree, quadfit's s6s needs the turned pod. (c) FIXED 8bf9a451, live in run 42 (s4 2026-09-30 carries
   `alley_cover_json`): s4 fires a ray every 5 ft along each
   alley line; the court uses a side alley only where it runs the whole
   side line (`flats.geom.alley.side_alley_along`). Expect 12 Portland
   lots (24 rows, <=3 green-if-signed) to go street-fed. Same over-read,
   FIXED 59533da1 (live in run 42): the alley is the
   court's aisle only where it runs the whole rear line (a stub still
   reaches the court); rear alley waivers/numbers only on a whole-line
   alley; the side-alley number is cut per stretch in `buildable`. Probe:
   ~64 rear-alley lots stop short, ~8 green->yellow expected (4-15), 0-5
   side moves. Left: quadfit s6s still reads the alley as the aisle on
   3-of-5 (FIXED 10f193ea, rides the next s6s run); Gresham's
   rear-with-alley number on a second rear line FIXED 09171698 (14 rows /
   7 lots shrink, 0 colour moves); a rear alley along PART of its line:
   BUILT c089acea -- the covered stretch takes the alley's rear, the rest
   the ordinary rear, cut per stretch as side lines are; both cuts are
   screened and the better kept (the court is charged against the smaller
   strip). Probe on 09-29 s4: 53 part-covered rear lines (52 Portland, 1
   Gresham), 48 cuttable; 0 colour moves, 4 lots gain room (+0.5 to +32
   ft), nothing worse -- rides the next re-screen; whether a
   line an alley runs PART of is "a lot line abutting an alley": RULED by
   Steph 2026-09-28 -- careful reading (covered stretch only), and the
   covered stretch is the travel lane only if long enough: BUILT 288f0daa
   (covered run with buildable ground behind it >= stalls x stall width;
   probe 53 partial rear lines, 30 long enough, 23 not). Left: the fit
   compares length only, it does not place the court against the stretch;
   the lot page could say when an alley stops short. (d) Gresham's 200 alley lots fail lot
   area/frontage regardless.
4. **Four places the screen and the county map disagree, found by the
   bridge's sample run (2026-09-17) and left alone on purpose.** Named so
   the comparison stays readable, each its own change: (a) the court's
   shape -- **side court BUILT 3e8e3bab/1b7b5567 (deployed 15ffab9e,
   rides the next full run)**: a court BESIDE the building with its aisle
   straight in from the street, tried only when the row behind fails;
   bound 3,551 lots: 0 losses, 152 yellow->green if signed (Portland 137),
   228 yellow->unknown (no variance now, an unmeasured fact left). Still
   open: an L/T-shaped search for the other 339 quadfit-fits lots; two-row
   stall count. FIXED cef95109: the beside court must come within 3 ft of
   the envelope's front (full run 0930 had 61 greens with the court up to
   151 ft back on L-shaped and flag lots, e.g. 1N1E13DC -00600, Gresham
   1S3E10AD -05300). LIVE: run 42 PROMOTED 2026-09-30 (full 0930 + reach
   + private-drive splices; drift 39 -> 42 7,679 moved / 0 unexplained;
   yellow->green 2,374 from the beside court). Original note: `court_across` draws one row of stalls across the lot behind
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
   **(e) DONE ca52f76a, run 28 PROMOTED 2026-09-27** (4th splice, 66,443
   corner lots with bearings >= 45 deg apart; 4,854 answers yellow->green,
   2,755 yellow->unknown (the fit now passes; the same unobserved fact the
   lot already leaned on decides it), 1 green->yellow; drift 7,610 / 0
   unexplained, matching the bound). `front_lot_line_corner` is followed:
   shortest line fronts (both within 1 ft), owner/entrance tries both and
   keeps the better, `both`/unread keeps every street a front; the other
   street is `street_side`, the interior line beside the front a `side`;
   `corner_access_street` any/side drops the lane. Leftovers: (i)
   `lowest_class` keeps the lane -- nothing measures street class;
   (ii) corner lots with an alley are left unnamed (the alley's name is
   resolved against either frontage); (iii) the court's end is assumed to
   reach the side street, as for a side alley; (iv) Wilsonville V: 25
   answers lose slack because the long interior lines are now SIDE lines
   (7.5 ft) not rear (5 ft) -- correct by the code, never changed a
   colour; (v) three Clackamas-unincorporated unnamed lots moved on input
   vintage (s4 2026-09-24 vs the base's), replayed identical on main and
   the branch; (vi) DONE b440fc67 -- `corner_lot` asks the corner-front 45 deg
   question through `flats.geom.corner.two_streets` (one street direction
   False, two >= 45 deg apart True, 20-45 deg left unasked); rides the next
   re-screen, expect some green->yellow in Gresham, Wood Village LR,
   Wilsonville, Multnomah MR4/LR5. Open: Gresham's corner is two or more
   streets at any angle incl. through lots -- a through lot with parallel
   streets still answers False (possible false GREEN on Gresham's
   tightening corner variants) -- FIXED f171c994: where the layer
   defines corner by `frontage_count` (Gresham 3.0100#L1304) a through lot
   (`flats.geom.corner.through_lot`) is a corner; expect tens of
   green->yellow in Gresham MDR-12/24, VLDR-SW, OFR on the next run. Open:
   Wilsonville 4.001(157)(2) / MCC 39.2000 pathway corners (HUMAN_TODO
   24); Private drives DONE 876267ad/a731c661 (rides the next full s4->s7
   run: new s4 column `sans_drive_json`): per-city `private_drives:`
   rulings (10 count a private road as a street; Gresham, Tualatin do
   not), a drive over the lot or across another lot screened both ways,
   worse kept. Bound (09-28 data): of 2,526 drive greens 1,594 stay,
   358 -> yellow, 574 -> unknown (565 have no real street without the
   drive), 0 gained. RULED by Steph 2026-09-30, BUILT dbc2cc40 (live in
   run 42): a private road is a way in for the parking
   everywhere (`QuadfitLot.access`), the yards follow the city --
   Gresham/Tualatin ordinary line, Fairview (two definitions) both ways
   worse kept, Clackamas ZDO 202 exc. 2 `access_choice` (both, better
   kept; drive-only lots read with the drive as front). Drives on other
   land give no way in. RLIS road types 1700/1800 read from the data.
   (FLATS's own envelope: DONE, item 12.) (`steep_slope` struck
   2026-09-27: no standard in the corpus is conditioned on it, so its
   False assumption leans on no lot; the hillside rules ride the overlay
   layers.) County-scale
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
   **(b) DONE caad6f3f** (`parking_alley_backout_ft`; leftovers item 3).
5. **Draw what the screen fitted -- DONE (666c6837, full run 31 PROMOTED
   2026-09-27; new splice base 137 /root/bridge_draw_full, 0 splices).**
   Leftovers: the drawing keeps the verdict's angle, so on a wide shallow
   lot the plan can run along the street; a side-alley column is drawn as
   a row behind the building.
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
   (i) DONE 67402fea (rides the next full run) -- `front_lot_line_through`
   per city; bound 17 Clackamas-uninc green-if-signed -> yellow, Gresham
   862 / Fairview 84 envelopes shrink, Milwaukie 8 grow; RULED by Steph
   2026-09-30 as built (city governs -> follow it, unmeasured -> worst:
   Gresham/Clackamas access control, Tualatin/Fairview lowest-class
   access; free choice -> the end that fits); street class per edge would
   loosen them;
   (j) COUNTED, not built: in a ban city the side court is drawn on ONE
   side of a through-lot pod -- a court on both sides would help 8 lots;
   (k) DONE 4a3cc09c -- s6s reserves a lane's
   width on the street strip before placing the pod beside it (court
   searched near the lane, straight lane charged as pavement; runs only
   after every front failed "no side lane", never on alley lots). Replay
   on 137 (09-29 data): +890 plans of 20,949 no-side-lane lots, 0 lost, 0
   other moves; rides the next s6s->s7->bridge run. Left: bent fronts whose
   body swings off the strip (Gresham 1N3E30CB -12300, ~238 of the 286
   targeted) need an angled/jog lane;
   (l) BUILT 5cb2bd75 -- the street strip is cut flat at a free end and
   keeps its square extension only where another street edge carries on
   (bend, corner clip, front meeting side street); the alley strip is
   unchanged (whether an alley that stops mid-lot needs the same is open).
   547e0578: a chain of street edges is one strip, its free end cut
   along the lane, not the last clip piece (the first cut refused 14
   clipped-corner lots wrongly). The 09-28 s1->s7 lost 50 lanes: 14 back,
   ~17 run past the frontage's end (correct), 5 side-street, 2 now short
   of stalls; the 7 read: 94fed5e3 gives the strip's free end half a
   grid cell of slack (2 slanted-line lots) and retries the side court
   up to 6 times when the biggest rectangle has no lane (1S1E03CB-80000);
   replay of the 88 moved lots: 36 lost -> 31 (29 no lane, 2 few stalls),
   0 regressions (137 /root/strip_chains/v2/replay2.csv). 32E07DC03600:
   the curved line past the lane may be a street s4 does not label --
   worth a look; (m) COUNTED 2026-09-29 on 09-18 data: 32 wide
   fronts with no envelope cell in street reach = 7 overlay carve-outs, 6
   round tier-C insets, 3 tier B with no strip, 16 with a strip in both
   envelopes (an older s6s refused them -- re-check on the current run);
   (n) BUILT 91840447 (lane out of the pole, pod
   beside it, charged from the street; local trial 65 lost / 51 redrawn /
   884 same -- read the 15 cul-de-sac/angled "not a pole" losses on the
   county run) -- was: the pole's lane jog: in the pole case the lane is taken at
   any column of the body's top while `_placement` puts the pod first-fit
   at the top-left, so a pole at the left leaves the lane to the pod's
   right with an undrawn, uncharged run along the body's top (92 of 123
   restored pole lots; six wide tracts with a short street piece where
   the envelope's strip, not the lot's ground, called it a pole) -- key
   the pole rule on the lot's ground at the street (`lot_xy` suffices)
   and place the pod beside the pole's lane (block the lane's corridor
   before placement), then bound: some 77-100 ft Portland bodies lose the
   56-wide pod to the 36-wide; (o) BUILT 38932a24 -- a zero front
   setback is the code's answer (Portland Table 130-2 "none", Oregon City
   17.35.060.E), never an unknown; the 10 ft fallback never moved the pod,
   it only forgave Portland's 10 ft parking setback for side courts in its
   eight zero-setback zones; now 0 (a missing number also 0, the strict
   end). Same bound as (l).
   Queued behind it, each to bound first: (a) struck 2026-09-27 -- s4's
   width/depth come from `lotdims.dimensions` + `pick`, which already takes
   the narrowest front where the city fixes it and the pair that conforms
   where the applicant chooses (2026-09-11), not `cluster_bearings`; (b)
   Portland 33.266.120.C.1.b: on a corner lot the court must sit behind the
   side-street building line and pave at most 20 % of the side-street
   setback -- the drawn lane is consistent by construction (court inside
   the envelope, a 12-ft lane is ~12 % of the strip), so only "behind the
   building line" is unread; (c) `lowest_class` needs a street classification per edge (s4
   holds none; drawn as `any` and said so at runtime); (d) Fairview
   19.30.050(D)(2)(a) side-yard parking setback -> redirect ledger; (e)
   Gresham 3.0100: the front is fixed where the minimum lot depth is met
   in one direction only (needs depth both ways = (a)).

7. **Green and outdoor space: charge the SHAPE, not just the amount.** (a)
   DONE 2026-09-28 (open-space commit): the screen's open space /
   landscaping checks now read lot - building - pavement (`paper.paved`:
   court, alley back-out, lane/side-street drive/alley-side aisle, counted
   as s6s counts it), `open_space_min_sqft` is read (Portland x18,
   Milwaukie, Multnomah LR7), `OPTIMISTIC_CHECKS` is empty; unknown
   pavement fails what the upper bound proves and otherwise holds the lot
   UNKNOWN (FACT_UNOBSERVED). Paper-lot census: moves possible only in
   Gresham CC/MC (15 % open space), Oregon City C/MUC-1 (15/20 %
   landscaping), Fairview VA (25 %; its paper minimum 3,102 sq ft looks
   odd), GREEN->YELLOW, on lots within a few hundred sq ft of the smallest
   fitting lot. The lane is priced at its shortest legal length. (b) DONE 7bd2d1e4..674208b6 (in full run 0930): Portland 33.110.240's
   12x12 square (10x10 R2.5) measured on the lot's own ground -- lot less
   building, court, lane, paving, front setback, overlay carves; a
   side-fed court paves its whole band; a court beside the building is
   measured where it stands (674208b6). LIVE in run 42: 3,056 Portland
   lots fail on the square alone (green->yellow); whether to chase the
   near misses is HUMAN_TODO 27. Milwaukie's 96 sq ft / 5 ft patio
   encoded (no Milwaukie lot green). Bound on 7,029 Portland R lots: 569
   green -> yellow (mostly pod80 end-on on 50 ft lots), 0 unknown, 0 other
   moves. Open: a side-street court standing as a long side strip stays
   unmeasured. (c) settled -- the amounts are charged since 91f40638;
   left for the county map only: landscaping share on the county map (Happy Valley 20 %,
   Portland RM 15-30 %, Oregon City R-2 15 %, Fairview 20-25 %, Wilsonville
   15 %) -- s6s holds no landscaping reserve. (d) what the leftover is FOR
   (sheds, ADUs, a second pod) is product direction, belongs with item 6's
   "least ground under pavement". Ruled NOT owed: Troutdale 8.120.B.1.b
   (balcony), Oregon City 17.62.057 (multi-family), Wilsonville Villebois
   25 % (communal), Gladstone / Tualatin / West Linn / Clackamas county
   state none.

8. **Pockets + corridors -- leftovers (PROMOTED run 33 2026-09-27, drift
   vs 31: 4,140 moved unknown -> green 4,112 / yellow 28 if signed, all
   rules, 0 unexplained; pocket lots 210 -> 25 still ZONE_POCKET, 174 now
   screened under their `of` layer, red at the use gate).** (a) DONE in code
   e7217598 -- s3 follows FLATS's pocket rulings (Clackamas R-MD ->
   Milwaukie, Happy Valley VR57 -> county, UPAR-10 -> Troutdale LDR-1); s5o
   carves them with both jurisdictions' overlays; export keeps them in
   their home jurisdiction. Rides the next s3->s7 run: expect NOT_MEASURED
   -9 (check by the pocket_of TLIDs; drift skips pocket lots); (b) 25 lots stay ZONE_POCKET:
   Troutdale NSA GGC/GSO and Oregon City `County` read against a map that
   answers no code the of-layer holds; (c) DONE 1ff23bdb -- Map 130-1's
   maximum is 20 ft instead of 10 (33.130.215.C.1), a RELAXATION, hung on
   `civic_corridor_setback_all_streets` (every street line on a stretch);
   0 moves, no screen reads a maximum (HUMAN_TODO 12); (d) DONE fa693288 -- the Map 130-1
   10 ft minimum is per LINE in the envelope: optional field
   `setback_street_off_corridor_ft` (the "Street Lot Line: none" row, six
   commercial zones); a street line read surely OFF every stretch
   (`flats.geom.corridor.off_corridor`) is cut at it, every other keeps 10;
   paper fit / driveway charge keep 10. Next re-screen: 520 corridor lots,
   297 with a line read off; moves only toward green/yellow -- read the
   gains. (d) re-screened in run 39 (promoted 2026-09-29). (e) DONE c9083b88 --
   33.130.215.B.1.b: CM2/CM3/CE/CX street lines take 5 ft, 0 only where
   s4's new `street_across_json` reads every ray across as non-residential
   and the line is off the corridor (`setback_street_across_nonresidential_ft`);
   quadfit CE/CM2/CM3/CX front 0 -> 5. Bound ~60 lots green/unknown ->
   yellow, 0 loosened. NEEDS the next full s4->s7 run (new s4 column).
10. **Two loose ends from the ruling pass.** (a) DONE 4b725b6a -- alias
   rulings can `observes:` a site fact; FLX->VC observes
   `inside_mapped_use_area`; the bridge applies aliases. Moves 0: the one
   FLX lot (1N3E33AB-00500) is dropped by quadfit s3 (zone_not_in_rules);
   to make it count, add a VC/FLX rule to quadfit's rules.yaml. (b) THR is
   one lot (1N2E36DA-02200, the Gresham IGA-162nd pocket) whose code no
   published document defines -- not Gresham 4.0100, not MCC 39; ruled
   `to_read` and worth one question to Gresham planning if it ever
   matters; nothing else owed.
12. **FLATS's own envelope -- loose ends (merged b5303d01, PROMOTED run 18
   2026-09-25).** Run 18 drift 879 moved / 0 unexplained: the old quadfit
   court credit was false on all-front lots and orientation-blind (now
   charged), Wood Village LR rear resolves to 20, Gresham MDR-24 corner
   street side 20. Found reading the losses: an 18-acre Oregon City C lot
   (32E05D 01204, 01211) blew the fit's cell cap and fit nothing -- fixed
   f0418b49 (coarser grid), rides the next batch. Left: (a -- settled
   2026-09-27: Table 8A's R-10 row is 20/20, R-7/R-5 are 15; FLATS holds
   the binding R-10 row and quadfit the loosest on purpose, per its own
   note; FLATS's own envelope charges 20 and RN is RED on use anyway) (b) DONE 09171698 -- a rear line off the alley keeps the ordinary rear, the alley line takes the waiver (the bridge resolves the lot twice); probe on 09-29 s4: 2,710 Portland rows move from quadfit's envelope to FLATS's, area identical on 2,708, 0 colour moves; (c)
   RULED b1d46053 -- Portland's commercial/employment/industrial chapters
   state no alley setback; under 33.910 an alley line is a non-street line
   and 33.130.215.B.2 sets it by the abutted zone; max(side, rear) already
   equals that number. 0 moves; plan districts not searched. (`checks.envelope` was dropped by assign's column list -- fixed
   a883f439, present from the next run.)
13. **Tax code area in the RLIS ingest.** The Gresham tax-impact snapshot
   (`scripts/flats_tax_snapshot.py`, migration 0136) needs each lot's tax
   code area (RLIS `TAXCODE`), which acquire drops because it is not a
   declared field; the script's `taxcodes` step pulls it separately out of
   the quarterly ZIP. Declare `TAXCODE` in the RLIS fields and carry it into
   `facts["assessor"]` so the next snapshot joins on the lot row and the
   county copy and the code areas are guaranteed the same release.
   TIMING TRAP: editing the `rlis_taxlots` registry entry makes the monthly
   probe report `registry_changed` and turns the Lots banner red until a
   new copy is taken -- make the edit as the first step of the November
   RLIS refresh, not before.
14. **Tax impact beyond Gresham.** `flats/config/tax/or/multnomah/2025-26.yaml`
   holds Gresham's eleven code areas only. Another city needs its code
   areas' rates (Multnomah's levy-code-rates PDF, split local option /
   bond / urban renewal as the Gresham file does) and its CPR row; Clackamas
   needs its own rate file and CPR table (a different county publication).
   Pending decision: which city next (the pitch is per-city).
15. **Edgemont (P7) bond-model update -- waiting on Steph's answers.**
    `docs/models/Edgemont_Model_Update_Instructions.md` (another agent's plan:
    60% AMI rent plan for the Portland nonprofit tax exemption, P7 property
    tax, RAMP credit, $500 concession policy, OpEx cuts, asset-mgmt fee, and
    rebuilding the typed-in cash-flow rows on every property tab) was
    reviewed 2026-09-23; the basis `CDC_of_Oregon_Bond_1_-_Investor_Pro_Forma.xlsx`
    is byte-identical to `... (no debt pricing) rev12.xlsx`. Its per-unit
    math re-checks exactly (84 units, 33/31/20, GPR $1,278,984). Open before
    any edit: does the exemption require passing the tax savings to tenants;
    who takes title (nonprofit?); do other properties rely on the same
    exemption; AM fee rate; update the Separate Projects rev12 twin too?;
    bond re-sizing (-$275K to -$435K par at 1.20x). Traps: the Pro Forma
    page recomputes OpEx and revenue itself (section K + per-category rows),
    so a change made only to the P7 roll-up leaves the portfolio pages
    stale; keep P7 units split Studio/1BR/2BR. Deliver as rev13 via Excel COM.
16. **Partial re-screen -- SHIPPED 50a0ecc2 2026-09-25 (runbook §4c).**
   Bridge `--zone "<city>:<zone>"` / `--tlid`; `python -m flats.ingest.splice
   splice|audit`. First use: the two Oregon City farm lots (f0418b49) in
   2 minutes, run 20, drift 4 moved / 0 unexplained, promoted. The NEXT
   splice's `--base` is `/root/bridge_pc_full` on 137 (full run 33,
   2026-09-27; 0 splices since). Full re-screen due
   after 5 partials or 30 days (2026-10-27); run `splice audit` against it
   before promoting -- out-of-scope moves are accepted known unknowns.
   (Showing the audit on /flats/refresh: Steph 2026-09-25 "an enhancement
   for later" -- not queued.)
18. **`GET /api/projects` is not scoped to the caller's organisation.** Any
   signed-in user sees every org's opportunities, filtered only by their
   own hidden list (found by the /api/ auth fix 2026-09-28, which closed
   anonymous and made-up-user access). Scope it to the user's org and add
   a two-org integration test; check the other list routes for the same.
19. **Excel export vs the engine -- four disagreements the parity tests
   found (PR #21/#22, 2026-09-29), none fixed; each needs a ruling.** (a)
   LOAN PAYOFF: the export's levered cash flow counts loan proceeds in at
   purchase but never the payoff at sale, while the engine's leaves loan
   principal out entirely -- export IRR / equity multiple cannot match the
   app on any deal with debt (test deal with debt: year 1 -$511k Excel vs
   -$1.51M engine); the parity deal is all-equity to dodge it. (b) IRR
   TIMING: "Combined Levered IRR" is annual (sale lands ~10 months late)
   while "Combined Unlevered IRR" on the same sheet is the engine's monthly
   figure (10.7% vs 12.5% on the test deal). (c) PRO FORMA mixes bases:
   revenue is stabilized x 12 but vacancy/capex are the engine's actual
   calendar year -- a construction-year deal shows full rent, ~no vacancy.
   (d) the Pro Forma skips the legacy per-deal expense fields (property
   tax, insurance, cost/unit, mgmt fee %) the engine still charges ($8.6k
   vs $75k on the standard test deal). Also docs/FINANCIAL_MODEL.md's EGI /
   year-0 revenue entries describe what the code no longer writes. (a) and
   (d) look like export bugs; (b) and (c) are presentation choices for
   Steph. Exporter = app/exporters/investor_export.py (not the engine).

17. **Washington County: drafts reviewed; publish, then the county map.**
   Steph 2026-09-29 (evening) answered HUMAN_TODO 25: A NO second cloud
   round -- Tigard, Cornelius and the 11 community plans are done LOCALLY
   (usage reset, 'go hard on data processing'); B design rules are catalogued
   and encoded (item 20); C the 19 city questions printed for Steph to send;
   D HB 2138 read (enrolled text): North Plains owes duplexes only, Banks and
   Gaston nothing -- they stay out. Agent work, in order:
   (a) PUBLISHED 2026-09-29: 0e45ffd5 on main, deployed (smoke PASS), CI
   green (light + full gate); flats 3,861 + quadfit 347 passed locally.
   886 numbers re-read blind, none wrong (handoff "Local review"). The
   worktree ../vicinitideals-worktrees/washington-draft stays for (b).
   (b) DONE b53873cf 2026-09-30 (handoff §6 "Rulings, 2026-09-30"):
   private_drives street:true in all six layers; Sherwood driveway share
   (driveway_max_frontage_pct); Durham walk (driveway_walkway_ft) and rear
   15; King City impervious cap (max_impervious_pct); city questions 6-19
   settled by the reading rules. Left for the cities (HUMAN_TODO 25C):
   Sherwood PD plans + Old Town zones, King City NMU patch, Durham MDR.
   (b2) MEASURE TWO EXPRESS EXCEPTIONS the screen holds against the pod
   today: Hillsboro SCC-SC min height 30 ft only within 800 ft of a light-rail
   station (none beyond) and MU-VTC 3 stories only inside the Center Cores
   (12.65.030 map; 2 outside). Needs a distance-to-LRT-station fact (TriMet
   stops in RLIS; also serves county TO:BUS 20 ft within 1,300 ft and SCR-V
   / SCR-OTC rows) and the Center Core polygons.
   (c) FOREST GROVE (7,756 lots): American Legal 403s from home too. Try the
   scrapling stealthy browser; if refused, ask Steph to save the PDFs.
   (d) COUNTY MAP on 137: COUNTY W into s0 KEEP_COUNTIES; zoning from the
   county's LUD layer + city layers (King City layer 4 = Kingston Terrace);
   overlays incl. Clean Water Services; send Tualatin/Portland/Wilsonville/
   Lake Oswego/Rivergrove's Washington lots to their existing layers (by
   JURIS_CITY, never SITECITY); regenerate the coverage ledger and empty
   OWED_A_COUNTY; bridge, drift, promote.
   (e) AFTER THE FIRST SCREEN, count what these cost: Beaverton/King City
   minimum density on big lots (fail vs closer look: bring Steph the
   number); the bigger next-to-a-named-zone setback (Hillsboro SCR-DNC,
   Beaverton downtown); Hillsboro's corner coverage bonus + two corner
   setbacks (test_corner_variants: measure before deferring again).
   (f) LOCAL, no cloud (25A answered no): store Tigard
   (ecode360.com/43691505) and Cornelius (ecode360.com/CO4396), draft both
   layers here with the same blind re-read; read the county's 11 community
   plans (Aloha, Bethany, Cedar Mill, ...) into the county layer as
   neighbourhood variants. Worktree per city, confirm with Steph first.
   (g) JAN 1 2027 (HB 2138 sec. 4): every Metro city must re-conform its
   middle-housing code (cottage clusters by 2028); a city that misses it
   gets the state model code directly. Run the drift check on every layer
   in early 2027 -- expect amendments across the board.
20. **Design-standards catalog (Steph 2026-09-29, HUMAN_TODO 25B).** Record
   and encode every rule about how the building LOOKS -- front windows
   share, entry facing the street, garage placement and width, siding and
   roof materials, articulation/offsets, eaves, porch, height transitions --
   systematically across every encoded jurisdiction (Multnomah, Clackamas,
   Washington), not just North Bethany. The pod's own design data does not
   exist yet, so screening stays held back; the deliverable is a catalog an
   ARCHITECT can design the pod against: per rule the citation, quote, the
   zones and lots it reaches, and whether it is a menu or a must. Start by
   harvesting the design-standards chapters the ledgers already point at
   (crossrefs.py/triage.py name several, e.g. Gresham 7.0420, ZDO 1005,
   Fairview VA menu). HB 2138 asks LCDC to strip design standards that
   'prevent or discourage' housing by 2028 -- the catalog is also the
   baseline to see what that removes. Plan first; ask Steph before a worktree.
21. **Post-2027 world (Steph 2026-09-29: "design the system for a post-2027
   world... retroactively apply that throughout our corpus").** Sources
   STORED 2026-09-30 (declared in `_state.yaml`, cited by nothing yet):
   `or/hb.2138.2025.txt` (enrolled); `or/oar.660-046.adopted-2026-08.txt`
   (Division 46 AS ADOPTED 2026-08-27, DLCD's copy; OARD's filed text LCDD
   11-2026 is WRONG, correction hearing 2026-10-22 -- re-fetch after);
   `or/oar.660-047.draft-v5.txt` (Oregon Homes draft v5, 2026-09-22; re-fetch
   after LCDC's October meeting). Worktree, confirm with Steph first. In order:
   (a) STATE LAYER TO ADOPTED DIV 46: quadplex min lot <= the zone's
   detached-house min lot (0220(2)(a)(B)), townhouse likewise (0220(3)(a)) --
   needs a per-zone detached-house minimum lot field read from every zone
   table and a preemption shape "cap at another field's value"; "zoned for
   residential use" (ORS 197A.420(1)(j)) as the scope limit the state layer
   has flagged NOT ENCODED since August; 0205(3) percentage option deleted --
   check whether any corpus city used it. Height floor (2)(d) unchanged; see
   the 2026-09-29 note in _state.yaml (SCR-OTC 20 ft not lifted).
   (b) OUT-OF-COMPLIANCE ZONES: residential zones that allow a detached house
   but refuse a quadplex (King City's older zones first). AUDITED for
   Multnomah + Clackamas 2026-09-30 (read-only; `quadplex_allowed: false`
   is the use gate, flats/score/screen.py ~L1320): 14 clear hits --
   Portland RF; Multnomah uninc RF, LR5, LR7, LR10, UF20; Gresham LDR/GB;
   Wilsonville RN (Frog Pond) and FDAHR; Happy Valley FU10; Clackamas
   uninc FU10 (693 lots), RRFF5 (2,082), RA2 (491), RA1 (329). Traps:
   Clackamas FU10's note leans on an "interim zoning" exemption
   (0010(2)(c)) that the ADOPTED text no longer has; RRFF5/RA1/RA2 hinge
   on ORS 197A.015 "urban unincorporated lands" (not stored); Gresham
   LDR/GB may take a Goal 7 hazard carve-out; Wilsonville RN may take the
   master-planned-community clause 0205(2)(b). Ambiguous 9: Clackamas FF10;
   Multnomah MUA20, RR, OR, GGR2 (mostly outside the UGB); Fairview VTH;
   Portland RMP; Milwaukie R-MD (unit-lot + flag variant); Wilsonville
   FDAHV. Happy Valley's child-lot refusals look allowed by the state rule. From 2027-01-01 the
   Div 46 model code applies directly (0040(4), "completely replaces"): audit
   the corpus, switch them to allowed under the city's middle-housing
   standards or the model code (2020 Exhibit B: front/rear setbacks > 10 ft
   invalid, height < 35 ft / 3 stories invalid, coverage limits invalid).
   (c) OREGON HOMES PATH (HB 2258, OAR 660-047, DRAFT until LCDC's October
   2026 meeting): lots 1,500-20,000 sq ft, residential zone, slope <= 15%,
   outside mapped resource/hazard areas, vacant (teardown < 5 years only with
   DCBS-approved plans); ministerial; 5 ft setbacks, no height cap, parking
   none/<=1 per unit, garage/parking <= 50% frontage, 15% outdoor area, 10%
   slack, min density still applies, <= 2,200 sq ft a unit. A second screen
   path beside the zone path once adopted. Steph's side: HUMAN_TODO 26.
   (d) ELECTIVE LEVERS, recorded not screened: bonus units (+2 on a quadplex
   with one Type A accessible or <=120% AMI for-sale unit; they stay middle
   housing, ORS 197A.420(1)(e)(B); commensurate floor area/height/density, not
   setbacks); keeping an existing house (197A.420(4)); covenants banning
   middle housing void 2027-01-01 (ORS 93.277, 94.776); no traffic study or
   traffic exaction for <= 12 units (197A.420(6)).
   (e) WATCH: Housing Choices rulemaking (HB 2138 §22: siting/design of
   prefabricated middle housing; RAC 1 on 2026-10-07, adoption ~2027-12-02)
   -- item 20's catalog is the baseline; January 2027 drift run (17g).
22. **Portland aisle 20 ft -- DONE (bacea669 + quadfit mirror 0df02fcc;
   run 44 PROMOTED 2026-09-30, splice base 137 /root/bridge_spliced_aisle0930).**
   Drift 42 -> 44: 7,633 moved, all rules, 0 unexplained -- Portland
   yellow->green 7,358 (7,001 on the fit alone), yellow->unknown 273
   (Portland 231, West Linn 42: the fit now passes, an unmeasured fact
   decides), green->yellow 2 (1S1E06AD -02100 pod80, 1S1E13DC -04000
   pod56): replayed -- the narrower court is drawn 0.1 / 0.7 ft past the
   beside-court reach tolerance (`BESIDE_REACH_TOL_FT` 3 ft, cef95109) and
   falls back to the row behind; knife-edge, conservative, accepted.
   **Milwaukie, pending Steph:** the ecode360 link Steph sent
   (guid 43863200) is 19.606.1, Table 19.606.1 -- 90 deg: 9 x 18 stall, 22 ft
   aisle -- which we already hold; 19.606's purpose sentence excepts middle
   housing, so it is refused today (milwaukie.yaml ~L948) and the court is
   drawn at 24. Asked: adopt 22 as Portland's 20 was adopted? Wilsonville's
   planning email (HUMAN_TODO 3) still open.
