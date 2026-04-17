# Workshop #4: Give AI the CRE Intelligence It Needs
Source: https://www.adventuresincre.com/workshop-4-give-ai-the-cre-intelligence-it-needs/
Reading Time: 16 min

On a recent live follow-up workshop, we took the Multiplier Framework out of theory and into one of the most important (and most unsolved) problems in CRE AI: data.

Your AI is only as good as what you give it. Without access to real data, it sounds confident, produces something that looks professional, and is often wrong in ways that are hard to catch.

The goal was simple. Show exactly what happens when Claude operates with no data connections, then fix it step by step using real comp databases and live data feeds, and demonstrate the difference side by side.

## The Real Problem Isn't the Prompt

Four years into the AI era, most CRE professionals have gotten reasonably good at prompt engineering. They know how to write a specific instruction, how to give context, how to ask for the format they want.

But the prompt is only one ingredient. Spencer introduced the Optimal Output Framework: every AI output is a product of three things. Instructions (the prompt, specific to the task at hand). Tools (the AI's ability to take action, like writing code, running web search, or editing a file). And knowledge, which splits into two subcategories: skills (stable methodology the AI follows every time) and data (live, deal-specific information that changes constantly).

Workshop #3 tackled skills. This one tackles data, and Spencer made the case directly: right now, data is the single biggest weakness in AI for commercial real estate.

## What Raw AI Does With a Real OM

Spencer built a hypothetical offering memorandum for Kent Valley Logistics Center, a fictional industrial property in the Kent Valley submarket of King County, Washington. He then asked Claude, with all connectors disabled, to produce a one-page investment proposal. The prompt was specific: validate the rent and cap rate with comps, analyze 10-mile radius demographics and employment, recommend floating versus fixed rate debt.

Claude declared it a great OM, attempted a web search for comps, and surfaced market-level reports from Cushman and CBRE, a cap rate survey, and listings from Loopnet and Commercial Cafe. It found spot SOFR rates but could not access Chatham's full forward curve. For demographics, it scraped what it could find, including results from King County government job boards and Ziprecruiter, which are not radius demographic sources. It noted a 10-mile radius analysis had been completed. That was a hallucination.

The output read well. It included rent validation, cap rate commentary, a debt recommendation, and key risks. A first-day analyst might find it reassuring. An experienced underwriter would immediately notice that the rent was flagged as approximately 5% above market, the cap rate was declared in-line, and the demographics section was populated with city-level data dressed up as a radius analysis. None of it was sourced from actual comps or actual data.

The problem is not that Claude failed. The problem is that it did not fail loudly. It hedged with ranges, it sourced from whatever it could reach, and it produced something that looks like analysis. That is what Spencer means when he says AI without data sounds confident and is often wrong.

## Fix #1: Build a Comp Database and Connect It via MCP

The first fix was a comp database. Spencer walked through building one in Airtable, a cloud-based database tool that is accessible to non-developers and connects directly to Claude via MCP (Model Context Protocol).

The schema was designed with Claude's help: Spencer asked Claude what fields an industrial sale comp database should have, refined the schema in a back-and-forth, then handed the final prompt to Airtable's built-in AI (called Omni) to auto-generate all the columns. The database included fields for address, submarket, building size, year built, clear height, column spacing, sale price per square foot, cap rate, NOI, and buyer and seller identities, among others.

With the Airtable MCP connector enabled, Claude could now read, query, and write to the database directly from a conversation. No copying and pasting, no tab-switching. Spencer described what MCP is in plain terms: if you are familiar with an API, it is the same idea, a connection to an external tool, but built on a protocol that is simpler for AI to speak to natively.

He then ran the same prompt with Airtable enabled. Claude found five Kent Valley comps, pulled them into a structured table, and came back with a materially different answer. The $13.50/SF asking rent was not 5% above market. It was 19% above the comp average and 12.5% above even the highest-rent comp in the set. The $5.73 cap rate was supported but described as tight. Price per square foot was a premium to every comparable trade. None of that signal existed in the raw AI output.

Spencer also noted something worth paying attention to: because Claude was working from real data, it also knew what was missing. Clear height data had not been populated for the comps, so it flagged that rather than inventing a comparison. AI working from training data or web scraping cannot tell you what it does not have. AI working from a structured database can.

One more feature: Claude can write back to the database. At the end of the session, Spencer asked it to save the subject property as a new rent comp, and it did. That bidirectional flow, pulling comps in and saving new observations back out, is how a comp database grows over time without manual data entry.

## Fix #2: The A.CRE Intelligence Hub

The second fix addressed what Airtable cannot provide on its own: market-level data. Spencer introduced the A.CRE Intelligence Hub, a proprietary MCP server built by the A.CRE and CRE Agents teams. The tech stack is Claude Code for development, MongoDB for data storage, and AWS for hosting. It currently serves four live data feeds:

- Rates and Capital Markets: A 121-period SOFR forward curve, swap rates, Treasury rates, corporate spreads, and loan proceeds modeling.
- Census and Demographics: Radius-based population, income, home value, and rent data at 1, 3, 5, and 10-mile rings, with percentile ranks comparing any given radius to every equivalent radius in the country. The radius calculation is the hard part: census data is reported at the block level, not the radius level, so producing a true radius requires weighting across all census blocks within the ring.
- Employment and Labor: Employment data by submarket and radius, including a momentum index and a resilience index.
- Residential Permits: Permit data for demand-side analysis.

With the Intelligence Hub enabled alongside Airtable, Spencer ran the same prompt a third time. The output now included three-mile, five-mile, and ten-mile radius demographics with percentile rankings, 11-year population and income growth trends, the full 121-period SOFR forward curve, loan proceeds comparisons for floating versus fixed, and employment data with momentum and resilience indicators.

## The Side by Side

Same OM. Same prompt. Three outputs.

Raw AI said the rent was approximately 5% above market. With real comp data: 19% above the comp average. Raw AI had no comp-level price-per-square-foot data. With Airtable: 14% above every comparable trade in the set. Raw AI described demographics using city-level Kent data. With the hub: true radius data at three rings with percentile ranks against the national distribution. Raw AI found a 2028 SOFR forward rate from a web scrape. With the hub: a 121-point forward curve suitable for structured loan modeling.

Spencer had Claude score both versions of the investment proposal. The raw AI version received a 6.5 out of 10. The data-connected version received an 8.5. The remaining 1.5 points, Claude noted, would require a full DCF with exit scenarios.

## What This Means for How You Build

On proprietary data sources: connecting to a paid data provider requires either an API or an MCP server. Spencer noted that CoStar is unlikely to open either, but providers like Hello Data have open APIs that subscribers can connect directly to their AI.

On building your own intelligence hub: it is more accessible than it sounds. Claude Code can help you scaffold the architecture. MongoDB is the right data store. AWS handles hosting.

On data governance at scale: AI has lowered the barrier to institutional-grade data architecture so significantly that if your endgame requires it, you might as well start there rather than building a simpler MVP first.

The takeaway from Workshop #4 is direct: the prompt matters, the skill matters, but if the data is not there, you cannot trust the output. Fixing the data problem is not a technical project for the IT team. It is a practical workflow decision that any CRE professional can start on today with a free Airtable account, an MCP connector, and the comps you already have sitting in an Excel file.
