# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **Regenerate `data/flats/coverage.csv` on 137.** Last committed 2026-09-08
   (c194fca2); since then Tualatin's bulb rows, the alley side half and the
   Multnomah alley waiver landed. The local parcel file is Multnomah-only (10
   Clackamas jurisdictions count no lots), so `flats.encode.backlog` refuses to
   write it here -- run it on 137 with `--corpus` pointed at the s2 parquet the
   pipeline uses, bring the CSV back, commit. Housekeeping, ~15 min. Offered
   2026-09-16.
2. **The paper lot never charges the parking court's width.** `paper.py
   court_depth` charges the rear court's depth (stall + aisle) and says in its
   own docstring that the court's WIDTH -- six stalls at the city's stall
   width, about 54 ft, plus the side driveway reaching them -- is unmodelled
   and can only make a lot need more. `parking_stall_width_ft` is encoded in
   all 14 cities and read by nothing (`flats.encode.consumed`). The county
   verdicts are not affected: quadfit's s6s siteplan places stalls by width.
   This is the per-zone paper answer only ("the smallest lot that satisfies
   everything written"), which today understates width wherever the court is
   wider than the building plus its side yards. Offered 2026-09-16.
