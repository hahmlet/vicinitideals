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

## F5 (2026-11-13, from the rel8 bound) -- West Linn sewer feed fails the certificate check

geo.westlinnoregon.gov now chains to "GoDaddy TLS Root CA - R1", which 137's Python cert store does
not trust, so `flats.ingest.acquire` fails `util_sewer_west_linn` (curl fails the same way). The
2026-11-10 snapshot keeps the 2026-10-01 copy. Fix: trust that root (newer certifi / a pinned extra
CA bundle for that host) before the next county refresh; never turn verification off.

## F6 (2026-11-13) -- bound recipe acquired into the worktree, not the shared snapshot

The rel8 body.sh ran `flats.ingest.acquire` from the worktree without `--root`, so it wrote to
`/root/wt/<sha>/data/flats/sources/`, not `$SRC`. Coordinator merged the four new sewer layers
(cws, cws_boundary, sandy, lake_oswego) into the shared 2026-11-10 snapshot by hand (manifest backup
in /root/rel8_bound/). Fix the /root/recipes/bound_splice template: pass `--root $D/flats/sources`.
