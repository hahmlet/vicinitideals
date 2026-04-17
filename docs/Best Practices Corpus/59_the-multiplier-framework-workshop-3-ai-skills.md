# The Multiplier Framework Workshop #3: AI Skills
Source: https://www.adventuresincre.com/the-multiplier-framework-workshop-3-ai-skills/
Reading Time: 12 min

On a recent live follow-up workshop, we took the Multiplier Framework out of "high level theory" and applied it to one of the most important (and most overlooked) concepts in AI productivity: skills.

*Every CRE professional has methodology they have developed over years of real deals, and right now most of that knowledge lives only in your head. AI skills change that.*

The goal was simple. Walk through what an AI skill actually is, why it matters more than any individual prompt, and then build one live from scratch.

If you missed the live session, or want a tighter walkthrough, this post gives you:

- The full 60-minute workshop replay
- A clear breakdown of what separates a skill from a prompt (and why the distinction matters)
- The anatomy of a great skill, including key principles for writing effective ones
- A live walkthrough of building a property tax underwriting skill in Claude
- A link to the Multiplier Framework app (free) and the framework overview
- Pointers to AI.Edge and CRE Agents if you want help learning or building

## Why AI Skills Are the Perfect AI Target

Most CRE professionals interact with AI one prompt at a time. They type a request, get an output, and either accept it or start over. The problem is not the AI. The problem is that every time you prompt, you are re-explaining your methodology from scratch. How you build an amortization table. How you underwrite property tax. How you format an Excel workbook. How you write an IC memo.

That re-explaining is wasted effort, and it produces inconsistent results. One prompt might get the amortization table right. The next one starts in period one instead of period zero. The one after that forgets IO periods entirely.

An AI skill solves this by encoding your methodology once and reusing it across every task that needs it. Think of a skill as the difference between teaching a new analyst something every morning versus handing them a procedures manual they follow every time. The manual is the skill. The specific assignment you give them is the task.

## Step 1: Separate the Skill from the Task

This is the most important distinction in the workshop: a skill is not a prompt. A prompt (or task) tells the AI what to do right now. A skill tells the AI how to do a category of work every time.

Take the amortization schedule example from the workshop. The skill encodes methodology: always start at period zero (that is your closing period, where the loan funds), build 360 periods, make it dynamic to term, define IO versus amortizing payment types. The skill says nothing about a specific loan. It does not mention a borrower, a rate, or a property.

The task is where the specifics come in: build an amortization schedule for a $25 million senior loan, 10-year term, 30-year amort, 5 years of IO, 6.5% fixed rate. Or: take this existing model and inject a debt module. Or: extract terms from these loan docs and build a schedule. Three completely different tasks, all governed by the same skill.

You cannot automate work you have not defined. If your methodology lives only in your head, AI has to guess at it every time you prompt. Define the methodology once as a skill, and AI follows it consistently across every task you throw at it.

## Step 2: Quantify the Impact

The value of a skill compounds with every task that uses it. Consider a simple example from the workshop.

Without a skill, every time you ask AI to build an amortization schedule, you spend 5 to 10 minutes re-explaining your methodology in the prompt, then another 5 to 10 minutes checking the output for errors that come from vague instructions. That is 10 to 20 minutes of friction per task.

With a skill governing the output, the prompt becomes two sentences. The methodology is already encoded. Your review time drops because the output follows your conventions every time. If you run 50 loan analyses a year, and each one saves you 15 minutes of prompt engineering and review, that is 12+ hours back just on one skill.

Now scale that across every repeatable methodology in your workflow: property tax underwriting, Excel formatting, IC memo narratives, location write-ups. The question is not whether encoding your knowledge is worth the effort. It is which skills have the highest impact and the highest feasibility to build first.

## Step 3: High-Impact, High-Feasibility Skill Use Cases (with possible solutions)

These are the skill types covered in the workshop, each one representing a repeatable methodology that CRE professionals can encode once and reuse across dozens of tasks.

#### Use Case 1: Amortization Schedule Logic

This was the primary example in the workshop. The skill defines core inputs (loan amount, rate, term, amort period, IO period, payment type), period logic (always start at period zero, build 360 periods, dynamic to term), and payment types (IO and amortizing). The skill says nothing about formatting or cell placement, which gives it flexibility to work across tasks that build from scratch, inject into existing models, or modify existing schedules.

- CRE Agents platform (30+ skills including amortization logic, shared across all users)
- Claude or ChatGPT with a custom skill file uploaded or saved to your skill library

#### Use Case 2: Property Tax Underwriting

This skill was built live during the workshop. It encodes a four-step methodology: establish the current tax position (mill rate, assessed value, current tax bill), determine the jurisdiction's reassessment rules (reassessment on sale, public sale price, Prop 13, abatements, special taxing districts), estimate the assessment delta (the standard gap between assessed value and market value using sale comps), and calculate stabilized annual property tax (underwritten value times assessment delta times mill rate as a percentage). It also includes a confidence grading system: high (all data plus comps), medium (subject data but no comps), and low (educated guesses).

- CRE Agents 'Property Tax Underwriting' task
- Claude skill builder (walk through your methodology, then click "Copy to your skills")
- ChatGPT skill editor (paste your skill markdown into the instructions field)

#### Use Case 3: Excel Document Standards

Spencer referenced a personal Excel Document Guide skill that governs formatting, structure, and conventions across all Excel outputs. One example: if the AI infers any inputs or encounters missing data, it highlights those cells in yellow and adds a note. This mirrors the convention many analysts already follow, but encoding it as a skill ensures AI does it every time without being told.

- CRE Agents platform (Excel document guide skill governs all Excel outputs)
- Build your own by documenting your team's Excel conventions and formatting them as a skill

#### Use Case 4: IC Memo Assumptions Narratives

When drafting assumptions for an investment committee memo, Spencer follows a specific methodology for when to write a single-paragraph versus a two-paragraph narrative. The skill includes examples of each: a single-paragraph RUBS narrative with placeholder formatting ("stabilized RUBS income is underwritten at [amount] producing [amount] annually") and a two-paragraph version for more complex assumptions. Those examples ground the AI in exactly what the output should look like.

- CRE Agents platform (assumptions narrative and location narrative skills)
- Build your own by narrating your process as you write a real IC memo, then feeding the transcript to Claude or ChatGPT to generate the skill

#### Use Case 5: Presentation and Slide Deck Standards

The workshop slides themselves were created entirely by Claude, governed by its built-in PPTX skill. Spencer noted that the quality of any AI-generated presentation is a direct function of the skill governing it. Different platforms produce different results: Claude writes Java to generate native PowerPoint files, while tools like Manus convert web pages or images into slides. If your presentations consistently miss the mark, the skill (or lack of one) is usually the reason.

- Claude's built-in PPTX skill (view it on Anthropic's GitHub)
- CRE Agents for custom presentation tasks with CRE-specific formatting

#### Use Case 6: Financial Model Module Skills

A full financial model is not one skill. It is a collection of modular skills: an S-curve methodology for development draw schedules, a reversion cash flow methodology for condo sellouts, a stabilized NOI skill that excludes one-time items. Spencer emphasized that trying to put an entire financial model into a single skill produces garbage. The tech is not there yet (as of early 2026). Instead, break the model into discrete methodology modules, encode each as its own skill, and combine them at the task level.

- CRE Agents platform (modular skills for apartment development, value-add acquisition, industrial development, and more)
- AI.Edge for training on financial modeling methodology before encoding it as a skill

## The Cockpit Mindset

Once you have a library of skills, you stop thinking about AI as a single-task tool and start thinking about it as a cockpit. Each skill governs a different instrument. You are the pilot.

Consider the amortization schedule example. Without a skill, building one schedule manually (writing the prompt, explaining your methodology, checking the output) takes 20 to 30 minutes. With the skill encoded, the prompt takes 30 seconds and review takes 5 minutes. That is a 4x multiplier on a single task.

Now scale it. You are underwriting three deals simultaneously. Each deal needs an amortization schedule, a property tax analysis, an assumptions narrative, and a formatted Excel workbook. Without skills, you are re-explaining your methodology for every task on every deal: 12 tasks, each taking 20 to 30 minutes of prompt engineering and review. That is 4 to 6 hours.

With skills governing each output, those same 12 tasks take roughly 60 to 90 minutes total, because the methodology is already encoded and the review cycle is tighter. That is a 4x multiplier, and it scales linearly with every additional deal you run in parallel. That is the cockpit mindset.

## Step 4: Prioritize

Not all skills are equally valuable. Rank by two criteria: how often you repeat the methodology, and how much time it costs you each time. A property tax underwriting skill that you use on every acquisition is worth more than a formatting skill you use once a quarter. Start with the methodology you repeat most frequently and where inconsistency costs you the most time in rework.

## Step 5: Execute and Iterate

Build the first version, then treat it like a financial model template. Spencer compared it to the A.CRE All-in-One model, which has been updated hundreds of times and still gets bug reports and improvement suggestions. Your first skill will contain errors. Run it against real tasks, check the output, get feedback from your team, check for conflicts between the skill and your task prompts, trim any bloat, and refine. That is how good skills are made.

## Your AI Skills Challenge

1. Identify one repeatable methodology you use on most deals (property tax, amortization, formatting, narratives).
2. Narrate your process out loud as you do it on a real deal, and capture it with a transcription app.
3. Feed that transcript to Claude or ChatGPT and ask it to build a skill from your methodology.
4. Test the skill against a real task. Check the output. Refine the skill where it missed.
5. Store the skill in your personal library, share it with your team, or upload it to CRE Agents for cross-platform use.
