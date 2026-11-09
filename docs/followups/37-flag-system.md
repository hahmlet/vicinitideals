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
   (iii) BUILT on flats/flag-leftovers (2026-11-08, awaiting bound): Gresham
   note 5 re-pointed to `at_street_end` + dead ends measured (8fbae177,
   a530e67c, 2026-10-04); now ENCODED at its worst reading -- 25 ft max
   front setback, no street named (every street line), on the True answer
   in LDR-5/LDR-7/TLDR/TR; MDR-12/MDR-24/OFR/CMF already hold a stricter
   20 ft max; the 5 ft min is never stricter. caps.json drops at_street_end,
   so the severity-0 bound tries both answers (sidewalk_easement no longer
   holds those lots since 972caa17). (e) OPEN: note 5 is the first capped
   footnote given its direction; the other 29 `unmeasured` notes turn on
   data nobody holds (easements, water features, LO net developable area,
   site-specific limits) and have no figure to bound. Unknown facts needing
   a title report: utility_easement 28k, sidewalk_easement 20k (run 63
   yellow lots). Plan gaps: flag history across county refreshes; bulk
   writes through the loader. (f) CLOSED 2026-11-08: the screen runs one
   fixed design (pod80x30, 0f2620b3), so no pod spec is owed; FLATS_PLAN
   Phase 4 set access is FOLLOWUPS 145.
