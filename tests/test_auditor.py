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

#Cost is proportional to token count and rounded to 3 decimals
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