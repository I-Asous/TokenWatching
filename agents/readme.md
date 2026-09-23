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
- No test file yet (`tests/test_auditor.py`) — currently only tested manually via the `if __name__ == "__main__":` block


## Agent 2 — Optimizer (`auditor.py`)

### Status: beginning to work on it now(9/23/2026)