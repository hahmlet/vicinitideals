# 199. Ground levels under the placed building, and per-lot foundation-method check

**Status:** offered 2026-11-18; waits on Steph's go and on the foundation agent's method table.

Foundation agent feedback (via Steph 11-18): a slope % alone is not enough -- on a 10% slope the ground falls 2.5 ft under the building along the hill but 8 ft down it; needs slope direction relative to the street or ground levels at the building corners. Steph's idea: the foundation agent supplies what each foundation method demands of the site (e.g. helical pile = stoop 16 in above ground, slab = 8 in), and FLATS computes each per lot.

Proposed split:
1. FLATS measures (no new data: the 1 m elevation model and the placed building outline from the drawn fit are both held): ground level at each building corner and along each wall, fall along the long side and across the short side, highest and lowest ground under the building, level of the street edge / driveway start vs the building, direction of fall relative to the street. Stored per lot and per placement, shown as a note and in the lot report.
2. Foundation agent supplies a method table: per method the limits it puts on those numbers (max fall under the building, floor height above highest ground, max exposed height at the low end, stoop/step height, any soil / groundwater / frost / hazard conditions from 196-198).
3. FLATS evaluates each method per lot: works / works with conditions / does not, with the governing number. NOTE ONLY unless Steph rules otherwise.
Caveats to state on the note: levels are existing ground from the elevation model (inches-level accuracy, not a survey); the building position is the screen's chosen spot and others may exist; floor height above ground feeds the zoning height limit, which is measured from grade -- that part may later belong in the screen proper.
No build-cost work (Steph 11-12).
