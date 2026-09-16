# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **Tualatin lot WIDTH on a cul-de-sac (RL and RML, 50 → 30 ft).** TDC
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
