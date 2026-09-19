# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **The county map copy: after the first candidate (HUMAN_TODO 20).** All
   four phases shipped 2026-09-19 (snapshots + banner + probe 41b64c45;
   delta dc1dbaad; every-lot normalize/assign + gate 1318db5b; promote /
   rollback / drift / `/flats/refresh` ffe407ec; runbook
   `docs/ops/flats-county-refresh.md`). The September copy is loaded as
   **run 8** (`candidate`, snapshot 3: 400,032 lots = 288,031 measured +
   112,001 unmeasured with a reason; 800,064 results; `?run=8`, default
   still run 2; run 6 -- the same snapshot with 2,001 condo unit records
   kept as lots -- was retired by a one-shot before the re-load, 8e596f8b),
   drift 2 -> 8 stored (575,478 compared, 178 moved: ground 39 /
   surroundings 104 / re-measured 35 / rules 0 / code 0 / unexplained
   0; causes read from the measured facts since 61e01c36:
   `surroundings` beyond float noise, `remeasured` within it -- 0.05 abs /
   2 % rel -- on an answer that sat on a line), gate trips **new_zones
   only** -- Steph reads; nobody promotes. When Steph promotes:
   `flats_promote.py prune --dry-run` then real (keeps snapshot 1 whole),
   confirm the Lots default is run 8 and the footer says 2026-09-18,
   re-run the probe. Still coarse at the end: `code` is the
   fall-through whenever the repo HEAD differs, so it says "a commit
   landed", not "the screen changed"; the api container has no git, so
   making it precise means the exporter stamping a hash of the screen's own
   files (`flats/score`, `flats/geom`, `flats/ingest/quadfit.py`, `Lot
   Analysis/quadfit`) on `run.json` -> `runs.screen_version` and `drift()`
   comparing that -- a migration + loader column; do it with the next
   loader change. Loose ends the September map
   found, queued not fixed: Happy Valley's layer carries both `MURM2` and
   `MURm2` (one lot; the source's casing, kept), Oregon City's zoning says
   `County` on 14 lots inside its boundary; quadfit's s1 condo test reads
   only stacked geometry, so it measures ~2,000 Multnomah condo unit
   records (PROP_CODE 102/132/202/122, 1,000-2,000 sq ft) every run --
   normalize's `excluded.csv.gz` ledger now names them and assign drops
   them (8e596f8b), but s1 itself could read the roll's property code the
   way `flats/normalize/condo.py` does; Terrain (DEM tiles) stays
   `deferred` until the slope stage exists; no writer for lot decisions in
   `app/` yet (they are inserted by hand or by a future review page).
2. **The court search takes the biggest rectangle, not the deepest one that
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
3. **Four places the screen and the county map disagree, found by the
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
   those 178 are quadfit `siteplan_no_layout` lots the sweep found a fit on.
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
4. **Draw what the screen fitted on the lot page.** `/flats/lots/{county}/
   {tlid}` (`app/api/routers/ui_flats.py`, the "lots" section) draws the
   outline only. Two things are missing before the building can be
   drawn on it: quadfit's carved envelope (s5o `wkb`) is not carried by
   `scripts/flats_load_bridge.py` -- a geometry column on `flats.lots`
   (migration) and one more `export` column; and the screen's `fit_for`
   reports depth / across / angle / orientation but no *position*, so a
   placement (the rectangle's origin on the lot, in 2913 feet) has to be
   returned by the fit and stored in `checks.fit` before anything can be
   drawn. Offered 2026-09-18 with the pages.
5. **Where parking may SIT, and which street is "the front".** Offered
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
   fronts_tried / court_street_ft; 53 siteplan tests. **NEXT: bound it on
   137** -- s6s -> s7 on the September tree (`s6s.py` then `s7`, ~10 min
   s6s), diff verdicts and stall counts against run 8's parquet BEFORE any
   load; report corner-lot moves per city and the within-band stall drops
   on interior lots separately; if a new candidate is loaded, retire run 8
   first (one transaction, rehearse with ROLLBACK) and keep its bundle.
   Then (iii) a named side-court arrangement; (iv) through lots as two
   fronts. Queued behind it, each to bound first: (a) s4 measures lot
   width/depth along the LONGEST street (`cluster_bearings` orders by
   length) -- in the shortest cities width and depth are swapped on most
   corner lots, which moves `lot_width_ft` facts and every width gate; (b)
   Portland 33.266.120.C.1.b: on a corner lot the court must sit behind the
   side-street building line and pave at most 20 % of the side-street
   setback; (c) `lowest_class` needs a street classification per edge (s4
   holds none; drawn as `any` and said so at runtime); (d) Fairview
   19.30.050(D)(2)(a) side-yard parking setback -> redirect ledger; (e)
   Gresham 3.0100: the front is fixed where the minimum lot depth is met
   in one direction only (needs depth both ways = (a)).

6. **Green and outdoor space: charge the SHAPE, not just the amount.**
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
   FOLLOWUPS 5's "least ground under pavement". Measure the affected
   population (Milwaukie ok plans with court depth within 7 ft of the
   floor; Portland ok plans with no 12 x 12 square outside the pavement)
   before any county run.
