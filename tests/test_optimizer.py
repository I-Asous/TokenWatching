"""
Offline unit tests for second agent
"""
from pathlib import Path
from types import SimpleNamespace
import pytest
from agents import optimizer
from agents.optimizer import OptimizationResult, Rewrite, RejectedAttempt


#Builds the structured reply the optimizer LLM would return for a rewrite
def makeRewrite(prompt, unchanged=False, changes=None, constraints=None):
    return Rewrite(
        preservedConstraints=constraints or ["short story", "about a dragon"],
        unchanged=unchanged,
        optimizedPrompt=prompt,
        changes=changes if changes is not None else ["removed politeness phrasing"],
    )


#Fake Anthropic client that records the request and returns a canned parsed reply
class FakeMessages:
    def __init__(self, reply, stopReason):
        self.reply = reply
        self.stopReason = stopReason
        self.lastRequest = None

    def parse(self, **kwargs):
        self.lastRequest = kwargs
        usage = SimpleNamespace(cache_read_input_tokens=0, cache_creation_input_tokens=0)
        return SimpleNamespace(parsed_output=self.reply, stop_reason=self.stopReason, usage=usage)


@pytest.fixture
def fakeClient(monkeypatch):
    def install(reply, stopReason="end_turn"):
        if isinstance(reply, str):
            reply = makeRewrite(reply)
        fake = SimpleNamespace(messages=FakeMessages(reply, stopReason))
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

#Rejected rewrites are shown with their reasons, between the issues and the prompt
def test_buildUserMessage_with_rejected_attempts():
    rejected = [RejectedAttempt("Write a story.", "Dropped the dragon.")]
    message = optimizer.buildUserMessage("Please write a dragon story.", ["Filler words"], rejected)

    assert "<rejected_rewrite number=\"1\">\nWrite a story.\n</rejected_rewrite>" in message
    assert "Rejected because: Dropped the dragon." in message
    assert message.index("- Filler words") < message.index("<rejected_rewrite")
    assert message.endswith("PROMPT TO OPTIMIZE:\nPlease write a dragon story.")

#With no rejected attempts, no rejection section is added
def test_buildUserMessage_without_rejected_attempts():
    assert "rejected" not in optimizer.buildUserMessage("Write a poem.", [], []).lower()

#Rejected attempts given to optimizePrompt reach the LLM request
def test_optimizePrompt_forwards_rejected_attempts(fakeClient):
    messages = fakeClient("Write a dragon story.")
    rejected = [RejectedAttempt("Write a story.", "Dropped the dragon.")]
    optimizer.optimizePrompt("Please write a dragon story.", ["Filler words"], rejectedAttempts=rejected)

    userContent = messages.lastRequest["messages"][0]["content"]
    assert "Write a story." in userContent
    assert "Dropped the dragon." in userContent

#LLM call uses the optimizer system prompt and schema, and strips whitespace from the rewrite
def test_callOptimizerLLM_sends_system_prompt_and_strips(fakeClient):
    messages = fakeClient("  Write a poem.\n")
    result = optimizer.callOptimizerLLM("Please write a poem.", ["Filler words"])

    assert result.optimizedPrompt == "Write a poem."
    assert messages.lastRequest["system"] == [{
        "type": "text",
        "text": optimizer.OPTIMIZER_SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }]
    assert messages.lastRequest["output_format"] is Rewrite
    assert messages.lastRequest["model"] == optimizer.OPTIMIZER_MODEL
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
    assert result.changes == ["removed politeness phrasing"]
    assert result.preservedConstraints == ["short story", "about a dragon"]

#A prompt the LLM marks unchanged keeps the original text, even if the LLM rewrote it anyway
def test_optimizePrompt_unchanged_keeps_original(fakeClient):
    fakeClient(makeRewrite("Write poem.", unchanged=True, changes=[]))
    result = optimizer.optimizePrompt("Write a poem.")
    assert result.optimizedPrompt == "Write a poem."
    assert result.tokensSaved == 0
    assert result.changes == []

#A refused, truncated or unparseable reply falls back to the original prompt
@pytest.mark.parametrize("reply, stopReason", [
    (None, "end_turn"),
    (makeRewrite("Write a poem"), "refusal"),
    (makeRewrite("Write a"), "max_tokens"),
])
def test_optimizePrompt_unusable_reply_keeps_original(fakeClient, reply, stopReason):
    fakeClient(reply, stopReason)
    result = optimizer.optimizePrompt("Please write a poem.")
    assert result.optimizedPrompt == "Please write a poem."
    assert result.tokensSaved == 0
    assert result.changes == []

#An empty rewrite is never returned as the optimized prompt
def test_optimizePrompt_empty_rewrite_keeps_original(fakeClient):
    fakeClient("   ")
    result = optimizer.optimizePrompt("Please write a poem.")
    assert result.optimizedPrompt == "Please write a poem."

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

#Examples marked unchanged copy the input verbatim and list no edits, matching what the prompt asks for
@pytest.mark.parametrize("prompt, rewrite", optimizer.OPTIMIZER_EXAMPLES)
def test_examples_are_consistent(prompt, rewrite):
    assert rewrite.preservedConstraints
    if rewrite.unchanged:
        assert rewrite.optimizedPrompt == prompt
        assert rewrite.changes == []
    else:
        assert rewrite.optimizedPrompt != prompt
        assert rewrite.changes
        assert optimizer.countTokens(rewrite.optimizedPrompt) < optimizer.countTokens(prompt)

#The examples teach both outcomes, so the model doesn't learn to always rewrite
def test_examples_include_unchanged_cases():
    unchangedCount = sum(rewrite.unchanged for _, rewrite in optimizer.OPTIMIZER_EXAMPLES)
    assert unchangedCount >= 2

#Code in an example survives the rewrite character for character
def test_code_example_keeps_code_block():
    codeExamples = [(p, r) for p, r in optimizer.OPTIMIZER_EXAMPLES if "```" in p]
    assert codeExamples
    for prompt, rewrite in codeExamples:
        codeBlock = prompt[prompt.index("```"):prompt.rindex("```") + 3]
        assert codeBlock in rewrite.optimizedPrompt

#Every example is rendered into the system prompt
def test_system_prompt_contains_examples():
    for prompt, rewrite in optimizer.OPTIMIZER_EXAMPLES:
        assert prompt in optimizer.OPTIMIZER_SYSTEM_PROMPT
        assert rewrite.model_dump_json(indent=2) in optimizer.OPTIMIZER_SYSTEM_PROMPT

#The system prompt is long enough to be cached (Sonnet 5.5's minimum is 512 tokens), with margin
#since this is a ChatGPT-tokenizer estimate of a Claude count
def test_system_prompt_is_cacheable():
    assert optimizer.countTokens(optimizer.OPTIMIZER_SYSTEM_PROMPT) > 512 * 1.5

#No example reuses a prompt the __main__ cases test, so passing those cases still means something
def test_examples_do_not_reuse_main_cases():
    source = Path(optimizer.__file__).read_text(encoding="utf-8")
    mainBlock = source[source.index('if __name__ == "__main__":'):]
    for prompt, _ in optimizer.OPTIMIZER_EXAMPLES:
        assert prompt[:40] not in mainBlock
