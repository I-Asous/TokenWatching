from dataclasses import dataclass, field
from spacy.tokens import Span, Token
from agents.auditor import loadNlp
from agents.locks import contentWords
from agents.prompt_types import CODE_BLOCK_RE

#Action classes and the verbs (lemmas) that signal them
ACTION_CLASSES: dict[str, frozenset[str]] = {
    "generate": frozenset({"write", "create", "generate", "draft", "build", "make", "design", "compose", "produce",
                           "suggest", "propose", "brainstorm", "plan", "name"}),
    "transform": frozenset({"rewrite", "refactor", "translate", "convert", "shorten", "rephrase", "improve", "edit",
                            "proofread", "simplify", "reformat", "paraphrase", "polish", "optimize", "expand"}),
    "fix": frozenset({"fix", "debug", "repair", "solve", "correct", "resolve", "troubleshoot"}),
    "explain": frozenset({"explain", "describe", "clarify", "teach", "tell", "define", "show"}),
    "extract": frozenset({"extract", "summarize", "list", "find", "pull", "identify", "highlight", "count"}),
    "compare": frozenset({"compare", "contrast", "evaluate", "rank", "choose", "recommend", "review", "assess",
                          "rate", "pick", "decide"}),
    "classify": frozenset({"classify", "categorize", "label", "tag", "sort"}),
}
VERB_CLASS = {verb: actionClass for actionClass, verbs in ACTION_CLASSES.items() for verb in verbs}
#Verb + particle pairs whose meaning isn't the verb's alone ("come up with names" generates)
PHRASAL_CLASS = {
    ("come", "up"): "generate", ("write", "up"): "generate", ("sum", "up"): "extract", ("look", "up"): "extract",
    ("find", "out"): "extract", ("point", "out"): "extract", ("figure", "out"): "explain",
    ("break", "down"): "explain", ("clean", "up"): "transform", ("tidy", "up"): "transform",
}
#"Give me a SUMMARY", "I need an EXPLANATION": the noun names the action. Other nouns are something to produce
NOUN_CLASS = {
    "summary": "extract", "overview": "extract", "list": "extract", "outline": "extract",
    "explanation": "explain", "definition": "explain", "breakdown": "explain",
    "comparison": "compare", "review": "compare", "feedback": "compare", "recommendation": "compare",
    "translation": "transform", "rewrite": "transform", "fix": "fix",
}

QUESTION = "question" #a question to answer, not a task ("What is...?", "How do I...?")
UNCLEAR = "unclear" #a request whose action can't be told from the words ("Can you help me with my essay?")
#Classes that ask for the same thing in different words, so a rewrite may swap one for the other
#("How do I reverse a list?" -> "Explain how to reverse a list.")
COMPATIBLE_CLASSES = {QUESTION: frozenset({QUESTION, "explain"}), "explain": frozenset({"explain", QUESTION})}

#Verbs that wrap the real request: "help me FIX", "I need you to SUMMARIZE", "I'd like you to TRANSLATE"
WRAPPER_VERBS = frozenset({"help", "need", "want", "like", "love", "try", "wonder", "ask"})
#"I need / want / would like X" with a noun and no inner verb is a request to produce X
WANT_VERBS = frozenset({"need", "want", "like", "love"})
#"Give / provide me X": the action is in the noun (NOUN_CLASS)
PROVIDE_VERBS = frozenset({"give", "provide", "offer", "send"})
#"make it shorter" transforms, but "make sure ..." is a constraint, not an action
MAKE_NOT_TRANSFORM = frozenset({"sure", "certain"})
WH_WORDS = frozenset({"what", "which", "who", "whom", "whose", "when", "where", "why", "how"})
#Words a command can start with before its verb, which the small model sometimes mistags
LEAD_WORDS = frozenset({"please", "hey", "hi", "hello", "ok", "okay", "so", "now", "also", "then"})
#Objects that are the user, not the thing acted on ("help ME", "tell US")
SELF_PRONOUNS = frozenset({"i", "me", "we", "us", "myself", "ourselves"})
OBJECT_DEPS = ("dobj", "obj", "appos")
#Common function words of Spanish, French, German, Italian and Portuguese that aren't English words.
#en_core_web_sm parses other languages as broken English, so their "actions" are noise
FOREIGN_WORDS = frozenset({
    "el", "la", "los", "las", "una", "por", "para", "que", "mi", "sobre", "del", "y", "es", "muy", "pero", "gracias",
    "le", "les", "des", "et", "une", "sur", "est", "pour", "avec", "dans", "du", "au", "ce", "qui", "merci",
    "der", "die", "das", "und", "ein", "eine", "einen", "mit", "ist", "nicht", "für", "über", "bitte",
    "il", "di", "che", "per", "della", "con", "sono", "grazie", "um", "uma", "não", "com", "obrigado",
})

@dataclass(frozen=True)
class Action:
    actionClass: str #a key of ACTION_CLASSES, QUESTION or UNCLEAR
    verb: str #lemma of the verb that carries the request, e.g. "fix" or "come up"
    object: str | None #what it acts on, e.g. "this bug"; None if the prompt doesn't say
    sentence: str
    objectHead: str | None = None #lemma of the object's main noun ("bug"); None for pronouns and clauses
    objectNames: tuple[str, ...] = () #proper nouns in the object ("french", "revolution"), lowercased

@dataclass
class Intent:
    actions: list[Action] = field(default_factory=list)
    hasAlternatives: bool = False #two actions joined by "or" ("fix X or rewrite Y")
    isEnglish: bool = True #False = not parsed, the English model can't read the prompt

    @property
    def primary(self) -> Action | None:
        return self.actions[0] if self.actions else None

    @property
    def isMultiIntent(self) -> bool:
        return len(self.actions) > 1

#True unless the prompt has more non-English function words than English stop words
def looksEnglish(doc) -> bool:
    words = [token.lower_ for token in doc if token.is_alpha]
    foreign = sum(word in FOREIGN_WORDS for word in words)
    return foreign == 0 or sum(token.is_stop for token in doc if token.is_alpha) > foreign

"""
* @brief Finds the verb a sentence's request starts from, before wrapper verbs are walked past.
* @post
* 1. Normally this is the sentence's root verb.
* 2. If the root has a subject other than "you" ("it's really bugging me", "I was wondering if"),
*    the clause addressed to "you" is used instead ("could you help me fix this").
* 3. If the root isn't a verb but the first real word is a known action verb, that word is used
*    (en_core_web_sm tags "List 5 causes..." as a noun and "Debug this code" as a proper noun).
"""
def findAnchorVerb(sentence):
    root = sentence.root
    subjects = [child for child in root.children if child.dep_ in ("nsubj", "nsubjpass")]
    if subjects and all(subject.lower_ != "you" for subject in subjects) and root.lemma_.lower() not in WANT_VERBS:
        addressed = next((token.head for token in sentence
                          if token.dep_ == "nsubj" and token.lower_ == "you" and token.head.pos_ in ("VERB", "AUX")), None)
        if addressed is not None:
            return addressed
    if root.pos_ not in ("VERB", "AUX"):
        first = next((token for token in sentence
                      if token.is_alpha and token.pos_ != "INTJ" and token.lower_ not in LEAD_WORDS), None)
        if first is not None and first.lemma_.lower() in VERB_CLASS:
            return first
    return root

#Walks past wrapper verbs to the verb they wrap ("help me fix" -> fix)
def unwrap(verb):
    while verb.lemma_.lower() in WRAPPER_VERBS:
        inner = next((child for child in verb.children if child.dep_ in ("xcomp", "ccomp") and child.pos_ == "VERB"), None)
        if inner is None:
            break
        verb = inner
    return verb

"""
* @brief Tells whether a sentence asks a question rather than requesting a task.
* @post
* 1. "Can you / could you / would you X?" is a polite request, not a question, wherever it sits
*    in the sentence ("I was wondering if you could help me...?").
* 2. Otherwise a sentence ending in "?" or starting with a wh-word is a question.
"""
def isQuestion(sentence, anchor) -> bool:
    politeRequest = (any(child.dep_ == "aux" and child.tag_ == "MD" for child in anchor.children)
                     and any(child.dep_ == "nsubj" and child.lower_ == "you" for child in anchor.children))
    if politeRequest:
        return False
    firstWord = next((token for token in sentence if token.is_alpha and token.pos_ != "INTJ"), None)
    return sentence.text.rstrip().endswith("?") or (firstWord is not None and firstWord.lower_ in WH_WORDS)

"""
* @brief Tells whether a sentence is directed at the model (a command or a request).
* @post
* 1. Commands have no subject ("Write a poem."), so a root with no nsubj counts.
* 2. Requests have "you" as the subject ("Can you...", "I need you to...").
* 3. "I need / want / would like ..." is a request too.
* 4. A mistagged command verb found by findAnchorVerb counts ("List 5 causes" parses as "List" being
*    the subject of "causes").
* 5. Statements about the user or the world ("I have a knee injury.") don't count.
"""
def isDirective(sentence, anchor) -> bool:
    root = sentence.root
    if any(token.dep_ == "nsubj" and token.lower_ == "you" for token in sentence):
        return True
    if anchor.i != root.i and anchor.pos_ not in ("VERB", "AUX"):
        return True
    if root.lemma_.lower() in WANT_VERBS and any(child.dep_ == "nsubj" and child.lower_ in SELF_PRONOUNS for child in root.children):
        return True
    return not any(child.dep_ in ("nsubj", "nsubjpass") for child in root.children)

"""
* @brief Finds the text an action verb acts on, and the lemma of its main noun.
* @post
* 1. A direct object is preferred, returned with its modifiers ("a Python function").
* 2. Objects that are the user ("help ME") are skipped.
* 3. Questions built on "be" ("Is Python faster...", "What is the capital...") use the subject.
* 4. "make it shorter" uses the subject of the adjective ("it").
* 5. Without one, the object of "with"/"about"/"on" ("help me with my essay") is used,
*    then a clause the verb takes ("explain why this returns undefined").
* 6. Returns (phrase span, head token); the head is None for clauses. (None, None) if nothing is found.
"""
def findObject(verb) -> tuple[Span | None, Token | None]:
    def usable(token) -> bool:
        return token.lower_ not in SELF_PRONOUNS and token.lower_ not in WH_WORDS

    children = list(verb.children)
    candidates = [child for child in children if child.dep_ in OBJECT_DEPS and usable(child)]
    if not candidates and verb.lemma_ == "make":
        candidates = [grandchild for child in children if child.dep_ == "ccomp" and child.pos_ == "ADJ"
                      for grandchild in child.children if grandchild.dep_ == "nsubj"]
    if not candidates and verb.lemma_ == "be":
        candidates = [child for child in children if child.dep_ in ("nsubj", "attr") and usable(child)]
    if not candidates:
        candidates = [grandchild for child in children if child.dep_ == "prep" and child.lower_ in ("with", "about", "on")
                      for grandchild in child.children if grandchild.dep_ == "pobj"]
    #A mistagged command verb hangs off the noun it acts on ("List" <- "5 causes")
    if not candidates and verb.pos_ not in ("VERB", "AUX") and verb.head.i != verb.i and verb.head.pos_ in ("NOUN", "PROPN"):
        phrase = nounPhrase(verb.head)
        return verb.doc[max(phrase.start, verb.i + 1):phrase.end], verb.head
    if candidates:
        return nounPhrase(candidates[0]), candidates[0]
    clause = next((child for child in children if child.dep_ == "ccomp"), None)
    if clause is not None:
        return clause.doc[clause.left_edge.i:clause.right_edge.i + 1], None
    return None, None

#The noun chunk a token heads ("a Python function"), or just the token ("this"),
#stretched over nouns joined to it ("React and Vue") so no compared item is lost
def nounPhrase(token) -> Span:
    def chunkOf(word):
        return next((chunk for chunk in word.doc.noun_chunks if chunk.root == word), word.doc[word.i:word.i + 1])

    first = chunkOf(token)
    last = first
    for conjunct in token.conjuncts:
        if conjunct.i > token.i and conjunct.pos_ in ("NOUN", "PROPN"):
            last = chunkOf(conjunct)
    return token.doc[first.start:max(first.end, last.end)]

"""
* @brief For "Give me a summary of X" / "I need an explanation of X", finds X.
* @post
* 1. The noun names the action (NOUN_CLASS), so what must survive a rewrite is what follows "of".
* 2. Returns the whole phrase ("a quick summary of the French Revolution") and X's head token,
*    or None if the noun has no "of" phrase.
"""
def nominalObject(verb) -> tuple[Span, Token] | None:
    noun = next((child for child in verb.children if child.dep_ in OBJECT_DEPS), None)
    if noun is None:
        return None
    topic = next((grandchild for child in noun.children if child.dep_ == "prep" and child.lower_ == "of"
                  for grandchild in child.children if grandchild.dep_ == "pobj"), None)
    if topic is None:
        return None
    return noun.doc[noun.left_edge.i:noun.right_edge.i + 1], topic

#Lemma of a noun a rewrite must keep, or None for pronouns and stop words ("this", "it")
def namedLemma(token: Token | None) -> str | None:
    if token is None or token.pos_ not in ("NOUN", "PROPN") or token.is_stop:
        return None
    return token.lemma_.lower()

#The verb's lemma, with its particle for phrasal verbs ("come up")
def verbName(verb) -> str:
    particle = next((child.lower_ for child in verb.children if child.dep_ == "prt"), None)
    lemma = verb.lemma_.lower()
    return f"{lemma} {particle}" if particle and (lemma, particle) in PHRASAL_CLASS else lemma

"""
* @brief Works out the action class of a verb in context.
* @post
* 1. Questions are QUESTION, whatever their verb.
* 2. "make" with an adjective ("make it shorter") is transform, except "make sure".
* 3. Phrasal verbs map through PHRASAL_CLASS, then single verbs through VERB_CLASS.
* 4. "I need X" / "Give me X" with no inner verb takes its class from the noun ("a summary" is extract),
*    and is generate for any other noun ("a workout plan").
* 5. A request to the model whose verb isn't known ("help me with...") is UNCLEAR.
* 6. Anything else (a constraint like "Keep it short", or context) returns None.
"""
def classifyVerb(verb, question: bool, wrapped: bool) -> str | None:
    lemma = verb.lemma_.lower()
    if question:
        return QUESTION
    if lemma == "make":
        complement = next((child for child in verb.children if child.dep_ in ("ccomp", "oprd", "acomp") and child.pos_ == "ADJ"), None)
        if complement is not None:
            return None if complement.lower_ in MAKE_NOT_TRANSFORM else "transform"
    name = verbName(verb)
    if " " in name:
        return PHRASAL_CLASS[tuple(name.split())]
    if lemma in VERB_CLASS:
        return VERB_CLASS[lemma]
    if lemma in WANT_VERBS | PROVIDE_VERBS:
        span, head = findObject(verb)
        if span is not None:
            return NOUN_CLASS.get(namedLemma(head), "generate")
    if wrapped:
        return UNCLEAR
    return None

"""
* @brief Finds what a prompt asks the model to do: each action's class, verb and object.
* @post
* 1. Code blocks are removed first, so code isn't parsed as English.
* 2. A prompt that isn't English returns an Intent with isEnglish False and no actions.
* 3. Each sentence's request verb is found past polite wrappers ("could you please help me fix").
* 4. Negated verbs ("don't write code") are constraints, not actions, and are skipped.
* 5. Verbs joined to the request by "and"/"or" are separate actions; "or" sets hasAlternatives.
* 6. Sentences that only add context or constraints ("Keep it short.", "I have a knee injury.") add nothing.
* 7. "make it short" next to another action is a constraint on that action, not a task of its own.
* 8. An UNCLEAR action about nothing named ("help me with that") is dropped when a clear action exists.
* 9. Returns None if the spaCy model isn't installed, and an empty Intent for an empty prompt.
"""
def detectIntent(prompt: str) -> Intent | None:
    nlp = loadNlp()
    if nlp is None:
        return None
    text = CODE_BLOCK_RE.sub("\n", prompt.replace("’", "'"))
    intent = Intent()
    if not text.strip():
        return intent
    doc = nlp(text)
    if not looksEnglish(doc):
        intent.isEnglish = False
        return intent

    for sentence in doc.sents:
        anchor = findAnchorVerb(sentence)
        verb = unwrap(anchor)
        question = isQuestion(sentence, anchor)
        wrapped = verb.i != anchor.i or anchor.lemma_.lower() in WRAPPER_VERBS
        if not question and not isDirective(sentence, anchor):
            continue
        for current in [verb] + [child for child in verb.children if child.dep_ == "conj" and child.pos_ == "VERB"]:
            if any(child.dep_ == "neg" for child in current.children):
                continue
            isMain = current.i == verb.i
            #Only the main verb can be UNCLEAR: "help me fix this and keep it short" has one action, not two
            actionClass = classifyVerb(current, question, wrapped and isMain)
            if actionClass is None:
                continue
            if not isMain and any(child.dep_ == "cc" and child.lower_ == "or" for child in verb.children):
                intent.hasAlternatives = True
            span, head = findObject(current)
            if current.lemma_.lower() in WANT_VERBS | PROVIDE_VERBS and namedLemma(head) in NOUN_CLASS:
                span, head = nominalObject(current) or (span, None)
            intent.actions.append(Action(
                actionClass, verbName(current),
                span.text.strip().rstrip(":;,.").strip() or None if span is not None else None,
                sentence.text.strip(), namedLemma(head),
                tuple(dict.fromkeys(token.lemma_.lower() for token in span if token.pos_ == "PROPN")) if span is not None else ()))

    if any(action.verb != "make" for action in intent.actions):
        intent.actions = [action for action in intent.actions if not (action.verb == "make" and action.actionClass == "transform")]
    #"...Could you help me out with that?" after a clear request only points back at it
    if any(action.actionClass != UNCLEAR for action in intent.actions):
        intent.actions = [action for action in intent.actions if action.actionClass != UNCLEAR or action.objectHead]
    return intent

"""
* @brief Describes a prompt's actions as short "must preserve" lines for the Optimizer.
* @post
* 1. Each action becomes a "task:" line with its verb and object.
* 2. Questions say what the question is about, so turning one into a command stays allowed.
* 3. UNCLEAR actions say the prompt doesn't state the action, so the Optimizer doesn't guess one.
* 4. Alternatives ("or") get their own line, so the rewrite doesn't turn them into "and".
"""
def describeIntent(intent: Intent | None) -> list[str]:
    if intent is None:
        return []
    lines = []
    for action in intent.actions:
        target = f' "{action.object}"' if action.object else ""
        if action.actionClass == QUESTION:
            lines.append(f'task: answer the question "{action.sentence}"')
        elif action.actionClass == UNCLEAR:
            lines.append(f"task: {action.verb}{target} (the prompt doesn't say exactly what to do; keep it as vague, don't guess)")
        else:
            lines.append(f"task: {action.verb}{target}")
    if intent.hasAlternatives:
        lines.append('the tasks are alternatives joined by "or", not all required')
    return lines

"""
* @brief Compares the actions of an optimized rewrite against the original's. Runs locally, no API call.
* @post
* 1. Every action of the original must still be asked for in the rewrite, by the same class
*    (or a compatible one: a question may become "Explain..."). The verb itself may change ("create" -> "write").
* 2. The main noun each action acts on ("bug" in "fix this bug") and any proper noun in it
*    ("French" in "the French Revolution") must still appear in the rewrite.
* 3. UNCLEAR actions aren't checked: the rewrite may state them more plainly.
* 4. If the original offers alternatives ("or") and the rewrite doesn't, that's reported.
* 5. Nothing is checked if the spaCy model is missing or the original isn't English.
* 6. A list of readable reasons is returned (empty if every action survived), written to be passed
*    back to the Optimizer as a RejectedAttempt, like findBrokenLocks.
"""
def findIntentChanges(original: str, rewrite: str) -> list[str]:
    before = detectIntent(original)
    after = detectIntent(rewrite)
    if before is None or after is None or not before.isEnglish or original.strip() == rewrite.strip():
        return []

    rewriteClasses = {action.actionClass for action in after.actions}
    rewriteWords = contentWords(CODE_BLOCK_RE.sub("\n", rewrite))
    reasons = []
    for action in before.actions:
        if action.actionClass == UNCLEAR:
            continue
        target = f' "{action.object}"' if action.object else ""
        if not COMPATIBLE_CLASSES.get(action.actionClass, {action.actionClass}) & rewriteClasses:
            reason = (f'question dropped or turned into a different task: "{action.sentence}"' if action.actionClass == QUESTION
                      else f"task dropped or changed: the original asks to {action.verb}{target}")
        elif any(word not in rewriteWords for word in (action.objectHead, *action.objectNames) if word):
            reason = f'what the task acts on was dropped or changed: "{action.object}" (from "{action.verb}")'
        else:
            continue
        if reason not in reasons:
            reasons.append(reason)
    if before.hasAlternatives and not after.hasAlternatives:
        reasons.append('the original offers a choice between tasks ("or"), the rewrite must keep it a choice')
    return reasons


if __name__ == "__main__":
    samples = [
        "Could you please help me fix this bug?",
        "Hi there! I'd like you to translate this email into French. Keep it formal.",
        "Please rewrite my cover letter and make it shorter. Make sure to mention SQL.",
        "List 5 common causes of a slow laptop and how to fix each.",
        "How do I reverse a list in Python?",
        "Can you help me with my essay?",
        "Fix the login bug or rewrite the auth module.",
        "I need a 3-day itinerary for Rome. I don't want museums.",
        "Explain why this returns undefined:\n```javascript\nfunction getName(user) { user.name; }\n```",
    ]
    for sample in samples:
        result = detectIntent(sample)
        print(repr(sample[:70]))
        for line in describeIntent(result):
            print(f"  {line}")
        print(f"  multi={result.isMultiIntent} alternatives={result.hasAlternatives}\n")

    print(findIntentChanges("Explain how recursion works.", "Write a function that uses recursion."))
    print(findIntentChanges("Fix the login bug or rewrite the auth module.", "Fix the login bug and rewrite the auth module."))
