"""
Offline unit tests for vagueness detection (agents/vagueness.py). No API calls.
Skipped if the spaCy model en_core_web_sm isn't installed.
"""
import pytest
from agents.auditor import loadNlp
from agents.vagueness import (SLOT_POINTS, REFERENCE_POINTS, WORD_POINTS, MAX_QUESTIONS,
                              findVagueness, findOptionalMarkers, findDroppedOptions, hasAttachedInput)

pytestmark = pytest.mark.skipif(loadNlp() is None, reason="spaCy model en_core_web_sm is not installed")

def signals(prompt: str) -> list[tuple[str, str]]:
    return [(signal.kind, signal.phrase) for signal in findVagueness(prompt).signals]

#Specific prompts score 0, so the questions only show up when they're needed
@pytest.mark.parametrize("prompt", [
    "Could you please write a 150-word product description for a steel water bottle, friendly tone, as 3 bullet points?",
    "Explain the difference between TCP and UDP to a beginner in 3 sentences.",
    "Write a Python function that returns the nth Fibonacci number.",
    "Rank these laptops by battery life: MacBook Air, Dell XPS 13, ThinkPad X1.",
    "Refactor utils.py to remove the duplicated parsing logic.",
    "Write a SQL query that returns the 10 newest orders from the orders table.",
    "Translate \"good morning\" to French.",
    "Please write a haiku about autumn leaves.",
    "Sort these reviews into positive and negative: great, awful, fine, loved it.",
    "Fix this:\n```python\ndef add(a, b): return a - b\n```\nIt returns -1 for add(1, 2) instead of 3.",
    "What is the capital of France?",
    "Write an email to my boss asking for Friday off.",
])
def test_specific_prompts_are_clear(prompt):
    report = findVagueness(prompt)
    assert report.score == 0, report.signals
    assert report.level == "clear" and report.questions == []

#Each task class has its own missing slot
@pytest.mark.parametrize("prompt, phrase", [
    ("Fix the login bug.", "what goes wrong"),
    ("Write a function that checks passwords.", "which language"),
    ("Write a blog post about remote work for developers.", "length or format"),
    ("Write a 500-word article about remote work.", "audience"),
    ("Improve my cover letter: I am a data analyst with five years of experience in SQL and Tableau.", "what to improve"),
    ("Translate this paragraph: the quick brown fox jumps over the lazy dog again.", "target"),
    ("Compare React and Vue.", "criteria"),
    ("Recommend a laptop.", "criteria"),
    ("Classify the following: great, awful, fine.", "categories"),
    ("Can you help me with my essay?", "what to do with my essay"),
])
def test_missing_slots(prompt, phrase):
    assert ("missing slot", phrase) in signals(prompt)

#A slot that's filled anywhere in the prompt isn't missing
@pytest.mark.parametrize("prompt", [
    "Fix the login bug. It throws a 500 error when the password has a space.",
    "Improve the code for readability.",
    "Make the intro shorter.",
    "Compare React and Vue for a small app.",
])
def test_filled_slots(prompt):
    assert not any(kind == "missing slot" and phrase != "what to fix" for kind, phrase in signals(prompt))

#Pointers with nothing attached are empty references; attached input or an earlier mention fills them
def test_empty_references():
    assert ("empty reference", "it") in signals("Make it better.")
    assert ("empty reference", "my essay") in signals("Proofread my essay.")
    assert ("empty reference", "these reviews") in signals("Classify these reviews.")
    assert ("empty reference", "the data") in signals("Clean the data.") #spaCy lemmatizes data -> datum
    assert not any(kind == "empty reference" for kind, _ in signals("Write a poem about the sea and make it short."))
    assert not any(kind == "empty reference" for kind, _ in signals("Proofread my essay: the cat sat on the mat all day long again."))
    assert not any(kind == "empty reference" for kind, _ in signals("Write my bio for the website."))

#"Fix this." is one gap: the empty "this" already asks what to fix
def test_fix_this_is_not_counted_twice():
    phrases = [phrase for _, phrase in signals("Fix this.")]
    assert "this" in phrases and "what to fix" not in phrases

#Judgement words count unless a standard follows, or they're politeness
def test_judgement_words():
    assert ("judgement word", "better") in signals("Make the intro better.")
    assert not any(kind == "judgement word" for kind, _ in signals("Make it cleaner, i.e. no nested ifs."))
    assert not any(kind == "judgement word" for kind, _ in signals("It would be amazing if the names sounded cozy."))

#Fuzzy amounts count unless the sentence has a number; length words are one wish, however often repeated
def test_fuzzy_amounts():
    assert ("fuzzy amount", "a few") in signals("Add a few examples.")
    assert not any(kind == "fuzzy amount" for kind, _ in signals("Add a few examples, at most 3."))
    assert not any(kind == "fuzzy amount" for kind, _ in signals("Write a short story about a dragon for kids, 300 words."))
    lengths = [phrase for kind, phrase in signals("Give me a quick summary. Make it short, nothing too long or detailed.") if kind == "fuzzy amount"]
    assert lengths == ["quick, short, long, detailed"]

#Request verbs with two readings are ambiguous; the same word describing something isn't
def test_ambiguous_words():
    assert ("ambiguous word", "test") in signals("Clean the data and test it.")
    assert ("ambiguous word", "Clean") in signals("Clean the data and test it.") #tagged as an adjective
    assert not any(kind == "ambiguous word" for kind, _ in signals("Write a Python function that checks passwords."))

#"or" between tasks and "anything else you think is relevant" leave the scope open
def test_open_scope():
    assert ("open scope", "fix or rewrite") in signals("Fix the login bug or rewrite the auth module.")
    assert ("open scope", "anything else you think is relevant") in signals("Add tests. Add anything else you think is relevant.")

#Score follows the weights, questions are ordered by points and capped
def test_score_and_questions():
    report = findVagueness("Make it better.")
    assert report.score == SLOT_POINTS + REFERENCE_POINTS + WORD_POINTS
    assert report.level == "vague"
    assert report.questions[0].startswith("Improve it toward what")
    many = findVagueness("Clean the data and test it, make it better and add some stuff, a few things, etc.")
    assert len(many.questions) == MAX_QUESTIONS

#Non-English prompts get an empty report rather than nonsense
def test_non_english_is_skipped():
    report = findVagueness("¿Podrías ayudarme a escribir un poema sobre el mar?")
    assert report.score == 0 and report.signals == []

def test_hasAttachedInput():
    assert hasAttachedInput("Fix `getName`.")
    assert hasAttachedInput("Summarize https://example.com/report")
    assert hasAttachedInput("Rank these: A, B, C")
    assert not hasAttachedInput("Fix this.")

#Hedges on the request make it optional; hedges on a polite wrapper are just politeness
def test_findOptionalMarkers():
    assert findOptionalMarkers("Write the parser. Maybe add tests.") == ["Maybe add tests."]
    assert findOptionalMarkers("If possible, use TypeScript. Feel free to add comments.") == [
        "If possible, use TypeScript.", "Feel free to add comments."]
    assert findOptionalMarkers("I was wondering if you could maybe help me name my bakery?") == []

#Optional parts are reported with 0 points
def test_optional_parts_are_not_scored():
    report = findVagueness("Write a Python script that renames files. Maybe add logging.")
    assert report.optionalParts == ["Maybe add logging."]
    assert all(signal.points == 0 for signal in report.signals if signal.kind == "optional")

#A rewrite must keep an option optional, and keep it at all
@pytest.mark.parametrize("rewrite, expected", [
    ("Write the parser and add tests.", "made required"),
    ("Write the parser.", "dropped"),
])
def test_findDroppedOptions_reports(rewrite, expected):
    reasons = findDroppedOptions("Please write the parser. Maybe add tests.", rewrite)
    assert len(reasons) == 1 and expected in reasons[0]

@pytest.mark.parametrize("rewrite", [
    "Write the parser. Optionally add tests.",
    "Write the parser; add tests if possible.",
    "Write the parser. You can add tests.",
])
def test_findDroppedOptions_allows_kept_options(rewrite):
    assert findDroppedOptions("Please write the parser. Maybe add tests.", rewrite) == []
