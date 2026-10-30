# 129. Trace the three North Bethany maps so R-15 NB / R-24 NB lots outside them can go green

129. [Claude] [scan: YES (yellows only go green)] **Trace the North Bethany map areas** -- OFFERED 2026-10-30 (districts chunk 6).

What: chunk 6 (FOLLOWUPS 109) encoded three North Bethany Subarea Plan rules on Washington County R-15 NB and R-24 NB behind facts nothing measures, so every lot in those zones that could fit the pod is held YELLOW:
- `north_bethany_special_setbacks` -- the Special Setbacks Map (build-to 5-15 ft front, 8 street side, 12 rear; community-plan.north-bethany-subarea.txt#L739-L750);
- `north_bethany_park_blocks` -- ASC 5, the Park Blocks (no vehicle access from the Park Blocks, no parking in front; #L2044-L2048);
- `north_bethany_kaiser_main_street` -- ASC Road Corridor 2, Kaiser Road Main Street, R-24 NB only (5-10 ft setback, 75% frontage; #L1215-L1300).

Where: rules in flats/config/jurisdictions/or/washington/_unincorporated.yaml; facts in flats/rules/conditions.py and flats/config/flags.yaml. The drawn-areas mechanism (memory project_flats_drawn_areas) traces map-only boundaries into geometry and adds a fact to DRAWN_CONDITIONS.

Why: only the lots ON those maps are bound; the rest are held yellow for want of a boundary. Tracing releases them (toward green only). Bound counts from the chunk 6 run land in FOLLOWUPS 109.

Pending: find the plan PDF figures (Special Setbacks Map; ASC map; Figure 1 Main Street Area) -- flats-source-scout first, then trace. Also check while there whether R-6 NB / R-9 NB lots touch the Park Blocks (chunk 6 judged they do not: the build-to table names only R-15+).
