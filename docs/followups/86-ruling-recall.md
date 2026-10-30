# 86. Agents could not recall a property ruling (Steph 2026-10-15, GO for A/B/C1/C2 the same day). A, B, C1, C2 MERGED; the DLCD backlog is READ.

86. [Claude] [Steph: (B) unattributed rulings] [scan: YES for (C1) once entered] **Agents could not recall a property ruling (Steph
   2026-10-15, GO for A/B/C1/C2 the same day). A, B, C1, C2 MERGED; the DLCD backlog is READ.**
   DONE: (A) `flats_find_lot` / `flats_lot_report` / `flats_rulings` JSON routes = VicinitiDeals
   MCP tools, CLAUDE.md rule. (B) flats/config/rulings.yaml (93094b35; additions 3a06a3e8,
   16d3d94a), test_rulings_register.py. RULE: every new Steph ruling gets a register entry in the
   same commit that encodes it. (C1) RICAP 11 (56efd334): adopted changes carry adopted/effective
   dates on the zone (rules loader `law_on`, run-key `law`). (C2) DLCD watch (38528135):
   scripts/flats_dlcd_watch.py + flats/watch/dlcd.py, ledger flats/config/dlcd_read.yaml, runbook
   docs/ops/flats-county-refresh.md 4f; Steph 2026-10-15: run it EVERY WEEKLY (coordinator runs
   it from this PC; an Opus agent reads every new notice). Backlog of 76 adopted + 92 proposed
   notices READ 2026-10-15 (96cc32ba): 6 encode, 16 watch, 146 no effect; encode items -> 88, 89.
   STILL OPEN:
   - (C1) CI1 opens 2026-11-01 under RM1 standards (est. 60-95 of 143 CI1 lots leave red at the
     first run after Nov 1) -- READ that run's CI1 moves; check item 2(d)'s CI cap guard then.
   - RICAP 11 MP5 (back-out pads <= 2 stalls), MP4 (aisle) and TA9 rooftop rear setback are not
     encoded (check later).
   - (B) left out of the register as unattributed/ambiguous: FEMA fringe yellow, landslide list,
     Tigard MUR stricter column (tigard.yaml L972), Portland total-turn, Hillsboro SCR side,
     Milwaukie 22 ft aisle -- add when Steph rules (FEMA fringe and landslide have since got
     entries: `2026-10-06-fema-fringe-stays-yellow`, `2026-10-05-landslide-slopes-declined`).
   - WATCH list: Portland design-review suspension to 2029 (yellow->green possible), Happy Valley
     code update (PC 2026-11-10), Sandy middle housing (2026-10-26/11-16), Canby UGB + Wilsonville
     annexation (new land), Oregon City geohazard clear path, Portland state-law compliance +
     central-city projects.
