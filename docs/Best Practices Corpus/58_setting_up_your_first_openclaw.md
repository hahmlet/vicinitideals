# Setting Up Your First OpenClaw
Source: https://www.adventuresincre.com/setup-openclaw-beginner/
Reading Time: 15 min

If chat-based AI was phase one, autonomous AI has the potential to be phase two. OpenClaw is an open-source platform for building autonomous AI agents that go beyond answering questions and can take action on your behalf.

Traditional AI tools are reactive. You ask, they respond. OpenClaw represents a shift toward agents that can execute tasks, make decisions, and operate with some level of independence based on the instructions and environment you give them.

## What You'll Need

1. Paid Claude Account with Claude Code Enabled - Claude Code will do most of the heavy lifting.
2. An Amazon AWS Account - AWS EC2 to host your agent in the cloud. Cost: Free to ~$50/month.
3. An OpenRouter Account - Access to a wide range of AI models through a single API key.
4. Telegram on Your Phone - Communication layer between you and your agent.
5. OpenClaw Setup Claude Skill - A 5,000+ word Claude Skill that guides non-technical CRE professionals through setup.

## The Big Idea: Let Claude Code Drive

You do not need to be the one writing code or setting up technical systems. Claude Code is your coding and technical partner while your role is to make decisions, review what it is doing, and provide inputs when needed.

## Setup Steps

### Step 1: Launch a Cloud Server on AWS EC2
- Ubuntu Server 24.04 LTS, t3.medium, 30 GB SSD
- SSH access restricted to your IP
- Save the .pem key file securely (NOT in cloud-synced folders)

### Step 2: Connect OpenRouter
- One API key that works with many model providers
- Start with a fast, affordable model for agent-style tasks
- Easy to switch models as they improve

### Step 3: Connect Telegram
- Create a Telegram bot using @BotFather
- Agent becomes accessible from your phone anywhere
- Agent can also message you proactively

### Step 4: Define the Agent's Identity
- SOUL.md: Who the agent is, how it communicates, values and boundaries
- USER.md: Who you are, your role, context, timezone, preferences
- AGENTS.md: Operational rules, defaults, system guidance

For CRE professionals: define market focus, property types, summary preferences, tasks to perform, tools to use.

### Step 5: Start Simple, Then Expand Carefully
Start with: chat via Telegram, answering questions, summarizing notes, structuring recurring tasks.
Then expand: web search, file access, APIs, calendar, email, scheduled tasks.

## Next Step: Census API

Connect agent to US Census API for radius-based demographic and market data relevant to CRE.

## Guardrails
- Review any skill or plugin before installing
- Set spending limits on AWS, OpenRouter, and external services
- Check logs and behavior regularly
- Keep services locked down - this is still infrastructure
