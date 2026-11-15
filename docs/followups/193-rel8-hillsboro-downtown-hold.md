# 193. rel8 BLOCK: Hillsboro R-7/MR-1 lots inside the traced downtown line

[Claude] [Steph: zone-list vs map question] [scan: YES -- false greens only, Hillsboro]

The rel8 move read (../vicinitideals-worktrees/rel8-moves.findings.md, F1) blocked release on three new
GREENs: 1N231DA04600 (27.7% inside the traced line), 1N231DA01800 (52.8%), 1S205BB04500 (fully inside).
All R-7. CDC 12.61.800.A.1/B apply the roof rule "within the boundaries shown on Figure 12.61.200-A"
(B.7 forbids a flat roof), but 12.61.200 lists only five downtown zones (SCC-DT, SCR-HD/MD/LD, SCR-DNC);
the `downtown_plan_district` variant exists only in the SCR blocks of hillsboro.yaml. Five more R-7/MR-1
lots inside the trace already went red->yellow for the same cause.

Fix on flats/rel8 (before release): lots in a zone outside the five but touching/inside the traced
line are held YELLOW with a flag (map and zone list disagree), never GREEN. Then a Hillsboro-scoped
re-bound spliced onto /root/rel8_bound, a re-read of the Hillsboro moves, then flats-release-runner.

Steph question (sheet): does "no flat roofs" apply to every lot inside the map line, or only the five
downtown zones? Every lot = RED for these (~3 greens lost); by zone = they could be GREEN.
