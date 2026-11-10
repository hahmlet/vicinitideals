# 177. The front-door ruling halves the greens (rel6 hold)

[Claude] [Steph] [scan: YES -- ~10,500 lots either way]

Found 2026-11-10 by the rel6-fit-loss investigation
(../vicinitideals-worktrees/rel6-fit-loss.findings.md). rel6 bound: GREEN
21,948 -> ~10,000. Cause is not a bug: Steph's 2026-11-08 ruling (no door on
the end home onto a porch; ruling id 2026-11-08-no-porch-end-door, FOLLOWUPS
153 round 3, commit 5c61b8ac, merged rel4 ed1d094d) turned 31 entrance blocks
from "alternative" to "required". The fit now only tries the pod with its long
door face toward the street; on lots under ~90 ft wide (median lost lot 74 ft)
the parking court no longer fits behind, so fit fails. The lane estimated
"hundreds"; real ~10,500 GREEN + ~4,500 YELLOW -> RED, mostly Portland
R5/R7/R2.5/RM1. Bisect, door-filter-off test (373/400 back to GREEN) and
basecheck all confirm.

Decision for Steph:
- Keep: release rel6 as packed (~10,000 greens).
- Soften: side-facing placement comes out YELLOW ("doors face the side; works
  only with a design change") instead of RED. Needs the ruling changed, then
  the 31 blocks.

rel6 is HELD until answered. Also open: Hillsboro corner lots (176 c) and
Cornelius "just for business" (176 g) re-asked.

**RULED 2026-11-10:** "Yellow: design change" (2026-11-10-side-door-fit-yellow). Lane door-yellow off rel6 rides rel7; rel6 is NOT released alone -- folded into the rel7 package and one bound.
