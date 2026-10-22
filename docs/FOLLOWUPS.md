# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. "Do the next thing" means the first item of section 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

Numbers are stable IDs, not an order: they are never reused or changed, and
items sit out of number order across the sections. A new item takes the next
unused number (102 onward) and goes in its section. A moved item leaves a
one-line pointer (27b).

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

Each item carries `[scan: ...]`: YES = the work changes lot answers, so a
before/after scan on 137 must be read before it ships; NO = tests are enough;
"NO new code, check after the weekly run" = already deployed, its moves are
read when the weekly full re-screen lands.

## 1. Claude -- priority

### 1a. The weekly re-screen (~2026-10-19): traps to honour before it, moves to read after it

   LAUNCHED 2026-10-19 16:07Z (Steph "execute scan"): tag 2026-10-19_weekly, log 137
   /root/weekly_chain_1019.log, state /root/weekly_2026-10-19_weekly, status copied to 114
   /root/weekly137/status.txt; ~9-10 h (quadfit ~78 min, bridge ~7 h). Re-launch after a crash:
   `setsid -f /root/launch_weekly_1019.sh` (finished steps are skipped). Then load the candidate,
   read the moves (items 95, 67, 77, 78, 61, 69 ...), and only then promote.
   Was READY TO LAUNCH (checked 2026-10-19): 137's checkout is at a69f4ca3 (items 85 + 93 merged) and
   `flats_weekly_chain.py --snapshot 2026-10-07 --sha a69f4ca3 --preflight-only` passes. The six
   datasets it was missing (overlay_pdx_main_street, pdx_historic_resources,
   pdx_landmark_footprints, pdx_pattern_areas, street_class_sherwood, street_class_tigard) were
   fetched into the 2026-10-07 snapshot that day. Launch line: docs/ops/flats-county-refresh.md
   step 5-10, with --snapshot 2026-10-07 --sha a69f4ca3 (or later main).

67. [Claude] [READ at run 78 2026-10-20: moves at the bound; only (b) open] [MERGED to main (d3b6db52, a212b7f5, cities 7cbc3346 = item 77), rides the weekly ~2026-10-19]
   **Washington County makes the owner hand over road land first (CDC 302-2.14 C(1), 303-306,
   307-2.13, 375, 390).** 25/30/37/45 ft to centre line (local / neighbourhood route /
   collector / arterial), measured per street lot line from Metro's centreline (a stub with no
   street beside it reads the nearest centreline, OSM included, which can only be nearer); the
   shortfall comes off the envelope like a setback; unmeasured = whole distance; unranked class
   = 45 ft; private roads (RLIS 1700/1800) take nothing. Steph RULED 2026-10-14 "YES" (register
   `2026-10-14-road-dedication`; an unranked street is taken at its worst case).
   Coordinator rulings 2026-10-14 (on "never a false green" / "unranked = worst case"): (a) an
   unranked street keeps the worst case; (a2) a corner piece on two streets BOTH read with a
   class on the lot takes the deeper of the two (d3b6db52, test at real coordinates); a piece
   with any street unread stays worst case; a212b7f5: a short piece whose own class reading
   fails (corner cut-off, curve) and whose ONE street is read with a class on another line of
   the same lot takes that class; no name, two names, or a name read nowhere else stay worst case.
   NOT ADOPTED 2026-10-11, with reasons: OPTION C (unmapped street = local): the county TSP
   (Effective Sept 24, 2026, PDF p. 8 and 33-35) says "New Local Streets that are not in this
   plan may be established via the land development process" and "other neighborhood routes may
   be designated through the development review process" -- so an unmapped street can be a
   neighbourhood route (30 ft) as easily as a local one. NARROWER READING (30 ft for a street
   absent from the county's classified layer): FAILS -- layer 4 (street_class_washington) is not
   a complete list of collector-class streets (vs RLIS type 1400 89.9%: missing Bankston ~2,294
   ft, Grabhorn ~207 ft, Glencoe ~50 ft; type 1450 97%: missing Roy ~1,609 ft); layer 8 "Special
   Area Streets" holds Special Area Commercial Streets (37 ft) that layer 4 covers only 6-9%. A
   30 ft ceiling would need layer 8 as a dataset plus "stays 45" exceptions; not built.
   Option A stands.
   EXPECTED at the weekly (FINAL bound vs run 74 on the 3,693 moved lots, best design per lot,
   green->red / green->yellow / yellow->red / yellow->green): WashCo uninc 1,178 / 83 / 603 / 31
   (+2 red->yellow), Oregon City 713 / 56 / 228 / 19, Sherwood 20 / 0 / 30 / 2, Milwaukie 17 /
   18 / 57 / 6, King City 0/0/3/0; total 1,928 / 157 / 921 / 58. Greens in scope 10,402 -> about
   8,375. Ten lots end GREENER than run 74 by a placement-search artefact (item 57's kind), all
   read: 1S114DA00701 1S112CC03400 22E28CA00702 1N225AB20000 1S103DB01800 22E32CC03100
   1S110BB07900 2S132DA05500 1N128DA02000 22E27BC01900. Bound base
   /root/bridge_spliced_2026-10-14_demw (proven valid).
   OPEN: (b) lots whose tax lot includes the roadway (lot line under ~12 ft from centre line)
   understate the road and are left at worst case (63 lost, 73 kept green). (The Fitter
   cache-key bug, item 74, is fixed 8bda9817.)
77. [Claude] [READ at run 78 2026-10-20: the four CHECK lots red, moves at the bound; OPEN list below] [MERGED to main (7cbc3346 + d3b6db52, with item 67), rides the weekly ~2026-10-19] **Road land to the
   centre line in the cities, not just unincorporated Washington County (found 2026-10-14 by
   item 64 round 2: 4 of the 7 wrong lots).** Steph RULED 2026-10-14 "YES" (register
   `2026-10-14-road-dedication`). Built: Sherwood 16.106.020 A + 16.106.040 D, 26/32/32/37/61 by
   its TSP class map (street_class_sherwood; a street the consultant map lacks = 61); King City
   16.80.060 A by named streets, 99W borrowing Sherwood's 61, county pockets on the county rule;
   Oregon City 16.12.011.B, half the widest Table 16.12.016 right-of-way 31/44/59/63 by
   street_class_oregon_city (RULED 2026-10-14 widest row per class; superseded by item 82: the
   zones on both sides stand in for the designation, the widest row kept only where that cannot
   be read); Milwaukie its 29 named rows of Table 19.501.2.A. Beaverton a refusal note
   (dedication at the decision-maker's call, no width stated).
   CHECK after the weekly: lots 2S132CD12600, 2S132AC01500, 2S116AA14200, 31E01DA00229 read red;
   expected moves are in item 67's table (Oregon City 713 / 56 / 228 / 19; Sherwood 20/0/30/2;
   Milwaukie 17/18/57/6; King City 3 yellow->red).
   TRAP: scripts/flats_weekly_chain.py preflight REFUSES a snapshot without
   street_class_washington/sherwood/oregon_city/milwaukie or rlis_streets (dedication_keys());
   runbook docs/ops/flats-county-refresh.md.
   OPEN: Tigard NOT ENCODED (18.210.030.A.1 setbacks from the future street edge; TSP widths not
   held -- a remaining false-GREEN gap, item 81); segment qualifiers in the tables applied to the
   whole street; lot area not reduced by the strip (only the envelope); an unmeasured public line
   gives up the whole 40-63 ft.
78. [Claude] [READ at run 78 2026-10-20: 1,628 green->red exactly the bound; "Still open" list below] **Portland false GREENs: main street minimum floor
   area and protected historic buildings are RED (MERGED 2026-10-15, branch flats/portland-overlays
   4ed70036).** The "m" overlay minimum FAR (33.415; half in Inner, a quarter in Eastern/Western) is
   measured on the part of the lot inside the overlay (PCC 33.700.070.F), crediting only the floor
   area of the drawn pod that sits on that part (no drawing = nothing credited); >90% covered = the
   whole lot. Landmarks and contributing buildings in Historic, Conservation and National Register
   districts are RED when at least half the building sits on the lot. Bound vs main: 1,628
   green->red, 198 yellow->red, 1 green->yellow (lots read one by one, none wrong); the
   partly-covered re-run then moved 8 red->green, 2 green->red, 1 red->yellow. Weekly must acquire
   overlay_pdx_main_street, pdx_pattern_areas, pdx_historic_resources, pdx_landmark_footprints (the
   bridge refuses a snapshot without them). Still open: Glendoveer, Macadam, the d overlay, 33.430
   environmental; the ground-floor active-use rule from 2029-01-01; the 800 sf accessory-building
   exemption, which the data can't separate.
80. [Claude] [Steph: (a), (c)] [(d) Copilot-able] [scan: (a)(b) RULED + BUILT, r3 MERGED to main (83a7683d), ride the weekly ~2026-10-19; (c)-(e) open] **Readings for Steph from item 64 round 2.**
   (a) "Parking may cover at most half of a street frontage" caps (Wilsonville 4.113(.14)D.3,
   Hillsboro 12.50.715 C.1, Clackamas ZDO 845.02(D), Beaverton). RULED (Steph 2026-10-14; register
   `2026-10-14-frontage-cap-any-street`): ANY street frontage. Built (flats/fit/frontage.py,
   measured on the drawn plan): a court behind the building on a one-street lot counts nothing, so
   31W15DC05351 and 31W22DC01400 (Wilsonville) STAY GREEN. Bound: 241 lots go red on the cap,
   every one a corner or through lot (Clackamas 105, Beaverton 103, Wilsonville 23, Hillsboro
   SCR-MD 10); two ways one street was read as two (a bend under the 45-degree corner angle; a jog
   in one frontage) fixed, 38 lots back. QUESTION for Steph, open: 1S113BA07700 (Beaverton RMC
   yellow -> green: base's preferred plan was yellow on SLOPE-GRADE, the cap pushed it to a green
   plan off the other front) -- should a yellow preferred plan hide a green one?
   (b) Hillsboro SCR-MD/SCR-HD 5 ft MAXIMUM side setback (12.22 tables): RULED (coordinator
   2026-10-14): "one wall within 5 ft" (12.50.130.C.3.a); moved no lot in the bound (the research
   leaned "both walls", moderate confidence -- recorded in hillsboro.yaml; not yet in the register,
   see 86(B)).
   (c) Wood Village TC: building goes through a "Town Center Development Plan" (the old Master
   Plan); its approval type is in 235.400/235.490, not stored, and the site answers 403 to every
   fetch. A human copy of those sections decides 10 TC greens (1N3E34B   -00807 can't tell).
   (d) Estacada is charged 4 stalls (state middle-housing cap) but is under 25,000 people and
   outside Metro, so its own 1.5 per home = 6 stalls applies (emc.16.76.txt:77-78). Every Estacada
   green still seats 6+ except 34E17D 00700 (5, room for more): a fix with no colour change.
   (e) Noticed: flats.flag_instances was last refreshed at run 70 (no row seen after it), so it
   still shows JURISDICTION-OFF on Tigard lots; run 74's own results carry the right flags.
76. [Claude] [Steph: (c) assessor lookup] [(a)(b) READ at run 78 2026-10-20, Estacada 34E17 02000 as expected; only (c) open; MERGED to main (5e29be82, 72f96818)] **Tigard pod80x25 red at exactly -43 ft, and split-zoned lots.**
   (a) -43 is NOT a sentinel: it is the floor fit_ft reports when no window as wide as building +
   lane (80 + 20 = 100 ft) exists at any street bearing: best_depth 0 minus (25 ft building + 18 ft
   court) = -43 (pod56x36 floors at -36). Checked against exact geometry: all true no-fits except
   raster near-misses (3 of 785 fit at width-0.5 ft). Steph ruled yes (register
   `2026-10-14-split-zone-near-miss-real-shortfall`): the fit now reports the real width shortfall
   (`Fit.width_short_ft`, flats/fit/rectangle.py) so the 1-ft rule applies (>= 1 ft red, < 1 ft
   yellow FIT-TIGHT). Bound: 50 design rows red -> yellow (Tigard 47, Gresham 2 DRL-2, Happy Valley
   1 R7). SIDE EFFECT, colour-neutral, on RED lots: the slack shown is now the real shortfall
   (-37/-48/-56/-80 ft ...) instead of the -43/-54 floor, and ~1,100 red rows gain or lose an
   informational flag (Milwaukie MEASURE-OUTDOOR-SHAPE +542, Beaverton net-area swaps). If the
   lot page should keep the old numbers for red lots, that is a separate decision (not asked).
   (b) Split zones. Steph's ruling (register `2026-10-14-split-zones`): "first check if the city
   has a rule on this. If no, I would say yellow." Built: flats/config/split_zone.yaml (cite +
   quote per city, tested against the stored text; what was searched in the 17 silent layers is
   written there so nobody searches again) and flats/geom/split_zone.py. Rule found -> applied
   (Beaverton BDC 10.35.2.C and Milwaukie MMC 19.107.5 <= 20 ft inclusive; Cornelius CMC
   18.05(D)(3), Hillsboro CDC 12.01(C)(1), Canby CMC 16.08.030 "less than" 20 ft; Sandy SDC
   17.04.80.B.6 majority; Portland and Multnomah PCC 33.110 each district for its own part). No
   rule -> a green whose building, lane or court stands on another district's ground goes YELLOW,
   ZONE-SPLIT (severity 4); an undrawn plan or unresolved district is the worst case. Bound: 134
   lots green -> yellow (Portland 94, Washington-uninc 20, Clackamas-uninc 12, ...), nothing else.
   CHECK after the weekly: these two bounds' moves. Estacada 34E17 02000: pod80x25@2 yellow,
   pod56x36@2 stays green.
   (c) OPEN, human lookup: Estacada 34E20AC00200 / 00201 (1015 NW Wade St) -- owner NOT in our
   data (RLIS roll carries no owner name); roll says COM class 201, taxed (assessed > 0), so the
   public-land rule correctly did not fire. Look up tax lot 34E20AC00201 at the Clackamas
   assessor: if the owner is the city or a district, it is a miss the roll cannot see.
84. [Claude] [READ at run 78 2026-10-20; only Fairview VC open] **Frontage caps read as caps on every street (MERGED 2026-10-15,
   branch flats/frontage-caps 667f57e9; phase 3 flats/frontage-fragments d8c6da14 MERGED 2026-10-16,
   bound read, rides the next weekly: 556 gains, Oregon City 349 red->green / 153 red->yellow /
   2 yellow->green, Beaverton 10 / 32, Clackamas 3 / 1, Troutdale 1 / 2, Sherwood 2 red->yellow,
   Wilsonville 1 red->yellow; OC D caps residential zones only, E governs mixed-use/commercial;
   a rounded corner is split between its streets).** Oregon City 17.16.060.D.1 (40 ft or 50% of the
   frontage, whichever is less -- check `parking_frontage_width`, worst street), Fairview
   19.30.040(E)(2) 50%, Troutdale 8.120.C.4.d 50% (front parking was blank = banned; now allowed
   except the townhouse path 8.130.C.4.b.i), Sandy 17.90.160 F 50% of any abutting public street,
   Beaverton 60.05.15.6.C 35% of any street lot line read as a DRIVEWAY cap (parking is held 20 ft
   back by 60.05.20.6.A.1) in all 12 blocks. Every % cap is now per street line (unknown street =
   shortest line). Still open: Fairview VC's conditional-use path (1 lot, 1N3E33AB-00500; see
   item 10). CHECK after the weekly: OC corner side courts (43 ft > 40), Beaverton side courts may
   gain, Sandy/Fairview through lots lose, small corners stay yellow (court not drawn).
42. [Claude] [scan: NO new code, check after the weekly run] **Water, wetland and flood ground at slope's fidelity -- DONE and live.**
   Steph asked 2026-10-04 "are we treating wetland/flood zones with as much
   fidelity as we now treat slopes?". Shipped: Portland z RED e55c22ee
   (PCC 33.418.040.B; Steph RULED "red, way in noted", register
   `2026-10-04-portland-constrained-sites-red`); quadfit `flag` overlays +
   FEMA fringe a YELLOW closer look 25d26ce6/2c5b461b; Milwaukie greenway
   RED; DSL wetlands 1c6da420; no-build carves 587b02d1; residue
   5b4ba52e + 799ef7a9 (Portland ezone p/c/v carved, PCC 33.430 -- the 25 ft
   transition area inside p+c stays buildable; Wood Village WVDC 430.170.A;
   Hillsboro CDC 12.27 own map). TRAP for the weekly: it must re-run quadfit
   s5o on this code and acquire `overlay_hillsboro_snro` (pipeline.yaml
   registers it). RULED, never re-offer (register
   `2026-10-06-fema-fringe-stays-yellow`, `-hca-allowance-declined`,
   `-maybe-list-declined`, `-west-linn-fish-bearing-streams`,
   `2026-10-05-landslide-slopes-declined`): FEMA fringe stays YELLOW ("we
   aren't customizing for flood zones"); landslide slopes, the "maybe list"
   (probable wetlands, hydric soils), the HCA disturbance allowance (Steph
   2026-10-06 "Leave it") and West Linn fish-bearing streams (ODFW 65 vs
   100 ft, Steph 2026-10-06 "ignore") all DECLINED. Still open:
   - washington_habitat stays a flag for WashCo uninc, Beaverton, Sherwood,
     King City, Durham (each needs a map or a determination the city holds).
   - Known under-carve: Portland's city-limit transition-area exception
     (33.430.050.A) is not drawn.
   - Left as they were, read: Clackamas WQRA, Happy Valley, Tualatin.
29. [Claude] [Steph: (C) county widths, deferred] [scan: YES for (C) when widths arrive; (A)/(B) checked after the weekly run] **Fire reach: measure where the truck really stands (Steph 2026-10-01,
   "later improvement"; RULED 2026-10-05).** Item 28 (the 150 ft hose,
   OFC 503.1.1) is LIVE since run 59. RULING 2026-10-05 (register
   `2026-10-05-fire-hose-from-curb`; no national standard; one Southern
   California template says "10 feet from the edge of the curb"): Steph
   "Let's go with stricter" -- the hose starts 10 ft out from the NEAR
   curb, capped at the street's middle; "with a flag to check later" --
   FIRE-HOSE-START (severity 1, the plan stays red) where the hose is the
   one bind and the route clears measured from the curb.
   (A) SHIPPED d8880db1 2026-10-05: flats/geom/curbs.py reads PBOT Curbs +
   PaveWidth, Multnomah RoadWidth, Wilsonville Width; a drawn curb loosens
   only where a recorded width agrees within 4 ft.
   (B) Steph 2026-10-05 "Assume narrow" (register
   `2026-10-05-unmeasured-street-narrow`): a street with no measured width
   is the narrowest a truck may use (20 ft, OFC 503.2.1) until measured --
   the hose starts at its middle; FIRE-HOSE-START says a width may lift it.
   SHIPPED 57313463 (Steph "Yes, ship it now").
   CHECK after the weekly (not recorded done): the bound's county estimate
   was ~360 worse (sample range ~270-500), ~150 of them green today
   (~100-250); every bound loss was read (181 routes 140-150 now 150-160).
   TRAP: the bridge REFUSES a --curbs/--sources snapshot missing any of
   curbs_portland, pave_width_portland, road_width_multnomah,
   width_wilsonville: the weekly run must acquire them (or pass --curbs
   /root/fire-curb_sources/2026-10-05), and so must any lane's bound.
   (C) Ask Washington County, Clackamas County and West Linn for their
   pavement widths -- DEFERRED, Steph: "follow up with them later". Also
   published but unused: Oregon City Edge of Pavement (CAD, undated),
   Hillsboro Roadway polygons (mixed with parking lots). Not reachable
   from here: Beaverton, Gresham. Scripts /root/fire-curb_probe/; detail
   in memory project_flats_fire_curb.
30. [Claude] [scan: NO new code, check after the weekly run] **Net land area review (Steph 2026-10-01: "not unique to Beaverton ...
   we need to do a review of net land areas and what to do about it").**
   SHIPPED d8d4a439 (run 61) + the 2026-10-04 additions (183 values) +
   slopes 995f0007. Steph 2026-10-02: **A** (register
   `2026-10-02-existing-lot-dedicates-nothing`: an ordinary existing lot =
   no new dedication/tract, net = gross minus what we measure per the
   city's own list), and "lots that fail for the only reason of min
   density need to go not red. Some sort of yellow or 'closer look'"
   (interim, until 31; later "a flag, maybe a 2", register
   `2026-10-02-minimum-density-a-flag`). Beaverton rulings ANSWERED
   2026-10-02 (register `2026-10-02-beaverton-common-driveway`): the pod's
   lane + aisle ARE a "common driveway" (stalls stay in), and constrained
   land comes off whether or not set aside in a tract ("very few will have
   done that") -- certain deductions in Beaverton and Cornelius 18.195
   (Metro wetland/habitat stand-ins stay `may_less` as regional proxies).
   CHECK after the weekly (not recorded done): run 63 had 2,077 lots in the
   2026-10-04 net-floor zones (King City KT, Wood Village LR/MR, Washington
   Co. TO:R24-40/TO:R40-80/NMU/CCMU/CBD), 419 failing the floor on the
   whole lot -- they land at the full re-screen.
   Still unmeasured (kept as `may_less` / `assumed_none`): floodplain area
   (only yes/no reaches FLATS; quadfit has ovl_<key>_sqft areas, not
   bridged); resource overlay area held in quadfit for HV / Milwaukie /
   Hillsboro / Beaverton (Metro proxy), NOTHING for Cornelius; landslide-
   area slopes (declined, register `2026-10-05-landslide-slopes-declined`). Gresham 3.0100 has two lists; its max density
   outside the LDR group is gross by the code's own words. Tigard read:
   MU-CBD's 25/50 per acre is not stated net in 18.650 (no false GREEN);
   Tigard FAR is net but no FAR is encoded. NB floors and county maxima
   stay gross by 300-2.8's words.
36. [Claude] [Steph: the OAR strip question] [scan: YES] **Parking tool queue (Steph 2026-10-02: "do them in the reverse order
   you listed them").** (5) partly, (4) and (3) LIVE as code f7ba7038;
   (2) turning path LIVE as 1723db45 (Steph "ship it"; register
   `2026-10-02-three-point-turn`: every stall usable by the AASHTO P car,
   three-point turn ok; ledger `flats/config/court_turns.json`). TRAP: a new
   court shape in the corpus needs `python -m flats.score.turns`
   (test_turns fails until it is solved).
   CHECK after the weekly (not recorded done): read the moves on corner lots
   with `lowest_class` and in Tualatin, Gladstone, Multnomah uninc and
   Hillsboro; turning path expected ~3% of Portland greens on narrow
   end-on lots to go yellow (bound: 18 of 561).
   Strips: RULED Steph 2026-10-04 (register `2026-10-04-planted-strips-yellow`):
   "Let's have strips be a flag for yellow at this time" -- DONE 1d3c89cb:
   a plan that misses only by the strip and clears with it read as
   unstated is YELLOW with flag PARKING-STRIP-UNCONFIRMED. STRIP IMPACT
   (bound 2026-10-04, strips on vs off): Gladstone 384 -> 445 green of
   3,217 (+61), Multnomah uninc 885 -> 898 of 2,213, Hillsboro ~+20 of
   27,402. Steph: "planter strips aren't parking, they're landscaping".
   QUESTION for Steph, still open: OAR 660-046-0220(2)(e)(E) makes large
   cities apply single-family parking standards to middle housing -- it
   may cancel the strips single-family homes are not held to (Multnomah,
   Gladstone, Hillsboro, Wood Village, Oregon City); encoded strict
   meanwhile. The OAR question decides whether the flag can clear.
   Left of (5): strips not yet encoded -- Wood Village 350.065(C) and Oregon
   City 17.52.060.C (one-lot projects only), Happy Valley 16.43.030.E.3 and
   Troutdale 9.095(A) (the neighbour district's setback; needs per-line
   neighbour zoning), Tigard 18.280.040.D.4 (width in unstored 18.420);
   unread chapters ZDO 1009, West Linn CDC 54, Washington CDC 407-6,
   Sherwood 16.92, King City 16.124, Tigard 18.420, Troutdale Ch. 11;
   Fairview 19.163.030(E) 5% of the parking area.
   (1) the free-form generator (item 92) -- PARKED by Steph 2026-10-04
   ("leave the free form generator for now").
44. [Claude] [scan: NO new code, check after the weekly run] **A lot's readings are ranked on the colour the map shows, and
   43's hose edge -- SHIPPED 51577bb8 2026-10-07; NOT in run 65 (the early
   10-07 weekly started first); Steph 2026-10-07: wait for the next weekly
   run.** `_front_rank`, `_worse`, `_better` (flats/ingest/quadfit.py)
   compare `signed.colour` first, the triage only on a tie. Hose edge: a
   utility-easement yard that fails a check the code's own yards passed
   falls to the 5 ft yard, question open (`_lost`). Bound (39,743 lots,
   3f514c9e vs 3cbe113c, every move read): control identical; owner-choice
   corners 436 lots better, none worse; through lots kept at the worse end
   99 lots yellow -> red; two-reading lots kept at the worse: 34 lots (39
   rows) were false GREENs (13 rows now red, 26 yellow), 72 lots yellow ->
   red; hose edge exactly the 4 known rows on 3 Oregon City lots red ->
   yellow. Run 65 still showed 30 of those lots / 34 rows green.
   STILL PENDING: after the next weekly run (run 73 or later), spot-check a
   few of the 34 lots on the map, then remove this item. Keep
   /root/rank-colour/{diff.out,moves_ABR.csv,probe2.py} on 137 until the
   spot-check.
51. [Claude] [DONE 2026-10-14, run 73 LIVE; one check after the weekly] **Tigard and Cornelius switched on.** Run 73 (best
   design per lot): Tigard 829 green / 785 yellow / 17,137 red of 18,751 (the bound said
   840 / 777 / 15,544); Cornelius 0 green / 434 yellow / 3,811 red (the bound said 381
   green: the DEM-less scan and the solar-shade flag kept R-7 / R-10 off green -- the
   elevation was restored in run 74, so re-count Cornelius greens on the weekly).
   829 Tigard greens read 2026-10-14: the sample is ordinary RES-B houses; the odd ones are
   existing apartment complexes (28 lots, prop code 701, $0.6M-$19.6M of buildings),
   churches kept checked by ruling (911/913), one 981 charity at 11895 SW 91st Ave ($13.2M of
   buildings), and occupied TMU commercial. Steph RULED 2026-10-14 (register
   `2026-10-14-existing-buildings-stay-green`): occupied apartment complexes STAY GREEN (the
   map answers "does the pod fit", not "is it for sale").
   CORNELIUS R-10 lot 1N335CD01200 FIXED (5d3c1831 on main, rides the next weekly, no
   splice): Metro's layer prints 0.00003% of it as county AF-5, so quadfit s3 dropped it
   `zone_not_in_rules`; s3_filter.lot_zone_rewrites now applies the `lot_zones` hand
   assignment. It is the ONLY lot in the corpus with a `lot_zones` entry. CHECK on the
   weekly that the lot is screened.
   Unsure: the register (`2026-10-01-cornelius-solar-shade-warning`) makes solar shading
   green WITH A WARNING, yet run 73's note above names the shade flag among the reasons R-7 /
   R-10 stayed off green -- check which is true when re-counting.
8. [Claude] [scan: NO new code, check after the weekly run; YES if (b) is taken up] **Pockets + corridors -- leftovers (PROMOTED run 33 2026-09-27; pocket
   lots 210 -> 25 still ZONE_POCKET).** All code is on main and in the
   weekly runs since run 65; the two checks below are not recorded as done.
   (a) e7217598 -- s3 follows FLATS's pocket rulings (Clackamas R-MD ->
   Milwaukie, Happy Valley VR57 -> county, UPAR-10 -> Troutdale LDR-1).
   Check: NOT_MEASURED -9 (check by the pocket_of TLIDs; drift skips
   pocket lots).
   (b) OPEN: 25 lots stay ZONE_POCKET: Troutdale NSA GGC/GSO and Oregon
   City `County` read against a map that answers no code the of-layer
   holds.
   (e) c9083b88 -- 33.130.215.B.1.b: CM2/CM3/CE/CX street lines take 5 ft,
   0 only where s4's `street_across_json` reads every ray across as
   non-residential and the line is off the corridor; quadfit CE/CM2/CM3/CX
   front 0 -> 5. Check: bound said ~60 lots green/unknown -> yellow, 0
   loosened.
   Done: (c) 1ff23bdb Map 130-1 maximum 20 ft (no screen reads a maximum,
   HUMAN_TODO 12); (d) fa693288 per-line corridor minimum, run 39.
33. [Claude] [scan: YES for (c) and any speed-up (must prove identical answers)] **Parking court leftovers (fix ca26e048 LIVE as run 63, 2026-10-02:
   drift 61->63 green->yellow 3,459, unknown->yellow 4,453, 0 unexplained).**
   Still open ((a), the court beside the building, fixed f7ba7038; (d) the
   scanline raster ce65b86b DONE, 2.2-2.6x faster):
   (b) lots outside the 15,940 scoped whose court stands in a side or front
   yard INSIDE the lot are corrected only by the next full re-screen
   (weekly run 65 onward -- not recorded as checked);
   (c) s5o-envelope lots use the whole lot (less carve) as the court's
   ground. Next speed levers if needed: `has_window` in the court
   searches, `ground_for`.
21. [Claude] [Steph: worktree go; HUMAN_TODO 26] [scan: YES for (a)-(c); NO for (d)-(e)] **Post-2027 world (Steph 2026-09-29: "design the system for a post-2027
   world... retroactively apply that throughout our corpus").** Sources
   STORED 2026-09-30 (declared in `_state.yaml`):
   `or/hb.2138.2025.txt` (enrolled); `or/oar.660-046.adopted-2026-08.txt`
   (Division 46 AS ADOPTED 2026-08-27, DLCD's copy; OARD's filed text LCDD
   11-2026 is WRONG, correction hearing 2026-10-22 -- re-fetch after);
   `or/oar.660-047.draft-v5.txt` (Oregon Homes draft v5, 2026-09-22; re-fetch
   after LCDC's October meeting). Worktree, confirm with Steph first.
   (a) OPEN -- STATE LAYER TO ADOPTED DIV 46: quadplex min lot <= the zone's
   detached-house min lot (0220(2)(a)(B)), townhouse likewise (0220(3)(a)) --
   needs a per-zone detached-house minimum lot field read from every zone
   table and a preemption shape "cap at another field's value"; "zoned for
   residential use" (ORS 197A.420(1)(j)) as the scope limit the state layer
   has flagged NOT ENCODED since August; 0205(3) percentage option deleted --
   check whether any corpus city used it. Height floor (2)(d) unchanged; see
   the 2026-09-29 note in _state.yaml (SCR-OTC 20 ft not lifted).
   (b) OUT-OF-COMPLIANCE ZONES -- BUILT (relief `state_middle_housing`,
   discretionary, never GREEN), runs 46 and 49. DECIDED A 2026-09-30
   (Steph: "the 'larger cities' is important"; register
   `2026-09-30-state-middle-housing-path`). Size cutoff: inside Metro every
   city over 1,000 people (all ours but Johnson City, Rivergrove, Maywood
   Park); outside Metro 25,000+ for every type, 2,500-25,000 duplexes only;
   county land only where "urban unincorporated" (ORS 197A.015(12): UGB,
   urban zoning, sewer district, water provider, not a holding zone).
   OPENED 5: Portland RF, Multnomah uninc RF, LR5, LR10, Happy Valley FU10.
   REFUSED 8: Multnomah UF20 + Clackamas FU10 (holding zones, (12)(e));
   RRFF5/RA1/RA2 (rural, (12)(b)); Gresham LDR/GB (Goal 7 hazard,
   0010(3)(c)); Wilsonville RN + FDAHR (pre-2021 master plan,
   0205(2)(b)(B)); Wilsonville RN as townhouses CHECKED shut. Ambiguous 9,
   unruled: Clackamas FF10; Multnomah MUA20, RR, OR, GGR2 (mostly outside
   the UGB); Fairview VTH; Portland RMP; Milwaukie R-MD (unit-lot + flag
   variant); Wilsonville FDAHV. Happy Valley's child-lot refusals look
   allowed by the state rule. Traps from the audit: Clackamas FU10's note
   leaned on an "interim zoning" exemption (0010(2)(c)) that the ADOPTED
   text no longer has; ORS 197A.015 is not stored. CHECK on the weekly run (not recorded
   done): LR10 (MCC 39.4878) and Happy Valley FU10 dimensions were coded
   2026-10-01, and `in_sewer_district` is answered on unincorporated
   Multnomah (`DISTRICT_ONLY`); only Dunthorpe-Riverdale and Clean Water
   Services are sewer districts there and no RF/LR5/LR10 lot is inside
   either -- so those lots should read refused (red): not "urban
   unincorporated" under ORS 197A.015(12)(c). From 2027-01-01 the Div 46
   model code applies directly (0040(4), "completely replaces"): audit the
   corpus, switch them to allowed under the city's middle-housing
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
64. [Claude] [scan: NO (a reading exercise; fixes it finds get their own items)] **Measure the
   false-GREEN rate, so "are we converging?" has a number (offered 2026-10-09 when Steph
   asked whether the work ever ends).** Draw a random sample of ~100 GREEN lots from the
   live run (stratified by county/city, not by flag), read each one deeply and blind
   (zoning words, lot shape, access, fire, slope, tract/ownership) and count how many are
   wrong and why. Repeat after each weekly. Also log per fix: greens moved as a share of
   all greens, and whether the cause was a NEW kind of problem or a known kind in a new
   place. Stopping signal to propose to Steph: a week whose fixes move < ~0.5% of greens
   and find no new kind of problem -> switch from hunting to maintenance (code-change
   watch, item 54) + onboarding new territory. Steph to decide whether to run it.
   ROUND 1 DONE 2026-10-10 (flats/false-green-sample, data/flats/false_green/2026-10-10/,
   seed fgs-2026-10-10-seed1): 102 greens from run 70, 97 RIGHT / 4 WRONG / 1 CAN'T TELL.
   ROUND 2 DONE 2026-10-14 (flats/false-green-sample-r2, data/flats/false_green/2026-10-14/,
   seed fgs-2026-10-14-seed2, work/draw.sql, work/consolidate.py): 108 greens from run 74,
   97 RIGHT / 7 WRONG / 4 CAN'T TELL; weighted 5.5% (95% range 1.7%-14.6%). BOTH ROUNDS
   POOLED (207 lots, 9 wrong): 3.9%, 1.5%-8.9% -- the number to quote; no change between
   rounds. Wrongs: road land to the centre line x5 (items 67/77), WashCo transit-district
   Type II-only path x1 (item 79), Portland Main Street overlay minimum FAR x1 (item 78).
   Can't tell: Portland Map 120-2/120-3 (item 68), Wilsonville x2 and Wood Village TC x1
   (item 80). PER-FIX LOG run 70 -> 74: hunting fixes moved 156 greens = 0.31%; gains 1,152
   from new territory. STOPPING SIGNAL NOT MET: moves < 0.5% but one new kind and two known
   kinds in five new places; item 67 alone will move ~3% of greens.
   NEXT: round 3 after the weekly that carries 67/77 (both merged) and once 78-80 are
   decided; new seed, weight the same way. Not read yet: the 59 PUB greens.
   POLICY class (counted apart, never "wrong"): FLATS ignores existing buildings by design --
   e.g. 1S2E02BB  -01100, a 6.66-acre Portland CE lot with a 75,050 sq ft commercial building,
   GREEN with the pod in a corner. Steph RULED 2026-10-14 (register
   `2026-10-14-existing-buildings-stay-green`) that occupied buildings STAY GREEN; the
   2026-10-10 question "should a lot whose pod sits on a working building's parking or yard
   stay green?" reads as answered by it -- confirm with Steph only if a case differs.

95. [Claude] [DONE 2026-10-20 -- gains and losses read; remove at the next weekly] [MERGED to main 2026-10-19 (items 85 + 93, merge 0e097bc8)] **Weekly 2026-10-19 DONE 2026-10-20: run 76 promoted by Steph (lots_drift +2.4% approved); the 916 lot gains to green read by group and all traced to rulings or merged commits (ORS 197A.400 green+flag: Clackamas MR-1 161/HDR 27, Hillsboro MR-2/SCR-HD, Canby, Gladstone C3, Sandy; townhouse form; Clackamas commercial encoded by item 61; flatter placement on slope). One gap found and fixed: unincorporated Clackamas had no minimum density (5367d599: 1012.08 + Table 510-2) and floors with nothing to subtract went unchecked (81840884); splice of 5 cities -> run 78 promoted on the standing word, 0 map moves (a missed floor is a low-risk flag by Steph's 2026-10-02 ruling), 527 lots gain the DENSITY-MIN flag. LOSSES READ 2026-10-20 (run 74 -> 78, each group against its item's bound, samples read lot by lot): Portland 1,628 green->red = item 78's bound exactly (894 protected historic, 699 main-street minimum floor area, 35 both -- the "770 with no named reason" carry the reason in the bind); WashCo uninc 1,176 / 96 / 601 / 31 (g->r / g->y / y->r / y->g) vs item 67's 1,178 / 83 / 603 / 31; Oregon City 488 g->r vs item 82's 388 on the strip (+19 fire hose, +front-yard and D caps of item 84); Sherwood 21/0/31/2, Milwaukie 16/19/56/11, King City 1/0/5/0 at their bounds; Tigard 113 g->r + 141 y->r on the road widths (item 81, RES-B 154; reported to Steph); Clackamas uninc 604 y->r on item 61's north-face cut (RCC 67, OC 52, RTL 32, RCO 20, RCHDR 11) as rehearsed. Items 61, 69, 79, 81, 82 closed. WashCo Type II: 17,761 lots carry CLEAR-OBJECTIVE, 1,097 of them green (1,061 already green at run 74) -- the lane's ~60k yellow->green does not happen; the rest are red on the ground. LATENT, not live: PCC 33.415.300.B bars attached houses within 100 ft of a transit street in the "m" overlay; no Portland green rides the townhouse form today (0 LAND-DIVISION greens), so nothing is false-green -- if the townhouse form ever greens an "m" lot, it must read 300.B first.**
   **Townhomes on their own lots + ORS 197A.400 "clear and objective" ride this weekly.**
   Rulings: Steph 2026-10-15 townhomes = separate lots (register
   `2026-10-15-townhomes-separate-lots`) and judgement-only / "may add conditions" review inside a
   UGB = GREEN with the CLEAR-OBJECTIVE flag (`2026-10-15-clear-objective-green-flag`; the
   2026-10-16 Clackamas design-review entry now notes the state-law exception).
   EXPECTED at the weekly, from the bounds (all read lot by lot):
   (a) townhouse form, round 2 (b5c0cbf4, 137 /root/th_*): 81 greens, every one the townhouse form
   with the row facing the street -- WashCo TO:BUS 16, TO:R24-40 11; Tualatin MUC 8, RMH 7, RH 3;
   Wilsonville PDR4 2; Gresham OFR, Milwaukie R-HD, West Linn R-4.5 1 each; Fairview VMU 7, VA 3;
   Sandy R-1 6; Troutdale HDR 14, MU-1 1 (green once signed). Round 1's 132 false greens fixed
   (home-lot width/area, row end-on to the street, Troutdale LDR-1 3.140.B.3.a density).
   (b) clear-objective, cities (bound co): Estacada R-3 10 red -> 6 green / 4 yellow; Milwaukie
   R-HD/R-MD 13 red -> 3 green / 10 yellow; newly admitted Canby 108 green / 35 yellow, Gladstone
   C3 40 green + 31 yellow, Milwaukie NMU 14 green / 9 yellow, Estacada 57 yellow, Cornelius 14
   yellow.
   (c) clear-objective, unincorporated (re-bound co2 after the `inside_ugb` fix f003fd49, read
   2026-10-19): WashCo 335 yellow -> green (R-24 128, R-9 55, CCMU 42, R-15 37, NMU 26, R-25+ 22,
   TO:R9-12 10, TO:R18-24 10 ...); Clackamas 385 yellow -> green (MR1 161, C3 99, CC 31, HDR 27,
   OC 19, RTL 15, RCC 15, RCHDR 11, RCO 4, MR2 3); Multnomah LR7 1 red -> yellow. Every move is
   REVIEW-CONDITIONS -> CLEAR-OBJECTIVE and nothing else, except 22 where reaching green let the
   placement search pick flatter ground or a placement wholly in one zone (slope / split-zone flag
   gone with the yellow; 11 of them by switching to pod80x25).
   WashCo Type II (~60k lots expected by the lane) is NOT in these numbers -- read the weekly's
   WashCo yellow -> green total against it and report the real count.
   Still open from the lanes: Canby R-1 (townhouses only via a planned development) red; the
   statute's exceptions (Portland central city + Gateway, historic) excluded; zones the code does
   not list at all stay red (Happy Valley MUC/RCMU/CCC, Wilsonville PDC, Milwaukie MUTSA, Oregon
   City MUE); item 94 (row held to the street's angle, false reds only).

### 1b. Built lanes not merged yet (merge so they ride a weekly)

24. [Claude] [Steph: confirm deleting flats/oc-two-approaches] [scan: YES] **Oregon City 16.12.035.F -- one driveway approach per two townhouses
   (Steph 2026-09-30, from the page check).** "Townhouses shall have one
   driveway approach for every two dwelling units (round up ...)". RULED by
   Steph 2026-09-30 (page-check flag #1; register
   `2026-09-30-oregon-city-two-approaches-requirement`): a REQUIREMENT --
   two separate approaches for the pod; "I don't think we're counting for
   anything more than 1". STEPH 2026-10-10 then asked whether state law
   overrides the rule. RULED 2026-10-10 (driveway-state-law): (i) STATE LAW
   OVERRIDES F. Large Cities Model Code (Exhibit B, stored) has NO per-unit
   minimum: townhouse "maximum of one (1) driveway approach ... for every
   townhouse", no corner lot "consolidate access for all lots into a single
   driveway". OAR 660-046-0225(1)(c) ("design standards may not scale by the
   number of dwelling units") + 0220(3)(f)(C) bar F as requirement or cap.
   0220(2)(e)(E) and (3)(f)(C) also require the SAME access standards as
   detached houses (OC 16.12.035.D.1: a house on one local frontage gets
   exactly one driveway), and OC's own 17.16.040.B.3/B.2 consolidate access
   into a single driveway. HB 2138 s.22 strengthens, not weakens. No 0235 alternative-standards
   filing found for OC Ord. 22-1001 (reopen if one turns up). Sweep: no
   other encoded city states a per-unit approach MINIMUM; Hillsboro/Tigard
   cap "one per two units" (never binds a one-approach pod); Durham 7.12.9
   pairing is an option the pod does not use. STEPH 2026-10-10: ENCODE the
   city rule anyway, with the state override on top, so a pre-emption
   filing by OC or a change in state law flips it back by deleting one
   override (register `2026-10-10-oregon-city-encode-approach-rule-with-override`).
   STATUS 2026-10-16: BUILT on flats/oc-driveway-preempt (0c1acab7, f08c5766,
   3fface67; worktree .claude/worktrees/bridge-cse_01AscZHMyQcrv55zaVAUrca4),
   OC bound read: ZERO colour moves, as expected. NOT MERGED -- merge it.
   Do NOT merge flats/oc-two-approaches (the old requirement build: 2,197
   OC greens -> yellow); Steph to confirm, then delete it.
   CORNELIUS (R-7/R-10/A-2/CR/GMU) "not more than two lots may be served by
   one shared driveway" is NOT state-overridden (it binds detached lots too)
   and would need a 2nd approach on the unit-lots plat; not encoded (no
   field, item 25 held). REOPEN when Cornelius is signed or item 25 is built.

### 1c. The rest, most urgent first (dated items first)

100. [Claude] [scan: YES (yellows only go green)] **Driveway street: measure it instead of asking
   (follow-on of 88/89, merged e63617b8 2026-10-20).** A driveway too wide for the frontage cap on
   the lot's shortest street but fine on a longer one is now YELLOW (MEASURE-DRIVE-STREET), not
   red -- the screen does not draw which street the drive uses. Expected at the next weekly: the
   bound's 53 Happy Valley yellow->red come back yellow; ~28 Beaverton and 2 Sherwood reds go
   yellow; Gladstone R-7.2 gains 50 (side yard 7.5 -> 5 ft, read). Two ways to turn these yellows
   into answers: (a) measure the street line the drawn drive crosses (as `parking_frontage` does
   for the court); (b) a Happy Valley street-class map, so 16.44's lowest-class corner rule can
   pick the street (corner lots stay yellow on ACCESS-STREET-RANK-UNKNOWN until then).
94. [Claude] [scan: YES -- false reds only] [after 93 merges] **Townhouse row held to the street's
   angle -- up to ~105 false reds (found by the round-2 read of item 93, 2026-10-17).** The
   townhouse form sets the row of four home lots parallel to the street line. On a lot whose side
   lines meet the street at a slant (example 1S126DD01800), a row set square to the SIDE lines
   would still give every home lot its street frontage and fit. Fix: also try the row square to
   the side lot lines (and keep the frontage + per-home-lot width/area checks of b5c0cbf4 on the
   tilted row); then bound and read every gain. Never loosens a check, so no false-green risk
   beyond the usual read.

86. [Claude] [Steph: (B) unattributed rulings] [scan: YES for (C1) once entered] **Agents could not recall a property ruling (Steph
   2026-10-15, GO for A/B/C1/C2 the same day). A, B, C1, C2 MERGED; the DLCD backlog is READ.**
   DONE: (A) `flats_find_lot` / `flats_lot_report` / `flats_rulings` JSON routes = VicinitiDeals
   MCP tools, CLAUDE.md rule. (B) flats/config/rulings.yaml (93094b35; additions 3a06a3e8,
   16d3d94a), test_rulings_register.py. RULE: every new Steph ruling gets a register entry in the
   same commit that encodes it. (C1) RICAP 11 (56efd334): adopted changes carry adopted/effective
   dates on the zone (rules loader `law_on`, run-key `law`). (C2) DLCD watch (38528135):
   scripts/flats_dlcd_watch.py + flats/watch/dlcd.py, ledger flats/config/dlcd_read.yaml, runbook
   docs/ops/flats-county-refresh.md 4f; Steph 2026-10-15: run it EVERY WEEKLY (coordinator runs
   it from this PC; an Opus agent reads every new notice). Backlog of 76 adopted + 92 proposed
   notices READ 2026-10-15 (96cc32ba): 6 encode, 16 watch, 146 no effect; encode items -> 88, 89.
   STILL OPEN:
   - (C1) CI1 opens 2026-11-01 under RM1 standards (est. 60-95 of 143 CI1 lots leave red at the
     first run after Nov 1) -- READ that run's CI1 moves; check item 2(d)'s CI cap guard then.
   - RICAP 11 MP5 (back-out pads <= 2 stalls), MP4 (aisle) and TA9 rooftop rear setback are not
     encoded (check later).
   - (B) left out of the register as unattributed/ambiguous: FEMA fringe yellow, landslide list,
     Tigard MUR stricter column (tigard.yaml L972), Portland total-turn, Hillsboro SCR side,
     Milwaukie 22 ft aisle -- add when Steph rules (FEMA fringe and landslide have since got
     entries: `2026-10-06-fema-fringe-stays-yellow`, `2026-10-05-landslide-slopes-declined`).
   - WATCH list: Portland design-review suspension to 2029 (yellow->green possible), Happy Valley
     code update (PC 2026-11-10), Sandy middle housing (2026-10-26/11-16), Canby UGB + Wilsonville
     annexation (new land), Oregon City geohazard clear path, Portland state-law compliance +
     central-city projects.
2. [Claude] [scan: YES] **Neighbour zoning per lot line -- loose ends after the measurement
   (4b25df09 + the carve fix cfc8c033; run 12 PROMOTED 2026-09-22; Wood
   Village TC 28850154 and the whole-block answer 86b06340 in run 16;
   the nine `AHEAD_OF_QUADFIT` zones 0504ef84 in run 14).** s4 reads the
   zone across every non-street line; FLATS answers
   `abuts_nonresidential_zone` in Portland / Troutdale / Fairview and
   `abuts_residential_zone` in Oregon City (ANY line tightens, EVERY line
   relaxes; anything unresolved stays UNKNOWN). Still owed, most lots first:
   (a) `abuts_lower_density_zone` is declared in Clackamas `_unincorporated`
   only (ZDO Table 315-4 note 14 = the 10-ft variant on MR1/MR2
   `setback_side_ft`). An observed fact lifts a caps.json cap and the base
   number would certify with the footnote's other number never encoded
   (`test_no_declared_condition_caps_a_value_on_that_layer`), so the city
   still capped stays undeclared: Oregon City R-2 (twelve fields; the note
   narrowed to `zones: [R-2]` 2026-09-22) is a dead end until
   `utility_easement` is read, because every OC R zone is capped on THAT
   fact on every field too (no easement layer in RLIS -- a measurement
   question, not an encoding one). Unchecked: whether item 43's PUE
   street-yard rule (a9106379, Oregon City since 2026-10-05) changes this.
   (c) 1,938 lots in the turning zones still lean on the fact: 813 a blank
   point across a line (park / ROW / fabric gap), 802 no non-street line
   at all (ANSWERED 86b06340 where s4 traced the lot and it is not
   irregular: 1,565 lots; the tier-C and untraced ones stay unanswered),
   272 a split-zone neighbour, 46 both, 5 a neighbour in another city.
   `abuts_park` BUILT a89a3b9b from RLIS ORCA (live in run 42; only
   Troutdale conditions on a park in the corpus). ORCA was never acquired
   into snapshot 2026-09-18 -- acquire it at the next county refresh
   (`rlis_orca` is registered in pipeline.yaml).
   (d) Portland CI1/CI2: 33.150 gives a CI lot 10 ft against OS, so the
   shared Portland list is wrong for CI home lots -- safe only while CI
   stays capped on `site_specific_limitation` (guard test); a per-zone list
   and the across-the-street reading (33.910) when that cap lifts. Note:
   RICAP 11 opens CI1 on 2026-11-01 (item 86) -- check this guard then.
   (e) Troutdale's 5 ft side against HDR is unread -- SIZED 2026-09-23: at
   most 13 MU lots see an HDR neighbour, the unread half only relaxes
   (7.5/15 -> 5), and reading it needs a fourth neighbour fact ("every line
   non-residential OR HDR"); recommend leaving it unless those lots come up.
13. [Claude] [scan: NO -- lands with the November county data refresh] **Tax code area in the RLIS ingest.** The Gresham tax-impact snapshot
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
53. [Claude] [Steph: (b) Molalla PDFs; (c)-(d) HUMAN_TODO 30; (f) Downtown yes/no] [scan: Estacada + Canby/Sandy DONE in run 73; Sandy REVERSED by r3 (83a7683d on main), rides the weekly ~2026-10-19; (b)-(f) below still open] **Canby, Sandy, Estacada, Molalla.**
   Steph's by-right-only ruling (2026-10-08) made Canby and Sandy RED in every zone
   (register `2026-10-08-by-right-only`, `2026-10-08-canby-no-state-fourplex-backstop`,
   `2026-10-08-sandy-no-state-fourplex-backstop`; each zone note
   opens "RED BY RULING" so the ruling can be reversed). REVIEW TIERS (Steph 2026-10-14, r3;
   register `2026-10-14-review-tiers`): Sandy R-1/R-2/R-3 come back YELLOW -- the 17.90.40 B
   design review applies stated standards but may add conditions (REVIEW-CONDITIONS). Bound
   on run 74's inputs: 0 green / 108 yellow / 1,853 red of 1,961 (R-1 779 red, 719 on fit;
   R-2 69 y / 510 r and R-3 39 y / 564 r, mostly the landscaped-area minimum). Canby
   re-checked and stays RED: the 16.49.030 Type III review is a one-off judgement (zone notes
   quote it). Steph 2026-10-15 (item 85, not merged yet): judgement-only red and the "may add
   conditions" tier both become GREEN with a flag inside a UGB -- the clear-objective bound
   shows newly admitted Canby 108 green / 35 yellow and Estacada R-3 10 red -> 6 green / 4
   yellow, so Sandy's yellows move again when 85 merges.
   Estacada (run 73 LIVE): 14 green / 7 yellow / 2,860 red of 2,881; admits C-2, CMU, R-3
   (townhouse lots only) and NCR (only within 200 ft of Eagle Creek Rd or Hinman Rd,
   `near_named_street_200ft`, flats/geom/named_street.py); the 16.132.015 planning-staff
   review Steph ruled by-right (register `2026-10-08-estacada-staff-review-by-right`). All 14
   greens read by hand; doubts, none changed: 34E17 02000 (30941 SE River Mill Rd) is a
   split-zone lot, 47% NCR, its band not checked against the zone line; 34E20AB01200 (30905
   SE Eagle Creek Rd) is an occupied apartment complex ($3.9M of buildings); 34E20AC00200/00201
   (1015 NW Wade St) are two COM lots whose owner the roll does not give; `inside_ugb` was
   false on all 14 (the UGB layer was not read -- fixed f003fd49 on flats/clear-objective).
   Checks Steph asked for (2026-10-08): wetlands overlay = the NWI layer already applied;
   historic overlay = inventoried buildings only; 33% geotechnical = already stricter in
   slope.yaml (15%). Still open:
   (b) Molalla (HUMAN_TODO 29, Steph's PDFs): 7 of 11 chapters (2.3, 2.4, 3.2, 4.4 still 429)
   -- layer files parked outside the repo unless all 11 land (copy in /tmp/fg53/molalla_parked
   + the new 5.1); gate already read: admits R-2, R-3, R-5, refuses R-1, C-1, C-2, M-1, M-2,
   PSP; ALSO check whether those zones need design review.
   (c) NCR "major collector" half of EMC 16.25.020 is unmeasured (no street-class map for
   Estacada; Currin Rd looks like one) -- lots near it screen RED; add the name to STREETS in
   named_street.py once Steph confirms (HUMAN_TODO 30 q5).
   (d) Airport Safety overlay (16.54) zone map, side-line PUE (the code only says the city MAY
   require 10 ft), parking facing Eagle Creek Rd and the Currin Creek 70 ft strip: Steph's
   answers pending in HUMAN_TODO 30 q1-4.
   (e) minimum density 8.712 du/ac in C-2, R-3, NCR on the unit-lot path (the quote check
   wants a printed operand; needs a form that holds half of a per-dwelling area).
   (f) the Canby/Sandy doubts (design review, 20 ft yards, 13 du/ac, overlays) were MOOT
   while the by-right ruling held -- re-read them once item 85 lands; Estacada's R-3
   townhouse-only reading and the MMU Council-master-plan refusal were re-read 2026-10-08
   and stand; the Downtown zone (D) could be encoded with the named-street tool (fourplex
   outright if it does not face Broadway/Main/OR 224, north of OR 224, 16 du/ac) -- waiting
   on Steph's yes/no. Forest Grove stays blocked on HUMAN_TODO 28.
87. [Claude] [scan: YES -- greens only lose] **Protected historic buildings outside Portland (found
   2026-10-15 by the register audit).** Steph's 2026-10-14 ruling (protected historic building on
   the lot = RED) is built only from Portland's historic resource map (Portland + Multnomah uninc).
   Other cities' landmarks and districts (e.g. Oregon City McLoughlin, West Linn Willamette, Milwaukie,
   Lake Oswego when re-enabled) are not screened -> possible false GREEN. Next: find a statewide
   source (Oregon SHPO Historic Sites Database / National Register GIS; ORS 197.772 + OAR
   660-023-0200 decide which listings are "protected"), else per-city maps; apply the standing rule
   (no re-ask), bound, read losses. Standing rule, no question for Steph.
68. [Claude] [scan: YES, after Steph or the agent supplies the maps] **Portland Maps 120-2 and 120-3 are not
   held (found 2026-10-10 by item 64's sample, 1 can't-tell).** 33.120.206 bars new homes on a site
   deeper than 160 ft with under 90 ft of frontage, but only on the sites shown on Map 120-2
   (Eastern Portland centres); 33.120.220.C adds a rear-setback rule for Map 120-3 (Eastern Pattern
   Area). Neither map is in the store (portland.yaml ~724), so both are left out and the lots stay
   green. Upper-bound reach: 902 Portland multi-dwelling greens are deeper than 160 ft with under
   90 ft of frontage (RM1 647, RM2 208, RM3 47); how many sit on the map is unknown. Sample lot:
   1N2E21AD  -06200 (RM1, 50 x 200 ft). PROPOSAL: fetch the two maps from the City's open-data
   portal as polygons (or get them from Steph), then add a frontage check and the rear setback with
   a corner exemption. Until then, consider marking these 902 yellow.
90. [Claude] [(a)'s check change Copilot-able] [scan: NO (citations move, answers must not)] **Cites that name a section
   the cited lines do not sit in (found 2026-10-16, docs/ops/quote-mismatch-2026-10-16.md).** (b)+(c) DONE
   8775562a 2026-10-21: 63 cites fixed in Estacada, Gladstone, Oregon City, Fairview, Troutdale, Wood
   Village, Tigard -- the quoted lines were right, the cite named a neighbouring section; no value,
   condition or quote moved. Counts now (a) header_or_xref 283, (b) 48, (c) 0, (d) unlocated 9. The 57
   left are the CHECK's errors, not cites: lagging page headers beat a real heading (Sherwood 16.94, King
   City 16.114.130 -- a fix added 89 false cases, reverted); Sherwood's 16.12.030 heading missing from
   the stored text (43, hand-checked correct); Beaverton cells "18.511" / "see 20.25.15" read as
   headings; the cite reader takes "Table 18.805.1" as a section and cannot read "19.65.030 through
   19.65.060". Next: teach the check to ignore (a). Also: Gresham NC-PV quadplex_allowed cites Tables
   4.1413/4.1415A/B but its quote is Table 4.1423 ("Quadplex NP") -- DONE 751bc5d5.
83. [Claude] [scan: YES (yellows only go green)] **Measure Washington County's "standard plat" gate instead
   of flagging it (offered 2026-10-14, item 79).** 731 R-9/R-15/... lots are yellow only because
   nothing says whether the lot was made by a standard subdivision or partition plat (302-2.14 ..
   307-2.13), so unmeasured = worst. A lot's recorded legal description names its plat ("PARTITION
   PLAT 2004-123, LOT 2", or a subdivision name and lot) where it was platted, and reads metes and
   bounds where it was not -- that measures "made by a plat". "Standard" vs a PUD or expedited land
   division needs the land-use case type behind the plat. Candidate sources, NOT checked yet:
   Washington County Assessment & Taxation property records (legal description per tax lot), the
   county surveyor's plat index. First step: confirm either holds the legal description in bulk
   for the WashCo uninc lots, then rule how a PUD plat is told apart.
   SOURCE FOUND 2026-10-15: Washington County's Taxlots FeatureServer/151
   (gispub.co.washington.or.us/server/rest/services/Urban_Services_Plan_Framework/Urban_Services_Framework/FeatureServer/151),
   free, 2,000 per page, LEGAL_DESCRIPTION on 201,183 of 201,678 lots ("VIEW CREST, LOT 3",
   "2016-037 PARTITION PLAT, LOT 1"; metes and bounds otherwise). PUD named in the text on only
   58 lots; no case-type index found, so standard vs PUD is not separable from it. Next: read the
   CDC gate -- does a PUD plat change the answer? If not, measure "made by a plat" and go.
66. [Claude] [Steph: (a), (d)] [scan: NO for (A); YES for (B)] **A price check beside the fit (Steph 2026-10-10: "Do we
   not have a financial screen? If there's a large commercial use ... redevelopment wouldn't
   support") -- (A) LIVE 2026-10-10 (merge d1d8c03f).** STEPH RULED 2026-10-10 (register
   `2026-10-10-price-per-home-label`): (A) -- colour unchanged, a PRICE PER UNIT label + a
   filter set at $30k/unit ($120k a pod), adjustable ("land price is passed to the buyer, so
   it flexes with the market"; look at everything). Units = pods the lot could hold x 4, NOT
   one pod: a big lot pays for (lot area - roads to serve the pods) / (pod + its parking),
   with parking possibly pooled to save buffers and planters (pods stay independent). STEPH
   CONFIRMED 2026-10-10 the defaults (4,500 sq ft a pod incl. parking + yard share; 25% to
   roads on lots of 3+ pods) and the guards: pods capped by the zone's density limit;
   multi-pod counts labelled ESTIMATE (new roads / a land division may need a review);
   county market value by default, last sale shown beside it; the two defaults adjustable.
   Price is rough until a PAID price feed arrives (vendor TBD, ~2 months): a paid feed goes IN
   FRONT in flats/score/price.py PRICE_SOURCES with one entry (each price carries its source +
   date). True layouts stay item 31 / parked 92.
   Built: table flats.lot_prices (migration 0143), app/services/flats_price.py, settings
   flats/config/price.yaml, filled by scripts/flats_load_bridge.py and
   scripts/flats_backfill_lot_prices.py (run it for the live copy, and again after a rule
   change moves a zone's density limit). TRAP: the first deploy (34e1a771) HUNG PRODUCTION
   and was reverted (4670491e) -- it worked the price out of each lot's JSON per row against
   the wide lot table; keep the page on the stored narrow columns (work_mem 128MB, 25 s
   statement_timeout inside a savepoint).
   (b) BUILT 2026-10-16 (77d466a0 on main): stored cap inputs now include max_units and
   whether density is measured on net area; the columns come from migration 0145 (renumbered
   from 0144 by 4e668a34) and a repeat run of scripts/flats_backfill_lot_prices.py -- that
   backfill re-run on production is not recorded as done; colours are unchanged.
   Open: (a) filter is opt-in, not on by default -- Steph to say if it should start ON;
   (c) ~10 greens carry county values under $1 a sq ft (price per home of $17-$950) -- shown
   as-is; (d) a "value looks too low" mark -- Steph to decide. Only (a) and (d) wait on Steph.
71. [Claude] [scan: NO unless it finds a siting rule] **Building-code editions (Steph 2026-10-10: "ORSC 2026
   came into effect 10/1/2026 -- is our app built on that or the previous version?").** The screen
   reads NO building code for pass/fail: it is zoning + fire access (_state.yaml) + the OSSC 2025
   accessibility chain (HUMAN_TODO ~L465, ENCODING_RULEBOOK 2026-09-03).
   EDITIONS CHECKED 2026-10-16 (1686bbd3, notes only): ORSC 2026 = IRC 2024, in force
   2026-10-01, mandatory 2027-04-01; OFC 2025 (IFC 2024) in force 2025-10-01, the 2022 OFC
   lapsed 2026-03-31. OPEN: (a) `fire_access_max_ft` (150 ft) still cites the 2022 OFC --
   re-cite to 2025 OFC 503.1.1 once its text is read; (b) BCD 26orsc-matrix lists R302.1
   (separation when townhouses share a lot) and R302.3 ("townhouse" = 2+ units) changes --
   read the adopted 2026 text (ICC reader 403 to the agent) before calling them inert. A siting
   change gets its own item.
17. [Claude] [Steph: (c) HUMAN_TODO 28; HUMAN_TODO 25C] [scan: YES] **Washington County: drafts reviewed; publish, then the county map.**
   Steph 2026-09-29 (evening) answered HUMAN_TODO 25: A NO second cloud
   round -- Tigard, Cornelius and the 11 community plans are done LOCALLY
   (usage reset, 'go hard on data processing'); B design rules are catalogued
   and encoded (item 20); C the 19 city questions printed for Steph to send;
   D HB 2138 read (enrolled text): North Plains owes duplexes only, Banks and
   Gaston nothing -- they stay out.
   DONE and live: (a) the layers published 0e45ffd5; (b) b53873cf rulings
   2026-09-30 (handoff §6); (b2) transit distance ceb6693d, run 48 (Steph:
   "build it for all"; "SHOW IT, DON'T SCREEN IT" -- register
   `2026-09-30-transit-show-not-screen`; the pod keeps 4 stalls; OAR
   660-012-0440 stays NOT ENCODED); (d) the county map ef08aebc, snapshot 4
   run 51, Tualatin CC drawn area; (e) the PUE question became item 43's
   rule (a9106379, Steph 2026-10-01: a 10 ft yard on every STREET line ->
   green, 5 ft -> yellow, else red; register
   `2026-10-01-beaverton-utility-easement`); net area became item 30
   (Steph's option A 2026-10-02); (f) Tigard and Cornelius drafted,
   merged and switched on in run 73 (item 51); the Cornelius/Tigard rulings
   of 2026-10-01 are in the register (`2026-10-01-cornelius-*`,
   `2026-10-01-tigard-*`, `2026-10-01-pod-ground-floor-12ft`) and in
   tigard.yaml's comments (MUR stricter column). The split-path
   `per_dwelling` double count is FIXED in the reader. Still open:
   - Left for the cities (HUMAN_TODO 25C): Sherwood PD plans + Old Town
     zones, King City NMU patch, Durham MDR.
   - Not in the transit layers: SMART, CAT, SAM, SCTD (reads as far from
     transit -- conservative for relief). MU-VTC Center Cores have no
     drawn boundary, so 3 stories stays held on every MU-VTC lot.
   - (c) FOREST GROVE (7,756 lots): REFUSED 2026-09-30 -- a Cloudflare
     Turnstile on every chapter (not to be bypassed). Asked Steph to save
     the six articles as PDFs (HUMAN_TODO 28); store them from the files,
     then rulebook 1-14.
   - Tualatin (Washington side): STEPH RULED 2026-10-02: PDI-RSIA 10% is
     per project site but the refusal stands ("this lot doesn't work for
     us"); RH/HR townhouse lot = the 10,000 sq ft fallback; RH/RH-HR/MUC
     stay unit-lot townhouses only (Quadplex is its own TDC 31.060 type,
     absent from their tables; Comp Plan Policy 3.2.1 is policy, not
     permission). Open: the CO refusal may miss the Ch. 58 townhouse path
     (58.400, Table 58-4, Block 1); RML lots now exist on the Washington
     side.
   - Tigard: TRACE the sub-area image maps (18.650.A/18.660.A/18.670.A,
     ~590 acres MUR/MUC/MU-CBD) LATER (Steph 2026-10-01) -- until then
     those lots stay review.
   - The county's 11 community plans (Aloha, Bethany, Cedar Mill, ...) as
     neighbourhood variants in the county layer -- not confirmed done.
   - Still to measure: Hillsboro `flag_lot` assumed on 48,650 answers (the
     same assumption holds 12,668 in Clackamas); the bigger
     next-to-a-named-zone setback (Hillsboro SCR-DNC, Beaverton downtown);
     Hillsboro's corner coverage bonus + two corner setbacks
     (test_corner_variants: measure before deferring again).
   - (g) JAN 1 2027 (HB 2138 sec. 4): every Metro city must re-conform its
     middle-housing code (cottage clusters by 2028); a city that misses it
     gets the state model code directly. Run the drift check on every
     layer in early 2027 -- expect amendments across the board.
52. [Claude] [scan: NO for the leftovers below unless one is built]
   **Lots dropped before a fit (run 65) -- SHIPPED 2cfd13d6 (POD_CANNOT_FIT red by
   arithmetic: 10,028 lots yellow -> red, all previously NOT_MEASURED); zone codes read
   2026-10-09, LIVE in runs 69/70 (ef4b272f, b9ced2fe, 9eb9f618).** GEOM-UNREADABLE is not
   broken outlines: it is the complex-shape cap (convexity < 0.80, > 10 edges, pole-like);
   only 357 yellow lots are held yellow by that flag alone -- left as is.
   Steph 2026-10-09 RULED (register `2026-10-09-milwaukie-dmu-optional-review`,
   `-clackamas-design-review-zones-red`, `-hillsboro-anx-yellow`,
   `-gladstone-portland-avenue-yellow`): Milwaukie DMU ALLOWED (design review optional via
   clear and objective standards); Clackamas MR-1, MR-2, HDR were RED BY RULING (ZDO 1102.01(A)
   design review; the same sentence reached PMD and VA) and 163 green MR-1/MR-2 lots went red --
   SUPERSEDED by the 2026-10-14 review tiers: all five zones (MR-1, MR-2, HDR, PMD, VA) stay
   YELLOW, not red. Steph was told 2026-10-16 and ruled (register
   `2026-10-16-design-review-default-red`): design review is RED unless a state or county law
   preempts it, but where the design review checks only clear and measurable standards the
   2026-10-14 tiers apply -- "this is where the 'design review' was 'clear and measurable'
   that's fine, yellow it is."; Hillsboro
   ANX stays yellow; Gladstone C2 Portland Avenue: YELLOW until known -- avenue-facing
   entrance + 25% ground-floor glass (GMC 17.18.050(3)(b)+(c)) is a fact about the building
   the catalog does not hold; no assumption about the pod. SHD/RCHDR/VTH stay unencodable
   (setbacks by compass bearing, ZDO 1005.02(L)) -> item 61. Note: the 2026-10-15 clear-
   objective ruling (item 85) may reach these design-review reds.
   TRAP: the splice cannot retire lots a re-run drops from s3 (assign keeps a measured lot's
   old row): a bound/splice scope must list those lots explicitly, as the 805
   MR1/MR2/PMD/VA lots were here.
   Still open (each touches 0 greens today):
   - OFFERED, not done: read faces_residential_zone_across_street per street line outside
     Portland so the Milwaukie DMU/GMU street yards can be released (0 lots today, all red).
   - Tualatin Basalt Creek 50 ft yard measured-zero (2,234 ft to the built parkway;
     re-measure when the extension is mapped or on annexation); Central Tualatin Overlay
     blocks (Map 10-3) and RH-HR 45 ft min height DEFERRED (0 lots, all red); 100 ft wetland
     yard, building separation, MUC 57.400 / Figure 57-1 height check.
   - Milwaukie Figure 19.304-2, 19.505.5.E.1, DMU 50 ft parking ban.
   - Fairview TCC Halsey storefront map (44 lots); VC stays because of the FLX alias; SCMU
     front setback and densities.
46. [Claude] [Steph: (d) after the measuring, (f) after the re-measure] [scan: YES (a proof run: every answer must come out identical)] **Scans (bounds) on 137 are the lanes' bottleneck (Steph 2026-10-06:
   ~1 h coding, then 5-6 h waiting for one scan at a time; four lanes
   queue on `heavy.lock`).** (a)-(c) SHIPPED 24a61695 2026-10-08
   (`flats/ingest/batch.py`: costliest lots first, memory-booked chunks, a
   dead worker costs one lot, `--cache`; proof 4 SAME on every run). 137 is
   now CPU-bound, so more than 14 processes buys nothing. (e) fewer lanes:
   not pursued. (g) GPU: Steph 2026-10-07 dropped it ("forget those two
   questions").
   (d) rented compute -- PARKED by Steph 2026-10-08 ("won't do for now";
   keep the research, don't delete it). 2026-10-09 RE-ASKED (Steph moving to
   Max 20x and 7-9 parallel agents; the Proxmox host is maxed -- 137 already
   has 16 of the i5-14600KF's 20 threads, so no free home capacity): est.
   at 7-9 agents ~3,000-4,000 vCPU-h/month beyond 137 = ~$250-350/month.
   Steph: NOT YET, MEASURE FIRST -- run a week at 7-9 agents, log how long
   checks wait on heavy.lock per day, decide with that number. Steph
   2026-10-06 PREFERS CLOUDFLARE (a commercial version would run there):
   Cloudflare Containers (GA 2026-04-13), many small boxes of at most 4 vCPU /
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
   until DELETED; one big machine, least build).
   (f) skip big PRIVATE lots by size -- Steph 2026-10-06 DEFERRED: "see what
   the institutional changes remove" (item 47), then decide. Item 47 has
   landed (ca06c2ff; scans skip institutional land c1a96d81), so this is
   now ready to re-measure with a full
   run's `timings.parquet` and bring to Steph. Measured before 47 on
   quadfit_2026-10-01_wash (418,021 lots screened): 861 lots >= 10 ac (660
   10-20, 167 20-44, 34 >= 44; biggest 194.8 ac 1S1080000504) = ~11% of the
   cost proxy; 47's signals (Washington PUB or PROP_CODE 9xx: 90; Multnomah
   ASSESSVAL 0 with TOTALVAL > 0: 109) leave ~660, mostly private (vacant,
   MFR, COM, farm, SFR acreage; Clackamas's 181 unsorted).
41. [Claude] [scan: YES] **Street class per lot line -- (a)+(b) SHIPPED 6b924963 2026-10-05;
   (i)-(iii) SHIPPED 2026-10-06 b03dcd88/92c5f1d9/972caa17, deployed.**
   Live: Gresham note 5 caps on measured `at_street_end` (False-only);
   `local_street` from Milwaukie's TSP map (True needs Metro to agree) and
   Wilsonville's (False only: Villebois "Collector Avenues" are the master
   plan's Figure 7). TRAP for every full re-screen: it needs ALL 7
   `street_class_*` keys (washington added) + rlis_streets acquired into
   the snapshot, or the facts stay unasked (safe, no gain). Rulings, in
   build order (memory project_flats_street_class.md; register
   `2026-10-05-corner-access-quieter-front`):
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
   depth (pessimistic), never to "none". Built: nothing measures the walk
   (RLIS 2851 is presence only, +/-10 ft; Gresham publishes no layer) so
   every street line takes the worst case: 7 ft on a Metro-local street,
   20 ft elsewhere (PWS 6.05.01/6.06.02), and the cap lifts.
   WashCo uninc 2026-10-06: 501-8.5 B(2)-(4) bars a 4-plex from
   collector/arterial/neighbourhood-route access, so `lowest_class` KEPT
   and ranked off the county TSP map (FClass2; an undrawn street ranks 0
   only where Metro calls it local). Bounds /root/street-class_bound_
   {base,new}5 and 6 on 137, every gain read.
   Still open: Tualatin through lots PARKED (351 lots, ~30 green if signed;
   an exact answer needs a court entered off the back street + a Tualatin
   class map); Wilsonville note P via easement layer 150 (low value while
   access_easement caps RN). Beaverton ROW strips are dropped in normalize
   since 77c99822; only bounds on the 10-01 stage files meet them.
6. [Claude] [scan: YES] **Where parking may SIT, and which street is "the front".** Offered
   2026-09-19 when Steph asked why the court is always behind. **Steph's
   ruling 2026-09-19** (register `2026-09-19-orientation-choice-order`):
   trying each street as the front applies ONLY where
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
   Through lots RULED 2026-09-30 (register `2026-09-30-through-lots`,
   built 67402fea as (i)): city governs -> follow it, unmeasured -> worst
   (Gresham/Clackamas access control, Tualatin/Fairview lowest-class
   access); free choice -> the end that fits.
   BUILT and live (s6s_siteplan.py): Slice A per-line fields, Slice B
   corner fronts (bound 364c360e), through lots + side court + trimmed rear
   court (bound v4 vs run 10, loaded 2026-09-20), (k) 4a3cc09c, (l)
   5cb2bd75/547e0578/94fed5e3, (n) 91840447, (o) 38932a24 (a zero front
   setback is the code's answer -- Portland Table 130-2 "none", Oregon
   City 17.35.060.E -- never an unknown). Bound files on 137:
   `/root/corner_diff.py`, `corner_moves.csv`, `/root/lane_diag3.py`,
   `/root/strip_chains/v2/replay2.csv`. Still open:
   (f) the rear court keeps a tie with the side court; Steph's "room for a
   2nd pod" could read the other way (prefer the side court so the rear
   yard is free) -- the ties are NOT counted: only the winning offer is in
   the output, so counting needs both offers written out.
   (g) the two-row court's lane lands on its near row's end where a stall
   is drawn (one-row courts turn the aisle to the lane; two-row need the
   landing carved out of the row or the lane run to the aisle band).
   (h) the alley-aisle court (`townhome_rear_court_alley_aisle`) still
   scores the whole room's exposure -- trim it to its stall row + back-out
   depth.
   (j) COUNTED, not built: in a ban city (Portland 33.266.120.C.1.a,
   Milwaukie 19.505.3.D.4.a) the side court is drawn on ONE side of a
   through-lot pod -- a court on both sides would help 8 lots.
   (k) left: bent fronts whose body swings off the strip (Gresham
   1N3E30CB -12300, ~238 of the 286 targeted) need an angled/jog lane.
   (l) left: whether an alley that stops mid-lot needs the flat-cut strip
   is open; 32E07DC03600: the curved line past the lane may be a street s4
   does not label -- worth a look.
   (m) COUNTED 2026-09-29 on 09-18 data: 32 wide fronts with no envelope
   cell in street reach = 7 overlay carve-outs, 6 round tier-C insets, 3
   tier B with no strip, 16 with a strip in both envelopes (an older s6s
   refused them -- re-check on the current run).
   (n) left: read the 15 cul-de-sac/angled "not a pole" losses on the
   county run (local trial 65 lost / 51 redrawn / 884 same).
   Queued behind it, each to bound first: (b) Portland 33.266.120.C.1.b:
   on a corner lot the court must sit behind the side-street building line
   and pave at most 20 % of the side-street setback -- the drawn lane is
   consistent by construction, so only "behind the building line" is
   unread; (d) Fairview 19.30.050(D)(2)(a) side-yard parking setback ->
   redirect ledger; (e) Gresham 3.0100: the front is fixed where the
   minimum lot depth is met in one direction only (needs depth both ways).
   ((a) struck 2026-09-27; (c) `lowest_class` now reads street class, item
   41.)
4. [Claude] [scan: YES] **Four places the screen and the county map disagree, found by the
   bridge's sample run (2026-09-17) and left alone on purpose.** Each its
   own change. Done and dropped here: the side court (15ffab9e, run 42,
   2,374 yellow->green; the 3 ft front rule cef95109); (b) alley as aisle
   (caad6f3f, item 3); (e) corner fronts (ca52f76a, run 28) with its
   leftovers (i) `lowest_class` (now read off street ranks, item 41) and
   (vi) b440fc67, plus the Gresham through-lot corner f171c994; private
   drives (Steph RULED 2026-09-30, register + memory
   feedback_access_rulings_2026_09_30.md, built dbc2cc40, run 42). Open:
   (a) the court's shape: an L/T-shaped search for the other 339
   quadfit-fits lots; two-row stall count. `court_across` draws one row of
   stalls across the lot (six at 9 ft = 54 ft); quadfit's s6s uses the
   largest rectangle behind the building either way round, so a 63-ft-wide
   Portland R5 lot seats eight along its depth. County run 2026-09-18
   (`/root/bridge_county2`): 517 quadfit-green / FLATS-yellow lots off
   their own lane, 268 of them seating eight with the row along the lot.
   The other direction: on the 13,196 lots both call green FLATS seats
   FEWER than quadfit on 3,881 (one row across where s6s found two) and
   MORE on 160 (`target` where quadfit's tier is `minimum` 100, `preferred`
   where `target` 58) -- find what the screen's row counts that s6s's
   rectangle does not before changing either. The stall count was decided
   2026-09-18 (HUMAN_TODO 18) and is out of this item.
   (c) quadfit's policy gates are not site facts: `z_overlay_constrained_site`
   (PCC 33.418), the overlay kill layers, `existing_*` current use and the
   sewer gate (`no_public_sewer` is a hard gate there; here `public_sewer`
   is observed but no Clackamas standard turns on it) -- 84 of the 178
   screen-GREEN / quadfit-red lots in the sample.
   (d) the sweep -- the screen tries 180 angles, s6 fits at the front
   bearings only; 94 of those 178 are quadfit `siteplan_no_layout` lots the
   sweep found a fit on. (c) + (d) county-scale: 21,660 GREEN-where-red.
   (e) leftovers still open: (ii) corner lots with an alley are left
   unnamed (the alley's name is resolved against either frontage); (iii)
   the court's end is assumed to reach the side street, as for a side
   alley; (iv) Wilsonville V: 25 answers lose slack because the long
   interior lines are now SIDE lines (7.5 ft) not rear (5 ft) -- correct by
   the code, never changed a colour; (v) three Clackamas-unincorporated
   unnamed lots moved on input vintage, replayed identical. Wilsonville
   4.001(157)(2) / MCC 39.2000 pathway corners: HUMAN_TODO 24.
   (`steep_slope` struck 2026-09-27: no standard in the corpus is
   conditioned on it; the hillside rules ride the overlay layers.)
3. [Claude] [scan: YES for the court placement; NO for the lot-page note] **Alley leftovers** (rear alley caad6f3f run 24; side alleys + the
   6-inch tight-fit rule 82d4c7de, run 26; whole-line fixes 8bf9a451 and
   59533da1 live in run 42; the partial-alley cut 288f0daa on main).
   RULED by Steph 2026-09-28 (register `2026-09-28-partial-alley`): a line
   an alley runs PART of is read carefully -- covered stretch only -- and
   the covered stretch is the travel lane only if long enough (covered run
   with buildable ground behind it >= stalls x stall width; probe 53
   partial rear lines, 30 long enough, 23 not). Left:
   (a) 36 of run 24's 4,803 quadfit cannot draw (knife-edge or a slanted
   alley), read and accepted.
   (b) Of the 55 side-alley lots gained, quadfit draws no pod on 23 -- 15
   because quadfit keeps the pod across the front while FLATS turns it (a
   wide shallow lot, court at the alley end), 3 an irregular block, the
   rest overlays; read, accepted; if Steph wants the drawing to agree,
   quadfit's s6s needs the turned pod.
   (c) quadfit s6s still reads the alley as the aisle on 3-of-5 (FIXED
   10f193ea, rides the next s6s run). The partial-alley fit compares length
   only; it does not place the court against the covered stretch.
   (d) Gresham's 200 alley lots fail lot area/frontage regardless.
7. [Claude] [Steph: HUMAN_TODO 27] [scan: YES] **Green and outdoor space: charge the SHAPE, not just the amount.**
   Done and live: (a) open space / landscaping read lot - building -
   pavement (2026-09-28, `paper.paved`; `OPTIMISTIC_CHECKS` is empty);
   (b) Portland 33.110.240's 12x12 square (10x10 R2.5) on the lot's own
   ground, 7bd2d1e4..674208b6, run 42: 3,056 Portland lots fail on the
   square alone (green->yellow); Milwaukie's 96 sq ft / 5 ft patio
   encoded. Open:
   - Whether to chase the Portland square's near misses is HUMAN_TODO 27.
   - A side-street court standing as a long side strip stays unmeasured.
   - Fairview VA's paper minimum (25 %; 3,102 sq ft) looks odd.
   - (c) for the county map only: landscaping share (Happy Valley 20 %,
     Portland RM 15-30 %, Oregon City R-2 15 %, Fairview 20-25 %,
     Wilsonville 15 %) -- s6s holds no landscaping reserve.
   - (d) what the leftover is FOR (sheds, ADUs, a second pod) is product
     direction, belongs with item 6's "least ground under pavement".
   Ruled NOT owed: Troutdale 8.120.B.1.b (balcony), Oregon City 17.62.057
   (multi-family), Wilsonville Villebois 25 % (communal), Gladstone /
   Tualatin / West Linn / Clackamas county state none.
10. [Claude] [scan: YES for (a), one lot; NO for (b)] **Two loose ends from the ruling pass.** (a) DONE 4b725b6a -- alias
   rulings can `observes:` a site fact; FLX->VC observes
   `inside_mapped_use_area`. Left: the one FLX lot (1N3E33AB-00500) is
   dropped by quadfit s3 (zone_not_in_rules); to make it count, add a
   VC/FLX rule to quadfit's rules.yaml. (b) THR is one lot (1N2E36DA-02200,
   the Gresham IGA-162nd pocket) whose code no published document defines
   -- not Gresham 4.0100, not MCC 39; ruled `to_read` and worth one
   question to Gresham planning if it ever matters; nothing else owed.
5. [Claude] [scan: YES, small sample (drawings move, colours must not)] **Draw what the screen fitted -- DONE (666c6837, full run 31 PROMOTED
   2026-09-27; new splice base 137 /root/bridge_draw_full, 0 splices).**
   Leftovers: the drawing keeps the verdict's angle, so on a wide shallow
   lot the plan can run along the street; a side-alley column is drawn as
   a row behind the building.
37. [Claude] [scan: YES for (iii); NO for (f)] **Flag system plan ("FLATS Flag System Plan.md", Steph 2026-10-02) --
   slices 1-(e) BUILT and LIVE** (34963899 slice 1 + approval page;
   6eb14ffe measure + lot page; 85712ad6 severity 0; flags tables
   0139-0142; cbc47269; check margins 7dc34722; room each way f3408efa).
   Steph's answers (register `2026-10-02-no-variances`,
   `-flag-below-three-stays-green`, `-minimum-density-a-flag`,
   `-colour-as-if-signed`, `-near-miss-one-foot-red`; memory
   feedback_flats_flag_plan_rulings.md): (1) no variances, a miss with a
   path is RED, path logged on the bind; (2) a flag below the line
   (severity < 3) keeps the lot green; (3) min density = low flag
   (severity 2 -> green); (4) colour stays "as if signed". Steph RULED
   2026-10-03 "Exactly 1 foot is red": short by 1 ft or more -> red (pull
   back later for targeted variances / no-parking ideas); under 1 ft ->
   yellow. Steph 2026-10-03: "measurement" is THE PREFERRED resolution type
   -- the other three (inquiry, document, per-lot review) are "the failure
   mode"; flag tables live in the app DB ("flags and warnings are
   equivalent data points just like a min setback is"); NO DEADLINE for a
   pending flag type (pending types top the approval page + the count is
   mentioned at session start). Steph 2026-10-04: "Start number 2
   [measure] first, then 1 [map + lot page], then continue"; room each way
   (Steph: "we need all dimensions ... oddly shaped lots?").
   TRAPS: drain on 114 needs --registry-out/--colour-out on /app/data;
   after promoting a run screened under the colour rule run
   `scripts/flats_flags.py sync` then `check` on 114 (nightly sync 10:30
   UTC). An ambiguous rule set binds nothing, so ~0.07% of rows stay yellow
   despite a 50+ ft fit miss (Wilsonville R, Hillsboro SCR-V) -- by design.
   OPEN: (iii) Gresham note 5 "end of a Minor Access Street" held on
   `local_street` (wrong fact) -- re-point + measure dead ends; worth little
   while sidewalk_easement holds the same Gresham lots. (e) extending
   severity 0 = encode each capped footnote's direction (most fact flags
   sit on footnotes with no stated direction). Unknown facts needing a
   title report: utility_easement 28k, sidewalk_easement 20k (run 63
   yellow lots). Plan gaps: flag history across county refreshes; bulk
   writes through the loader. (f) Phase 4 pod spec, deferred by the plan.
58. [Claude] [scan: YES] **Yellows held by one measurable question (offered 2026-10-08;
   first pass DONE c98be01d 2026-10-09; LIVE in run 69).** MEASURED: MEASURE-FIRE-ROUTE
   (paved type-2000 streets count as truck roads: Portland 348 rows yellow -> green) and
   FACT-CIVIC-CORRIDOR for Rockwood (`rockwood_design_district`, the city's own layer; 290
   rows / ~148 lots yellow -> green; SC/SC-RJ and CMF stay yellow). CANNOT BE MEASURED from
   data we hold, left yellow (counts per design):
   - FACT-AT-STREET-END (Gresham, 789): Table 4.0131 note 5 numbers are not encoded and the
     street-class layer cannot separate Minor Access Streets (see 37(iii)).
   - ACCESS-STREET-UNCONFIRMED (441): the only road line is a private drive or lies across
     someone else's land; no map says whether the lot abuts it.
   - PARKING-STRIP-UNCONFIRMED (213): OAR 660-046-0220(2)(e)(E) is an open reading of law,
     not a fact on the ground (Steph ruled yellow flag 2026-10-04; the question is in 36).
   - FACT-CIVIC-CORRIDOR (the rest): Gresham's own corridor map is the source, and Glisan /
     162nd are not on it.
   Open: a new source for any of these four would release them; nothing else queued.
27. [Claude] [Steph: (a)] [scan: YES for (a) if the answer changes the rule; NO for (b)] **Steph's Oregon City page check (2026-10-01): what is left.** All of
   Steph's answers triaged; card and reader fixes shipped (set-aside tint,
   other numbers held, yes/no cards say where they were read, smaller-face
   columns no longer read as footnotes, centred headings claim their column
   -- 129 boxes narrowed to one column across OC/Gresham/Portland --, notes
   on a group heading reach its rows). Left: (a) MUC-1/MUC-2/MUD/WFDD/C
   "front parking banned: yes" answered "differs" with no comment --
   17.16.060.E has a three-condition escape (local street + not corner +
   topography) held as binding; ask Steph whether the "differs" was the
   escape. (b) Other cities' prose refusals still need locating into
   `set_aside:` so their pages tint grey.
27b. Moved to 92 (Parking layout generator, the second item numbered 27).
25. [Claude] [scan: YES, when built (on hold)] **Driveway approach geometry, ahead of a second approach (Steph
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
   local frontage, never more than two). If the pod ever draws two
   approaches, all of these start to bind together: per-approach width,
   spacing between them, offset from lot lines, count per frontage. Since
   2026-10-10 Oregon City's second approach is overridden by state law
   (item 24), so the remaining trigger is Cornelius's two-lots-per-shared-
   driveway limit (item 24).
20. [Claude] [Steph: before a worktree] [scan: NO -- a catalog; nothing screens it yet] **Design-standards catalog (Steph 2026-09-29, HUMAN_TODO 25B).** Record
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
31. [Claude] [scan: YES (not started)] **Split a big lot to meet a minimum density (Steph 2026-10-02: "create
   a task for later ... immensely complicated ... large guesstimates on
   roads, utilities, etc. maybe never done").** A lot too big for 4 homes
   under a city's minimum density could still work as a land division
   (several pods, or pod + other lots). Needs guessed streets, utilities,
   tracts and each city's land-division rules. Until then, a lot whose
   ONLY failure is minimum density is yellow "closer look" (item 30), not
   red. Not started; may never be.
1. [Claude] [Steph: HUMAN_TODO 23] [the "look again" bullet Copilot-able] [scan: NO] **The county map copy: loose ends after the first promotion (HUMAN_TODO
   20).** The September copy (snapshot 3, run 10: 400,032 lots = 288,031
   measured + 112,001 unmeasured with a reason) was PROMOTED 2026-09-20.
   Done since and dropped here: condo records (e7217598, run 42); Happy
   Valley `MURM2`/`MURm2` both aliased to MURM; terrain (`dem_3dep` is
   acquired and the slope stage exists). Still open:
   - No writer for lot decisions in `app/` yet (they are inserted by hand
     or by a future review page). No lot decisions exist yet (0 rows
     2026-09-25), so the "look again" flag has nothing to mark until a
     review page writes some.
   - A decision on a lot whose verdict moved in a re-screen of the same
     copy (`promote --run`) is not marked "look again" -- only ground and
     zone changes are flagged, so a re-screen's moves are read in its
     drift report and nowhere on the lot page.
   - The 142 Multnomah `_unincorporated` RR lots behind a
     `planned_development` lever are a relief-policy question --
     HUMAN_TODO 23 (2026-09-25).

96. [Claude] [Steph: mark the 13 handed on] [scan: LIVE run 80 2026-10-21] **Hand-off: 13 open
   Gresham questions from 2026-08-17 -- ANSWERED 2026-10-21.** CMF (feedback 4-12): notes 1, 3a, 6, 7,
   8, 11 are all applied -- see the Table 4.0430 page (item 104). DRL-1 (13-18): corner frontage 40,
   townhouse 16/20 frontage and width, townhouse lot size none -- all held; depth 70 was held on corner
   lots too, now exempt on corners in DRL-1/DRL-2/DCC/DTM (35e6f087, LIVE run 80). Left: Steph marks
   them handed on.

99. [Claude] [scan: NO until a 2-unit design exists] **State middle-housing parking is held as a
   per-unit ratio (Steph 2026-10-19, page check id 248).** or layer defaults hold
   parking_min_per_unit 0.25 / 0.5 / 0.75 by lot size: right for a 4-unit pod (0.5 x 4 = 2 spaces),
   but the rule is a TOTAL per lot (OAR 660-046), so it would mis-scale for a 2-unit pod or any
   other unit count. When layout variants with other unit counts arrive, hold these as totals per
   building type. No colour moves today (every design is 4 units).

### 1d. Finance (underwriting) -- [Claude]; kept word for word (15 waits on Steph's answers)

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
102. [Claude] [Steph: Durham 273/282 say what differs] [scan: LIVE run 80 2026-10-21 (splice 1e2b45ae,
   main 67611b26)] **Gresham front lot line on corner and through lots (Steph page check 2026-10-20, ids
   295-298).** Corner: tried only facing a street that meets the zone's minimum depth -- no corner
   colour moved. Through: both ends are fronts (Table 4.0131 note 2) + a never-blocking flag -- 7
   answers red->yellow vs live (fire reach now from the nearer street; min density still holds them
   yellow). Rulings registered. Durham 273/282 left alone: no Durham ruling to read them against.
103. [Claude] [scan: YES for (d) only] **Page check: notes the cards still cannot ask (2026-10-20).** (a) DONE
   0387fc8a: a heading over several columns ("FRONT²" over Front Facade / Front Porch / Garage) now
   reaches each; 15 Table 4.0131 cards gained note 2, none lost a marker. (b) DONE a40e4be8 (merge
   e239cf80): headings printed sideways are read along their own direction; 27 Pleasant Valley p10 /
   Springwater p9 cards now box one cell, no other card moved. It found VLDR-SW's townhouse garage
   setback held 20 where the table prints 25 (fixed 55cbdef9, stricter only, rides the weekly). Left:
   Pleasant Valley pp7-8 (max_far, THR-SW frontage) still box several cells -- headings upright there,
   a different cause. (c) ~890 cards now say "<zone> is not printed on this page"; most are true
   (chapter-wide parking/open-space pages) -- watch whether Steph finds the line noisy. (d) RIDES THE
   WEEKLY: Gresham MDR-24 and corridor corner townhouse frontage 32 -> 25 and MDR-24 corner width
   42 -> 25 (dc79bd29) -- read those gains lot by lot at the next weekly. (e) A marker on the TABLE'S
   TITLE ("Table 4.0131 - Minimum Setbacks in Residential Districts¹") reaches every cell and no card
   asks it. STEPH 2026-10-21: "I think we have to" -- ask it, refined: a note on the table's title
   reaches every cell; a note on a COLUMN heading reaches only that column's cells; and the
   title-note cards come one after another in the queue so Steph can clear them in a run. DONE
   3783bfb5 (merge 0da52f03, LIVE): 92 cards gained a title note, none reopened; card answer numbers
   (#id) shown too. Limit: a column-heading note more than ~8 lines above a row does not reach it. (f) DONE 67a8d0b5: reading down a wrapped cell
   stops at a numbered block ("2. Minimum Street Frontage: Corner lots"); MDR-24's interior 45 ft
   frontage stopped asking the corner cell's note 10 (Steph check 646). Sweep: that one card only.
104. [Claude] [left: (f), (g)] [LIVE run 81 2026-10-21 (main 0060aad3); Gresham green 1,834 -> 2,039] [scan: (a) LIVE run 80 2026-10-21] **Gresham Table 4.0430
   notes, read note by note (Steph 2026-10-20).** DONE: all 18 notes read, plain-English page
   https://claude.ai/artifact/BQaymC5Un4njJZaTH9LJDf; note 14 encoded as civic_corridor variants.
   (a) Steph 2026-10-20 "Yes, map it". Gresham has NO map (zoning layer GME/Planning/MapServer/4 is plain
   CMF; Ord. 1830 2022 names the streets only). 659 CMF lots (505 red, 154 yellow); seven CMF blocks
   touch Glisan/162nd. LIVE run 80 (main 67611b26): true = a street lot line on NE Glisan or NE
   162nd north of Burnside (~59); false = CMF outside the seven blocks (~569); unknown = the ~31 behind
   the frontage in touching blocks (NE 183rd, deep lots, the NE Halsey strip). STEPH 2026-10-21 "only lots actually touching the street count as along. If it touches, it's
   along" -> behind-frontage = false, a lot touching Glisan/162nd (Halsey strip corner) = true. BUILDING. Was asked:
   do lots behind the frontage count; does the Halsey strip that touches 162nd only at its corner
   count. Vs live: 5 lots unknown->green (off the corridor, every one >1,247 ft from
   Glisan/162nd), 10 answers unknown->yellow (on it: the corridor yards do not fit); the unknowns wait on
   the two questions. (b) BUILDING (Steph 2026-10-21 "map Rockwood") note 12's target 7.0512.B.6 requires 3 storeys at the
   181st/Burnside, 181st/Stark, Burnside/Stark gateways -- yellow, should be red once Rockwood is
   mapped; (c) note 6 townhouse lot width not held on its own (low risk); (d) HOLD (Steph 2026-10-21: "could be a big change") row M buffering points
   to Section 9.0100, not stored; (e) BUILDING (Steph 2026-10-21) row C width/depth ratio for a single-lot quadplex in SC, SC-RJ,
   CMU not encoded.
   BUILT 2026-10-21 (flats/gresham-4430 c0c53f7f): along = within 75 ft of the centreline (frontage lots
   34-54 ft, nearest behind-frontage 125 ft); ratio row C on SC, SC-RJ, CMU, CMF (townhouse split exempt,
   note 6); NEW FIX Table 4.0420 note 2 -- CMF land division only on the corridor. Bound: 40 ratio reds
   (9 green->red), 16 note-2 reds (4 green), 3 corridor greens. (b) Rockwood does NOT reach the pod:
   7.0502(B) exempts quadplexes, 7.0512 "All Development" excludes townhouses -- no gateway reds.
   STEPH 2026-10-21 ANSWERED both: (i) "assume that the lots from the gis and other data sources we
   have are legal. Every lot we try to purchase will go thru a legal review" -> yes; (ii) yes. Were: (i) 4.0431.C lets an EXISTING lot of record that misses lot
   size, frontage or the ratio still be built on (and skips min density) -- treat every taxlot as a lot
   of record on the single-lot path? (ii) lift note 13's Rockwood setback hold, since 7.0502(B)/7.0512
   take the pod out? BUILDING both, then bound, merge, splice.
   ALSO (possible false GREEN, found by 109): 7.0420(J)(1)(a) 50% street-oriented frontage reaches plexes
   in the Corridor Design District, which 3.0100#L834 defines to include MDR-12, MDR-24, OFR -- encoded
   on the corridor zones, missing on these three (live: 54 greens). Added to flats/gresham-4430.
   BOUND (ead841e2, 25,660 Gresham lots): 289 move, 0 false GREEN -- +149 green lots of record (CMF CMU
   SC SC-RJ), +65 Rockwood setbacks, +81 both; -20 green on the 50% frontage (MDR-12 11, MDR-24 9).
   LEFT: (f) the 50% frontage is applied to the TOWNHOUSE form too (as on the eight zones that already
   carry it) -- J.1 names plexes only; read 7.0431 before exempting townhouses (possible false REDs).
   (g) 1S3E14AA-08900 + two big yellows fail the 150 ft fire hose at 167 ft -- placement on very
   large lots looks poor (too strict, not a false GREEN).
110. [Claude] [DONE 2026-10-21 -- remove at next bookkeeping] **Wilsonville Villebois vacant lots.** LIVE run
   82 (main 936fd020): an empty V lot goes through (.18)(B) SAP/PDP/FDP review ("may require
   modifications") -> yellow at best, flag FACT-NO-EXISTING-DWELLING; 31W15AC02800 + 31W15AC03623
   green->yellow, 72 lots flagged. Built-lot greens (20) kept on (.23)'s own standards.
111. [Claude] [DONE 2026-10-21 55213389 -- remove at next bookkeeping; drift 81->82 now shows green->yellow 2] **Drift misses colour moves made by flags.** Run 82's drift said "0 moved" while
   two lots went green->yellow on a new flag (checks->>'colour'); the agent caught it in SQL. A promote
   gate that cannot see a colour move can pass an unexplained one. Make `flats_promote.py drift` compare
   COALESCE(checks->>'colour', checks->>'if_signed') too, attribute it, and test it.
112. [Claude] [Opus reading; Steph sees the result on the page check] **Page check: show the passage that sends a number to another table, everywhere (Steph 2026-10-22: "I have no evidence that the cross-table references ... are accurate").** 81457395 added `via` (the cross-reference's lines) and boxes it above the table; only Gresham CMF corridor values carry it (note 14 of Table 4.0430). 958 cards say the zone is not printed on the cited page (Beaverton 241, Wilsonville 167, WashCo uninc 125, Multnomah uninc 94, Portland 72, King City 56, Oregon City 51, Tualatin 40, Gresham 32, Hillsboro 29, Sherwood 26, Troutdale 16, Rivergrove 6, Durham 2, Happy Valley 1); they now say "we have not stored the passage that sends us here". Sweep: per card, find the sentence that sends the reader there and set `via`, or, where the page is general text that applies to every zone, say so instead. flats/tests/test_citations.py already checks each `via` resolves. (b) Gresham open flags, 2026-10-22: 15 resolved flags got "Resolved" replies and are off the cards; 29 still open, to triage: 309, 362, 372, 386, 427, 430, 538, 556, 574, 637, 645, 677, 681, 712, 742, 752, 758, 846 (no follow-up); 479, 510, 555, 570, 572, 721, 724, 769 (fixed and re-asked, Steph has not re-answered); 639 (Steph re-answered "this is a footnote").

108. [Claude] [after 104 lands] [scan: YES (reds/yellows only go toward green)] **Every taxlot is a legal
   lot of record (Steph 2026-10-21, GLOBAL).** "Let's assume that the lots from the gis and other data
   sources we have are legal. Every lot we try to purchase will go thru a legal review." Lot-of-record
   reliefs were dismissed as conservative (e.g. Gresham residential note 2, Clackamas ZDO notes). Sweep
   every layer's footnote ledgers + yamls for "lot of record" relief on the single-lot path; take each
   (a new lot from a division still meets the table); bound per city; read gains one by one.
109. [Claude] [chunk 1 of 7 LIVE run 84 2026-10-22 (greens 48,185 -> 46,932, 0 unexplained); chunk 2 INGEST LIVE 75afe352 2026-10-22 (docs/flats/ingest_c2_2026-10-22.md: 18 outlines, 5 map-only PDFs to trace, 37 texts in flats/provenance/pending/ with declarations.yaml; NOT FOUND Clackamas CRC X-CRC-1/3/7a, Sunnyside X-SV-1, Gladstone parking map); chunk 3 BUILDING 2026-10-22 (Steph go; 2 workers: frontage-c3, newdata-c3); PLAN docs/flats/design_districts_plan.md] [Steph 2026-10-21: all go, ingest first, flat roof = RED, read WashCo plans, max 2 chunks/week] **Design districts (Steph
   2026-10-21: "we do need to incorporate Rockwood (and other) design districts").** Inventory DONE:
   docs/flats/design_districts_2026-10-21.md -- 84 districts, 62 reach the pod, 32 non-zone districts
   lack a boundary. TIER 1 false-GREEN fixes (no ask): (a) building-frontage share -- Beaverton Downtown
   50-90% (~150 greens), Beaverton mixed-use 60% (1,504 lots), WashCo NMU/CCMU 50%, King City Kingston
   Terrace entrance -- BUILDING flats/frontage-share; (b) Portland main street "m" townhouse ban within
   100 ft of a transit street + 70% build-to + vehicle cap; historic/conservation district vacant lots;
   "d" overlay yellow claim nothing implements -- BUILDING flats/pdx-overlays-2; (c) Oregon City Park
   Place/South End concept plans (1,200 sf footprint rule) + historic districts -- needs boundaries;
   smaller: Sunnyside Village, WashCo transit townhouses, Wood Village TC, Sandy Bornstedt, Wilsonville
   Old Town. TIER 2 false-RED openings: Gresham townhouse-only zones (~832), Troutdale HDR Town Center
   (~350), Tigard Washington Square map, Estacada, Canby, Tualatin CO Block 1, Gladstone TC. TIER 3
   boundaries: Oregon City, Portland plan districts + 33.420/33.5xx text, Troutdale, Tigard, Sandy,
   Wilsonville Old Town. QUESTIONS: is the pod roof flat (Fairview Village + West Linn ban flat roofs)?
   WashCo's eleven community plans (68,777 lots) are unread -- read them?
   CHUNK 1 BUILT 2026-10-21 (merged; joint splice next): pdx-overlays-2 01a5d05d (Portland 925 greens
   lost: Historic Districts red 197g/16y, Central City d RX/CX red 501g/217y -- both ORS 197A.400
   exceptions; Conservation Districts yellow ~102; main street "m" yellow ~164, every street taken as a
   transit street until the map is ingested) + frontage-share 45d8f5a7 (Beaverton 60.05 38r/94y lost +140
   y->r; Downtown 16r/134y + 22 y->r; WashCo NMU/CCMU 26r/20y; King City 3 y->r). QUESTIONS for Steph:
   (q1) a wide lot one pod cannot fill to the share -- RED (as built) or YELLOW (more buildings could)?
   (q2) King City: must every one of the four front doors face the street (as built), or one per
   building? Answers ride the next chunk's splice.
   STEPH 2026-10-21 (on q1, a gap found): the share is measured on the ORIGINAL lot for both forms --
   "We should measure it based on what they base it on": per lot -> townhouse form on each unit lot;
   site/development -> original lot (rulings.yaml 2026-10-21-frontage-share-measured-as-coded; chunk 3).
   q1 ANSWERED: room for enough pods side by side (rough) -> YELLOW, else RED (rulings.yaml
   2026-10-21-wide-lot-frontage-more-pods; chunk 3). q2 ANSWERED: all four doors face the street, as built -- no change (rulings.yaml 2026-10-21-king-city-all-four-doors).
107. [Claude] [DONE 2026-10-21 -- remove at next bookkeeping] **Page check: footnotes asked as their own
   value card (Steph 2026-10-21).** LIVE 411f37ae (335097e6 + 4a1c6d4e). 76 stand-alone cards read wholly
   off one note now ride their table cell's note question ("we read it as ... is that what the note
   says?"): 23 note questions added, 32 reworded; answers kept (reopened 802-806, 809-828 come back as
   the note question). New "This is a footnote" button (key 5) files a card as a problem. Column-heading
   notes now reach every row of the table: 3 Gresham parking cards gain note 1. E2E 18/18 on prod.
106. [Claude] [DONE 2026-10-21 -- remove at next bookkeeping] **Gresham corridor minimum density for a quadplex
   on one lot (ids 736/738/740).** Steph 2026-10-21: density minimums on big lots are a known limit -- one pod
   is checked though the land would be split into several, which waits for plotting street additions
   (item 31). Single-lot exemption stands; registered 7213dff8; the three cards answered.
105. [Claude] [AFTER 73's restructure + clean] [scan: YES (new standards bind)] **Follow every
   cross-reference one layer down (Steph 2026-10-20).** A footnote or standard that says "see Section
   X", "conform with Table Y for the Z district" or "may be approved per Section W" is not read until
   the place it points to is. Steph's words: "If the next layer is clear and objective, then it is
   just as essential to understand as any other table/ruling at the top level. If it's leading to an
   administrative ruling process or something, then we need to know that too." So each reference
   lands in one of: (a) clear, measurable -> encode it like any top-level standard; (b) an approval
   process -> classify by the 2026-10-14 three tiers (clear review green / conditions yellow+flag /
   judgement red); (c) not about the pod -> dismiss with the reason. Start from
   flats/encode/crossrefs.py (chapters never fetched) and the footnote ledger's "See Section" notes;
   Gresham Table 4.0430 (item 104) is the worked example. Steph: "not now -- maybe after the text
   cleanup when we have better formatting and understanding."

## 2. Waiting on Steph

73. [Steph] [scan: NO (citations move, answers must not)] **The code library as a public, structured repository
   (Steph 2026-10-10, thinking only -- "Don't begin work"). Not started.** Today: 397 text files,
   23 MB, 25 jurisdictions under flats/provenance/docs, each with .meta.json (url, retrieved,
   sha256, extractor) and .pages.json; rules cite them 6,668 times by LINE
   (`file.txt#L1066-L1068`) and 641 times by anchor; every cite also carries a human section
   string ("OCMC 16.12.035.F").
   Proposal: (1) STRUCTURE first -- rebuild each code as a tree of sections addressed by its own
   numbering (16.12.035.F), line WITHIN the section as the sub-address, tables by row/column;
   translate every citation mechanically (match the quoted text, refuse any that does not match;
   flats/provenance/repoint.py is the starting point); pilot one city. (2) HOSTING second -- its
   own GitHub repo, our apps read it as a dependency; git history doubles as the code-change
   watch (item 54). Keep rulings/encoding private either way.
   STEPH 2026-10-10: PUBLIC. Publisher terms not a concern ("we cite the code, not their
   interpretation"). Readability cleanup is part of it: collapse extra spaces, rejoin words split
   by the PDF reader ("dri v ewa y s"), strip running page headers/footers left mid-sentence
   ("Oregon City Supp. No. 46 266.4"), join hyphenated line breaks; NEVER auto-change a character
   inside a number (1/l, 0/O) -- flag it; keep the raw download beside the clean text as proof.
   LICENCE: Steph withholds zero rights to the municipal-code portion -> CC0 1.0 (public-domain
   dedication, with its fallback licence where dedication is not recognised) on the text,
   structure and metadata, plus an "unofficial copy, not legal advice, check the city" notice.
   Tooling code licensed separately, Steph to pick.
   ORDER (coordinator recommendation, put to Steph): restructure + clean FIRST, human signing
   AFTER. Signatures are hashed over value + citation, so a new citation withdraws them; only 18
   rule signatures (5 verified, 13 unclear, none drained) and 244 page checks exist, carried over
   where the words match, re-queued where not. The map shows as-if-signed colours, so pausing
   signing costs the map nothing. PRIORITY (recommended): after the weekly scan settles, ahead of
   new cities and the signing push; false-GREEN fixes carry on beside it; freeze edits to the code
   text and citations while each city is being converted. (Steph's "not before Tuesday
   2026-10-13" has passed; still needs Steph's go to start.)
   READING QUEUE (found 2026-10-21): 74 reading rulings are back open as "ruled against text that has
   since changed" -- the 2026-09-27/28 re-fetches (Fairview to eCode360 46, Clackamas ZDO-293 12,
   Portland pypdf 5, 11 others). Left for after this restructure, which moves every fingerprint again;
   carry each ruling where its words match, re-queue the rest (`python -m flats.encode.worklist --audit`).
54. [Steph] [scan: NO (warn-only: changes no rule and no answer; the fixes it leads to land at the next weekly)] **Code-change
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
55. [Steph] [scan: NO (nothing it writes reaches the rules or the map)] **Expansion scouting on the
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
22. [Steph] [scan: YES if Steph adopts Milwaukie's 22 ft aisle] **Portland aisle 20 ft -- DONE (bacea669 + quadfit mirror 0df02fcc;
   run 44 PROMOTED 2026-09-30; register `2026-09-30-portland-aisle-20ft`).**
   Portland yellow->green 7,358. Two green->yellow (1S1E06AD -02100 pod80,
   1S1E13DC -04000 pod56) replayed: the narrower court is drawn 0.1 / 0.7
   ft past the beside-court reach tolerance (`BESIDE_REACH_TOL_FT` 3 ft,
   cef95109) -- knife-edge, conservative, accepted.
   **Milwaukie, pending Steph:** the ecode360 link Steph sent
   (guid 43863200) is 19.606.1, Table 19.606.1 -- 90 deg: 9 x 18 stall, 22 ft
   aisle -- which we already hold; 19.606's purpose sentence excepts middle
   housing, so it is refused today (milwaukie.yaml ~L948) and the court is
   drawn at 24. Asked: adopt 22 as Portland's 20 was adopted? Wilsonville's
   planning email (HUMAN_TODO 3) still open.
32. [Steph] [(B) Copilot-able after a yes] [scan: NO] **Windows CPU spikes (Steph 2026-10-02: "60%+ of my CPU on Python").**
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
65. [Steph] [scan: YES (a proof run: every answer must come out identical to 137's)] **The Windows PC
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
62. [Steph] [scan: YES] **Roof shape: teach the screen gable vs flat (offered 2026-10-09
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
40. [Steph] [scan: YES, if started] **Easements from maps (Steph 2026-10-04 asked the odds of reading an
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
   Steph sends maps. If Steph does: pilot 5-10 maps (modern plat, old plat, tax
   map; one with a title report to grade against), first check whether
   Beaverton/Hillsboro/Washington Co. publish an easement GIS layer or bulk
   plat images; severity of "plat read, deed easements unchecked" is ruled
   AFTER the pilot, not before.
72. [Steph] [scan: NO] **Oregon Explorer statewide map (Steph 2026-10-10 link,
   oregon-explorer.apps.geocortex.com ...app=6244abbf93e54b88a13a17b6cb6b9b37) -- PARKED.**
   STEPH 2026-10-10: the viewer is the building code's site-design map, NOT zoning: ground snow
   load, basic design wind speed, seismic design category, weathering, frost line depth, decay,
   air freezing index, radon mitigation for new dwellings (the ORSC Table R301.2 climatic and
   geographic design criteria, state-wide in one place). Not a siting rule; it decides what the
   factory-built pod must be ENGINEERED for at each lot. OFFERED: (a) fetch the layers behind
   the viewer, measure each lot, show the values on the lot page (show, don't screen); (b) once
   Steph gives the pod's rated snow load / wind speed / seismic category / frost depth, flag lots
   that exceed them (re-engineering = a cost, YELLOW at most, never RED by itself). Confirm the
   map matches the ORSC 2026 edition (item 71).
   STEPH 2026-10-10: PARKED for later -- "eventually we will need to encode and design for this
   list" (all eight criteria). Do not start without Steph; raise it again when the pod design
   ratings exist or the market moves beyond the metro.
   Separately noted: the DLCD statewide zoning layer (services8 .../Zoning/FeatureServer, item
   72416393747c...) holds per polygon the local zone code + name, a statewide class
   (orZCode/orZDesc), a code link (codeRef), an effective date and the owner -- NO setbacks /
   heights / lot sizes. Use: a zoning map for cities beyond the 3 counties, codeRef to fetch each
   code, effDate as a change watch (item 54). Not a replacement for reading the codes.
92. [Steph] [scan: YES (parked)] **Parking layout generator -- was the second item 27, renumbered 92 on 2026-10-16 (commits 7d603344, cba189dc, d20eb8c3, 38239df5, 8121773e, 06e2a856 and memory call it "FOLLOWUPS 27") (Steph 2026-10-01: "more parking flexibility
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
   UPDATE 2026-10-16: street class per lot line is now measured (item 41, 972caa17), so the
   `lowest_class` gap above is closed; the re-check of today's greens there rides item 36's
   weekly read. Oregon City's "one approach per two townhouses" is overridden by state law
   (item 24, 2026-10-10), so the pod needs one approach there.

## 3. Copilot queue -- low priority, not time-sensitive

101. [Copilot] [scan: NO (quadfit mirror only)] **Port Gladstone Ord. 1545 to quadfit's rules.yaml.**
   Files: `Lot Analysis/quadfit/config/rules.yaml`, the Gladstone R7.2 row (~line 2743). Change:
   `min_lot_sqft` 3600 -> 7200 and `setback_side_ft` 7.5 -> 5, and rewrite its `notes` to cite Ord.
   1545 (in force 2026-08-13) as `flats/config/jurisdictions/or/clackamas/gladstone.yaml`'s
   `amended:` entry does. Must not change: any other row; anything under `flats/`. Test:
   `uv run pytest "Lot Analysis/quadfit/tests/test_zone_mirror.py" -q` green.
91. [Copilot] [scan: no] **Copilot cleanup batch 10 -- QUEUED for 2026-11-01.** Copilot's monthly quota ran
   out 2026-10-16 (HTTP 402) and resets 2026-11-01. Steph RULED 2026-10-16 (memory
   feedback_copilot_monthly_burn.md): on the 1st of each month, start Copilot on its tier of work
   right away and run it until the quota is gone; don't buy more credit and don't offer it; when
   the quota is gone the queue waits for the 1st -- Claude does not take it over. Fire briefs in
   parallel batches of 4; a 402 means stop, not retry. Before firing (reference_copilot_cli.md):
   Steph checks the real balance on github.com/settings/billing, pin a cheaper model instead of
   auto, stop at ~70% of the allowance.
   Four briefs written (docs/copilot/briefs/, runner docs/copilot/run_batch.sh), worktrees + branches left
   as-is (flats/nul-note-posts, e2e-waits, test-hygiene, flags-cache-geometry; local only, at
   main's tip; e2e-waits has a partial uncommitted edit). (a) NUL byte in the note of an otherwise
   valid /ui/flats/sign (and passage, reading, words, triage, check) POST -- likely 500, strip NUL
   before storing. (b) E2E waits that pass without checking: test_flats_reading filter-survives
   (wait_for_htmx swallows), test_flats_price ppu reload race (assert URL), test_flats_page_check
   cited-page flake (poll the scroll). (c) Test hygiene: test_permit.py:147 `or True`; five blind
   pytest.raises(Exception); test_missed temp-file leak; dead _MAX_WRAP; four unused loop
   variables. (d) Cache flags.yaml parse (64 ms/request, key on mtime) and dedupe _outline/_plan
   geometry behind a golden test.
23. [Copilot] [scan: NO] **Page check -- SHIPPED 2026-09-30 (a203e9f1).** `/flats/check`: the
   printed page with a box on the number, signed numbers first, then one card
   per footnote on it; "no" answers form the problems list
   (`/flats/check/problems.txt`, stamps `bundled_at`). (a) DONE -- web
   codes show the stored text with the number tinted (3267d23a on main;
   answers go to the same table with page NULL and placed = "web").
   Still open: (b) nothing reads the problems list yet -- wire a "differs"
   into the signing disputes so the number reopens there.
   [Copilot brief for (b)] Files: app/api/routers/ui_flats_check.py (the page-check answers;
   `flats_check_problems` serves /flats/check/problems.txt), flats/encode/dispute.py (the
   dispute log the signing pages read; read it first). Do: a page-check answer of "differs"
   on a number also lands as a dispute on that number, so the signing pages show it reopened.
   Must not change: any answer, colour or rule value; the problems.txt output; existing
   disputes. Test: in tests/api/test_ui_flats_check.py, answer "differs" on a number and
   assert the number shows as disputed; answer "yes" and assert it does not. If the dispute
   log has no place for a page-check answer, stop and report rather than invent one.
16. [Copilot] [PARKED: Steph called it "for later" -- ask before firing] [scan: NO] **Partial re-screen -- SHIPPED 50a0ecc2 2026-09-25 (runbook §4c).**
   Nothing left to build. Kept for one remark: showing the `splice audit`
   on /flats/refresh -- Steph 2026-09-25 "an enhancement for later" -- not
   queued.
   [Copilot brief] Files: app/api/routers/ui_flats.py (`/flats/refresh` handler),
   app/templates/flats_refresh.html, flats/ingest/splice.py (`audit()` and `report()`). Do:
   show the latest splice audit's result read-only on /flats/refresh. First find where an
   audit's result is kept on VM 114; if it is not kept anywhere the app can read, stop and
   report. Must not change: splice or audit behaviour, the page's refresh actions, any
   answer. Test: tests/api/test_ui_flats_refresh.py -- the page renders with and without an
   audit result present.
