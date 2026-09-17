# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **A lane ceiling the pod cannot get under.** Six cities cap the
   maneuvering width on townhouse (unit-lot) plats at 10 or 12 ft
   (`parking_maneuvering_max_width_ft`, `unit_lots` variants only). A cap
   under the lane the design draws is not a wider lot, it is a site plan
   that cannot be drawn -- s6s drops the lane where the cap is under it, but
   the paper lot has no "cannot be drawn" state and declares the field
   unread. Adding that state to `PaperFit` (and a row on the plan page) is
   the honest fix; Milwaukie's 10 ft cap against a 12 ft lane is the case
   that would show. Offered 2026-09-17.
