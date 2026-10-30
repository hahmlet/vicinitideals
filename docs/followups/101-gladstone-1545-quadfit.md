# 101. Port Gladstone Ord. 1545 to quadfit's rules.yaml.

101. [Copilot] [scan: NO (quadfit mirror only)] **Port Gladstone Ord. 1545 to quadfit's rules.yaml.**
   Files: `Lot Analysis/quadfit/config/rules.yaml`, the Gladstone R7.2 row (~line 2743). Change:
   `min_lot_sqft` 3600 -> 7200 and `setback_side_ft` 7.5 -> 5, and rewrite its `notes` to cite Ord.
   1545 (in force 2026-08-13) as `flats/config/jurisdictions/or/clackamas/gladstone.yaml`'s
   `amended:` entry does. Must not change: any other row; anything under `flats/`. Test:
   `uv run pytest "Lot Analysis/quadfit/tests/test_zone_mirror.py" -q` green.
