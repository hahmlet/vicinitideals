# 184. Crane set access (Steph 2026-11-11) -- FLATS_PLAN Phase 4 stage 8

[Claude] [Steph] [scan: NO at first -- flag only]

Steph: crane 100 in (8.33 ft) wide, 40 ft long, needs a 28 x 40 ft setup pad
(raw dirt OK) near the home; may enter/leave temporarily from any side with
room (setbacks ignored); must be able to leave once the pod is up. Steph's
hypothesis: if the parking court fits, the crane fits.
Assessment given 11-11: mostly true -- a single-row court (4-6 stalls x 9 ft,
18 ft stalls + 24 ft aisle) is ~36-54 x 42 ft, drive >= 9 ft. Gaps: (1)
double-loaded courts ~18-27 ft wide; (2) a bend a car turns in a 40 ft crane
may not; (3) reach to the far end of the 80 ft pod (60-90 ft radius); (4)
overhead power lines + trees -- no data held; (5) lots with no court (alley as
aisle, zero-parking Portland) -> set from alley/street, city permit.
Options: v1 court proxy (pad fits in court+drive+open yard next to the pod,
40 ft vehicle turning check on the drawn drive, pad slope from DEM, reach) --
~1 worker-day + a flag-only bound; v2 anywhere-on-lot pad + temporary path from
any frontage -- ~3-5 worker-days, only if v1 shows many failures.
Waiting on Steph: crane reach (max radius at the heaviest panel weight);
failure = flag only (recommended) or yellow? pod config delivery.crane_required
/ crane_reach_ft fields already exist (flats/designs/model.py).
