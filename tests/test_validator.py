"""
Offline unit tests for third agent
"""
import json
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

#A reply as the structured output returns it
def verdict(score, reason="Fine.", lost=()):
    return json.dumps({"lost": list(lost), "score": score, "reason": reason})

#Both prompts are included, each in its own tags
def test_buildUserMessage_labels_both_prompts():
    message = validator.buildUserMessage("Please write a poem.", "Write a poem.")
    assert message == "<original>\nPlease write a poem.\n</original>\n\n<rewrite>\nWrite a poem.\n</rewrite>"

#Type rules come first, one bullet per type, with the note that weakening one is a loss
def test_buildUserMessage_with_type_rules():
    message = validator.buildUserMessage("Please fix my code.", "Fix my code.",
                                         typeRules="Code prompt: never change code.\nSecurity prompt: keep every rule.")
    assert "- Code prompt: never change code.\n- Security prompt: keep every rule." in message
    assert "meaningful loss (score 3-5)" in message
    assert message.index("Code prompt") < message.index("<original>") < message.index("<rewrite>")

#The type rules reach the request sent to the LLM
def test_validatePrompt_sends_type_rules(fakeClient):
    messages = fakeClient(verdict(8))
    validator.validatePrompt("Please fix my code.", "Fix my code.", typeRules="Code prompt: never change code.")
    assert "- Code prompt: never change code." in messages.lastRequest["messages"][0]["content"]

#A verdict with nothing lost and a passing score passes, and the trace says nothing was lost
def test_parseVerdict_nothing_lost():
    score, passed, reason, trace = validator.parseVerdict(verdict(8, "Only filler was removed."))
    assert (score, passed, reason, trace) == (8, True, "Only filler was removed.", "Nothing lost.")

#What was lost is added to the reason (what the Optimizer's retry is told) and to the trace
def test_parseVerdict_lists_losses():
    score, passed, reason, trace = validator.parseVerdict(verdict(4, "Dropped the word limit.", ["100-word limit"]))
    assert score == 4
    assert passed is False
    assert reason == "Dropped the word limit. Lost: 100-word limit."
    assert trace == "Lost: 100-word limit"

#A listed loss fails the rewrite even when the score is 6 or more
def test_parseVerdict_loss_fails_any_score():
    _, passed, _, _ = validator.parseVerdict(verdict(7, "Mostly kept.", ["the knee injury"]))
    assert passed is False

#Blank loss entries don't count as losses
def test_parseVerdict_ignores_blank_losses():
    _, passed, _, trace = validator.parseVerdict(verdict(9, lost=["", "  "]))
    assert passed is True
    assert trace == "Nothing lost."

#A score under 6 fails with nothing listed
def test_parseVerdict_low_score_fails():
    assert validator.parseVerdict(verdict(5))[1] is False

#A reply that isn't a valid verdict raises instead of failing the rewrite with a made-up reason
@pytest.mark.parametrize("reply", [
    "SCORE: 8\nPASSED: Yes\nREASON: Fine.",
    '{"score": 8, "reason": "Fine."}',
    '{"lost": [], "score": "high", "reason": "Fine."}',
])
def test_parseVerdict_invalid_raises(reply):
    with pytest.raises(validator.ValidatorReplyError):
        validator.parseVerdict(reply)

#The schema keeps lost before score, so the model lists what was lost before it scores
def test_verdict_format_order():
    schema = validator.VERDICT_FORMAT["schema"]
    assert validator.VERDICT_FORMAT["type"] == "json_schema"
    assert list(schema["properties"]) == ["lost", "score", "reason"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"lost", "score", "reason"}

#The system prompt says politeness and filler are never requirements, so cutting them isn't a loss
def test_system_prompt_politeness_is_not_a_requirement():
    assert "Never requirements" in validator.VALIDATOR_SYSTEM_PROMPT
    assert "politeness" in validator.VALIDATOR_SYSTEM_PROMPT

#LLM call sends the system prompt, both prompts, the verdict schema and low effort
def test_callValidatorLLM_sends_request(fakeClient):
    messages = fakeClient(verdict(7))
    result = validator.callValidatorLLM("Please write a poem.", "Write a poem.")

    assert result == (7, True, "Fine.", "Nothing lost.")
    request = messages.lastRequest
    assert request["system"] == validator.VALIDATOR_SYSTEM_PROMPT
    assert request["model"] == validator.VALIDATOR_MODEL
    assert request["output_config"] == {"effort": validator.VALIDATOR_EFFORT, "format": validator.VERDICT_FORMAT}
    assert "Please write a poem." in request["messages"][0]["content"]
    assert "Write a poem." in request["messages"][0]["content"]

#The verdict is read from the text block after any thinking block, and without one too
@pytest.mark.parametrize("thinking", [True, False])
def test_callValidatorLLM_reads_text_block(fakeClient, thinking):
    fakeClient(verdict(8, "Only filler was removed."), thinking=thinking)
    assert validator.callValidatorLLM("Please write a poem.", "Write a poem.") == (
        8, True, "Only filler was removed.", "Nothing lost.")

#A reply cut off by max_tokens, refused, or with no text raises instead of failing the rewrite
@pytest.mark.parametrize("reply, stopReason", [
    ('{"lost": [], "sco', "max_tokens"),
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
    messages = fakeClient(verdict(1, "should not be used", ["everything"]))
    result = validator.validatePrompt("Write a poem.", "  Write a poem.\n")

    assert messages.calls == 0
    assert result.passed is True
    assert result.qualityScore == 10.0

#A changed prompt is sent to the LLM and its verdict is returned
def test_validatePrompt_uses_llm_verdict(fakeClient):
    original = "Write a 100-word story about a dragon."
    optimized = "Write a story about a dragon."
    messages = fakeClient(verdict(4, "Dropped the word limit.", ["100-word limit"]))

    result = validator.validatePrompt(original, optimized)

    assert messages.calls == 1
    assert isinstance(result, ValidationResult)
    assert result.originalPrompt == original
    assert result.optimizedPrompt == optimized
    assert result.qualityScore == 4
    assert result.passed is False
    assert result.reasoning == "Dropped the word limit. Lost: 100-word limit."
    assert result.reactTrace == "Lost: 100-word limit"

#A prompt type can ask for a higher score than the LLM's own pass mark of 6
def test_validatePrompt_applies_pass_score(fakeClient):
    fakeClient(verdict(7, "Mostly preserved."))
    assert validator.validatePrompt("Please fix this code.", "Fix code.").passed is True

    strict = validator.validatePrompt("Please fix this code.", "Fix code.", passScore=8) #above any type's bar today, still applied
    assert strict.passed is False
    assert strict.qualityScore == 7
    assert strict.reasoning.startswith("Mostly preserved.")
    assert "below the 8" in strict.reasoning

#The pass score never turns a listed loss into a pass
def test_validatePrompt_pass_score_never_overrides_fail(fakeClient):
    fakeClient(verdict(9, "Dropped the code block.", ["the code block"]))
    assert validator.validatePrompt("Fix this.", "Fix.", passScore=6).passed is False
