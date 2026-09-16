# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **Tualatin's lot width on a cul-de-sac bulb is declined on 74 of 81 bulb
   lots.** The 30 ft bulb row shipped 2026-09-15 evening
   (`min_lot_width_cul_de_sac_ft`, s7 width gate), but it reaches 4 lots:
   Tualatin measures width `center_parallel` ("parallel to the front lot
   line", TDC 31.060), `lotdims.center_parallel_width_ft` refuses any lot
   with more than one front bearing as a corner lot, and a bulb arc reads as
   TWO front groups on 74 of the 81 (tier B 68, C 6; `front_bearings_json`
   two bearings 20-60 degrees apart on the same arc). A lot s4 has proven on
   a bulb (`fronts_cul_de_sac`) with both bearings on that arc is one front,
   not a corner; measure parallel to the chord across the arc's ends (or the
   bulb circle's tangent at the lot's centre angle) and the row starts to buy
   something. quadfit s4 change, needs the 31.060 second-half refusal kept
   for TRUE corners (two bearings on two streets), then s4->s7 on 137 (~48
   min). Zero verdicts moved by the row so far (the one bulb lot under 50 ft
   is already below the minimum lot area). Offered 2026-09-15.
