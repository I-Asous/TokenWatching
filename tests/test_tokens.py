"""
Offline unit tests for the shared token counter
"""
from types import SimpleNamespace
import pytest
#anthropic 1.x is built on httpx2 and 0.x on httpx; build the fake request with whichever the SDK uses
try:
    import httpx2 as httpx
except ImportError:
    import httpx
from anthropic import APIConnectionError
from agents import tokens

#Message framing the fake count_tokens endpoint adds around every prompt
FAKE_OVERHEAD = 7


#Fake Anthropic client whose count_tokens returns one token per word plus framing
class FakeMessages:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def count_tokens(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
        text = kwargs["messages"][0]["content"]
        return SimpleNamespace(input_tokens=len(text.split()) + FAKE_OVERHEAD)


#Every test starts with empty caches --> counts from one test can't leak in nother
@pytest.fixture(autouse=True)
def clearCaches():
    for cached in (tokens.countTokens, tokens.estimateTokens, tokens.claudeMessageOverhead):
        cached.cache_clear()
    yield
    for cached in (tokens.countTokens, tokens.estimateTokens, tokens.claudeMessageOverhead):
        cached.cache_clear()


@pytest.fixture
def fakeClient(monkeypatch):
    def install(fail=False):
        fake = SimpleNamespace(messages=FakeMessages(fail))
        monkeypatch.setattr(tokens, "client", fake)
        return fake.messages
    return install

#ChatGPT = o200k_base
def test_countTokens_chatgpt_uses_o200k():
    text = "Write a short story about a dragon."
    expected = len(tokens.tiktoken.get_encoding("o200k_base").encode(text))
    assert tokens.countTokens(text, tokens.CHATGPT) == expected

#Empty text is zero tokens
def test_countTokens_empty_text(fakeClient):
    messages = fakeClient()
    assert tokens.countTokens("", tokens.CHATGPT) == 0
    assert tokens.countTokens("", tokens.CLAUDE) == 0
    assert messages.calls == []

#Claude counts come from count_tokens, minus the message framing overhead
def test_countTokens_claude_subtracts_overhead(fakeClient):
    messages = fakeClient()
    assert tokens.countTokens("Write a short story", tokens.CLAUDE) == 4
    assert messages.calls[0]["model"] == tokens.CLAUDE_COUNT_MODEL

#Counting the same prompt twice only calls the API once
def test_countTokens_claude_is_cached(fakeClient):
    messages = fakeClient()
    tokens.countTokens("Write a poem", tokens.CLAUDE)
    callsAfterFirst = len(messages.calls)
    tokens.countTokens("Write a poem", tokens.CLAUDE)
    assert len(messages.calls) == callsAfterFirst

#count_tokens fails so the local estimate is used instead of crashing EVERYTHING
def test_countTokens_claude_falls_back_on_api_error(fakeClient):
    fakeClient(fail=True)
    text = "Write a short story about a dragon."
    assert tokens.countTokens(text, tokens.CLAUDE) == tokens.estimateTokens(text, tokens.CLAUDE)

#ChatGPT estimates are exact, the same o200k_base count as countTokens
def test_estimateTokens_chatgpt_is_exact():
    text = "Write a short story about a dragon."
    assert tokens.estimateTokens(text, tokens.CHATGPT) == tokens.countTokens(text, tokens.CHATGPT)

#Claude estimates scale the local count by CLAUDE_TOKEN_RATIO and never call the API
def test_estimateTokens_claude_scales_local_count_without_api(fakeClient, monkeypatch):
    messages = fakeClient()
    monkeypatch.setattr(tokens, "CLAUDE_TOKEN_RATIO", 1.5)
    text = "Write a short story about a dragon."
    assert tokens.estimateTokens(text, tokens.CLAUDE) == round(tokens.localTokenCount(text) * 1.5)
    assert tokens.estimateTokens("", tokens.CLAUDE) == 0
    assert messages.calls == []

#A one-token text never rounds down to 0 tokens
def test_estimateTokens_claude_is_at_least_one(monkeypatch):
    monkeypatch.setattr(tokens, "CLAUDE_TOKEN_RATIO", 0.1)
    assert tokens.estimateTokens("hi", tokens.CLAUDE) == 1

def test_estimateTokens_unknown_target():
    with pytest.raises(ValueError):
        tokens.estimateTokens("hi", "gemini")

#unknown target is rejected
def test_countTokens_unknown_target():
    with pytest.raises(ValueError):
        tokens.countTokens("hi", "gemini")
