# Design districts — plan (FOLLOWUPS 109)

Steph, 2026-10-21: "we do need to incorporate Rockwood (and other) design
districts." The inventory is in
[design_districts_2026-10-21.md](design_districts_2026-10-21.md). It found
84 districts in the screened cities; 62 reach the pod in at least one form,
and 32 of the ones that are not simply a zone have no boundary in our data.

## Steph's answers (2026-10-21)

- **Order:** both stages go ahead. Ingest the information before analysing it.
- **Roof:** the pod's roof is intended to be flat. A district that refuses
  flat roofs is RED (rulings.yaml `2026-10-21-pod-roof-flat`).
- **Washington County community plans:** yes, read them.
- **Budget:** work in chunks, not open-ended, so other development keeps
  its share of the week's usage.

## How each chunk runs

- At most **two workers** at a time, and one chunk at a time.
- A chunk **ends** when its changes are tested, every lot that changes colour
  has been read one by one, and the result is live, either by one splice or
  by riding the weekly re-screen when that is due within two days.
- Report to Steph at the end of each chunk: colour changes and why, and any
  questions.
- **Cadence: no more than two chunks a week.** Steph can say "pause" (the
  capacity goes to other work) or "speed up".
- A chunk that turns out bigger than planned stops at the plan's line, and
  the rest becomes the next chunk. It does not keep going.
- Fixes that could leave a **false GREEN** go first inside every chunk.

## The chunks

| # | What | Kind | Size |
|---|---|---|---|
| 1 | **Greens at risk, on data we already hold.** Building-frontage share (Beaverton Downtown and mixed-use, Washington County NMU/CCMU, King City Kingston Terrace). Portland main-street townhouse ban, historic- and conservation-district vacant lots, and the design overlay "d" that nothing makes yellow. | false-GREEN fixes | **LIVE run 84 (2026-10-22)**: best-pod greens 48,185 -> 46,932 |
| 2 | **Ingest everything missing. No encoding.** Portland's transit-street map (unlocks most of the main-street yellows from chunk 1). Boundaries: Oregon City concept plans (Park Place, South End) and historic districts; Portland plan districts; Troutdale Town Center; Tigard Washington Square and River Terrace; Sandy Bornstedt Village; Wilsonville Old Town; Clackamas Regional Center and Sunnyside Village; Canby downtown, Tualatin Central (CO Block 1), Gladstone Town Center; Hillsboro South Hillsboro and Witch Hazel Village South; Gresham's six district outlines (already downloaded). Text: Portland's plan-district chapters, Wilsonville's Old Town design book, Washington County's eleven community plans. Output: a list of what was fetched and what could not be found. | ingest | 1 worker |
| 3 | **Frontage share measured as each code measures it** (Steph 2026-10-21): townhouse form on the four unit lots where the code applies the share per lot, the original lot where it says site or development -- Beaverton (both rules), Washington County, King City, Gresham. Wide lots (Steph 2026-10-21): if enough pods to reach the share fit side by side along the street, even roughly placed, YELLOW; if not, RED. Plus Steph's answer on King City entrances. **Greens at risk, on the newly ingested data.** Oregon City concept plans (the pod misses the footprint rule) and historic districts (hearing, so not green). Flat-roof bans (Fairview Village, West Linn, and any others the text shows). Clackamas Sunnyside Village, Washington County transit-district townhouses, Wood Village Town Center, Sandy Bornstedt (row-house widths), Wilsonville Old Town. | false-GREEN fixes | 2 workers |
| 4 | **Reds that may be wrong.** Gresham townhouse-only zones (~830 lots), Troutdale HDR in the Town Center (~350), Tigard Washington Square, Estacada Downtown, Canby, Tualatin CO Block 1, Gladstone Town Center. | false-RED openings | 2 workers |
| 5–7 | **Washington County community plans**, about four plans per chunk, largest first. They cover all 68,777 unincorporated lots. | read and encode | 2 workers each |

Other queued work outside this plan stays in docs/FOLLOWUPS.md. For example,
the lot-of-record sweep (item 108) fits between chunks.
