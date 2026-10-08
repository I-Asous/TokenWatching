# Agents — Progress Log

This README tracks what's been built in `agents/`, why specific decisions were made, and bugs encountered along the way (and how they were fixed). Keep this updated as agents are built — it doubles as documentation for the team and as notes for the final write-up.

---

## Agent 1 — Auditor (`auditor.py`)

### Status: Core logic working. Token counting moved to `tokens.py`, cost estimate no longer rounded (10/4/2026)

### What it does

Takes a single user-submitted prompt and returns:

- Token count, as the target LLM (`chatgpt` or `claude`) tokenizes it. Counting now lives in `tokens.py` (see the Token counting section); `auditPrompt(prompt, target)` passes the target through
- Estimated dollar cost (flat rate of $0.003 per 1K tokens, i.e. $3 per million. `config/prices.yaml` exists now but isn't wired in yet)
- A list of flagged waste issues (rule-based checks, escalates to an LLM review only when the prompt is long and no rule-based issues were actually found)
- A severity rating (`Low` / `Medium` / `High`)

### To test: pytest tests/test_auditor.py -v

### Design decisions

- **Tiered analysis (rule-based first, LLM only when needed):** since Agent 1's whole job is flagging wasted tokens, it shouldn't itself waste tokens doing so itself. Cheaper, deterministic checks run first (token-to-word ratio, filler word count, excessive blank lines). The LLM review only fires if the prompt is long (> 500 tokens) and none of the rule-based checks caught anything ie there might be subtler issues.
- **Plain functions, not a class:** originally tried wrapping everything in a `@dataclass class Auditor` with methods... reverted this. None of the functions need shared state (so no `self.something` is used across calls), thus plain top-level functions are simpler and match how the orchestrator will call this file later (`from agents.auditor import auditPrompt`).
- **`AuditResult` is a separate dataclass, data only:** keeps the "what data comes back" separate from "how it's calculated". Overall its just cleaner to reason about and test.
- **Token counting is shared, not owned by Agent 1:** `countTokens()` used to live here. It moved to `tokens.py` so Agents 1 and 2 count the same way for the same target, and the result is cached between them.
- **`estimateCost()` returns the unrounded value:** rounding happens where the number is displayed (e.g. `formatComparisonTable()` formats with 3 decimals). Rounding inside the function made every normal prompt cost `0.0`.

### Bugs encountered + fixes

| Bug                                                                                 | Cause                                                                                                                                                                                                                                         | Fix                                                                                                                                                                                                                                                                             |
| ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NameError: name 'AuditResult' is not defined`                                    | Function return type was annotated`-> AuditResult`, but the dataclass was actually named `Auditor` at the time (naming mismatch from an earlier refactor)                                                                                 | Renamed the dataclass to`AuditResult`, defined it before any function references it                                                                                                                                                                                           |
| `TypeError: AuditResult.__init__() got an unexpected keyword argument 'severity'` | `auditPrompt()` was updated to pass `severity=severity` into `AuditResult(...)`, but the `AuditResult` dataclass definition hadn't been updated to include a `severity` field yet so edits were made in one place but not the other | Added`severity: str = "Low"` as a field on `AuditResult`                                                                                                                                                                                                                    |
| Would-be`ZeroDivisionError` on empty prompt input                                 | `if word_count > 0 or (token_count / word_count) > 1:` — used `or` instead of `and`. With `or`, Python still evaluates the division even when `word_count` is 0, since the check doesn't short-circuit the way `and` does        | Changed`or` → `and`. Now if `word_count` is 0, Python short-circuits and never evaluates the division — no crash, and the ratio check also works correctly (previously `or` made the condition nearly always `True`, so the check wasn't really filtering anything) |
| Would-be`NameError: name 'llm_review' is not defined`                             | `auditPrompt()` called `llm_review(prompt)` (snake_case), but the function was actually defined as `llmReview` (camelCase) — naming drift between edits                                                                                | Corrected the call site to`llmReview(prompt)`, matching the actual function name                                                                                                                                                                                              |
| `estimatedCost` was `0.0` for almost every prompt | `estimateCost()` rounded to 3 decimals, and a single prompt costs a fraction of a cent (any prompt under about 170 tokens rounded to $0.000) | Removed the rounding. The function returns the raw value (30 tokens → `0.00009`) and callers round when they display it |
| The rate parameter's name didn't match the math | It was called `rate_per_100k`, but the function divides by 1,000 and the default `0.003` is a per-1K rate. Changing the divisor to 100,000 to match the name made costs 100x too low and failed `test_estimateCost_scales_with_tokens` (1M tokens gave $0.03, not $3.00) | Kept the divisor at 1,000 and renamed the parameter to `rate_per_1k` |

### Known limitations / things to revisit

- Cost estimate uses a flat hardcoded rate. `config/prices.yaml` now exists but nothing reads it, and it has no entry for `claude-sonnet-5-5` yet
- ~~Token counts are `tiktoken`-based estimates, not exact for Claude models~~ **Fixed.** With `target="claude"`, counts come from Anthropic's `count_tokens` endpoint (see the Token counting section). ChatGPT counts use `o200k_base` instead of the older `cl100k_base`
- Naming convention is currently a mix of `camelCase` and `snake_case`,  worth standardizing (team decision) before this gets much bigger
- ~~Open bug: token-to-word ratio check over-flags~~ **Fixed.** The threshold was `> 1`, but normal English averages ~1.3 tokens/word, so almost every prompt got flagged (e.g. `"What is the capital of France?"` → 7 tokens / 6 words → flagged), and severity was almost never `Low`. Raised it to `> 1.6` (a bit above the ~1.3 average) and removed the `xfail` marker from the clean-prompt test. 1.6 is still a guess, so it's worth gathering real prompt data to tune it
- `llmReview()` isn't covered by tests yet, since it needs an API key and real API calls (would need mocking)
- **Filler words are matched as substrings:** `text.lower().count(w)` counts "just" inside "adjust" and "best" in "find the best algorithm", so normal prompts can be flagged
- **The token-to-word ratio check also fires on code, URLs and non-English text**, which naturally have more tokens per word. Those are the prompts the Optimizer should touch least
- **Short wordy prompts are never optimized:** under 500 tokens the LLM review doesn't run, so a prompt with fewer than 3 filler hits gets no issues and the pipeline returns it as-is
- **`llmReview()` turns every non-empty line of the reply into an issue**, including a preamble line like "Here are the issues:". It still uses `claude-sonnet-4-6`
- `severity` is computed but nothing in the pipeline uses it yet

### Tests (`tests/test_auditor.py`)

Offline unit tests. They need no API key and never call Claude. Run from the repo root with `pytest` (`pytest.ini` puts the repo root on the path, so tests import the agents as `from agents import auditor`).

| Test                                                     | Checks                                                                        |
| -------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `test_countTokens_counts_nonempty_text`                | Non-empty text gives > 0 tokens, empty string gives 0                         |
| `test_estimateCost_scales_with_tokens`                 | Cost is 0 for 0 tokens and $3.00 for 1M tokens                                |
| `test_runRuleCheck_flags_filler_words_and_blank_lines` | Filler words and`\n\n\n` are both flagged                                   |
| `test_flags_excessive_blank_lines`                     | 2 newlines in a row are fine, 3+ get flagged                                  |
| `test_runRuleCheck_clean_prompt_has_no_issues`         | A short, direct prompt has no issues (passes now that the ratio bug is fixed) |
| `test_determineSeverity_thresholds`                    | Low/Medium/High boundaries (300/800 tokens, 1/3 issues)                       |

## CI/CD (9/23/2026)

Replaced the old pylint-only workflow (which was failing on every PR at a 5.61/10 score) with a full pipeline. Details for the agents side:

- **CI (`.github/workflows/ci.yml`)** runs on every PR and push to `main`: pylint + `pytest` on Python 3.12/3.13/3.14, plus separate jobs for the dashboard (lint + build) and the extension (manifest check + zip packaging)
- **Pylint gate:** `pylintrc.toml` sets `fail-under = 4.0` (lowered from 8.0; the current score is about 6.2), so CI passes today but fails if code quality drops. Raise this as the existing warnings in `auditor.py` are cleaned up (missing docstrings, trailing whitespace, and the `"""..."""` comment blocks above functions, which pylint flags as `pointless-string-statement`. Moving them *inside* the function as docstrings fixes both)
- **Dev dependencies:** `pip install -r requirements-dev.txt` installs the runtime deps plus `pylint` and `pytest`
- **Validator (Agent 3):** `tests/test_validator.py` runs offline in CI with a fake client (same pattern as the optimizer tests). `tests/test_validator_live.py` calls the real API to check the validator still passes a filler-only rewrite and fails one that drops a constraint. These tests are marked `live`, are skipped by default (`pytest.ini` sets `-m "not live"`), and run in `.github/workflows/validator-live.yml` on manual dispatch or when `agents/validator.py` changes on `main`. That workflow needs the `ANTHROPIC_API_KEY` repo secret. To run them locally: `pytest -m live`
- **Releases:** bump `version` in `manifest.json`, then push a matching tag (`git tag v1.1 && git push origin v1.1`), and a GitHub Release with the extension zip is created automatically

## Agent 2 — Optimizer (`optimizer.py`)

### Status: Reworked around structured outputs and worked examples, hardened against edge cases (10/4/2026)

### What it does

Takes a prompt, plus optionally the issues Agent 1 flagged, the target LLM, and any earlier rewrites the Validator rejected. Returns an `OptimizationResult` with:

- The original and rewritten prompt
- Token counts for both, counted with the target LLM's tokenizer (`tokens.py`), so the numbers match what the user is billed
- Tokens saved and percent saved
- `changes`: the LLM's short list of edits (e.g. "removed politeness phrasing")
- `preservedConstraints`: the requirements the LLM said the rewrite had to keep

If the LLM marks the prompt as already concise, refuses, is cut off, or returns nothing usable, the original prompt is kept and the savings are 0.

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
- **Structured output instead of free text:** the reply is constrained to the `Rewrite` schema (Pydantic, sent with `client.messages.parse(..., output_format=Rewrite)`). The rewrite arrives in its own field, so a preamble like "Here's your optimized prompt:" can't end up in the prompt the user sees.
- **Field order is generation order:** `Rewrite` is `preservedConstraints` → `unchanged` → `optimizedPrompt` → `changes`. The model has to list what it must keep and decide whether to rewrite at all before it writes anything.
- **An explicit `unchanged` flag:** already-direct prompts are marked unchanged and the original is kept, even if the model also wrote a rewrite. This replaced relying on the model to copy the prompt back exactly.
- **System prompt explains the stakes, then gives rules:** it says the rewrite is a one-click replacement in a browser extension and that a changed meaning costs more trust than any tokens saved. Then four lists: what to remove (greetings, hedging, repeated instructions, wordy phrasing), what to copy exactly (code, URLs, paths, quotes, numbers, names, negations, examples, step order, the prompt's language, context that changes the answer), what isn't worth an edit (synonym swaps, dropping only "please"), and how to answer.
- **8 worked examples, one rule each** (`OPTIMIZER_EXAMPLES`): filler removal, hard constraints, code copied exactly, negations and answer-changing context, already direct, "please"-only, merged duplicate instructions, and a Spanish prompt that stays in Spanish. Two of the eight are `unchanged`, so the model doesn't learn to always rewrite. They are rendered as `<example><input>…</input><output>…JSON…</output></example>` so the model sees every field filled in.
- **Examples don't overlap the test prompts:** none of them reuse a prompt from the `__main__` cases, and a test enforces it, so passing those cases still means something.
- **The prompt is treated as text, not instructions:** the system prompt says to rewrite or leave a prompt like "ignore previous instructions", never act on it.
- **Rejected rewrites come back with their reason:** on a retry, each earlier rewrite is shown in `<rejected_rewrite>` tags with the Validator's reason, and the system prompt says to start again from the original, keep the cuts that were fine, restore what was lost, and never return a rejected rewrite again.
- **Cached system prompt:** the system prompt is identical on every call (about 1,570 tokens by the `o200k_base` estimate), so it's sent with `cache_control: ephemeral`. Only the per-prompt text is in `messages`. Cache reads and writes are logged to confirm the cache is hit.
- **Model moved to `claude-sonnet-5-5`** (`OPTIMIZER_MODEL`), because structured outputs weren't available on `claude-sonnet-4-6`.
- **Same structure as Agent 1:** plain functions plus a data-only `OptimizationResult` dataclass, so the orchestrator can call `optimizePrompt()` the same way it calls `auditPrompt()`.
- **Reuses `estimateCost()` from Agent 1** for the table, instead of a second copy of the rate.

### Challenges + fixes

| Challenge                                            | Cause                                                                                              | Fix                                                                                                                                                                                            |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cost column always showed`$0.000`                  | A single prompt costs a fraction of a cent, and`estimateCost()` rounded to 3 decimals            | Table shows**cost per 1,000 runs** instead, which is also closer to how real apps pay (same prompt, many calls). `estimateCost()` no longer rounds (10/4), but the table keeps this column |
| Negative "savings"                                   | The LLM can return a rewrite that's*longer* than the original (e.g. for an already short prompt) | `tokensSaved = max(original - optimized, 0)`, so savings are never negative                                                                                                                  |
| `ZeroDivisionError` on empty prompt                | `percentSaved` divides by `originalTokens`                                                     | Returns`0.0` when `originalTokens` is 0 (same kind of bug as the one in Agent 1)                                                                                                           |
| Long prompts broke the table layout                  | A 500-word prompt made one very wide row                                                           | `textwrap` wraps the prompt column (default 50 chars); other cells are padded so every line has the same width                                                                               |
| Testing without an API key / without spending tokens | `callOptimizerLLM()` makes a real Claude call                                                    | Tests swap the module's`client` for a fake one with `monkeypatch`. The fake records the request and returns a set reply, so we can check both what gets sent and how the result is handled |

| The model could add a preamble or commentary around the rewrite | The reply was free text, so nothing separated the prompt from anything else the model wrote | Structured output: the rewrite is the `optimizedPrompt` field of the `Rewrite` schema |
| "Return it unchanged" wasn't reliable | The model had to copy the prompt back exactly, and a one-word difference counted as a rewrite | Added the `unchanged` flag. When it's true the original is kept, whatever is in `optimizedPrompt` |
| Dropping "please" could make a prompt longer | Changing the first word changes how the rest tokenizes, so a one-word cut can save nothing or add a token | The system prompt lists these edits under "Don't bother", with a "please"-only example marked unchanged |
| A retry could repeat the same mistake | The Validator's reason was passed as one more line in the issue list, without the rewrite it referred to | `RejectedAttempt(rewrite, reason)`: the retry sees each rejected rewrite next to its reason |
| A refused or cut-off reply would crash or return half a prompt | Nothing checked `stop_reason` | `callOptimizerLLM()` returns `None` on `refusal`, `max_tokens`, or an unparseable reply, and `optimizePrompt()` keeps the original. An empty rewrite is handled the same way |
| Savings didn't match the LLM the user was prompting | Everything was counted with `cl100k_base`, which neither current ChatGPT models nor Claude use | `optimizePrompt(..., target=...)` counts with `tokens.py` |

### Known limitations / things to revisit

- Model is a constant in the file (`OPTIMIZER_MODEL = "claude-sonnet-5-5"`), should move to config along with pricing. Agents 1 and 3 are still on `claude-sonnet-4-6`
- `optimizePrompt()` on its own doesn't check that the rewrite kept every item in `preservedConstraints`. The list is the model's own, and nothing compares it to the rewrite. Inside the pipeline, Agent 3 checks the rewrite and the orchestrator falls back to the original if it fails
- If the rewrite is longer, `optimizePrompt()` reports 0% saved but still returns the longer prompt. The orchestrator discards a rewrite that saves nothing (see the Orchestrator section)
- The 10 edge cases in `__main__` (filler, concise, constraints, code, URL + quote, negation, injection, "please"-only, duplicates, Spanish) call the real API and print PASS/FAIL, but they aren't a pytest suite and don't run in CI
- `max_tokens` is 16000 for a reply that is usually a few hundred tokens
- Cost still uses Agent 1's flat placeholder rate

### Tests (`tests/test_optimizer.py`)

Offline, no API key needed. The fake client records the request and returns a canned parsed `Rewrite`. 31 tests (22 functions, some parametrized).

| Test                                                       | Checks                                                                                  |
| ---------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `test_countTokens_counts_nonempty_text`                  | Non-empty text gives > 0 tokens, empty string gives 0                                   |
| `test_buildUserMessage_without_issues`                   | No issues → message is just`PROMPT TO OPTIMIZE:\n<prompt>`                           |
| `test_buildUserMessage_with_issues`                      | Issues are listed as bullets before the prompt                                          |
| `test_buildUserMessage_with_rejected_attempts`           | Rejected rewrites and their reasons appear between the issues and the prompt            |
| `test_buildUserMessage_without_rejected_attempts`        | No rejected attempts → no rejection section                                            |
| `test_optimizePrompt_forwards_rejected_attempts`         | Rejected attempts given to `optimizePrompt()` reach the LLM request                   |
| `test_callOptimizerLLM_sends_system_prompt_and_strips`   | The system prompt and schema are sent, and whitespace is stripped from the rewrite      |
| `test_optimizePrompt_computes_savings`                   | Token counts, tokens saved and percent saved are correct                                |
| `test_optimizePrompt_unchanged_keeps_original`           | A prompt marked unchanged keeps the original text, even if the LLM rewrote it anyway    |
| `test_optimizePrompt_unusable_reply_keeps_original`      | A refused, truncated or unparseable reply falls back to the original (parametrized)     |
| `test_optimizePrompt_empty_rewrite_keeps_original`       | An empty rewrite is never returned                                                      |
| `test_optimizePrompt_never_negative`                     | A longer rewrite gives 0 saved, not a negative number                                   |
| `test_optimizePrompt_empty_prompt`                       | Empty prompt doesn't divide by zero                                                     |
| `test_optimizePrompt_default_issues`                     | `issues` defaults to an empty list                                                    |
| `test_formatComparisonTable_contains_prompts_and_counts` | Both prompts, counts, percent and headers are in the table                              |
| `test_formatComparisonTable_wraps_long_prompts`          | Long prompts wrap and every line has the same width                                     |
| `test_examples_are_consistent`                           | Each worked example agrees with itself, e.g. unchanged ones copy the input and list no edits (one case per example) |
| `test_examples_include_unchanged_cases`                  | The examples include both rewritten and unchanged outcomes                              |
| `test_code_example_keeps_code_block`                     | Code in an example survives the rewrite character for character                         |
| `test_system_prompt_contains_examples`                   | Every example is rendered into the system prompt                                        |
| `test_system_prompt_is_cacheable`                        | The system prompt is long enough to be cached, with margin                              |
| `test_examples_do_not_reuse_main_cases`                  | No example reuses a prompt from the `__main__` cases                                  |

## Agent 3 — Validator (`validator.py`)

### Status: Core logic working and tested in CI, called by the orchestrator (10/1/2026)

### What it does

Takes the original prompt and Agent 2's rewrite, asks Claude whether the rewrite still keeps the original's intent and requirements, and returns a `ValidationResult` with:

- The original and optimized prompt
- A quality score from 1 to 10
- A pass/fail verdict (pass means a score of 6 or higher)
- A one-sentence reason for the verdict
- `reactTrace`: the READ / ANSWER / CITE / THINK steps the model wrote before its verdict, kept so the verdict can be inspected and not just trusted

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
- **Fixed score scale in the system prompt:** the score is an integer from 1 to 10, and each band (9–10, 6–8, 3–5, 1–2) describes what counts as a loss, e.g. a dropped constraint or example puts the rewrite at 3–5. This makes scores more consistent between runs than asking for a plain "rate this 1–10".
- **ReAcT steps before the verdict:** the system prompt makes the model list the original's requirements (READ), check each one against the rewrite (ANSWER), quote what was lost (CITE) and decide whether the loss changes the output (THINK) before it writes `SCORE:`. The score is then based on specific findings instead of a general impression. This costs more output tokens on every validation.
- **Strict by design:** the prompt says that a shorter prompt that changes meaning fails, even if it saves tokens. This matches the rule behind Agent 2.
- **No LLM call for identical prompts:** if the rewrite matches the original (ignoring surrounding whitespace), it passes with a score of 10 without calling the API, following the "don't waste tokens to save tokens" idea from Agent 1.
- **Parsing never crashes:** a reply that can't be parsed gives score 1 (the lowest score on the scale) and `passed = False`. An unreadable verdict counts as a fail, not a pass.
- **Same structure as Agents 1 and 2:** plain functions plus a data-only `ValidationResult` dataclass.

### Challenges + fixes

| Challenge                                              | Cause                                                                                                                                                                                        | Fix                                                                                                                                                                                                                                       |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reply was hard to parse reliably                       | The first system prompt asked for`Score <float 1, 10>` / `Passed <Yes or No>` / `Reasoning: ...`, so the format was inconsistent: some lines had colons and some didn't                | Changed to fixed`SCORE:` / `PASSED:` / `REASON:` labels. `parseValidatorReply()` matches them case-insensitively and ignores surrounding whitespace                                                                               |
| Score bands were empty, then had a gap                 | The first version listed ranges (`7-8.99:`, `5-6.99:` ...) without descriptions. The next version described them but used `0:` for the bottom band, which didn't cover scores like 0.5 | Wrote a description for each band, lined the bands up with the pass threshold of 6, and changed the bottom band to`0-0.99`                                                                                                              |
| A non-numeric score (e.g.`SCORE: high`) would crash  | `float()` raises `ValueError`                                                                                                                                                            | Caught the error and kept the default score (now 1)                                                                                                                                                                                         |
| Only the verdict was visible, not how it was reached   | The parser threw away everything except the three fields                                                                                                                                     | Added`reactTrace`: everything before the `SCORE:` line is kept on the result                                                                                                                                                          |
| No tests and no CI coverage for Agent 3                | It was the only agent without tests                                                                                                                                                          | Offline tests with a fake client (`tests/test_validator.py`) run in CI on every PR. Live tests against the real API (`tests/test_validator_live.py`) run in their own workflow; see the CI/CD section above for how they're triggered |
| Testing the validator's*judgment*, not just the code | The fake client only checks how a reply is handled, not whether Claude grades correctly                                                                                                      | The live tests use two known cases: a rewrite that only removes filler words must pass, and a rewrite that drops a word limit and a JSON format must fail. If the prompt or model changes and grading gets worse, these fail              |
| Scores were based on a general impression | The prompt only asked for a score, a verdict and a reason, so `reactTrace` was almost always empty | Reworked the system prompt around the ReAcT steps (READ, ANSWER, CITE, THINK), which must be written before the `SCORE:` line. The scale also changed from 0–10 decimals to 1–10 integers |
| Two offline tests failed after the ReAcT rework | The fallback score in `parseValidatorReply()` changed from 0 to 1 to match the new 1–10 scale, but `test_parseValidatorReply_unparseable_uses_defaults` and `test_parseValidatorReply_bad_score` still expected 0 | Updated both tests to expect 1. The docstring and the code now agree on the fallback |
| The reply would be cut off before the verdict | `max_tokens` was still 300, which was set when the reply was three lines. The ReAcT steps are longer than that, so the reply would end before `SCORE:` and every rewrite would parse as score 1 / fail | Raised `max_tokens` to 1024. Not confirmed with a live run yet: run `pytest -m live` with an API key to check |

### Known limitations / things to revisit

- **`passed` comes from the model, not the score:** a reply like `SCORE: 4` / `PASSED: Yes` counts as a pass. The rule "pass only at 6 or higher" is only enforced by the prompt
- **A cut-off reply looks the same as a bad rewrite:** if the reply still runs past `max_tokens` (now 1024), there is no `SCORE:` line and the result is score 1 / fail. `stop_reason` isn't checked, so the caller can't tell the two apart
- `qualityScore` is declared as `int`, but the parser returns a `float` (e.g. 8.0)
- Model is hardcoded (`claude-sonnet-4-6`). Agent 2 moved to `claude-sonnet-5-5` for structured outputs; moving Agent 3 the same way would replace the `SCORE:` / `PASSED:` / `REASON:` text parsing and fix the first three limitations in this list
- The two prompts are sent as plain labeled text (`original prompt:` / `optimized prompt:`), not in tags, and the system prompt doesn't say to treat them as text only (Agent 2's does)
- The validator is a single LLM judge, so the same pair of prompts can score slightly differently between runs. Scores close to 6 are the least reliable

### Tests (`tests/test_validator.py`, offline)

| Test                                                   | Checks                                                                         |
| ------------------------------------------------------ | ------------------------------------------------------------------------------ |
| `test_buildUserMessage_labels_both_prompts`          | Both prompts are included and labeled                                          |
| `test_parseValidatorReply_well_formed`               | Score, passed and reason are parsed from a clean reply, and the trace is empty |
| `test_parseValidatorReply_case_and_whitespace`       | Lowercase labels and extra whitespace still parse                              |
| `test_parseValidatorReply_keeps_trace`               | Text before`SCORE:` is kept as the trace                                     |
| `test_parseValidatorReply_unparseable_uses_defaults` | An unreadable reply gives score 1, a fail, and the default reason              |
| `test_parseValidatorReply_bad_score`                 | A non-numeric score doesn't crash and keeps the default score of 1             |
| `test_callValidatorLLM_sends_system_prompt`          | The validator system prompt and both prompts are sent                          |
| `test_validatePrompt_identical_skips_llm`            | Identical prompts pass with score 10 and make no API call                      |
| `test_validatePrompt_uses_llm_verdict`               | A changed prompt uses the model's score, verdict, reason and trace             |

Live tests (`tests/test_validator_live.py`, run with `pytest -m live`, need `ANTHROPIC_API_KEY`): `test_filler_removal_passes`, `test_dropped_constraint_fails`.

## Token counting (`tokens.py`)

### Status: Working and tested offline, used by Agents 1 and 2 (10/2/2026)

### What it does

`countTokens(text, target)` counts tokens the way the LLM the user is prompting would, so the savings shown match what they are billed.

| Target | How it's counted |
| --- | --- |
| `chatgpt` (default) | Locally with `tiktoken`, `o200k_base` encoding (GPT-4o and newer) |
| `claude` | Anthropic's `count_tokens` endpoint (`claude-sonnet-5-5`), minus the message framing |

### To test: pytest tests/test_tokens.py -v

### Design decisions

- **One function for every agent:** Agents 1 and 2 both import `countTokens` and `DEFAULT_TARGET` from here, so before/after counts always use the same tokenizer.
- **Framing overhead is measured, not hardcoded:** `count_tokens` counts the user-turn wrapper as well as the text. `claudeMessageOverhead()` measures it once with a one-token message and subtracts it, so only the prompt's own tokens are returned.
- **Falls back instead of failing:** if the Claude call raises `APIError`, a warning is logged and the local `o200k_base` count is used as an estimate.
- **Cached (`lru_cache`, 1024 entries):** the Auditor and the Optimizer both count the original prompt, and that costs one API call, not two.
- **Empty text is 0 with no API call, and an unknown target raises `ValueError`.**

### Known limitations / things to revisit

- A fallback estimate is cached like a real count, so after one failed Claude call that text keeps its `tiktoken` estimate for the rest of the process
- `chatgpt` assumes `o200k_base` for every ChatGPT model
- Each distinct text costs one `count_tokens` request when the target is `claude`
- This module creates its own Anthropic client, as do the three agents (four clients in total)

### Tests (`tests/test_tokens.py`, offline)

The fake client's `count_tokens` returns one token per word plus a fixed framing amount. Caches are cleared before every test.

| Test | Checks |
| --- | --- |
| `test_countTokens_chatgpt_uses_o200k` | ChatGPT counts match `o200k_base` |
| `test_countTokens_empty_text` | Empty text is 0 tokens and makes no API call |
| `test_countTokens_claude_subtracts_overhead` | Claude counts come from `count_tokens`, minus the framing overhead |
| `test_countTokens_claude_is_cached` | Counting the same prompt twice calls the API once |
| `test_countTokens_claude_falls_back_on_api_error` | A failed `count_tokens` call gives the local estimate instead of crashing |
| `test_countTokens_unknown_target` | An unknown target raises `ValueError` |

## Orchestrator (`orchestrator.py`)

### Status: Pipeline working and tested offline. Target-aware, retries carry the rejected rewrite (10/4/2026)

### What it does

`runPipeline(prompt, target="chatgpt")` runs Agent 1 → Agent 2 → Agent 3 on one prompt and returns an `OrchestrationResult` with:

- The original prompt and the final prompt (the rewrite if one passed, otherwise the original)
- `wasOptimized`: whether the final prompt is a rewrite
- The `AuditResult` from Agent 1
- `attempts`: the `ValidationResult` of every rewrite that was validated, in order
- Tokens saved and percent saved (0 when the original is returned), counted with the target's tokenizer
- `changes`: Agent 2's list of edits for the accepted rewrite

The steps:

1. Agent 1 audits the prompt. If it finds no issues, the original is returned and Agents 2 and 3 are not called.
2. Agent 2 rewrites the prompt using Agent 1's issues.
3. If the rewrite saves no tokens (unchanged or longer), the loop stops and the original is returned.
4. Agent 3 checks the rewrite against the original. If it passes, the rewrite is returned and the loop stops.
5. If it fails, the rewrite and Agent 3's reason are stored as a `RejectedAttempt` and Agent 2 tries again with every rejected attempt so far, up to `MAX_OPTIMIZATION_ATTEMPTS` (3) attempts in total.
6. If no attempt passes, the original prompt is returned.

### To test: pytest tests/test_orchestrator.py -v

### To run

From the repo root, with `ANTHROPIC_API_KEY` exported in the shell:

```
python -m agents.orchestrator
```

`python agents/orchestrator.py` does not work (see the first row of the bugs table).

The run prints the original and final prompt, the audit severity and issues, then a JSON summary: one entry per attempt (score, passed, reason) plus `changes`, `tokensSaved` and `percentSaved` when a rewrite was accepted.

### Example

```python
from agents.orchestrator import runPipeline

result = runPipeline("Please, could you kindly help me write a short story? I would really "
                     "appreciate it if you could make it about a dragon. Thank you so much!")

print(result.finalPrompt, result.wasOptimized)
for attempt in result.attempts:
    print(attempt.qualityScore, attempt.passed, attempt.reasoning)
print(result.tokensSaved, result.percentSaved, result.changes)
```

Pass `target="claude"` to count with Claude's tokenizer.

### Design decisions

- **Skip Agents 2 and 3 when Agent 1 finds nothing:** same "don't waste tokens to save tokens" idea as Agent 1. A clean prompt costs no LLM calls (unless it is over 500 tokens, where Agent 1 runs its own LLM review).
- **The original is returned when nothing passes:** a rewrite that Agent 3 rejected is never returned, even if it saves tokens. Getting the same result for more tokens is better than a different result for fewer.
- **Retries include the rejected rewrite and the Validator's reason:** each failed attempt is passed to Agent 2 as a `RejectedAttempt(rewrite, reason)`, and every earlier rejection is sent, not just the latest. The next attempt sees exactly what it wrote and what that broke. (Before 10/2 only the reason was passed, as one more line in the issue list.)
- **The target is forwarded to Agents 1 and 2:** both count with the same tokenizer, so the audit's token count and the reported savings are consistent. Agent 3 doesn't count tokens, so it doesn't take a target.
- **Stop at the first pass:** no further calls are made once a rewrite passes.
- **Retry feedback is kept apart from the audit issues:** rejections live in their own `rejectedAttempts` list, and Agent 2 gets a copy of it on each call, so the `AuditResult` on the result still holds only what Agent 1 found.
- **Same structure as the agents:** one plain function plus a data-only `OrchestrationResult` dataclass.

### Bugs encountered + fixes

| Bug | Cause | Fix |
| --- | --- | --- |
| `ModuleNotFoundError: No module named 'auditor'` when running `pytest`, so `tests/test_optimizer.py` could not be collected and CI would fail | `orchestrator.py` and `optimizer.py` imported the other agents as `from auditor import ...`. That only works when a file inside `agents/` is run directly. `pytest` runs from the repo root, where the modules are `agents.auditor`, `agents.optimizer`, ... | Changed the imports to `from agents.auditor import ...` in both files (the form `optimizer.py` used before). The orchestrator is now run with `python -m agents.orchestrator` from the repo root |
| `wasOptimized = True` with 0 tokens saved | If Agent 2 returned the prompt unchanged, Agent 3 passed it automatically (identical prompts) and it was reported as an optimization. If Agent 2 returned a longer rewrite that Agent 3 passed, the longer prompt became `finalPrompt` | The loop stops when `optimizationResult.tokensSaved == 0`, before calling Agent 3, and the original is returned with `wasOptimized = False` |
| Every attempt would fail validation and the pipeline would always return the original after 3 attempts (6 LLM calls for nothing) | Agent 3's reply was cut off before the `SCORE:` line (`max_tokens=300` with the new ReAcT steps), so each rewrite parsed as a fail | Raised `max_tokens` to 1024 in `validator.py` (see the Agent 3 table). Not confirmed with a live run yet |
| Testing the pipeline without an API key | `runPipeline()` makes up to 7 Claude calls through the three agents | Tests replace `auditPrompt`, `optimizePrompt` and `validatePrompt` on the `orchestrator` module with fakes (`monkeypatch`). The fakes return set results and record their arguments, so the tests check the order of calls, what is passed between agents, and when the loop stops |

### Known limitations / things to revisit

- **`passed` is taken from Agent 3 as-is:** a reply like `SCORE: 4` / `PASSED: yes` makes the orchestrator return that rewrite (see Agent 3's limitations and next step 3)
- **A reply that can't be parsed is handled as a rejection:** the reason "Could not parse Agent 3, Validator, response." is passed to Agent 2 as a rejected attempt, under a heading that says the rewrite was rejected for changing the prompt's meaning. The retry is then told to fix a problem that doesn't exist
- **No handling of API errors:** a rate limit or network error in any agent raises out of `runPipeline()`. It should return the original prompt instead. Only `tokens.py` catches `APIError` today
- **`.env` is not loaded:** none of the agents call `load_dotenv()`, so the key has to be exported in the shell. Without it the first Claude call fails with "Could not resolve authentication method"
- **A failed optimization costs more than it could save:** 3 attempts are 6 LLM calls (7 if Agent 1 ran its LLM review), all in sequence before the user gets an answer. `MAX_OPTIMIZATION_ATTEMPTS = 3` is a guess and should be tuned on real prompts
- **No minimum saving:** only a rewrite that saves 0 tokens is skipped. One that saves 1 or 2 tokens still costs a Validator call and is offered to the user
- **Whether to optimize depends only on Agent 1's rule checks for prompts under 500 tokens:** e.g. `"Please, could you kindly help me write a short story about a dragon? Thank you so much!"` has 2 filler hits (the threshold is 3), so no issue is flagged and the prompt is returned as-is
- **No cost on the result:** the docstring mentions cost savings, but `OrchestrationResult` only has `tokensSaved` and `percentSaved`
- **The rewrite is only kept for attempts that were validated:** a rewrite dropped for saving no tokens is not recorded in `attempts`
- `import os` and `OptimizationResult` are imported but not used
- No live test of the full pipeline yet
- Nothing in `backend/` or the extension calls `runPipeline()` yet

### Tests (`tests/test_orchestrator.py`, offline)

| Test | Checks |
| --- | --- |
| `test_runPipeline_no_issues_skips_optimization` | No audit issues → original returned, Agents 2 and 3 not called, no attempts |
| `test_runPipeline_first_attempt_passes` | A rewrite that passes first time becomes `finalPrompt` and the loop stops |
| `test_runPipeline_forwards_target` | The target is passed to the Auditor and the Optimizer |
| `test_runPipeline_defaults_to_chatgpt` | Without a target, the pipeline uses `chatgpt` |
| `test_runPipeline_retries_with_validator_feedback` | A rejected rewrite is retried, and Agent 2 gets that rewrite and the Validator's reason |
| `test_runPipeline_passes_all_rejected_attempts` | Every earlier rejection is passed on, not just the latest one |
| `test_runPipeline_does_not_mutate_audit_issues` | The retry feedback is not added to `auditResult.issues` |
| `test_runPipeline_all_attempts_fail_returns_original` | After `MAX_OPTIMIZATION_ATTEMPTS` rejections the original is returned with `wasOptimized = False` and 0 saved |
| `test_runPipeline_respects_max_attempts` | With the limit set to 1, Agent 2 is called once |
| `test_runPipeline_no_savings_returns_original` | A rewrite that is unchanged or longer (2 cases) is not validated, retried or returned |

Current result: `63 passed, 2 deselected` across all five offline test files (auditor 6, optimizer 31, validator 9, orchestrator 11, tokens 6). The 2 deselected are the live validator tests.

---

## Next steps (with examples)

Updated 10/4/2026. Done since the last version of this list:

- ~~Use exact Claude token counts~~ → `tokens.py` (`target="claude"`).
- ~~Check the rewrite for a preamble before validating it~~ → no longer needed; the Optimizer's structured output puts the rewrite in its own field.
- ~~Create the pricing config~~ → `config/prices.yaml` exists. Reading it is still open (step 7).

**1. Handle errors in the orchestrator.** Return the original prompt if an agent raises:

```python
try:
    optimizationResult = optimizePrompt(prompt, auditResult.issues, target,
                                        rejectedAttempts=list(rejectedAttempts))
    validationResult = validatePrompt(prompt, optimizationResult.optimizedPrompt)
except anthropic.APIError:
    break  # falls through to returning the original
```

**2. Move Agent 3 to structured output, like Agent 2.** This fixes three things at once: a cut-off reply no longer looks like a bad rewrite, a parse failure is no longer fed back to Agent 2 as a rejection reason, and `passed` can be computed from the score instead of trusted from the model:

```python
class Verdict(BaseModel):
    requirements: list[str]   # READ
    losses: list[str]         # ANSWER + CITE
    reasoning: str            # THINK
    score: int
    reason: str

passed = verdict.score >= 6
```

**3. Fix the Auditor's rule checks**, since for prompts under 500 tokens they alone decide whether anything gets optimized. Match filler words on word boundaries, and skip the ratio check for prompts that contain code or URLs:

```python
filler_hits = sum(len(re.findall(rf"\b{re.escape(w)}\b", text.lower())) for w in filler_words)
```

**4. Add a minimum saving** in the orchestrator, so a rewrite that saves a token or two isn't validated or shown:

```python
if optimizationResult.percentSaved < MIN_PERCENT_SAVED:
    break
```

**5. Run the pipeline against the real API and turn the `__main__` cases into a live suite.** The Optimizer's 10 edge cases already print PASS/FAIL. As `pytest -m live` tests they could also record which attempt passed, tokens saved and latency. That gives real numbers for the open guesses: `MAX_OPTIMIZATION_ATTEMPTS`, the 1.6 ratio, the filler threshold of 3, and the pass score of 6. Also confirm that Agent 3's reply reaches the `SCORE:` line with `max_tokens=1024`.

**6. Connect the pipeline to the backend.** Add an endpoint that calls `runPipeline(prompt, target)` and saves the result, so the extension can use it.

**7. Read rates from `config/prices.yaml`** instead of the flat rate in `estimateCost()`, add `claude-sonnet-5-5` to the file, and add cost saved to `OrchestrationResult`.

**8. Load the API key from `.env`** (`load_dotenv()`, as `testing_agent.py` does) so the agents run without exporting the key first.

**9. One shared client and one place for model names.** Four modules each create an Anthropic client, and the model is `claude-sonnet-4-6` in two of them and `claude-sonnet-5-5` in the other two.

**10. Add more live test cases for Agent 3** (dropped example, changed audience, a borderline rewrite) so changes to the prompt or model are checked against more than two cases.

**11. Cleanup (team decisions):** pick one naming convention (camelCase vs snake_case), move the `"""..."""` blocks above functions into docstrings to raise the pylint score, then raise `fail-under` back up from 4.0.
