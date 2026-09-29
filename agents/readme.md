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

### To test: pytest tests/test_auditor.py -v

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
- ~~Open bug: token-to-word ratio check over-flags~~ **Fixed.** The threshold was `> 1`, but normal English averages ~1.3 tokens/word, so almost every prompt got flagged (e.g. `"What is the capital of France?"` → 7 tokens / 6 words → flagged), and severity was almost never `Low`. Raised it to `> 1.6` (a bit above the ~1.3 average) and removed the `xfail` marker from the clean-prompt test. 1.6 is still a guess, so it's worth gathering real prompt data to tune it
- `llmReview()` isn't covered by tests yet, since it needs an API key and real API calls (would need mocking)

### Tests (`tests/test_auditor.py`)
Offline unit tests. They need no API key and never call Claude. Run from the repo root with `pytest` (the settings in `pytest.ini` let tests `import auditor` directly).
| Test | Checks |
|---|---|
| `test_countTokens_counts_nonempty_text` | Non-empty text gives > 0 tokens, empty string gives 0 |
| `test_estimateCost_scales_with_tokens` | Cost is 0 for 0 tokens and scales with token count |
| `test_runRuleCheck_flags_filler_words_and_blank_lines` | Filler words and `\n\n\n` are both flagged |
| `test_flags_excessive_blank_lines` | 2 newlines in a row are fine, 3+ get flagged |
| `test_runRuleCheck_clean_prompt_has_no_issues` | A short, direct prompt has no issues (passes now that the ratio bug is fixed) |
| `test_determineSeverity_thresholds` | Low/Medium/High boundaries (300/800 tokens, 1/3 issues) |


## CI/CD (9/23/2026)
Replaced the old pylint-only workflow (which was failing on every PR at a 5.61/10 score) with a full pipeline. Details for the agents side:
- **CI (`.github/workflows/ci.yml`)** runs on every PR and push to `main`: pylint + `pytest` on Python 3.12/3.13/3.14, plus separate jobs for the dashboard (lint + build) and the extension (manifest check + zip packaging)
- **Pylint gate:** `pylintrc.toml` now sets `fail-under = 8.0`, so CI passes today but fails if code quality drops. Raise this as the existing warnings in `auditor.py` are cleaned up (missing docstrings, trailing whitespace, and the `"""..."""` comment blocks above functions, which pylint flags as `pointless-string-statement`. Moving them *inside* the function as docstrings fixes both)
- **Dev dependencies:** `pip install -r requirements-dev.txt` installs the runtime deps plus `pylint` and `pytest`
- **Releases:** bump `version` in `manifest.json`, then push a matching tag (`git tag v1.1 && git push origin v1.1`), and a GitHub Release with the extension zip is created automatically


## Agent 2 — Optimizer (`optimizer.py`)

### Status: Core logic working, not wired into the orchestrator yet (9/24/2026)

### What it does
Takes a prompt (plus, optionally, the issues Agent 1 flagged) and returns an `OptimizationResult` with:
- The original and rewritten prompt
- Token counts for both (same `tiktoken` `cl100k_base` encoding as Agent 1, so the numbers are comparable)
- Tokens saved and percent saved

### To test: pytest tests/test_optimizer.py -v

`formatComparisonTable()` turns that result into a side-by-side table for the terminal/demo.

### Example
```python
from agents.auditor import auditPrompt
from agents.optimizer import optimizePrompt, formatComparisonTable

prompt = ("Please, could you kindly help me write a short story? I would really "
          "appreciate it if you could make it about a dragon. Thank you so much!")

audit = auditPrompt(prompt)                       # Agent 1
result = optimizePrompt(prompt, audit.issues)     # Agent 2 (calls Claude)
print(formatComparisonTable(result))
```
Output:
```
+-----------+--------------------------------------------------+--------+----------------+
|           | Prompt                                           | Tokens | Cost / 1K Runs |
+-----------+--------------------------------------------------+--------+----------------+
| Original  | Please, could you kindly help me write a short   | 31     | $0.093         |
|           | story? I would really appreciate it if you could |        |                |
|           | make it about a dragon. Thank you so much!       |        |                |
+-----------+--------------------------------------------------+--------+----------------+
| Optimized | Write a short story about a dragon.              | 8      | $0.024         |
+-----------+--------------------------------------------------+--------+----------------+
| Saved     | 74.19%                                           | 23     | $0.069         |
+-----------+--------------------------------------------------+--------+----------------+
```

### Design decisions
- **Agent 1's issues are passed into the rewrite:** `buildUserMessage()` lists them above the prompt ("Known issues found in prompt: ..."), so the LLM targets the actual problems instead of guessing. If there are no issues, the message is just the delimited prompt.
- **System prompt keeps meaning over length:** it removes filler and repetition but is told to keep examples, format requirements, constraints and edge cases, and to return an already-concise prompt unchanged. A shorter prompt that gives worse output isn't a saving.
- **One before/after example in the system prompt:** shows the model the expected style of rewrite without adding many tokens.
- **Same structure as Agent 1:** plain functions plus a data-only `OptimizationResult` dataclass, so the orchestrator can call `optimizePrompt()` the same way it calls `auditPrompt()`.
- **Reuses `estimateCost()` from Agent 1** for the table, instead of a second copy of the rate.

### Challenges + fixes
| Challenge | Cause | Fix |
|---|---|---|
| Cost column always showed `$0.000` | A single prompt costs a fraction of a cent, and `estimateCost()` rounds to 3 decimals | Table shows **cost per 1,000 runs** instead, which is also closer to how real apps pay (same prompt, many calls) |
| Negative "savings" | The LLM can return a rewrite that's *longer* than the original (e.g. for an already short prompt) | `tokensSaved = max(original - optimized, 0)`, so savings are never negative |
| `ZeroDivisionError` on empty prompt | `percentSaved` divides by `originalTokens` | Returns `0.0` when `originalTokens` is 0 (same kind of bug as the one in Agent 1) |
| Long prompts broke the table layout | A 500-word prompt made one very wide row | `textwrap` wraps the prompt column (default 50 chars); other cells are padded so every line has the same width |
| Testing without an API key / without spending tokens | `callOptimizerLLM()` makes a real Claude call | Tests swap the module's `client` for a fake one with `monkeypatch`. The fake records the request and returns a set reply, so we can check both what gets sent and how the result is handled |

### Known limitations / things to revisit
- Model is hardcoded (`claude-sonnet-4-6`), should move to config along with pricing
- No check that the LLM actually followed the rules. If it adds a preamble ("Here's your optimized prompt: ...") or drops a constraint, we'd still return it
- If the rewrite is longer, we report 0% saved but still return the longer prompt, when the original should be returned instead
- Same `tiktoken` estimate caveat as Agent 1
- Cost still uses Agent 1's flat placeholder rate

### Tests (`tests/test_optimizer.py`)
Offline, no API key needed (uses the fake client described above).
| Test | Checks |
|---|---|
| `test_countTokens_counts_nonempty_text` | Non-empty text gives > 0 tokens, empty string gives 0 |
| `test_buildUserMessage_without_issues` | No issues → message is just `PROMPT TO OPTIMIZE:\n<prompt>` |
| `test_buildUserMessage_with_issues` | Issues are listed as bullets before the prompt |
| `test_callOptimizerLLM_sends_system_prompt_and_strips` | The system prompt and issues are sent, and whitespace is stripped from the reply |
| `test_optimizePrompt_computes_savings` | Token counts, tokens saved and percent saved are correct |
| `test_optimizePrompt_never_negative` | A longer rewrite gives 0 saved, not a negative number |
| `test_optimizePrompt_empty_prompt` | Empty prompt doesn't divide by zero |
| `test_optimizePrompt_default_issues` | `issues` defaults to an empty list |
| `test_formatComparisonTable_contains_prompts_and_counts` | Both prompts, counts, percent and headers are in the table |
| `test_formatComparisonTable_wraps_long_prompts` | Long prompts wrap and every line has the same width |

Current result: `16 passed` across both test files.

---

## Next steps (with examples)

**1. Return the original when the rewrite isn't shorter.** Right now a longer rewrite still gets returned:
```python
if optimizedTokens >= originalTokens:
    optimizedPrompt, optimizedTokens = prompt, originalTokens
```

**2. Check the rewrite before returning it.** Catch the model breaking the "only return the prompt" rule, e.g.:
```python
if optimizedPrompt.lower().startswith(("here's", "here is", "optimized prompt")):
    ...  # retry once, or fall back to the original
```

**3. Create `config/pricing.yaml` + `services/cost_calculator.py`** so both agents use real per-model rates instead of the placeholder:
```yaml
claude-sonnet-4-6:
  input_per_million: 3.00
  output_per_million: 15.00
```

**4. Use exact Claude token counts where possible.** `testing_agent.py` already tries the API's token-counting endpoint, which could replace the `tiktoken` estimate (costs an API call, so maybe only for the final numbers):
```python
client.messages.count_tokens(model=MODEL, messages=[{"role": "user", "content": prompt}]).input_tokens
```

**5. Orchestrator:** one function that runs Agent 1 → Agent 2 and skips the LLM rewrite when there's nothing to fix (same "don't waste tokens to save tokens" idea as Agent 1):
```python
def run(prompt):
    audit = auditPrompt(prompt)
    if not audit.issues and audit.severity == "Low":
        return audit, None
    return audit, optimizePrompt(prompt, audit.issues)
```

**6. Cleanup (team decisions):** pick one naming convention (camelCase vs snake_case), move the `"""..."""` blocks above functions into docstrings to raise the pylint score, then bump `fail-under` above 8.0.
