# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **Portland 33.266 / Fairview 19.145: vehicle access must come *from* the
   alley where there is one, and the site plan still faces the street.** The
   alley edge is now classed `A` in `Lot Analysis/quadfit/s4_edges.py`, so the
   fact is known; nothing lays the pod out with its parking off the alley.
   12 Portland greens went red on 2026-09-12 for exactly this (they lay out
   from the alley side and not from the street), and every Portland green
   with an alley is passing on a street-fed layout the city would not
   permit. Decide whether s6s tries an alley-fed layout on class-`A` lots in
   those two cities, or records the refusal. Same lots, same decision: the
   alley-side setback relief (Multnomah County 33.110 waives it, Fairview lets
   a garage sit on the alley line) is not modelled either — strict side.
   Carried from 2026-09-12.
2. **Wire `abuts_alley` into FLATS from quadfit class `A`.** The site fact is
   registered in `flats/rules/fields.py` and nothing fills it; s4's
   `edges_json` now carries the answer for 11,794 lots. One job with the
   bearing + neighbour-zone facts already noted as computable. Carried from
   2026-09-12.
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
