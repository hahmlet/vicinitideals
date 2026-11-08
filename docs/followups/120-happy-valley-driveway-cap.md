# 120. Happy Valley 16.44 driveway cap measured on a short line.

120. [Claude] [BACKLOG] [scan: YES -- false red only] **Happy Valley 16.44 driveway cap measured on a short line.** Found reading run 87's moves (2026-10-28): 3 Happy Valley lots went yellow->red on the half-frontage driveway cap. 22E01DD03100 looks like a false RED: 139.9 ft of frontage, but the cap came out 11.5 ft because it was taken from a short lot line, not the frontage the drive crosses. Check the other two; fix the frontage the cap is halved from; test on the 3.

BUILT 2026-11-03 by Copilot: flats/happy-valley-driveway-cap 56891775 (pushed) -- cap measured on the access frontage; path also reaches Beaverton and Sherwood. Needs a bound (HV, Beaverton, Sherwood) + read every move, both directions. Hand-off ../vicinitideals-worktrees/happy-valley-driveway-cap.handoff.md.
- 2026-11-05 bound hv_cap2 (e6efdcb1 + main) READ = HOLD: the private-drive fix never ran (22E01DD03100 still on the 23.1 ft fallback, expected 69.95 ft); 2 slope-data moves only. Encoder fixing on the branch, then re-bound.
