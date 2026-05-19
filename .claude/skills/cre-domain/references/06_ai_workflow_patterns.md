# AI Workflow Patterns in CRE

## Why This Matters for Viciniti

Viciniti is not competing against static Excel workbooks. It is competing against Excel workbooks that are increasingly wrapped in AI copilots — Claude for Excel, ChatGPT for Excel, Endex, Shortcut, FormulaBot, and a growing list of vertical tools like CRE Agents, Archer, rrol.ai, and Fundrise's RealAI (source: 50_ai_tools_for_commercial_real_estate.md, 65_best_ai_tools_for_excel.md, 73_realai_aiedge_by_acre.md). The AI-augmented analyst using Claude inside Excel is the real benchmark. If Viciniti cannot match the "ask a question, get a sourced answer with a cell trace" experience, it will be perceived as slower and less flexible than the tool users already trust.

At the same time, industry leaders are openly telling CRE pros that "using AI regularly is now the expected baseline" and that reflexive, systematic AI use is the differentiator (50_ai_tools_for_commercial_real_estate.md). The frameworks that have emerged — the Multiplier Framework from A.CRE and Musk's 5 Principles applied to CRE — tell us exactly how practitioners are thinking about where AI adds value. Viciniti's product decisions should be read through these frameworks: users will evaluate Viciniti on whether it makes their highest-impact micro-tasks faster, whether it integrates cleanly with their AI cockpit, and whether it exposes enough structure for their skills and agents to operate on top of it.

## The Multiplier Framework: Audit, Quantify, Identify, Prioritize, Execute

A.CRE's Multiplier Framework (61_multiplier-framework-double-your-cre-output-with-ai.md) is the dominant mental model CRE pros are adopting in 2026. It is explicitly portfolio-level: it tells you *where* in your workflow AI will pay off, and in what order.

1. **Audit** — Inventory deliverables and decompose each into 20-50 repeatable micro-tasks. "I build a financial model" is a deliverable; "download the OM, parse the rent roll, map the T12 to your chart of accounts, extract unit mix, run a fit check" are tasks.
2. **Quantify** — Assign hours, dollars, and frequency to each task. Example from the workshop: if closing 2 acquisitions generates $400K in fees and you screen 200 deals a year, every screened deal is worth $2,000 of attention (60_the-multiplier-framework-workshop-2-double-underwriting-speed-with-ai.md).
3. **Identify** — Brainstorm solutions. Critically, solutions are NOT tools-first: they go (1) make requirements less dumb, (2) delete, (3) delegate, (4) automate.
4. **Prioritize** — Rank by impact × feasibility. Start high-impact, easy.
5. **Execute** — Move tasks through a Kanban: Manual → Implementing → Iterating → Automated.

Underwriting is the #1 requested AI target, but "underwriting" is not a single AI job — it's 7-10 micro-tasks (fit check, rent roll cleanup, T12 mapping, comp research, model build, validation). The multiplier math in Workshop #2 is striking: running three properties through three parallel AI micro-tasks cuts 180 minutes of manual work to ~23 minutes — an 8x multiplier (60_the-multiplier-framework-workshop-2-double-underwriting-speed-with-ai.md).

## Musk's 5 Principles, Applied to CRE (Automation Is Step 5, Not Step 1)

The Multiplier Framework sits at the portfolio level. Musk's 5 Principles sit at the task level and describe how to redesign any single workflow before automating it (53_automation_principles_multiplier_framework.md):

1. **Make the requirements less dumb** — Do investors actually read the 25-page quarterly report, or do they need 6 charts and 2 paragraphs?
2. **Delete the part or process** — CRE culture biases toward more checks, more tabs, more approvals. Strip legacy appendices from IC memos. Stop abstracting lease fields no one uses.
3. **Simplify and optimize** — Standardize templates, inputs, batching. If you can't explain the workflow to a new analyst in two minutes, you are not ready to automate it.
4. **Accelerate cycle time** — Scheduled review blocks, checklists, fewer sign-offs.
5. **Automate** — Only now plug in AI. The goal is not "use AI somewhere"; it's to tell the AI exactly what input, what output, and what happens next.

The canonical example: a legacy IC memo is 60-80 pages and 100+ man-hours. The redesigned "algorithm" IC memo is 15-25 pages, 20-30 man-hours, and better for actual decisions. The win was shrinking the deliverable before automating it — not automating the bloated version.

**Implication**: CRE pros who think this way are hostile to tools that lock them into someone else's workflow assumptions. They want tools that respect their redesigned process, not impose a new one.

## Categories of AI Tools CRE Pros Actually Use

From the A.CRE tools roundup (50_ai_tools_for_commercial_real_estate.md) and 2026 updates, the practical stack is:

- **General LLMs** (ChatGPT, Claude, Gemini, Grok) — Drafting, summarizing, error-checking, validation passes. Now deeply embedded in Excel/PowerPoint via native add-ins with MCP support.
- **CRE-specific vertical AI** — CRE Agents (vertical agentic platform for acquisitions/asset management/brokerage), AI.Edge (education + prompts/skills community), RealAI by Fundrise (market and asset analyst), Archer (multifamily underwriting), rrol.ai (rent roll parsing), LeaseLens and Prophia (lease abstraction).
- **Workflow automation** — Zapier, Make, n8n, Gumloop, Pipedream. These are the glue between CRM, email, project tools, and AI endpoints.
- **Document AI** — LeaseLens, DocSumo, Handl, Pipe.CRE, Proda — for leases, OMs, rent rolls, lender term sheets, PCRs, and Phase I reports.
- **Excel-native AI** — Claude for Excel, ChatGPT for Excel, Endex, Shortcut, FormulaBot, Microsoft Copilot, Excel 4 CRE Add-in (65_best_ai_tools_for_excel.md). This is where most CRE work is still actually done.
- **Coding/app builders** — Lovable, Replit, v0, Bolt, Cursor, Claude Code. Non-technical CRE pros are now building web apps (e.g., turning an Excel proforma into a browser-based flipping-house calculator — 64_financial_model_web_app.md).

## Skills vs Data: The Methodology/Specifics Split

Workshop #3 (59_the-multiplier-framework-workshop-3-ai-skills.md) introduces the most important architectural concept in this corpus: **an AI skill is not a prompt**. A skill encodes *how* to do a category of work every time. A task (prompt) supplies the *specifics* of this deal.

- **Skill** = stable methodology. "Always start amortization at period zero, build 360 periods, dynamic to term, IO vs amortizing payment types." Encoded once.
- **Task** = deal-specific data. "$25M senior loan, 10-year term, 30-year amort, 5 years IO, 6.5% fixed."

High-value CRE skills the workshop identified: amortization logic, property tax underwriting (4-step methodology with high/medium/low confidence grading), Excel document standards (yellow-highlight inferred cells), IC memo assumptions narratives, slide deck standards, and *modular* financial model skills (S-curves, reversion cash flows, stabilized NOI). The workshop is emphatic that a full financial model crammed into one skill produces garbage — you need modular skills combined at the task layer.

The cockpit mindset: with skills governing each output, a 12-task workload across three deals drops from 4-6 hours of manual prompt engineering to 60-90 minutes — a 4x multiplier that scales linearly.

## Autonomous Agents: OpenClaw and When They Make Sense

Chat-based AI is reactive — you ask, it responds. OpenClaw (58_setting_up_your_first_openclaw.md) is the reference architecture for autonomous CRE agents: a cloud-hosted Telegram-facing agent with three identity files (SOUL.md for personality, USER.md for context, AGENTS.md for operational rules) that can take action, not just answer.

Agents make sense when: (1) the task is recurring and scheduled (daily deal screens, new-listing monitoring); (2) it can be decomposed into clear inputs/outputs; (3) proactive notification is valuable (agent pushes you a hot deal at 2am). Chat-based AI is still better for: one-off analysis, ambiguous judgment calls, and anything requiring back-and-forth iteration.

The Belasco example in 61_multiplier-framework-double-your-cre-output-with-ai.md shows the natural progression: start with a notification engine (all inbound → Slack), add pre-screening (filter by type/location/price), then add qualifying logic (score quality, draft LOI skeletons). Five years ago this needed a developer; now a non-technical principal stands it up in 30 minutes.

## What's Ripe for AI vs What Stays Human

Ripe for AI augmentation (per 60_the-multiplier-framework-workshop-2-double-underwriting-speed-with-ai.md):
- Rent roll parsing, T12 mapping, unit mix tables
- Lease abstraction
- Fit checks against a buy box
- OM-to-first-pass-model input extraction
- Market/location research and 5-year trend summaries
- PCR and Phase I summarization
- Cross-checking: validation passes, assumption vs narrative consistency

Stays human: final investment judgment, relationship/negotiation, physical inspection, capital partner alignment, and the "why now" thesis. AI drafts, humans decide.

## Viciniti Implications

- **Expose an MCP server / AI-friendly API.** CRE pros in 2026 expect Claude, ChatGPT, and CRE Agents to reach into their tools via MCP. Viciniti should ship an MCP endpoint that exposes deal reads, scenario writes, sensitivity runs, and parcel queries. This reframes Viciniti from "another SaaS" to "an MCP-addressable deal database" that slots into the user's existing AI cockpit.
- **Publish a Viciniti skill library.** Provide versioned Claude/ChatGPT skills for the methodologies Viciniti already encodes (e.g., "Viciniti NOI Stabilization Skill," "Viciniti Debt Carry Skill," "Viciniti Waterfall Skill"). These are free marketing and anchor the platform as the source of truth for the methodology.
- **Preserve Excel export as the lingua franca.** 65_best_ai_tools_for_excel.md confirms Excel isn't going away — users will want Viciniti data in a workbook that Claude for Excel can audit. Keep Excel export first-class, with the yellow-highlight convention for inferred cells that matches the industry skill pattern.
- **Build in micro-task surfaces, not just the full model.** The Multiplier Framework wins by attacking underwriting as 7-10 separable tasks. Viciniti should expose rent roll parse, T12 map, fit check, and sensitivity as independent endpoints/UIs — not only behind the full-model wall. This is how Viciniti becomes useful at screen time, not only at IC time.
- **Position as "Excel alternative for the web-and-agent era."** The 64_financial_model_web_app.md piece is the Viciniti thesis in miniature: Excel is the rigor, the web app is the distribution and collaboration layer. Lean into that narrative — rigor preserved, distribution/collaboration/agent-integration unlocked.
