# 157. Building pushed back at an inward bend in the front lot line (square setback caps)

Found 2026-11-08 by the rel4-fixes lane (../vicinitideals-worktrees/rel4-fixes.handoff.md, "Tigard three lots").

Tigard 2S103BA00137: the front lot line bends 4.5 deg inward (37.8 ft at 171.04, 78.3 ft at 175.61).
`flats/geom/envelope.py` buildable() builds the setback strip with square caps; at a reflex bend the
cap runs ~17 ft past the bend ~1.5 ft deep, pushing the building to 21.08 ft vs the 20 ft maximum front
setback + 1 ft drawing allowance -> false RED. Every lot with an inward front bend can be affected.

Status: lane envelope-caps (flats/envelope-caps, off flats/rel5 28861142) BUILDING 2026-11-09; rides the
rel6 package bound. Must never shrink a true setback (no false GREEN).
