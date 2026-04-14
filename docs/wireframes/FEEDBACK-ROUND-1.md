# Wireframe Feedback — Round 1
_Captured 2026-04-04. Items marked [DISCUSS] need a conversation before implementing._

---

## DEALS (Page 01)

### Small / Clear
- [ ] **Hide Archived by default** — table should open with Archived filtered out for all users
- [ ] **Add deal type column** — major reno, minor reno, conversion, new construction, etc. Helps differentiate deals at a glance
- [ ] **Rename status "Hypothetical" → "Evaluation"**
- [ ] **Rename status "Active" → "Execution"**
- [ ] **Define the status pipeline** — evaluation → execution → under contract → closed. There are drop-off points at each stage. Treat it as a forward-moving funnel, not a generic status picker.
- [ ] **Rename "Hide" → "Archive"** (or similar). "Hide" encourages poor data hygiene; archived implies intentional removal with data preserved
- [ ] **Deal Name must be user-settable** — not auto-generated
- [ ] **Building data column must be user-settable** — similar to deal name; user defines what's meaningful here
- [ ] Address displayed below deal name — confirmed, keep as-is

### [DISCUSS] — RESOLVED
- **What is a deal?** ✅ Deal = Building + Parcel. One deal row per B+P combination. Financial models are a layer on top; one model is designated "primary" (the one we currently think is the winning scenario). No multiple deal rows for the same B+P.
- **Multiple deals for a B+P combo** ✅ Resolved by above — there is only one deal per B+P. Multiple models are evaluated, one is marked primary.
- **Financial model structure** ✅ Templates exist but are lightweight. Example: every renovation project gets a Uses table scaffold. Not fully standardized, not fully snowflake — light scaffolding that can be customized per deal.

---

## BUILDINGS (Page 03)

### Small / Clear
- [ ] **Don't auto-open the detail drawer** — the wireframe shows it open by default as an artifact to demonstrate the state. On the real page, nothing should be selected until the user clicks a row
- [ ] **"Post-conversion units" → "Existing units"** — unit count belongs to the building as-listed, not to any deal outcome. The deal determines what happens to those units.

### [DISCUSS]
- **Sale status field** — poll from the listing source daily to show whether a property is still listed, under contract, or sold. Touches the scraper/ingest pipeline and needs a data model decision on where this lives (Listing? Building? Both?).

---

## LISTINGS (Page 05)

### Small / Clear
- [ ] **Source column hidden by default** — source is secondary data. When visible, each source entry should be a link to the listing on that platform. Multiple sources per listing is a feature.
- [ ] **Rename "Parse" column** — "Parsed" implies text extraction from unstructured paragraphs. We're pulling structured API data. Better label options to discuss: "Ingest Status", "Import Status", "Data Status"
- [ ] **`{}` Raw JSON button does nothing** — wireframe artifact, needs real behavior (open raw JSON drawer)
- [ ] **Add three date columns:**
  - *Original Scraped Date* — when we first saw this listing
  - *Last Updated* — last time actual data changed
  - *Last Checked* — last time we polled regardless of change

### [DISCUSS] — RESOLVED
- **Page feels like two pages** ✅ Primary page = listing feed. Saved Views management moves out of the main content area.
- **Saved Search Criteria → Saved Views** ✅ Confirmed. Model: we hold the full dataset; users save named filter presets (views) to slice it. Criteria eligible for a view TBD in a follow-up conversation.
- **Multi-source disagreement engine** — still open, deferred.

---

## PARCELS (Page 04)

### Small / Clear
- [ ] **Remove "Overrides" column** — the per-field custom badge in the drawer is sufficient; a column-level summary adds noise without value
- [ ] **Add Address City vs Jurisdiction City** — some parcels have an address city that differs from their legal jurisdiction (e.g., 16111 E Burnside shows "Portland, OR 97233" but is actually in Gresham's jurisdiction). Need both fields:
  - *Address City* — what the address says (postal city)
  - *Jurisdiction City* — the actual governing municipality
  - *Jurisdiction County* — may already exist in the scraper; confirm

---

## DE-DUPLICATION (Page 06)

- Direction looks good. No immediate action items.

---

## Items That Are Wireframe Artifacts (Not Bugs)
These look wrong in the HTML but are intentional "default open" states to demonstrate the interaction — not something to fix until building for real:
- Buildings drawer open on load
- Parcels drawer open on load
- Brokers drawer open on load
- Listings ingest banner always showing
