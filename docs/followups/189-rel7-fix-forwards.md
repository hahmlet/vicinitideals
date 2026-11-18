# 189. rel7 move-read fix-forwards (2026-11-12)

[Claude] [scan: YES -- toward green only, a handful of lots]

From ../vicinitideals-worktrees/rel7-moves.findings.md (move reader on net live -> rel7a,
fingerprint a0274bc3322afc538045642f2c37c2dd; 699 gained greens all read right, verdict SHIP).
None is a false GREEN; all are possible false YELLOW/RED.

- F2 CLOSED, expectation was wrong (no code change, branch flats/fix-189): the 9 ft retry IS
  reached on both. 1N2E21BA -12200 (70 ft wide): the pod's 80 ft face cannot face the street on a
  60 ft envelope at any lane width; turned, it misses by 1.5 ft (116.5 of 118 ft deep) and a 9 ft
  lane makes the court aisle deeper, never shallower -> RED stands. 1S2E15AD -08900 (67 ft wide):
  an 80 ft face cannot face the street -> ENTRANCE-SIDE-DOOR stands. The lane targeted 94-97 ft lots.
- F3 FIXED on flats/fix-189 (fire_roads._room_across): Thorville's 80 ft bulb stands 16 ft off the
  centreline; the room at a dead end is now also read across the street's own mapped right-of-way.
  The lot loses FIRE-DEAD-END but stays YELLOW on ENTRANCE-SIDE-DOOR. ~1% of walked dead ends read
  ROOM (14 of ~1,400 in the test area), toward green only. Awaits a bound.
- F4 FIXED on flats/fix-189 (quadfit._screen_on): a parking-frontage cap miss retries the building
  squared to each street the lot abuts and keeps the better reading; Rusk Rd reads 48.78% -> back to
  YELLOW. Awaits a bound.
- F1 (note only) Eldorado 22E08AC02500: the fg4 lane's "missed by 0.2 ft" was wrong; it is 24.5 ft
  short and correctly RED.

- F5 DONE 766dd02d: West Linn sewer root (GoDaddy TLS Root CA - R1) pinned in flats/config/ca/, trusted beside certifi by the ingest clients (flats/ingest/tls.py); live acquire from 137 verified.
- F6 DONE (recipe, no repo commit): /root/recipes/bound_splice/body.sh has an acquire() helper that passes `--root $D/flats/sources`; acquire.py default root left as is.
