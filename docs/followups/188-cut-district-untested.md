# 188. Lots cut by a district boundary pass untested (possible false GREEN)

[Claude] [scan: YES -- toward yellow]

Found 2026-11-12 by the gresham-end-glass lane (FOLLOWUPS 187 extension, flats/gresham-end-glass 4c3e50be,
hand-off ../vicinitideals-worktrees/gresham-end-glass.handoff.md). When a district boundary (South
Hillsboro, East Hillsboro, the Portland map areas) cuts through a lot, the district test returns no answer
and the lot is let through untested instead of held out of GREEN. For South Hillsboro end-wall glass it
is nil in practice (5 ft side setback), but the same gap reaches every district-scoped rule in those places.

Standing ruling 2026-10-14 (split zones -> yellow) points to the fix: a lot a district boundary cuts is
YELLOW + flag for that district's rules, unless every side of the cut passes. Before building: count the
cut lots per district on the current bound (how many are GREEN), and read a sample. Ride a weekly re-screen.
