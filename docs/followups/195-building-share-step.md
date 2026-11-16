# 195. Building minimum share of frontage: a pass exactly at the minimum on 1 ft steps

[Claude] [scan: YES -- toward yellow, possible FALSE GREEN]

Found while fixing the rel9 move read's F1 (../vicinitideals-worktrees/rel9-frontage.handoff.md, "Open items").
The parking-share cap fix (flats/rel9 2b166a6b) holds a share that only meets its cap because it is
counted in 1 ft steps. `building_runs` (the building's MINIMUM share of frontage) uses the same 1 ft steps
in flats/fit/frontage.py, so a lot that meets a minimum exactly on the coarse count may be under it.
The same fix applies the other way round: take the lower bound (count minus one step per start or stop
of the building along the line), and hold the lot YELLOW (existing measurement-tolerance flag) when the
count passes but the lower bound fails. Count the live GREENs sitting exactly at a minimum first.
Build as a rel10 lane; read every GREEN it moves.
