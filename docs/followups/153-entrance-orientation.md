# 153. Front door toward the street: read each city's entrance-orientation standard

[Claude] [scan: YES -- toward red/yellow; possible FALSE GREEN today]

Steph 2026-11-08, asked whether the pod's 80 ft door face must face the street:
"that's a code question. Each muni will have a standard typically." So it is
not a design choice; each city's code decides.

Today the screen also tries the building turned sideways (30 ft end to the
street, doors to a side yard) everywhere. Where a city requires the main
entrance to face / be oriented to the street (often a townhouse or middle-housing
design standard, sometimes with a "or open onto a porch/walkway within N degrees"
alternative), a sideways fit is a possible false GREEN.

To do:
- Read every switched-on jurisdiction's entrance/orientation standard that
  reaches a 4-unit attached townhouse (middle housing). Note OAR 660-046 limits
  what a city may apply to middle housing (entry orientation must be no stricter
  than for detached single-family in some cases) -- read it, it may void a
  city rule for our building.
- Encode a per-place field (store as printed, conservative default when unread),
  and make the screen drop the sideways placement only where the code requires
  street-facing entrances. Corner lots: which street counts.
- Bound, read moves, release.
- 2026-11-08 BUILT c04eeea0 (flats/entrance-orientation, off rescreen-1110): 24 rule files; must-face: Wood Village res, Milwaukie/Estacada/Beaverton downtown, WashCo MU; unread -> yellow. Round 2 (corners, unmapped sub-areas) running. OPEN Steph: (Q2) can one end home's door open onto a covered porch near the street (most cities' alternative)? (Q3) Hillsboro: every home's door to the street, or one per building?
- 2026-11-08 Steph Q2 = NO (no end-home porch door / street-end windows): alternative cities -> required; Hillsboro Q3 moot (doors only on the 80 ft face). Round 3 on flats/entrance-orientation + ruling 2026-11-08-no-porch-end-door; rides flats/rel4.
