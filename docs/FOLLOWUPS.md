# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **Happy Valley cul-de-sac frontage (22 review lots)** — HV asks 35 ft on
   a bulb and more on a straight street; the screen cannot tell a bulb. The
   curve-merge machinery in `lotdims.front_groups` now knows a chord chain's
   radius and sweep, which is most of a bulb detector. Carried from 2026-09-11.
2. **The side half of the alley waiver — a per-side setback in the FLATS
   model.** PCC 33.110.220.D.9 / 33.120.220.B.3.g (and the county's copy)
   waive the SIDE setback from a lot line abutting an alley as well as the
   rear. The rear half shipped 2026-09-13 keyed to `alley_at_rear`; the
   side half is refused in portland.yaml (RF) and `_unincorporated.yaml`
   (R10) because `setback_side_ft` is one number for both side lines and an
   `exempt: true when: [alley_at_side]` on it would waive the far side yard
   too. `alley_at_side` is measured and registered (quadfit s4 class `A`
   more than 30° off the frontage; `flats.geom.alley`) and switches nothing
   — `test_alley_at_side_switches_nothing_yet` pins that. Needs a per-side
   field (or `setback_side_ft` split into near/far by the envelope), then
   the exemption on the alley side only. Small population: alley-beside
   lots are mostly corners. Offered 2026-09-13.
