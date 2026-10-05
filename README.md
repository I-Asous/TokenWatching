# Token Watching

**Real-time prompt cost optimization, built into the everyday tools you already use.**

Token Watching is a browser extension that lives in your browser and supports you as you prompt. Using a 3-agent pipeline,
it shows real-time token cost and offers an optimized rewrite of your prompt before you even hit enter.

---

## Team

| Name                   | Role                                                                       |
| ---------------------- | -------------------------------------------------------------------------- |
| Islam Asous            | Agents & Orchestrator                                                      |
| Maida Kucevic          | API & Data Layer (routes, DB, cost calc)                                   |
| Vincenzo Monterosso    | Integration & Infra (CORS, deployment, testing, error handling, user auth) |
| Alejandro Moya Ramirez | Frontend (extension popup UI/UX) & Data Analysis                           |

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

| Agent                      | Role                                                                                              |
| -------------------------- | ------------------------------------------------------------------------------------------------- |
| **1. The Auditor**   | Counts tokens, calculates cost, flags waste patterns (redundancy, verbosity, unnecessary context) |
| **2. The Optimizer** | Rewrites the prompt to cut tokens while preserving intent                                         |
| **3. The Validator** | Compares original vs. optimized output quality to confirm nothing was lost                        |

### The Orchestrator

A lightweight pipeline controller that sequences the agents, passes state between them, handles errors/retries, and streams live status updates to the UI.

---

## Project Structure

```
TokenWatching/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml              # Lint, tests, dashboard build, extension packaging (PRs + main)
│   │   ├── release.yml         # Tag v* → validates version, publishes GitHub Release with extension zip
│   │   └── validator-live.yml  # Live Validator tests against the real Claude API (manual / on main)
│   └── dependabot.yml          # Weekly dependency update PRs (pip, npm, Actions)
│
├── agents/                     # Agent pipeline (Python)
│   ├── auditor.py              # Agent 1: token count, cost estimate, waste issues, severity
│   ├── optimizer.py            # Agent 2: rewrites the prompt to cut tokens, reports tokens/percent saved
│   ├── validator.py            # Agent 3: ReAcT-structured check that the rewrite preserves intent (score 1-10, pass/fail)
│   ├── testing_agent.py        # Scratch script for testing the Anthropic API connection
│   └── readme.md               # Agents progress log (decisions, bugs, fixes)
│
├── tests/
│   ├── test_auditor.py         # Offline unit tests for the Auditor (no API key needed)
│   ├── test_optimizer.py       # Offline unit tests for the Optimizer (fake Anthropic client)
│   ├── test_validator.py       # Offline unit tests for the Validator (fake Anthropic client)
│   └── test_validator_live.py  # Live Validator tests (marked `live`, skipped by default)
│
├── src/                        # Extension popup: React + TypeScript
│   ├── main.tsx                # Entry point, ClerkProvider setup and theming
│   ├── App.tsx                 # Sign-in / sign-up / signed-in views
│   └── style.css               # Popup styles
│
├── content.ts                  # Content script injected into ChatGPT (prompt box detection, in progress)
├── index.html                  # Extension popup HTML (mounts src/main.tsx)
├── manifest.json               # Chrome extension manifest (MV3)
├── vite.config.ts              # Vite build for the extension (@crxjs/vite-plugin)
├── package.json                # Extension JS deps (React, Clerk, Vite)
├── tsconfig.json               # TypeScript config for the extension
├── Token_Watching_Logo.png     # Extension icon
│
├── dashboard/                  # Web dashboard: React + TypeScript (Vite), Clerk auth
│   └── src/
│
├── scripts/
│   └── package_extension.py    # Validates manifest.json and zips the extension files
│
├── config/
│   └── prices.yaml             # Per-model pricing and modifiers (to be wired into cost estimates)
│
├── requirements.txt            # Runtime Python deps (anthropic, tiktoken, python-dotenv)
├── requirements-dev.txt        # + pylint, pytest
├── pylintrc.toml               # Pylint config (CI fails below fail-under score)
├── pytest.ini                  # Pytest config (skips `live` tests unless run with -m live)
└── README.md
```

### Running the tests

```bash
pip install -r requirements-dev.txt
pytest              # offline unit tests only
pytest -m live      # live Validator tests (needs ANTHROPIC_API_KEY)
```

## Dependency Updates (Dependabot)

[Dependabot](https://docs.github.com/en/code-security/dependabot) checks weekly for newer versions of our dependencies and opens a PR for each update, including release notes. CI runs on these PRs like any other, so a breaking upgrade shows up before it's merged.

| Ecosystem      | Directory      | Notes                                                                |
| -------------- | -------------- | -------------------------------------------------------------------- |
| pip            | `/`          | Python packages in`requirements*.txt`                              |
| npm            | `/dashboard` | All dashboard updates grouped into a single`dashboard-deps` PR     |
| GitHub Actions | `/`          | Action versions in`.github/workflows/` (e.g. `actions/checkout`) |

Configured in [`.github/dependabot.yml`](.github/dependabot.yml). Review and merge these PRs like any other. Staying current keeps us off versions with known vulnerabilities and avoids a large catch-up upgrade later.

## Tech Stack

- **Agents:** Python 3.12+, Anthropic SDK (Claude Sonnet 4.6), `tiktoken` for token counting, `python-dotenv`
- **Extension:** Chrome Manifest V3, React 19 + TypeScript popup, built with Vite + `@crxjs/vite-plugin`
- **Auth:** Clerk (`@clerk/chrome-extension` in the extension, `@clerk/react` in the dashboard)
- **Dashboard:** React 19 + TypeScript (Vite), linted with oxlint
- **Testing & CI:** pytest (offline + live suites), pylint, GitHub Actions, Dependabot
- **Future Goals**

  - **Backend:** FastAPI orchestrator serving the agent pipeline
  - **Dashboard:** Tailwind, Recharts
  - **Database:** SQLite (dev) → Postgres (production path)
  - **Deployment:** Railway/Render (backend), Vercel (dashboard)

---
