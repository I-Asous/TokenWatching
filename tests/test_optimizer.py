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
    assert messages.lastRequest["output_config"] == {"effort": optimizer.OPTIMIZER_EFFORT}
    assert messages.lastRequest["thinking"] == optimizer.OPTIMIZER_THINKING
    assert messages.lastRequest["model"] == optimizer.OPTIMIZER_MODEL
    userContent = messages.lastRequest["messages"][0]["content"]
    assert "- Filler words" in userContent
    assert "Please write a poem." in userContent

#Haiku 5.5 returns a 400 for disabled thinking above effort "high"
def test_disabled_thinking_uses_an_accepted_effort():
    if optimizer.OPTIMIZER_THINKING["type"] == "disabled":
        assert optimizer.OPTIMIZER_EFFORT in ("low", "medium", "high")

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

#Every tool ends the task, so a clean rewrite takes one API call
def test_every_tool_ends_the_task(fakeClient):
    assert [tool["name"] for tool in optimizer.OPTIMIZER_TOOLS] == [
        optimizer.SUBMIT_TOOL, optimizer.LOCAL_TOOL, optimizer.ASK_TOOL]
    messages = fakeClient("Write a poem.")
    optimizer.callOptimizerLLM("Please write a poem.", [])
    assert len(messages.requests) == 1

LOCAL = OptimizationResult(originalPrompt="Hi! Please write a poem about rain. Thanks!",
                           optimizedPrompt="Write a poem about rain.", originalTokens=14, optimizedTokens=7,
                           tokensSaved=7, percentSaved=50.0, changes=["removed politeness and filler: 'Hi!'"])

#The tools are sent on every call even when a run doesn't offer them, so the cached prefix never changes
def test_tools_are_the_same_whatever_is_offered(fakeClient):
    messages = fakeClient("Write a poem.")
    optimizer.optimizePrompt("Please write a poem.", localResult=LOCAL, questions=["Q?"], maxQuestions=2)
    assert messages.lastRequest["tools"] is optimizer.OPTIMIZER_TOOLS

#Choosing the local rewrite returns it as is, marked "local"
def test_optimizePrompt_local_choice(fakeClient):
    fakeClient([[toolUse(optimizer.LOCAL_TOOL, {"reason": "Nothing more to cut."})]])
    result = optimizer.optimizePrompt(LOCAL.originalPrompt, localResult=LOCAL)
    assert result.action == "local"
    assert result.optimizedPrompt == LOCAL.optimizedPrompt
    assert result.tokensSaved == LOCAL.tokensSaved

#Asking keeps the original prompt, saves nothing, and returns the questions
def test_optimizePrompt_ask_user(fakeClient):
    fakeClient([[toolUse(optimizer.ASK_TOOL, {"questions": ["What goes wrong?"], "reason": "Nothing attached."})]])
    result = optimizer.optimizePrompt("Please fix this.", questions=["What goes wrong?"], maxQuestions=3)
    assert result.action == "ask_user"
    assert result.questions == ["What goes wrong?"]
    assert result.optimizedPrompt == "Please fix this."
    assert result.tokensSaved == 0

#A tool the run doesn't offer is refused, and the model can still submit on the next turn
@pytest.mark.parametrize("name, toolInput", [
    (optimizer.LOCAL_TOOL, {"reason": "r"}),
    (optimizer.ASK_TOOL, {"questions": ["Who is it for?"], "reason": "r"}),
])
def test_unoffered_tool_is_refused(fakeClient, name, toolInput):
    messages = fakeClient([[toolUse(name, toolInput)], submitTurn(makeRewrite("Write a poem."), "toolu_2")])
    result = optimizer.optimizePrompt("Please write a poem.")
    assert toolResults(messages, 1)[0]["is_error"] is True
    assert result.action == "rewrite"
    assert result.optimizedPrompt == "Write a poem."

#ask_user drops blank, repeated and already answered questions, and asks at most maxQuestions
def test_runTool_ask_user_cleans_questions():
    context = optimizer.ToolContext(maxQuestions=2, answered=["Who is it for?"])
    toolInput = {"questions": [" How long? ", "", "who is it for?", "How long?", "Which tone?", "Which format?"],
                 "reason": "r"}
    content, isError, choice = optimizer.runTool(optimizer.ASK_TOOL, toolInput, "Write a post.", context)
    assert isError is False
    assert choice.questions == ["How long?", "Which tone?"]

#ask_user with only answered questions is refused
def test_runTool_ask_user_refuses_answered_questions():
    context = optimizer.ToolContext(maxQuestions=2, answered=["Who is it for?"])
    content, isError, choice = optimizer.runTool(optimizer.ASK_TOOL, {"questions": ["Who is it for?"], "reason": "r"},
                                                 "Write a post.", context)
    assert isError is True and choice is None

#ask_user is offered only when there are questions to suggest
def test_optimizePrompt_no_questions_no_ask(fakeClient):
    messages = fakeClient([[toolUse(optimizer.ASK_TOOL, {"questions": ["Who?"], "reason": "r"})],
                           submitTurn(makeRewrite("Write a poem."), "toolu_2")])
    optimizer.optimizePrompt("Please write a poem.", questions=[], maxQuestions=3)
    assert toolResults(messages, 1)[0]["is_error"] is True

#A submission is checked against checkAgainst when set, so a number the person gave in an answer may be used
def test_submission_checked_against_answers():
    prompt = "Please write a blog post about remote work.\n\nHow long should it be? 300 words"
    context = optimizer.ToolContext(checkAgainst="Please write a blog post about remote work.\n\n300 words")
    rewrite = makeRewrite("Write a 300-word blog post about remote work.")
    assert optimizer.runTool(optimizer.SUBMIT_TOOL, rewrite.model_dump(), "Write a blog post.")[1] is True
    content, isError, submitted = optimizer.runTool(optimizer.SUBMIT_TOOL, rewrite.model_dump(), prompt, context)
    assert isError is False, content

#The message lists the answers, the questions that may be asked and the local rewrite, before the prompt
def test_buildUserMessage_with_offers():
    context = optimizer.ToolContext(localRewrite="Write a poem.", maxQuestions=2)
    message = optimizer.buildUserMessage("Please write a poem.", [], answers=[optimizer.Answer("About what?", "rain")],
                                         questions=["How long?"], context=context, localSaved=3)
    assert "- About what? -> rain" in message
    assert "at most 2" in message and "- How long?" in message
    assert "<local_rewrite>\nWrite a poem.\n</local_rewrite>" in message and "saves 3 tokens" in message
    assert message.endswith("PROMPT TO OPTIMIZE:\nPlease write a poem.")

#Without offers, none of those sections are added
def test_buildUserMessage_without_offers():
    message = optimizer.buildUserMessage("Write a poem.", [], questions=["How long?"])
    assert message == "PROMPT TO OPTIMIZE:\nWrite a poem."

#Every tool is strict, and submit_rewrite takes exactly the Rewrite fields
def test_tools_are_strict():
    for tool in optimizer.OPTIMIZER_TOOLS:
        assert tool["strict"] is True
        assert tool["input_schema"]["additionalProperties"] is False
    submit = next(t for t in optimizer.OPTIMIZER_TOOLS if t["name"] == optimizer.SUBMIT_TOOL)
    assert set(submit["input_schema"]["required"]) == set(Rewrite.model_fields)

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
    content, isError, submitted = optimizer.runTool(optimizer.SUBMIT_TOOL, rewrite.model_dump(), "Write a bio in under 300 words.")
    assert (content, isError) == ("Submitted.", False)
    assert submitted.unchanged is True

#A tool that no longer exists, or never did, is reported as an error
@pytest.mark.parametrize("name", ["check_rewrite", "count_tokens", "delete_everything"])
def test_runTool_unknown_tool(name):
    assert optimizer.runTool(name, {}, "")[1] is True

#An invalid submission is an error result, not a crash
def test_runTool_invalid_submission():
    content, isError, submitted = optimizer.runTool(optimizer.SUBMIT_TOOL, {"optimizedPrompt": "x"}, "Write x.")
    assert isError is True and submitted is None
    assert content.startswith("Invalid submission")

#Every tool call in one turn gets a result, all in one message
def test_callOptimizerLLM_answers_parallel_calls_together(fakeClient):
    broken = makeRewrite("Write a bio.").model_dump()
    messages = fakeClient([
        [toolUse(optimizer.SUBMIT_TOOL, broken, "toolu_1"), toolUse(optimizer.SUBMIT_TOOL, broken, "toolu_2")],
        submitTurn(makeRewrite("Write a bio in under 300 words."), "toolu_3"),
    ])
    optimizer.callOptimizerLLM("Please write a bio in under 300 words.", [])
    assert [r["tool_use_id"] for r in toolResults(messages, 1)] == ["toolu_1", "toolu_2"]

#Type rules are listed after the issues and before the prompt, one bullet per type
def test_buildUserMessage_with_type_rules():
    message = optimizer.buildUserMessage("Please fix my code.", ["Filler words"],
                                         typeRules="Code prompt: never change code.\nSecurity prompt: keep every rule.")
    assert "Rules for this kind of prompt:\n- Code prompt: never change code.\n- Security prompt: keep every rule." in message
    assert message.index("- Filler words") < message.index("Rules for this kind") < message.index("PROMPT TO OPTIMIZE")

#Without type rules, no section is added
def test_buildUserMessage_without_type_rules():
    assert "Rules for this kind" not in optimizer.buildUserMessage("Write a poem.", [])


#Records each rewrite it's asked to validate and plays back scripted verdicts, like the orchestrator's
#SubmissionValidator without the Validator call
class FakeValidate:
    def __init__(self, *verdicts):
        self.verdicts = list(verdicts)
        self.rewrites = []

    def __call__(self, rewrite):
        self.rewrites.append(rewrite.optimizedPrompt)
        passed = self.verdicts[min(len(self.rewrites), len(self.verdicts)) - 1]
        return optimizer.ValidationResult("original", rewrite.optimizedPrompt, 8 if passed else 3, passed,
                                          "Fine." if passed else "Dropped the dragon.")

POLITE = "Hi there! Please write me a short story about a brave dragon. Thank you so much, I really appreciate it!"
STORY = "Write a short story about a brave dragon."

#A submission that saves too little is refused with the measured saving, and an unchanged one then ends the run
def test_submission_saving_too_little_is_refused(fakeClient):
    messages = fakeClient([submitTurn(makeRewrite(POLITE.replace("Hi there! ", ""))),
                           submitTurn(makeRewrite(POLITE, unchanged=True, changes=[]), "toolu_2")])
    result = optimizer.optimizePrompt(POLITE, minTokensSaved=10, minPercentSaved=2.0)
    assert "must cut at least 10 of them" in messages.requests[0]["messages"][0]["content"]
    [refusal] = toolResults(messages, 1)
    assert refusal["is_error"] is True
    assert "saves 3 tokens" in refusal["content"] and "at least 10 tokens" in refusal["content"]
    assert result.optimizedPrompt == POLITE

#With a minimum saving, the message gives the prompt's size and the fewest tokens to cut, before the prompt
def test_buildUserMessage_with_saving_minimum():
    context = optimizer.ToolContext(minTokensSaved=5, minPercentSaved=2.0)
    message = optimizer.buildUserMessage(POLITE, [], context=context)
    assert f"This prompt is {optimizer.countTokens(POLITE)} tokens" in message
    assert "must cut at least 5 of them" in message
    assert message.index("must cut") < message.index("PROMPT TO OPTIMIZE")

#No minimum, or a zero one (a prompt with answers), adds no saving line
@pytest.mark.parametrize("minimum", [None, 0])
def test_buildUserMessage_without_saving_minimum(minimum):
    context = optimizer.ToolContext(minTokensSaved=minimum)
    assert "must cut" not in optimizer.buildUserMessage(POLITE, [], context=context)

#The number the message asks for is the saving check's own bar: the larger of the token and percent minimums.
#A rewrite cutting exactly that many passes, one token less is refused
def test_tokensToSave_matches_the_saving_check(monkeypatch):
    counts = {"short": 30, "long": 400, "cut 8": 392, "cut 7": 393}
    monkeypatch.setattr(optimizer, "countTokens", lambda text, target: counts[text])
    monkeypatch.setattr(optimizer, "findRewriteProblems", lambda original, rewrite: [])
    context = optimizer.ToolContext(minTokensSaved=5, minPercentSaved=2.0)
    assert optimizer.tokensToSave("short", context) == 5
    assert optimizer.tokensToSave("long", context) == 8
    assert optimizer.findSubmissionProblems(makeRewrite("cut 8"), "long", context) is None
    assert optimizer.findSubmissionProblems(makeRewrite("cut 7"), "long", context).startswith("Refused")

#With a zero minimum (a prompt with answers), only a rewrite longer than the prompt is refused
def test_submission_longer_than_prompt_is_refused():
    context = optimizer.ToolContext(minTokensSaved=0)
    longer = makeRewrite(STORY + " Make it good.").model_dump()
    assert optimizer.runTool(optimizer.SUBMIT_TOOL, longer, STORY + " ", context)[1] is True
    shorter = makeRewrite("Write a story about a brave dragon.").model_dump()
    assert optimizer.runTool(optimizer.SUBMIT_TOOL, shorter, STORY, context)[1] is False

#A failed validation is refused with the reviewer's reasoning, and the fixed rewrite is accepted
def test_failed_validation_is_refused_then_fixed(fakeClient):
    validate = FakeValidate(False, True)
    messages = fakeClient([submitTurn(makeRewrite("Write a short story about a dragon.")),
                           submitTurn(makeRewrite(STORY), "toolu_2")])
    result = optimizer.optimizePrompt(POLITE, minTokensSaved=5, validate=validate)
    [refusal] = toolResults(messages, 1)
    assert refusal["is_error"] is True
    assert "Dropped the dragon." in refusal["content"] and "1 review left" in refusal["content"]
    assert validate.rewrites == ["Write a short story about a dragon.", STORY]
    assert result.optimizedPrompt == STORY

#Validation only runs once the local checks pass, so a broken rewrite never costs a Validator call
def test_local_problems_are_refused_before_validating(fakeClient):
    validate = FakeValidate(True)
    original = "Could you please write a bio for our CEO in under 300 words? Thanks!"
    fakeClient([submitTurn(makeRewrite("Write a bio for our CEO.")),
                submitTurn(makeRewrite("Write a bio for our CEO in under 300 words."), "toolu_2")])
    optimizer.optimizePrompt(original, validate=validate)
    assert validate.rewrites == ["Write a bio for our CEO in under 300 words."]

#Once every validation has failed, the run stops without spending the remaining turns
def test_loop_stops_when_validations_run_out(fakeClient):
    validate = FakeValidate(False)
    messages = fakeClient(makeRewrite(STORY))
    result = optimizer.optimizePrompt(POLITE, validate=validate)
    assert len(validate.rewrites) == optimizer.MAX_VALIDATIONS
    assert len(messages.requests) == optimizer.MAX_VALIDATIONS
    assert result.optimizedPrompt == POLITE and result.tokensSaved == 0

#After an accepted submission, a second one in the same turn isn't run, so it can't spend a validation
def test_parallel_submission_after_accepted_one_is_skipped(fakeClient):
    validate = FakeValidate(True)
    fakeClient([[toolUse(optimizer.SUBMIT_TOOL, makeRewrite(STORY).model_dump(), "toolu_1"),
                 toolUse(optimizer.SUBMIT_TOOL, makeRewrite("Write a dragon story.").model_dump(), "toolu_2")]])
    result = optimizer.optimizePrompt(POLITE, validate=validate)
    assert validate.rewrites == [STORY]
    assert result.optimizedPrompt == STORY

#A copy of the prompt counts as unchanged even when not marked, so it's never validated
def test_copy_of_prompt_is_unchanged():
    validate = FakeValidate(True)
    context = optimizer.ToolContext(minTokensSaved=0, validate=validate)
    content, isError, submitted = optimizer.runTool(optimizer.SUBMIT_TOOL, makeRewrite(STORY).model_dump(),
                                                    STORY, context)
    assert (content, isError) == ("Submitted.", False)
    assert submitted.unchanged is True and validate.rewrites == []

#rewriteResult keeps the prompt for a missing or unchanged rewrite and never reports a negative saving
def test_rewriteResult():
    assert optimizer.rewriteResult(STORY, None).optimizedPrompt == STORY
    kept = optimizer.rewriteResult(STORY, makeRewrite("Something else", unchanged=True))
    assert kept.optimizedPrompt == STORY and kept.tokensSaved == 0
    longer = optimizer.rewriteResult(STORY, makeRewrite(STORY + " Make it long and detailed."))
    assert longer.tokensSaved == 0 and longer.percentSaved == 0.0
    shorter = optimizer.rewriteResult(POLITE, makeRewrite(STORY))
    assert shorter.tokensSaved > 0 and shorter.changes == ["removed politeness phrasing"]
