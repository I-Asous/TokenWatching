import re
import textwrap
from dataclasses import dataclass
from agents.auditor import loadNlp

#Words that turn a sentence into a rule the rewrite has to keep ("Always use parameterized queries")
CONSTRAINT_WORDS = ["must", "never", "always", "shall", "required", "ensure", "make sure",
                    "do not", "don't", "cannot", "can't"]
#If the original rule is negative ("Never use eval"), the rewrite must still be negative
NEGATION_WORDS = ["never", "not", "no", "don't", "cannot", "can't", "without", "avoid"]
#Where the rule stops and its explanation starts. Only the part before these is locked, so
#"Always use parameterized queries to prevent SQL injection" may be shortened to "Always use parameterized queries"
REASON_WORDS = ["so that", "because", "since", "in order to", "to prevent", "to avoid",
                "to ensure", "to make sure", "which"]

def wordsRegex(words: list[str]) -> re.Pattern:
    #Matches any of the words as whole words, ignoring case
    return re.compile(r"\b(?:" + "|".join(map(re.escape, words)) + r")\b", re.IGNORECASE)

CONSTRAINT_RE = wordsRegex(CONSTRAINT_WORDS)
NEGATION_RE = wordsRegex(NEGATION_WORDS)
REASON_RE = wordsRegex(REASON_WORDS)

CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
URL_RE = re.compile(r"https?://[^\s)>\]]+")
STEP_RE = re.compile(r"^\s*(?:\d+[.)]|step\s+\d+[:.)]?)\s+(.+)$", re.IGNORECASE | re.MULTILINE)
STEP_MARKER_RE = re.compile(r"^\s*(?:\d+[.)]|step\s+\d+[:.)]?)\s+", re.IGNORECASE | re.MULTILINE)
#"one" is left out: it's more often a pronoun ("the best one") than a count
NUMBER_WORDS = {"two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
                "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15", "twenty": "20",
                "thirty": "30", "fifty": "50", "hundred": "100"}
#Whole numbers only, so "q3" and "v2" aren't numbers, but "3-day" and "$50" are
NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?!\w)|\b(?:" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
WORD_RE = re.compile(r"[a-z]+")

MATCH_SHARE = 0.6 #share of a rule's content words that one sentence of the rewrite must contain
DUPLICATE_SIMILARITY = 0.8 #rules this similar count as one, so removing a repeated rule is allowed
URL_TRAILING_PUNCTUATION = ".,;:!?'\""

#when no spaCy model
FALLBACK_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "if", "of", "to", "in", "on", "at", "for", "with", "by",
    "from", "as", "is", "are", "be", "it", "this", "that", "these", "those", "you", "your", "i", "me",
    "my", "we", "our", "they", "them", "do", "does", "not", "no", "never", "always", "must", "shall",
    "should", "can", "will", "would", "could", "all", "any", "each", "every", "so", "then", "than",
})

@dataclass(frozen=True)
class Lock:
    kind: str #"code block", "inline code", "url", "constraint", "step" or "number"
    text: str
    context: str = "" #for numbers: the sentence it came from, so the reason says which number

"""
* @brief Finds the numbers in a prompt's prose and the sentence each one is in.
* @post
* 1. Code blocks, inline code, URLs and step markers ("1.", "Step 2:") are removed first:
*    they're locked on their own, and "1." isn't a count.
* 2. Number words become digits ("five" -> "5") and thousands commas are dropped ("1,000" -> "1000"),
*    so a rewrite may write a number either way.
* 3. Returns {number: first sentence it appears in}, in order of appearance.
"""
def findNumbers(text: str) -> dict[str, str]:
    prose = URL_RE.sub(" ", INLINE_CODE_RE.sub(" ", CODE_BLOCK_RE.sub("\n", text)))
    prose = STEP_MARKER_RE.sub("", prose)
    numbers: dict[str, str] = {}
    for sentence in splitSentences(prose):
        for match in NUMBER_RE.finditer(sentence):
            value = match.group(0).lower()
            value = NUMBER_WORDS.get(value, re.sub(r"(?<=\d),(?=\d{3}\b)", "", value))
            numbers.setdefault(value, sentence)
    return numbers

"""
* @brief Reduces text to its set of content words, so two sentences can be compared by meaning-carrying words.
* @post
* 1. With the spaCy model: lowercase lemmas of alphabetic, non-stop-word tokens ("queries" -> "query").
* 2. Without it: lowercase words minus a small stop-word list, with common suffixes stripped.
* 3. Both texts in a comparison go through the same path, so they stay comparable.
"""
def contentWords(text: str) -> set[str]:
    nlp = loadNlp()
    if nlp is not None:
        return {token.lemma_.lower() for token in nlp(text) if token.is_alpha and not token.is_stop}
    return {stripSuffix(word) for word in WORD_RE.findall(text.lower()) if word not in FALLBACK_STOP_WORDS}

def stripSuffix(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]
    return word

def normalizeCode(text: str) -> str:
    #Trailing spaces and surrounding blank lines don't matter, indentation does (Python)
    return "\n".join(line.rstrip() for line in text.strip().splitlines())

def containsExactly(text: str, part: str) -> bool:
    #Whole match only, so `orders` isn't found inside "reorders". Backticks around it are optional
    return re.search(rf"(?<!\w){re.escape(part)}(?!\w)", text) is not None

def splitSentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in SENTENCE_SPLIT_RE.split(text) if sentence.strip()]

def ruleWords(sentence: str) -> set[str]:
    return contentWords(REASON_RE.split(sentence, maxsplit=1)[0])

def shorten(text: str) -> str:
    return textwrap.shorten(" ".join(text.split()), width=80, placeholder="...")

"""
* @brief Finds the parts of a prompt that an optimized rewrite must keep.
* @post
* 1. Code blocks, inline code and URLs are locked exactly.
* 2. Sentences with a rule word (must, never, always, do not...) are locked as constraints.
*    Code blocks are removed first, so code doesn't count as a sentence.
* 3. A constraint that repeats an earlier one is skipped, so deduplicating rules stays allowed.
* 4. Numbered lines ("1. ...", "Step 2: ...") are locked as steps, in order.
* 5. Every number in the prose is locked ("under 300 words", "5 names"). Constraints only compare
*    words, so without this "Never return more than 100 rows" -> "...10 rows" would pass.
* 6. The locks are returned in the order above.
"""
def extractLocks(prompt: str) -> list[Lock]:
    prompt = prompt.replace("’", "'") #curly apostrophes, so "don’t" matches "don't" in the word lists
    locks = [Lock("code block", block) for block in CODE_BLOCK_RE.findall(prompt)]
    prose = CODE_BLOCK_RE.sub("\n", prompt)

    locks += [Lock("inline code", code) for code in INLINE_CODE_RE.findall(prose)]
    locks += [Lock("url", url.rstrip(URL_TRAILING_PUNCTUATION)) for url in URL_RE.findall(prose)]

    seenRules: list[set[str]] = []
    for sentence in splitSentences(prose):
        if not CONSTRAINT_RE.search(sentence):
            continue
        words = ruleWords(sentence)
        if not words:
            continue
        if any(len(words & earlier) / len(words | earlier) >= DUPLICATE_SIMILARITY for earlier in seenRules):
            continue
        seenRules.append(words)
        locks.append(Lock("constraint", sentence))

    locks += [Lock("step", step.strip()) for step in STEP_RE.findall(prose)]
    locks += [Lock("number", value, sentence) for value, sentence in findNumbers(prompt).items()]
    return locks

"""
* @brief Checks one constraint sentence against the rewrite.
* @post
* 1. The constraint is kept if one sentence of the rewrite contains at least MATCH_SHARE
*    of the rule's content words (the explanation after "to prevent", "because"... doesn't count).
* 2. If the original rule is negative, that sentence must be negative too, otherwise the
*    meaning flipped ("Never use eval" -> "Use eval").
* 3. Returns None if kept, otherwise the reason it broke.
"""
def checkConstraint(constraint: str, rewriteSentences: list[str]) -> str | None:
    words = ruleWords(constraint)
    negative = bool(NEGATION_RE.search(constraint))
    flipped = False
    for sentence in rewriteSentences:
        if len(words & contentWords(sentence)) / len(words) < MATCH_SHARE:
            continue
        if negative and not NEGATION_RE.search(sentence):
            flipped = True
            continue
        return None
    if flipped:
        return f'constraint flipped (the "not" was lost): "{shorten(constraint)}"'
    return f'constraint dropped: "{shorten(constraint)}"'

"""
* @brief Checks that every numbered step survived, in the same order.
* @post
* 1. Each original step must match a numbered line of the rewrite (same MATCH_SHARE rule as constraints).
* 2. A step that matches an earlier line than the step before it is reported as out of order.
* 3. Returns the list of reasons (empty if every step is kept in order).
"""
def checkSteps(steps: list[str], rewrite: str) -> list[str]:
    rewriteSteps = [contentWords(step) for step in STEP_RE.findall(CODE_BLOCK_RE.sub("\n", rewrite))]
    reasons = []
    lastMatch = -1
    for number, step in enumerate(steps, start=1):
        words = contentWords(step)
        if not words:
            continue
        match = next((index for index, candidate in enumerate(rewriteSteps)
                      if len(words & candidate) / len(words) >= MATCH_SHARE), None)
        if match is None:
            reasons.append(f'step {number} dropped: "{shorten(step)}"')
        elif match < lastMatch:
            reasons.append(f'step {number} moved out of order: "{shorten(step)}"')
        else:
            lastMatch = match
    return reasons

"""
* @brief Compares an optimized rewrite against the original prompt's locks. Runs locally, no API call.
* @post
* 1. Code blocks, inline code and URLs must appear exactly in the rewrite (code compared line by line,
*    ignoring trailing spaces).
* 2. Constraints must survive in some sentence of the rewrite, with negations kept.
* 3. Numbered steps must all survive, in order.
* 4. Every number must still appear in the rewrite's prose (written as digits or as a word).
* 5. A list of readable reasons is returned, one per broken lock (empty if the rewrite keeps everything).
*    The reasons are written so they can be passed straight back to the Optimizer as a RejectedAttempt.
"""
def findBrokenLocks(prompt: str, rewrite: str) -> list[str]:
    prompt = prompt.replace("’", "'")
    rewrite = rewrite.replace("’", "'")
    if prompt.strip() == rewrite.strip():
        return []

    locks = extractLocks(prompt)
    normalizedRewrite = normalizeCode(rewrite)
    rewriteSentences = splitSentences(CODE_BLOCK_RE.sub("\n", rewrite))
    rewriteNumbers = findNumbers(rewrite)
    reasons = []

    for lock in locks:
        if lock.kind == "code block" and normalizeCode(lock.text) not in normalizedRewrite:
            reasons.append(f'code block changed or dropped: "{shorten(lock.text)}"')
        elif lock.kind in ("inline code", "url") and not containsExactly(rewrite, lock.text):
            reasons.append(f'{lock.kind} changed or dropped: "{lock.text}"')
        elif lock.kind == "constraint":
            reason = checkConstraint(lock.text, rewriteSentences)
            if reason:
                reasons.append(reason)
        elif lock.kind == "number" and lock.text not in rewriteNumbers:
            reasons.append(f'number dropped or changed: "{lock.text}" (in "{shorten(lock.context)}")')

    steps = [lock.text for lock in locks if lock.kind == "step"]
    reasons += checkSteps(steps, rewrite)
    return reasons


if __name__ == "__main__":
    original = ("You are a SQL assistant. Please write queries for our `orders` table. "
                "Always use parameterized queries to prevent SQL injection. Never return more than 100 rows.\n"
                "1. Read the question.\n2. Write the query.\n3. Explain it in one sentence.")
    rewrites = {
        "keeps everything": ("SQL assistant for the `orders` table. Always use parameterized queries. "
                             "Never return more than 100 rows.\n1. Read the question.\n2. Write the query.\n3. Explain it in one sentence."),
        "drops the SQL rule": ("SQL assistant for the `orders` table. Never return more than 100 rows.\n"
                               "1. Read the question.\n2. Write the query.\n3. Explain it in one sentence."),
        "flips a rule, drops a step": ("SQL assistant for the `orders` table. Always use parameterized queries. "
                                       "Return more than 100 rows.\n1. Read the question.\n2. Write the query."),
    }
    for name, candidate in rewrites.items():
        print(f"{name}: {findBrokenLocks(original, candidate) or 'all locks kept'}")
