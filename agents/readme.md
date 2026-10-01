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

| Bug                                                                                 | Cause                                                                                                                                                                                                                                         | Fix                                                                                                                                                                                                                                                                             |
| ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NameError: name 'AuditResult' is not defined`                                    | Function return type was annotated`-> AuditResult`, but the dataclass was actually named `Auditor` at the time (naming mismatch from an earlier refactor)                                                                                 | Renamed the dataclass to`AuditResult`, defined it before any function references it                                                                                                                                                                                           |
| `TypeError: AuditResult.__init__() got an unexpected keyword argument 'severity'` | `auditPrompt()` was updated to pass `severity=severity` into `AuditResult(...)`, but the `AuditResult` dataclass definition hadn't been updated to include a `severity` field yet so edits were made in one place but not the other | Added`severity: str = "Low"` as a field on `AuditResult`                                                                                                                                                                                                                    |
| Would-be`ZeroDivisionError` on empty prompt input                                 | `if word_count > 0 or (token_count / word_count) > 1:` — used `or` instead of `and`. With `or`, Python still evaluates the division even when `word_count` is 0, since the check doesn't short-circuit the way `and` does        | Changed`or` → `and`. Now if `word_count` is 0, Python short-circuits and never evaluates the division — no crash, and the ratio check also works correctly (previously `or` made the condition nearly always `True`, so the check wasn't really filtering anything) |
| Would-be`NameError: name 'llm_review' is not defined`                             | `auditPrompt()` called `llm_review(prompt)` (snake_case), but the function was actually defined as `llmReview` (camelCase) — naming drift between edits                                                                                | Corrected the call site to`llmReview(prompt)`, matching the actual function name                                                                                                                                                                                              |

### Known limitations / things to revisit

- Cost estimate uses a flat hardcoded rate, needs to connect to `config/pricing.yaml` once that file and `services/cost_calculator.py` exist
- Token counts are `tiktoken`-based estimates, not exact for Claude models (Anthropic doesn't expose a public tokenizer) — Note. worth stating this explicitly in the final pitch
- Naming convention is currently a mix of `camelCase` and `snake_case`,  worth standardizing (team decision) before this gets much bigger
- ~~Open bug: token-to-word ratio check over-flags~~ **Fixed.** The threshold was `> 1`, but normal English averages ~1.3 tokens/word, so almost every prompt got flagged (e.g. `"What is the capital of France?"` → 7 tokens / 6 words → flagged), and severity was almost never `Low`. Raised it to `> 1.6` (a bit above the ~1.3 average) and removed the `xfail` marker from the clean-prompt test. 1.6 is still a guess, so it's worth gathering real prompt data to tune it
- `llmReview()` isn't covered by tests yet, since it needs an API key and real API calls (would need mocking)

### Tests (`tests/test_auditor.py`)

Offline unit tests. They need no API key and never call Claude. Run from the repo root with `pytest` (the settings in `pytest.ini` let tests `import auditor` directly).

| Test                                                     | Checks                                                                        |
| -------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `test_countTokens_counts_nonempty_text`                | Non-empty text gives > 0 tokens, empty string gives 0                         |
| `test_estimateCost_scales_with_tokens`                 | Cost is 0 for 0 tokens and scales with token count                            |
| `test_runRuleCheck_flags_filler_words_and_blank_lines` | Filler words and`\n\n\n` are both flagged                                   |
| `test_flags_excessive_blank_lines`                     | 2 newlines in a row are fine, 3+ get flagged                                  |
| `test_runRuleCheck_clean_prompt_has_no_issues`         | A short, direct prompt has no issues (passes now that the ratio bug is fixed) |
| `test_determineSeverity_thresholds`                    | Low/Medium/High boundaries (300/800 tokens, 1/3 issues)                       |

## CI/CD (9/23/2026)

Replaced the old pylint-only workflow (which was failing on every PR at a 5.61/10 score) with a full pipeline. Details for the agents side:

- **CI (`.github/workflows/ci.yml`)** runs on every PR and push to `main`: pylint + `pytest` on Python 3.12/3.13/3.14, plus separate jobs for the dashboard (lint + build) and the extension (manifest check + zip packaging)
- **Pylint gate:** `pylintrc.toml` now sets `fail-under = 8.0`, so CI passes today but fails if code quality drops. Raise this as the existing warnings in `auditor.py` are cleaned up (missing docstrings, trailing whitespace, and the `"""..."""` comment blocks above functions, which pylint flags as `pointless-string-statement`. Moving them *inside* the function as docstrings fixes both)
- **Dev dependencies:** `pip install -r requirements-dev.txt` installs the runtime deps plus `pylint` and `pytest`
- **Validator (Agent 3):** `tests/test_validator.py` runs offline in CI with a fake client (same pattern as the optimizer tests). `tests/test_validator_live.py` calls the real API to check the validator still passes a filler-only rewrite and fails one that drops a constraint. These tests are marked `live`, are skipped by default (`pytest.ini` sets `-m "not live"`), and run in `.github/workflows/validator-live.yml` on manual dispatch or when `agents/validator.py` changes on `main`. That workflow needs the `ANTHROPIC_API_KEY` repo secret. To run them locally: `pytest -m live`
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

| Challenge                                            | Cause                                                                                              | Fix                                                                                                                                                                                            |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cost column always showed`$0.000`                  | A single prompt costs a fraction of a cent, and`estimateCost()` rounds to 3 decimals             | Table shows**cost per 1,000 runs** instead, which is also closer to how real apps pay (same prompt, many calls)                                                                          |
| Negative "savings"                                   | The LLM can return a rewrite that's*longer* than the original (e.g. for an already short prompt) | `tokensSaved = max(original - optimized, 0)`, so savings are never negative                                                                                                                  |
| `ZeroDivisionError` on empty prompt                | `percentSaved` divides by `originalTokens`                                                     | Returns`0.0` when `originalTokens` is 0 (same kind of bug as the one in Agent 1)                                                                                                           |
| Long prompts broke the table layout                  | A 500-word prompt made one very wide row                                                           | `textwrap` wraps the prompt column (default 50 chars); other cells are padded so every line has the same width                                                                               |
| Testing without an API key / without spending tokens | `callOptimizerLLM()` makes a real Claude call                                                    | Tests swap the module's`client` for a fake one with `monkeypatch`. The fake records the request and returns a set reply, so we can check both what gets sent and how the result is handled |

### Known limitations / things to revisit

- Model is hardcoded (`claude-sonnet-4-6`), should move to config along with pricing
- No check that the LLM actually followed the rules. If it adds a preamble ("Here's your optimized prompt: ...") or drops a constraint, we'd still return it
- If the rewrite is longer, we report 0% saved but still return the longer prompt, when the original should be returned instead
- Same `tiktoken` estimate caveat as Agent 1
- Cost still uses Agent 1's flat placeholder rate

### Tests (`tests/test_optimizer.py`)

Offline, no API key needed (uses the fake client described above).

| Test                                                       | Checks                                                                           |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `test_countTokens_counts_nonempty_text`                  | Non-empty text gives > 0 tokens, empty string gives 0                            |
| `test_buildUserMessage_without_issues`                   | No issues → message is just`PROMPT TO OPTIMIZE:\n<prompt>`                    |
| `test_buildUserMessage_with_issues`                      | Issues are listed as bullets before the prompt                                   |
| `test_callOptimizerLLM_sends_system_prompt_and_strips`   | The system prompt and issues are sent, and whitespace is stripped from the reply |
| `test_optimizePrompt_computes_savings`                   | Token counts, tokens saved and percent saved are correct                         |
| `test_optimizePrompt_never_negative`                     | A longer rewrite gives 0 saved, not a negative number                            |
| `test_optimizePrompt_empty_prompt`                       | Empty prompt doesn't divide by zero                                              |
| `test_optimizePrompt_default_issues`                     | `issues` defaults to an empty list                                             |
| `test_formatComparisonTable_contains_prompts_and_counts` | Both prompts, counts, percent and headers are in the table                       |
| `test_formatComparisonTable_wraps_long_prompts`          | Long prompts wrap and every line has the same width                              |

Current result: `16 passed` across both test files.

## Agent 3 — Validator (`validator.py`)

### Status: Core logic working and tested in CI, not wired into the orchestrator yet (9/29/2026)

### What it does

Takes the original prompt and Agent 2's rewrite, asks Claude whether the rewrite still keeps the original's intent and requirements, and returns a `ValidationResult` with:

- The original and optimized prompt
- A quality score from 0 to 10
- A pass/fail verdict (pass means a score of 6 or higher)
- A one-sentence reason for the verdict
- `reactTrace`: any reasoning the model wrote before its verdict, kept so the verdict can be inspected and not just trusted

### To test: pytest tests/test_validator.py -v

### Example

```python
from agents.optimizer import optimizePrompt
from agents.validator import validatePrompt

prompt = "Please, could you kindly help me write a short story about a dragon? Thank you so much!"
optimized = optimizePrompt(prompt).optimizedPrompt     # Agent 2
result = validatePrompt(prompt, optimized)             # Agent 3 (calls Claude)
print(result.qualityScore, result.passed, result.reasoning)
```

### Design decisions

- **Agent 3 is the safety net for Agent 2:** Agent 2 is told to keep meaning over length, but nothing checked that it did. Agent 3 checks it, so a shorter prompt that changes the result is caught before it reaches the user.
- **Fixed score scale in the system prompt:** each band (9–10, 6–8.99, 3–5.99, 1–2.99, 0–0.99) describes what counts as a loss, e.g. a dropped constraint or example puts the rewrite at 3–5.99. This makes scores more consistent between runs than asking for a plain "rate this 1–10".
- **Strict by design:** the prompt says that a shorter prompt that changes meaning fails, even if it saves tokens. This matches the rule behind Agent 2.
- **No LLM call for identical prompts:** if the rewrite matches the original (ignoring surrounding whitespace), it passes with a score of 10 without calling the API, following the "don't waste tokens to save tokens" idea from Agent 1.
- **Parsing never crashes:** a reply that can't be parsed gives score 0 and `passed = False`. An unreadable verdict counts as a fail, not a pass.
- **Same structure as Agents 1 and 2:** plain functions plus a data-only `ValidationResult` dataclass.

### Challenges + fixes

| Challenge                                              | Cause                                                                                                                                                                                        | Fix                                                                                                                                                                                                                                       |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reply was hard to parse reliably                       | The first system prompt asked for`Score <float 1, 10>` / `Passed <Yes or No>` / `Reasoning: ...`, so the format was inconsistent: some lines had colons and some didn't                | Changed to fixed`SCORE:` / `PASSED:` / `REASON:` labels. `parseValidatorReply()` matches them case-insensitively and ignores surrounding whitespace                                                                               |
| Score bands were empty, then had a gap                 | The first version listed ranges (`7-8.99:`, `5-6.99:` ...) without descriptions. The next version described them but used `0:` for the bottom band, which didn't cover scores like 0.5 | Wrote a description for each band, lined the bands up with the pass threshold of 6, and changed the bottom band to`0-0.99`                                                                                                              |
| A non-numeric score (e.g.`SCORE: high`) would crash  | `float()` raises `ValueError`                                                                                                                                                            | Caught the error and kept the default score of 0                                                                                                                                                                                          |
| Only the verdict was visible, not how it was reached   | The parser threw away everything except the three fields                                                                                                                                     | Added`reactTrace`: everything before the `SCORE:` line is kept on the result                                                                                                                                                          |
| No tests and no CI coverage for Agent 3                | It was the only agent without tests                                                                                                                                                          | Offline tests with a fake client (`tests/test_validator.py`) run in CI on every PR. Live tests against the real API (`tests/test_validator_live.py`) run in their own workflow; see the CI/CD section above for how they're triggered |
| Testing the validator's*judgment*, not just the code | The fake client only checks how a reply is handled, not whether Claude grades correctly                                                                                                      | The live tests use two known cases: a rewrite that only removes filler words must pass, and a rewrite that drops a word limit and a JSON format must fail. If the prompt or model changes and grading gets worse, these fail              |

### Known limitations / things to revisit

- **`passed` comes from the model, not the score:** a reply like `SCORE: 4` / `PASSED: Yes` counts as a pass. The rule "pass only at 6 or higher" is only enforced by the prompt
- **The trace is usually empty:** the parser is ready for a READ/ANSWER/CITE/THINK trace, but the system prompt never asks for one. Also, `max_tokens=300` would likely cut off a long trace before the `SCORE:` line is written
- **The docstring and code disagree on the fallback score:** the `parseValidatorReply` docstring says the fallback score is 1, but the code uses 0. The tests check for 0
- `qualityScore` is declared as `int`, but it holds decimal scores (e.g. 8.5)
- Model is hardcoded (`claude-sonnet-4-6`), same as Agent 2
- The validator is a single LLM judge, so the same pair of prompts can score slightly differently between runs. Scores close to 6 are the least reliable

### Tests (`tests/test_validator.py`, offline)

| Test                                                   | Checks                                                                         |
| ------------------------------------------------------ | ------------------------------------------------------------------------------ |
| `test_buildUserMessage_labels_both_prompts`          | Both prompts are included and labeled                                          |
| `test_parseValidatorReply_well_formed`               | Score, passed and reason are parsed from a clean reply, and the trace is empty |
| `test_parseValidatorReply_case_and_whitespace`       | Lowercase labels and extra whitespace still parse                              |
| `test_parseValidatorReply_keeps_trace`               | Text before`SCORE:` is kept as the trace                                     |
| `test_parseValidatorReply_unparseable_uses_defaults` | An unreadable reply gives score 0, a fail, and the default reason              |
| `test_parseValidatorReply_bad_score`                 | A non-numeric score doesn't crash                                              |
| `test_callValidatorLLM_sends_system_prompt`          | The validator system prompt and both prompts are sent                          |
| `test_validatePrompt_identical_skips_llm`            | Identical prompts pass with score 10 and make no API call                      |
| `test_validatePrompt_uses_llm_verdict`               | A changed prompt uses the model's score, verdict, reason and trace             |

Live tests (`tests/test_validator_live.py`, run with `pytest -m live`, need `ANTHROPIC_API_KEY`): `test_filler_removal_passes`, `test_dropped_constraint_fails`.

Current result: `25 passed, 2 deselected` across all three test files. The 2 deselected are the live tests.

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

**5. Orchestrator:** one function that runs Agent 1 → Agent 2 → Agent 3. It skips the LLM rewrite when there's nothing to fix (same "don't waste tokens to save tokens" idea as Agent 1) and falls back to the original prompt when validation fails:

```python
def run(prompt):
    audit = auditPrompt(prompt)
    if not audit.issues and audit.severity == "Low":
        return audit, None, None
    optimization = optimizePrompt(prompt, audit.issues)
    validation = validatePrompt(prompt, optimization.optimizedPrompt)
    if not validation.passed:
        optimization.optimizedPrompt = prompt  # don't hand back a rewrite that changes meaning
    return audit, optimization, validation
```

**6. Decide `passed` from the score in Agent 3.** Right now the model's `PASSED:` line is trusted even when it contradicts the score:

```python
passed = score >= 6
```

**7. Actually ask for the reasoning trace in Agent 3, or drop it.** Either add a step to `VALIDATOR_SYSTEM_PROMPT` asking for a short trace before `SCORE:` (and raise `max_tokens` so it isn't cut off), or remove `reactTrace`. Asking for the trace costs more output tokens on every validation.

**8. Retry Agent 2 when Agent 3 fails it.** Pass the validator's `reasoning` back to the optimizer as an extra issue ("Rewrite dropped the 100-word limit") and try once more before falling back to the original.

**9. Add more live test cases for Agent 3** (dropped example, changed audience, a borderline rewrite) so changes to the prompt or model are checked against more than two cases. Once the model moves to config, run the live tests before switching models.

**10. Cleanup (team decisions):** pick one naming convention (camelCase vs snake_case), move the `"""..."""` blocks above functions into docstrings to raise the pylint score, then bump `fail-under` above 8.0.
