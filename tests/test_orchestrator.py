"""
Offline unit tests for the orchestrator
"""
import pytest
from agents import orchestrator
from agents.auditor import AuditResult
from agents.optimizer import OptimizationResult
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
        self.validatorCalls = []

    def auditPrompt(self, prompt):
        return AuditResult(token_count=20, estimatedCost=0.0, issues=self.issues, severity="Medium")

    def optimizePrompt(self, prompt, issues):
        rewrite, tokensSaved = self.rewrites[len(self.optimizerCalls)]
        #Copy the list, since the orchestrator keeps appending to it between attempts
        self.optimizerCalls.append(list(issues))
        return OptimizationResult(
            originalPrompt=prompt,
            optimizedPrompt=rewrite,
            originalTokens=20,
            optimizedTokens=20 - tokensSaved,
            tokensSaved=tokensSaved,
            percentSaved=tokensSaved * 5.0,
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

#A rejected rewrite is retried, with the Validator's reason passed to Agent 2 as an extra issue
def test_runPipeline_retries_with_validator_feedback(fakeAgents):
    fake = fakeAgents(
        issues=["filler"],
        rewrites=[("Write a story.", 15), (REWRITE, 12)],
        verdicts=[(False, "Dropped the dragon."), (True, "Only filler removed.")],
    )
    result = orchestrator.runPipeline(PROMPT)

    assert len(fake.optimizerCalls) == 2
    assert fake.optimizerCalls[0] == ["filler"]
    assert fake.optimizerCalls[1][0] == "filler"
    assert "attempt 1" in fake.optimizerCalls[1][1]
    assert "Dropped the dragon." in fake.optimizerCalls[1][1]
    assert result.finalPrompt == REWRITE
    assert result.wasOptimized is True
    assert [attempt.passed for attempt in result.attempts] == [False, True]
    assert result.tokensSaved == 12

#The retry feedback is added to a copy, so the audit's own issue list is left alone
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
