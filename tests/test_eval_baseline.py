"""
Offline tests for the eval runner (scripts/eval_baseline.py) and its eval set. No API calls:
runPipeline and the agents' clients are faked.
"""
from types import SimpleNamespace
import pytest
from scripts import eval_baseline
from agents.auditor import AuditResult
from agents.orchestrator import OrchestrationResult, fillerOnlyValidation
from agents.validator import ValidationResult


def makeResult(**overrides) -> OrchestrationResult:
    fields = dict(originalPrompt="Please write a haiku about autumn.", finalPrompt="Write a haiku about autumn.",
                  wasOptimized=True, auditResult=AuditResult(token_count=8, estimatedCost=0.0, issues=["filler"]),
                  tokensSaved=1, percentSaved=12.5)
    fields.update(overrides)
    return OrchestrationResult(**fields)


def validation(passed: bool, score: int = 8) -> ValidationResult:
    return ValidationResult("a", "b", score, passed, "reason")


#Fake client whose create returns a response with usage, like the Anthropic SDK
def fakeClient():
    usage = SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=50,
                            cache_creation_input_tokens=0)
    response = SimpleNamespace(usage=usage, stop_reason="tool_use")
    return SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: response))


@pytest.fixture
def recorder(monkeypatch):
    for module in eval_baseline.LLM_AGENTS.values():
        monkeypatch.setattr(module, "client", fakeClient())
    return eval_baseline.CallRecorder("chatgpt")


#The eval set itself: unique ids, a known expect, and every mustKeep string really in its prompt
def test_eval_set_is_well_formed():
    cases = eval_baseline.loadCases(eval_baseline.DEFAULT_CASES)
    assert len(cases) >= 30
    assert len({case["id"] for case in cases}) == len(cases)
    for case in cases:
        assert case["expect"] in eval_baseline.EXPECTED_OUTCOMES, case["id"]
        for keep in case["mustKeep"]:
            assert keep in case["prompt"], (case["id"], keep)


def test_outcomeOf():
    assert eval_baseline.outcomeOf(makeResult(attempts=[validation(True)])) == "optimized"
    filler = fillerOnlyValidation("Please write a haiku.", "Write a haiku.")
    assert eval_baseline.outcomeOf(makeResult(attempts=[validation(False), filler])) == "fillerOnly"
    assert eval_baseline.outcomeOf(makeResult(wasOptimized=False, needsClarification=True)) == "ask"
    assert eval_baseline.outcomeOf(makeResult(wasOptimized=False)) == "unchanged"
    assert eval_baseline.outcomeOf(makeResult(wasOptimized=False, error="Optimizer call failed")) == "error"


def test_expectMet_counts_vague_unchanged_as_ask():
    from agents.vagueness import VaguenessReport
    vague = makeResult(wasOptimized=False, vagueness=VaguenessReport(level="vague", questions=["Which essay?"]))
    clear = makeResult(wasOptimized=False)
    assert eval_baseline.expectMet("ask", "unchanged", vague) is True
    assert eval_baseline.expectMet("ask", "unchanged", clear) is False
    assert eval_baseline.expectMet("unchanged", "unchanged", vague) is True
    assert eval_baseline.expectMet(None, "unchanged", clear) is None


def test_recorder_counts_calls_per_agent(recorder):
    eval_baseline.optimizer.client.messages.create(model="claude-sonnet-5-5")
    eval_baseline.optimizer.client.messages.create(model="claude-sonnet-5-5")
    eval_baseline.validator.client.messages.create(model="claude-sonnet-4-6")
    summary = eval_baseline.summarizeCalls(recorder.calls)
    assert summary["llmCalls"] == 3
    assert summary["optimizerTurns"] == 2
    assert summary["validatorCalls"] == 1
    assert summary["tokensPerModel"]["claude-sonnet-5-5"]["input_tokens"] == 200
    assert summary["tokensPerModel"]["claude-sonnet-5-5"]["cache_read_input_tokens"] == 100


def test_recorder_records_and_reraises_errors(monkeypatch, recorder):
    def fail(**kwargs):
        raise RuntimeError("down")
    monkeypatch.setattr(eval_baseline.validator, "client", SimpleNamespace(messages=SimpleNamespace(create=fail)))
    recorder = eval_baseline.CallRecorder("chatgpt")
    with pytest.raises(RuntimeError):
        eval_baseline.validator.client.messages.create(model="claude-haiku-5-5")
    assert recorder.calls[0]["error"] == "RuntimeError"


def test_runCase_builds_record(monkeypatch, recorder):
    def fakePipeline(prompt, target, hook):
        hook.updateStage("optimizing")
        eval_baseline.optimizer.client.messages.create(model="claude-sonnet-5-5")
        eval_baseline.validator.client.messages.create(model="claude-sonnet-4-6")
        return makeResult(originalPrompt=prompt, attempts=[validation(True)])
    monkeypatch.setattr(eval_baseline, "runPipeline", fakePipeline)
    case = {"id": "haiku", "category": "filler", "prompt": "Please write a haiku about autumn.",
            "mustKeep": ["haiku", "autumn", "leaves"], "expect": "optimize"}
    record = eval_baseline.runCase(case, "chatgpt", recorder)
    assert record["outcome"] == "optimized"
    assert record["expectMet"] is True
    assert record["missingMustKeep"] == ["leaves"]
    assert record["llmCalls"] == 2
    assert record["stages"] == ["optimizing"]


def test_runCase_records_crash(monkeypatch, recorder):
    def crash(prompt, target, hook):
        raise ValueError("boom")
    monkeypatch.setattr(eval_baseline, "runPipeline", crash)
    record = eval_baseline.runCase({"id": "x", "category": "c", "prompt": "p", "mustKeep": [], "expect": "ask"},
                                   "chatgpt", recorder)
    assert record["outcome"] == "crash"
    assert record["expectMet"] is False
    assert "boom" in record["crash"]


def test_summarize():
    calls = eval_baseline.summarizeCalls([])
    base = {"category": "filler", "expect": "optimize", "missingMustKeep": [], "rewriteProblems": [],
            "originalTokens": 20, "percentSaved": 0.0, "tokensSaved": 0, "attemptPassed": [], **calls}
    records = [
        {**base, "id": "a", "outcome": "optimized", "expectMet": True, "tokensSaved": 5, "percentSaved": 25.0,
         "attemptPassed": [False, True], "optimizerTurns": 2, "validatorCalls": 2, "llmCalls": 4, "latencyMs": 3000},
        {**base, "id": "b", "outcome": "unchanged", "expectMet": False, "latencyMs": 10,
         "missingMustKeep": ["x"]},
        {**base, "id": "c", "outcome": "crash", "expectMet": False, "latencyMs": 5},
    ]
    summary = eval_baseline.summarize(records)
    assert summary["runs"] == 3
    assert summary["outcomes"]["crash"] == 1
    assert summary["expectMatchRate"] == 0.5  #the crash has no expectation result to count
    assert summary["expectMisses"] == ["b"]
    assert summary["totalTokensSaved"] == 5
    assert summary["meanPercentSavedOptimized"] == 25.0
    assert summary["mustKeepViolations"] == ["b"]
    assert summary["firstAttemptPassRate"] == 0.0
    assert summary["attemptPassRate"] == 0.5
    assert summary["optimizerTurnsMean"] == 2
    assert summary["crashes"] == ["c"]


def test_percentile():
    assert eval_baseline.percentile([], 50) is None
    assert eval_baseline.percentile([1, 2, 3, 4], 50) == 2
    assert eval_baseline.percentile(list(range(1, 101)), 95) == 95


#Every model the agents call has a price, so the eval's pipeline cost leaves nothing out. The Auditor makes
#no LLM call of its own (11/4/2026), so only the Optimizer and Validator's models are checked here
def test_loadPricing_prices_the_agents_models():
    prices, savedTokenPrice = eval_baseline.loadPricing()
    for model in (eval_baseline.optimizer.OPTIMIZER_MODEL, eval_baseline.validator.VALIDATOR_MODEL, "claude-sonnet-4-6"):
        assert model in prices, model
    sonnet = prices["claude-sonnet-5-5"]
    assert sonnet["input_tokens"] == pytest.approx(2 / 1_000_000)
    assert sonnet["cache_read_input_tokens"] == pytest.approx(0.2 / 1_000_000)
    assert sonnet["cache_creation_input_tokens"] == pytest.approx(2.5 / 1_000_000)
    assert savedTokenPrice == pytest.approx(2 / 1_000_000)
    assert eval_baseline.loadPricing("claude-opus-5-5")[1] == pytest.approx(4 / 1_000_000)
    with pytest.raises(KeyError):
        eval_baseline.loadPricing("no-such-model")


def test_summarize_costs():
    pricing = ({"m": {"input_tokens": 1.0, "output_tokens": 2.0, "cache_read_input_tokens": 0.5,
                      "cache_creation_input_tokens": 3.0}}, 0.25)
    base = {"category": "filler", "expect": "optimize", "expectMet": True, "missingMustKeep": [],
            "rewriteProblems": [], "originalTokens": 20, "percentSaved": 0.0, "attemptPassed": [],
            **eval_baseline.summarizeCalls([])}
    usage = {"input_tokens": 1, "output_tokens": 1, "cache_read_input_tokens": 2, "cache_creation_input_tokens": 1}
    records = [
        {**base, "id": "a", "outcome": "optimized", "tokensSaved": 8, "llmCalls": 2, "latencyMs": 3000,
         "tokensPerModel": {"m": usage, "unknown-model": {"input_tokens": 5}}},
        {**base, "id": "b", "outcome": "unchanged", "tokensSaved": 0, "latencyMs": 10},
    ]
    summary = eval_baseline.summarize(records, pricing)
    assert summary["pipelineCostUsd"] == 7.0  #1 + 2 + 2*0.5 + 3, the unpriced model left out
    assert summary["unpricedModels"] == ["unknown-model"]
    assert summary["pipelineCostPerRunUsd"] == 3.5
    assert summary["pipelineCostPerLLMRunUsd"] == 7.0
    assert summary["savedValueUsd"] == 2.0
    assert summary["netSavingsUsd"] == -5.0
    assert summary["breakEvenSends"] == 3.5
    assert eval_baseline.summarize(records[1:], pricing)["breakEvenSends"] is None
