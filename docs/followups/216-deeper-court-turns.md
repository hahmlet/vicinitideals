# 216. Court turns for the deeper stair-room courts (fd8 F3)

[Claude] [Steph: count a deeper court as passing when the standard court passes?] [scan: YES -- toward green]

Opened 2026-11-22 from the fd8b move read (`../vicinitideals-worktrees/fd8b-moves.findings.md` F3) and fd8-fix2
(`../vicinitideals-worktrees/fd8-fix2.result.md` "F3 -- stopped").

- About 1,473 of 1,592 FOUNDATION-STAIR-MOVED green->yellow lots are yellow only on MEASURE-COURT-TURNS: the
  stair-room re-placement raises the building-to-court standoff (`Design.reserving`, `building_gap_ft`), and
  `court_turns.json` holds no measured entry for the deeper gaps (135 shapes).
- The turning search cannot measure them honestly: its answers depend on lattice alignment (passes at 6.25 / 6.5 ft,
  fails at 5.33 ft on the same court with a longer straight drive). Partial results kept on 137 (`/root/fd8fix2/`).
  Gap-5 promotion is impossible (no base entries for these shapes).
- Options: (1) full independent search of all 135 shapes -- many hours, still lattice-unreliable; (2) carry the car's
  measured path from the standard court onto the deeper court (a longer straight drive cannot be harder), checking each
  step; (3) align the search lattice to the standard court.
- Pending: Steph's ruling on (2). Ships after the 213 release; its lots are a subset of the fd8 re-bound scope.
