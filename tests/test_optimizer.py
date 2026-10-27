"""
Offline unit tests for second agent
"""
from pathlib import Path
from types import SimpleNamespace
import pytest
#anthropic 1.x is built on httpx2 and 0.x on httpx; build the fake request with whichever the SDK uses
try:
    import httpx2 as httpx
except ImportError:
    import httpx
from anthropic import APIConnectionError
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


#A tool call block, as the optimizer LLM would send it
def toolUse(name, toolInput, blockId="toolu_1"):
    return SimpleNamespace(type="tool_use", id=blockId, name=name, input=toolInput)

#One turn that only submits this rewrite
def submitTurn(rewrite, blockId="toolu_1"):
    return [toolUse(optimizer.SUBMIT_TOOL, rewrite.model_dump(), blockId)]

#One turn with text and no tool call
TEXT_TURN = [SimpleNamespace(type="text", text="Here is my rewrite.")]


#Fake Anthropic client that records each request and plays back one scripted turn per call,
#repeating the last turn once the script runs out
class FakeMessages:
    def __init__(self, turns, stopReason):
        self.turns = turns
        self.stopReason = stopReason
        self.requests = []

    @property
    def lastRequest(self):
        return self.requests[-1]

    def create(self, **kwargs):
        self.requests.append(kwargs)
        content = self.turns[min(len(self.requests), len(self.turns)) - 1]
        usage = SimpleNamespace(cache_read_input_tokens=0, cache_creation_input_tokens=0)
        stopReason = self.stopReason or ("tool_use" if any(b.type == "tool_use" for b in content) else "end_turn")
        return SimpleNamespace(content=content, stop_reason=stopReason, usage=usage)


#Installs a fake client. A string or Rewrite reply is submitted on the first turn, None is a
#reply that never calls a tool, and a list of turns is played back as given
@pytest.fixture
def fakeClient(monkeypatch):
    def install(reply, stopReason=None):
        if isinstance(reply, str):
            reply = makeRewrite(reply)
        if isinstance(reply, Rewrite):
            turns = [submitTurn(reply)]
        elif reply is None:
            turns = [TEXT_TURN]
        else:
            turns = reply
        fake = SimpleNamespace(messages=FakeMessages(turns, stopReason))
        monkeypatch.setattr(optimizer, "client", fake)
        return fake.messages
    return install

#The tool results the optimizer sent back after a given turn (1-based)
def toolResults(messages, turn):
    return messages.lastRequest["messages"][turn * 2]["content"]

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

#LLM call uses the cached optimizer system prompt and the tools, and strips whitespace from the rewrite
def test_callOptimizerLLM_sends_system_prompt_and_strips(fakeClient):
    messages = fakeClient("  Write a poem.\n")
    result = optimizer.callOptimizerLLM("Please write a poem.", ["Filler words"])

    assert result.optimizedPrompt == "Write a poem."
    assert messages.lastRequest["system"] == [{
        "type": "text",
        "text": optimizer.OPTIMIZER_SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }]
    assert messages.lastRequest["tools"] is optimizer.OPTIMIZER_TOOLS
    assert messages.lastRequest["cache_control"] == {"type": "ephemeral"}
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

#A refused, truncated or never-submitted reply falls back to the original prompt
@pytest.mark.parametrize("reply, stopReason", [
    (None, None),
    (makeRewrite("Write a poem"), "refusal"),
    (makeRewrite("Write a"), "max_tokens"),
])
def test_optimizePrompt_unusable_reply_keeps_original(fakeClient, reply, stopReason):
    fakeClient(reply, stopReason)
    result = optimizer.optimizePrompt("Please write a poem.")
    assert result.optimizedPrompt == "Please write a poem."
    assert result.tokensSaved == 0
    assert result.changes == []

#A failed API call is raised, not hidden as "unchanged", so the orchestrator can record it
def test_optimizePrompt_api_error_is_raised(monkeypatch):
    def fail(**kwargs):
        raise APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    monkeypatch.setattr(optimizer, "client", SimpleNamespace(messages=SimpleNamespace(create=fail)))
    with pytest.raises(APIConnectionError):
        optimizer.optimizePrompt("Please write a poem.")

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

#Must-preserve items are listed before the prompt; the section is left out when there are none
def test_buildUserMessage_with_must_preserve():
    message = optimizer.buildUserMessage("Please write a 300-word bio.", [], mustPreserve=['task: write "a bio"', "number: 300"])
    assert "must keep" in message and '- task: write "a bio"' in message and "- number: 300" in message
    assert message.index("number: 300") < message.index("PROMPT TO OPTIMIZE")
    assert "must keep" not in optimizer.buildUserMessage("Write a poem.", [])

#optimizePrompt passes the must-preserve list through to the LLM message
def test_optimizePrompt_forwards_must_preserve(fakeClient):
    messages = fakeClient("Write a 300-word bio.")
    optimizer.optimizePrompt("Please write a 300-word bio.", mustPreserve=["number: 300"])
    assert "- number: 300" in messages.lastRequest["messages"][0]["content"]

#The system prompt tells the Optimizer to keep options optional and never resolve vagueness itself
def test_system_prompt_keeps_options_and_vagueness():
    assert "maybe add tests" in optimizer.OPTIMIZER_SYSTEM_PROMPT
    assert "keep it exactly as vague" in optimizer.OPTIMIZER_SYSTEM_PROMPT

#Every tool is strict, and submit_rewrite takes exactly the Rewrite fields
def test_tools_are_strict():
    for tool in optimizer.OPTIMIZER_TOOLS:
        assert tool["strict"] is True
        assert tool["input_schema"]["additionalProperties"] is False
    submit = next(t for t in optimizer.OPTIMIZER_TOOLS if t["name"] == optimizer.SUBMIT_TOOL)
    assert set(submit["input_schema"]["required"]) == set(Rewrite.model_fields)

#The model can check a draft, see the result, and then submit it
def test_callOptimizerLLM_check_then_submit(fakeClient):
    rewrite = "Write a short story about a dragon."
    messages = fakeClient([
        [toolUse("check_rewrite", {"rewrite": rewrite})],
        submitTurn(makeRewrite(rewrite), "toolu_2"),
    ])
    result = optimizer.callOptimizerLLM("Please, could you write a short story about a dragon? Thanks!", [])

    assert result.optimizedPrompt == rewrite
    assert len(messages.requests) == 2
    [checkResult] = toolResults(messages, 1)
    assert checkResult["tool_use_id"] == "toolu_1"
    assert checkResult["is_error"] is False
    assert checkResult["content"].startswith("No problems found.")
    assert "Tokens: original" in checkResult["content"]

#check_rewrite lists what a draft dropped
def test_check_rewrite_reports_problems():
    report = optimizer.describeCheck("Write a bio in under 300 words.", "Write a bio.", "chatgpt")
    assert report.startswith("Problems:\n- ")
    assert "300" in report

#A submission that drops a lock is refused with the reasons, and the fixed one is accepted
def test_callOptimizerLLM_refuses_broken_submission(fakeClient):
    original = "Could you please write a bio for our CEO in under 300 words? Thanks!"
    messages = fakeClient([
        submitTurn(makeRewrite("Write a bio for our CEO.")),
        submitTurn(makeRewrite("Write a bio for our CEO in under 300 words."), "toolu_2"),
    ])
    result = optimizer.callOptimizerLLM(original, [])

    assert result.optimizedPrompt == "Write a bio for our CEO in under 300 words."
    [refusal] = toolResults(messages, 1)
    assert refusal["is_error"] is True
    assert refusal["content"].startswith("Refused.")
    assert "300" in refusal["content"]

#A model that never gets a submission through stops after MAX_TOOL_TURNS calls
def test_callOptimizerLLM_stops_at_turn_cap(fakeClient):
    original = "Could you please write a bio in under 300 words? Thanks!"
    messages = fakeClient(makeRewrite("Write a bio."))
    assert optimizer.callOptimizerLLM(original, []) is None
    assert len(messages.requests) == optimizer.MAX_TOOL_TURNS

#A turn with no tool call is answered with a reminder to submit
def test_callOptimizerLLM_reminds_to_submit(fakeClient):
    messages = fakeClient([TEXT_TURN, submitTurn(makeRewrite("Write a poem."))])
    result = optimizer.callOptimizerLLM("Please write a poem.", [])

    assert result.optimizedPrompt == "Write a poem."
    assert optimizer.SUBMIT_TOOL in messages.lastRequest["messages"][2]["content"]

#An unchanged submission isn't checked, since it is the original
def test_runTool_unchanged_submission_skips_check():
    rewrite = makeRewrite("Write a bio in under 300 words.", unchanged=True, changes=[])
    content, isError, submitted = optimizer.runTool(optimizer.SUBMIT_TOOL, rewrite.model_dump(), "Write a bio in under 300 words.", "chatgpt")
    assert (content, isError) == ("Submitted.", False)
    assert submitted.unchanged is True

#count_tokens counts with the target's tokenizer, and an unknown tool is reported as an error
def test_runTool_count_tokens_and_unknown_tool():
    content, isError, _ = optimizer.runTool("count_tokens", {"text": "Hello, world"}, "", "chatgpt")
    assert content == f"{optimizer.countTokens('Hello, world')} tokens" and isError is False
    assert optimizer.runTool("delete_everything", {}, "", "chatgpt")[1] is True

#An invalid submission is an error result, not a crash
def test_runTool_invalid_submission():
    content, isError, submitted = optimizer.runTool(optimizer.SUBMIT_TOOL, {"optimizedPrompt": "x"}, "Write x.", "chatgpt")
    assert isError is True and submitted is None
    assert content.startswith("Invalid submission")

#Every tool call in one turn gets a result, all in one message
def test_callOptimizerLLM_answers_parallel_calls_together(fakeClient):
    messages = fakeClient([
        [toolUse("count_tokens", {"text": "Write a poem."}, "toolu_1"),
         toolUse("check_rewrite", {"rewrite": "Write a poem."}, "toolu_2")],
        submitTurn(makeRewrite("Write a poem."), "toolu_3"),
    ])
    optimizer.callOptimizerLLM("Please write a poem.", [])
    assert [r["tool_use_id"] for r in toolResults(messages, 1)] == ["toolu_1", "toolu_2"]
