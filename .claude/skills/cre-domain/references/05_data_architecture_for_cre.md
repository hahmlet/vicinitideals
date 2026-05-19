# 05 — Data Architecture for CRE: Building Systems That Make AI Actually Useful

## Why This Matters for Viciniti

Viciniti is, at its core, a CRE data platform. The underwriting engine is the visible surface, but the moat is 446K parcels stitched to jurisdictions, a continuously refreshed listings corpus from Crexi/LoopNet/REALie, and a KNN market engine that interpolates financial metrics from completed deals. Every downstream feature — deal scoring, rent prefill, NOI benchmarks, pipeline triage — depends on whether that data layer is structured, auditable, and queryable by both humans and AI agents. If the data architecture is sloppy, the model outputs and the AI assistants built on top will be confidently wrong in ways that are hard to catch.

The A.CRE Workshop #4 [51] makes the case plainly: four years into the AI era, the prompt is no longer the bottleneck — the data is. This document synthesizes how CRE data pipelines should be built so that both deterministic engines and AI copilots can reason over them, using the Workshop #4 framework and the radius-demographics methodology [63] as anchors.

## The Optimal Output Framework: Instructions + Tools + Knowledge

Every AI output is a product of three ingredients [51]:

1. **Instructions** — the prompt, task-specific.
2. **Tools** — the AI's ability to act (run code, query a DB, edit a file).
3. **Knowledge**, which splits into two:
   - **Skills** — stable methodology the AI follows every time (the topic of Workshop #3).
   - **Data** — live, deal-specific information that changes constantly.

Raw AI with no data connections fills the data slot with a mix of training-cutoff memory, opportunistic web scraping, and confident-sounding interpolation. In Spencer's Kent Valley demonstration [51], Claude with connectors disabled declared a $13.50/SF asking rent "approximately 5% above market"; the same prompt against a real Airtable comp set revealed the rent was **19% above the comp average and 12.5% above the highest-rent comparable**. For demographics, raw Claude scraped King County job boards and Ziprecruiter and labeled the output a "10-mile radius analysis." That was a hallucination — not a lie, but a confabulation born from missing structure.

## Why Raw AI Fails Loudly Only When It Has Structure

The deeper insight from Workshop #4 [51]: *AI working from a structured database knows what it doesn't have.* When Spencer connected the Airtable comps, Claude correctly flagged that clear-height data was missing and refused to fabricate the comparison. Training-data AI cannot do this — it has no schema to check against, no concept of a NULL cell, no way to distinguish "I don't know" from "I wasn't asked."

This is the single strongest argument for structured data over scraped data: **structure gives AI the negative space it needs to be calibrated.** A well-shaped schema with explicit nullable fields turns every query into a partial-information problem the model can reason about honestly. An unstructured blob of listing HTML turns every query into a creative-writing exercise.

## Comp Database Design Principles

From Workshop #4 [51], the design rules for a comp DB that AI can actually use:

- **Schema co-designed with the model.** Spencer asked Claude what fields an industrial sale comp should have, refined in dialogue, then handed the spec to Airtable's auto-generation. This is a pattern: let the model surface the fields it will later need to query, then lock them in.
- **Fields must include the decision-relevant, not just the identifying.** Address and price are necessary but insufficient. Cap rate, NOI, price/SF, clear height, column spacing, year built, buyer/seller identity — these are the fields that drive underwriting comparisons.
- **Bidirectional writes.** The database grows by AI appending new observations, not just by humans typing. In the workshop, Claude saved the subject property back as a new rent comp at session end. Without write-back, every deal dies as a one-off.
- **Queryable granularity.** Submarket, property type, vintage buckets — the filter dimensions the AI needs to narrow a comp set. KNN only works if the features are there to match on.

## Radius-Based Demographics: The Hardest Easy Problem

Census data is published at block-group and tract level, but CRE demand analysis is radius-based (1/3/5/10-mile rings). You cannot solve this by averaging nearby tracts, distance-weighting centroids, or treating block groups as binary in/out of the ring [63]. The A.CRE methodology:

1. Geocode the address to lat/lng and draw a **true geometric circle** of the requested radius.
2. Use Census TIGERweb to find all block groups that **intersect** the circle.
3. Compute the **actual geometric intersection polygon** for each partially-covered block group.
4. **Weight by land area**, assuming uniform population distribution within the block group (disclosed assumption) and excluding water area.
5. **Aggregate**: sum totals (population), compute population-weighted averages (per-capita income), and use weighted distributions for medians.

The output is auditable because every step is explicit: an analyst can inspect which block groups were included, what percentage of each fell inside the ring, and which assumption drove the weighting. Percentile ranks against the national distribution of equivalent radii [51] turn raw numbers into a decision signal.

## The Four Guiding Principles

Lifted directly from the radius-demographics build [63] — these generalize to any CRE data pipeline:

1. **Use free, authoritative data where it exists.** Census ACS, TIGERweb, county GIS. Paid layers are reserved for gaps the free tier cannot fill.
2. **Work at the finest practical resolution.** Block group > tract. Parcel > ZIP. Monthly > annual. Downsampling is cheap; upsampling is a lie.
3. **Be mathematically explicit about assumptions.** "Population is uniformly distributed inside each block group" is disclosed in the output, not hidden in the code.
4. **Fail loudly when results aren't trustworthy.** Population density outliers, coverage thresholds, single-block dominance, geometry errors — every output passes internal QA gates and surfaces a warning rather than a plausible-but-wrong number. Plausible-but-wrong is worse than nothing.

## MCP Versus API for AI Integration

Spencer framed it simply [51]: MCP (Model Context Protocol) is an API, but built on a protocol the AI speaks natively. The practical difference is the integration cost. An API requires a tool-calling shim — you write an OpenAPI spec, register functions, handle auth per call, shape responses for the model. An MCP connector exposes typed tools and resources the model can discover and invoke without the glue layer. The A.CRE Intelligence Hub [51] — MongoDB for storage, AWS for hosting, Claude Code for build — exposes SOFR curves, radius demographics, employment, and permits through MCP so Claude can call them in the middle of a conversation without the user switching tabs.

For a data platform like Viciniti, the choice is not either/or: expose a REST API for external integrations and a parallel MCP server for AI copilots. Same underlying queries, two surfaces.

## Viciniti Implications

- **The parcel + listings + KNN stack is already the hard part — expose it via MCP.** Viciniti has what most CRE shops spend years building: 446K parcels with jurisdictions, a continuously refreshed listings corpus, and a KNN comp engine that already interpolates financial metrics. The highest-leverage next step is wrapping that engine in an MCP server (parcel lookup, comp search, market-metric interpolation, radius demographics) so Claude and downstream tools can query it directly — not a future "AI feature," but infrastructure.
- **Fix the jurisdiction labeling problem before it poisons AI outputs.** The known issue in CLAUDE.md — scraped `city` values using metro names instead of actual jurisdictions (Gresham listings tagged "Portland") — is exactly the kind of plausible-but-wrong signal Workshop #4 warns against. Backfilling `jurisdiction` from nearest-parcel lookup is a data-quality project with direct AI-correctness implications.
- **Adopt radius-demographics methodology for submarket rollups.** The block-group-intersection-with-land-area-weighting pattern [63] is directly applicable for building Viciniti submarket demographics from parcel geometry. Same math, same guardrails, same disclosed assumptions — and the parcels are the finer-resolution equivalent of block groups for inventory/ownership rollups.
- **Bidirectional writes for the KNN engine.** Every completed deal underwritten in Viciniti should write back as a comp observation (with consent/flags for private deals) so the KNN set grows monotonically. This is how the comp database becomes a compounding asset rather than a static snapshot.
- **Schema-level guardrails, not just engine-level.** Add the radius-demographics QA pattern [63] to Viciniti outputs: coverage thresholds on KNN neighbor counts, outlier flags on comp prices, explicit "insufficient data" states in the API and UI. Fail loudly. The weighted-median work in commit `4eb074f` is already this pattern — formalize it across every derived metric.
