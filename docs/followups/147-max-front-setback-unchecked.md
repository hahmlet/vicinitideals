# 147. The maximum front setback is never checked on its own -- FALSE GREEN RISK (found 2026-11-04).

147. [Claude] [scan: YES -- toward red] **Maximum front setback never checked on its own -- FALSE GREEN RISK.**
   Found by the move read of the fire_rp3 bound (FOLLOWUPS 142a; scratch /root/fire_rp3_rd/ on 137).
   Tigard 2S103AA00300 (RES-B, max front setback 20 ft) is GREEN with its building drawn 60 ft from the
   street, in the BASE screen too, not only on the fire branch.
   Where it is used today: `setback_front_max_ft` only bounds the building-frontage share band
   (flats/ingest/quadfit.py share_band ~L4175, flats/score/screen.py ~L2745) and caps the flatter-ground
   search (flats/ingest/flatter.py _max_front_ft, which itself allows max(stated, where the plan already
   stands)), plus the Portland main-street overlay (flats/geom/pdx_overlays.py ~L1178). A zone with a
   maximum front setback but no building-frontage share has NO check that the drawn building stands
   within it. ~25 jurisdiction files carry the field (Gresham 27, Beaverton 27, Hillsboro 16, WashCo 10,
   Portland 9, Tigard 9, ...).
   Build: (1) count live greens/yellows whose drawn building stands beyond the stated maximum on every
   street the code applies it to; (2) a screen check: if a fitting placement within the maximum exists,
   draw there; if none fits, the plan fails the maximum (RED where the rule is clear, YELLOW where the
   street it applies to is unclear, e.g. a corner); unmeasured (no drawing/street line) = held, never
   GREEN. Status: encoder BUILDING 2026-11-04 (flats/max-front-setback).
