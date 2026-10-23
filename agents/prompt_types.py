import re
from dataclasses import dataclass

#Auditor rule checks a type can switch off (names the Auditor will look up in skipChecks)
CHECK_TOKEN_RATIO = "token_ratio" #fires on code, URLs and identifiers, which naturally use more tokens per word
CHECK_READABILITY = "readability" #textstat formulas are built for prose
CHECK_ADVERBS = "adverbs" #spaCy adverb share, meaningless inside code

STRONG_POINTS = 2 #one strong signal is enough on its own
WEAK_POINTS = 1 #weak signals ("policy", "style") need a second one, so one passing mention doesn't change the type
MIN_POINTS = 2
MIN_STEPS = 2 #numbered lines needed to count as a step list
DEFAULT_TYPE = "conversational"

def wordsRegex(words: list[str]) -> re.Pattern:
    #Matches any of the words as whole words, ignoring case
    return re.compile(r"\b(?:" + "|".join(map(re.escape, words)) + r")\b", re.IGNORECASE)

#Same patterns as locks.py
CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
URL_RE = re.compile(r"https?://[^\s)>\]]+")
STEP_RE = re.compile(r"^\s*(?:\d+[.)]|step\s+\d+[:.)]?)\s+\S", re.IGNORECASE | re.MULTILINE)
CODE_SYNTAX_RE = re.compile(
    r"\bdef \w+\(|\bfunction\s*\w*\s*\(|\bclass \w+\s*[:({]|\bimport \w+|\bconst \w+\s*=|=>|"
    r"console\.log|System\.out|#include|Traceback \(most recent call last\)")
SQL_RE = re.compile(r"\bSELECT\b[\s\S]+?\bFROM\b") #uppercase only, so "select a book from the shelf" isn't SQL
FILE_RE = re.compile(r"\b[\w-]+\.(?:py|js|jsx|ts|tsx|java|go|rb|cpp|cs|php|sql|rs|sh|json|ya?ml|html|css)\b")

#Signals per type: (pattern, points). Weak keyword lists only count distinct words, so repeating one doesn't add up
SIGNALS: dict[str, list[tuple[re.Pattern, int]]] = {
    "security": [
        (wordsRegex(["gdpr", "hipaa", "pci", "pii", "soc 2", "sql injection", "xss", "csrf", "credentials",
                     "api key", "encryption", "compliance", "audit trail", "access control"]), STRONG_POINTS),
        (wordsRegex(["security", "secure", "password", "passwords", "policy", "audit", "privacy", "sensitive",
                     "confidential", "permission", "permissions", "vulnerability", "injection",
                     "authentication", "authorization"]), WEAK_POINTS),
    ],
    "code": [
        (CODE_BLOCK_RE, STRONG_POINTS),
        (CODE_SYNTAX_RE, STRONG_POINTS),
        (SQL_RE, STRONG_POINTS),
        (FILE_RE, STRONG_POINTS),
        (INLINE_CODE_RE, WEAK_POINTS),
        (wordsRegex(["code", "function", "script", "bug", "compile", "api", "endpoint", "database", "query",
                     "python", "javascript", "typescript", "java", "sql", "regex", "refactor", "debug",
                     "variable", "unit test", "stack trace"]), WEAK_POINTS),
    ],
    "workflow": [
        (wordsRegex(["workflow", "checklist", "procedure", "step by step", "step-by-step"]), STRONG_POINTS),
        (wordsRegex(["step", "steps", "process", "otherwise", "finally", "afterwards", "followed by",
                     "in that case", "if not", "once done"]), WEAK_POINTS),
    ],
    "research": [
        (wordsRegex(["cite", "citation", "citations", "references", "bibliography", "peer-reviewed",
                     "according to"]), STRONG_POINTS),
        (URL_RE, WEAK_POINTS),
        (wordsRegex(["source", "sources", "study", "studies", "research", "paper", "article", "evidence",
                     "summarize", "summary", "fact-check", "statistics"]), WEAK_POINTS),
    ],
    "creative": [
        (wordsRegex(["poem", "story", "haiku", "lyrics", "song", "screenplay", "novel", "slogan", "tagline",
                     "brand voice"]), STRONG_POINTS),
        (wordsRegex(["creative", "tone", "voice", "style", "character", "plot", "brand", "playful",
                     "imaginative", "narrative", "blog post", "caption", "brainstorm"]), WEAK_POINTS),
    ],
}

@dataclass(frozen=True)
class TypeProfile:
    strictness: int #higher wins when a prompt has several types
    passScore: int #Validator score (1-10) a rewrite needs to pass
    skipChecks: frozenset[str] #Auditor rule checks that misfire on this type
    optimizerRules: str #what the Optimizer may and may not cut, added to its message
    optimize: bool = True #False = leave prompts of this type as they are

PROFILES: dict[str, TypeProfile] = {
    "security": TypeProfile(
        strictness=6, passScore=8, skipChecks=frozenset(),
        optimizerRules=("Security/compliance prompt: never remove or soften a requirement, restriction, policy, "
                        "compliance term or audit requirement. Only remove politeness and filler.")),
    "code": TypeProfile(
        strictness=5, passScore=8, skipChecks=frozenset({CHECK_TOKEN_RATIO, CHECK_READABILITY, CHECK_ADVERBS}),
        optimizerRules=("Code prompt: never change code, identifiers, types, error handling or conditions. "
                        "Only shorten explanations, framing and examples.")),
    "workflow": TypeProfile(
        strictness=4, passScore=7, skipChecks=frozenset(),
        optimizerRules=("Workflow prompt: keep every step, its order and every if/otherwise condition. "
                        "Only shorten the wording inside steps.")),
    "research": TypeProfile(
        strictness=3, passScore=7, skipChecks=frozenset({CHECK_TOKEN_RATIO}),
        optimizerRules=("Research prompt: keep every source, link and citation or attribution requirement. "
                        "Only shorten the framing around them.")),
    "creative": TypeProfile(
        strictness=2, passScore=6, skipChecks=frozenset(),
        optimizerRules=("Creative prompt: keep every style, voice, tone and brand rule. "
                        "Only remove filler and repeated examples.")),
    "conversational": TypeProfile(
        strictness=1, passScore=6, skipChecks=frozenset(),
        optimizerRules="Conversational prompt: rewording is fine as long as the tone and the request stay the same."),
}

"""
* @brief Finds which signals of each type appear in a prompt (useful for debugging and tuning on labeled prompts).
* @post
* 1. Every type's patterns are searched; keyword lists record each distinct matched word once.
* 2. Two or more numbered lines count as a strong workflow signal ("numbered steps").
* 3. Returns {type: [(signal text, points), ...]} for types with at least one match.
"""
def detectSignals(prompt: str) -> dict[str, list[tuple[str, int]]]:
    prompt = prompt.replace("’", "'")
    found: dict[str, list[tuple[str, int]]] = {}
    for promptType, patterns in SIGNALS.items():
        hits = []
        for pattern, points in patterns:
            matches = {" ".join(match.group(0).lower().split())[:40] for match in pattern.finditer(prompt)}
            hits += [(match, points) for match in sorted(matches)]
        if promptType == "workflow" and len(STEP_RE.findall(prompt)) >= MIN_STEPS:
            hits.append(("numbered steps", STRONG_POINTS))
        if hits:
            found[promptType] = hits
    return found

"""
* @brief Detects every type a prompt belongs to.
* @post
* 1. A type matches when its signals add up to MIN_POINTS (one strong signal, or two different weak ones).
* 2. Several types can match ("write a Python function that checks passwords" is code and security).
* 3. Types are returned strictest first; ["conversational"] if nothing matches.
"""
def detectPromptTypes(prompt: str) -> list[str]:
    signals = detectSignals(prompt)
    types = [promptType for promptType, hits in signals.items() if sum(points for _, points in hits) >= MIN_POINTS]
    if not types:
        return [DEFAULT_TYPE]
    return sorted(types, key=lambda promptType: PROFILES[promptType].strictness, reverse=True)

"""
* @brief Merges the profiles of several types into one, with the strictest setting winning.
* @post
* 1. passScore and strictness are the highest of the types.
* 2. skipChecks is every check any type skips (a check that misfires on one type isn't trusted for the mix).
* 3. optimizerRules lists every type's rules, strictest first.
* 4. optimize is True only if every type allows optimizing.
* 5. An empty list is treated as ["conversational"].
"""
def combineProfiles(types: list[str]) -> TypeProfile:
    profiles = sorted((PROFILES[promptType] for promptType in types or [DEFAULT_TYPE]),
                      key=lambda profile: profile.strictness, reverse=True)
    return TypeProfile(
        strictness=profiles[0].strictness,
        passScore=max(profile.passScore for profile in profiles),
        skipChecks=frozenset().union(*(profile.skipChecks for profile in profiles)),
        optimizerRules="\n".join(profile.optimizerRules for profile in profiles),
        optimize=all(profile.optimize for profile in profiles),
    )


if __name__ == "__main__":
    samples = [
        "Write a Python function that checks a user's password. Never log the password. Must follow our GDPR policy.",
        "Please, could you kindly write me a short poem about the ocean? Thank you so much!",
        "Summarize this article and cite your sources: https://example.com/study",
        "1. Pull the latest data.\n2. Remove duplicates.\n3. If the file is empty, stop. Otherwise email the report.",
        "hey what's a good name for my cat",
    ]
    for sample in samples:
        detected = detectPromptTypes(sample)
        profile = combineProfiles(detected)
        print(f"{sample[:60]!r}\n  types={detected} passScore={profile.passScore} "
              f"skipChecks={sorted(profile.skipChecks)}\n  signals={detectSignals(sample)}\n")
