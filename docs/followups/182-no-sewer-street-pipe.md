# 182. No-sewer rule: outside every district but a city pipe in the street (lane no-sewer, 2026-11-10)

[Claude] [scan: YES -- false greens only] [release: rel8]

RULED 2026-11-11 (2026-11-11-sewer-pipe-in-street-yellow): outside every district with a city main in the street -> YELLOW + flag (SEWER-STREET-MAIN).
RULED 2026-11-10: no public sewer within 800 ft (state septic rule) -> RED.
BUILT flats/no-sewer 4592039a, merged into flats/rel8 (cb445efa), bound running 11-13: ~398 G->R (391 Lake Oswego fringe, 5 Sandy, 1 Gladstone,
1 Gresham PV), ~148 G->Y, ~115 flag-only (SEWER-UNMEASURED: Canby, Estacada, uninc. Multnomah). The bound must re-acquire the 15 sewer layers
(command in ../vicinitideals-worktrees/no-sewer.handoff.md). Not read (note only): CWS / WES / Gresham sewer rules (800 ft is the state rule only).
