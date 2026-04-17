# Radius-Based Demographics for Real Estate – Built with AI and Census Data
Source: https://www.adventuresincre.com/radius-based-demographics-tool-census-data-ai/
Reading Time: 7 min

## The Core Problem

The U.S. Census publishes data by block group and tract, not by custom radii. But in CRE, everything is radius-based (1-, 3-, 5-, 10-mile rings).

You can't just average nearby tracts or use distance weighting. And you can't pretend that block groups are either "in" or "out" of your circle.

The goal: build a tool that delivers radius-based demographics in a way that is auditable, explainable, and institutionally defensible.

## Four Guiding Principles

- Use only free, authoritative data
- Work at the finest practical Census resolution
- Be mathematically explicit about assumptions
- Fail loudly when the results aren't trustworthy

## The Methodology

### Step 1: Start With a Point and Radius
User inputs an address. Convert it to latitude/longitude coordinates via Google Geocoding API and draw a true geometric circle based on the requested radius. Verify the geometry before continuing.

### Step 2: Identify Intersecting Block Groups
Use the Census' TIGERweb to find Census Block Groups that intersect with the radius circle. Block groups provide the best mix of granularity and data quality.

### Step 3: Compute True Intersections
For each intersecting block group, compute the actual geometric intersection with the radius. This is critical. Partial overlaps are handled precisely without heuristics.

### Step 4: Weight by Land Area
Assume population is evenly distributed within each block group's land area (disclosed assumption). For each group, calculate what % of its land area falls inside the circle and weight the data accordingly. Water areas are excluded.

### Step 5: Aggregate to Radius-Level Metrics
Sum totals (like population), calculate population-weighted averages (like per-capita income), and use weighted distributions to estimate medians.

## Guardrails and Data Quality Checks

Every output goes through internal QA checks:
- Population density outliers
- Coverage area thresholds
- Single-block dominance
- Geometry errors

If something fails, flag it. Plausible but wrong data can be worse than no data at all.

## Tech Stack

- ChatGPT 5.2 Thinking for logical reasoning through the problem
- Replit's Agent3 for building the backend
- Spatial intersections using TIGERweb
- ACS queries via Census API
- Polygon math and area weighting
- Aggregation and error handling
- Frontend design and implementation

Fully self-hosted for control over caching, versioning, and performance.

## Relevance to Viciniti

The exact problem Viciniti's parcel data solves at the jurisdiction level. The block-group-to-radius weighting approach is directly applicable for building submarket demographics from the 446K parcels in inventory.
