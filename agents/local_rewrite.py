import re
from dataclasses import dataclass
from spacy.lang.en.stop_words import STOP_WORDS
from agents.auditor import (MAX_SPANS_SHOWN, CODE_BLOCK_RE, maskProtected, findRemovableFiller, findWordyPhraseMatches,
                            shortFormOf, runRuleCheck)
from agents.optimizer import OptimizationResult, findRewriteProblems
from agents.tokens import countTokens, DEFAULT_TARGET
from agents.vagueness import PASTED_AFTER_COLON_RE

#Only the edges of a prompt or sentence are deleted, never a word inside one: "How do I say thank you in Japanese?",
#"the just war theory" and "a band like Thank You Scientist" all use these words as what they're asking about.
#Anything else is left for the Optimizer, since a missed cut costs a call and a wrong cut changes the request

#A greeting needs punctuation or a request after it, so "Hello World in Rust" and "Hi-fi speakers" aren't greetings
GREETING_RE = re.compile(r"(?:hi|hey|hello|good (?:morning|afternoon|evening))(?: there)?"
                         r"(?:[!,.]+(?!\s*world\b)|(?=\s+(?:could|can|would|please|i)\b)|(?=\s*$))", re.IGNORECASE)
HOPE_RE = re.compile(r"(?:i\s+)?hope (?:you're|you are) (?:doing )?(?:well|good|great|having an? (?:\w+ )?"
                     r"(?:day|week|morning|afternoon|evening))[!.,]*", re.IGNORECASE)
PLEASE_START_RE = re.compile(r"please\b(?![-'])(?!\s+(?:is|means|was)\b),?", re.IGNORECASE)
#Only with a comma: "How do you say please?" ends in the word it's asking about
TRAILING_PLEASE_RE = re.compile(r",\s*please(?=[.!?:]*\s*$)", re.IGNORECASE)
#Verbs that ask the model to do something. Verbs people use with a general "you" are left out: "Can you freeze
#cooked rice?" and "Can you build muscle on a vegan diet?" are questions, and cutting "Can you" makes them commands
REQUEST_VERBS = (r"write(?!\s+off\b)|draft|compose|rewrite|rephrase|proofread|summarize|summarise|translate|explain|"
                 r"describe|define|suggest|recommend|list|compare|review|brainstorm|outline|(?:tell|give|show|teach) (?:me|us)")
REQUEST_WRAPPER_RE = re.compile(
    r"(?:(?:could|can|would) you(?:\s+(?:please|kindly|possibly|maybe))*(?:\s+help me(?:\s+to)?|\s+be so kind as to)?"
    r"|i (?:was|am) (?:just )?wondering if you could(?:\s+(?:please|maybe))*"
    r"|i(?:'d| would) (?:really |greatly )?(?:like|love) (?:it )?if you could(?:\s+please)?"
    r"|is it possible for you to|kindly)"
    rf"(?=\s+(?:{REQUEST_VERBS})\b)", re.IGNORECASE)
#A sentence made of nothing but thanks. "Thanks for helping with this" has to go whole: cutting only "Thanks" leaves "for helping with this"
THANKS = (r"(?:(?:many )?thanks?(?: you)?(?: so much| very much| a lot| a ton| in advance)*"
          r"(?: for (?:your|the|any|all|this|helping|that)(?: me)?(?: (?:help|time|assistance))?(?: with (?:this|that|it))?)?(?: in advance)?"
          r"|cheers"
          r"|i(?:'d| would)? (?:really |greatly |truly )?appreciate (?:it|this|any help|your help)(?: (?:so|very) much)?"
          r"|(?:any|your) help (?:is|would be) (?:greatly |much |really )?appreciated)")
CLOSING_SENTENCE_RE = re.compile(rf"{THANKS}(?:[,;]?\s*(?:and\s+)?{THANKS})*[!.]*", re.IGNORECASE)

#A sentence ends after .!? followed by whitespace, or at a newline. Only sentences with a deletion are tidied,
#every other one is kept byte for byte
SENTENCE_END_RE = re.compile(r"[.!?]+(?=\s)|\n")
WORD_RE = re.compile(r"[\w'-]+")
#A sentence starting with one of these is still a question once its wrapper is gone ("Can you tell me
#what DNS is?" -> "Tell me what DNS is." but "Could you check... Is it safe?" stays a question)
QUESTION_STARTS = frozenset({"what", "which", "who", "whom", "whose", "when", "where", "why", "how", "is", "are",
                             "am", "was", "were", "do", "does", "did", "can", "could", "would", "will", "should",
                             "shall", "may", "might", "have", "has", "had", "must"})
#Two or more blank lines (whitespace-only lines count), and "!!" or "??": they take tokens and say nothing more
EXTRA_BLANK_LINES_RE = re.compile(r"\n[ \t]*(?:\n[ \t]*){2,}")
REPEATED_MARKS_RE = re.compile(r"([!?])\1+")
#A list item ("- Run tests", "2) Deploy"): the same item under two headings is two tasks, not a repeat
LIST_ITEM_RE = re.compile(r"(?:[-*•]|\d+[.)])\s")
#A repeated sentence shorter than this ("Thanks!", "Yes.") is left alone
MIN_REPEAT_WORDS = 3

@dataclass(frozen=True)
class Deletion:
    start: int
    end: int

"""
* @brief Finds the politeness a rewrite can delete without an LLM.
* @post
* 1. A greeting and "I hope you're well" are deleted only at the very start of the prompt.
* 2. At the start of any sentence, "Please" and a request wrapper directly before a REQUEST_VERBS verb are
*    deleted ("Could you please write..."). A wrapper before any other verb is kept ("Can you freeze rice?").
* 3. ", please" at the end of a sentence is deleted, and so are whole closing sentences of thanks at the end of the prompt.
* 4. Words inside a sentence are never deleted, so a filler word or a phrase the prompt is about stays.
* 5. Code blocks, quoted text and optional sentences are skipped (maskProtected), and so is everything from
*    pasted material after a colon on ("Summarize this: I would really appreciate it if you could stop.").
* 6. Returns the deletions in order, as offsets into text.
"""
def findDeletions(text: str) -> list[Deletion]:
    masked = maskProtected(text.replace("’", "'"))
    pasted = PASTED_AFTER_COLON_RE.search(masked)
    materialStart = pasted.start() if pasted else len(masked)
    sentences = [strippedRange(masked, start, end) for start, end in sentenceRanges(masked) if masked[start:end].strip()]
    ranges = []

    opening = True
    for start, end in sentences:
        if start >= materialStart:
            break
        position = start
        if opening:
            position = takeMatch(GREETING_RE, masked, position, end, ranges)
            hope = HOPE_RE.fullmatch(masked, position, end)
            if hope:
                ranges.append((position, hope.end()))
                position = end
            opening = position == end
        position = takeMatch(PLEASE_START_RE, masked, position, end, ranges)
        takeMatch(REQUEST_WRAPPER_RE, masked, position, end, ranges)
        trailing = TRAILING_PLEASE_RE.search(masked, start, end)
        if trailing and end <= materialStart:
            ranges.append((trailing.start(), trailing.end()))

    for start, end in reversed(sentences):
        if end > materialStart or not CLOSING_SENTENCE_RE.fullmatch(masked, start, end):
            break
        ranges.append((start, end))
    return [Deletion(start, end) for start, end in sorted(set(ranges))]

#Adds a match at this position to ranges, and returns where the text after it starts
def takeMatch(pattern: re.Pattern, text: str, position: int, end: int, ranges: list[tuple[int, int]]) -> int:
    match = pattern.match(text, position, end)
    if not match:
        return position
    ranges.append((match.start(), match.end()))
    return strippedRange(text, match.end(), end)[0]

def strippedRange(text: str, start: int, end: int) -> tuple[int, int]:
    part = text[start:end]
    return end - len(part.lstrip()), start + len(part.rstrip())

def sentenceRanges(text: str) -> list[tuple[int, int]]:
    starts = [0] + [match.end() for match in SENTENCE_END_RE.finditer(text)]
    ends = starts[1:] + [len(text)]
    return [(start, end) for start, end in zip(starts, ends) if start < end]

"""
* @brief Deletes spans from one sentence and repairs the punctuation and capitals they leave behind.
* @post
* 1. The spans are cut, then doubled spaces, spaces before punctuation, commas left before the end and
*    punctuation left at the start are removed.
* 2. A sentence with no words left ("Thanks!") is dropped along with its leading whitespace.
* 3. A sentence left with only stop words ("Could you please help me with this?" -> "this?") is a fragment,
*    not a request, so None is returned and the caller leaves the prompt to the Optimizer.
* 4. If the cut was at the start, the first letter is capitalized, and a "?" ending becomes "." unless
*    the sentence still starts like a question ("Could you write a poem?" -> "Write a poem.").
* 5. Whitespace around the sentence is kept, so the lines and paragraphs around it don't move.
"""
def tidySentence(sentence: str, spans: list[tuple[int, int]]) -> str | None:
    leading = sentence[:len(sentence) - len(sentence.lstrip())]
    trailing = sentence[len(sentence.rstrip()):]
    cutAtStart = spans[0][0] <= len(leading)
    for start, end in reversed(spans):
        sentence = sentence[:start] + sentence[end:]

    core = sentence.strip()
    core = re.sub(r"[ \t]{2,}", " ", core)
    core = re.sub(r"[ \t]+(?=[,.!?;:])", "", core)
    core = re.sub(r"[,;:](?:\s*([,;:]))+", r"\1", core)
    core = re.sub(r"[,;]+(?=[.!?:]|$)", "", core)
    core = re.sub(r"^[\s,.!?;:]+", "", core)
    words = WORD_RE.findall(core)
    if not words:
        return trailing if "\n" in trailing else ""
    if all(word.lower() in STOP_WORDS for word in words):
        return None

    if cutAtStart:
        core = core[0].upper() + core[1:]
        firstWord = WORD_RE.match(core)
        if core.endswith("?") and "¿" not in core and (firstWord is None or firstWord.group(0).lower() not in QUESTION_STARTS):
            core = core.rstrip("?") + "."
    return leading + core + trailing

"""
* @brief Deletes every span from findDeletions and tidies the sentences they were in.
* @post
* 1. Each deletion belongs to the sentence it starts in (clipped to that sentence's end).
* 2. Sentences without a deletion are copied exactly; the others go through tidySentence.
* 3. The result is stripped and returned, with the deleted spans as text for the changes list.
* 4. If any sentence is left as a fragment (tidySentence returns None), the rewrite is "" so the caller
*    doesn't use it.
"""
def deleteFiller(text: str) -> tuple[str, list[str]]:
    deletions = findDeletions(text)
    deleted = [text[deletion.start:deletion.end] for deletion in deletions]
    parts = []
    for start, end in sentenceRanges(text):
        spans = [(max(deletion.start, start) - start, min(deletion.end, end) - start)
                 for deletion in deletions if start <= deletion.start < end]
        part = tidySentence(text[start:end], spans) if spans else text[start:end]
        if part is None:
            return "", deleted
        parts.append(part)
    return "".join(parts).strip(), deleted

"""
* @brief Collapses extra blank lines and repeated "!!" or "??" outside code and quoted text.
* @post
* 1. Two or more blank lines become one, except inside a code block, where blank lines may matter.
* 2. A run of "!" or "?" becomes one, except in code blocks, quoted text and optional sentences (maskProtected).
* 3. Returns the text and whether anything changed.
"""
def tidyWhitespace(text: str) -> tuple[str, bool]:
    codeBlocks = [match.span() for match in CODE_BLOCK_RE.finditer(text)]
    edits = [(match.start(), match.end(), "\n\n") for match in EXTRA_BLANK_LINES_RE.finditer(text)
             if not any(start <= match.start() < end for start, end in codeBlocks)]
    edits += [(match.start(), match.end(), match.group(1)) for match in REPEATED_MARKS_RE.finditer(maskProtected(text))]
    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text, bool(edits)

"""
* @brief Finds sentences that repeat an earlier sentence word for word.
* @post
* 1. Two sentences are the same when they have the same words in the same order, ignoring capitals,
*    punctuation and spacing. A near-repeat ("Keep it short." after "Make it brief.") is left for the Optimizer:
*    only an exact repeat is sure to add nothing.
* 2. Only finished prose sentences are compared: a sentence must end in . ! or ?, have at least MIN_REPEAT_WORDS
*    words, not be a list item, and hold no code, quoted text or optional request (maskProtected).
*    Everything from pasted material after a colon on is skipped.
* 3. Returns the range of every later copy, including the whitespace before it, as offsets into text.
"""
def findRepeatedSentences(text: str) -> list[tuple[int, int]]:
    text = text.replace("’", "'")
    masked = maskProtected(text)
    pasted = PASTED_AFTER_COLON_RE.search(masked)
    materialStart = pasted.start() if pasted else len(masked)
    seen: set[tuple[str, ...]] = set()
    repeats = []
    for start, end in sentenceRanges(masked):
        if end > materialStart:
            break
        sentence = masked[start:end].strip()
        if masked[start:end] != text[start:end] or not sentence.endswith((".", "!", "?")) or LIST_ITEM_RE.match(sentence):
            continue
        words = tuple(word.lower() for word in WORD_RE.findall(sentence))
        if len(words) < MIN_REPEAT_WORDS:
            continue
        if words in seen:
            repeats.append((start, end))
        else:
            seen.add(words)
    return repeats

#Deletes every word-for-word repeat of an earlier sentence, and returns the text and the sentences deleted
def deleteRepeatedSentences(text: str) -> tuple[str, list[str]]:
    repeats = findRepeatedSentences(text)
    deleted = [text[start:end].strip() for start, end in repeats]
    for start, end in reversed(repeats):
        text = text[:start] + text[end:]
    return text, deleted

"""
* @brief Replaces each wordy phrase (auditor.WORDY_PHRASES) with its shorter form.
* @post
* 1. Code, quoted text, optional sentences and pasted material are left alone (findWordyPhraseMatches).
* 2. A phrase starting with a capital gets a capitalized replacement ("In order to" -> "To").
* 3. Returns the text and each replacement made, once, as "'phrase' -> 'short'".
"""
def replaceWordyPhrases(text: str) -> tuple[str, list[str]]:
    replaced = []
    for match in reversed(findWordyPhraseMatches(text)):
        short = shortFormOf(match.group(0))
        if match.group(0)[0].isupper():
            short = short[0].upper() + short[1:]
        text = text[:match.start()] + short + text[match.end():]
        replaced.append(f"'{match.group(0)}' -> '{short}'")
    return text, list(dict.fromkeys(reversed(replaced)))

def quoteSpans(spans: list[str]) -> str:
    return ", ".join(f"'{span}'" for span in list(dict.fromkeys(spans))[:MAX_SPANS_SHOWN])

"""
* @brief Makes every edit that can't change what a prompt asks for, in order, and lists them.
* @post
* 1. Extra blank lines and repeated "!!" go (tidyWhitespace), then word-for-word repeated sentences
*    (deleteRepeatedSentences), then wordy phrases are shortened (replaceWordyPhrases).
* 2. Politeness and filler are deleted last (deleteFiller), and only when the Auditor's filler check flags the
*    prompt (findRemovableFiller), so a lone "Please" isn't cut. If deleting it would leave a fragment, the
*    other edits are kept without it.
* 3. Returns the stripped text and one line per kind of edit made.
"""
def localEdits(prompt: str) -> tuple[str, list[str]]:
    changes = []
    text, tidied = tidyWhitespace(prompt)
    if tidied:
        changes.append("removed extra blank lines and repeated punctuation")
    text, repeated = deleteRepeatedSentences(text)
    if repeated:
        changes.append(f"removed repeated sentences: {quoteSpans(repeated)}")
    text, shortened = replaceWordyPhrases(text)
    if shortened:
        changes.append(f"shortened wordy phrases: {', '.join(shortened[:MAX_SPANS_SHOWN])}")
    if findRemovableFiller(prompt) is not None:
        withoutFiller, deleted = deleteFiller(text)
        if withoutFiller and deleted:
            text = withoutFiller
            changes.append(f"removed politeness and filler: {quoteSpans(deleted)}")
    return text.strip(), changes

"""
* @brief Rewrites a prompt without an LLM, when edits that can't change the request are all it needs.
* @post
* 1. The edits are made by localEdits: blank lines and repeated punctuation, word-for-word repeated sentences,
*    wordy phrases, and politeness and filler when the Auditor's filler check flags the prompt.
* 2. The rewrite must pass findRewriteProblems, save tokens with the target's tokenizer, and, if requireClean,
*    leave nothing for the rule checks to flag (minus skipChecks). Otherwise None is returned and the
*    Optimizer handles the prompt.
* 3. Without requireClean the rewrite may leave other issues (long sentences, dense wording). It's still
*    safe, so the orchestrator offers it to the Optimizer and falls back to it when no LLM rewrite passes.
* 4. Returns an OptimizationResult like the Optimizer's, with one change line per kind of edit.
"""
def localRewrite(prompt: str, target: str = DEFAULT_TARGET, skipChecks: frozenset[str] = frozenset(),
                 requireClean: bool = True) -> OptimizationResult | None:
    rewrite, changes = localEdits(prompt)
    if not rewrite or rewrite == prompt.strip() or findRewriteProblems(prompt, rewrite):
        return None

    originalTokens = countTokens(prompt, target)
    optimizedTokens = countTokens(rewrite, target)
    if optimizedTokens >= originalTokens or (requireClean and runRuleCheck(rewrite, optimizedTokens, skipChecks)):
        return None

    tokensSaved = originalTokens - optimizedTokens
    return OptimizationResult(
        originalPrompt=prompt,
        optimizedPrompt=rewrite,
        originalTokens=originalTokens,
        optimizedTokens=optimizedTokens,
        tokensSaved=tokensSaved,
        percentSaved=round(tokensSaved / originalTokens * 100, 2),
        changes=changes,
    )

"""
* @brief Tells whether a rewrite only made edits the local rewrite could have made (deleted politeness and
* filler or a word-for-word repeated sentence, shortened a wordy phrase), so it can't have changed what the
* prompt asks for and needs no Validator call.
* @post
* 1. Wordy phrases are shortened in both texts first (replaceWordyPhrases), so "to" in the rewrite matches
*    "in order to" in the original, whichever of the two forms each one uses.
* 2. Both texts are then compared as lowercase words, so capitals, punctuation and spacing don't count.
* 3. The rewrite's words must appear in the original in the same order, and every original word it left out
*    must be inside a span findDeletions would delete or a repeated sentence (findRepeatedSentences). No word
*    may be added or reworded, and a word cut from inside a sentence ("really", "thank you") goes to the Validator.
* 4. Words are matched greedily, so an unusual repeat can be reported False; that only costs a Validator call.
* 5. Code, URLs and numbers are compared exactly by findRewriteProblems, which must run before this.
"""
def isFillerOnlyEdit(original: str, rewrite: str) -> bool:
    original = replaceWordyPhrases(original.replace("’", "'"))[0]
    rewrite = replaceWordyPhrases(rewrite.replace("’", "'"))[0]
    removable = [(deletion.start, deletion.end) for deletion in findDeletions(original)] + findRepeatedSentences(original)
    originalWords = [(match.group(0).lower(), any(start <= match.start() and match.end() <= end for start, end in removable))
                     for match in WORD_RE.finditer(original)]
    index = 0
    for word in (match.group(0).lower() for match in WORD_RE.finditer(rewrite)):
        while index < len(originalWords) and originalWords[index][0] != word:
            if not originalWords[index][1]:
                return False
            index += 1
        if index == len(originalWords):
            return False
        index += 1
    return all(removable for _, removable in originalWords[index:])


if __name__ == "__main__":
    samples = [
        "Please, could you kindly write a short story about a dragon? Thank you so much!",
        "Hi there! I hope you're doing well. Can you summarize this article for me, please? Thanks in advance!",
        "Hey, could you please help me fix this, it's really bugging me:\n```python\ndef add(a, b): return a - b\n```",
        "Could you please write a 150-word bio for our CEO? Do NOT mention their age. Maybe add a quote. Thanks!",
        "Please explain the difference between TCP and UDP.",
    ]
    for sample in samples:
        result = localRewrite(sample)
        print(repr(sample))
        print("  ->", repr(result.optimizedPrompt) if result else None, result.changes if result else "")
        print("  deleteFiller:", repr(deleteFiller(sample)[0]))
