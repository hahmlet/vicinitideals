# 161. Sight triangles (clear-vision areas) at corners and driveways

Scoping: ../vicinitideals-worktrees/sight-triangles.scoping.md (2026-11-09). Screen changed nothing yet.

- Corner triangles: of 21,948 GREENs in the re-screen base (3,997 corners), the drawn building enters a
  stated, building-barring triangle on ~9 lots (typical curb) up to ~90 (curb at lot line), mostly Gresham
  downtown/corridor; ~1-29 can't re-fit. Example 1S3E06BA  -00700 (16816-16822 SE Stark, Gresham).
  Portland's corner rule covers the street only -> Portland unaffected.
- Manuals not held (triangle size): Beaverton, Hillsboro, Milwaukie, Gladstone, Oregon City, Wood Village;
  ~133 more GREENs in reach at 30 ft. Fetch lane started 2026-11-09 (downloads always OK).
- Driveways: corner distance < ~40 lots; driveway triangles Gresham 108-455, Tigard 133, West Linn 85;
  Portland PBOT 15x15 ft from pavement edge: ~400-550 GREENs (ordinary sidewalk strip), up to 4,865.

Build: corner triangles = medium (geometry piece, ~15 city entries, bound + read every move); driveway
spacing = small extension of the Durham driveway check; driveway triangles = second medium piece.

Waiting on Steph (asked 2026-11-09):
0. Major feature: go ahead with corner triangles (the false-GREEN part)?
1. Apply Portland's driveway sight triangle (a street-permit rule, not zoning)?
2. Until we map curb positions: assume worst (curb at lot line) or a typical sidewalk width?
3. Does the four-unit pod count as "single-family" under West Linn's driveway triangle (85 lots)?
Leftover readings: Tigard + King City building wording, Tualatin 200 ft rule (in the scoping file).

Manual fetch 2026-11-09 (../vicinitideals-worktrees/sight-manuals.findings.md; files in gitignored data/flats/books/sight-manuals/):
Beaverton 15 ft legs, bars structures (EDM 210.18.1, edition doubt 2019 vs 2025); Milwaukie defers size to AASHTO
(paid book -- Steph: buy?); Oregon City/Wood Village partial; Hillsboro, Gladstone blocked by site bot checks
(not bypassed) -- fetch by hand or via Steph's Chrome only after Steph says go on the build.

Curb scout 2026-11-09 (../vicinitideals-worktrees/curb-layer.findings.md): Portland PBOT Curbs layer 74 (118k lines,
weekly, 'shoulder' = pavement edge) covers 62.7% of GREENs; saved gitignored data/flats/sources/2026-11-09-curb/.
Oregon City edge-of-pavement (partial), Hillsboro roadway polygons; Gresham NONE (Metro ROW polygons only).
NEXT (after rel6 bound frees 137): measure Portland curb-to-lot-line offsets on GREEN lots -> real numbers for Q2/Q3.
Explained all questions to Steph in plain English 2026-11-09; recommendations: build corners; Portland driveway = warning
(yellow+note); curb = middle way; West Linn = single-family; Hillsboro/Gladstone via Steph's Chrome; Milwaukie email not buy;
extend Portland aisle + alley rulings to Multnomah pockets.

Prep readings 2026-11-09 (../vicinitideals-worktrees/sight-readings.md): Tigard 18.930 bars buildings (30/35 ft);
King City unclear (conservative default when built: bars); Tualatin Table 75-1 200 ft literally reaches the pod drive
(conservative default: applies; needs cross-street class); Troutdale 110x15 curb, Fairview 15x15 curb, both bar buildings;
Clackamas County sight DISTANCE wedge (280/240/205 ft at 25 mph, 14.5 ft back) -> geometry check; Happy Valley 25 ft legs
+ 50 ft drive from corner; Cornelius 15 ft curb + drive 25/100 ft citywide; Beaverton 2025 EDM Ch.2 needs a browser save;
Oregon City 10.32 + Wood Village blocked.

RULED 2026-11-09 (Steph, rulings.yaml): 1 build the corner check YES; 2 Portland TRN-10.40 driveway zone = GREEN with a note
(colour unchanged, flag); 3 curb position = middle way (green if clear at lot-line curb, red if blocked at a generous offset,
yellow+flag between); 4 West Linn pod = single-family apex; 6 Multnomah pockets take both Portland parking rulings.
Still open: Q5 Milwaukie (buy AASHTO / email city; hold yellow meanwhile).
RULED 2026-11-10 (Steph): Milwaukie uses the AASHTO figures already held (Clackamas reproduction); no purchase.

Leftovers 2026-11-13 (branch flats/sight-leftovers, hand-off ../vicinitideals-worktrees/sight-leftovers.handoff.md):
King City read (buildings barred; 20/35 ft in Kingston Terrace; the pod's 4-unit drive takes 20/35, not 15). Gladstone,
Oregon City: buildings barred, size still unsettled (ROW width / city engineer) -> stay YELLOW. Hillsboro wedge 450 -> 500
(AASHTO at 45 mph). Tigard 30/35 picked per corner from the TSP class map. New checks (YELLOW+flag, never RED): alley
corners (SIGHT_CORNER_ALLEY; Gresham 25, Sandy 20, Canby 15 read, else the corner figure) and parked cars / drive in the
corner area (SIGHT_CORNER_PARKING; vehicles: 14 cities, driveways: Gresham). Needs a bound. Open for Steph: Oregon City /
Hillsboro engineer-set size (keep YELLOW?).
