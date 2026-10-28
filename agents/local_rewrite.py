import re
from dataclasses import dataclass
from agents.auditor import POLITENESS_RE, MAX_SPANS_SHOWN, maskProtected, findRemovableFiller, runRuleCheck
from agents.optimizer import OptimizationResult, findRewriteProblems
from agents.tokens import countTokens, DEFAULT_TARGET

#Filler words that are safe to delete outright. The Auditor's FILLER_WORDS also has words that
#carry meaning ("best", "perfect", "somewhat", "maybe"), which it only counts, so they're left to the Optimizer
DELETABLE_FILLER = ["please", "thank you", "really", "basically", "essentially", "literally", "just"]
DELETABLE_FILLER_RE = re.compile(r"\b(?:" + "|".join(map(re.escape, DELETABLE_FILLER)) + r")\b", re.IGNORECASE)

#A sentence ends after .!? followed by whitespace, or at a newline. Only sentences with a deletion are tidied,
#every other one is kept byte for byte
SENTENCE_END_RE = re.compile(r"[.!?]+(?=\s)|\n")
WORD_RE = re.compile(r"[\w'-]+")
#A sentence starting with one of these is still a question once its wrapper is gone ("Can you tell me
#what DNS is?" -> "Tell me what DNS is." but "Could you check... Is it safe?" stays a question)
QUESTION_STARTS = frozenset({"what", "which", "who", "whom", "whose", "when", "where", "why", "how", "is", "are",
                             "am", "was", "were", "do", "does", "did", "can", "could", "would", "will", "should",
                             "shall", "may", "might", "have", "has", "had", "must"})

@dataclass(frozen=True)
class Deletion:
    start: int
    end: int

"""
* @brief Finds the politeness and filler a rewrite can delete without an LLM.
* @post
* 1. Politeness phrases (the Auditor's POLITENESS_PATTERNS) and DELETABLE_FILLER words are matched outside
*    code blocks and optional sentences (maskProtected), so code and "Maybe add tests." are never touched.
* 2. Overlapping matches are merged, and whitespace at either end of a match is left in the text.
* 3. Returns the deletions in order, as offsets into text.
"""
def findDeletions(text: str) -> list[Deletion]:
    masked = maskProtected(text.replace("’", "'"))
    ranges = sorted((match.start(), match.end()) for pattern in (POLITENESS_RE, DELETABLE_FILLER_RE)
                    for match in pattern.finditer(masked) if match.group(0).strip())
    merged: list[list[int]] = []
    for start, end in ranges:
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        elif start < end:
            merged.append([start, end])
    return [Deletion(start, end) for start, end in merged]

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
* 3. If the cut was at the start, the first letter is capitalized, and a "?" ending becomes "." unless
*    the sentence still starts like a question ("Could you write a poem?" -> "Write a poem.").
* 4. Whitespace around the sentence is kept, so the lines and paragraphs around it don't move.
"""
def tidySentence(sentence: str, spans: list[tuple[int, int]]) -> str:
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
    if not WORD_RE.search(core):
        return trailing if "\n" in trailing else ""

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
"""
def deleteFiller(text: str) -> tuple[str, list[str]]:
    deletions = findDeletions(text)
    parts = []
    for start, end in sentenceRanges(text):
        spans = [(max(deletion.start, start) - start, min(deletion.end, end) - start)
                 for deletion in deletions if start <= deletion.start < end]
        parts.append(tidySentence(text[start:end], spans) if spans else text[start:end])
    return "".join(parts).strip(), [text[deletion.start:deletion.end] for deletion in deletions]

"""
* @brief Rewrites a prompt without an LLM, when deleting its politeness and filler is all it needs.
* @post
* 1. Only runs when the Auditor's filler check flagged the prompt (findRemovableFiller), so the audit's
*    issues came from the rule checks, not the LLM review, and there is enough to cut to be worth it.
* 2. The spans are deleted (deleteFiller) and the rewrite must pass findRewriteProblems, save tokens with
*    the target's tokenizer, and leave nothing for the rule checks to flag (minus skipChecks).
*    Otherwise None is returned and the Optimizer handles the prompt.
* 3. Returns an OptimizationResult like the Optimizer's, listing the deleted spans as its change.
"""
def localRewrite(prompt: str, target: str = DEFAULT_TARGET,
                 skipChecks: frozenset[str] = frozenset()) -> OptimizationResult | None:
    if findRemovableFiller(prompt) is None:
        return None
    rewrite, deleted = deleteFiller(prompt)
    if not rewrite or rewrite == prompt.strip() or findRewriteProblems(prompt, rewrite):
        return None

    originalTokens = countTokens(prompt, target)
    optimizedTokens = countTokens(rewrite, target)
    if optimizedTokens >= originalTokens or runRuleCheck(rewrite, optimizedTokens, skipChecks):
        return None

    tokensSaved = originalTokens - optimizedTokens
    shown = ", ".join(f"'{span}'" for span in list(dict.fromkeys(deleted))[:MAX_SPANS_SHOWN])
    return OptimizationResult(
        originalPrompt=prompt,
        optimizedPrompt=rewrite,
        originalTokens=originalTokens,
        optimizedTokens=optimizedTokens,
        tokensSaved=tokensSaved,
        percentSaved=round(tokensSaved / originalTokens * 100, 2),
        changes=[f"removed politeness and filler: {shown}"],
    )

"""
* @brief Tells whether a rewrite only deleted politeness and filler from the original, so it can't have
* changed what the prompt asks for and needs no Validator call.
* @post
* 1. Both texts are compared as lowercase words, so capitals, punctuation and spacing don't count.
* 2. The rewrite's words must appear in the original in the same order, and every original word it
*    left out must be inside a span findDeletions would delete. No word may be added or reworded.
* 3. Words are matched greedily, so an unusual repeat can be reported False; that only costs a Validator call.
* 4. Code, URLs and numbers are compared exactly by findRewriteProblems, which must run before this.
"""
def isFillerOnlyEdit(original: str, rewrite: str) -> bool:
    original = original.replace("’", "'")
    rewrite = rewrite.replace("’", "'")
    deletions = findDeletions(original)
    originalWords = [(match.group(0).lower(), any(d.start <= match.start() and match.end() <= d.end for d in deletions))
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
