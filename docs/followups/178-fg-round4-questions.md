# 178. False-green round 4 (2026-11-10): findings and Steph questions

[Claude] [Steph] [scan: YES]

Round 4 batch C (Multnomah, seed 65, live run 122): 16/50 wrong -- 13 are
the side-door kind fixed by rel7 (ruling 2026-11-10-side-door-fit-yellow);
3/50 otherwise (6%). After rel7: 1 false green + 1 doubtful in the sample.
Report ../vicinitideals-worktrees/fg-rate-C.md. Batch D (Wash+Clack) running.

Built / building:
- Wood Village LR 7.5 / LR 12 / MR 2 / MR 4 flat-roof ban (210.375 B(3),
  220.355) skipped twice -> ~108 false greens; lane roof-ban off rel7 (also
  sweeps roof wording in every city). May join rel7 before release.
- 1S1E23BA  -03601 Portland R5 through lot: court between building and a
  second street, rel7 may miss (KNOWN-154) -> for the rel7 move read.

Questions for Steph (asked 2026-11-10):
- (a) Portland driveway 9 ft (code minimum, 33.266) vs the plan's 12 ft:
  9 ft keeps more narrow lots green with doors to the street (2 sample lots
  + some rel7 door yellows). Cost: tighter drive than the plan elsewhere.
- (b) Streets whose whole public strip is ~20 ft: treat as too narrow for
  a fire truck (YELLOW) before paving is measured? 1 sample lot
  (1S1E19CA  -07700). Recommend YES (unmeasured = conservative).
