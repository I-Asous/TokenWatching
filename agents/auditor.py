import re
import logging
from dataclasses import dataclass, field
from functools import lru_cache
import spacy
import textstat
import tiktoken
from agents.tokens import countTokens, DEFAULT_TARGET
from agents.prompt_types import CHECK_TOKEN_RATIO, CHECK_READABILITY, CHECK_ADVERBS

logger = logging.getLogger(__name__)

FILLER_WORDS = frozenset({
    "please", "thank you", "really", "basically", "essentially", "maybe",
    "possibly", "just", "hopefully", "somewhat", "amazing", "perfect",
    "literally", "best",
})

# \b word boundaries so "just" doesn't match inside "adjust", "best" inside "bestow", etc.
FILLER_RE = re.compile(r"\b(?:" + "|".join(map(re.escape, FILLER_WORDS)) + r")\b", re.IGNORECASE)

#Politeness comes in phrases more than single words ("could you kindly help me", "thank you so much"),
#so these are matched as whole spans. Each one can be cut without changing what the prompt asks for
POLITENESS_PATTERNS = [
    #greetings, at the start of the prompt or a line
    r"^\s*(?:hi|hey|hello|good (?:morning|afternoon|evening))(?: there)?\b[!,.]*",
    r"\bi hope (?:you're|you are) (?:doing )?well\b[!.]*",
    #request wrappers
    r"\b(?:could|can|would) you(?: please| kindly| possibly| maybe)*(?: help me(?: (?:to|with|out))?| be so kind as to)?\b",
    r"\bwould you mind\b",
    r"\bi (?:was|am) (?:just )?wondering if(?: you could)?\b",
    r"\bi(?:'d| would) (?:really |greatly )?(?:like|love) (?:it )?if you could\b",
    r"\bis it possible (?:for you )?to\b",
    r"\bif you don't mind\b",
    r"\bkindly\b",
    #closings
    r"\bthanks?(?: you)?(?: so much| very much| a lot| in advance)?\b[!.]*",
    r"\bmany thanks\b[!.]*",
    r"\bcheers\b[!.]*",
    r"\bi(?:'d| would) (?:really |greatly |truly )?appreciate (?:it|any help|your help)(?: so much)?\b[!.]*",
    r"\b(?:any|your) help (?:is|would be) (?:greatly |much |really )?appreciated\b[!.]*",
    #apologies
    r"\bsorry (?:to bother you|for the trouble|if this is (?:a )?(?:dumb|stupid|silly) question)\b[!.]*",
]
POLITENESS_RE = re.compile("|".join(f"(?:{pattern})" for pattern in POLITENESS_PATTERNS), re.IGNORECASE | re.MULTILINE)
#Wordy phrases and a shorter form that means the same in any sentence, so they can be replaced without an LLM.
#Phrases whose short form depends on the words around them ("be able to", "the majority of the") are left to the Optimizer
WORDY_PHRASES = {
    "in order to": "to",
    "due to the fact that": "because",
    "owing to the fact that": "because",
    "despite the fact that": "although",
    "in spite of the fact that": "although",
    "at this point in time": "now",
    "at the present time": "now",
    "in the event that": "if",
    "until such time as": "until",
    "for the purpose of": "for",
    "prior to": "before",
    "in the near future": "soon",
    "with regard to": "regarding",
    "with regards to": "regarding",
    "in regard to": "regarding",
    "each and every": "every",
    "first and foremost": "first",
    "is able to": "can",
    "are able to": "can",
}
#Longest first, so "in spite of the fact that" isn't matched as a shorter phrase inside it
WORDY_PHRASE_RE = re.compile(r"\b(?:" + "|".join(r"\s+".join(map(re.escape, phrase.split()))
                                                  for phrase in sorted(WORDY_PHRASES, key=len, reverse=True)) + r")\b",
                             re.IGNORECASE)
CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
#Local tokenizer for the estimate, even for Claude targets: it's only an estimate and shouldn't cost API calls
ESTIMATE_ENCODING = "o200k_base"
#Flag a prompt when this many tokens look removable, or this share of it (with at least MIN_REMOVABLE_FOR_SHARE).
#Cutting a lone "please" or "Can you" (1-2 tokens) isn't worth a rewrite, the Optimizer is told the same. All guesses: tune on real prompts
MIN_REMOVABLE_TOKENS = 5
#Tried lowering this to 0.10 (11/4/2026) to flag "Could you please translate this sentence into French and
#also explain..." (multi-translate in evals/prompts.jsonl, 3 of 30 tokens, a 10% share). Reverted the same
#day: 3 repeated live runs (evals/results/phase3-repeat.jsonl) showed the Optimizer burning 2-4 Haiku turns
#on it every time and never clearing the orchestrator's own MIN_TOKENS_SAVED=5 floor, since nothing else in
#that sentence is safely cuttable -- flagging it only paid for a guaranteed failure. Left at 0.15
MIN_REMOVABLE_SHARE = 0.15
MIN_REMOVABLE_FOR_SHARE = 3
MAX_SPANS_SHOWN = 4

#textstat thresholds. Readability scores are noisy on a sentence or two, so short prompts are skipped
MIN_WORDS_FOR_READABILITY = 20
MAX_WORDS_PER_SENTENCE = 25 #plain English writing guides aim for ~15-20 !!! <-- gather data on it
MIN_READING_EASE = 30 #Flesch reading ease below 30 = "very difficult", long words split into more tokens

#spaCy settings. en_core_web_sm is the small English model (python -m spacy download en_core_web_sm)
SPACY_MODEL = "en_core_web_sm"
MIN_WORDS_FOR_ADVERBS = 15
MAX_ADVERB_RATIO = 0.12 #more than ~1 in 8 words being an adverb ("very", "really", "actually") reads as padding
#Lowered from 0.8 to 0.7 (11/4/2026): "Write a function that reverses a string in Go." and "The function
#should reverse a string." (dup-repeat in evals/prompts.jsonl) share 3 of 4 content words (0.75), just under
#the old bar. Checked against every prompt in evals/prompts.jsonl: no other sentence pair in the whole set
#falls between 0.7 and 0.8, so this doesn't newly flag anything else there
REPEAT_SIMILARITY = 0.7
MIN_CONTENT_WORDS = 3 #sentences shorter than this ("Thanks!") are too short to compare

#A sentence asking for brevity ("quick", "short") and one asking for thoroughness ("long", "detailed") read
#as two different requests about two different things ("a short intro and a detailed conclusion"). But two or
#more sentences on the SAME side, each using a different word for it, are one instruction repeated, not two:
#"Give me a quick summary... Make it short... nothing too long or detailed" asks for brevity three times.
#countRepeatedSentences' lemma overlap can't see this (these sentences share no words at all), so it's checked
#separately, by word family instead of by shared wording
BREVITY_WORDS = frozenset({"short", "brief", "briefly", "quick", "quickly", "concise", "concisely"})
THOROUGH_WORDS = frozenset({"long", "detailed", "lengthy", "thorough", "comprehensive"})
LENGTH_FAMILY_RE = re.compile(r"\b(?:" + "|".join(map(re.escape, BREVITY_WORDS | THOROUGH_WORDS)) + r")\b",
                              re.IGNORECASE)

@dataclass
class AuditResult:
    token_count: int
    estimatedCost: float
    issues: list[str] = field(default_factory = list)
    severity: str = "Low"
    
"""
* @brief Estimates the dollar cost of a prompt based on token count.
* @post
* 1. The token count is divided into per-1000-token units.
* 2. Cost is calculated using the provided (or default) rate.
* 3. The unrounded result is returned; callers round when displaying it.
"""
def estimateCost(token_count: int, rate_per_1k: float = 0.003) -> float:
    return (token_count / 1000) * rate_per_1k

"""
* @brief Blanks out the parts of a prompt whose politeness isn't removable, keeping every offset in place.
* @post
* 1. Code blocks and quoted text ("Please do not touch") are blanked: they're the user's material, not their wording.
* 2. Sentences that make a request optional ("Maybe add tests.", vagueness.py) are blanked, since
*    cutting their "maybe" turns an option into a requirement.
* 3. The import is done here, not at the top: vagueness.py imports this module (for loadNlp).
"""
def maskProtected(text: str) -> str:
    from agents.vagueness import findOptionalMarkers, QUOTE_RE  # pylint: disable=import-outside-toplevel
    def blank(match: re.Match) -> str:
        return re.sub(r"\S", " ", match.group(0))
    masked = QUOTE_RE.sub(blank, CODE_BLOCK_RE.sub(blank, text))
    for sentence in findOptionalMarkers(text):
        masked = re.sub(re.escape(sentence), blank, masked)
    return masked

"""
* @brief Estimates how many tokens of politeness, hedging and filler a rewrite could cut.
* @post
* 1. Politeness phrases (POLITENESS_PATTERNS) and filler words (FILLER_WORDS) are found, outside
*    code blocks and optional sentences (maskProtected). Overlapping matches count once.
* 2. Tokens are counted locally with ESTIMATE_ENCODING, for the spans and for the whole prompt.
* 3. Returns (removable tokens, total tokens, the matched spans in order).
"""
def estimateRemovableTokens(text: str) -> tuple[int, int, list[str]]:
    text = text.replace("’", "'") #curly apostrophes, so "you’re" matches "you're"
    masked = maskProtected(text)
    ranges = sorted((match.start(), match.end()) for pattern in (POLITENESS_RE, FILLER_RE)
                    for match in pattern.finditer(masked) if match.group(0).strip())
    merged: list[list[int]] = []
    for start, end in ranges:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    encoding = tiktoken.get_encoding(ESTIMATE_ENCODING)
    spans = [text[start:end].strip() for start, end in merged]
    removable = sum(len(encoding.encode(span)) for span in spans)
    return removable, len(encoding.encode(text)), spans

"""
* @brief Flags a prompt when enough of it is politeness, hedging or filler to be worth a rewrite.
* @post
* 1. Flagged at MIN_REMOVABLE_TOKENS removable tokens, or at MIN_REMOVABLE_SHARE of the prompt
*    (with at least MIN_REMOVABLE_FOR_SHARE), so "Please explain TCP vs UDP." isn't flagged for one "please"
*    and "Can you explain DNS?" isn't flagged for two tokens.
* 2. The issue names the spans (up to MAX_SPANS_SHOWN, repeats once) so the Optimizer knows what to cut.
* 3. Returns the issue, or None.
"""
def findRemovableFiller(text: str) -> str | None:
    removable, total, spans = estimateRemovableTokens(text)
    share = removable / total if total else 0.0
    if removable < MIN_REMOVABLE_TOKENS and not (removable >= MIN_REMOVABLE_FOR_SHARE and share >= MIN_REMOVABLE_SHARE):
        return None
    shown = ", ".join(f"'{span}'" for span in list(dict.fromkeys(spans))[:MAX_SPANS_SHOWN])
    return f"About {removable} of {total} tokens are politeness, hedging or filler that can be cut: {shown}"

"""
* @brief Finds the wordy phrases (WORDY_PHRASES) a rewrite can shorten without changing the request.
* @post
* 1. Code blocks, quoted text and optional sentences are skipped (maskProtected), and so is everything from
*    pasted material after a colon on, since that's the person's material, not their wording.
* 2. Returns the matches in order; their offsets are offsets into text.
* 3. The import is done here, not at the top: vagueness.py imports this module (for loadNlp).
"""
def findWordyPhraseMatches(text: str) -> list[re.Match]:
    from agents.vagueness import PASTED_AFTER_COLON_RE  # pylint: disable=import-outside-toplevel
    masked = maskProtected(text.replace("’", "'"))
    pasted = PASTED_AFTER_COLON_RE.search(masked)
    return list(WORDY_PHRASE_RE.finditer(masked, 0, pasted.start() if pasted else len(masked)))

#The shorter form of a matched wordy phrase, whatever its capitals and spacing
def shortFormOf(phrase: str) -> str:
    return WORDY_PHRASES[" ".join(phrase.lower().split())]

"""
* @brief Flags a prompt that asks for the same length or thoroughness more than once, in different words.
* @post
* 1. Code blocks, quoted text and optional sentences are skipped (maskProtected), same as the other local checks.
* 2. Each sentence is sorted into "brevity" (BREVITY_WORDS) or "thorough" (THOROUGH_WORDS); a sentence that
*    uses both ("a short intro and a detailed conclusion") is dropped, since that reads as two different
*    things, not one instruction repeated.
* 3. Flagged when either side has 2 or more sentences: "Give me a quick summary... Make it short..." asks
*    for brevity twice, with no word in common for countRepeatedSentences' lemma overlap to catch.
* 4. Returns the issue naming every sentence's matched word, or None.
"""
def findRepeatedLengthWording(text: str) -> str | None:
    from agents.locks import splitSentences  # pylint: disable=import-outside-toplevel
    masked = maskProtected(text)
    brevityHits, thoroughHits = [], []
    for sentence in splitSentences(masked):
        words = {match.group(0).lower() for match in LENGTH_FAMILY_RE.finditer(sentence)}
        inBrevity, inThorough = bool(words & BREVITY_WORDS), bool(words & THOROUGH_WORDS)
        if inBrevity and not inThorough:
            brevityHits.append(words)
        elif inThorough and not inBrevity:
            thoroughHits.append(words)

    for hits in (brevityHits, thoroughHits):
        if len(hits) >= 2:
            words = ", ".join(dict.fromkeys(word for matched in hits for word in matched))
            return f"{len(hits)} sentences each ask for the same length in different words ({words}); say it once"
    return None

"""
* @brief Flags a prompt when shortening its wordy phrases saves enough tokens to be worth a rewrite.
* @post
* 1. The saving is counted locally with ESTIMATE_ENCODING, each phrase against its shorter form.
* 2. Flagged at MIN_REMOVABLE_TOKENS saved, the same bar as filler, so a single "in order to" doesn't send a
*    prompt to the Optimizer for a 2-token cut.
* 3. Returns the issue naming the phrases (up to MAX_SPANS_SHOWN), or None.
"""
def findWordyPhrases(text: str) -> str | None:
    matches = findWordyPhraseMatches(text)
    encoding = tiktoken.get_encoding(ESTIMATE_ENCODING)
    saved = sum(len(encoding.encode(" " + match.group(0))) - len(encoding.encode(" " + shortFormOf(match.group(0))))
                for match in matches)
    if saved < MIN_REMOVABLE_TOKENS:
        return None
    pairs = list(dict.fromkeys(f"'{match.group(0)}' -> '{shortFormOf(match.group(0))}'" for match in matches))
    return f"About {saved} tokens are wordy phrases with a shorter form: {', '.join(pairs[:MAX_SPANS_SHOWN])}"

"""
* @brief Runs fast, rule-based checks for common token-waste patterns.
* @post
* 1. The text's token-to-word ratio is checked for signs of verbiage meaning redundancy, or too wordy.
* 2. Politeness, hedging and filler are flagged when enough tokens could be cut (findRemovableFiller).
*    Words that make a request optional ("Maybe add tests") aren't counted, since cutting them changes the request.
*    So are wordy phrases with a shorter form, when enough tokens could be saved (findWordyPhrases), and a
*    length or thoroughness instruction repeated in different words (findRepeatedLengthWording).
* 3. Excessive blank lines/whitespace are detected.
* 4. Readability (textstat) and grammar-based (spaCy) checks are added on.
* 5. Checks named in skipChecks (prompt_types.py) are left out, since they misfire on that kind of
*    prompt (the token ratio on code, readability on code and research).
* 6. A list of human-readable issue descriptions is returned (empty if none found).
"""
def runRuleCheck(text: str, token_count: int, skipChecks: frozenset[str] = frozenset()) -> list[str]:
    issues = []
    word_count = len(text.split())

    if CHECK_TOKEN_RATIO not in skipChecks and word_count > 0 and (token_count / word_count) > 1.6: #chose 1.6 becayse its abit above the token to word ration(1.3). !!! <-- gather data on it
        issues.append("High token to word ratio. Perhaps too verbose?")
    
    filler = findRemovableFiller(text)
    if filler:
        issues.append(filler)

    wordy = findWordyPhrases(text)
    if wordy:
        issues.append(wordy)

    repeatedLength = findRepeatedLengthWording(text)
    if repeatedLength:
        issues.append(repeatedLength)

    if "\n\n\n" in text:
        issues.append("Unnecessary blank lines and or whitespace added")

    if CHECK_READABILITY not in skipChecks:
        issues.extend(runReadabilityCheck(text))
    issues.extend(runSpacyCheck(text, checkAdverbs=CHECK_ADVERBS not in skipChecks))

    return issues

"""
* @brief Uses textstat to flag prose that is harder to read than it needs to be.
* @post
* 1. Prompts with a code block or fewer than MIN_WORDS_FOR_READABILITY words are skipped,
*    since readability formulas are built for prose and are unreliable on very short text.
* 2. Average sentence length is flagged above MAX_WORDS_PER_SENTENCE.
* 3. A Flesch reading ease below MIN_READING_EASE (long words, long sentences) is flagged.
*    If NLTK's cmudict (used to count syllables) isn't installed, this check is skipped with a warning.
* 4. A list of issue descriptions is returned (empty if none found).
"""
def runReadabilityCheck(text: str) -> list[str]:
    if "```" in text:
        return []

    word_count = textstat.lexicon_count(text)
    if word_count < MIN_WORDS_FOR_READABILITY:
        return []

    issues = []
    words_per_sentence = word_count / max(textstat.sentence_count(text), 1)
    if words_per_sentence > MAX_WORDS_PER_SENTENCE:
        issues.append(f"Long sentences (about {words_per_sentence:.0f} words each on average). Splitting or trimming them usually cuts words")

    #Flesch counts syllables with NLTK's cmudict, which textstat downloads on first use.
    #If that download failed (no network, SSL certificates), skip this one check instead of crashing the audit
    try:
        reading_ease = textstat.flesch_reading_ease(text)
    except LookupError:
        logger.warning("NLTK cmudict is not installed, skipping the reading ease check. Install it with: python -m nltk.downloader cmudict")
        return issues

    if reading_ease < MIN_READING_EASE:
        issues.append(f"Dense, complex wording (Flesch reading ease {reading_ease:.0f}). Plainer, shorter words usually take fewer tokens")

    return issues

"""
* @brief Loads the spaCy English model once and reuses it.
* @post
* 1. The model is loaded without the named-entity recognizer, which no check uses.
* 2. If the model isn't installed, a warning is logged (once) and None is returned,
*    so the spaCy checks are skipped instead of breaking the audit.
"""
@lru_cache(maxsize=1)
def loadNlp():
    try:
        return spacy.load(SPACY_MODEL, exclude=["ner"])
    except OSError:
        logger.warning("spaCy model %s is not installed, skipping spaCy checks. Install it with: python -m spacy download %s",
                       SPACY_MODEL, SPACY_MODEL)
        return None

"""
* @brief Uses spaCy's part-of-speech tags and lemmas to find padding and repetition.
* @post
* 1. If the spaCy model isn't available or the text is empty, an empty list is returned.
* 2. The share of adverbs among words is flagged above MAX_ADVERB_RATIO
*    (only for prompts of at least MIN_WORDS_FOR_ADVERBS words, and only if checkAdverbs is True).
* 3. Sentences that repeat an earlier sentence are counted and flagged.
* 4. A list of issue descriptions is returned (empty if none found).
"""
def runSpacyCheck(text: str, checkAdverbs: bool = True) -> list[str]:
    nlp = loadNlp()
    if nlp is None or not text.strip():
        return []

    doc = nlp(text)
    issues = []

    words = [token for token in doc if token.is_alpha]
    adverbs = [token for token in words if token.pos_ == "ADV"]
    if checkAdverbs and len(words) >= MIN_WORDS_FOR_ADVERBS and len(adverbs) / len(words) > MAX_ADVERB_RATIO:
        issues.append(f"Lots of adverbs ({len(adverbs)} of {len(words)} words), most can be cut without changing the meaning")

    repeats = countRepeatedSentences(doc)
    if repeats:
        issues.append(f"{repeats} sentence(s) repeat something already said earlier in the prompt")

    return issues

"""
* @brief Counts sentences that say the same thing as an earlier sentence.
* @post
* 1. Each sentence is reduced to its set of content-word lemmas (no stop words or punctuation),
*    so "Keep it short." and "Keeping it short" compare as the same words.
* 2. A sentence counts as a repeat when its overlap (Jaccard) with an earlier sentence
*    is at least REPEAT_SIMILARITY.
* 3. Sentences with fewer than MIN_CONTENT_WORDS content words are skipped.
* 4. The number of repeated sentences is returned.
"""
def countRepeatedSentences(doc) -> int:
    seen: list[set[str]] = []
    repeats = 0
    for sentence in doc.sents:
        lemmas = {token.lemma_.lower() for token in sentence if token.is_alpha and not token.is_stop}
        if len(lemmas) < MIN_CONTENT_WORDS:
            continue
        if any(len(lemmas & earlier) / len(lemmas | earlier) >= REPEAT_SIMILARITY for earlier in seen):
            repeats += 1
        else:
            seen.append(lemmas)
    return repeats

"""
* @brief Determines overall severity rating for the audit result.
* @post
* 1. Token count and issue count are compared against the fixed thresholds.
* 2. A severity level of "High", "Medium", or "Low" is returned accordingly to count
"""
def determineSeverity(token_count: int, issue_count: int) -> str:
    if token_count > 800 or issue_count >= 3:
        return "High"
    elif token_count > 300 or issue_count >= 1:
        return "Medium"
    return "Low"

"""
* @brief Executes the full audit process on a single user-submitted prompt.
* @post
* 1. The prompt's token count (as the target LLM tokenizes it) and estimated cost are calculated.
* 2. Fast, free, rule-based checks are run against the prompt, minus the ones in skipChecks (the prompt
*    type's profile, see prompt_types.py). This makes no API call: a long prompt these checks pass as clean
*    used to also get a dedicated LLM review here (removed 11/4/2026). That review read the whole prompt to
*    judge whether anything was worth cutting, which is exactly what the Optimizer's own first turn has to
*    do anyway; the orchestrator now gives the Optimizer that look itself (orchestrator.py, gated on token
*    count) instead of paying for a second model call to ask the same question first.
* 3. A severity rating is computed from the issue count and token count.
* 4. A populated AuditResult object is returned, containing all of the above.
"""
def auditPrompt(prompt: str, target: str = DEFAULT_TARGET, skipChecks: frozenset[str] = frozenset()) -> AuditResult:
    token_count = countTokens(prompt, target)
    cost = estimateCost(token_count)
    issues = runRuleCheck(prompt, token_count, skipChecks)
    severity = determineSeverity(token_count, len(issues))

    return AuditResult(
                        token_count=token_count,
                        estimatedCost=cost,
                        issues=issues,
                        severity=severity,
                        )


#Test dummy haha
if __name__ == "__main__":
    test1 = "Hi world me llamo islam"
    test2 = "Please PLEASE please could you really kindly help me write a essay about some dragons?"
    test3 = ""

    print("Text:", test1)
    print("Token count:", countTokens(test1))
    print()

    print("Text:", test2)
    print("Token count:", countTokens(test2))
    print()

    print("Text:", test3)
    print("Token count:", countTokens(test3))
    
    """
    sample = "Please, please could you kindly just help me write a short story about a dragon please? I would appreciate it so much!"
    result = auditPrompt(sample)
    print(result)
    """
    empty_result = auditPrompt("")
    print(empty_result)