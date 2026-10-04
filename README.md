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
  Content Script (reads the prompt box in ChatGPT)
        │
        ▼
  Extension Popup (React)
        │
        ▼
  Orchestrator: runPipeline(prompt, target)
        │
        ▼
  Agent 1: Auditor ── no issues ──► original prompt returned unchanged
        │ issues found
        ▼
  Agent 2: Optimizer ◄──────────────────────┐
        │ rewrite saves tokens              │ rejected rewrite + reason
        ▼                                   │ (up to 3 attempts)
  Agent 3: Validator ── fails ──────────────┘
        │ passes
        ▼
  Optimized prompt + tokens saved
        │
        ▼
  Backend API (FastAPI) → Supabase → Extension Popup + Dashboard
```

This is the intended end-to-end flow. The agent pipeline and the backend API each work on their own today, but are not connected to each other or to the popup yet; see [Current Status](#current-status).

The pipeline fails closed: if no rewrite passes validation within the retry budget, the user keeps their original prompt. A rewrite the Validator rejected is never shown, even if it would have saved tokens.

### The Agents

| Agent                      | Role                                                                                                                                              |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1. The Auditor**   | Counts tokens, estimates cost, and flags waste (filler and politeness words, extra blank lines, high token-to-word ratio). Long prompts with no rule hits get an LLM review. |
| **2. The Optimizer** | Rewrites the prompt to cut tokens while preserving intent. Returns a structured reply: the constraints it must keep, the rewrite, and a list of changes. Leaves already-concise prompts unchanged. |
| **3. The Validator** | Compares the original and the rewrite step by step (Read, Answer, Cite, Think), then gives a 1-10 score and a pass/fail verdict.                   |

### The Orchestrator

`agents/orchestrator.py` sequences the agents and passes state between them. When the Validator rejects a rewrite, the Orchestrator retries the Optimizer with every rejected rewrite and the Validator's reason, so each attempt sees what the previous one broke. It stops early when a rewrite passes or saves no tokens.

### Token Counting

`agents/tokens.py` counts tokens the way the LLM the user is prompting would, so the savings shown match what they are billed:

| Target      | How tokens are counted                                                                     |
| ----------- | ------------------------------------------------------------------------------------------ |
| `chatgpt` | Locally with `tiktoken` (`o200k_base`). This is the default.                               |
| `claude`  | Anthropic's `count_tokens` endpoint, falling back to the local estimate if the call fails. |

---

## Current Status

**Done**

- All three agents and the Orchestrator, with the retry loop and validator feedback.
- Target-aware token counting for ChatGPT and Claude, with cached results.
- Optimizer hardening: structured outputs, a cached system prompt with worked examples, and rules that protect code, URLs, numbers, negations and the prompt's language.
- Offline unit tests for every agent module (63 tests, no API key needed), plus a live Validator suite.
- Backend API: FastAPI routes for users, prompts, optimized prompts, and the combined prompt-with-optimized view, stored in Supabase.
- Extension popup: Clerk sign-in and sign-up (including Google), and a tabbed layout with Stats, Enter Prompt and History.
- Content script that reads the prompt box in ChatGPT and passes the text to the popup.
- CI (lint, tests, dashboard build, extension packaging), tagged releases, and Dependabot.

**Not yet done**

- The backend does not call the agent pipeline yet. `runPipeline` runs on its own (see below), and the API only stores and returns prompts.
- The popup does not send prompts to the backend. The Stats tab shows sample data and the History tab is a placeholder.
- The content script supports ChatGPT only; Claude.ai is not detected yet.
- `config/prices.yaml` is not wired into cost estimates. The Auditor uses a fixed rate of $3 per million tokens.

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
│   ├── orchestrator.py         # runPipeline(): Auditor → Optimizer → Validator, with retries and fail-closed fallback
│   ├── auditor.py              # Agent 1: token count, cost estimate, waste issues, severity
│   ├── optimizer.py            # Agent 2: structured rewrite that cuts tokens, reports tokens/percent saved
│   ├── validator.py            # Agent 3: step-by-step check that the rewrite preserves intent (score 1-10, pass/fail)
│   ├── tokens.py               # Token counting per target LLM (tiktoken for ChatGPT, count_tokens for Claude)
│   ├── testing_agent.py        # Scratch script for testing the Anthropic API connection
│   └── readme.md               # Agents progress log (decisions, bugs, fixes)
│
├── backend/                    # REST API (FastAPI + Supabase)
│   ├── main.py                 # FastAPI app, mounts the router
│   ├── routes/                 # HTTP endpoints
│   │   ├── endpoints.py        # Combines the routers below
│   │   ├── users.py            # Create, update, delete users
│   │   ├── prompts.py          # Submit, list, read, delete original prompts
│   │   ├── optimized_prompts.py    # Save and read optimized prompts
│   │   └── prompt_w_optimized.py   # Read original and optimized prompts side by side
│   ├── repository/             # Supabase queries, one file per resource
│   │   └── client.py           # Supabase client (reads SUPABASE_URL / SUPABASE_KEY from .env)
│   └── schema/                 # Pydantic request and response models, one file per resource
│
├── tests/
│   ├── test_auditor.py         # Offline unit tests for the Auditor (no API key needed)
│   ├── test_optimizer.py       # Offline unit tests for the Optimizer (fake Anthropic client)
│   ├── test_validator.py       # Offline unit tests for the Validator (fake Anthropic client)
│   ├── test_orchestrator.py    # Offline unit tests for the pipeline and retry loop (fake agents)
│   ├── test_tokens.py          # Offline unit tests for token counting
│   └── test_validator_live.py  # Live Validator tests (marked `live`, skipped by default)
│
├── src/                        # Extension popup: React + TypeScript
│   ├── main.tsx                # Entry point, ClerkProvider setup and theming
│   ├── App.tsx                 # Sign-in / sign-up, Google login hand-off, tab switching
│   ├── components/
│   │   └── Navbar.tsx          # Stats / Enter Prompt / History tabs
│   ├── pages/
│   │   ├── Chatbox.tsx         # Enter Prompt tab, prefilled from the ChatGPT prompt box
│   │   ├── Stats.tsx           # Token charts (Chart.js, sample data for now)
│   │   ├── History.tsx         # Prompt history (placeholder)
│   │   └── Login.tsx           # Earlier hand-built login form (not used; Clerk handles sign-in)
│   └── style.css               # Popup styles
│
├── content.ts                  # Content script: reads the ChatGPT prompt box and sends the text to the popup
├── index.html                  # Extension popup HTML (mounts src/main.tsx)
├── manifest.json               # Chrome extension manifest (MV3)
├── vite.config.ts              # Vite build for the extension (@crxjs/vite-plugin)
├── package.json                # Extension JS deps (React, Clerk, Chart.js, Vite)
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
├── requirements.txt            # Runtime Python deps (anthropic, pydantic, tiktoken, python-dotenv, fastapi, supabase)
├── requirements-dev.txt        # + pylint, pytest
├── pylintrc.toml               # Pylint config (CI fails below fail-under score)
├── pytest.ini                  # Pytest config (skips `live` tests unless run with -m live)
└── README.md
```

---

## Getting Started

### Environment variables

Create a `.env` file in the project root:

| Variable                       | Used by                                    |
| ------------------------------ | ------------------------------------------ |
| `ANTHROPIC_API_KEY`          | Agents (Claude calls and token counting)   |
| `SUPABASE_URL`               | Backend                                    |
| `SUPABASE_KEY`               | Backend                                    |
| `VITE_CLERK_PUBLISHABLE_KEY` | Extension popup                            |
| `VITE_CLERK_SYNC_HOST`       | Extension popup (Google login hand-off)    |

The agents read `ANTHROPIC_API_KEY` from the environment and do not load `.env` themselves, so export it in your shell before running them.

### Running the agent pipeline

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python -m agents.orchestrator   # full pipeline on a sample prompt
python -m agents.optimizer      # optimizer against its built-in edge cases
```

### Running the backend

```bash
cd backend
fastapi dev main.py             # http://localhost:8000, API docs at /docs
```

### Running the extension

```bash
npm install
npm run build                   # output in dist/, load it unpacked at chrome://extensions
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

- **Agents:** Python 3.12+, Anthropic SDK with Claude Sonnet 5.5 (Optimizer, Claude token counting) and Claude Sonnet 4.6 (Auditor review, Validator), Pydantic structured outputs, prompt caching, `tiktoken`
- **Backend:** FastAPI, Supabase (Postgres), Pydantic, `python-dotenv`
- **Extension:** Chrome Manifest V3, React 19 + TypeScript popup, Chart.js, built with Vite + `@crxjs/vite-plugin`
- **Auth:** Clerk (`@clerk/chrome-extension` in the extension, `@clerk/react` in the dashboard)
- **Dashboard:** React 19 + TypeScript (Vite), linted with oxlint
- **Testing & CI:** pytest (offline + live suites), pylint, GitHub Actions, Dependabot
- **Future Goals**

  - **Backend:** endpoint that runs the agent pipeline and saves the result
  - **Extension:** Claude.ai prompt detection, live data in Stats and History
  - **Dashboard:** Tailwind, Recharts
  - **Deployment:** Railway/Render (backend), Vercel (dashboard)

---
