"""
Offline unit tests for prompt type detection (agents/prompt_types.py). No API calls
"""
import pytest
from agents.prompt_types import (PROFILES, SIGNALS, DEFAULT_TYPE, CHECK_READABILITY, CHECK_TOKEN_RATIO,
                                 detectPromptTypes, detectSignals, combineProfiles)

#One clear example per type
@pytest.mark.parametrize("prompt, expected", [
    ("Make sure the export is GDPR compliant.", ["security"]),
    ("Fix this:\n```python\nprint(x)\n```", ["code"]),
    ("Why does SELECT name FROM users return nothing?", ["code"]),
    ("Clean up utils.py for me.", ["code"]),
    ("1. Pull the data.\n2. Remove duplicates.\n3. Email the report.", ["workflow"]),
    ("Summarize the findings and cite every claim.", ["research"]),
    ("Write a haiku about autumn.", ["creative"]),
])
def test_detects_each_type(prompt, expected):
    assert detectPromptTypes(prompt) == expected

#A prompt with no signals is conversational
def test_no_signals_is_conversational():
    assert detectPromptTypes("hey what's a good name for my cat") == ["conversational"]
    assert detectSignals("hey what's a good name for my cat") == {}

#One weak word isn't enough, two different weak words are
def test_one_weak_signal_is_not_enough():
    assert detectPromptTypes("What's your refund policy?") == ["conversational"]
    assert detectPromptTypes("Explain our password policy.") == ["security"]

#Repeating the same weak word doesn't add up
def test_repeated_weak_word_counts_once():
    assert detectPromptTypes("policy policy policy policy") == ["conversational"]

#Lowercase "select ... from" in normal English isn't SQL
def test_lowercase_select_from_is_not_sql():
    assert "code" not in detectPromptTypes("Help me select a gift from these three options.")

#One numbered line isn't a workflow, two are
def test_needs_two_numbered_steps():
    assert detectPromptTypes("1. Write a short bio for me.") == ["conversational"]
    assert detectPromptTypes("1. Write a short bio.\n2. Translate it to French.") == ["workflow"]

#Several types can match, returned strictest first
def test_several_types_strictest_first():
    prompt = "Write a Python function that checks a user's password. Must follow our GDPR policy."
    assert detectPromptTypes(prompt) == ["security", "code"]

#Curly apostrophes don't hide signals
def test_curly_apostrophes():
    curly = detectSignals("Don’t forget to cite sources.")
    assert curly == detectSignals("Don't forget to cite sources.")

#Combining takes the highest pass score, every skipped check, every rule, strictest first
def test_combineProfiles_strictest_wins():
    combined = combineProfiles(["creative", "code", "research"])
    assert combined.passScore == PROFILES["code"].passScore == 7
    assert combined.strictness == PROFILES["code"].strictness
    assert {CHECK_READABILITY, CHECK_TOKEN_RATIO} <= combined.skipChecks
    rules = combined.optimizerRules.splitlines()
    assert rules == [PROFILES["code"].optimizerRules, PROFILES["research"].optimizerRules,
                     PROFILES["creative"].optimizerRules]

#Optimizing is allowed only if every type allows it
def test_combineProfiles_optimize_needs_every_type(monkeypatch):
    monkeypatch.setitem(PROFILES, "security", PROFILES["security"].__class__(
        strictness=6, passScore=8, skipChecks=frozenset(), optimizerRules="x", optimize=False))
    assert combineProfiles(["security", "creative"]).optimize is False
    assert combineProfiles(["creative"]).optimize is True

#An empty list falls back to conversational
def test_combineProfiles_empty_is_conversational():
    assert combineProfiles([]) == PROFILES["conversational"]

#Every type has a profile and every signal type is a profile
def test_profiles_cover_every_type():
    assert set(SIGNALS) | {DEFAULT_TYPE} == set(PROFILES)
