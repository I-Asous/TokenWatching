"""
Offline unit tests for the local (no LLM) rewrite and the filler-only edit check
"""
import pytest
from agents.local_rewrite import deleteFiller, localEdits, localRewrite, isFillerOnlyEdit, tidyWhitespace

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
    rewrite, _ = deleteFiller("Could you please tell me what DNS is? Also, is it slow?")
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

#"Could you please help me with this?" has no request verb to keep, so the wrapper stays and the Optimizer handles it
def test_localRewrite_defers_wrapper_with_no_request_verb():
    prompt = "Hi there! Could you please help me with this? Don't just list the bugs in my code, fix them. Thanks so much!"
    assert deleteFiller(prompt)[0] == "Could you please help me with this? Don't just list the bugs in my code, fix them."
    assert localRewrite(prompt) is None

@pytest.mark.parametrize("prompt", [
    "Can you freeze cooked rice? Thanks so much!",
    "Could you get sick from eating raw cookie dough? Thanks in advance!",
    "Would you say this is a good idea for a startup? Thanks!",
    "Can you build muscle on a vegan diet? Thanks so much!",
    "Can you write off a home office as a W-2 employee? Thanks so much!",
    "Is it possible to write a for loop in bash? Thank you so much!",
])
#A question with a general "you" isn't a polite request: cutting "Can you" turns it into a command
def test_deleteFiller_keeps_real_yes_no_questions(prompt):
    assert deleteFiller(prompt)[0] == prompt.split("?")[0] + "?"

@pytest.mark.parametrize("prompt, kept", [
    ("How do I say thank you in Japanese? Thanks so much!", "How do I say thank you in Japanese?"),
    ("How do you say please in French? Thank you!", "How do you say please in French?"),
    ("How do you say please? Thank you!", "How do you say please?"),
    ("Please explain the just war theory. Thank you so much!", "Explain the just war theory."),
    ("Please explain just-in-time compilation. Thank you so much!", "Explain just-in-time compilation."),
    ("Please name a movie like Just Mercy. Thank you so much!", "Name a movie like Just Mercy."),
    ("Name a band like Thank You Scientist please. Thank you so much!", "Name a band like Thank You Scientist please."),
    ("Please write a toast that ends with cheers. Thank you so much!", "Write a toast that ends with cheers."),
    ("Please write a thank you note to my boss. Thanks!", "Write a thank you note to my boss."),
    ("Please draft a letter that says thank you to our donors. Thanks so much!", "Draft a letter that says thank you to our donors."),
    ("Write an email that opens with I hope you are doing well. Thank you so much!", "Write an email that opens with I hope you are doing well."),
    ("Please write a reminder asking the client to kindly pay the invoice. Thanks!", "Write a reminder asking the client to kindly pay the invoice."),
    ("Hello World in Rust. Thank you so much!", "Hello World in Rust."),
    ("Hello, world in Rust. Thank you so much!", "Hello, world in Rust."),
    ("Hi-fi speakers, which should I buy? Thank you so much!", "Hi-fi speakers, which should I buy?"),
])
#These words are what the prompt is about when they sit inside a sentence, so only the real closing goes
def test_deleteFiller_keeps_words_the_prompt_is_about(prompt, kept):
    assert deleteFiller(prompt)[0] == kept

@pytest.mark.parametrize("prompt, kept", [
    ("Write a policy. Thank you so much for helping with this.", "Write a policy."),
    ("Explain DNS. Thanks so much for your help, I really appreciate it!", "Explain DNS."),
    ("Explain DNS. Thanks a lot for this.", "Explain DNS."),
    ("Explain DNS. I would really appreciate it. Thanks!", "Explain DNS."),
    ("Explain DNS. Any help is greatly appreciated!", "Explain DNS."),
])
#A closing sentence goes whole, so it can't leave "For helping with this." behind
def test_deleteFiller_removes_whole_closing_sentences(prompt, kept):
    assert deleteFiller(prompt)[0] == kept

@pytest.mark.parametrize("prompt", [
    "Write a bio. Thank you very much, and I look forward to seeing what you come up with.",
    "Write a bio. I'd really appreciate it if you could keep it short.",
])
#A closing that also asks or says something else is kept
def test_deleteFiller_keeps_closings_with_other_content(prompt):
    assert deleteFiller(prompt)[0] == prompt

#"Would you mind telling me" can't lose its wrapper by deleting: "telling" would have to be reworded
def test_deleteFiller_keeps_would_you_mind():
    prompt = "Would you mind telling me the boiling point of water? Thanks!"
    assert deleteFiller(prompt)[0] == "Would you mind telling me the boiling point of water?"

#A wrapper inside a sentence is left alone, so the sentence's grammar isn't broken
def test_deleteFiller_keeps_wrapper_inside_a_sentence():
    prompt = "I'm writing a review and I'd really appreciate it if you could give me an overview."
    assert deleteFiller(prompt)[0] == prompt

#Words inside a sentence stay, filler or not
def test_deleteFiller_keeps_filler_words_inside_a_sentence():
    prompt = "Is it really safe, and is this just a phase, basically?"
    assert deleteFiller(prompt)[0] == prompt

#A greeting and a hope sentence go at the start, with or without punctuation between them
@pytest.mark.parametrize("prompt, kept", [
    ("Hi, hope you're having a great day! Explain DNS.", "Explain DNS."),
    ("Hey can you explain DNS?", "Explain DNS."),
    ("Good morning! Could you please list three fruits?", "List three fruits."),
])
def test_deleteFiller_removes_openings(prompt, kept):
    assert deleteFiller(prompt)[0] == kept

#Pasted material after a colon is the user's, including what looks like politeness
def test_deleteFiller_leaves_pasted_material_alone():
    prompt = "Summarize this sentence: I would really appreciate it if you could stop doing that. Thanks so much!"
    assert deleteFiller(prompt)[0] == prompt

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

@pytest.mark.parametrize("original, rewrite", [
    ("Can you freeze cooked rice?", "Freeze cooked rice."),
    ("How do I say thank you in Japanese?", "How do I say in Japanese?"),
    ("Please write a thank you note to my boss.", "Write a note to my boss."),
    ("Please explain the just war theory.", "Explain the war theory."),
    ("Write a toast for my sister's wedding that ends with cheers.", "Write a toast for my sister's wedding that ends with"),
    ("Name a movie like Just Mercy.", "Name a movie like Mercy."),
])
#These look like deletions, but each changes the request, so the Validator has to see them
def test_isFillerOnlyEdit_rejects_deletions_that_change_the_request(original, rewrite):
    assert not isFillerOnlyEdit(original, rewrite)

#A sentence repeated word for word is deleted locally, keeping the first copy
def test_localRewrite_removes_word_for_word_repeats():
    result = localRewrite("Write a summary of the report for the team. Keep it under 200 words. Keep it under 200 words.")
    assert result is not None
    assert result.optimizedPrompt == "Write a summary of the report for the team. Keep it under 200 words."
    assert result.changes == ["removed repeated sentences: 'Keep it under 200 words.'"]

#Wordy phrases get their shorter form, keeping a capital at the start of a sentence
def test_localRewrite_shortens_wordy_phrases():
    result = localRewrite("Due to the fact that the API is able to time out, add retries prior to the release. "
                          "In the event that it fails, log it.")
    assert result is not None
    assert result.optimizedPrompt == "Because the API can time out, add retries before the release. If it fails, log it."

@pytest.mark.parametrize("prompt", [
    "Translate 'in order to' into French. Translate 'in order to' into French.",       #quoted material
    "Summarize this: due to the fact that sales fell in order to cut costs we closed two stores.",  #pasted material
    "Frontend:\n- Run the unit tests.\nBackend:\n- Run the unit tests.",                #same item under two headings
    "Make it short. Keep it brief and concise.",                                        #near-repeat, not word for word
    "Fix this:\n```python\nx = 1  # in order to test\n```\nFix this:\n```python\nx = 1  # in order to test\n```",
])
#The person's material, list items and near-repeats are left for the Optimizer
def test_localEdits_leave_material_and_near_repeats_alone(prompt):
    assert localEdits(prompt)[0] == prompt.strip()

#Blank lines inside a code block are kept; outside, two or more become one, and "!!!" becomes "!"
def test_tidyWhitespace_skips_code():
    text, changed = tidyWhitespace("Explain this.\n\n\n\nIt fails!!!\n```python\nx = 1\n\n\n\ny = 2\n```")
    assert changed
    assert text == "Explain this.\n\nIt fails!\n```python\nx = 1\n\n\n\ny = 2\n```"

@pytest.mark.parametrize("rewrite", [
    "Because the API can time out, add retries before the release. Log every failure.",
    "Due to the fact that the API is able to time out, add retries before the release. Log every failure.",
    "Because the API can time out, add retries before the release. Log every failure. Log every failure.",
])
#Shortening wordy phrases and deleting a word-for-word repeat, in any combination, skips the Validator
def test_isFillerOnlyEdit_accepts_phrases_and_repeats(rewrite):
    original = ("Due to the fact that the API is able to time out, add retries prior to the release. "
                "Log every failure. Log every failure.")
    assert isFillerOnlyEdit(original, rewrite)

#Swapping in a shorter word that isn't in the phrase table is rewording, so the Validator sees it
def test_isFillerOnlyEdit_rejects_rewording_beyond_the_table():
    original = "Due to the fact that the API is able to time out, add retries prior to the release."
    assert not isFillerOnlyEdit(original, "Since the API can time out, add retries before the release.")
