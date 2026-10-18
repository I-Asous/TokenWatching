"""
Offline unit tests for first agent
"""
import re
import pytest
from agents import auditor
from agents.auditor import runRuleCheck, countTokens, AuditResult

#Token counting returns a positive count for text and zero for empty input
def test_countTokens_counts_nonempty_text():
    assert auditor.countTokens("Hello, world") > 0
    assert auditor.countTokens("") == 0

#Cost is proportional to token count
def test_estimateCost_scales_with_tokens():
    assert auditor.estimateCost(0) == 0
    assert auditor.estimateCost(1_000_000) == 3.0

#Filler words and runs of blank lines are reported as issues
def test_runRuleCheck_flags_filler_words_and_blank_lines():
    text = "please just really help me\n\n\nthanks"
    issues = auditor.runRuleCheck(text, auditor.countTokens(text))
    assert any("filler" in issue.lower() for issue in issues)
    assert any("blank lines" in issue.lower() for issue in issues)

#Severity follows the token-count and issue-count thresholds
def test_determineSeverity_thresholds():
    """Severity follows the token-count and issue-count thresholds."""
    assert auditor.determineSeverity(100, 0) == "Low"
    assert auditor.determineSeverity(400, 0) == "Medium"
    assert auditor.determineSeverity(100, 1) == "Medium"
    assert auditor.determineSeverity(900, 0) == "High"
    assert auditor.determineSeverity(100, 3) == "High"

#Uses regex for test inpt with different num of lines
def test_flags_excessive_blank_lines():
    twoBlankLines = "Some text.\n\nMore text."
    threeBlankLines = "Some text.\n\n\nMore text."

    #regex used to verify the test input itself is shaped correctly
    assert re.search(r"\n{2}", twoBlankLines)
    assert re.search(r"\n{3,}", threeBlankLines)

    issuesTwo = runRuleCheck(twoBlankLines, token_count=10)
    issuesThree = runRuleCheck(threeBlankLines, token_count=10)

    assert not any("blank lines" in issue.lower() for issue in issuesTwo)
    assert any("blank lines" in issue.lower() for issue in issuesThree)

#safe prompt no filler/excess should pass????"""
def test_runRuleCheck_clean_prompt_has_no_issues():
    clean = "Write a short story about a dragon."
    issues = auditor.runRuleCheck(clean, auditor.countTokens(clean))
    assert issues == []

needsSpacyModel = pytest.mark.skipif(auditor.loadNlp() is None, reason="spaCy model en_core_web_sm is not installed")

#One run-on sentence well past MAX_WORDS_PER_SENTENCE is flagged as long
def test_runReadabilityCheck_flags_long_sentences():
    runOn = ("I would like you to write a story about a dragon that lives in a cave near a village "
             "and protects the people there from bandits while also learning to make friends with the children")
    issues = auditor.runReadabilityCheck(runOn)
    assert any("long sentences" in issue.lower() for issue in issues)

#Short prompts and prompts with code blocks are skipped, readability formulas are for prose
def test_runReadabilityCheck_skips_short_text_and_code():
    assert auditor.runReadabilityCheck("Summarize this article in three bullet points.") == []
    code = "Fix this:\n```python\n" + "result = compute_everything(argument_one, argument_two) " * 10 + "\n```"
    assert auditor.runReadabilityCheck(code) == []

#A sentence that says the same thing again is counted as a repeat
@needsSpacyModel
def test_runSpacyCheck_flags_repeated_sentences():
    text = "Write a short poem about the ocean. Keep the poem short. Write a short poem about the ocean."
    issues = auditor.runSpacyCheck(text)
    assert any("repeat" in issue.lower() for issue in issues)

#Adverb-heavy prompts are flagged, a plain prompt isn't
@needsSpacyModel
def test_runSpacyCheck_flags_adverb_heavy_text():
    padded = ("Could you very quickly and really carefully write a fairly short summary that actually "
              "covers basically all of the extremely important points really clearly?")
    plain = "Write a short summary of the article that covers the main points and the conclusion in plain language."
    assert any("adverbs" in issue.lower() for issue in auditor.runSpacyCheck(padded))
    assert not any("adverbs" in issue.lower() for issue in auditor.runSpacyCheck(plain))

#Without the spaCy model the spaCy checks are skipped and the rest of the audit still runs
def test_runSpacyCheck_without_model_returns_no_issues(monkeypatch):
    monkeypatch.setattr(auditor, "loadNlp", lambda: None)
    assert auditor.runSpacyCheck("Write a poem. Write a poem. Write a poem.") == []
    text = "please just really help me\n\n\nthanks"
    assert any("filler" in issue.lower() for issue in auditor.runRuleCheck(text, auditor.countTokens(text)))