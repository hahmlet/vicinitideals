# 105. Follow every cross-reference one layer down (Steph 2026-10-20).

105. [Claude] [rounds 1-4 DONE and live (main); open list below] [scan: YES (new standards bind)]
   **Follow every cross-reference one layer down (Steph 2026-10-20).** A footnote or standard that says
   "see Section X", "conform with Table Y for the Z district" or "may be approved per Section W" is not
   read until the place it points to is. Steph's words: "If the next layer is clear and objective, then it
   is just as essential to understand as any other table/ruling at the top level. If it's leading to an
   administrative ruling process or something, then we need to know that too." So each reference lands in
   one of: (a) clear, measurable -> encode it like any top-level standard; (b) an approval process ->
   classify by the 2026-10-14 three tiers (clear review green / conditions yellow+flag / judgement red);
   (c) not about the pod -> dismiss with the reason. Tools: `uv run python -m flats.encode.crossrefs
   <layer> --binding` (references never fetched; a ruling goes in the jurisdiction YAML `crossrefs:` map)
   and `flats.encode.routing` (redirects into held sections; closes only on an encoded value, so its
   rulings are recorded here, not in YAML).

## Done (all on main and live; history in git)
Batch 1 + round 2 (flats/crossref-follow 9a229b24, rel4); round 3 (flats/crossref-follow-2 b78a4495, rel5: Tigard RES-A/B/C 5 ft S-3 strip, every binding row in the corpus ruled); round 4 (flats/crossref-follow-3 3f1e7f0e, rel6: ten binding rows, 128 routing rows read, Washington R-9 NB / R-24 NB / NMU / CCMU 5 ft buffer, Washington alley flag 16 ft). Fetched under Steph's OK (11-08, standing download OK 11-09): Tigard 18.420, Canby 16.41.060, Gladstone 17.76, Washington 409, West Linn 42 and 28. Canby 16.41.060 and Gladstone 17.76 read, no change. Items 4 (Washington improved alley flag) and 5 (Clackamas 1002.02 trees, answered by the trees ruling) and 9, 10 are done.

## Still open

1. **Beaverton 70.20.10.6.2, the Active Frontage Design Map: TRACED 2026-11-13 (flats/beaverton-type-a,
   dd475d15).** Figure fetched from the BDC full export (PDF page 612, same sha256 as the stored source),
   georeferenced to RLIS centrelines and typed per 20 ft piece (A / B / doubt / none) into
   flats/config/areas/or/washington/beaverton/active-frontage-design.geojson (`drawn: true`); read by
   flats/geom/active_frontage.py and observed in flats/ingest/quadfit.py. Two facts now: on the map
   (12 ft ground floor, D.3/S2.c) and Type A (16 ft, D.2/S1.a); off the map the D.1 exemption stands.
   A lot within 60 ft of a traced end or with mixed frontage stays held; Area C = Type A, Area D held.
   Run 124: 228 off the map lose this hold (0 to GREEN, other holds remain); 73 newly bound (RED, the pod
   misses 12 and 16); 152 still held. Left: D.1's "within min/max setback" fronting test is not modelled.
2. **Corner vision areas** -- still unmodelled (now its own item, FOLLOWUPS 161, ruled 11-09); round 4 collected the legs (below). (Washington 418-3; West Linn Chapter 42, held round 4; Beaverton 60.55.35.3,
   which defers to the Engineering Design Manual). This corpus does not model vision areas anywhere.
   This is the known under-count.
3. **West Linn Chapter 28**: HELD and read round 4 (below); needs a quadfit overlay. Was: (river protection areas and Habitat Conservation Areas) kept `fetch`. The
   areas are boundaries the screen does not hold (see the 28.040 ruling).
4. **Resolver gap** in flats/encode/crossrefs.py `_resolves`. A held section answers only for printed
   full-number headings. So subsections printed locally ("7." under 60.05.15), hyphen numbering
   (Washington 431-8, 407-6, 307-7.5), letter suffixes (Hillsboro 12.61.700G), ranges (Gresham
   4.1531-4.1534) and table or figure captions all read as unfetched. A fix would let `ref` resolve
   when it starts with a held id plus "." or "-". That shifts every layer's ledger, so it is its own
   change.
5. **Beaverton, noticed and not chased**: 60.05.20.7.A asks for a 10 ft walkway along an elevation with
   a primary entrance. It reads as commercial (tenant entrances, display windows). Cooper Mountain
   Nature Park 25 ft setback (Table 20.22.15 G.6): already listed NOT ENCODED.
6. **Non-binding rows: not worked.** 1,523 open rows that stand beside no encoded value (round 3
   read one, Beaverton 60.05.25.13 landscape buffers: N/A for middle housing except the Cooper Mountain
   NPB-25 already listed). Most are use-specific chapters, procedures and boilerplate; the top of the
   queue by mentions was skimmed and nothing distance-bearing seen besides that one.

Read, not encoded (possible false GREENs, each needs a mechanism or data; listed for the coordinator):
- **Vision triangles, corpus-wide.** Legs collected: Washington 418-3 20 ft from the road-edge apex;
  Estacada 15 ft from lot lines; Tigard 18.930 30 ft (35 ft on arterials); Gresham Table 6.04 40/45 ft,
  no drive or parking inside; Milwaukie 12.24 by AASHTO; Canby 10 ft street-to-driveway, 30 ft
  street-to-street from curb lines; West Linn 42.040 30 ft at corners and 42.050 a driveway triangle
  30 ft each way along the street with its apex 30 ft into the lot for every use but a one- or
  two-family house -- the pod's own driveway. A corner triangle never reaches a building whose front
  plus street-side setback is at least the leg; the West Linn driveway triangle reaches a pod whose
  front setback plus offset from the drive centreline is under 30 ft.
- **Driveway spacing by street class.** Tigard 18.920.030.I.2 (150 ft from a collector or arterial
  intersection; relief below 150 ft of frontage) and I.3 (200 ft on a collector, 600 ft on an
  arterial, no relief); Estacada 16.116.010 (D)(2) (50 ft from an intersection, relief where no other
  access) and Table 16.116.030 (private access 200 ft on a major collector, 100 ft minor). Reaches lots
  whose every street is a collector or arterial; `local_street` answers that in Tigard, but `when:`
  cannot negate it.
- **West Linn Chapter 28.** Inside the Willamette Greenway / Tualatin protection area (city zoning map,
  not held) a lot holding a Metro HCA needs a quasi-judicial permit; on HCA land the house and its
  impermeable surfaces may total 5,000 sq ft (28.110.B). Metro Title 13 is laid over Wood Village only
  in quadfit overlays.yaml.
- **Washington 418-2 future right-of-way** for R-24 NB, NMU, CCMU (half the TSP maximum width; not
  for Middle Housing): the TSP design parameters are not held. Zones already UNKNOWN.
- Cornelius Type I middle housing site review (18.100.030 (A)(2)): ministerial, GREEN tier; no change.
- Beaverton 70.20.10.6.2 trace (item 1): done 2026-11-13 on flats/beaverton-type-a (see item 1).
- Lake Oswego 50.06.001.5: not fetched (layer switched off, zero lots).
