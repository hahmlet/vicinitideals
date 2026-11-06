# 151. A fit that found no window wide enough reads as a 0.5 ft near miss (found 2026-11-06)

151. [Claude] [scan: YES -- toward red only] **Width-short fits score the width miss and never the depth.**
   Found by the FOLLOWUPS 150 round-3 move-read (../vicinitideals-worktrees/rear-court-150.r3.moveread.md, Finding 3).
   - Where no window as wide as the search asked exists, `Fit.width_short_ft` is set and `best_depth_ft` is 0
     (flats/fit/rectangle.py ~L54-L66). The screen then scores fit_ft by the width shortfall alone
     (flats/score/screen.py ~L1038-L1048), so a lot one grid step too narrow reads -0.5 ft, FIT-TIGHT, YELLOW,
     even when the building could never reach the depth it needs at any width close to that.
   - Examples (Gresham 50x100, rear-court-150 branch): 1S3E03CC02201, 1S3E03CC05800, 1S3E10AC05200,
     1S3E10AC07000, 1S3E10BD00100. Live measured them -33 to -35.5 ft deep (RED); on the branch they read -0.5 (YELLOW).
     About 29 live yellows carry the same pattern (list them from live: fit_ft slack -0.5, best depth 0, angle NaN).
   - Not a false GREEN (the lots stay out of GREEN). Fix: where width_short_ft is set, also measure the depth at the
     narrower width (the widest window the lot does hold) and score the worse of the two; or score it as a fail when
     the depth shortfall at that width exceeds the tolerance.
   - Test: a Fit with width_short_ft 0.5 and a 30 ft depth miss at the narrower width -> RED, not FIT-TIGHT.
   Status: found, not started. Ships separately from 150 (fix-forward).
