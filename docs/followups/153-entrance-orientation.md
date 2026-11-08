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
