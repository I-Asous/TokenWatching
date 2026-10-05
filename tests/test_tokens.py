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
    tokens.countTokens.cache_clear()
    tokens.claudeMessageOverhead.cache_clear()
    yield
    tokens.countTokens.cache_clear()
    tokens.claudeMessageOverhead.cache_clear()


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

#count_tokens fails so local o200k_base count is used instead of crashing EVERYTHING
def test_countTokens_claude_falls_back_on_api_error(fakeClient):
    fakeClient(fail=True)
    text = "Write a short story about a dragon."
    expected = len(tokens.tiktoken.get_encoding("o200k_base").encode(text))
    assert tokens.countTokens(text, tokens.CLAUDE) == expected

#unknown target is rejected
def test_countTokens_unknown_target():
    with pytest.raises(ValueError):
        tokens.countTokens("hi", "gemini")
