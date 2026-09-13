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
2. **Wilsonville and West Linn send the driveway to the alley too; Milwaukie
   does not.** Read 2026-09-13 while doing Gresham: Wilsonville
   4.113(.14)(D)(4)(c)(i) (`wilsonville/4.planning.txt#L3556-L3559`, the
   quadplex driveway standard: *"For lots or parcels abutting an alley that
   is improved with a paved surface, access must be taken from the alley"*;
   the townhouse copy `#L3835-L3838`; Villebois 4.125 `#L4928-L4929` is
   moot, its 30 alley lots are all OTR) and West Linn 48.025(B)(3)(a)
   (`west-linn/48.access.txt#L55`, Option 1: *"If a property has access to
   an alley or lane, direct access to a public street is not permitted"*;
   Willamette historic `25.willamette-historic.txt#L432,L440` says the
   same for garages). Milwaukie's only alley sentence
   (`19.500.supplementary.txt#L1988`) lets a stall sit within 10 ft of an
   alley line — placement, not access — and its 7 alley lots stay
   street-fed. Set `alley_access_required: true` on wilsonville and
   west_linn in `config/footprints.yaml` with those cites (Wilsonville's
   "paved" condition is unmeasured — take it, note it), pin them in
   `test_footprints_yaml_sends_two_cities_driveways_to_the_alley`, s6s→s7
   (~10 min) measured both ways. Stake: 54 lots, all red today (Wilsonville
   30 OTR: 21 under the zone minimum, 22 fail the plan — 19
   `court_too_shallow`, 3 `no_side_lane`; West Linn 24 R-5: 14
   `siteplan_no_layout`, 11 of them `no_court`). Neither city states an
   alley setback. Offered 2026-09-13. **Approved by Steph 2026-09-13; the
   measurement baseline is `/root/lots_results_after_alleywidth4.csv`
   (the alley-width run of the same evening).**
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
