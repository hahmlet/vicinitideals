# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **The paper lot never charges the parking court's width.** `paper.py
   court_depth` charges the rear court's depth (stall + aisle) and says in its
   own docstring that the court's WIDTH -- six stalls at the city's stall
   width, about 54 ft, plus the side driveway reaching them -- is unmodelled
   and can only make a lot need more. `parking_stall_width_ft` is encoded in
   all 14 cities and read by nothing (`flats.encode.consumed`). The county
   verdicts are not affected: quadfit's s6s siteplan places stalls by width.
   This is the per-zone paper answer only ("the smallest lot that satisfies
   everything written"), which today understates width wherever the court is
   wider than the building plus its side yards. Offered 2026-09-16.
