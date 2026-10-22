"""
Offline unit tests for intent detection (agents/intent.py). No API calls.
Skipped if the spaCy model en_core_web_sm isn't installed.
"""
import pytest
from agents.auditor import loadNlp
from agents.intent import QUESTION, UNCLEAR, VERB_CLASS, ACTION_CLASSES, detectIntent

pytestmark = pytest.mark.skipif(loadNlp() is None, reason="spaCy model en_core_web_sm is not installed")

def actions(prompt: str) -> list[tuple[str, str, str | None]]:
    return [(action.actionClass, action.verb, action.object) for action in detectIntent(prompt).actions]

#Plain commands: class, verb and object
@pytest.mark.parametrize("prompt, expected", [
    ("Write a Python function that checks passwords.", ("generate", "write", "a Python function")),
    ("Summarize this article.", ("extract", "summarize", "this article")),
    ("Translate this email into French.", ("transform", "translate", "this email")),
    ("Generate 5 names for my bakery.", ("generate", "generate", "5 names")),
    ("Tell me about black holes.", ("explain", "tell", "black holes")),
])
def test_plain_commands(prompt, expected):
    assert actions(prompt) == [expected]

#Polite wrappers are walked past to the real request
@pytest.mark.parametrize("prompt, expected", [
    ("Could you please help me fix this bug?", ("fix", "fix", "this bug")),
    ("I need you to summarize this article.", ("extract", "summarize", "this article")),
    ("I'd like you to translate this email into French.", ("transform", "translate", "this email")),
    ("Hey, could you create a workout plan for beginners?", ("generate", "create", "a workout plan")),
    ("Help me write a poem about the sea.", ("generate", "write", "a poem")),
])
def test_wrappers_are_skipped(prompt, expected):
    assert actions(prompt) == [expected]

#The small model tags these command verbs as nouns, the first-word fallback still finds them
@pytest.mark.parametrize("prompt, expected", [
    ("List 5 common causes of a slow laptop and how to fix each.", ("extract", "list", "5 common causes")),
    ("Debug this code.", ("fix", "debug", "this code")),
])
def test_mistagged_command_verbs(prompt, expected):
    assert actions(prompt) == [expected]

#Questions are QUESTION, but "can you X?" is a request
def test_questions_vs_polite_requests():
    assert actions("How do I reverse a list in Python?")[0][0] == QUESTION
    assert actions("What is the capital of France?")[0][0] == QUESTION
    assert actions("Is Python faster than Java?") == [(QUESTION, "be", "Python")]
    assert actions("Can you explain recursion to a 10-year-old?")[0][:2] == ("explain", "explain")

#A request whose action isn't stated is UNCLEAR, with what it's about kept
def test_unclear_request():
    assert actions("Can you help me with my essay?") == [(UNCLEAR, "help", "my essay")]

#"I need / want X" with no verb asks for X to be produced
def test_want_noun_is_generate():
    assert actions("I need a 3-day itinerary for Rome.") == [("generate", "need", "a 3-day itinerary")]

#Constraints, negated verbs and context aren't actions
@pytest.mark.parametrize("prompt", [
    "Keep it short.",
    "Make sure to mention SQL.",
    "Don't write any code.",
    "I have a knee injury.",
    "Thanks so much!",
])
def test_constraints_and_context_add_nothing(prompt):
    assert actions(prompt) == []

#"make it shorter" transforms "it", but "make sure" is a constraint
def test_make_with_adjective():
    assert actions("Make it better.") == [("transform", "make", "it")]

#Joined verbs are separate actions; "or" marks them as alternatives
def test_multiple_actions():
    intent = detectIntent("Summarize the report and list the key risks.")
    assert [action.verb for action in intent.actions] == ["summarize", "list"]
    assert intent.isMultiIntent and not intent.hasAlternatives

    intent = detectIntent("Fix the login bug or rewrite the auth module.")
    assert [action.verb for action in intent.actions] == ["fix", "rewrite"]
    assert intent.hasAlternatives

#A constraint joined to a wrapped request isn't a second, unclear action
def test_joined_constraint_is_not_unclear():
    assert actions("Could you help me fix this and keep it short?") == [("fix", "fix", "this")]

#Actions across sentences are all found; greetings and constraints in between are skipped
def test_actions_across_sentences():
    prompt = "Hi there! Please rewrite my cover letter. Keep it under 300 words. Then translate it into Spanish."
    assert [action.verb for action in detectIntent(prompt).actions] == ["rewrite", "translate"]

#Every compared item stays in the object
def test_joined_objects_are_kept():
    assert actions("I want you to compare React and Vue for a small app.") == [("compare", "compare", "React and Vue")]

#Code blocks aren't parsed as English; a clause is the object when there's no noun
def test_code_block_is_ignored():
    prompt = "Explain why this returns undefined:\n```javascript\nfunction getName(user) { user.name; }\n```"
    assert actions(prompt) == [("explain", "explain", "why this returns undefined")]

def test_empty_prompt():
    intent = detectIntent("   ")
    assert intent.actions == [] and intent.primary is None and not intent.isMultiIntent

#Each verb belongs to one class only
def test_verb_classes_dont_overlap():
    assert len(VERB_CLASS) == sum(len(verbs) for verbs in ACTION_CLASSES.values())
