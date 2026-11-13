# 178. False-green round 4 (2026-11-10): findings and Steph questions

[Claude] [scan: YES]

Round 4 (Multnomah batch C 16/50 wrong, Wash+Clack batch D 17/60 wrong; reports ../vicinitideals-worktrees/fg-rate-C.md, fg-rate-D.md) -- all four Steph questions RULED 2026-11-10 and every fix is built. Rel7 (live, run 124): door-yellow, Wood Village roof ban + Tigard cornice YELLOW (roof-ban 2e675fee/f4072a52 -> b381a27d, 0a7d473a), fg4-fixes 1-4a (Beaverton EDM 210.21 spacing c3ae3b0a; Clackamas half-frontage 84fd6c21; Beaverton plex front court 2dadcf2c; ZDO 1009 strip off R/VR 41d18db9, ef5583e9), Portland 9 ft drive 6320d47c, narrow street fire YELLOW bdc19c96. (c) no public sewer = RED (lane no-sewer 4592039a) rides rel8, bound running 11-13 (ruling 2026-11-10-no-public-sewer-red).

STILL OPEN (Claude work, no Steph answer needed):
- Driveway spacing table has no entry for cities that store a rule (table: flats/config/driveway_spacing.yaml; list in ../vicinitideals-worktrees/fg4-fixes.handoff.md, "Other cities"): Gresham PWS 6.03 Table 6.03 (100 ft from arterial curb return / 45 ft; large GREEN pool; arterial queue-length rule L55-L57 unmeasured), Oregon City 16.12.035 (175/100/25), West Linn 48.060, Milwaukie 12.16, Fairview 19.162, Sherwood, Wilsonville. A city with no entry is not checked = a possible false GREEN on arterials.
- Not done: Clackamas SCMU 1005.09 frontage share (needs Map 1005-1 which FLATS does not hold); 1005.02(E)(1) 20 ft front setback option (stricter reading kept).
- Known, not fixed: 1S1E23BA  -03601 Portland R5 through lot (court between building and a second street, KNOWN-154).
- Beaverton plexes: Claude kept the court-in-front reading (code bans front parking only for townhouses, caps at half frontage); a move-read check of the gains is the safety net.
Spacing table gaps DONE 11-13 (flats/drive-spacing off rel8, rides rel9): Gresham, Oregon City,
West Linn (+ TSP Table 15 stored), Milwaukie, Fairview, Sherwood, Wilsonville encoded in
driveway_spacing.yaml; unread rules hold YELLOW (G->Y only). Hand-off
../vicinitideals-worktrees/drive-spacing.handoff.md.
