# 37. Flag system plan ("FLATS Flag System Plan.md", Steph 2026-10-02) -- slices 1-(e) BUILT and LIVE

37. [Claude] [scan: YES for (iii)] **Flag system plan ("FLATS Flag System Plan.md", Steph 2026-10-02) --
   slices 1-(e) BUILT and LIVE** (34963899 slice 1 + approval page;
   6eb14ffe measure + lot page; 85712ad6 severity 0; flags tables
   0139-0142; cbc47269; check margins 7dc34722; room each way f3408efa).
   Steph's answers (register `2026-10-02-no-variances`,
   `-flag-below-three-stays-green`, `-minimum-density-a-flag`,
   `-colour-as-if-signed`, `-near-miss-one-foot-red`; memory
   feedback_flats_flag_plan_rulings.md): (1) no variances, a miss with a
   path is RED, path logged on the bind; (2) a flag below the line
   (severity < 3) keeps the lot green; (3) min density = low flag
   (severity 2 -> green); (4) colour stays "as if signed". Steph RULED
   2026-10-03 "Exactly 1 foot is red": short by 1 ft or more -> red (pull
   back later for targeted variances / no-parking ideas); under 1 ft ->
   yellow. Steph 2026-10-03: "measurement" is THE PREFERRED resolution type
   -- the other three (inquiry, document, per-lot review) are "the failure
   mode"; flag tables live in the app DB ("flags and warnings are
   equivalent data points just like a min setback is"); NO DEADLINE for a
   pending flag type (pending types top the approval page + the count is
   mentioned at session start). Steph 2026-10-04: "Start number 2
   [measure] first, then 1 [map + lot page], then continue"; room each way
   (Steph: "we need all dimensions ... oddly shaped lots?").
   TRAPS: drain on 114 needs --registry-out/--colour-out on /app/data;
   after promoting a run screened under the colour rule run
   `scripts/flats_flags.py sync` then `check` on 114 (nightly sync 10:30
   UTC). An ambiguous rule set binds nothing, so ~0.07% of rows stay yellow
   despite a 50+ ft fit miss (Wilsonville R, Hillsboro SCR-V) -- by design.
   (iii) DONE and live (main, run 124): Gresham note 5 encoded at its worst reading
   (c37b8b54 via flats/flag-leftovers, merged into rel5 as 4d9e7666); (f) CLOSED 2026-11-08 (one fixed
   design; set access is FOLLOWUPS 145).
   STILL OPEN: (e) the other 29 `unmeasured` notes turn on data nobody holds (easements, water
   features, LO net developable area, site-specific limits) and have no figure to bound -- nothing
   buildable; unknown facts needing a title report: utility_easement 28k, sidewalk_easement 20k (run 63
   yellow lots). Plan gaps "flag history across county refreshes" and "bulk writes through the loader"
   are unspecified: a feature to scope with Steph before building.
