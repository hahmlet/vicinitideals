# 185. Pod is really 80 x 30 (homes 20 x 30), not 80 x 25 (Steph 2026-11-11)

[Claude] [Steph] [scan: YES -- every lot]

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
