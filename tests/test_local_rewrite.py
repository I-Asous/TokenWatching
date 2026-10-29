"""
Offline unit tests for the local (no LLM) rewrite and the filler-only edit check
"""
import pytest
from agents.local_rewrite import deleteFiller, localRewrite, isFillerOnlyEdit

#Politeness, filler and the thanks are deleted, and the leftover question becomes a direct instruction
def test_deleteFiller_removes_politeness_and_fixes_punctuation():
    rewrite, deleted = deleteFiller("Please, could you kindly write a short story about a dragon? Thank you so much!")
    assert rewrite == "Write a short story about a dragon."
    assert "could you kindly" in deleted

#A greeting line and closing thanks go, the request in between stays
def test_deleteFiller_greeting_and_closing():
    rewrite, _ = deleteFiller("Hi there! I hope you're doing well. Can you summarize this article for me, please? Thanks in advance!")
    assert rewrite == "Summarize this article for me."

#A real question keeps its question mark once the wrapper is gone
def test_deleteFiller_keeps_real_questions():
    rewrite, _ = deleteFiller("Could you please tell me what DNS is? Also, is it really slow?")
    assert rewrite == "Tell me what DNS is. Also, is it slow?"

#Sentences without filler are copied exactly, and so is code
def test_deleteFiller_leaves_other_sentences_and_code_alone():
    prompt = "Fix this bug, please.\n```python\ndef add(a, b):  # please   keep\n    return a - b\n```\nKeep  the  spacing here."
    rewrite, _ = deleteFiller(prompt)
    assert rewrite == "Fix this bug.\n```python\ndef add(a, b):  # please   keep\n    return a - b\n```\nKeep  the  spacing here."

#A colon introducing what follows is kept
def test_deleteFiller_keeps_trailing_colon():
    rewrite, _ = deleteFiller("Summarize this, please:\nThe meeting moved to Friday.")
    assert rewrite == "Summarize this:\nThe meeting moved to Friday."

#Optional requests keep their "maybe", and meaningful words like "best" aren't deleted
def test_deleteFiller_keeps_options_and_meaningful_words():
    rewrite, _ = deleteFiller("Please write the best intro you can. Maybe add a quote. Thanks!")
    assert rewrite == "Write the best intro you can. Maybe add a quote."

#Quoted text is the user's material: its "Please" and "thank you" are part of what to translate
def test_deleteFiller_leaves_quoted_text_alone():
    rewrite, _ = deleteFiller('Hi! Could you please translate the sign "Please do not touch, thank you" into French? Thanks!')
    assert rewrite == 'Translate the sign "Please do not touch, thank you" into French.'

@pytest.mark.parametrize("prompt, kept", [
    ("Please don't just list the bugs, fix them. Thanks!", "Don't just list the bugs, fix them."),
    ("Please write a summary, not just a list. Thanks!", "Write a summary, not just a list."),
    ("Please keep it short, I don't really need examples. Thanks!", "Keep it short, I don't really need examples."),
])
#"just" and "really" after a negation carry the meaning, so they're kept
def test_deleteFiller_keeps_filler_after_negation(prompt, kept):
    assert deleteFiller(prompt)[0] == kept

#"Could you please help me with this?" leaves only "this": a fragment, so nothing is rewritten locally
def test_deleteFiller_refuses_to_leave_a_fragment():
    prompt = "Hi there! Could you please help me with this? Don't just list the bugs in my code, fix them. Thanks so much!"
    assert deleteFiller(prompt)[0] == ""
    assert localRewrite(prompt) is None

#Dropping a "just" that follows a negation isn't filler-only, so the Validator still checks it
def test_isFillerOnlyEdit_rejects_dropped_word_after_negation():
    assert not isFillerOnlyEdit("Please don't just list the bugs, fix them.", "Don't list the bugs, fix them.")

#A prompt that's mostly politeness is rewritten locally, with the deleted spans as its change
def test_localRewrite_rewrites_filler_heavy_prompt():
    result = localRewrite("Please, could you kindly write a short story about a dragon? Thank you so much!")
    assert result is not None
    assert result.optimizedPrompt == "Write a short story about a dragon."
    assert result.tokensSaved > 0
    assert 0 < result.percentSaved < 100
    assert "removed politeness and filler" in result.changes[0]

#A lone "please" isn't worth a rewrite, same as the Auditor and Optimizer decide
def test_localRewrite_skips_prompt_with_little_filler():
    assert localRewrite("Please explain the difference between TCP and UDP.") is None

#Rules, numbers and negations survive the local rewrite
def test_localRewrite_keeps_rules_and_numbers():
    result = localRewrite("Could you please write a 150-word bio for our CEO? Do NOT mention their age. Thanks so much!")
    assert result is not None
    assert result.optimizedPrompt == "Write a 150-word bio for our CEO. Do NOT mention their age."

#If deleting filler leaves something the rule checks still flag, the Optimizer handles it instead
def test_localRewrite_defers_when_other_issues_remain():
    prompt = ("Please could you kindly help me. Write a summary of the report for the team. "
              "Write a summary of the report for the team. Thanks!")
    assert localRewrite(prompt) is None

@pytest.mark.parametrize("rewrite", [
    "Write a short story about a dragon.",
    "write a short story about a dragon",
    "Could you write a short story about a dragon?",
])
#Deleting only politeness and filler, with any capitals and punctuation, is a filler-only edit
def test_isFillerOnlyEdit_accepts_deletions(rewrite):
    assert isFillerOnlyEdit("Please, could you kindly write a short story about a dragon? Thank you so much!", rewrite)

@pytest.mark.parametrize("rewrite", [
    "Write a brief story about a dragon.",         #reworded
    "Write a short story.",                        #dropped real words
    "Write a short funny story about a dragon.",   #added a word
    "Write a story about a short dragon.",         #reordered
])
#Rewording, dropping, adding or reordering real words is not a filler-only edit
def test_isFillerOnlyEdit_rejects_other_edits(rewrite):
    assert not isFillerOnlyEdit("Please, could you kindly write a short story about a dragon? Thank you so much!", rewrite)
