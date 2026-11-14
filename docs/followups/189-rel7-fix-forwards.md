# 189. rel7 move-read fix-forwards (2026-11-12)

[Claude] [scan: YES -- toward green only, a handful of lots]

From ../vicinitideals-worktrees/rel7-moves.findings.md (move reader on net live -> rel7a,
fingerprint a0274bc3322afc538045642f2c37c2dd; 699 gained greens all read right, verdict SHIP).
None is a false GREEN; all are possible false YELLOW/RED.

- F2 pdx-9ft named cases did not move: 1N2E21BA -12200 (R7, fit -63.5 at 70 ft wide, never
  reached) and 1S2E15AD -08900 (CM2, still ENTRANCE-SIDE-DOOR after the 9 ft retry). Check whether
  the lane's expectation was wrong or the retry is not reached.
- F3 22E08DA01100 (Thorville Ave, Clackamas): fire road unmeasured -> FIRE-DEAD-END yellow;
  measure the bulb (flats fire_roads._room_to_turn).
- F4 22E06AD01800 (Clackamas R10): yellow -> red on parking_frontage_share 51.22% vs 50% cap
  after the 1009 strip change; retry other placements before RED.
- F1 (note only) Eldorado 22E08AC02500: the fg4 lane's "missed by 0.2 ft" was wrong; it is 24.5 ft
  short and correctly RED.

- F5 DONE 766dd02d: West Linn sewer root (GoDaddy TLS Root CA - R1) pinned in flats/config/ca/, trusted beside certifi by the ingest clients (flats/ingest/tls.py); live acquire from 137 verified.
- F6 DONE (recipe, no repo commit): /root/recipes/bound_splice/body.sh has an acquire() helper that passes `--root $D/flats/sources`; acquire.py default root left as is.
