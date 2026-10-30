# 80. Readings for Steph from item 64 round 2.

80. [Claude] [Steph: (a), (c)] [(d) Copilot-able] [scan: (a)(b) RULED + BUILT, r3 MERGED to main (83a7683d), ride the weekly ~2026-10-19; (c)-(e) open] **Readings for Steph from item 64 round 2.**
   (a) "Parking may cover at most half of a street frontage" caps (Wilsonville 4.113(.14)D.3,
   Hillsboro 12.50.715 C.1, Clackamas ZDO 845.02(D), Beaverton). RULED (Steph 2026-10-14; register
   `2026-10-14-frontage-cap-any-street`): ANY street frontage. Built (flats/fit/frontage.py,
   measured on the drawn plan): a court behind the building on a one-street lot counts nothing, so
   31W15DC05351 and 31W22DC01400 (Wilsonville) STAY GREEN. Bound: 241 lots go red on the cap,
   every one a corner or through lot (Clackamas 105, Beaverton 103, Wilsonville 23, Hillsboro
   SCR-MD 10); two ways one street was read as two (a bend under the 45-degree corner angle; a jog
   in one frontage) fixed, 38 lots back. QUESTION for Steph, open: 1S113BA07700 (Beaverton RMC
   yellow -> green: base's preferred plan was yellow on SLOPE-GRADE, the cap pushed it to a green
   plan off the other front) -- should a yellow preferred plan hide a green one?
   (b) Hillsboro SCR-MD/SCR-HD 5 ft MAXIMUM side setback (12.22 tables): RULED (coordinator
   2026-10-14): "one wall within 5 ft" (12.50.130.C.3.a); moved no lot in the bound (the research
   leaned "both walls", moderate confidence -- recorded in hillsboro.yaml; not yet in the register,
   see 86(B)).
   (c) Wood Village TC: building goes through a "Town Center Development Plan" (the old Master
   Plan); its approval type is in 235.400/235.490, not stored, and the site answers 403 to every
   fetch. A human copy of those sections decides 10 TC greens (1N3E34B   -00807 can't tell).
   (d) Estacada is charged 4 stalls (state middle-housing cap) but is under 25,000 people and
   outside Metro, so its own 1.5 per home = 6 stalls applies (emc.16.76.txt:77-78). Every Estacada
   green still seats 6+ except 34E17D 00700 (5, room for more): a fix with no colour change.
   (e) Noticed: flats.flag_instances was last refreshed at run 70 (no row seen after it), so it
   still shows JURISDICTION-OFF on Tigard lots; run 74's own results carry the right flags.
