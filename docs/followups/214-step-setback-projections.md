# 214 -- Precast steps standing in a front or side setback (projection allowances not encoded)

Opened 2026-11-21 from the stair-room build (FOLLOWUPS 213, `flats/foundation-fd8` a78c1ade; hand-off
`../vicinitideals-worktrees/foundation-fd8.handoff.md`, section "Setbacks").

## What

The stair-room build keeps every door's precast unit inside the lot and clear of the drawn court and
lane, but not out of the setbacks. A building drawn at the front or side setback line puts its steps
(about 3.2 ft out at one riser, 97 in at six) inside the setback. Codes usually list what may project
into a setback; anything not listed may not. FLATS encodes no projection allowance (`flats/fields.py`
has no field), so a lot can read GREEN with steps where the code limits them. Not new: live screens
have the same exposure (the steps were never modelled before 213).

Grep of the stored codes found allowances in: Happy Valley (dimensional-table footnote, stairways over
30 in high), Wilsonville (note F, a porch 5 ft into the front; 4.127 note B), Clackamas unincorporated
(notes 14, 17, 7), Milwaukie (porch to 5 ft from the line), Sandy (accessory projections). Other
cities not yet read; Portland 33.110/120 projections section to be read.

## To do

1. Reading job, every encoded jurisdiction: what may project into the front, side and rear setbacks,
   uncovered steps/stairs/landings specifically, limits by height and distance. Whole-document grep
   per the absence-claims rule; follow cross-references.
2. Encode as a projection field; the stair-room reserve then also keeps each face's units within the
   allowed projection. Where a code is silent, conservative (steps outside the setback).
3. Bound, move read (each lost GREEN read), release.

Decision pending: none; queue after the 213 release.
