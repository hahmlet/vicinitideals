# 131. Tualatin CO: the overlay's 25,000 sq ft / 16 du-ac stored as the base zone's

131. [Copilot] [scan: YES (reasons only; no colour expected)] **Tualatin CO carries the Central Tualatin overlay's minimums as its base** -- FOUND 2026-10-30 by the chunk 6 move reader.

What: flats/config/jurisdictions/or/clackamas/tualatin.yaml's CO block holds min lot 25,000 sq ft and min density 16 du/ac as BASE values. Both are printed only in the Central Tualatin Overlay's Table 58-7 (flats/provenance/docs/or/clackamas/tualatin/58/58.800.txt#L34-L36). The CO zone's own Table 50-2 prints a 10,000 sq ft minimum lot and no minimum density (50/50.300.txt#L7-L8). The quadfit row (`Lot Analysis/quadfit/config/rules.yaml`, Tualatin CO, ported 2026-10-30) copies them.

Why it matters: no colour today -- outside Block 1 the pod is a prohibited use (TDC 50.200(1)), and inside Block 1 the overlay numbers do apply. But lots show a wrong failing reason (e.g. 2S124DC02100, 21,799 sq ft, lists a lot-size failure it would not have under 10,000), and a future change admitting the pod outside Block 1 would inherit the wrong floor (false RED only).

Change: base min lot 10,000, no base min density; 25,000 and the 16-25 density as variants under the overlay / Block 1 condition (the same one chunk 5 used for the Block 1 townhouse path). Re-port quadfit (`port_from_flats.py --write`) so its CO row takes 10,000.
Must not change: any colour. Test: flats/tests/test_tualatin*.py asserts base 10,000 and the overlay variant 25,000; quadfit test_zone_mirror passes; a bound on Tualatin CO shows 0 colour moves.
