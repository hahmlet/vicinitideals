# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **Portland waives the setback from an alley, and s5 still charges it.**
   PCC 33.110.220.C.9: "No side, rear, or garage entrance setback is
   required from a lot line abutting an alley" (single-dwelling zones);
   33.120.220 says the same of the garage entrance in the multi-dwelling
   zones. `Lot Analysis/quadfit/s5_envelope.py` sets a class-`A` edge back
   as the rear (5–10 ft), so every one of Portland's 11,519 alley lots has a
   court 5–10 ft shallower than the city would allow — and `court_too_shallow`
   is the reason 6,700 of them are red. An s5 change is a full s5→s7 run
   (~86 min); measure both ways against `/root/lots_results_after_alleyfeed.csv`
   on 137. Decide whether the relief reaches the whole building or only the
   garage entrance in 33.120 before encoding it there. Related and smaller:
   33.266.130.F.1.b(2) lets stalls back straight out into the alley with 20
   ft of manoeuvring across it, which would drop the on-site aisle the
   alley-fed court still draws — needs alley widths RLIS does not carry.
   Carried from 2026-09-12.
2. **Wire `abuts_alley` into FLATS from quadfit class `A`.** The site fact is
   registered in `flats/rules/fields.py` and nothing fills it; s4's
   `edges_json` carries the answer for 11,794 lots, and s6s now acts on it
   for Portland (`DrivewayRules.alley_access_required`, the one driveway
   field with no FLATS counterpart — add it to `DRIVEWAY_MIRRORED` in
   `test_parking_geometry.py` and lift the NOT ENCODED note beside
   `parking_street_setback_ft` in portland.yaml the same day). One job with
   the bearing + neighbour-zone facts already noted as computable. Carried
   from 2026-09-12.
3. **5,614 lots still get a "narrowest street edge" under 20 ft beside a
   real run of 45 ft or more** (2,655 in the clean shape tiers; Portland
   3,925). The tractable part is ~1,300 end-of-street corner arcs of two or
   more chords (20–45 ft): the second street lies past the 50 ft the edge
   classifier looks, so the arc has a street run on one side only and
   `_is_clip` cannot tell it from a narrow corner lot's real front. Single
   chords under 20 ft are already dropped (`_END_CLIP_MAX_FT`). Either look
   further for the second street when a chain turns 60°+ on a tight radius,
   or record it as a refusal. The rest are slivers, notches, stubs and lots
   ringed by street, plus 128 lots whose street run continues straight into
   a non-street line (44 picked as the front) — likely a street the file
   does not carry. Carried from 2026-09-11, widened 2026-09-12.
4. **Happy Valley cul-de-sac frontage (22 review lots)** — HV asks 35 ft on
   a bulb and more on a straight street; the screen cannot tell a bulb. The
   curve-merge machinery in `lotdims.front_groups` now knows a chord chain's
   radius and sweep, which is most of a bulb detector. Carried from 2026-09-11.
