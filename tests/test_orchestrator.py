"""
Offline unit tests for the orchestrator
"""
import pytest
from agents import orchestrator
from agents.auditor import AuditResult
from agents.optimizer import OptimizationResult, RejectedAttempt
from agents.validator import ValidationResult

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

    def auditPrompt(self, prompt, target):
        self.targets.append(target)
        return AuditResult(token_count=20, estimatedCost=0.0, issues=self.issues, severity="Medium")

    def optimizePrompt(self, prompt, issues, target, rejectedAttempts=None):
        self.targets.append(target)
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

    def validatePrompt(self, originalPrompt, optimizedPrompt):
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
def test_runPipeline_passes_all_rejected_attempts(fakeAgents):
    fake = fakeAgents(
        issues=["filler"],
        rewrites=[("Write a story.", 15), ("Write about a dragon.", 14), (REWRITE, 12)],
        verdicts=[(False, "Dropped the dragon."), (False, "Dropped short story."), (True, "Fine.")],
    )
    orchestrator.runPipeline(PROMPT)

    assert fake.rejectedCalls[2] == [
        RejectedAttempt("Write a story.", "Dropped the dragon."),
        RejectedAttempt("Write about a dragon.", "Dropped short story."),
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

#The retry limit comes from MAX_OPTIMIZATION_ATTEMPTS
def test_runPipeline_respects_max_attempts(fakeAgents, monkeypatch):
    monkeypatch.setattr(orchestrator, "MAX_OPTIMIZATION_ATTEMPTS", 1)
    fake = fakeAgents(issues=["filler"], rewrites=[("Write a story.", 15)], verdicts=[(False, "Dropped the dragon.")])
    result = orchestrator.runPipeline(PROMPT)

    assert len(fake.optimizerCalls) == 1
    assert result.finalPrompt == PROMPT

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
