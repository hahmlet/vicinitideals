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
   2026-09-19 when Steph asked why the court is always behind. Today the
   rear court is the one arrangement that survives every city's rule
   (Gresham 7.0431 bars front/side-yard parking for townhouses; Portland
   33.266.120.C.1.a bans a vehicle area between building and street; Happy
   Valley 16.43.030.E.4 sets parking back by the building setback; Oregon
   City 17.16.060.D caps parking width at 40 ft), and the county drawing
   (`s6s_siteplan.py`) never draws a side court; the screen's fit
   (`flats/fit/rectangle.py`) sweeps 180 angles where no
   `orientation_constraint: axis_required` is held and charges the court as
   depth behind the building in whatever direction it faces, so it can
   already count a sideways placement the drawing would refuse -- the two
   disagree on wide lots and neither asks the code. No field holds "side
   parking allowed / forbidden" (`parking_front_prohibited` is the front
   only). **Steph's ruling 2026-09-19 on the front:** trying each street
   as the front applies ONLY where the lot has more than one street AND
   the code leaves the choice to us; if one front parks and the other does
   not, take the one that parks; if both park, HUMAN_TODO 21 DECIDED
   2026-09-19: (1) the orientation that turns the lot green, (2) if both
   green, the one that reaches the `preferred` band, (3) if both preferred
   or both only `minimum`, the orientation whose COURT has the least
   exposure to a street -- "might be rear, might be shortest street" --
   measured as the court's frontage on street edges (s4 edge classes: a
   court touching no street edge beats one along the shorter street beats
   one along the longer); my reading: a higher band wins before exposure
   decides. **More parking is not a goal** --
   Steph: "optimize for sufficient, but minimal parking so we can fit a 2nd
   pod" -- so s6s's "keep the orientation with the MOST stalls" rule is
   to be revisited here (green, then band, then the least ground under
   pavement), and a two-pod lot is a product direction to keep in view
   (`flats/designs/`: one pod per lot today). And read every
   city for multi-street rules even where the front is clear. Whole-corpus
   grep 2026-09-19 (`flats/provenance/docs`, "corner lot|through lot|double
   frontage" near "front lot line"): the CHOICE IS OURS in Gladstone
   (17.06, owner designates), Happy Valley (16.12, applicant chooses,
   through lots too), Milwaukie (19.200, "the street on which the
   development will face"), Troutdale (1.020, either street unless the
   corner is one continuous curve), Fairview (19.13, set by the main
   entrance) and Gresham (3.0100, owner; Manager if disputed); the CODE
   FIXES IT as the SHORTEST street line in Portland (33.910; equal ->
   choose), Oregon City (17 "narrowest frontage"), Wilsonville (4.planning
   "shortest"), Multnomah unincorporated (39 "narrowest") and Wood Village
   (720.030 FRONT LOT LINES "shortest"; its FRONTAGE definition says owner
   -- two definitions, read both); BOTH STREETS ARE FRONTS (two front
   setbacks) in Clackamas ZDO 202 (corner and through lots; 315 [4] gives a
   corner townhouse 10 ft from one of them), Gresham 4.0131 (double
   frontage), Lake Oswego 50.04 (through lots) and Portland (a through lot
   has two front lot lines); Tualatin 40-41 gives every street side the
   front setback. Multi-street RULES beyond the front: Gresham
   7.0431(B)(3)(b)(ii) and Oregon City 17 (L5350) -- a townhouse project on
   a corner lot takes access from a single driveway on the SIDE street;
   Fairview 19.162.5 -- a double-frontage lot takes access from the
   lowest-classification street first; Wilsonville corner lots under 100
   ft wide get a street-side yard rule. FINDING: `s4_edges.cluster_bearings`
   orders fronts by LENGTH and s6s takes `bearings[0]`, so the drawing
   makes the LONGER street the front -- the opposite of Portland / Oregon
   City / Wilsonville / the county, where the front is the shortest -- and
   puts the lane on the front street where Gresham and Oregon City send a
   corner lot's driveway to the side street; a lot with streets at both
   ends (bearings mod 180 = one cluster) gets its court facing the other
   street; `frontage_ft` sums both street edges on a corner. Do in this
   order: (i) per-line fields read per city -- `parking_side_prohibited`,
   `front_lot_line_corner` (shortest | owner | both | entrance | curve) and
   `corner_access_street` (side | lowest_class | any) -- whole-document
   grep each parking and definitions chapter; (ii) s6s: the front per the
   city's rule, our choice only where the rule leaves it, the lane from
   the street the rule names; (iii) a named side-court arrangement in s6s
   counted under its own `layout_method`; (iv) through lots as two fronts
   where the code says so. Measure the affected population first (corner
   lots by city, through lots, lots wider than deep) before any county run.

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
