"""
Offline unit tests for third agent
"""
from types import SimpleNamespace
import pytest
from agents import validator
from agents.validator import ValidationResult


#Fake Anthropic client that records the request and returns a canned reply
#Haiku 5.5 thinks by default, so the reply starts with a thinking block (empty text, as the API returns it)
class FakeMessages:
    def __init__(self, reply, stopReason="end_turn", thinking=True):
        self.reply = reply
        self.stopReason = stopReason
        self.thinking = thinking
        self.calls = 0
        self.lastRequest = None

    def create(self, **kwargs):
        self.calls += 1
        self.lastRequest = kwargs
        content = [SimpleNamespace(type="thinking", thinking="", signature="sig")] if self.thinking else []
        if self.reply is not None:
            content.append(SimpleNamespace(type="text", text=self.reply))
        return SimpleNamespace(content=content, stop_reason=self.stopReason)


@pytest.fixture
def fakeClient(monkeypatch):
    def install(reply, stopReason="end_turn", thinking=True):
        fake = SimpleNamespace(messages=FakeMessages(reply, stopReason, thinking))
        monkeypatch.setattr(validator, "client", fake)
        return fake.messages
    return install

#Both prompts are included and labeled in the message
def test_buildUserMessage_labels_both_prompts():
    message = validator.buildUserMessage("Please write a poem.", "Write a poem.")
    assert message == "original prompt:\nPlease write a poem.\n\noptimized prompt:\nWrite a poem."

#Type rules come first, one bullet per type, with the note that weakening one is a loss
def test_buildUserMessage_with_type_rules():
    message = validator.buildUserMessage("Please fix my code.", "Fix my code.",
                                         typeRules="Code prompt: never change code.\nSecurity prompt: keep every rule.")
    assert "- Code prompt: never change code.\n- Security prompt: keep every rule." in message
    assert "meaningful loss (score 3-5)" in message
    assert message.index("Code prompt") < message.index("original prompt:") < message.index("optimized prompt:")

#The type rules reach the request sent to the LLM
def test_validatePrompt_sends_type_rules(fakeClient):
    messages = fakeClient("SCORE: 8\nPASSED: Yes\nREASON: Fine.")
    validator.validatePrompt("Please fix my code.", "Fix my code.", typeRules="Code prompt: never change code.")
    assert "- Code prompt: never change code." in messages.lastRequest["messages"][0]["content"]

#A well-formed reply is parsed into score, passed and reason, with no trace
def test_parseValidatorReply_well_formed():
    reply = "SCORE: 8.5\nPASSED: Yes\nREASON: Only filler was removed."
    score, passed, reason, trace = validator.parseValidatorReply(reply)
    assert score == 8.5
    assert passed is True
    assert reason == "Only filler was removed."
    assert trace == ""

#Field labels are matched case-insensitively and surrounding whitespace is ignored
def test_parseValidatorReply_case_and_whitespace():
    reply = "\n  score: 3\n  passed: no\n  reason: Dropped the word limit.  \n"
    score, passed, reason, _ = validator.parseValidatorReply(reply)
    assert score == 3.0
    assert passed is False
    assert reason == "Dropped the word limit."

#Any text before SCORE is kept as the reasoning trace
def test_parseValidatorReply_keeps_trace():
    reply = "THINK: both ask for a dragon story.\nANSWER: same intent.\nSCORE: 9\nPASSED: Yes\nREASON: Same."
    _, _, _, trace = validator.parseValidatorReply(reply)
    assert trace == "THINK: both ask for a dragon story.\nANSWER: same intent."

#A reply with no recognizable fields falls back to safe defaults
def test_parseValidatorReply_unparseable_uses_defaults():
    reply = "I think these prompts are pretty similar."
    score, passed, reason, trace = validator.parseValidatorReply(reply)
    assert score == 1
    assert passed is False
    assert reason == "Could not parse Agent 3, Validator, response."
    assert trace == reply

#A non-numeric score doesn't raise and keeps the default
def test_parseValidatorReply_bad_score():
    score, passed, _, _ = validator.parseValidatorReply("SCORE: high\nPASSED: Yes\nREASON: ok")
    assert score == 1
    assert passed is True

#LLM call sends the validator system prompt and both prompts
def test_callValidatorLLM_sends_system_prompt(fakeClient):
    messages = fakeClient("SCORE: 7\nPASSED: Yes\nREASON: Fine.")
    result = validator.callValidatorLLM("Please write a poem.", "Write a poem.")

    assert result == (7.0, True, "Fine.", "")
    assert messages.lastRequest["system"] == validator.VALIDATOR_SYSTEM_PROMPT
    userContent = messages.lastRequest["messages"][0]["content"]
    assert "Please write a poem." in userContent
    assert "Write a poem." in userContent

#The verdict is read from the text block, after any thinking block, at low effort
def test_callValidatorLLM_skips_thinking_block(fakeClient):
    messages = fakeClient("SCORE: 8\nPASSED: Yes\nREASON: Only filler was removed.")
    result = validator.callValidatorLLM("Please write a poem.", "Write a poem.")

    assert result == (8.0, True, "Only filler was removed.", "")
    assert messages.lastRequest["output_config"] == {"effort": validator.VALIDATOR_EFFORT}
    assert messages.lastRequest["model"] == validator.VALIDATOR_MODEL

#A reply without thinking is read the same way
def test_callValidatorLLM_without_thinking(fakeClient):
    fakeClient("SCORE: 7\nPASSED: Yes\nREASON: Fine.", thinking=False)
    assert validator.callValidatorLLM("Please write a poem.", "Write a poem.") == (7.0, True, "Fine.", "")

#A reply cut off by max_tokens, refused, or with no text raises instead of scoring the rewrite 1
@pytest.mark.parametrize("reply, stopReason", [
    ("READ: - a poem\nANSWER: yes\nTHI", "max_tokens"),
    (None, "max_tokens"),
    (None, "refusal"),
    (None, "end_turn"),
    ("   ", "end_turn"),
])
def test_callValidatorLLM_unusable_reply_raises(fakeClient, reply, stopReason):
    fakeClient(reply, stopReason)
    with pytest.raises(validator.ValidatorReplyError):
        validator.callValidatorLLM("Please write a poem.", "Write a poem.")

#Identical prompts pass automatically without calling the LLM
def test_validatePrompt_identical_skips_llm(fakeClient):
    messages = fakeClient("SCORE: 0\nPASSED: No\nREASON: should not be used")
    result = validator.validatePrompt("Write a poem.", "  Write a poem.\n")

    assert messages.calls == 0
    assert result.passed is True
    assert result.qualityScore == 10.0

#A changed prompt is sent to the LLM and its verdict is returned
def test_validatePrompt_uses_llm_verdict(fakeClient):
    original = "Write a 100-word story about a dragon."
    optimized = "Write a story about a dragon."
    messages = fakeClient("THINK: word limit dropped.\nSCORE: 4\nPASSED: No\nREASON: Lost the 100-word limit.")

    result = validator.validatePrompt(original, optimized)

    assert messages.calls == 1
    assert isinstance(result, ValidationResult)
    assert result.originalPrompt == original
    assert result.optimizedPrompt == optimized
    assert result.qualityScore == 4.0
    assert result.passed is False
    assert result.reasoning == "Lost the 100-word limit."
    assert result.reactTrace == "THINK: word limit dropped."

#A prompt type can ask for a higher score than the LLM's own pass mark of 6
def test_validatePrompt_applies_pass_score(fakeClient):
    fakeClient("THINK: minor loss.\nSCORE: 7\nPASSED: Yes\nREASON: Mostly preserved.")
    assert validator.validatePrompt("Please fix this code.", "Fix code.").passed is True

    strict = validator.validatePrompt("Please fix this code.", "Fix code.", passScore=8) #above any type's bar today, still applied
    assert strict.passed is False
    assert strict.qualityScore == 7.0
    assert strict.reasoning.startswith("Mostly preserved.")
    assert "below the 8" in strict.reasoning

#The pass score never turns the LLM's "no" into a pass
def test_validatePrompt_pass_score_never_overrides_fail(fakeClient):
    fakeClient("SCORE: 9\nPASSED: No\nREASON: Dropped the code block.")
    assert validator.validatePrompt("Fix this.", "Fix.", passScore=6).passed is False
