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

Batch D (Wash+Clack, 60 lots): 17 wrong / 2 doubtful / 41 right (28%); rel7 fixes
16 -> ~2% after rel7. No new kind. Report ../vicinitideals-worktrees/fg-rate-D.md.
Lane fg4-fixes off rel7 (cherry-pick before release): Beaverton driveway spacing
missing from rel7's table (false green), Clackamas building-frontage share (noted
2026-09-09, never encoded), Beaverton front court behind the 10 ft yard (code read;
Claude decides by the text), rel7 risk notes (Clackamas R-zone 5 ft strip,
turning circles missed).
More questions for Steph:
- (c) Lots with no public sewer (Lake Oswego edge; FLATS ignores sewer): YELLOW
  (check service) or RED? Recommend YELLOW.
- (d) Tigard rowhouse flat roof allowed only with a 12 in+ cornice: can the pod
  carry one? If not, Tigard townhouse greens go RED under the flat-roof ruling.

RULED 2026-11-10: (a) "9ft in Portland" (2026-11-10-portland-driveway-9ft); (b) narrow street = fire YELLOW (2026-11-10-narrow-street-fire-yellow), "a common Fire and Safety shoot down point on a permit". Lanes pdx-9ft and narrow-row off rel7.
RULED 2026-11-10: (c) no public sewer = RED (2026-11-10-no-public-sewer-red), lane no-sewer; (d) Tigard cornice = YELLOW + flag (2026-11-10-tigard-cornice-yellow), folded into lane roof-ban.
