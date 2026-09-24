# Token Watching
 
**Real-time prompt cost optimization, built into the everyday tools you already use.**
 
Token Watching is a browser extension that lives in your browser and supports you as you prompt. Using a 3-agent pipeline, 
it shows real-time token cost and offers an optimized rewrite of your prompt before you even hit enter.
 
---

 ## Team
 
| Name | Role |
|---|---|
| Islam Asous | Agents & Orchestrator |
| Maida Kucevic | API & Data Layer (routes, DB, cost calc) |
| Vincenzo Monterosso | Integration & Infra (CORS, deployment, testing, error handling, user auth) |
| Alejandro Moya Ramirez | Frontend (extension popup UI/UX) & Data Analysis |

---

## The Problem
 
With the fast emergence of AI Engineering, proper prompting is more important than ever. As teams adopt LLMs at scale, 
poorly written prompts burn through tokens, which in turn burns through the budget. Most teams have no visibility into which prompts are wasteful, 
no way to catch it in the moment, and no easy way to fix it without slowing people down.
 
## The Solution
 
Token Watching sits on top of the AI tools people already use (ChatGPT, Claude.ai), watches prompts as they're typed, and runs them through a 3-agent pipeline to:
 
1. Calculate real-time token cost
2. Rewrite the prompt to be more efficient
3. Validate that the optimized version still produces comparable output quality
The result: fewer wasted tokens, lower cost, and a better prompt every time.
 
---
 
## How It Works
 
```
User types a prompt
        │
        ▼
  Content Script (detects prompt in ChatGPT/Claude.ai)
        │
        ▼
  Background Service Worker
        │
        ▼
  Backend Orchestrator
        │
    ┌───┴────┬─────────┐
    ▼        ▼         ▼
 Agent 1   Agent 2   Agent 3
 Auditor   Optimizer Validator
    │        │         │
    └───┬────┴─────────┘
        ▼
   Saved to DB → shown in Extension Popup + Dashboard
```
 
### The Agents
 
| Agent | Role |
|---|---|
| **1. The Auditor** | Counts tokens, calculates cost, flags waste patterns (redundancy, verbosity, unnecessary context) |
| **2. The Optimizer** | Rewrites the prompt to cut tokens while preserving intent |
| **3. The Validator** | Compares original vs. optimized output quality to confirm nothing was lost |
 
### The Orchestrator
 
A lightweight pipeline controller that sequences the agents, passes state between them, handles errors/retries, and streams live status updates to the UI.
 
---
 
## Project Structure
 
```
TokenWatching/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml            # Lint, tests, dashboard build, extension packaging (PRs + main)
│   │   └── release.yml       # Tag v* → validates version, publishes GitHub Release with extension zip
│   └── dependabot.yml        # Weekly dependency update PRs (pip, npm, Actions)
│
├── agents/                   # Agent pipeline (Python)
│   ├── auditor.py            # Agent 1: token count, cost estimate, waste issues, severity
│   ├── optimizer.py          # Agent 2: prompt rewriting (in progress)
│   ├── testing_agent.py      # Scratch script for testing the Anthropic API connection
│   └── readme.md             # Agents progress log (decisions, bugs, fixes)
│
├── tests/
│   └── test_auditor.py       # Offline unit tests for the Auditor (no API key needed)
│
├── scripts/
│   └── package_extension.py  # Validates manifest.json and zips the extension files
│
├── config/
│   └── prices.yaml           # Model pricing (to be wired into cost estimates)
│
├── dashboard/                # Web dashboard: React + TypeScript (Vite), Clerk auth
│   └── src/
│
├── manifest.json             # Chrome extension manifest (MV3)
├── hello.html                # Extension popup (placeholder)
├── hello_extensions.png      # Extension icon
│
├── requirements.txt          # Runtime Python deps
├── requirements-dev.txt      # + pylint, pytest
├── pylintrc.toml             # Pylint config (CI fails below fail-under score)
├── pytest.ini                # Pytest config (tests import from agents/)
└── README.md
```
 
## Dependency Updates (Dependabot)
 
[Dependabot](https://docs.github.com/en/code-security/dependabot) checks weekly for newer versions of our dependencies and opens a PR for each update, including release notes. CI runs on these PRs like any other, so a breaking upgrade shows up before it's merged.
 
| Ecosystem | Directory | Notes |
|---|---|---|
| pip | `/` | Python packages in `requirements*.txt` |
| npm | `/dashboard` | All dashboard updates grouped into a single `dashboard-deps` PR |
| GitHub Actions | `/` | Action versions in `.github/workflows/` (e.g. `actions/checkout`) |
 
Configured in [`.github/dependabot.yml`](.github/dependabot.yml). Review and merge these PRs like any other. Staying current keeps us off versions with known vulnerabilities and avoids a large catch-up upgrade later.
 
## Tech Stack
 
- **Backend:** FastAPI (Python), `tiktoken`, Anthropic/OpenAI SDK
- **Extension:** Manifest V3, JavaScript/React (popup)
- **Deployment:** Railway/Render (backend), Vercel (dashboard)
  
- **Future Goals**
  - **Dashboard:** React (Vite), Tailwind, Recharts
    - **Database:** SQLite (dev) → Postgres (production path)
---
