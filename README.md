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
  Backend Orchestrator (runPipeline)
        │
        ▼
  Agent 1: Auditor ──── no issues ────► original prompt returned
        │ issues
        ▼
  Agent 2: Optimizer ◄────────────────────┐
        │ rewrite                         │ rejected: the reasons are fed back
        ▼                                 │ (up to 3 attempts, then the
  Lock check (local, free) ── broken ─────┤  original prompt is returned)
        │ every lock kept                 │
        ▼                                 │
  Agent 3: Validator ──────── fail ───────┘
        │ pass
        ▼
   Saved to DB → shown in Extension Popup + Dashboard
```

### The Agents

| Agent                      | Role                                                                                                                                                                                                                                                                                       |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **1. The Auditor**   | Counts tokens for the target LLM, estimates cost, and flags waste. Rule checks first (filler words, extra blank lines, token-to-word ratio, readability with textstat, adverb padding and repeated sentences with spaCy), then a Claude Haiku review for long prompts the rules don't flag |
| **2. The Optimizer** | Rewrites the prompt to cut tokens while preserving intent. On a retry it sees each rejected rewrite and why it was rejected                                                                                                                                                                |
| **3. The Validator** | Compares the original and the rewrite and scores whether intent and requirements were preserved (1-10, pass at 6+)                                                                                                                                                                         |

### The Lock Check

A free, local check (`agents/locks.py`) that runs between the Optimizer and the Validator. It finds what a rewrite must keep: code blocks, inline code, URLs, rules (sentences with *must*, *never*, *always*, *do not*...) and numbered steps, and rejects any rewrite that drops or changes one, without paying for a Validator call. The exact reasons (e.g. `constraint dropped: "Always use parameterized queries..."`) go back to the Optimizer for its next attempt. A rule may be shortened (the explanation after "to prevent" or "because" can go), but negative rules must stay negative.

### The Orchestrator

A lightweight pipeline controller (`agents/orchestrator.py`) that sequences the agents, runs the lock check, passes rejection reasons back to the Optimizer, and returns the original prompt if no rewrite passes within the retry limit.

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
│   ├── auditor.py              # Agent 1: token count, cost estimate, waste issues (rules, textstat, spaCy, Haiku review), severity
│   ├── optimizer.py            # Agent 2: rewrites the prompt to cut tokens, reports tokens/percent saved
│   ├── validator.py            # Agent 3: ReAcT-structured check that the rewrite preserves intent (score 1-10, pass/fail)
│   ├── locks.py                # Local lock check: rejects rewrites that drop code, URLs, rules or steps
│   ├── orchestrator.py         # runPipeline(): Auditor → Optimizer → lock check → Validator, with retries
│   ├── tokens.py               # Shared token counting per target LLM (tiktoken / Claude count_tokens)
│   ├── testing_agent.py        # Scratch script for testing the Anthropic API connection
│   └── readme.md               # Agents progress log (decisions, bugs, fixes)
│
├── tests/
│   ├── test_auditor.py         # Offline unit tests for the Auditor (no API key needed)
│   ├── test_optimizer.py       # Offline unit tests for the Optimizer (fake Anthropic client)
│   ├── test_validator.py       # Offline unit tests for the Validator (fake Anthropic client)
│   ├── test_locks.py           # Offline unit tests for the lock check (with and without the spaCy model)
│   ├── test_orchestrator.py    # Offline pipeline tests with fake agents
│   ├── test_tokens.py          # Offline token counting tests
│   ├── test_cors.py            # Backend CORS tests
│   └── test_validator_live.py  # Live Validator tests (marked `live`, skipped by default)
│
├── extension/                  # Chrome extension (MV3): React + TypeScript popup, built with Vite + @crxjs/vite-plugin
│   ├── manifest.json           # Extension manifest
│   ├── index.html              # Popup HTML (mounts src/main.tsx)
│   └── src/
│       ├── main.tsx            # Entry point, ClerkProvider setup and theming
│       ├── App.tsx             # Popup views
│       ├── api.ts              # Calls to the backend (sends the Clerk token)
│       ├── content.ts          # Content script injected into ChatGPT / Claude.ai (prompt box detection)
│       ├── pages/              # Chatbox, History, Login, Stats
│       └── components/         # Navbar
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
├── backend/                    # FastAPI API: routes, Supabase repository, Pydantic schemas
│   ├── main.py                 # App entry point (uvicorn main:app)
│   ├── auth.py                 # Clerk token verification
│   ├── routes/ repository/ schema/ service/
│
├── .env                        # Local secrets (API keys), never committed
│
├── Dockerfile                  # Container image for the backend (Python 3.13, uvicorn, non-root user)
├── .dockerignore               # Keeps secrets, extension, dashboard and node_modules out of the image
│
├── requirements.txt            # Runtime Python deps (anthropic, tiktoken, spacy, textstat, fastapi, supabase...)
├── requirements-dev.txt        # + pylint, pytest
├── pylintrc.toml               # Pylint config (CI fails below fail-under score)
├── pytest.ini                  # Pytest config (skips `live` tests unless run with -m live)
└── README.md
```

### Running the tests

```bash
pip install -r requirements-dev.txt
python -m spacy download en_core_web_sm   # English model for the Auditor and lock check
python -m nltk.downloader cmudict         # word list textstat uses to count syllables
pytest              # offline unit tests only
pytest -m live      # live Validator tests (needs ANTHROPIC_API_KEY)
```

Without the spaCy model or `cmudict`, those checks are skipped with a warning and their tests are skipped, so the rest still runs. On macOS with the python.org Python, run `Install Certificates.command` (in the Python folder under Applications) first, or the `cmudict` download fails with `CERTIFICATE_VERIFY_FAILED`.

To run an agent file on its own, run it as a module from the repo root (e.g. `python -m agents.locks`). Running the file directly (`python agents/locks.py`) fails with `No module named 'agents'`.

## Dependency Updates (Dependabot)

[Dependabot](https://docs.github.com/en/code-security/dependabot) checks weekly for newer versions of our dependencies and opens a PR for each update, including release notes. CI runs on these PRs like any other, so a breaking upgrade shows up before it's merged.

| Ecosystem      | Directory      | Notes                                                                |
| -------------- | -------------- | -------------------------------------------------------------------- |
| pip            | `/`          | Python packages in`requirements*.txt`                              |
| npm            | `/dashboard` | All dashboard updates grouped into a single`dashboard-deps` PR     |
| GitHub Actions | `/`          | Action versions in`.github/workflows/` (e.g. `actions/checkout`) |

Configured in [`.github/dependabot.yml`](.github/dependabot.yml). Review and merge these PRs like any other. Staying current keeps us off versions with known vulnerabilities and avoids a large catch-up upgrade later.

## Tech Stack

- **Agents:** Python 3.12+, Anthropic SDK (Claude Haiku 5.5 for the Auditor's review, Claude Sonnet 5.5 for the Optimizer, Claude Sonnet 4.6 for the Validator), `tiktoken` and Claude's `count_tokens` for token counting, spaCy and textstat for the rule-based checks, `python-dotenv`
- **Backend:** FastAPI serving the agent pipeline, Supabase (Postgres), Clerk token verification
- **Extension:** Chrome Manifest V3, React 19 + TypeScript popup, built with Vite + `@crxjs/vite-plugin`
- **Auth:** Clerk (`@clerk/chrome-extension` in the extension, `@clerk/react` in the dashboard)
- **Dashboard:** React 19 + TypeScript (Vite), linted with oxlint
- **Testing & CI:** pytest (offline + live suites), pylint, GitHub Actions, Dependabot
- **Future Goals**

  - **Dashboard:** Tailwind, Recharts
  - **Deployment:** Railway/Render (backend), Vercel (dashboard)

---
