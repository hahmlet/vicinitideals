# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **Wilsonville's corner side yard as a share of the lot's own width.** CDC
   4.113(.02)A.2: on a corner lot over 10,000 sq ft and under 100 ft wide, the
   street-side yard is 20 percent of the lot width, never under 10 ft. The
   value registry has no form for "a share of the lot's width" (nearest:
   `per_height_ft`), so every Wilsonville zone charges the 10 ft floor and a
   78 ft lot that owes 15.6 is read as clear -- the one false-GREEN shape the
   reading queue found and left standing (card `4.planning.txt#4.113`, ruled
   applies, open on this sentence). Counted on 137 (2026-09-16): 205 measured
   Wilsonville corner lots over 10,000 sq ft and under 100 ft wide -- 199 red,
   4 review, 2 green (76 and 78 ft wide); 228 more such corner lots have no
   measured width (the corner refusal) and would take the conservative
   reading. Work: a `pct_of_lot_width` form with a floor, in the registry,
   readiness, `paper.py`, the quadfit `rules.yaml` mirror and s7, tested both
   ways; then s7 alone on 137 to see whether the 2 green survive. Small reach,
   real shape. Offered 2026-09-16.
2. **Regenerate `data/flats/coverage.csv` on 137.** Last committed 2026-09-08
   (c194fca2); since then Tualatin's bulb rows, the alley side half and the
   Multnomah alley waiver landed. The local parcel file is Multnomah-only (10
   Clackamas jurisdictions count no lots), so `flats.encode.backlog` refuses to
   write it here -- run it on 137 with `--corpus` pointed at the s2 parquet the
   pipeline uses, bring the CSV back, commit. Housekeeping, ~15 min. Offered
   2026-09-16.
3. **The paper lot never charges the parking court's width.** `paper.py
   court_depth` charges the rear court's depth (stall + aisle) and says in its
   own docstring that the court's WIDTH -- six stalls at the city's stall
   width, about 54 ft, plus the side driveway reaching them -- is unmodelled
   and can only make a lot need more. `parking_stall_width_ft` is encoded in
   all 14 cities and read by nothing (`flats.encode.consumed`). The county
   verdicts are not affected: quadfit's s6s siteplan places stalls by width.
   This is the per-zone paper answer only ("the smallest lot that satisfies
   everything written"), which today understates width wherever the court is
   wider than the building plus its side yards. Offered 2026-09-16.
