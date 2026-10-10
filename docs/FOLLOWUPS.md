# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1 -- EXCEPT item 48 (scan
resilience), which Steph put AHEAD of the rest on 2026-10-07.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

Each item carries `[scan: ...]`: YES = the work changes lot answers, so a
before/after scan on 137 must be read before it ships; NO = tests are enough;
"NO new code, check after the weekly run" = already deployed, its moves are
read when the weekly full re-screen lands.

1. [scan: NO] **The county map copy: loose ends after the first promotion (HUMAN_TODO
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
2. [scan: YES] **Neighbour zoning per lot line -- loose ends after the measurement
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
3. [scan: YES for the court placement; NO for the lot-page note] **Alley leftovers (rear alley caad6f3f run 24; side alleys + the
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
4. [scan: YES] **Four places the screen and the county map disagree, found by the
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
5. [scan: YES, small sample (drawings move, colours must not)] **Draw what the screen fitted -- DONE (666c6837, full run 31 PROMOTED
   2026-09-27; new splice base 137 /root/bridge_draw_full, 0 splices).**
   Leftovers: the drawing keeps the verdict's angle, so on a wide shallow
   lot the plan can run along the street; a side-alley column is drawn as
   a row behind the building.
6. [scan: YES] **Where parking may SIT, and which street is "the front".** Offered
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

7. [scan: YES] **Green and outdoor space: charge the SHAPE, not just the amount.** (a)
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

8. [scan: NO new code, check after the weekly run; YES if (b) is taken up] **Pockets + corridors -- leftovers (PROMOTED run 33 2026-09-27, drift
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
10. [scan: YES for (a), one lot; NO for (b)] **Two loose ends from the ruling pass.** (a) DONE 4b725b6a -- alias
   rulings can `observes:` a site fact; FLX->VC observes
   `inside_mapped_use_area`; the bridge applies aliases. Moves 0: the one
   FLX lot (1N3E33AB-00500) is dropped by quadfit s3 (zone_not_in_rules);
   to make it count, add a VC/FLX rule to quadfit's rules.yaml. (b) THR is
   one lot (1N2E36DA-02200, the Gresham IGA-162nd pocket) whose code no
   published document defines -- not Gresham 4.0100, not MCC 39; ruled
   `to_read` and worth one question to Gresham planning if it ever
   matters; nothing else owed.
12. [scan: NO -- nothing open; the weekly run carries f0418b49] **FLATS's own envelope -- loose ends (merged b5303d01, PROMOTED run 18
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
13. [scan: NO -- lands with the November county data refresh] **Tax code area in the RLIS ingest.** The Gresham tax-impact snapshot
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
14. [scan: NO] **Tax impact beyond Gresham.** `flats/config/tax/or/multnomah/2025-26.yaml`
   holds Gresham's eleven code areas only. Another city needs its code
   areas' rates (Multnomah's levy-code-rates PDF, split local option /
   bond / urban renewal as the Gresham file does) and its CPR row; Clackamas
   needs its own rate file and CPR table (a different county publication).
   Pending decision: which city next (the pitch is per-city).
15. [scan: NO] **Edgemont (P7) bond-model update -- waiting on Steph's answers.**
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
16. [scan: NO] **Partial re-screen -- SHIPPED 50a0ecc2 2026-09-25 (runbook §4c).**
   Bridge `--zone "<city>:<zone>"` / `--tlid`; `python -m flats.ingest.splice
   splice|audit`. First use: the two Oregon City farm lots (f0418b49) in
   2 minutes, run 20, drift 4 moved / 0 unexplained, promoted. The NEXT
   splice's `--base` is `/root/bridge_pc_full` on 137 (full run 33,
   2026-09-27; 0 splices since). Full re-screen due
   after 5 partials or 30 days (2026-10-27); run `splice audit` against it
   before promoting -- out-of-scope moves are accepted known unknowns.
   (Showing the audit on /flats/refresh: Steph 2026-09-25 "an enhancement
   for later" -- not queued.)
18. [scan: NO] **`GET /api/projects` is not scoped to the caller's organisation.** Any
   signed-in user sees every org's opportunities, filtered only by their
   own hidden list (found by the /api/ auth fix 2026-09-28, which closed
   anonymous and made-up-user access). Scope it to the user's org and add
   a two-org integration test; check the other list routes for the same.
19. [scan: NO] **Excel export vs the engine -- four disagreements the parity tests
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

17. [scan: YES] **Washington County: drafts reviewed; publish, then the county map.**
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
   (b2) TRANSIT DISTANCE BUILT ceb6693d 2026-09-30 (Steph: "build it for
   all", measure once, re-measure only when stops change): every lot gets
   its distance to a rail stop, a MAX station, any stop and a Frequent
   Service line (flats/geom/transit.py, flats/ingest/transit.py, runbook
   §4d); the probe flags new_release when TriMet edits a layer. Banded on
   it: Hillsboro SCC-SC min height + SCC-SC/SCR-DNC/SCR-V densities,
   Beaverton SC 400 ft density. (1) DONE 2026-09-30: measured on 137
   (data/flats/transit/2026-09-30, version 6d3a528e4091692b, 400,032 lots)
   and re-exported as run 48 (0 moves, PROMOTED) -- every lot page shows
   it; every later bridge run passes --transit (Washington lots too once
   (d) lands -- without it those station zones screen unknown); (2) COUNTED 2026-09-30 in PostGIS on 114
   (run 44, best design per lot, station points, no slack): 213,006 of
   400,032 lots lie within 3/4 mi of rail or 1/2 mi of a TriMet frequent
   line (35,518 green / 156,257 yellow / 9,410 red / 11,821 unknown;
   Portland 170,645 of 194,056). Steph 2026-09-30: "SHOW IT, DON'T SCREEN
   IT" -- the lot page shows the distances and the reform's reach
   (facts.transit, export --transit / meta); the pod keeps 4 stalls. The
   state reform (OAR 660-012-0440) stays NOT ENCODED in or/_state.yaml.
   (3) CLOSED 2026-09-30: the
   MU-VTC Center Cores have no drawn boundary (Figure 12.65.930-A only
   "illustrates"; the city's open data holds 2020 gallery symbols, not the
   cores), so 3 stories stays held on every MU-VTC lot (hillsboro.yaml). Not in the layers: SMART, CAT,
   SAM, SCTD (reads as far from transit -- conservative for relief).
   (c) FOREST GROVE (7,756 lots): REFUSED 2026-09-30 -- curl gets only the
   script shell; a local headless browser got the contents page once, then
   a Cloudflare Turnstile on every chapter (not to be bypassed); the
   scrapling MCP's proxy is down. Asked Steph to save the six articles as
   PDFs (HUMAN_TODO 28); store them from the files, then rulebook 1-14.
   (d) STARTED 2026-09-30 (Steph: "start it"), worktree
   ../vicinitideals-worktrees/washington-map, branch flats/washington-map.
   COUNTY MAP on 137: COUNTY W into s0 KEEP_COUNTIES; zoning from the
   county's LUD layer + city layers (King City layer 4 = Kingston Terrace);
   overlays incl. Clean Water Services; send Tualatin/Portland/Wilsonville/
   Lake Oswego/Rivergrove's Washington lots to their existing layers (by
   JURIS_CITY, never SITECITY); regenerate the coverage ledger and empty
   OWED_A_COUNTY; bridge, drift, promote.
   MERGED ef08aebc + deployed; snapshot 4 (2026-10-01) loaded as CANDIDATE
   RUN 51 (590,282 lots; Washington 190,250: best-pod if-signed green
   18,891 / yellow 100,888 / red 8,644 / unknown 61,827). Drift vs run 49:
   2 moved (sewer district), 0 unexplained. Gate WARNED (count_drift,
   lots_drift = the new county) -> ASKED Steph to promote. Unruled codes
   (warn only): Tualatin's Washington side BCE CC CN CR IN MBP MP MUC RH
   RH/HR (~420 lots) and Wilsonville PDI-RSIA/PFC (17) -- RULED 2026-10-01
   (8 refusal blocks; RH, RH/HR, MUC, CC to_read). STEPH RULED 2026-10-02:
   PDI-RSIA 10% is per project site but the refusal stands ("this lot
   doesn't work for us"); RH/HR townhouse lot = the 10,000 sq ft fallback;
   RH/RH-HR/MUC stay unit-lot townhouses only (Quadplex is its own TDC
   31.060 type, absent from their tables; Comp Plan Policy 3.2.1 is policy,
   not permission). CC ENCODED 2026-10-02: Map 10-3 traced onto TualGIS
   taxlots (flats/config/areas/.../residential-sub-district.geojson, new
   `drawn_areas` layer block + flats/geom/drawn.py); 155 CC lots, 91 inside
   (quadplex permitted, 16-25 du/ac), 64 outside (refused), 0 cut. LANDS AT
   THE NEXT FULL RE-SCREEN (no partial). Still open: Tualatin CO refusal may
   miss the Ch. 58 townhouse path (58.400, Table 58-4, Block 1); RML lots now exist on the Washington side. 08 splices LR10/FU10/sewer + fire reach on
   /root/bridge_2026-10-01_wash AFTER promotion (message it then).
   (e) AFTER THE FIRST SCREEN, count what these cost. FIRST COUNTS (run 51):
   Beaverton has 0 green -- `utility_easement` unmeasured holds ~32,100
   answers (BDC 20.05 note 7 / 20.22 note 7 "In no case shall a building
   encroach into a Public Utility Easement"; footnotes beaverton.yaml caps
   MR/RMA/RMB/RMC/CM-MR/CM-RM). ~6,650 Beaverton lots fail nothing else;
   Oregon City's same note holds ~3,700 more. Steph 2026-10-01 pointed at
   Survey Explorer's Dedication layer (gispub.co.washington.or.us/server/
   rest/services/LUT_ETS/Survey_Explorer/MapServer/15): 8,412 recorded
   dedication deeds 1978-2026 as MARKER points (28,541), no width, no
   type field -- mostly street right-of-way deeds; plat PUEs are NOT in it
   (plats are layer 4 polygons + scanned TIFFs). Steph's test "no point
   within ~3 ft of a lot line of an otherwise-green lot = clear": of 6,481
   such Beaverton lots, 476 touched, 6,005 clear (10 ft 517; 25 ft 657;
   inside the lot 384). Script /root/e1.py on 137, points cached
   /root/wash_dedications.json. Steph then DROPPED the dedication data:
   rule = building fits with a 10 ft yard on every STREET line (Steph:
   "just the side on a street") -> green; fits at 5 ft but not 10 ->
   yellow; not even at 5 -> red. What-if on 137 (/root/pue_driver.py,
   PUE_FT floors the street yards; /root/pue_chain.sh, E10 then E5 on
   what E10 lost). RESULT 2026-10-01 (what-if only, nothing built): the
   6,481 were NOT otherwise green -- the cap masked a second hold, net
   area (`measured_on: net_developable_area`, nothing surveys it). At 10
   ft: 6,305 fit (one design lost on ~2,800, the other fits), 176 red on
   fire reach (still red at 5 ft; route median 216 ft), 0 needed 5 ft.
   Net-area holds on the 6,305: max FAR (RMA 1.6 / RMB 1.2 / RMC 0.9) is
   passed even after losing 30% of the lot on ALL 6,305 (50% on 4,918);
   min density (17/10/7 per net acre) settled on 5,395, unsettled on 910
   big lots (RMA 299, RMB 321, RMC 290). ASKED Steph: (1) treat FAR as
   passed when it survives a 1/3 deduction? (2) the 910: red or closer
   look? If both yes: ~5,395 green / 910 per (2) / 176 red.
   Hillsboro 25 green -- `flag_lot` assumed on 48,650 answers (the
   same assumption holds 12,668 in Clackamas). Also: Beaverton/King City
   minimum density on big lots (fail vs closer look: bring Steph the
   number); the bigger next-to-a-named-zone setback (Hillsboro SCR-DNC,
   Beaverton downtown); Hillsboro's corner coverage bonus + two corner
   setbacks (test_corner_variants: measure before deferring again).
   (f) LOCAL, no cloud (25A answered no): store Tigard
   (ecode360.com/43691505) and Cornelius (ecode360.com/CO4396), draft both
   layers here with the same blind re-read; read the county's 11 community
   plans (Aloha, Bethany, Cedar Mill, ...) into the county layer as
   neighbourhood variants. Worktree per city, confirm with Steph first.
   STARTED 2026-10-01 (Steph: "both, in parallel"): worktrees
   ../vicinitideals-worktrees/flats-tigard (flats/tigard-draft) and
   flats-cornelius (flats/cornelius-draft), rules + documents + blind
   re-read only; map wiring after flats/washington-map merges. eCode360
   serves the real page to a browser User-Agent (no challenge solved).
   Both drafts DONE 2026-10-01 (Cornelius 1681a829: 12 zones, 4 admit;
   Tigard d5f53149: 13 zones, 9 admit; both full suites green, blind
   re-read 0 wrong). Steph 2026-10-01: Cornelius R-7 one-home line is
   superseded (keep); charge parking out of side/rear yards + Tigard's
   5 ft screen (being built on flats/cornelius-draft); Tigard's per-home
   lot cap follows Tigard's townhome definition (if unit lots, no parent
   cap); TRACE the Tigard sub-area image maps (18.650.A/18.660.A/18.670.A,
   ~590 acres MUR/MUC/MU-CBD) LATER -- until then those lots stay review.
   Remaining questions: handoff §6 Tigard + Cornelius. Merge both after
   flats/washington-map lands, then wire Tigard/Cornelius into the map
   (JURIS_CITY -> layer, Metro ZONE; Cornelius R-10 parcel by hand).
   Rulings round 2 (all Steph 2026-10-01, applied on the two branches):
   Tigard Triangle ground floor >= 12 ft (pod fact), MUR stricter column,
   MUC blank cells = no limit, Triangle 10 ft one-lane drive OK; Cornelius
   fourplex NOT multi-family, 9 ft stall, CR standalone only near
   Adair/Baseline, sun shading = flag every R-7/R-10 lot, GMU townhome
   path REVIEW (subdistrict figure traced later), corner front = narrower
   side, pod has NO covered parking. Both drafts finished the round
   (Cornelius 5bf6e848, Tigard 266053fa, suites green, not pushed). The
   Adair/Baseline standalone-fourplex rule is CC, not CR as asked (the
   substance ruled stands). OPEN: sun shading as built makes every R-7/R-10
   lot (about half of Cornelius) never-GREEN "needs a closer look", not the
   note-only flag Steph was told. Steph 2026-10-01: GREEN WITH A WARNING
   (lot-page shading flag, verdict not held); being reworked on the branch. Merge Cornelius first (it adds
   parking_required_yard_prohibited / behind_wall_ft), then Tigard
   reuses it for its 5 ft planted parking strip (RES-A/B/C).
   The split-path double count the Tigard draft found in Hillsboro
   (R-8.5 asked 24,000 sq ft, should be 6,000) was every `per_dwelling`
   variant on `unit_lots` (24 in the corpus, Gladstone/Happy Valley/West
   Linn too): FIXED in the reader (Effective/Resolved.whole_project), not
   the files; nothing screens the split path yet, so no verdict moved.
   MERGED with flats/washington-map on flats/tigard-draft 2026-10-01
   (layers 27, zones 455): TIGARD and CORNELIUS now route by JURIS_CITY to
   their layers; the next Washington re-screen shows whether every lot
   finds its zone (Cornelius R-10 by hand still owed).
   (g) JAN 1 2027 (HB 2138 sec. 4): every Metro city must re-conform its
   middle-housing code (cottage clusters by 2028); a city that misses it
   gets the state model code directly. Run the drift check on every layer
   in early 2027 -- expect amendments across the board.
20. [scan: NO -- a catalog; nothing screens it yet] **Design-standards catalog (Steph 2026-09-29, HUMAN_TODO 25B).** Record
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
21. [scan: YES for (a)-(c); NO for (d)-(e)] **Post-2027 world (Steph 2026-09-29: "design the system for a post-2027
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
   FDAHV. Happy Valley's child-lot refusals look allowed by the state rule.
   DECIDED A 2026-09-30 (Steph: "the 'larger cities' is important"). Size
   cutoff: inside Metro every city over 1,000 people (all ours but Johnson
   City, Rivergrove, Maywood Park); outside Metro 25,000+ for every type,
   2,500-25,000 duplexes only; county land only where "urban
   unincorporated" (ORS 197A.015(12): UGB, urban zoning, sewer district,
   water provider, not a holding zone). BUILT (relief `state_middle_housing`,
   discretionary, never GREEN; the use gate now reads a zone's OWN relief
   exceptions -- which also opens LR7's conditional use, Multnomah OR/RR
   planned development and LR5's corner/flag conditional use; a path that
   turns on an unmeasured fact is UNKNOWN, not RED). OPENED 5: Portland RF
   (min lot 52,000 = the house's, Table 610-2), Multnomah uninc RF, LR5,
   LR10, Happy Valley FU10. REFUSED 8: Multnomah UF20 + Clackamas FU10
   (holding zones, (12)(e)); RRFF5/RA1/RA2 (rural, (12)(b)); Gresham LDR/GB
   (Goal 7 hazard, 0010(3)(c)); Wilsonville RN + FDAHR (pre-2021 master
   plan, 0205(2)(b)(B)). LEFT: Multnomah county lots need
   `in_sewer_district` measured (only Clackamas has it) -- UNKNOWN till
   then; LR10 + Happy Valley FU10 dimensions not encoded (the state caps
   them at the house's; notes list LR10's); Wilsonville RN as townhouses
   CHECKED 2026-10-01: shut (two attached, three on a corner, during
   Frog Pond West's initial development; every RN lot is West -- East/South
   are not in the city's zoning yet; RN zone note). RUN 46 PROMOTED
   2026-09-30 (9096f164, scope 137 /root/mh_scope.txt, splice base now
   /root/bridge_spliced_mh0930): drift 44 -> 46 316 moved / 0 unexplained,
   all LR7 red->yellow if signed (its conditional use, read at last). The
   opened zones' own lots moved red-if-signed -> "not measured": quadfit's
   s3 filter drops a zone it thinks refuses the pod, so Portland RF (634),
   Multnomah RF (225), LR10 (15) and Happy Valley FU10 (12) have no
   measurement to screen. MEASURED 2026-10-01, RUN 49 PROMOTED (d5e42388
   rules.yaml opens Portland RF + county RF + LR5 at needs_verification;
   cd746111 lets a splice take measurement files that only ADD its own
   lots): quadfit tree 137 data/quadfit_2026-09-30mh, bound 0 lost / 0
   changed / 851 gained (Portland RF 626, county RF 224, LR5 1); splice
   base now 137 /root/bridge_spliced_mhq0930; drift 48->49 0 moved. Portland
   RF: 1,252 answers yellow-if-signed (use by the state path; under 52,000
   sq ft the lot size miss rides the ASSUMED variance, RELIEF_UNCONFIRMED,
   as every unread adjustment chapter does), 16 too narrow. County RF/LR5
   stay unknown until `in_sewer_district` is measured in Multnomah. LR10 +
   Happy Valley FU10 still unmeasured (no dimensions encoded). A FULL
   re-screen is now due (5 splices since full0930). 2026-10-01 CODED, NOT
   YET SCREENED: LR10 (MCC 39.4878; min lot = the house's 10,000) and Happy
   Valley FU10 (Table 16.22.010-2, 10 acres) dimensions in the corpus and
   quadfit rules/footprints; the bridge now answers `in_sewer_district` on
   unincorporated Multnomah (`DISTRICT_ONLY`, from the district layer quadfit
   already reads). The county assessor's tax districts list only
   Dunthorpe-Riverdale and Clean Water Services as sewer districts in the
   county, and no RF/LR5/LR10 lot is inside either -- so those lots go
   UNKNOWN -> refused (red) on the next screen: not "urban unincorporated"
   under ORS 197A.015(12)(c). SCREEN PLAN (agreed with the washington-map
   session 2026-10-01): its three-county candidate (137 /root/chain_wash.sh,
   snapshot 2026-10-01, bridge ETA ~13:00-14:00 UTC) is the full re-screen
   Steph asked for; Steph promotes it by hand (lots_drift warns); then a §4c
   partial on that copy -- quadfit s3-s7 in a COPY tree
   data/quadfit_2026-10-01_mh, scope = new LR10/FU10 lots + every
   unincorporated Multnomah lot, splice onto /root/bridge_2026-10-01_wash. From 2027-01-01 the
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
22. [scan: YES if Steph adopts Milwaukie's 22 ft aisle] **Portland aisle 20 ft -- DONE (bacea669 + quadfit mirror 0df02fcc;
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
23. [scan: NO] **Page check -- SHIPPED 2026-09-30 (a203e9f1).** `/flats/check`: the
   printed page with a box on the number, signed numbers first, then one card
   per footnote on it; "no" answers form the problems list
   (`/flats/check/problems.txt`, stamps `bundled_at`). Page maps now cover
   190 PDF documents; 1,742 of 2,129 numbers get a box (362 get their line
   highlighted, 25 nothing). Still open: (a) web-published codes (Happy
   Valley, Lake Oswego, Clackamas ZDO, Fairview, Wood Village, ~1,100
   numbers) have no printed page -- draw them from the stored HTML snapshot
   instead; (b) nothing reads the problems list yet -- wire a "differs" into
   the signing disputes so the number reopens there; (c) Gresham
   4.1400.pleasant-valley's page map no longer matches its source -- re-fetch
   then re-map.
24. [scan: YES] **Oregon City 16.12.035.F -- one driveway approach per two townhouses
   (Steph 2026-09-30, from the page check).** "Townhouses shall have one
   driveway approach for every two dwelling units (round up ...)". Not
   encoded and not among the file's NOT ENCODED notes (E.1, the middle
   housing "may be allowed one per two units", is). Read as a requirement it
   asks two approaches for the four-unit pod on unit lots, where the plan
   draws one shared drive; read as a cap it never binds. RULED by Steph
   2026-09-30 (page-check flag #1): a REQUIREMENT -- two separate approaches
   for the pod; "I don't think we're counting for anything more than 1".
   Next: a field for approaches required per N townhouses + the site plan
   drawing (and charging frontage for) a second approach; check which other
   cities state the same rule before building it for one.
   BUILT 2026-10-10 on flats/oc-two-approaches (aa1dff63 + ac827c09, needs a rebase), NOT
   MERGED: optional driveway_units_per_approach = 2, Oregon City only; a lot needing two is
   YELLOW (DRIVEWAY-SECOND-APPROACH, sev 5) until item 25 can prove a second approach fits.
   BOUND (OC 11,944 lots): 2,197 greens -> yellow (nearly every OC green), 0 gained, no red
   moves. OFFERED TO STEPH 2026-10-10: merge before the weekly (OC greens go yellow until
   item 25) or hold; and whether to start item 25 (a major build, on hold by Steph).
   STEPH 2026-10-10: (A), then asked whether state law overrides the rule. MERGE HELD. Coordinator
   reading (stored text): OAR 660-046-0020(4) counts DRIVEWAYS as a design standard;
   660-046-0225(1)(c): a Large City (OC is in Metro) may apply only Model Code standards, less
   restrictive ones, or the SAME as detached houses, and "design standards may not scale by the
   number of dwelling units"; 660-046-0220(2)(e)(E) and (3)(f)(C): the SAME access standards as
   detached houses (OC 16.12.035.D.1: a house on one local frontage gets exactly one driveway).
   OC's own 17.16.040.B.3 (rear-parked townhouses, no corner lot) says "consolidate access for all
   lots into a single driveway"; B.2 corner lot: a single driveway on the side. So F likely cannot
   demand a second approach for the pod. NOT YET READ: the Large Cities Model Code itself
   (660-046-0010(4)(b), not in the store) -- if it states a per-unit approach ratio, OC may apply
   it. AGENT INSTRUCTIONS GIVEN 2026-10-10 ("driveway-state-law"): fetch the Model Code, settle it,
   sweep every encoded city for any driveway/curb-cut per-unit ratio, report before encoding.
   RULED 2026-10-10 (driveway-state-law, branch flats/driveway-state-law): (i) STATE LAW
   OVERRIDES F. Large Cities Model Code (Exhibit B, stored) has NO per-unit minimum: townhouse
   "maximum of one (1) driveway approach ... for every townhouse", no corner lot "consolidate
   access for all lots into a single driveway". 0225(1)(c) + 0220(3)(f)(C) bar F as requirement
   or cap. HB 2138 s.22 strengthens, not weakens. No 0235 alternative-standards filing found
   for OC Ord. 22-1001 (reopen if one turns up). Recorded as NOT ENCODED/overridden in
   oregon-city.yaml; no colour moves (the pod keeps one approach). Sweep: no other encoded city
   states a per-unit approach MINIMUM; Hillsboro/Tigard cap "one per two units" (never binds a
   one-approach pod). DURHAM 7.12.9 pairing = an option for front drives, the pod uses Option 2 (rear
   court): nothing to encode. CORNELIUS (R-7/R-10/A-2/CR/GMU) "not more than two lots may be served by
   one shared driveway" is NOT state-overridden (it binds detached lots too) and would need a 2nd
   approach on the unit-lots plat; not encoded (no field, item 25 held); run 70 Cornelius = 0 green,
   so no colour moves. REOPEN when Cornelius is signed or item 25 is built. Do NOT merge flats/oc-two-approaches; Steph to confirm, then delete it. Item 25
   no longer needs a second approach for item 24.
   AGENT INSTRUCTIONS GIVEN 2026-10-10 ("oc-two-approaches"; reach first,
   bound + read every move, lands at the weekly; stop and ask if it needs
   item 25's approach geometry).
   STEPH 2026-10-10: ENCODE the city rule anyway, with the state override on top, so a
   pre-emption filing by OC or a change in state law flips it back by deleting one override.
   AGENT INSTRUCTIONS GIVEN 2026-10-10 ("oc-driveway-preempt"): reuse the field/flag/screen code
   from flats/oc-two-approaches, OC value 2 cited to F, a _state.yaml preempts entry cited to
   OAR 660-046-0225(1)(c) + the stored Model Code; expected moves ZERO, proven by an OC bound.
25. [scan: YES, when built (on hold)] **Driveway approach geometry, ahead of a second approach (Steph
   2026-09-30, flag only -- do not build yet).** What is measured today: the
   drive lane's width (`driveway_min_width_one_way_ft` / `_two_way_ft`, read
   by `flats/score/paper.py`) and the driveway's share of frontage
   (`driveway_max_frontage_pct`, `flats/score/screen.py`). What is encoded
   but read by NOTHING: the approach (curb cut) width,
   `driveway_approach_min_width_ft` / `_max_width_ft`, filled in 14
   jurisdiction files. Not encoded at all: spacing between approaches and
   from the corner (Oregon City Table 16.12.035.A, refused as NOT ENCODED),
   the 5 ft offset from the property line (OC note 2, a known live gap), and
   any "combine approaches"/one-per-frontage limits (OC 16.12.035.D: one per
   local frontage, never more than two). Once item 24 makes the pod draw two
   approaches, all of these start to bind together: per-approach width,
   spacing between them, offset from lot lines, count per frontage.
26. [scan: NO] **Page check: whole-document read-through (Steph 2026-10-01).**
   Finding an untinted rule is a different task from checking a tinted
   number; the existing card flow stays as it is for the second (Steph: no
   fly-through changes). Build a read-through: every page of a document in
   one scroll with headings visible for context, encoded rules tinted, arrow
   keys between pages, a comment box that knows which page is on screen
   (and/or drag a box on the page to mark what is missing), held as a draft
   and submitted once at the end of the document; a per-document "read by a
   human" record so the corpus gets covered over time. Until it exists, keep
   "Flag something missing" on the card.
27. [scan: YES for (a) if the answer changes the rule; NO for (b)] **Steph's Oregon City page check (2026-10-01): what is left.** All of
   her answers triaged; card and reader fixes shipped (set-aside tint,
   other numbers held, yes/no cards say where they were read, smaller-face
   columns no longer read as footnotes, centred headings claim their column
   -- 129 boxes narrowed to one column across OC/Gresham/Portland --, notes
   on a group heading reach its rows). Left: (a) MUC-1/MUC-2/MUD/WFDD/C
   "front parking banned: yes" answered "differs" with no comment --
   17.16.060.E has a three-condition escape (local street + not corner +
   topography) held as binding; ask Steph whether the "differs" was the
   escape. (b) Other cities' prose refusals still need locating into
   `set_aside:` so their pages tint grey.
27. [scan: YES (parked)] **Parking layout generator (Steph 2026-10-01: "more parking flexibility
   opens up more lots"; don't invent shapes).** PARKED by Steph 2026-10-04
   ("leave the free form generator for now"). SCOPING, nothing built.
   Steph's frame: NOT a menu of shapes -- feed the city's parameters (stall
   sizes per angle, aisle widths, number of drives -- Oregon City wants one
   approach per two townhouses = 2 for the pod -- backing rules, setbacks)
   and let it find ANY valid layout, odd angles and leftover shapes
   included ("yes, SOME solution works"; TestFit does this commercially).
   Cheap pre-defined shapes may run first as a lite screen, the generator
   only where they fail. Pool (run 49): ~108k lots fail ONLY on the court
   behind (Portland 78k) + ~32k ambiguous. Corpus: no field holds parallel/
   angled stalls or backing-into-street limits yet (Happy Valley 16.43.030.I
   exemption and Sherwood 9x20 unencoded). Steph sent 8 references (MDPI
   2075-5309/13/11/2898, arXiv 2407.01333, Grasshopper parking solvers,
   IAAC, nvdomidi/ProceduralGenerator) -- digested: none solves it, none
   checks a turning path; lessons: access first, lot-edge angles first, an
   independent validator, score against real approved site plans.
   PROPOSED time box: simple shapes (1-2 sessions) + generator prototype on
   137 (<= 2 sessions, 5,000 failing lots); continue only if it adds lots
   beyond the shapes, zero false fits in hand review, <= ~3 s a lot.
   HUMAN VERIFICATION (Steph): an annotated image per layout -- every
   distance dimensioned and tagged, a table of required vs measured with the
   citation behind each number; physical numbers no code states (design
   car, turning radii, inside-corner offset, end-stall width, dead-end
   extension, driveway spacing) from official/industry standards in a cited
   registry (research running); a review queue like the page check; zero
   false fits before any promotion. RESTRICTIONS ARE HARD LIMITS (Steph):
   moving the building never licenses a drive or court the code forbids
   (side-street-only entrance, front/side parking bans, frontage caps). GAP
   that matters now: `lowest_class` corner lots (Clackamas, Milwaukie,
   Oregon City, West Linn, Wilsonville, Fairview) -- no street's functional
   class is measured (6(c)), so today's lane may sit on the busier street;
   measure it per edge from RLIS street TYPE in s4 and re-check today's
   greens there. Awaiting Steph's go.
29. [scan: YES for (C) when widths arrive; (A)/(B) checked after the weekly run] **Fire reach: measure where the truck really stands (Steph 2026-10-01,
   "later improvement"; RULED 2026-10-05).** Item 28 (the 150 ft hose,
   OFC 503.1.1) is LIVE since run 59. RULING 2026-10-05 (no national
   standard; one Southern California template says "10 feet from the edge
   of the curb"): Steph "Let's go with stricter" -- the hose starts 10 ft
   out from the NEAR curb, capped at the street's middle; "with a flag to
   check later" -- FIRE-HOSE-START (severity 1, the plan stays red) where
   the hose is the one bind and the route clears measured from the curb.
   (A) SHIPPED d8880db1 2026-10-05, deployed (NOT in a promoted run yet --
   it lands with the next re-screen). flats/geom/curbs.py reads PBOT
   Curbs + PaveWidth, Multnomah RoadWidth, Wilsonville Width; a drawn curb
   loosens only where a recorded width agrees within 4 ft. Bound: 25 lots
   worse on the map (Portland 23, Wilsonville 2; every one a street under
   40 ft), 3 better (wide main roads with an agreeing drawn curb); 0 worse
   / 1 better over the other 4,579 lots it could touch.
   (B) Steph 2026-10-05 "Assume narrow": a street with no measured width is
   the narrowest a truck may use (20 ft, OFC 503.2.1) until measured -- the
   hose starts at its middle; FIRE-HOSE-START says a width may lift it.
   SHIPPED 57313463 2026-10-05 (Steph "Yes, ship it now"), deployed; lands
   with the next re-screen. The bridge now REFUSES a --curbs/--sources snapshot missing
   any of curbs_portland, pave_width_portland, road_width_multnomah,
   width_wilsonville: the weekly run must acquire them (or pass --curbs
   /root/fire-curb_sources/2026-10-05), and so must any lane's bound.
   BOUND 2026-10-05 (before d8880db1 / after a7b51185, same curbs): the
   4,312 lots whose run-63 route is 125-160 ft: map colour 170 worse
   (green->red 79, green->yellow 7, yellow->red 84), 2 better; 3,000 random
   of the other 47,836: 12 worse (2 / 2 / 8), 0 better. County estimate
   ~360 worse (sample range ~270-500), ~150 of them green today (~100-250);
   Washington uninc 65, Beaverton 23, Clackamas uninc 16, Oregon City 14,
   West Linn 14 of the 182 found. Every loss read: 181 routes 140-150 now
   150-160; 1 Hillsboro lot is the worse of two readings (doubtful private
   drive). 176 of 182 carry FIRE-HOSE-START; 4 without still reach (moved
   onto a slope warning), 2 Gladstone redraws report steep ground / fit
   instead of the hose (red either way). Both gains read: the hose miss
   moved the building on the same lot onto ground under 5% -- the slope
   warning was where the default drawing stood, not the lot (slope lane:
   the placement does not search for flatter ground). Scripts
   /root/fire-curb_probe/{pick_b,lotview_b,losses_b}.py.
   (C) Ask Washington County, Clackamas County and West Linn for their
   pavement widths -- DEFERRED, Steph: "follow up with them later". Also
   published but unused: Oregon City Edge of Pavement (CAD, undated),
   Hillsboro Roadway polygons (mixed with parking lots). Not reachable
   from here: Beaverton, Gresham. Scripts /root/fire-curb_probe/; detail
   in memory project_flats_fire_curb. Not tied to the 10-08 re-screen.

30. [scan: NO new code, check after the weekly run] **Net land area review (Steph 2026-10-01: "not unique to Beaverton ...
   we need to do a review of net land areas and what to do about it").**
   129 numeric values in 10 layers carry `measured_on: net_developable_area`
   (HV, Milwaukie, OC, West Linn, Fairview, Gresham, Troutdale, Beaverton,
   Cornelius, Hillsboro); nothing measures net area, so the check settles
   one way from gross and holds the lot otherwise. Run 51 best-pod lots with
   a net check unsettled: Beaverton 20,341, West Linn 9,511, Hillsboro
   2,969, Gresham 2,339, Oregon City 1,105, Fairview 174, Happy Valley 97
   (~36,500; net area is the ONLY hold on just 165 -- other holds mask it).
   Ceilings (max density/FAR) mostly have wide margins (Beaverton 14,818 of
   17,589 survive losing 1/3); near-cap lots in OC/Hillsboro/HV do not.
   Floors (min density, big lots): ~6,600 pass only if >10% is deducted.
   What each city subtracts (agent read, 2026-10-01): existing ROW is
   already outside a tax lot; new street dedication/tracts/parks/private
   streets arise in land divisions (not measurable); floodplain measured
   (only yes/no reaches FLATS; quadfit has ovl_<key>_sqft areas, not
   bridged); resource overlays carved in Gresham/OC/WL/Troutdale, area held
   in quadfit for HV/Milwaukie/Hillsboro/Beaverton (Metro proxy), NOTHING
   for Cornelius; slopes: lidar held, no "area over 25%" computed; no
   landslide layer. Gresham 3.0100 has two lists; its max density outside
   the LDR group is gross by the code's own words (settle now). Fairview
   subtracts street ROW only (= gross on an existing lot).
   Possible encoding gaps: Tigard MU-CBD 25/50 du/ac may be net (18.40
   "net development area") -- false-GREEN risk, read first; King City KT
   min densities "per net acre" unmarked, Wood Village defines "Land area,
   net" (720.030 L224-234) though the yaml says undefined, Washington Co.
   min density may exclude constrained land -- all three false-RED only.
   Beaverton rulings owed: is the pod's own drive aisle a "common driveway";
   do wetlands count only when set aside in a tract/easement.
   OFFERED Steph: (A) ordinary existing lot = no new dedication/tract, net =
   gross minus what we measure per the city's own list (floodplain,
   overlays, slopes) -- settles nearly all, big lots under a floor go red;
   (B) margin rule (settle when the lot could lose 1/3) -- ceilings settle,
   near-cap and floor lots stay held; (C) leave held. Steph 2026-10-02:
   **A**, and "lots that fail for the only reason of min density need to
   go not red. Some sort of yellow or 'closer look'" (interim, until 31).
   SHIPPED d8d4a439 (deployed 2026-10-02): all 170 net-area values carry
   `less` / `may_less` / `assumed_none`; net area is a range (overlaps
   unknown), settled when both ends agree; min density alone = yellow
   CLOSER_LOOK_MIN_DENSITY. RUN 61 PROMOTED 2026-10-02 (131,039 lots
   at 6d9f7197, spliced on bridge_spliced_2026-10-02_draw; drift 59->61
   5,765 moved / 0 unexplained: 5,733 unknown->yellow as FAR + min
   density settle -- Beaverton FAR 32,240 rows, West Linn FAR 11,700 --
   29,626 rows now carry the closer look; 23 green->unknown + 6 ->red
   are FIRE, lots no fire partial had re-bridged, reported to the fire
   session).
   Beaverton rulings ANSWERED (Steph 2026-10-02): the pod's lane + aisle
   ARE a "common driveway" (neither code defines one; stalls stay in), and
   constrained land comes off whether or not set aside in a tract ("very
   few will have done that") -- both now certain deductions in Beaverton
   and Cornelius 18.195 (Metro wetland/habitat stand-ins stay `may_less`
   as regional proxies). Tigard read: MU-CBD's 25/50 per acre is not
   stated net in 18.650 (no false GREEN); Tigard FAR is net but no FAR is
   encoded. 2026-10-04: King City KT (4), Wood Village LR/MR (4) and
   Washington Co. TO:R24-40/TO:R40-80/NMU/CCMU/CBD floors now net (183
   values); Wood Village floodplain certain, the rest `may_less`; NB floors
   and county maxima stay gross by 300-2.8's words. Run 63: 2,077 lots in
   those zones, 419 failing the floor on the whole lot -- lands at the next
   FULL re-screen. Lot page names each net-land list + what was assumed
   absent (rules read at view time). (e) slopes: SHIPPED 2026-10-04 with
   item 38(b) -- lidar measures each city's slope item; only the
   landslide-area slopes stay assumed absent (see 38).
31. [scan: YES (not started)] **Split a big lot to meet a minimum density (Steph 2026-10-02: "create
   a task for later ... immensely complicated ... large guesstimates on
   roads, utilities, etc. maybe never done").** A lot too big for 4 homes
   under a city's minimum density could still work as a land division
   (several pods, or pod + other lots). Needs guessed streets, utilities,
   tracts and each city's land-division rules. Until then, a lot whose
   ONLY failure is minimum density is yellow "closer look" (item 30), not
   red. Not started; may never be.

32. [scan: NO] **Windows CPU spikes (Steph 2026-10-02: "60%+ of my CPU on Python").**
   Measured: at idle Python uses ~2% of the PC. The bursts are (a) test runs
   on Windows -- `pytest flats/tests -n auto` starts 16 workers, one per
   thread; the Stop hook's `pytest tests/` when `app/` changed; (b) the
   code-review-graph PostToolUse hook re-parsing after every Edit/Write/Bash;
   (c) NOT vicinitideals: the claude-mem plugin's chroma-mcp leaks a copy
   per session -- 256 Python processes, 66 uvx trees (26 orphaned), 1.25 GB,
   6,260 CPU-s since 2026-09-30. County runs already happen on LXC 137.
   DONE 2026-10-02: 137 raised 12 -> 16 cores, 24 -> 32 GB (Steph); full
   re-screens capped at once a week (runbook §4c). OFFERED, PENDING:
   (A) kill the orphaned memory-plugin copies; (B) cap local test workers
   (`-n 4`) so tests never take the whole PC. Running tests on 137
   instead was DECLINED by Steph 2026-10-04 -- do not re-offer.
33. [scan: YES for (c) and any speed-up (must prove identical answers)] **Parking court leftovers (fix ca26e048 LIVE as run 63, 2026-10-02:
   drift 61->63 green->yellow 3,459, unknown->yellow 4,453, 0 unexplained).**
   Still open ((a), the court beside the building, fixed f7ba7038):
   (b) lots outside the 15,940 scoped whose court stands in a side or front
   yard INSIDE the lot are corrected only by the next full re-screen;
   (c) s5o-envelope lots use the whole lot (less carve) as the court's
   ground; (d) DONE ce65b86b 2026-10-04: scanline raster + longest-run depth
   (`flats/fit/raster.py`) -- bridge 2.2-2.6x faster, answers identical on
   every column (bound on 137: 2,000 Multnomah + 2,000 Washington lots +
   60 mixed; random-shape harness 0 cells gained). Next levers if needed:
   `has_window` in the court searches, `ground_for`.
36. [scan: YES] **Parking tool queue (Steph 2026-10-02: "do them in the reverse order
   you listed them").** (5) partly, (4) and (3) LIVE as code f7ba7038; the
   re-screen rides the weekly full run (~10-08) -- read the moves on
   corner lots with `lowest_class` and in Tualatin, Gladstone, Multnomah
   uninc and Hillsboro. Left of (5): strips not yet encoded -- Wood Village
   350.065(C) and Oregon City 17.52.060.C (one-lot projects only), Happy
   Valley 16.43.030.E.3 and Troutdale 9.095(A) (the neighbour district's
   setback; needs per-line neighbour zoning), Tigard 18.280.040.D.4 (width
   in unstored 18.420); unread chapters ZDO 1009, West Linn CDC 54,
   Washington CDC 407-6, Sherwood 16.92, King City 16.124, Tigard 18.420,
   Troutdale Ch. 11; Fairview 19.163.030(E) 5% of the parking area.
   QUESTION for Steph: OAR 660-046-0220(2)(e)(E) makes large cities apply
   single-family parking standards to middle housing -- it may cancel the
   strips single-family homes are not held to (Multnomah, Gladstone,
   Hillsboro, Wood Village, Oregon City); encoded strict meanwhile.
   RULED Steph 2026-10-04: "Let's have strips be a flag for yellow at this
   time" -- DONE 1d3c89cb: a plan that misses only by the strip (court-shaped
   checks, fire route, steep ground, within 3 strip widths) and clears with
   it read as unstated is YELLOW with flag PARKING-STRIP-UNCONFIRMED.
   Bound 2026-10-04 (21,700 lots): Gladstone 32 red->yellow, Tualatin 50,
   Multnomah uninc 7, Hillsboro 4; 0 lots worse. Rides the weekly full
   re-screen. The OAR question still decides whether the flag can clear.
   STRIP IMPACT measured 2026-10-04 (bound on 137, strips on vs off, best
   pod as if signed): Gladstone 384 -> 445 green of 3,217 (+61), Multnomah
   uninc 885 -> 898 of 2,213 (+14 gained, 1 lost), Hillsboro 2 -> 5 of a
   4,000 sample (~+20 of 27,402). Steph: "planter strips aren't parking,
   they're landscaping" -- the OAR question stands. The few lots that got
   WORSE with more ground are item 39 (fire route), not strips.
   (2) turning path LIVE as code 1723db45 (2026-10-04, Steph "ship it"):
   every stall must be usable by the AASHTO P car (three-point turn ok);
   ledger `flats/config/court_turns.json` holds a menu of fixes per court
   shape (deeper aisle, wider stalls, mixed, dead end last), least paving
   first. The re-screen rides the weekly full run (~10-08) -- expect ~3%
   of Portland greens on narrow end-on lots to go yellow (bound: 18 of
   561), and read the moves. A new court shape in the corpus needs
   `python -m flats.score.turns` (test_turns fails until it is solved).
   (1) the free-form generator (item 27) -- PARKED by Steph 2026-10-04
   ("leave the free form generator for now").
37. [scan: YES for (iii); NO for (f)] **Flag system plan ("FLATS Flag System Plan.md", Steph 2026-10-02) --
   slice 1 + approval page DEPLOYED 2026-10-03 (Steph: "Deploy"), merge
   34963899 on main; no lot colour moves until the next bridge run writes
   the new columns (planned with the ~10-08 full re-screen, item (c)).** Steph's answers: (1) no variances, a miss with a path
   is RED, path logged on the bind; (2) a flag below the line (severity < 3)
   keeps the lot green; (3) min density = low flag (severity 2 -> green);
   (4) colour stays "as if signed". Slice 1: flats/score/flags.py (Flag,
   Bind, colour, write gate), flags.yaml (68 types, all pending), colour.yaml
   (pending); screen/bridge/assign write colour+flags+binds beside the old
   triage; loader stores them in lot_results.checks; the map still shows
   if_signed. Expected shift (run 63 base): most of 330k yellow -> red
   (653k of 675k yellow rows rest on RELIEF_UNCONFIRMED); use gates with a
   conditional-use path (~1,900 rows) also go red. REMAINING vs Steph's
   plan checklist (offered 2026-10-02, order recommended): (a) trial count
   DONE 2026-10-03 on 137 (/root/bridge_flags_trial, 10,000 lots seed 23,
   branch code in /root/code/flags-trial, compare script
   /root/flags_trial_compare.py): best pod per lot green 1,594 -> 1,783,
   yellow 7,952 -> 675, unknown 345 -> 0 (unknowns become yellow), red 109
   -> 7,542; yellow->red 7,427 (fit short 20+ ft dominates); yellow->green
   189 (min density only); unknown->red 6 (prohibited use); no green moved;
   no crash; the run-63 SQL prediction agreed on 99.76% of rows. Steph
   RULED 2026-10-03 "Exactly 1 foot is red": the fit moves in half-foot
   steps and 6 in short is already green-with-flag, so the near-miss band
   holds no lot today; the ~1,900 lots short by exactly 1 ft go red. Also: an
   ambiguous rule set binds nothing, so ~0.07% of rows stay yellow despite
   a 50+ ft fit miss (Wilsonville R, Hillsboro SCR-V) -- by design. (b) APPROVAL PAGE BUILT 2026-10-03 9faf1664 on the branch: /flats/flags "Unknowns" (owner-only approve, waiting kinds on top), flats.flag_decisions (0139), scripts/flats_drain_flag_decisions.py (only writer of status: approved); LIVE 2026-10-03, E2E tests/e2e/test_flats_flags.py 3/3 green on prod; drain on 114 needs --registry-out/--colour-out on /app/data. Still open in (b): per-lot flag instances with open/cleared history in the DB + review queue. Was: DB tables (flag type / instance with open-cleared
   history + review note / bind) + one write path + approval page where
   Steph sets the 68 types' numbers (agent can only propose) + review
   queue; (c) map + lot page show the new colour with its reasons; ship on
   the weekly full re-screen (~10-08) = the plan's snapshot + rerun +
   reconcile, leftovers = audit list; (d) nightly consistency check, counts
   per type/key by colour, work queue (priority then yield), design
   sensitivity report (needs binds to name the pod dimension + the pass
   threshold + pod version -- not stored yet); (e) severity 0 for flags
   cleared at the worst bound; (f) Phase 4 pod spec, deferred by the plan.
   Steph 2026-10-03: "measurement" (the code works it out from maps) is THE
   PREFERRED resolution type -- the other three (inquiry, document, per-lot
   review) are "the failure mode"; flag tables live in the app DB from the
   start ("flags and warnings are equivalent data points just like a min
   setback is"); NO DEADLINE for a pending flag type (pending types top the
   approval page + the count is mentioned at session start). Plan gaps: flag history
   across county refreshes; bulk writes through the loader.
   Live run 63 breakdown of 329,484 yellow lots (best pod): 318,290 break a
   rule as read; fit short >20 ft 220,618 / 5-20 66,903 / 1-5 19,925 / <1
   1,887; fits but misses another rule 8,957; 129,219 also carry unknowns;
   11,194 yellow with no miss. Steph RULED: short by 1 ft or more -> red
   (pull back later for targeted variances / no-parking ideas); under 1 ft
   -> yellow (near_miss in colour.yaml, built on the branch). Unknown facts
   on yellow lots: mostly mappable (local_street 28k, north_of_marine_drive
   20k, through_lot 20k, water 10k, historic 8k) vs needs a title report
   (utility_easement 28k, sidewalk_easement 20k) -- offered as next work.
   Steph 2026-10-04: "Start number 2 [measure] first, then 1 [map + lot
   page], then continue". ALL BUILT + DEPLOYED 2026-10-04 (6eb14ffe on
   main): (2) measured through_lot, OC NROD water, West Linn WHD, Gresham
   north of Marine Dr + held_open guard -- bound 10k seed 23: 75 rows
   yellow->green (all West Linn outside WHD), nothing lost, no reds; (1)
   lot page shows rule colour + misses + open questions (9ed00826, 0140);
   (e) severity 0 at the worst bound (85712ad6, `_bounded`): partial bound
   15/4,000 rows yellow->green (local_street, flag_lot, abuts_*_zone); most
   fact flags sit on footnotes with no stated direction so cannot drop --
   extending = encode each capped footnote's direction; (b-rest) flag
   history flats.flag_instances + question queue /flats/flags/questions
   (0141, nightly sync 10:30 UTC, scripts/flats_flags.py sync|ask|check);
   (d) /flats/flags/queue (priority, then lots it turns green alone) +
   nightly check + pod width report /flats/flags/report (0142) -- FIT
   ONLY. NOTHING SHOWS until a run screened under the colour rule is in
   use (the ~10-08 re-screen); after promoting it run `scripts/flats_flags.py
   sync` then `check` on 114. Item-3 bound DONE: 20k rows,
   74 yellow->green, all severity-0 fact flags, no reds, no fit change;
   timing 2,000 lots same load: 1,873 s without vs 2,029 s with (+8%);
   cbc47269 (True-first + seen-standards dedupe) identical output, LIVE.
   The ~10-08 re-screen must run from main >= cbc47269. (ii) DONE 2026-10-05 79dff142+7dc34722 (check-margins
   lane): the bridge keeps {check: [observed, threshold, room]} for every
   PASSING check (lot_results.checks->'margins'); /flats/flags/report charges
   a wider pod on coverage/FAR/paving/open space too, tries the pod taller and
   lower, and shows "room to spare on green lots" per limit. Bound on 137 (10k
   lots seed 23, old vs new): 0 colours moved, every column identical. The ~10-08
   re-screen carries it only if run from main >= 7dc34722; nothing shows
   until that run is in use. ROOM EACH WAY DONE 2026-10-05
   794b5f3d+f3408efa (Steph: "we need all dimensions ... oddly shaped
   lots?"): on every green/yellow lot whose fit passes outright the bridge
   searches the real lot shape, in the plan the screen took, for how much
   WIDER, DEEPER and BIGGER BOTH WAYS the pod could be (checks.fit.room,
   capped 40 ft; tight-fit and non-fitting lots carry none, by design). The
   report tries the pod wider / deeper / both ways each from that room and
   counts "tight shapes" (both ways a foot+ less than either way alone).
   Bound on 137 (10k lots seed 23): every old column identical, 0 colours
   moved; room on 2,828 rows (1,848 of 1,850 greens); 638 a half foot+ tight; 1,218 s ->
   1,280 s (+5%). The ~10-08 re-screen carries it only from main >=
   f3408efa (137's weekly checkout was still 0bf7c8e2 at 12:05 UTC 10-05).
   OPEN: (iii) Gresham
   note 5 "end of a Minor Access Street" held on `local_street` (wrong
   fact) -- re-point + measure dead ends; worth little while
   sidewalk_easement holds the same Gresham lots; (f) Phase 4 pod spec.
38. [scan: NO new code, check after the weekly run] **Slope (Steph 2026-10-04: "work on slope ... on most small lots steep
   slope would be disqualified due to build costs rather than net land").**
   TODAY: quadfit s5o measures per-lot mean/p85/max slope % (3DEP 1 m lidar,
   10 m DEM east of ~-122.48: Gresham/Troutdale/Fairview/Wood Village/east
   Portland) and the bridge loads it onto `facts.slope`; the lot page prints
   it. FLATS's verdict reads none of it (quadfit's old 10/20% p85 tiers held
   lots for review; FLATS dropped that). `steep_slope` struck 2026-09-27 (no
   rule uses it); slack.yaml slope_pct 2.0 tolerance unused. Hillside
   overlays act only as carves (Gresham HGRO, Troutdale VECO) or a flag (HV
   steep slopes). Run 63: of ~68,000 best-green lots, ~15,400 have p85 >20%
   and ~10,800 >25% -- but 1 m pixel slope reads micro-relief (flat SE
   Portland lots mean ~6% on 1 m vs ~3% on 10 m), so the statistic overstates
   build grade. PLAN: (a) build-cost grade = fall across where the fit DREW
   the building + court, from a smoothed lidar surface (plane fit), per
   design; (b) net-land slope = lot area steeper than each city's threshold
   (15/20/25%) measured over a code-like run, plus DOGAMI SLIDO landslide
   areas where a list says "within a landslide hazard area"; (c) coarse-DEM
   lots over a cutoff go yellow, never red. RULED (Steph 2026-10-04): pad
   grade <=5% green, 5-15% closer look, >15% red; AND "slope-based lot
   elimination should happen before pod placement ... measure how much of
   the lot is sloped like that and subtract it and see if there's even
   enough land for the pod. If no, don't check pod placement." and "Ignore
   banks under 4 ft" (a patch falling <4 ft top to bottom is regraded, not
   lost; ignoring steep ground in setbacks was tried at Steph's question
   and brought back 1 of 101, so not adopted). SHIPPED (code only; nothing
   live moves until a re-screen): flats/fit/slope.py + flats/config/
   slope.yaml; ground >15% over a 5 m run comes off the envelope + court
   ground before the fit, a fit lost to it is `steep_ground` (RED, no
   relief), the drawn building + court is graded (SLOPE-GRADE sev 4 =
   yellow, >15% on 1 m RED); coarse 10 m never RED. SAMPLE (2,000 lots,
   seed 31, wash data): ~25% of greens go RED on steep ground (mostly real
   hillsides, median lot grade 12%), ~7% yellow; the 4 ft bank rule
   brought back 10 flat lots (pad <=5%). Bridge time +48% overall, ~2x on
   lots with steep ground. LANDED: run 65 (weekly, promoted 2026-10-07);
   49(e)/(f)/(h) fixes in run 67; the E2E slope test passes on production
   (2026-10-08). (b) SHIPPED
   2026-10-04 (code only): the bridge counts the lot area at >=20/25/35%
   on 1 m lidar and hands it to the net-acre list as `slope_20/25/35`
   (never on 10 m). Read per sentence: Hillsboro 12.01.500(6), Milwaukie
   19.200, Cornelius R-7/A-2 = `less slope_25`; Oregon City 17.04.810(3)
   `less slope_35` + `may_less slope_25` (director may lower it); West
   Linn Type I/II "as shown on the RLIS layer" = `may_less slope_25`
   (lidar stands in); Washington Co. 300-3.1(D) "may be excluded" =
   `may_less slope_20`. SAMPLE (3,000 lots, seed 7): zero colour moves,
   min-density failing rows 100 -> 96, bridge +9.5%. OPEN (offered to
   Steph 2026-10-04, low payoff): slopes that count only "within a
   landslide hazard area" -- Beaverton BDC 90 (Comp Plan Fig 8.6.1) and
   Wood Village 720.030, both the applicant's option -- plus West Linn's
   landslide areas on NHMP Maps 16/17. Needs DOGAMI SLIDO or the city
   maps traced; today assumed absent. Steph 2026-10-05 DECLINED (agreed
   to leave it) -- do not re-offer.
40. [scan: YES, if started] **Easements from maps (Steph 2026-10-04 asked the odds of reading an
   assessor/easement map onto the lot).** Holds: utility_easement ~28k and
   sidewalk_easement ~20k yellow answers (Beaverton 0 green: BDC 20.05/20.22
   note 7 "no building may encroach into a Public Utility Easement"; OC R
   zones same). No easement layer in RLIS. Answer given: assessor tax maps
   rarely draw easements -- the subdivision/partition PLAT (and its notes,
   e.g. "8 ft PUE along all street frontages") is the right source; placing
   a drawn strip on a lot line is the drawn_areas trace recipe; modern plats
   ~85-90% right, old hand-drawn scans ~60-70%. A plat cannot prove ABSENCE
   (easements granted later by separate deed are not on it). HYPOTHETICAL
   (Steph 2026-10-04: "I don't know that I'll do it"); do not start unless
   Steph sends maps. If he does: pilot 5-10 maps (modern plat, old plat, tax
   map; one with a title report to grade against), first check whether
   Beaverton/Hillsboro/Washington Co. publish an easement GIS layer or bulk
   plat images; severity of "plat read, deed easements unchecked" is ruled
   AFTER the pilot, not before.
41. [scan: YES] **Street class per lot line -- (a)+(b) SHIPPED 6b924963 2026-10-05;
   (i)-(iii) SHIPPED 2026-10-06 b03dcd88/92c5f1d9/972caa17, deployed.** Live:
   Gresham note 5 caps on measured `at_street_end` (False-only);
   `local_street` from Milwaukie's TSP map (True needs Metro to agree) and
   Wilsonville's (False only: Villebois "Collector Avenues" are the master
   plan's Figure 7). Bound: every number identical, 0 colours, if-signed
   37 Milwaukie lots up. WEEKLY RUN (~10-08): acquire `--keys
   street_class_*` (all of them) into the snapshot or the facts stay
   unasked (safe, no gain). Rulings, in build order:
   (i) corner lots on a quiet AND a busy street: the building FACES THE
   BUSY STREET so the quiet one is the side and the drive comes off it
   (both the 10-02 side-street ruling and `lowest_class` hold) -- ~224
   Milwaukie lots; where the code fixes the front on the quiet street,
   the drive comes off the front (lane beside the building) or fails;
   (ii) MORE CITY MAPS for every `lowest_class` city (Oregon City,
   Fairview, Tualatin, Clackamas Co., West Linn if a layer exists,
   Hillsboro PSU layer...) -- each city's class words checked against its
   code's words (the Villebois lesson);
   (iii) Gresham sidewalk easement (note 1: setback measured from the
   easement line): MEASURE where the sidewalk runs against the lot line;
   where it cannot be measured, FALL BACK to a stated worst-case easement
   depth (pessimistic), never to "none".
   Built:
   (i) `measured_access`; (ii) rank maps for Oregon City, West Linn,
   Fairview, Beaverton (+ Milwaukie/Wilsonville ranked); (iii) nothing
   measures the walk (RLIS 2851 is presence only, +/-10 ft; Gresham
   publishes no layer) so every street line takes the worst case: 7 ft on
   a Metro-local street, 20 ft elsewhere (PWS 6.05.01/6.06.02), and the cap
   lifts. Bound /root/street-class_bound_{base,new}5 (every mixed-rank
   corner in the 6 cities, 5,228, less 244 Beaverton ROW strips + 4,000
   random Gresham): corners -- 32 greens lost (West Linn 16, Milwaukie 9,
   Wilsonville 7), ~120 yellow->red, 2 gains (slope read at the moved
   building); Gresham sample -- 247 greens gained, ~262 yellow->red,
   x6.45 county-wide ~1,600 up / ~1,700 down. Every gain read: cap lift,
   item 44's ranking (a fitting front now beats a variance-yellow miss),
   or flatter ground under the moved building. Reaches the map with the
   ~10-08 full re-screen, which needs ALL 7 `street_class_*` keys
   (washington added) + rlis_streets.
   Leftovers 2026-10-06: WashCo uninc re-read -- 501-8.5 B(2)-(4) bars a
   4-plex from collector/arterial/neighbourhood-route access, so
   `lowest_class` KEPT and ranked off the county TSP map (FClass2; local
   streets undrawn, so an undrawn street ranks 0 only where Metro calls it
   local). Bound /root/street-class_bound_{base,new}6 (the 1,717 corners
   whose drive moves to the quieter front): 248 greens lost (237 red: the
   drive off the front does not fit, or steep ground), 94 yellow->red, 6
   up (slope/fire route read at the moved building); 410 local fronts
   checked for a missed parallel TSP line: none. Lot page shows the
   assumed sidewalk easement (after the next promoted run). Tualatin
   through lots PARKED: 351 lots, ~30 green if signed; an exact answer
   needs a court entered off the back street + a Tualatin class map.
   Beaverton ROW strips: dropped in normalize since 77c99822; only bounds
   on the 10-01 stage files meet them. Still open: Wilsonville note P via
   easement layer 150 (low value while access_easement caps RN).
42. [scan: NO new code, check after the weekly run] **Water, wetland and flood ground at slope's fidelity -- DONE; reaches
   the map with the weekly runs from ~10-08 (all WARNED promotions, Steph
   promotes).** Steph asked 2026-10-04 "are we treating wetland/flood zones
   with as much fidelity as we now treat slopes?". Shipped: (a) Portland z
   RED e55c22ee (PCC 33.418.040.B; Steph RULED "red, way in noted", ~17,900
   lots); (b)/(c) every quadfit `flag` overlay + FEMA fringe a YELLOW
   closer look 25d26ce6/2c5b461b (8,873 greens), Milwaukie greenway RED
   (126); (d) DSL state wetland maps everywhere 1c6da420 (+33 yellow);
   phase 2 no-build carves 587b02d1 (824 yellow->red, read); residue
   5b4ba52e + 799ef7a9 2026-10-06, deployed: Portland ezone p/c/v resource
   areas carved (PCC 33.430; the 25 ft transition area inside p+c stays
   buildable); Wood Village carves only streams, wetland buffers and real
   HCAs (WVDC 430.170.A -- its "NO HCA" and flood-only polygons were an
   over-carve) and flags WQR/HCA; Hillsboro reads its own significant
   natural resource map (CDC 12.27: site or impact area = flag, the
   no-build core carved) instead of Metro's habitat map. Bounds on 137,
   colour per lot: Portland/Wood Village 1,821 lots -- 25 Portland
   yellow->red, Wood Village 3 red->green + 5 red->yellow (over-carve gone,
   read) and 1 green->yellow (WQR flag); Hillsboro 5,145 lots -- 28
   yellow->green, every one read (on Metro's habitat map only, off
   Hillsboro's map, envelope and every other flag unchanged), 7 yellow->red
   (4 no fit, 2 steep, 1 hose), 1 red->yellow, 0 greens lost. The weekly
   run that carries phase 2 and the residue must re-run quadfit s5o on this
   code (every bound patched a copy) and acquire `overlay_hillsboro_snro`
   (pipeline.yaml registers it). RULED, never re-offer: FEMA fringe stays
   YELLOW ("we aren't customizing for flood zones"); landslide slopes, the
   "maybe list" (probable wetlands, hydric soils), the HCA disturbance
   allowance (Steph 2026-10-06 "Leave it") and West Linn fish-bearing
   streams (ODFW 65 vs 100 ft, Steph 2026-10-06 "ignore") all DECLINED.
   Left as they were, read: Clackamas WQRA, Happy Valley, Tualatin;
   washington_habitat stays a flag for WashCo uninc, Beaverton, Sherwood,
   King City, Durham (each needs a map or a determination the city holds).
   Known under-carve: Portland's city-limit transition-area exception
   (33.430.050.A) is not drawn.
44. [scan: NO new code, check after the weekly run] **A lot's readings are ranked on the colour the map shows, and
   43's hose edge -- SHIPPED 51577bb8 2026-10-07; NOT in run 65 (the early
   10-07 weekly started first); Steph 2026-10-07: wait for the next weekly
   run.** `_front_rank`, `_worse`, `_better` (flats/ingest/quadfit.py)
   compare `signed.colour` first, the triage only on a tie; the triage had
   ranked a missed fit (yellow, its variance path) above a fit waiting on
   an open fact. Hose edge (item 43's last loose end): a utility-easement
   yard that fails a check the code's own yards passed falls to the 5 ft
   yard, question open (`_lost`). Bound on 137 over every corner, through,
   part-alley and two-reading lot + 2,012 control (39,743 lots, 3f514c9e vs
   3cbe113c, /root/rank-colour/diff.out, moves_ABR.csv; every move read, 7
   replayed with probe2.py): control identical; owner-choice corners 436
   lots better (32 red -> green, 404 red -> yellow), none worse; through
   lots kept at the worse end 99 lots yellow -> red, no false GREEN;
   two-reading lots kept at the worse: 34 lots (39 rows) were false GREENs
   (13 rows now red, 26 yellow), 72 lots yellow -> red; hose edge exactly
   the 4 known rows on 3 Oregon City lots red -> yellow (593 hose-red rows
   at 10 ft stay red); every new green graded. Run 65 still shows 30 of
   those lots / 34 rows green (item 49(b)). Item 43's easement rule itself
   checked on run 65 2026-10-07 and closed: lots green Beaverton 3,202
   (2,833 answered at 10 ft + 369 in CS/GC/RC/SC/TC zones the PUE sentence
   does not reach -- whole-corpus grep: only BDC 20.05 and 20.22 say it),
   Oregon City 2,166, vs the bound's 3,043 / 2,230. After the next weekly
   run: spot-check a few of the 34 lots on the map, then remove this item.
   137 cleanup DONE 2026-10-07 (bound dirs gone, both trees removed);
   /root/rank-colour/{diff.out,moves_ABR.csv,probe2.py} kept until the
   spot-check.
46. [scan: YES (a proof run: every answer must come out identical)] **Scans (bounds) on 137 are the lanes' bottleneck (Steph 2026-10-06:
   ~1 h coding, then 5-6 h waiting for one scan at a time; four lanes
   queue on `heavy.lock`).** (a)-(c) SHIPPED 24a61695 2026-10-08
   (deployed, smoke passed): `flats/ingest/batch.py` -- costliest lots
   first; chunks start on live free memory with a 3 GB reserve; each
   chunk runs its hungriest lot first and, in flight, holds memory only
   for the lots it has left; a dead worker costs one lot (retried alone)
   instead of hanging the Pool; `--cache` answer cache; sample while
   iterating (parallel-agents rule 12). Proof 4 on 137 (2026-10-08,
   scope_A 9,936 lots vs `/root/rank-colour_bound_base_A`, base 3,640 s):
   SAME on every run -- cold 16 procs 3,227 s, booked 16 procs 3,057 s,
   booked 14 procs 3,074 s, warm 66 s; no worker died; least
   MemAvailable 3.6 GB. 137 is now CPU-bound (lot-seconds 37k -> 43k
   with 16 busy), so the simulator's ~2,000 s was not reachable and more
   than 14 processes buys nothing. Proofs 1-3 caught a `python -m`
   worker-setup bug and an OOM kill, both fixed. (d) rented compute --
   PARKED by Steph 2026-10-08 ("won't do for now"; keep the research,
   don't delete it). 2026-10-09 RE-ASKED (Steph moving to Max 20x
   and 7-9 parallel agents; the Proxmox host is maxed -- 137 already has
   16 of the i5-14600KF's 20 threads, so no free home capacity): est.
   at 7-9 agents ~3,000-4,000 vCPU-h/month beyond 137 = ~$250-350/month.
   Steph: NOT YET, MEASURE FIRST -- run a week at 7-9 agents, log how long
   checks wait on heavy.lock per day, decide with that number. Steph 2026-10-06 PREFERS
   CLOUDFLARE (a commercial version would run there): Cloudflare
   Containers (GA 2026-04-13), many small boxes of at most 4 vCPU /
   12 GiB / 20 GB each, up to 1,500 vCPU per account at once; CPU billed
   only while busy ($0.072/vCPU-h), memory while running
   ($0.009/GiB-h), so ~$0.40 per busy 4-vCPU box-hour; inputs via an
   R2 bucket mounted in the box; $5/month Workers Paid plan. Est. (to
   prove on a first trial): full re-screen under an hour for ~$10-20, a
   lane bound ~10-15 min for ~$1-3, a 2,000-lot sample ~$0.30. Build:
   a chunk mode for the bridge, a dispatcher Worker + Durable Object,
   answers written as `AnswerCache` files to R2 and merged by the
   existing cache read; first rented run must reproduce a 137 run
   exactly. Risk: a lot that needs more than ~11 GB cannot run in a
   12 GiB box -- those stay on 137; the first full run's
   `timings.parquet` (peak memory per lot) counts them. Steph's part:
   Workers Paid plan, an API token (Containers, Workers, R2) in a file
   outside the repo, a monthly budget alert. Fallback considered:
   Hetzner CCX63 in Hillsboro OR (48 vCPU / 192 GB, ~$1.64/h, billed
   until DELETED; one big machine, least build). (e) fewer lanes: not
   pursued. LEFT: (f) skip big PRIVATE lots by size -- Steph 2026-10-06
   DEFERRED: "see what the institutional changes remove" (item 47), then
   decide. Measured on quadfit_2026-10-01_wash (418,021 lots screened):
   861 lots >= 10 ac (660 10-20, 167 20-44, 34 >= 44; biggest 194.8 ac
   1S1080000504) = ~11% of the cost proxy; 47's signals (Washington PUB
   or PROP_CODE 9xx: 90; Multnomah ASSESSVAL 0 with TOTALVAL > 0: 109)
   leave ~660, mostly private (vacant, MFR, COM, farm, SFR acreage;
   Clackamas's 181 unsorted). Re-measure with the first full run's
   `timings.parquet` after 47 lands. (g) GPU: Steph 2026-10-07 dropped
   it ("forget those two questions").
47. [scan: YES] **Institutional land is RED and never scanned (Steph RULED
   2026-10-06: "hospitals, schools, municipal, parks, water treatment/heavy
   infrastructure should just be flagged red and flagged out of scans for
   any reason").** Found when a 44-acre R-5 school campus (1N1190002300,
   4200 NW 185th Ave, Westview HS) held 137's lock alone for 70+ min. No
   owner name in the RLIS feed. Signals measured on the 10-01 s1 (656,383
   records): Washington `LANDUSE = PUB` (4,387; 1,899 in the screened
   universe; PROP_CODE 9xx); Multnomah has no PUB but `ASSESSVAL = 0` with
   `TOTALVAL > 0` marks tax-exempt land (10,572: PCC Sylvania, Mt Hood CC,
   David Douglas HS... -- also churches and nonprofits); Clackamas has
   neither -- needs map layers (ORCA parks held; schools/hospitals/utility
   sites to find). Scope ANSWERED 2026-10-06: churches and charities stay
   CHECKED; ADDED airports, marinas, transit hubs, rail, public pools/
   plazas, waste treatment, malls; a church's school is a SCHOOL (Steph,
   asked 2026-10-06). SHIPPED ca06c2ff (deployed, smoke passed): OSM
   extract `osm_land_use` + ORCA public parks/school land, >= 50% of the
   lot; assign answers RED (INSTITUTIONAL_USE / institutional_share),
   bridge `--institutional` skips. EVERY bridge scan (agents' test and
   partial scans too) skips them since c1a96d81: the bridge reads the land
   from `--sources`, else refuses; agents on 137 pass `--institutional
   /root/institutional_sources/2026-10-06`. Measured vs run 63: 9,923 of 587,815
   lots -> RED (381 green, 1,906 yellow, 3,926 unmeasured); every green
   read. LEFT: the WEEKLY RUN (~10-08) must `acquire --keys osm_land_use`,
   run runbook step 7b, and pass `--institutional` to the bridge -- then
   check `institutional_were_scanned` is 0 in assign's summary. Remove
   this item once that run is promoted.
48. [scan: NO -- proved] **PRIORITY -- scans must survive a crash without losing time (Steph
   2026-10-07: "we're moving quick and stacking a lot of changes between
   runs. Don't want to lose time to avoidable problems").** (a)-(f)
   SHIPPED 1762716a + 66545fb6 2026-10-08 (deployed, smoke passed, CI
   green): the bridge command keeps an answer cache by default
   (`bridge_cache` beside `--out`; `--no-cache` off), so a re-launch
   resumes; the weekly re-screen is `scripts/flats_weekly_chain.py`
   (runbook §4 + §4b) -- a done-marker per step, `--preflight-only`
   refuses in seconds, a failed or stalled step re-runs up to 3 tries
   (bridge processes halved after a memory kill), stall = the step's own
   group under 60 CPU-s in 20 min (CPU, not new parts: one big lot runs
   30+ min without one), status every 2 min to 114
   `/root/weekly137/status.txt`. Proof 5 on 137 (2026-10-08, scope_A on
   the 10-07 weekly inputs): uninterrupted chain 37.2 min; the sabotaged
   one -- bridge parent SIGKILLed at 16 min (retry at 8 procs, 1,636 lots
   from the cache), then its group SIGSTOPped (stall caught in 3 min, try
   3 resumed 2,515 lots, done at 48.8 min) -- lots SAME, no process left
   behind. CI then caught a minute lost per stall (a zombie counted as
   alive), fixed 66545fb6. LEFT: the next weekly launches with the chain
   (whoever runs it); remove this item once that run is promoted.
49. [scan: YES for (b)-(f), (h), (i)] **The 2026-10-07 weekly (run 65 on snapshot 4, PROMOTED 2026-10-07
   ~14:45 UTC by Steph from the County copy page; prune-runs retired run 59,
   kept 61/63/65; VACUUM FULL of lot_results NOT run -- permission denied,
   24 GB free, owed at the next load): what the one-by-one read found.**
   Run 65 = bundle `data/flats/bridge/2026-10-07_weekly` on 114, assign
   `/root/assign_2026-10-07_weekly` on 137 (code 62b2259d, bridge 7 h 53 min
   at 12 procs). Gate clean (8 rows ok); drift 63 -> 65: 133,872 of 827,770
   answers moved, all `rules`, 0 unexplained (report
   `data/flats/reports/2026-10-07/drift_run65.md`). Best pod per lot,
   if_signed: green 68,044 -> 41,361, red 30,061 -> 72,172. Read by three
   agents (scripts + tables on 137 in `/root/weekly_read/{gains,losses,
   slope_water}/`, compare `/root/cmp1007/`): slope is behind most losses
   (fit, fire, Portland density/coverage/landscaped moves are slope under a
   different `head`); court turning 1723db45 ~2,600 lots; Portland z
   e55c22ee 16,538 lots (red on `colour`, yellow on if_signed via the
   attached-house relief); gains = 43 easement (Beaverton 2,542, Oregon City
   2,012 -- the bound's 3,043/2,230 were colour counts, reconciled), 41
   Gresham 1,470, West Linn historic district 483, corner side-street fits;
   35 CLOSED (every green row carries a fire result); 34 Washington ROW
   verified (7,817 neighbour-zone changes, no new failure); 47 verified
   (`institutional_were_scanned` 0). OWED, false GREEN first:
   (a)+(d)+item 45 DONE 81c3b77b + 84e702de (deployed 2026-10-07; land
   at the next splice or weekly, NOT in run 65): a plan green on the map
   is fire-checked; a tight fit is drawn fitting (half a foot short,
   `drawing.tight`, lot page says "give or take half a foot") so its
   route and pad grade are measured. Bound on 137 over 9,860 tight /
   map-green lots (`/root/weekly_fixes/`, base f2aa1bf3): lots yellow->
   green 529 (every one tight, route <= 150 ft, grade < 5%), green->
   yellow 43 (38 Portland lots fronting an unimproved road, unnamed drive
   or the Tilikum approach -- no truck road, correct; 5 tight fits on a
   5-15% pad -- the item-45 false greens), yellow->red 60 (hose > 150 ft),
   unknown->measured 657 on if_signed. Every gain and loss read.
   (b) 51577bb8 (item 44) not in run 65: 30 lots / 34 rows map-green
   (`item44_false_greens_in_weekly.csv`).
   (c) DONE c98be01d (deployed 2026-10-09; lands at the next splice): the
   hole was bigger than ~12 lots. A corner lot whose code sends the driveway
   to the lowest-class street, with a street line that has no class, was
   screened as if the side street served, unchecked. Now the driveway is
   tried off BOTH streets and the worse answer kept; each plan's access
   line is recorded (bridge-only column `access_json`: rule, street charged,
   why, the ranks read). Steph 2026-10-09: unranked corner = yellow ("yellow,
   then measure"): where only the unranked street's reading misses, the lot
   keeps the measured plan's answer and carries ACCESS-STREET-RANK-UNKNOWN
   (severity 6, closer look); a miss on the measured plan itself stays red.
   Bound over 1,465 lots vs run 67 (every moved lot read): 852 rows
   green -> yellow with the new flag (Washington Co. uninc 636, Beaverton
   87, Oregon City 58, West Linn 37, Wilsonville 31, Milwaukie 4), 10 rows
   already yellow gain the flag, 0 green -> red. The named lots are inside
   those counts. Also in the same code (read lot by lot): paved type-2000
   streets count as fire-truck roads (Portland: 348 rows yellow -> green,
   22 red -> green, hose routes 70-150 ft; private park drives and alleys
   stay yellow), 28 other rows green -> yellow (Milwaukie 20 lose a
   proven-harmless flag; Portland 4, Oregon City 3, Beaverton 2), 7 Portland
   yellow -> red (hose > 150 ft). The lots to splice are listed in
   `/root/fo/scope_yellow.txt` on 137 (1,465, one per line -- Portland and
   Gresham TLIDs hold spaces, never split on whitespace). NEW ITEM 60 ranks
   the streets.
   (e)+(f)+(h) DONE 2dacbe1c (deployed 2026-10-08; lands at the (i) splice,
   NOT in run 65): steep is read on the lot's own ground (a neighbour's bank
   or raised road no longer spills in; a bank's height is walked across the
   lot's own steep cells), coarse-10 m-only steep is YELLOW + SLOPE-STEEP-
   COARSE sev 7, steep takes the blame when it is most of a fit miss. Bound
   on 137 (/root/sf, base 1dcd278c vs final, 93,908 lots): 2,525 moves --
   red->green 537, red->yellow 861 + 838 (h), yellow->green 84; green->red
   29, green->yellow 122 (pad now on 5-15% ground: SLOPE-GRADE), yellow->red
   54; control 0. Every class read; no false GREEN. ~40 new reds sit on a
   4-4.5 ft bank: Steph 2026-10-08 KEPT the 4 ft line. 3 losses are the
   placer landing elsewhere on a bigger envelope (open_space_shape / fire).
   Water flag on overlay slivers (48 lots < 10 sq ft, 194 < 100 sq ft):
   left yellow by item 50 (codes reach 25-100 ft past the drawn line).
   (g) DONE a7243f4f (live 2026-10-07): the lots list says why a design is
   red (every standard missed, worst first) or yellow (the open questions
   at the line), not `head`; the bridge report adds `dominant`. The
   if_signed-vs-map disagreements are the legacy `if_signed` column only --
   the app shows the map colour everywhere; the 16 STREET_UNCONFIRMED
   y->unknown rows traced: their missed standard went away, leaving the
   unconfirmed street alone (map: yellow, ACCESS-STREET-UNCONFIRMED).
   (i) DONE 2026-10-08 -- RUN 67 PROMOTED (agent, clean gate, ~00:40 UTC
   10-09). Splice of 162,717 lots on run 65 (SHA f16f1fd6: 81c3b77b +
   84e702de, 51577bb8, 2dacbe1c; 2cfd13d6 in assign): bridge 6 h 06 min,
   bundle `data/flats/bridge/2026-10-08_49i`, drift
   `data/flats/reports/2026-10-08/drift_run67.md` -- 32,753 answers moved,
   all `rules`, 0 unexplained; gate 8 rows ok. Best pod per lot (map
   colour): green 49,091 -> 50,071, yellow 162,370 -> 153,799, red
   376,354 -> 383,945. Lots moved 13,869: 10,024 outside the scope =
   item 52's too-small/too-narrow yellow->red; inside 3,845, of which
   3,757 the same move a lane's bound predicted for that lot (slope
   movers3, weekly_fixes b_ca283cfa vs f2aa1bf3, rank moves_ABR). 88 read
   one by one (lists `/root/weekly137/` on 114): all two fixes meeting --
   steep ground coming off lets the building sit nearer the street, so the
   hose route drops under 150 ft (S lots), or the new reading ranking picks
   a tight fit that 81c3b77b now measures (R lots); 14 new greens, every
   one with a route <= 150 ft and no steep under the building. 017f63cf
   (50) did NOT land (s5o not re-run) -> the weekly. prune-runs retired run
   61 (kept 63/65/67); plain VACUUM ANALYZE run, VACUUM FULL still owed
   (24 GB free). flats_flags sync run 67 (926,292 opened) + check passed.
   (j) DONE 2026-10-09 -- RUN 69 PROMOTED (agent, clean gate, ~17:55 UTC).
   ONE splice on run 67 carrying three lanes: 57 flatter placement
   (34b42b4f), 58/49(c) one-question (c98be01d unranked corner = yellow,
   Portland type-2000 fire, Rockwood), 52b zone gaps (e91f05a8/30500bd4;
   s4/s5o = /root/zg/Qn = weekly + 1,256 added lots, assign on /root/zg/Nn +
   Qn). Code 97a1bef2, scope 20,336 lots (/root/s49j/scope.txt), bridge
   1 h 38 min at 14 procs; bundle `data/flats/bridge/2026-10-09_49j`
   (re-exported with --quadfit-results = the weekly lots_results.csv: Qn
   holds none, so the first export left quadfit's columns empty -- TRAP for
   any assign on a quadfit dir without lots_results.csv). Drift
   `data/flats/reports/2026-10-09/drift_run69.md`: 3,671 answers, all
   `rules`, 0 unexplained; gate 8 rows ok. Map colour, best pod: green
   50,071 -> 50,008, yellow 153,799 -> 151,010, red 383,945 -> 386,797.
   7,947 design rows moved; every row matched its lane's own bound
   (/root/s57/expected.csv, /root/fo/expected.csv, /root/zg/assign_new)
   except 10 lane interactions read one by one and replayed by the 57
   agent (6 Portland lots green: placement drops SLOPE-GRADE AND type-2000
   roads measure the hose route, 103-149 ft; Gresham 1N3E32BB-05100 green:
   civic-corridor flag gone; Beaverton 1N132CC05200 green->yellow: new
   drive on an unranked street) and 3 Clackamas MR1 lots red by ruling.
   Lists /root/s49j/moves_{s57,fo,zg}.csv on 137. prune-runs retired run 63
   (kept 65/67/69); plain VACUUM ANALYZE run, VACUUM FULL still owed (23 GB
   free). flats_flags sync (33,279 opened, 34,215 cleared) + check passed.
   Splice base for the next partial: /root/bridge_spliced_2026-10-09_49j,
   assign quadfit dir /root/zg/Qn, normalized /root/zg/Nn.
   (k) LAUNCH CHECKLIST, next weekly (~2026-10-14; audited 2026-10-09,
   chain gates c2650098 on flats/weekly-gates). BEFORE launch, on 137:
   - Acquire the three zoning layers into the weekly's snapshot (absent
     from 2026-10-07; the preflight refuses without them): `cd
     /root/code/vicinitideals && PYTHONIOENCODING=utf-8 .venv/bin/python
     -m flats.ingest.acquire --snapshot <date> --keys zoning_canby
     zoning_sandy zoning_estacada` (scratch fetch 2026-10-09: 49 / 128 /
     38 features). A full acquire at a new date fetches them anyway.
   - Once item 60 merges, the same line with `--keys osm_roads`
     (Geofabrik Oregon ZIP, 0.45 GB; 255,488 roads in the scratch fetch).
     The preflight then demands it, but that branch's bridge does NOT
     refuse without the file -- streets just stay unranked (yellow).
   - `--preflight-only` first; it must name no problem.
   - Launch line (runbook §4) with `--transit-reuse
     data/flats/transit/2026-10-07_weekly/distances.parquet` (Tigard,
     Cornelius and Estacada lots are measured fresh).
   - Run the WHOLE chain: quadfit must re-run (the 10-07 s5o lacks the
     ten `ovl_*_site` columns of item 50; the chain now stops `--from
     bridge` on it with "REFUSED before bridge").
   AT LOAD (114): VACUUM FULL of lot_results (owed since run 65).
   AFTER THE RUN, before promotion:
   - 51: Tigard + Cornelius colour counts vs 51's bound; Cornelius R-10
     lot 1N335CD01200 screens (not JURISDICTION_OFF).
   - 47: assign's report shows `institutional_were_scanned` 0 -> remove 47.
   - 50: the 42 green -> yellow movers (West Linn 19, Gresham 15, Tualatin
     6, Troutdale 2) carry RESOURCE-PERMIT on a `*_site` key; compare with
     `/root/tw/` on 137.
   - 53: Estacada lots screen (no 1 m tiles: coarse steep = yellow sev 7).
   - 48: remove once this weekly is promoted.
   - 50: the twins are already on the map since run 70 (below); the weekly
     only re-measures them natively -- expect ~0 new RESOURCE-PERMIT moves.
   (l) RUN 70 PROMOTED 2026-10-10 ~04:47 UTC (agent, gate clean): ONE joint
   splice on run 69 carrying 59 (county roll, assign-only), 60+63 (quiet
   street = Metro AND OSM; a one-street bend is not a corner; curve clauses),
   52 slice 1 (Gladstone Portland Ave) and 50 (ovl_*_site twins copied into
   /root/js/Qn s5o). Screen code 7f354aa4, splice 7f68b122 (a splice may add
   a DECLARED column: `--added-columns`, recorded in the lineage). Scope
   47,135 lots (/root/js/scope.txt), bridge 52 min at 14 procs, tag
   2026-10-10_49k. TRAP FOUND: the 60+63 lane's scope files were built with
   `.read().split()`, which cuts spaced Multnomah TLIDs in two; the bridge
   drops the pieces silently (scope rebuilt line by line). Moves, best design
   per lot (4,242 lots, 0 outside the scope): 59 = 3,117 (112 green + 3,005
   yellow -> red), exactly its bound; Gladstone 23 green -> yellow (51
   flagged), exactly its bound; 50 = 43 green -> yellow (RESOURCE-PERMIT);
   60+63 = 1,051: 228 green -> red and 446 yellow -> red (every one
   CORNER_READ_AS_BEND), 367 yellow -> green (354 rank now known, 10 slope,
   4 Gresham civic-corridor clears from c98be01d whose scope missed them),
   7 green -> yellow, 3 red -> yellow. 1,032 of the 1,051 match the lane's
   last bounds lot for lot, 0 disagree; the 19 its broken scope never saw
   (Troutdale 14, Fairview 1, Gresham 4) were read one by one: one street
   name on every street edge (cul-de-sac bulbs / curves), cities silent ->
   the ruled bend reading. Map green 50,008 -> 49,960, yellow 151,010 ->
   147,262. Drift 69 -> 70: 2,067 answers moved, 0 unexplained. prune
   retired 65 (kept 67/69/70); VACUUM FULL DONE (lot_results 8 GB, 26 GB
   free). NEXT SPLICE BASE: /root/bridge_spliced_2026-10-10_49k with s4/s5o
   /root/js/Qn (twins) and assign inputs /root/js/Qn + /root/zg/Nn;
   bridge `--sources /root/js/snap_osm` (moved from /root/fo). 137 CLEANED
   2026-10-10 (Steph asked): every other scratch dir and worktree under
   /root is gone (names in /root/cleanup_2026-10-10/deleted.txt), so
   /root/fo, /root/tr, /root/wk*, /root/s57, /root/s49j paths quoted in
   older items no longer exist; 58 -> 36 GB used.
50. [scan: YES (greens only turn yellow; nothing gains)] **DONE 017f63cf (deployed 2026-10-07): an older
   no-build water area keeps the lot a closer look once the pod clears it.**
   City codes read: Gresham GDC 5.0703(A)(1)/5.0706(A)/5.0705(A)(3),
   Troutdale TDC 4.311(A), Fairview FMC 19.106.070(A), West Linn WLCDC
   32.060/32.020(B), Tualatin TDC 72.040(3)(c) all owe paperwork on a site
   holding the area -> 10 `*_site` flag twins in overlays.yaml (same layer,
   buffer, clip as the carve) + PERMITS words/cite. Gresham hillside,
   Oregon City NROD, Tualatin WPD no-build and FEMA floodway reach only
   inside the area -> `resource_overlays.CLEARED` (stay green, cite kept);
   test_resource_overlays holds every carve flagged-or-cleared. Bound on
   137 (`/root/tw/`, 327 run-65 lots not red): 42 green -> yellow (West
   Linn 19, Gresham 15, Tualatin 6, Troutdale 2), 285 yellow unchanged,
   nothing else moved; every mover carries RESOURCE-PERMIT on a `*_site`
   key. Lands at the next weekly (s5o must re-run to write the
   `ovl_*_site` columns); a splice on run 65's s5o reads them as nothing
   unless it copies `ovl_<carve>` into `ovl_<carve>_site` first (recipe
   `/root/tw/prep.py`). 49(f) slivers: left yellow (codes reach 25-100 ft
   past the drawn line).
51. [scan: NO new code, check after the weekly run] **Tigard and Cornelius switched on (SHIPPED 2026-10-08; nothing shows until the next weekly).**
   Both cities were encoded but never listed in `flats/config/pipeline.yaml`,
   so every lot was JURISDICTION_OFF (run 65: 18,516 Tigard + 4,182
   Cornelius yellows). Now on; quadfit rows ported from the corpus; Cornelius
   R-10 tax lot 1N335CD01200 read by hand (`lot_zones`). Bound on 137
   (/root/f51, can be deleted), measured lots: Cornelius 381 green / 3,406
   red / 47 yellow; Tigard 840 green / 15,544 red / 777 yellow; unmeasured
   Cornelius 334 red + 77 yellow, Tigard 824 red + 766 yellow. All 1,221
   greens read: 1,034 ordinary houses, 187 commercial/apartment/public-coded
   (the pipeline ignores existing buildings by design). 34 Cornelius greens
   turn yellow as-if-signed on min density (as designed). AFTER THE NEXT
   WEEKLY: check Tigard + Cornelius colour counts against the bound above;
   R-10 lot 1N335CD01200 should now screen; 4 NO_ZONE + 3 sliver-labelled +
   3 west-side Cornelius county-coded lots stay gated.
52. [scan: lands at 49(i)'s splice or the next weekly; no re-screen, no promotion]
   **Lots dropped before a fit (run 65): 11,427 yellow NOT_MEASURED +
   2,203 yellow GEOM-UNREADABLE.** Bucketed 2026-10-07: 6,951 had no 20 ft
   circle in the outline (quadfit s3 too_narrow_20ft), 2,737 were under 1,000
   sq ft (sliver_area), 1,598 sit in a zone quadfit's rules lack
   (zone_not_in_rules), 140 Multnomah uninc RR (its rules say no fourplex),
   1 no zone (Washington uninc R-24). SHIPPED (2cfd13d6): the first two
   (9,688) plus any lot under 98% of a pod footprint are now RED by
   arithmetic (POD_CANNOT_FIT, bind pod_footprint_area / pod_width); a lot
   arithmetic does not settle stays NOT_MEASURED. BOUND on 137 (old
   2026-10-07 weekly assign vs new, 1,175,630 rows each): 10,028 lots / 20,052
   rows moved, ALL yellow -> red, all previously NOT_MEASURED, zero other
   differences, no green gained or lost (9,688 + 340 small zone_not_in_rules
   lots; 4 of those sit between the two pod footprints and are red on
   pod56x36 only). Read: 8,568 area proofs (max outline area 1,974 sq ft,
   under the 1,976 line), 1,460 width proofs (max inscribed radius 10.0000 ft
   by independent shapely; the pod needs 12.5), 25 multi-part lots where the
   stored area and outline differ -- proofs hold either way. GEOM-UNREADABLE is not
   broken outlines (0 invalid, 0 multi-part, 1,544 with holes): it is the
   complex-shape cap (convexity < 0.80, > 10 edges, pole-like), measured at
   a uniform inset; make_valid / buffer-0 do not apply; only 357 yellow lots
   are held yellow by that flag alone -- left as is. ZONES READ 2026-10-09 (branch flats/zone-gaps, bound on 137 over
   6,017 lots, 48 greens gained, 163 greens lost, every one read; LIVE in
   run 69, promoted 2026-10-09, spliced with 57 and 58/49(c), see 49(j)):
   (a) ZONE_TO_READ and (c) 52b zones are encoded and ported so the pod is
   measured: Gladstone C2/MR, Tualatin CC/RMH/RH/RH-HR/MUC, Milwaukie
   GMU/DMU, West Linn MU, Gresham DCC/DTM, Fairview TCC/VC, Oregon City
   MUE/GI/HC/CI/I/NC, Portland CI1, Wood Village NC, Happy Valley
   MURM/MURX, Multnomah uninc RR/OR/EFU. Gains: Gladstone C2 34, MR 10,
   West Linn MU 3, Tualatin CC 1; the rest measure red. Steph 2026-10-09
   RULED: Milwaukie DMU ALLOWED (design review optional via clear and
   objective standards); Clackamas MR-1, MR-2, HDR RED BY RULING
   (ZDO 1102.01(A) design review) -- the same sentence also makes PMD and
   VA red (agent extended it; tell Steph); 163 green MR-1/MR-2 lots go red;
   Hillsboro ANX stays yellow. SHD/RCHDR/VTH stay unencodable (setbacks by
   compass bearing, ZDO 1005.02(L)) -> item 61.
   STILL OPEN from 52: Gladstone C2 Portland Avenue entrance + 25% window
   rules; Tualatin RH/HR 45 ft minimum height scope, Central Tualatin
   Overlay block lot sizes (Map 10-3), Basalt Creek Parkway 50 ft yard,
   100 ft wetland yard, building separation, MUC 57.400 / Figure 57-1
   height check; Milwaukie Figure 19.304-2, the neighbours block (20 ft
   abuts-residential yards), 19.505.5.E.1, DMU 50 ft parking ban; Fairview
   TCC Halsey storefront map (44 lots), VC stays because of the FLX alias;
   SCMU front setback and densities; Happy Valley / Gladstone leftovers;
   add ZDO Section 1102 to the provenance store. The weekly run must fetch
   canby/estacada/sandy zoning (the bound needed empty placeholders). The
   splice cannot retire lots a re-run drops from s3 (assign keeps a
   measured lot's old row): a bound/splice scope must list those lots
   explicitly, as the 805 MR1/MR2/PMD/VA lots were here.
   LEFTOVERS TRIAGED 2026-10-09 (run 69): only Gladstone C2 Portland Avenue
   reaches greens (23 of 34 C2 greens abut the avenue). STEPH RULED
   2026-10-09: YELLOW until known -- avenue-facing entrance + 25% ground-floor
   glass (GMC 17.18.050(3)(b)+(c)) is a fact about the building the catalog
   does not hold; no assumption about the pod. Everything else touches 0
   greens: ZDO 1102 into the store, Milwaukie neighbours block, then recorded
   refusals / measured-zero; Tualatin block tracing + RH-HR min height
   deferred (0 lots). Assigned to the "Remaining zone codes" agent.
   Slice 1 DONE ef4b272f: Gladstone C2 within 60 ft of the Portland Ave
   centreline is held YELLOW under FACT-ALONG-PORTLAND-AVENUE (GMC
   17.18.050(3)(b)+(c)); bound 23 lots green->yellow, 51 lots flagged, 0
   other moves (/root/wk52/b_after). LIVE in run 70 (49(l)): 23 + 51 exact.
   52 STILL OPEN leftovers: DONE 2026-10-09 (slices 1-4: b9ced2fe, 9eb9f618).
   Gladstone C2 Portland Ave yellow; ZDO 1102 stored and cited (prefab
   exemption = single-family only, ZDO 202); Milwaukie neighbours block
   (R-MD/R-HD true; DMU/GMU street yards held on across-street; bound 0
   colour moves, 14 abutting lots take the 20 ft yard, all already red;
   13 abut R-HD only -- the letter of 19.504.4 names R-MD, R-HD read as the
   tighter side). OFFERED, not done: read faces_residential_zone_across_street
   per street line outside Portland so those street yards can be released
   (0 lots today, all DMU/GMU red). Tualatin Basalt Creek 50 ft yard
   measured-zero (2,234 ft to the built parkway; re-measure when the
   extension is mapped or on annexation); Central Tualatin Overlay blocks
   and RH-HR min height DEFERRED (0 lots, all red). "Happy Valley /
   Gladstone leftovers" had no list behind it: every refusal there
   loosens or does not reach a 4-unit lot.
53. [scan: YES (Estacada layer is drafted and unscreened; it lands at the next weekly after the acquire of its zoning dataset)] **Canby and Sandy are RED in every zone (Steph's by-right-only ruling,
   2026-10-08); Estacada is encoded; Molalla is blocked on HUMAN_TODO 29
   (Steph's PDFs); Forest Grove stays blocked on HUMAN_TODO 28.** Canby's only
   path to the pod is a Type III site and design review, Sandy's is a Type II
   design review: neither is by-right, so `quadplex_allowed` is false in
   Canby R-1.5, R-2, C-R and Sandy R-1, R-2, R-3 (standards kept, each zone
   note opens "RED BY RULING" so the ruling can be reversed). Estacada admits
   C-2, CMU, R-3 (townhouse lots only) and NCR (only within 200 ft of Eagle
   Creek Rd or Hinman Rd, measured by the new `near_named_street_200ft` fact
   in `flats/geom/named_street.py`); no design review in those zone chapters,
   only the 16.132.015 planning-staff review, which Steph ruled by-right.
   Everything is `draft`. Checks Steph asked for (2026-10-08): wetlands
   overlay = the NWI layer already applied; historic overlay = inventoried
   buildings only; 33% geotechnical = already stricter in slope.yaml (15%).
   (a) BOUND RE-RAN 2026-10-09 on 137 at 5f4c2e9f (the dwelling-in-band fix;
   tree quadfit_2026-10-07_fg53e, bridge /root/bridge_fg53e). Estacada: 261 lots
   admitted, 260 bridged (the 261st, 34E20AC00403 at 825 NW Wade St, is an
   institutional lot left out of the scan). Best design per lot: C-2 3 green/27
   red, CMU 6 green/4 yellow, NCR 7 green/4 yellow/139 red, R-3 70 red. Every
   non-red NCR building now sits 134 ft or less from Eagle Creek Rd / Hinman Rd
   (was 335 ft on 34E17 00901, now 37-64 ft); the C-2/CMU distances are not a rule
   there. The s4 compare against the 10-07 weekly shows 805 lost (Clackamas
   MR-1/MR-2/PMD/VA, red by main's design-review ruling) and 22,724 gained (Tigard
   17,230, Cornelius 3,891, Gresham 479, Tualatin 416, Estacada 261, Gladstone 224,
   Milwaukie 150, Fairview 48, West Linn 25): all main's zone-gaps lane, none from
   this branch. bound_cols.py then crashed on the column compare, so
   "existing lots unchanged" was NOT proven this time; the first bound (1d7209b0)
   proved 0 lost / 261 gained. Nothing is spliced or promoted; Estacada reaches
   the map at the next weekly (or a splice Steph's coordinator schedules, built
   on /root/zg/Qn).
   DECISION (coordinator, 2026-10-09): NO splice. Estacada lands at the next weekly;
   the weekly runbook must acquire Estacada zoning (its zoning dataset is not in the
   snapshot yet and Qn holds none of its lots). Existing-lots-unchanged proof, by
   reading not by bound: the new reach-off logic is gated on BAND_ZONES, which holds
   only (estacada, NCR), and every other row gets None; near_named_street_200ft is
   consumed in one place in all of flats/config (estacada.yaml, NCR quadplex_allowed).
   No other zone or city carries either, so no other lot can move.
   (b) Molalla: 7 of 11 chapters (5.1 came down; 2.3, 2.4, 3.2, 4.4 still 429, retried every
   10 minutes) -- layer files are parked outside the repo again unless all 11
   land (copy in /tmp/fg53/molalla_parked + the new 5.1); gate already read:
   admits R-2, R-3, R-5, refuses R-1, C-1, C-2, M-1, M-2, PSP; ALSO check
   whether those zones need design review -- by-right only); (c) NCR "major
   collector" half of EMC 16.25.020 is unmeasured (no street-class map for
   Estacada; Currin Rd looks like one) -- lots near it screen RED; add the
   name to STREETS in named_street.py once Steph confirms (HUMAN_TODO 30 q5);
   (d) Airport Safety overlay (16.54) zone map, side-line PUE (the code only
   says the city MAY require 10 ft), parking facing Eagle Creek Rd and the
   Currin Creek 70 ft strip: Steph's answers pending in HUMAN_TODO 30 q1-4;
   (e) minimum density 8.712 du/ac in C-2, R-3, NCR on the unit-lot path
   (the quote check wants a printed operand; needs a form that holds half of
   a per-dwelling area); (f) the Canby/Sandy doubts (design review, 20 ft
   yards, 13 du/ac, overlays) are MOOT while the by-right ruling holds;
   Estacada's R-3 townhouse-only reading and the MMU Council-master-plan
   refusal were re-read 2026-10-08 against the text and stand; the Downtown
   zone (D) could be encoded with the named-street tool (fourplex outright
   if it does not face Broadway/Main/OR 224, north of OR 224, 16 du/ac) --
   waiting on Steph's yes/no.
54. [scan: NO (warn-only: changes no rule and no answer; the fixes it leads to land at the next weekly)] **Code-change
   reader on the Claude API credit ($100/month). Steph 2026-10-07 picked this one and
   DECLINED the other two offered (a second reader beside signing; moving the finance-side
   email/pro forma reading off local Ollama).** Why it matters: nothing re-checks the codes
   today -- `fetch --all --check` (flats/provenance/fetch.py, the corpus watch) exists but no
   schedule runs it -- and Steph has done NO sign-offs (told 2026-10-07), so the map is
   as-if-signed and an amended number keeps answering from the old words until somebody
   happens to re-read. Plan, Steph to approve before building:
   (a) Cadence: WEEKLY celery beat task on 114, built like `flats_probe_task` (warn-only,
   writes rows, changes no rule): fetch every declared document (~680) into memory, compare
   with the store in the image, store nothing. Weekly because detection costs no credit;
   daily only invites the 429s Municode already throws (pace per host; a 429 = "not checked
   this week"; 3 misses in a row = warn). Early Monday Pacific; nothing runs on 137.
   (b) Proactive poll, reactive AI: the model runs only on what the sweep finds. Free
   deterministic pass first: a value whose every cited line survives byte-for-byte
   (`repoint.survivors`) or word-for-word (`loose_line_map`, a republish) is "moved, words
   unchanged" -- no call. Only values whose own lines changed are sent, one request per
   changed document (old slice + new slice + all its affected values). One city changing
   >20 documents in a sweep is a reformat, not an amendment: no calls for that city until
   Steph says. Later, not v1: DLCD's notices of proposed amendments (cities notify DLCD
   before the first hearing -- confirm the feed is public and readable) as early warning
   that never changes an answer.
   (c) Code checks the model before anything is queued: structured output per value =
   unchanged / changed (new number) / removed / cannot_tell + the new sentence VERBATIM.
   The quote must exist in the fetched text and the new number must appear in it, else
   cannot_tell. Stricter/looser is computed from the field's min/max sense, never asked.
   The model never signs and never edits YAML.
   (d) Interim map (Steph's call; recommended): stricter or cannot_tell -> greens whose
   stored room on that check (check margins 7dc34722) is less than the change -- every
   green in the zone for cannot_tell -- get a "city changed this rule, being re-read" flag
   that shows yellow until fixed; looser -> no colour change (a missed lot, not a false
   promise); unchanged -> nothing. Display-only if the flag tables can carry a colour
   without a re-screen (check); otherwise it rides the next weekly.
   (e) Who acts: with no sign-offs every number is a draft, so a changed number is
   ENCODING work, not review: findings land on an agent work list ("do the next thing"
   picks it up), the agent re-reads, runs `fetch --refresh --repoint`, fixes the encoding,
   the next weekly moves the answers. Only a change to a number Steph HAS signed goes to a
   Steph queue (old/new sentence with the change marked, our number, the model's reading,
   greens at risk; Still right / Changed to X / Needs a closer read; stricter-with-greens
   first). Resend email only on weeks with findings, plus a Lots-page banner like the
   county probe's. A backlog is safe by construction: (d) keeps at-risk greens yellow while
   it waits, so waiting costs missed lots, never a false GREEN. For when signing starts:
   an inbox signature hashes the quote ADDRESS, not the words, so an amendment at the same
   line numbers leaves it standing -- the watch must mark those rows too.
   (f) Credit: the watch has FIRST CLAIM, always. Expected a few dollars a month (~10-15
   cents per changed document, claude-opus-5 at medium effort through the Batches API, half
   price, results within 24 h). Even every document we hold changing in one month roughly
   fits one month's credit, so the watch alone cannot carry a backlog from month to month.
   Background work (item 55) only spends above a sliding floor: $40 to day 21, $20 until 3
   days before reset, $5 in the last 3 days (last batch submitted 2 days before reset).
   Ledger row per call; hard cap = the credit, set in the Anthropic console. If the watch
   still runs dry (a mass republish): findings queue "not pre-read", count as cannot_tell
   for (d), and are read first after reset, before any background work. No Ollama
   fallback -- a missing note is safe, a wrong "unchanged" is not. Assumed: unused credit
   does not roll over -- confirm, and confirm the reset day (calendar month or billing day).
   (g) Model by test, not assumption. Steph asked whether comparing against our encoding
   lets model and effort drop. The comparison is narrower than encoding, but our errors
   live in READING the text (wrong column, short headers, footnote markers, orphaned
   numerals), which the structured side does not help, and the costly miss is one-sided
   (false "unchanged" = possible false GREEN); at this volume the saving is a dollar or two.
   Answer key: real past refreshes in git (the Gresham 4.1400 renumber etc.) + planted edits
   on real cited passages (one number changed, a table column swapped, a pure reformat,
   untouched controls). Run claude-opus-5 and claude-sonnet-5 at low/medium; ship the
   cheapest with zero missed planted changes and zero unverifiable quotes. Test costs a few
   dollars. Before any of it: confirm the credit covers an API key the app can use; key in
   VM 114 .env only.
55. [scan: NO (nothing it writes reaches the rules or the map)] **Expansion scouting on the
   credit item 54 leaves (Steph 2026-10-07: underspend is likelier than overspend -- use the
   month's remainder on proactive expansion that runs in the background and waits until we
   choose to encode a place).** All 28 encoded layers are tri-county; the market is all of
   Oregon (~240 cities, 36 counties). Per place, cheapest step first: (1) find the code --
   `flats.provenance.discover` (free, codifier URL shapes); only on a miss, the model with
   web search; (2) the model reads the table of contents and picks the chapters holding
   the zones, use table, dimensional standards, parking and definitions (the step
   discover.py says still needs a reader); (3) gate + headline read: which zones allow 4
   attached townhouses outright / with review / not at all; min lot area, width, depth;
   setbacks; height; coverage; parking; density; obvious blockers (design review, master
   plan, overlays) -- every number with a verbatim quote the app checks exists, as in
   54(c); (4) where the county publishes its lot and zoning maps (outside tri-county there
   is no RLIS; getting that data is its own task). Output: one "scouted, not encoded" card
   per place in the app DB (not the repo; nothing loads it as a rule) and a ranked list
   (zones that admit the pod x residential land x distance -- Steph sets the weights).
   Order: nearest first (Columbia, Yamhill, Marion, Polk ...), counties' unincorporated
   codes after the cities. Proposed model claude-sonnet-5 (Steph to approve): a rough cut
   where a mistake costs a wrong priority, never an answer, because encoding re-reads
   everything and uses the card's numbers only as a cross-check. Rough cost well under a
   few dollars a place, so the whole state fits in a few months of leftover. Scouted
   places join 54's free weekly check; a change since scouting marks the card "re-scout
   before encoding". Once the state is scouted the leftover goes to re-scouting changed
   cards, then a reading list + doubts list (the item-53 kind) for the top-ranked places.
58. [scan: YES] **Yellows held by one measurable question (offered 2026-10-08;
   first pass DONE c98be01d 2026-10-09; LIVE in run 69).** Run 67 best-pod yellows held by a
   single flag: FACT-AT-STREET-END 633, ACCESS-STREET-UNCONFIRMED 359,
   MEASURE-FIRE-ROUTE 334, FACT-CIVIC-CORRIDOR 141, PARKING-STRIP-UNCONFIRMED
   97. MEASURED: MEASURE-FIRE-ROUTE (paved type-2000 streets now count as
   truck roads: Portland 348 rows yellow -> green; see 49(c)) and
   FACT-CIVIC-CORRIDOR for Rockwood (Gresham's Rockwood Design District
   drawn from the city's own layer, `rockwood_design_district`; 290 rows /
   ~148 lots yellow -> green: CMU 197, MDR-24 60, MDR-12 29, OFR 4; SC/SC-RJ
   and CMF stay yellow; scope `/root/fo/scope_rockwood.txt`, inside
   scope_yellow.txt). CANNOT BE MEASURED from data we hold, left yellow:
   - FACT-AT-STREET-END (Gresham, 789 per-design lots): Table 4.0131 note 5
     numbers are not encoded and the street-class layer cannot separate
     Minor Access Streets.
   - ACCESS-STREET-UNCONFIRMED (441): the only road line is a private drive
     or lies across someone else's land; no map says whether the lot abuts it.
   - PARKING-STRIP-UNCONFIRMED (213): OAR 660-046-0220(2)(e)(E) is an open
     reading of law, not a fact on the ground (Steph ruled yellow flag
     2026-10-04).
   - FACT-CIVIC-CORRIDOR (the rest): Gresham's own corridor map is the
     source, and Glisan / 162nd are not on it.
   Counts above are per design; the best-pod counts differ.
59. [scan: YES] **Tracts, zero-value parcels and public county codes show GREEN (found 2026-10-08
   reading item 51's gains; the leak already exists in every city).** The
   institutional rule works by map overlap only; no county property code or
   value check backs it. Missed: land-and-building-value-zero tracts (e.g.
   Tigard 2S111CD01100 = Summerfield Golf Course, 100% overlap, not in any
   institutional map; 2S107DA12900, 2S101AC90000, 2S111DA24400; Cornelius
   1N334DC90000) and public-looking codes 960 (parks/open space), 910, 940,
   980, 990. Live run 67: 153 zero-value greens + 159 9xx-coded greens of
   49,091. Churches/charities (911, 981) STAY CHECKED by Steph's ruling
   (item 47); a golf course is not an institutional category, so ask Steph:
   is a tract / common-area / golf course RED? Then add a tract + zero-value
   (+ public-code) rule, bound over run 67, read every moved lot. Also
   1S133AD02200 (code 911) overlaps Westgate Christian School at 17% only.
   STEPH RULED 2026-10-09: ALL RED -- HOA tracts, common areas, open space,
   golf courses and zero-value parcels are RED and never scanned, like
   schools and parks; churches and charities stay checked (item 47).
   Assigned to the zone-gaps agent: rule + bound + read every moved lot.
   CODE LIVE bfc7dee9 (2026-10-09; rules 48aed13d on c787f79f). THE MAP WAITS
   on the joint splice with 60+63 (ONE splice on
   /root/bridge_spliced_2026-10-09_49j). Four tiers, first hit answers
   (flats/config/roll_red.yaml, flats/geom/roll.py): public land (Washington
   only, codes x20/x30/x40/x50/x60/x70/x90; the x1 variants stay screened),
   tract (zero value + tract-style parcel number), open space (zero value +
   8xx or 0x5), no address (zero value + blank / NO SITUS / LEVY CODE). A bare
   no-address lot is SPARED (stays screened) when 3 or more OTHER lots built
   in 2021+ (county YEARBUILT) are on the same tax map page (parcel number
   less its last 5 characters) AND within 500 ft edge to edge; no year, no
   geometry = red. Bound (assign alone, run 69 -> assign_v4 on 137
   /root/tr/assign_v4): 3,117 lots turn red = 112 green + 3,005 yellow
   (Clackamas 19/1,030, Multnomah 35/251, Washington 58/1,724) -- LIVE in run
   70 (49(l)), 3,117 of 3,117 exactly; 635 spared
   (190 x1 codes + 445 near new houses; 163 more went back to red under the
   500 ft line). 4 spared greens read: all leftovers beside new
   subdivisions. SPLICE NOTE: assign needs no new file; the roll columns are
   already in the normalized lots table (PROP_CODE, LANDVAL, BLDGVAL,
   TOTALVAL, ASSESSVAL, site_address, YEARBUILT, wkb). Re-run
   `python -m flats.ingest.assign --normalized /root/zg/Nn --bridge
   <bridge> --quadfit-dir /root/zg/Qn --snapshot-date 2026-10-01` from a
   checkout at bfc7dee9 or later; lots that turn red need no re-screen, the
   spared ones already hold run 69 rows. The weekly chain is unchanged: the
   institutional step reads the same lots table.
   TIERS (agent count, run 69 green/yellow): (1) WashCo public codes
   92x/94x-97x/99x per OAR 150-308-0310; (2) $0 + tract-style number;
   (3) $0 + recreation/open-space code; (4) $0 + no street address --
   all RED. (5) $0 WITH a real street address (~1,100 lots, ~55 green;
   sample = new splits not yet valued): STEPH RULED 2026-10-09 "screen
   them normally" -- no red, no flag. Multnomah exempt-by-value (10,041)
   untouched: cannot tell a park from a church.
   BOUND (assign-only over run 69, 02041372): 3,752 lots -> red (152 green,
   3,600 yellow), nothing else moved. STEPH RULED 2026-10-09 on the two
   risks: (i) WashCo "x1" public codes (921/941/943/951/961/971/991/993,
   190 lots, real buildings + values, housing-authority/nonprofit) STAY
   CHECKED -- only bare-land x0 codes go red; (ii) $0 + no-address lots in
   blocks with 3+ neighbours built 2021 or later (~173 yellow + some green)
   STAY CHECKED as possibly new lots. Cemeteries (93x) red; student
   housing (90x) checked. Re-bound after the change, then ship.
60. [scan: YES] **Rank the unranked corner streets (opened 2026-10-09 from
   49(c); Steph: "yellow, then measure").** In the current bound 634 lots
   have a corner street with no class (60 street names, 69 street lines;
   an earlier check counted 351 lots with no rank on either side). Metro's
   street file has no street at all beside 615 of the 634 lots (1,502 of
   1,517 unranked street lines have none beside them) and the county map
   draws classified roads only, so an absence of a classified road is not a
   reading. Today each such corner lot is yellow (ACCESS-STREET-RANK-UNKNOWN,
   852 rows). Measure it from a real second source: (1) OpenStreetMap
   `highway=` category (the coordinator measured the county: 18,867 drivable
   ways, residential 11,644 / tertiary 2,718 / secondary 1,789 / primary
   1,457 / trunk 565 / unclassified 409 / living_street 133; lanes= on 1% of
   residential and 54-83% of busy roads, width= almost never, no traffic
   volume) -- match each unranked street line to an OSM way (name, then
   nearest parallel centreline within 60 ft), rank by category. A `service`
   way is never a ranked street: an edge with only a service way beside it
   stays unresolved. Known disagreement to leave unresolved under any rule:
   Farmington Rd (county Neighborhood Route, rank 1, vs OSM primary).
   (2) the county's own road centreline layer; (3) the street gap in the
   taxlot fabric. Steph's call: does OSM count as the second source for the
   two-source rule? FALLBACK only, needs Steph's yes: "no Metro line and no
   classified road within 300 ft = local" (relaxes the two-source rule). Then
   bound over the 852 rows (`/root/fo/scope_yellow.txt`), read every lot that
   turns green.
   OSM position pass + dig into the empty edges (2026-10-09, read-only,
   scripts `/root/fo/osm_match4.py`, `osm_dig.py`; not wired into the screen).
   Matching each unranked street edge to the nearest OSM way within 60 ft
   that runs alongside it (within 25 degrees) gives, over the 634 lots: 151
   lots with EVERY unranked edge on a residential-or-above way; 13 lots with
   an arterial or collector edge; 23 with an edge that has only a service
   way; 466 with an edge that has no OSM way (874 edges); 15 with an edge
   reading mixed classes. THE 874 EMPTY EDGES ARE REAL STREETS: 855 are
   street edges (RLIS minor residential, TYPE 1500, within 50 ft) and 19 are
   private drives (TYPE 1700/1800, on 10 lots); 867 of 874 have an OSM way
   within 60 ft (848 residential, 5 secondary, 2 tertiary, 19 service) at
   the same distance as the RLIS line. They failed only the alongside test:
   532 are under 25 ft long (241 under 10 ft), short side edges or chords of
   a bend that run toward the street, not along it. Across them: 729 right-
   of-way, 80 gap in the fabric, 65 another lot. Without the alongside test,
   448 of the 466 lots have residential-or-above OSM on every empty edge (an
   upper bound: their other edges' service/mixed readings are not applied);
   Kinnaman Rd, West Union Rd, Oleson Rd and NW 143rd Ave touch 6 of the
   lots with secondary/tertiary. BIGGER FINDING, NOT VERIFIED: only 556 of
   the 634 yellow lots have two street edges of 25 ft or more; 68 have one
   and 10 have none, so ~78 may not be real corners (cul-de-sac or curved
   fronts whose short chords counted as a second street) and their yellow
   may be wrong. Read those 78 before any ranking rule is wired.
   READ OF THE ~78 + THE "615 vs 855" CONTRADICTION (2026-10-09, read-only;
   nothing in shipped code changed; scripts `/root/fo/rank_why.py`,
   `rank_fix.py`, `corner_read.py`, `county_corner.py`, what-ifs `bound8.sh`
   `bound9.sh`). (a) THE CONTRADICTION: same cause, not the same test.
   "615 lots have NO Metro street beside the lot line" is true OF THE RANK
   MAP, not of Metro's file: `load_class_maps` (flats/geom/street_class.py,
   `if not g.intersects(zone): continue`) keeps only Metro streets within
   210 ft (150 corridor + 60 front reach) of a classified road. Washington
   County's map lists classified roads only, so every local street farther
   than that is cut out BEFORE the rank lookup, and the lookup finds nothing
   beside the lot. The "855 of 874 are Metro streets within 50 ft" count
   reads the full file. Of 2,145 unranked edges, 1,440 have no map street
   within 60 ft (the clip); ~626 more fail the alongside/bearing test
   (`corridor._fronted` -> `_abreast`, mostly short side edges and chords).
   (b) A METRO-ONLY FIX EXISTS, NO OSM: skip the clip when the map has
   `unlisted` set (one line; the design already says "a street the county
   map leaves out is local where Metro agrees"). What-if over the 1,465
   scope lots (`bound_noclip`): 0 changes to any already-ranked edge (0 of
   2,675 on the 634 lots; 0 of 5,838 on a 2,500-lot WashCo sample), 1,541
   of 2,145 unranked edges (72%) rank local, 449 rows / 445 lots go
   yellow -> green, nothing goes red, nothing green changes, `fits` and
   slack identical on every row. ~604 edges stay unranked (the short-chord
   and non-alongside ones). It is the already-shipped two-source design
   (county map + Metro type), so it is a bug fix, not a widened gate --
   but ASK Steph/coordinator to confirm that reading before it ships; it
   would lift 445 of the 634 yellows on its own. (c) THE ~78 NOT-CORNERS:
   read from the edge list, street names and nearest dead end (not from a
   picture). 14 are true corners (two named streets on separate runs, six
   with a second frontage under 25 ft); 64 are ONE street read as two:
   27 cul-de-sac/bulb fronts (20 `fronts_cul_de_sac` measured, 7 with a
   dead end beside and the flag unset), 5 only short chords (no edge >=25
   ft), 22 curved single fronts (turn 33-131 degrees), 10 a straight front
   plus a sliver edge of 15 ft or less. No flag pole among them (a flag
   lot is tier irregular, not corner). Washington County's CDC defines no
   corner lot (definitions block, "CORNER LOT: SILENT"), so no legal
   definition makes a bend a corner there.
   See item 63 for the step that makes it, the county-wide count and the fix.
   STEPH RULED 2026-10-09 ("yes, when both agree"): a street line counts
   as QUIET only when Metro's unclipped file AND OpenStreetMap both call it
   residential/local. A busier OSM class (Kinnaman, West Union, Oleson,
   NW 143rd) or any disagreement (Farmington) stays unranked = yellow;
   `service` never counts. OSM becomes an acquired dataset (Geofabrik
   Oregon extract) in the weekly snapshot; bound + report moves first.
   OSM RELEASE NAME DONE 2026-10-10 (merged flats/osm-release-name): the
   manifest names the dated Geofabrik file a run read; the probe compares it
   as an `ok` finding (daily files are expected, no Metro banner).
61. [scan: YES, after the weekly re-screen] **Which way does each lot line face
   (Steph 2026-10-09: BUILD it).** Clackamas ZDO 1005.02(L) sets setbacks by
   compass bearing (north/south/east/west), so SHD, RCHDR and VTH cannot be
   encoded until each lot line carries a bearing. Measure the bearing per
   lot line, add it as a per-line field, then encode those three districts.
   Not part of branch flats/zone-gaps; start only after the weekly re-screen.
62. [scan: YES] **Roof shape: teach the screen gable vs flat (offered 2026-10-09
   after Steph asked what a gable costs in height; nothing signed).** The
   design holds ONE height (26 ft) compared straight to every cap, so it
   cannot tell a gable from a flat roof. Corpus read 2026-10-09: a gable is
   measured at its MIDPOINT (eave-to-ridge average) in Portland, Beaverton,
   Tigard, Hillsboro, Cornelius, Sherwood, WashCo, MultCo, Fairview, Oregon
   City, Gladstone, Wilsonville, Troutdale (IBC "average height of highest
   roof surface"), Milwaukie (<=12:12; steeper = peak), ClackCo (defers to
   the state building code, text not stored); at the PEAK in Gresham
   (3.0100 "highest point of the structure"), West Linn 41.005, Happy
   Valley 16.12, King City 16.24; no stored definition for Tualatin, Wood
   Village, Durham, Rivergrove. Shed roofs steeper than flat (2:12 PDX/
   Tigard, 4:12 Beaverton) = highest point. Build: Design gets eave_ft +
   ridge_ft + roof form; a per-layer `height_measured_to` (midpoint / peak
   / unknown -> peak); max/min height checks read the measured figure;
   Gresham 7.0420(G) and Milwaukie side planes read the roof profile
   facing the line. Then `flats.encode.height` prices each roof option.
   Current curve (426,106 lots): only exactly 25 ft keeps everything; 26
   loses Hillsboro's 2-1/2-storey zones (~23,500); >30 loses Portland
   R5/R7/R10/R20 (~148,700 total); >35 loses ~371,600. Wait for a drawing
   with real eave/ridge figures before building.
63. [scan: YES, after Steph rules] **One street bending is read as a corner
   (found 2026-10-09 reading the ~78 of item 60; a CORRECTNESS bug, not only
   a yellow-flag one).** A lot on ONE street whose frontage turns 45 degrees or
   more (cul-de-sac bulb, knuckle, curved front, or a straight front with a
   short sliver edge) is screened as a corner lot. THE STEP: s4 `classify_lot`
   (Lot Analysis/quadfit/s4_edges.py, `street_threshold_ft` 50) calls an edge a
   street when its midpoint is within 50 ft of ANY non-alley centreline -- no
   name, length or bearing test -- then `cluster_bearings`
   (flats/geom/edges.py:193, 20 degrees) makes `Tier.corner` at edges.py:333
   when the edges form two clusters. The only guard is `corner.two_streets`
   (corner.py:92: bearings at least 45 degrees apart), which a bulb or sharp
   curve passes. `is_corner` (corner.py:259) then names a front by
   `front_lot_line_corner` (WashCo: `shortest`), renames the other street
   edges street-side, turns an interior line from rear to side, and the
   access step asks for a rank on each "street" (the 634 yellows). Both the
   envelope and the access reading change.
   REACH (run 69 colours, best design, tier corner AND two streets >=45
   degrees: 21,199 green/yellow lots, 15,137 green + 6,062 yellow): 2,311
   have every street edge on ONE street name (1,078 green, 1,233 yellow;
   2,266 of them one unbroken run; only 232 carry `fronts_cul_de_sac`);
   760 of those have at most one street edge of 25 ft or more (349 green,
   411 yellow). By city (2,311): WashCo 703, Portland 494, Beaverton 271,
   Clackamas uninc. 247, Gresham 104, Oregon City 100, West Linn 82,
   Tualatin 65, Wilsonville 51, Happy Valley 50. Portland, Gresham, Oregon
   City and Beaverton WRITE their corner test (Portland: a curve <=120
   degrees is two streets), so for them a bend can legally be a corner and
   the count is a ceiling; WashCo, Clackamas uninc. and others are silent.
   DIRECTION: it runs the lenient way. What-if (`bound9.sh`, 762 lots = the
   760 + the ~64 not-corners of item 60) treating them as "one street that
   bends" -- the screen's own rule for a turn under 45 degrees (front left
   unnamed, every street edge takes the stricter of front and street side):
   envelopes never grow and 796 of 1,524 rows shrink; 293 of 762 lots change
   colour -- 67 green -> red, 1 green -> yellow, 222 yellow -> red, 3 yellow
   -> green (no rank needed any more). That is the STRICT end; the truth is
   between it and today, so some of today's greens on these lots are
   probably false greens. FIX PLAN, nothing built: (1) where a city's
   definition is written, route the corner question through
   `definitions.decide` for a curve, as Portland/Gresham already do; (2)
   where it is silent, a corner needs two different street names or two
   unbroken runs; one name on one run is a bend and gets the unnamed
   reading; (3) stop the sliver: a street edge under ~15 ft that runs
   toward the street is not a second frontage. Step (2) turns the 67 greens
   red -- STEPH DECIDES: bend rule (strict, 67 greens lost), or keep the
   corner reading and flag it. Ship with item 60's unclipped-streets fix
   (rank edges local where Metro agrees), which clears most of the yellows
   on the same lots. Reads: `/root/fo/corner_sus.pkl` (78),
   `county_corner.pkl` (21,199), `onebend_changes.csv`.
   STEPH RULED 2026-10-09: ONE STREET, NOT A CORNER -- where the city's
   code is silent, one street name on one unbroken run is a bend and takes
   the unnamed reading (steps 2 + 3), accepting ~67 greens -> red; cities
   that write a corner test (Portland, Gresham, Oregon City, Beaverton)
   follow their own words (step 1). Bound + read every moved lot first.
   BUILT 2026-10-09 (branch flats/items-60-63; bound read lot by lot; NOT merged,
   NOT spliced). Where the city's code is silent, a one-street bend takes the
   unnamed reading unless the front is broken: `read_as_bend` = two+ bearings,
   one street name, one UNBROKEN run (flats/geom/frontage_curve.py), and the
   city's own corner words (if any) say "not a corner". Curve clauses are ONE
   angle across the whole frontage: Beaverton BDC 90 = chord angle at the
   foremost point, strict < 135; Gresham 3.0100 = inside curve, total turn
   >= 60 (tangent <= 120); Portland PCC 33.910 + Wood Village WVDC 720.030 =
   tangent <= 120. PORTLAND/WOOD VILLAGE AMBIGUITY: "angles that are 120
   degrees or less" read as TOTAL turn (ruled); the per-bend reading is a
   one-line config change and keeps 44 lots as corners (noted in both layers).
   Oregon City has no curve clause, so a one-street bend is never a corner.
   SLIVER RULE: a street edge < 15 ft turning >= SLIVER_TURN_DEG off the
   longest is ignored ONLY inside a stretch that also holds a real front edge;
   an isolated short piece is a second front (a through lot), so the run is
   broken. +-1 DEGREE BAND (BAND_DEG): digitising error is 0.5-2 deg (0.5 ft
   slip) to 1-4 deg (1 ft), so a lot within 1 deg of a ceiling (Beaverton 135,
   Portland/Wood Village 120, Gresham 60/120) takes the bend reading and
   carries flag CURVE-ON-THE-LINE (sev 1) with bounds (measured, ceiling).
   Band re-bound (80 lots, 160 rows): 4 colour moves -- Beaverton 134.4 /
   134.9 / 134.95 deg: green -> red 1, yellow -> red 2 (each also CORNER-READ-
   AS-BEND); Portland 119.48 deg: yellow -> green 1; flags on all as expected.
   FINAL NUMBERS (best design per lot, vs main or item-60-only): WashCo uninc.
   green -> red 84, green -> yellow 2, yellow -> red 225, yellow -> green 5,
   red -> yellow 1; item-60 gains 374 yellow -> green, all WashCo uninc., 66 of
   them FIT-TIGHT; Clackamas uninc. green -> red 25, yellow -> green 2, yellow
   -> red 36; Portland green -> red 59, green -> yellow 3, yellow -> green 2,
   red -> yellow 1, yellow -> red 13; Beaverton green -> red 4, yellow -> red
   20; Gresham green -> red 4, yellow -> red 20; Tualatin green -> red 22,
   green -> yellow 1, yellow -> red 19; West Linn 14/33; Oregon City 19/1/28;
   others small. Scopes (137): /root/fo/scope_curve.txt (6,809), scope_unb_diff
   .txt (312), scope_band.txt (80). LIVE in run 70 (49(l)); the counts above
   came from a scope that dropped spaced Multnomah TLIDs -- the splice's
   numbers replace them: green -> red 228 (Portland 59, WashCo uninc. 65,
   Clackamas uninc. 25, Tualatin 20, Oregon City 19, West Linn 13, Troutdale
   10, Beaverton 5, Gresham 4, Durham 4, others 4), yellow -> red 446, yellow
   -> green 367. STILL TO DO: the weekly acquire must include `osm_roads`.
64. [scan: NO (a reading exercise; fixes it finds get their own items)] **Measure the
   false-GREEN rate, so "are we converging?" has a number (offered 2026-10-09 when Steph
   asked whether the work ever ends).** Draw a random sample of ~100 GREEN lots from the
   live run (stratified by county/city, not by flag), read each one deeply and blind
   (zoning words, lot shape, access, fire, slope, tract/ownership) and count how many are
   wrong and why. Repeat after each weekly. Also log per fix: greens moved as a share of
   all greens, and whether the cause was a NEW kind of problem or a known kind in a new
   place. Stopping signal to propose to Steph: a week whose fixes move < ~0.5% of greens
   and find no new kind of problem -> switch from hunting to maintenance (code-change
   watch, item 54) + onboarding new territory. Steph to decide whether to run it.
   AGENT INSTRUCTIONS GIVEN 2026-10-10 ("false-green-sample", first round on run 70).
   POLICY QUESTION FOR STEPH (raised 2026-10-10 by the sample): FLATS ignores
   existing buildings by design, so a 6.66-acre Portland CE lot carrying an
   operating 75,050 sq ft commercial building (1S2E02BB  -01100) is GREEN with
   the pod in a corner (quadfit had it red, existing_commercial). Unless it is a
   shopping centre (item 47, red), it is not a false GREEN under today's rules.
   The sample counts such greens separately; ask Steph whether a lot whose
   pod sits on a working building's parking or yard should stay green.
   ROUND 1 DONE 2026-10-10 (branch flats/false-green-sample, data/flats/false_green/2026-10-10/:
   SUMMARY.md, false_green_round1.csv, seed fgs-2026-10-10-seed1, query work/draw.sql). 102 greens
   from run 70 (49,960), 19 cities: 97 RIGHT, 4 WRONG, 1 CAN'T TELL. Weighted false-GREEN rate
   3.4% (about 1,700 lots), 95% range about 1%-10%; 4.8% if the can't-tell is wrong. Portland 0
   of 38; the 4 sit in WashCo unincorporated (2 of 11) and Hillsboro (2 of 3). Kinds: NEW x2 =
   right-of-way dedication to the centre line not taken out of the fit (item 67); KNOWN x2 =
   item 53 (by-right: Development Review) in a new city, Hillsboro, owned by the lane
   flats/hillsboro-review-red (reach 152 of 427 Hillsboro greens). Existing-building POLICY
   class counted apart: 17 of 102 greens carry one (11 non-house); run 70 about 3,000 greens
   (6%) carry a 5,000+ sq ft non-house building, about 900 (1.8%) a 20,000+ one; none counted
   wrong (item 66). CAN'T TELL: 1N2E21AD  -06200, Portland RM1, 50 x 200 ft, red if on Map 120-2
   (item 68). Not read: the 59 PUB greens (maybe item 59's public-code rule). Stopping signal not
   met (new kinds found). Round 2: after items 67 and the Hillsboro fix ship, redraw with a new
   seed and weight the same way (scripts: work/consolidate.py).
65. [scan: YES (a proof run: every answer must come out identical to 137's)] **The Windows PC
   as an idle-time scan helper (Steph 2026-10-09 asked; offered, not started).** Scans are
   CPU-bound (item 46: >14 processes buy nothing on 137; memory only sets how many run at
   once; disk is not a limit -- inputs ~2.5 GB). The Windows PC (i7-11700F, 8 cores / 16
   threads, 32 GB, 355 GB free) is worth ~half of 137. Shape: 137 stays the owner of every
   job; a bound is cut into lot chunks (the bridge already writes per-chunk parts and
   resumes from them); a small helper on Windows, started only when the PC is idle (no
   input for N minutes, low CPU) and stopped the moment it is used, takes chunks, sends
   parts back; a chunk not returned in time goes back to 137. Off/asleep PC = slower, never
   wrong or stuck. Needs: inputs synced to the PC once per snapshot, the same code sha,
   a proof that a chunk scored on Windows equals 137's answer (Windows vs Linux floating
   point), and a cap so the PC never runs hot while in use (item 32). ~2-4 days of agent
   work. Steph to decide; measure the 137 queue first (46(d) lockwatch on 137,
   /root/lockwatch.log, every 5 min since 2026-10-10).
66. [scan: NO for (A); YES for (B)] **A price check beside the fit (Steph 2026-10-10: "Do we
   not have a financial screen? If there's a large commercial use ... redevelopment wouldn't
   support").** No: FLATS answers legal + physical fit only and ignores existing buildings by
   design; nothing compares what a lot would cost with what a 4-home pod can pay for land.
   The county's land, building and total values and the last sale price are already in the
   normalized lot table for every lot (RLIS LANDVAL/BLDGVAL/TOTALVAL/SALEPRICE). Run 70 greens
   (49,960): county total value > $1M 7,994, > $2M 3,324, > $3M 2,123; building worth more than
   the land AND total > $1M 5,143; ~3,000 carry a 5,000+ sq ft non-house building, ~900 a
   20,000+ one (item 64's sample: 1S2E02BB  -01100, a closed 75,050 sq ft big box, $5.8M sale
   2020). Offered: (A) SHOW, don't screen -- a likely-price figure and an "over budget" label
   on every lot + a Lots-page filter, colour unchanged; (B) SCREEN -- over budget = YELLOW
   (never red: an owner may sell part of a big lot). Either needs Steph's land budget per pod
   (dollars a 4-home project can pay for land, maybe by city). Kept OUT of the fit colour by
   default so "can it be placed" stays honest. Steph to choose (A)/(B) and give the budget.
   STEPH RULED 2026-10-10: (A) -- colour unchanged, a PRICE PER UNIT label + a filter set at
   $30k/unit ($120k a pod), adjustable ("land price is passed to the buyer, so it flexes with
   the market"; look at everything). Units = pods the lot could hold x 4, NOT one pod: a big
   lot pays for (lot area - roads to serve the pods) / (pod + its parking), with parking
   possibly pooled to save buffers and planters (pods stay independent). Rough cut measured
   on run 70 greens (county total value; 4,500 sq ft a pod incl. parking + yard share; 25% to
   roads on lots of 3+ pods): one-pod basis 126 lots <= $30k/unit; capacity basis 771 <= $30k,
   4,911 <= $60k, 13,651 <= $100k; 1S2E02BB  -01100 (the closed big box) ~48 pods, ~$26k/unit.
   Coordinator's proposed guards (Steph to confirm): pods capped by the zone's density limit;
   multi-pod counts labelled ESTIMATE (new roads / a land division may need a review, against
   the by-right rule); county market value by default, last sale shown beside it; the two
   defaults (4,500 sq ft a pod, 25% roads) adjustable. True layouts stay item 31 / parked 27.
   STEPH CONFIRMED 2026-10-10: the defaults and the guards. Price is rough until a PAID price
   feed arrives (vendor TBD, ~2 months): build so a second price source slots in ahead of the
   county value with no rework (each price carries its source + date). No scan needed: the
   county values are already loaded per lot (scripts/flats_load_bridge.py ASSESSOR; lot page
   ui_flats.py ~3804). BUILT 2026-10-10 on branch flats/price-per-unit: "Price per home"
   column + opt-in filter (default $30,000, adjustable, with sq ft per pod and roads % boxes
   and a cheapest-first sort) on the Lots page; a price block on the lot page (pods, homes,
   ESTIMATE, county value, source + as-of, last sale shown but not used). Colour never moves.
   Settings: flats/config/price.yaml. Price sources are an ordered list in
   flats/score/price.py PRICE_SOURCES -- a paid feed goes IN FRONT with one entry.
   FIRST DEPLOY (34e1a771) HUNG PRODUCTION AND WAS REVERTED (4670491e): the filter worked the
   price out of each lot's JSON, per row, against the wide lot table. REBUILT 2026-10-10 on
   stored columns: table flats.lot_prices (migration 0143), one narrow row per lot: price,
   source name, as-of, a copy of the area, the zone's two density limits (flats/ingest/
   lot_prices.py). Pods and price per home are plain arithmetic on those columns
   (app/services/flats_price.py; parity test tests/api/test_ui_flats_price.py), so pod size
   and roads % stay adjustable. Filled by the bridge loader (scripts/flats_load_bridge.py,
   only the lots a bundle writes) and by scripts/flats_backfill_lot_prices.py (a whole
   snapshot: run it for the live copy, and again after a rule change moves a zone's density
   limit). Page queries now run with work_mem 128MB and a 25 s statement_timeout inside a
   savepoint; past the clock the page says "took too long" instead of hanging. The counts skip
   the wide lot table unless a city/zone/search is set; cheapest-first takes its 50 ids off the
   narrow tables, then fetches those lots.
   DEPLOY ORDER: (1) deploy (runs migration 0143, table starts empty: every lot reads "no
   price", nothing hidden); (2) `uv run python scripts/flats_backfill_lot_prices.py --snapshot
   3 --snapshot 4` on the app box (add --dry-run first); (3) re-time green+filter+sort and
   run tests/e2e/test_flats_price.py against viciniti.deals. The row label on the page is
   still worked out from the lot's facts, so until step 2 a label can show a price the filter
   does not know.
   TIMINGS (read-only, production, run 70, snapshot 4): upper bounds only, the table cannot
   be made read-only-safe. Best-colour aggregate 4.9 s at the default 4MB work_mem (sort
   spilling 1.4 GB), 1.6 s at 128MB. Stand-in for the stored table (a CTE built from the
   JSONB): filtered count 7.6-16 s, filtered+sorted 50 rows 10.6 s; 15 s of that is the cold
   read of the wide lot table, which the stored table removes. RE-MEASURE after step 2.
   Run 70 greens (49,960), per home: <= $30k 716 / $60k 9,115 / $100k 23,441 with the zone
   density cap; 843 / 11,199 / 29,282 without. 8,727 greens lose pods to the cap. 62 greens
   have no county value (green+yellow 4,959, mostly Washington County unincorporated 2,728).
   Open: (a) filter is opt-in, not on by default -- Steph to say if it should start ON;
   (b) cap reads units/acre and the townhouse-lot minimum only, on gross area; max_units and
   net-area density not applied; (c) ~10 greens carry county values under $1 a sq ft (price
   per home of $17-$950) -- shown as-is; (d) a "value looks too low" mark -- Steph to decide.
   LIVE 2026-10-10 (merge d1d8c03f): migration 0143 ran, backfill done (snapshot 3: 400,032 rows,
   390,554 priced; snapshot 4: 590,282 / 566,553; 148 zone caps), ANALYZE run. Production
   timings (e2e user): plain 4.7 s, green 6.4 s, green+sort 6.5 s, green+filter 7.5 s,
   green+filter+sort 7.3 s; no query left running; tests/e2e/test_flats_price.py 3 passed on
   viciniti.deals. Only (a) and (d) wait on Steph.
67. [scan: YES, after the weekly re-screen (a rule change; gains none, greens turn yellow or red)]
   **Washington County makes the owner hand over road land first; the fit ignores it (found
   2026-10-10 by item 64's sample, 2 of 11 WashCo greens wrong).** CDC 302-2.14 C(1) (and 303-2.14
   C for R-6) says a middle-housing lot must give land out to a set distance from the road's
   centre line: 25 ft on a local street, 30 ft on a neighbourhood route, 37 ft on a collector,
   recorded before the first building permit (C(2)); no strip is due where the road is already
   built to the county's final width. Our file says "NOT ENCODED: right-of-way dedication"
   (_unincorporated.yaml ~485-495) because nothing measures the road's existing half-width.
   Wrong lots: 1S201CC12500 (about 3.6 ft due, pod had 0.0 ft spare) and 1N120AD09600 (about 4 ft
   due, pod about 2.5 ft short after it). REACH (measured as alley width is, across the gap between
   lots, read-only SQL on run 70): of 7,711 WashCo unincorporated greens, 778 (10.1%) face a road
   at least 2 ft short; 206 (2.7%) might lose fit; 180 (2.3%) red-grade. For 4+ ft short: 504 / 144
   / 134. PROPOSAL (nothing built): measure each fronting road's half-width from the lot-fabric gap
   (`Lot Analysis/quadfit/s4_edges.py` `_alley_width` ray-cast), take the missing strip off the
   envelope on that side, rescreen. Unmeasured road = worst case, per the standing rule. Decision
   pending: none for Steph unless a lot with exactly 0 ft to spare is wanted yellow rather than red.
   AGENT INSTRUCTIONS GIVEN 2026-10-10 ("washco-road-dedication"): measure each fronting road's
   half-width, take the missing strip off the envelope, bound WashCo unincorporated, read every
   loss; lands at a splice or the weekly after it.
68. [scan: YES, after Steph or the agent supplies the maps] **Portland Maps 120-2 and 120-3 are not
   held (found 2026-10-10 by item 64's sample, 1 can't-tell).** 33.120.206 bars new homes on a site
   deeper than 160 ft with under 90 ft of frontage, but only on the sites shown on Map 120-2
   (Eastern Portland centres); 33.120.220.C adds a rear-setback rule for Map 120-3 (Eastern Pattern
   Area). Neither map is in the store (portland.yaml ~724), so both are left out and the lots stay
   green. Upper-bound reach: 902 Portland multi-dwelling greens are deeper than 160 ft with under
   90 ft of frontage (RM1 647, RM2 208, RM3 47); how many sit on the map is unknown. Sample lot:
   1N2E21AD  -06200 (RM1, 50 x 200 ft). PROPOSAL: fetch the two maps from the City's open-data
   portal as polygons (or get them from Steph), then add a frontage check and the rear setback with
   a corner exemption. Until then, consider marking these 902 yellow.
69. [scan: YES, at the next weekly (a zone-level refusal; no bound needed)] **Hillsboro zones that
   need Development Review are RED BY RULING (found 2026-10-10 by item 64's sample, 2 of 3
   Hillsboro greens wrong; branch flats/hillsboro-review-red).** CDC 12.80.040 B.1 requires a Type
   II Development Review for new development in any zone except D.1's list, and D.1 exempts middle
   housing only in MR-1, SCR-LD, SCR-MD and the R zones (cdc.12.80.applications.txt L318-L320,
   L338-L343, E at L379-L380). Ruling applied: Steph 2026-10-08 by-right only (item 53; Sandy's Type
   II Director's review is the precedent). State law does not lift it: OAR 660-046-0215 asks only
   for the same process as a detached house, which in these zones needs the same review, and
   clear and objective criteria, which the residential criteria H.1-H.6 already are (H.7, the
   discretionary one, is non-residential only). 17 zones refused, standards kept: MR-2, MR-3,
   SCR-HD, SCR-OTC, SCR-DNC, SCR-V, SCC-SC, SCC-MM, MU-N, MU-C, MU-VTC, UC-RM, UC-MU, UC-AC,
   UC-NC, UC-OR, UC-RP. Run 70 reach (best design per lot): green -> red 152 (MR-2 84, SCR-HD 46,
   SCR-V 11, MR-3 5, MU-N 3, SCC-MM 2, UC-RM 1); yellow -> red 212 (SCR-V 128, MR-2 18, MR-3 18,
   SCR-DNC 16, SCC-MM 12, SCR-HD 8, UC-RM 7, MU-N 5); 275 SCR-MD greens stay. Lands at the next
   weekly (~2026-10-14). Open for Steph only if a Type II review on clear and objective
   criteria should count as by-right (then all 17 zones come back).
   MERGED 84f215f8 2026-10-10 (code live, map moves at the weekly).
71. [scan: NO unless it finds a siting rule] **Building-code editions (Steph 2026-10-10: "ORSC 2026
   came into effect 10/1/2026 -- is our app built on that or the previous version?").** The screen
   reads NO building code for pass/fail: it is zoning + fire access (OFC 2022, _state.yaml) +
   the OSSC 2025 accessibility chain (HUMAN_TODO ~L465, ENCODING_RULEBOOK 2026-09-03). ORSC appears
   only as the 2023 edition in that note ("2026 edition expected 2026-10-01") and as a dismissed
   fire-flow cross-reference (_state.yaml "302.5"). Offered: an edition check -- confirm the ORSC
   2026 base (IRC 2024?) and its Oregon amendments for anything that changes WHERE the pod may sit
   (exterior-wall distance to a lot line R302.1, townhouse definition/limits, R302.2), confirm the
   fire code edition in force (is OFC 2022 still current?), update the notes; a siting change gets
   its own item.
72. [scan: NO] **Oregon Explorer statewide zoning viewer (Steph 2026-10-10 link,
   oregon-explorer.apps.geocortex.com ...app=6244abbf93e54b88a13a17b6cb6b9b37).** Not opened: the
   browser tool was offline and the app item is not public on ArcGIS Online. The DLCD statewide
   zoning layer reachable as data (services8 .../Zoning/FeatureServer, item 72416393747c...) holds
   per polygon: local zone code + name, a statewide standard class (orZCode/orZDesc), a link to the
   code (codeRef), an effective date and the owner -- NO setbacks/heights/lot sizes. Use: a
   zoning map for cities beyond the 3 counties (all-Oregon market), the codeRef link to fetch each
   code, effDate as a change watch (item 54). Not a replacement for reading the codes. Waiting on
   Steph to say what the viewer shows (or reconnect Chrome).
   STEPH 2026-10-10: the viewer is the building code's site-design map, NOT zoning: ground snow
   load, basic design wind speed, seismic design category, weathering, frost line depth, decay,
   air freezing index, radon mitigation for new dwellings (the ORSC Table R301.2 climatic and
   geographic design criteria, state-wide in one place). Not a siting rule; it decides what the
   factory-built pod must be ENGINEERED for at each lot. OFFERED: (a) fetch the layers behind
   the viewer, measure each lot, show the values on the lot page (show, don't screen); (b) once
   Steph gives the pod's rated snow load / wind speed / seismic category / frost depth, flag lots
   that exceed them (re-engineering = a cost, YELLOW at most, never RED by itself). Confirm the
   map matches the ORSC 2026 edition (item 71). Steph to say whether to build; (b) needs the
   manufacturer's ratings.
   STEPH 2026-10-10: PARKED for later -- "eventually we will need to encode and design for this
   list" (all eight criteria). Do not start without Steph; raise it again when the pod design
   ratings exist or the market moves beyond the metro.
73. [scan: NO (citations move, answers must not)] **The code library as a public, structured repository
   (Steph 2026-10-10, thinking only -- "Don't begin work").** Today: 397 text files, 23 MB, 25
   jurisdictions under flats/provenance/docs, each with .meta.json (url, retrieved, sha256,
   extractor) and .pages.json; rules cite them 6,668 times by LINE (`file.txt#L1066-L1068`) and 641
   times by anchor; every cite also carries a human section string ("OCMC 16.12.035.F").
   Proposal offered: (1) STRUCTURE first -- rebuild each code as a tree of sections addressed
   by its own numbering (16.12.035.F), line WITHIN the section as the sub-address, tables by
   row/column; translate every citation mechanically (match the quoted text, refuse any that does
   not match; flats/provenance/repoint.py is the starting point); pilot one city. (2) HOSTING
   second -- its own GitHub repo, our apps read it as a dependency; git history doubles as the
   code-change watch (item 54). Open for Steph: public or private; publisher terms (Municode
   etc.) before going public; keep rulings/encoding private either way.
