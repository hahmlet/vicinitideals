# 158. 17 fire-reach / front-max reds left after rel4-fixes

From ../vicinitideals-worktrees/rel4-fixes.handoff.md section 3: after the corner-tie fix, 17 non-Tigard
lots stay RED, mostly fire_access_ft with the building drawn further back at the same angle (not the tie):
12E29DA11900, 12E33AC00500, 12E36BD09000, 1N3E31AD  -00500, 1S122BD14200, 1S206AB10200, 1S212AD01301,
1S2E09BA  -05500, 1S2E16CB  -05000, 1S2E16CB  -05300, 21E02DC05400, 21E26D 01002, 22E18BC01003,
22E18DC03800, 22E19BA06800, 22E32AD00301, 2S110DC00700 (TLIDs keep their spaces).

RED is the conservative side. Next: read each (why the drawn spot sits further back), then a fix lane
stacked on flats/rel4-fixes if a code cause is found.

**Status 2026-11-09 (lane fire-reds-158, branch flats/fire-reds-158): read; one code cause fixed.**
Hand-off: ../vicinitideals-worktrees/fire-reds-158.handoff.md (the verdict for each lot).

- Fixed: Hillsboro read the entrance angle as 0. It prints 45 deg (12.50.710.C.1.b.ii), and rel4
  finding 2 missed it. 1S206AB10200 goes back to its 11-10 colour.
- Real under ruling 2026-11-08-no-front-yard-parking-silent-codes (11 lots): the only nearer
  placement stands the court in a front yard. Through lots overlap FOLLOWUPS 154.
- Envelope shrank in rel4, not the drawing (1S212AD01301, 2S110DC00700, 22E32AD00301). The cause is
  not traced: open.
- Other: 1S122BD14200 (fit on the worse reading), 1S2E09BA -05500 (L-shaped envelope on the worse
  reading), 1S2E16CB -05300 (alley-stretch court, leftovers-b).
- Not shipped: let the fire retry run past a missed minimum density, and on one-street lots with a
  0 share. Neither moved any of the 17, and in the sample the retry pre-empted the turned search and
  drew Portland 1S2E07BC -12600 into a front-max RED (the retry does not re-measure the maximum
  front). Needs a front-max check on the retry's candidate first.
