# 185. Pod is really 80 x 30 (homes 20 x 30), not 80 x 25 (Steph 2026-11-11)

[Claude] [scan: YES -- every lot]

Steph has been building to 20 x 30 homes with the factory; FLATS pod80x25.yaml is
20 x 25 (my glazing study also used a 30 ft end wall, adding to the mix-up).
Steph: "we get to start over on design and factory build" -- recommended NOT
yet: first run the screen with an 80 x 30 pod and compare greens vs 80 x 25,
so the redesign decision rests on a count.
Plan: after rel7 releases, add pod80x30.yaml (depth 30) as a comparison design
(not shipped), run a full bound on 137 (quadfit stages may need the new design
too -- bound runner to check), report greens at 25 vs 30 by place.
Also mismatched vs the factory lift list (FOLLOWUPS 145): wall panels 8'1" high
=> storeys ~9.5 ft with 15.5 in cassettes, overall ~20-21 ft, vs config
height_ft 26 and ground_story_ft 12 (Steph 2026-10-01 "12 ft or more"). Confirm
real heights with Steph and run them in the same comparison.
RESOLVED 11-11 (Steph): "I really do want 25x20" -- FLATS pod80x25 stays; no 30 ft
comparison run. Factory design goes back to 20 x 25 (lift list in 145 will change).
Still open: real height "going to be lower than 26" and ground storey -- Steph to
give figures; keep 26 / 12 until then (26 is the cautious side for height limits;
a ground storey under 12 ft would fail Tigard TMU-type minimums).

RULED 2026-11-12 (2026-11-12-single-design-80x25-20ft): the screen had been running pod80x30 since 11-08
(the 11-11 note above was wrong: it said pod80x25 "stays", but pod80x25 is archived). Switch to 80 x 25,
height 20 ft, each storey 9'2" (Steph 11-12: "8' wall with 14 in truss" per floor, ground and top). Lane pod-80x25 off rel7 -> rel8, full bound (every lot). False-GREEN watch: code minimum
building heights / storey heights / first-floor heights that 26/12 passed and 20/9.17 fail.

BUILT 2026-11-12 flats/pod-80x25 91f29656 (hand-off ../vicinitideals-worktrees/pod-80x25.handoff.md): pod80x25@3 active, 80x30 archived. Now miss: Tigard TMU 12 ft first storey; 25 ft floors in Milwaukie DMU, Oregon City WFDD, Troutdale MU-3, Hillsboro UC-RM/NC/OR/RP. Ties at exactly 20 ft (pass only if the pod's code-measured height is >= 20): Clackamas SCMU, Tualatin MUC, Tigard MU-CBD, WashCo TO:BUS. Kenton 33.538.230 25 ft walls (Map 538-4) unencoded -> holding Kenton CM2/CM3/CE YELLOW. Quadfit port + 5 test fixes in progress. Asked Steph 11-12: how is the 20 ft measured.
RULED 2026-11-12 (2026-11-12-height-measured-per-city): Steph "Different cities measure height differently. Our 8' walls will be secured to the slab and flooring will start on the slab" -> slab-on-grade, 18'4" structure above slab; total = slab rise + 18'4" + roofing + parapet (~19'2" with no parapet). Lane pod-height-measure (on flats/pod-80x25): read each city's height definition for every limit near 20 ft; hold the three 20 ft-minimum ties (Tualatin MUC, Tigard MU-CBD, WashCo TO:BUS) YELLOW. Asked Steph: slab rise above ground, roofing thickness, parapet yes/no + height.
