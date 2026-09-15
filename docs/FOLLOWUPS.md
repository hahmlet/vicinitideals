# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **The side half of the alley waiver — a per-side setback in the FLATS
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
2. **Tualatin lot WIDTH on a cul-de-sac (RL and RML, 50 → 30 ft).** TDC
   Tables 40.220 / 41.220 (`40-41.residential.txt#L190-L193`, `#L500-L503`):
   the quadplex row's 50 ft minimum average lot width "may be reduced to 30
   feet if on a cul-de-sac". Refused in tualatin.yaml because nothing
   measured the bulb; since 2026-09-15 quadfit s4 does (`fronts_cul_de_sac`,
   81 Tualatin lots). Happy Valley and Wilsonville hold it on the FRONTAGE
   row via `min_frontage_cul_de_sac_ft`; this is the WIDTH row, so it needs a
   `min_lot_width_cul_de_sac_ft` column in `rules.yaml`/`common.py`, the s7
   width gate to take it, `port_quadfit.HELD_AS_VARIANT` to route it to
   `min_lot_width_ft` under `fronts_cul_de_sac`, and the two variants. Small
   population (Tualatin is mostly Washington County). Offered 2026-09-15.
