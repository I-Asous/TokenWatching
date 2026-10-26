"""
Offline unit tests for the lock check (agents/locks.py). No API calls
"""
import pytest
from agents import auditor, locks
from agents.locks import extractLocks, findBrokenLocks

SQL_PROMPT = ("You write SQL for our `orders` table. "
              "Always use parameterized queries to prevent SQL injection. "
              "Docs: https://example.com/schema.")

#Every test runs twice: with the spaCy model (lemmas) and without it (fallback word matching)
@pytest.fixture(params=["spacy", "fallback"], autouse=True)
def wordMode(request, monkeypatch):
    if request.param == "spacy" and auditor.loadNlp() is None:
        pytest.skip("spaCy model en_core_web_sm is not installed")
    if request.param == "fallback":
        monkeypatch.setattr(locks, "loadNlp", lambda: None)
    return request.param

#Code blocks, inline code, URLs, rules and numbered steps are all found
def test_extractLocks_finds_every_kind():
    prompt = ("Use `pandas`. See https://example.com/docs.\n"
              "```python\nprint('hi')\n```\n"
              "You must keep the column names.\n"
              "1. Load the file.\n2. Clean it.")
    kinds = [lock.kind for lock in extractLocks(prompt)]
    assert kinds == ["code block", "inline code", "url", "constraint", "step", "step"]

#Trailing punctuation isn't part of a URL
def test_extractLocks_strips_url_punctuation():
    urls = [lock.text for lock in extractLocks(SQL_PROMPT) if lock.kind == "url"]
    assert urls == ["https://example.com/schema"]

#The same rule said twice is locked once, so removing the repeat is allowed
def test_extractLocks_skips_repeated_rules():
    prompt = "Never share passwords. Write a poem. Never share passwords."
    assert [lock.text for lock in extractLocks(prompt) if lock.kind == "constraint"] == ["Never share passwords."]
    assert findBrokenLocks(prompt, "Never share passwords. Write a poem.") == []

#The SQL injection case: dropping the rule is caught
def test_dropped_constraint_is_caught():
    rewrite = "SQL for the `orders` table. Docs: https://example.com/schema"
    reasons = findBrokenLocks(SQL_PROMPT, rewrite)
    assert len(reasons) == 1
    assert reasons[0].startswith("constraint dropped") and "parameterized" in reasons[0]

#Cutting the explanation after "to prevent" is allowed, the rule itself is still there
def test_shortened_constraint_passes():
    rewrite = "SQL for the `orders` table. Always use parameterized queries. Docs: https://example.com/schema"
    assert findBrokenLocks(SQL_PROMPT, rewrite) == []

#"Never X" rewritten as "X" flips the meaning
def test_flipped_negation_is_caught():
    reasons = findBrokenLocks("Never use eval on user input.", "Use eval on user input.")
    assert len(reasons) == 1 and reasons[0].startswith("constraint flipped")

#Code blocks must survive exactly, a one-character change fails
def test_changed_code_block_is_caught():
    prompt = "Fix this:\n```python\ndef add(a, b):\n    return a - b\n```"
    assert findBrokenLocks(prompt, "Fix:\n```python\ndef add(a, b):\n    return a - b\n```") == []
    reasons = findBrokenLocks(prompt, "Fix:\n```python\ndef add(a, b):\n    return a + b\n```")
    assert len(reasons) == 1 and reasons[0].startswith("code block")

#Renamed inline code and dropped URLs are caught, a name only inside a longer word doesn't count
def test_dropped_inline_code_and_url_are_caught():
    reasons = findBrokenLocks(SQL_PROMPT, "SQL for the reorders table. Always use parameterized queries.")
    assert 'inline code changed or dropped: "orders"' in reasons
    assert 'url changed or dropped: "https://example.com/schema"' in reasons

#Keeping the name without its backticks is fine, the name is what matters
def test_inline_code_without_backticks_passes():
    rewrite = "SQL for the orders table. Always use parameterized queries. Docs: https://example.com/schema"
    assert findBrokenLocks(SQL_PROMPT, rewrite) == []

#A dropped step and a reordered step are both caught
def test_steps_must_keep_count_and_order():
    prompt = "1. Load the file.\n2. Remove empty rows.\n3. Save the result."
    assert findBrokenLocks(prompt, "1. Load file.\n2. Remove empty rows.\n3. Save result.") == []

    dropped = findBrokenLocks(prompt, "1. Load the file.\n2. Save the result.")
    assert dropped == ['step 2 dropped: "Remove empty rows."']

    reordered = findBrokenLocks(prompt, "1. Load the file.\n2. Save the result.\n3. Remove empty rows.")
    assert reordered == ['step 3 moved out of order: "Save the result."']

#A rewrite that only removes filler keeps every lock
def test_filler_only_rewrite_passes():
    prompt = "Please, could you kindly help me? You must answer in Spanish. Thank you so much!"
    assert findBrokenLocks(prompt, "You must answer in Spanish.") == []

#An unchanged rewrite and a prompt with no locks never fail
def test_no_locks_and_identical_rewrite_pass():
    assert findBrokenLocks(SQL_PROMPT, SQL_PROMPT) == []
    assert findBrokenLocks("Write a story about a dragon.", "Dragon story.") == []

#Every number in the prose is locked; step markers, URLs and inline code aren't numbers
def test_extractLocks_finds_numbers():
    prompt = "Write 3 bullet points under 1,000 characters. See https://example.com/q3 and `v2`.\n1. Draft it.\n2. Cut five words."
    assert [lock.text for lock in extractLocks(prompt) if lock.kind == "number"] == ["3", "1000", "5"]

#A changed number is a broken lock, even inside a constraint whose words all survived
def test_findBrokenLocks_changed_number():
    reasons = findBrokenLocks("Never return more than 100 rows.", "Never return more than 10 rows.")
    assert reasons == ['number dropped or changed: "100" (in "Never return more than 100 rows.")',
                       'number added that the original didn\'t give: "10" (don\'t guess details the person didn\'t state)']

#A number the original never gave is a guess, so it's rejected too
def test_findBrokenLocks_added_number():
    reasons = findBrokenLocks("Please write a short story about a dragon.", "Write a 500-word story about a dragon.")
    assert any('number added' in reason and '"500"' in reason for reason in reasons)

#Numbers may be written as digits or words, and with or without thousands commas
@pytest.mark.parametrize("original, rewrite", [
    ("Please suggest five names.", "Suggest 5 names."),
    ("Keep it under 1,000 words please.", "Keep it under 1000 words."),
])
def test_findBrokenLocks_number_spelling_is_free(original, rewrite):
    assert findBrokenLocks(original, rewrite) == []
