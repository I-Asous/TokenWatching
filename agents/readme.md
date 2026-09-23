# Agents — Progress Log
 
This README tracks what's been built in `agents/`, why specific decisions were made, and bugs encountered along the way (and how they were fixed). Keep this updated as agents are built — it doubles as documentation for the team and as notes for the final write-up.
 
---
 
## Agent 1 — Auditor (`auditor.py`)
 
### Status: Core logic is now working (9/23/2026)
 
### What it does
Takes a single user-submitted prompt and returns:
- Token count (via `tiktoken`, `cl100k_base` encoding)
- Estimated dollar cost (placeholder flat rate — will connect to `pricing.yaml` once `config/` is created)
- A list of flagged waste issues (rule-based checks, escalates to an LLM review only when the prompt is long and no rule-based issues were actually found)
- A severity rating (`Low` / `Medium` / `High`)
### Design decisions
- **Tiered analysis (rule-based first, LLM only when needed):** since Agent 1's whole job is flagging wasted tokens, it shouldn't itself waste tokens doing so itself. Cheaper, deterministic checks run first (token-to-word ratio, filler word count, excessive blank lines). The LLM review only fires if the prompt is long (> 500 tokens) and none of the rule-based checks caught anything ie there might be subtler issues.
- **Plain functions, not a class:** originally tried wrapping everything in a `@dataclass class Auditor` with methods... reverted this. None of the functions need shared state (so no `self.something` is used across calls), thus plain top-level functions are simpler and match how the orchestrator will call this file later (`from agents.auditor import auditPrompt`).
- **`AuditResult` is a separate dataclass, data only:** keeps the "what data comes back" separate from "how it's calculated". Overall its just cleaner to reason about and test.

### Bugs encountered + fixes
| Bug | Cause | Fix |
|---|---|---|
| `NameError: name 'AuditResult' is not defined` | Function return type was annotated `-> AuditResult`, but the dataclass was actually named `Auditor` at the time (naming mismatch from an earlier refactor) | Renamed the dataclass to `AuditResult`, defined it before any function references it |
| `TypeError: AuditResult.__init__() got an unexpected keyword argument 'severity'` | `auditPrompt()` was updated to pass `severity=severity` into `AuditResult(...)`, but the `AuditResult` dataclass definition hadn't been updated to include a `severity` field yet so edits were made in one place but not the other | Added `severity: str = "Low"` as a field on `AuditResult` |
| Would-be `ZeroDivisionError` on empty prompt input | `if word_count > 0 or (token_count / word_count) > 1:` — used `or` instead of `and`. With `or`, Python still evaluates the division even when `word_count` is 0, since the check doesn't short-circuit the way `and` does | Changed `or` → `and`. Now if `word_count` is 0, Python short-circuits and never evaluates the division — no crash, and the ratio check also works correctly (previously `or` made the condition nearly always `True`, so the check wasn't really filtering anything) |
| Would-be `NameError: name 'llm_review' is not defined` | `auditPrompt()` called `llm_review(prompt)` (snake_case), but the function was actually defined as `llmReview` (camelCase) — naming drift between edits | Corrected the call site to `llmReview(prompt)`, matching the actual function name |
 
### Known limitations / things to revisit
- Cost estimate uses a flat hardcoded rate, needs to connect to `config/pricing.yaml` once that file and `services/cost_calculator.py` exist
- Token counts are `tiktoken`-based estimates, not exact for Claude models (Anthropic doesn't expose a public tokenizer) — Note. worth stating this explicitly in the final pitch
- Naming convention is currently a mix of `camelCase` and `snake_case`,  worth standardizing (team decision) before this gets much bigger
- **Open bug: token-to-word ratio check over-flags.** `runRuleCheck()` flags any prompt with more than 1 token per word, but normal English averages ~1.3 tokens/word, so almost every prompt gets flagged as "too verbose" (e.g. `"What is the capital of France?"` → 7 tokens / 6 words → flagged). Knock-on effect: nearly every prompt has at least 1 issue, so severity is almost never `Low`. Likely fix is raising the threshold to ~1.5–2 (to be decided). Tracked by an `xfail` test in `tests/test_auditor.py`, which will start failing on purpose once this is fixed, as a reminder to remove the `xfail` marker
- `llmReview()` isn't covered by tests yet, since it needs an API key and real API calls (would need mocking)

### Tests (`tests/test_auditor.py`)
Offline unit tests. They need no API key and never call Claude. Run from the repo root with `pytest` (the settings in `pytest.ini` let tests `import auditor` directly).
| Test | Checks |
|---|---|
| `test_countTokens_counts_nonempty_text` | Non-empty text gives > 0 tokens, empty string gives 0 |
| `test_estimateCost_scales_with_tokens` | Cost is 0 for 0 tokens and scales with token count |
| `test_runRuleCheck_flags_filler_words_and_blank_lines` | Filler words and `\n\n\n` are both flagged |
| `test_runRuleCheck_clean_prompt_has_no_issues` | A short, direct prompt has no issues (**expected to fail for now**, see the ratio bug above) |
| `test_determineSeverity_thresholds` | Low/Medium/High boundaries (300/800 tokens, 1/3 issues) |


## Agent 2 — Optimizer (`optimizer.py`)

### Status: beginning to work on it now(9/23/2026)


---

## CI/CD (9/23/2026)
Replaced the old pylint-only workflow (which was failing on every PR at a 5.61/10 score) with a full pipeline. Details for the agents side:
- **CI (`.github/workflows/ci.yml`)** runs on every PR and push to `main`: pylint + `pytest` on Python 3.12/3.13/3.14, plus separate jobs for the dashboard (lint + build) and the extension (manifest check + zip packaging)
- **Pylint gate:** `pylintrc.toml` now sets `fail-under = 8.0`, so CI passes today but fails if code quality drops. Raise this as the existing warnings in `auditor.py` are cleaned up (missing docstrings, trailing whitespace, and the `"""..."""` comment blocks above functions, which pylint flags as `pointless-string-statement`. Moving them *inside* the function as docstrings fixes both)
- **Dev dependencies:** `pip install -r requirements-dev.txt` installs the runtime deps plus `pylint` and `pytest`
- **Releases:** bump `version` in `manifest.json`, then push a matching tag (`git tag v1.1 && git push origin v1.1`), and a GitHub Release with the extension zip is created automatically

