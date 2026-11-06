"""
Offline unit tests for first agent
"""
import re
import pytest
from agents import auditor
from agents.auditor import runRuleCheck, countTokens, AuditResult
from agents.prompt_types import CHECK_TOKEN_RATIO, CHECK_READABILITY, CHECK_ADVERBS

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
#"maybe" / "possibly" that make a request optional aren't filler, the same words as hedging still are
@needsSpacyModel
def test_runRuleCheck_option_words_are_not_filler():
    options = "Write the parser. Maybe add tests. Maybe add docs. Possibly add a README."
    assert not any("filler" in issue.lower() for issue in auditor.runRuleCheck(options, auditor.countTokens(options)))
    hedging = "I was just wondering if you could maybe possibly help me write the parser, please."
    assert any("filler" in issue.lower() for issue in auditor.runRuleCheck(hedging, auditor.countTokens(hedging)))

#Checks a prompt type skips aren't run (code skips the token ratio, readability and adverbs)
def test_runRuleCheck_skips_checks(monkeypatch):
    calls = {}
    def fakeReadability(text):
        calls["readability"] = True
        return ["readability issue"]
    def fakeSpacy(text, checkAdverbs=True):
        calls["adverbs"] = checkAdverbs
        return []
    monkeypatch.setattr(auditor, "runReadabilityCheck", fakeReadability)
    monkeypatch.setattr(auditor, "runSpacyCheck", fakeSpacy)

    #"x" at 5 tokens per word trips the ratio check
    everything = runRuleCheck("x", token_count=5)
    assert any("token to word" in issue for issue in everything)
    assert "readability issue" in everything and calls["adverbs"] is True

    calls.clear()
    skipped = runRuleCheck("x", 5, frozenset({CHECK_TOKEN_RATIO, CHECK_READABILITY, CHECK_ADVERBS}))
    assert skipped == []
    assert "readability" not in calls and calls["adverbs"] is False

DRAGON = "Please, could you kindly help me write a short story about a dragon? Thank you so much!"

#Politeness phrases count as whole spans, so a prompt with few filler words but lots of politeness is flagged
def test_findRemovableFiller_flags_politeness_phrases():
    removable, total, spans = auditor.estimateRemovableTokens(DRAGON)
    assert spans == ["Please", "could you kindly help me", "Thank you so much!"]
    assert removable > total / 3
    issue = auditor.findRemovableFiller(DRAGON)
    assert issue.startswith(f"About {removable} of {total} tokens")
    assert "'could you kindly help me'" in issue
    assert any(issue == found for found in runRuleCheck(DRAGON, countTokens(DRAGON)))

#A cut of a token or two isn't worth a rewrite, however short the prompt
@pytest.mark.parametrize("prompt", ["Please explain the difference between TCP and UDP.",
                                    "Can you explain how DNS works?",
                                    "Write a short story about a dragon."])
def test_findRemovableFiller_ignores_small_cuts(prompt):
    assert auditor.findRemovableFiller(prompt) is None

#A 3-token politeness phrase at 10% of the prompt isn't flagged (MIN_REMOVABLE_SHARE), even though a
#multi-translate prompt like this one is otherwise worth a rewrite: 3 repeated live runs showed nothing
#else in the sentence is safely cuttable, so the Optimizer could never clear the orchestrator's own
#MIN_TOKENS_SAVED=5 floor on it and flagging it only paid for a guaranteed failure (evals/results/phase3-repeat.jsonl)
def test_findRemovableFiller_ignores_share_the_optimizer_cant_use():
    prompt = ("Could you please translate this sentence into French and also explain the grammar of the "
              "verb tense you used? 'I would have gone if I had known.'")
    assert auditor.findRemovableFiller(prompt) is None

#Code blocks are the user's material: politeness inside them isn't counted
def test_estimateRemovableTokens_skips_code_blocks():
    prompt = "Fix this:\n```python\n# thanks, please just work\ndef add(a, b): return a - b\n```"
    assert auditor.estimateRemovableTokens(prompt)[0] == 0

#Overlapping matches ("could you please" and "please") count once
def test_estimateRemovableTokens_merges_overlaps():
    assert auditor.estimateRemovableTokens("Could you please list three fruits?")[2] == ["Could you please"]

#Hedge words that make a request optional aren't removable
@needsSpacyModel
def test_estimateRemovableTokens_keeps_options():
    assert auditor.estimateRemovableTokens("Write the parser. Maybe add tests. Possibly add a README.")[0] == 0

#auditPrompt makes no LLM call of its own (removed 11/4/2026: folded into the Optimizer's own first look,
#see orchestrator.MIN_TOKENS_TO_LET_OPTIMIZER_LOOK) -- its issues are exactly runRuleCheck's, nothing added
def test_auditPrompt_has_no_llm_call(monkeypatch):
    monkeypatch.setattr(auditor, "runRuleCheck", lambda text, token_count, skipChecks: ["an issue"])
    assert auditor.auditPrompt("Write a long report." * 50).issues == ["an issue"]

#Two or more sentences asking for the same length in different words are flagged as one repeated instruction
def test_findRepeatedLengthWording_flags_different_words_for_the_same_length():
    text = "Give me a quick summary of the French Revolution. Make it short. Just the main points, nothing too long or detailed."
    issue = auditor.findRepeatedLengthWording(text)
    assert issue is not None and "quick" in issue and "short" in issue

#Two different sentences each asking for a different length, about different things, aren't a repeat
def test_findRepeatedLengthWording_ignores_different_targets():
    assert auditor.findRepeatedLengthWording("Write a short intro. Make the conclusion detailed.") is None
    assert auditor.findRepeatedLengthWording("Write a short intro and a detailed conclusion.") is None
    assert auditor.findRepeatedLengthWording("Write a short story about a dragon.") is None

#Sentences that repeat the same length word via different lemmas (e.g. "reverses" and "reverse") are
#caught by the lower REPEAT_SIMILARITY bar (0.7), tuned from a real near-miss at 0.75 overlap
def test_runSpacyCheck_flags_close_but_not_identical_repeat():
    text = ("Write a function that reverses a string in Go. The function should reverse a string. Make sure "
            "it reverses the string correctly, and handle Unicode characters properly so multi-byte "
            "characters are reversed correctly too.")
    assert any("repeat" in issue.lower() for issue in auditor.runSpacyCheck(text))


#Wordy phrases are flagged once shortening them saves MIN_REMOVABLE_TOKENS, the same bar as filler
def test_findWordyPhrases_flags_enough_savings():
    issue = auditor.findWordyPhrases("Due to the fact that the API is able to time out, add retries prior to the release.")
    assert issue is not None and "'Due to the fact that' -> 'because'" in issue
    assert auditor.findWordyPhrases("Add retries in order to handle timeouts.") is None

#A phrase inside quoted text is the person's material, not their wording
def test_findWordyPhrases_skips_quoted_text():
    assert auditor.findWordyPhraseMatches('Translate "due to the fact that" and "in the event that" into French.') == []
