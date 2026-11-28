# 202. Portland FEMA / flood gap: what is still open

Shipped in rel11 (run 131, ee8baaba) 2026-11-21. Portland now screened against the FEMA zone and the 1996 flood area (PCC 24.50.040 E, same treatment); river 'e' overlay carved (Steph 11-18: a lot touching 'e' with everything drawn clear stays green). The 64 Title 3 greens were read: 63 right, 1 fixed.

Open (findings ../vicinitideals-worktrees/fema-portland.findings.md, pdx-flood-text.findings.md, title3-greens.findings.md):
1. 8 greens within 50 ft of the FEMA zone: PCC 24.50.050 edge rule, no elevation check. Levee buffer on 1N1E03AD  -02200 undetermined.
2. Not fetched: PCC 24.70 and the Metro Title 3 map layers.
3. Carry the 1996 layer (Portland Maps Hazard layer 30) into the next promoted snapshot.
4. Hazard flood note shows "not mapped" on about 5,876 Portland greens (the old FEMA gap): reload the hazard flood note, and add FEMA depth / datum fields then. Hazard lot rows need reloading with each new county copy.
5. Metro's regional flood map flags 73 greens inside the FEMA floodplain (68 Portland) against 13 on the FEMA zone; the 64-lot read covered part of it, the rest is unread.
6. One class on the coarse statewide landslide map is not in its legend (20 lots, stored as printed, level undetermined).
