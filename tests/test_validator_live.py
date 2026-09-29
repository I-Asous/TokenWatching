"""
Live checks for third agent. These call the real Claude API, so they are
skipped by default and only run with: pytest -m live
"""
import os
import pytest
from agents import validator

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"),
]

#Removing only filler words keeps the intent, so it should pass
def test_filler_removal_passes():
    result = validator.validatePrompt(
        "Please, could you kindly help me write a short story about a dragon? Thank you so much!",
        "Write a short story about a dragon.",
    )
    assert result.passed, result.reasoning
    assert result.qualityScore >= 6

#Dropping an explicit constraint changes the result, so it should fail
def test_dropped_constraint_fails():
    result = validator.validatePrompt(
        "Write a story about a dragon in exactly 100 words, as a JSON object with 'title' and 'body' keys.",
        "Write a story about a dragon.",
    )
    assert not result.passed, result.reasoning
    assert result.qualityScore < 6
