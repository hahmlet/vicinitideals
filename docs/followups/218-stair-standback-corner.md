# 218. Stair-room stand-back slides along the street on corner lots (fd8c F-A, F-B, F-C)

[Claude] [scan: YES -- toward green]

Opened 2026-11-22/27 from the fd8c move read (`../vicinitideals-worktrees/fd8c-moves.findings.md`). No false GREEN.

- **F-A (wrong reds).** Where the steps need room, the placement should stand back a few feet from the door street;
  on corner lots it instead slides ~43 ft along that street and away from the side street, then fails the side
  street's maximum setback. `flats/fit/draw.py@c1a0830c:883` ranks windows by distance to the NEAREST street point and
  `:908` takes the nearest stair-clear window. Fix: rank by the farthest street the building must face
  (draw.py:893-899). Lots: 1S2E16CB  -04300 (new green->red), likely 1N1E27AD  -00100, 1N1E24BB  -25300,
  1S2E16CB  -16600; unproven (court room too) 1N1E16AB  -02100, 1N1E24BB  -17800, 1N2E20BD  -05500, 1S1E11BD  -13000,
  1N1E08CD  -16700. ~34 Portland lots of the 167 green->red STAIR-ROOM fail the same check. Scoped re-bound on them.
- **F-B (cautious).** 1S2E04BA  -15800, 1S2E09BA  -08500, 1N1E35DC  -04200, 1S1E12CA  -03600 read green after the move
  but are held yellow because the first (stair-blocked) placement read yellow. Decide whether a held-at-first colour
  should look at the reason for the first colour (it was the stairs) -- never a false GREEN.
- **F-C (display).** The DENSITY-MIN flag drops off some of the 49 red->yellow lots' shown rows.
- Steps standing in the required front yard (6 of 40 read lots) is FOLLOWUPS 214's question, not this item's.
