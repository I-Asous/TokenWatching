"""
Offline unit tests for the orchestrator
"""
from dataclasses import replace
import pytest
#anthropic 1.x is built on httpx2 and 0.x on httpx; build the fake request with whichever the SDK uses
try:
    import httpx2 as httpx
except ImportError:
    import httpx
from anthropic import APIConnectionError
from agents import orchestrator
from agents.auditor import AuditResult
from agents.optimizer import OptimizationResult, RejectedAttempt
from agents.validator import ValidationResult
from agents.prompt_types import PROFILES

PROMPT = "Please, could you kindly write a short story about a dragon? Thank you so much!"
REWRITE = "Write a short story about a dragon."


#Fake agents that record how they were called and return canned results, so no API call is made
class FakeAgents:
    def __init__(self, issues, rewrites, verdicts):
        self.issues = issues
        self.rewrites = rewrites
        self.verdicts = verdicts
        self.optimizerCalls = []
        self.rejectedCalls = []
        self.validatorCalls = []
        self.targets = []
        self.preserveCalls = []
        self.skipChecks = []
        self.typeRules = []
        self.passScores = []
        self.validatorRules = []

    def auditPrompt(self, prompt, target, skipChecks=frozenset()):
        self.targets.append(target)
        self.skipChecks.append(skipChecks)
        return AuditResult(token_count=20, estimatedCost=0.0, issues=self.issues, severity="Medium")

    def optimizePrompt(self, prompt, issues, target, rejectedAttempts=None, mustPreserve=None, typeRules=""):
        self.targets.append(target)
        self.typeRules.append(typeRules)
        self.preserveCalls.append(list(mustPreserve or []))
        rewrite, tokensSaved = self.rewrites[len(self.optimizerCalls)]
        self.optimizerCalls.append(list(issues))
        self.rejectedCalls.append(list(rejectedAttempts or []))
        return OptimizationResult(
            originalPrompt=prompt,
            optimizedPrompt=rewrite,
            originalTokens=20,
            optimizedTokens=20 - tokensSaved,
            tokensSaved=tokensSaved,
            percentSaved=tokensSaved * 5.0,
            changes=["removed filler"],
        )

    def validatePrompt(self, originalPrompt, optimizedPrompt, passScore=6, typeRules=""):
        self.passScores.append(passScore)
        self.validatorRules.append(typeRules)
        passed, reason = self.verdicts[len(self.validatorCalls)]
        self.validatorCalls.append(optimizedPrompt)
        return ValidationResult(
            originalPrompt=originalPrompt,
            optimizedPrompt=optimizedPrompt,
            qualityScore=9 if passed else 4,
            passed=passed,
            reasoning=reason,
        )


@pytest.fixture
def fakeAgents(monkeypatch):
    def install(issues, rewrites=(), verdicts=()):
        fake = FakeAgents(issues, rewrites, verdicts)
        monkeypatch.setattr(orchestrator, "auditPrompt", fake.auditPrompt)
        monkeypatch.setattr(orchestrator, "optimizePrompt", fake.optimizePrompt)
        monkeypatch.setattr(orchestrator, "validatePrompt", fake.validatePrompt)
        return fake
    return install

#A prompt with no audit issues is returned unchanged without calling Agent 2 or 3
def test_runPipeline_no_issues_skips_optimization(fakeAgents):
    fake = fakeAgents(issues=[])
    result = orchestrator.runPipeline(PROMPT)

    assert fake.optimizerCalls == []
    assert fake.validatorCalls == []
    assert result.finalPrompt == PROMPT
    assert result.wasOptimized is False
    assert result.attempts == []
    assert result.tokensSaved == 0

#A rewrite that passes on the first attempt becomes the final prompt and the loop stops
def test_runPipeline_first_attempt_passes(fakeAgents):
    fake = fakeAgents(issues=["filler"], rewrites=[(REWRITE, 12)], verdicts=[(True, "Only filler removed.")])
    result = orchestrator.runPipeline(PROMPT)

    assert fake.optimizerCalls == [["filler"]]
    assert fake.validatorCalls == [REWRITE]
    assert result.originalPrompt == PROMPT
    assert result.finalPrompt == REWRITE
    assert result.wasOptimized is True
    assert len(result.attempts) == 1
    assert result.tokensSaved == 12
    assert result.percentSaved == 60.0
    assert result.changes == ["removed filler"]

#The target LLM is forwarded to the Auditor and Optimizer so both count with its tokenizer
def test_runPipeline_forwards_target(fakeAgents):
    fake = fakeAgents(issues=["filler"], rewrites=[(REWRITE, 12)], verdicts=[(True, "Only filler removed.")])
    orchestrator.runPipeline(PROMPT, target="claude")
    assert fake.targets == ["claude", "claude"]

#Without a target, the pipeline defaults to ChatGPT
def test_runPipeline_defaults_to_chatgpt(fakeAgents):
    fake = fakeAgents(issues=[])
    orchestrator.runPipeline(PROMPT)
    assert fake.targets == ["chatgpt"]

#A rejected rewrite is retried, with that rewrite and the Validator's reason passed to Agent 2
def test_runPipeline_retries_with_validator_feedback(fakeAgents):
    fake = fakeAgents(
        issues=["filler"],
        rewrites=[("Write a story.", 15), (REWRITE, 12)],
        verdicts=[(False, "Dropped the dragon."), (True, "Only filler removed.")],
    )
    result = orchestrator.runPipeline(PROMPT)

    assert fake.optimizerCalls == [["filler"], ["filler"]]
    assert fake.rejectedCalls == [[], [RejectedAttempt("Write a story.", "Dropped the dragon.")]]
    assert result.finalPrompt == REWRITE
    assert result.wasOptimized is True
    assert [attempt.passed for attempt in result.attempts] == [False, True]
    assert result.tokensSaved == 12

#Every earlier rejection is passed on, not just the latest one
def test_runPipeline_passes_all_rejected_attempts(fakeAgents, monkeypatch):
    monkeypatch.setattr(orchestrator, "MAX_OPTIMIZATION_ATTEMPTS", 3)
    fake = fakeAgents(
        issues=["filler"],
        rewrites=[("Write a story.", 15), ("Write a short story.", 14), (REWRITE, 12)],
        verdicts=[(False, "Dropped the dragon and 'short'."), (False, "Dropped the dragon."), (True, "Fine.")],
    )
    orchestrator.runPipeline(PROMPT)

    assert fake.rejectedCalls[2] == [
        RejectedAttempt("Write a story.", "Dropped the dragon and 'short'."),
        RejectedAttempt("Write a short story.", "Dropped the dragon."),
    ]

#Retry feedback never leaks into the audit's own issue list
def test_runPipeline_does_not_mutate_audit_issues(fakeAgents):
    fakeAgents(
        issues=["filler"],
        rewrites=[("Write a story.", 15), (REWRITE, 12)],
        verdicts=[(False, "Dropped the dragon."), (True, "Only filler removed.")],
    )
    result = orchestrator.runPipeline(PROMPT)

    assert result.auditResult.issues == ["filler"]

#When every attempt is rejected, the original prompt is returned and no savings are reported
def test_runPipeline_all_attempts_fail_returns_original(fakeAgents):
    attempts = orchestrator.MAX_OPTIMIZATION_ATTEMPTS
    fake = fakeAgents(
        issues=["filler"],
        rewrites=[("Write a story.", 15)] * attempts,
        verdicts=[(False, "Dropped the dragon.")] * attempts,
    )
    result = orchestrator.runPipeline(PROMPT)

    assert len(fake.optimizerCalls) == attempts
    assert len(result.attempts) == attempts
    assert result.finalPrompt == PROMPT
    assert result.wasOptimized is False
    assert result.tokensSaved == 0
    assert result.percentSaved == 0.0

#A failed Validator call returns the original prompt and isn't fed back to the Optimizer as a rejection
def test_runPipeline_validator_api_error_returns_original(fakeAgents, monkeypatch):
    fake = fakeAgents(issues=["filler"], rewrites=[(REWRITE, 12)] * 2)
    def fail(originalPrompt, optimizedPrompt, passScore=6, typeRules=""):
        raise APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    monkeypatch.setattr(orchestrator, "validatePrompt", fail)
    result = orchestrator.runPipeline(PROMPT)

    assert len(fake.optimizerCalls) == 1
    assert result.finalPrompt == PROMPT
    assert result.wasOptimized is False
    assert result.attempts == []
    assert result.tokensSaved == 0
    assert result.error.startswith("Validator call failed")

#A failed Optimizer call returns the original prompt, records the error and doesn't call the Validator
def test_runPipeline_optimizer_api_error_returns_original(fakeAgents, monkeypatch):
    fake = fakeAgents(issues=["filler"])
    def fail(prompt, issues, target, rejectedAttempts=None, mustPreserve=None, typeRules=""):
        raise APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    monkeypatch.setattr(orchestrator, "optimizePrompt", fail)
    result = orchestrator.runPipeline(PROMPT)

    assert fake.validatorCalls == []
    assert result.finalPrompt == PROMPT
    assert result.wasOptimized is False
    assert result.error.startswith("Optimizer call failed")

#A run without API failures has no error, even when every rewrite is rejected
def test_runPipeline_rejections_are_not_errors(fakeAgents):
    attempts = orchestrator.MAX_OPTIMIZATION_ATTEMPTS
    fakeAgents(
        issues=["filler"],
        rewrites=[("Write a story.", 15)] * attempts,
        verdicts=[(False, "Dropped the dragon.")] * attempts,
    )
    assert orchestrator.runPipeline(PROMPT).error is None

#The retry limit comes from MAX_OPTIMIZATION_ATTEMPTS
def test_runPipeline_respects_max_attempts(fakeAgents, monkeypatch):
    monkeypatch.setattr(orchestrator, "MAX_OPTIMIZATION_ATTEMPTS", 1)
    fake = fakeAgents(issues=["filler"], rewrites=[("Write a story.", 15)], verdicts=[(False, "Dropped the dragon.")])
    result = orchestrator.runPipeline(PROMPT)

    assert len(fake.optimizerCalls) == 1
    assert result.finalPrompt == PROMPT

SQL_PROMPT = "Please write SQL for me. Always use parameterized queries to prevent SQL injection. Thanks so much!"
SQL_DROPPED = "Write SQL."
SQL_KEPT = "Write SQL. Always use parameterized queries."

#A rewrite that breaks a lock is rejected without a Validator call, and the retry is told what it dropped
def test_runPipeline_broken_lock_skips_validator_and_retries(fakeAgents):
    fake = fakeAgents(
        issues=["filler"],
        rewrites=[(SQL_DROPPED, 15), (SQL_KEPT, 10)],
        verdicts=[(True, "Only filler removed.")],
    )
    result = orchestrator.runPipeline(SQL_PROMPT)

    assert fake.validatorCalls == [SQL_KEPT]
    retryFeedback = fake.rejectedCalls[1]
    assert len(retryFeedback) == 1
    assert retryFeedback[0].rewrite == SQL_DROPPED
    assert "constraint dropped" in retryFeedback[0].reason and "parameterized" in retryFeedback[0].reason

    assert result.finalPrompt == SQL_KEPT
    assert result.wasOptimized is True
    first, second = result.attempts
    assert first.passed is False and first.qualityScore == 0
    assert first.reactTrace == "Failed the local lock check, Validator not called."
    assert second.passed is True

#A rewrite that changes the task is rejected without a Validator call, like a broken lock
def test_runPipeline_changed_task_skips_validator_and_retries(fakeAgents):
    prompt = "Hi! Could you please explain how recursion works? Thanks!"
    kept = "Explain how recursion works."
    fake = fakeAgents(
        issues=["filler"],
        rewrites=[("Write a recursive function.", 8), (kept, 6)],
        verdicts=[(True, "Only filler removed.")],
    )
    result = orchestrator.runPipeline(prompt)

    assert fake.validatorCalls == [kept]
    reason = fake.rejectedCalls[1][0].reason
    assert "task dropped or changed" in reason and "explain" in reason
    assert result.finalPrompt == kept

#A dropped or changed number is rejected without a Validator call
def test_runPipeline_changed_number_skips_validator(fakeAgents):
    prompt = "Please write me a product description in under 150 words. Thank you!"
    fake = fakeAgents(issues=["filler"], rewrites=[("Write a product description under 100 words.", 8)] * 3)
    result = orchestrator.runPipeline(prompt)

    assert fake.validatorCalls == []
    assert '"150"' in fake.rejectedCalls[1][0].reason
    assert result.finalPrompt == prompt

#The Optimizer is told the prompt's tasks, rules and numbers on every attempt, not only after a rejection
def test_runPipeline_passes_must_preserve(fakeAgents):
    prompt = "Hi! Please write a 300-word bio for our CEO. Do not mention their age. Thanks!"
    fake = fakeAgents(issues=["filler"], rewrites=[("Write a bio.", 15), (prompt, 0)], verdicts=[])
    orchestrator.runPipeline(prompt)

    assert len(fake.preserveCalls) == 2 and fake.preserveCalls[0] == fake.preserveCalls[1]
    assert fake.preserveCalls[0] == ['task: write "a 300-word bio"', "rule: Do not mention their age.", "number: 300"]

#buildMustPreserve lists tasks first, then rules and numbers; code blocks and URLs are left to the system prompt
def test_buildMustPreserve():
    prompt = ("Fix this function. Never change its name. It must run in under 2 seconds.\n"
              "```python\ndef add(a, b): return a - b\n```\nDocs: https://example.com/add")
    items = orchestrator.buildMustPreserve(prompt)
    assert items[0] == 'task: fix "this function"'
    assert "rule: Never change its name." in items
    assert "number: 2" in items
    assert not any("example.com" in item or "def add" in item for item in items)

#The vagueness report is attached even when optimization is skipped, so the extension can ask its questions
def test_runPipeline_attaches_vagueness(fakeAgents):
    fakeAgents(issues=[])
    result = orchestrator.runPipeline("Make it better.")
    assert result.vagueness.level == "vague"
    assert result.vagueness.questions[0].startswith("Improve it toward what")

#A rewrite that turns an option into a requirement is rejected without a Validator call
def test_runPipeline_dropped_option_skips_validator(fakeAgents):
    prompt = "Please write a Python script that renames files. Maybe add logging. Thanks so much!"
    kept = "Write a Python script that renames files. Optionally add logging."
    fake = fakeAgents(
        issues=["filler"],
        rewrites=[("Write a Python script that renames files and adds logging.", 9), (kept, 7)],
        verdicts=[(True, "Only filler removed.")],
    )
    result = orchestrator.runPipeline(prompt)

    assert fake.validatorCalls == [kept]
    assert "optional request made required" in fake.rejectedCalls[1][0].reason
    assert "optional (keep it optional): Maybe add logging." in fake.preserveCalls[0]
    assert result.finalPrompt == kept

#If every rewrite breaks a lock, the Validator is never called and the original prompt is returned
def test_runPipeline_every_rewrite_breaks_lock_returns_original(fakeAgents):
    attempts = orchestrator.MAX_OPTIMIZATION_ATTEMPTS
    fake = fakeAgents(issues=["filler"], rewrites=[(SQL_DROPPED, 15)] * attempts)
    result = orchestrator.runPipeline(SQL_PROMPT)

    assert fake.validatorCalls == []
    assert len(fake.optimizerCalls) == attempts
    assert len(result.attempts) == attempts
    assert result.finalPrompt == SQL_PROMPT
    assert result.wasOptimized is False

#A rewrite that saves no tokens (unchanged or longer) is not validated, retried or returned
@pytest.mark.parametrize("rewrite", [PROMPT, PROMPT + " Make it as detailed as you possibly can."])
def test_runPipeline_no_savings_returns_original(fakeAgents, rewrite):
    fake = fakeAgents(issues=["filler"], rewrites=[(rewrite, 0)])
    result = orchestrator.runPipeline(PROMPT)

    assert len(fake.optimizerCalls) == 1
    assert fake.validatorCalls == []
    assert result.finalPrompt == PROMPT
    assert result.wasOptimized is False
    assert result.attempts == []

CHAT_PROMPT = "Hey, could you please suggest some fun weekend plans for me? Thanks so much!"
CODE_PROMPT = "Hey, could you please fix this, thanks so much!\n```python\ndef add(a, b): return a - b\n```"
CODE_REWRITE = "Fix this:\n```python\ndef add(a, b): return a - b\n```"

#The prompt's type profile reaches every agent: skipped checks, type rules (Optimizer and Validator) and the pass score
def test_runPipeline_passes_type_profile(fakeAgents):
    fake = fakeAgents(issues=["filler"], rewrites=[(CODE_REWRITE, 8)], verdicts=[(True, "Only filler removed.")])
    result = orchestrator.runPipeline(CODE_PROMPT)

    assert result.promptTypes == ["code"]
    assert fake.skipChecks == [PROFILES["code"].skipChecks]
    assert fake.typeRules == [PROFILES["code"].optimizerRules]
    assert fake.passScores == [PROFILES["code"].passScore]
    assert fake.validatorRules == [PROFILES["code"].optimizerRules]

#A prompt with several types gets the strictest settings of all of them
def test_runPipeline_combines_several_types(fakeAgents):
    prompt = "Please write a Python function that checks a password. Never log the password. Must follow GDPR."
    fake = fakeAgents(issues=["filler"], rewrites=[(prompt, 0)])
    result = orchestrator.runPipeline(prompt)

    assert result.promptTypes == ["security", "code"]
    assert fake.passScores == [] #saved nothing, so the Validator wasn't called
    assert PROFILES["security"].optimizerRules in fake.typeRules[0]
    assert PROFILES["code"].optimizerRules in fake.typeRules[0]

#A prompt with no type signals is conversational, and the result says so even when optimization is skipped
def test_runPipeline_conversational_by_default(fakeAgents):
    fake = fakeAgents(issues=[])
    result = orchestrator.runPipeline(CHAT_PROMPT)

    assert result.promptTypes == ["conversational"]
    assert fake.skipChecks == [frozenset()]

#A type that may not be optimized is returned as-is, without calling the Optimizer
def test_runPipeline_type_without_optimize_skips_optimizer(fakeAgents, monkeypatch):
    monkeypatch.setitem(PROFILES, "conversational", replace(PROFILES["conversational"], optimize=False))
    fake = fakeAgents(issues=["filler"])
    result = orchestrator.runPipeline(CHAT_PROMPT)

    assert fake.optimizerCalls == []
    assert result.finalPrompt == CHAT_PROMPT
    assert result.wasOptimized is False
