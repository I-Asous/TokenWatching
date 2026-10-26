import re
from dataclasses import dataclass, field
from agents.auditor import loadNlp
from agents.intent import detectIntent, QUESTION, UNCLEAR, WRAPPER_VERBS
from agents.locks import CODE_BLOCK_RE, INLINE_CODE_RE, URL_RE, NUMBER_RE, contentWords, splitSentences, shorten
from agents.prompt_types import FILE_RE

SLOT_POINTS = 2 #a missing slot is the strongest signal: the model has to guess something the answer depends on
REFERENCE_POINTS = 2 #"fix this" with nothing attached: the model can't even see what to work on
WORD_POINTS = 1 #one vague word or phrase; the model can usually pick a sensible reading
OPTION_POINTS = 0 #"maybe add tests" isn't vague, it's an option. Reported so it's protected, not scored
#Score thresholds for the level shown to the user
VAGUE_SCORE = 4
SOMEWHAT_VAGUE_SCORE = 2
MAX_QUESTIONS = 3 #more than this and the user stops reading

#Pasted material: quoted text of 3+ words, or after a colon 8+ words or a comma list ("Rank these: A, B, C")
QUOTE_RE = re.compile(r"[\"“][^\"”]+?[\"”]|(?<!\w)'[^'\n]+?'(?!\w)")
PASTED_AFTER_COLON_RE = re.compile(r":\s*(?:(?:\S+\s+){7,}\S+|[^,\n]+(?:,[^,\n]+)+)")

#What a fix needs to know: what goes wrong. "it's broken" / "doesn't work" aren't symptoms
SYMPTOM_RE = re.compile(
    r"\b(?:error|errors|exception|traceback|crash(?:es|ed|ing)?|fail(?:s|ed|ing)?|returns?|returning|instead of|expected|"
    r"wrong (?:output|result|answer|value)|undefined|null|none|nan|timeout|times out|hangs?|freezes?|throws?|raises?|"
    r"warning|says|shows|prints|outputs?|slow|leaks?|infinite|off by)\b", re.IGNORECASE)
#Length or format of something to generate
LENGTH_FORMAT_RE = re.compile(
    r"\b(?:words?|sentences?|paragraphs?|pages?|lines?|bullets?|bullet points?|points|items|characters|minutes?|"
    r"slides?|table|json|csv|yaml|markdown|html|list|outline|short|brief|long|detailed|concise|one-liner)\b", re.IGNORECASE)
#Things whose form fixes their length ("a haiku", "a tagline"), so they need no length
FIXED_FORMS = frozenset({"haiku", "tweet", "limerick", "sonnet", "slogan", "tagline", "title", "name", "headline",
                         "caption", "motto", "acronym", "username", "password", "subject", "joke", "riddle", "pun"})
#Code to generate: needs a language instead of a length
CODE_OBJECTS = frozenset({"function", "script", "class", "query", "regex", "program", "code", "method", "snippet",
                          "algorithm", "endpoint", "component", "test", "module", "api"})
LANGUAGE_RE = re.compile(
    r"\b(?:python|javascript|js|typescript|ts|java|kotlin|swift|go|golang|rust|c\+\+|c#|ruby|php|sql|bash|shell|"
    r"powershell|r|scala|dart|html|css|react|node|excel|vba)\b", re.IGNORECASE)
#Prose whose length is up to the model unless the prompt says ("a workout plan" or "a function" has no word count)
LENGTH_OBJECTS = frozenset({"article", "post", "blog", "report", "speech", "essay", "newsletter", "description", "bio",
                            "story", "poem", "summary", "overview", "explanation"})
#Writing whose wording depends on who reads it
AUDIENCE_OBJECTS = frozenset({"explanation", "article", "post", "blog", "report", "presentation", "speech", "tutorial",
                              "guide", "email", "letter", "newsletter", "announcement", "description", "bio", "essay",
                              "message", "proposal", "pitch", "summary", "overview", "lesson", "story"})
AUDIENCE_RE = re.compile(
    r"\bfor\s+\w+|\bto\s+(?:my|our|the|a|an|your)\s+\w+|\b(?:audience|readers?|beginners?|kids?|children|students?|"
    r"experts?|customers?|clients?|team|manager|boss|recruiters?|hiring|investors?|developers?|engineers?|"
    r"non-technical|technical|executives?|year-old|formal|casual|friendly|professional|warm|tone)\b", re.IGNORECASE)
#A direction for "improve / rewrite / optimize": a comparative ("shorter", "more formal") or a goal
DIRECTION_RE = re.compile(
    r"\b(?:more|less|fewer)\s+\w+|\w+er\b(?<!\bever)(?<!\bother)(?<!\bafter)(?<!\bunder)(?<!\bover)(?<!\bpaper)"
    r"(?<!\bletter)(?<!\bcover)(?<!\buser)(?<!\bnumber)(?<!\border)|\bfor\s+\w+|\bso\s+(?:that|it)\b|\bby\s+\w+ing\b|"
    r"\bin terms of\b|\bfocus(?:ing)? on\b|\bwithout\b|\bto be\s+\w+|\bto\s+(?!the\b|a\b|an\b|my\b|our\b|your\b|me\b|us\b)[a-z]+\b|\b(?:readability|readable|performance|speed|"
    r"clarity|grammar|spelling|tone|length|seo|memory|security|formal|casual|concise)\b", re.IGNORECASE)
#Self-directed transforms: the verb already says which way ("shorten", "proofread")
DIRECTED_TRANSFORMS = frozenset({"shorten", "simplify", "expand", "proofread", "paraphrase", "rephrase", "reformat",
                                 "convert", "translate"})
#Transforms whose target is a language or a format ("into French", "to JSON")
TARGET_TRANSFORMS = {"translate": "Translate into which language?", "convert": "Convert to what format?"}
INTO_RE = re.compile(r"\b(?:into|to|as)\s+\w+", re.IGNORECASE)
#What to compare or decide on
CRITERIA_RE = re.compile(
    r"\bfor\s+\w+|\bbased on\b|\bin terms of\b|\bby\s+\w+|\bcriteria\b|\bpros and cons\b|\bon\s+(?:price|cost|speed|"
    r"performance|quality|size)\b|\b\w+er\b(?=\s+than)|\b(?:cheap|fast|easy|simple|safe|secure|reliable)\w*\b", re.IGNORECASE)
CATEGORIES_RE = re.compile(r"\binto\s+\w+|\bas\s+(?:either\s+)?\w+|\bcategor(?:y|ies)\b|\blabels?\b", re.IGNORECASE)

#Nouns that name material the user has (or should have) attached: "fix THE FILE", "proofread MY ESSAY"
INPUT_NOUNS = frozenset({"file", "code", "function", "script", "bug", "error", "text", "document", "doc", "article",
                         "essay", "email", "report", "data", "dataset", "table", "spreadsheet", "page", "query", "message",
                         "letter", "image", "picture", "screenshot", "project", "app", "program", "paragraph", "draft",
                         "resume", "cv", "list", "output", "log", "issue", "problem", "thing", "one", "stuff", "version",
                         "website", "site", "repo", "class", "method", "section", "slide", "presentation", "story", "post",
                         "datum"}) #spaCy lemmatizes "data" to "datum"
REFERRING_DETERMINERS = frozenset({"this", "that", "these", "those", "the", "my", "our", "your"})
#"these reviews", "those numbers": plural pointers almost always mean items the user meant to paste
PLURAL_POINTERS = frozenset({"these", "those"})
REFERRING_PRONOUNS = frozenset({"this", "that", "these", "those", "it", "them"})

#Judgement words: fine with a standard after them ("cleaner, i.e. no nested ifs"), vague without one
JUDGEMENT_WORDS = frozenset({"better", "best", "good", "great", "nice", "cleaner", "professional", "proper", "properly",
                             "optimized", "optimised", "modern", "engaging", "interesting", "polished", "efficient",
                             "elegant", "robust", "appropriate", "perfect", "amazing", "awesome", "cool", "solid",
                             "natural", "fancy", "pretty", "beautiful", "impressive", "user-friendly", "high-quality"})
JUDGEMENT_PHRASE_RE = re.compile(r"\b(?:user-friendly|high-quality|best practices?)\b", re.IGNORECASE)
CRITERION_AFTER_RE = re.compile(
    r"\b(?:i\.e|e\.g|such as|like|meaning|for example|than|so that|without|with no|no more than|under|at least|"
    r"at most|by\s+\w+ing)\b|[:(]|\d", re.IGNORECASE)
CRITERION_WINDOW = 8 #words after a judgement word that are searched for its standard

#Amounts with no number: fine when the sentence has a number, vague otherwise. "short story" is a genre
FUZZY_RE = re.compile(
    r"\b(?:some|a few|a couple(?: of)?|several|a lot(?: of)?|lots of|many|short(?! story| stories)|brief(?:ly)?|"
    r"quick(?:ly)?|long|detailed|a bit|a little|etc\.?|and so on|and stuff|or so|something like|stuff)(?!\w)", re.IGNORECASE)
FUZZY_LIST_ENDINGS = frozenset({"etc", "etc.", "and so on", "and stuff"})
FUZZY_LENGTH_WORDS = frozenset({"short", "brief", "briefly", "quick", "quickly", "long", "detailed"})

#Verbs with more than one reasonable reading, and the question that settles which
AMBIGUOUS_VERBS = {
    "test": "Should I write tests, or run it and report what happens?",
    "clean": "Clean it how: remove duplicates, fix formatting, or drop missing values?",
    "update": "Update it how: change the content, or upgrade it to a newer version?",
    "check": "Check it for what: errors, style, or whether it works?",
    "handle": "Handle it how: catch and log it, retry, or show an error?",
    "format": "Format it how, and into what?",
    "look": "Should I review it, explain it, or fix it?",
    "deal": "Deal with it how: fix it, remove it, or work around it?",
    "process": "Process it how: what should happen to each item?",
}

REQUEST_DEPS = frozenset({"ROOT", "conj", "xcomp", "ccomp"})

#Scope with no edge: the model decides how much to do
OPEN_SCOPE_RE = re.compile(
    r"\b(?:anything else(?: you think)?(?: is| would be)?(?: relevant| useful| helpful)?|whatever you (?:think|want|like)|"
    r"anything (?:you think|relevant|useful)|as needed|if necessary|and more|or something|or whatever|you decide|"
    r"up to you|any other (?:ideas|suggestions|improvements))\b", re.IGNORECASE)

#Words that make a request optional. FILLER_WORDS has some of them, but here they carry meaning:
#"Maybe add tests" -> "Add tests" turns an option into a requirement
HEDGE_WORDS = frozenset({"maybe", "possibly", "perhaps", "optionally", "ideally"})
HEDGE_PHRASE_RE = re.compile(r"\b(?:if possible|if you can|if needed|if you have time|feel free to|bonus points?|"
                             r"optional(?:ly)?|nice to have)\b", re.IGNORECASE)
#Anything a rewrite can use to keep a request optional
KEEPS_OPTION_RE = re.compile(r"\b(?:maybe|possibly|perhaps|optional(?:ly)?|ideally|if possible|if you can|if needed|"
                             r"if you have time|feel free|bonus|nice to have|can|could|may|might)\b", re.IGNORECASE)

@dataclass(frozen=True)
class VagueSignal:
    kind: str #"missing slot", "empty reference", "judgement word", "fuzzy amount", "ambiguous word", "open scope", "optional"
    phrase: str #the words that triggered it (for a missing slot, what's missing)
    points: int
    question: str = "" #a clarifying question for the user, empty for "optional"

@dataclass
class VaguenessReport:
    signals: list[VagueSignal] = field(default_factory=list)
    score: int = 0
    level: str = "clear" #"clear", "somewhat vague" or "vague"
    questions: list[str] = field(default_factory=list) #at most MAX_QUESTIONS, highest points first
    optionalParts: list[str] = field(default_factory=list) #sentences with an option a rewrite must keep optional

"""
* @brief Tells whether the prompt has material attached for "this" / "the file" to point to.
* @post
* 1. Code blocks, inline code, URLs, file names and quoted text of 3+ words count.
* 2. So do 8+ words after a colon ("Proofread this: <pasted paragraph>").
"""
def hasAttachedInput(prompt: str) -> bool:
    if CODE_BLOCK_RE.search(prompt) or INLINE_CODE_RE.search(prompt) or URL_RE.search(prompt) or FILE_RE.search(prompt):
        return True
    if any(len(quote.split()) >= 3 for quote in QUOTE_RE.findall(prompt)):
        return True
    return PASTED_AFTER_COLON_RE.search(prompt) is not None

#Prose to look for vague words in: no code, URLs, quoted or pasted text, which are the user's material, not their wording
def proseOf(prompt: str) -> str:
    text = CODE_BLOCK_RE.sub("\n", prompt.replace("’", "'"))
    text = QUOTE_RE.sub(" ", URL_RE.sub(" ", INLINE_CODE_RE.sub(" ", text)))
    return PASTED_AFTER_COLON_RE.sub(":", text)

#"a short blog post" -> "the short blog post", for questions about it
def theObject(phrase: str | None) -> str:
    if not phrase:
        return "it"
    return "the " + re.sub(r"^(?:a|an|the|some|my|our|your)\s+", "", phrase, flags=re.IGNORECASE)

"""
* @brief Finds slots each of the prompt's tasks needs but doesn't fill.
* @post
* 1. fix needs what to fix (attached input) and what goes wrong (a symptom, not "it's broken").
* 2. generate needs a length or format (code needs a language instead; a haiku or a tagline needs neither),
*    and writing meant for readers ("an email", "an explanation") needs an audience.
* 3. transform needs a direction ("improve" toward what?); translate and convert need a target.
* 4. compare/decide needs criteria, classify needs categories.
* 5. UNCLEAR tasks are missing the action itself.
* 6. Slots are looked for in the whole prompt, since constraints often sit in other sentences.
"""
def findMissingSlots(prompt: str, intent, attached: bool) -> list[VagueSignal]:
    prose = proseOf(prompt)
    signals = []

    def missing(phrase: str, question: str):
        signals.append(VagueSignal("missing slot", phrase, SLOT_POINTS, question))

    hasNumber = NUMBER_RE.search(prose) is not None
    #"better" is a comparative but no direction: judgement words don't say which way to go
    directionProse = re.sub(r"\b(?:" + "|".join(map(re.escape, JUDGEMENT_WORDS)) + r")\b", " ", prose, flags=re.IGNORECASE)
    for action in intent.actions:
        head = action.objectHead
        if action.actionClass == UNCLEAR:
            target = f" with {action.object}" if action.object else ""
            missing(f"what to do{target}", f"What should I do{target}: review it, rewrite it, shorten it, or check it for mistakes?")
        elif action.actionClass == "fix":
            if not attached:
                missing("what to fix", "Paste the code or text that needs fixing.")
            if not SYMPTOM_RE.search(prompt):
                missing("what goes wrong", "What goes wrong? Paste the error, or say what happens and what you expected.")
        elif action.actionClass == "generate":
            if head in CODE_OBJECTS:
                if not LANGUAGE_RE.search(prose) and not FILE_RE.search(prompt):
                    missing("which language", "Which programming language should it be in?")
            elif head in LENGTH_OBJECTS and not hasNumber and not LENGTH_FORMAT_RE.search(prose):
                missing("length or format", f"How long should {theObject(action.object)} be, and in what format?")
            if head in AUDIENCE_OBJECTS and not AUDIENCE_RE.search(prose):
                missing("audience", f"Who is {theObject(action.object)} for?")
        elif action.actionClass == "transform":
            verb = action.verb
            if verb in TARGET_TRANSFORMS:
                if not INTO_RE.search(prose):
                    missing("target", TARGET_TRANSFORMS[verb])
            elif verb not in DIRECTED_TRANSFORMS and not DIRECTION_RE.search(directionProse):
                missing("what to improve", "Improve it toward what: shorter, clearer, more formal, faster, or something else?")
        elif action.actionClass == "compare":
            if not CRITERIA_RE.search(prose):
                missing("criteria", "What should they be judged on: price, speed, ease of use, or something else?")
        elif action.actionClass == "classify":
            if not CATEGORIES_RE.search(prose):
                missing("categories", "Which categories should I sort them into?")
    return signals

"""
* @brief Finds "this", "it", "the file", "my essay" when there's nothing for them to point to.
* @post
* 1. Nothing is reported if the prompt has attached input (code, a URL, a file name, quoted or pasted text).
* 2. A referring pronoun ("fix this", "make it better") counts when no noun comes before it in the prompt.
*    "it" as the subject of "be" ("it's important that...") doesn't count.
* 3. A material noun (INPUT_NOUNS) with "this/the/my...", or any noun with "these/those", counts when it wasn't mentioned earlier and
*    isn't named ("the README file", "auth.py"). Something the prompt asks to create ("write my bio") doesn't count.
"""
def findEmptyReferences(doc, intent, attached: bool) -> list[VagueSignal]:
    if attached:
        return []
    created = {action.objectHead for action in intent.actions if action.actionClass == "generate"}
    earlierNouns: set[str] = set()
    signals = []
    for token in doc:
        lemma = token.lemma_.lower()
        if token.pos_ in ("NOUN", "PROPN"):
            determiner = next((child for child in token.children if child.dep_ in ("det", "poss")
                               and child.lower_ in REFERRING_DETERMINERS), None)
            #"the README file", "the orders table", "auth.py": a qualifier says which one
            named = any(child.pos_ == "PROPN" or child.dep_ == "compound" or FILE_RE.search(child.text) for child in token.children)
            pointsAtInput = determiner is not None and (lemma in INPUT_NOUNS or determiner.lower_ in PLURAL_POINTERS)
            #"for the website", "to the team" say where the result goes, not what to work on
            destination = token.dep_ == "pobj" and token.head.lower_ in ("for", "to")
            if (pointsAtInput and not destination and lemma not in earlierNouns
                    and lemma not in created and not named and token.pos_ == "NOUN"):
                signals.append(VagueSignal("empty reference", f"{determiner.text} {token.text}", REFERENCE_POINTS,
                                           f'Which {token.text}? Paste it or name it.'))
            earlierNouns.add(lemma)
        elif (token.pos_ == "PRON" and token.lower_ in REFERRING_PRONOUNS and token.tag_ != "WDT"
              and not earlierNouns and not (token.lower_ == "it" and token.head.lemma_ == "be")
              and token.dep_ != "expl"):
            signals.append(VagueSignal("empty reference", token.text, REFERENCE_POINTS,
                                       f'What does "{token.text}" refer to? Paste it or name it.'))
    return signals

#Judgement words with no standard in the next CRITERION_WINDOW words
def findJudgementWords(doc) -> list[VagueSignal]:
    signals = []
    for token in doc:
        if token.lower_ not in JUDGEMENT_WORDS or token.pos_ not in ("ADJ", "ADV"):
            continue
        #"It would be amazing if..." is politeness about the request, not a standard for the answer
        if token.head.lemma_ == "be" and any(child.lower_ == "it" for child in token.head.children):
            continue
        after = token.doc[token.i + 1:min(token.i + 1 + CRITERION_WINDOW, token.sent.end)].text
        if CRITERION_AFTER_RE.search(after):
            continue
        signals.append(VagueSignal("judgement word", token.text, WORD_POINTS, f'What would "{token.text}" look like when it\'s done?'))
    for match in JUDGEMENT_PHRASE_RE.finditer(doc.text):
        signals.append(VagueSignal("judgement word", match.group(0), WORD_POINTS, f'What does "{match.group(0)}" mean here?'))
    return signals

"""
* @brief Finds amounts with no number in their sentence ("a few", "short", "etc.").
* @post
* 1. A sentence with a number is skipped: "a short 300-word story" says how short.
* 2. Length words ("quick", "short", "nothing too long or detailed") are one wish about length,
*    however many times it's repeated, so they make one signal together.
* 3. "etc." / "and so on" ask what else the list includes.
"""
def findFuzzyAmounts(prose: str) -> list[VagueSignal]:
    signals = []
    lengthWords: list[str] = []
    for sentence in splitSentences(prose):
        if NUMBER_RE.search(sentence):
            continue
        for match in FUZZY_RE.finditer(sentence):
            phrase = match.group(0)
            if phrase.lower() in FUZZY_LENGTH_WORDS:
                lengthWords.append(phrase)
                continue
            question = (f'What else does "{phrase}" include? List everything you want.' if phrase.lower() in FUZZY_LIST_ENDINGS
                        else f'How much is "{phrase}"? Give a number if it matters.')
            signals.append(VagueSignal("fuzzy amount", phrase, WORD_POINTS, question))
    if lengthWords:
        signals.append(VagueSignal("fuzzy amount", ", ".join(dict.fromkeys(lengthWords)), WORD_POINTS,
                                   "How long should it be? Give a number of words or sentences if it matters."))
    return signals

"""
* @brief Finds request verbs with more than one reasonable reading ("test it": write tests, or run it?).
* @post
* 1. Only verbs in a request position count (the main verb, or one joined to it): in "a function that
*    checks passwords", "checks" describes the function, it isn't something to do.
* 2. A command word the small model tags as a noun or adjective ("Clean the data") counts if it has an object.
"""
def findAmbiguousWords(doc) -> list[VagueSignal]:
    signals = []
    for token in doc:
        if token.lemma_.lower() not in AMBIGUOUS_VERBS or token.dep_ not in REQUEST_DEPS:
            continue
        if token.pos_ == "VERB" or any(child.dep_ == "dobj" for child in token.children):
            signals.append(VagueSignal("ambiguous word", token.text, WORD_POINTS, AMBIGUOUS_VERBS[token.lemma_.lower()]))
    return signals

#Tasks joined by "or", and phrases that leave the scope to the model ("anything else you think is relevant")
def findOpenScope(prose: str, intent) -> list[VagueSignal]:
    signals = []
    if intent.hasAlternatives:
        verbs = " or ".join(dict.fromkeys(action.verb for action in intent.actions))
        signals.append(VagueSignal("open scope", verbs, WORD_POINTS, f"Do you want all of these, or only one: {verbs}?"))
    for match in OPEN_SCOPE_RE.finditer(prose):
        signals.append(VagueSignal("open scope", match.group(0), WORD_POINTS, f'What exactly should "{match.group(0)}" cover?'))
    return signals

"""
* @brief Finds sentences that make a request optional ("Maybe add tests.", "If possible, use TypeScript.").
* @post
* 1. A hedge word counts when it modifies the request verb itself, not a wrapper:
*    "Maybe add tests" is an option, "I was wondering if you could maybe help me" is just politeness.
* 2. Phrases like "if possible", "feel free to", "optionally" always count.
* 3. Returns each such sentence once, in order. Without the spaCy model, only the phrases are found.
"""
def findOptionalMarkers(prompt: str) -> list[str]:
    prose = proseOf(prompt)
    sentences = [sentence for sentence in splitSentences(prose) if HEDGE_PHRASE_RE.search(sentence)]
    nlp = loadNlp()
    if nlp is not None:
        for token in nlp(prose):
            head = token.head
            if (token.lower_ in HEDGE_WORDS and head.pos_ == "VERB" and head.lemma_.lower() not in WRAPPER_VERBS
                    and not any(child.lower_ == "you" and child.dep_ == "nsubj" for child in head.children)):
                sentences.append(token.sent.text.strip())
    ordered = sorted(dict.fromkeys(sentences), key=prose.find)
    return ordered

"""
* @brief Scores how vague a prompt is and says which words made it so.
* @post
* 1. Missing slots and empty references score SLOT_POINTS / REFERENCE_POINTS each; judgement words,
*    fuzzy amounts, ambiguous words and open scope score WORD_POINTS each.
* 2. Optional parts ("maybe add tests") are listed with 0 points, so they're protected, not "fixed".
* 3. Each scored signal has a clarifying question; the report keeps the MAX_QUESTIONS most important,
*    without repeats, so the extension can ask instead of letting the Optimizer guess.
* 4. level is "vague" from VAGUE_SCORE, "somewhat vague" from SOMEWHAT_VAGUE_SCORE, else "clear".
* 5. Non-English prompts and a missing spaCy model give an empty report: the checks can't read them.
"""
def findVagueness(prompt: str) -> VaguenessReport:
    nlp = loadNlp()
    prose = proseOf(prompt)
    #Tasks are read from the instructions alone: pasted text after "Proofread this:" would merge into their sentence
    intent = detectIntent(prose)
    if nlp is None or intent is None or not intent.isEnglish or not prompt.strip():
        return VaguenessReport()

    doc = nlp(prose)
    attached = hasAttachedInput(prompt)
    optionalParts = findOptionalMarkers(prompt)
    signals = (findMissingSlots(prompt, intent, attached) + findEmptyReferences(doc, intent, attached)
               + findJudgementWords(doc) + findFuzzyAmounts(prose) + findAmbiguousWords(doc) + findOpenScope(prose, intent))
    #"Fix this." is one gap, not two: the empty "this" already asks what to fix
    if any(signal.kind == "empty reference" for signal in signals):
        signals = [signal for signal in signals if signal.phrase != "what to fix"]
    signals = list(dict.fromkeys(signals)) #the same phrase found twice counts once
    signals += [VagueSignal("optional", shorten(sentence), OPTION_POINTS) for sentence in optionalParts]

    score = sum(signal.points for signal in signals)
    ranked = sorted((signal for signal in signals if signal.points), key=lambda signal: -signal.points)
    questions = list(dict.fromkeys(signal.question for signal in ranked))[:MAX_QUESTIONS]
    level = "vague" if score >= VAGUE_SCORE else "somewhat vague" if score >= SOMEWHAT_VAGUE_SCORE else "clear"
    return VaguenessReport(signals, score, level, questions, optionalParts)

"""
* @brief Checks that a rewrite kept every optional request optional. Runs locally, no API call.
* @post
* 1. For each optional sentence of the original, the rewrite sentence that shares most of its
*    content words must still contain something that keeps it optional ("maybe", "if possible", "can"...).
* 2. A rewrite that drops the optional request entirely is reported too.
* 3. Returns readable reasons, written to be passed back to the Optimizer like findBrokenLocks.
"""
def findDroppedOptions(original: str, rewrite: str) -> list[str]:
    if original.strip() == rewrite.strip():
        return []
    rewriteSentences = [(sentence, contentWords(sentence)) for sentence in splitSentences(proseOf(rewrite))]
    reasons = []
    for sentence in findOptionalMarkers(original):
        words = contentWords(HEDGE_PHRASE_RE.sub(" ", sentence)) - HEDGE_WORDS
        if not words:
            continue
        best = max(rewriteSentences, key=lambda pair: len(words & pair[1]), default=None)
        if best is None or len(words & best[1]) / len(words) < 0.5:
            reasons.append(f'optional request dropped: "{shorten(sentence)}"')
        elif not KEEPS_OPTION_RE.search(best[0]):
            reasons.append(f'optional request made required (keep the "maybe" / "if possible"): "{shorten(sentence)}"')
    return reasons


if __name__ == "__main__":
    samples = [
        "Make it better.",
        "Fix this.",
        "Could you write a function that checks passwords?",
        "Write a short blog post about remote work. Maybe add a few statistics.",
        "Improve my essay and make it more professional.",
        "Compare React and Vue.",
        "Can you help me with my essay?",
        "Write a 300-word cover letter for a junior data analyst job, professional but warm.",
        "Fix this:\n```python\ndef add(a, b): return a - b\n```\nIt returns -1 for add(1, 2) instead of 3.",
        "Clean the data and test it. Add anything else you think is relevant.",
    ]
    for sample in samples:
        report = findVagueness(sample)
        print(f"{sample[:70]!r}\n  score={report.score} level={report.level}")
        for signal in report.signals:
            print(f"    [{signal.points}] {signal.kind}: {signal.phrase!r}")
        for question in report.questions:
            print(f"    ? {question}")
        print()
