# 143. FLATS 2.0: every word in the code bound to the definition that governs it (major feature).

143. [Claude] [Steph: design before build -- major feature] [FLATS 2.0 -- after 1.0, do NOT start midstream]
   [scan: YES when built (greens can only lose)] **Every word in the code bound to the definition that governs it.**

Decided by Steph 2026-11-03: important, but it must not stop the regular FLATS work. FLATS reaches
1.0 without it; 2.0 is primarily this. "Ideally we would have done this first, but we didn't know
what we didn't know at the time."

## The problem (why this exists)

An AI reads code text in the everyday sense of its words unless the governing definition is
literally in front of it. It does not stop at a word that may be a term of art, and it rarely asks.
That is a judgement failure, not a data, text or software failure -- everything it needed was stored.

The proving case, 2026-11-02 (FOLLOWUPS 80(d), run 113): OAR 660-046-0220's parking ceiling applies
only to a "Large City", a term OAR 660-046-0020(8) defines (25,000+ people, or over 1,000 inside
Metro). The definition was in the store. The encoding AI wrote in flats/config/jurisdictions/or/
_state.yaml that "every jurisdiction in this corpus is one" -- and the same file, a few sections
down, records Canby, Sandy and Estacada as outside Metro and under 25,000. It never checked a
26-city claim against the definition or against its own note. Result: 44 false GREENs in Canby,
Sandy and Estacada, live until run 113.

## What others do (researched 2026-11-03)

- Contract tools (Definely, Zuva, Spellbook): detect defined terms, link each use to its
  definition, flag words "used as if defined but never defined". Works because contract
  definitions are capitalised and in one section; city code defines "lot", "story" uncapitalised,
  in many places, with scopes, and through state law.
- Legal research tools (CoCounsel on Westlaw etc.): answer only from authoritative sources. Fixes
  invented law, not real law misapplied (Large City was real law misapplied).
- Zoning AI vendors (Municode.ai, City Ordinance AI, ...): retrieve sections, answer. None found
  binds definitions. Academic zoning study (Bartik, Gupta, Milo; ~6,000 codes) had to re-check
  every "the code says no" answer. A 2026 error taxonomy calls who/what-a-rule-reaches mistakes
  "scope errors" -- subtler and costlier than wrong numbers. Large City is one.
- Rules as code (Catala; ICML 2026 Catala-from-German-statute pipeline): every term must be defined
  before a rule runs -- strongest binding; forces a single reading; experts still check.
- Legislative markup (Akoma Ntoso, USLM): each use of a defined term carries a hidden pointer to
  its definition. Cities do not publish this way.
- Nobody found doing "every word starts unknown". This design is stricter than any of the above.

## The design (Steph's, refined in discussion)

1. **Start from zero.** Every word and repeated phrase in a city's code starts as "meaning
   unknown" and must earn a status. Only true grammar words (the, of, and, a, is -- a few hundred)
   are dropped unchecked. NOT "common English": the dangerous words are common ("lot", "yard",
   "story", "street", "front", "abut", "adjacent", "height", "average").
2. **Phrases are terms of their own.** "Large City", "dwelling unit", "front lot line", "net acre",
   "half story", "parking lot", "lot of record", "flag lot" -- never folded into their words.
3. **A meaning ID per definition set.** Two uses of a term share an ID exactly when the same set
   of definitions reaches them (code-wide + chapter/section-scoped + county + state). The set is
   the key, so grouping is mechanical, not a judgement. "Lot" might have ~10 IDs corpus-wide.
4. **One synthesised meaning per ID, references kept.** The governing definitions are combined
   once into a single working meaning for that ID; every source definition stays attached, so a
   person or the AI can take it apart and review it. Where sources conflict, the meaning states
   which wins and why (precedence written down); where that cannot be settled, the ID is marked
   CONTESTED with both readings and sources -- never smoothed into one.
5. **Statuses** for every term at every spot: defined here (points to it) / defined by county or
   state (points there) / ordinary meaning, checked (someone looked and nothing applies -- "plain
   meaning" checked against the dictionary Oregon courts use, Webster's Third New International) /
   unknown (not yet checked). "Nobody looked" must never pass for "nothing to find".
6. **Logic words are their own class**: shall, may, must, except, unless, notwithstanding, subject
   to, including. Not definitions -- they decide hard vs soft and which section governs.
7. **Binding at read time.** When the AI reads a passage (encoding, page check, re-reads), each
   term carries its ID and its single meaning beside it -- invisible to a human reader, impossible
   for the AI to replace with the everyday sense without overriding what it was handed.
8. **Amendments re-open only what they touch.** Because references are kept, an amended
   definition marks exactly the IDs it feeds for re-synthesis (same idea as the stored-text drift
   check).
9. **Review economy.** Review ~10 meanings of "lot", not every use. A wrong meaning is wrong
   everywhere it is used -- concentrated, so found and fixed once.

## Finding phrases: brute-force matching (Steph 2026-11-03, assessed sound)

Steph's method: drop grammar words, look every remaining word up in the defined-term list for
that place (city + county + state), and when a word also appears inside a longer defined term
("lot" -> "flag lot"), check the neighbouring words in the text and upgrade to the phrase if it is
there; repeat across the corpus. This is longest-match defined-term linking -- what contract and
legislative-markup tools do -- and needs no AI: plain text search over the whole corpus.

Refinements found in discussion:
- Match longest defined terms first ("front lot line", then "lot line", then "lot"); same result
  as the upgrade loop in one pass.
- Do NOT strip grammar words before matching: "lot of record", "right of way", "floor area
  ratio" contain them. Strip only when listing what is left over.
- Normalise forms before matching: plurals, hyphens (right-of-way), glossary inversions ("story,
  half" vs "half story"), capitals, phrases broken across lines/pages (use the spelling checker's
  word list).
- Split phrases ("front and rear lot lines", "flag or panhandle lot") will be missed: flag any
  word sitting just before a matched term that itself begins a longer defined term -> review.
- Only DEFINED phrases are found. Second pass: multi-word phrases that recur or are capitalised but
  match no definition anywhere -> "used like a term, defined nowhere" queue (Large City-type risk
  if state definitions are missing from the list).
- A match is a candidate, not a binding: which definition governs still depends on each
  definition's scope ("for the purposes of this chapter") -> the meaning-ID step.
- Keep the inner word reachable: "flag lot"'s own definition leans on "lot", so the phrase's
  meaning links to lot's meaning rather than dropping it.
- Leftover queues (unmatched words, split phrases, undefined recurring phrases) are the only part
  needing AI or human reading.

Possible early measurement (Steph to decide; would not change any rule or colour): run the matcher
on one city as a Copilot job and report counts -- words matched, phrases upgraded, leftovers per
queue.

## Known limits (do not oversell)

- The synthesised meaning is itself an interpretation; precedence must be explicit (point 4).
- Meaning is not referent: under middle-housing land division the parent lot and the home lots
  share one definition of "lot" but are different ground. The ID settles what a word means, not
  which thing a sentence is about.
- Scope of a definition ("for the purposes of this chapter") must be read correctly for the ID
  key to be right; that reading is where the AI still needs checking.

## What already exists to build on

- Definition capture in the provenance layer; the glossary reader (flats/encode/glossary.py);
  the hidden-glossary census (687 terms defined outside a glossary; memory "FLATS denominators +
  hidden glossaries").
- The code-library spelling checker (flats/provenance/spelling.py) already lists every word in
  each city's stored code -- the raw word list this design starts from.
- Cross-reference following (FOLLOWUPS 105), footnote scope rules, the rulings register
  (flats/config/rulings.yaml) as the "house interpretations" log.

## Open for Steph before any build

- Design review before a worktree (major feature rule).
- Pilot city choice (one city end to end, then measure: how many terms, how many IDs, how many
  CONTESTED, and whether re-reading encoded rules against the bound meanings finds misreads like
  Large City).
- Whether 2.0 re-reads every encoded rule against the bound meanings, or only rules whose terms
  change status.
