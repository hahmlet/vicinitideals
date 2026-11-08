# 105. Follow every cross-reference one layer down (Steph 2026-10-20).

105. [Claude] [batch 1 DONE 2026-11-08 on flats/crossref-follow; rest listed below] [scan: YES (new standards bind)]
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

## Batch 1 (2026-11-08, flats/crossref-follow)

Every BINDING crossref row closed in the ten places with the most lots except Tigard (unmapped), apart
from the rows below. New outcome `design` (fills ground sized elsewhere; Portland 33.248 landscaping).
Nothing found tightened a standard the screen applies to the pod, so no lot is expected to move.
Places: Portland, Washington County, Clackamas County, Hillsboro, Gresham, Beaverton, Oregon City,
Happy Valley, West Linn. Left `later` (lot creation, binds only when a pod declares a plat): Portland
33.612-33.614, Washington 430-46/601/606, Clackamas 1105.

Routing rows read (routing.csv stays open until something is encoded inside the target):
- Portland 33.120.210 -> .211: FAR bonus options (affordability, three-bedroom, visitability, fund
  payment). Reliefs only; FAR does not bind the pod.
- Portland 33.120.220 -> .283: garage walls. The pod has no garage.
- Portland 33.130.215 -> 33.120.280: detached accessory structures. Another building.
- Portland 33.140.210 note [1] -> 33.140.215.B: Table 140-3 does not apply on lines abutting RX lots.
  Can only loosen.
- Washington 418: 418-1 projections (relief); 418-2 future right-of-way "does not apply to ... Middle
  Housing"; 418-3 corner vision triangle (see open list).

## Still open

1. **Beaverton 70.20.10.6.2, the Active Frontage Design Map (live finding, possible false GREENs).**
   Facades on mapped Downtown streets (RC-BC, RC-OT, RC-MU, RC-DT; 460 lots in all) must meet the
   Active Ground Floor rules. Type A frontages need the non-residential design, with a ground floor of
   at least 16 ft floor to floor (70.20.10.txt#L377-L378). The pod states 12 ft. Type B may take the
   residential design (12 ft minimum, entry no more than 4 ft above the sidewalk, and a stoop, porch,
   patio, terrace or frontage court) (L486-L491). Encode it the Hillsboro Active Use Street way: trace
   the Type A and Type B frontages of the figure as a drawn condition, then put `min_ground_story_ft` 16
   under the Type A condition. Until then a GREEN lot on a Type A frontage is a false GREEN.
2. **Corner vision areas** (Washington 418-3; West Linn Chapter 42 kept `fetch`; Beaverton 60.55.35.3,
   which defers to the Engineering Design Manual). This corpus does not model vision areas anywhere.
   This is the known under-count.
3. **West Linn Chapter 28** (river protection areas and Habitat Conservation Areas) is kept `fetch`. The
   areas are boundaries the screen does not hold (see the 28.040 ruling).
4. **Washington "improved alley"**: 430-84 lets middle housing take access from an improved alley, and
   409-3.3 A sets an alley at 16 ft paved. The screen measures alley width, maybe as right-of-way
   rather than paving. Question for Steph.
5. **Clackamas 1002.02 tree history** (ruled `procedure`). The county refuses design review,
   conditional use or land division applications where more than three trees were removed in the past
   five years (UGB). It reaches the pod only where design review applies (1102.01 districts). Question
   for Steph: flag it, or leave it to the purchase check.
6. **Resolver gap** in flats/encode/crossrefs.py `_resolves`. A held section answers only for printed
   full-number headings. So subsections printed locally ("7." under 60.05.15), hyphen numbering
   (Washington 431-8, 407-6, 307-7.5), letter suffixes (Hillsboro 12.61.700G), ranges (Gresham
   4.1531-4.1534) and table or figure captions all read as unfetched. A fix would let `ref` resolve
   when it starts with a held id plus "." or "-". That shifts every layer's ledger, so it is its own
   change.
7. **Beaverton, noticed and not chased**: 60.05.20.7.A asks for a 10 ft walkway along an elevation with
   a primary entrance. It reads as commercial (tenant entrances, display windows). Cooper Mountain
   Nature Park 25 ft setback (Table 20.22.15 G.6): already listed NOT ENCODED.
8. **Not started**: Tigard (34 binding; unmapped, so no lots move), every other place's binding rows,
   all non-binding rows, and the footnote ledger's "See Section" notes.
