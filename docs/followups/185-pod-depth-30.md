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
