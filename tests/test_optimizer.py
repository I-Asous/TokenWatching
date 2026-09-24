"""
Offline unit tests for second agent
"""
from types import SimpleNamespace
import pytest
from agents import optimizer
from agents.optimizer import OptimizationResult


#Fake Anthropic client that records the request and returns a canned reply
class FakeMessages:
    def __init__(self, reply):
        self.reply = reply
        self.lastRequest = None

    def create(self, **kwargs):
        self.lastRequest = kwargs
        return SimpleNamespace(content=[SimpleNamespace(text=self.reply)])


@pytest.fixture
def fakeClient(monkeypatch):
    def install(reply):
        fake = SimpleNamespace(messages=FakeMessages(reply))
        monkeypatch.setattr(optimizer, "client", fake)
        return fake.messages
    return install

#Token counting returns a positive count for text and zero for empty input
def test_countTokens_counts_nonempty_text():
    assert optimizer.countTokens("Hello, world") > 0
    assert optimizer.countTokens("") == 0

#With no issues, the message is just the delimited prompt
def test_buildUserMessage_without_issues():
    message = optimizer.buildUserMessage("Write a poem.", [])
    assert message == "PROMPT TO OPTIMIZE:\nWrite a poem."
    assert "Known issues" not in message

#Issues from Agent 1 are listed as bullets before the prompt
def test_buildUserMessage_with_issues():
    message = optimizer.buildUserMessage("Write a poem.", ["Filler words", "Blank lines"])
    assert message.startswith("Known issues found in prompt:\n")
    assert "- Filler words\n- Blank lines" in message
    assert message.endswith("PROMPT TO OPTIMIZE:\nWrite a poem.")

#LLM call uses the optimizer system prompt and strips whitespace from the reply
def test_callOptimizerLLM_sends_system_prompt_and_strips(fakeClient):
    messages = fakeClient("  Write a poem.\n")
    result = optimizer.callOptimizerLLM("Please write a poem.", ["Filler words"])

    assert result == "Write a poem."
    assert messages.lastRequest["system"] == optimizer.OPTIMIZER_SYSTEM_PROMPT
    userContent = messages.lastRequest["messages"][0]["content"]
    assert "- Filler words" in userContent
    assert "Please write a poem." in userContent

#A shorter rewrite produces correct token savings and percent
def test_optimizePrompt_computes_savings(fakeClient):
    original = "Please, could you kindly help me write a short story about a dragon? Thank you so much!"
    optimized = "Write a short story about a dragon."
    fakeClient(optimized)

    result = optimizer.optimizePrompt(original)
    originalTokens = optimizer.countTokens(original)
    optimizedTokens = optimizer.countTokens(optimized)

    assert isinstance(result, OptimizationResult)
    assert result.originalPrompt == original
    assert result.optimizedPrompt == optimized
    assert result.originalTokens == originalTokens
    assert result.optimizedTokens == optimizedTokens
    assert result.tokensSaved == originalTokens - optimizedTokens
    assert result.percentSaved == round((originalTokens - optimizedTokens) / originalTokens * 100, 2)

#A longer rewrite never reports negative savings
def test_optimizePrompt_never_negative(fakeClient):
    fakeClient("Write a short story about a dragon with lots of extra added words.")
    result = optimizer.optimizePrompt("Write a story.")
    assert result.tokensSaved == 0
    assert result.percentSaved == 0.0

#Empty prompt avoids division by zero
def test_optimizePrompt_empty_prompt(fakeClient):
    fakeClient("")
    result = optimizer.optimizePrompt("")
    assert result.originalTokens == 0
    assert result.percentSaved == 0.0

#Issues default to an empty list when not provided
def test_optimizePrompt_default_issues(fakeClient):
    messages = fakeClient("Write a poem.")
    optimizer.optimizePrompt("Write a poem.")
    assert "Known issues" not in messages.lastRequest["messages"][0]["content"]

#Table shows both prompts with their token counts and costs
def test_formatComparisonTable_contains_prompts_and_counts():
    result = OptimizationResult(
        originalPrompt="Please kindly write a poem.",
        optimizedPrompt="Write a poem.",
        originalTokens=6,
        optimizedTokens=4,
        tokensSaved=2,
        percentSaved=33.33,
    )
    table = optimizer.formatComparisonTable(result)

    assert "Please kindly write a poem." in table
    assert "Write a poem." in table
    assert "| Original " in table and "| Optimized " in table
    assert "33.33%" in table
    assert "Tokens" in table and "Cost / 1K Runs" in table

#Long prompts wrap onto multiple lines and every line has the same width
def test_formatComparisonTable_wraps_long_prompts():
    longPrompt = "word " * 40
    result = OptimizationResult(longPrompt, "word", 40, 1, 39, 97.5)
    table = optimizer.formatComparisonTable(result, promptWidth=20)

    lines = table.split("\n")
    assert len({len(line) for line in lines}) == 1
    assert all(len(line) < 80 for line in lines)
