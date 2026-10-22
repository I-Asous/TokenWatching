import re
from dataclasses import dataclass, field
from agents.auditor import loadNlp
from agents.prompt_types import CODE_BLOCK_RE

#Action classes and the verbs (lemmas) that signal them
ACTION_CLASSES: dict[str, frozenset[str]] = {
    "generate": frozenset({"write", "create", "generate", "draft", "build", "make", "design", "compose", "produce",
                           "suggest", "propose", "brainstorm", "plan"}),
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

QUESTION = "question" #a question to answer, not a task ("What is...?", "How do I...?")
UNCLEAR = "unclear" #a request whose action can't be told from the words ("Can you help me with my essay?")

#Verbs that wrap the real request: "help me FIX", "I need you to SUMMARIZE", "I'd like you to TRANSLATE"
WRAPPER_VERBS = frozenset({"help", "need", "want", "like", "love", "try", "wonder", "ask"})
#"I need / want / would like X" with a noun and no inner verb is a request to produce X
WANT_VERBS = frozenset({"need", "want", "like", "love"})
#"make it shorter" transforms, but "make sure ..." is a constraint, not an action
MAKE_NOT_TRANSFORM = frozenset({"sure", "certain"})
WH_WORDS = frozenset({"what", "which", "who", "whom", "whose", "when", "where", "why", "how"})
#Words a command can start with before its verb, which the small model sometimes mistags
LEAD_WORDS = frozenset({"please", "hey", "hi", "hello", "ok", "okay", "so", "now", "also", "then"})
#Objects that are the user, not the thing acted on ("help ME", "tell US")
SELF_PRONOUNS = frozenset({"i", "me", "we", "us", "myself", "ourselves"})
OBJECT_DEPS = ("dobj", "obj", "appos")

@dataclass(frozen=True)
class Action:
    actionClass: str #a key of ACTION_CLASSES, QUESTION or UNCLEAR
    verb: str #lemma of the verb that carries the request, e.g. "fix"
    object: str | None #what it acts on, e.g. "this bug"; None if the prompt doesn't say
    sentence: str

@dataclass
class Intent:
    actions: list[Action] = field(default_factory=list)
    hasAlternatives: bool = False #two actions joined by "or" ("fix X or rewrite Y")

    @property
    def primary(self) -> Action | None:
        return self.actions[0] if self.actions else None

    @property
    def isMultiIntent(self) -> bool:
        return len(self.actions) > 1

"""
* @brief Finds the token that carries a sentence's request.
* @post
* 1. Normally this is the sentence's root verb.
* 2. If the root isn't a verb but the first real word is a known action verb, that word is used
*    (en_core_web_sm tags "List 5 causes..." as a noun and "Debug this code" as a proper noun).
* 3. Wrapper verbs are walked past to the verb they wrap ("help me fix" -> fix).
"""
def findActionVerb(sentence):
    verb = sentence.root
    if verb.pos_ not in ("VERB", "AUX"):
        first = next((token for token in sentence
                      if token.is_alpha and token.pos_ != "INTJ" and token.lower_ not in LEAD_WORDS), None)
        if first is not None and first.lemma_.lower() in VERB_CLASS:
            verb = first
    while verb.lemma_.lower() in WRAPPER_VERBS:
        inner = next((child for child in verb.children if child.dep_ in ("xcomp", "ccomp") and child.pos_ == "VERB"), None)
        if inner is None:
            break
        verb = inner
    return verb

"""
* @brief Tells whether a sentence asks a question rather than requesting a task.
* @post
* 1. "Can you / could you / would you X?" is a polite request, not a question.
* 2. Otherwise a sentence ending in "?" or starting with a wh-word is a question.
"""
def isQuestion(sentence) -> bool:
    root = sentence.root
    politeRequest = (any(child.dep_ == "aux" and child.tag_ == "MD" for child in root.children)
                     and any(child.dep_ == "nsubj" and child.lower_ == "you" for child in root.children))
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
* 4. Statements about the user or the world ("I have a knee injury.") don't count.
"""
def isDirective(sentence) -> bool:
    root = sentence.root
    if any(token.dep_ == "nsubj" and token.lower_ == "you" for token in sentence):
        return True
    if root.lemma_.lower() in WANT_VERBS and any(child.dep_ == "nsubj" and child.lower_ in SELF_PRONOUNS for child in root.children):
        return True
    return not any(child.dep_ in ("nsubj", "nsubjpass") for child in root.children)

"""
* @brief Finds the text an action verb acts on.
* @post
* 1. A direct object is preferred, returned with its modifiers ("a Python function").
* 2. Objects that are the user ("help ME") are skipped.
* 3. Questions built on "be" ("Is Python faster...", "What is the capital...") use the subject.
* 4. "make it shorter" uses the subject of the adjective ("it").
* 5. Without one, the object of "with"/"about"/"on" ("help me with my essay") is used,
*    then a clause the verb takes ("explain why this returns undefined").
* 6. None is returned if nothing is found.
"""
def findObject(verb) -> str | None:
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
    if candidates:
        return nounPhrase(candidates[0])
    clause = next((child for child in children if child.dep_ == "ccomp"), None)
    if clause is not None:
        span = clause.doc[clause.left_edge.i:clause.right_edge.i + 1]
        return span.text.strip().rstrip(":;,.").strip() or None
    return None

#The noun chunk a token heads ("a Python function"), or just the token ("this"),
#stretched over nouns joined to it ("React and Vue") so no compared item is lost
def nounPhrase(token) -> str:
    def chunkOf(word):
        return next((chunk for chunk in word.doc.noun_chunks if chunk.root == word), word.doc[word.i:word.i + 1])

    first = chunkOf(token)
    last = first
    for conjunct in token.conjuncts:
        if conjunct.i > token.i and conjunct.pos_ in ("NOUN", "PROPN"):
            last = chunkOf(conjunct)
    return token.doc[first.start:max(first.end, last.end)].text

"""
* @brief Works out the action class of a verb in context.
* @post
* 1. Questions are QUESTION, whatever their verb.
* 2. "make" with an adjective ("make it shorter") is transform, except "make sure".
* 3. "I need / want / would like X" with no inner verb is generate.
* 4. Known verbs map through VERB_CLASS.
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
    if lemma in VERB_CLASS:
        return VERB_CLASS[lemma]
    if lemma in WANT_VERBS and findObject(verb):
        return "generate"
    if wrapped:
        return UNCLEAR
    return None

"""
* @brief Finds what a prompt asks the model to do: each action's class, verb and object.
* @post
* 1. Code blocks are removed first, so code isn't parsed as English.
* 2. Each sentence's request verb is found past polite wrappers ("could you please help me fix").
* 3. Negated verbs ("don't write code") are constraints, not actions, and are skipped.
* 4. Verbs joined to the request by "and"/"or" are separate actions; "or" sets hasAlternatives.
* 5. Sentences that only add context or constraints ("Keep it short.", "I have a knee injury.") add nothing.
* 6. Returns None if the spaCy model isn't installed, and an empty Intent for an empty prompt.
"""
def detectIntent(prompt: str) -> Intent | None:
    nlp = loadNlp()
    if nlp is None:
        return None
    text = CODE_BLOCK_RE.sub("\n", prompt.replace("’", "'"))
    intent = Intent()
    if not text.strip():
        return intent

    for sentence in nlp(text).sents:
        verb = findActionVerb(sentence)
        question = isQuestion(sentence)
        wrapped = verb.lemma_.lower() in WRAPPER_VERBS or verb != sentence.root
        if not question and not isDirective(sentence):
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
            intent.actions.append(Action(actionClass, current.lemma_.lower(), findObject(current), sentence.text.strip()))
    return intent


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
        for action in result.actions:
            print(f"  {action.actionClass:10} verb={action.verb!r} object={action.object!r}")
        print(f"  multi={result.isMultiIntent} alternatives={result.hasAlternatives}\n")
