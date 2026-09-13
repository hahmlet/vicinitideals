# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **Wire `abuts_alley` into FLATS from quadfit class `A`, and name the
   line.** The site fact is registered in `flats/rules/fields.py` and nothing
   fills it; s4's `edges_json` carries the answer for 11,340 lots (every
   one with a measured `alley_width_ft` since 2026-09-13), and s6s
   acts on it for Portland (`DrivewayRules.alley_access_required`, the one
   driveway field with no FLATS counterpart — add it to `DRIVEWAY_MIRRORED`
   in `test_parking_geometry.py` and lift the NOT ENCODED note beside
   `parking_street_setback_ft` in portland.yaml the same day). The fact has
   to say WHICH lot line abuts the alley (rear / side), not just that one
   does: PCC 33.110.220.D.9 and 33.120.220.B.3.g waive the side AND rear
   setback from that line, quadfit's s5 now cuts to it (`setback_alley_ft`,
   2026-09-12), and the corpus holds the sentence only as the
   `setback_garage_entrance_ft` exemption because an `exempt: true when:
   [abuts_alley]` on `setback_side_ft` would waive both side yards of a lot
   whose alley is behind it (see `HELD_AS_VARIANT` in
   `flats/encode/port_quadfit.py`). Encode the rear/side variants the day the
   per-line fact exists. One job with the bearing + neighbour-zone facts
   already noted as computable. Carried from 2026-09-12. **Approved by
   Steph 2026-09-13 ("I'm good with 1 and 2").**
2. **5,614 lots still get a "narrowest street edge" under 20 ft beside a
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
3. **Happy Valley cul-de-sac frontage (22 review lots)** — HV asks 35 ft on
   a bulb and more on a straight street; the screen cannot tell a bulb. The
   curve-merge machinery in `lotdims.front_groups` now knows a chord chain's
   radius and sweep, which is most of a bulb detector. Carried from 2026-09-11.
