# Washington County: who governs the land

The scope for drafting Washington County, researched 2026-09-28 by the local
session. Read it after [CLOUD_COUNTY_BRIEF.md](../CLOUD_COUNTY_BRIEF.md).

## How the list was made

The list comes from the lots, not from a list of cities. Metro RLIS
`Taxlots (Public)`, `COUNTY='W'`, grouped by `JURIS_CITY`. A state list of
cities by county files each city under one county and misses the ones that
straddle a line. Tier rules come from OAR 660-046-0020, as amended by
HB 3395 (2023). Populations are PSU's 2024 certified figures.

## The jurisdictions

| Jurisdiction | Wash Co lots | In Metro | Middle-housing tier | For the cloud session |
|---|---:|---|---|---|
| Unincorporated (county CDC) | 84,949 | urban part yes | Large (urban) | **Encode** as `or/washington/_unincorporated.yaml` |
| Hillsboro | 33,173 | yes | Large | **Encode** |
| Beaverton | 28,596 | yes | Large | **Encode** |
| Tigard | 19,927 | yes | Large | **Encode** |
| Forest Grove | 7,756 | yes | Large | **Encode** |
| Sherwood | 7,241 | yes | Large | **Encode** |
| Cornelius | 4,288 | yes | Large | **Encode** |
| King City | 2,787 | yes | Large | **Encode** |
| Durham | 446 | yes | Large (pop. ~1,900) | **Encode** |
| Tualatin | 7,358 | yes | Large | Already encoded (`or/clackamas/tualatin.yaml`); do not copy |
| Portland | 383 | yes | Large | Already encoded (`or/multnomah/portland.yaml`) |
| Wilsonville | 163 | yes | Large | Already encoded; likely prison and industrial land |
| Lake Oswego | 14 | yes | Large | Already encoded; `eligible: false` is Steph's |
| Rivergrove | 16 | yes | Exempt (under 1,000) | Already `eligible: false` |
| North Plains | 2,057 | **no** | Medium: duplexes only | Do not encode; owner decision |
| Banks | 678 | **no** | Exempt | Do not encode; owner decision |
| Gaston | 285 | **no** | Exempt | Do not encode; owner decision |

Pointing the already-encoded cities' Washington County lots at their
existing layers is county-map work. The local session does it. The
Tualatin lots are the large share: the Clackamas map holds only about
1,000 of Tualatin's 8,400 lots.

HB 2138 (2025) requires middle housing on every residential lot from
2027-01-01. It may bring North Plains, Banks and Gaston into scope. Record
that in the handoff; do not act on it.

## Traps to read the code for

- **The mailing city is not the jurisdiction.** About 68,000 county-governed
  lots have a Portland or Beaverton address (Aloha, Cedar Mill, Bethany, and
  others). The layer is chosen by `JURIS_CITY`, never by `SITECITY`.
- **Holding zones FD-20 and FD-10.** Land added to the urban growth boundary
  but not yet annexed stays under the county, zoned FD-20 (FD-10 for the
  small cities), even where a city's concept plan shows it dense. Cooper
  Mountain, River Terrace 2.0, Sherwood West and Kingston Terrace are
  examples. The county's middle-housing list leaves FD out. Rule the use
  gate from the CDC's use table, never from a city plan.
- **County district families.** Plan-district variants live in the zone
  codes, so the zone list must hold each one as its own zone or as a `like:`:
  - urban R-5 to R-25+
  - North Bethany `R-6 NB` / `R-9 NB` / `R-15 NB`
  - transit-oriented `TO:R9-12` to `TO:R80-120`, `TO:RC`, `TO:EMP`, `TO:BUS`
  - `CBD`, `NMU`, `CCMU`, and the other commercial districts

  The county's own zoning layer is
  `gispub.co.washington.or.us/server/rest/services/Open_Data/Open_Data_AGOL/MapServer/2`,
  field `LUD`, with an `Urban` flag. Use it for the zone harvest.
- **Community plans.** The county has 11 community plans (Aloha-Reedville,
  Bethany, Bull Mountain, Cedar Hills-Cedar Mill, and others). Each has
  subareas and "areas of special concern" that change standards by place.
  Such a standard is a per-area condition. Encode it as a variant behind a
  condition nothing measures yet, so the lot screens UNKNOWN, and list it
  in the handoff. Never guess which lots it covers.
- **Rural districts do not take a quadplex.** They are EFU, EFC, AF-5/10/20,
  RR-5, R-COM, R-IND and MA-E. Rule each one `quadplex_allowed: false` with
  its cite. Do not encode their dimensions.
- **Beaverton.**
  - An interim zone `WAcnty` (county zoning kept after annexation) exists
    inside the city.
  - UPAA §V.D lets Beaverton keep applying the county's setbacks, lot
    sizes, coverage and heights in subdivisions the county approved before
    annexation. That is a per-lot condition nothing measures. Declare it,
    do not guess it.
- **Hillsboro** carries an `ANX` zone (annexed, zoning pending). Rule it,
  don't skip it.
- **Tigard, Tualatin and Sherwood** apply city zoning at annexation (TMC
  18.720 table 18.720.1, the Tualatin UPAA, Sherwood Title 16 interim
  zoning). No gap needs encoding there.
- **Clean Water Services** vegetated-corridor and sensitive-area standards
  apply across urban Washington County, in cities and county alike. They
  are overlay data, which is local work. Note where each code points at
  them.

## Unverified; check before relying on it

- The annexation-zoning clause for Forest Grove, Cornelius, King City,
  Durham and Wilsonville. Their agreements are scanned images.
- Whether River Terrace 2.0 has annexed since June 2026.
- North Plains' duplex-only compliance status.
