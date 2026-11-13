# 161. Sight triangles (clear-vision areas) at corners and driveways

Done (one line): all Steph questions ruled 2026-11-09/10 (rulings.yaml: corner check built; Portland driveway = green + note; curb middle way; West Linn pod = single-family; Milwaukie uses the AASHTO figures already held); corner and driveway checks built b8f9ade4 (merge bbcc7f47) and live since rel7 (run 124).

Hand-off: ../vicinitideals-worktrees/sight-triangles.handoff.md (table of each city's figure, "Left out" section). Manuals in gitignored data/flats/books/sight-manuals/; findings in sight-manuals.findings.md, sight-readings.md, curb-layer.findings.md.

**Still open (no Steph answer needed):**
- Cities with an UNSETTLED figure (held YELLOW, not measured): Hillsboro (wedge 450 ft), Oregon City (wedge 250/450), Gladstone (20/30/40, buildings unclear), plus Tigard 30/35 and King City wording. Hillsboro/Gladstone/Oregon City manuals were blocked by site bot checks; Steph's standing OK is to download maps/codes (fetch by hand or Chrome).
- Left out of the build: alley corners; parking/courts inside a corner triangle (Gresham, Canby bar parking there); Gresham "no driveway in the CVA"; measured curbs at corners (only Portland has a curb layer, 62.7% of GREENs); street-class figures (bands go YELLOW instead); Tualatin 200 ft rule needs cross-street class (169 built the class machinery).
Leftovers 2026-11-13 (branch flats/sight-leftovers, hand-off ../vicinitideals-worktrees/sight-leftovers.handoff.md):
King City read (buildings barred; 20/35 ft in Kingston Terrace; the pod's 4-unit drive takes 20/35, not 15). Gladstone,
Oregon City: buildings barred, size still unsettled (ROW width / city engineer) -> stay YELLOW. Hillsboro wedge 450 -> 500
(AASHTO at 45 mph). Tigard 30/35 picked per corner from the TSP class map. New checks (YELLOW+flag, never RED): alley
corners (SIGHT_CORNER_ALLEY; Gresham 25, Sandy 20, Canby 15 read, else the corner figure) and parked cars / drive in the
corner area (SIGHT_CORNER_PARKING; vehicles: 14 cities, driveways: Gresham). Needs a bound. Open for Steph: Oregon City /
Hillsboro engineer-set size (keep YELLOW?).
